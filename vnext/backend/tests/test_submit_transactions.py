"""T1/T3 submit transaction matrix tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType

import pytest

from gateway_backend.application.job_definitions import JobDefinition, JobDefinitionRegistry, NormalPublicationCapability
from gateway_backend.application.recovery import RecoveryCapability
from gateway_backend.application.submission.accept_transaction import (
    AcceptSubmitPreflight,
    accept_submit_transaction,
    deterministic_submit_attempt_id,
    deterministic_submit_operation_id,
)
from gateway_backend.application.submission.abort_transaction import (
    AbortSubmitTransactionRequest,
    AbortSubmitTransactionResult,
    abort_submit_transaction,
)
from gateway_backend.application.submission.contracts import (
    SUBMIT_JOB_CONTRACT_VERSION,
    AcceptSubmitCommand,
    FinalizeSubmitResult,
    MatchingAbortProof,
    MatchingFinalizeFacts,
    RepositoryOperationTerminalStatus,
    SubmitAcceptanceRecord,
    compute_new_accept_fingerprint,
)
from gateway_backend.application.submission.errors import (
    BaselineVersionConflict,
    FinalizeRecoveryRequired,
    IdempotencyConflict,
    NoCanonicalChange,
    PreviewBindingConflict,
    SubmitOccupancyConflict,
)
from gateway_backend.application.submission.finalize_transaction import (
    FinalizeSubmitTransactionRequest,
    finalize_submit_transaction,
)
from gateway_backend.application.submission.job_payload import SUBMIT_JOB_KIND, SUBMIT_STEP_AWAIT, SUBMIT_STEP_PREPARE, SUBMIT_STEP_SUBMIT
from gateway_backend.application.submission.ports import SubmitControlUnitOfWorkFactory
from gateway_backend.application.workspace.services import create_or_get_workspace
from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.submission.errors import SubmitAttemptVersionConflict
from gateway_backend.domain.submission.models import (
    BackendArtifactRef,
    BuilderMutationPolicy,
    RepositoryArtifactRef,
    SubmitAttempt,
    SubmitAttemptState,
    SubmitTargetRef,
    SubmitUnknownTypePolicy,
    SubmitVerificationPolicy,
)
from gateway_backend.domain.workspace.errors import ScopeForbidden, WorkspaceVersionConflict
from gateway_backend.domain.workspace.models import (
    BaselineHead,
    InputCompleteness,
    PreviewResult,
    PreviewResultDigests,
    SourceArtifactBinding,
    SourceArtifactRole,
    UploadRevision,
    Workspace,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, initialize_control_db
from gateway_backend.infrastructure.control_db.sqlite_mapping import seed_provisioned_mappings
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    JobStepKey,
    OperationDiagnostic,
    OperationStatus,
    StaleWrite,
    StepRecord,
    StepStatus,
    WritePrecondition,
)
from tests.support.workspace_fixtures import FixedScopeResolutionPort, make_baseline_head, make_identity

pytestmark = pytest.mark.unit

TS0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
TS1 = datetime(2024, 6, 1, 12, 30, 0, tzinfo=UTC)
BASELINE_HEAD = make_baseline_head(version=3, commit_id="commit-base")
BASELINE_CANONICAL_DIGEST = "sha256:baseline-canonical"
SNAPSHOT_TABLE_ARTIFACT_REFS = ("snap-1",)
PREVIEW_READY_CLOSURE_DIGEST = "d-closure"
SNAPSHOT_TABLE_SET_DIGEST = "sha256:snapshot-set"
_SHA_INITIAL = "sha256:" + "a" * 64
_SHA_MODIFIED = "sha256:" + "b" * 64
_SHA_CLOSURE = "sha256:" + "c" * 64
_SHA_SNAP = "sha256:" + "d" * 64
_SHA_PACKAGE = "sha256:" + "e" * 64
_SHA_MANIFEST = "sha256:" + "f" * 64
_SHA_REPO = "sha256:" + "9" * 64


@dataclass
class WriterLockTracker:
    writer_open: bool = False
    writer_entries: int = 0
    active_uow_entries: int = 0
    factory_calls: tuple[bool, ...] = ()


class TrackingUnitOfWork:
    def __init__(
        self,
        inner: ControlDbUnitOfWork,
        tracker: WriterLockTracker,
        *,
        read_only: bool,
    ) -> None:
        self._inner = inner
        self._tracker = tracker
        self._read_only = read_only

    def __enter__(self) -> ControlDbUnitOfWork:
        self._tracker.active_uow_entries += 1
        if not self._read_only:
            self._tracker.writer_entries += 1
            self._tracker.writer_open = True
        return self._inner.__enter__()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            self._inner.__exit__(exc_type, exc, tb)
        finally:
            self._tracker.active_uow_entries -= 1
            self._tracker.writer_open = False


def _uow_factory(db_path: Path) -> SubmitControlUnitOfWorkFactory:
    def factory(*, read_only: bool = False) -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(db_path, read_only=read_only)

    return factory


def _tracking_uow_factory(db_path: Path, tracker: WriterLockTracker) -> SubmitControlUnitOfWorkFactory:
    def factory(*, read_only: bool = False) -> TrackingUnitOfWork:
        tracker.factory_calls = (*tracker.factory_calls, read_only)
        return TrackingUnitOfWork(
            ControlDbUnitOfWork(db_path, read_only=read_only),
            tracker,
            read_only=read_only,
        )

    return factory


@dataclass
class FakeBaselineCanonicalDigestPort:
    digest: str = BASELINE_CANONICAL_DIGEST
    tracker: WriterLockTracker | None = None
    calls: int = 0
    writer_open_during_calls: tuple[bool, ...] = ()
    uow_active_during_calls: tuple[bool, ...] = ()
    fail_with: BaseException | None = None

    def get_baseline_canonical_digest(self, *, repository_id: str, baseline_head: object) -> str:
        del repository_id, baseline_head
        self.calls += 1
        writer_open = False if self.tracker is None else self.tracker.writer_open
        uow_active = False if self.tracker is None else self.tracker.active_uow_entries > 0
        self.writer_open_during_calls = (*self.writer_open_during_calls, writer_open)
        self.uow_active_during_calls = (*self.uow_active_during_calls, uow_active)
        if self.fail_with is not None:
            raise self.fail_with
        return self.digest


@dataclass
class RecordingMainResolvePort:
    commit_id: str = "commit-main"
    tracker: WriterLockTracker | None = None
    calls: int = 0
    writer_open_during_calls: tuple[bool, ...] = ()
    uow_active_during_calls: tuple[bool, ...] = ()

    def resolve_main_expected_commit(self, *, repository_id: str) -> str:
        del repository_id
        self.calls += 1
        writer_open = False if self.tracker is None else self.tracker.writer_open
        uow_active = False if self.tracker is None else self.tracker.active_uow_entries > 0
        self.writer_open_during_calls = (*self.writer_open_during_calls, writer_open)
        self.uow_active_during_calls = (*self.uow_active_during_calls, uow_active)
        return self.commit_id


@dataclass
class FakeAbortEvidencePort:
    tracker: WriterLockTracker | None = None
    calls: int = 0
    writer_open_during_calls: tuple[bool, ...] = ()

    def validate_matching_stable_failure(self, *, attempt: SubmitAttempt, proof: MatchingAbortProof) -> None:
        del attempt, proof
        self.calls += 1
        writer_open = False if self.tracker is None else self.tracker.writer_open
        self.writer_open_during_calls = (*self.writer_open_during_calls, writer_open)


@dataclass
class SubmitSeed:
    db_path: Path
    workspace: Workspace
    upload_revision: UploadRevision
    preview_result: PreviewResult
    preview_operation_id: str
    protected_refs: tuple[ArtifactRef, ...]


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "control.db"
    initialize_control_db(path)
    return path


def _seed_provisioned_mapping(
    db_path: Path,
    *,
    device_key: str = "device-1",
    project_id: str = "project-1",
    repository_id: str = "repo-1",
    baseline_head: BaselineHead = BASELINE_HEAD,
    enabled: bool = True,
) -> None:
    mapping_file = db_path.parent / "provisioned-mapping.json"
    mapping_file.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "gateway_device_external_key": device_key,
                        "business_project_id": project_id,
                        "repository_id": repository_id,
                        "business_baseline_node_id": baseline_head.business_baseline_node_id,
                        "business_baseline_commit_id": baseline_head.business_baseline_commit_id,
                        "baseline_head_version": baseline_head.baseline_head_version,
                        "enabled": enabled,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    seed_provisioned_mappings(db_path, mapping_file)


def _upsert_provisioned_mapping_row(
    db_path: Path,
    *,
    device_key: str = "device-1",
    project_id: str = "project-1",
    repository_id: str = "repo-1",
    baseline_head: BaselineHead = BASELINE_HEAD,
    enabled: bool = True,
) -> None:
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.connection.execute(
            """
            INSERT INTO provisioned_scope_mappings (
                gateway_device_external_key,
                business_project_id,
                repository_id,
                business_baseline_node_id,
                business_baseline_commit_id,
                baseline_head_version,
                enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(gateway_device_external_key, business_project_id) DO UPDATE SET
                repository_id = excluded.repository_id,
                business_baseline_node_id = excluded.business_baseline_node_id,
                business_baseline_commit_id = excluded.business_baseline_commit_id,
                baseline_head_version = excluded.baseline_head_version,
                enabled = excluded.enabled
            """,
            (
                device_key,
                project_id,
                repository_id,
                baseline_head.business_baseline_node_id,
                baseline_head.business_baseline_commit_id,
                baseline_head.baseline_head_version,
                1 if enabled else 0,
            ),
        )


def _assert_t1_zero_writes(db_path: Path, seed: SubmitSeed, *, idempotency_key: str) -> None:
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        workspace = unit_of_work.workspace.get_workspace(seed.workspace.workspace_id)
        assert workspace is not None
        assert workspace.optimistic_version == seed.workspace.optimistic_version
        assert (
            unit_of_work.submission.find_submit_idempotency(
                seed.workspace.workspace_id,
                idempotency_key,
            )
            is None
        )
        assert unit_of_work.submission.get_workspace_occupancy(seed.workspace.workspace_id) is None
        assert unit_of_work.submission.get_repository_occupancy(seed.workspace.repository_id) is None
        assert unit_of_work.connection.execute("SELECT COUNT(*) FROM submit_attempt_records").fetchone()[0] == 0


def _submit_job_registry() -> JobDefinitionRegistry:
    definitions = (
        JobDefinition(
            key=JobStepKey(job_kind=SUBMIT_JOB_KIND, step_name=SUBMIT_STEP_PREPARE),
            supported_payload_versions=frozenset({SUBMIT_JOB_CONTRACT_VERSION}),
            decoder_identity="backend-vnext/submit/prepare-import/decoder/v1",
            handler_identity="backend-vnext/submit/prepare-import/handler/v1",
            publication_capability=NormalPublicationCapability.SINGLE_SUCCESSOR,
            recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
        ),
        JobDefinition(
            key=JobStepKey(job_kind=SUBMIT_JOB_KIND, step_name=SUBMIT_STEP_SUBMIT),
            supported_payload_versions=frozenset({SUBMIT_JOB_CONTRACT_VERSION}),
            decoder_identity="backend-vnext/submit/submit-import/decoder/v1",
            handler_identity="backend-vnext/submit/submit-import/handler/v1",
            publication_capability=NormalPublicationCapability.SINGLE_SUCCESSOR,
            recovery_capability=RecoveryCapability.EXTERNAL_EFFECT,
        ),
        JobDefinition(
            key=JobStepKey(job_kind=SUBMIT_JOB_KIND, step_name=SUBMIT_STEP_AWAIT),
            supported_payload_versions=frozenset({SUBMIT_JOB_CONTRACT_VERSION}),
            decoder_identity="backend-vnext/submit/await-import-result/decoder/v1",
            handler_identity="backend-vnext/submit/await-import-result/handler/v1",
            publication_capability=NormalPublicationCapability.TERMINAL,
            recovery_capability=RecoveryCapability.EXTERNAL_EFFECT,
        ),
    )
    return JobDefinitionRegistry.build(definitions)


def _preview_result(workspace_id: str) -> PreviewResult:
    return PreviewResult(
        preview_result_id="pr-1",
        workspace_id=workspace_id,
        upload_revision_id="ur-1",
        generation=1,
        repository_id="repo-1",
        business_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        business_baseline_commit_id=BASELINE_HEAD.business_baseline_commit_id,
        baseline_head_version=BASELINE_HEAD.baseline_head_version,
        ruleset_version="rules-1",
        contract_version="contract-1",
        provider_versions={"comparison": "v1"},
        digests=PreviewResultDigests(
            source_digest="d-source",
            input_digest="d-input",
            snapshot_digest="d-snapshot",
            comparison_digest="d-comparison",
            risk_digest="d-risk",
            surface_digest="d-surface",
            bundle_digest="sha256:preview-canonical",
        ),
        bundle_artifact_id="bundle-1",
        ready_closure_artifact_id="closure-1",
        operation_id="op-preview-1",
        created_at=TS1,
    )


def _protected_preview_refs() -> tuple[ArtifactRef, ...]:
    return (
        ArtifactRef(
            artifact_id="initial-1",
            media_type="application/gzip",
            size_bytes=1,
            raw_sha256=DigestRef(_SHA_INITIAL),
        ),
        ArtifactRef(
            artifact_id="modified-1",
            media_type="application/gzip",
            size_bytes=2,
            raw_sha256=DigestRef(_SHA_MODIFIED),
        ),
        ArtifactRef(
            artifact_id="closure-1",
            media_type="application/json",
            size_bytes=1,
            raw_sha256=DigestRef(_SHA_CLOSURE),
        ),
        ArtifactRef(
            artifact_id="snap-1",
            media_type="application/octet-stream",
            size_bytes=1,
            raw_sha256=DigestRef(_SHA_SNAP),
        ),
    )


def seed_submit_ready_workspace(
    db_path: Path,
    *,
    repository_id: str = "repo-1",
) -> SubmitSeed:
    _seed_provisioned_mapping(db_path, repository_id=repository_id)
    scope_resolution = FixedScopeResolutionPort(
        repository_id=repository_id,
        baseline_head=BASELINE_HEAD,
    )
    context = make_identity(permissions=frozenset({"upload_submit_workspace", "workspace_read"}))
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        created = create_or_get_workspace(
            context=context,
            scope_resolution=scope_resolution,
            repository=unit_of_work.workspace,
            created_at=TS0,
        )
        workspace = created.workspace
        upload_revision = UploadRevision(
            upload_revision_id="ur-1",
            workspace_id=workspace.workspace_id,
            generation=1,
            input_completeness=InputCompleteness.FULL,
            source_artifacts={
                SourceArtifactRole.INITIAL: SourceArtifactBinding(
                    artifact_id="initial-1",
                    media_type="application/gzip",
                    size_bytes=1,
                    raw_sha256="sha256:initial",
                ),
                SourceArtifactRole.MODIFIED: SourceArtifactBinding(
                    artifact_id="modified-1",
                    media_type="application/gzip",
                    size_bytes=2,
                    raw_sha256="sha256:modified",
                ),
            },
            idempotency_key="upload-key",
            request_fingerprint="fp-upload",
            created_by="actor-1",
            created_at=TS0,
        )
        preview = _preview_result(workspace.workspace_id)
        preview = replace(preview, repository_id=repository_id)
        unit_of_work.workspace.save_upload_revision(upload_revision)
        unit_of_work.workspace.save_preview_result(preview)
        updated_workspace = replace(
            workspace,
            repository_id=repository_id,
            generation=1,
            optimistic_version=workspace.optimistic_version + 1,
            current_upload_revision_id=upload_revision.upload_revision_id,
            current_preview_result_id=preview.preview_result_id,
            updated_at=TS1,
        )
        unit_of_work.workspace.save_workspace(
            updated_workspace,
            expected_version=workspace.optimistic_version,
        )
        preview_operation_id = "op-preview-1"
        protected_refs = _protected_preview_refs()
        unit_of_work.set_artifact_protection(
            protected_refs,
            owner_kind="current-preview",
            owner_id=updated_workspace.workspace_id,
            intent="current-preview",
        )
        unit_of_work.set_artifact_protection(
            protected_refs[:2],
            owner_kind="preview-operation",
            owner_id=preview_operation_id,
            intent="preview-operation",
        )
    return SubmitSeed(
        db_path=db_path,
        workspace=updated_workspace,
        upload_revision=upload_revision,
        preview_result=preview,
        preview_operation_id=preview_operation_id,
        protected_refs=protected_refs,
    )


def _accept_command(seed: SubmitSeed, *, idempotency_key: str) -> AcceptSubmitCommand:
    return AcceptSubmitCommand(
        context=make_identity(
            actor_id=seed.workspace.owner_actor_id,
            device_key=seed.workspace.gateway_device_external_key,
            project_id=seed.workspace.business_project_id,
            permissions=frozenset({"upload_submit_workspace", "workspace_read"}),
        ),
        workspace_id=seed.workspace.workspace_id,
        expected_workspace_version=seed.workspace.optimistic_version,
        upload_revision_id=seed.upload_revision.upload_revision_id,
        preview_result_id=seed.preview_result.preview_result_id,
        generation=seed.preview_result.generation,
        expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
        idempotency_key=idempotency_key,
        options={},
    )


def _preflight(seed: SubmitSeed) -> AcceptSubmitPreflight:
    return AcceptSubmitPreflight(
        snapshot_table_artifact_refs=SNAPSHOT_TABLE_ARTIFACT_REFS,
        preview_ready_closure_digest=PREVIEW_READY_CLOSURE_DIGEST,
        preview_operation_id=seed.preview_operation_id,
        protected_artifact_refs=seed.protected_refs,
        snapshot_table_set_digest=SNAPSHOT_TABLE_SET_DIGEST,
    )


def test_t1_accept_persists_attempt_operation_and_occupancy(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    result = accept_submit_transaction(
        command=_accept_command(seed, idempotency_key="accept-key-1"),
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        baseline_digest=FakeBaselineCanonicalDigestPort(),
        main_resolve=RecordingMainResolvePort(),
        preflight=_preflight(seed),
        now=TS1,
    )
    assert result.replay is False

    with ControlDbUnitOfWork(seed.db_path, read_only=True) as unit_of_work:
        attempt = unit_of_work.submission.get_submit_attempt(result.submit_attempt_id)
        workspace_occupancy = unit_of_work.submission.get_workspace_occupancy(seed.workspace.workspace_id)
        repository_occupancy = unit_of_work.submission.get_repository_occupancy(seed.workspace.repository_id)
        operation = unit_of_work.operations.get_operation(result.operation_id)
        workspace = unit_of_work.workspace.get_workspace(seed.workspace.workspace_id)

    assert attempt is not None
    assert attempt.state is SubmitAttemptState.PREPARED
    assert workspace_occupancy is not None
    assert workspace_occupancy.active_submit_attempt_id == result.submit_attempt_id
    assert repository_occupancy is not None
    assert repository_occupancy.submit_attempt_id == result.submit_attempt_id
    assert operation.status is OperationStatus.QUEUED
    assert workspace is not None
    assert workspace.optimistic_version == seed.workspace.optimistic_version + 1


def test_t1_accept_replay_returns_existing_attempt(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    command = _accept_command(seed, idempotency_key="accept-key-1")
    first = accept_submit_transaction(
        command=command,
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        baseline_digest=FakeBaselineCanonicalDigestPort(),
        main_resolve=RecordingMainResolvePort(),
        preflight=_preflight(seed),
        now=TS1,
    )
    replay = accept_submit_transaction(
        command=command,
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        baseline_digest=FakeBaselineCanonicalDigestPort(),
        main_resolve=RecordingMainResolvePort(),
        preflight=_preflight(seed),
        now=TS1,
    )
    assert replay.replay is True
    assert replay.submit_attempt_id == first.submit_attempt_id
    assert replay.operation_id == first.operation_id


def test_t1_accept_rolls_back_when_late_write_fails(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed = seed_submit_ready_workspace(db_path)

    def fail_insert_repository_occupancy(self, occupancy):  # type: ignore[no-untyped-def]
        raise RuntimeError("synthetic occupancy failure")

    monkeypatch.setattr(
        "gateway_backend.infrastructure.control_db.sqlite_submission.SQLiteSubmissionRepository.insert_repository_occupancy",
        fail_insert_repository_occupancy,
    )

    with pytest.raises(RuntimeError, match="synthetic occupancy failure"):
        accept_submit_transaction(
            command=_accept_command(seed, idempotency_key="accept-key-1"),
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(seed.db_path),
            job_registry=_submit_job_registry(),
            baseline_digest=FakeBaselineCanonicalDigestPort(),
            main_resolve=RecordingMainResolvePort(),
            preflight=_preflight(seed),
            now=TS1,
        )

    with ControlDbUnitOfWork(seed.db_path, read_only=True) as unit_of_work:
        attempt_id = deterministic_submit_attempt_id(
            workspace_id=seed.workspace.workspace_id,
            idempotency_key="accept-key-1",
        )
        operation_id = deterministic_submit_operation_id(
            workspace_id=seed.workspace.workspace_id,
            idempotency_key="accept-key-1",
        )
        workspace = unit_of_work.workspace.get_workspace(seed.workspace.workspace_id)
        assert unit_of_work.submission.find_submit_idempotency(seed.workspace.workspace_id, "accept-key-1") is None
        assert unit_of_work.submission.get_submit_attempt(attempt_id) is None
        assert unit_of_work.submission.get_workspace_occupancy(seed.workspace.workspace_id) is None
        assert unit_of_work.submission.get_repository_occupancy(seed.workspace.repository_id) is None
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="submit-attempt",
            owner_id=attempt_id,
        ) == frozenset()
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="current-preview",
            owner_id=seed.workspace.workspace_id,
        ) == frozenset(ref.artifact_id for ref in seed.protected_refs)
        assert workspace is not None
        assert workspace.optimistic_version == seed.workspace.optimistic_version
        assert unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM operation_records WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()[0] == 0
        assert unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM step_records WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()[0] == 0


def test_t1_rejects_conflicting_idempotency_fingerprint(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    command = _accept_command(seed, idempotency_key="accept-key-1")
    fingerprint = compute_new_accept_fingerprint(
        command=command,
        workspace=seed.workspace,
        preview_result=seed.preview_result,
        upload_revision=seed.upload_revision,
        baseline_head=BASELINE_HEAD,
        repository_expected_commit_id="commit-main",
        snapshot_table_artifact_refs=SNAPSHOT_TABLE_ARTIFACT_REFS,
        preview_ready_closure_digest=PREVIEW_READY_CLOSURE_DIGEST,
    )
    with ControlDbUnitOfWork(seed.db_path) as unit_of_work:
        attempt = SubmitAttempt(
            submit_attempt_id="sa-existing",
            workspace_id=seed.workspace.workspace_id,
            workspace_generation=seed.workspace.generation,
            upload_revision_id=seed.upload_revision.upload_revision_id,
            preview_result_id=seed.preview_result.preview_result_id,
            repository_id=seed.workspace.repository_id,
            business_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
            business_baseline_commit_id=BASELINE_HEAD.business_baseline_commit_id,
            baseline_head_version=BASELINE_HEAD.baseline_head_version,
            repository_expected_commit_id="commit-main",
            canonical_business_digest=seed.preview_result.digests.bundle_digest,
            source_digest=seed.preview_result.digests.source_digest,
            snapshot_digest=seed.preview_result.digests.snapshot_digest,
            source_artifact_refs=("initial-1", "modified-1"),
            snapshot_table_artifact_refs=SNAPSHOT_TABLE_ARTIFACT_REFS,
            preview_ready_closure_ref=seed.preview_result.ready_closure_artifact_id,
            preview_ready_closure_digest=PREVIEW_READY_CLOSURE_DIGEST,
            canonicalization_manifest_ref=None,
            canonicalization_manifest_digest=None,
            repository_import_artifact_ref=None,
            repository_artifact_ref=None,
            repository_operation_id=None,
            repository_operation_evidence=None,
            requested_target_ref=SubmitTargetRef.MAIN,
            requested_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
            requested_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
            builder_mutation_policy=BuilderMutationPolicy.REBUILD_ALWAYS,
            accept_idempotency_key="accept-key-1",
            accept_request_fingerprint=fingerprint,
            repository_upload_idempotency_key="p5b-upload-v1:abc",
            repository_import_idempotency_key="p5b-import-v1:abc",
            operation_id="op-existing",
            state=SubmitAttemptState.PREPARED,
            submission_id=None,
            optimistic_version=0,
            created_by="actor-1",
            created_at=TS0,
        )
        unit_of_work.connection.execute(
            """
            INSERT INTO operation_records (
                operation_id, contract_version, optimistic_version, job_kind, job_contract_version,
                job_payload, job_payload_ref, business_refs, artifact_refs, repository_operation_id,
                checkpoint_ref, ready_closure_ref, status, diagnostic, cancel_requested,
                created_at_us, updated_at_us, completed_at_us
            ) VALUES (?, ?, 0, 'backend-vnext/submit', ?, ?, NULL, ?, ?, NULL, NULL, NULL, 'QUEUED', NULL, 0, ?, ?, NULL)
            """,
            (
                "op-existing",
                OPERATION_RUNTIME_CONTRACT_VERSION,
                SUBMIT_JOB_CONTRACT_VERSION,
                b"{}",
                b"[]",
                b"[]",
                1,
                1,
            ),
        )
        unit_of_work.submission.insert_attempt_prepared(attempt)
        unit_of_work.submission.insert_idempotency(
            SubmitAcceptanceRecord(
                workspace_id=seed.workspace.workspace_id,
                idempotency_key="accept-key-1",
                request_fingerprint="sha256:tampered",
                submit_attempt_id="sa-existing",
            )
        )

    with pytest.raises(IdempotencyConflict):
        accept_submit_transaction(
            command=command,
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(seed.db_path),
            job_registry=_submit_job_registry(),
            baseline_digest=FakeBaselineCanonicalDigestPort(),
            main_resolve=RecordingMainResolvePort(),
            preflight=_preflight(seed),
            now=TS1,
        )


def test_t1_repository_occupancy_conflict_blocks_second_workspace(db_path: Path) -> None:
    first_seed = seed_submit_ready_workspace(db_path)
    accept_submit_transaction(
        command=_accept_command(first_seed, idempotency_key="accept-key-1"),
        scope_resolution=FixedScopeResolutionPort(
            repository_id=first_seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(first_seed.db_path),
        job_registry=_submit_job_registry(),
        baseline_digest=FakeBaselineCanonicalDigestPort(),
        main_resolve=RecordingMainResolvePort(),
        preflight=_preflight(first_seed),
        now=TS1,
    )

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        workspace = Workspace(
            workspace_id="ws-2",
            owner_actor_id="actor-2",
            gateway_device_external_key="device-2",
            business_project_id="project-2",
            repository_id="repo-1",
            state=first_seed.workspace.state,
            generation=1,
            optimistic_version=0,
            current_upload_revision_id="ur-2",
            current_preview_result_id="pr-2",
            created_at=TS0,
            updated_at=TS0,
        )
        unit_of_work.workspace.save_workspace(workspace, expected_version=0)
        upload_revision = replace(first_seed.upload_revision, upload_revision_id="ur-2", workspace_id="ws-2")
        preview = replace(
            first_seed.preview_result,
            preview_result_id="pr-2",
            workspace_id="ws-2",
            upload_revision_id="ur-2",
            operation_id="op-preview-2",
        )
        unit_of_work.workspace.save_upload_revision(upload_revision)
        unit_of_work.workspace.save_preview_result(preview)
        updated = replace(
            workspace,
            optimistic_version=1,
            current_upload_revision_id="ur-2",
            current_preview_result_id="pr-2",
            updated_at=TS1,
        )
        unit_of_work.workspace.save_workspace(updated, expected_version=0)
        unit_of_work.set_artifact_protection(
            first_seed.protected_refs,
            owner_kind="current-preview",
            owner_id="ws-2",
            intent="current-preview",
        )

    second_seed = SubmitSeed(
        db_path=db_path,
        workspace=updated,
        upload_revision=upload_revision,
        preview_result=preview,
        preview_operation_id="op-preview-2",
        protected_refs=first_seed.protected_refs,
    )
    with pytest.raises(SubmitOccupancyConflict):
        accept_submit_transaction(
            command=_accept_command(second_seed, idempotency_key="accept-key-2"),
            scope_resolution=FixedScopeResolutionPort(
                repository_id="repo-1",
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(db_path),
            job_registry=_submit_job_registry(),
            baseline_digest=FakeBaselineCanonicalDigestPort(),
            main_resolve=RecordingMainResolvePort(),
            preflight=_preflight(second_seed),
            now=TS1,
        )


def _seed_effect_pending_attempt(db_path: Path, seed: SubmitSeed) -> SubmitAttempt:
    accepted = accept_submit_transaction(
        command=_accept_command(seed, idempotency_key="accept-key-1"),
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        baseline_digest=FakeBaselineCanonicalDigestPort(),
        main_resolve=RecordingMainResolvePort(),
        preflight=_preflight(seed),
        now=TS1,
    )
    backend_ref = BackendArtifactRef(
        artifact_id="backend-pkg-1",
        media_type="application/vnd.gateway.repository-import.v1+tar+zstd",
        size_bytes=10,
        raw_sha256=_SHA_PACKAGE,
    )
    repository_ref = RepositoryArtifactRef(
        artifact_id="repo-artifact-1",
        media_type="application/octet-stream",
        size_bytes=10,
        raw_sha256=_SHA_REPO,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        attempt = unit_of_work.submission.get_submit_attempt(accepted.submit_attempt_id)
        assert attempt is not None
        updated = replace(
            attempt,
            state=SubmitAttemptState.EFFECT_PENDING,
            effect_pending_at=TS1,
            optimistic_version=1,
            canonicalization_manifest_ref="manifest-1",
            canonicalization_manifest_digest=_SHA_MANIFEST,
            repository_import_artifact_ref=backend_ref,
            repository_artifact_ref=repository_ref,
            repository_operation_id="repo-op-1",
        )
        unit_of_work.submission.cas_update_attempt(updated, expected_version=0)
        now = unit_of_work.transaction_now
        lease_expires_at = now + timedelta(seconds=60)
        steps, _cursor = unit_of_work.operations.list_steps(accepted.operation_id)
        prepare = next(step for step in steps if step.step_name == SUBMIT_STEP_PREPARE)
        running_prepare = replace(
            prepare,
            status=StepStatus.RUNNING,
            attempt_count=1,
            started_at=now,
            updated_at=now,
            worker_id="worker-test",
            lease_token="lease-test",
            lease_expires_at=lease_expires_at,
            optimistic_version=prepare.optimistic_version + 1,
        )
        unit_of_work.operations.compare_and_set_step(
            running_prepare,
            WritePrecondition(
                expected_optimistic_version=prepare.optimistic_version,
                worker_id=None,
                lease_token=None,
            ),
        )
        succeeded_prepare = replace(
            running_prepare,
            status=StepStatus.SUCCEEDED,
            completed_at=now,
            updated_at=now,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            optimistic_version=running_prepare.optimistic_version + 1,
        )
        unit_of_work.operations.compare_and_set_step(
            succeeded_prepare,
            WritePrecondition(
                expected_optimistic_version=running_prepare.optimistic_version,
                worker_id=running_prepare.worker_id,
                lease_token=running_prepare.lease_token,
            ),
            require_live_lease=True,
        )
        submit_step = StepRecord(
            contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
            step_id=f"{accepted.operation_id}-step-2",
            operation_id=accepted.operation_id,
            step_name=SUBMIT_STEP_SUBMIT,
            status=StepStatus.PENDING,
            attempt_count=0,
            diagnostic=None,
            cancel_requested=False,
            retry_not_before=None,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            checkpoint_ref=None,
            prior_output_refs=(),
            created_at=now,
            updated_at=now,
            started_at=None,
            completed_at=None,
            optimistic_version=0,
        )
        unit_of_work.operations.insert_successor_step(submit_step)
        running_submit = replace(
            submit_step,
            status=StepStatus.RUNNING,
            attempt_count=1,
            started_at=now,
            updated_at=now,
            worker_id="worker-test",
            lease_token="lease-test",
            lease_expires_at=lease_expires_at,
            optimistic_version=1,
        )
        unit_of_work.operations.compare_and_set_step(
            running_submit,
            WritePrecondition(
                expected_optimistic_version=submit_step.optimistic_version,
                worker_id=None,
                lease_token=None,
            ),
        )
        succeeded_submit = replace(
            running_submit,
            status=StepStatus.SUCCEEDED,
            completed_at=now,
            updated_at=now,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            optimistic_version=2,
        )
        unit_of_work.operations.compare_and_set_step(
            succeeded_submit,
            WritePrecondition(
                expected_optimistic_version=running_submit.optimistic_version,
                worker_id=running_submit.worker_id,
                lease_token=running_submit.lease_token,
            ),
            require_live_lease=True,
        )
        await_step = StepRecord(
            contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
            step_id=f"{accepted.operation_id}-step-3",
            operation_id=accepted.operation_id,
            step_name=SUBMIT_STEP_AWAIT,
            status=StepStatus.PENDING,
            attempt_count=0,
            diagnostic=None,
            cancel_requested=False,
            retry_not_before=None,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            checkpoint_ref=None,
            prior_output_refs=(),
            created_at=now,
            updated_at=now,
            started_at=None,
            completed_at=None,
            optimistic_version=0,
        )
        unit_of_work.operations.insert_successor_step(await_step)
        running_await = replace(
            await_step,
            status=StepStatus.RUNNING,
            attempt_count=1,
            started_at=now,
            updated_at=now,
            worker_id="worker-test",
            lease_token="lease-test",
            lease_expires_at=lease_expires_at,
            optimistic_version=1,
        )
        unit_of_work.operations.compare_and_set_step(
            running_await,
            WritePrecondition(
                expected_optimistic_version=await_step.optimistic_version,
                worker_id=None,
                lease_token=None,
            ),
        )
        operation = unit_of_work.operations.get_operation(accepted.operation_id)
        running_operation = replace(
            operation,
            status=OperationStatus.RUNNING,
            updated_at=now,
            optimistic_version=operation.optimistic_version + 1,
        )
        unit_of_work.operations.compare_and_set_operation(
            running_operation,
            WritePrecondition(
                expected_optimistic_version=operation.optimistic_version,
                worker_id=None,
                lease_token=None,
            ),
        )
        return updated


def test_t3_finalize_inserts_submission_and_switches_occupancy(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    attempt_version, await_version, operation_version = _read_finalize_versions(db_path, attempt)
    facts = MatchingFinalizeFacts(
        repository_id=seed.workspace.repository_id,
        repository_operation_id="repo-op-1",
        repository_commit_id="commit-new",
        repository_expected_parent_commit_id="commit-main",
        repository_artifact_id="repo-artifact-1",
        repository_import_artifact_raw_sha256=_SHA_PACKAGE,
        canonicalization_manifest_ref="manifest-1",
        canonicalization_manifest_digest=_SHA_MANIFEST,
        completed_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        completed_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        target_ref=SubmitTargetRef.MAIN,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        result = finalize_submit_transaction(
            request=FinalizeSubmitTransactionRequest(
                submit_attempt_id=attempt.submit_attempt_id,
                facts=facts,
                submission_id="sub-1",
                created_at=TS1,
                expected_attempt_version=attempt_version,
                expected_await_step_version=await_version,
                expected_operation_version=operation_version,
                worker_id="worker-test",
                lease_token="lease-test",
            ),
            unit_of_work=unit_of_work,
        )
    assert result.replay is False
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        submission = unit_of_work.submission.get_submission_by_attempt(attempt.submit_attempt_id)
        occupancy = unit_of_work.submission.get_workspace_occupancy(seed.workspace.workspace_id)
        repository_occupancy = unit_of_work.submission.get_repository_occupancy(seed.workspace.repository_id)
        operation = unit_of_work.operations.get_operation(attempt.operation_id)
    assert submission is not None
    assert submission.submission_id == "sub-1"
    assert occupancy is not None
    assert occupancy.active_submission_id == "sub-1"
    assert repository_occupancy is None
    assert operation.status is OperationStatus.SUCCEEDED


def test_t3_finalize_replay_does_not_insert_second_submission(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    attempt_version, await_version, operation_version = _read_finalize_versions(db_path, attempt)
    facts = MatchingFinalizeFacts(
        repository_id=seed.workspace.repository_id,
        repository_operation_id="repo-op-1",
        repository_commit_id="commit-new",
        repository_expected_parent_commit_id="commit-main",
        repository_artifact_id="repo-artifact-1",
        repository_import_artifact_raw_sha256=_SHA_PACKAGE,
        canonicalization_manifest_ref="manifest-1",
        canonicalization_manifest_digest=_SHA_MANIFEST,
        completed_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        completed_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        target_ref=SubmitTargetRef.MAIN,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        finalize_submit_transaction(
            request=FinalizeSubmitTransactionRequest(
                submit_attempt_id=attempt.submit_attempt_id,
                facts=facts,
                submission_id="sub-1",
                created_at=TS1,
                expected_attempt_version=attempt_version,
                expected_await_step_version=await_version,
                expected_operation_version=operation_version,
                worker_id="worker-test",
                lease_token="lease-test",
            ),
            unit_of_work=unit_of_work,
        )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        replay = finalize_submit_transaction(
            request=FinalizeSubmitTransactionRequest(
                submit_attempt_id=attempt.submit_attempt_id,
                facts=facts,
                submission_id="sub-1",
                created_at=TS1,
                expected_attempt_version=attempt_version,
                expected_await_step_version=await_version,
                expected_operation_version=operation_version,
                worker_id="worker-test",
                lease_token="lease-test",
            ),
            unit_of_work=unit_of_work,
        )
    assert replay.replay is True
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        rows = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM submission_records WHERE submit_attempt_id = ?",
            (attempt.submit_attempt_id,),
        ).fetchone()[0]
    assert rows == 1


def test_stable_abort_releases_occupancy_without_submission(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    tracker = WriterLockTracker()
    evidence = FakeAbortEvidencePort(tracker=tracker)
    result = abort_submit_transaction(
        request=AbortSubmitTransactionRequest(
            submit_attempt_id=attempt.submit_attempt_id,
            proof=MatchingAbortProof(
                repository_id=seed.workspace.repository_id,
                repository_operation_id="repo-op-1",
                terminal_status=RepositoryOperationTerminalStatus.FAILED,
                stable_failure_code="IMPORT_REJECTED",
            ),
            aborted_at=TS1,
            worker_id="worker-test",
            lease_token="lease-test",
        ),
        evidence=evidence,
        unit_of_work_factory=_tracking_uow_factory(db_path, tracker),
    )
    assert result.replay is False
    assert result.attempt.state is SubmitAttemptState.ABORTED
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        submission = unit_of_work.submission.get_submission_by_attempt(attempt.submit_attempt_id)
        occupancy = unit_of_work.submission.get_workspace_occupancy(seed.workspace.workspace_id)
        repository_occupancy = unit_of_work.submission.get_repository_occupancy(seed.workspace.repository_id)
        operation = unit_of_work.operations.get_operation(attempt.operation_id)
    assert submission is None
    assert occupancy is None
    assert repository_occupancy is None
    assert operation.status is OperationStatus.FAILED
    assert evidence.calls == 1
    assert evidence.writer_open_during_calls == (False,)


def _read_finalize_versions(
    db_path: Path,
    attempt: SubmitAttempt,
) -> tuple[int, int, int]:
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        current = unit_of_work.submission.get_submit_attempt(attempt.submit_attempt_id)
        assert current is not None
        if current.state is SubmitAttemptState.FINALIZED:
            return (current.optimistic_version, 0, 0)
        operation = unit_of_work.operations.get_operation(attempt.operation_id)
        steps, _cursor = unit_of_work.operations.list_steps(attempt.operation_id)
        await_step = next(
            (step for step in steps if step.step_name == SUBMIT_STEP_AWAIT),
            None,
        )
        await_version = await_step.optimistic_version if await_step is not None else 0
        return (
            current.optimistic_version,
            await_version,
            operation.optimistic_version,
        )


def _finalize_facts(seed: SubmitSeed) -> MatchingFinalizeFacts:
    return MatchingFinalizeFacts(
        repository_id=seed.workspace.repository_id,
        repository_operation_id="repo-op-1",
        repository_commit_id="commit-new",
        repository_expected_parent_commit_id="commit-main",
        repository_artifact_id="repo-artifact-1",
        repository_import_artifact_raw_sha256=_SHA_PACKAGE,
        canonicalization_manifest_ref="manifest-1",
        canonicalization_manifest_digest=_SHA_MANIFEST,
        completed_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        completed_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        target_ref=SubmitTargetRef.MAIN,
    )


def _abort_proof(seed: SubmitSeed) -> MatchingAbortProof:
    return MatchingAbortProof(
        repository_id=seed.workspace.repository_id,
        repository_operation_id="repo-op-1",
        terminal_status=RepositoryOperationTerminalStatus.FAILED,
        stable_failure_code="IMPORT_REJECTED",
    )


def _finalize(
    db_path: Path,
    attempt: SubmitAttempt,
    seed: SubmitSeed,
    *,
    worker_id: str | None = "worker-test",
    lease_token: str | None = "lease-test",
    expected_attempt_version: int | None = None,
    expected_await_step_version: int | None = None,
    expected_operation_version: int | None = None,
) -> FinalizeSubmitResult:
    actual_attempt_version, actual_await_version, actual_operation_version = _read_finalize_versions(
        db_path,
        attempt,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        return finalize_submit_transaction(
            request=FinalizeSubmitTransactionRequest(
                submit_attempt_id=attempt.submit_attempt_id,
                facts=_finalize_facts(seed),
                submission_id="sub-1",
                created_at=TS1,
                expected_attempt_version=(
                    expected_attempt_version
                    if expected_attempt_version is not None
                    else actual_attempt_version
                ),
                expected_await_step_version=(
                    expected_await_step_version
                    if expected_await_step_version is not None
                    else actual_await_version
                ),
                expected_operation_version=(
                    expected_operation_version
                    if expected_operation_version is not None
                    else actual_operation_version
                ),
                worker_id=worker_id,
                lease_token=lease_token,
            ),
            unit_of_work=unit_of_work,
        )


def _abort(
    db_path: Path,
    attempt: SubmitAttempt,
    seed: SubmitSeed,
    *,
    worker_id: str | None,
    lease_token: str | None,
    tracker: WriterLockTracker | None = None,
) -> tuple[AbortSubmitTransactionResult, FakeAbortEvidencePort]:
    evidence = FakeAbortEvidencePort(tracker=tracker)
    factory = _tracking_uow_factory(db_path, tracker) if tracker is not None else _uow_factory(db_path)
    result = abort_submit_transaction(
        request=AbortSubmitTransactionRequest(
            submit_attempt_id=attempt.submit_attempt_id,
            proof=_abort_proof(seed),
            aborted_at=TS1,
            worker_id=worker_id,
            lease_token=lease_token,
        ),
        evidence=evidence,
        unit_of_work_factory=factory,
    )
    return result, evidence


def _prepare_only_registry() -> JobDefinitionRegistry:
    return JobDefinitionRegistry.build(
        (
            JobDefinition(
                key=JobStepKey(job_kind=SUBMIT_JOB_KIND, step_name=SUBMIT_STEP_PREPARE),
                supported_payload_versions=frozenset({SUBMIT_JOB_CONTRACT_VERSION}),
                decoder_identity="backend-vnext/submit/prepare-import/decoder/v1",
                handler_identity="backend-vnext/submit/prepare-import/handler/v1",
                publication_capability=NormalPublicationCapability.SINGLE_SUCCESSOR,
                recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
            ),
        )
    )


def test_t1_accept_ports_run_outside_writer_transaction(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    tracker = WriterLockTracker()
    digest = FakeBaselineCanonicalDigestPort(tracker=tracker)
    resolve = RecordingMainResolvePort(tracker=tracker)
    accept_submit_transaction(
        command=_accept_command(seed, idempotency_key="accept-key-1"),
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_tracking_uow_factory(seed.db_path, tracker),
        job_registry=_submit_job_registry(),
        baseline_digest=digest,
        main_resolve=resolve,
        preflight=_preflight(seed),
        now=TS1,
    )
    assert digest.calls == 1
    assert resolve.calls == 1
    assert digest.writer_open_during_calls == (False,)
    assert resolve.writer_open_during_calls == (False,)
    assert digest.uow_active_during_calls == (False,)
    assert resolve.uow_active_during_calls == (False,)


def test_t1_accept_replay_does_not_call_repository_ports(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    command = _accept_command(seed, idempotency_key="accept-key-1")
    accept_submit_transaction(
        command=command,
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        baseline_digest=FakeBaselineCanonicalDigestPort(),
        main_resolve=RecordingMainResolvePort(),
        preflight=_preflight(seed),
        now=TS1,
    )
    digest = FakeBaselineCanonicalDigestPort()
    resolve = RecordingMainResolvePort()
    replay = accept_submit_transaction(
        command=command,
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        baseline_digest=digest,
        main_resolve=resolve,
        preflight=_preflight(seed),
        now=TS1,
    )
    assert replay.replay is True
    assert digest.calls == 0
    assert resolve.calls == 0


def test_t1_rejects_incomplete_submit_job_registry_without_writes(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    with pytest.raises(PreviewBindingConflict, match="submit job definition is not registered"):
        accept_submit_transaction(
            command=_accept_command(seed, idempotency_key="accept-key-1"),
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(seed.db_path),
            job_registry=_prepare_only_registry(),
            baseline_digest=FakeBaselineCanonicalDigestPort(),
            main_resolve=RecordingMainResolvePort(),
            preflight=_preflight(seed),
            now=TS1,
        )
    with ControlDbUnitOfWork(seed.db_path, read_only=True) as unit_of_work:
        assert unit_of_work.submission.find_submit_idempotency(seed.workspace.workspace_id, "accept-key-1") is None
        assert unit_of_work.submission.get_workspace_occupancy(seed.workspace.workspace_id) is None
        assert unit_of_work.connection.execute("SELECT COUNT(*) FROM submit_attempt_records").fetchone()[0] == 0


def test_t1_rejects_stale_workspace_version_without_writes(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        workspace = unit_of_work.workspace.get_workspace(seed.workspace.workspace_id)
        assert workspace is not None
        unit_of_work.workspace.save_workspace(
            replace(workspace, optimistic_version=workspace.optimistic_version + 1, updated_at=TS1),
            expected_version=workspace.optimistic_version,
        )
    baseline_digest = FakeBaselineCanonicalDigestPort(
        fail_with=RuntimeError("baseline provider unavailable"),
    )
    with pytest.raises(WorkspaceVersionConflict):
        accept_submit_transaction(
            command=_accept_command(seed, idempotency_key="accept-key-1"),
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(seed.db_path),
            job_registry=_submit_job_registry(),
            baseline_digest=baseline_digest,
            main_resolve=RecordingMainResolvePort(),
            preflight=_preflight(seed),
            now=TS1,
        )
    assert baseline_digest.calls == 0
    with ControlDbUnitOfWork(seed.db_path, read_only=True) as unit_of_work:
        assert unit_of_work.submission.find_submit_idempotency(seed.workspace.workspace_id, "accept-key-1") is None
        assert unit_of_work.submission.get_workspace_occupancy(seed.workspace.workspace_id) is None


def _take_over_await_lease(db_path: Path, operation_id: str) -> None:
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        steps, _cursor = unit_of_work.operations.list_steps(operation_id)
        await_step = next(step for step in steps if step.step_name == SUBMIT_STEP_AWAIT)
        unit_of_work.connection.execute(
            """
            UPDATE step_records
            SET worker_id = ?, lease_token = ?
            WHERE step_id = ?
            """,
            ("worker-new", "lease-new", await_step.step_id),
        )


def test_t3_rejects_stale_lease_after_takeover(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    _take_over_await_lease(db_path, attempt.operation_id)
    with pytest.raises(StaleWrite, match="write precondition no longer matches"):
        _finalize(db_path, attempt, seed, worker_id="worker-test", lease_token="lease-test")
    result = _finalize(db_path, attempt, seed, worker_id="worker-new", lease_token="lease-new")
    assert result.replay is False


def test_abort_rejects_stale_lease_after_takeover(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    _take_over_await_lease(db_path, attempt.operation_id)
    with pytest.raises(StaleWrite, match="write precondition no longer matches"):
        _abort(db_path, attempt, seed, worker_id="worker-test", lease_token="lease-test")
    result, _evidence = _abort(db_path, attempt, seed, worker_id="worker-new", lease_token="lease-new")
    assert result.replay is False
    assert result.attempt.state is SubmitAttemptState.ABORTED


def _advance_await_step_with_cancel(db_path: Path, operation_id: str) -> int:
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        steps, _cursor = unit_of_work.operations.list_steps(operation_id)
        await_step = next(step for step in steps if step.step_name == SUBMIT_STEP_AWAIT)
        observed_version = await_step.optimistic_version
        now = unit_of_work.transaction_now
        updated_step = replace(
            await_step,
            cancel_requested=True,
            optimistic_version=await_step.optimistic_version + 1,
            updated_at=now,
        )
        unit_of_work.operations.compare_and_set_step(
            updated_step,
            WritePrecondition(
                expected_optimistic_version=await_step.optimistic_version,
                worker_id=await_step.worker_id,
                lease_token=await_step.lease_token,
            ),
            require_live_lease=True,
        )
        operation = unit_of_work.operations.get_operation(operation_id)
        updated_operation = replace(
            operation,
            cancel_requested=True,
            optimistic_version=operation.optimistic_version + 1,
            updated_at=now,
        )
        unit_of_work.operations.compare_and_set_operation(
            updated_operation,
            WritePrecondition(
                expected_optimistic_version=operation.optimistic_version,
                worker_id=None,
                lease_token=None,
            ),
        )
        return observed_version


def _bump_attempt_version(db_path: Path, submit_attempt_id: str) -> int:
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
        assert attempt is not None
        observed_version = attempt.optimistic_version
        unit_of_work.submission.cas_update_attempt(
            replace(attempt, optimistic_version=attempt.optimistic_version + 1),
            expected_version=attempt.optimistic_version,
        )
        return observed_version


def _assert_effect_pending_with_occupancy_held(
    db_path: Path,
    seed: SubmitSeed,
    attempt: SubmitAttempt,
) -> None:
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted = unit_of_work.submission.get_submit_attempt(attempt.submit_attempt_id)
        workspace_occupancy = unit_of_work.submission.get_workspace_occupancy(seed.workspace.workspace_id)
        repository_occupancy = unit_of_work.submission.get_repository_occupancy(seed.workspace.repository_id)
        operation = unit_of_work.operations.get_operation(attempt.operation_id)
    assert persisted is not None
    assert persisted.state is SubmitAttemptState.EFFECT_PENDING
    assert workspace_occupancy is not None
    assert workspace_occupancy.active_submit_attempt_id == attempt.submit_attempt_id
    assert repository_occupancy is not None
    assert repository_occupancy.submit_attempt_id == attempt.submit_attempt_id
    assert operation.status is not OperationStatus.SUCCEEDED


def test_t3_rejects_stale_step_version_after_cancel_advance(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    stale_await_version = _advance_await_step_with_cancel(db_path, attempt.operation_id)
    with pytest.raises(StaleWrite, match="write precondition no longer matches"):
        _finalize(
            db_path,
            attempt,
            seed,
            expected_await_step_version=stale_await_version,
        )
    _assert_effect_pending_with_occupancy_held(db_path, seed, attempt)


def test_t3_rejects_stale_attempt_version(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    stale_attempt_version = _bump_attempt_version(db_path, attempt.submit_attempt_id)
    with pytest.raises(SubmitAttemptVersionConflict):
        _finalize(
            db_path,
            attempt,
            seed,
            expected_attempt_version=stale_attempt_version,
        )
    _assert_effect_pending_with_occupancy_held(db_path, seed, attempt)


def test_abort_rejects_stale_step_version_when_expected_set(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    stale_await_version = _advance_await_step_with_cancel(db_path, attempt.operation_id)
    evidence = FakeAbortEvidencePort()
    with pytest.raises(StaleWrite, match="write precondition no longer matches"):
        abort_submit_transaction(
            request=AbortSubmitTransactionRequest(
                submit_attempt_id=attempt.submit_attempt_id,
                proof=_abort_proof(seed),
                aborted_at=TS1,
                worker_id="worker-test",
                lease_token="lease-test",
                expected_await_step_version=stale_await_version,
            ),
            evidence=evidence,
            unit_of_work_factory=_uow_factory(db_path),
        )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted = unit_of_work.submission.get_submit_attempt(attempt.submit_attempt_id)
    assert persisted is not None
    assert persisted.state is SubmitAttemptState.EFFECT_PENDING


def test_t1_rejects_no_canonical_change_without_main_resolve_or_writes(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    tracker = WriterLockTracker()
    resolve = RecordingMainResolvePort(tracker=tracker)
    digest = FakeBaselineCanonicalDigestPort(
        digest="sha256:preview-canonical",
        tracker=tracker,
    )
    with pytest.raises(NoCanonicalChange):
        accept_submit_transaction(
            command=_accept_command(seed, idempotency_key="accept-key-1"),
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_tracking_uow_factory(seed.db_path, tracker),
            job_registry=_submit_job_registry(),
            baseline_digest=digest,
            main_resolve=resolve,
            preflight=_preflight(seed),
            now=TS1,
        )
    assert resolve.calls == 0
    assert digest.calls == 1
    assert tracker.writer_entries == 0
    assert tracker.active_uow_entries == 0
    assert tracker.factory_calls == (True,)
    assert digest.writer_open_during_calls == (False,)
    assert digest.uow_active_during_calls == (False,)
    assert resolve.writer_open_during_calls == ()
    assert resolve.uow_active_during_calls == ()
    with ControlDbUnitOfWork(seed.db_path, read_only=True) as unit_of_work:
        workspace = unit_of_work.workspace.get_workspace(seed.workspace.workspace_id)
        assert unit_of_work.submission.find_submit_idempotency(seed.workspace.workspace_id, "accept-key-1") is None
        assert unit_of_work.submission.get_workspace_occupancy(seed.workspace.workspace_id) is None
        assert unit_of_work.submission.get_repository_occupancy(seed.workspace.repository_id) is None
        assert unit_of_work.connection.execute("SELECT COUNT(*) FROM submit_attempt_records").fetchone()[0] == 0
        assert unit_of_work.connection.execute("SELECT COUNT(*) FROM operation_records").fetchone()[0] == 0
        assert unit_of_work.connection.execute("SELECT COUNT(*) FROM step_records").fetchone()[0] == 0
        assert workspace is not None
        assert workspace.optimistic_version == seed.workspace.optimistic_version


def test_t1_no_canonical_change_precedes_occupancy_conflict(db_path: Path) -> None:
    first_seed = seed_submit_ready_workspace(db_path)
    accept_submit_transaction(
        command=_accept_command(first_seed, idempotency_key="accept-key-1"),
        scope_resolution=FixedScopeResolutionPort(
            repository_id=first_seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(first_seed.db_path),
        job_registry=_submit_job_registry(),
        baseline_digest=FakeBaselineCanonicalDigestPort(),
        main_resolve=RecordingMainResolvePort(),
        preflight=_preflight(first_seed),
        now=TS1,
    )

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        workspace = Workspace(
            workspace_id="ws-2",
            owner_actor_id="actor-2",
            gateway_device_external_key="device-2",
            business_project_id="project-2",
            repository_id="repo-1",
            state=first_seed.workspace.state,
            generation=1,
            optimistic_version=0,
            current_upload_revision_id="ur-2",
            current_preview_result_id="pr-2",
            created_at=TS0,
            updated_at=TS0,
        )
        unit_of_work.workspace.save_workspace(workspace, expected_version=0)
        upload_revision = replace(first_seed.upload_revision, upload_revision_id="ur-2", workspace_id="ws-2")
        preview = replace(
            first_seed.preview_result,
            preview_result_id="pr-2",
            workspace_id="ws-2",
            upload_revision_id="ur-2",
            operation_id="op-preview-2",
        )
        unit_of_work.workspace.save_upload_revision(upload_revision)
        unit_of_work.workspace.save_preview_result(preview)
        updated = replace(
            workspace,
            optimistic_version=1,
            current_upload_revision_id="ur-2",
            current_preview_result_id="pr-2",
            updated_at=TS1,
        )
        unit_of_work.workspace.save_workspace(updated, expected_version=0)
        unit_of_work.set_artifact_protection(
            first_seed.protected_refs,
            owner_kind="current-preview",
            owner_id="ws-2",
            intent="current-preview",
        )

    second_seed = SubmitSeed(
        db_path=db_path,
        workspace=updated,
        upload_revision=upload_revision,
        preview_result=preview,
        preview_operation_id="op-preview-2",
        protected_refs=first_seed.protected_refs,
    )
    digest = FakeBaselineCanonicalDigestPort(digest="sha256:preview-canonical")
    with pytest.raises(NoCanonicalChange):
        accept_submit_transaction(
            command=_accept_command(second_seed, idempotency_key="accept-key-2"),
            scope_resolution=FixedScopeResolutionPort(
                repository_id="repo-1",
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(db_path),
            job_registry=_submit_job_registry(),
            baseline_digest=digest,
            main_resolve=RecordingMainResolvePort(),
            preflight=_preflight(second_seed),
            now=TS1,
        )
    assert digest.calls == 1


def test_t1_no_canonical_change_precedes_closure_digest_conflict(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    digest = FakeBaselineCanonicalDigestPort(digest="sha256:preview-canonical")
    with pytest.raises(NoCanonicalChange):
        accept_submit_transaction(
            command=_accept_command(seed, idempotency_key="accept-key-1"),
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(seed.db_path),
            job_registry=_submit_job_registry(),
            baseline_digest=digest,
            main_resolve=RecordingMainResolvePort(),
            preflight=AcceptSubmitPreflight(
                snapshot_table_artifact_refs=SNAPSHOT_TABLE_ARTIFACT_REFS,
                preview_ready_closure_digest="",
                preview_operation_id=seed.preview_operation_id,
                protected_artifact_refs=seed.protected_refs,
                snapshot_table_set_digest=SNAPSHOT_TABLE_SET_DIGEST,
            ),
            now=TS1,
        )
    assert digest.calls == 1


def _terminalize_await_step(db_path: Path, operation_id: str, *, fail_operation: bool) -> None:
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        steps, _cursor = unit_of_work.operations.list_steps(operation_id)
        await_step = next(step for step in steps if step.step_name == SUBMIT_STEP_AWAIT)
        now = unit_of_work.transaction_now
        failed = replace(
            await_step,
            status=StepStatus.FAILED,
            diagnostic=OperationDiagnostic(code="OPERATOR_CLOSED", message="operator recovery"),
            completed_at=now,
            updated_at=now,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            optimistic_version=await_step.optimistic_version + 1,
        )
        unit_of_work.operations.compare_and_set_step(
            failed,
            WritePrecondition(
                expected_optimistic_version=await_step.optimistic_version,
                worker_id=await_step.worker_id,
                lease_token=await_step.lease_token,
            ),
            require_live_lease=True,
        )
        if fail_operation:
            operation = unit_of_work.operations.get_operation(operation_id)
            unit_of_work.operations.compare_and_set_operation(
                replace(
                    operation,
                    status=OperationStatus.FAILED,
                    diagnostic=OperationDiagnostic(code="OPERATOR_CLOSED", message="operator recovery"),
                    completed_at=now,
                    updated_at=now,
                    optimistic_version=operation.optimistic_version + 1,
                ),
                WritePrecondition(
                    expected_optimistic_version=operation.optimistic_version,
                    worker_id=None,
                    lease_token=None,
                ),
            )


def test_abort_is_idempotent_after_operator_terminalized_await_step(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    _terminalize_await_step(db_path, attempt.operation_id, fail_operation=True)
    first, _evidence = _abort(db_path, attempt, seed, worker_id=None, lease_token=None)
    assert first.replay is False
    assert first.attempt.state is SubmitAttemptState.ABORTED
    second, _evidence = _abort(db_path, attempt, seed, worker_id=None, lease_token=None)
    assert second.replay is True
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        assert unit_of_work.submission.get_workspace_occupancy(seed.workspace.workspace_id) is None
        assert unit_of_work.submission.get_repository_occupancy(seed.workspace.repository_id) is None


def test_abort_completes_when_await_step_failed_and_operation_still_running(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    _terminalize_await_step(db_path, attempt.operation_id, fail_operation=False)
    result, _evidence = _abort(db_path, attempt, seed, worker_id=None, lease_token=None)
    assert result.replay is False
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(attempt.operation_id)
        occupancy = unit_of_work.submission.get_workspace_occupancy(seed.workspace.workspace_id)
    assert operation.status is OperationStatus.FAILED
    assert occupancy is None


def test_abort_rejects_mismatched_occupancy_owner(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.connection.execute(
            """
            INSERT INTO operation_records (
                operation_id, contract_version, optimistic_version, job_kind, job_contract_version,
                job_payload, job_payload_ref, business_refs, artifact_refs, repository_operation_id,
                checkpoint_ref, ready_closure_ref, status, diagnostic, cancel_requested,
                created_at_us, updated_at_us, completed_at_us
            ) VALUES (?, ?, 0, 'backend-vnext/submit', ?, ?, NULL, ?, ?, NULL, NULL, NULL, 'QUEUED', NULL, 0, ?, ?, NULL)
            """,
            (
                "op-other",
                OPERATION_RUNTIME_CONTRACT_VERSION,
                SUBMIT_JOB_CONTRACT_VERSION,
                b"{}",
                b"[]",
                b"[]",
                1,
                1,
            ),
        )
        unit_of_work.submission.insert_attempt_prepared(
            replace(
                attempt,
                submit_attempt_id="sa-other",
                operation_id="op-other",
                state=SubmitAttemptState.PREPARED,
                optimistic_version=0,
                effect_pending_at=None,
                canonicalization_manifest_ref=None,
                canonicalization_manifest_digest=None,
                repository_import_artifact_ref=None,
                repository_artifact_ref=None,
                repository_operation_id=None,
                accept_idempotency_key="accept-key-other",
            )
        )
        unit_of_work.connection.execute(
            """
            UPDATE workspace_submit_occupancy_records
            SET active_submit_attempt_id = ?
            WHERE workspace_id = ?
            """,
            ("sa-other", seed.workspace.workspace_id),
        )
    with pytest.raises(SubmitOccupancyConflict):
        _abort(db_path, attempt, seed, worker_id="worker-test", lease_token="lease-test")
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        occupancy = unit_of_work.submission.get_workspace_occupancy(seed.workspace.workspace_id)
        persisted = unit_of_work.submission.get_submit_attempt(attempt.submit_attempt_id)
    assert occupancy is not None
    assert occupancy.active_submit_attempt_id == "sa-other"
    assert persisted is not None
    assert persisted.state is SubmitAttemptState.EFFECT_PENDING


@pytest.mark.parametrize(
    "broken_component",
    ("workspace occupancy", "repository occupancy", "await step", "operation"),
)
def test_t3_replay_fails_closed_when_closure_is_incomplete(
    db_path: Path,
    broken_component: str,
) -> None:
    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    _finalize(db_path, attempt, seed)
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        if broken_component == "workspace occupancy":
            unit_of_work.connection.execute(
                "DELETE FROM workspace_submit_occupancy_records WHERE workspace_id = ?",
                (seed.workspace.workspace_id,),
            )
        elif broken_component == "repository occupancy":
            unit_of_work.connection.execute(
                """
                INSERT INTO repository_submit_occupancy_records (
                    repository_id, workspace_id, submit_attempt_id,
                    business_baseline_node_id, baseline_head_version, acquired_at_us
                ) VALUES (?, ?, ?, ?, ?, 1)
                """,
                (
                    seed.workspace.repository_id,
                    seed.workspace.workspace_id,
                    attempt.submit_attempt_id,
                    BASELINE_HEAD.business_baseline_node_id,
                    BASELINE_HEAD.baseline_head_version,
                ),
            )
        elif broken_component == "await step":
            unit_of_work.connection.execute(
                "DELETE FROM step_records WHERE step_name = ?",
                (SUBMIT_STEP_AWAIT,),
            )
        else:
            unit_of_work.connection.execute(
                "UPDATE operation_records SET status = 'CANCELLED' WHERE operation_id = ?",
                (attempt.operation_id,),
            )
    with pytest.raises(FinalizeRecoveryRequired):
        _finalize(db_path, attempt, seed)


def test_prepared_attempt_rejects_business_abort(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    accepted = accept_submit_transaction(
        command=_accept_command(seed, idempotency_key="accept-key-1"),
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        baseline_digest=FakeBaselineCanonicalDigestPort(),
        main_resolve=RecordingMainResolvePort(),
        preflight=_preflight(seed),
        now=TS1,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        attempt = unit_of_work.submission.get_submit_attempt(accepted.submit_attempt_id)
        assert attempt is not None
        assert attempt.state is SubmitAttemptState.PREPARED
    with pytest.raises(ValueError, match="abort requires EFFECT_PENDING attempt"):
        abort_submit_transaction(
            request=AbortSubmitTransactionRequest(
                submit_attempt_id=accepted.submit_attempt_id,
                proof=_abort_proof(seed),
                aborted_at=TS1,
            ),
            evidence=FakeAbortEvidencePort(),
            unit_of_work_factory=_uow_factory(db_path),
        )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        occupancy = unit_of_work.submission.get_workspace_occupancy(seed.workspace.workspace_id)
        repository_occupancy = unit_of_work.submission.get_repository_occupancy(seed.workspace.repository_id)
        persisted = unit_of_work.submission.get_submit_attempt(accepted.submit_attempt_id)
    assert occupancy is not None
    assert repository_occupancy is not None
    assert persisted is not None
    assert persisted.state is SubmitAttemptState.PREPARED


@dataclass
class DriftOnResolveMainResolvePort:
    commit_id: str = "commit-main"
    calls: int = 0
    on_resolve: Callable[[], None] | None = None

    def resolve_main_expected_commit(self, *, repository_id: str) -> str:
        del repository_id
        self.calls += 1
        if self.on_resolve is not None:
            self.on_resolve()
        return self.commit_id


def _drift_head_version_only(db_path: Path) -> None:
    _upsert_provisioned_mapping_row(
        db_path,
        baseline_head=replace(BASELINE_HEAD, baseline_head_version=BASELINE_HEAD.baseline_head_version + 1),
    )


def _drift_head_commit_only(db_path: Path) -> None:
    _upsert_provisioned_mapping_row(
        db_path,
        baseline_head=replace(BASELINE_HEAD, business_baseline_commit_id="commit-only-drift"),
    )


def _drift_head_node_only(db_path: Path) -> None:
    _upsert_provisioned_mapping_row(
        db_path,
        baseline_head=replace(BASELINE_HEAD, business_baseline_node_id="node-only-drift"),
    )


def _drift_mapping_disable(db_path: Path) -> None:
    _upsert_provisioned_mapping_row(db_path, enabled=False)


def _drift_repo_swap(db_path: Path) -> None:
    _upsert_provisioned_mapping_row(db_path, repository_id="repo-other")


NEW_KEY_PROJECTION_DRIFT_CASES: tuple[tuple[str, type[Exception], Callable[[Path], None]], ...] = (
    ("version_only", BaselineVersionConflict, _drift_head_version_only),
    ("commit_only", BaselineVersionConflict, _drift_head_commit_only),
    ("node_only", BaselineVersionConflict, _drift_head_node_only),
    ("mapping_disable", ScopeForbidden, _drift_mapping_disable),
    ("repo_swap", ScopeForbidden, _drift_repo_swap),
)


@pytest.mark.parametrize(
    ("case_id", "expected_error", "apply_drift"),
    NEW_KEY_PROJECTION_DRIFT_CASES,
    ids=[case[0] for case in NEW_KEY_PROJECTION_DRIFT_CASES],
)
def test_t1_new_key_rejects_projection_drift_without_writes(
    db_path: Path,
    case_id: str,
    expected_error: type[Exception],
    apply_drift: Callable[[Path], None],
) -> None:
    del case_id
    seed = seed_submit_ready_workspace(db_path)
    idempotency_key = "accept-key-drift"
    resolve = DriftOnResolveMainResolvePort(on_resolve=lambda: apply_drift(seed.db_path))
    with pytest.raises(expected_error):
        accept_submit_transaction(
            command=_accept_command(seed, idempotency_key=idempotency_key),
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(seed.db_path),
            job_registry=_submit_job_registry(),
            baseline_digest=FakeBaselineCanonicalDigestPort(),
            main_resolve=resolve,
            preflight=_preflight(seed),
            now=TS1,
        )
    _assert_t1_zero_writes(seed.db_path, seed, idempotency_key=idempotency_key)
    with ControlDbUnitOfWork(seed.db_path, read_only=True) as unit_of_work:
        row = unit_of_work.connection.execute(
            """
            SELECT repository_id, business_baseline_node_id, business_baseline_commit_id,
                   baseline_head_version, enabled
            FROM provisioned_scope_mappings
            WHERE gateway_device_external_key = ? AND business_project_id = ?
            """,
            ("device-1", "project-1"),
        ).fetchone()
        assert row is not None
        if expected_error is ScopeForbidden and apply_drift is _drift_mapping_disable:
            assert row["enabled"] == 0
        elif expected_error is ScopeForbidden and apply_drift is _drift_repo_swap:
            assert row["repository_id"] == "repo-other"


def test_t1_replay_rejects_when_mapping_disabled_after_concurrent_winner(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    command = _accept_command(seed, idempotency_key="accept-key-winner")
    winner_submitted = False

    def on_resolve() -> None:
        nonlocal winner_submitted
        if winner_submitted:
            return
        accept_submit_transaction(
            command=command,
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(seed.db_path),
            job_registry=_submit_job_registry(),
            baseline_digest=FakeBaselineCanonicalDigestPort(),
            main_resolve=RecordingMainResolvePort(),
            preflight=_preflight(seed),
            now=TS1,
        )
        _upsert_provisioned_mapping_row(seed.db_path, enabled=False)
        winner_submitted = True

    with pytest.raises(ScopeForbidden):
        accept_submit_transaction(
            command=command,
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(seed.db_path),
            job_registry=_submit_job_registry(),
            baseline_digest=FakeBaselineCanonicalDigestPort(),
            main_resolve=DriftOnResolveMainResolvePort(on_resolve=on_resolve),
            preflight=_preflight(seed),
            now=TS1,
        )

    with ControlDbUnitOfWork(seed.db_path, read_only=True) as unit_of_work:
        winner_id = deterministic_submit_attempt_id(
            workspace_id=seed.workspace.workspace_id,
            idempotency_key=command.idempotency_key,
        )
        winner = unit_of_work.submission.get_submit_attempt(winner_id)
        assert winner is not None
        assert winner.state is SubmitAttemptState.PREPARED
        assert unit_of_work.connection.execute(
            "SELECT enabled FROM provisioned_scope_mappings WHERE gateway_device_external_key = ?",
            ("device-1",),
        ).fetchone()[0] == 0


def test_t1_replay_returns_winner_when_only_head_drifts_after_concurrent_winner(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    command = _accept_command(seed, idempotency_key="accept-key-head-replay")
    winner_submitted = False
    winner_attempt_id: str | None = None

    def on_resolve() -> None:
        nonlocal winner_submitted, winner_attempt_id
        if winner_submitted:
            return
        winner = accept_submit_transaction(
            command=command,
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(seed.db_path),
            job_registry=_submit_job_registry(),
            baseline_digest=FakeBaselineCanonicalDigestPort(),
            main_resolve=RecordingMainResolvePort(),
            preflight=_preflight(seed),
            now=TS1,
        )
        assert winner.replay is False
        winner_attempt_id = winner.submit_attempt_id
        _drift_head_commit_only(seed.db_path)
        winner_submitted = True

    digest = FakeBaselineCanonicalDigestPort()
    drift_resolve = DriftOnResolveMainResolvePort(on_resolve=on_resolve)
    result = accept_submit_transaction(
        command=command,
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        baseline_digest=digest,
        main_resolve=drift_resolve,
        preflight=_preflight(seed),
        now=TS1,
    )
    assert result.replay is True
    assert result.submit_attempt_id == winner_attempt_id
    assert digest.calls == 1
    assert drift_resolve.calls == 1

    with ControlDbUnitOfWork(seed.db_path, read_only=True) as unit_of_work:
        winner = unit_of_work.submission.get_submit_attempt(result.submit_attempt_id)
        assert winner is not None
        assert winner.state is SubmitAttemptState.PREPARED
        row = unit_of_work.connection.execute(
            """
            SELECT business_baseline_commit_id
            FROM provisioned_scope_mappings
            WHERE gateway_device_external_key = ? AND business_project_id = ?
            """,
            ("device-1", "project-1"),
        ).fetchone()
        assert row is not None
        assert row["business_baseline_commit_id"] == "commit-only-drift"
        assert unit_of_work.connection.execute("SELECT COUNT(*) FROM submit_attempt_records").fetchone()[0] == 1
