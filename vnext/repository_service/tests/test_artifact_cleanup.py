"""Artifact retention, admission-pin cleanup, and cleaner lifecycle tests."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

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
    try_unlink_ready_artifact_with_recheck,
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
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.admission_pin import ArtifactAdmissionPin
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import import versioned_import_fingerprint_v1
from gateway_repository_service.versioned_import.models import (
    ArtifactOperationReference,
    ImportRequestBinding,
    IMPORT_ADMISSION_PENDING_STATUS,
)
from gateway_repository_service.versioned_import.store import ImportOperationStore
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
BASE_NOW = datetime(2026, 8, 2, tzinfo=UTC)

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
    decision = decide_artifact_bytes_deletion(
        lifecycle=_lifecycle(),
        references=[
            ArtifactOperationReference(
                operation_id=OPERATION_ID,
                durable_status=OperationStatus.SUCCEEDED.value,
                status=OperationStatus.SUCCEEDED,
                is_protected=False,
                completed_at="2026-08-02T00:00:00+00:00",
            )
        ],
        now=BASE_NOW,
        ttl_seconds=86400,
    )
    assert decision.eligible is True
    assert decision.reason is ArtifactBytesDeletionReason.SUCCEEDED_IMMEDIATE


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
        ),
        ArtifactOperationReference(
            operation_id=OTHER_OPERATION_ID,
            durable_status=OperationStatus.FAILED.value,
            status=OperationStatus.FAILED,
            is_protected=False,
            completed_at=later,
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

    def flaky(path: Path, *, recheck: object) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "unlink_failed"
        return original(path, recheck=recheck)  # type: ignore[arg-type]

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


def test_already_absent_records_bytes_deleted_at(
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
    assert lifecycle.bytes_deleted_at is not None


def test_symlink_and_malformed_paths_are_not_deleted(layout: DurableLayout, tmp_path: Path) -> None:
    ready = artifact_ready_path(layout, REPOSITORY_ID, ARTIFACT_ID)
    ready.parent.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "target.bin"
    target.write_bytes(ARTIFACT_PAYLOAD)
    ready.symlink_to(target)
    assert classify_ready_artifact_path(ready, expected=ready) == "symlink"

    malformed = ready.parent / "not-a-uuid"
    malformed.write_bytes(b"x")
    assert classify_ready_artifact_path(malformed, expected=ready) == "unexpected_path"


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
    with mutation_store._lock:
        mutation_store._connection.execute(
            "UPDATE artifact_lifecycle SET bytes_deleted_at = ? WHERE artifact_id = ?",
            ("2026-08-02T00:00:00+00:00", str(ARTIFACT_ID)),
        )
        mutation_store._connection.commit()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert retention_explains_missing_ready_bytes(
        lifecycle=lifecycle,
        repository_id=REPOSITORY_ID,
        references=[],
    )
    assert upload_artifact_bytes_reconciled_after_import(
        store,
        mutation_store,
        REPOSITORY_ID,
        ARTIFACT_ID,
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
    )
    assert failures
    assert any("missing" in item for item in failures)


@pytest.mark.integration
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

        lifecycle = runtime.mutation_store.get_artifact_lifecycle(artifact_id)
        assert lifecycle is not None
        created = datetime.fromisoformat(lifecycle.created_at or CREATED_AT)
        cleaner = runtime.artifact_cleaner
        assert isinstance(cleaner, ArtifactCleaner)
        setattr(cleaner, "_clock", lambda: created + timedelta(seconds=2))
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
