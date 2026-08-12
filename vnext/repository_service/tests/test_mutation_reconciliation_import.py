"""Unit tests for import-aware mutation reconciliation helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID

import pytest

from gateway_repository_contracts import (
    RepositoryArtifactRef,
    SimpleError,
    UnknownTypePolicy,
    VerificationPolicy,
    VersionedImportResult,
)
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
from gateway_repository_service.mutation_store import (
    IdempotencyKeyHash,
    MutationStore,
    configure_connection,
)
from gateway_repository_service.versioned_import import (
    ImportOperationStore,
    ImportRequestBinding,
    versioned_import_fingerprint_v1,
)
from gateway_repository_service.versioned_import.models import MANUAL_RECOVERY_REQUIRED_CODE
from gateway_repository_service.mutation_reconciliation import (
    ConsistencyWatch,
    import_artifact_watch_failures,
    upload_artifact_bytes_reconciled_after_import,
)

REPOSITORY_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
OTHER_REPOSITORY_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c12")
ARTIFACT_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11")
OTHER_ARTIFACT_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c12")
OPERATION_ID = UUID("018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11")
OTHER_OPERATION_ID = UUID("018f0f3e-7b0a-7c18-8a9e-2e4b9f4d2c11")
MEDIA_TYPE = "application/vnd.gateway.repository-import.v1+tar+zstd"
SHA256 = "a" * 64
NOW = "2026-08-09T00:00:00+00:00"


@pytest.fixture
def stores(tmp_path: Path) -> tuple[ImportOperationStore, MutationStore]:
    db_path = tmp_path / "service-state" / "repository-service.sqlite3"
    ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000).close()
    connection = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
    configure_connection(connection)
    import_store = ImportOperationStore(connection)
    return import_store, import_store.mutation_store


def _seed_artifact_lifecycle(
    mutation_store: MutationStore,
    *,
    repository_id: UUID,
    artifact_id: UUID,
) -> None:
    mutation_store._connection.execute(
        """
        INSERT INTO artifact_lifecycle (
            artifact_id, repository_scope, media_type, size_bytes, raw_sha256, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(artifact_id),
            repository_id.hex,
            MEDIA_TYPE,
            12,
            SHA256,
            NOW,
            NOW,
        ),
    )
    mutation_store._connection.commit()


def _binding(*, repository_id: UUID, artifact_id: UUID) -> ImportRequestBinding:
    return ImportRequestBinding(
        repository_id=repository_id,
        artifact_ref=RepositoryArtifactRef(
            artifact_id=artifact_id,
            media_type=MEDIA_TYPE,
            size_bytes=12,
            raw_sha256=SHA256,
        ),
        target_ref="main",
        expected_commit_id="commit-0",
        verification_policy=VerificationPolicy.STRUCTURAL,
        unknown_type_policy=UnknownTypePolicy.REJECT,
    )


def _enqueue_operation(
    import_store: ImportOperationStore,
    *,
    repository_id: UUID,
    artifact_id: UUID,
    operation_id: UUID,
    key: str,
) -> None:
    binding = _binding(repository_id=repository_id, artifact_id=artifact_id)
    key_hash = IdempotencyKeyHash.from_raw_key(key)
    fingerprint = versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash)
    import_store.claim_or_enqueue(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        operation_id=operation_id,
    )
    import_store.claim_if_queued(operation_id)


@pytest.mark.unit
def test_upload_artifact_bytes_reconciled_requires_deletion_stamp(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    import_store, mutation_store = stores
    _seed_artifact_lifecycle(mutation_store, repository_id=REPOSITORY_ID, artifact_id=ARTIFACT_ID)
    _enqueue_operation(
        import_store,
        repository_id=REPOSITORY_ID,
        artifact_id=ARTIFACT_ID,
        operation_id=OPERATION_ID,
        key="happy-import",
    )
    import_store.mark_succeeded(
        OPERATION_ID,
        result=VersionedImportResult(
            commit_id="commit-1",
            target_ref="main",
            artifact_id=ARTIFACT_ID,
            canonicalization_manifest_digest="manifest-1",
            expected_commit_id="commit-0",
            completed_verification_policy=VerificationPolicy.STRUCTURAL,
            unknown_type_policy=UnknownTypePolicy.REJECT,
        ),
    )

    assert not upload_artifact_bytes_reconciled_after_import(
        import_store,
        mutation_store,
        REPOSITORY_ID,
        ARTIFACT_ID,
        ttl_seconds=24 * 60 * 60,
    )

    generation = import_store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=1,
        ino=1,
        phase="quarantined",
        intent_at=NOW,
    )
    import_store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        expected_dev=1,
        expected_ino=1,
        expected_generation=generation,
    )
    assert upload_artifact_bytes_reconciled_after_import(
        import_store,
        mutation_store,
        REPOSITORY_ID,
        ARTIFACT_ID,
        ttl_seconds=24 * 60 * 60,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("setup", "expected"),
    [
        pytest.param("wrong_artifact_binding", False, id="wrong-artifact-binding"),
        pytest.param("failed_operation", False, id="failed-operation"),
        pytest.param("missing_consumption_evidence", False, id="missing-consumption-evidence"),
        pytest.param("cross_repository_scope", False, id="cross-repository-scope"),
        pytest.param("other_active_reference", False, id="other-active-reference"),
        pytest.param("manual_protected_reference", False, id="manual-protected-reference"),
    ],
)
def test_upload_artifact_bytes_reconciled_negative_cases(
    stores: tuple[ImportOperationStore, MutationStore],
    setup: str,
    expected: bool,
) -> None:
    import_store, mutation_store = stores
    _seed_artifact_lifecycle(mutation_store, repository_id=REPOSITORY_ID, artifact_id=ARTIFACT_ID)
    _seed_artifact_lifecycle(
        mutation_store,
        repository_id=REPOSITORY_ID,
        artifact_id=OTHER_ARTIFACT_ID,
    )
    query_repository_id = REPOSITORY_ID

    if setup == "wrong_artifact_binding":
        _enqueue_operation(
            import_store,
            repository_id=REPOSITORY_ID,
            artifact_id=OTHER_ARTIFACT_ID,
            operation_id=OPERATION_ID,
            key="other-artifact-import",
        )
        import_store.mark_succeeded(
            OPERATION_ID,
            result=VersionedImportResult(
                commit_id="commit-1",
                target_ref="main",
                artifact_id=OTHER_ARTIFACT_ID,
                canonicalization_manifest_digest="manifest-1",
                expected_commit_id="commit-0",
                completed_verification_policy=VerificationPolicy.STRUCTURAL,
                unknown_type_policy=UnknownTypePolicy.REJECT,
            ),
        )
        mutation_store._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET consumed_by_operation_id = ?, consumed_at = ?, bytes_deleted_at = ?
            WHERE artifact_id = ?
            """,
            (str(OPERATION_ID), NOW, NOW, str(ARTIFACT_ID)),
        )
        mutation_store._connection.commit()
    elif setup == "failed_operation":
        _enqueue_operation(
            import_store,
            repository_id=REPOSITORY_ID,
            artifact_id=ARTIFACT_ID,
            operation_id=OPERATION_ID,
            key="failed-import",
        )
        import_store.mark_failed(
            OPERATION_ID,
            error=SimpleError(code=MANUAL_RECOVERY_REQUIRED_CODE, message="manual"),
        )
        mutation_store.record_artifact_consumed(
            ARTIFACT_ID,
            operation_id=OPERATION_ID,
            consumed_at=NOW,
            repository_id=REPOSITORY_ID,
        )
        mutation_store._connection.commit()
    elif setup == "missing_consumption_evidence":
        _enqueue_operation(
            import_store,
            repository_id=REPOSITORY_ID,
            artifact_id=ARTIFACT_ID,
            operation_id=OPERATION_ID,
            key="missing-evidence-import",
        )
        import_store.mark_succeeded(
            OPERATION_ID,
            result=VersionedImportResult(
                commit_id="commit-1",
                target_ref="main",
                artifact_id=ARTIFACT_ID,
                canonicalization_manifest_digest="manifest-1",
                expected_commit_id="commit-0",
                completed_verification_policy=VerificationPolicy.STRUCTURAL,
                unknown_type_policy=UnknownTypePolicy.REJECT,
            ),
        )
        mutation_store._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET consumed_by_operation_id = ?, consumed_at = NULL, bytes_deleted_at = NULL
            WHERE artifact_id = ?
            """,
            (str(OPERATION_ID), str(ARTIFACT_ID)),
        )
        mutation_store._connection.commit()
    elif setup == "cross_repository_scope":
        _enqueue_operation(
            import_store,
            repository_id=REPOSITORY_ID,
            artifact_id=ARTIFACT_ID,
            operation_id=OPERATION_ID,
            key="cross-repo-import",
        )
        import_store.mark_succeeded(
            OPERATION_ID,
            result=VersionedImportResult(
                commit_id="commit-1",
                target_ref="main",
                artifact_id=ARTIFACT_ID,
                canonicalization_manifest_digest="manifest-1",
                expected_commit_id="commit-0",
                completed_verification_policy=VerificationPolicy.STRUCTURAL,
                unknown_type_policy=UnknownTypePolicy.REJECT,
            ),
        )
        query_repository_id = OTHER_REPOSITORY_ID
    elif setup == "other_active_reference":
        _enqueue_operation(
            import_store,
            repository_id=REPOSITORY_ID,
            artifact_id=ARTIFACT_ID,
            operation_id=OPERATION_ID,
            key="primary-import",
        )
        import_store.mark_succeeded(
            OPERATION_ID,
            result=VersionedImportResult(
                commit_id="commit-1",
                target_ref="main",
                artifact_id=ARTIFACT_ID,
                canonicalization_manifest_digest="manifest-1",
                expected_commit_id="commit-0",
                completed_verification_policy=VerificationPolicy.STRUCTURAL,
                unknown_type_policy=UnknownTypePolicy.REJECT,
            ),
        )
        _enqueue_operation(
            import_store,
            repository_id=REPOSITORY_ID,
            artifact_id=ARTIFACT_ID,
            operation_id=OTHER_OPERATION_ID,
            key="secondary-import",
        )
        import_store.claim_if_queued(OTHER_OPERATION_ID)
    elif setup == "manual_protected_reference":
        _enqueue_operation(
            import_store,
            repository_id=REPOSITORY_ID,
            artifact_id=ARTIFACT_ID,
            operation_id=OPERATION_ID,
            key="primary-import",
        )
        import_store.mark_succeeded(
            OPERATION_ID,
            result=VersionedImportResult(
                commit_id="commit-1",
                target_ref="main",
                artifact_id=ARTIFACT_ID,
                canonicalization_manifest_digest="manifest-1",
                expected_commit_id="commit-0",
                completed_verification_policy=VerificationPolicy.STRUCTURAL,
                unknown_type_policy=UnknownTypePolicy.REJECT,
            ),
        )
        _enqueue_operation(
            import_store,
            repository_id=REPOSITORY_ID,
            artifact_id=ARTIFACT_ID,
            operation_id=OTHER_OPERATION_ID,
            key="manual-import",
        )
        import_store.mark_failed(
            OTHER_OPERATION_ID,
            error=SimpleError(code=MANUAL_RECOVERY_REQUIRED_CODE, message="manual"),
        )
        mutation_store.record_artifact_consumed(
            ARTIFACT_ID,
            operation_id=OPERATION_ID,
            consumed_at=NOW,
            repository_id=REPOSITORY_ID,
        )
        mutation_store._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET bytes_deleted_at = ?
            WHERE artifact_id = ?
            """,
            (NOW, str(ARTIFACT_ID)),
        )
        mutation_store._connection.commit()
    else:
        raise AssertionError(f"unknown setup {setup}")

    assert (
        upload_artifact_bytes_reconciled_after_import(
            import_store,
            mutation_store,
            query_repository_id,
            ARTIFACT_ID,
            ttl_seconds=24 * 60 * 60,
        )
        is expected
    )


@pytest.mark.unit
def test_protected_manual_pin_blocks_readiness_when_bytes_deleted(
    stores: tuple[ImportOperationStore, MutationStore],
    tmp_path: Path,
) -> None:
    import_store, mutation_store = stores
    _seed_artifact_lifecycle(mutation_store, repository_id=REPOSITORY_ID, artifact_id=ARTIFACT_ID)
    _enqueue_operation(
        import_store,
        repository_id=REPOSITORY_ID,
        artifact_id=ARTIFACT_ID,
        operation_id=OPERATION_ID,
        key="manual-pin",
    )
    import_store.mark_failed(
        OPERATION_ID,
        error=SimpleError(code=MANUAL_RECOVERY_REQUIRED_CODE, message="manual"),
    )
    mutation_store._connection.execute(
        """
        UPDATE artifact_lifecycle
        SET bytes_deleted_at = ?
        WHERE artifact_id = ?
        """,
        (NOW, str(ARTIFACT_ID)),
    )
    mutation_store._connection.commit()

    from gateway_repository_service.layout import DurableLayout

    layout = DurableLayout.create_for_probe(tmp_path)
    failures = import_artifact_watch_failures(
        import_store,
        mutation_store,
        ConsistencyWatch(create_repository_ids=(), upload_artifacts=()),
        layout,
        ttl_seconds=24 * 60 * 60,
    )
    assert failures
    assert any("protected import artifact" in failure for failure in failures)
