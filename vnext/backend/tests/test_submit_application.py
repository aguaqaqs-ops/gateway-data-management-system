"""AcceptSubmit application validation and in-memory fake harness tests."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from typing import Any

import pytest

from gateway_backend.application.submission.accept import validate_accept_submit
from gateway_backend.application.submission.abort import validate_abort_proof
from gateway_backend.application.submission.contracts import (
    AcceptSubmitCommand,
    AcceptSubmitValidationResult,
    FinalizeSubmitCommand,
    MatchingAbortProof,
    MatchingFinalizeFacts,
    RepositoryOperationTerminalStatus,
    RepositorySubmitOccupancy,
    SubmitAcceptanceRecord,
    WorkspaceSubmitOccupancy,
    compute_new_accept_fingerprint,
)
from gateway_backend.application.submission.errors import (
    AbortProofNotSatisfied,
    FinalizeBindingMismatch,
    IdempotencyConflict,
    PreviewBindingConflict,
    PreviewDerivedStale,
    SubmitOccupancyConflict,
)
from gateway_backend.application.submission.finalize import (
    finalize_submit,
    validate_finalize_replay,
    validate_matching_result_for_finalize,
)
from gateway_backend.domain.workspace.errors import ScopeForbidden, WorkspaceNotOpen
from gateway_backend.domain.submission.models import (
    BackendArtifactRef,
    BuilderMutationPolicy,
    RepositoryArtifactRef,
    SubmitAttempt,
    SubmitAttemptState,
    Submission,
    SubmitTargetRef,
    SubmitUnknownTypePolicy,
    SubmitVerificationPolicy,
)
from gateway_backend.domain.workspace.models import (
    InputCompleteness,
    PreviewResult,
    PreviewResultDigests,
    SourceArtifactBinding,
    SourceArtifactRole,
    UploadRevision,
    Workspace,
    WorkspaceState,
)
from tests.support.preview_fixtures import make_preview_canonical_bindings
from tests.support.workspace_fixtures import (
    FixedScopeResolutionPort,
    InMemoryWorkspaceRepository,
    make_baseline_head,
    make_identity,
    make_not_applicable_preview_identity,
    seed_open_workspace,
)

pytestmark = pytest.mark.unit

TS0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
TS1 = datetime(2024, 6, 1, 12, 30, 0, tzinfo=UTC)

BASELINE_HEAD = make_baseline_head(version=3, commit_id="commit-base")
PREVIEW_READY_CLOSURE_DIGEST = "d-closure"


@dataclass
class FakeAbortEvidencePort:
    reject_reason: str | None = None
    stable_failure_code: str = "IMPORT_REJECTED"

    def resolve_stable_failure_code(
        self,
        *,
        repository_id: str,
        repository_operation_id: str,
    ) -> str:
        del repository_id, repository_operation_id
        return self.stable_failure_code

    def validate_matching_stable_failure(
        self,
        *,
        attempt: SubmitAttempt,
        proof: MatchingAbortProof,
    ) -> None:
        del attempt
        if self.reject_reason is not None:
            raise AbortProofNotSatisfied(self.reject_reason)
        if proof.terminal_status is not RepositoryOperationTerminalStatus.FAILED:
            raise AbortProofNotSatisfied("abort proof terminal status must be FAILED")


@dataclass
class RecordingMainResolvePort:
    commit_id: str = "commit-main"
    resolve_calls: int = 0

    def resolve_main_expected_commit(self, *, repository_id: str) -> str:
        del repository_id
        self.resolve_calls += 1
        return self.commit_id


@dataclass
class FakeSubmitOccupancyPort:
    workspace_occupancy: WorkspaceSubmitOccupancy | None = None
    repository_occupied: bool = False

    def get_workspace_occupancy(self, workspace_id: str) -> WorkspaceSubmitOccupancy | None:
        del workspace_id
        return self.workspace_occupancy

    def get_repository_occupancy(self, repository_id: str) -> RepositorySubmitOccupancy | None:
        del repository_id
        if not self.repository_occupied:
            return None
        return RepositorySubmitOccupancy(
            repository_id="repo-1",
            workspace_id="ws-other",
            submit_attempt_id="sa-other",
            business_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
            baseline_head_version=BASELINE_HEAD.baseline_head_version,
            acquired_at=TS0,
        )


class InMemorySubmissionRepository:
    def __init__(self) -> None:
        self._attempts: dict[str, SubmitAttempt] = {}
        self._idempotency: dict[tuple[str, str], SubmitAcceptanceRecord] = {}

    def find_submit_idempotency(
        self,
        workspace_id: str,
        idempotency_key: str,
    ) -> SubmitAcceptanceRecord | None:
        return self._idempotency.get((workspace_id, idempotency_key))

    def get_submit_attempt(self, submit_attempt_id: str) -> SubmitAttempt | None:
        return self._attempts.get(submit_attempt_id)

    def get_submission(self, submission_id: str) -> Submission | None:
        del submission_id
        return None

    def get_submission_by_attempt(self, submit_attempt_id: str) -> Submission | None:
        del submit_attempt_id
        return None

    def save_attempt_with_idempotency(
        self,
        *,
        attempt: SubmitAttempt,
        record: SubmitAcceptanceRecord,
    ) -> None:
        self._attempts[attempt.submit_attempt_id] = attempt
        self._idempotency[(record.workspace_id, record.idempotency_key)] = record


@dataclass
class SubmitApplicationHarness:
    workspace_repository: InMemoryWorkspaceRepository
    submission_repository: InMemorySubmissionRepository
    scope_resolution: FixedScopeResolutionPort
    occupancy: FakeSubmitOccupancyPort
    main_resolve: RecordingMainResolvePort

    def validate(self, command: AcceptSubmitCommand) -> AcceptSubmitValidationResult:
        preview = self.workspace_repository.get_preview_result(command.preview_result_id)
        if preview is None:
            raise PreviewBindingConflict("preview result is missing")
        return validate_accept_submit(
            command=command,
            scope_resolution=self.scope_resolution,
            workspace_repository=self.workspace_repository,
            submission_repository=self.submission_repository,
            occupancy=self.occupancy,
            main_resolve=self.main_resolve,
            current_storage_projection_ruleset_digest=(
                preview.canonical.storage_projection_ruleset_digest.value
            ),
            preview_ready_closure_digest=PREVIEW_READY_CLOSURE_DIGEST,
        )


def _preview_result(*, workspace_id: str, bundle_digest: str = "sha256:preview-canonical") -> PreviewResult:
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
            bundle_digest=bundle_digest,
        ),
        canonical=make_preview_canonical_bindings(),
        identity_assessment_set_digest=identity_digest,
        identity_pairs=identity_pairs,
        bundle_artifact_id="bundle-1",
        ready_closure_artifact_id="closure-1",
        operation_id="op-preview-1",
        created_at=TS1,
    )


def _seed_ready_workspace(
    repository: InMemoryWorkspaceRepository,
    *,
    bundle_digest: str = "sha256:preview-canonical",
) -> tuple[Workspace, UploadRevision, PreviewResult]:
    workspace = seed_open_workspace(repository, optimistic_version=1, generation=1)
    revision = UploadRevision(
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
    preview = _preview_result(workspace_id=workspace.workspace_id, bundle_digest=bundle_digest)
    repository.save_upload_revision(revision)
    repository.save_preview_result(preview)
    updated = replace(
        workspace,
        current_upload_revision_id=revision.upload_revision_id,
        current_preview_result_id=preview.preview_result_id,
    )
    repository.save_workspace(updated, expected_version=workspace.optimistic_version)
    return updated, revision, preview


def make_accept_command(*, idempotency_key: str) -> AcceptSubmitCommand:
    return AcceptSubmitCommand(
        context=make_identity(permissions=frozenset({"upload_submit_workspace", "workspace_read"})),
        workspace_id=WORKSPACE.workspace_id,
        expected_workspace_version=WORKSPACE.optimistic_version,
        upload_revision_id=PREVIEW_RESULT.upload_revision_id,
        preview_result_id=PREVIEW_RESULT.preview_result_id,
        generation=PREVIEW_RESULT.generation,
        expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
        idempotency_key=idempotency_key,
        options={},
    )


@pytest.fixture
def submit_application_harness() -> SubmitApplicationHarness:
    return make_submit_application_harness()


def make_submit_application_harness() -> SubmitApplicationHarness:
    workspace_repository = InMemoryWorkspaceRepository()
    workspace, _revision, preview = _seed_ready_workspace(workspace_repository)
    submission_repository = InMemorySubmissionRepository()
    global WORKSPACE, PREVIEW_RESULT
    WORKSPACE = workspace
    PREVIEW_RESULT = preview
    attempt = SubmitAttempt(
        submit_attempt_id="sa-1",
        workspace_id=workspace.workspace_id,
        workspace_generation=workspace.generation,
        upload_revision_id=preview.upload_revision_id,
        preview_result_id=preview.preview_result_id,
        repository_id=workspace.repository_id,
        business_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        business_baseline_commit_id=BASELINE_HEAD.business_baseline_commit_id,
        baseline_head_version=BASELINE_HEAD.baseline_head_version,
        repository_expected_commit_id="commit-main",
        canonical_business_digest=preview.canonical.modified_canonical_state_digest.value,
        source_digest=preview.digests.source_digest,
        snapshot_digest=preview.digests.snapshot_digest,
        source_artifact_refs=("initial-1", "modified-1"),
        canonical_table_set_closure_ref=(
            preview.canonical.canonical_table_set_closure_ref.artifact_id
        ),
        canonical_table_set_closure_digest=(
            preview.canonical.canonical_table_set_closure_digest.value
        ),
        canonicalization_manifest_ref=preview.canonical.canonicalization_manifest_ref.artifact_id,
        canonicalization_manifest_digest=preview.canonical.canonicalization_manifest_digest.value,
        preview_ready_closure_ref=preview.ready_closure_artifact_id,
        preview_ready_closure_digest=PREVIEW_READY_CLOSURE_DIGEST,
        repository_import_artifact_ref=None,
        repository_artifact_ref=None,
        repository_operation_id=None,
        repository_operation_evidence=None,
        requested_target_ref=SubmitTargetRef.MAIN,
        requested_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        requested_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        builder_mutation_policy=BuilderMutationPolicy.REBUILD_ALWAYS,
        accept_idempotency_key="accept-key-1",
        accept_request_fingerprint="sha256:pending",
        repository_upload_idempotency_key="p5b-upload-v1:abc",
        repository_import_idempotency_key="p5b-import-v1:abc",
        operation_id="op-submit-1",
        state=SubmitAttemptState.PREPARED,
        submission_id=None,
        optimistic_version=0,
        created_by="actor-1",
        created_at=TS0,
    )
    seeded_command = make_accept_command(idempotency_key="accept-key-1")
    seeded_fingerprint = compute_new_accept_fingerprint(
        command=seeded_command,
        workspace=workspace,
        preview_result=preview,
        upload_revision=_revision,
        baseline_head=BASELINE_HEAD,
        repository_expected_commit_id="commit-main",
        preview_ready_closure_digest=PREVIEW_READY_CLOSURE_DIGEST,
    )
    attempt = replace(attempt, accept_request_fingerprint=seeded_fingerprint)
    submission_repository.save_attempt_with_idempotency(
        attempt=attempt,
        record=SubmitAcceptanceRecord(
            workspace_id=workspace.workspace_id,
            idempotency_key="accept-key-1",
            request_fingerprint=seeded_fingerprint,
            submit_attempt_id=attempt.submit_attempt_id,
        ),
    )
    return SubmitApplicationHarness(
        workspace_repository=workspace_repository,
        submission_repository=submission_repository,
        scope_resolution=FixedScopeResolutionPort(
            repository_id=workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        occupancy=FakeSubmitOccupancyPort(),
        main_resolve=RecordingMainResolvePort(),
    )


WORKSPACE = seed_open_workspace(InMemoryWorkspaceRepository())
PREVIEW_RESULT = _preview_result(workspace_id=WORKSPACE.workspace_id)


def test_validate_accept_submit_accepts_current_preview_binding(
    submit_application_harness: SubmitApplicationHarness,
) -> None:
    result = submit_application_harness.validate(
        make_accept_command(idempotency_key="accept-key-new")
    )

    assert result.replay is False
    assert result.repository_expected_commit_id == "commit-main"
    assert result.canonical_business_digest == PREVIEW_RESULT.canonical.modified_canonical_state_digest.value
    assert result.accept_request_fingerprint.startswith("sha256:")


def test_validate_accept_submit_checks_idempotency_before_occupancy(
    submit_application_harness: SubmitApplicationHarness,
) -> None:
    harness = submit_application_harness
    harness.occupancy.workspace_occupancy = WorkspaceSubmitOccupancy(
        workspace_id=WORKSPACE.workspace_id,
        active_submit_attempt_id="sa-blocked",
        active_submission_id=None,
    )

    result = harness.validate(make_accept_command(idempotency_key="accept-key-1"))

    assert result.replay is True


def test_validate_accept_submit_rejects_workspace_occupancy_for_new_key(
    submit_application_harness: SubmitApplicationHarness,
) -> None:
    harness = submit_application_harness
    harness.occupancy.workspace_occupancy = WorkspaceSubmitOccupancy(
        workspace_id=WORKSPACE.workspace_id,
        active_submit_attempt_id="sa-blocked",
        active_submission_id=None,
    )

    with pytest.raises(SubmitOccupancyConflict, match="workspace submit occupancy"):
        harness.validate(make_accept_command(idempotency_key="accept-key-new"))


def test_validate_accept_submit_rejects_submission_pointer_occupancy_for_new_key(
    submit_application_harness: SubmitApplicationHarness,
) -> None:
    harness = submit_application_harness
    harness.occupancy.workspace_occupancy = WorkspaceSubmitOccupancy(
        workspace_id=WORKSPACE.workspace_id,
        active_submit_attempt_id=None,
        active_submission_id="sub-blocked",
    )

    with pytest.raises(SubmitOccupancyConflict, match="workspace submit occupancy"):
        harness.validate(make_accept_command(idempotency_key="accept-key-new"))


def test_validate_accept_submit_rejects_repository_occupancy_for_new_key(
    submit_application_harness: SubmitApplicationHarness,
) -> None:
    harness = submit_application_harness
    harness.occupancy.repository_occupied = True

    with pytest.raises(SubmitOccupancyConflict, match="repository submit occupancy"):
        harness.validate(make_accept_command(idempotency_key="accept-key-new"))


def test_validate_accept_submit_rejects_mismatched_scope_repository(
    submit_application_harness: SubmitApplicationHarness,
) -> None:
    harness = submit_application_harness
    harness.scope_resolution.repository_id = "repo-different"

    with pytest.raises(ScopeForbidden):
        harness.validate(make_accept_command(idempotency_key="accept-key-new"))


def test_validate_accept_submit_rejects_closed_workspace_for_new_key(
    submit_application_harness: SubmitApplicationHarness,
) -> None:
    harness = submit_application_harness
    current = harness.workspace_repository.get_workspace(WORKSPACE.workspace_id)
    assert current is not None
    closed = replace(current, state=WorkspaceState.CLOSED)
    harness.workspace_repository.save_workspace(
        closed,
        expected_version=current.optimistic_version,
    )

    with pytest.raises(WorkspaceNotOpen):
        harness.validate(make_accept_command(idempotency_key="accept-key-new"))


def test_validate_accept_submit_rejects_derived_stale_preview(
    submit_application_harness: SubmitApplicationHarness,
) -> None:
    harness = submit_application_harness
    harness.scope_resolution.baseline_head = make_baseline_head(version=4, commit_id="commit-base")
    command = AcceptSubmitCommand(
        context=make_identity(permissions=frozenset({"upload_submit_workspace"})),
        workspace_id=WORKSPACE.workspace_id,
        expected_workspace_version=WORKSPACE.optimistic_version,
        upload_revision_id=PREVIEW_RESULT.upload_revision_id,
        preview_result_id=PREVIEW_RESULT.preview_result_id,
        generation=PREVIEW_RESULT.generation,
        expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        expected_baseline_head_version=4,
        idempotency_key="accept-key-new",
        options={},
    )

    with pytest.raises(PreviewDerivedStale):
        harness.validate(command)


def test_validate_accept_submit_rejects_preview_binding_mismatch(
    submit_application_harness: SubmitApplicationHarness,
) -> None:
    harness = submit_application_harness
    command = AcceptSubmitCommand(
        context=make_identity(permissions=frozenset({"upload_submit_workspace"})),
        workspace_id=WORKSPACE.workspace_id,
        expected_workspace_version=WORKSPACE.optimistic_version,
        upload_revision_id="ur-missing",
        preview_result_id=PREVIEW_RESULT.preview_result_id,
        generation=PREVIEW_RESULT.generation,
        expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
        idempotency_key="accept-key-new",
        options={},
    )

    with pytest.raises(PreviewBindingConflict, match="upload_revision_id"):
        harness.validate(command)


def test_validate_accept_submit_replays_after_workspace_generation_change(
    submit_application_harness: SubmitApplicationHarness,
) -> None:
    harness = submit_application_harness
    bumped = replace(
        WORKSPACE,
        generation=WORKSPACE.generation + 1,
        optimistic_version=WORKSPACE.optimistic_version + 1,
        current_upload_revision_id="ur-2",
        current_preview_result_id="pr-2",
    )
    harness.workspace_repository.save_workspace(bumped, expected_version=WORKSPACE.optimistic_version)
    harness.main_resolve.resolve_calls = 0

    result = harness.validate(make_accept_command(idempotency_key="accept-key-1"))

    assert result.replay is True
    assert harness.main_resolve.resolve_calls == 0


def test_validate_accept_submit_conflicts_on_reused_key_with_different_body(
    submit_application_harness: SubmitApplicationHarness,
) -> None:
    harness = submit_application_harness
    command = replace(
        make_accept_command(idempotency_key="accept-key-1"),
        upload_revision_id="ur-changed",
    )

    with pytest.raises(IdempotencyConflict, match="accept-key-1"):
        harness.validate(command)


def test_validate_accept_submit_conflicts_on_tampered_idempotency_fingerprint(
    submit_application_harness: SubmitApplicationHarness,
) -> None:
    harness = submit_application_harness
    record = harness.submission_repository._idempotency[
        (WORKSPACE.workspace_id, "accept-key-1")
    ]
    harness.submission_repository._idempotency[
        (WORKSPACE.workspace_id, "accept-key-1")
    ] = replace(
        record,
        request_fingerprint="sha256:tampered",
    )

    with pytest.raises(IdempotencyConflict, match="accept-key-1"):
        harness.validate(make_accept_command(idempotency_key="accept-key-1"))


def _effect_pending_attempt_for_finalize() -> SubmitAttempt:
    backend_ref = BackendArtifactRef(
        artifact_id="backend-pkg-1",
        media_type="application/vnd.gateway.repository-import.v1+tar+zstd",
        size_bytes=10,
        raw_sha256="sha256:package",
    )
    repository_ref = RepositoryArtifactRef(
        artifact_id="repo-artifact-1",
        media_type="application/octet-stream",
        size_bytes=10,
        raw_sha256="sha256:repo",
    )
    return SubmitAttempt(
        submit_attempt_id="sa-1",
        workspace_id="ws-1",
        workspace_generation=1,
        upload_revision_id="ur-1",
        preview_result_id="pr-1",
        repository_id="repo-1",
        business_baseline_node_id="node-1",
        business_baseline_commit_id="commit-base",
        baseline_head_version=1,
        repository_expected_commit_id="commit-main",
        canonical_business_digest="sha256:canonical",
        source_digest="d-source",
        snapshot_digest="d-snapshot",
        source_artifact_refs=("source-1",),
        canonical_table_set_closure_ref="canonical-table-closure-1",
        canonical_table_set_closure_digest="sha256:canonical-table-closure",
        preview_ready_closure_ref="closure-1",
        preview_ready_closure_digest="d-closure",
        canonicalization_manifest_ref="manifest-1",
        canonicalization_manifest_digest="sha256:manifest",
        repository_import_artifact_ref=backend_ref,
        repository_artifact_ref=repository_ref,
        repository_operation_id="repo-op-1",
        repository_operation_evidence=None,
        requested_target_ref=SubmitTargetRef.MAIN,
        requested_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        requested_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        builder_mutation_policy=BuilderMutationPolicy.REBUILD_ALWAYS,
        accept_idempotency_key="accept-key-1",
        accept_request_fingerprint="sha256:fp",
        repository_upload_idempotency_key="p5b-upload-v1:abc",
        repository_import_idempotency_key="p5b-import-v1:abc",
        operation_id="op-1",
        state=SubmitAttemptState.EFFECT_PENDING,
        submission_id=None,
        optimistic_version=1,
        created_by="actor-1",
        created_at=TS0,
        prepared_canonicalization_manifest_ref="manifest-1",
        prepared_canonicalization_manifest_digest="sha256:manifest",
        effect_pending_at=TS0,
    )


def _matching_finalize_facts(**overrides: Any) -> MatchingFinalizeFacts:
    base = MatchingFinalizeFacts(
        repository_id="repo-1",
        repository_operation_id="repo-op-1",
        repository_commit_id="commit-new",
        repository_expected_parent_commit_id="commit-main",
        repository_artifact_id="repo-artifact-1",
        repository_import_artifact_raw_sha256="sha256:package",
        canonicalization_manifest_ref="manifest-1",
        canonicalization_manifest_digest="sha256:manifest",
        completed_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        completed_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        target_ref=SubmitTargetRef.MAIN,
    )
    return replace(base, **overrides) if overrides else base


FINALIZE_MATCHING_FAULTS = (
    ({"repository_operation_id": "repo-op-other"}, "repository operation identity does not match attempt"),
    ({"repository_id": "repo-other"}, "repository scope does not match attempt"),
    ({"repository_artifact_id": "repo-artifact-other"}, "repository artifact id does not match attempt checkpoint"),
)


def test_validate_matching_result_for_finalize_rejects_non_effect_pending_attempt() -> None:
    attempt = replace(
        _effect_pending_attempt_for_finalize(),
        state=SubmitAttemptState.FINALIZED,
        submission_id="sub-1",
        finalized_at=TS1,
    )
    facts = _matching_finalize_facts()

    with pytest.raises(FinalizeBindingMismatch, match="finalize requires EFFECT_PENDING attempt"):
        finalize_submit(
            command=FinalizeSubmitCommand(
                attempt=attempt,
                facts=facts,
                submission_id="sub-new",
                created_at=TS1,
            ),
            existing_submission=None,
        )


@pytest.mark.parametrize(("fact_overrides", "message"), FINALIZE_MATCHING_FAULTS)
def test_validate_matching_result_for_finalize_rejects_binding_faults(
    fact_overrides: dict[str, object],
    message: str,
) -> None:
    attempt = _effect_pending_attempt_for_finalize()
    facts = _matching_finalize_facts(**fact_overrides)

    with pytest.raises(FinalizeBindingMismatch, match=message):
        validate_matching_result_for_finalize(attempt=attempt, facts=facts)


def test_validate_matching_result_for_finalize_rejects_missing_operation_id() -> None:
    attempt = replace(_effect_pending_attempt_for_finalize(), repository_operation_id=None)
    facts = _matching_finalize_facts()

    with pytest.raises(FinalizeBindingMismatch, match="repository operation identity is missing"):
        validate_matching_result_for_finalize(attempt=attempt, facts=facts)


def test_validate_finalize_replay_rejects_mismatched_artifact_id() -> None:
    attempt = replace(
        _effect_pending_attempt_for_finalize(),
        state=SubmitAttemptState.FINALIZED,
        submission_id="sub-1",
        finalized_at=TS1,
    )
    submission = Submission(
        submission_id="sub-1",
        submit_attempt_id="sa-1",
        workspace_id="ws-1",
        workspace_generation=1,
        upload_revision_id="ur-1",
        preview_result_id="pr-1",
        repository_id="repo-1",
        based_on_baseline_node_id="node-1",
        business_baseline_commit_id="commit-base",
        repository_commit_id="commit-new",
        canonical_business_digest="sha256:canonical",
        source_artifact_refs=("source-1",),
        canonicalization_manifest_ref="manifest-1",
        canonicalization_manifest_digest="sha256:manifest",
        repository_import_artifact_raw_sha256="sha256:package",
        repository_artifact_id="repo-artifact-1",
        requested_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        completed_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        requested_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        target_ref=SubmitTargetRef.MAIN,
        created_by="actor-1",
        created_at=TS1,
    )
    facts = _matching_finalize_facts(repository_artifact_id="repo-artifact-other")

    with pytest.raises(FinalizeBindingMismatch, match="repository artifact id does not match attempt checkpoint"):
        validate_finalize_replay(attempt=attempt, submission=submission, facts=facts)


def test_validate_abort_proof_accepts_matching_failed_evidence() -> None:
    attempt = _effect_pending_attempt_for_finalize()
    proof = MatchingAbortProof(
        repository_id="repo-1",
        repository_operation_id="repo-op-1",
        terminal_status=RepositoryOperationTerminalStatus.FAILED,
        stable_failure_code="IMPORT_REJECTED",
    )

    validate_abort_proof(attempt=attempt, proof=proof, evidence=FakeAbortEvidencePort())


ABORT_PROOF_FAULTS = (
    (
        MatchingAbortProof(
            repository_id="repo-1",
            repository_operation_id="repo-op-other",
            terminal_status=RepositoryOperationTerminalStatus.FAILED,
            stable_failure_code="IMPORT_REJECTED",
        ),
        "abort proof repository operation identity must match attempt",
    ),
    (
        MatchingAbortProof(
            repository_id="repo-other",
            repository_operation_id="repo-op-1",
            terminal_status=RepositoryOperationTerminalStatus.FAILED,
            stable_failure_code="IMPORT_REJECTED",
        ),
        "abort proof repository scope must match attempt",
    ),
    (
        MatchingAbortProof(
            repository_id="repo-1",
            repository_operation_id="repo-op-1",
            terminal_status=RepositoryOperationTerminalStatus.FAILED,
            stable_failure_code="NOT_ALLOWED",
        ),
        "is not an allowed not-published stable failure",
    ),
)


@pytest.mark.parametrize(("proof", "message"), ABORT_PROOF_FAULTS)
def test_validate_abort_proof_rejects_identity_and_code_faults(
    proof: MatchingAbortProof,
    message: str,
) -> None:
    attempt = _effect_pending_attempt_for_finalize()

    with pytest.raises(AbortProofNotSatisfied, match=message):
        validate_abort_proof(attempt=attempt, proof=proof, evidence=FakeAbortEvidencePort())


def test_validate_abort_proof_requires_evidence_port_confirmation() -> None:
    attempt = _effect_pending_attempt_for_finalize()
    proof = MatchingAbortProof(
        repository_id="repo-1",
        repository_operation_id="repo-op-1",
        terminal_status=RepositoryOperationTerminalStatus.FAILED,
        stable_failure_code="IMPORT_REJECTED",
    )

    with pytest.raises(AbortProofNotSatisfied, match="matching evidence missing"):
        validate_abort_proof(
            attempt=attempt,
            proof=proof,
            evidence=FakeAbortEvidencePort(reject_reason="matching evidence missing"),
        )


def test_finalize_submit_replay_returns_existing_submission() -> None:
    attempt = replace(
        _effect_pending_attempt_for_finalize(),
        state=SubmitAttemptState.FINALIZED,
        submission_id="sub-1",
        finalized_at=TS1,
    )
    submission = Submission(
        submission_id="sub-1",
        submit_attempt_id="sa-1",
        workspace_id="ws-1",
        workspace_generation=1,
        upload_revision_id="ur-1",
        preview_result_id="pr-1",
        repository_id="repo-1",
        based_on_baseline_node_id="node-1",
        business_baseline_commit_id="commit-base",
        repository_commit_id="commit-new",
        canonical_business_digest="sha256:canonical",
        source_artifact_refs=("source-1",),
        canonicalization_manifest_ref="manifest-1",
        canonicalization_manifest_digest="sha256:manifest",
        repository_import_artifact_raw_sha256="sha256:package",
        repository_artifact_id="repo-artifact-1",
        requested_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        completed_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        requested_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        target_ref=SubmitTargetRef.MAIN,
        created_by="actor-1",
        created_at=TS1,
    )
    facts = _matching_finalize_facts()

    result = finalize_submit(
        command=FinalizeSubmitCommand(
            attempt=attempt,
            facts=facts,
            submission_id="sub-1",
            created_at=TS1,
        ),
        existing_submission=submission,
    )

    assert result.replay is True
    assert result.submission is submission
