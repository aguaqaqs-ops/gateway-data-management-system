"""T1/T3 submit transaction matrix tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType

import pytest

from gateway_backend.application.job_definitions import (
    JobDefinition,
    JobDefinitionRegistry,
    NormalPublicationCapability,
)
from gateway_backend.application.recovery import RecoveryCapability
from gateway_backend.application.submit_registry import submit_job_registry
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
    IdentityConfirmationRequest,
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
    PreviewDerivedStale,
    ProjectIdentityConfirmationMismatch,
    ProjectIdentityConfirmationRequired,
    ReviewIntegrityFailure,
    SubmitJobNotRegistered,
    SubmitOccupancyConflict,
)
from gateway_backend.application.submission.finalize_transaction import (
    FinalizeSubmitTransactionRequest,
    finalize_submit_transaction,
)
from gateway_backend.application.submission.job_payload import SUBMIT_JOB_KIND, SUBMIT_STEP_AWAIT, SUBMIT_STEP_PREPARE, SUBMIT_STEP_SUBMIT
from gateway_backend.application.submission.ports import SubmitControlUnitOfWorkFactory
from gateway_backend.application.workspace.services import create_or_get_workspace
from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.submission.errors import (
    SubmitAttemptInvariantViolation,
    SubmitAttemptVersionConflict,
)
from gateway_backend.domain.submission.review import ReviewEventKind, ReviewStatus
from gateway_backend.domain.submission.models import (
    BackendArtifactRef,
    BuilderMutationPolicy,
    RepositoryArtifactRef,
    SubmitAttempt,
    SubmitAttemptState,
    SubmitTargetRef,
    SubmitUnknownTypePolicy,
    SubmitVerificationPolicy,
    IdentityConfirmationAction,
)
from gateway_backend.domain.workspace.errors import (
    PermissionDenied,
    ScopeForbidden,
    WorkspaceVersionConflict,
)
from gateway_backend.domain.workspace.models import (
    BaselineHead,
    InputCompleteness,
    PreviewResult,
    PreviewResultDigests,
    PreviewArtifactRef,
    PreviewIdentityPair,
    ProjectIdentityApplicability,
    ProjectIdentityMode,
    ProjectIdentityStatus,
    SourceArtifactBinding,
    SourceArtifactRole,
    UploadRevision,
    Workspace,
)
from tests.support.preview_fixtures import (
    make_canonical_artifact_fixture,
    make_preview_canonical_bindings,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, initialize_control_db
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
from tests.support.baseline_fixtures import (
    seed_provisioned_mapping_with_head,
    upsert_provisioned_mapping_row,
)
from tests.support.workspace_fixtures import (
    FixedScopeResolutionPort,
    make_baseline_head,
    make_identity,
    make_not_applicable_preview_identity,
)

pytestmark = pytest.mark.unit

TS0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
TS1 = datetime(2024, 6, 1, 12, 30, 0, tzinfo=UTC)
BASELINE_HEAD = make_baseline_head(version=3, commit_id="commit-base")
PREVIEW_READY_CLOSURE_DIGEST = "d-closure"
_SHA_INITIAL = "sha256:" + "a" * 64
_SHA_MODIFIED = "sha256:" + "b" * 64
_SHA_CLOSURE = "sha256:" + "c" * 64
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
    stable_failure_code: str = "IMPORT_REJECTED"

    def resolve_stable_failure_code(
        self,
        *,
        repository_id: str,
        repository_operation_id: str,
    ) -> str:
        del repository_id, repository_operation_id
        return self.stable_failure_code

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
    seed_provisioned_mapping_with_head(
        db_path,
        device_key=device_key,
        project_id=project_id,
        repository_id=repository_id,
        baseline_head=baseline_head,
        enabled=enabled,
    )


def _upsert_provisioned_mapping_row(
    db_path: Path,
    *,
    device_key: str = "device-1",
    project_id: str = "project-1",
    repository_id: str = "repo-1",
    baseline_head: BaselineHead | None = BASELINE_HEAD,
    enabled: bool = True,
) -> None:
    upsert_provisioned_mapping_row(
        db_path,
        device_key=device_key,
        project_id=project_id,
        repository_id=repository_id,
        baseline_head=baseline_head,
        enabled=enabled,
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
    return submit_job_registry()


def _preview_result(workspace_id: str) -> PreviewResult:
    identity_digest, identity_pairs = make_not_applicable_preview_identity()
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
        canonical=make_preview_canonical_bindings(),
        identity_assessment_set_digest=identity_digest,
        identity_pairs=identity_pairs,
        bundle_artifact_id="bundle-1",
        ready_closure_artifact_id="closure-1",
        operation_id="op-preview-1",
        created_at=TS1,
    )


def _set_preview_identity_statuses(
    seed: SubmitSeed,
    statuses: tuple[ProjectIdentityStatus, ...],
) -> SubmitSeed:
    pair_ids = (
        ("initial_to_modified",)
        if len(statuses) == 1
        else ("baseline_to_initial", "initial_to_modified")
    )
    assert len(statuses) == len(pair_ids)
    pairs_list: list[PreviewIdentityPair] = []
    for pair_id, status in zip(pair_ids, statuses, strict=True):
        assessment_digest = raw_blob_digest(
            canonicalize_json_value({"pair_id": pair_id, "status": status.value})
        )
        pairs_list.append(
            PreviewIdentityPair(
                pair_id=pair_id,
                applicability=ProjectIdentityApplicability.APPLICABLE,
                status=status,
                mode=(
                    ProjectIdentityMode.DATASET_REPLACEMENT
                    if status is ProjectIdentityStatus.DIFFERENT_PROJECT
                    else ProjectIdentityMode.DETAILED
                ),
                assessment_ref=PreviewArtifactRef(
                    artifact_id=f"identity-{pair_id}",
                    media_type="application/json",
                    size_bytes=0,
                    raw_sha256=assessment_digest,
                ),
                assessment_digest=assessment_digest,
            )
        )
    pairs = tuple(pairs_list)
    assessment_set_digest = raw_blob_digest(
        canonicalize_json_value(
            {
                "schema": "project-identity-assessment-set/v1",
                "pairs": [
                    [
                        pair.pair_id,
                        pair.applicability.value,
                        pair.status.value,
                        pair.assessment_digest.value if pair.assessment_digest is not None else None,
                    ]
                    for pair in pairs
                ],
            }
        )
    )
    preview = replace(
        seed.preview_result,
        identity_assessment_set_digest=assessment_set_digest,
        identity_pairs=pairs,
    )
    from gateway_backend.infrastructure.control_db.sqlite_workspace import preview_result_to_row

    preview_row = preview_result_to_row(preview)
    with ControlDbUnitOfWork(seed.db_path) as unit_of_work:
        unit_of_work.connection.execute(
            "UPDATE preview_result_records SET binding = ? WHERE preview_result_id = ?",
            (preview_row[5], preview.preview_result_id),
        )
    return replace(seed, preview_result=preview)


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
        *make_canonical_artifact_fixture().refs,
    )


def seed_submit_ready_workspace(
    db_path: Path,
    *,
    repository_id: str = "repo-1",
    actor_id: str = "actor-1",
    device_key: str = "device-1",
    project_id: str = "project-1",
) -> SubmitSeed:
    from tests.support.baseline_fixtures import read_authoritative_baseline_head

    _seed_provisioned_mapping(db_path, repository_id=repository_id)
    baseline_head = read_authoritative_baseline_head(db_path, repository_id)
    scope_resolution = FixedScopeResolutionPort(
        repository_id=repository_id,
        baseline_head=baseline_head,
    )
    context = make_identity(
        actor_id=actor_id,
        device_key=device_key,
        project_id=project_id,
        permissions=frozenset({"upload_submit_workspace", "workspace_read"}),
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        created = create_or_get_workspace(
            context=context,
            scope_resolution=scope_resolution,
            repository=unit_of_work.workspace,
            created_at=TS0,
        )
        workspace = created.workspace
        upload_revision_id = "ur-1" if actor_id == "actor-1" else f"ur-{actor_id}"
        preview_result_id = "pr-1" if actor_id == "actor-1" else f"pr-{actor_id}"
        upload_revision = UploadRevision(
            upload_revision_id=upload_revision_id,
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
            idempotency_key=f"upload-key-{actor_id}",
            request_fingerprint=f"fp-upload-{actor_id}",
            created_by=actor_id,
            created_at=TS0,
        )
        preview = replace(
            _preview_result(workspace.workspace_id),
            preview_result_id=preview_result_id,
            upload_revision_id=upload_revision_id,
            repository_id=repository_id,
            operation_id=f"op-preview-{actor_id}",
            business_baseline_node_id=baseline_head.business_baseline_node_id,
            business_baseline_commit_id=baseline_head.business_baseline_commit_id,
            baseline_head_version=baseline_head.baseline_head_version,
        )
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


def _accept_command(
    seed: SubmitSeed,
    *,
    idempotency_key: str,
    baseline_head: BaselineHead = BASELINE_HEAD,
    identity_confirmations: tuple[IdentityConfirmationRequest, ...] = (),
) -> AcceptSubmitCommand:
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
        expected_baseline_node_id=baseline_head.business_baseline_node_id,
        expected_baseline_head_version=baseline_head.baseline_head_version,
        idempotency_key=idempotency_key,
        options={},
        identity_confirmations=identity_confirmations,
    )


def _preflight(seed: SubmitSeed) -> AcceptSubmitPreflight:
    return AcceptSubmitPreflight(
        preview_ready_closure_digest=PREVIEW_READY_CLOSURE_DIGEST,
        preview_operation_id=seed.preview_operation_id,
        protected_artifact_refs=seed.protected_refs,
        current_storage_projection_ruleset_digest=(
            seed.preview_result.canonical.storage_projection_ruleset_digest.value
        ),
    )


def _set_preview_canonical_states_equal(seed: SubmitSeed) -> SubmitSeed:
    canonical = replace(
        seed.preview_result.canonical,
        baseline_canonical_state_digest=(
            seed.preview_result.canonical.modified_canonical_state_digest
        ),
    )
    preview = replace(seed.preview_result, canonical=canonical)
    from gateway_backend.infrastructure.control_db.sqlite_workspace import preview_result_to_row

    preview_row = preview_result_to_row(preview)
    with ControlDbUnitOfWork(seed.db_path) as unit_of_work:
        unit_of_work.connection.execute(
            "UPDATE preview_result_records SET binding = ? WHERE preview_result_id = ?",
            (preview_row[5], preview.preview_result_id),
        )
    return replace(seed, preview_result=preview)


def test_t1_accept_persists_attempt_operation_and_occupancy(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    additional_refs = tuple(
        ArtifactRef(
            artifact_id=f"additional-protected-{index:03d}",
            media_type="application/octet-stream",
            size_bytes=1,
            raw_sha256=DigestRef("sha256:" + f"{index:064x}"),
        )
        for index in range(70)
    )
    protected_refs = (*seed.protected_refs, *additional_refs)
    with ControlDbUnitOfWork(seed.db_path) as unit_of_work:
        unit_of_work.clear_artifact_protection(
            owner_kind="current-preview",
            owner_id=seed.workspace.workspace_id,
        )
        unit_of_work.set_artifact_protection(
            protected_refs,
            owner_kind="current-preview",
            owner_id=seed.workspace.workspace_id,
            intent="current-preview",
        )
    result = accept_submit_transaction(
        command=_accept_command(seed, idempotency_key="accept-key-1"),
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        main_resolve=RecordingMainResolvePort(),
        preflight=replace(_preflight(seed), protected_artifact_refs=protected_refs),
        now=TS1,
    )
    assert result.replay is False

    with ControlDbUnitOfWork(seed.db_path, read_only=True) as unit_of_work:
        attempt = unit_of_work.submission.get_submit_attempt(result.submit_attempt_id)
        workspace_occupancy = unit_of_work.submission.get_workspace_occupancy(seed.workspace.workspace_id)
        repository_occupancy = unit_of_work.submission.get_repository_occupancy(seed.workspace.repository_id)
        operation = unit_of_work.operations.get_operation(result.operation_id)
        workspace = unit_of_work.workspace.get_workspace(seed.workspace.workspace_id)
        submit_artifact_ids = unit_of_work.list_artifact_protection_for_owner(
            owner_kind="submit-attempt",
            owner_id=result.submit_attempt_id,
        )
        current_preview_artifact_ids = unit_of_work.list_artifact_protection_for_owner(
            owner_kind="current-preview",
            owner_id=seed.workspace.workspace_id,
        )
        preview_operation_artifact_ids = unit_of_work.list_artifact_protection_for_owner(
            owner_kind="preview-operation",
            owner_id=seed.preview_operation_id,
        )

    assert attempt is not None
    assert attempt.state is SubmitAttemptState.PREPARED
    assert attempt.canonical_table_set_closure_ref == (
        seed.preview_result.canonical.canonical_table_set_closure_ref.artifact_id
    )
    assert attempt.canonical_table_set_closure_digest == (
        seed.preview_result.canonical.canonical_table_set_closure_digest.value
    )
    assert attempt.canonicalization_manifest_ref == (
        seed.preview_result.canonical.canonicalization_manifest_ref.artifact_id
    )
    assert attempt.canonicalization_manifest_digest == (
        seed.preview_result.canonical.canonicalization_manifest_digest.value
    )
    expected_protected_ids = frozenset(ref.artifact_id for ref in protected_refs)
    expected_operation_ids = frozenset(
        (
            *attempt.source_artifact_refs,
            attempt.preview_ready_closure_ref,
            attempt.canonical_table_set_closure_ref,
            attempt.canonicalization_manifest_ref,
        )
    )
    assert frozenset(ref.artifact_id for ref in operation.artifact_refs) == expected_operation_ids
    assert len(operation.artifact_refs) <= 64
    assert submit_artifact_ids == expected_protected_ids
    assert current_preview_artifact_ids == frozenset()
    assert preview_operation_artifact_ids == frozenset()
    assert workspace_occupancy is not None
    assert workspace_occupancy.active_submit_attempt_id == result.submit_attempt_id
    assert repository_occupancy is not None
    assert repository_occupancy.submit_attempt_id == result.submit_attempt_id
    assert operation.status is OperationStatus.QUEUED
    assert workspace is not None
    assert workspace.optimistic_version == seed.workspace.optimistic_version + 1


IDENTITY_CONFIRMATION_FAILURE_CASES = (
    pytest.param(
        (ProjectIdentityStatus.DIFFERENT_PROJECT,),
        (),
        False,
        ProjectIdentityConfirmationRequired,
        id="replacement-confirmation-required",
    ),
    pytest.param(
        (ProjectIdentityStatus.UNVERIFIABLE,),
        (),
        False,
        ProjectIdentityConfirmationRequired,
        id="unverifiable-confirmation-required",
    ),
    pytest.param(
        (ProjectIdentityStatus.DIFFERENT_PROJECT, ProjectIdentityStatus.UNVERIFIABLE),
        (IdentityConfirmationAction.ACCEPT_DATASET_REPLACEMENT,),
        False,
        ProjectIdentityConfirmationRequired,
        id="each-status-requires-its-own-action",
    ),
    pytest.param(
        (ProjectIdentityStatus.SAME_PROJECT,),
        (IdentityConfirmationAction.ACCEPT_DATASET_REPLACEMENT,),
        False,
        ProjectIdentityConfirmationMismatch,
        id="unneeded-action-is-rejected",
    ),
    pytest.param(
        (ProjectIdentityStatus.DIFFERENT_PROJECT,),
        (IdentityConfirmationAction.ACCEPT_DATASET_REPLACEMENT,),
        True,
        ProjectIdentityConfirmationMismatch,
        id="assessment-set-digest-must-match",
    ),
)


@pytest.mark.parametrize(
    ("statuses", "actions", "wrong_digest", "expected_error"),
    IDENTITY_CONFIRMATION_FAILURE_CASES,
)
def test_t1_identity_confirmation_guards_leave_no_durable_writes(
    db_path: Path,
    statuses: tuple[ProjectIdentityStatus, ...],
    actions: tuple[IdentityConfirmationAction, ...],
    wrong_digest: bool,
    expected_error: type[Exception],
) -> None:
    seed = _set_preview_identity_statuses(seed_submit_ready_workspace(db_path), statuses)
    digest = seed.preview_result.identity_assessment_set_digest.value
    if wrong_digest:
        digest = "sha256:" + "0" * 64
    confirmations = tuple(
        IdentityConfirmationRequest(
            action=action,
            assessment_set_digest=digest,
            reason="operator confirmed identity handling",
        )
        for action in actions
    )

    with pytest.raises(expected_error):
        accept_submit_transaction(
            command=_accept_command(
                seed,
                idempotency_key="accept-key-identity-guard",
                identity_confirmations=confirmations,
            ),
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(seed.db_path),
            job_registry=_submit_job_registry(),
            main_resolve=RecordingMainResolvePort(),
            preflight=_preflight(seed),
            now=TS1,
        )

    _assert_t1_zero_writes(seed.db_path, seed, idempotency_key="accept-key-identity-guard")


def test_t1_freezes_both_identity_confirmations_and_fingerprints_reason(db_path: Path) -> None:
    seed = _set_preview_identity_statuses(
        seed_submit_ready_workspace(db_path),
        (ProjectIdentityStatus.DIFFERENT_PROJECT, ProjectIdentityStatus.UNVERIFIABLE),
    )
    digest = seed.preview_result.identity_assessment_set_digest.value
    confirmations = (
        IdentityConfirmationRequest(
            action=IdentityConfirmationAction.ACCEPT_DATASET_REPLACEMENT,
            assessment_set_digest=digest,
            reason="replace the selected dataset\noperator checked source",
        ),
        IdentityConfirmationRequest(
            action=IdentityConfirmationAction.ACCEPT_UNVERIFIABLE_DETAILED_RESULT,
            assessment_set_digest=digest,
            reason="identity could not be verified\tcontinue with review",
        ),
    )
    command = _accept_command(
        seed,
        idempotency_key="accept-key-identity-confirmed",
        identity_confirmations=confirmations,
    )
    first = accept_submit_transaction(
        command=command,
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        main_resolve=RecordingMainResolvePort(),
        preflight=_preflight(seed),
        now=TS1,
    )

    with ControlDbUnitOfWork(seed.db_path, read_only=True) as unit_of_work:
        attempt = unit_of_work.submission.get_submit_attempt(first.submit_attempt_id)
    assert attempt is not None
    assert tuple(item.action for item in attempt.identity_confirmations) == tuple(
        item.action for item in confirmations
    )
    assert tuple(item.reason for item in attempt.identity_confirmations) == tuple(
        item.reason for item in confirmations
    )
    assert all(item.assessment_set_digest == digest for item in attempt.identity_confirmations)
    assert all(item.actor_id == command.context.actor_id for item in attempt.identity_confirmations)
    assert all(item.confirmed_at == TS1 for item in attempt.identity_confirmations)
    altered_attempt = replace(
        attempt,
        identity_confirmations=(
            replace(attempt.identity_confirmations[0], reason="changed after acceptance"),
            attempt.identity_confirmations[1],
        ),
    )
    with ControlDbUnitOfWork(seed.db_path) as unit_of_work:
        with pytest.raises(SubmitAttemptInvariantViolation, match="identity confirmations are immutable"):
            unit_of_work.submission.cas_update_attempt(altered_attempt, expected_version=0)

    replay = accept_submit_transaction(
        command=command,
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        main_resolve=RecordingMainResolvePort(),
        preflight=_preflight(seed),
        now=TS1 + timedelta(seconds=1),
    )
    assert replay.replay is True
    assert replay.submit_attempt_id == first.submit_attempt_id

    changed_reason = replace(confirmations[0], reason="different confirmation text")
    changed_command = replace(
        command,
        identity_confirmations=(changed_reason, confirmations[1]),
    )
    with pytest.raises(IdempotencyConflict):
        accept_submit_transaction(
            command=changed_command,
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(seed.db_path),
            job_registry=_submit_job_registry(),
            main_resolve=RecordingMainResolvePort(),
            preflight=_preflight(seed),
            now=TS1 + timedelta(seconds=2),
        )


def test_t1_no_canonical_change_precedes_identity_confirmation(db_path: Path) -> None:
    seed = _set_preview_identity_statuses(
        seed_submit_ready_workspace(db_path),
        (ProjectIdentityStatus.DIFFERENT_PROJECT,),
    )
    seed = _set_preview_canonical_states_equal(seed)
    main_resolve = RecordingMainResolvePort()

    with pytest.raises(NoCanonicalChange):
        accept_submit_transaction(
            command=_accept_command(seed, idempotency_key="accept-key-noop-identity"),
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(seed.db_path),
            job_registry=_submit_job_registry(),
            main_resolve=main_resolve,
            preflight=_preflight(seed),
            now=TS1,
        )

    assert main_resolve.calls == 0
    _assert_t1_zero_writes(seed.db_path, seed, idempotency_key="accept-key-noop-identity")


def test_t1_identity_confirmation_precedes_submit_occupancy(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    first = accept_submit_transaction(
        command=_accept_command(seed, idempotency_key="accept-key-occupancy-winner"),
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        main_resolve=RecordingMainResolvePort(),
        preflight=_preflight(seed),
        now=TS1,
    )
    seed = _set_preview_identity_statuses(
        seed,
        (ProjectIdentityStatus.DIFFERENT_PROJECT,),
    )
    with ControlDbUnitOfWork(seed.db_path, read_only=True) as unit_of_work:
        workspace = unit_of_work.workspace.get_workspace(seed.workspace.workspace_id)
        assert workspace is not None
    seed = replace(seed, workspace=workspace)

    with pytest.raises(ProjectIdentityConfirmationRequired):
        accept_submit_transaction(
            command=_accept_command(
                seed,
                idempotency_key="accept-key-identity-before-occupancy",
            ),
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(seed.db_path),
            job_registry=_submit_job_registry(),
            main_resolve=RecordingMainResolvePort(),
            preflight=_preflight(seed),
            now=TS1,
        )

    with ControlDbUnitOfWork(seed.db_path, read_only=True) as unit_of_work:
        occupancy = unit_of_work.submission.get_repository_occupancy(seed.workspace.repository_id)
        attempts = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM submit_attempt_records"
        ).fetchone()[0]
    assert occupancy is not None
    assert occupancy.submit_attempt_id == first.submit_attempt_id
    assert attempts == 1


def test_t1_replay_rechecks_current_permission_and_exact_scope(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    command = _accept_command(seed, idempotency_key="accept-key-scope-replay")
    accept_submit_transaction(
        command=command,
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        main_resolve=RecordingMainResolvePort(),
        preflight=_preflight(seed),
        now=TS1,
    )

    denied_permission = replace(
        command,
        context=replace(command.context, permissions=frozenset({"workspace_read"})),
    )
    with pytest.raises(PermissionDenied):
        accept_submit_transaction(
            command=denied_permission,
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(seed.db_path),
            job_registry=_submit_job_registry(),
            main_resolve=RecordingMainResolvePort(),
            preflight=_preflight(seed),
            now=TS1,
        )

    wrong_scope = replace(
        command,
        context=replace(command.context, business_project_id="another-project"),
    )
    with pytest.raises(ScopeForbidden):
        accept_submit_transaction(
            command=wrong_scope,
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(seed.db_path),
            job_registry=_submit_job_registry(),
            main_resolve=RecordingMainResolvePort(),
            preflight=_preflight(seed),
            now=TS1,
        )


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
            canonical_business_digest=(
                seed.preview_result.canonical.modified_canonical_state_digest.value
            ),
            source_digest=seed.preview_result.digests.source_digest,
            snapshot_digest=seed.preview_result.digests.snapshot_digest,
            source_artifact_refs=("initial-1", "modified-1"),
            canonical_table_set_closure_ref=(
                seed.preview_result.canonical.canonical_table_set_closure_ref.artifact_id
            ),
            canonical_table_set_closure_digest=(
                seed.preview_result.canonical.canonical_table_set_closure_digest.value
            ),
            preview_ready_closure_ref=seed.preview_result.ready_closure_artifact_id,
            preview_ready_closure_digest=PREVIEW_READY_CLOSURE_DIGEST,
            canonicalization_manifest_ref=(
                seed.preview_result.canonical.canonicalization_manifest_ref.artifact_id
            ),
            canonicalization_manifest_digest=(
                seed.preview_result.canonical.canonicalization_manifest_digest.value
            ),
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
        main_resolve=RecordingMainResolvePort(),
        preflight=_preflight(first_seed),
        now=TS1,
    )

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        workspace = Workspace(
            workspace_id="ws-2",
            owner_actor_id="actor-2",
            gateway_device_external_key="device-1",
            business_project_id="project-1",
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
            main_resolve=RecordingMainResolvePort(),
            preflight=_preflight(second_seed),
            now=TS1,
        )


def _seed_effect_pending_attempt(
    db_path: Path,
    seed: SubmitSeed,
    *,
    baseline_head: BaselineHead | None = None,
    identity_confirmations: tuple[IdentityConfirmationRequest, ...] = (),
) -> SubmitAttempt:
    if baseline_head is None:
        from tests.support.baseline_fixtures import read_authoritative_baseline_head

        baseline_head = read_authoritative_baseline_head(db_path, seed.workspace.repository_id)
    accepted = accept_submit_transaction(
        command=_accept_command(
            seed,
            idempotency_key="accept-key-1",
            baseline_head=baseline_head,
            identity_confirmations=identity_confirmations,
        ),
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=baseline_head,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
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
            prepared_canonicalization_manifest_ref="manifest-1",
            prepared_canonicalization_manifest_digest=_SHA_MANIFEST,
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
    assert attempt.canonicalization_manifest_ref == (
        seed.preview_result.canonical.canonicalization_manifest_ref.artifact_id
    )
    assert attempt.canonicalization_manifest_digest == (
        seed.preview_result.canonical.canonicalization_manifest_digest.value
    )
    assert attempt.prepared_canonicalization_manifest_ref == "manifest-1"
    assert attempt.prepared_canonicalization_manifest_digest == _SHA_MANIFEST
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
        projection = unit_of_work.review.get_projection("sub-1")
        events = unit_of_work.review.list_events("sub-1")
    assert submission is not None
    assert submission.submission_id == "sub-1"
    assert occupancy is not None
    assert occupancy.active_submission_id == "sub-1"
    assert repository_occupancy is None
    assert operation.status is OperationStatus.SUCCEEDED
    assert projection is not None
    assert projection.status is ReviewStatus.PENDING
    assert projection.optimistic_version == 0
    assert projection.latest_sequence == 0
    assert len(events) == 1
    assert events[0].sequence == 0
    assert events[0].event_kind is ReviewEventKind.SUBMISSION_FINALIZED


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
        event_rows = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM review_event_records WHERE submission_id = ?",
            ("sub-1",),
        ).fetchone()[0]
        projection_rows = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM review_projection_records WHERE submission_id = ?",
            ("sub-1",),
        ).fetchone()[0]
    assert rows == 1
    assert event_rows == 1
    assert projection_rows == 1


def test_t3_finalize_replay_fails_when_review_seed_missing(db_path: Path) -> None:
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
        unit_of_work.connection.execute(
            "DELETE FROM review_projection_records WHERE submission_id = ?",
            ("sub-1",),
        )
        unit_of_work.connection.execute(
            "DELETE FROM review_event_records WHERE submission_id = ?",
            ("sub-1",),
        )
    with ControlDbUnitOfWork(db_path) as unit_of_work, pytest.raises(ReviewIntegrityFailure):
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


def test_identity_confirmation_is_copied_from_attempt_to_submission(db_path: Path) -> None:
    finalize_db_path = db_path.with_name("identity-finalize-control.db")
    initialize_control_db(finalize_db_path)
    seed = _set_preview_identity_statuses(
        seed_submit_ready_workspace(finalize_db_path),
        (ProjectIdentityStatus.DIFFERENT_PROJECT,),
    )
    confirmation = IdentityConfirmationRequest(
        action=IdentityConfirmationAction.ACCEPT_DATASET_REPLACEMENT,
        assessment_set_digest=seed.preview_result.identity_assessment_set_digest.value,
        reason="accepted replacement for archive review",
    )
    attempt = _seed_effect_pending_attempt(
        finalize_db_path,
        seed,
        identity_confirmations=(confirmation,),
    )

    _finalize(finalize_db_path, attempt, seed)

    with ControlDbUnitOfWork(finalize_db_path, read_only=True) as unit_of_work:
        submission = unit_of_work.submission.get_submission("sub-1")
    assert submission is not None
    assert submission.identity_confirmations == attempt.identity_confirmations


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


def test_t1_main_resolve_runs_outside_writer_transaction(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    tracker = WriterLockTracker()
    resolve = RecordingMainResolvePort(tracker=tracker)
    accept_submit_transaction(
        command=_accept_command(seed, idempotency_key="accept-key-1"),
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_tracking_uow_factory(seed.db_path, tracker),
        job_registry=_submit_job_registry(),
        main_resolve=resolve,
        preflight=_preflight(seed),
        now=TS1,
    )
    assert resolve.calls == 1
    assert resolve.writer_open_during_calls == (False,)
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
        main_resolve=RecordingMainResolvePort(),
        preflight=_preflight(seed),
        now=TS1,
    )
    resolve = RecordingMainResolvePort()
    replay = accept_submit_transaction(
        command=command,
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        main_resolve=resolve,
        preflight=_preflight(seed),
        now=TS1,
    )
    assert replay.replay is True
    assert resolve.calls == 0


def test_t1_rejects_incomplete_submit_job_registry_without_writes(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    with pytest.raises(SubmitJobNotRegistered):
        accept_submit_transaction(
            command=_accept_command(seed, idempotency_key="accept-key-1"),
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(seed.db_path),
            job_registry=_prepare_only_registry(),
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
    with pytest.raises(WorkspaceVersionConflict):
        accept_submit_transaction(
            command=_accept_command(seed, idempotency_key="accept-key-1"),
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(seed.db_path),
            job_registry=_submit_job_registry(),
            main_resolve=RecordingMainResolvePort(),
            preflight=_preflight(seed),
            now=TS1,
        )
    with ControlDbUnitOfWork(seed.db_path, read_only=True) as unit_of_work:
        assert unit_of_work.submission.find_submit_idempotency(seed.workspace.workspace_id, "accept-key-1") is None
        assert unit_of_work.submission.get_workspace_occupancy(seed.workspace.workspace_id) is None


def test_t1_rejects_preview_built_with_another_projection_ruleset(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    resolve = RecordingMainResolvePort()
    preflight = replace(
        _preflight(seed),
        current_storage_projection_ruleset_digest="sha256:" + "0" * 64,
    )

    with pytest.raises(PreviewDerivedStale):
        accept_submit_transaction(
            command=_accept_command(seed, idempotency_key="accept-key-1"),
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(seed.db_path),
            job_registry=_submit_job_registry(),
            main_resolve=resolve,
            preflight=preflight,
            now=TS1,
        )

    assert resolve.calls == 0
    with ControlDbUnitOfWork(seed.db_path, read_only=True) as unit_of_work:
        assert unit_of_work.submission.find_submit_idempotency(
            seed.workspace.workspace_id,
            "accept-key-1",
        ) is None
        assert unit_of_work.submission.get_workspace_occupancy(seed.workspace.workspace_id) is None
        assert unit_of_work.submission.get_repository_occupancy(seed.workspace.repository_id) is None


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
    seed = _set_preview_canonical_states_equal(seed_submit_ready_workspace(db_path))
    tracker = WriterLockTracker()
    resolve = RecordingMainResolvePort(tracker=tracker)
    with pytest.raises(NoCanonicalChange):
        accept_submit_transaction(
            command=_accept_command(seed, idempotency_key="accept-key-1"),
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_tracking_uow_factory(seed.db_path, tracker),
            job_registry=_submit_job_registry(),
            main_resolve=resolve,
            preflight=_preflight(seed),
            now=TS1,
        )
    assert resolve.calls == 0
    assert tracker.writer_entries == 0
    assert tracker.active_uow_entries == 0
    assert tracker.factory_calls == (True,)
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
            canonical=replace(
                first_seed.preview_result.canonical,
                baseline_canonical_state_digest=(
                    first_seed.preview_result.canonical.modified_canonical_state_digest
                ),
            ),
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
    with pytest.raises(NoCanonicalChange):
        accept_submit_transaction(
            command=_accept_command(second_seed, idempotency_key="accept-key-2"),
            scope_resolution=FixedScopeResolutionPort(
                repository_id="repo-1",
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(db_path),
            job_registry=_submit_job_registry(),
            main_resolve=RecordingMainResolvePort(),
            preflight=_preflight(second_seed),
            now=TS1,
        )


def test_t1_no_canonical_change_precedes_closure_digest_conflict(db_path: Path) -> None:
    seed = _set_preview_canonical_states_equal(seed_submit_ready_workspace(db_path))
    with pytest.raises(NoCanonicalChange):
        accept_submit_transaction(
            command=_accept_command(seed, idempotency_key="accept-key-1"),
            scope_resolution=FixedScopeResolutionPort(
                repository_id=seed.workspace.repository_id,
                baseline_head=BASELINE_HEAD,
            ),
            unit_of_work_factory=_uow_factory(seed.db_path),
            job_registry=_submit_job_registry(),
            main_resolve=RecordingMainResolvePort(),
            preflight=AcceptSubmitPreflight(
                preview_ready_closure_digest="",
                preview_operation_id=seed.preview_operation_id,
                protected_artifact_refs=seed.protected_refs,
                current_storage_projection_ruleset_digest=(
                    seed.preview_result.canonical.storage_projection_ruleset_digest.value
                ),
            ),
            now=TS1,
        )


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
    _upsert_provisioned_mapping_row(db_path, baseline_head=None, enabled=False)


def _drift_repo_swap(db_path: Path) -> None:
    _upsert_provisioned_mapping_row(db_path, repository_id="repo-other", baseline_head=None)


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
            main_resolve=resolve,
            preflight=_preflight(seed),
            now=TS1,
        )
    _assert_t1_zero_writes(seed.db_path, seed, idempotency_key=idempotency_key)
    with ControlDbUnitOfWork(seed.db_path, read_only=True) as unit_of_work:
        row = unit_of_work.connection.execute(
            """
            SELECT repository_id, enabled
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
            main_resolve=RecordingMainResolvePort(),
            preflight=_preflight(seed),
            now=TS1,
        )
        assert winner.replay is False
        winner_attempt_id = winner.submit_attempt_id
        _drift_head_commit_only(seed.db_path)
        winner_submitted = True

    drift_resolve = DriftOnResolveMainResolvePort(on_resolve=on_resolve)
    result = accept_submit_transaction(
        command=command,
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        main_resolve=drift_resolve,
        preflight=_preflight(seed),
        now=TS1,
    )
    assert result.replay is True
    assert result.submit_attempt_id == winner_attempt_id
    assert drift_resolve.calls == 1

    with ControlDbUnitOfWork(seed.db_path, read_only=True) as unit_of_work:
        winner = unit_of_work.submission.get_submit_attempt(result.submit_attempt_id)
        assert winner is not None
        assert winner.state is SubmitAttemptState.PREPARED
        head_row = unit_of_work.connection.execute(
            """
            SELECT node.commit_id
            FROM baseline_head_records AS head
            INNER JOIN baseline_node_records AS node ON node.node_id = head.node_id
            WHERE head.repository_id = ?
            """,
            (seed.workspace.repository_id,),
        ).fetchone()
        assert head_row is not None
        assert head_row["commit_id"] == "commit-only-drift"
        assert unit_of_work.connection.execute("SELECT COUNT(*) FROM submit_attempt_records").fetchone()[0] == 1
