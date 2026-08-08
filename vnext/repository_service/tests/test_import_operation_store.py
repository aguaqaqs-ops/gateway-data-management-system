"""Tests for durable Versioned import operation store."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from gateway_repository_contracts import (
    OperationStatus,
    RepositoryArtifactRef,
    SimpleError,
    UnknownTypePolicy,
    VerificationPolicy,
    VersionedImportResult,
)
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_fingerprints import create_repository_fingerprint_v1
from gateway_repository_service.mutation_store import (
    EffectStatus,
    IdempotencyScope,
    IdempotencyKeyHash,
    MutationStore,
    MutationStoreError,
    configure_connection,
)
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import import (
    ClaimOrEnqueueResult,
    ImportFingerprintConflict,
    ImportOperationStore,
    ImportOperationTransitionRejected,
    ImportReplayCountRejected,
    ImportRequestBinding,
    ManualCorrectionDecision,
    versioned_import_fingerprint_v1,
)
from gateway_repository_service.versioned_import.models import (
    ImportManualBarrierRequired,
    ImportQueueFull,
    ImportStoreInvariantError,
    IMPORT_ADMISSION_PENDING_STATUS,
)

REPOSITORY_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
ARTIFACT_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11")
OPERATION_ID = UUID("018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11")
OTHER_OPERATION_ID = UUID("018f0f3e-7b0a-7c18-8a9e-2e4b9f4d2c11")
LARGER_UUID_OPERATION_ID = OTHER_OPERATION_ID
SMALLER_UUID_OPERATION_ID = OPERATION_ID
ARTIFACT_PAYLOAD = b"x" * 12
SHA256 = hashlib.sha256(ARTIFACT_PAYLOAD).hexdigest()
MEDIA_TYPE = "application/vnd.gateway.repository-import.v1+tar+zstd"


@pytest.fixture
def layout(tmp_path: Path) -> DurableLayout:
    return DurableLayout.create_for_probe(tmp_path / "data-root")


@pytest.fixture
def stores(tmp_path: Path) -> tuple[ImportOperationStore, MutationStore]:
    db_path = tmp_path / "service-state" / "repository-service.sqlite3"
    ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000).close()
    connection = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
    configure_connection(connection)
    import_store = ImportOperationStore(connection)
    return import_store, import_store.mutation_store


def _artifact_ref(*, artifact_id: UUID = ARTIFACT_ID) -> RepositoryArtifactRef:
    return RepositoryArtifactRef(
        artifact_id=artifact_id,
        media_type=MEDIA_TYPE,
        size_bytes=len(ARTIFACT_PAYLOAD),
        raw_sha256=SHA256,
    )


def _binding(*, artifact_id: UUID = ARTIFACT_ID) -> ImportRequestBinding:
    return ImportRequestBinding(
        repository_id=REPOSITORY_ID,
        artifact_ref=_artifact_ref(artifact_id=artifact_id),
        target_ref="main",
        expected_commit_id="commit-0",
        verification_policy=VerificationPolicy.STRUCTURAL,
        unknown_type_policy=UnknownTypePolicy.REJECT,
    )


def _fingerprint(
    binding: ImportRequestBinding,
    key_hash: IdempotencyKeyHash,
) -> bytes:
    return versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash)


def _import_result(*, artifact_id: UUID = ARTIFACT_ID) -> VersionedImportResult:
    return VersionedImportResult(
        commit_id="commit-1",
        target_ref="main",
        artifact_id=artifact_id,
        canonicalization_manifest_digest="manifest-digest-1",
        expected_commit_id="commit-0",
        completed_verification_policy=VerificationPolicy.STRUCTURAL,
        unknown_type_policy=UnknownTypePolicy.REJECT,
    )


def _seed_create_succeeded(mutation_store: MutationStore, *, repository_id: UUID = REPOSITORY_ID) -> None:
    now = "2026-08-06T00:00:00+00:00"
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
    del now


def _seed_artifact(mutation_store: MutationStore, *, artifact_id: UUID = ARTIFACT_ID) -> None:
    now = "2026-08-06T00:00:00+00:00"
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
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(artifact_id),
                REPOSITORY_ID.hex,
                MEDIA_TYPE,
                len(ARTIFACT_PAYLOAD),
                SHA256,
                now,
                now,
            ),
        )
        mutation_store._connection.commit()


def _write_ready_artifact(layout: DurableLayout, binding: ImportRequestBinding) -> None:
    ready_path = artifact_ready_path(
        layout,
        binding.repository_id,
        binding.artifact_ref.artifact_id,
    )
    ready_path.parent.mkdir(parents=True, exist_ok=True)
    ready_path.write_bytes(ARTIFACT_PAYLOAD)


def _enqueue(
    store: ImportOperationStore,
    *,
    key: str = "import-key-1",
    binding: ImportRequestBinding | None = None,
    operation_id: UUID | None = None,
) -> tuple[IdempotencyKeyHash, bytes]:
    resolved_binding = binding or _binding()
    key_hash = IdempotencyKeyHash.from_raw_key(key)
    fingerprint = _fingerprint(resolved_binding, key_hash)
    store.claim_or_enqueue(
        resolved_binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        operation_id=operation_id,
    )
    return key_hash, fingerprint


def _admit_and_publish(
    store: ImportOperationStore,
    binding: ImportRequestBinding,
    *,
    key_hash: IdempotencyKeyHash,
    fingerprint: bytes,
    max_queued_imports: int = 64,
    operation_id: UUID | None = None,
) -> ClaimOrEnqueueResult:
    result = store.admit_new_import(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        max_queued_imports=max_queued_imports,
        operation_id=operation_id,
    )
    if result.is_new:
        assert store.publish_queued_import(result.operation_id)
    return result


def test_versioned_import_fingerprint_is_versioned() -> None:
    binding = _binding()
    key_hash = IdempotencyKeyHash.from_raw_key("import-key")
    fingerprint = versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash)
    assert fingerprint.startswith(b"versioned_import/v1\x00")


def test_idempotency_key_hash_repr_does_not_include_raw_key() -> None:
    key_hash = IdempotencyKeyHash.from_raw_key("secret-import-key")
    rendered = repr(key_hash)
    assert "secret-import-key" not in rendered


def test_claim_or_enqueue_inserts_queued_operation(stores: tuple[ImportOperationStore, MutationStore]) -> None:
    store, _ = stores
    binding = _binding()
    key_hash = IdempotencyKeyHash.from_raw_key("enqueue-1")
    fingerprint = _fingerprint(binding, key_hash)

    result = store.claim_or_enqueue(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        operation_id=OPERATION_ID,
    )

    assert result.is_new is True
    assert result.operation_id == OPERATION_ID
    assert result.operation.status == OperationStatus.QUEUED
    assert result.operation.result is None
    assert result.operation.error is None
    assert result.operation.private_ref_name == f"gateway-import-{OPERATION_ID.hex}"
    assert result.operation.operation_marker == (
        f"gateway-versioned-import operation_id={OPERATION_ID}"
    )


def test_same_key_same_fingerprint_replays_operation(stores: tuple[ImportOperationStore, MutationStore]) -> None:
    store, _ = stores
    binding = _binding()
    key_hash = IdempotencyKeyHash.from_raw_key("replay-key")
    fingerprint = _fingerprint(binding, key_hash)

    first = store.claim_or_enqueue(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        operation_id=OPERATION_ID,
    )
    second = store.claim_or_enqueue(binding, key_hash=key_hash, fingerprint=fingerprint)

    assert first.operation_id == second.operation_id
    assert second.is_new is False


def test_same_key_different_fingerprint_conflicts(stores: tuple[ImportOperationStore, MutationStore]) -> None:
    store, _ = stores
    key_hash = IdempotencyKeyHash.from_raw_key("conflict-key")
    first_binding = _binding()
    second_binding = ImportRequestBinding(
        repository_id=REPOSITORY_ID,
        artifact_ref=_artifact_ref(),
        target_ref="main",
        expected_commit_id="commit-1",
        verification_policy=VerificationPolicy.STRUCTURAL,
        unknown_type_policy=UnknownTypePolicy.REJECT,
    )
    store.claim_or_enqueue(
        first_binding,
        key_hash=key_hash,
        fingerprint=_fingerprint(first_binding, key_hash),
        operation_id=OPERATION_ID,
    )

    with pytest.raises(ImportFingerprintConflict):
        store.claim_or_enqueue(
            second_binding,
            key_hash=key_hash,
            fingerprint=_fingerprint(second_binding, key_hash),
        )


def test_claim_next_queued_is_fifo(
    stores: tuple[ImportOperationStore, MutationStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _ = stores
    fixed_now = "2026-08-06T00:00:00+00:00"
    monkeypatch.setattr(
        "gateway_repository_service.versioned_import.store.utc_now_iso",
        lambda: fixed_now,
    )
    _enqueue(store, key="fifo-1", operation_id=LARGER_UUID_OPERATION_ID)
    _enqueue(store, key="fifo-2", operation_id=SMALLER_UUID_OPERATION_ID)

    first = store.claim_next_queued(REPOSITORY_ID)
    second = store.claim_next_queued(REPOSITORY_ID)

    assert first is not None
    assert second is not None
    assert first.operation_id == LARGER_UUID_OPERATION_ID
    assert second.operation_id == SMALLER_UUID_OPERATION_ID
    assert first.status == OperationStatus.RUNNING
    assert second.status == OperationStatus.RUNNING


def test_claim_if_queued_is_atomic_for_concurrent_callers(tmp_path: Path) -> None:
    db_path = tmp_path / "service-state" / "repository-service.sqlite3"
    ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000).close()
    connection = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
    configure_connection(connection)
    store = ImportOperationStore(connection)
    _enqueue(store, operation_id=OPERATION_ID)

    barrier = threading.Barrier(2)
    results: list[OperationStatus | BaseException | None] = []

    def worker() -> None:
        barrier.wait()
        try:
            claimed = store.claim_if_queued(OPERATION_ID)
            results.append(claimed.status if claimed is not None else None)
        except BaseException as exc:
            results.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    connection.close()

    claimed = [item for item in results if item == OperationStatus.RUNNING]
    not_claimed = [item for item in results if item is None]
    assert len(claimed) == 1
    assert len(not_claimed) == 1


def test_mark_succeeded_persists_result_and_consumed_binding(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _enqueue(store, operation_id=OPERATION_ID)
    store.claim_if_queued(OPERATION_ID)

    operation = store.mark_succeeded(OPERATION_ID, result=_import_result())
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)

    assert operation.status == OperationStatus.SUCCEEDED
    assert operation.result is not None
    assert operation.error is None
    assert lifecycle is not None
    assert lifecycle.consumed_by_operation_id == OPERATION_ID
    assert lifecycle.consumed_at is not None


def test_mark_failed_persists_terminal_error(stores: tuple[ImportOperationStore, MutationStore]) -> None:
    store, _ = stores
    _enqueue(store, operation_id=OPERATION_ID)
    store.claim_if_queued(OPERATION_ID)

    operation = store.mark_failed(
        OPERATION_ID,
        error=SimpleError(code="IMPORT_REJECTED", message="rejected"),
    )

    assert operation.status == OperationStatus.FAILED
    assert operation.error is not None
    assert operation.error.code == "IMPORT_REJECTED"
    assert operation.result is None


def test_mark_failed_rejects_request_id(stores: tuple[ImportOperationStore, MutationStore]) -> None:
    store, _ = stores
    _enqueue(store, operation_id=OPERATION_ID)
    store.claim_if_queued(OPERATION_ID)

    with pytest.raises(Exception, match="request_id must be empty"):
        store.mark_failed(
            OPERATION_ID,
            error=SimpleError(code="IMPORT_REJECTED", message="rejected", request_id="req-1"),
        )


def test_increment_automatic_replay_count_only_once(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, _ = stores
    _enqueue(store, operation_id=OPERATION_ID)

    updated = store.increment_automatic_replay_count(OPERATION_ID)
    assert updated.automatic_replay_count == 1

    with pytest.raises(ImportReplayCountRejected):
        store.increment_automatic_replay_count(OPERATION_ID)


def test_manual_correction_and_audit_clear_barrier(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _enqueue(store, operation_id=OPERATION_ID)
    store.claim_if_queued(OPERATION_ID)
    store.mark_failed(
        OPERATION_ID,
        error=SimpleError(code="MANUAL_RECOVERY_REQUIRED", message="manual"),
    )

    assert store.has_unresolved_manual_barrier(REPOSITORY_ID) is True

    corrected = store.apply_manual_correction(
        OPERATION_ID,
        decision=ManualCorrectionDecision.SUCCEEDED,
        evidence_summary={"summary": "published"},
        final_result=_import_result(),
    )

    assert corrected.status == OperationStatus.SUCCEEDED
    assert store.has_unresolved_manual_barrier(REPOSITORY_ID) is False

    audit_count = mutation_store._connection.execute(
        "SELECT COUNT(*) FROM repository_import_recovery_audit WHERE operation_id = ?",
        (str(OPERATION_ID),),
    ).fetchone()
    assert int(audit_count[0]) == 1


def test_manual_correction_rejects_non_manual_operation(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, _ = stores
    _enqueue(store, operation_id=OPERATION_ID)
    store.claim_if_queued(OPERATION_ID)
    store.mark_failed(
        OPERATION_ID,
        error=SimpleError(code="IMPORT_REJECTED", message="rejected"),
    )

    with pytest.raises(ImportOperationTransitionRejected):
        store.apply_manual_correction(
            OPERATION_ID,
            decision=ManualCorrectionDecision.NOT_PUBLISHED,
            evidence_summary={"summary": "not published"},
            final_error=SimpleError(code="IMPORT_REJECTED", message="operator confirmed"),
        )


def test_artifact_references_mark_protected_states(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _enqueue(store, key="queued", operation_id=OPERATION_ID)
    _enqueue(store, key="manual", operation_id=OTHER_OPERATION_ID)
    store.claim_if_queued(OTHER_OPERATION_ID)
    store.mark_failed(
        OTHER_OPERATION_ID,
        error=SimpleError(code="MANUAL_RECOVERY_REQUIRED", message="manual"),
    )

    references = store.list_artifact_references(ARTIFACT_ID)
    by_id = {reference.operation_id: reference for reference in references}

    assert by_id[OPERATION_ID].is_protected is True
    assert by_id[OTHER_OPERATION_ID].is_protected is True


def test_can_delete_artifact_bytes_requires_no_protected_references(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _enqueue(store, key="queued", operation_id=OPERATION_ID)
    _enqueue(store, key="succeeded", operation_id=OTHER_OPERATION_ID)
    store.claim_if_queued(OTHER_OPERATION_ID)
    store.mark_succeeded(OTHER_OPERATION_ID, result=_import_result())

    assert store.can_delete_artifact_bytes(ARTIFACT_ID) is False

    store.claim_if_queued(OPERATION_ID)
    store.mark_failed(
        OPERATION_ID,
        error=SimpleError(code="IMPORT_REJECTED", message="rejected"),
    )

    assert store.can_delete_artifact_bytes(ARTIFACT_ID) is True


def test_mark_artifact_bytes_deleted_records_timestamp(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _enqueue(store, operation_id=OPERATION_ID)
    store.claim_if_queued(OPERATION_ID)
    store.mark_succeeded(OPERATION_ID, result=_import_result())

    store.mark_artifact_bytes_deleted(ARTIFACT_ID)
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)

    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None


def test_terminal_transition_rejects_invalid_status(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, _ = stores
    _enqueue(store, operation_id=OPERATION_ID)

    with pytest.raises(ImportOperationTransitionRejected):
        store.mark_succeeded(OPERATION_ID, result=_import_result())


def test_concurrent_import_and_mutation_store_on_shared_connection(tmp_path: Path) -> None:
    db_path = tmp_path / "service-state" / "repository-service.sqlite3"
    ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000).close()
    connection = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
    configure_connection(connection)
    import_store = ImportOperationStore(connection)
    mutation_store = import_store.mutation_store

    barrier = threading.Barrier(2)
    results: list[object] = []

    def import_worker() -> None:
        binding = _binding()
        key_hash = IdempotencyKeyHash.from_raw_key("shared-connection-import")
        fingerprint = _fingerprint(binding, key_hash)
        barrier.wait()
        try:
            import_store.claim_or_enqueue(
                binding,
                key_hash=key_hash,
                fingerprint=fingerprint,
                operation_id=OPERATION_ID,
            )
            results.append("import-ok")
        except BaseException as exc:
            results.append(exc)

    def mutation_worker() -> None:
        barrier.wait()
        try:
            effect = mutation_store.allocate_pending(
                IdempotencyScope.for_create(),
                key_hash=IdempotencyKeyHash.from_raw_key("shared-connection-create"),
                fingerprint=create_repository_fingerprint_v1(),
                resource_id=uuid4(),
            )
            results.append(effect.status)
        except BaseException as exc:
            results.append(exc)

    threads = [threading.Thread(target=import_worker), threading.Thread(target=mutation_worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    connection.close()

    assert results.count("import-ok") == 1
    statuses = [item for item in results if isinstance(item, EffectStatus)]
    failures = [item for item in results if isinstance(item, BaseException)]
    assert statuses == [EffectStatus.PENDING]
    assert failures == []


def test_mark_succeeded_rejects_mismatched_artifact_id(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _enqueue(store, operation_id=OPERATION_ID)
    store.claim_if_queued(OPERATION_ID)

    with pytest.raises(ImportOperationTransitionRejected, match="artifact_id"):
        store.mark_succeeded(
            OPERATION_ID,
            result=_import_result(artifact_id=uuid4()),
        )


def test_manual_correction_succeeded_rejects_mismatched_expected_commit_id(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _enqueue(store, operation_id=OPERATION_ID)
    store.claim_if_queued(OPERATION_ID)
    store.mark_failed(
        OPERATION_ID,
        error=SimpleError(code="MANUAL_RECOVERY_REQUIRED", message="manual"),
    )

    mismatched = _import_result()
    mismatched = mismatched.model_copy(update={"expected_commit_id": "commit-9"})

    with pytest.raises(ImportOperationTransitionRejected, match="expected_commit_id"):
        store.apply_manual_correction(
            OPERATION_ID,
            decision=ManualCorrectionDecision.SUCCEEDED,
            evidence_summary={"summary": "published"},
            final_result=mismatched,
        )


def test_mark_succeeded_without_artifact_lifecycle_row_fails_and_stays_running(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, mutation_store = stores
    _enqueue(store, operation_id=OPERATION_ID)
    store.claim_if_queued(OPERATION_ID)

    with pytest.raises(MutationStoreError, match="artifact lifecycle row is missing"):
        store.mark_succeeded(OPERATION_ID, result=_import_result())

    operation = store.get_operation(REPOSITORY_ID, OPERATION_ID)
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert operation is not None
    assert operation.status == OperationStatus.RUNNING
    assert lifecycle is None


def test_not_published_correction_rejects_manual_code_and_writes_no_audit(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, mutation_store = stores
    _enqueue(store, operation_id=OPERATION_ID)
    store.claim_if_queued(OPERATION_ID)
    store.mark_failed(
        OPERATION_ID,
        error=SimpleError(code="MANUAL_RECOVERY_REQUIRED", message="manual"),
    )

    with pytest.raises(ImportOperationTransitionRejected, match="ordinary stable error code"):
        store.apply_manual_correction(
            OPERATION_ID,
            decision=ManualCorrectionDecision.NOT_PUBLISHED,
            evidence_summary={"summary": "still manual"},
            final_error=SimpleError(code="MANUAL_RECOVERY_REQUIRED", message="manual"),
        )

    assert store.has_unresolved_manual_barrier(REPOSITORY_ID) is True
    audit_count = mutation_store._connection.execute(
        "SELECT COUNT(*) FROM repository_import_recovery_audit WHERE operation_id = ?",
        (str(OPERATION_ID),),
    ).fetchone()
    assert int(audit_count[0]) == 0


def test_lookup_by_key_returns_none_for_missing_key(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, _ = stores
    key_hash = IdempotencyKeyHash.from_raw_key("missing-key")
    assert store.lookup_by_key(REPOSITORY_ID, key_hash) is None


def test_lookup_by_key_returns_existing_operation(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, _ = stores
    key_hash, _ = _enqueue(store, operation_id=OPERATION_ID)
    found = store.lookup_by_key(REPOSITORY_ID, key_hash)
    assert found is not None
    assert found.operation_id == OPERATION_ID


def test_count_global_queued_counts_pending_and_queued_status(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, mutation_store = stores
    assert store.count_global_queued() == 0
    _enqueue(store, operation_id=OPERATION_ID, key="queued-1")
    assert store.count_global_queued() == 1
    _seed_artifact(mutation_store)
    _seed_create_succeeded(mutation_store)
    binding = _binding()
    key_hash = IdempotencyKeyHash.from_raw_key("pending-only")
    fingerprint = _fingerprint(binding, key_hash)
    pending = store.admit_new_import(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        max_queued_imports=64,
    )
    assert pending.is_new is True
    assert store.get_operation_durable_status(pending.operation_id) == IMPORT_ADMISSION_PENDING_STATUS
    assert store.count_global_queued() == 2
    _enqueue(store, operation_id=OTHER_OPERATION_ID, key="queued-2")
    assert store.count_global_queued() == 3
    store.claim_if_queued(OPERATION_ID)
    assert store.count_global_queued() == 2


def test_admit_new_import_inserts_admission_pending_status(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _seed_create_succeeded(mutation_store)
    binding = _binding()
    key_hash = IdempotencyKeyHash.from_raw_key("pending-status")
    fingerprint = _fingerprint(binding, key_hash)
    result = store.admit_new_import(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        max_queued_imports=64,
    )
    assert result.is_new is True
    assert store.get_operation_durable_status(result.operation_id) == IMPORT_ADMISSION_PENDING_STATUS
    assert store.claim_if_queued(result.operation_id) is None
    assert store.publish_queued_import(result.operation_id) is True
    claimed = store.claim_if_queued(result.operation_id)
    assert claimed is not None
    assert claimed.status == OperationStatus.RUNNING


def test_abort_admission_import_only_deletes_pending_rows(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _seed_create_succeeded(mutation_store)
    binding = _binding()
    key_hash = IdempotencyKeyHash.from_raw_key("abort-pending")
    fingerprint = _fingerprint(binding, key_hash)
    admitted = store.admit_new_import(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        max_queued_imports=64,
    )
    assert store.abort_admission_import(admitted.operation_id) is True
    assert store.lookup_by_key(REPOSITORY_ID, key_hash) is None
    _admit_and_publish(
        store,
        binding,
        key_hash=IdempotencyKeyHash.from_raw_key("abort-running"),
        fingerprint=_fingerprint(binding, IdempotencyKeyHash.from_raw_key("abort-running")),
        operation_id=OPERATION_ID,
    )
    store.claim_if_queued(OPERATION_ID)
    assert store.abort_admission_import(OPERATION_ID) is False


def test_count_global_queued_counts_only_queued_status(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, mutation_store = stores
    assert store.count_global_queued() == 0
    _enqueue(store, operation_id=OPERATION_ID, key="queued-1")
    assert store.count_global_queued() == 1
    _seed_artifact(mutation_store)
    _enqueue(store, operation_id=OTHER_OPERATION_ID, key="queued-2")
    assert store.count_global_queued() == 2
    store.claim_if_queued(OPERATION_ID)
    assert store.count_global_queued() == 1


def test_admit_new_import_rejects_manual_barrier(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _seed_create_succeeded(mutation_store)
    binding = _binding()
    _write_ready_artifact(layout, binding)
    _enqueue(store, operation_id=OPERATION_ID, key="manual-key")
    store.claim_if_queued(OPERATION_ID)
    store.mark_failed(
        OPERATION_ID,
        error=SimpleError(code="MANUAL_RECOVERY_REQUIRED", message="manual"),
    )
    binding = _binding()
    key_hash = IdempotencyKeyHash.from_raw_key("new-key")
    fingerprint = _fingerprint(binding, key_hash)
    with pytest.raises(ImportManualBarrierRequired):
        store.admit_new_import(
            binding,
            key_hash=key_hash,
            fingerprint=fingerprint,
            max_queued_imports=64,
        )


def test_admit_new_import_rejects_when_queue_full(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _seed_create_succeeded(mutation_store)
    binding = _binding()
    _write_ready_artifact(layout, binding)
    _enqueue(store, operation_id=OPERATION_ID, key="queued-1")
    binding = _binding()
    key_hash = IdempotencyKeyHash.from_raw_key("new-key")
    fingerprint = _fingerprint(binding, key_hash)
    with pytest.raises(ImportQueueFull):
        store.admit_new_import(
            binding,
            key_hash=key_hash,
            fingerprint=fingerprint,
            max_queued_imports=1,
        )


def test_admit_new_import_succeeds_without_ready_file_at_store_layer(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _seed_create_succeeded(mutation_store)
    binding = _binding()
    key_hash = IdempotencyKeyHash.from_raw_key("db-only-key")
    fingerprint = _fingerprint(binding, key_hash)
    result = store.admit_new_import(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        max_queued_imports=64,
    )
    assert result.is_new is True
    assert result.operation.durable_status == IMPORT_ADMISSION_PENDING_STATUS
    assert result.operation.status is None


def test_lookup_replay_state_returns_operation_and_fingerprint(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _seed_create_succeeded(mutation_store)
    binding = _binding()
    key_hash = IdempotencyKeyHash.from_raw_key("replay-state-key")
    fingerprint = _fingerprint(binding, key_hash)
    admitted = store.admit_new_import(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        max_queued_imports=64,
    )
    replay_state = store.lookup_replay_state(REPOSITORY_ID, key_hash)
    assert replay_state is not None
    assert replay_state.operation.operation_id == admitted.operation_id
    assert replay_state.stored_fingerprint == fingerprint
    assert replay_state.durable_status == IMPORT_ADMISSION_PENDING_STATUS
    assert replay_state.operation.status is None
    assert store.get_operation(REPOSITORY_ID, admitted.operation_id) is None


def test_list_artifact_references_treats_pending_as_protected(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _seed_create_succeeded(mutation_store)
    binding = _binding()
    key_hash = IdempotencyKeyHash.from_raw_key("pending-reference")
    fingerprint = _fingerprint(binding, key_hash)
    admitted = store.admit_new_import(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        max_queued_imports=64,
        operation_id=OPERATION_ID,
    )
    references = store.list_artifact_references(ARTIFACT_ID)
    pending_reference = next(
        reference for reference in references if reference.operation_id == admitted.operation_id
    )
    assert pending_reference.durable_status == IMPORT_ADMISSION_PENDING_STATUS
    assert pending_reference.status is None
    assert pending_reference.is_protected is True


PENDING_ROW_SHAPE_FAULTS = [
    (
        "error_json",
        "UPDATE repository_import_operations SET error_json = ? WHERE operation_id = ?",
        ('{"code":"IMPORT_REJECTED","message":"rejected"}',),
    ),
    (
        "started_at",
        "UPDATE repository_import_operations SET started_at = ? WHERE operation_id = ?",
        ("2026-08-06T00:00:00+00:00",),
    ),
]


@pytest.mark.parametrize(("case_name", "sql", "params"), PENDING_ROW_SHAPE_FAULTS)
def test_pending_operation_row_shape_faults_raise_invariant_error(
    stores: tuple[ImportOperationStore, MutationStore],
    case_name: str,
    sql: str,
    params: tuple[object, ...],
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _seed_create_succeeded(mutation_store)
    binding = _binding()
    key_hash = IdempotencyKeyHash.from_raw_key(f"pending-shape-{case_name}")
    fingerprint = _fingerprint(binding, key_hash)
    admitted = store.admit_new_import(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        max_queued_imports=64,
    )
    store._connection.execute(
        sql,
        (*params, str(admitted.operation_id)),
    )
    store._connection.commit()
    with pytest.raises(ImportStoreInvariantError):
        store.lookup_replay_state(REPOSITORY_ID, key_hash)


def test_lookup_by_key_raises_invariant_error_for_invalid_result_json(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _seed_create_succeeded(mutation_store)
    binding = _binding()
    key_hash = IdempotencyKeyHash.from_raw_key("invalid-json-key")
    fingerprint = _fingerprint(binding, key_hash)
    admitted = store.admit_new_import(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        max_queued_imports=64,
    )
    store._connection.execute(
        "UPDATE repository_import_operations SET result_json = ? WHERE operation_id = ?",
        ("{", str(admitted.operation_id)),
    )
    store._connection.commit()
    with pytest.raises(ImportStoreInvariantError):
        store.lookup_by_key(REPOSITORY_ID, key_hash)


@pytest.mark.parametrize(
    ("fingerprint_value",),
    [
        ("text-fingerprint",),
        (42,),
    ],
)
def test_lookup_replay_state_rejects_invalid_fingerprint_type(
    stores: tuple[ImportOperationStore, MutationStore],
    fingerprint_value: object,
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _seed_create_succeeded(mutation_store)
    binding = _binding()
    key_hash = IdempotencyKeyHash.from_raw_key("invalid-fingerprint-type")
    fingerprint = _fingerprint(binding, key_hash)
    admitted = store.admit_new_import(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        max_queued_imports=64,
    )
    store._connection.execute(
        "UPDATE repository_import_operations SET request_fingerprint = ? WHERE operation_id = ?",
        (fingerprint_value, str(admitted.operation_id)),
    )
    store._connection.commit()
    with pytest.raises(ImportStoreInvariantError):
        store.lookup_replay_state(REPOSITORY_ID, key_hash)


def test_admit_new_import_replays_concurrent_same_key(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _seed_create_succeeded(mutation_store)
    binding = _binding()
    _write_ready_artifact(layout, binding)
    binding = _binding()
    key_hash = IdempotencyKeyHash.from_raw_key("concurrent-key")
    fingerprint = _fingerprint(binding, key_hash)
    barrier = threading.Barrier(2)
    results: list[ClaimOrEnqueueResult] = []
    errors: list[BaseException] = []

    def worker() -> None:
        barrier.wait()
        try:
            results.append(
                store.admit_new_import(
                    binding,
                    key_hash=key_hash,
                    fingerprint=fingerprint,
                    max_queued_imports=64,
                )
            )
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(results) == 2
    assert results[0].operation_id == results[1].operation_id
    assert store.count_global_queued() == 1
