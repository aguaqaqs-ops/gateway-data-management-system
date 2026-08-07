"""Shared helpers for Versioned import worker tests."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_contracts import (
    OperationStatus,
    RepositoryArtifactRef,
    UnknownTypePolicy,
    VerificationPolicy,
)
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.mutation_store import IdempotencyKeyHash, configure_connection
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.errors import ImportProviderError
from gateway_repository_service.versioned_import.faults import ImportWorkerFaultInjector
from gateway_repository_service.versioned_import.locks import RepositoryLockRegistry
from gateway_repository_service.versioned_import.models import ImportRequestBinding
from gateway_repository_service.versioned_import.ports import (
    CancellationCallback,
    MarkerInspection,
    MarkerInspectionUnique,
    MarkerInspectionZero,
    PublishMainAmbiguous,
    PublishMainMismatch,
    PublishMainPublished,
    PublishMainResult,
    VersionedImportProvider,
)
from gateway_repository_service.versioned_import.store import ImportOperationStore
from gateway_repository_service.versioned_import.worker import ImportWorkerPool
from gateway_repository_service.versioned_import import versioned_import_fingerprint_v1
from gateway_repository_service.arrow_mapping import ColumnCatalog, TableCatalog
from support.lifecycle_harness import lifecycle_settings
from test_import_package import build_package_bytes, write_artifact

MEDIA_TYPE = "application/vnd.gateway.repository-import.v1+tar+zstd"
DEFAULT_MAIN_COMMIT = "commit-main"


class FakeImportProvider:
    """In-memory provider for worker orchestration tests."""

    def __init__(self, *, main_commit: str = DEFAULT_MAIN_COMMIT) -> None:
        self.refs: dict[str, str] = {"main": main_commit}
        self.markers: dict[str, tuple[str, str, tuple[str, ...]]] = {}
        self.publish_force_fail = False
        self.replay_delay_seconds = 0.0
        self.fail_on_replay = False
        self.fail_on_checkout = False
        self.replay_order: list[str] = []

    def read_ref(self, ref_name: str) -> str:
        return self.refs[ref_name]

    def create_private_ref(self, private_ref: str, expected_commit: str) -> None:
        self.refs[private_ref] = expected_commit

    def checkout_private_ref(self, private_ref: str) -> None:
        if self.fail_on_checkout:
            raise ImportProviderError("checkout private ref failed")
        if private_ref not in self.refs:
            raise RuntimeError("missing private ref")

    def replay_sql(
        self,
        private_ref: str,
        replay_path: Path,
        cancellation: CancellationCallback | None = None,
    ) -> None:
        if cancellation is not None and cancellation():
            raise RuntimeError("cancelled")
        if self.fail_on_replay:
            raise RuntimeError("replay failed")
        self.replay_order.append(private_ref)
        if self.replay_delay_seconds > 0:
            time.sleep(self.replay_delay_seconds)

    def commit_operation_marker(self, private_ref: str, marker: str) -> str:
        parent = self.refs[private_ref]
        candidate = f"candidate-{len(self.markers) + 1}"
        self.refs[private_ref] = candidate
        self.markers[marker] = (candidate, parent, (private_ref,))
        return candidate

    def inspect_marker(self, marker: str) -> MarkerInspection:
        if marker not in self.markers:
            return MarkerInspectionZero()
        candidate, parent, refs = self.markers[marker]
        return MarkerInspectionUnique(candidate=candidate, parent=parent, refs=refs)

    def read_catalog(self, candidate: str) -> tuple[TableCatalog, ...]:
        return (
            TableCatalog(
                "records",
                (ColumnCatalog("id", "BIGINT", False, 1),),
                0,
            ),
        )

    def read_type_catalog(self, candidate: str) -> tuple[TableCatalog, ...]:
        return self.read_catalog(candidate)

    def stream_table(
        self,
        candidate: str,
        table: TableCatalog,
        policy: UnknownTypePolicy,
    ) -> Iterator[pa.RecordBatch]:
        yield pa.record_batch({"id": pa.array([], type=pa.int64())})

    def publish_main(self, expected_commit: str, candidate: str) -> PublishMainResult:
        if self.refs["main"] != expected_commit:
            return PublishMainMismatch(actual=self.refs["main"])
        if self.publish_force_fail:
            return PublishMainAmbiguous()
        self.refs["main"] = candidate
        return PublishMainPublished()

    def delete_private_ref(self, private_ref: str, expected_candidate: str | None = None) -> None:
        if expected_candidate is not None and self.refs.get(private_ref) != expected_candidate:
            raise RuntimeError("candidate mismatch")
        del self.refs[private_ref]


class WorkerTestEnvironment:
    def __init__(
        self,
        tmp_path: Path,
        *,
        max_import_workers: int = 4,
        fault_injector: ImportWorkerFaultInjector | None = None,
    ) -> None:
        self.settings = lifecycle_settings(
            tmp_path,
            bearer_token="token",
        )
        self.settings = self.settings.model_copy(update={"max_import_workers": max_import_workers})
        self.layout = DurableLayout.create_for_probe(self.settings.data_root)
        db_path = self.settings.control_db_path
        ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000).close()
        self.connection = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
        configure_connection(self.connection)
        self.store = ImportOperationStore(self.connection)
        self.mutation_store = self.store.mutation_store
        self.providers: dict[UUID, FakeImportProvider] = {}
        self.locks = RepositoryLockRegistry()
        self.fault_injector = fault_injector
        self.pool = ImportWorkerPool(
            settings=self.settings,
            layout=self.layout,
            store=self.store,
            provider_factory=self._provider_factory,
            locks=self.locks,
            fault_injector=fault_injector,
        )

    def _provider_factory(self, repository_id: UUID) -> VersionedImportProvider:
        provider = self.providers.get(repository_id)
        if provider is None:
            provider = FakeImportProvider()
            self.providers[repository_id] = provider
        return provider

    def provider_for(self, repository_id: UUID) -> FakeImportProvider:
        provider = self.providers.get(repository_id)
        if provider is None:
            provider = FakeImportProvider()
            self.providers[repository_id] = provider
        return provider

    def seed_artifact(
        self,
        repository_id: UUID,
        artifact_id: UUID,
        *,
        size_bytes: int,
        raw_sha256: str,
    ) -> None:
        now = "2026-08-06T00:00:00+00:00"
        with self.store._lock:
            self.connection.execute(
                """
                INSERT INTO artifact_lifecycle (
                    artifact_id,
                    repository_scope,
                    media_type,
                    size_bytes,
                    raw_sha256,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(artifact_id),
                    repository_id.hex,
                    MEDIA_TYPE,
                    size_bytes,
                    raw_sha256,
                    now,
                    now,
                ),
            )
            self.connection.commit()

    def write_ready_artifact(
        self,
        repository_id: UUID,
        artifact_id: UUID,
        *,
        payload: bytes | None = None,
    ) -> tuple[int, str]:
        package_payload = payload or build_package_bytes()
        ready_path = artifact_ready_path(self.layout, repository_id, artifact_id)
        ready_path.parent.mkdir(parents=True, exist_ok=True)
        return write_artifact(ready_path, package_payload)

    def enqueue(
        self,
        repository_id: UUID,
        *,
        artifact_id: UUID,
        expected_commit_id: str = DEFAULT_MAIN_COMMIT,
        operation_id: UUID | None = None,
        key: str | None = None,
        verification_policy: VerificationPolicy = VerificationPolicy.STRUCTURAL,
        unknown_type_policy: UnknownTypePolicy = UnknownTypePolicy.REJECT,
    ) -> UUID:
        ready_path = artifact_ready_path(self.layout, repository_id, artifact_id)
        size_bytes, raw_sha256 = write_artifact(ready_path, build_package_bytes())
        self.seed_artifact(
            repository_id,
            artifact_id,
            size_bytes=size_bytes,
            raw_sha256=raw_sha256,
        )
        binding = ImportRequestBinding(
            repository_id=repository_id,
            artifact_ref=RepositoryArtifactRef(
                artifact_id=artifact_id,
                media_type=MEDIA_TYPE,
                size_bytes=size_bytes,
                raw_sha256=raw_sha256,
            ),
            target_ref="main",
            expected_commit_id=expected_commit_id,
            verification_policy=verification_policy,
            unknown_type_policy=unknown_type_policy,
        )
        resolved_operation_id = operation_id or uuid4()
        key_hash = IdempotencyKeyHash.from_raw_key(key or f"import-{resolved_operation_id}")
        fingerprint = versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash)
        result = self.store.claim_or_enqueue(
            binding,
            key_hash=key_hash,
            fingerprint=fingerprint,
            operation_id=resolved_operation_id,
        )
        self.pool.notify()
        return result.operation_id

    def wait_for_status(
        self,
        repository_id: UUID,
        operation_id: UUID,
        expected: OperationStatus,
        *,
        timeout: float = 5.0,
    ) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            operation = self.store.get_operation(repository_id, operation_id)
            if operation is not None and operation.status == expected:
                return
            time.sleep(0.01)
        operation = self.store.get_operation(repository_id, operation_id)
        raise AssertionError(
            f"operation {operation_id} did not reach {expected.value}, last={operation}"
        )

    def close(self) -> None:
        self.pool.stop()
        self.connection.close()


def published_repository_path(layout: DurableLayout, repository_id: UUID) -> Path:
    return layout.published_repository(repository_key(repository_id))
