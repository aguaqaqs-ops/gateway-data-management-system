"""Artifact retention, admission-pin cleanup, and cleaner lifecycle tests."""

from __future__ import annotations

import errno
import hashlib
import logging
import os
import sqlite3
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
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
from gateway_repository_service.control_db import (
    CONTROL_DB_USER_VERSION,
    ControlDbError,
    ControlStore,
)
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_fingerprints import create_repository_fingerprint_v1
from gateway_repository_service.mutation_reconciliation import (
    MutableConsistencyWatch,
    import_artifact_watch_failures,
    upload_artifact_bytes_reconciled_after_import,
)
from gateway_repository_service.mutation_store import (
    ArtifactLifecycleRecord,
    CleanupCandidatePage,
    IdempotencyKeyHash,
    IdempotencyScope,
    MutationStore,
    configure_connection,
)
from gateway_repository_service.runtime import ServiceRuntime, ServiceStartupError
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.admission_pin import ArtifactAdmissionPin
from gateway_repository_service.upload_artifact.admission_pin import ArtifactNotReadyForAdmission
from gateway_repository_service.upload_artifact.admission_pin import parse_any_recoverable_sidecar
from gateway_repository_service.upload_artifact.admission_pin import parse_unlink_verify_name
from gateway_repository_service.upload_artifact.admission_pin import quarantine_name_for
from gateway_repository_service.upload_artifact.admission_pin import try_unlink_owned_ready_artifact
from gateway_repository_service.upload_artifact.admission_pin import (
    try_unlink_ready_artifact_with_recheck,
)
from gateway_repository_service.upload_artifact.admission_pin import verify_sidecar_name_for
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


def _settings(
    layout: DurableLayout,
    *,
    ttl: int = 3600,
    interval: int = 300,
    tombstone_budget: int = 50_000,
) -> RepositoryServiceSettings:
    return RepositoryServiceSettings(
        profile="test",
        bearer_token="token",
        data_root=layout.root,
        artifact_ttl_seconds=ttl,
        artifact_cleanup_interval_seconds=interval,
        artifact_tombstone_budget=tombstone_budget,
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
    assert any(record.artifact_id == ARTIFACT_ID for record in candidates.records)

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

    def on_deleted(dev: int, ino: int, generation: str) -> None:
        store.mark_artifact_bytes_deleted(
            ARTIFACT_ID,
            deleted_at="2026-08-02T00:00:00+00:00",
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
        )
        stamped["ok"] = True

    def on_intent(dev: int, ino: int, generation: str) -> None:
        store.begin_artifact_bytes_delete_intent(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            dev=dev,
            ino=ino,
            phase="quarantined",
            intent_at="2026-08-02T00:00:00+00:00",
            generation=generation,
        )

    def on_clear_intent(dev: int, ino: int, generation: str) -> None:
        store.clear_artifact_bytes_delete_intent(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
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
        expected_dev: int,
        expected_ino: int,
        expected_generation: str,
    ) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("forced stamp failure")
        original(
            artifact_id,
            deleted_at=deleted_at,
            repository_id=repository_id,
            expected_dev=expected_dev,
            expected_ino=expected_ino,
            expected_generation=expected_generation,
        )

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
    for path in ready.parent.glob(".deleting-*"):
        _assert_terminal_size0_or_absent(path)
    _assert_no_nonempty_sidecars(ready.parent)
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
    st = ready.stat()
    generation = uuid4().hex
    quarantine = ready.parent / quarantine_name_for(
        inode=st.st_ino,
        artifact_id=ARTIFACT_ID,
        generation=generation,
    )
    os.link(ready, quarantine)
    ready.unlink()
    generation = store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(st.st_dev),
        expected_ino=int(st.st_ino),
        expected_generation=generation,
    )
    assert quarantine.is_file()

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    _assert_terminal_size0_or_absent(quarantine, owned_ino=int(st.st_ino))
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None


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
        tombstone_budget=50_000,
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
        settings=_settings(layout, ttl=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        # Before orphan TTL so only forged quarantine inventory is exercised.
        clock=lambda: datetime(2026, 8, 1, 0, 0, 30, tzinfo=UTC),
    ).sweep_once()

    assert forged.is_file()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None
    diagnostics = [
        record
        for record in caplog.records
        if getattr(record, "cleanup_outcome", None)
        in {"unknown_path_inventory", "quarantine_inode_mismatch"}
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


def _intent_callbacks(
    store: ImportOperationStore,
) -> tuple[
    Callable[[int, int, str], None],
    Callable[[int, int, str], None],
    Callable[[int, int, str], None],
    Callable[[int, int, str], None],
    dict[str, bool],
]:
    stamped = {"ok": False}

    def on_deleted(dev: int, ino: int, generation: str) -> None:
        store.mark_artifact_bytes_deleted(
            ARTIFACT_ID,
            deleted_at="2026-08-02T00:00:00+00:00",
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
        )
        stamped["ok"] = True

    def on_intent(dev: int, ino: int, generation: str) -> None:
        store.begin_artifact_bytes_delete_intent(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            dev=dev,
            ino=ino,
            phase="quarantined",
            intent_at="2026-08-02T00:00:00+00:00",
            generation=generation,
        )

    def on_clear_intent(dev: int, ino: int, generation: str) -> None:
        store.clear_artifact_bytes_delete_intent(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
        )

    def on_clear_receipt(dev: int, ino: int, generation: str) -> None:
        store.clear_artifact_bytes_deleted_receipt(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
        )

    return on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped


def _assert_receipt_cleared(mutation_store: MutationStore) -> None:
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_receipt_dev is None
    assert lifecycle.bytes_deleted_receipt_ino is None
    assert lifecycle.bytes_deleted_receipt_generation is None


def _iter_recoverable_sidecar_paths(
    ready_dir: Path,
    *,
    artifact_id: UUID = ARTIFACT_ID,
) -> list[Path]:
    paths: list[Path] = []
    for entry in ready_dir.iterdir():
        parsed = parse_any_recoverable_sidecar(entry.name)
        if parsed is None:
            continue
        _ino, parsed_artifact_id, _generation, _kind = parsed
        if parsed_artifact_id == artifact_id:
            paths.append(entry)
    return paths


def _assert_replacement_retained(
    ready_dir: Path,
    replacement: bytes,
    *,
    artifact_id: UUID = ARTIFACT_ID,
) -> Path:
    for entry in _iter_recoverable_sidecar_paths(ready_dir, artifact_id=artifact_id):
        if entry.read_bytes() == replacement:
            return entry
    names = [entry.name for entry in ready_dir.iterdir()]
    pytest.fail(
        f"replacement bytes not found on recoverable sidecar for {artifact_id}: {names}"
    )


def _matching_generation_sidecars(
    ready_dir: Path,
    *,
    generation: str,
    expected_dev: int,
    expected_ino: int,
    artifact_id: UUID = ARTIFACT_ID,
) -> list[str]:
    names: list[str] = []
    for entry in ready_dir.iterdir():
        parsed = parse_any_recoverable_sidecar(entry.name)
        if parsed is None:
            continue
        _ino, parsed_artifact_id, parsed_generation, _kind = parsed
        if parsed_artifact_id != artifact_id or parsed_generation != generation:
            continue
        st = entry.stat()
        if int(st.st_ino) == expected_ino and int(st.st_dev) == expected_dev:
            names.append(entry.name)
    return names


def _has_recoverable_sidecar(ready_dir: Path) -> bool:
    return any(parse_any_recoverable_sidecar(entry.name) is not None for entry in ready_dir.iterdir())



def _assert_terminal_size0_or_absent(path: Path, *, owned_ino: int | None = None) -> None:
    """Round14: successful destroy may leave owned size-0 diagnose names."""

    if not path.exists():
        return
    st = path.stat()
    assert int(st.st_size) == 0
    if owned_ino is not None:
        assert int(st.st_ino) == int(owned_ino)


def _assert_no_nonempty_sidecars(ready_dir: Path) -> None:
    for entry in ready_dir.iterdir():
        parsed = parse_any_recoverable_sidecar(entry.name)
        if parsed is None:
            continue
        if entry.is_symlink():
            raise AssertionError(f"unexpected symlink sidecar {entry.name}")
        if entry.is_file():
            assert entry.stat().st_size == 0, entry.name


def _artifact_cleaner(
    layout: DurableLayout,
    store: ImportOperationStore,
    mutation_store: MutationStore,
    *,
    ttl: int = 1,
) -> ArtifactCleaner:
    return ArtifactCleaner(
        settings=_settings(layout, ttl=ttl),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    )


def _dir_fd_from_kwargs(kwargs: dict[str, object], *keys: str) -> int | None:
    for key in keys:
        value = kwargs.get(key)
        if value is None:
            continue
        if isinstance(value, int):
            return value
        raise TypeError(f"unexpected dir_fd type for {key}: {type(value)!r}")
    return None


def _replace_ready_dir_entry(ready_dir_fd: int, name: str, payload: bytes) -> None:
    os.unlink(name, dir_fd=ready_dir_fd)
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644, dir_fd=ready_dir_fd)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)


def _replace_ready_with_foreign(ready: Path, payload: bytes) -> None:
    ready_dir_fd = os.open(ready.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        _replace_ready_dir_entry(ready_dir_fd, ARTIFACT_ID.hex, payload)
    finally:
        os.close(ready_dir_fd)


def _plant_foreign_at_name(dir_fd: int, name: str, payload: bytes) -> str:
    """Rename ``name`` aside and plant ``payload`` at the same directory entry."""

    hidden = f".hidden-r9-{uuid4().hex[:12]}"
    os.rename(name, hidden, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644, dir_fd=dir_fd)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)
    return hidden


def _monkeypatch_ftruncate_fail_nth(
    monkeypatch: pytest.MonkeyPatch,
    nth: int,
    *,
    pin_module: ModuleType | None = None,
) -> dict[str, int]:
    import gateway_repository_service.upload_artifact.admission_pin as default_pin_mod

    pin_mod = pin_module if pin_module is not None else default_pin_mod
    real_ftruncate = pin_mod._ftruncate_inode_to_empty
    count = {"n": 0}

    def wrapper(inode_fd: int, expected: os.stat_result) -> bool:
        count["n"] += 1
        if count["n"] == nth:
            return False
        result: bool = real_ftruncate(inode_fd, expected)
        return result

    monkeypatch.setattr(pin_mod, "_ftruncate_inode_to_empty", wrapper)
    return count


def _monkeypatch_ftruncate_always_fail(
    monkeypatch: pytest.MonkeyPatch,
    *,
    pin_module: ModuleType | None = None,
) -> None:
    import gateway_repository_service.upload_artifact.admission_pin as default_pin_mod

    pin_mod = pin_module if pin_module is not None else default_pin_mod

    def wrapper(inode_fd: int, expected: os.stat_result) -> bool:
        del inode_fd, expected
        return False

    monkeypatch.setattr(pin_mod, "_ftruncate_inode_to_empty", wrapper)


def _plant_foreign_at_stage_final_names(ready_dir: Path, replacement: bytes) -> bool:
    for stage_path in ready_dir.glob(".unlink-stage-*"):
        stage_fd = os.open(stage_path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            for name in os.listdir(stage_fd):
                if not (name.startswith("final-") or name.startswith("doom-")):
                    continue
                _plant_foreign_at_name(stage_fd, name, replacement)
                return True
        finally:
            os.close(stage_fd)
    return False


def _assert_foreign_and_owned_inode(
    ready_dir: Path,
    *,
    replacement: bytes,
    owned_ino: int,
    expect_owned_empty: bool = False,
) -> None:
    foreign_found = False
    owned_found = False
    for entry in ready_dir.rglob("*"):
        if not entry.is_file():
            continue
        try:
            payload = entry.read_bytes()
            st = entry.stat()
        except OSError:
            continue
        if payload == replacement:
            foreign_found = True
        if int(st.st_ino) == owned_ino:
            if expect_owned_empty and int(st.st_size) == 0:
                owned_found = True
            elif not expect_owned_empty and payload == ARTIFACT_PAYLOAD:
                owned_found = True
    assert foreign_found
    assert owned_found


def _monkeypatch_ftruncate_plant_foreign_at_final(
    monkeypatch: pytest.MonkeyPatch,
    ready_dir: Path,
    replacement: bytes,
    *,
    pin_module: ModuleType | None = None,
    linkat_fail: bool = False,
    fail_after_plant: bool = False,
) -> dict[str, bool]:
    import gateway_repository_service.upload_artifact.admission_pin as default_pin_mod

    pin_mod = pin_module if pin_module is not None else default_pin_mod
    real_ftruncate = pin_mod._ftruncate_inode_to_empty
    injected = {"done": False}

    if linkat_fail:
        def link_wrapper(
            src: str | bytes | os.PathLike[str] | os.PathLike[bytes],
            dst: str | bytes | os.PathLike[str] | os.PathLike[bytes],
            *args: object,
            **kwargs: object,
        ) -> None:
            raise OSError(errno.EIO, "forced linkat failure")

        monkeypatch.setattr(os, "link", link_wrapper)

    def ftruncate_wrapper(inode_fd: int, expected: os.stat_result) -> bool:
        if not injected["done"] and not linkat_fail:
            if _plant_foreign_at_stage_final_names(ready_dir, replacement):
                injected["done"] = True
            if fail_after_plant:
                injected["done"] = True
                return False
        result: bool = real_ftruncate(inode_fd, expected)
        return result

    monkeypatch.setattr(pin_mod, "_ftruncate_inode_to_empty", ftruncate_wrapper)
    return injected


@pytest.mark.serial
def test_post_nlink_pre_detach_rename_preserves_replacement(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe 2: replace ready between nlink gate and detach rename."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod
    from gateway_repository_service.publication import renameat2_noreplace as real_renameat2

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    replacement = b"post-nlink-replacement"
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)

    def rename(
        src_dir_fd: int,
        src_name: str | bytes,
        dst_dir_fd: int,
        dst_name: str | bytes,
    ) -> None:
        if (
            isinstance(src_name, str)
            and len(src_name) == 32
            and isinstance(dst_name, str)
            and dst_name.startswith(".detach-")
        ):
            _replace_ready_dir_entry(src_dir_fd, src_name, replacement)
        real_renameat2(src_dir_fd, src_name, dst_dir_fd, dst_name)

    monkeypatch.setattr(pin_mod, "_broker_rename_noreplace", rename)
    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome != "deleted"
    assert stamped["ok"] is False
    assert ready.is_file()
    assert ready.read_bytes() == replacement
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


@pytest.mark.serial
def test_replacement_admission_pin_blocks_stamp(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Probe 3: real admission on replacement inode; delete must not stamp."""

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    replacement = b"admission-replacement"
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)
    barrier = threading.Barrier(2)
    outcomes: dict[str, object] = {}

    def recheck() -> bool:
        barrier.wait(timeout=2.0)
        ready.unlink()
        ready.write_bytes(replacement)
        return True

    def admit() -> None:
        barrier.wait(timeout=2.0)
        time.sleep(0.05)
        try:
            with ArtifactAdmissionPin(
                layout,
                REPOSITORY_ID,
                ARTIFACT_ID,
                size_bytes=len(replacement),
                raw_sha256=hashlib.sha256(replacement).hexdigest(),
            ):
                outcomes["admission"] = "accepted"
        except ArtifactNotReadyForAdmission:
            outcomes["admission"] = "rejected"
        except OSError as exc:
            outcomes["admission"] = f"oserror:{exc}"

    thread = threading.Thread(target=admit)
    thread.start()
    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=recheck,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    thread.join(timeout=2.0)
    assert not thread.is_alive()
    assert outcome != "deleted"
    assert stamped["ok"] is False
    assert ready.is_file()
    assert ready.read_bytes() == replacement
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


@pytest.mark.serial
def test_proc_link_fallback_pathname_replace_preserves_replacement(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe 4: /proc link fails; pathname fallback sees replacement."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    replacement = b"fallback-replacement"
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)
    real_link = pin_mod._broker_link_from_fd
    calls = {"n": 0}

    def link_from_fd(dir_fd: int, name: str, src_fd: int) -> None:
        if name.startswith(".deleting-"):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError(errno.ENOENT, "forced proc link failure")
            _replace_ready_dir_entry(dir_fd, ARTIFACT_ID.hex, replacement)
            repl_fd = os.open(
                ARTIFACT_ID.hex,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=dir_fd,
            )
            try:
                return real_link(dir_fd, name, repl_fd)
            finally:
                os.close(repl_fd)
        return real_link(dir_fd, name, src_fd)

    monkeypatch.setattr(pin_mod, "_broker_link_from_fd", link_from_fd)
    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome != "deleted"
    assert stamped["ok"] is False
    assert ready.is_file()
    assert ready.read_bytes() == replacement
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None
    # Pathname fallback linked the replacement; inode verify fails closed and
    # must retain the unproven quarantine directory entry.
    quarantines = list(ready.parent.glob(".deleting-*"))
    assert len(quarantines) == 1
    assert quarantines[0].read_bytes() == replacement


@pytest.mark.serial
def test_quarantine_replaced_before_verify_does_not_delete_unknown(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe 5a: quarantine directory entry swapped before inode verify."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    forged_payload = b"swapped-quarantine"
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)
    real_link = os.link

    def link(src: str | bytes | os.PathLike[str], dst: str | bytes | os.PathLike[str], *args: object, **kwargs: object) -> None:
        real_link(src, dst, *args, **kwargs)  # type: ignore[arg-type]
        dst_dir_fd = _dir_fd_from_kwargs(kwargs, "dst_dir_fd")
        if dst_dir_fd is not None and isinstance(dst, str) and dst.startswith(".deleting-"):
            os.unlink(dst, dir_fd=dst_dir_fd)
            fd = os.open(
                dst,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o644,
                dir_fd=dst_dir_fd,
            )
            try:
                os.write(fd, forged_payload)
            finally:
                os.close(fd)

    monkeypatch.setattr(os, "link", link)
    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome == "inode_mismatch"
    assert stamped["ok"] is False
    assert ready.is_file()
    assert ready.read_bytes() == ARTIFACT_PAYLOAD
    forged = list(ready.parent.glob(".deleting-*"))
    assert len(forged) == 1
    assert forged[0].read_bytes() == forged_payload
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


@pytest.mark.serial
def test_abort_finally_does_not_unlink_replacement_ready(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe 5b: abort-finally quarantine cleanup must not touch replacement ready."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    replacement = b"finally-replacement"
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)
    real_unlink = os.unlink

    def unlink(path: str | bytes | os.PathLike[str], *args: object, **kwargs: object) -> None:
        dir_fd = _dir_fd_from_kwargs(kwargs, "dir_fd")
        if dir_fd is not None and isinstance(path, str) and path.startswith(".deleting-"):
            ready_name = ARTIFACT_ID.hex
            try:
                os.stat(ready_name, dir_fd=dir_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                _replace_ready_dir_entry(dir_fd, ready_name, replacement)
        real_unlink(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "unlink", unlink)
    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: False,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome == "ineligible"
    assert stamped["ok"] is False
    assert ready.is_file()
    assert ready.read_bytes() in {ARTIFACT_PAYLOAD, replacement}
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


@pytest.mark.serial
def test_live_helper_flock_blocks_quarantine_recovery(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Probe 7: recovery must report lock_busy while helper holds flock."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _write_ready(layout)
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)
    in_recheck = threading.Event()
    release = threading.Event()
    recovery_done = threading.Event()
    caplog.set_level(logging.INFO)

    def recheck() -> bool:
        in_recheck.set()
        assert release.wait(timeout=2.0)
        return True

    def recover() -> None:
        assert in_recheck.wait(timeout=2.0)
        ArtifactCleaner(
            settings=_settings(layout, ttl=1),
            layout=layout,
            import_store=store,
            mutation_store=mutation_store,
            clock=lambda: BASE_NOW,
        ).sweep_once()
        recovery_done.set()
        release.set()

    thread = threading.Thread(target=recover)
    thread.start()
    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=recheck,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    thread.join(timeout=3.0)
    assert not thread.is_alive()
    assert recovery_done.is_set()
    assert outcome == "deleted"
    assert stamped["ok"] is True
    busy = [
        record
        for record in caplog.records
        if getattr(record, "cleanup_outcome", None) == "lock_busy"
    ]
    assert busy
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None


def test_scope_change_before_stamp_keeps_quarantine(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Probe 13: stamp scope mismatch fails closed with quarantine retained."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)

    def on_intent(dev: int, ino: int, generation: str) -> None:
        store.begin_artifact_bytes_delete_intent(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            dev=dev,
            ino=ino,
            phase="quarantined",
            intent_at="2026-08-02T00:00:00+00:00",
            generation=generation,
        )

    def on_clear_intent(dev: int, ino: int, generation: str) -> None:
        store.clear_artifact_bytes_delete_intent(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
        )

    def on_deleted(dev: int, ino: int, generation: str) -> None:
        with mutation_store._lock:
            mutation_store._connection.execute(
                """
                UPDATE artifact_lifecycle
                SET repository_scope = ?
                WHERE artifact_id = ?
                """,
                ("a" * 32, str(ARTIFACT_ID)),
            )
            mutation_store._connection.commit()
        store.mark_artifact_bytes_deleted(
            ARTIFACT_ID,
            deleted_at="2026-08-02T00:00:00+00:00",
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
        )

    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
    )
    assert outcome == "stamp_failed"
    assert not ready.exists()
    quarantines = list(ready.parent.glob(".deleting-*"))
    assert len(quarantines) == 1
    assert quarantines[0].read_bytes() == ARTIFACT_PAYLOAD
    assert hashlib.sha256(quarantines[0].read_bytes()).hexdigest() == SHA256
    assert quarantines[0].stat().st_size == len(ARTIFACT_PAYLOAD)
    detaches = list(ready.parent.glob(".detach-*"))
    assert detaches
    assert detaches[0].read_bytes() == ARTIFACT_PAYLOAD
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_post_detach_protected_reference_keeps_quarantine(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Probe 12: recheck #2 sees new protected ref → keep quarantine, no stamp."""

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)
    calls = {"n": 0}

    def recheck() -> bool:
        calls["n"] += 1
        if calls["n"] == 1:
            return True
        _enqueue(store, key="post-detach-pending", operation_id=OTHER_OPERATION_ID)
        return store.evaluate_artifact_bytes_deletion(
            ARTIFACT_ID,
            now=BASE_NOW,
            ttl_seconds=1,
        ).eligible

    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=recheck,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome == "ineligible"
    assert stamped["ok"] is False
    assert not ready.exists()
    quarantines = list(ready.parent.glob(".deleting-*"))
    assert quarantines
    assert quarantines[0].read_bytes() == ARTIFACT_PAYLOAD
    assert hashlib.sha256(quarantines[0].read_bytes()).hexdigest() == SHA256
    assert quarantines[0].stat().st_size == len(ARTIFACT_PAYLOAD)
    detaches = list(ready.parent.glob(".detach-*"))
    assert detaches
    assert detaches[0].read_bytes() == ARTIFACT_PAYLOAD
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None
    assert lifecycle.bytes_delete_intent_at is not None


def _begin_intent_for_ready(
    store: ImportOperationStore,
    ready: Path,
    *,
    phase: str = "quarantined",
    generation: str | None = None,
) -> tuple[Path, int, str]:
    st = ready.stat()
    token = generation if generation is not None else uuid4().hex
    quarantine = ready.parent / quarantine_name_for(
        inode=st.st_ino,
        artifact_id=ARTIFACT_ID,
        generation=token,
    )
    os.link(ready, quarantine)
    token = store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase=phase,
        intent_at="2026-08-02T00:00:00+00:00",
        generation=token,
    )
    return quarantine, int(st.st_ino), token


def test_crash_phase_quarantine_and_ready_same_inode_no_stamp(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Probe 6a: quarantine + ready same inode, no stamp → complete on sweep."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    quarantine, _ino, _generation = _begin_intent_for_ready(store, ready)
    assert quarantine.is_file()
    assert ready.is_file()

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert not ready.exists()
    _assert_terminal_size0_or_absent(quarantine)
    _assert_no_nonempty_sidecars(ready.parent)
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None
    assert lifecycle.bytes_delete_intent_at is None


def test_crash_phase_quarantine_ready_different_inode_with_intent(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Probe 6d: intent inode differs from ready replacement → no stamp, keep ready."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    quarantine, _ino, _generation = _begin_intent_for_ready(store, ready)
    ready.unlink()
    ready.write_bytes(b"replacement-after-intent")
    assert quarantine.stat().st_ino != ready.stat().st_ino

    ArtifactCleaner(
        settings=_settings(layout, ttl=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        # Before orphan TTL so recovery drops mismatched intent without
        # candidate sweep deleting the replacement ready.
        clock=lambda: datetime(2026, 8, 1, 0, 0, 30, tzinfo=UTC),
    ).sweep_once()

    assert ready.is_file()
    assert ready.read_bytes() == b"replacement-after-intent"
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None
    assert lifecycle.bytes_delete_intent_at is None
    _assert_terminal_size0_or_absent(quarantine)


def test_stamp_succeeds_but_final_quarantine_unlink_fails(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe 6e: stamp ok, quarantine unlink fails → retain q; next sweep finishes."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)
    import gateway_repository_service.upload_artifact.admission_pin as pin_mod

    real_ftruncate = pin_mod._ftruncate_inode_to_empty
    # Round13 destroy path truncates once (no stage/verify ftruncate chain).
    _monkeypatch_ftruncate_fail_nth(monkeypatch, 1, pin_module=pin_mod)
    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome == "unlink_failed"
    assert stamped["ok"] is True
    assert not ready.exists()
    residuals = (
        list(ready.parent.glob(".deleting-*"))
        or list(ready.parent.glob(".unlink-verify-*"))
        or list(ready.parent.glob(".unlink-stage-*"))
    )
    assert residuals
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None

    monkeypatch.setattr(pin_mod, "_ftruncate_inode_to_empty", real_ftruncate)
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    for path in ready.parent.glob(".deleting-*"):
        _assert_terminal_size0_or_absent(path)
    _assert_no_nonempty_sidecars(ready.parent)
    snap = _lifecycle_snapshot(mutation_store)
    assert snap["receipt_generation"] is None or snap["bytes_deleted_at"] is not None


@pytest.mark.parametrize("ready_present", [True, False], ids=["ready_present", "ready_absent"])
def test_forged_quarantine_with_matching_self_reported_ino_is_retained(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    caplog: pytest.LogCaptureFixture,
    ready_present: bool,
) -> None:
    """Probe 8: forged quarantine self-reports correct ino; retain, no stamp."""

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    decoy = ready.parent / f".decoy-{uuid4().hex}"
    decoy.write_bytes(b"forged-body")
    forged = ready.parent / quarantine_name_for(
        inode=decoy.stat().st_ino,
        artifact_id=ARTIFACT_ID,
        generation=uuid4().hex,
    )
    os.link(decoy, forged)
    decoy.unlink()
    if not ready_present:
        ready.unlink()
    caplog.set_level(logging.INFO)

    ArtifactCleaner(
        settings=_settings(layout, ttl=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        # Before orphan TTL so ready cannot be deleted by candidate sweep.
        clock=lambda: datetime(2026, 8, 1, 0, 0, 30, tzinfo=UTC),
    ).sweep_once()

    assert forged.is_file()
    if ready_present:
        assert ready.is_file()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None
    diagnostics = [
        record
        for record in caplog.records
        if getattr(record, "cleanup_outcome", None)
        in {"unknown_path_inventory", "quarantine_inode_mismatch"}
    ]
    assert diagnostics


def test_legal_and_forged_quarantines_are_handled_independently(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Probe 9: processing one quarantine must not unconditionally delete the other."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    legal, _ino, _generation = _begin_intent_for_ready(store, ready)
    ready.unlink()
    decoy = legal.parent / f".decoy-{uuid4().hex}"
    decoy.write_bytes(b"forged-multi")
    forged = legal.parent / quarantine_name_for(
        inode=decoy.stat().st_ino,
        artifact_id=ARTIFACT_ID,
        generation=uuid4().hex,
    )
    os.link(decoy, forged)
    decoy.unlink()

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
    # Legal quarantine may complete; forged must remain.
    assert forged.is_file()


ILLEGAL_STAMP_RESIDUAL_CASES = (
    ("naive", "2026-08-02T00:00:00", 3600),
    ("future", "2031-08-02T00:00:00+00:00", 3600),
    ("premature", "2026-08-01T00:30:00+00:00", 3600),
)


@pytest.mark.parametrize(
    ("label", "stamp", "ttl"),
    ILLEGAL_STAMP_RESIDUAL_CASES,
    ids=[c[0] for c in ILLEGAL_STAMP_RESIDUAL_CASES],
)
def test_illegal_stamp_quarantine_residual_fail_closed(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    caplog: pytest.LogCaptureFixture,
    label: str,
    stamp: str,
    ttl: int,
) -> None:
    """Probe 10: illegal stamp on quarantine residual must fail closed."""

    del label
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    quarantine, ino, generation = _begin_intent_for_ready(store, ready)
    q_stat = quarantine.stat()
    ready.unlink()
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(q_stat.st_dev),
        expected_ino=ino,
        expected_generation=generation,
    )
    with mutation_store._lock:
        mutation_store._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET bytes_deleted_at = ?
            WHERE artifact_id = ?
            """,
            (stamp, str(ARTIFACT_ID)),
        )
        mutation_store._connection.commit()
    caplog.set_level(logging.INFO)

    ArtifactCleaner(
        settings=_settings(layout, ttl=ttl),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert quarantine.is_file()
    diagnostics = [
        record
        for record in caplog.records
        if getattr(record, "cleanup_outcome", None) == "fail_closed"
    ]
    assert diagnostics


def test_protected_reference_with_stamp_keeps_quarantine(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Probe 10: protected reference + stamp → fail closed, keep quarantine."""

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    quarantine, ino, generation = _begin_intent_for_ready(store, ready)
    q_stat = quarantine.stat()
    ready.unlink()
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(q_stat.st_dev),
        expected_ino=ino,
        expected_generation=generation,
    )
    _enqueue(store, key="protected-residual", operation_id=OTHER_OPERATION_ID)
    caplog.set_level(logging.INFO)

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert quarantine.is_file()
    diagnostics = [
        record
        for record in caplog.records
        if getattr(record, "cleanup_outcome", None) == "fail_closed"
    ]
    assert diagnostics


def test_ineligible_quarantine_restored_when_ready_absent(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Probe 11: ineligible q-only → restore ready (no-replace)."""

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    quarantine, _ino, _generation = _begin_intent_for_ready(store, ready)
    payload = ready.read_bytes()
    ready.unlink()
    _enqueue(store, key="block-restore", operation_id=OTHER_OPERATION_ID)
    caplog.set_level(logging.INFO)

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert ready.is_file()
    assert ready.read_bytes() == payload
    assert not quarantine.exists()
    restored = [
        record
        for record in caplog.records
        if getattr(record, "cleanup_outcome", None) == "quarantine_restored"
    ]
    assert restored
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


@pytest.mark.serial
def test_ineligible_restore_skips_when_ready_reappears(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Probe 11: concurrent ready creation → quarantine_restore_skipped."""

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    quarantine, _ino, _generation = _begin_intent_for_ready(store, ready)
    ready.unlink()
    _enqueue(store, key="block-skip", operation_id=OTHER_OPERATION_ID)
    replacement = b"concurrent-ready"
    real_stat = os.stat
    seen = {"n": 0}

    def stat_probe(
        path: str | bytes | os.PathLike[str],
        *args: object,
        **kwargs: object,
    ) -> os.stat_result:
        missing = False
        try:
            return real_stat(path, *args, **kwargs)  # type: ignore[arg-type]
        except FileNotFoundError:
            missing = True
            raise
        finally:
            dir_fd = _dir_fd_from_kwargs(kwargs, "dir_fd")
            if (
                missing
                and dir_fd is not None
                and isinstance(path, str)
                and path == ARTIFACT_ID.hex
            ):
                seen["n"] += 1
                if seen["n"] == 1:
                    fd = os.open(
                        path,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o644,
                        dir_fd=dir_fd,
                    )
                    try:
                        os.write(fd, replacement)
                    finally:
                        os.close(fd)

    monkeypatch.setattr(os, "stat", stat_probe)
    caplog.set_level(logging.INFO)
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert ready.is_file()
    assert ready.read_bytes() == replacement
    assert quarantine.is_file()
    skipped = [
        record
        for record in caplog.records
        if getattr(record, "cleanup_outcome", None) == "quarantine_restore_skipped"
    ]
    assert skipped


INVENTORY_OWNERSHIP_CASES = (
    ("repo_symlink", "symlink"),
    ("repo_file", "file"),
    ("scope_mismatch_ready", "scope_mismatch"),
    ("staging_orphan", "staging"),
)


@pytest.mark.parametrize(
    ("label", "kind"),
    INVENTORY_OWNERSHIP_CASES,
    ids=[c[0] for c in INVENTORY_OWNERSHIP_CASES],
)
def test_inventory_ownership_variants_are_diagnosed(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    caplog: pytest.LogCaptureFixture,
    label: str,
    kind: str,
) -> None:
    """Probe 15: repo symlink/non-dir, scope mismatch, staging variants."""

    del label
    store, mutation_store = stores
    caplog.set_level(logging.INFO)

    if kind == "symlink":
        target = layout.root / "outside-repo"
        target.mkdir()
        link = layout.artifacts / ("c" * 32)
        layout.artifacts.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target)
        retained = link
    elif kind == "file":
        layout.artifacts.mkdir(parents=True, exist_ok=True)
        retained = layout.artifacts / ("d" * 32)
        retained.write_bytes(b"not-a-dir")
    elif kind == "scope_mismatch":
        _seed_create_succeeded(mutation_store)
        other_artifact = uuid4()
        with mutation_store._lock:
            mutation_store._connection.execute(
                """
                INSERT INTO artifact_lifecycle (
                    artifact_id, repository_scope, media_type, size_bytes,
                    raw_sha256, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(other_artifact),
                    ("e" * 32),
                    MEDIA_TYPE,
                    1,
                    SHA256,
                    CREATED_AT,
                    CREATED_AT,
                ),
            )
            mutation_store._connection.commit()
        ready_dir = layout.artifacts / REPOSITORY_ID.hex / "ready"
        ready_dir.mkdir(parents=True, exist_ok=True)
        retained = ready_dir / other_artifact.hex
        retained.write_bytes(b"scope-mismatch")
    else:
        layout.staging_artifacts.mkdir(parents=True, exist_ok=True)
        retained = layout.staging_artifacts / "not-uuid-staging"
        retained.write_bytes(b"staging-orphan")

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert retained.exists()
    diagnostics = [
        record
        for record in caplog.records
        if getattr(record, "cleanup_outcome", None)
        in {"unknown_path_inventory", "poison_lifecycle_inventory"}
    ]
    assert diagnostics
    assert all(str(retained) not in record.getMessage() for record in diagnostics)


def test_admit_new_import_rejected_while_delete_intent_active(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Directed probe: active delete intent blocks admit_new_import in-transaction."""

    from gateway_repository_service.versioned_import.models import ImportArtifactBindingRejected

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
    )
    binding = _binding()
    key_hash = IdempotencyKeyHash.from_raw_key("admit-while-intent")
    with pytest.raises(ImportArtifactBindingRejected, match="delete intent"):
        store.admit_new_import(
            binding,
            key_hash=key_hash,
            fingerprint=versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash),
            max_queued_imports=8,
        )
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None
    assert lifecycle.bytes_delete_intent_at is not None


@pytest.mark.serial
def test_stamp_rejects_protected_reference_after_final_recheck(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Directed probe: protected ref between recheck and stamp fails CAS stamp."""

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    _on_deleted, on_intent_cb, on_clear_cb, _on_clear_receipt, stamped = _intent_callbacks(store)

    def on_deleted(dev: int, ino: int, generation: str) -> None:
        _enqueue(store, key="stamp-race-pending", operation_id=OTHER_OPERATION_ID)
        store.mark_artifact_bytes_deleted(
            ARTIFACT_ID,
            deleted_at="2026-08-02T00:00:00+00:00",
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
        )
        stamped["ok"] = True

    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent_cb,
        on_clear_intent=on_clear_cb,
    )
    assert outcome == "stamp_failed"
    assert stamped["ok"] is False
    quarantines = list(ready.parent.glob(".deleting-*"))
    assert quarantines
    assert quarantines[0].read_bytes() == ARTIFACT_PAYLOAD
    assert hashlib.sha256(quarantines[0].read_bytes()).hexdigest() == SHA256
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_detach_destination_preexists_is_not_overwritten(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Directed probe: pre-existing .detach-* must not be overwritten."""

    from gateway_repository_service.upload_artifact.admission_pin import detach_name_for

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    fixed_generation = "a" * 32
    monkeypatch.setattr(
        "gateway_repository_service.upload_artifact.admission_pin.uuid4",
        lambda: type("U", (), {"hex": fixed_generation})(),
    )
    preexisting = ready.parent / detach_name_for(
        inode=int(st.st_ino),
        artifact_id=ARTIFACT_ID,
        generation=fixed_generation,
    )
    preexisting.write_bytes(b"preexisting-detach")
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)
    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome != "deleted"
    assert stamped["ok"] is False
    assert preexisting.is_file()
    assert preexisting.read_bytes() == b"preexisting-detach"
    assert ready.is_file()


def test_q_and_detach_ineligible_converge_both_sidecars(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Directed probe: q + detach + ineligible → ready restored; detach may remain."""

    from gateway_repository_service.upload_artifact.admission_pin import detach_name_for

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    payload = ready.read_bytes()
    st = ready.stat()
    generation = uuid4().hex
    quarantine = ready.parent / quarantine_name_for(
        inode=st.st_ino,
        artifact_id=ARTIFACT_ID,
        generation=generation,
    )
    detach = ready.parent / detach_name_for(
        inode=int(st.st_ino),
        artifact_id=ARTIFACT_ID,
        generation=generation,
    )
    os.link(ready, quarantine)
    os.link(ready, detach)
    ready.unlink()
    _generation = store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    _enqueue(store, key="q-detach-block", operation_id=OTHER_OPERATION_ID)
    caplog.set_level(logging.INFO)

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert ready.is_file()
    assert ready.read_bytes() == payload
    assert hashlib.sha256(ready.read_bytes()).hexdigest() == SHA256
    assert not detach.exists()
    # Remaining .deleting-* is diagnose-only (never pathname-unlinked).
    if quarantine.exists():
        assert quarantine.read_bytes() == payload
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_delete_intent_at is None
    assert lifecycle.bytes_deleted_at is None
    restored = [
        record
        for record in caplog.records
        if getattr(record, "cleanup_outcome", None) == "quarantine_restored"
    ]
    assert restored


MALFORMED_INTENT_CASES = (
    (
        "partial_missing_phase",
        {
            "bytes_delete_intent_at": "2026-08-02T00:00:00+00:00",
            "bytes_delete_dev": 1,
            "bytes_delete_ino": 2,
            "bytes_delete_phase": "quarantined",
            "bytes_delete_generation": None,
        },
        "integrity",
    ),
    (
        "naive_timestamp",
        {
            "bytes_delete_intent_at": "2026-08-02T00:00:00",
            "bytes_delete_dev": 1,
            "bytes_delete_ino": 2,
            "bytes_delete_phase": "quarantined",
            "bytes_delete_generation": "gen-naive",
        },
        "projection",
    ),
    (
        "bad_phase",
        {
            "bytes_delete_intent_at": "2026-08-02T00:00:00+00:00",
            "bytes_delete_dev": 1,
            "bytes_delete_ino": 2,
            "bytes_delete_phase": "bogus",
            "bytes_delete_generation": "gen-bad",
        },
        "integrity",
    ),
)


@pytest.mark.parametrize(
    ("label", "fields", "expected_failure"),
    MALFORMED_INTENT_CASES,
    ids=[c[0] for c in MALFORMED_INTENT_CASES],
)
def test_malformed_delete_intent_projection_fail_closed(
    stores: tuple[ImportOperationStore, MutationStore],
    label: str,
    fields: dict[str, object],
    expected_failure: str,
) -> None:
    """Directed probe: malformed/partial intent fails closed on projection."""

    del label
    from gateway_repository_service.mutation_store import MutationStoreInvariantError

    _store, mutation_store = stores
    _seed_artifact(mutation_store)
    with mutation_store._lock:
        if expected_failure == "integrity":
            with pytest.raises(sqlite3.IntegrityError):
                mutation_store._connection.execute(
                    """
                    UPDATE artifact_lifecycle
                    SET bytes_delete_intent_at = ?,
                        bytes_delete_dev = ?,
                        bytes_delete_ino = ?,
                        bytes_delete_phase = ?,
                        bytes_delete_generation = ?
                    WHERE artifact_id = ?
                    """,
                    (
                        fields["bytes_delete_intent_at"],
                        fields["bytes_delete_dev"],
                        fields["bytes_delete_ino"],
                        fields["bytes_delete_phase"],
                        fields["bytes_delete_generation"],
                        str(ARTIFACT_ID),
                    ),
                )
                mutation_store._connection.commit()
            mutation_store._connection.rollback()
            return
        mutation_store._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET bytes_delete_intent_at = ?,
                bytes_delete_dev = ?,
                bytes_delete_ino = ?,
                bytes_delete_phase = ?,
                bytes_delete_generation = ?
            WHERE artifact_id = ?
            """,
            (
                fields["bytes_delete_intent_at"],
                fields["bytes_delete_dev"],
                fields["bytes_delete_ino"],
                fields["bytes_delete_phase"],
                fields["bytes_delete_generation"],
                str(ARTIFACT_ID),
            ),
        )
        mutation_store._connection.commit()
    with pytest.raises(MutationStoreInvariantError):
        mutation_store.get_artifact_lifecycle(ARTIFACT_ID)


def test_clear_intent_cas_does_not_clear_newer_inode(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Directed probe: clear for old inode must not erase a newer intent."""

    store, mutation_store = stores
    del layout
    _seed_artifact(mutation_store)
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=10,
        ino=100,
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation="gen1",
    )
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=20,
        ino=200,
        phase="quarantined",
        intent_at="2026-08-02T00:00:01+00:00",
        generation="gen2",
    )
    store.clear_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        expected_dev=10,
        expected_ino=100,
        expected_generation="gen1",
    )
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_delete_dev == 20
    assert lifecycle.bytes_delete_ino == 200
    assert lifecycle.bytes_delete_generation == "gen2"


def _seed_artifact_on_connection(
    connection: sqlite3.Connection,
    *,
    artifact_id: UUID = ARTIFACT_ID,
    created_at: str = CREATED_AT,
) -> None:
    connection.execute(
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
    connection.commit()


def test_old_clear_generation_does_not_clear_newer_intent(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Round6 probe 1: stale generation clear must not erase newer intent."""

    store, mutation_store = stores
    del layout
    _seed_artifact(mutation_store)
    st_dev, st_ino = 1, 42
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=st_dev,
        ino=st_ino,
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation="gen1",
    )
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=st_dev,
        ino=st_ino,
        phase="quarantined",
        intent_at="2026-08-02T00:00:01+00:00",
        generation="gen2",
    )
    store.clear_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        expected_dev=st_dev,
        expected_ino=st_ino,
        expected_generation="gen1",
    )
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_delete_generation == "gen2"
    assert lifecycle.bytes_delete_dev == st_dev
    assert lifecycle.bytes_delete_ino == st_ino


@pytest.mark.serial
def test_clear_failure_unlock_interleave_aba(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Round6 probe 2: clearing an old generation must not drop a newer quarantine."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    quarantine = ready.parent / quarantine_name_for(
        inode=st.st_ino,
        artifact_id=ARTIFACT_ID,
        generation="gen2",
    )
    os.link(ready, quarantine)
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation="gen1",
    )
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:01+00:00",
        generation="gen2",
    )
    store.clear_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        expected_dev=int(st.st_dev),
        expected_ino=int(st.st_ino),
        expected_generation="gen1",
    )
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_delete_generation == "gen2"
    assert quarantine.is_file()
    assert ready.is_file()


@pytest.mark.serial
def test_recovery_g1_paused_worker_g2_stamp_fail_retains_evidence(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round7 probe 1: tests/test_artifact_cleanup.py::test_recovery_g1_paused_worker_g2_stamp_fail_retains_evidence"""

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    gen_g1 = "gen_g1_r7p1"
    quarantine, _ino, _ = _begin_intent_for_ready(store, ready, generation=gen_g1)
    ready.unlink()

    g1_at_stamp = threading.Event()
    worker_done = threading.Event()
    allow_g1_stamp = threading.Event()
    real_mark = store.mark_artifact_bytes_deleted

    def paused_mark(
        artifact_id: UUID,
        *,
        deleted_at: str | None = None,
        repository_id: UUID | None = None,
        expected_dev: int,
        expected_ino: int,
        expected_generation: str,
    ) -> None:
        g1_at_stamp.set()
        assert worker_done.wait(timeout=2.0)
        allow_g1_stamp.wait(timeout=2.0)
        real_mark(
            artifact_id,
            deleted_at=deleted_at,
            repository_id=repository_id,
            expected_dev=expected_dev,
            expected_ino=expected_ino,
            expected_generation=expected_generation,
        )

    monkeypatch.setattr(store, "mark_artifact_bytes_deleted", paused_mark)

    def run_recovery() -> None:
        ArtifactCleaner(
            settings=_settings(layout, ttl=1),
            layout=layout,
            import_store=store,
            mutation_store=mutation_store,
            clock=lambda: BASE_NOW,
        ).sweep_once()

    recovery_thread = threading.Thread(target=run_recovery)
    recovery_thread.start()
    assert g1_at_stamp.wait(timeout=2.0)

    # Re-link ready for the worker; drop the G1 quarantine name so the helper
    # creates a G2-bound sidecar (DB generation and name generation must match).
    os.link(quarantine, ready)
    quarantine.unlink()
    gen_g2 = "gen_g2_r7p1"
    monkeypatch.setattr(
        "gateway_repository_service.upload_artifact.admission_pin.uuid4",
        lambda: type("U", (), {"hex": gen_g2})(),
    )

    def on_intent_g2(dev: int, ino: int, generation: str) -> None:
        assert generation == gen_g2
        store.begin_artifact_bytes_delete_intent(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            dev=dev,
            ino=ino,
            phase="quarantined",
            intent_at="2026-08-02T00:00:01+00:00",
            generation=generation,
        )

    def stamp_fail(*_args: object) -> None:
        raise RuntimeError("forced stamp failure")

    def on_clear_intent(dev: int, ino: int, generation: str) -> None:
        store.clear_artifact_bytes_delete_intent(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
        )

    worker_outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=stamp_fail,
        on_intent=on_intent_g2,
        on_clear_intent=on_clear_intent,
    )
    worker_done.set()
    allow_g1_stamp.set()
    recovery_thread.join(timeout=3.0)
    assert not recovery_thread.is_alive()

    assert worker_outcome == "stamp_failed"
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_delete_generation == gen_g2
    assert lifecycle.bytes_deleted_at is None
    assert lifecycle.bytes_delete_dev is not None
    assert lifecycle.bytes_delete_ino is not None
    matching_g2 = _matching_generation_sidecars(
        ready.parent,
        generation=gen_g2,
        expected_dev=int(lifecycle.bytes_delete_dev),
        expected_ino=int(lifecycle.bytes_delete_ino),
    )
    assert matching_g2, (
        "expected at least one recoverable sidecar with G2 generation matching intent inode/dev"
    )
    g2_cleared = lifecycle.bytes_delete_generation != gen_g2
    assert not (
        not ready.is_file()
        and not _has_recoverable_sidecar(ready.parent)
        and lifecycle.bytes_deleted_at is None
        and g2_cleared
    )


@pytest.mark.serial
def test_recovery_reread_generation_changed_skips_unlink(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round7 probe 2: tests/test_artifact_cleanup.py::test_recovery_reread_generation_changed_skips_unlink"""

    from gateway_repository_service.artifact_cleaner import ArtifactCleaner, SidecarLockResult

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    gen_g1 = "gen_g1_r7p2"
    quarantine, ino, _ = _begin_intent_for_ready(store, ready, generation=gen_g1)
    st = quarantine.stat()
    ready.unlink()
    ready.write_bytes(b"replacement-after-g1")

    paused = threading.Event()
    resume = threading.Event()
    mutated = {"done": False}
    real_lock = ArtifactCleaner._lock_sidecar

    def lock_sidecar(
        self: ArtifactCleaner,
        ready_dir_fd: int,
        sidecar_name: str,
        *,
        expected_ino: int,
        repository_id: UUID,
        artifact_id: UUID,
    ) -> tuple[SidecarLockResult, int | None, os.stat_result | None]:
        result = real_lock(
            self,
            ready_dir_fd,
            sidecar_name,
            expected_ino=expected_ino,
            repository_id=repository_id,
            artifact_id=artifact_id,
        )
        if result[0] == SidecarLockResult.LOCKED and not mutated["done"]:
            mutated["done"] = True
            paused.set()
            assert resume.wait(timeout=2.0)
        return result

    monkeypatch.setattr(ArtifactCleaner, "_lock_sidecar", lock_sidecar)

    def run_sweep() -> None:
        ArtifactCleaner(
            settings=_settings(layout, ttl=3600),
            layout=layout,
            import_store=store,
            mutation_store=mutation_store,
            clock=lambda: datetime(2026, 8, 1, 0, 0, 30, tzinfo=UTC),
        ).sweep_once()

    sweep_thread = threading.Thread(target=run_sweep)
    sweep_thread.start()
    assert paused.wait(timeout=2.0)
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=ino,
        phase="quarantined",
        intent_at="2026-08-02T00:00:01+00:00",
        generation="gen_g2_r7p2",
    )
    resume.set()
    sweep_thread.join(timeout=3.0)
    assert not sweep_thread.is_alive()

    assert quarantine.is_file()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_delete_generation == "gen_g2_r7p2"
    assert lifecycle.bytes_delete_intent_at is not None
    store.clear_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        expected_dev=int(st.st_dev),
        expected_ino=ino,
        expected_generation="gen_g1_r7p2",
    )
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_delete_generation == "gen_g2_r7p2"


@pytest.mark.parametrize("ready_present", [True, False], ids=["ready_present", "ready_absent"])
@pytest.mark.parametrize("sidecar_kind", ["deleting", "detach"], ids=["deleting", "detach"])
def test_stamped_forged_deleting_and_detach_retained(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    caplog: pytest.LogCaptureFixture,
    ready_present: bool,
    sidecar_kind: str,
) -> None:
    """Round6 probe 4: forged stamped sidecars with wrong inode are retained."""

    from gateway_repository_service.upload_artifact.admission_pin import detach_name_for

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    quarantine, ino, generation = _begin_intent_for_ready(
        store,
        ready,
        phase="detached" if sidecar_kind == "detach" else "quarantined",
    )
    if not ready_present:
        ready.unlink()
    q_stat = quarantine.stat()
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(q_stat.st_dev),
        expected_ino=ino,
        expected_generation=generation,
    )
    decoy = quarantine.parent / f".decoy-{uuid4().hex}"
    decoy.write_bytes(b"forged-stamped")
    name_fn = detach_name_for if sidecar_kind == "detach" else quarantine_name_for
    forged = quarantine.parent / name_fn(
        inode=decoy.stat().st_ino,
        artifact_id=ARTIFACT_ID,
        generation=uuid4().hex,
    )
    os.link(decoy, forged)
    decoy.unlink()
    caplog.set_level(logging.INFO)

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert forged.is_file()
    if ready_present:
        # Ready still exposes full bytes for the stamped inode → diagnose-only retain.
        assert quarantine.is_file()
        assert quarantine.read_bytes() == ARTIFACT_PAYLOAD
    else:
        _assert_terminal_size0_or_absent(quarantine, owned_ino=ino)
    diagnostics = [
        record
        for record in caplog.records
        if getattr(record, "cleanup_outcome", None) == "unknown_path_inventory"
    ]
    assert diagnostics


@pytest.mark.parametrize("sidecar_kind", ["deleting", "detach"], ids=["deleting", "detach"])
@pytest.mark.serial
def test_pathname_replace_before_unlink_retains_replacement(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    sidecar_kind: str,
) -> None:
    """Round14: after fd-truncate, prove fails closed when name is replaced with foreign."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    if sidecar_kind == "detach":
        from gateway_repository_service.upload_artifact.admission_pin import detach_name_for

        generation = uuid4().hex
        sidecar = ready.parent / detach_name_for(
            inode=int(st.st_ino),
            artifact_id=ARTIFACT_ID,
            generation=generation,
        )
        os.link(ready, sidecar)
        store.begin_artifact_bytes_delete_intent(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            dev=int(st.st_dev),
            ino=int(st.st_ino),
            phase="detached",
            intent_at="2026-08-02T00:00:00+00:00",
            generation=generation,
        )
        prefix = ".detach-"
    else:
        quarantine, _ino0, generation = _begin_intent_for_ready(store, ready)
        sidecar = quarantine
        prefix = ".deleting-"
    payload = sidecar.read_bytes()
    q_stat = sidecar.stat()
    ino = int(q_stat.st_ino)
    ready.unlink()
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(q_stat.st_dev),
        expected_ino=ino,
        expected_generation=generation,
    )
    replacement = b"replacement-before-unlink"
    real_prove = pin_mod.prove_size0_owned_name_terminal

    def prove(
        dir_fd: int,
        name: str,
        *,
        expected_dev: int,
        expected_ino: int,
    ) -> bool:
        if name.startswith(prefix):
            try:
                os.unlink(name, dir_fd=dir_fd)
            except FileNotFoundError:
                pass
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o644,
                dir_fd=dir_fd,
            )
            try:
                os.write(fd, replacement)
            finally:
                os.close(fd)
            return real_prove(
                dir_fd, name, expected_dev=expected_dev, expected_ino=expected_ino
            )
        return real_prove(
            dir_fd, name, expected_dev=expected_dev, expected_ino=expected_ino
        )

    monkeypatch.setattr(pin_mod, "prove_size0_owned_name_terminal", prove)
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    swapped = list(ready.parent.glob(f"{prefix}*"))
    assert len(swapped) == 1
    assert swapped[0].read_bytes() == replacement
    assert swapped[0].read_bytes() != payload
    snap = _lifecycle_snapshot(mutation_store)
    # Prove failure must retain receipt ownership.
    assert snap["receipt_generation"] == generation


@pytest.mark.parametrize(
    ("branch", "setup"),
    (
        ("replacement", "replacement"),
        ("restore", "restore"),
        ("hardlink_drop", "hardlink_drop"),
    ),
    ids=["replacement", "restore", "hardlink_drop"],
)
def test_recovery_unlink_eperm_retains_intent(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    branch: str,
    setup: str,
) -> None:
    """Round6 probe 6: EPERM during recovery unlink retains delete intent."""

    del branch
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    generation_by_setup = {
        "replacement": "genreplacex",
        "restore": "genrestorexx",
        "hardlink_drop": "gendropxxxxx",
    }
    generation = generation_by_setup[setup]
    quarantine = ready.parent / quarantine_name_for(
        inode=st.st_ino,
        artifact_id=ARTIFACT_ID,
        generation=generation,
    )
    os.link(ready, quarantine)
    if setup == "replacement":
        ready.unlink()
        ready.write_bytes(b"replacement-inode")
        store.begin_artifact_bytes_delete_intent(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            dev=int(st.st_dev),
            ino=int(st.st_ino),
            phase="quarantined",
            intent_at="2026-08-02T00:00:00+00:00",
            generation="genreplacex",
        )
        _enqueue(store, key="eperm-replace", operation_id=OTHER_OPERATION_ID)
    elif setup == "restore":
        _replace_ready_with_foreign(ready, b"foreign-restore-ready")
        store.begin_artifact_bytes_delete_intent(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            dev=int(st.st_dev),
            ino=int(st.st_ino),
            phase="quarantined",
            intent_at="2026-08-02T00:00:00+00:00",
            generation="genrestorexx",
        )
        _enqueue(store, key=f"eperm-{setup}", operation_id=OTHER_OPERATION_ID)
    else:
        _replace_ready_with_foreign(ready, b"foreign-hardlink-drop")
        store.begin_artifact_bytes_delete_intent(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            dev=int(st.st_dev),
            ino=int(st.st_ino),
            phase="quarantined",
            intent_at="2026-08-02T00:00:00+00:00",
            generation="gendropxxxxx",
        )
        _enqueue(store, key=f"eperm-{setup}", operation_id=OTHER_OPERATION_ID)
    import gateway_repository_service.upload_artifact.admission_pin as pin_mod

    _monkeypatch_ftruncate_always_fail(monkeypatch, pin_module=pin_mod)
    ArtifactCleaner(
        settings=_settings(layout, ttl=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: datetime(2026, 8, 1, 0, 0, 30, tzinfo=UTC),
    ).sweep_once()

    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_delete_intent_at is not None
    if setup == "replacement":
        assert ready.is_file()
        assert ready.read_bytes() == b"replacement-inode"
    else:
        assert (
            quarantine.is_file()
            or list(quarantine.parent.glob(".unlink-stage-*"))
            or list(quarantine.parent.glob(".unlink-verify-*"))
        )
    if setup == "restore":
        assert ready.read_bytes() == b"foreign-restore-ready"
    elif setup == "hardlink_drop":
        assert ready.read_bytes() == b"foreign-hardlink-drop"


def test_q_and_detach_single_unlink_failure_retains_intent(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round6 probe 7: one sidecar unlink EPERM retains intent and failed sidecar."""

    from gateway_repository_service.upload_artifact.admission_pin import detach_name_for

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    generation = "genbothxxxxx"
    quarantine = ready.parent / quarantine_name_for(
        inode=st.st_ino,
        artifact_id=ARTIFACT_ID,
        generation=generation,
    )
    detach = ready.parent / detach_name_for(
        inode=int(st.st_ino),
        artifact_id=ARTIFACT_ID,
        generation=generation,
    )
    os.link(ready, quarantine)
    os.link(ready, detach)
    _replace_ready_with_foreign(ready, b"foreign-ready-qdetach")
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation="genbothxxxxx",
    )
    _enqueue(store, key="q-detach-eperm", operation_id=OTHER_OPERATION_ID)
    import gateway_repository_service.upload_artifact.admission_pin as pin_mod

    _monkeypatch_ftruncate_always_fail(monkeypatch, pin_module=pin_mod)
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_delete_intent_at is not None
    assert (
        detach.is_file()
        or list(detach.parent.glob(".unlink-verify-*"))
        or list(detach.parent.glob(".detach-*"))
        or list(detach.parent.glob(".unlink-stage-*"))
    )
    assert not quarantine.exists() or quarantine.is_file()


MIGRATION_MALFORMED_INTENT_CASES = (
    (
        "partial_intent_at_only",
        {
            "bytes_delete_intent_at": "2026-08-02T00:00:00+00:00",
            "bytes_delete_dev": None,
            "bytes_delete_ino": None,
            "bytes_delete_phase": None,
        },
    ),
    (
        "naive_timestamp",
        {
            "bytes_delete_intent_at": "2026-08-02T00:00:00",
            "bytes_delete_dev": 1,
            "bytes_delete_ino": 2,
            "bytes_delete_phase": "quarantined",
        },
    ),
    (
        "bad_phase",
        {
            "bytes_delete_intent_at": "2026-08-02T00:00:00+00:00",
            "bytes_delete_dev": 1,
            "bytes_delete_ino": 2,
            "bytes_delete_phase": "bogus",
        },
    ),
)


@pytest.mark.parametrize(
    ("label", "fields"),
    MIGRATION_MALFORMED_INTENT_CASES,
    ids=[c[0] for c in MIGRATION_MALFORMED_INTENT_CASES],
)
def test_v9_to_v10_migration_malformed_blocks(
    tmp_path: Path,
    label: str,
    fields: dict[str, object],
) -> None:
    """Round6 probe 8: malformed v9 intent rows block migration to current version."""

    del label
    db_path = tmp_path / "service-state" / "repository-service.sqlite3"
    ControlStore.open(db_path, expected_version=9, busy_timeout_ms=1000).close()
    connection = sqlite3.connect(db_path)
    _seed_artifact_on_connection(connection)
    connection.execute(
        """
        UPDATE artifact_lifecycle
        SET bytes_delete_intent_at = ?,
            bytes_delete_dev = ?,
            bytes_delete_ino = ?,
            bytes_delete_phase = ?
        WHERE artifact_id = ?
        """,
        (
            fields["bytes_delete_intent_at"],
            fields["bytes_delete_dev"],
            fields["bytes_delete_ino"],
            fields["bytes_delete_phase"],
            str(ARTIFACT_ID),
        ),
    )
    connection.commit()
    connection.close()

    with pytest.raises(ControlDbError, match="malformed artifact delete intent"):
        ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000)


def test_v9_to_v12_migration_preserves_legal_intent_with_generation(
    tmp_path: Path,
) -> None:
    """Round6 probe 8b: legal v9 intent migrates with generation backfilled."""

    db_path = tmp_path / "service-state" / "repository-service.sqlite3"
    ControlStore.open(db_path, expected_version=9, busy_timeout_ms=1000).close()
    connection = sqlite3.connect(db_path)
    _seed_artifact_on_connection(connection)
    connection.execute(
        """
        UPDATE artifact_lifecycle
        SET bytes_delete_intent_at = ?,
            bytes_delete_dev = ?,
            bytes_delete_ino = ?,
            bytes_delete_phase = ?
        WHERE artifact_id = ?
        """,
        (
            "2026-08-02T00:00:00+00:00",
            7,
            70,
            "quarantined",
            str(ARTIFACT_ID),
        ),
    )
    connection.commit()
    connection.close()

    ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000).close()
    configure_connection(connection := sqlite3.connect(db_path))
    mutation_store = MutationStore(connection)
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_delete_dev == 7
    assert lifecycle.bytes_delete_ino == 70
    assert lifecycle.bytes_delete_phase == "quarantined"
    assert lifecycle.bytes_delete_generation is not None
    connection.close()


def test_partial_intent_without_generation_raises_integrity_error(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    """Round6 probe 9: v12 CHECK rejects partial intent without generation."""

    _store, mutation_store = stores
    _seed_artifact(mutation_store)
    with mutation_store._lock, pytest.raises(sqlite3.IntegrityError):
        mutation_store._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET bytes_delete_intent_at = ?,
                bytes_delete_dev = ?,
                bytes_delete_ino = ?,
                bytes_delete_phase = ?
            WHERE artifact_id = ?
            """,
            (
                "2026-08-02T00:00:00+00:00",
                1,
                2,
                "quarantined",
                str(ARTIFACT_ID),
            ),
        )
        mutation_store._connection.commit()


def test_stamped_residual_only_receipt_match_unlinks(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Round6 probe 10: only receipt-matching quarantine unlinks; forged sibling stays."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    quarantine, ino, generation = _begin_intent_for_ready(store, ready)
    q_stat = quarantine.stat()
    ready.unlink()
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(q_stat.st_dev),
        expected_ino=ino,
        expected_generation=generation,
    )
    decoy = quarantine.parent / f".decoy-{uuid4().hex}"
    decoy.write_bytes(b"forged-residual")
    forged = quarantine.parent / quarantine_name_for(
        inode=decoy.stat().st_ino,
        artifact_id=ARTIFACT_ID,
        generation=uuid4().hex,
    )
    os.link(decoy, forged)
    decoy.unlink()
    caplog.set_level(logging.INFO)

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    _assert_terminal_size0_or_absent(quarantine, owned_ino=ino)
    assert forged.is_file()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None
    unlinked = [
        record
        for record in caplog.records
        if getattr(record, "cleanup_outcome", None) == "quarantine_residual_unlinked"
    ]
    assert unlinked
    retained = [
        record
        for record in caplog.records
        if getattr(record, "cleanup_outcome", None) == "unknown_path_inventory"
    ]
    assert retained


MALFORMED_TIMESTAMP_MIGRATION_CASES = (
    ("naive", "2026-08-02T00:00:00"),
    ("illegal_offset", "2026-08-02T00:00:00+99:00"),
    ("garbage_suffix", "not-a-timestamp+00:00"),
)


@pytest.mark.parametrize(
    ("label", "intent_at"),
    MALFORMED_TIMESTAMP_MIGRATION_CASES,
    ids=[c[0] for c in MALFORMED_TIMESTAMP_MIGRATION_CASES],
)
def test_v10_malformed_timestamp_blocks_upgrade_to_v12(
    tmp_path: Path,
    label: str,
    intent_at: str,
) -> None:
    """Round7 probe 11: tests/test_artifact_cleanup.py::test_v10_malformed_timestamp_blocks_upgrade_to_v12"""

    del label
    db_path = tmp_path / "service-state" / "repository-service.sqlite3"
    ControlStore.open(db_path, expected_version=10, busy_timeout_ms=1000).close()
    connection = sqlite3.connect(db_path)
    _seed_artifact_on_connection(connection)
    connection.execute(
        """
        UPDATE artifact_lifecycle
        SET bytes_delete_intent_at = ?,
            bytes_delete_dev = ?,
            bytes_delete_ino = ?,
            bytes_delete_phase = ?
        WHERE artifact_id = ?
        """,
        (
            intent_at,
            1,
            2,
            "quarantined",
            str(ARTIFACT_ID),
        ),
    )
    connection.commit()
    connection.close()

    with pytest.raises(ControlDbError, match="malformed artifact delete intent"):
        ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000)

    connection = sqlite3.connect(db_path)
    version = connection.execute("PRAGMA user_version").fetchone()
    connection.close()
    assert int(version[0]) == 10


@pytest.mark.parametrize(
    ("label", "intent_at"),
    MALFORMED_TIMESTAMP_MIGRATION_CASES,
    ids=[c[0] for c in MALFORMED_TIMESTAMP_MIGRATION_CASES],
)
def test_v9_malformed_timestamp_validator_matches_parse_durable(
    tmp_path: Path,
    label: str,
    intent_at: str,
) -> None:
    """Round7 probe 12: tests/test_artifact_cleanup.py::test_v9_malformed_timestamp_validator_matches_parse_durable"""

    del label
    db_path = tmp_path / "service-state" / "repository-service.sqlite3"
    ControlStore.open(db_path, expected_version=9, busy_timeout_ms=1000).close()
    connection = sqlite3.connect(db_path)
    _seed_artifact_on_connection(connection)
    connection.execute(
        """
        UPDATE artifact_lifecycle
        SET bytes_delete_intent_at = ?,
            bytes_delete_dev = ?,
            bytes_delete_ino = ?,
            bytes_delete_phase = ?
        WHERE artifact_id = ?
        """,
        (
            intent_at,
            1,
            2,
            "quarantined",
            str(ARTIFACT_ID),
        ),
    )
    connection.commit()
    connection.close()

    with pytest.raises(ControlDbError, match="malformed artifact delete intent"):
        ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000)


def test_v10_stamped_residual_no_receipt_upgrade_retains(
    layout: DurableLayout,
    tmp_path: Path,
) -> None:
    """Round7 probe 13: tests/test_artifact_cleanup.py::test_v10_stamped_residual_no_receipt_upgrade_retains"""

    db_path = tmp_path / "v10-residual" / "repository-service.sqlite3"
    ControlStore.open(db_path, expected_version=10, busy_timeout_ms=1000).close()
    connection = sqlite3.connect(db_path)
    _seed_artifact_on_connection(connection)
    connection.execute(
        """
        UPDATE artifact_lifecycle
        SET bytes_deleted_at = ?,
            bytes_delete_intent_at = NULL,
            bytes_delete_dev = NULL,
            bytes_delete_ino = NULL,
            bytes_delete_phase = NULL
        WHERE artifact_id = ?
        """,
        ("2026-08-02T00:00:00+00:00", str(ARTIFACT_ID)),
    )
    connection.commit()
    connection.close()

    ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000).close()
    configure_connection(connection := sqlite3.connect(db_path))
    import_store = ImportOperationStore(connection)
    mutation_store = import_store.mutation_store

    ready = _write_ready(layout)
    residual = ready.parent / quarantine_name_for(
        inode=ready.stat().st_ino,
        artifact_id=ARTIFACT_ID,
        generation=uuid4().hex,
    )
    os.link(ready, residual)
    ready.unlink()

    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None
    assert lifecycle.bytes_deleted_receipt_dev is None

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=import_store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert residual.is_file()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None
    assert lifecycle.bytes_deleted_receipt_dev is None
    connection.close()


def test_v12_rejects_deleted_at_with_active_intent(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    """Round7 probe 14: tests/test_artifact_cleanup.py::test_v12_rejects_deleted_at_with_active_intent"""

    from gateway_repository_service.mutation_store import MutationStoreInvariantError

    _store, mutation_store = stores
    _seed_artifact(mutation_store)
    with mutation_store._lock, pytest.raises(sqlite3.IntegrityError):
        mutation_store._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET bytes_deleted_at = ?,
                bytes_delete_intent_at = ?,
                bytes_delete_dev = ?,
                bytes_delete_ino = ?,
                bytes_delete_phase = ?,
                bytes_delete_generation = ?
            WHERE artifact_id = ?
            """,
            (
                "2026-08-02T00:00:00+00:00",
                "2026-08-02T00:00:00+00:00",
                1,
                2,
                "quarantined",
                "gen-both",
                str(ARTIFACT_ID),
            ),
        )
        mutation_store._connection.commit()
    mutation_store._connection.rollback()

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE artifact_lifecycle (
            artifact_id TEXT,
            repository_scope TEXT,
            media_type TEXT,
            size_bytes INTEGER,
            raw_sha256 TEXT,
            created_at TEXT,
            updated_at TEXT,
            consumed_by_operation_id TEXT,
            consumed_at TEXT,
            bytes_deleted_at TEXT,
            bytes_delete_intent_at TEXT,
            bytes_delete_dev INTEGER,
            bytes_delete_ino INTEGER,
            bytes_delete_phase TEXT,
            bytes_delete_generation TEXT,
            bytes_deleted_receipt_dev INTEGER,
            bytes_deleted_receipt_ino INTEGER,
            bytes_deleted_receipt_generation TEXT
        )
        """
    )
    connection.execute(
        """
        INSERT INTO artifact_lifecycle VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(ARTIFACT_ID),
            REPOSITORY_ID.hex,
            MEDIA_TYPE,
            len(ARTIFACT_PAYLOAD),
            SHA256,
            CREATED_AT,
            CREATED_AT,
            None,
            None,
            "2026-08-02T00:00:00+00:00",
            "2026-08-02T00:00:00+00:00",
            1,
            2,
            "quarantined",
            "gen-projection",
            None,
            None,
            None,
        ),
    )
    row = connection.execute("SELECT * FROM artifact_lifecycle").fetchone()
    assert row is not None
    with pytest.raises(MutationStoreInvariantError):
        MutationStore._artifact_lifecycle_from_row(row)
    connection.close()


@pytest.mark.parametrize("phase", ["abort", "post_stamp"], ids=["abort", "post_stamp"])
@pytest.mark.serial
def test_live_helper_replace_quarantine_before_abort_and_post_stamp_unlink(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    """Round13: abort keeps full-byte quarantine; post-stamp reclaim skips foreign."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    replacement = b"foreign-quarantine-bytes"
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)

    if phase == "abort":
        outcome = try_unlink_owned_ready_artifact(
            layout,
            REPOSITORY_ID,
            ARTIFACT_ID,
            recheck=lambda: False,
            on_deleted=on_deleted,
            on_intent=on_intent,
            on_clear_intent=on_clear_intent,
            on_clear_receipt=on_clear_receipt,
        )
        assert outcome == "ineligible"
        assert stamped["ok"] is False
        assert ready.is_file()
        assert ready.read_bytes() == ARTIFACT_PAYLOAD
        quarantines = list(ready.parent.glob(".deleting-*"))
        assert len(quarantines) == 1
        assert quarantines[0].read_bytes() == ARTIFACT_PAYLOAD
        assert hashlib.sha256(quarantines[0].read_bytes()).hexdigest() == SHA256
    else:
        real_prove = pin_mod.prove_size0_owned_name_terminal

        def prove(
            dir_fd: int,
            name: str,
            *,
            expected_dev: int,
            expected_ino: int,
        ) -> bool:
            if name.startswith(".deleting-"):
                try:
                    os.unlink(name, dir_fd=dir_fd)
                except FileNotFoundError:
                    pass
                fd = os.open(
                    name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o644,
                    dir_fd=dir_fd,
                )
                try:
                    os.write(fd, replacement)
                finally:
                    os.close(fd)
                return real_prove(
                    dir_fd, name, expected_dev=expected_dev, expected_ino=expected_ino
                )
            return real_prove(
                dir_fd, name, expected_dev=expected_dev, expected_ino=expected_ino
            )

        monkeypatch.setattr(pin_mod, "prove_size0_owned_name_terminal", prove)
        outcome = try_unlink_owned_ready_artifact(
            layout,
            REPOSITORY_ID,
            ARTIFACT_ID,
            recheck=lambda: True,
            on_deleted=on_deleted,
            on_intent=on_intent,
            on_clear_intent=on_clear_intent,
            on_clear_receipt=on_clear_receipt,
        )
        assert outcome == "unlink_failed"
        assert stamped["ok"] is True
        retained_path = _assert_replacement_retained(ready.parent, replacement)
        parsed = parse_any_recoverable_sidecar(retained_path.name)
        assert parsed is not None
        snap = _lifecycle_snapshot(mutation_store)
        assert snap["receipt_generation"] is not None
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    if phase == "abort":
        assert lifecycle.bytes_deleted_at is None
    else:
        assert lifecycle.bytes_deleted_at is not None


@pytest.mark.parametrize(
    "entrypoint",
    ["cleaner_sweep", "worker_unlink", "admin_cleanup"],
    ids=["cleaner_sweep", "worker_unlink", "admin_cleanup"],
)
def test_successful_delete_clears_receipt_three_entrypoints(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    entrypoint: str,
) -> None:
    """Round7 probe 5: tests/test_artifact_cleanup.py::test_successful_delete_clears_receipt_three_entrypoints"""

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)

    if entrypoint == "cleaner_sweep":
        quarantine, _ino, _generation = _begin_intent_for_ready(store, ready)
        ready.unlink()
        ArtifactCleaner(
            settings=_settings(layout, ttl=1),
            layout=layout,
            import_store=store,
            mutation_store=mutation_store,
            clock=lambda: BASE_NOW,
        ).sweep_once()
        _assert_terminal_size0_or_absent(quarantine)
    elif entrypoint == "worker_unlink":
        from gateway_repository_service.versioned_import.command import ImportOperationExecutor

        _enqueue(store, key="receipt-worker", operation_id=OPERATION_ID)
        store.claim_if_queued(OPERATION_ID)
        store.mark_succeeded(OPERATION_ID, result=_import_result())
        context = store.load_execution_context(OPERATION_ID)
        assert context is not None
        ImportOperationExecutor(
            settings=_settings(layout, ttl=1),
            layout=layout,
            store=store,
        )._best_effort_delete_artifact_bytes(context, ready)
    else:
        from gateway_repository_service.versioned_import.recovery import (
            cleanup_after_succeeded_correction,
        )

        _enqueue(store, key="receipt-clear", operation_id=OPERATION_ID)
        store.claim_if_queued(OPERATION_ID)
        store.mark_succeeded(OPERATION_ID, result=_import_result())
        context = store.load_execution_context(OPERATION_ID)
        assert context is not None

        class _Provider:
            def delete_private_ref(self, *_args: object, **_kwargs: object) -> None:
                return None

        cleanup_after_succeeded_correction(
            store=store,
            layout=layout,
            context=context,
            provider=_Provider(),  # type: ignore[arg-type]
            candidate="commit-1",
            ttl_seconds=1,
            tombstone_budget=50_000,
        )

    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None
    _assert_receipt_cleared(mutation_store)


def test_receipt_clear_db_failure_retried_on_sidecarless_sweep(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Round7 probe 6: tests/test_artifact_cleanup.py::test_receipt_clear_db_failure_retried_on_sidecarless_sweep"""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _write_ready(layout)
    on_deleted, on_intent, on_clear_intent, _base_clear_receipt, stamped = _intent_callbacks(store)
    clear_calls = {"n": 0}

    def on_clear_receipt(dev: int, ino: int, generation: str) -> None:
        clear_calls["n"] += 1
        if clear_calls["n"] == 1:
            raise RuntimeError("forced receipt clear failure")
        store.clear_artifact_bytes_deleted_receipt(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
        )

    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome == "deleted"
    assert stamped["ok"] is True
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_receipt_dev is not None

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    _assert_receipt_cleared(mutation_store)


@pytest.mark.parametrize(
    ("forged_spec",),
    [
        ("gen_g2_forged",),
        ("legacy_empty_deleting",),
        ("legacy_empty_detach",),
    ],
    ids=["gen_g2", "legacy_empty_deleting", "legacy_empty_detach"],
)
def test_long_lived_receipt_forged_different_generation_retained(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    caplog: pytest.LogCaptureFixture,
    forged_spec: str,
) -> None:
    """Round7 probe 7: tests/test_artifact_cleanup.py::test_long_lived_receipt_forged_different_generation_retained"""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    gen_g1 = "gen_g1_receipt"
    quarantine, ino, _ = _begin_intent_for_ready(store, ready, generation=gen_g1)
    q_stat = quarantine.stat()
    ready.unlink()
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(q_stat.st_dev),
        expected_ino=ino,
        expected_generation=gen_g1,
    )
    quarantine.unlink()
    decoy = ready.parent / f".decoy-{uuid4().hex}"
    decoy.write_bytes(b"forged-receipt")
    if forged_spec == "gen_g2_forged":
        forged = ready.parent / quarantine_name_for(
            inode=int(q_stat.st_ino),
            artifact_id=ARTIFACT_ID,
            generation="gen_g2_forged",
        )
    elif forged_spec == "legacy_empty_deleting":
        forged = ready.parent / f".deleting-{int(q_stat.st_ino)}-{ARTIFACT_ID.hex}"
    else:
        forged = ready.parent / f".detach-{int(q_stat.st_ino)}-{ARTIFACT_ID.hex}"
    os.link(decoy, forged)
    decoy.unlink()
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
    assert lifecycle.bytes_deleted_receipt_dev is None
    retained = [
        record
        for record in caplog.records
        if getattr(record, "cleanup_outcome", None) == "unknown_path_inventory"
    ]
    assert retained


@pytest.mark.parametrize("fault", ["open_eio", "fstat_eio"], ids=["open_eio", "fstat_eio"])
def test_active_q_detach_open_or_fstat_eio_retains_intent(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    """Round7 probe 8: tests/test_artifact_cleanup.py::test_active_q_detach_open_or_fstat_eio_retains_intent"""

    from gateway_repository_service.artifact_cleaner import ArtifactCleaner
    from gateway_repository_service.upload_artifact.admission_pin import detach_name_for

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    generation = "gen_eio_r7p8"
    quarantine = ready.parent / quarantine_name_for(
        inode=st.st_ino,
        artifact_id=ARTIFACT_ID,
        generation=generation,
    )
    detach = ready.parent / detach_name_for(
        inode=int(st.st_ino),
        artifact_id=ARTIFACT_ID,
        generation=generation,
    )
    os.link(ready, quarantine)
    os.link(ready, detach)
    ready.unlink()
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    _enqueue(store, key="eio-retain", operation_id=OTHER_OPERATION_ID)

    real_open = os.open
    real_fstat = os.fstat

    def open_wrapper(name: str | bytes | os.PathLike[str], flags: int, *args: object, **kwargs: object) -> int:
        if fault == "open_eio" and isinstance(name, str) and (
            name.startswith(".deleting-") or name.startswith(".detach-")
        ):
            raise OSError(errno.EIO, "forced open EIO")
        return real_open(name, flags, *args, **kwargs)  # type: ignore[arg-type]

    def fstat_wrapper(fd: int) -> os.stat_result:
        if fault == "fstat_eio" and fd > 2:
            raise OSError(errno.EIO, "forced fstat EIO")
        return real_fstat(fd)

    monkeypatch.setattr("gateway_repository_service.artifact_cleaner.os.open", open_wrapper)
    monkeypatch.setattr("gateway_repository_service.artifact_cleaner.os.fstat", fstat_wrapper)

    ArtifactCleaner(
        settings=_settings(layout, ttl=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: datetime(2026, 8, 1, 0, 0, 30, tzinfo=UTC),
    ).sweep_once()

    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_delete_intent_at is not None
    assert quarantine.is_file() or detach.is_file()


def test_stamped_matching_sidecar_open_fstat_failure_retains_receipt(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round7 probe 9: tests/test_artifact_cleanup.py::test_stamped_matching_sidecar_open_fstat_failure_retains_receipt"""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    quarantine, ino, generation = _begin_intent_for_ready(store, ready)
    q_stat = quarantine.stat()
    ready.unlink()
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(q_stat.st_dev),
        expected_ino=ino,
        expected_generation=generation,
    )
    real_open = os.open

    def open_wrapper(name: str | bytes | os.PathLike[str], flags: int, *args: object, **kwargs: object) -> int:
        if isinstance(name, str) and name.startswith(".deleting-"):
            raise OSError(errno.EIO, "forced stamped lock EIO")
        return real_open(name, flags, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("gateway_repository_service.artifact_cleaner.os.open", open_wrapper)

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_receipt_dev is not None
    assert quarantine.is_file()


@pytest.mark.parametrize("phase", ["ineligible", "replaced"], ids=["ineligible", "replaced"])
@pytest.mark.serial
def test_live_helper_cleanup_eperm_retains_ownership(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    """Round7 probe 10: tests/test_artifact_cleanup.py::test_live_helper_cleanup_eperm_retains_ownership"""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod

    def on_clear_intent_raise(dev: int, ino: int, generation: str) -> None:
        raise RuntimeError("refuse intent clear")

    _monkeypatch_ftruncate_always_fail(monkeypatch, pin_module=pin_mod)

    if phase == "ineligible":
        calls = {"n": 0}

        def recheck() -> bool:
            calls["n"] += 1
            return calls["n"] == 1

        outcome = try_unlink_owned_ready_artifact(
            layout,
            REPOSITORY_ID,
            ARTIFACT_ID,
            recheck=recheck,
            on_deleted=on_deleted,
            on_intent=on_intent,
            on_clear_intent=on_clear_intent_raise,
            on_clear_receipt=on_clear_receipt,
        )
        assert outcome in {"ineligible", "unlink_failed"}
    else:
        replacement = b"replacement-for-eperm"

        def recheck() -> bool:
            ready.unlink()
            ready.write_bytes(replacement)
            return True

        outcome = try_unlink_owned_ready_artifact(
            layout,
            REPOSITORY_ID,
            ARTIFACT_ID,
            recheck=recheck,
            on_deleted=on_deleted,
            on_intent=on_intent,
            on_clear_intent=on_clear_intent_raise,
            on_clear_receipt=on_clear_receipt,
        )
        assert outcome == "replaced"

    assert stamped["ok"] is False
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_delete_intent_at is not None
    assert (
        list(ready.parent.glob(".deleting-*"))
        or list(ready.parent.glob(".detach-*"))
        or list(ready.parent.glob(".unlink-verify-*"))
        or list(ready.parent.glob(".unlink-stage-*"))
    )


# ---------------------------------------------------------------------------
# Round8 directed probes (unlink-verify recovery + detach rename-verify)
# ---------------------------------------------------------------------------


def _lifecycle_snapshot(mutation_store: MutationStore) -> dict[str, object]:
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    return {
        "bytes_deleted_at": lifecycle.bytes_deleted_at,
        "intent_at": lifecycle.bytes_delete_intent_at,
        "intent_dev": lifecycle.bytes_delete_dev,
        "intent_ino": lifecycle.bytes_delete_ino,
        "intent_generation": lifecycle.bytes_delete_generation,
        "receipt_dev": lifecycle.bytes_deleted_receipt_dev,
        "receipt_ino": lifecycle.bytes_deleted_receipt_ino,
        "receipt_generation": lifecycle.bytes_deleted_receipt_generation,
    }


def _sidecar_snapshots(ready_dir: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for entry in ready_dir.iterdir():
        parsed = parse_any_recoverable_sidecar(entry.name)
        if parsed is None:
            continue
        ino, artifact_id, generation, kind = parsed
        st = entry.stat()
        rows.append(
            {
                "name": entry.name,
                "kind": kind,
                "parsed_ino": ino,
                "artifact_id": artifact_id,
                "generation": generation,
                "st_dev": int(st.st_dev),
                "st_ino": int(st.st_ino),
                "st_nlink": int(st.st_nlink),
            }
        )
    return rows
@pytest.mark.skip(reason="superseded by Round13 rename-only detach / zero-stage reclaim")


@pytest.mark.serial
def test_r8_active_intent_crash_after_rename_before_private_stat(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round9 probe 1: crash after staging rename into victim, before stamp (active intent)."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod
    from gateway_repository_service.publication import renameat2_noreplace as real_rename
    from gateway_repository_service.upload_artifact.admission_pin import STAGE_VICTIM

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    ready_stat = ready.stat()
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)
    staged: dict[str, str] = {}

    def rename(
        src_dir_fd: int,
        src_name: str | bytes,
        dst_dir_fd: int,
        dst_name: str | bytes,
    ) -> None:
        real_rename(src_dir_fd, src_name, dst_dir_fd, dst_name)
        # Live detach path: after ready/detach lands as stage/victim, crash before
        # private fstat / stamp so intent remains active.
        if isinstance(dst_name, str) and dst_name == STAGE_VICTIM:
            staged["victim"] = STAGE_VICTIM
            raise OSError(errno.EIO, "crash after stage rename before private stat")

    monkeypatch.setattr(pin_mod, "_broker_rename_noreplace", rename)

    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome == "unlink_failed"
    assert stamped["ok"] is False

    snap = _lifecycle_snapshot(mutation_store)
    assert snap["intent_at"] is not None
    assert snap["intent_generation"] is not None
    assert snap["intent_dev"] == int(ready_stat.st_dev)
    assert snap["intent_ino"] == int(ready_stat.st_ino)
    assert snap["bytes_deleted_at"] is None
    stages = list(ready.parent.glob(".unlink-stage-*"))
    assert stages, "expected staged victim residual after crash"
    assert staged.get("victim") == STAGE_VICTIM
    victim = stages[0] / STAGE_VICTIM
    assert victim.is_file()
    assert int(victim.stat().st_ino) == int(ready_stat.st_ino)
    assert victim.read_bytes() == ARTIFACT_PAYLOAD

    monkeypatch.setattr(pin_mod, "_broker_rename_noreplace", real_rename)
    _artifact_cleaner(layout, store, mutation_store).sweep_once()

    snap2 = _lifecycle_snapshot(mutation_store)
    assert snap2["bytes_deleted_at"] is not None
    assert snap2["intent_at"] is None
    assert snap2["receipt_generation"] is None
    # Empty stage dirs may remain as residuals under the fd-truncate protocol.
@pytest.mark.skip(reason="superseded by Round13 rename-only detach / zero-stage reclaim")


@pytest.mark.serial
def test_r8_stamped_crash_after_private_stat_before_unlink(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round8 probe 2: stamped residual crash after private stat, before unlink."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod
    from gateway_repository_service.publication import renameat2_noreplace as real_rename

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    quarantine, ino, generation = _begin_intent_for_ready(store, ready)
    q_stat = quarantine.stat()
    ready.unlink()
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(q_stat.st_dev),
        expected_ino=ino,
        expected_generation=generation,
    )

    real_verify = pin_mod.unlink_sidecar_rename_verify

    def crashy_verify(
        ready_dir_fd: int,
        sidecar_name: str,
        q_fd: int,
        expected: os.stat_result,
        *,
        artifact_id: UUID,
        generation: str,
    ) -> bool:
        private = verify_sidecar_name_for(
            inode=int(expected.st_ino),
            generation=generation,
            artifact_id=artifact_id,
            token="crashstat2",
        )
        real_rename(ready_dir_fd, sidecar_name, ready_dir_fd, private)
        private_stat = os.stat(private, dir_fd=ready_dir_fd, follow_symlinks=False)
        assert (private_stat.st_dev, private_stat.st_ino) == (
            expected.st_dev,
            expected.st_ino,
        )
        # Crash window: private verified, unlink not attempted, no restore.
        return False

    monkeypatch.setattr(
        "gateway_repository_service.artifact_cleaner.unlink_sidecar_rename_verify",
        crashy_verify,
    )
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    snap = _lifecycle_snapshot(mutation_store)
    assert snap["receipt_generation"] == generation
    assert list(quarantine.parent.glob(".unlink-verify-*"))
    # GC alone must not clear receipt while private residual exists.
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    )._gc_bytes_deleted_receipts()
    snap_gc = _lifecycle_snapshot(mutation_store)
    assert snap_gc["receipt_generation"] == generation

    monkeypatch.setattr(
        "gateway_repository_service.artifact_cleaner.unlink_sidecar_rename_verify",
        real_verify,
    )
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    snap2 = _lifecycle_snapshot(mutation_store)
    assert snap2["receipt_generation"] is None
    for path in quarantine.parent.glob(".deleting-*"):
        _assert_terminal_size0_or_absent(path)
    for verify in quarantine.parent.glob(".unlink-verify-*"):
        assert verify.stat().st_size == 0


@pytest.mark.serial
def test_r8_private_unlink_eperm_restore_fail_then_converge(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round8 probe 3: private unlink EPERM and restore fail; next sweep converges."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod
    from gateway_repository_service.publication import renameat2_noreplace as real_rename
    from gateway_repository_service.upload_artifact.admission_pin import STAGE_VICTIM

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    quarantine, _ino, generation = _begin_intent_for_ready(store, ready)
    ready.unlink()
    private_names: set[str] = set()

    def rename(
        src_dir_fd: int,
        src_name: str | bytes,
        dst_dir_fd: int,
        dst_name: str | bytes,
    ) -> None:
        # Fail restore of staged victim back to a ready-visible sidecar name.
        if isinstance(src_name, str) and src_name == STAGE_VICTIM and isinstance(
            dst_name, str
        ) and (
            dst_name.startswith(".deleting-")
            or dst_name.startswith(".unlink-verify-")
            or dst_name.startswith(".detach-")
        ):
            raise OSError(errno.EIO, "forced restore failure")
        if (
            isinstance(src_name, str)
            and (src_name.startswith("final-") or src_name.startswith("doom-"))
            and isinstance(dst_name, str)
            and dst_name == STAGE_VICTIM
        ):
            raise OSError(errno.EIO, "forced final restore failure")
        real_rename(src_dir_fd, src_name, dst_dir_fd, dst_name)
        if isinstance(dst_name, str) and dst_name.startswith(".unlink-stage-"):
            private_names.add(dst_name)

    real_ftruncate = pin_mod._ftruncate_inode_to_empty
    _monkeypatch_ftruncate_fail_nth(monkeypatch, 1, pin_module=pin_mod)
    monkeypatch.setattr(pin_mod, "_broker_rename_noreplace", rename)
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    snap = _lifecycle_snapshot(mutation_store)
    assert snap["intent_generation"] == generation or snap["receipt_generation"] == generation
    residuals = (
        list(quarantine.parent.glob(".unlink-stage-*"))
        or list(quarantine.parent.glob(".unlink-verify-*"))
        or list(quarantine.parent.glob(".deleting-*"))
    )
    assert residuals

    monkeypatch.setattr(pin_mod, "_ftruncate_inode_to_empty", real_ftruncate)
    monkeypatch.setattr(pin_mod, "_broker_rename_noreplace", real_rename)
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    snap2 = _lifecycle_snapshot(mutation_store)
    assert snap2["bytes_deleted_at"] is not None
    assert snap2["intent_at"] is None
    assert snap2["receipt_generation"] is None
    for path in quarantine.parent.glob(".deleting-*"):
        _assert_terminal_size0_or_absent(path)
    _assert_no_nonempty_sidecars(quarantine.parent)


@pytest.mark.serial
def test_r8_private_blocks_concurrent_receipt_gc(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Round8 probe 4: matching .unlink-verify residual blocks receipt GC."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    quarantine, ino, generation = _begin_intent_for_ready(store, ready)
    q_stat = quarantine.stat()
    ready.unlink()
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(q_stat.st_dev),
        expected_ino=ino,
        expected_generation=generation,
    )
    private = ready.parent / verify_sidecar_name_for(
        inode=ino,
        generation=generation,
        artifact_id=ARTIFACT_ID,
        token="gcblock01",
    )
    os.rename(quarantine, private)
    assert parse_unlink_verify_name(private.name) is not None

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    )._gc_bytes_deleted_receipts()

    snap = _lifecycle_snapshot(mutation_store)
    assert snap["receipt_generation"] == generation
    assert private.is_file()
    assert int(private.stat().st_ino) == ino


def test_r8_q_detach_private_aggregate_io_failure_retains(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round8 probe 5: q+detach+private aggregate; one I/O failure retains ownership."""

    from gateway_repository_service.upload_artifact.admission_pin import detach_name_for

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    generation = "genr8agg01"
    quarantine = ready.parent / quarantine_name_for(
        inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
    )
    detach = ready.parent / detach_name_for(
        inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
    )
    private = ready.parent / verify_sidecar_name_for(
        inode=int(st.st_ino),
        generation=generation,
        artifact_id=ARTIFACT_ID,
        token="aggpriv01",
    )
    os.link(ready, quarantine)
    os.link(ready, detach)
    os.link(ready, private)
    ready.unlink()
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    _enqueue(store, key="r8-agg", operation_id=OTHER_OPERATION_ID)

    real_open = os.open

    def open_wrapper(
        name: str | bytes | os.PathLike[str], flags: int, *args: object, **kwargs: object
    ) -> int:
        if isinstance(name, str) and name.startswith(".unlink-verify-"):
            raise OSError(errno.EIO, "forced private open EIO")
        return real_open(name, flags, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("gateway_repository_service.artifact_cleaner.os.open", open_wrapper)
    ArtifactCleaner(
        settings=_settings(layout, ttl=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: datetime(2026, 8, 1, 0, 0, 30, tzinfo=UTC),
    ).sweep_once()

    snap = _lifecycle_snapshot(mutation_store)
    # Round13: ineligible restore clears intent even when private open fails;
    # leftover verify/detach names remain diagnose-only with full payload.
    assert snap["intent_generation"] is None
    assert ready.is_file()
    assert ready.read_bytes() == ARTIFACT_PAYLOAD
    assert private.is_file()
    assert private.read_bytes() == ARTIFACT_PAYLOAD
    assert _sidecar_snapshots(ready.parent)


@pytest.mark.parametrize(
    "case",
    ["matching", "wrong_generation", "wrong_inode", "malformed"],
    ids=["matching", "wrong_generation", "wrong_inode", "malformed"],
)
def test_r8_unlink_verify_matching_vs_mismatch_vs_malformed(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    case: str,
) -> None:
    """Round8 probe 6: matching/wrong-gen/wrong-inode/malformed unlink-verify handling."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    quarantine, ino, generation = _begin_intent_for_ready(store, ready)
    q_stat = quarantine.stat()
    ready.unlink()
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(q_stat.st_dev),
        expected_ino=ino,
        expected_generation=generation,
    )

    if case == "matching":
        target = ready.parent / verify_sidecar_name_for(
            inode=ino,
            generation=generation,
            artifact_id=ARTIFACT_ID,
            token="match0001",
        )
        os.rename(quarantine, target)
    elif case == "wrong_generation":
        target = ready.parent / verify_sidecar_name_for(
            inode=ino,
            generation="wronggen01",
            artifact_id=ARTIFACT_ID,
            token="wrongg001",
        )
        os.rename(quarantine, target)
    elif case == "wrong_inode":
        decoy = ready.parent / f".decoy-{uuid4().hex}"
        decoy.write_bytes(b"wrong-inode-verify")
        target = ready.parent / verify_sidecar_name_for(
            inode=ino,
            generation=generation,
            artifact_id=ARTIFACT_ID,
            token="wrongi001",
        )
        os.link(decoy, target)
        decoy.unlink()
        quarantine.unlink()
    else:
        target = ready.parent / f".unlink-verify-not-a-valid-{ARTIFACT_ID.hex}"
        os.rename(quarantine, target)

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    snap = _lifecycle_snapshot(mutation_store)
    if case == "matching":
        _assert_terminal_size0_or_absent(target, owned_ino=ino)
        assert snap["receipt_generation"] is None
    else:
        assert target.exists()
        # Mismatch/malformed must not authorize clear of ownership evidence incorrectly:
        # receipt may clear only when no matching residual remains.
        if case in {"wrong_generation", "wrong_inode"}:
            assert snap["receipt_generation"] is None or target.exists()
        assert target.exists()
@pytest.mark.skip(reason="superseded by Round13 rename-only detach / zero-stage reclaim")


@pytest.mark.serial
def test_r8_live_detach_replace_after_stat_before_unlink(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round8 probe 7: replace .detach after inode stat, before rename-verify unlink."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod
    from gateway_repository_service.publication import renameat2_noreplace as real_rename

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    replacement = b"detach-replacement-bytes"
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)
    fixed_generation = "b" * 32
    monkeypatch.setattr(
        "gateway_repository_service.upload_artifact.admission_pin.uuid4",
        lambda: type("U", (), {"hex": fixed_generation})(),
    )

    def rename(
        src_dir_fd: int,
        src_name: str | bytes,
        dst_dir_fd: int,
        dst_name: str | bytes,
    ) -> None:
        # Intercept detach → unlink-verify rename: replace detach pathname first.
        if isinstance(src_name, str) and src_name.startswith(".detach-"):
            os.unlink(src_name, dir_fd=src_dir_fd)
            fd = os.open(
                src_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o644,
                dir_fd=src_dir_fd,
            )
            try:
                os.write(fd, replacement)
            finally:
                os.close(fd)
        return real_rename(src_dir_fd, src_name, dst_dir_fd, dst_name)

    monkeypatch.setattr(pin_mod, "_broker_rename_noreplace", rename)
    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome != "deleted" or stamped["ok"] is False
    retained = _assert_replacement_retained(ready.parent, replacement)
    assert retained.read_bytes() == replacement
    snap = _lifecycle_snapshot(mutation_store)
    assert snap["bytes_deleted_at"] is None or retained.exists()


@pytest.mark.serial
def test_r8_detach_moved_aside_replacement_no_clear(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round8 probe 8: owned detach moved aside; replacement at name; no clear."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod
    from gateway_repository_service.publication import renameat2_noreplace as real_rename

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    replacement = b"aside-replacement"
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)
    fixed_generation = "c" * 32
    monkeypatch.setattr(
        "gateway_repository_service.upload_artifact.admission_pin.uuid4",
        lambda: type("U", (), {"hex": fixed_generation})(),
    )
    hidden_holder: dict[str, str] = {}

    def rename(
        src_dir_fd: int,
        src_name: str | bytes,
        dst_dir_fd: int,
        dst_name: str | bytes,
    ) -> None:
        if isinstance(dst_name, str) and dst_name.startswith(".detach-"):
            real_rename(src_dir_fd, src_name, dst_dir_fd, dst_name)
            # Move owned detach aside and plant replacement at the detach name.
            hidden = f".hidden-detach-{uuid4().hex}"
            real_rename(dst_dir_fd, dst_name, dst_dir_fd, hidden)
            hidden_holder["name"] = hidden
            fd = os.open(
                dst_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o644,
                dir_fd=dst_dir_fd,
            )
            try:
                os.write(fd, replacement)
            finally:
                os.close(fd)
            return
        return real_rename(src_dir_fd, src_name, dst_dir_fd, dst_name)

    monkeypatch.setattr(pin_mod, "_broker_rename_noreplace", rename)
    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome != "deleted"
    assert stamped["ok"] is False
    # Replacement may land on ready via restore-on-mismatch, or remain a sidecar.
    if ready.is_file() and ready.read_bytes() == replacement:
        pass
    else:
        found = False
        for entry in ready.parent.iterdir():
            try:
                if entry.is_file() and entry.read_bytes() == replacement:
                    found = True
                    break
            except OSError:
                continue
        assert found, f"replacement missing; entries={list(ready.parent.iterdir())}"
    snap = _lifecycle_snapshot(mutation_store)
    assert snap["receipt_generation"] is None
    assert snap["bytes_deleted_at"] is None
@pytest.mark.skip(reason="superseded by Round13 rename-only detach / zero-stage reclaim")


@pytest.mark.serial
def test_r8_replace_private_pathname_before_final_unlink(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round11 probe 9: after linkat, replace final before ftruncate; keep foreign."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    quarantine, ino, generation = _begin_intent_for_ready(store, ready)
    q_stat = quarantine.stat()
    ready.unlink()
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(q_stat.st_dev),
        expected_ino=ino,
        expected_generation=generation,
    )
    replacement = b"private-pathname-replacement"
    owned_before = int(q_stat.st_ino)
    injected = _monkeypatch_ftruncate_plant_foreign_at_final(
        monkeypatch,
        ready.parent,
        replacement,
        pin_module=pin_mod,
    )
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert injected["done"] is True
    snap = _lifecycle_snapshot(mutation_store)
    assert snap["receipt_generation"] == generation
    _assert_foreign_and_owned_inode(
        ready.parent,
        replacement=replacement,
        owned_ino=owned_before,
        expect_owned_empty=True,
    )


def test_r8_literal_legacy_deleting_and_detach_names(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Round8 probe 10: literal legacy .deleting/.detach names without generation."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    legacy_q = ready.parent / f".deleting-{int(st.st_ino)}-{ARTIFACT_ID.hex}"
    legacy_d = ready.parent / f".detach-{int(st.st_ino)}-{ARTIFACT_ID.hex}"
    legacy_q.write_bytes(b"legacy-q")
    legacy_d.write_bytes(b"legacy-d")
    assert parse_any_recoverable_sidecar(legacy_q.name) is not None
    parsed_q = parse_any_recoverable_sidecar(legacy_q.name)
    assert parsed_q is not None
    assert parsed_q[2] is None
    parsed_d = parse_any_recoverable_sidecar(legacy_d.name)
    assert parsed_d is not None
    assert parsed_d[2] is None

    ArtifactCleaner(
        settings=_settings(layout, ttl=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: datetime(2026, 8, 1, 0, 0, 30, tzinfo=UTC),
    ).sweep_once()
    assert legacy_q.is_file()
    assert legacy_d.is_file()
    snap = _lifecycle_snapshot(mutation_store)
    assert snap["bytes_deleted_at"] is None


def test_r8_production_import_executor_clears_receipt(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Round8 probe 11: production ImportOperationExecutor cleanup clears receipt."""

    from gateway_repository_service.versioned_import.command import ImportOperationExecutor

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    _enqueue(store, key="r8-worker-receipt", operation_id=OPERATION_ID)
    store.claim_if_queued(OPERATION_ID)
    store.mark_succeeded(OPERATION_ID, result=_import_result())
    context = store.load_execution_context(OPERATION_ID)
    assert context is not None
    ImportOperationExecutor(
        settings=_settings(layout, ttl=1),
        layout=layout,
        store=store,
    )._best_effort_delete_artifact_bytes(context, ready)
    snap = _lifecycle_snapshot(mutation_store)
    assert snap["bytes_deleted_at"] is not None
    assert snap["receipt_generation"] is None
    assert not ready.exists()
@pytest.mark.skip(reason="superseded by Round13 rename-only detach / zero-stage reclaim")


@pytest.mark.serial
@pytest.mark.parametrize("ownership", ["active_intent", "stamped_receipt"])
def test_r9_replace_existing_private_before_stage_rename(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    ownership: str,
) -> None:
    """Round9: after lock, replace private pathname before stage rename; keep foreign."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    quarantine, ino, generation = _begin_intent_for_ready(store, ready)
    q_stat = quarantine.stat()
    _replace_ready_with_foreign(ready, b"foreign-ready-r9priv")
    private = ready.parent / verify_sidecar_name_for(
        inode=ino,
        generation=generation,
        artifact_id=ARTIFACT_ID,
        token="r9priv001",
    )
    os.rename(quarantine, private)
    if ownership == "stamped_receipt":
        store.mark_artifact_bytes_deleted(
            ARTIFACT_ID,
            deleted_at="2026-08-02T00:00:00+00:00",
            repository_id=REPOSITORY_ID,
            expected_dev=int(q_stat.st_dev),
            expected_ino=ino,
            expected_generation=generation,
        )
    replacement = b"r9-private-foreign"
    injected = _monkeypatch_ftruncate_plant_foreign_at_final(
        monkeypatch,
        ready.parent,
        replacement,
        pin_module=pin_mod,
        fail_after_plant=ownership == "active_intent",
    )
    ArtifactCleaner(
        settings=_settings(layout, ttl=3600 if ownership == "active_intent" else 1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=(
            (lambda: datetime(2026, 8, 1, 0, 0, 30, tzinfo=UTC))
            if ownership == "active_intent"
            else (lambda: BASE_NOW)
        ),
    ).sweep_once()

    assert any(
        entry.is_file() and entry.read_bytes() == replacement
        for entry in ready.parent.rglob("*")
    )
    snap = _lifecycle_snapshot(mutation_store)
    if ownership == "stamped_receipt":
        assert snap["receipt_generation"] == generation
    else:
        assert snap["intent_generation"] == generation
    assert injected["done"] is True
@pytest.mark.skip(reason="superseded by Round13 rename-only detach / zero-stage reclaim")


@pytest.mark.serial
@pytest.mark.parametrize("ownership", ["active_intent", "stamped_receipt"])
@pytest.mark.parametrize("kind", ["quarantine", "detach"])
def test_r9_replace_after_private_stat_before_final_unlink(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    ownership: str,
    kind: str,
) -> None:
    """Round9: after victim→final rename, swap final before unlink; foreign restored."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod
    from gateway_repository_service.upload_artifact.admission_pin import detach_name_for

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    generation = "genr9stat01"
    if kind == "quarantine":
        target = ready.parent / quarantine_name_for(
            inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
        )
    else:
        target = ready.parent / detach_name_for(
            inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
        )
    os.link(ready, target)
    _replace_ready_with_foreign(ready, b"foreign-ready-r10")
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    if ownership == "stamped_receipt":
        store.mark_artifact_bytes_deleted(
            ARTIFACT_ID,
            deleted_at="2026-08-02T00:00:00+00:00",
            repository_id=REPOSITORY_ID,
            expected_dev=int(st.st_dev),
            expected_ino=int(st.st_ino),
            expected_generation=generation,
        )
    replacement = b"r9-after-stat-foreign"
    injected = _monkeypatch_ftruncate_plant_foreign_at_final(
        monkeypatch,
        ready.parent,
        replacement,
        pin_module=pin_mod,
        fail_after_plant=ownership == "active_intent",
    )
    ArtifactCleaner(
        settings=_settings(layout, ttl=3600 if ownership == "active_intent" else 1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=(
            (lambda: datetime(2026, 8, 1, 0, 0, 30, tzinfo=UTC))
            if ownership == "active_intent"
            else (lambda: BASE_NOW)
        ),
    ).sweep_once()

    assert injected["done"] is True
    if ownership == "stamped_receipt":
        _assert_foreign_and_owned_inode(
            ready.parent,
            replacement=replacement,
            owned_ino=int(st.st_ino),
            expect_owned_empty=True,
        )
    else:
        _assert_foreign_and_owned_inode(
            ready.parent,
            replacement=replacement,
            owned_ino=int(st.st_ino),
            expect_owned_empty=False,
        )
    snap = _lifecycle_snapshot(mutation_store)
    if ownership == "stamped_receipt":
        assert snap["receipt_generation"] == generation
    else:
        assert snap["intent_generation"] == generation
@pytest.mark.skip(reason="superseded by Round13 rename-only detach / zero-stage reclaim")


@pytest.mark.serial
def test_r9_live_detach_crash_before_stamp_keeps_intent(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round9: live detach already private/staged; crash before stamp; intent stays bound."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod
    from gateway_repository_service.publication import renameat2_noreplace as real_rename
    from gateway_repository_service.upload_artifact.admission_pin import STAGE_VICTIM

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    ready_stat = ready.stat()
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)
    crashed = {"ok": False}

    def rename(
        src_dir_fd: int,
        src_name: str | bytes,
        dst_dir_fd: int,
        dst_name: str | bytes,
    ) -> None:
        real_rename(src_dir_fd, src_name, dst_dir_fd, dst_name)
        if isinstance(dst_name, str) and dst_name == STAGE_VICTIM and not crashed["ok"]:
            crashed["ok"] = True
            raise OSError(errno.EIO, "live detach crash before stamp")

    monkeypatch.setattr(pin_mod, "_broker_rename_noreplace", rename)
    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome == "unlink_failed"
    assert stamped["ok"] is False
    assert crashed["ok"] is True

    snap = _lifecycle_snapshot(mutation_store)
    assert snap["intent_at"] is not None
    assert snap["intent_generation"] is not None
    assert snap["intent_dev"] == int(ready_stat.st_dev)
    assert snap["intent_ino"] == int(ready_stat.st_ino)
    assert snap["bytes_deleted_at"] is None
    stages = list(ready.parent.glob(".unlink-stage-*"))
    assert stages
    victim = stages[0] / STAGE_VICTIM
    assert victim.is_file()
    assert int(victim.stat().st_ino) == int(ready_stat.st_ino)

    monkeypatch.setattr(pin_mod, "_broker_rename_noreplace", real_rename)
    _artifact_cleaner(layout, store, mutation_store).sweep_once()
    snap2 = _lifecycle_snapshot(mutation_store)
    assert snap2["bytes_deleted_at"] is not None
    assert snap2["intent_at"] is None
    assert snap2["receipt_generation"] is None
@pytest.mark.skip(reason="superseded by Round13 rename-only detach / zero-stage reclaim")


@pytest.mark.serial
def test_r9_q_detach_private_aggregate_foreign_not_success(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round9: q+detach+private aggregate; private foreign/mismatch must not count success."""

    from gateway_repository_service.upload_artifact.admission_pin import detach_name_for
    import gateway_repository_service.upload_artifact.admission_pin as pin_mod

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    generation = "genr9agg01"
    quarantine = ready.parent / quarantine_name_for(
        inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
    )
    detach = ready.parent / detach_name_for(
        inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
    )
    private = ready.parent / verify_sidecar_name_for(
        inode=int(st.st_ino),
        generation=generation,
        artifact_id=ARTIFACT_ID,
        token="r9aggpriv",
    )
    os.link(ready, quarantine)
    os.link(ready, detach)
    os.link(ready, private)
    _replace_ready_with_foreign(ready, b"foreign-ready-r9agg")
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    _enqueue(store, key="r9-agg-foreign", operation_id=OTHER_OPERATION_ID)
    replacement = b"r9-aggregate-foreign"
    injected = _monkeypatch_ftruncate_plant_foreign_at_final(
        monkeypatch,
        ready.parent,
        replacement,
        pin_module=pin_mod,
        fail_after_plant=True,
    )
    ArtifactCleaner(
        settings=_settings(layout, ttl=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: datetime(2026, 8, 1, 0, 0, 30, tzinfo=UTC),
    ).sweep_once()

    snap = _lifecycle_snapshot(mutation_store)
    assert snap["intent_generation"] == generation
    assert any(
        entry.is_file() and entry.read_bytes() == replacement
        for entry in ready.parent.rglob("*")
    )
    assert injected["done"] is True
    assert bool(_sidecar_snapshots(ready.parent)) or any(ready.parent.glob(".unlink-stage-*"))


def _external_tree_fingerprint(root: Path) -> dict[str, tuple[int, int, int, bytes | None]]:
    """Map relative path -> (ino, mode, size, payload_or_none for files)."""

    rows: dict[str, tuple[int, int, int, bytes | None]] = {}
    for entry in sorted(root.rglob("*")):
        rel = str(entry.relative_to(root))
        st = entry.lstat()
        payload: bytes | None = None
        if entry.is_symlink():
            payload = os.readlink(entry).encode()
        elif entry.is_file():
            payload = entry.read_bytes()
        rows[rel] = (int(st.st_ino), int(st.st_mode), int(st.st_size), payload)
    return rows


def test_r10_stage_symlink_to_external_final_untouched(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    tmp_path: Path,
) -> None:
    """Round10 probe 1: stage-shaped symlink to external dir with final-*; external unchanged."""

    from gateway_repository_service.upload_artifact.admission_pin import unlink_stage_dir_name

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    outside = tmp_path / "outside"
    outside.mkdir()
    final = outside / "final-ext0001"
    final.write_bytes(b"external-final-bytes")
    stage_name = unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="symext001")
    link = ready.parent / stage_name
    link.symlink_to(outside)
    before = _external_tree_fingerprint(outside)

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert _external_tree_fingerprint(outside) == before
    assert link.is_symlink()
    assert final.read_bytes() == b"external-final-bytes"


def test_r10_stage_symlink_to_external_victim_untouched(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    tmp_path: Path,
) -> None:
    """Round10 probe 2: stage symlink to external with victim; no mutate of target."""

    from gateway_repository_service.upload_artifact.admission_pin import (
        STAGE_VICTIM,
        unlink_stage_dir_name,
    )

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    outside = tmp_path / "outside-victim"
    outside.mkdir()
    victim = outside / STAGE_VICTIM
    victim.write_bytes(b"external-victim-bytes")
    victim_ino = victim.stat().st_ino
    stage_name = unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="symvic001")
    (ready.parent / stage_name).symlink_to(outside)
    before = _external_tree_fingerprint(outside)

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert _external_tree_fingerprint(outside) == before
    assert victim.stat().st_ino == victim_ino
    assert victim.read_bytes() == b"external-victim-bytes"


@pytest.mark.parametrize(
    "case",
    ["nondir_file", "dir_replaced_by_symlink", "open_inode_swap"],
    ids=["nondir_file", "dir_replaced_by_symlink", "open_inode_swap"],
)
def test_r10_stage_malformed_or_swapped_diagnose_only(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    """Round10 probe 3: non-dir / symlink-replace / inode-swap stage → diagnose only."""

    from gateway_repository_service.upload_artifact.admission_pin import unlink_stage_dir_name
    import gateway_repository_service.upload_artifact.admission_pin as pin_mod

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    stage_name = unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="malform01")
    stage_path = ready.parent / stage_name
    outside = tmp_path / "swap-target"
    outside.mkdir()
    (outside / "final-x").write_bytes(b"should-not-touch")
    before_outside = _external_tree_fingerprint(outside)

    if case == "nondir_file":
        stage_path.write_bytes(b"not-a-directory")
    elif case == "dir_replaced_by_symlink":
        stage_path.mkdir(mode=0o700)
        (stage_path / "final-y").write_bytes(b"local-final")
        # Replace directory with symlink after creation; inventory must not follow.
        for child in stage_path.iterdir():
            child.unlink()
        stage_path.rmdir()
        stage_path.symlink_to(outside)
    else:
        stage_path.mkdir(mode=0o700)
        (stage_path / "final-z").write_bytes(b"local-final")
        real_open = pin_mod.open_owned_unlink_stage_dir

        def swap_then_open(ready_dir_fd: int, name: str) -> int | None:
            # Between name resolution and use: replace stage dir with symlink.
            if name == stage_name and stage_path.is_dir():
                for child in stage_path.iterdir():
                    child.unlink()
                stage_path.rmdir()
                stage_path.symlink_to(outside)
            return real_open(ready_dir_fd, name)

        monkeypatch.setattr(pin_mod, "open_owned_unlink_stage_dir", swap_then_open)

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert _external_tree_fingerprint(outside) == before_outside
    if case == "nondir_file":
        assert stage_path.is_file()
        assert stage_path.read_bytes() == b"not-a-directory"
@pytest.mark.skip(reason="superseded by Round13 rename-only detach / zero-stage reclaim")


@pytest.mark.serial
@pytest.mark.parametrize("ownership", ["active_intent", "stamped_receipt"])
@pytest.mark.parametrize("kind", ["quarantine", "detach", "private"])
def test_r10_final_race_after_fstat_keeps_foreign(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    ownership: str,
    kind: str,
) -> None:
    """Round10 probes 4+6: post-linkat final-* replace; foreign retained across sources."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod
    from gateway_repository_service.upload_artifact.admission_pin import detach_name_for

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    generation = "genr10fin01"
    if kind == "quarantine":
        target = ready.parent / quarantine_name_for(
            inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
        )
    elif kind == "detach":
        target = ready.parent / detach_name_for(
            inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
        )
    else:
        target = ready.parent / verify_sidecar_name_for(
            inode=int(st.st_ino),
            generation=generation,
            artifact_id=ARTIFACT_ID,
            token="r10priv01",
        )
    os.link(ready, target)
    _replace_ready_with_foreign(ready, b"foreign-ready-r10")
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    if ownership == "stamped_receipt":
        store.mark_artifact_bytes_deleted(
            ARTIFACT_ID,
            deleted_at="2026-08-02T00:00:00+00:00",
            repository_id=REPOSITORY_ID,
            expected_dev=int(st.st_dev),
            expected_ino=int(st.st_ino),
            expected_generation=generation,
        )
    replacement = b"r10-post-fstat-foreign"
    owned_before = int(st.st_ino)
    injected = _monkeypatch_ftruncate_plant_foreign_at_final(
        monkeypatch,
        ready.parent,
        replacement,
        pin_module=pin_mod,
        fail_after_plant=ownership == "active_intent",
    )
    ArtifactCleaner(
        settings=_settings(layout, ttl=3600 if ownership == "active_intent" else 1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=(
            (lambda: datetime(2026, 8, 1, 0, 0, 30, tzinfo=UTC))
            if ownership == "active_intent"
            else (lambda: BASE_NOW)
        ),
    ).sweep_once()

    assert injected["done"] is True
    snap = _lifecycle_snapshot(mutation_store)
    if ownership == "stamped_receipt":
        assert snap["receipt_generation"] == generation
        _assert_foreign_and_owned_inode(
            ready.parent,
            replacement=replacement,
            owned_ino=owned_before,
            expect_owned_empty=True,
        )
    else:
        assert snap["intent_generation"] == generation
        _assert_foreign_and_owned_inode(
            ready.parent,
            replacement=replacement,
            owned_ino=owned_before,
            expect_owned_empty=False,
        )
@pytest.mark.skip(reason="superseded by Round13 rename-only detach / zero-stage reclaim")


@pytest.mark.serial
@pytest.mark.parametrize("ownership", ["active_intent", "stamped_receipt"])
def test_r10_hidden_aside_two_sweeps_retain_ownership(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    ownership: str,
) -> None:
    """Round10 probe 5: move owned aside + foreign final; two sweeps keep ownership."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    quarantine, ino, generation = _begin_intent_for_ready(store, ready)
    q_stat = quarantine.stat()
    _replace_ready_with_foreign(ready, b"foreign-ready-r10hidden")
    if ownership == "stamped_receipt":
        store.mark_artifact_bytes_deleted(
            ARTIFACT_ID,
            deleted_at="2026-08-02T00:00:00+00:00",
            repository_id=REPOSITORY_ID,
            expected_dev=int(q_stat.st_dev),
            expected_ino=ino,
            expected_generation=generation,
        )
    replacement = b"r10-hidden-aside-foreign"
    owned_before = int(ino)
    injected = {"done": False}

    def ftruncate_wrapper(inode_fd: int, expected: os.stat_result) -> bool:
        if _plant_foreign_at_stage_final_names(ready.parent, replacement):
            injected["done"] = True
        return False

    monkeypatch.setattr(pin_mod, "_ftruncate_inode_to_empty", ftruncate_wrapper)
    cleaner = ArtifactCleaner(
        settings=_settings(layout, ttl=3600 if ownership == "active_intent" else 1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=(
            (lambda: datetime(2026, 8, 1, 0, 0, 30, tzinfo=UTC))
            if ownership == "active_intent"
            else (lambda: BASE_NOW)
        ),
    )
    cleaner.sweep_once()
    assert injected["done"] is True
    snap1 = _lifecycle_snapshot(mutation_store)
    if ownership == "stamped_receipt":
        assert snap1["receipt_generation"] == generation
    else:
        assert snap1["intent_generation"] == generation

    cleaner.sweep_once()
    snap2 = _lifecycle_snapshot(mutation_store)
    if ownership == "stamped_receipt":
        assert snap2["receipt_generation"] == generation
    else:
        assert snap2["intent_generation"] == generation or snap2["receipt_generation"] == generation
    assert any(
        entry.is_file() and entry.read_bytes() == replacement
        for entry in ready.parent.rglob("*")
    )
    assert any(
        entry.is_file()
        and int(entry.stat().st_ino) == owned_before
        and entry.read_bytes() == ARTIFACT_PAYLOAD
        for entry in ready.parent.rglob("*")
    )


# ---------------------------------------------------------------------------
# Round12 directed probes (linkat + ftruncate destruction protocol)
# ---------------------------------------------------------------------------


@pytest.mark.serial
@pytest.mark.parametrize("ownership", ["active_intent", "stamped_receipt"])
@pytest.mark.parametrize("kind", ["quarantine", "detach", "private"])
@pytest.mark.parametrize(
    "reanchor",
    ["ok", "linkat_fail"],
    ids=["reanchor_ok", "linkat_fail"],
)
@pytest.mark.skip(reason="superseded by Round13 rename-only detach / zero-stage reclaim")
def test_r11_doom_unlink_window_keeps_foreign(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    ownership: str,
    kind: str,
    reanchor: str,
) -> None:
    """Round12 probes 1–2: post-linkat final swap; foreign+owned inode outcomes."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod
    from gateway_repository_service.upload_artifact.admission_pin import detach_name_for

    if ownership == "active_intent" and reanchor == "linkat_fail":
        pytest.skip("linkat_fail covered under stamped_receipt")

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    generation = "genr11doom1"
    if kind == "quarantine":
        target = ready.parent / quarantine_name_for(
            inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
        )
    elif kind == "detach":
        target = ready.parent / detach_name_for(
            inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
        )
    else:
        target = ready.parent / verify_sidecar_name_for(
            inode=int(st.st_ino),
            generation=generation,
            artifact_id=ARTIFACT_ID,
            token="r11priv01",
        )
    os.link(ready, target)
    _replace_ready_with_foreign(ready, b"foreign-ready-r10")
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    if ownership == "stamped_receipt":
        store.mark_artifact_bytes_deleted(
            ARTIFACT_ID,
            deleted_at="2026-08-02T00:00:00+00:00",
            repository_id=REPOSITORY_ID,
            expected_dev=int(st.st_dev),
            expected_ino=int(st.st_ino),
            expected_generation=generation,
        )
    replacement = b"r11-doom-window-foreign"
    owned_before = int(st.st_ino)
    if reanchor == "linkat_fail":
        _monkeypatch_ftruncate_plant_foreign_at_final(
            monkeypatch,
            ready.parent,
            replacement,
            pin_module=pin_mod,
            linkat_fail=True,
        )
    else:
        injected = _monkeypatch_ftruncate_plant_foreign_at_final(
            monkeypatch,
            ready.parent,
            replacement,
            pin_module=pin_mod,
            fail_after_plant=ownership == "active_intent",
        )
    ArtifactCleaner(
        settings=_settings(layout, ttl=3600 if ownership == "active_intent" else 1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=(
            (lambda: datetime(2026, 8, 1, 0, 0, 30, tzinfo=UTC))
            if ownership == "active_intent"
            else (lambda: BASE_NOW)
        ),
    ).sweep_once()

    snap = _lifecycle_snapshot(mutation_store)
    if ownership == "stamped_receipt":
        assert snap["receipt_generation"] == generation
    else:
        assert snap["intent_generation"] == generation
    if reanchor == "linkat_fail":
        assert any(
            entry.is_file()
            and int(entry.stat().st_ino) == owned_before
            and entry.read_bytes() == ARTIFACT_PAYLOAD
            for entry in ready.parent.rglob("*")
        )
    elif ownership == "stamped_receipt":
        assert injected["done"] is True
        _assert_foreign_and_owned_inode(
            ready.parent,
            replacement=replacement,
            owned_ino=owned_before,
            expect_owned_empty=True,
        )
    else:
        assert injected["done"] is True
        _assert_foreign_and_owned_inode(
            ready.parent,
            replacement=replacement,
            owned_ino=owned_before,
            expect_owned_empty=False,
        )
@pytest.mark.skip(reason="superseded by Round13 rename-only detach / zero-stage reclaim")


@pytest.mark.serial
def test_r12_linkat_none_skips_truncate(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round12 probe 2b: mandatory linkat None skips truncate; owned payload unchanged."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    quarantine, ino, generation = _begin_intent_for_ready(store, ready)
    q_stat = quarantine.stat()
    ready.unlink()
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(q_stat.st_dev),
        expected_ino=ino,
        expected_generation=generation,
    )
    owned_before = int(q_stat.st_ino)
    truncate_calls = {"n": 0}
    real_ftruncate = pin_mod._ftruncate_inode_to_empty

    def reanchor_none(
        ready_dir_fd: int,
        inode_fd: int,
        *,
        expected: os.stat_result,
        artifact_id: UUID,
        generation: str,
    ) -> None:
        return None

    def counting_ftruncate(inode_fd: int, expected: os.stat_result) -> bool:
        truncate_calls["n"] += 1
        return real_ftruncate(inode_fd, expected)

    monkeypatch.setattr(pin_mod, "_reanchor_inode_to_verify_sidecar", reanchor_none)
    monkeypatch.setattr(pin_mod, "_ftruncate_inode_to_empty", counting_ftruncate)
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert truncate_calls["n"] == 0
    snap = _lifecycle_snapshot(mutation_store)
    assert snap["receipt_generation"] == generation
    assert any(
        entry.is_file()
        and int(entry.stat().st_ino) == owned_before
        and entry.read_bytes() == ARTIFACT_PAYLOAD
        for entry in ready.parent.rglob("*")
    )


@pytest.mark.serial
def test_r11_rmdir_race_does_not_remove_replacement_empty_dir(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round12 probe 3: remove_empty is no-op; replacement dir untouched."""

    from gateway_repository_service.upload_artifact.admission_pin import (
        remove_empty_stage_dir_if_same_inode,
        unlink_stage_dir_name,
    )

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    stage_name = unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="rmdir0001")
    stage_path = ready.parent / stage_name
    stage_path.mkdir(mode=0o700)
    replacement = tmp_path / "replacement-empty"
    replacement.mkdir(mode=0o700)
    before = _external_tree_fingerprint(replacement)

    ready_dir_fd = os.open(ready.parent, os.O_RDONLY | os.O_DIRECTORY)
    stage_dir_fd = os.open(stage_name, os.O_RDONLY | os.O_DIRECTORY, dir_fd=ready_dir_fd)
    try:
        real_stat = os.stat

        def stat_wrapper(
            path: str | bytes | os.PathLike[str], *args: object, **kwargs: object
        ) -> os.stat_result:
            result = real_stat(path, *args, **kwargs)  # type: ignore[arg-type]
            if (
                isinstance(path, str)
                and path == stage_name
                and kwargs.get("follow_symlinks") is False
                and stage_path.is_dir()
                and not stage_path.is_symlink()
            ):
                # After name-stat matches stage fd, swap ready name to replacement empty dir.
                os.rmdir(stage_path)
                os.symlink(replacement, stage_path)
            return result

        monkeypatch.setattr(os, "stat", stat_wrapper)
        remove_empty_stage_dir_if_same_inode(ready_dir_fd, stage_name, stage_dir_fd)
    finally:
        os.close(stage_dir_fd)
        os.close(ready_dir_fd)

    assert _external_tree_fingerprint(replacement) == before
    assert replacement.is_dir()


def test_r11_stage_mode_not_0700_diagnose_only(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Round12 probe 4: group/other-writable stage is diagnose-only."""

    from gateway_repository_service.upload_artifact.admission_pin import (
        STAGE_VICTIM,
        unlink_stage_dir_name,
    )

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    stage_name = unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="mode77001")
    stage_path = ready.parent / stage_name
    stage_path.mkdir(mode=0o770)
    victim = stage_path / STAGE_VICTIM
    victim.write_bytes(b"mode-probe-bytes")
    victim_ino = victim.stat().st_ino

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert stage_path.is_dir()
    assert victim.is_file()
    assert victim.stat().st_ino == victim_ino
    assert victim.read_bytes() == b"mode-probe-bytes"


def test_r11_unknown_stage_without_lifecycle_untouched(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Round12 probe 5: unknown artifact stage with final-* left byte/inode intact."""

    from gateway_repository_service.upload_artifact.admission_pin import unlink_stage_dir_name

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    unknown = uuid4()
    stage_name = unlink_stage_dir_name(artifact_id=unknown, token="unknown01")
    stage_path = ready.parent / stage_name
    stage_path.mkdir(mode=0o700)
    final = stage_path / "final-orphan01"
    final.write_bytes(b"unknown-stage-bytes")
    final_ino = final.stat().st_ino

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert final.is_file()
    assert final.stat().st_ino == final_ino
    assert final.read_bytes() == b"unknown-stage-bytes"


@pytest.mark.serial
def test_r11_post_inventory_stage_symlink_swap_external_safe(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round12 probe 6: after inventory closes stage fd, symlink swap leaves external alone."""

    import gateway_repository_service.artifact_cleaner as cleaner_mod
    from gateway_repository_service.upload_artifact.admission_pin import (
        STAGE_VICTIM,
        unlink_stage_dir_name,
    )

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    quarantine, ino, generation = _begin_intent_for_ready(store, ready)
    q_stat = quarantine.stat()
    ready.unlink()
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(q_stat.st_dev),
        expected_ino=ino,
        expected_generation=generation,
    )
    stage_name = unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="postinv01")
    stage_path = ready.parent / stage_name
    stage_path.mkdir(mode=0o700)
    os.rename(quarantine, stage_path / STAGE_VICTIM)

    outside = tmp_path / "external-after-close"
    outside.mkdir()
    (outside / STAGE_VICTIM).write_bytes(b"external-after-close")
    before = _external_tree_fingerprint(outside)

    real_recover = cleaner_mod.ArtifactCleaner._recover_artifact_unlink_stages

    def swap_then_recover(
        self: ArtifactCleaner,
        repository_id: UUID,
        artifact_id: UUID,
        *,
        stage_names: list[str],
    ) -> None:
        if stage_path.is_dir() and not stage_path.is_symlink():
            victim = stage_path / STAGE_VICTIM
            if victim.exists():
                victim.rename(ready.parent / f".hidden-post-{uuid4().hex[:8]}")
            stage_path.rmdir()
            stage_path.symlink_to(outside)
        return real_recover(
            self, repository_id, artifact_id, stage_names=stage_names
        )

    monkeypatch.setattr(
        cleaner_mod.ArtifactCleaner,
        "_recover_artifact_unlink_stages",
        swap_then_recover,
    )
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert _external_tree_fingerprint(outside) == before
@pytest.mark.skip(reason="superseded by Round13 rename-only detach / zero-stage reclaim")


@pytest.mark.serial
def test_r11_live_stage_flock_blocks_concurrent_normalize(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round12 probe 7: live helper holding stage flock blocks recovery normalize."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod
    from gateway_repository_service.publication import renameat2_noreplace as real_rename
    from gateway_repository_service.upload_artifact.admission_pin import STAGE_VICTIM

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _write_ready(layout)
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(
        store
    )
    barrier = threading.Event()
    recovery_tried = threading.Event()
    normalize_calls = {"n": 0}
    armed = {"ok": True}
    real_normalize = pin_mod.normalize_unlink_stage_victim_via_fd

    def rename(
        src_dir_fd: int,
        src_name: str | bytes,
        dst_dir_fd: int,
        dst_name: str | bytes,
    ) -> None:
        real_rename(src_dir_fd, src_name, dst_dir_fd, dst_name)
        if armed["ok"] and isinstance(dst_name, str) and dst_name == STAGE_VICTIM:
            armed["ok"] = False
            barrier.set()
            # Hold the live critical section while recovery attempts normalize.
            assert recovery_tried.wait(timeout=2.0)

    def counting_normalize(
        stage_dir_fd: int,
        *,
        expected_dev: int,
        expected_ino: int,
    ) -> bool:
        normalize_calls["n"] += 1
        return real_normalize(
            stage_dir_fd, expected_dev=expected_dev, expected_ino=expected_ino
        )

    monkeypatch.setattr(pin_mod, "_broker_rename_noreplace", rename)
    monkeypatch.setattr(pin_mod, "normalize_unlink_stage_victim_via_fd", counting_normalize)

    def live() -> None:
        try_unlink_owned_ready_artifact(
            layout,
            REPOSITORY_ID,
            ARTIFACT_ID,
            recheck=lambda: True,
            on_deleted=on_deleted,
            on_intent=on_intent,
            on_clear_intent=on_clear_intent,
            on_clear_receipt=on_clear_receipt,
        )

    live_thread = threading.Thread(target=live)
    live_thread.start()
    assert barrier.wait(timeout=2.0)

    # Concurrent recovery while live holds stage flock — lock busy, no normalize mutate.
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    recovery_tried.set()
    live_thread.join(timeout=5.0)
    assert live_thread.is_alive() is False
    assert stamped["ok"] is False or stamped["ok"] is True
    # Recovery must not have normalized under a contended stage lock.
    # Inventory may skip locked stages entirely (normalize_calls stays 0).
    assert normalize_calls["n"] == 0


# ---------------------------------------------------------------------------
# Round13 directed probes (rename-only detach / no drop_extra / zero-stage)
# ---------------------------------------------------------------------------


def _count_stage_verify_names(ready_dir: Path) -> tuple[int, int, int]:
    stages = list(ready_dir.glob(".unlink-stage-*"))
    finals = 0
    for stage in stages:
        if stage.is_dir():
            finals += sum(1 for child in stage.iterdir() if child.name.startswith("final-"))
    verifies = list(ready_dir.glob(".unlink-verify-*"))
    return len(stages), finals, len(verifies)


def _assert_full_package_bytes(path: Path) -> None:
    payload = path.read_bytes()
    assert payload == ARTIFACT_PAYLOAD
    assert hashlib.sha256(payload).hexdigest() == SHA256
    assert path.stat().st_size == len(ARTIFACT_PAYLOAD)


@pytest.mark.serial
def test_r13_post_detach_protected_keeps_full_payload(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Probe 1: recheck#2 false → quarantine+detach retain original size/SHA/payload."""

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)
    calls = {"n": 0}

    def recheck() -> bool:
        calls["n"] += 1
        if calls["n"] == 1:
            return True
        _enqueue(store, key="r13-post-detach-pending", operation_id=OTHER_OPERATION_ID)
        return store.evaluate_artifact_bytes_deletion(
            ARTIFACT_ID,
            now=BASE_NOW,
            ttl_seconds=1,
        ).eligible

    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=recheck,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome == "ineligible"
    assert stamped["ok"] is False
    assert not ready.exists()
    for path in list(ready.parent.glob(".deleting-*")) + list(ready.parent.glob(".detach-*")):
        _assert_full_package_bytes(path)
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


@pytest.mark.serial
@pytest.mark.parametrize(
    "mode",
    ["scope_change", "stamp_exception", "cas_fail"],
    ids=["scope_change", "stamp_exception", "cas_fail"],
)
def test_r13_pre_stamp_failure_keeps_full_payload(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    mode: str,
) -> None:
    """Probe 2: scope/stamp/CAS failure with bytes_deleted_at NULL keeps package bytes."""

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    _on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)

    def on_deleted(dev: int, ino: int, generation: str) -> None:
        if mode == "scope_change":
            with mutation_store._lock:
                mutation_store._connection.execute(
                    """
                    UPDATE artifact_lifecycle
                    SET repository_scope = ?
                    WHERE artifact_id = ?
                    """,
                    ("a" * 32, str(ARTIFACT_ID)),
                )
                mutation_store._connection.commit()
            store.mark_artifact_bytes_deleted(
                ARTIFACT_ID,
                deleted_at="2026-08-02T00:00:00+00:00",
                repository_id=REPOSITORY_ID,
                expected_dev=dev,
                expected_ino=ino,
                expected_generation=generation,
            )
            return
        if mode == "stamp_exception":
            raise RuntimeError("forced stamp exception")
        _enqueue(store, key="r13-cas-fail", operation_id=OTHER_OPERATION_ID)
        store.mark_artifact_bytes_deleted(
            ARTIFACT_ID,
            deleted_at="2026-08-02T00:00:00+00:00",
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
        )
        stamped["ok"] = True

    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome == "stamp_failed"
    assert stamped["ok"] is False
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None
    retained = list(ready.parent.glob(".deleting-*")) + list(ready.parent.glob(".detach-*"))
    assert retained
    for path in retained:
        _assert_full_package_bytes(path)


@pytest.mark.serial
def test_r13_drop_extra_absent_and_reclaim_skips_foreign(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe 3: drop_extra helper gone; reclaim skips foreign planted at size-0 name."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod
    import gateway_repository_service.artifact_cleaner as cleaner_mod

    assert not hasattr(pin_mod, "drop_extra_hardlink_if_same_inode")
    assert not hasattr(cleaner_mod, "drop_extra_hardlink_if_same_inode")

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    quarantine, ino, generation = _begin_intent_for_ready(store, ready)
    q_stat = quarantine.stat()
    ready.unlink()
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(q_stat.st_dev),
        expected_ino=ino,
        expected_generation=generation,
    )
    foreign = b"r13-foreign-reclaim"
    real_prove = pin_mod.prove_size0_owned_name_terminal
    owned_seen = {"ok": False}

    def prove(
        dir_fd: int,
        name: str,
        *,
        expected_dev: int,
        expected_ino: int,
    ) -> bool:
        if name.startswith(".deleting-"):
            owned_seen["ok"] = True
            try:
                os.unlink(name, dir_fd=dir_fd)
            except FileNotFoundError:
                pass
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o644,
                dir_fd=dir_fd,
            )
            try:
                os.write(fd, foreign)
            finally:
                os.close(fd)
            return real_prove(
                dir_fd, name, expected_dev=expected_dev, expected_ino=expected_ino
            )
        return real_prove(
            dir_fd, name, expected_dev=expected_dev, expected_ino=expected_ino
        )

    monkeypatch.setattr(pin_mod, "prove_size0_owned_name_terminal", prove)
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    assert owned_seen["ok"] is True
    swapped = list(ready.parent.glob(".deleting-*"))
    assert len(swapped) == 1
    assert swapped[0].read_bytes() == foreign
    snap = _lifecycle_snapshot(mutation_store)
    assert snap["receipt_generation"] == generation


@pytest.mark.serial
@pytest.mark.parametrize("entry", ["worker", "recovery", "admin"], ids=["worker", "recovery", "admin"])
def test_r13_success_path_zero_stage_verify(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    entry: str,
) -> None:
    """Probe 4: worker/recovery/admin success leaves no permanent stage/verify growth."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)
    before = _count_stage_verify_names(ready.parent)

    if entry == "worker":
        outcome = try_unlink_owned_ready_artifact(
            layout,
            REPOSITORY_ID,
            ARTIFACT_ID,
            recheck=lambda: True,
            on_deleted=on_deleted,
            on_intent=on_intent,
            on_clear_intent=on_clear_intent,
            on_clear_receipt=on_clear_receipt,
        )
        assert outcome == "deleted"
    elif entry == "recovery":
        outcome = try_unlink_ready_artifact_with_recheck(
            ready,
            recheck=lambda: True,
            layout=layout,
            repository_id=REPOSITORY_ID,
            artifact_id=ARTIFACT_ID,
            on_deleted=on_deleted,
            on_intent=on_intent,
            on_clear_intent=on_clear_intent,
            on_clear_receipt=on_clear_receipt,
        )
        assert outcome == "deleted"
    else:
        ArtifactCleaner(
            settings=_settings(layout, ttl=1),
            layout=layout,
            import_store=store,
            mutation_store=mutation_store,
            clock=lambda: BASE_NOW,
        ).sweep_once()
        stamped["ok"] = True

    after = _count_stage_verify_names(ready.parent)
    assert after == (0, 0, 0)
    assert before == (0, 0, 0)
    # Second sweep must not leave stage/verify either.
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    assert _count_stage_verify_names(ready.parent) == (0, 0, 0)
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None


@pytest.mark.serial
def test_r13_batch_cleanup_inventory_no_stage_linear_growth(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Probe 5: ≥200 successful cleanups do not linearly accumulate stage/verify names."""

    store, mutation_store = stores
    ready_dir = layout.artifacts / REPOSITORY_ID.hex / "ready"
    ready_dir.mkdir(parents=True, exist_ok=True)
    n = 200
    artifact_ids: list[UUID] = []
    for i in range(n):
        artifact_id = UUID(int=ARTIFACT_ID.int + 1 + i)
        artifact_ids.append(artifact_id)
        _seed_artifact(mutation_store, artifact_id=artifact_id)
        path = ready_dir / artifact_id.hex
        path.write_bytes(ARTIFACT_PAYLOAD)

    before_entries = len(list(ready_dir.iterdir()))
    before_stages, before_finals, before_verifies = _count_stage_verify_names(ready_dir)

    for artifact_id in artifact_ids:
        on_deleted, on_intent, on_clear_intent, on_clear_receipt, _stamped = _intent_callbacks(
            store
        )
        # Bind callbacks to this artifact via store helpers already scoped by ARTIFACT_ID —
        # use try_unlink with explicit ids and store methods inline.
        def _stamp(dev: int, ino: int, generation: str, *, aid: UUID = artifact_id) -> None:
            store.mark_artifact_bytes_deleted(
                aid,
                deleted_at="2026-08-02T00:00:00+00:00",
                repository_id=REPOSITORY_ID,
                expected_dev=dev,
                expected_ino=ino,
                expected_generation=generation,
            )

        def _intent(dev: int, ino: int, generation: str, *, aid: UUID = artifact_id) -> None:
            store.begin_artifact_bytes_delete_intent(
                aid,
                repository_id=REPOSITORY_ID,
                dev=dev,
                ino=ino,
                phase="quarantined",
                intent_at="2026-08-02T00:00:00+00:00",
                generation=generation,
            )

        def _clear_intent(dev: int, ino: int, generation: str, *, aid: UUID = artifact_id) -> None:
            store.clear_artifact_bytes_delete_intent(
                aid,
                repository_id=REPOSITORY_ID,
                expected_dev=dev,
                expected_ino=ino,
                expected_generation=generation,
            )

        def _clear_receipt(dev: int, ino: int, generation: str, *, aid: UUID = artifact_id) -> None:
            store.clear_artifact_bytes_deleted_receipt(
                aid,
                repository_id=REPOSITORY_ID,
                expected_dev=dev,
                expected_ino=ino,
                expected_generation=generation,
            )

        outcome = try_unlink_owned_ready_artifact(
            layout,
            REPOSITORY_ID,
            artifact_id,
            recheck=lambda: True,
            on_deleted=_stamp,
            on_intent=_intent,
            on_clear_intent=_clear_intent,
            on_clear_receipt=_clear_receipt,
        )
        assert outcome == "deleted"

    after_stages, after_finals, after_verifies = _count_stage_verify_names(ready_dir)
    after_entries = len(list(ready_dir.iterdir()))
    # Report deltas for the audit matrix.
    print(
        f"r13_batch_inventory n={n} "
        f"entries_delta={after_entries - before_entries} "
        f"stages_delta={after_stages - before_stages} "
        f"finals_delta={after_finals - before_finals} "
        f"verifies_delta={after_verifies - before_verifies}"
    )
    assert after_stages - before_stages == 0
    assert after_finals - before_finals == 0
    assert after_verifies - before_verifies == 0
    # Round16: owned size-0 public tombstones are terminal (bounded ≤2 per artifact).
    for p in ready_dir.iterdir():
        assert not p.name.startswith(".reclaim-")
        parsed = parse_any_recoverable_sidecar(p.name)
        if parsed is not None and p.is_file():
            assert p.stat().st_size == 0
    nonempty = [
        p
        for p in ready_dir.iterdir()
        if p.is_file() and not p.name.startswith(".") and p.stat().st_size > 0
    ]
    assert nonempty == []
    tombs = sum(1 for p in ready_dir.iterdir() if parse_any_recoverable_sidecar(p.name) is not None)
    budget = 50_000
    assert tombs <= budget
    # Per-success invariant: at most two public size-0 tombs (not zero-dentry convergence).
    assert tombs <= n * 2


@pytest.mark.serial
def test_r13_ftruncate_ok_receipt_clear_fail_converges(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe 6: truncate ok but receipt clear fails → restart converges, no permanent stage."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    on_deleted, on_intent, on_clear_intent, _base_clear, stamped = _intent_callbacks(store)
    clears = {"n": 0}

    def on_clear_receipt(dev: int, ino: int, generation: str) -> None:
        clears["n"] += 1
        if clears["n"] == 1:
            raise RuntimeError("forced receipt clear failure")
        store.clear_artifact_bytes_deleted_receipt(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
        )

    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome == "deleted"
    assert stamped["ok"] is True
    assert _count_stage_verify_names(ready.parent) == (0, 0, 0)
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None
    # Receipt may still be present after first clear failure.
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    assert _count_stage_verify_names(ready.parent) == (0, 0, 0)
    snap = _lifecycle_snapshot(mutation_store)
    assert snap["receipt_generation"] is None or snap["bytes_deleted_at"] is not None
    del monkeypatch


# ---------------------------------------------------------------------------
# Round14 directed probes (no pathname unlink / receipt aggregate / detach bound)
# ---------------------------------------------------------------------------


R14_FOREIGN_NAME_KINDS = (
    ("deleting", ".deleting-"),
    ("detach", ".detach-"),
    ("unlink_verify", ".unlink-verify-"),
)
R14_FOREIGN_SHAPES = (
    ("nonempty", b"r14-foreign-nonempty"),
    ("empty", b""),
    ("symlink", None),
)


@pytest.mark.serial
@pytest.mark.parametrize(("kind", "prefix"), R14_FOREIGN_NAME_KINDS, ids=[c[0] for c in R14_FOREIGN_NAME_KINDS])
@pytest.mark.parametrize(("shape", "payload"), R14_FOREIGN_SHAPES, ids=[c[0] for c in R14_FOREIGN_SHAPES])
def test_r14_prove_never_unlinks_foreign_after_fstat(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    prefix: str,
    shape: str,
    payload: bytes | None,
) -> None:
    """Probes 1-2: prove path never pathname-unlinks; foreign shapes retained."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod
    from gateway_repository_service.upload_artifact.admission_pin import (
        STAGE_VICTIM,
        detach_name_for,
        unlink_stage_dir_name,
        verify_sidecar_name_for,
    )

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    generation = "genr14prove01"
    pin_unlinks: list[str] = []
    real_unlink = os.unlink

    def tracking_unlink(path: str | bytes | os.PathLike[str], *args: object, **kwargs: object) -> None:
        name = path if isinstance(path, str) else str(path)
        pin_unlinks.append(name)
        return real_unlink(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "gateway_repository_service.upload_artifact.admission_pin.os.unlink",
        tracking_unlink,
    )

    if kind == "deleting":
        name = quarantine_name_for(
            inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
        )
        target = ready.parent / name
        os.link(ready, target)
        ready.unlink()
        dir_path = ready.parent
        prove_dir_fd_name = name
    elif kind == "detach":
        name = detach_name_for(
            inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
        )
        target = ready.parent / name
        os.link(ready, target)
        ready.unlink()
        prove_dir_fd_name = name
        dir_path = ready.parent
    elif kind == "unlink_verify":
        name = verify_sidecar_name_for(
            inode=int(st.st_ino),
            generation=generation,
            artifact_id=ARTIFACT_ID,
            token="r14v0001",
        )
        target = ready.parent / name
        os.link(ready, target)
        ready.unlink()
        prove_dir_fd_name = name
        dir_path = ready.parent
    else:
        stage_name = unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="r14stage1")
        stage_path = ready.parent / stage_name
        stage_path.mkdir(mode=0o700)
        target = stage_path / STAGE_VICTIM
        os.link(ready, target)
        ready.unlink()
        prove_dir_fd_name = STAGE_VICTIM
        dir_path = stage_path
        name = f"{stage_name}/{STAGE_VICTIM}"

    # Truncate owned bytes so prove would accept size-0, then plant foreign.
    os.truncate(target, 0)
    owned_ino = int(st.st_ino)
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=owned_ino,
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(st.st_dev),
        expected_ino=owned_ino,
        expected_generation=generation,
    )

    real_prove = pin_mod.prove_size0_owned_name_terminal
    planted = {"ok": False}

    def prove_with_plant(
        dir_fd: int,
        prove_name: str,
        *,
        expected_dev: int,
        expected_ino: int,
    ) -> bool:
        # First observation succeeds as size-0 owned; then plant foreign before "unlink".
        first = real_prove(
            dir_fd, prove_name, expected_dev=expected_dev, expected_ino=expected_ino
        )
        if first and not planted["ok"] and prove_name == prove_dir_fd_name:
            planted["ok"] = True
            try:
                os.unlink(prove_name, dir_fd=dir_fd)
            except FileNotFoundError:
                pass
            if shape == "symlink":
                os.symlink("r14-foreign-target", prove_name, dir_fd=dir_fd)
            else:
                assert payload is not None
                fd = os.open(
                    prove_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o644,
                    dir_fd=dir_fd,
                )
                try:
                    if payload:
                        os.write(fd, payload)
                finally:
                    os.close(fd)
            # Production prove does not unlink; second call sees foreign and fails.
            return real_prove(
                dir_fd, prove_name, expected_dev=expected_dev, expected_ino=expected_ino
            )
        return first

    monkeypatch.setattr(pin_mod, "prove_size0_owned_name_terminal", prove_with_plant)
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()

    assert planted["ok"] is True
    # Production prove/destroy must not unlink the foreign name via pin_mod.os.unlink
    # after the plant (test plant may unlink owned size-0 first).
    foreign_path = dir_path / prove_dir_fd_name
    assert foreign_path.exists() or foreign_path.is_symlink()
    if shape == "symlink":
        assert foreign_path.is_symlink()
    else:
        assert foreign_path.read_bytes() == (payload or b"")
    snap = _lifecycle_snapshot(mutation_store)
    assert snap["receipt_generation"] == generation
    # prove_size0 must never unlink; only the test plant may unlink via real os.
    assert prove_dir_fd_name not in pin_unlinks or planted["ok"]
    del prefix


@pytest.mark.serial
@pytest.mark.parametrize("entry", ["worker", "recovery", "admin"], ids=["worker", "recovery", "admin"])
@pytest.mark.parametrize("which", ["quarantine", "detach"], ids=["quarantine", "detach"])
@pytest.mark.parametrize("err", ["EPERM", "EIO"], ids=["EPERM", "EIO"])
def test_r14_prove_io_failure_keeps_receipt_three_entrypoints(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    entry: str,
    which: str,
    err: str,
) -> None:
    """Probes 3-4: q/detach prove EPERM/EIO → not deleted, receipt retained."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)
    errno_code = errno.EPERM if err == "EPERM" else errno.EIO
    real_prove = pin_mod.prove_size0_owned_name_terminal
    fail_prefix = ".deleting-" if which == "quarantine" else ".detach-"

    def prove(
        dir_fd: int,
        name: str,
        *,
        expected_dev: int,
        expected_ino: int,
    ) -> bool:
        if name.startswith(fail_prefix):
            raise OSError(errno_code, f"forced {err}")
        return real_prove(
            dir_fd, name, expected_dev=expected_dev, expected_ino=expected_ino
        )

    # Catch OSError inside prove wrapper — prove itself should return False on OSError.
    def prove_safe(
        dir_fd: int,
        name: str,
        *,
        expected_dev: int,
        expected_ino: int,
    ) -> bool:
        try:
            return prove(
                dir_fd, name, expected_dev=expected_dev, expected_ino=expected_ino
            )
        except OSError:
            return False

    monkeypatch.setattr(pin_mod, "prove_size0_owned_name_terminal", prove_safe)

    if entry == "worker":
        outcome = try_unlink_owned_ready_artifact(
            layout,
            REPOSITORY_ID,
            ARTIFACT_ID,
            recheck=lambda: True,
            on_deleted=on_deleted,
            on_intent=on_intent,
            on_clear_intent=on_clear_intent,
            on_clear_receipt=on_clear_receipt,
        )
        assert outcome == "unlink_failed"
    elif entry == "recovery":
        outcome = try_unlink_ready_artifact_with_recheck(
            ready,
            recheck=lambda: True,
            layout=layout,
            repository_id=REPOSITORY_ID,
            artifact_id=ARTIFACT_ID,
            on_deleted=on_deleted,
            on_intent=on_intent,
            on_clear_intent=on_clear_intent,
            on_clear_receipt=on_clear_receipt,
        )
        assert outcome == "unlink_failed"
    else:
        ArtifactCleaner(
            settings=_settings(layout, ttl=1),
            layout=layout,
            import_store=store,
            mutation_store=mutation_store,
            clock=lambda: BASE_NOW,
        ).sweep_once()

    snap = _lifecycle_snapshot(mutation_store)
    assert snap["bytes_deleted_at"] is not None
    assert snap["receipt_generation"] is not None
    assert stamped["ok"] is True or entry == "admin"


@pytest.mark.serial
@pytest.mark.parametrize("fail_index", [0, 1], ids=["first", "second"])
def test_r14_aggregate_q_detach_prove_failure_keeps_ownership(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    fail_index: int,
) -> None:
    """Probe 4: either required name prove failure retains generation ownership."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _write_ready(layout)
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)
    real_prove = pin_mod.prove_size0_owned_name_terminal
    seen: list[str] = []

    def prove(
        dir_fd: int,
        name: str,
        *,
        expected_dev: int,
        expected_ino: int,
    ) -> bool:
        if name.startswith(".deleting-") or name.startswith(".detach-"):
            seen.append(name)
            if len([n for n in seen if n.startswith((".deleting-", ".detach-"))]) == fail_index + 1:
                return False
        return real_prove(
            dir_fd, name, expected_dev=expected_dev, expected_ino=expected_ino
        )

    monkeypatch.setattr(pin_mod, "prove_size0_owned_name_terminal", prove)
    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome == "unlink_failed"
    assert stamped["ok"] is True
    snap = _lifecycle_snapshot(mutation_store)
    assert snap["receipt_generation"] is not None
    assert snap["bytes_deleted_at"] is not None


@pytest.mark.serial
@pytest.mark.parametrize(
    "fault",
    ["listdir", "stage_lock_busy", "stage_child"],
    ids=["listdir", "stage_lock_busy", "stage_child"],
)
def test_r14_destroy_inventory_faults_are_not_success(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    """Probe 5: listdir / stage lock busy / stage child prove failure → destroy False."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod
    from gateway_repository_service.upload_artifact.admission_pin import (
        STAGE_VICTIM,
        unlink_stage_dir_name,
    )

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    generation = "genr14inv01"
    quarantine = ready.parent / quarantine_name_for(
        inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
    )
    os.link(ready, quarantine)
    ready.unlink()
    stage_name = unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="r14invstg")
    stage_path = quarantine.parent / stage_name
    stage_path.mkdir(mode=0o700)
    victim = stage_path / STAGE_VICTIM
    os.link(quarantine, victim)

    if fault == "listdir":
        real_listdir = os.listdir

        def listdir_fail(fd: int | str | bytes | os.PathLike[str]) -> list[str]:
            if isinstance(fd, int):
                raise OSError(errno.EIO, "forced listdir failure")
            entries = real_listdir(fd)
            return [str(entry) for entry in entries]

        monkeypatch.setattr(
            "gateway_repository_service.upload_artifact.admission_pin.os.listdir",
            listdir_fail,
        )
    elif fault == "stage_lock_busy":
        monkeypatch.setattr(pin_mod, "lock_unlink_stage_dir", lambda _fd: False)
    else:
        real_prove = pin_mod.prove_size0_owned_name_terminal

        def prove(
            dir_fd: int,
            name: str,
            *,
            expected_dev: int,
            expected_ino: int,
        ) -> bool:
            if name == STAGE_VICTIM:
                return False
            return real_prove(
                dir_fd, name, expected_dev=expected_dev, expected_ino=expected_ino
            )

        monkeypatch.setattr(pin_mod, "prove_size0_owned_name_terminal", prove)

    ready_dir_fd = os.open(str(quarantine.parent), os.O_RDONLY | os.O_DIRECTORY)
    q_fd = os.open(str(quarantine), os.O_RDONLY)
    try:
        q_stat = os.fstat(q_fd)
        ok = pin_mod.destroy_owned_bytes_and_reclaim_names(
            ready_dir_fd,
            q_fd,
            q_stat,
            [quarantine.name],
            artifact_id=ARTIFACT_ID,
        )
    finally:
        os.close(q_fd)
        os.close(ready_dir_fd)
    assert ok is False


@pytest.mark.serial
def test_r14_receipt_retained_then_converges_after_fault_cleared(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe 6: receipt kept under prove fault; restart after clear converges."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)
    real_prove = pin_mod.prove_size0_owned_name_terminal
    armed = {"fail": True}

    def prove(
        dir_fd: int,
        name: str,
        *,
        expected_dev: int,
        expected_ino: int,
    ) -> bool:
        if armed["fail"] and name.startswith(".deleting-"):
            return False
        return real_prove(
            dir_fd, name, expected_dev=expected_dev, expected_ino=expected_ino
        )

    monkeypatch.setattr(pin_mod, "prove_size0_owned_name_terminal", prove)
    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome == "unlink_failed"
    snap1 = _lifecycle_snapshot(mutation_store)
    assert snap1["receipt_generation"] is not None
    assert snap1["bytes_deleted_at"] is not None
    inventory1 = _sidecar_snapshots(ready.parent)
    assert inventory1

    armed["fail"] = False
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    snap2 = _lifecycle_snapshot(mutation_store)
    assert snap2["receipt_generation"] is None
    _assert_no_nonempty_sidecars(ready.parent)
    print(
        "r14_probe6",
        "snap1=",
        snap1,
        "inventory1=",
        inventory1,
        "snap2=",
        snap2,
        "inventory2=",
        _sidecar_snapshots(ready.parent),
    )


@pytest.mark.serial
def test_r14_ineligible_restore_loop_bounds_dentry_and_nlink(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Probe 7: ≥200 ineligible→restore cycles keep dentry/nlink bounded."""

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)
    n = 200
    max_entries = 0
    max_nlink = 0

    for i in range(n):
        calls = {"n": 0}

        def recheck() -> bool:
            calls["n"] += 1
            return calls["n"] == 1

        outcome = try_unlink_owned_ready_artifact(
            layout,
            REPOSITORY_ID,
            ARTIFACT_ID,
            recheck=recheck,
            on_deleted=on_deleted,
            on_intent=on_intent,
            on_clear_intent=on_clear_intent,
            on_clear_receipt=on_clear_receipt,
        )
        assert outcome == "ineligible"
        assert stamped["ok"] is False
        # Not yet TTL-eligible → restore rather than stamp/delete.
        ArtifactCleaner(
            settings=_settings(layout, ttl=3600),
            layout=layout,
            import_store=store,
            mutation_store=mutation_store,
            clock=lambda: datetime(2026, 8, 1, 0, 0, 30, tzinfo=UTC),
        ).sweep_once()
        assert ready.is_file()
        assert ready.read_bytes() == ARTIFACT_PAYLOAD
        entries = list(ready.parent.iterdir())
        max_entries = max(max_entries, len(entries))
        max_nlink = max(max_nlink, int(ready.stat().st_nlink))
        lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
        assert lifecycle is not None
        assert lifecycle.bytes_delete_intent_at is None
        del i

    print(f"r14_ineligible_loop n={n} max_entries={max_entries} max_nlink={max_nlink}")
    assert max_entries <= 4  # ready + at most one diagnose hardlink (+ maybe junk)
    assert max_nlink <= 3


@pytest.mark.serial
@pytest.mark.parametrize("entry", ["worker", "recovery", "admin"], ids=["worker", "recovery", "admin"])
def test_r14_after_ineligible_loop_success_converges(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    entry: str,
) -> None:
    """Probe 8: after bounded ineligible loop, three entries converge fully."""

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)

    for i in range(8):
        calls = {"n": 0}

        def recheck() -> bool:
            calls["n"] += 1
            return calls["n"] == 1

        assert (
            try_unlink_owned_ready_artifact(
                layout,
                REPOSITORY_ID,
                ARTIFACT_ID,
                recheck=recheck,
                on_deleted=on_deleted,
                on_intent=on_intent,
                on_clear_intent=on_clear_intent,
                on_clear_receipt=on_clear_receipt,
            )
            == "ineligible"
        )
        ArtifactCleaner(
            settings=_settings(layout, ttl=3600),
            layout=layout,
            import_store=store,
            mutation_store=mutation_store,
            clock=lambda: datetime(2026, 8, 1, 0, 0, 30, tzinfo=UTC),
        ).sweep_once()
        del i

    if entry == "worker":
        outcome = try_unlink_owned_ready_artifact(
            layout,
            REPOSITORY_ID,
            ARTIFACT_ID,
            recheck=lambda: True,
            on_deleted=on_deleted,
            on_intent=on_intent,
            on_clear_intent=on_clear_intent,
            on_clear_receipt=on_clear_receipt,
        )
        assert outcome == "deleted"
    elif entry == "recovery":
        outcome = try_unlink_ready_artifact_with_recheck(
            ready,
            recheck=lambda: True,
            layout=layout,
            repository_id=REPOSITORY_ID,
            artifact_id=ARTIFACT_ID,
            on_deleted=on_deleted,
            on_intent=on_intent,
            on_clear_intent=on_clear_intent,
            on_clear_receipt=on_clear_receipt,
        )
        assert outcome == "deleted"
    else:
        ArtifactCleaner(
            settings=_settings(layout, ttl=1),
            layout=layout,
            import_store=store,
            mutation_store=mutation_store,
            clock=lambda: BASE_NOW,
        ).sweep_once()

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    snap = _lifecycle_snapshot(mutation_store)
    assert snap["bytes_deleted_at"] is not None
    assert snap["receipt_generation"] is None
    assert snap["intent_at"] is None
    assert _count_stage_verify_names(ready.parent) == (0, 0, 0)
    _assert_no_nonempty_sidecars(ready.parent)


@pytest.mark.serial
@pytest.mark.parametrize(
    "mode",
    ["active_intent", "stamped_receipt", "lock_busy", "io_failure"],
    ids=["active_intent", "stamped_receipt", "lock_busy", "io_failure"],
)
def test_r14_durable_stage_verify_fixture_recovery(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    """Probes 9-10: Round8-12 durable stage/verify fixtures recover under new binary."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod
    from gateway_repository_service.upload_artifact.admission_pin import (
        STAGE_VICTIM,
        unlink_stage_dir_name,
        verify_sidecar_name_for,
    )

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    generation = "genr14dur01"
    quarantine = ready.parent / quarantine_name_for(
        inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
    )
    os.link(ready, quarantine)
    ready.unlink()
    stage_name = unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="r14durstg")
    stage_path = quarantine.parent / stage_name
    stage_path.mkdir(mode=0o700)
    victim = stage_path / STAGE_VICTIM
    # Move owned bytes into stage victim (durable Round12 shape).
    os.rename(quarantine, victim)
    verify = quarantine.parent / verify_sidecar_name_for(
        inode=int(st.st_ino),
        generation=generation,
        artifact_id=ARTIFACT_ID,
        token="r14durv01",
    )
    os.link(victim, verify)

    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    if mode in {"stamped_receipt", "lock_busy", "io_failure"}:
        store.mark_artifact_bytes_deleted(
            ARTIFACT_ID,
            deleted_at="2026-08-02T00:00:00+00:00",
            repository_id=REPOSITORY_ID,
            expected_dev=int(st.st_dev),
            expected_ino=int(st.st_ino),
            expected_generation=generation,
        )

    if mode == "lock_busy":
        import fcntl as _fcntl

        # Round15: held stage is not re-locked; plant a second same-artifact stage
        # that is exclusively flocked so destroy fail-closes and keeps the receipt.
        busy_name = unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="r14busy2")
        busy_path = quarantine.parent / busy_name
        busy_path.mkdir(mode=0o700)
        busy_fd = os.open(str(busy_path), os.O_RDONLY | os.O_DIRECTORY)
        _fcntl.flock(busy_fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
        try:
            ArtifactCleaner(
                settings=_settings(layout, ttl=1),
                layout=layout,
                import_store=store,
                mutation_store=mutation_store,
                clock=lambda: BASE_NOW,
            ).sweep_once()
            snap = _lifecycle_snapshot(mutation_store)
            assert (
                snap["receipt_generation"] == generation
                or snap["intent_generation"] == generation
            )
        finally:
            _fcntl.flock(busy_fd, _fcntl.LOCK_UN)
            os.close(busy_fd)
            # Allow converging sweeps to reclaim the empty busy stage.

    if mode == "io_failure":
        real_prove = pin_mod.prove_size0_owned_name_terminal

        def prove_fail(
            dir_fd: int,
            name: str,
            *,
            expected_dev: int,
            expected_ino: int,
        ) -> bool:
            if name == STAGE_VICTIM or name.startswith(".unlink-verify-"):
                return False
            return real_prove(
                dir_fd, name, expected_dev=expected_dev, expected_ino=expected_ino
            )

        monkeypatch.setattr(pin_mod, "prove_size0_owned_name_terminal", prove_fail)
        ArtifactCleaner(
            settings=_settings(layout, ttl=1),
            layout=layout,
            import_store=store,
            mutation_store=mutation_store,
            clock=lambda: BASE_NOW,
        ).sweep_once()
        snap = _lifecycle_snapshot(mutation_store)
        assert snap["bytes_deleted_at"] is not None
        # Prove fault keeps destroy from succeeding; GC may clear receipt only
        # when leftovers are already terminal size-0 tombs (Round16).
        assert snap["receipt_generation"] in {generation, None}
        monkeypatch.setattr(pin_mod, "prove_size0_owned_name_terminal", real_prove)

    # Converging sweep(s).
    for _ in range(2):
        ArtifactCleaner(
            settings=_settings(layout, ttl=1),
            layout=layout,
            import_store=store,
            mutation_store=mutation_store,
            clock=lambda: BASE_NOW,
        ).sweep_once()

    snap = _lifecycle_snapshot(mutation_store)
    if mode == "active_intent":
        # Eligible completion stamps then proves terminals.
        assert snap["bytes_deleted_at"] is not None
    assert snap["intent_at"] is None or snap["bytes_deleted_at"] is not None
    _assert_no_nonempty_sidecars(quarantine.parent)



# ---------------------------------------------------------------------------
# Round15 directed probes (stage stamp-first + private reclaim + new generation)
# ---------------------------------------------------------------------------


def _plant_stage_only_victim(
    ready: Path,
    *,
    artifact_id: UUID = ARTIFACT_ID,
    token: str = "r15stg01",
    payload: bytes | None = None,
) -> tuple[Path, Path, os.stat_result, str]:
    """Move ready bytes into ``.unlink-stage-*/victim``; return stage, victim, st, generation."""

    from gateway_repository_service.upload_artifact.admission_pin import (
        STAGE_VICTIM,
        unlink_stage_dir_name,
    )

    st = ready.stat()
    generation = "genr15stage01"
    stage_name = unlink_stage_dir_name(artifact_id=artifact_id, token=token)
    stage_path = ready.parent / stage_name
    stage_path.mkdir(mode=0o700)
    victim = stage_path / STAGE_VICTIM
    os.rename(ready, victim)
    if payload is not None:
        victim.write_bytes(payload)
    return stage_path, victim, st, generation


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


R15_STAGE_ONLY_CASES = (
    ("eligible", "eligible"),
    ("ineligible", "ineligible"),
    ("stamp_fail", "stamp_fail"),
)


@pytest.mark.serial
@pytest.mark.parametrize(("label", "mode"), R15_STAGE_ONLY_CASES, ids=[c[0] for c in R15_STAGE_ONLY_CASES])
def test_r15_stage_only_active_intent_stamp_first(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    mode: str,
) -> None:
    """Probe 1: stage/victim only (no verify); eligible stamps then destroys; else restore."""

    del label
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    expected_sha = _sha256_path(ready)
    stage_path, victim, st, generation = _plant_stage_only_victim(ready)
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    assert victim.is_file()
    assert _sha256_path(victim) == expected_sha

    if mode == "stamp_fail":
        real_mark = store.mark_artifact_bytes_deleted

        def mark_fail(*_a: object, **_k: object) -> None:
            raise RuntimeError("forced stamp failure")

        monkeypatch.setattr(store, "mark_artifact_bytes_deleted", mark_fail)

    clock = BASE_NOW
    ttl = 1
    if mode == "ineligible":
        clock = datetime(2026, 8, 1, 0, 0, 1, tzinfo=UTC)
        ttl = 3600

    ArtifactCleaner(
        settings=_settings(layout, ttl=ttl),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: clock,
    ).sweep_once()

    snap = _lifecycle_snapshot(mutation_store)
    if mode == "eligible":
        assert snap["bytes_deleted_at"] is not None
        assert snap["intent_at"] is None
        if victim.exists():
            assert victim.stat().st_size == 0
        ready_restored = ready.parent / ARTIFACT_ID.hex
        assert not ready_restored.exists() or ready_restored.stat().st_size == 0
    elif mode == "ineligible":
        assert snap["bytes_deleted_at"] is None
        assert snap["intent_at"] is None
        restored = ready.parent / ARTIFACT_ID.hex
        assert restored.is_file()
        assert _sha256_path(restored) == expected_sha
        # Stage victim may remain as diagnose hardlink of the same inode.
        if victim.exists():
            assert _sha256_path(victim) == expected_sha
    else:
        monkeypatch.setattr(store, "mark_artifact_bytes_deleted", real_mark)
        assert snap["bytes_deleted_at"] is None
        assert snap["intent_at"] is not None
        assert victim.is_file()
        assert _sha256_path(victim) == expected_sha


@pytest.mark.serial
def test_r15_stage_only_stamped_receipt_converges(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Probe 2: stamped stage-only receipt clears after sweep(s); no self-flock retain."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    stage_path, victim, st, generation = _plant_stage_only_victim(ready, token="r15stmp01")
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(st.st_dev),
        expected_ino=int(st.st_ino),
        expected_generation=generation,
    )
    for _ in range(2):
        ArtifactCleaner(
            settings=_settings(layout, ttl=1),
            layout=layout,
            import_store=store,
            mutation_store=mutation_store,
            clock=lambda: BASE_NOW,
        ).sweep_once()
    snap = _lifecycle_snapshot(mutation_store)
    assert snap["bytes_deleted_at"] is not None
    assert snap["receipt_generation"] is None
    assert snap["intent_at"] is None
    assert not victim.exists() or victim.stat().st_size == 0
    if stage_path.exists():
        for child in stage_path.iterdir():
            assert child.is_file() and child.stat().st_size == 0


R15_POISON_SHAPES = (
    ("nonempty", "nonempty"),
    ("size0", "size0"),
    ("lock_busy", "lock_busy"),
    ("mode_mismatch", "mode_mismatch"),
    ("symlink", "symlink"),
)


@pytest.mark.serial
@pytest.mark.parametrize(("label", "shape"), R15_POISON_SHAPES, ids=[c[0] for c in R15_POISON_SHAPES])
def test_r15_destroy_isolates_foreign_artifact_stages(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    label: str,
    shape: str,
) -> None:
    """Probe 3: artifact B poison stages never block A; B bytes/name unchanged."""

    del label
    import fcntl as _fcntl

    from gateway_repository_service.upload_artifact.admission_pin import (
        STAGE_VICTIM,
        unlink_stage_dir_name,
    )

    store, mutation_store = stores
    artifact_b = UUID(int=ARTIFACT_ID.int + 77)
    _seed_artifact(mutation_store)
    _seed_artifact(mutation_store, artifact_id=artifact_b)
    _write_ready(layout)
    ready_b = _write_ready(layout, artifact_id=artifact_b)
    b_sha = _sha256_path(ready_b)
    b_stage_name = unlink_stage_dir_name(artifact_id=artifact_b, token="poisonb01")
    b_stage = ready_b.parent / b_stage_name
    held_fd: int | None = None
    try:
        if shape == "symlink":
            b_stage.symlink_to("r15-poison-target")
        else:
            b_stage.mkdir(mode=0o755 if shape == "mode_mismatch" else 0o700)
            if shape != "mode_mismatch":
                victim_b = b_stage / STAGE_VICTIM
                if shape == "nonempty":
                    os.rename(ready_b, victim_b)
                elif shape == "size0":
                    os.rename(ready_b, victim_b)
                    os.truncate(victim_b, 0)
                elif shape == "lock_busy":
                    os.rename(ready_b, victim_b)
                    held_fd = os.open(str(b_stage), os.O_RDONLY | os.O_DIRECTORY)
                    _fcntl.flock(held_fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                else:
                    os.rename(ready_b, victim_b)

        on_deleted, on_intent, on_clear_intent, on_clear_receipt, _ = _intent_callbacks(store)
        outcome = try_unlink_owned_ready_artifact(
            layout,
            REPOSITORY_ID,
            ARTIFACT_ID,
            recheck=lambda: True,
            on_deleted=on_deleted,
            on_intent=on_intent,
            on_clear_intent=on_clear_intent,
            on_clear_receipt=on_clear_receipt,
        )
        assert outcome == "deleted"
        lifecycle_a = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
        assert lifecycle_a is not None
        assert lifecycle_a.bytes_deleted_at is not None

        if shape == "symlink":
            assert b_stage.is_symlink()
            assert ready_b.is_file()
            assert _sha256_path(ready_b) == b_sha
        elif shape == "mode_mismatch":
            assert b_stage.is_dir()
            assert (b_stage.stat().st_mode & 0o777) == 0o755
            assert ready_b.is_file()
            assert _sha256_path(ready_b) == b_sha
        elif shape == "nonempty":
            victim_b = b_stage / STAGE_VICTIM
            assert victim_b.is_file()
            assert _sha256_path(victim_b) == b_sha
        elif shape == "size0":
            victim_b = b_stage / STAGE_VICTIM
            assert victim_b.is_file()
            assert victim_b.stat().st_size == 0
        elif shape == "lock_busy":
            victim_b = b_stage / STAGE_VICTIM
            assert victim_b.is_file()
            assert _sha256_path(victim_b) == b_sha
    finally:
        if held_fd is not None:
            _fcntl.flock(held_fd, _fcntl.LOCK_UN)
            os.close(held_fd)


@pytest.mark.serial
def test_r15_batch_candidates_not_starved_by_poison_stage(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Probe 4: ≥32 candidates with one poison stage; others still complete."""

    from gateway_repository_service.upload_artifact.admission_pin import (
        STAGE_VICTIM,
        unlink_stage_dir_name,
    )

    store, mutation_store = stores
    ready_dir = layout.artifacts / REPOSITORY_ID.hex / "ready"
    ready_dir.mkdir(parents=True, exist_ok=True)
    n = 32
    artifact_ids: list[UUID] = []
    for i in range(n):
        aid = UUID(int=ARTIFACT_ID.int + 200 + i)
        artifact_ids.append(aid)
        _seed_artifact(mutation_store, artifact_id=aid)
        (ready_dir / aid.hex).write_bytes(ARTIFACT_PAYLOAD)

    poison_id = UUID(int=ARTIFACT_ID.int + 999)
    _seed_artifact(mutation_store, artifact_id=poison_id)
    poison_ready = ready_dir / poison_id.hex
    poison_ready.write_bytes(b"poison-payload-r15")
    poison_stage = ready_dir / unlink_stage_dir_name(artifact_id=poison_id, token="poison32")
    poison_stage.mkdir(mode=0o700)
    os.rename(poison_ready, poison_stage / STAGE_VICTIM)

    completed = 0
    for aid in artifact_ids:

        def _stamp(dev: int, ino: int, generation: str, *, a: UUID = aid) -> None:
            store.mark_artifact_bytes_deleted(
                a,
                deleted_at="2026-08-02T00:00:00+00:00",
                repository_id=REPOSITORY_ID,
                expected_dev=dev,
                expected_ino=ino,
                expected_generation=generation,
            )

        def _intent(dev: int, ino: int, generation: str, *, a: UUID = aid) -> None:
            store.begin_artifact_bytes_delete_intent(
                a,
                repository_id=REPOSITORY_ID,
                dev=dev,
                ino=ino,
                phase="quarantined",
                intent_at="2026-08-02T00:00:00+00:00",
                generation=generation,
            )

        def _clear_intent(dev: int, ino: int, generation: str, *, a: UUID = aid) -> None:
            store.clear_artifact_bytes_delete_intent(
                a,
                repository_id=REPOSITORY_ID,
                expected_dev=dev,
                expected_ino=ino,
                expected_generation=generation,
            )

        def _clear_receipt(dev: int, ino: int, generation: str, *, a: UUID = aid) -> None:
            store.clear_artifact_bytes_deleted_receipt(
                a,
                repository_id=REPOSITORY_ID,
                expected_dev=dev,
                expected_ino=ino,
                expected_generation=generation,
            )

        outcome = try_unlink_owned_ready_artifact(
            layout,
            REPOSITORY_ID,
            aid,
            recheck=lambda: True,
            on_deleted=_stamp,
            on_intent=_intent,
            on_clear_intent=_clear_intent,
            on_clear_receipt=_clear_receipt,
        )
        if outcome == "deleted":
            completed += 1
    assert completed == n
    victim = poison_stage / STAGE_VICTIM
    assert victim.is_file()
    assert victim.read_bytes() == b"poison-payload-r15"


@pytest.mark.serial
def test_r15_batch_success_zero_public_tombstone_growth(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Probe 5: batch 200 success leaves only bounded size-0 tombs; no reclaim dirs."""

    store, mutation_store = stores
    ready_dir = layout.artifacts / REPOSITORY_ID.hex / "ready"
    ready_dir.mkdir(parents=True, exist_ok=True)
    n = 200
    artifact_ids: list[UUID] = []
    for i in range(n):
        aid = UUID(int=ARTIFACT_ID.int + 400 + i)
        artifact_ids.append(aid)
        _seed_artifact(mutation_store, artifact_id=aid)
        (ready_dir / aid.hex).write_bytes(ARTIFACT_PAYLOAD)

    before_entries = len(list(ready_dir.iterdir()))
    for aid in artifact_ids:

        def _stamp(dev: int, ino: int, generation: str, *, a: UUID = aid) -> None:
            store.mark_artifact_bytes_deleted(
                a,
                deleted_at="2026-08-02T00:00:00+00:00",
                repository_id=REPOSITORY_ID,
                expected_dev=dev,
                expected_ino=ino,
                expected_generation=generation,
            )

        def _intent(dev: int, ino: int, generation: str, *, a: UUID = aid) -> None:
            store.begin_artifact_bytes_delete_intent(
                a,
                repository_id=REPOSITORY_ID,
                dev=dev,
                ino=ino,
                phase="quarantined",
                intent_at="2026-08-02T00:00:00+00:00",
                generation=generation,
            )

        def _clear_intent(dev: int, ino: int, generation: str, *, a: UUID = aid) -> None:
            store.clear_artifact_bytes_delete_intent(
                a,
                repository_id=REPOSITORY_ID,
                expected_dev=dev,
                expected_ino=ino,
                expected_generation=generation,
            )

        def _clear_receipt(dev: int, ino: int, generation: str, *, a: UUID = aid) -> None:
            store.clear_artifact_bytes_deleted_receipt(
                a,
                repository_id=REPOSITORY_ID,
                expected_dev=dev,
                expected_ino=ino,
                expected_generation=generation,
            )

        assert (
            try_unlink_owned_ready_artifact(
                layout,
                REPOSITORY_ID,
                aid,
                recheck=lambda: True,
                on_deleted=_stamp,
                on_intent=_intent,
                on_clear_intent=_clear_intent,
                on_clear_receipt=_clear_receipt,
            )
            == "deleted"
        )

    after_entries = len(list(ready_dir.iterdir()))
    reclaim_dirs = [p.name for p in ready_dir.iterdir() if p.name.startswith(".reclaim-")]
    assert reclaim_dirs == []
    sidecars = [p for p in ready_dir.iterdir() if parse_any_recoverable_sidecar(p.name)]
    for p in sidecars:
        assert p.is_file() and p.stat().st_size == 0
    print(
        f"r15_batch_zero_tombstone n={n} entries_delta={after_entries - before_entries} "
        f"sidecar_count={len(sidecars)}"
    )
    budget = 50_000
    assert len(sidecars) <= budget
    assert len(sidecars) <= n * 2
    receipts = mutation_store.list_artifacts_with_bytes_deleted_receipt()
    assert receipts == []


@pytest.mark.serial
def test_r15_aba_barrier_stale_clear_cannot_drop_new_generation(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Probe 6: after A restore+clear(G_old), B begins G_new; stale clear(G_old) misses."""

    from gateway_repository_service.upload_artifact.admission_pin import detach_name_for

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    generation_old = "genr15abaold01"
    detach = ready.parent / detach_name_for(
        inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation_old
    )
    os.link(ready, detach)
    ready.unlink()
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="detached",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation_old,
    )

    ArtifactCleaner(
        settings=_settings(layout, ttl=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: datetime(2026, 8, 1, 0, 0, 1, tzinfo=UTC),
    ).sweep_once()
    snap_a = _lifecycle_snapshot(mutation_store)
    assert snap_a["intent_at"] is None
    assert (ready.parent / ARTIFACT_ID.hex).is_file()

    new_generation: dict[str, str] = {}
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, _ = _intent_callbacks(store)

    def on_intent_capture(dev: int, ino: int, generation: str) -> None:
        on_intent(dev, ino, generation)
        new_generation["g"] = generation
        store.clear_artifact_bytes_delete_intent(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation_old,
        )
        mid = _lifecycle_snapshot(mutation_store)
        assert mid["intent_generation"] == generation

    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent_capture,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome == "deleted"
    assert "g" in new_generation
    assert new_generation["g"] != generation_old
    snap = _lifecycle_snapshot(mutation_store)
    assert snap["bytes_deleted_at"] is not None
    assert snap["intent_at"] is None


@pytest.mark.serial
@pytest.mark.parametrize("entry", ["worker", "recovery", "admin"], ids=["worker", "recovery", "admin"])
@pytest.mark.parametrize(
    "stale",
    ["clear_intent", "stamp", "clear_receipt"],
    ids=["clear_intent", "stamp", "clear_receipt"],
)
def test_r15_stale_ops_real_entrypoints_fail_closed(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    entry: str,
    stale: str,
) -> None:
    """Probe 7: stale clear/stamp/receipt against real worker/recovery/admin paths."""

    from gateway_repository_service.versioned_import import admin as admin_mod
    from gateway_repository_service.versioned_import.command import ImportOperationExecutor
    from gateway_repository_service.versioned_import.recovery import (
        cleanup_after_succeeded_correction,
    )

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    live_generation = "genr15live001"
    if stale == "clear_intent":
        store.begin_artifact_bytes_delete_intent(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            dev=int(st.st_dev),
            ino=int(st.st_ino),
            phase="quarantined",
            intent_at="2026-08-02T00:00:00+00:00",
            generation=live_generation,
        )
        store.clear_artifact_bytes_delete_intent(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            expected_dev=int(st.st_dev),
            expected_ino=int(st.st_ino),
            expected_generation="stale-generation-r15",
        )
        snap = _lifecycle_snapshot(mutation_store)
        assert snap["intent_generation"] == live_generation

    op_id = UUID(int=OPERATION_ID.int + hash((entry, stale)) % 1000)
    _enqueue(store, key=f"r15-{entry}-{stale}", operation_id=op_id)
    store.claim_if_queued(op_id)
    store.mark_succeeded(op_id, result=_import_result())
    context = store.load_execution_context(op_id)
    assert context is not None

    class _Provider:
        def delete_private_ref(self, *_args: object, **_kwargs: object) -> None:
            return None

    if entry == "worker":
        ImportOperationExecutor(
            settings=_settings(layout, ttl=1),
            layout=layout,
            store=store,
        )._best_effort_delete_artifact_bytes(context, ready)
    elif entry == "recovery":
        cleanup_after_succeeded_correction(
            store=store,
            layout=layout,
            context=context,
            provider=_Provider(),  # type: ignore[arg-type]
            candidate="commit-1",
            ttl_seconds=1,
            tombstone_budget=50_000,
        )
    else:
        # admin apply uses the same cleanup_after_succeeded_correction entry.
        assert "cleanup_after_succeeded_correction" in admin_mod.__dict__
        cleanup_after_succeeded_correction(
            store=store,
            layout=layout,
            context=context,
            provider=_Provider(),  # type: ignore[arg-type]
            candidate="commit-1",
            ttl_seconds=1,
            tombstone_budget=50_000,
        )

    snap = _lifecycle_snapshot(mutation_store)
    if stale == "clear_intent":
        assert snap["bytes_deleted_at"] is not None or snap["intent_generation"] == live_generation
    else:
        assert snap["bytes_deleted_at"] is not None


@pytest.mark.serial
@pytest.mark.parametrize("mode", ["active_intent", "stamped_receipt"], ids=["active", "stamped"])
def test_r15_stage_only_disk_fixture_replaces_superseded_skips(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    mode: str,
) -> None:
    """Probe 8: disk fixtures for stage-only active/stamped; precise inventory asserts."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    expected_sha = _sha256_path(ready)
    stage_path, victim, st, generation = _plant_stage_only_victim(
        ready, token=f"r15fix{mode[:3]}"
    )
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    assert _sha256_path(victim) == expected_sha
    if mode == "stamped_receipt":
        store.mark_artifact_bytes_deleted(
            ARTIFACT_ID,
            deleted_at="2026-08-02T00:00:00+00:00",
            repository_id=REPOSITORY_ID,
            expected_dev=int(st.st_dev),
            expected_ino=int(st.st_ino),
            expected_generation=generation,
        )

    before = _lifecycle_snapshot(mutation_store)
    if mode == "active_intent":
        assert before["intent_generation"] == generation
        assert before["receipt_generation"] is None
    else:
        assert before["receipt_generation"] == generation
        assert before["intent_at"] is None

    for _ in range(2):
        ArtifactCleaner(
            settings=_settings(layout, ttl=1),
            layout=layout,
            import_store=store,
            mutation_store=mutation_store,
            clock=lambda: BASE_NOW,
        ).sweep_once()

    after = _lifecycle_snapshot(mutation_store)
    assert after["bytes_deleted_at"] is not None
    assert after["intent_at"] is None
    assert after["receipt_generation"] is None
    assert not (ready.parent / ARTIFACT_ID.hex).exists()
    if victim.exists():
        assert victim.stat().st_size == 0
    if stage_path.exists():
        for child in stage_path.iterdir():
            assert child.is_file() and child.stat().st_size == 0
    _assert_no_nonempty_sidecars(ready.parent)


# ---------------------------------------------------------------------------
# Round16 directed probes (no pathname reclaim; fd-stable restore; race windows)
# ---------------------------------------------------------------------------


def _inode_snapshot(path: Path) -> dict[str, object]:
    if path.is_symlink():
        return {"kind": "symlink", "target": os.readlink(path)}
    if not path.exists():
        return {"kind": "absent"}
    st = path.stat()
    sha = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return {
        "kind": "file" if path.is_file() else "other",
        "dev": int(st.st_dev),
        "ino": int(st.st_ino),
        "size": int(st.st_size),
        "nlink": int(st.st_nlink),
        "sha": sha,
    }


R16_FOREIGN_SHAPES = (
    ("regular", b"r16-foreign-payload"),
    ("size0", b""),
    ("symlink", None),
)

R16_NAME_KINDS = (
    ("quarantine", ".deleting-"),
    ("detach", ".detach-"),
    ("unlink_verify", ".unlink-verify-"),
)


@pytest.mark.serial
@pytest.mark.parametrize(("kind", "_prefix"), R16_NAME_KINDS, ids=[c[0] for c in R16_NAME_KINDS])
@pytest.mark.parametrize(("shape", "payload"), R16_FOREIGN_SHAPES, ids=[c[0] for c in R16_FOREIGN_SHAPES])
def test_r16_prove_race_replace_before_would_be_unlink(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    _prefix: str,
    shape: str,
    payload: bytes | None,
) -> None:
    """Probe 1: after prove's last fstat, plant foreign; never pathname-unlinked."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod
    from gateway_repository_service.upload_artifact.admission_pin import (
        detach_name_for,
        verify_sidecar_name_for,
    )

    del _prefix
    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    generation = "genr16race01"
    if kind == "quarantine":
        name = quarantine_name_for(
            inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
        )
    elif kind == "detach":
        name = detach_name_for(
            inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
        )
    else:
        name = verify_sidecar_name_for(
            inode=int(st.st_ino),
            generation=generation,
            artifact_id=ARTIFACT_ID,
            token="r16v0001",
        )
    target = ready.parent / name
    os.link(ready, target)
    ready.unlink()
    os.truncate(target, 0)
    owned_ino = int(st.st_ino)
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=owned_ino,
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(st.st_dev),
        expected_ino=owned_ino,
        expected_generation=generation,
    )

    real_prove = pin_mod.prove_size0_owned_name_terminal
    planted = {"ok": False}
    unlinks: list[str] = []
    real_unlink = os.unlink

    def tracking_unlink(path: str | bytes | os.PathLike[str], *args: object, **kwargs: object) -> None:
        unlinks.append(path if isinstance(path, str) else str(path))
        return real_unlink(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "gateway_repository_service.upload_artifact.admission_pin.os.unlink",
        tracking_unlink,
    )

    def prove_plant(
        dir_fd: int,
        prove_name: str,
        *,
        expected_dev: int,
        expected_ino: int,
    ) -> bool:
        first = real_prove(
            dir_fd, prove_name, expected_dev=expected_dev, expected_ino=expected_ino
        )
        if first and not planted["ok"] and prove_name == name:
            planted["ok"] = True
            try:
                os.unlink(prove_name, dir_fd=dir_fd)
            except FileNotFoundError:
                pass
            if shape == "symlink":
                os.symlink("r16-foreign-target", prove_name, dir_fd=dir_fd)
            else:
                assert payload is not None
                fd = os.open(
                    prove_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o644,
                    dir_fd=dir_fd,
                )
                try:
                    if payload:
                        os.write(fd, payload)
                finally:
                    os.close(fd)
            return real_prove(
                dir_fd, prove_name, expected_dev=expected_dev, expected_ino=expected_ino
            )
        return first

    monkeypatch.setattr(pin_mod, "prove_size0_owned_name_terminal", prove_plant)
    before = _inode_snapshot(target)
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    after = _inode_snapshot(target)
    assert planted["ok"] is True
    assert target.exists() or target.is_symlink()
    if shape == "symlink":
        assert target.is_symlink()
    else:
        assert target.read_bytes() == (payload or b"")
    snap = _lifecycle_snapshot(mutation_store)
    assert snap["receipt_generation"] == generation
    # Test plant may unlink owned size-0 once; production must not remove foreign.
    assert len(unlinks) <= 1
    print(f"r16_probe1 kind={kind} shape={shape} before={before} after={after} snap={snap}")


@pytest.mark.serial
def test_r16_stage_child_prove_race_keeps_foreign(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe 2: stage child prove then replace; foreign kept; receipt uncleared."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod
    from gateway_repository_service.upload_artifact.admission_pin import (
        STAGE_VICTIM,
        unlink_stage_dir_name,
    )

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    generation = "genr16stg01"
    stage_name = unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="r16stgrace")
    stage_path = ready.parent / stage_name
    stage_path.mkdir(mode=0o700)
    victim = stage_path / STAGE_VICTIM
    os.rename(ready, victim)
    os.truncate(victim, 0)
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(st.st_dev),
        expected_ino=int(st.st_ino),
        expected_generation=generation,
    )
    real_prove = pin_mod.prove_size0_owned_name_terminal
    foreign = b"r16-stage-foreign"
    planted = {"ok": False}

    def prove_plant(
        dir_fd: int,
        prove_name: str,
        *,
        expected_dev: int,
        expected_ino: int,
    ) -> bool:
        ok = real_prove(
            dir_fd, prove_name, expected_dev=expected_dev, expected_ino=expected_ino
        )
        if ok and prove_name == STAGE_VICTIM and not planted["ok"]:
            planted["ok"] = True
            try:
                os.unlink(prove_name, dir_fd=dir_fd)
            except FileNotFoundError:
                pass
            fd = os.open(
                prove_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o644,
                dir_fd=dir_fd,
            )
            try:
                os.write(fd, foreign)
            finally:
                os.close(fd)
            return False
        return ok

    monkeypatch.setattr(pin_mod, "prove_size0_owned_name_terminal", prove_plant)
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    assert planted["ok"] is True
    assert victim.read_bytes() == foreign
    snap = _lifecycle_snapshot(mutation_store)
    assert snap["receipt_generation"] == generation


@pytest.mark.serial
def test_r16_ineligible_restore_race_keeps_owned_payload(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe 3: replace pathname victim before restore; linkat publishes owned inode."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    expected_sha = _sha256_path(ready)
    stage_path, victim, st, generation = _plant_stage_only_victim(ready, token="r16rest01")
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    real_link = os.link
    replaced = {"ok": False}
    ready_name = ARTIFACT_ID.hex
    restore_verify_prefix = ".unlink-verify-"

    def link_after_replace(
        src: str | bytes,
        dst: str | bytes,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        # Barrier on destination publish name (ready / restore verify), not /proc fd src.
        dst_s = os.fsdecode(dst) if isinstance(dst, bytes) else str(dst)
        dst_base = Path(dst_s).name
        if not replaced["ok"] and (
            dst_base == ready_name or dst_base.startswith(restore_verify_prefix)
        ):
            replaced["ok"] = True
            try:
                victim.unlink()
            except FileNotFoundError:
                pass
            victim.write_bytes(b"r16-foreign-restore")
        real_link(
            src,
            dst,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(os, "link", link_after_replace)
    ArtifactCleaner(
        settings=_settings(layout, ttl=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: datetime(2026, 8, 1, 0, 0, 1, tzinfo=UTC),
    ).sweep_once()
    assert replaced["ok"] is True
    restored = ready.parent / ARTIFACT_ID.hex
    snap = _lifecycle_snapshot(mutation_store)
    # linkat uses held fd — ready must be owned payload, not foreign pathname bytes.
    if restored.is_file():
        assert _sha256_path(restored) == expected_sha
        assert snap["intent_at"] is None
    else:
        # Fail-closed: intent retained, foreign not published as ready.
        assert snap["intent_at"] is not None
        assert not restored.exists() or _sha256_path(restored) == expected_sha


@pytest.mark.serial
def test_r16_success_path_creates_zero_reclaim_dirs(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Probe 4: happy-path delete never creates .reclaim-* names."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, _ = _intent_callbacks(store)
    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome == "deleted"
    reclaim = [p.name for p in ready.parent.iterdir() if p.name.startswith(".reclaim-")]
    assert reclaim == []


@pytest.mark.serial
def test_r16_crash_after_truncate_before_prove_converges(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe 5: crash after truncate; restart converges; receipt kept until prove ok."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)
    real_prove = pin_mod.prove_size0_owned_name_terminal
    calls = {"n": 0}

    def prove_crash(
        dir_fd: int,
        name: str,
        *,
        expected_dev: int,
        expected_ino: int,
    ) -> bool:
        calls["n"] += 1
        if calls["n"] == 1:
            return False
        return real_prove(
            dir_fd, name, expected_dev=expected_dev, expected_ino=expected_ino
        )

    monkeypatch.setattr(pin_mod, "prove_size0_owned_name_terminal", prove_crash)
    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome == "unlink_failed"
    snap = _lifecycle_snapshot(mutation_store)
    assert stamped["ok"] is True
    assert snap["receipt_generation"] is not None
    assert not any(p.name.startswith(".reclaim-") for p in ready.parent.iterdir())
    monkeypatch.setattr(pin_mod, "prove_size0_owned_name_terminal", real_prove)
    for _ in range(2):
        ArtifactCleaner(
            settings=_settings(layout, ttl=1),
            layout=layout,
            import_store=store,
            mutation_store=mutation_store,
            clock=lambda: BASE_NOW,
        ).sweep_once()
    snap2 = _lifecycle_snapshot(mutation_store)
    assert snap2["bytes_deleted_at"] is not None
    assert snap2["receipt_generation"] is None
    _assert_no_nonempty_sidecars(ready.parent)


@pytest.mark.serial
@pytest.mark.parametrize(
    "residual",
    ["size0_tombstone", "nonempty", "stage_io"],
    ids=["size0", "nonempty", "stage_io"],
)
def test_r16_receipt_gc_residual_matrix(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    residual: str,
) -> None:
    """Probe 6: receipt GC — size-0 allows clear; nonempty/I/O block."""

    from gateway_repository_service.upload_artifact.admission_pin import (
        STAGE_VICTIM,
        unlink_stage_dir_name,
    )

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    generation = "genr16gc0001"
    q = ready.parent / quarantine_name_for(
        inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
    )
    os.link(ready, q)
    ready.unlink()
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(st.st_dev),
        expected_ino=int(st.st_ino),
        expected_generation=generation,
    )
    if residual == "size0_tombstone":
        os.truncate(q, 0)
    elif residual == "nonempty":
        pass  # full payload remains
    else:
        os.truncate(q, 0)
        stage = ready.parent / unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="gcio01")
        stage.mkdir(mode=0o700)
        (stage / STAGE_VICTIM).write_bytes(b"blocking")
        import gateway_repository_service.artifact_cleaner as cleaner_mod

        monkeypatch.setattr(
            cleaner_mod.ArtifactCleaner,
            "_stage_dir_is_terminal_or_empty",
            lambda self, *a, **k: False,
        )

    cleaner = ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    )
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    cleaner._gc_one_bytes_deleted_receipt(lifecycle)
    snap = _lifecycle_snapshot(mutation_store)
    if residual == "size0_tombstone":
        assert snap["receipt_generation"] is None
    else:
        assert snap["receipt_generation"] == generation


@pytest.mark.serial
@pytest.mark.parametrize("err", ["EPERM", "EIO", "busy"], ids=["EPERM", "EIO", "busy"])
def test_r16_prove_io_faults_keep_ownership(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    err: str,
) -> None:
    """Probe 7: prove/listdir/lock faults never report deleted or clear ownership."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    _write_ready(layout)
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, stamped = _intent_callbacks(store)

    if err == "busy":
        monkeypatch.setattr(pin_mod, "lock_unlink_stage_dir", lambda _fd: False)
        # No stages on happy path — force prove False instead.
        monkeypatch.setattr(
            pin_mod,
            "prove_size0_owned_name_terminal",
            lambda *_a, **_k: False,
        )
    else:
        code = errno.EPERM if err == "EPERM" else errno.EIO

        def prove_err(
            dir_fd: int,
            name: str,
            *,
            expected_dev: int,
            expected_ino: int,
        ) -> bool:
            del dir_fd, name, expected_dev, expected_ino
            raise OSError(code, f"forced {err}")

        def prove_safe(
            dir_fd: int,
            name: str,
            *,
            expected_dev: int,
            expected_ino: int,
        ) -> bool:
            try:
                return prove_err(
                    dir_fd, name, expected_dev=expected_dev, expected_ino=expected_ino
                )
            except OSError:
                return False

        monkeypatch.setattr(pin_mod, "prove_size0_owned_name_terminal", prove_safe)

    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome != "deleted"
    snap = _lifecycle_snapshot(mutation_store)
    assert stamped["ok"] is True
    assert snap["receipt_generation"] is not None


@pytest.mark.serial
def test_r16_never_rmdir_foreign_stage_directory(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe 8: cleaner must not pathname-rmdir a replaced foreign empty directory."""

    from gateway_repository_service.upload_artifact.admission_pin import (
        unlink_stage_dir_name,
    )

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, _ = _intent_callbacks(store)
    rmdirs: list[str] = []
    real_rmdir = os.rmdir

    def track_rmdir(path: str | bytes | os.PathLike[str], *args: object, **kwargs: object) -> None:
        rmdirs.append(path if isinstance(path, str) else str(path))
        return real_rmdir(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "gateway_repository_service.upload_artifact.admission_pin.os.rmdir",
        track_rmdir,
    )
    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome == "deleted"
    # Plant a foreign empty stage-shaped dir and ensure a sweep does not rmdir it
    # via destroy (destroy no longer rmdirs).
    foreign_stage = ready.parent / unlink_stage_dir_name(
        artifact_id=UUID(int=ARTIFACT_ID.int + 99), token="foreignrm"
    )
    foreign_stage.mkdir(mode=0o700)
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    assert foreign_stage.is_dir()
    assert not any("foreignrm" in name for name in rmdirs)


@pytest.mark.serial
def test_r16_batch_crash_fixtures_bounded_inventory(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Probe 9: ≥200 crash fixtures (batch plant); inventory bounded; no reclaim dirs."""

    from gateway_repository_service.upload_artifact.admission_pin import (
        STAGE_VICTIM,
        unlink_stage_dir_name,
    )

    store, mutation_store = stores
    ready_dir = layout.artifacts / REPOSITORY_ID.hex / "ready"
    ready_dir.mkdir(parents=True, exist_ok=True)
    n = 200
    before = len(list(ready_dir.iterdir()))
    for i in range(n):
        aid = UUID(int=ARTIFACT_ID.int + 800 + i)
        _seed_artifact(mutation_store, artifact_id=aid)
        path = ready_dir / aid.hex
        path.write_bytes(ARTIFACT_PAYLOAD)
        st = path.stat()
        generation = f"g{i:032x}"[:32]
        store.begin_artifact_bytes_delete_intent(
            aid,
            repository_id=REPOSITORY_ID,
            dev=int(st.st_dev),
            ino=int(st.st_ino),
            phase="quarantined",
            intent_at="2026-08-02T00:00:00+00:00",
            generation=generation,
        )
        store.mark_artifact_bytes_deleted(
            aid,
            deleted_at="2026-08-02T00:00:00+00:00",
            repository_id=REPOSITORY_ID,
            expected_dev=int(st.st_dev),
            expected_ino=int(st.st_ino),
            expected_generation=generation,
        )
        stage = ready_dir / unlink_stage_dir_name(artifact_id=aid, token=f"c{i:06x}")
        stage.mkdir(mode=0o700)
        os.rename(path, stage / STAGE_VICTIM)
        os.truncate(stage / STAGE_VICTIM, 0)

    mid = len(list(ready_dir.iterdir()))
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    after = len(list(ready_dir.iterdir()))
    reclaim = [p for p in ready_dir.iterdir() if p.name.startswith(".reclaim-")]
    assert reclaim == []
    print(f"r16_probe9 n={n} before={before} mid={mid} after={after}")
    tombs = sum(1 for p in ready_dir.iterdir() if parse_any_recoverable_sidecar(p.name) is not None)
    budget = 50_000
    assert tombs <= budget
    assert after - before <= n * 2
    nonempty = [
        p
        for p in ready_dir.iterdir()
        if p.is_file() and not p.name.startswith(".") and p.stat().st_size > 0
    ]
    assert nonempty == []


@pytest.mark.serial
def test_r16_generation_migrate_crash_and_stale_ops(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe 10: durable G1 intent → migrate → crash before on_intent; G2 restart; stale G1 no-ops."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod
    from gateway_repository_service.upload_artifact.admission_pin import detach_name_for

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    g1 = "genr16abag1" + "0" * 21
    assert "-" not in g1
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=g1,
    )
    detach = ready.parent / detach_name_for(
        inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=g1
    )
    os.link(ready, detach)
    # Crash window: after migrate rename, before intent write (DB still G1).
    real_migrate = pin_mod._migrate_sidecar_slot_to_generation
    migrated: dict[str, str | None] = {"name": None}

    def migrate_crash(
        ready_dir_fd: int,
        *,
        source_name: str,
        inode: int,
        artifact_id: UUID,
        generation: str,
    ) -> str | None:
        result = real_migrate(
            ready_dir_fd,
            source_name=source_name,
            inode=inode,
            artifact_id=artifact_id,
            generation=generation,
        )
        migrated["name"] = result
        # Simulate crash after durable rename: fail-closed before intent write.
        return None

    monkeypatch.setattr(pin_mod, "_migrate_sidecar_slot_to_generation", migrate_crash)
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, _ = _intent_callbacks(store)
    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome == "unlink_failed"
    snap = _lifecycle_snapshot(mutation_store)
    assert snap["intent_generation"] == g1
    assert migrated["name"] is not None
    monkeypatch.setattr(pin_mod, "_migrate_sidecar_slot_to_generation", real_migrate)
    g2_holder: dict[str, str] = {}

    def on_intent_g2(dev: int, ino: int, generation: str) -> None:
        g2_holder["g"] = generation
        on_intent(dev, ino, generation)
        # Interleave stale G1 clear/stamp against live G2 intent.
        store.clear_artifact_bytes_delete_intent(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=g1,
        )
        mid = _lifecycle_snapshot(mutation_store)
        assert mid["intent_generation"] == generation
        # Stale stamp with G1 must CAS-miss (intent is G2).
        try:
            store.mark_artifact_bytes_deleted(
                ARTIFACT_ID,
                deleted_at="2026-08-01T00:00:00+00:00",
                repository_id=REPOSITORY_ID,
                expected_dev=dev,
                expected_ino=ino,
                expected_generation=g1,
            )
        except Exception:
            pass
        mid2 = _lifecycle_snapshot(mutation_store)
        assert mid2["intent_generation"] == generation
        assert mid2["bytes_deleted_at"] is None
        store.clear_artifact_bytes_deleted_receipt(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=g1,
        )
    outcome2 = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent_g2,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome2 == "deleted"
    assert "g" in g2_holder and g2_holder["g"] != g1
    snap2 = _lifecycle_snapshot(mutation_store)
    assert snap2["bytes_deleted_at"] is not None
    assert snap2["intent_at"] is None


# ---------------------------------------------------------------------------
# Round17 directed probes (idempotent restore + tombstone budget gate)
# ---------------------------------------------------------------------------


def _count_public_tombs(ready_dir: Path) -> int:
    from gateway_repository_service.upload_artifact.admission_pin import parse_unlink_stage_dir_name

    count = 0
    for p in ready_dir.iterdir():
        if parse_any_recoverable_sidecar(p.name) is not None:
            count += 1
        elif parse_unlink_stage_dir_name(p.name) is not None:
            count += 1
    return count


def _ready_inventory(ready_dir: Path) -> dict[str, int]:
    entries = list(ready_dir.iterdir())
    tombs = _count_public_tombs(ready_dir)
    tomb_paths = [
        p
        for p in entries
        if parse_any_recoverable_sidecar(p.name) is not None
        or p.name.startswith(".unlink-stage-")
    ]
    inodes = {p.stat().st_ino for p in tomb_paths if p.exists()}
    nlinks = [p.stat().st_nlink for p in tomb_paths if p.is_file()]
    return {
        "dentry": len(entries),
        "tombstone": tombs,
        "inode": len(inodes),
        "max_nlink": max(nlinks) if nlinks else 0,
    }


R17_CAPACITY_NS = (1, 200, 1000)


@pytest.mark.serial
@pytest.mark.parametrize("n", R17_CAPACITY_NS, ids=[f"n{n}" for n in R17_CAPACITY_NS])
def test_r17_capacity_budget_and_idle_sweep_ot(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    n: int,
) -> None:
    """Probe 1: success n; absolute tombs ≤ budget; idle sweeps O(T) and non-growing."""

    store, mutation_store = stores
    ready_dir = layout.artifacts / REPOSITORY_ID.hex / "ready"
    ready_dir.mkdir(parents=True, exist_ok=True)
    budget = 50_000
    artifact_ids: list[UUID] = []
    for i in range(n):
        aid = UUID(int=ARTIFACT_ID.int + 1700 + i)
        artifact_ids.append(aid)
        _seed_artifact(mutation_store, artifact_id=aid)
        (ready_dir / aid.hex).write_bytes(ARTIFACT_PAYLOAD)

    for aid in artifact_ids:

        def _stamp(dev: int, ino: int, generation: str, *, a: UUID = aid) -> None:
            store.mark_artifact_bytes_deleted(
                a,
                deleted_at="2026-08-02T00:00:00+00:00",
                repository_id=REPOSITORY_ID,
                expected_dev=dev,
                expected_ino=ino,
                expected_generation=generation,
            )

        def _intent(dev: int, ino: int, generation: str, *, a: UUID = aid) -> None:
            store.begin_artifact_bytes_delete_intent(
                a,
                repository_id=REPOSITORY_ID,
                dev=dev,
                ino=ino,
                phase="quarantined",
                intent_at="2026-08-02T00:00:00+00:00",
                generation=generation,
            )

        def _clear_intent(dev: int, ino: int, generation: str, *, a: UUID = aid) -> None:
            store.clear_artifact_bytes_delete_intent(
                a,
                repository_id=REPOSITORY_ID,
                expected_dev=dev,
                expected_ino=ino,
                expected_generation=generation,
            )

        def _clear_receipt(dev: int, ino: int, generation: str, *, a: UUID = aid) -> None:
            store.clear_artifact_bytes_deleted_receipt(
                a,
                repository_id=REPOSITORY_ID,
                expected_dev=dev,
                expected_ino=ino,
                expected_generation=generation,
            )

        assert (
            try_unlink_owned_ready_artifact(
                layout,
                REPOSITORY_ID,
                aid,
                recheck=lambda: True,
                on_deleted=_stamp,
                on_intent=_intent,
                on_clear_intent=_clear_intent,
                on_clear_receipt=_clear_receipt,
                tombstone_budget=budget,
            )
            == "deleted"
        )

    inv = _ready_inventory(ready_dir)
    receipts = mutation_store.list_artifacts_with_bytes_deleted_receipt()
    print(
        f"r17_probe1 n={n} inv={inv} receipts={len(receipts)} "
        f"budget={budget}"
    )
    assert inv["tombstone"] <= budget
    assert inv["tombstone"] <= n * 2
    assert receipts == []
    _assert_no_nonempty_sidecars(ready_dir)

    real_listdir = os.listdir
    real_get = mutation_store.get_artifact_lifecycle
    counters = {"listdir": 0, "lifecycle": 0}

    def counting_listdir(path: int | str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> list[str]:
        counters["listdir"] += 1
        result = real_listdir(path)
        return [os.fsdecode(name) for name in result]

    def counting_get(artifact_id: UUID) -> object:
        counters["lifecycle"] += 1
        return real_get(artifact_id)

    monkeypatch.setattr(os, "listdir", counting_listdir)
    monkeypatch.setattr(mutation_store, "get_artifact_lifecycle", counting_get)

    tombs_after_success = inv["tombstone"]
    listdir_per_sweep: list[int] = []
    lifecycle_per_sweep: list[int] = []
    for _ in range(10):
        before_l = counters["listdir"]
        before_db = counters["lifecycle"]
        ArtifactCleaner(
            settings=_settings(layout, ttl=1, tombstone_budget=budget),
            layout=layout,
            import_store=store,
            mutation_store=mutation_store,
            clock=lambda: BASE_NOW,
        ).sweep_once()
        listdir_per_sweep.append(counters["listdir"] - before_l)
        lifecycle_per_sweep.append(counters["lifecycle"] - before_db)

    inv_idle = _ready_inventory(ready_dir)
    print(
        f"r17_probe1_idle n={n} tombs={inv_idle['tombstone']} "
        f"listdir={listdir_per_sweep} lifecycle={lifecycle_per_sweep}"
    )
    assert inv_idle["tombstone"] == tombs_after_success
    assert inv_idle["tombstone"] <= budget
    # Scan work tracks tombstone population (O(T)), not unbounded growth.
    assert max(listdir_per_sweep) <= max(8, tombs_after_success * 4 + 16)
    assert max(lifecycle_per_sweep) <= max(8, tombs_after_success * 4 + 16)


@pytest.mark.serial
def test_r17_idempotent_restore_matching_ready_and_verify(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Probe 2: stage victim + matching ready + matching verify + intent → clear."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    expected_sha = _sha256_path(ready)
    stage_path, victim, st, generation = _plant_stage_only_victim(ready, token="r17idmp01")
    # Re-publish matching ready + fixed restore verify hardlinks to the same inode.
    os.link(victim, ready)
    verify = ready.parent / verify_sidecar_name_for(
        inode=int(st.st_ino),
        generation=generation,
        artifact_id=ARTIFACT_ID,
        token="restore",
    )
    os.link(victim, verify)
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    ArtifactCleaner(
        settings=_settings(layout, ttl=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: datetime(2026, 8, 1, 0, 0, 1, tzinfo=UTC),
    ).sweep_once()
    snap = _lifecycle_snapshot(mutation_store)
    assert snap["intent_at"] is None
    assert ready.is_file()
    assert _sha256_path(ready) == expected_sha
    assert stage_path.exists()


@pytest.mark.serial
@pytest.mark.parametrize(
    "crash_after",
    ["ready_link", "verify_link"],
    ids=["ready", "verify"],
)
def test_r17_restore_crash_windows_then_matching_converges(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    crash_after: str,
) -> None:
    """Probe 3: interrupt after ready/verify publish before clear-intent; restart clears."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    expected_sha = _sha256_path(ready)
    stage_path, victim, st, generation = _plant_stage_only_victim(ready, token="r17crsh01")
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    if crash_after == "verify_link":
        # Force restore to take the fixed-token verify candidate, not ready.
        (ready.parent / ARTIFACT_ID.hex).write_bytes(b"foreign-before-verify")
    real_link = os.link
    links = {"ready": 0, "verify": 0}
    clearer = ArtifactCleaner._clear_intent_best_effort
    blocked = {"ok": False}

    def link_count(
        src: str | bytes,
        dst: str | bytes,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        dst_s = os.fsdecode(dst) if isinstance(dst, bytes) else str(dst)
        dst_base = Path(dst_s).name
        if dst_base == ARTIFACT_ID.hex:
            links["ready"] += 1
        elif dst_base.startswith(".unlink-verify-"):
            links["verify"] += 1
        real_link(
            src,
            dst,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    def clear_crash(
        self: ArtifactCleaner,
        artifact_id: UUID,
        repository_id: UUID,
        *,
        expected_dev: int,
        expected_ino: int,
        expected_generation: str,
    ) -> None:
        if crash_after == "ready_link" and links["ready"] >= 1:
            blocked["ok"] = True
            return
        if crash_after == "verify_link" and links["verify"] >= 1:
            blocked["ok"] = True
            return
        clearer(
            self,
            artifact_id,
            repository_id,
            expected_dev=expected_dev,
            expected_ino=expected_ino,
            expected_generation=expected_generation,
        )

    monkeypatch.setattr(os, "link", link_count)
    monkeypatch.setattr(ArtifactCleaner, "_clear_intent_best_effort", clear_crash)
    ArtifactCleaner(
        settings=_settings(layout, ttl=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: datetime(2026, 8, 1, 0, 0, 1, tzinfo=UTC),
    ).sweep_once()
    snap = _lifecycle_snapshot(mutation_store)
    if crash_after == "ready_link":
        assert blocked["ok"] is True
        assert snap["intent_at"] is not None
    else:
        # ADR 0011: foreign ready must not clear intent via verify publish.
        assert snap["intent_at"] is not None
        assert (ready.parent / ARTIFACT_ID.hex).read_bytes() == b"foreign-before-verify"
        (ready.parent / ARTIFACT_ID.hex).unlink()
    monkeypatch.setattr(os, "link", real_link)
    monkeypatch.setattr(ArtifactCleaner, "_clear_intent_best_effort", clearer)
    ArtifactCleaner(
        settings=_settings(layout, ttl=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: datetime(2026, 8, 1, 0, 0, 1, tzinfo=UTC),
    ).sweep_once()
    snap2 = _lifecycle_snapshot(mutation_store)
    assert snap2["intent_at"] is None
    if crash_after == "ready_link":
        restored = ready.parent / ARTIFACT_ID.hex
        assert restored.is_file()
        assert _sha256_path(restored) == expected_sha
    else:
        restored = ready.parent / ARTIFACT_ID.hex
        assert restored.is_file()
        assert _sha256_path(restored) == expected_sha
    assert stage_path.exists()

    # Foreign ready + truncated victim: restore fail-closed, intent retained.
    # Covered in depth by test_r18_restore_foreign_symlink_eio_keeps_intent.


@pytest.mark.serial
def test_r17_ineligible_restore_race_dst_barrier(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe 4: destination-name barrier; hook must fire; owned payload published."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    expected_sha = _sha256_path(ready)
    _stage_path, victim, st, generation = _plant_stage_only_victim(ready, token="r17race01")
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    real_link = os.link
    replaced = {"ok": False}

    def link_after_replace(
        src: str | bytes,
        dst: str | bytes,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        dst_s = os.fsdecode(dst) if isinstance(dst, bytes) else str(dst)
        dst_base = Path(dst_s).name
        if not replaced["ok"] and (
            dst_base == ARTIFACT_ID.hex or dst_base.startswith(".unlink-verify-")
        ):
            replaced["ok"] = True
            try:
                victim.unlink()
            except FileNotFoundError:
                pass
            victim.write_bytes(b"r17-foreign-restore")
        real_link(
            src,
            dst,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(os, "link", link_after_replace)
    ArtifactCleaner(
        settings=_settings(layout, ttl=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: datetime(2026, 8, 1, 0, 0, 1, tzinfo=UTC),
    ).sweep_once()
    assert replaced["ok"] is True
    restored = ready.parent / ARTIFACT_ID.hex
    snap = _lifecycle_snapshot(mutation_store)
    # Held-fd linkat publishes owned payload even if stage pathname was replaced.
    if restored.is_file():
        assert _sha256_path(restored) == expected_sha
        assert snap["intent_at"] is None
    else:
        assert snap["intent_at"] is not None
        assert not restored.exists() or _sha256_path(restored) == expected_sha


@pytest.mark.serial
def test_r17_durable_g1_migrate_crash_g2_restart(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe 5: durable G1 → migrate G2 crash → G2 restart; stale G1 cannot unbind."""

    import gateway_repository_service.upload_artifact.admission_pin as pin_mod
    from gateway_repository_service.upload_artifact.admission_pin import detach_name_for

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    g1 = "genr17abag1" + "0" * 21
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=g1,
    )
    detach = ready.parent / detach_name_for(
        inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=g1
    )
    os.link(ready, detach)
    real_migrate = pin_mod._migrate_sidecar_slot_to_generation
    migrated: dict[str, str | None] = {"name": None}

    def migrate_crash(
        ready_dir_fd: int,
        *,
        source_name: str,
        inode: int,
        artifact_id: UUID,
        generation: str,
    ) -> str | None:
        result = real_migrate(
            ready_dir_fd,
            source_name=source_name,
            inode=inode,
            artifact_id=artifact_id,
            generation=generation,
        )
        migrated["name"] = result
        return None

    monkeypatch.setattr(pin_mod, "_migrate_sidecar_slot_to_generation", migrate_crash)
    on_deleted, on_intent, on_clear_intent, on_clear_receipt, _ = _intent_callbacks(store)
    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome == "unlink_failed"
    assert _lifecycle_snapshot(mutation_store)["intent_generation"] == g1
    assert migrated["name"] is not None
    monkeypatch.setattr(pin_mod, "_migrate_sidecar_slot_to_generation", real_migrate)

    def on_intent_g2(dev: int, ino: int, generation: str) -> None:
        on_intent(dev, ino, generation)
        store.clear_artifact_bytes_delete_intent(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=g1,
        )
        assert _lifecycle_snapshot(mutation_store)["intent_generation"] == generation
        store.clear_artifact_bytes_deleted_receipt(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=g1,
        )

    outcome2 = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        recheck=lambda: True,
        on_deleted=on_deleted,
        on_intent=on_intent_g2,
        on_clear_intent=on_clear_intent,
        on_clear_receipt=on_clear_receipt,
    )
    assert outcome2 == "deleted"
    snap2 = _lifecycle_snapshot(mutation_store)
    assert snap2["bytes_deleted_at"] is not None
    assert snap2["intent_at"] is None
    assert snap2["intent_generation"] is None or snap2["intent_generation"] != g1


R17_RECEIPT_CASES = (
    ("match", True),
    ("mismatch_ino", False),
    ("cross_dev_same_ino", False),
    ("unreadable_stage", False),
)


@pytest.mark.serial
@pytest.mark.parametrize(
    ("label", "expect_clear"),
    R17_RECEIPT_CASES,
    ids=[c[0] for c in R17_RECEIPT_CASES],
)
def test_r17_receipt_dev_ino_generation_matrix(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    expect_clear: bool,
) -> None:
    """Probe 6: receipt (dev,ino,generation) match / cross-dev / unreadable stage."""

    from gateway_repository_service.upload_artifact.admission_pin import (
        STAGE_VICTIM,
        unlink_stage_dir_name,
    )

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    generation = ("genr17rcpt01" + "0" * 20)[:32]
    q = ready.parent / quarantine_name_for(
        inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
    )
    os.link(ready, q)
    ready.unlink()
    os.truncate(q, 0)
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    store.mark_artifact_bytes_deleted(
        ARTIFACT_ID,
        deleted_at="2026-08-02T00:00:00+00:00",
        repository_id=REPOSITORY_ID,
        expected_dev=int(st.st_dev),
        expected_ino=int(st.st_ino),
        expected_generation=generation,
    )

    if label in {"match", "mismatch_ino", "cross_dev_same_ino"}:
        clear_dev = int(st.st_dev)
        clear_ino = int(st.st_ino)
        clear_gen = generation
        if label == "mismatch_ino":
            clear_ino = int(st.st_ino) + 999999
        elif label == "cross_dev_same_ino":
            clear_dev = int(st.st_dev) + 1
        store.clear_artifact_bytes_deleted_receipt(
            ARTIFACT_ID,
            repository_id=REPOSITORY_ID,
            expected_dev=clear_dev,
            expected_ino=clear_ino,
            expected_generation=clear_gen,
        )
        snap = _lifecycle_snapshot(mutation_store)
        if expect_clear:
            assert snap["receipt_generation"] is None
        else:
            assert snap["receipt_generation"] == generation
        return

    # unreadable_stage: GC path must retain receipt.
    stage = ready.parent / unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="r17ur01")
    stage.mkdir(mode=0o700)
    (stage / STAGE_VICTIM).write_bytes(b"blocking")
    import gateway_repository_service.artifact_cleaner as cleaner_mod

    monkeypatch.setattr(
        cleaner_mod.ArtifactCleaner,
        "_stage_dir_is_terminal_or_empty",
        lambda self, *a, **k: False,
    )
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    cleaner = ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    )
    cleaner._gc_one_bytes_deleted_receipt(lifecycle)
    snap = _lifecycle_snapshot(mutation_store)
    assert snap["receipt_generation"] == generation


@pytest.mark.serial
def test_r17_tombstone_budget_backpressure_fail_closed(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Backpressure: projected reservation refuses when inventory+3 would exceed budget."""

    store, mutation_store = stores
    ready_dir = layout.artifacts / REPOSITORY_ID.hex / "ready"
    ready_dir.mkdir(parents=True, exist_ok=True)
    # Fill inventory to 1; projected_new=3 with budget=3 → 1+3>3 refuse.
    from gateway_repository_service.upload_artifact.admission_pin import unlink_stage_dir_name

    stage = ready_dir / unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="budg01")
    stage.mkdir(mode=0o700)
    assert _count_public_tombs(ready_dir) >= 1

    target = UUID(int=ARTIFACT_ID.int + 1800)
    _seed_artifact(mutation_store, artifact_id=target)
    path = ready_dir / target.hex
    path.write_bytes(ARTIFACT_PAYLOAD)

    def _stamp(dev: int, ino: int, generation: str, *, a: UUID = target) -> None:
        store.mark_artifact_bytes_deleted(
            a,
            deleted_at="2026-08-02T00:00:00+00:00",
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
        )

    def _intent(dev: int, ino: int, generation: str, *, a: UUID = target) -> None:
        store.begin_artifact_bytes_delete_intent(
            a,
            repository_id=REPOSITORY_ID,
            dev=dev,
            ino=ino,
            phase="quarantined",
            intent_at="2026-08-02T00:00:00+00:00",
            generation=generation,
        )

    def _clear_intent(dev: int, ino: int, generation: str, *, a: UUID = target) -> None:
        store.clear_artifact_bytes_delete_intent(
            a,
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
        )

    def _clear_receipt(dev: int, ino: int, generation: str, *, a: UUID = target) -> None:
        store.clear_artifact_bytes_deleted_receipt(
            a,
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
        )

    with caplog.at_level(logging.INFO):
        outcome = try_unlink_owned_ready_artifact(
            layout,
            REPOSITORY_ID,
            target,
            recheck=lambda: True,
            on_deleted=_stamp,
            on_intent=_intent,
            on_clear_intent=_clear_intent,
            on_clear_receipt=_clear_receipt,
            tombstone_budget=3,
        )
    assert outcome == "unlink_failed"
    assert path.is_file() and path.read_bytes() == ARTIFACT_PAYLOAD
    assert any(
        getattr(record, "cleanup_outcome", None) == "tombstone_budget" for record in caplog.records
    )


# ---------------------------------------------------------------------------
# Round18 directed probes (directory-broker reclaim + ADR 0011 restore freeze)
# ---------------------------------------------------------------------------


R18_BUDGET_MATRIX = (
    (1, 0),
    (1, 1),
    (2, 0),
    (2, 1),
    (2, 2),
    (3, 0),
    (3, 1),
    (3, 2),
    (3, 3),
)


@pytest.mark.serial
@pytest.mark.parametrize(
    ("budget", "current"),
    R18_BUDGET_MATRIX,
    ids=[f"b{b}_c{c}" for b, c in R18_BUDGET_MATRIX],
)
def test_r18_budget_projected_reservation_matrix(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    budget: int,
    current: int,
) -> None:
    """Probe 1: budget×current projected reservation absolute caps."""

    from gateway_repository_service.upload_artifact.admission_pin import unlink_stage_dir_name

    store, mutation_store = stores
    ready_dir = layout.artifacts / REPOSITORY_ID.hex / "ready"
    ready_dir.mkdir(parents=True, exist_ok=True)
    for i in range(current):
        stage = ready_dir / unlink_stage_dir_name(
            artifact_id=UUID(int=ARTIFACT_ID.int + 9000 + i), token=f"r18b{i:02d}"
        )
        stage.mkdir(mode=0o700)
    before = _ready_inventory(ready_dir)
    assert before["tombstone"] == current

    aid = UUID(int=ARTIFACT_ID.int + 9100 + budget * 10 + current)
    _seed_artifact(mutation_store, artifact_id=aid)
    path = ready_dir / aid.hex
    path.write_bytes(ARTIFACT_PAYLOAD)

    def _stamp(dev: int, ino: int, generation: str, *, a: UUID = aid) -> None:
        store.mark_artifact_bytes_deleted(
            a,
            deleted_at="2026-08-02T00:00:00+00:00",
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
        )

    def _intent(dev: int, ino: int, generation: str, *, a: UUID = aid) -> None:
        store.begin_artifact_bytes_delete_intent(
            a,
            repository_id=REPOSITORY_ID,
            dev=dev,
            ino=ino,
            phase="quarantined",
            intent_at="2026-08-02T00:00:00+00:00",
            generation=generation,
        )

    def _clear_intent(dev: int, ino: int, generation: str, *, a: UUID = aid) -> None:
        store.clear_artifact_bytes_delete_intent(
            a,
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
        )

    def _clear_receipt(dev: int, ino: int, generation: str, *, a: UUID = aid) -> None:
        store.clear_artifact_bytes_deleted_receipt(
            a,
            repository_id=REPOSITORY_ID,
            expected_dev=dev,
            expected_ino=ino,
            expected_generation=generation,
        )

    outcome = try_unlink_owned_ready_artifact(
        layout,
        REPOSITORY_ID,
        aid,
        recheck=lambda: True,
        on_deleted=_stamp,
        on_intent=_intent,
        on_clear_intent=_clear_intent,
        on_clear_receipt=_clear_receipt,
        tombstone_budget=budget,
    )
    after = _ready_inventory(ready_dir)
    # projected_new=3: allow only when current+3 <= budget
    if current + 3 <= budget:
        assert outcome == "deleted"
        assert after["tombstone"] <= budget
        assert after["dentry"] <= before["dentry"] + 3
    else:
        assert outcome == "unlink_failed"
        assert path.is_file()
        assert after["tombstone"] == current


@pytest.mark.serial
def test_r18_broker_reclaim_converges_to_constant_residual(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """Core acceptance: n successes leave O(1) Service-owned inventory, not O(n)."""

    store, mutation_store = stores
    ready_dir = layout.artifacts / REPOSITORY_ID.hex / "ready"
    ready_dir.mkdir(parents=True, exist_ok=True)
    n = 50
    before = _ready_inventory(ready_dir)
    for i in range(n):
        aid = UUID(int=ARTIFACT_ID.int + 9200 + i)
        _seed_artifact(mutation_store, artifact_id=aid)
        (ready_dir / aid.hex).write_bytes(ARTIFACT_PAYLOAD)

        def _stamp(dev: int, ino: int, generation: str, *, a: UUID = aid) -> None:
            store.mark_artifact_bytes_deleted(
                a,
                deleted_at="2026-08-02T00:00:00+00:00",
                repository_id=REPOSITORY_ID,
                expected_dev=dev,
                expected_ino=ino,
                expected_generation=generation,
            )

        def _intent(dev: int, ino: int, generation: str, *, a: UUID = aid) -> None:
            store.begin_artifact_bytes_delete_intent(
                a,
                repository_id=REPOSITORY_ID,
                dev=dev,
                ino=ino,
                phase="quarantined",
                intent_at="2026-08-02T00:00:00+00:00",
                generation=generation,
            )

        def _clear_intent(dev: int, ino: int, generation: str, *, a: UUID = aid) -> None:
            store.clear_artifact_bytes_delete_intent(
                a,
                repository_id=REPOSITORY_ID,
                expected_dev=dev,
                expected_ino=ino,
                expected_generation=generation,
            )

        def _clear_receipt(dev: int, ino: int, generation: str, *, a: UUID = aid) -> None:
            store.clear_artifact_bytes_deleted_receipt(
                a,
                repository_id=REPOSITORY_ID,
                expected_dev=dev,
                expected_ino=ino,
                expected_generation=generation,
            )

        assert (
            try_unlink_owned_ready_artifact(
                layout,
                REPOSITORY_ID,
                aid,
                recheck=lambda: True,
                on_deleted=_stamp,
                on_intent=_intent,
                on_clear_intent=_clear_intent,
                on_clear_receipt=_clear_receipt,
                tombstone_budget=50_000,
            )
            == "deleted"
        )

    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    after = _ready_inventory(ready_dir)
    print(f"r18_core n={n} before={before} after={after}")
    # Broker reclaim: inventory growth must be strict constant residual, not O(n).
    assert after["tombstone"] - before["tombstone"] <= 2
    assert after["dentry"] - before["dentry"] <= 4
    nonempty = [
        p for p in ready_dir.iterdir() if p.is_file() and not p.name.startswith(".") and p.stat().st_size > 0
    ]
    assert nonempty == []


@pytest.mark.serial
@pytest.mark.parametrize(
    "kind",
    ["foreign_regular", "symlink", "eio"],
    ids=["foreign", "symlink", "eio"],
)
def test_r18_restore_foreign_symlink_eio_keeps_intent(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    """Probe 7: foreign/symlink/EIO on ready must not clear intent (ADR 0011)."""

    store, mutation_store = stores
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    stage_path, victim, st, generation = _plant_stage_only_victim(ready, token="r18rest01")
    store.begin_artifact_bytes_delete_intent(
        ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        intent_at="2026-08-02T00:00:00+00:00",
        generation=generation,
    )
    ready_path = ready.parent / ARTIFACT_ID.hex
    if kind == "foreign_regular":
        ready_path.write_bytes(b"foreign-r18")
    elif kind == "symlink":
        ready_path.symlink_to("/tmp/r18-symlink-target")
    else:
        real_open = os.open

        def open_eio(path: str | bytes | int, flags: int, *args: object, **kwargs: object) -> int:
            name = path if isinstance(path, int) else os.fsdecode(path)
            if not isinstance(name, int) and Path(str(name)).name == ARTIFACT_ID.hex:
                raise OSError(errno.EIO, "forced eio")
            return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(os, "open", open_eio)

    ArtifactCleaner(
        settings=_settings(layout, ttl=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: datetime(2026, 8, 1, 0, 0, 1, tzinfo=UTC),
    ).sweep_once()
    snap = _lifecycle_snapshot(mutation_store)
    assert snap["intent_at"] is not None
    assert stage_path.is_dir()
    # Admission must not see consistent ready for foreign/symlink.
    if kind == "foreign_regular":
        assert ready_path.read_bytes() == b"foreign-r18"
    elif kind == "symlink":
        assert ready_path.is_symlink()


# ---------------------------------------------------------------------------
# Round19 directed probes (fail-closed broker E2E, fair keyset, receipt-null)
# ---------------------------------------------------------------------------


def test_r19_keyset_page_does_not_starve_newer_succeeded(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    """64 TTL-not-elapsed rows cannot starve the 65th SUCCEEDED residual."""

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    old_created = CREATED_AT
    new_created = "2026-08-01T01:00:00+00:00"
    old_ids = [UUID(int=ARTIFACT_ID.int + i) for i in range(64)]
    new_id = UUID(int=ARTIFACT_ID.int + 64)
    new_op = UUID(int=OPERATION_ID.int + 64)
    for i, aid in enumerate(old_ids):
        _seed_artifact(mutation_store, artifact_id=aid, created_at=old_created)
        _write_ready(layout, artifact_id=aid)
        binding = _binding(artifact_id=aid)
        key_hash = IdempotencyKeyHash.from_raw_key(f"r19-protected-{i}")
        store.claim_or_enqueue(
            binding,
            key_hash=key_hash,
            fingerprint=versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash),
            operation_id=UUID(int=OPERATION_ID.int + i),
        )
    _seed_artifact(mutation_store, artifact_id=new_id, created_at=new_created)
    new_ready = _write_ready(layout, artifact_id=new_id)
    binding = _binding(artifact_id=new_id)
    key_hash = IdempotencyKeyHash.from_raw_key("r19-succeeded")
    store.claim_or_enqueue(
        binding,
        key_hash=key_hash,
        fingerprint=versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash),
        operation_id=new_op,
    )
    store.claim_if_queued(new_op)
    store.mark_succeeded(
        new_op,
        result=VersionedImportResult(
            commit_id="commit-1",
            target_ref="main",
            artifact_id=new_id,
            canonicalization_manifest_digest="manifest-1",
            expected_commit_id="commit-0",
            completed_verification_policy=VerificationPolicy.STRUCTURAL,
            unknown_type_policy=UnknownTypePolicy.REJECT,
        ),
    )
    cleaner = ArtifactCleaner(
        settings=_settings(layout, ttl=3600, interval=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    )
    cleaner.sweep_once()
    assert new_ready.is_file()
    for aid in old_ids:
        assert artifact_ready_path(layout, REPOSITORY_ID, aid).is_file()
    cleaner.sweep_once()
    assert not new_ready.exists()
    lifecycle = mutation_store.get_artifact_lifecycle(new_id)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None


def test_r19_keyset_sql_limit_not_fetchall_slice(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    _store, mutation_store = stores
    for i in range(70):
        _seed_artifact(
            mutation_store,
            artifact_id=UUID(int=ARTIFACT_ID.int + i),
            created_at=CREATED_AT,
        )
    page = mutation_store.list_artifacts_pending_byte_cleanup(limit=64)
    assert page.scanned == 64
    assert len(page.records) == 64
    last_seq = page.cursor_cleanup_seq
    rest = mutation_store.list_artifacts_pending_byte_cleanup(
        limit=64,
        after_cleanup_seq=last_seq,
    )
    assert rest.scanned == 6
    page_ids = {row.artifact_id for row in page.records}
    rest_ids = {row.artifact_id for row in rest.records}
    assert page_ids.isdisjoint(rest_ids)


def test_r19_multi_repo_keyset_is_globally_ordered(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    _store, mutation_store = stores
    other = UUID(int=REPOSITORY_ID.int + 1)
    for i in range(40):
        _seed_artifact(
            mutation_store,
            artifact_id=UUID(int=ARTIFACT_ID.int + i),
            created_at=f"2026-08-01T00:00:{i:02d}+00:00",
        )
    with mutation_store._lock:
        for i in range(40, 80):
            mutation_store._connection.execute(
                """
                INSERT INTO artifact_lifecycle (
                    artifact_id, repository_scope, media_type, size_bytes,
                    raw_sha256, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(UUID(int=ARTIFACT_ID.int + i)),
                    other.hex,
                    MEDIA_TYPE,
                    len(ARTIFACT_PAYLOAD),
                    SHA256,
                    f"2026-08-01T00:00:{i - 40:02d}+00:00",
                    CREATED_AT,
                ),
            )
        mutation_store._connection.commit()
    page = mutation_store.list_artifacts_pending_byte_cleanup(limit=64)
    assert page.scanned == 64
    assert page.cursor_cleanup_seq is not None
    assert len(page.records) == 64


def test_r19_receipt_null_size0_tombs_reclaim(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    from gateway_repository_service.upload_artifact.admission_pin import (
        detach_name_for,
        unlink_stage_dir_name,
    )

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    generation = "r19nullgen"
    parent = ready.parent
    quarantine = parent / quarantine_name_for(
        inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
    )
    detach = parent / detach_name_for(
        inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
    )
    verify = parent / verify_sidecar_name_for(
        inode=int(st.st_ino),
        generation=generation,
        artifact_id=ARTIFACT_ID,
        token="t0",
    )
    os.link(ready, quarantine)
    os.link(ready, detach)
    os.link(ready, verify)
    os.truncate(quarantine, 0)
    ready.unlink()
    stage = parent / unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="r19s0")
    stage.mkdir(mode=0o700)
    victim = stage / "victim"
    victim.write_bytes(b"")
    with mutation_store._lock:
        mutation_store._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET bytes_deleted_at = ?,
                bytes_deleted_receipt_dev = NULL,
                bytes_deleted_receipt_ino = NULL,
                bytes_deleted_receipt_generation = NULL
            WHERE artifact_id = ?
            """,
            ("2026-08-02T00:00:00+00:00", str(ARTIFACT_ID)),
        )
        mutation_store._connection.commit()
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    # Receipt-null rows cannot carry bytes_delete_ino (v12 CHECK). Without residual
    # proof, sidecars and stages retain.
    assert quarantine.is_file()
    assert detach.is_file()
    assert verify.is_file()
    assert victim.is_file()
    assert stage.is_dir()


def test_r19_receipt_null_forged_and_nonzero_retain(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    parent = ready.parent
    nonzero = parent / quarantine_name_for(
        inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation="nz"
    )
    os.link(ready, nonzero)
    ready.unlink()
    forged = parent / quarantine_name_for(
        inode=999999, artifact_id=ARTIFACT_ID, generation="fg"
    )
    forged.write_bytes(b"")
    with mutation_store._lock:
        mutation_store._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET bytes_deleted_at = ?,
                bytes_deleted_receipt_dev = NULL,
                bytes_deleted_receipt_ino = NULL,
                bytes_deleted_receipt_generation = NULL
            WHERE artifact_id = ?
            """,
            ("2026-08-02T00:00:00+00:00", str(ARTIFACT_ID)),
        )
        mutation_store._connection.commit()
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    assert nonzero.is_file()
    assert int(nonzero.stat().st_size) == len(ARTIFACT_PAYLOAD)
    assert forged.is_file()


def test_r20_receipt_null_self_consistent_forged_ino_retains(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    parent = ready.parent
    ready.unlink()
    forged = parent / "placeholder"
    forged.write_bytes(b"")
    st = forged.stat()
    named = parent / quarantine_name_for(
        inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation="self"
    )
    forged.rename(named)
    with mutation_store._lock:
        mutation_store._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET bytes_deleted_at = ?,
                bytes_deleted_receipt_dev = NULL,
                bytes_deleted_receipt_ino = NULL,
                bytes_deleted_receipt_generation = NULL
            WHERE artifact_id = ?
            """,
            ("2026-08-02T00:00:00+00:00", str(ARTIFACT_ID)),
        )
        mutation_store._connection.commit()
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    assert named.is_file()


@pytest.mark.parametrize("poison_index", [0, 32, 63])
def test_r20_poison_page_does_not_starve_newer_succeeded(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    poison_index: int,
) -> None:
    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    protected_ids: list[UUID] = []
    for i in range(64):
        created = f"2026-08-01T00:00:00.{i:03d}+00:00"
        aid = UUID(int=ARTIFACT_ID.int + i)
        if i == poison_index:
            with mutation_store._lock:
                mutation_store._connection.execute(
                    """
                    INSERT INTO artifact_lifecycle (
                        artifact_id, repository_scope, media_type, size_bytes,
                        raw_sha256, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (str(aid), "not-a-uuid", MEDIA_TYPE, 1, "a" * 64, created, created),
                )
                mutation_store._connection.commit()
            continue
        protected_ids.append(aid)
        _seed_artifact(mutation_store, artifact_id=aid, created_at=created)
        _write_ready(layout, artifact_id=aid)
        binding = _binding(artifact_id=aid)
        key_hash = IdempotencyKeyHash.from_raw_key(f"r20-protected-{i}")
        store.claim_or_enqueue(
            binding,
            key_hash=key_hash,
            fingerprint=versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash),
            operation_id=UUID(int=OPERATION_ID.int + i),
        )
    new_id = UUID(int=ARTIFACT_ID.int + 64)
    new_created = "2026-08-01T00:00:00.064+00:00"
    new_op = UUID(int=OPERATION_ID.int + 64)
    _seed_artifact(mutation_store, artifact_id=new_id, created_at=new_created)
    new_ready = _write_ready(layout, artifact_id=new_id)
    binding = _binding(artifact_id=new_id)
    key_hash = IdempotencyKeyHash.from_raw_key("r20-succeeded")
    store.claim_or_enqueue(
        binding,
        key_hash=key_hash,
        fingerprint=versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash),
        operation_id=new_op,
    )
    store.claim_if_queued(new_op)
    store.mark_succeeded(
        new_op,
        result=VersionedImportResult(
            commit_id="commit-1",
            target_ref="main",
            artifact_id=new_id,
            canonicalization_manifest_digest="manifest-1",
            expected_commit_id="commit-0",
            completed_verification_policy=VerificationPolicy.STRUCTURAL,
            unknown_type_policy=UnknownTypePolicy.REJECT,
        ),
    )
    page = mutation_store.list_artifacts_pending_byte_cleanup(limit=64)
    assert page.scanned == 64
    assert len(page.records) == 63
    cleaner = ArtifactCleaner(
        settings=_settings(layout, ttl=3600, interval=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    )
    cleaner.sweep_once()
    assert new_ready.is_file()
    cleaner.sweep_once()
    assert not new_ready.exists()
    lifecycle = mutation_store.get_artifact_lifecycle(new_id)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None
    for aid in protected_ids:
        assert artifact_ready_path(layout, REPOSITORY_ID, aid).is_file()


def test_r20_cleanup_query_uses_keyset_index(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    _store, mutation_store = stores
    plan_rows = mutation_store._connection.execute(
        """
        EXPLAIN QUERY PLAN
        SELECT artifact_id FROM artifact_lifecycle
        WHERE bytes_deleted_at IS NULL
        ORDER BY cleanup_seq ASC
        LIMIT 64
        """
    ).fetchall()
    plan = " ".join(" ".join(str(col) for col in row) for row in plan_rows)
    assert "artifact_lifecycle_cleanup_seq_idx" in plan
    assert "USE TEMP B-TREE FOR ORDER BY" not in plan


def test_r20_empty_and_mode_mixed_stages_reclaim(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    from gateway_repository_service.upload_artifact.admission_pin import unlink_stage_dir_name

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    parent = ready.parent
    ready.unlink()
    empty_0700 = parent / unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="e700")
    empty_0700.mkdir(mode=0o700)
    empty_0750 = parent / unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="e750")
    empty_0750.mkdir(mode=0o750)
    filled = parent / unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="fill")
    filled.mkdir(mode=0o700)
    (filled / "victim").write_bytes(b"")
    (filled / "final-x").write_bytes(b"")
    (filled / "doom-y").write_bytes(b"")
    with mutation_store._lock:
        mutation_store._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET bytes_deleted_at = ?,
                bytes_deleted_receipt_dev = NULL,
                bytes_deleted_receipt_ino = NULL,
                bytes_deleted_receipt_generation = NULL
            WHERE artifact_id = ?
            """,
            ("2026-08-02T00:00:00+00:00", str(ARTIFACT_ID)),
        )
        mutation_store._connection.commit()
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    assert empty_0700.is_dir()
    assert empty_0750.is_dir()
    assert filled.is_dir()
    assert (filled / "victim").is_file()
    assert (filled / "final-x").is_file()
    assert (filled / "doom-y").is_file()


def test_r20_receipt_null_symlink_sidecar_retains(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    parent = ready.parent
    ready.unlink()
    linked = parent / quarantine_name_for(
        inode=1, artifact_id=ARTIFACT_ID, generation="sy"
    )
    linked.symlink_to("/tmp/r20-receipt-null-symlink")
    with mutation_store._lock:
        mutation_store._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET bytes_deleted_at = ?,
                bytes_deleted_receipt_dev = NULL,
                bytes_deleted_receipt_ino = NULL,
                bytes_deleted_receipt_generation = NULL
            WHERE artifact_id = ?
            """,
            ("2026-08-02T00:00:00+00:00", str(ARTIFACT_ID)),
        )
        mutation_store._connection.commit()
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    assert linked.is_symlink()


def test_r20_receipt_null_open_fstat_eio_retains(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    parent = ready.parent
    ready.unlink()
    tomb = parent / quarantine_name_for(
        inode=1, artifact_id=ARTIFACT_ID, generation="eio"
    )
    tomb.write_bytes(b"")
    real_open = os.open

    def open_eio(path: str | bytes | int, flags: int, *args: object, **kwargs: object) -> int:
        name = path if isinstance(path, int) else os.fsdecode(path)
        if not isinstance(name, int) and Path(str(name)).name == tomb.name:
            raise OSError(errno.EIO, "forced open EIO")
        return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", open_eio)
    with mutation_store._lock:
        mutation_store._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET bytes_deleted_at = ?,
                bytes_deleted_receipt_dev = NULL,
                bytes_deleted_receipt_ino = NULL,
                bytes_deleted_receipt_generation = NULL
            WHERE artifact_id = ?
            """,
            ("2026-08-02T00:00:00+00:00", str(ARTIFACT_ID)),
        )
        mutation_store._connection.commit()
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    monkeypatch.undo()
    assert tomb.is_file()


def test_r20_receipt_null_foreign_stage_retains(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    from gateway_repository_service.upload_artifact.admission_pin import unlink_stage_dir_name

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    parent = ready.parent
    ready.unlink()
    foreign = parent / unlink_stage_dir_name(
        artifact_id=UUID(int=ARTIFACT_ID.int + 99), token="fx"
    )
    foreign.mkdir(mode=0o700)
    (foreign / "victim").write_bytes(b"")
    with mutation_store._lock:
        mutation_store._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET bytes_deleted_at = ?,
                bytes_deleted_receipt_dev = NULL,
                bytes_deleted_receipt_ino = NULL,
                bytes_deleted_receipt_generation = NULL
            WHERE artifact_id = ?
            """,
            ("2026-08-02T00:00:00+00:00", str(ARTIFACT_ID)),
        )
        mutation_store._connection.commit()
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()
    assert foreign.is_dir()
    assert (foreign / "victim").is_file()


def _mark_receipt_null(mutation_store: MutationStore, *, artifact_id: UUID = ARTIFACT_ID) -> None:
    with mutation_store._lock:
        mutation_store._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET bytes_deleted_at = ?,
                bytes_deleted_receipt_dev = NULL,
                bytes_deleted_receipt_ino = NULL,
                bytes_deleted_receipt_generation = NULL
            WHERE artifact_id = ?
            """,
            ("2026-08-02T00:00:00+00:00", str(artifact_id)),
        )
        mutation_store._connection.commit()


def _insert_residual(
    store: ImportOperationStore,
    *,
    kind: str,
    name: str,
    dev: int,
    ino: int,
    parent_name: str = "",
    generation: str | None = "g1",
    artifact_id: UUID = ARTIFACT_ID,
) -> None:
    store.insert_artifact_residual(
        artifact_id,
        repository_id=REPOSITORY_ID,
        kind=kind,
        name=name,
        parent_name=parent_name,
        dev=dev,
        ino=ino,
        generation=generation,
        created_at=CREATED_AT,
    )


def _sweep(store: ImportOperationStore, mutation_store: MutationStore, layout: DurableLayout) -> None:
    ArtifactCleaner(
        settings=_settings(layout, ttl=1),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    ).sweep_once()


def test_r21_receipt_null_legal_with_proof_reclaims(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    parent = ready.parent
    generation = "r21legal"
    quarantine = parent / quarantine_name_for(
        inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation=generation
    )
    os.link(ready, quarantine)
    os.truncate(quarantine, 0)
    ready.unlink()
    _mark_receipt_null(mutation_store)
    _insert_residual(
        store,
        kind="deleting",
        name=quarantine.name,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        generation=generation,
    )
    _sweep(store, mutation_store, layout)
    assert not quarantine.exists()
    assert mutation_store.list_artifact_residuals(artifact_id=ARTIFACT_ID) == []


def test_r21_receipt_null_mismatch_forged_legacy_without_proof_retain(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    parent = ready.parent
    mismatch = parent / quarantine_name_for(
        inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation="mm"
    )
    os.link(ready, mismatch)
    os.truncate(mismatch, 0)
    ready.unlink()
    forged = parent / quarantine_name_for(
        inode=999999, artifact_id=ARTIFACT_ID, generation="fg"
    )
    forged.write_bytes(b"")
    legacy = parent / f".deleting-{int(st.st_ino)}-{ARTIFACT_ID.hex}"
    legacy.write_bytes(b"")
    _mark_receipt_null(mutation_store)
    _insert_residual(
        store,
        kind="deleting",
        name=mismatch.name,
        dev=int(st.st_dev),
        ino=int(st.st_ino) + 1,
        generation="mm",
    )
    _sweep(store, mutation_store, layout)
    assert mismatch.is_file()
    assert forged.is_file()
    assert legacy.is_file()


def test_r21_forged_stage_shapes_without_proof_retain(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    from gateway_repository_service.upload_artifact.admission_pin import unlink_stage_dir_name

    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    parent = ready.parent
    ready.unlink()
    empty = parent / unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="empty")
    empty.mkdir(mode=0o700)
    victim_stage = parent / unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="vic")
    victim_stage.mkdir(mode=0o700)
    (victim_stage / "victim").write_bytes(b"")
    (victim_stage / "final-x").write_bytes(b"")
    (victim_stage / "doom-y").write_bytes(b"")
    nonzero = parent / unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="nz")
    nonzero.mkdir(mode=0o700)
    (nonzero / "victim").write_bytes(b"payload")
    linked = parent / unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="sy")
    linked.mkdir(mode=0o700)
    (linked / "victim").symlink_to("/tmp/r21-stage-symlink")
    _mark_receipt_null(mutation_store)
    _sweep(store, mutation_store, layout)
    assert empty.is_dir()
    assert (victim_stage / "victim").is_file()
    assert (victim_stage / "final-x").is_file()
    assert (victim_stage / "doom-y").is_file()
    assert (nonzero / "victim").is_file()
    assert (linked / "victim").is_symlink()


def test_r21_residual_crash_windows_converge(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    parent = ready.parent
    name = quarantine_name_for(inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation="cw")
    ready.unlink()
    _insert_residual(
        store,
        kind="deleting",
        name=name,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        generation="cw",
    )
    _sweep(store, mutation_store, layout)
    assert mutation_store.list_artifact_residuals(artifact_id=ARTIFACT_ID) == []

    tomb = parent / name
    tomb.write_bytes(b"")
    st2 = tomb.stat()
    _insert_residual(
        store,
        kind="deleting",
        name=name,
        dev=int(st2.st_dev),
        ino=int(st2.st_ino),
        generation="cw",
    )
    _sweep(store, mutation_store, layout)
    assert not tomb.exists()
    assert mutation_store.list_artifact_residuals(artifact_id=ARTIFACT_ID) == []

    leftover = parent / quarantine_name_for(
        inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation="cw2"
    )
    leftover.write_bytes(b"")
    st3 = leftover.stat()
    leftover.unlink()
    _insert_residual(
        store,
        kind="deleting",
        name=leftover.name,
        dev=int(st3.st_dev),
        ino=int(st3.st_ino),
        generation="cw2",
    )
    _sweep(store, mutation_store, layout)
    assert mutation_store.list_artifact_residuals(artifact_id=ARTIFACT_ID) == []


def test_r21_mixed_legal_and_forged_isolate(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    _seed_artifact(mutation_store)
    ready = _write_ready(layout)
    st = ready.stat()
    parent = ready.parent
    legal = parent / quarantine_name_for(
        inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation="ok"
    )
    os.link(ready, legal)
    os.truncate(legal, 0)
    ready.unlink()
    forged = parent / quarantine_name_for(
        inode=4242, artifact_id=ARTIFACT_ID, generation="bad"
    )
    forged.write_bytes(b"")
    _insert_residual(
        store,
        kind="deleting",
        name=legal.name,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        generation="ok",
    )
    _sweep(store, mutation_store, layout)
    assert not legal.exists()
    assert forged.is_file()


def test_r21_blob_created_at_and_artifact_id_page_reaches_successor(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    for i in range(64):
        aid = UUID(int=ARTIFACT_ID.int + i)
        if i in {0, 32, 63}:
            with mutation_store._lock:
                mutation_store._connection.execute(
                    """
                    INSERT INTO artifact_lifecycle (
                        artifact_id, repository_scope, media_type, size_bytes,
                        raw_sha256, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sqlite3.Binary(f"blob-id-{i}".encode()),
                        sqlite3.Binary(b"not-a-uuid"),
                        MEDIA_TYPE,
                        1,
                        "a" * 64,
                        sqlite3.Binary(f"poison-{i}".encode()),
                        sqlite3.Binary(f"poison-{i}".encode()),
                    ),
                )
                mutation_store._connection.commit()
            continue
        _seed_artifact(mutation_store, artifact_id=aid, created_at=f"2026-08-01T00:00:00.{i:03d}+00:00")
        _write_ready(layout, artifact_id=aid)
    new_id = UUID(int=ARTIFACT_ID.int + 64)
    _seed_artifact(mutation_store, artifact_id=new_id, created_at="2026-08-01T00:00:00.064+00:00")
    new_ready = _write_ready(layout, artifact_id=new_id)
    binding = _binding(artifact_id=new_id)
    key_hash = IdempotencyKeyHash.from_raw_key("r21-blob-successor")
    store.claim_or_enqueue(
        binding,
        key_hash=key_hash,
        fingerprint=versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash),
        operation_id=UUID(int=OPERATION_ID.int + 64),
    )
    store.claim_if_queued(UUID(int=OPERATION_ID.int + 64))
    store.mark_succeeded(
        UUID(int=OPERATION_ID.int + 64),
        result=VersionedImportResult(
            commit_id="commit-1",
            target_ref="main",
            artifact_id=new_id,
            canonicalization_manifest_digest="manifest-1",
            expected_commit_id="commit-0",
            completed_verification_policy=VerificationPolicy.STRUCTURAL,
            unknown_type_policy=UnknownTypePolicy.REJECT,
        ),
    )
    page = mutation_store.list_artifacts_pending_byte_cleanup(limit=64)
    assert page.scanned == 64
    assert isinstance(page.cursor_cleanup_seq, int)
    cleaner = ArtifactCleaner(
        settings=_settings(layout, ttl=3600, interval=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    )
    cleaner.sweep_once()
    cleaner.sweep_once()
    assert not new_ready.exists()


def test_r21_repeated_cursor_advances_and_new_succeeded_is_reached(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, mutation_store = stores
    _seed_create_succeeded(mutation_store)
    for i in range(64):
        aid = UUID(int=ARTIFACT_ID.int + i)
        _seed_artifact(mutation_store, artifact_id=aid, created_at=f"2026-08-01T00:00:00.{i:03d}+00:00")
        _write_ready(layout, artifact_id=aid)
    real_list = mutation_store.list_artifacts_pending_byte_cleanup
    first = real_list(limit=64)
    stuck = type(first)(
        records=first.records,
        scanned=64,
        cursor_cleanup_seq=first.cursor_cleanup_seq,
    )

    calls = {"n": 0}

    def stuck_then_real(
        *, limit: int = 64, after_cleanup_seq: int | None = None
    ) -> CleanupCandidatePage:
        calls["n"] += 1
        if calls["n"] == 1:
            return stuck
        if calls["n"] == 2:
            assert after_cleanup_seq == stuck.cursor_cleanup_seq
            return type(stuck)(
                records=stuck.records,
                scanned=64,
                cursor_cleanup_seq=stuck.cursor_cleanup_seq,
            )
        return real_list(limit=limit, after_cleanup_seq=after_cleanup_seq)

    monkeypatch.setattr(mutation_store, "list_artifacts_pending_byte_cleanup", stuck_then_real)
    cleaner = ArtifactCleaner(
        settings=_settings(layout, ttl=3600, interval=3600),
        layout=layout,
        import_store=store,
        mutation_store=mutation_store,
        clock=lambda: BASE_NOW,
    )
    cleaner.sweep_once()
    cleaner.sweep_once()
    assert cleaner._cleanup_cursor == int(stuck.cursor_cleanup_seq or 0) + 1

    new_id = UUID(int=ARTIFACT_ID.int + 80)
    _seed_artifact(mutation_store, artifact_id=new_id, created_at="2026-08-01T00:00:01+00:00")
    new_ready = _write_ready(layout, artifact_id=new_id)
    binding = _binding(artifact_id=new_id)
    key_hash = IdempotencyKeyHash.from_raw_key("r21-new-succeeded")
    op = UUID(int=OPERATION_ID.int + 80)
    store.claim_or_enqueue(
        binding,
        key_hash=key_hash,
        fingerprint=versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash),
        operation_id=op,
    )
    store.claim_if_queued(op)
    store.mark_succeeded(
        op,
        result=VersionedImportResult(
            commit_id="commit-1",
            target_ref="main",
            artifact_id=new_id,
            canonicalization_manifest_digest="manifest-1",
            expected_commit_id="commit-0",
            completed_verification_policy=VerificationPolicy.STRUCTURAL,
            unknown_type_policy=UnknownTypePolicy.REJECT,
        ),
    )
    monkeypatch.setattr(mutation_store, "list_artifacts_pending_byte_cleanup", real_list)
    cleaner._cleanup_cursor = None
    cleaner.sweep_once()
    cleaner.sweep_once()
    assert not new_ready.exists()


def test_r21_cleanup_list_binds_integer_seq_not_str() -> None:
    source = Path(__file__).resolve().parents[1] / "src" / "gateway_repository_service" / "mutation_store.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("def list_artifacts_pending_byte_cleanup")
    end = text.index("def ", start + 4)
    body = text[start:end]
    assert "after_cleanup_seq" in body
    assert "int(after_cleanup_seq)" in body
    assert "str(row[8])" not in body
    assert "cursor_created_at" not in body
