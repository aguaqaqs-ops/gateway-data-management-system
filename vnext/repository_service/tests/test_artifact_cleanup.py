"""Artifact retention, admission-pin cleanup, and cleaner lifecycle tests."""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta
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
from gateway_repository_service.artifact_cleaner import (
    ArtifactCleaner,
    ArtifactCleanerShutdownError,
    classify_ready_artifact_path,
)
from gateway_repository_service.artifact_retention import (
    ArtifactBytesDeletionReason,
    decide_artifact_bytes_deletion,
    retention_explains_missing_ready_bytes,
)
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_fingerprints import create_repository_fingerprint_v1
from gateway_repository_service.mutation_reconciliation import (
    MutableConsistencyWatch,
    import_artifact_watch_failures,
    upload_artifact_bytes_reconciled_after_import,
)
from gateway_repository_service.mutation_store import (
    ArtifactLifecycleRecord,
    IdempotencyKeyHash,
    IdempotencyScope,
    MutationStore,
    configure_connection,
)
from gateway_repository_service.runtime import ServiceRuntime, ServiceStartupError
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.admission_pin import ArtifactAdmissionPin
from gateway_repository_service.upload_artifact.admission_pin import ArtifactNotReadyForAdmission
from gateway_repository_service.upload_artifact.admission_pin import try_unlink_owned_ready_artifact
from gateway_repository_service.upload_artifact.admission_pin import (
    try_unlink_ready_artifact_with_recheck,
)
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import import versioned_import_fingerprint_v1
from gateway_repository_service.versioned_import.models import (
    ArtifactOperationReference,
    ImportRequestBinding,
    IMPORT_ADMISSION_PENDING_STATUS,
)
from gateway_repository_service.versioned_import.store import ImportOperationStore
from gateway_repository_service.versioned_import.worker import ImportWorkerPool
from support.lifecycle_harness import lifecycle_settings
from support.recovery_harness import ready_client, replay_create
from support.upload_harness import upload_headers

REPOSITORY_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c21")
ARTIFACT_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c21")
OPERATION_ID = UUID("018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c21")
OTHER_OPERATION_ID = UUID("018f0f3e-7b0a-7c18-8a9e-2e4b9f4d2c21")
ARTIFACT_PAYLOAD = b"artifact-cleanup-payload"
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


def _lifecycle(
    *,
    created_at: str | None = CREATED_AT,
    bytes_deleted_at: str | None = None,
    consumed_by_operation_id: UUID | None = None,
    consumed_at: str | None = None,
) -> ArtifactLifecycleRecord:
    return ArtifactLifecycleRecord(
        artifact_id=ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        media_type=MEDIA_TYPE,
        size_bytes=len(ARTIFACT_PAYLOAD),
        raw_sha256=SHA256,
        created_at=created_at,
        bytes_deleted_at=bytes_deleted_at,
        consumed_by_operation_id=consumed_by_operation_id,
        consumed_at=consumed_at,
    )


def _seed_create_succeeded(mutation_store: MutationStore) -> None:
    scope = IdempotencyScope.for_create()
    key_hash = IdempotencyKeyHash.from_raw_key(f"create-{REPOSITORY_ID}")
    fingerprint = create_repository_fingerprint_v1()
    effect = mutation_store.allocate_pending(
        scope,
        key_hash=key_hash,
        fingerprint=fingerprint,
        resource_id=REPOSITORY_ID,
    )
    mutation_store.mark_succeeded(
        effect.effect_id,
        response_body={
            "repository_id": str(REPOSITORY_ID),
            "default_ref": "main",
            "initial_commit_id": "commit-0",
        },
    )


def _seed_artifact(
    mutation_store: MutationStore,
    *,
    artifact_id: UUID = ARTIFACT_ID,
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
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(artifact_id),
                REPOSITORY_ID.hex,
                MEDIA_TYPE,
                len(ARTIFACT_PAYLOAD),
                SHA256,
                created_at,
                created_at,
            ),
        )
        mutation_store._connection.commit()


def _binding(*, artifact_id: UUID = ARTIFACT_ID) -> ImportRequestBinding:
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


def _enqueue(
    store: ImportOperationStore,
    *,
    key: str,
    operation_id: UUID,
) -> None:
    binding = _binding()
    key_hash = IdempotencyKeyHash.from_raw_key(key)
    store.claim_or_enqueue(
        binding,
        key_hash=key_hash,
        fingerprint=versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash),
        operation_id=operation_id,
    )


def _import_result() -> VersionedImportResult:
    return VersionedImportResult(
        commit_id="commit-1",
        target_ref="main",
        artifact_id=ARTIFACT_ID,
        canonicalization_manifest_digest="manifest-1",
        expected_commit_id="commit-0",
        completed_verification_policy=VerificationPolicy.STRUCTURAL,
        unknown_type_policy=UnknownTypePolicy.REJECT,
    )


def _write_ready(layout: DurableLayout, *, artifact_id: UUID = ARTIFACT_ID) -> Path:
    path = artifact_ready_path(layout, REPOSITORY_ID, artifact_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ARTIFACT_PAYLOAD)
    return path


def _settings(layout: DurableLayout, *, ttl: int = 3600, interval: int = 300) -> RepositoryServiceSettings:
    return RepositoryServiceSettings(
        profile="test",
        bearer_token="token",
        data_root=layout.root,
        artifact_ttl_seconds=ttl,
        artifact_cleanup_interval_seconds=interval,
        max_import_workers=1,
    )


@pytest.mark.parametrize(
    ("_label", "delta", "eligible", "reason"),
    TTL_BOUNDARY_CASES,
    ids=[case[0] for case in TTL_BOUNDARY_CASES],
)
def test_ordinary_failed_ttl_boundaries(
    _label: str,
    delta: timedelta,
    eligible: bool,
    reason: ArtifactBytesDeletionReason,
) -> None:
    completed_at = "2026-08-01T12:00:00+00:00"
    boundary = datetime.fromisoformat(completed_at)
    decision = decide_artifact_bytes_deletion(
        lifecycle=_lifecycle(),
        references=[
            ArtifactOperationReference(
                operation_id=OPERATION_ID,
                durable_status=OperationStatus.FAILED.value,
                status=OperationStatus.FAILED,
                is_protected=False,
                completed_at=completed_at,
                error_code="IMPORT_REJECTED",
            )
        ],
        now=boundary + timedelta(seconds=3600) + delta,
        ttl_seconds=3600,
    )
    assert decision.eligible is eligible
    assert decision.reason is reason


@pytest.mark.parametrize(
    ("_label", "delta", "eligible", "reason"),
    ORPHAN_TTL_BOUNDARY_CASES,
    ids=[case[0] for case in ORPHAN_TTL_BOUNDARY_CASES],
)
def test_orphan_ttl_boundaries(
    _label: str,
    delta: timedelta,
    eligible: bool,
    reason: ArtifactBytesDeletionReason,
) -> None:
    created = datetime.fromisoformat(CREATED_AT)
    decision = decide_artifact_bytes_deletion(
        lifecycle=_lifecycle(),
        references=[],
        now=created + timedelta(seconds=3600) + delta,
        ttl_seconds=3600,
    )
    assert decision.eligible is eligible
    assert decision.reason is reason


@pytest.mark.parametrize(("label", "reference"), PROTECTED_REFERENCE_CASES, ids=[c[0] for c in PROTECTED_REFERENCE_CASES])
def test_protected_references_are_retained(label: str, reference: ArtifactOperationReference) -> None:
    del label
    decision = decide_artifact_bytes_deletion(
        lifecycle=_lifecycle(),
        references=[reference],
        now=BASE_NOW + timedelta(days=30),
        ttl_seconds=1,
    )
    assert decision.eligible is False
    assert decision.reason is ArtifactBytesDeletionReason.PROTECTED


def test_succeeded_residual_is_immediately_eligible() -> None:
    completed = "2026-08-02T00:00:00+00:00"
    decision = decide_artifact_bytes_deletion(
        lifecycle=_lifecycle(
            consumed_by_operation_id=OPERATION_ID,
            consumed_at=completed,
        ),
        references=[
            ArtifactOperationReference(
                operation_id=OPERATION_ID,
                durable_status=OperationStatus.SUCCEEDED.value,
                status=OperationStatus.SUCCEEDED,
                is_protected=False,
                completed_at=completed,
                result_artifact_id=ARTIFACT_ID,
                projection_valid=True,
            )
        ],
        now=BASE_NOW,
        ttl_seconds=86400,
    )
    assert decision.eligible is True
    assert decision.reason is ArtifactBytesDeletionReason.SUCCEEDED_IMMEDIATE


def test_succeeded_without_consumption_is_not_immediately_eligible() -> None:
    decision = decide_artifact_bytes_deletion(
        lifecycle=_lifecycle(),
        references=[
            ArtifactOperationReference(
                operation_id=OPERATION_ID,
                durable_status=OperationStatus.SUCCEEDED.value,
                status=OperationStatus.SUCCEEDED,
                is_protected=False,
                completed_at="2026-08-02T00:00:00+00:00",
                result_artifact_id=ARTIFACT_ID,
                projection_valid=True,
            )
        ],
        now=BASE_NOW,
        ttl_seconds=86400,
    )
    assert decision.eligible is False
    assert decision.reason is ArtifactBytesDeletionReason.FAIL_CLOSED


def test_multi_ordinary_failed_uses_conservative_latest_completed_at() -> None:
    earlier = "2026-08-01T00:00:00+00:00"
    later = "2026-08-01T12:00:00+00:00"
    references = [
        ArtifactOperationReference(
            operation_id=OPERATION_ID,
            durable_status=OperationStatus.FAILED.value,
            status=OperationStatus.FAILED,
            is_protected=False,
            completed_at=earlier,
            error_code="IMPORT_REJECTED",
        ),
        ArtifactOperationReference(
            operation_id=OTHER_OPERATION_ID,
            durable_status=OperationStatus.FAILED.value,
            status=OperationStatus.FAILED,
            is_protected=False,
            completed_at=later,
            error_code="VERIFICATION_FAILED_NOT_PUBLISHED",
        ),
    ]
    before_latest_ttl = decide_artifact_bytes_deletion(
        lifecycle=_lifecycle(),
        references=references,
        now=datetime.fromisoformat(later) + timedelta(seconds=3599),
        ttl_seconds=3600,
    )
    assert before_latest_ttl.eligible is False
    after_latest_ttl = decide_artifact_bytes_deletion(
        lifecycle=_lifecycle(),
        references=references,
        now=datetime.fromisoformat(later) + timedelta(seconds=3600),
        ttl_seconds=3600,
    )
    assert after_latest_ttl.eligible is True
    assert after_latest_ttl.reason is ArtifactBytesDeletionReason.ORDINARY_FAILED_TTL


def test_already_deleted_and_malformed_fail_closed() -> None:
    deleted = decide_artifact_bytes_deletion(
        lifecycle=_lifecycle(bytes_deleted_at="2026-08-02T00:00:00+00:00"),
        references=[],
        now=BASE_NOW,
        ttl_seconds=1,
    )
    assert deleted.reason is ArtifactBytesDeletionReason.ALREADY_DELETED
    malformed = decide_artifact_bytes_deletion(
        lifecycle=_lifecycle(created_at="not-a-timestamp"),
        references=[],
        now=BASE_NOW,
        ttl_seconds=1,
    )
    assert malformed.eligible is False
    assert malformed.reason is ArtifactBytesDeletionReason.FAIL_CLOSED


@pytest.mark.parametrize(
    ("_label", "reference"),
    MALFORMED_REFERENCE_CASES,
    ids=[case[0] for case in MALFORMED_REFERENCE_CASES],
)
def test_malformed_reference_evidence_fails_closed(
    _label: str,
    reference: ArtifactOperationReference,
) -> None:
    decision = decide_artifact_bytes_deletion(
        lifecycle=_lifecycle(),
        references=[reference],
        now=BASE_NOW + timedelta(days=30),
        ttl_seconds=1,
    )
    assert decision.eligible is False
    assert decision.reason is ArtifactBytesDeletionReason.FAIL_CLOSED


def test_ordinary_failed_artifact_expires(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    _enqueue(store, key="fail-1", operation_id=OPERATION_ID)
    store.claim_if_queued(OPERATION_ID)
    store.mark_failed(
        OPERATION_ID,
        error=SimpleError(code="IMPORT_REJECTED", message="rejected"),
    )
    operation = store.get_operation(REPOSITORY_ID, OPERATION_ID)
    assert operation is not None
    completed_at = datetime.fromisoformat(operation.completed_at or CREATED_AT)

    clock = {"now": completed_at + timedelta(seconds=10)}
    settings = _settings(layout, ttl=60, interval=3600)
    cleaner = ArtifactCleaner(
        settings=settings,
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: clock["now"],
    )
    cleaner.sweep_once()
    assert ready.is_file()

    clock["now"] = completed_at + timedelta(seconds=60)
    cleaner.sweep_once()
    assert not ready.exists()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None
    assert lifecycle.created_at is not None


def test_orphan_artifact_expires(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store, created_at=CREATED_AT)
    ready = _write_ready(layout)
    clock = {"now": datetime.fromisoformat(CREATED_AT) + timedelta(seconds=10)}
    cleaner = ArtifactCleaner(
        settings=_settings(layout, ttl=60, interval=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: clock["now"],
    )
    cleaner.sweep_once()
    assert ready.is_file()
    clock["now"] = datetime.fromisoformat(CREATED_AT) + timedelta(seconds=60)
    cleaner.sweep_once()
    assert not ready.exists()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None


def test_cleanup_retries_after_first_failure(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    _enqueue(store, key="ok", operation_id=OPERATION_ID)
    store.claim_if_queued(OPERATION_ID)
    store.mark_succeeded(OPERATION_ID, result=_import_result())

    cleaner = ArtifactCleaner(
        settings=_settings(layout, ttl=60, interval=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    )
    calls = {"n": 0}
    original = try_unlink_ready_artifact_with_recheck

    def flaky(path: Path, *, recheck: object, **kwargs: object) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "unlink_failed"
        return original(path, recheck=recheck, **kwargs)  # type: ignore[arg-type]

    import gateway_repository_service.artifact_cleaner as cleaner_mod

    monkey = flaky
    setattr(cleaner_mod, "try_unlink_ready_artifact_with_recheck", monkey)
    try:
        cleaner.sweep_once()
        assert ready.is_file()
        lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
        assert lifecycle is not None
        assert lifecycle.bytes_deleted_at is None
        cleaner.sweep_once()
        assert not ready.exists()
        lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
        assert lifecycle is not None
        assert lifecycle.bytes_deleted_at is not None
    finally:
        setattr(cleaner_mod, "try_unlink_ready_artifact_with_recheck", original)


@pytest.mark.serial
def test_cleanup_failure_retries_after_lifecycle_notification(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    first_failure = threading.Event()
    original = try_unlink_ready_artifact_with_recheck
    calls = 0

    def fail_once(path: Path, *, recheck: object, **kwargs: object) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            first_failure.set()
            return "unlink_failed"
        return original(path, recheck=recheck, **kwargs)  # type: ignore[arg-type]

    import gateway_repository_service.artifact_cleaner as cleaner_mod

    monkeypatch.setattr(cleaner_mod, "try_unlink_ready_artifact_with_recheck", fail_once)
    cleaner = ArtifactCleaner(
        settings=_settings(layout, ttl=1, interval=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    )
    cleaner.start()
    try:
        assert first_failure.wait(timeout=2.0)
        assert ready.is_file()
        cleaner.notify()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and ready.exists():
            time.sleep(0.01)
        assert not ready.exists()
        assert calls == 2
    finally:
        cleaner.stop(timeout=2.0)


@pytest.mark.serial
def test_cleanup_failure_retries_after_interval_fallback(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    first_failure = threading.Event()
    original = try_unlink_ready_artifact_with_recheck
    calls = 0

    def fail_once(path: Path, *, recheck: object, **kwargs: object) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            first_failure.set()
            return "unlink_failed"
        return original(path, recheck=recheck, **kwargs)  # type: ignore[arg-type]

    import gateway_repository_service.artifact_cleaner as cleaner_mod

    monkeypatch.setattr(cleaner_mod, "try_unlink_ready_artifact_with_recheck", fail_once)
    cleaner = ArtifactCleaner(
        settings=_settings(layout, ttl=1, interval=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    )
    cleaner.start()
    try:
        assert first_failure.wait(timeout=2.0)
        assert ready.is_file()
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and ready.exists():
            time.sleep(0.01)
        assert not ready.exists()
        assert calls == 2
    finally:
        cleaner.stop(timeout=2.0)


def test_lock_busy_retains_bytes(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    _enqueue(store, key="ok", operation_id=OPERATION_ID)
    store.claim_if_queued(OPERATION_ID)
    store.mark_succeeded(OPERATION_ID, result=_import_result())

    with ArtifactAdmissionPin(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        size_bytes=len(ARTIFACT_PAYLOAD),
        raw_sha256=SHA256,
    ):
        cleaner = ArtifactCleaner(
            settings=_settings(layout, ttl=1, interval=3600),
            layout=layout,
            import_store=store,
            mutation_store=mutation_store,
            clock=lambda: BASE_NOW,
        )
        cleaner.sweep_once()
        assert ready.is_file()
        lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
        assert lifecycle is not None
        assert lifecycle.bytes_deleted_at is None


@pytest.mark.serial
def test_admission_pin_race_does_not_delete_pending_reference(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    # SUCCEEDED residual eligible until ADMISSION_PENDING appears under the pin.
    _enqueue(store, key="ok", operation_id=OPERATION_ID)
    store.claim_if_queued(OPERATION_ID)
    store.mark_succeeded(OPERATION_ID, result=_import_result())

    barrier = threading.Barrier(2)
    outcome: dict[str, str] = {}

    def cleaner_side() -> None:
        barrier.wait()
        result = try_unlink_ready_artifact_with_recheck(
            ready,
            recheck=lambda: store.evaluate_artifact_bytes_deletion(
                ARTIFACT_ID,
                now=BASE_NOW,
                ttl_seconds=1,
            ).eligible,
            layout=layout,
            repository_id=REPOSITORY_ID,
            artifact_id=ARTIFACT_ID,
        )
        outcome["result"] = result

    thread = threading.Thread(target=cleaner_side)
    with ArtifactAdmissionPin(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        size_bytes=len(ARTIFACT_PAYLOAD),
        raw_sha256=SHA256,
    ):
        thread.start()
        barrier.wait()
        # Hold pin while a new protected admission is durable.
        _enqueue(store, key="pending-2", operation_id=OTHER_OPERATION_ID)
        thread.join(timeout=2.0)
        assert not thread.is_alive()
        assert outcome["result"] == "busy"
        assert ready.is_file()
        assert store.evaluate_artifact_bytes_deletion(
            ARTIFACT_ID, now=BASE_NOW, ttl_seconds=1
        ).eligible is False


def test_unlink_failure_does_not_record_bytes_deleted_at(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    _enqueue(store, key="ok", operation_id=OPERATION_ID)
    store.claim_if_queued(OPERATION_ID)
    store.mark_succeeded(OPERATION_ID, result=_import_result())

    import gateway_repository_service.artifact_cleaner as cleaner_mod

    original = cleaner_mod.try_unlink_ready_artifact_with_recheck
    setattr(
        cleaner_mod,
        "try_unlink_ready_artifact_with_recheck",
        lambda *args, **kwargs: "unlink_failed",
    )
    try:
        ArtifactCleaner(
            settings=_settings(layout),
            layout=layout,
            import_store=store,
            mutation_store=mutation_store,
            clock=lambda: BASE_NOW,
        ).sweep_once()
    finally:
        setattr(cleaner_mod, "try_unlink_ready_artifact_with_recheck", original)

    assert ready.is_file()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_already_absent_does_not_record_bytes_deleted_at(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = artifact_ready_path(layout, REPOSITORY_ID, ARTIFACT_ID)
    ready.parent.mkdir(parents=True, exist_ok=True)
    _enqueue(store, key="ok", operation_id=OPERATION_ID)
    store.claim_if_queued(OPERATION_ID)
    store.mark_succeeded(OPERATION_ID, result=_import_result())
    assert not ready.exists()

    ArtifactCleaner(
        settings=_settings(layout),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_lost_bytes_before_ttl_still_block_readiness_after_ttl(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store, created_at=CREATED_AT)
    ready = _write_ready(layout)
    ready.unlink()
    assert not ready.exists()

    before_ttl = datetime.fromisoformat(CREATED_AT) + timedelta(seconds=10)
    after_ttl = datetime.fromisoformat(CREATED_AT) + timedelta(seconds=120)
    cleaner = ArtifactCleaner(
        settings=_settings(layout, ttl=60, interval=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: after_ttl,
    )
    # Eligible by orphan TTL, but absence is unproven — must not mint stamp.
    cleaner.sweep_once()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None
    assert not retention_explains_missing_ready_bytes(
        lifecycle=lifecycle,
        repository_id=REPOSITORY_ID,
        references=[],
        ttl_seconds=60,
        now=after_ttl,
    )
    watch = MutableConsistencyWatch()
    watch.register_succeeded_upload(REPOSITORY_ID, ARTIFACT_ID, len(ARTIFACT_PAYLOAD))
    failures = import_artifact_watch_failures(
        store,
        mutation_store,
        watch.snapshot(),
        layout,
        ttl_seconds=60,
        now=after_ttl,
    )
    assert failures
    del before_ttl


def test_symlink_and_malformed_paths_are_not_deleted(layout: DurableLayout, tmp_path: Path) -> None:
    ready = artifact_ready_path(layout, REPOSITORY_ID, ARTIFACT_ID)
    ready.parent.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "target.bin"
    target.write_bytes(ARTIFACT_PAYLOAD)
    ready.symlink_to(target)
    assert (
        classify_ready_artifact_path(ready, expected=ready, artifact_id=ARTIFACT_ID)
        == "symlink"
    )

    malformed = ready.parent / "not-a-uuid"
    malformed.write_bytes(b"x")
    assert (
        classify_ready_artifact_path(malformed, expected=ready, artifact_id=ARTIFACT_ID)
        == "unexpected_path"
    )


def test_broken_symlink_is_retained_without_deleted_stamp(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = artifact_ready_path(layout, REPOSITORY_ID, ARTIFACT_ID)
    ready.parent.mkdir(parents=True, exist_ok=True)
    ready.symlink_to(ready.parent / "missing-target")

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert ready.is_symlink()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_unknown_and_malformed_ready_entries_are_retained_with_safe_diagnostics(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready_dir = artifact_ready_path(layout, REPOSITORY_ID, ARTIFACT_ID).parent
    ready_dir.mkdir(parents=True, exist_ok=True)
    unknown_uuid_entry = ready_dir / uuid4().hex
    malformed_entry = ready_dir / "not-an-artifact"
    unknown_uuid_entry.write_bytes(b"unknown")
    malformed_entry.write_bytes(b"malformed")
    caplog.set_level(logging.INFO)

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert unknown_uuid_entry.is_file()
    assert malformed_entry.is_file()
    unknown_diagnostics = [
        record
        for record in caplog.records
        if getattr(record, "cleanup_outcome", None) == "unknown_path_inventory"
    ]
    # Exact UUID without lifecycle and malformed names both inventory; files retained.
    assert len(unknown_diagnostics) == 2
    assert all(str(ready_dir) not in record.getMessage() for record in unknown_diagnostics)


@pytest.mark.serial
def test_cleaner_wins_pin_race_admission_cannot_accept_missing_bytes(
    layout: DurableLayout,
) -> None:
    ready = _write_ready(layout)
    recheck_entered = threading.Event()
    release_cleaner = threading.Event()
    admission_started = threading.Event()
    outcomes: dict[str, str] = {}

    def recheck() -> bool:
        recheck_entered.set()
        assert release_cleaner.wait(timeout=2.0)
        return True

    def clean() -> None:
        outcomes["cleaner"] = try_unlink_ready_artifact_with_recheck(
            ready,
            recheck=recheck,
            layout=layout,
            repository_id=REPOSITORY_ID,
            artifact_id=ARTIFACT_ID,
        )

    def admit() -> None:
        admission_started.set()
        try:
            with ArtifactAdmissionPin(
                layout,
                REPOSITORY_ID,
                ARTIFACT_ID,
                size_bytes=len(ARTIFACT_PAYLOAD),
                raw_sha256=SHA256,
            ):
                outcomes["admission"] = "accepted"
        except ArtifactNotReadyForAdmission:
            outcomes["admission"] = "rejected"

    cleaner_thread = threading.Thread(target=clean)
    admission_thread = threading.Thread(target=admit)
    cleaner_thread.start()
    assert recheck_entered.wait(timeout=2.0)
    admission_thread.start()
    assert admission_started.wait(timeout=2.0)
    release_cleaner.set()
    cleaner_thread.join(timeout=2.0)
    admission_thread.join(timeout=2.0)

    assert not cleaner_thread.is_alive()
    assert not admission_thread.is_alive()
    assert outcomes == {"cleaner": "deleted", "admission": "rejected"}
    assert not ready.exists()


def test_recorded_delete_is_not_processed_twice(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _write_ready(layout)
    cleaner = ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    )
    cleaner.sweep_once()
    first = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert first is not None and first.bytes_deleted_at is not None

    cleaner.sweep_once()
    second = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert second is not None
    assert second.bytes_deleted_at == first.bytes_deleted_at


def test_classify_rejects_path_outside_layout_ready_dir(
    layout: DurableLayout,
    tmp_path: Path,
) -> None:
    expected = artifact_ready_path(layout, REPOSITORY_ID, ARTIFACT_ID)
    expected.parent.mkdir(parents=True, exist_ok=True)
    outsider = tmp_path / "other" / ARTIFACT_ID.hex
    outsider.parent.mkdir(parents=True, exist_ok=True)
    outsider.write_bytes(ARTIFACT_PAYLOAD)
    assert (
        classify_ready_artifact_path(outsider, expected=expected, artifact_id=ARTIFACT_ID)
        == "unexpected_path"
    )


def test_poison_lifecycle_row_does_not_block_other_candidates(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    poison_id = uuid4()
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
                str(poison_id),
                "not-a-uuid",
                MEDIA_TYPE,
                1,
                "a" * 64,
                CREATED_AT,
                CREATED_AT,
            ),
        )
        mutation_store._connection.commit()
    poison_ready = artifact_ready_path(layout, REPOSITORY_ID, poison_id)
    poison_ready.parent.mkdir(parents=True, exist_ok=True)
    poison_ready.write_bytes(b"poison")

    candidates = mutation_store.list_artifacts_pending_byte_cleanup()
    assert any(record.artifact_id == ARTIFACT_ID for record in candidates)

    cleaner = ArtifactCleaner(
        settings=_settings(layout, ttl=1, interval=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: datetime.fromisoformat(CREATED_AT) + timedelta(seconds=2),
    )
    cleaner.sweep_once()
    assert not ready.exists()
    assert poison_ready.is_file()


def test_inode_mismatch_retains_bytes_without_deleted_at(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    _enqueue(store, key="ok", operation_id=OPERATION_ID)
    store.claim_if_queued(OPERATION_ID)
    store.mark_succeeded(OPERATION_ID, result=_import_result())

    class _MismatchedStat:
        def __init__(self, base: os.stat_result) -> None:
            self._base = base

        @property
        def st_ino(self) -> int:
            return int(self._base.st_ino) + 1

        @property
        def st_dev(self) -> int:
            return int(self._base.st_dev)

        @property
        def st_nlink(self) -> int:
            return int(self._base.st_nlink)

        @property
        def st_mode(self) -> int:
            return int(self._base.st_mode)

    def flaky_lstat(self: Path) -> os.stat_result:
        base = os.lstat(self)
        if self.resolve() == ready.resolve():
            return _MismatchedStat(base)  # type: ignore[return-value]
        return base

    monkeypatch.setattr(Path, "lstat", flaky_lstat)
    outcome = try_unlink_ready_artifact_with_recheck(ready, recheck=lambda: True)
    assert outcome == "inode_mismatch"
    assert ready.is_file()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


@pytest.mark.serial
def test_sticky_notification_not_lost_during_sweep_wait(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    clock = {"now": datetime.fromisoformat(CREATED_AT) + timedelta(seconds=1)}
    cleaner = ArtifactCleaner(
        settings=_settings(layout, ttl=60, interval=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: clock["now"],
    )
    cleaner.start()
    try:
        # Immediate sweep keeps orphan; thread parks on long interval wait.
        time.sleep(0.05)
        assert ready.is_file()
        # Notify while waiting, then make eligible — sticky wake must not be lost.
        cleaner.notify()
        time.sleep(0.05)
        clock["now"] = datetime.fromisoformat(CREATED_AT) + timedelta(seconds=120)
        cleaner.notify()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and ready.exists():
            time.sleep(0.02)
        assert not ready.exists()
    finally:
        cleaner.stop(timeout=2.0)


@pytest.mark.serial
def test_shutdown_leaves_no_cleaner_thread(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    cleaner = ArtifactCleaner(
        settings=_settings(layout, interval=60),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    )
    cleaner.start()
    thread = cleaner._thread  # noqa: SLF001
    assert thread is not None and thread.is_alive()
    cleaner.stop(timeout=2.0)
    assert not thread.is_alive()
    cleaner.stop(timeout=1.0)  # idempotent


@pytest.mark.serial
def test_join_timeout_raises(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    hang = threading.Event()
    cleaner = ArtifactCleaner(
        settings=_settings(layout, interval=60),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    )

    def hanging_sweep() -> None:
        hang.wait(timeout=5.0)

    setattr(cleaner, "_sweep", hanging_sweep)
    cleaner.start()
    try:
        with pytest.raises(ArtifactCleanerShutdownError):
            cleaner.stop(timeout=0.05)
    finally:
        hang.set()
        # Ensure the hung thread can exit after we forced a timeout raise.
        thread = cleaner._thread  # noqa: SLF001
        if thread is not None and thread.is_alive():
            with cleaner._condition:  # noqa: SLF001
                cleaner._stopping = True  # noqa: SLF001
                cleaner._pending = True  # noqa: SLF001
                cleaner._condition.notify_all()  # noqa: SLF001
            thread.join(timeout=2.0)
            cleaner._thread = None  # noqa: SLF001
            cleaner._started = False  # noqa: SLF001


def test_legal_bytes_deleted_explains_missing_ready_bytes(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    # Orphan TTL=3600 from CREATED_AT → earliest 2026-08-01T01:00:00Z; stamp after boundary.
    deleted_at = "2026-08-01T01:00:00+00:00"
    with mutation_store._lock:
        mutation_store._connection.execute(
            "UPDATE artifact_lifecycle SET bytes_deleted_at = ? WHERE artifact_id = ?",
            (deleted_at, str(ARTIFACT_ID)),
        )
        mutation_store._connection.commit()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    now = datetime(2026, 8, 2, tzinfo=UTC)
    assert retention_explains_missing_ready_bytes(
        lifecycle=lifecycle,
        repository_id=REPOSITORY_ID,
        references=[],
        ttl_seconds=3600,
        now=now,
    )
    assert upload_artifact_bytes_reconciled_after_import(
        store,
        mutation_store,
        REPOSITORY_ID,
        ARTIFACT_ID,
        ttl_seconds=3600,
        now=now,
    )


def test_premature_bytes_deleted_at_does_not_explain_missing_bytes() -> None:
    lifecycle = _lifecycle(bytes_deleted_at="2026-08-01T00:30:00+00:00")
    now = datetime(2026, 8, 2, tzinfo=UTC)
    assert (
        retention_explains_missing_ready_bytes(
            lifecycle=lifecycle,
            repository_id=REPOSITORY_ID,
            references=[],
            ttl_seconds=3600,
            now=now,
        )
        is False
    )
    decision = decide_artifact_bytes_deletion(
        lifecycle=_lifecycle(),
        references=[],
        now=datetime(2026, 8, 1, 0, 30, tzinfo=UTC),
        ttl_seconds=3600,
    )
    assert decision.eligible is False
    assert decision.reason is ArtifactBytesDeletionReason.TTL_NOT_ELAPSED


def test_naive_and_future_bytes_deleted_at_fail_closed() -> None:
    now = datetime(2026, 8, 2, tzinfo=UTC)
    naive = _lifecycle(bytes_deleted_at="2026-08-02T00:00:00")
    assert (
        retention_explains_missing_ready_bytes(
            lifecycle=naive,
            repository_id=REPOSITORY_ID,
            references=[],
            ttl_seconds=1,
            now=now,
        )
        is False
    )
    future = _lifecycle(bytes_deleted_at="2026-08-03T00:00:00+00:00")
    assert (
        retention_explains_missing_ready_bytes(
            lifecycle=future,
            repository_id=REPOSITORY_ID,
            references=[],
            ttl_seconds=1,
            now=now,
        )
        is False
    )


def test_illegal_missing_artifact_still_blocks_readiness(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    watch = MutableConsistencyWatch()
    watch.register_succeeded_upload(REPOSITORY_ID, ARTIFACT_ID, len(ARTIFACT_PAYLOAD))
    failures = import_artifact_watch_failures(
        store,
        mutation_store,
        watch.snapshot(),
        layout,
        ttl_seconds=3600,
    )
    assert failures
    assert any("missing" in item for item in failures)


@pytest.mark.integration
@pytest.mark.serial
def test_legal_ttl_delete_survives_restart_readiness(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    settings = settings.model_copy(
        update={
            "artifact_ttl_seconds": 1,
            "artifact_cleanup_interval_seconds": 3600,
            "max_import_workers": 1,
        }
    )
    runtime = ServiceRuntime.start(settings)
    try:
        repository_id = UUID(
            str(replay_create(runtime, idempotency_key="cleanup-create").repository_id)
        )
        payload = b"cleanup-orphan-upload"
        headers = upload_headers(idempotency_key="cleanup-upload", payload=payload)
        with ready_client(runtime) as client:
            upload = client.post(
                f"/v1/repositories/{repository_id}/artifacts",
                headers=headers,
                content=payload,
            )
            assert upload.status_code == 201
            artifact_id = UUID(str(upload.json()["artifact_ref"]["artifact_id"]))

        # Backdate durable created_at so wall-clock TTL has elapsed (cleaner clock == wall).
        past = (datetime.now(UTC) - timedelta(seconds=10)).replace(microsecond=0).isoformat()
        with runtime.mutation_store._lock:
            runtime.mutation_store._connection.execute(
                "UPDATE artifact_lifecycle SET created_at = ? WHERE artifact_id = ?",
                (past, str(artifact_id)),
            )
            runtime.mutation_store._connection.commit()

        cleaner = runtime.artifact_cleaner
        assert isinstance(cleaner, ArtifactCleaner)
        cleaner.notify()
        ready = artifact_ready_path(runtime.layout, repository_id, artifact_id)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and ready.exists():
            time.sleep(0.05)
        assert not ready.exists()
        lifecycle = runtime.mutation_store.get_artifact_lifecycle(artifact_id)
        assert lifecycle is not None and lifecycle.bytes_deleted_at is not None
        assert runtime.is_ready()
    finally:
        runtime.shutdown()

    restarted = ServiceRuntime.start(settings)
    try:
        assert restarted.is_ready()
    finally:
        restarted.shutdown()


@pytest.mark.integration
def test_runtime_start_failure_unwinds_cleaner_thread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = lifecycle_settings(tmp_path).model_copy(update={"max_import_workers": 1})
    existing_cleaners = {
        thread.ident for thread in threading.enumerate() if thread.name == "artifact-cleaner"
    }

    def fail_lifecycle_wiring(
        self: ImportWorkerPool,
        callback: object,
    ) -> None:
        del self, callback
        raise RuntimeError("forced lifecycle wiring failure")

    monkeypatch.setattr(ImportWorkerPool, "set_lifecycle_notify", fail_lifecycle_wiring)
    with pytest.raises(ServiceStartupError, match="forced lifecycle wiring failure"):
        ServiceRuntime.start(settings)

    leaked = [
        thread
        for thread in threading.enumerate()
        if thread.name == "artifact-cleaner" and thread.ident not in existing_cleaners
    ]
    assert leaked == []


def test_parent_symlink_escape_does_not_delete_outside_target(
    layout: DurableLayout,
    tmp_path: Path,
) -> None:
    ready = _write_ready(layout)
    outside_dir = tmp_path / "escape-ready"
    outside_dir.mkdir()
    outside_target = outside_dir / ARTIFACT_ID.hex
    ready.rename(outside_target)
    ready_dir = ready.parent
    ready_dir.rmdir()
    ready_dir.symlink_to(outside_dir)

    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
    )
    assert outcome != "deleted"
    assert outside_target.is_file()
    assert outside_target.read_bytes() == ARTIFACT_PAYLOAD


def test_pathname_replace_during_recheck_preserves_replacement(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    replacement = b"replacement-inode"
    stamped = {"ok": False}

    def recheck() -> bool:
        ready.unlink()
        ready.write_bytes(replacement)
        return True

    def on_deleted() -> None:
        store.mark_artifact_bytes_deleted(
            ARTIFACT_ID,
            deleted_at="2026-08-02T00:00:00+00:00",
            repository_id=REPOSITORY_ID,
        )
        stamped["ok"] = True

    def on_intent(dev: int, ino: int) -> None:
        store.begin_artifact_bytes_delete_intent(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            dev=dev,
            ino=ino,
            phase="quarantined",
            intent_at="2026-08-02T00:00:00+00:00",
        )

    def on_clear_intent() -> None:
        store.clear_artifact_bytes_delete_intent(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
        )

    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=recheck,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
    )
    # Replacement must not be stamped as deleted; ready content stays.
    assert outcome != "deleted"
    assert stamped["ok"] is False
    assert ready.is_file()
    assert ready.read_bytes() == replacement
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_bytes_deleted_stamp_is_written_while_flock_held(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fcntl

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _write_ready(layout)
    stamped_before_unlock = {"ok": False}
    real_flock = fcntl.flock

    def probe_flock(fd: int, operation: int) -> None:
        if operation == fcntl.LOCK_UN:
            lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
            stamped_before_unlock["ok"] = (
                lifecycle is not None and lifecycle.bytes_deleted_at is not None
            )
        return real_flock(fd, operation)

    monkeypatch.setattr(fcntl, "flock", probe_flock)
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    assert stamped_before_unlock["ok"] is True
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None and lifecycle.bytes_deleted_at is not None


def test_inventory_reports_unknown_entries_without_lifecycle(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store, mutation_store = stores
    del mutation_store
    unknown_repo = layout.artifacts / ("a" * 32)
    ready_dir = unknown_repo / "ready"
    ready_dir.mkdir(parents=True)
    malformed = ready_dir / "not-an-artifact"
    malformed.write_bytes(b"x")
    caplog.set_level(logging.INFO)

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=stores[1],
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert malformed.is_file()
    diagnostics = [
        record
        for record in caplog.records
        if getattr(record, "cleanup_outcome", None) == "unknown_path_inventory"
    ]
    assert diagnostics
    assert all(str(ready_dir) not in record.getMessage() for record in diagnostics)


def test_malformed_succeeded_result_json_is_not_eligible(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    _enqueue(store, key="ok", operation_id=OPERATION_ID)
    store.claim_if_queued(OPERATION_ID)
    store.mark_succeeded(OPERATION_ID, result=_import_result())

    with store._lock:
        store._connection.execute(
            """
            UPDATE repository_import_operations
            SET result_json = NULL
            WHERE operation_id = ?
            """,
            (str(OPERATION_ID),),
        )
        store._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET consumed_by_operation_id = NULL, consumed_at = NULL
            WHERE artifact_id = ?
            """,
            (str(ARTIFACT_ID),),
        )
        store._connection.commit()

    decision = store.evaluate_artifact_bytes_deletion(
        ARTIFACT_ID,
        now=BASE_NOW,
        ttl_seconds=1,
    )
    assert decision.eligible is False
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    assert ready.is_file()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    assert ready.is_file()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_stamp_failed_keeps_quarantine_and_recovers_on_next_sweep(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    calls = {"n": 0}
    original = store.mark_artifact_bytes_deleted

    def flaky_stamp(
        artifact_id: UUID,
        *,
        deleted_at: str | None = None,
        repository_id: UUID | None = None,
    ) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("forced stamp failure")
        original(artifact_id, deleted_at=deleted_at, repository_id=repository_id)

    store.mark_artifact_bytes_deleted = flaky_stamp  # type: ignore[method-assign]
    cleaner = ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    )
    cleaner.sweep_once()
    assert not ready.exists()
    quarantines = list(ready.parent.glob(".deleting-*"))
    assert len(quarantines) == 1
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None

    cleaner.sweep_once()
    assert list(ready.parent.glob(".deleting-*")) == []
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None
    assert not ready.exists()


def test_stamped_quarantine_residual_is_unlinked_on_sweep(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    ino = ready.stat().st_ino
    quarantine = ready.parent / f".deleting-{ino}-{ARTIFACT_ID.hex}"
    os.link(ready, quarantine)
    ready.unlink()
    store.mark_artifact_bytes_deleted(ARTIFACT_ID, deleted_at="2026-08-02T00:00:00+00:00")
    assert quarantine.is_file()

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    assert not quarantine.exists()


def test_best_effort_succeeded_cleanup_retains_when_consumption_cleared(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    from gateway_repository_service.versioned_import.recovery import (
        cleanup_after_succeeded_correction,
    )

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    _enqueue(store, key="ok", operation_id=OPERATION_ID)
    store.claim_if_queued(OPERATION_ID)
    store.mark_succeeded(OPERATION_ID, result=_import_result())
    context = store.load_execution_context(OPERATION_ID)
    assert context is not None

    with store._lock:
        store._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET consumed_by_operation_id = NULL, consumed_at = NULL
            WHERE artifact_id = ?
            """,
            (str(ARTIFACT_ID),),
        )
        store._connection.commit()

    class _Provider:
        def delete_private_ref(self, *_args: object, **_kwargs: object) -> None:
            return None

    cleanup_after_succeeded_correction(
        store=store,
        layout=layout,
        context=context,
        provider=_Provider(),  # type: ignore[arg-type]
        candidate="commit-1",
        ttl_seconds=3600,
    )
    assert ready.is_file()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_forged_quarantine_without_intent_is_retained(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    forged = ready.parent / f".deleting-{ready.stat().st_ino}-{ARTIFACT_ID.hex}"
    forged.write_bytes(b"forged-quarantine")
    caplog.set_level(logging.INFO)

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert forged.is_file()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None
    diagnostics = [
        record
        for record in caplog.records
        if getattr(record, "cleanup_outcome", None)
        in {"unknown_path_inventory", "quarantine_inode_mismatch", "forged_quarantine"}
    ]
    assert diagnostics


def test_unknown_uuid_repository_directory_is_diagnosed(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store, mutation_store = stores
    del mutation_store
    unknown_repo = layout.artifacts / ("b" * 32)
    unknown_repo.mkdir(parents=True)
    (unknown_repo / "ready").mkdir()
    caplog.set_level(logging.INFO)

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=stores[1],
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert unknown_repo.is_dir()
    diagnostics = [
        record
        for record in caplog.records
        if getattr(record, "cleanup_outcome", None) == "unknown_path_inventory"
    ]
    assert diagnostics
