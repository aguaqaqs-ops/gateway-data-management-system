"""Startup reconciliation for synchronous create/upload mutation effects."""

from __future__ import annotations

import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import UUID

from gateway_repository_contracts import OperationStatus, REPOSITORY_IMPORT_MEDIA_TYPE

from gateway_repository_service.create_repository.visibility import (
    DEFAULT_REF,
    create_repository_matches_ledger_full,
    has_published_repository_tree,
    read_published_repository_head_strict,
)
from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.mutation_fingerprints import parse_upload_artifact_fingerprint_v1
from gateway_repository_service.mutation_store import (
    ArtifactLifecycleRecord,
    EffectStatus,
    MutationKind,
    MutationStore,
    StoredEffectView,
)
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.visibility import (
    has_published_artifact_file,
    has_ready_artifact_size,
)
from gateway_repository_service.versioned_import.store import ImportOperationStore
from gateway_repository_service.versioned_import.models import IMPORT_ADMISSION_PENDING_STATUS


class ReconciliationError(RuntimeError):
    """Raised when startup reconciliation cannot complete safely."""


@dataclass(frozen=True, slots=True)
class ConsistencyWatch:
    create_repository_ids: tuple[UUID, ...]
    upload_artifacts: tuple[tuple[UUID, UUID, int], ...]


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    blocking_failures: tuple[str, ...]
    consistency_watch: ConsistencyWatch


def build_consistency_watch(mutation_store: MutationStore) -> ConsistencyWatch:
    create_repository_ids: list[UUID] = []
    upload_artifacts: list[tuple[UUID, UUID, int]] = []
    for effect in mutation_store.iter_effects_by_status(EffectStatus.SUCCEEDED):
        if effect.scope.mutation_kind == MutationKind.CREATE_REPOSITORY:
            create_repository_ids.append(effect.resource_id)
            continue
        repository_id = effect.scope.repository_id
        if repository_id is None:
            continue
        lifecycle = mutation_store.get_artifact_lifecycle(effect.resource_id)
        if lifecycle is None:
            continue
        upload_artifacts.append((repository_id, effect.resource_id, lifecycle.size_bytes))
    return ConsistencyWatch(
        create_repository_ids=tuple(create_repository_ids),
        upload_artifacts=tuple(upload_artifacts),
    )


@dataclass
class MutableConsistencyWatch:
    """Thread-safe, monotonic consistency watch for runtime readiness probes."""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _create_repository_ids: set[UUID] = field(default_factory=set, repr=False)
    _upload_artifacts: dict[tuple[UUID, UUID], int] = field(default_factory=dict, repr=False)

    def register_succeeded_create(self, repository_id: UUID) -> None:
        with self._lock:
            self._create_repository_ids.add(repository_id)

    def register_succeeded_upload(
        self,
        repository_id: UUID,
        artifact_id: UUID,
        size_bytes: int,
    ) -> None:
        with self._lock:
            self._upload_artifacts[(repository_id, artifact_id)] = size_bytes

    def snapshot(self) -> ConsistencyWatch:
        with self._lock:
            return ConsistencyWatch(
                create_repository_ids=tuple(self._create_repository_ids),
                upload_artifacts=tuple(
                    (repository_id, artifact_id, size_bytes)
                    for (repository_id, artifact_id), size_bytes in self._upload_artifacts.items()
                ),
            )

    @classmethod
    def from_watch(cls, watch: ConsistencyWatch) -> MutableConsistencyWatch:
        mutable = cls()
        mutable._create_repository_ids = set(watch.create_repository_ids)
        mutable._upload_artifacts = {
            (repository_id, artifact_id): size_bytes
            for repository_id, artifact_id, size_bytes in watch.upload_artifacts
        }
        return mutable


def upload_artifact_bytes_reconciled_after_import(
    import_store: ImportOperationStore,
    mutation_store: MutationStore,
    repository_id: UUID,
    artifact_id: UUID,
    *,
    ttl_seconds: int,
    now: datetime | None = None,
) -> bool:
    """Return True when missing ready bytes are explained by legal retention cleanup."""

    from gateway_repository_service.artifact_retention import (
        retention_explains_missing_ready_bytes,
    )

    lifecycle = mutation_store.get_artifact_lifecycle(artifact_id)
    if lifecycle is None:
        return False
    if lifecycle.repository_id != repository_id:
        return False

    references = import_store.list_artifact_references(artifact_id)
    consumed_operation_artifact_id: UUID | None = None
    if lifecycle.consumed_by_operation_id is not None:
        operation = import_store.get_operation(
            repository_id,
            lifecycle.consumed_by_operation_id,
        )
        if operation is not None:
            consumed_operation_artifact_id = operation.artifact_id
            if operation.status != OperationStatus.SUCCEEDED:
                consumed_operation_artifact_id = None

    if retention_explains_missing_ready_bytes(
        lifecycle=lifecycle,
        repository_id=repository_id,
        references=references,
        ttl_seconds=ttl_seconds,
        now=now,
        consumed_operation_artifact_id=consumed_operation_artifact_id,
    ):
        return True

    if lifecycle.consumed_by_operation_id is None:
        return False
    if lifecycle.consumed_at is None and lifecycle.bytes_deleted_at is None:
        return False
    operation = import_store.get_operation(
        repository_id,
        lifecycle.consumed_by_operation_id,
    )
    if operation is None:
        return False
    if operation.artifact_id != artifact_id:
        return False
    if operation.status != OperationStatus.SUCCEEDED:
        return False
    for reference in references:
        if reference.operation_id == lifecycle.consumed_by_operation_id:
            continue
        if reference.is_protected:
            return False
        if reference.durable_status == IMPORT_ADMISSION_PENDING_STATUS:
            return False
        if reference.status in {
            OperationStatus.QUEUED,
            OperationStatus.RUNNING,
        }:
            return False
    return True


def filesystem_watch_failures(
    watch: ConsistencyWatch,
    layout: DurableLayout,
) -> tuple[str, ...]:
    blocking: list[str] = []
    for repository_id in watch.create_repository_ids:
        if not has_published_repository_tree(layout, repository_id):
            blocking.append(f"published repository {repository_id} is missing")
    return tuple(blocking)


def import_artifact_watch_failures(
    import_store: ImportOperationStore,
    mutation_store: MutationStore,
    watch: ConsistencyWatch,
    layout: DurableLayout,
    *,
    ttl_seconds: int,
    now: datetime | None = None,
) -> tuple[str, ...]:
    blocking: list[str] = []
    for repository_id, artifact_id, size_bytes in watch.upload_artifacts:
        if has_ready_artifact_size(
            layout,
            repository_id,
            artifact_id,
            size_bytes=size_bytes,
        ):
            continue
        if upload_artifact_bytes_reconciled_after_import(
            import_store,
            mutation_store,
            repository_id,
            artifact_id,
            ttl_seconds=ttl_seconds,
            now=now,
        ):
            continue
        blocking.append(f"ready artifact {artifact_id} is missing or truncated")

    for repository_id, artifact_id in import_store.list_protected_artifact_pins():
        lifecycle = mutation_store.get_artifact_lifecycle(artifact_id)
        if lifecycle is not None and has_published_artifact_file(
            layout,
            repository_id,
            artifact_id,
            size_bytes=lifecycle.size_bytes,
            raw_sha256=lifecycle.raw_sha256,
        ):
            continue
        blocking.append(
            f"protected import artifact {artifact_id} is missing while operation evidence is unresolved"
        )
    return tuple(blocking)


class SynchronousMutationReconciler:
    """Reconcile create/upload ledgers with filesystem evidence at startup."""

    def __init__(
        self,
        *,
        settings: RepositoryServiceSettings,
        layout: DurableLayout,
        mutation_store: MutationStore,
        import_store: ImportOperationStore,
    ) -> None:
        self._settings = settings
        self._layout = layout
        self._mutation_store = mutation_store
        self._import_store = import_store

    def reconcile(self) -> ReconciliationResult:
        for effect in self._mutation_store.iter_effects_by_status(EffectStatus.PENDING):
            if effect.terminal_not_published:
                continue
            if effect.scope.mutation_kind == MutationKind.CREATE_REPOSITORY:
                self._reconcile_pending_create(effect)
            else:
                self._reconcile_pending_upload(effect)

        return ReconciliationResult(
            blocking_failures=self.consistency_failures_full(),
            consistency_watch=build_consistency_watch(self._mutation_store),
        )

    def consistency_failures_full(self) -> tuple[str, ...]:
        return self._consistency_failures(verify_upload_sha=True)

    def consistency_failures_bounded(self) -> tuple[str, ...]:
        return self._consistency_failures(verify_upload_sha=False)

    def consistency_failures(self) -> tuple[str, ...]:
        """Backward-compatible alias for startup full consistency checks."""

        return self.consistency_failures_full()

    def _consistency_failures(self, *, verify_upload_sha: bool) -> tuple[str, ...]:
        blocking: list[str] = []
        for effect in self._mutation_store.iter_effects_by_status(EffectStatus.SUCCEEDED):
            if effect.scope.mutation_kind == MutationKind.CREATE_REPOSITORY:
                if not create_repository_matches_ledger_full(
                    settings=self._settings,
                    layout=self._layout,
                    repository_id=effect.resource_id,
                    response_body=effect.response_body,
                ):
                    blocking.append(
                        f"create effect {effect.effect_id} succeeded without matching published repository"
                    )
            else:
                repository_id = effect.scope.repository_id
                if repository_id is None:
                    blocking.append(
                        f"upload effect {effect.effect_id} has invalid repository scope"
                    )
                    continue
                lifecycle = self._mutation_store.get_artifact_lifecycle(effect.resource_id)
                if lifecycle is None:
                    blocking.append(
                        f"upload effect {effect.effect_id} succeeded without artifact lifecycle"
                    )
                    continue
                if verify_upload_sha:
                    matches = has_published_artifact_file(
                        self._layout,
                        repository_id,
                        effect.resource_id,
                        size_bytes=lifecycle.size_bytes,
                        raw_sha256=lifecycle.raw_sha256,
                    )
                else:
                    matches = has_ready_artifact_size(
                        self._layout,
                        repository_id,
                        effect.resource_id,
                        size_bytes=lifecycle.size_bytes,
                    )
                if not matches and not upload_artifact_bytes_reconciled_after_import(
                    self._import_store,
                    self._mutation_store,
                    repository_id,
                    effect.resource_id,
                    ttl_seconds=self._settings.artifact_ttl_seconds,
                ):
                    blocking.append(
                        f"upload effect {effect.effect_id} succeeded without matching ready artifact"
                    )
        return tuple(blocking)

    def _reconcile_pending_create(self, effect: StoredEffectView) -> None:
        repository_id = effect.resource_id
        if has_published_repository_tree(self._layout, repository_id):
            try:
                initial_commit_id = read_published_repository_head_strict(
                    self._settings,
                    self._layout,
                    repository_id,
                )
            except Exception as exc:
                raise ReconciliationError(
                    f"failed to read head for pending create effect {effect.effect_id}"
                ) from exc
            if initial_commit_id is None:
                raise ReconciliationError(
                    f"published repository tree exists but main head is unavailable for effect {effect.effect_id}"
                )
            response_body = {
                "repository_id": str(repository_id),
                "default_ref": DEFAULT_REF,
                "initial_commit_id": initial_commit_id,
            }
            self._mutation_store.mark_succeeded(effect.effect_id, response_body=response_body)
            return

        self._cleanup_create_staging(repository_id)
        self._assert_create_staging_absent(repository_id)
        self._mutation_store.mark_terminal_not_published(
            effect.scope,
            key_hash=effect.key_hash,
            fingerprint=effect.fingerprint,
            effect_id=effect.effect_id,
        )

    def _reconcile_pending_upload(self, effect: StoredEffectView) -> None:
        repository_id = effect.scope.repository_id
        if repository_id is None:
            return

        parsed = parse_upload_artifact_fingerprint_v1(effect.fingerprint)
        artifact_id = effect.resource_id
        if has_published_artifact_file(
            self._layout,
            repository_id,
            artifact_id,
            size_bytes=parsed.declared_size,
            raw_sha256=parsed.raw_sha256_hex,
        ):
            response_body = {
                "artifact_ref": {
                    "artifact_id": str(artifact_id),
                    "media_type": REPOSITORY_IMPORT_MEDIA_TYPE,
                    "size_bytes": parsed.declared_size,
                    "raw_sha256": parsed.raw_sha256_hex,
                }
            }
            self._mutation_store.mark_succeeded(
                effect.effect_id,
                response_body=response_body,
                artifact_lifecycle=ArtifactLifecycleRecord(
                    artifact_id=artifact_id,
                    repository_id=repository_id,
                    media_type=parsed.media_type,
                    size_bytes=parsed.declared_size,
                    raw_sha256=parsed.raw_sha256_hex,
                ),
            )
            return

        self._cleanup_upload_staging(repository_id, artifact_id)
        self._assert_upload_staging_absent(repository_id, artifact_id)
        self._mutation_store.mark_terminal_not_published(
            effect.scope,
            key_hash=effect.key_hash,
            fingerprint=effect.fingerprint,
            effect_id=effect.effect_id,
        )

    def _cleanup_create_staging(self, repository_id: UUID) -> None:
        key = repository_key(repository_id)
        pattern = f"{key}.*"
        for staged in self._layout.staging_versioned.glob(pattern):
            if staged.is_dir():
                shutil.rmtree(staged)

    def _assert_create_staging_absent(self, repository_id: UUID) -> None:
        if staging_dirs_for_repository(self._layout, repository_id):
            raise ReconciliationError(
                f"failed to remove create staging for repository {repository_id.hex}"
            )

    def _cleanup_upload_staging(self, repository_id: UUID, artifact_id: UUID) -> None:
        key = repository_key(repository_id)
        staging_dir, _ready_dir = self._layout.repository_artifact_directories(key)
        pattern = f"{artifact_id.hex}.*"
        for staged in staging_dir.glob(pattern):
            if staged.is_file():
                staged.unlink()

    def _assert_upload_staging_absent(self, repository_id: UUID, artifact_id: UUID) -> None:
        if upload_staging_files_for_artifact(self._layout, repository_id, artifact_id):
            raise ReconciliationError(
                f"failed to remove upload staging for artifact {artifact_id.hex}"
            )


def staging_dirs_for_repository(layout: DurableLayout, repository_id: UUID) -> list[Path]:
    key = repository_key(repository_id)
    return list(layout.staging_versioned.glob(f"{key}.*"))


def upload_staging_files_for_artifact(
    layout: DurableLayout,
    repository_id: UUID,
    artifact_id: UUID,
) -> list[Path]:
    key = repository_key(repository_id)
    staging_dir, _ready = layout.repository_artifact_directories(key)
    return list(staging_dir.glob(f"{artifact_id.hex}.*"))
