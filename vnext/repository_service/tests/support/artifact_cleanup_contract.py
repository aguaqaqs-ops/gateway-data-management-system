"""Shared fixtures and seeds for cooperative artifact-cleanup Contract tests."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from gateway_repository_contracts import (
    OperationStatus,
    RepositoryArtifactRef,
    UnknownTypePolicy,
    VerificationPolicy,
    VersionedImportResult,
)
from gateway_repository_service.artifact_cleaner import ArtifactCleaner
from gateway_repository_service.artifact_retention import ArtifactBytesDeletionReason
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_fingerprints import create_repository_fingerprint_v1
from gateway_repository_service.mutation_store import (
    ArtifactLifecycleRecord,
    IdempotencyKeyHash,
    IdempotencyScope,
    MutationStore,
    configure_connection,
)
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import import versioned_import_fingerprint_v1
from gateway_repository_service.versioned_import.models import (
    ArtifactOperationReference,
    ImportRequestBinding,
    IMPORT_ADMISSION_PENDING_STATUS,
)
from gateway_repository_service.versioned_import.store import ImportOperationStore

REPOSITORY_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c21")
OTHER_REPOSITORY_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c22")
ARTIFACT_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c21")
OTHER_ARTIFACT_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c22")
OPERATION_ID = UUID("018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c21")
OTHER_OPERATION_ID = UUID("018f0f3e-7b0a-7c18-8a9e-2e4b9f4d2c21")
ARTIFACT_PAYLOAD = b"artifact-cleanup-contract-payload"


def _validate_leftover_generation(generation: str) -> None:
    if not generation:
        raise ValueError("generation must be non-empty")
    if "-" in generation:
        raise ValueError("generation must not contain '-'")


def quarantine_name_for(*, inode: int, artifact_id: UUID, generation: str) -> str:
    """Test-only leftover ``.deleting-*`` name matching inventory parsers."""

    _validate_leftover_generation(generation)
    return f".deleting-{inode}-{generation}-{artifact_id.hex}"


def detach_name_for(*, inode: int, artifact_id: UUID, generation: str) -> str:
    """Test-only leftover ``.detach-*`` name matching inventory parsers."""

    _validate_leftover_generation(generation)
    return f".detach-{inode}-{generation}-{artifact_id.hex}"


def unlink_stage_dir_name(*, artifact_id: UUID, token: str) -> str:
    """Test-only leftover ``.unlink-stage-*`` name matching inventory parsers."""

    if not token:
        raise ValueError("token must be non-empty")
    if "-" in token:
        raise ValueError("token must not contain '-'")
    return f".unlink-stage-{artifact_id.hex}-{token}"


SHA256 = hashlib.sha256(ARTIFACT_PAYLOAD).hexdigest()
MEDIA_TYPE = "application/vnd.gateway.repository-import.v1+tar+zstd"
CREATED_AT = "2026-08-01T00:00:00+00:00"
BASE_NOW = datetime(2030, 8, 2, tzinfo=UTC)

TTL_BOUNDARY_CASES = (
    ("just_before", timedelta(seconds=-1), False, ArtifactBytesDeletionReason.TTL_NOT_ELAPSED),
    ("exactly_at", timedelta(seconds=0), True, ArtifactBytesDeletionReason.ORDINARY_FAILED_TTL),
    ("after", timedelta(seconds=1), True, ArtifactBytesDeletionReason.ORDINARY_FAILED_TTL),
)

ORPHAN_TTL_BOUNDARY_CASES = (
    ("just_before", timedelta(seconds=-1), False, ArtifactBytesDeletionReason.TTL_NOT_ELAPSED),
    ("exactly_at", timedelta(seconds=0), True, ArtifactBytesDeletionReason.ORPHAN_TTL),
    ("after", timedelta(seconds=1), True, ArtifactBytesDeletionReason.ORPHAN_TTL),
)

PROTECTED_REFERENCE_CASES = (
    (
        "admission_pending",
        ArtifactOperationReference(
            operation_id=OPERATION_ID,
            durable_status=IMPORT_ADMISSION_PENDING_STATUS,
            status=None,
            is_protected=True,
            completed_at=None,
        ),
    ),
    (
        "queued",
        ArtifactOperationReference(
            operation_id=OPERATION_ID,
            durable_status=OperationStatus.QUEUED.value,
            status=OperationStatus.QUEUED,
            is_protected=True,
            completed_at=None,
        ),
    ),
    (
        "running",
        ArtifactOperationReference(
            operation_id=OPERATION_ID,
            durable_status=OperationStatus.RUNNING.value,
            status=OperationStatus.RUNNING,
            is_protected=True,
            completed_at=None,
        ),
    ),
    (
        "manual_failed",
        ArtifactOperationReference(
            operation_id=OPERATION_ID,
            durable_status=OperationStatus.FAILED.value,
            status=OperationStatus.FAILED,
            is_protected=True,
            completed_at="2026-08-01T00:00:00+00:00",
            error_code="MANUAL_RECOVERY_REQUIRED",
        ),
    ),
)


MALFORMED_REFERENCE_CASES = (
    (
        "failed_without_error",
        ArtifactOperationReference(
            operation_id=OPERATION_ID,
            durable_status=OperationStatus.FAILED.value,
            status=OperationStatus.FAILED,
            is_protected=False,
            completed_at="2026-08-01T12:00:00+00:00",
        ),
    ),
    (
        "failed_unknown_error",
        ArtifactOperationReference(
            operation_id=OPERATION_ID,
            durable_status=OperationStatus.FAILED.value,
            status=OperationStatus.FAILED,
            is_protected=False,
            completed_at="2026-08-01T12:00:00+00:00",
            error_code="UNKNOWN_FAILURE",
        ),
    ),
    (
        "succeeded_without_completion",
        ArtifactOperationReference(
            operation_id=OPERATION_ID,
            durable_status=OperationStatus.SUCCEEDED.value,
            status=OperationStatus.SUCCEEDED,
            is_protected=False,
        ),
    ),
    (
        "unknown_durable_status",
        ArtifactOperationReference(
            operation_id=OPERATION_ID,
            durable_status="BROKEN",
            status=None,
            is_protected=True,
        ),
    ),
)


def open_contract_stores(tmp_path: Path) -> tuple[ImportOperationStore, MutationStore]:
    db_path = tmp_path / "service-state" / "repository-service.sqlite3"
    ControlStore.open(
        db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=1000,
    ).close()
    connection = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
    configure_connection(connection)
    import_store = ImportOperationStore(connection)
    return import_store, import_store.mutation_store


def lifecycle(
    *,
    artifact_id: UUID = ARTIFACT_ID,
    created_at: str | None = CREATED_AT,
    bytes_deleted_at: str | None = None,
    consumed_by_operation_id: UUID | None = None,
    consumed_at: str | None = None,
) -> ArtifactLifecycleRecord:
    return ArtifactLifecycleRecord(
        artifact_id=artifact_id,
        repository_id=REPOSITORY_ID,
        media_type=MEDIA_TYPE,
        size_bytes=len(ARTIFACT_PAYLOAD),
        raw_sha256=SHA256,
        created_at=created_at,
        bytes_deleted_at=bytes_deleted_at,
        consumed_by_operation_id=consumed_by_operation_id,
        consumed_at=consumed_at,
    )


def succeeded_reference(
    *,
    artifact_id: UUID = ARTIFACT_ID,
    operation_id: UUID = OPERATION_ID,
    completed_at: str = "2026-08-02T00:00:00+00:00",
    projection_valid: bool = True,
    result_artifact_id: UUID | None = ARTIFACT_ID,
) -> ArtifactOperationReference:
    return ArtifactOperationReference(
        operation_id=operation_id,
        durable_status=OperationStatus.SUCCEEDED.value,
        status=OperationStatus.SUCCEEDED,
        is_protected=False,
        completed_at=completed_at,
        result_artifact_id=result_artifact_id,
        projection_valid=projection_valid,
    )


def seed_create_succeeded(
    mutation_store: MutationStore,
    *,
    repository_id: UUID = REPOSITORY_ID,
) -> None:
    scope = IdempotencyScope.for_create()
    key_hash = IdempotencyKeyHash.from_raw_key(f"create-{repository_id}")
    fingerprint = create_repository_fingerprint_v1()
    effect = mutation_store.allocate_pending(
        scope,
        key_hash=key_hash,
        fingerprint=fingerprint,
        resource_id=repository_id,
    )
    mutation_store.mark_succeeded(
        effect.effect_id,
        response_body={
            "repository_id": str(repository_id),
            "default_ref": "main",
            "initial_commit_id": "commit-0",
        },
    )


def seed_artifact(
    mutation_store: MutationStore,
    *,
    artifact_id: UUID = ARTIFACT_ID,
    repository_id: UUID = REPOSITORY_ID,
    created_at: str = CREATED_AT,
) -> None:
    with mutation_store._lock:
        mutation_store._connection.execute(
            """
            INSERT INTO artifact_lifecycle (
                artifact_id,
                repository_scope,
                media_type,
                size_bytes,
                raw_sha256,
                created_at,
                updated_at,
                cleanup_seq
            ) VALUES (?, ?, ?, ?, ?, ?, ?, (
                SELECT COALESCE(MAX(cleanup_seq), 0) + 1 FROM artifact_lifecycle
            ))
            """,
            (
                str(artifact_id),
                repository_id.hex,
                MEDIA_TYPE,
                len(ARTIFACT_PAYLOAD),
                SHA256,
                created_at,
                created_at,
            ),
        )
        mutation_store._connection.commit()


def seed_bytes_delete_intent(
    mutation_store: MutationStore,
    *,
    artifact_id: UUID = ARTIFACT_ID,
    repository_id: UUID = REPOSITORY_ID,
    dev: int,
    ino: int,
    phase: str = "quarantined",
    generation: str | None = None,
    intent_at: str = CREATED_AT,
) -> str:
    token = generation if generation is not None else uuid4().hex
    with mutation_store._lock:
        cursor = mutation_store._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET bytes_delete_intent_at = ?,
                bytes_delete_dev = ?,
                bytes_delete_ino = ?,
                bytes_delete_phase = ?,
                bytes_delete_generation = ?,
                updated_at = ?
            WHERE artifact_id = ?
              AND repository_scope = ?
              AND bytes_deleted_at IS NULL
            """,
            (
                intent_at,
                int(dev),
                int(ino),
                phase,
                token,
                intent_at,
                str(artifact_id),
                repository_id.hex,
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("failed to seed delete intent")
        mutation_store._connection.commit()
    return token


def seed_artifact_residual(
    mutation_store: MutationStore,
    *,
    artifact_id: UUID = ARTIFACT_ID,
    repository_id: UUID = REPOSITORY_ID,
    kind: str,
    name: str,
    parent_name: str = "",
    dev: int,
    ino: int,
    generation: str | None,
    created_at: str = CREATED_AT,
) -> None:
    with mutation_store._lock:
        mutation_store._connection.execute(
            """
            INSERT INTO artifact_residual (
                artifact_id, repository_scope, kind, name, parent_name,
                dev, ino, generation, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(artifact_id),
                repository_id.hex,
                kind,
                name,
                parent_name,
                int(dev),
                int(ino),
                generation,
                created_at,
            ),
        )
        mutation_store._connection.commit()


def seed_bytes_deleted_receipt(
    mutation_store: MutationStore,
    *,
    artifact_id: UUID = ARTIFACT_ID,
    repository_id: UUID = REPOSITORY_ID,
    dev: int = 1,
    ino: int = 1,
    generation: str,
    deleted_at: str = CREATED_AT,
) -> None:
    with mutation_store._lock:
        cursor = mutation_store._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET bytes_deleted_at = ?,
                bytes_deleted_receipt_dev = ?,
                bytes_deleted_receipt_ino = ?,
                bytes_deleted_receipt_generation = ?,
                updated_at = ?
            WHERE artifact_id = ?
              AND repository_scope = ?
            """,
            (
                deleted_at,
                int(dev),
                int(ino),
                generation,
                deleted_at,
                str(artifact_id),
                repository_id.hex,
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("failed to seed deleted receipt")
        mutation_store._connection.commit()


def binding(*, artifact_id: UUID = ARTIFACT_ID) -> ImportRequestBinding:
    return ImportRequestBinding(
        repository_id=REPOSITORY_ID,
        artifact_ref=RepositoryArtifactRef(
            artifact_id=artifact_id,
            media_type=MEDIA_TYPE,
            size_bytes=len(ARTIFACT_PAYLOAD),
            raw_sha256=SHA256,
        ),
        target_ref="main",
        expected_commit_id="commit-0",
        verification_policy=VerificationPolicy.STRUCTURAL,
        unknown_type_policy=UnknownTypePolicy.REJECT,
    )


def enqueue(
    store: ImportOperationStore,
    *,
    key: str,
    operation_id: UUID,
    artifact_id: UUID = ARTIFACT_ID,
) -> None:
    request = binding(artifact_id=artifact_id)
    key_hash = IdempotencyKeyHash.from_raw_key(key)
    store.claim_or_enqueue(
        request,
        key_hash=key_hash,
        fingerprint=versioned_import_fingerprint_v1(binding=request, key_hash=key_hash),
        operation_id=operation_id,
    )


def import_result(*, artifact_id: UUID = ARTIFACT_ID) -> VersionedImportResult:
    return VersionedImportResult(
        commit_id="commit-1",
        target_ref="main",
        artifact_id=artifact_id,
        canonicalization_manifest_digest="manifest-1",
        expected_commit_id="commit-0",
        completed_verification_policy=VerificationPolicy.STRUCTURAL,
        unknown_type_policy=UnknownTypePolicy.REJECT,
    )


def mark_succeeded_consumed(
    store: ImportOperationStore,
    *,
    key: str,
    operation_id: UUID = OPERATION_ID,
    artifact_id: UUID = ARTIFACT_ID,
) -> None:
    enqueue(store, key=key, operation_id=operation_id, artifact_id=artifact_id)
    store.claim_if_queued(operation_id)
    store.mark_succeeded(operation_id, result=import_result(artifact_id=artifact_id))


def write_ready(
    layout: DurableLayout,
    *,
    artifact_id: UUID = ARTIFACT_ID,
    repository_id: UUID = REPOSITORY_ID,
) -> Path:
    path = artifact_ready_path(layout, repository_id, artifact_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ARTIFACT_PAYLOAD)
    return path


def settings(
    layout: DurableLayout,
    *,
    ttl: int = 3600,
    interval: int = 300,
) -> RepositoryServiceSettings:
    return RepositoryServiceSettings(
        profile="test",
        bearer_token="token",
        data_root=layout.root,
        artifact_ttl_seconds=ttl,
        artifact_cleanup_interval_seconds=interval,
        max_import_workers=1,
    )


def cleaner(
    layout: DurableLayout,
    store: ImportOperationStore,
    mutation_store: MutationStore,
    *,
    ttl: int = 3600,
    interval: int = 3600,
    clock: datetime | Callable[[], datetime] | None = None,
) -> ArtifactCleaner:
    if callable(clock):
        clock_fn = clock
    else:
        frozen = clock if clock is not None else BASE_NOW

        def clock_fn() -> datetime:
            return frozen

    return ArtifactCleaner(
        settings=settings(layout, ttl=ttl, interval=interval),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=clock_fn,
    )


class FakePrivateRefProvider:
    def delete_private_ref(self, *_args: object, **_kwargs: object) -> None:
        return None
