"""S2 pair binding, applicability validation and deterministic table planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias, cast

from gateway_shared_kernel import DigestRef, canonicalize_identifier

from gateway_backend.capabilities.comparison.contracts import (
    DEFAULT_CONTRACT_VERSIONS,
    ArtifactScope,
    BaselineReconstructionResult,
    BaselineReconstructionStatus,
    BoundSnapshotInput,
    ComparisonMode,
    ComparisonOptions,
    ComparisonPlan,
    ComparisonTablePolicy,
    ContinuationAction,
    FailedResult,
    IdentityApplicability,
    IdentityGateBlockedResult,
    IdentityStatus,
    InitialSnapshotResult,
    InputCompleteness,
    PairExecutionInput,
    PairExecutionResult,
    PairResultStatus,
    PairRole,
    PairViewKind,
    ProjectIdentityAssessment,
    TableComparisonTask,
    TrustedFlowApplicabilityBinding,
    UnverifiableContinuationBinding,
    ContractVersions,
    DatasetReplacementResult,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    SnapshotTable,
    SnapshotTableDescriptor,
)


PairBindingOutcome: TypeAlias = PairExecutionInput | FailedResult
PairPlanningOutcome: TypeAlias = ComparisonPlan | PairExecutionResult


@dataclass(frozen=True, slots=True)
class _AssessmentState:
    status: IdentityStatus
    assessment_digest: DigestRef
    requires_continuation_confirmation: bool
    requires_submit_confirmation: bool


def bind_pair_input(
    *,
    pair_id: str,
    view_kind: PairViewKind,
    current: BoundSnapshotInput,
    before: BoundSnapshotInput | None = None,
    input_completeness: InputCompleteness = InputCompleteness.FULL,
    pair_role: PairRole | None = None,
    artifact_scope: ArtifactScope | None = None,
    identity_assessment: ProjectIdentityAssessment | None = None,
    continuation_binding: UnverifiableContinuationBinding | None = None,
    comparison_options: ComparisonOptions = (),
    contract_versions: ContractVersions = DEFAULT_CONTRACT_VERSIONS,
    baseline_reconstruction: BaselineReconstructionResult | None = None,
    trusted_flow_binding: TrustedFlowApplicabilityBinding | None = None,
    table_policies: tuple[ComparisonTablePolicy, ...] = (),
) -> PairBindingOutcome:
    """Bind an immutable pair and derive its mode/applicability before reader access.

    Shape errors that cannot be represented by a valid result envelope raise ``ValueError``. Valid
    pair identities with a missing baseline return ``FailedResult`` so callers can publish a
    terminal diagnostic without opening either side.
    """

    _require_pair_id(pair_id)
    if type(view_kind) is not PairViewKind:
        return _failed(pair_id, "PAIR_VIEW_KIND_INVALID")
    if type(current) is not BoundSnapshotInput:
        return _failed(pair_id, "CURRENT_SNAPSHOT_BINDING_INVALID")
    if before is not None and type(before) is not BoundSnapshotInput:
        return _failed(pair_id, "BEFORE_SNAPSHOT_BINDING_INVALID")
    if type(input_completeness) is not InputCompleteness:
        return _failed(pair_id, "INPUT_COMPLETENESS_INVALID")
    if artifact_scope is not None and type(artifact_scope) is not ArtifactScope:
        return _failed(pair_id, "ARTIFACT_SCOPE_INVALID")
    if continuation_binding is not None and type(continuation_binding) is not UnverifiableContinuationBinding:
        return _failed(pair_id, "CONTINUATION_BINDING_INVALID")
    if trusted_flow_binding is not None and type(trusted_flow_binding) is not TrustedFlowApplicabilityBinding:
        return _failed(pair_id, "FLOW_APPLICABILITY_BINDING_INVALID")
    if type(table_policies) is not tuple or any(
        type(item) is not ComparisonTablePolicy for item in table_policies
    ):
        return _failed(pair_id, "TABLE_POLICY_INVALID")

    role = _resolve_role(view_kind, pair_role)
    if role is None:
        return _failed(pair_id, "PAIR_ROLE_REQUIRED")

    if view_kind is PairViewKind.INITIAL_SNAPSHOT:
        if input_completeness is not InputCompleteness.FULL:
            return _failed(pair_id, "INITIAL_SNAPSHOT_FORBIDS_MODIFIED_ONLY")
        if before is not None or artifact_scope is not None:
            return _failed(pair_id, "INITIAL_SNAPSHOT_BEFORE_OR_SCOPE_PRESENT")
        if identity_assessment is not None or continuation_binding is not None:
            return _failed(pair_id, "INITIAL_SNAPSHOT_IDENTITY_INPUT_PRESENT")
        if baseline_reconstruction is not None or trusted_flow_binding is not None:
            return _failed(pair_id, "INITIAL_SNAPSHOT_FLOW_BINDING_PRESENT")
        return PairExecutionInput(
            pair_id=pair_id,
            view_kind=view_kind,
            pair_role=role,
            before=None,
            current=current,
            input_completeness=input_completeness,
            comparison_mode=None,
            artifact_scope=None,
            identity_applicability=IdentityApplicability.NOT_APPLICABLE,
            comparison_options=comparison_options,
            contract_versions=contract_versions,
            table_policies=table_policies,
        )

    if view_kind is PairViewKind.PAIR_COMPARISON:
        if trusted_flow_binding is not None:
            return _failed(pair_id, "PAIR_COMPARISON_TRUSTED_FLOW_BINDING_PRESENT")
        if role not in {PairRole.BASELINE_TO_INITIAL, PairRole.INITIAL_TO_MODIFIED}:
            return _failed(pair_id, "PAIR_ROLE_INVALID")
        if artifact_scope is None:
            return _failed(pair_id, "PAIR_ARTIFACT_SCOPE_REQUIRED")
        if input_completeness is InputCompleteness.MODIFIED_ONLY:
            if role is not PairRole.INITIAL_TO_MODIFIED:
                return _failed(pair_id, "MODIFIED_ONLY_ROLE_INVALID")
            if baseline_reconstruction is None:
                return _failed(pair_id, "BASELINE_RECONSTRUCTION_REQUIRED")
            if baseline_reconstruction.status is BaselineReconstructionStatus.UNAVAILABLE:
                return _failed(pair_id, "BASELINE_PAIR_UNAVAILABLE")
            if baseline_reconstruction.baseline is None:
                return _failed(pair_id, "BASELINE_RECONSTRUCTION_EMPTY")
            before = baseline_reconstruction.baseline
        elif baseline_reconstruction is not None:
            return _failed(pair_id, "FULL_FORBIDS_BASELINE_RECONSTRUCTION_RESULT")
        if before is None:
            return _failed(pair_id, "PAIR_BEFORE_REQUIRED")

        assessment = _validate_assessment(
            identity_assessment,
            before_snapshot_digest=before.snapshot.snapshot_digest,
            current_snapshot_digest=current.snapshot.snapshot_digest,
        )
        if assessment is None:
            return _failed(pair_id, "IDENTITY_ASSESSMENT_INVALID")
        mode = (
            ComparisonMode.DATASET_REPLACEMENT
            if assessment.status is IdentityStatus.DIFFERENT_PROJECT
            else ComparisonMode.DETAILED
        )
        if assessment.status is IdentityStatus.UNVERIFIABLE:
            if not assessment.requires_continuation_confirmation:
                return _failed(pair_id, "UNVERIFIABLE_CONTINUATION_FLAG_INVALID")
        elif assessment.requires_continuation_confirmation:
            return _failed(pair_id, "CONTINUATION_FLAG_INVALID")
        if continuation_binding is not None and assessment.status is not IdentityStatus.UNVERIFIABLE:
            return _failed(pair_id, "CONTINUATION_FOR_NON_UNVERIFIABLE")

        return PairExecutionInput(
            pair_id=pair_id,
            view_kind=view_kind,
            pair_role=role,
            before=before,
            current=current,
            input_completeness=input_completeness,
            comparison_mode=mode,
            artifact_scope=artifact_scope,
            identity_applicability=IdentityApplicability.REQUIRED,
            identity_assessment=identity_assessment,
            continuation_binding=continuation_binding,
            comparison_options=comparison_options,
            contract_versions=contract_versions,
            table_policies=table_policies,
        )

    if input_completeness is not InputCompleteness.FULL:
        return _failed(pair_id, "REPLAY_FORBIDS_MODIFIED_ONLY")
    if before is None:
        return _failed(pair_id, "REPLAY_BEFORE_REQUIRED")
    if artifact_scope is None:
        return _failed(pair_id, "REPLAY_ARTIFACT_SCOPE_REQUIRED")
    if identity_assessment is not None or continuation_binding is not None:
        return _failed(pair_id, "REPLAY_IDENTITY_INPUT_PRESENT")
    if baseline_reconstruction is not None:
        return _failed(pair_id, "REPLAY_BASELINE_RECONSTRUCTION_PRESENT")
    if trusted_flow_binding is None or trusted_flow_binding.view_kind is not view_kind:
        return _failed(pair_id, "TRUSTED_APPLICABILITY_BINDING_REQUIRED")
    expected_role = PairRole.HISTORY if view_kind is PairViewKind.HISTORY else PairRole.ARCHIVE_REPLAY
    if role is not expected_role:
        return _failed(pair_id, "REPLAY_PAIR_ROLE_INVALID")

    return PairExecutionInput(
        pair_id=pair_id,
        view_kind=view_kind,
        pair_role=role,
        before=before,
        current=current,
        input_completeness=input_completeness,
        comparison_mode=ComparisonMode.DETAILED,
        artifact_scope=artifact_scope,
        identity_applicability=IdentityApplicability.NOT_APPLICABLE,
        comparison_options=comparison_options,
        contract_versions=contract_versions,
        trusted_flow_binding=trusted_flow_binding,
        table_policies=table_policies,
    )


def plan_pair(pair_input: PairBindingOutcome) -> PairPlanningOutcome:
    """Return a terminal gate result or a deterministic detailed table plan.

    This function only reads descriptors and already-bound table objects. It never calls any reader
    lifecycle or row iteration method.
    """

    if isinstance(pair_input, FailedResult):
        return pair_input
    if type(pair_input) is not PairExecutionInput:
        raise TypeError("pair_input must be PairExecutionInput or FailedResult")

    if pair_input.view_kind is PairViewKind.INITIAL_SNAPSHOT:
        return InitialSnapshotResult(
            pair_id=pair_input.pair_id,
            status=PairResultStatus.NOT_APPLICABLE,
        )

    assessment_state: _AssessmentState | None = None
    if pair_input.identity_applicability is IdentityApplicability.REQUIRED:
        assert pair_input.before is not None
        assessment_state = _validate_assessment(
            pair_input.identity_assessment,
            before_snapshot_digest=pair_input.before.snapshot.snapshot_digest,
            current_snapshot_digest=pair_input.current.snapshot.snapshot_digest,
        )
        if assessment_state is None:
            return _failed(pair_input.pair_id, "IDENTITY_ASSESSMENT_INVALID")
        if assessment_state.status is IdentityStatus.DIFFERENT_PROJECT:
            return DatasetReplacementResult(
                pair_id=pair_input.pair_id,
                status=PairResultStatus.CHANGED,
                diagnostics=("PROJECT_IDENTITY_DIFFERENT_PROJECT",),
            )
        if assessment_state.status is IdentityStatus.UNVERIFIABLE:
            continuation_diagnostic = _continuation_diagnostic(
                pair_input,
                assessment_state,
            )
            if continuation_diagnostic is not None:
                return IdentityGateBlockedResult(
                    pair_id=pair_input.pair_id,
                    status=PairResultStatus.DEGRADED,
                    diagnostics=(continuation_diagnostic,),
                )

    assert pair_input.before is not None
    tasks = _build_tasks(
        before=pair_input.before,
        current=pair_input.current,
        artifact_scope=cast(ArtifactScope, pair_input.artifact_scope),
        table_policies=pair_input.table_policies,
    )
    identity_status = (
        IdentityStatus.NOT_APPLICABLE
        if pair_input.identity_applicability is IdentityApplicability.NOT_APPLICABLE
        else cast(_AssessmentState, assessment_state).status
    )
    assessment_digest = None if assessment_state is None else assessment_state.assessment_digest
    diagnostics: tuple[str, ...] = ()
    if assessment_state is not None and assessment_state.status is IdentityStatus.UNVERIFIABLE:
        diagnostics = ("PROJECT_IDENTITY_UNVERIFIABLE",)
    return ComparisonPlan(
        pair_id=pair_input.pair_id,
        view_kind=pair_input.view_kind,
        pair_role=pair_input.pair_role,
        before=pair_input.before,
        current=pair_input.current,
        comparison_mode=ComparisonMode.DETAILED,
        artifact_scope=cast(ArtifactScope, pair_input.artifact_scope),
        identity_status=identity_status,
        assessment_digest=assessment_digest,
        tasks=tasks,
        diagnostics=diagnostics,
        comparison_options=pair_input.comparison_options,
        contract_versions=pair_input.contract_versions,
    )


def _build_tasks(
    *,
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    artifact_scope: ArtifactScope,
    table_policies: tuple[ComparisonTablePolicy, ...],
) -> tuple[TableComparisonTask, ...]:
    before_descriptors = _descriptor_map(before)
    current_descriptors = _descriptor_map(current)
    before_tables = _table_map(before)
    current_tables = _table_map(current)
    policy_map = {policy.table_name: policy for policy in table_policies}
    table_names = sorted(before_descriptors.keys() | current_descriptors.keys())
    return tuple(
        TableComparisonTask(
            table_name=table_name,
            before_descriptor=before_descriptors.get(table_name),
            current_descriptor=current_descriptors.get(table_name),
            before_table=before_tables.get(table_name),
            current_table=current_tables.get(table_name),
            artifact_scope=artifact_scope,
            policy=policy_map.get(table_name, ComparisonTablePolicy(table_name=table_name)),
        )
        for table_name in table_names
    )


def _descriptor_map(bound: BoundSnapshotInput) -> dict[str, SnapshotTableDescriptor]:
    return {
        canonicalize_identifier(table.table_name): table
        for table in bound.summary.tables
    }


def _table_map(bound: BoundSnapshotInput) -> dict[str, SnapshotTable]:
    if bound.table_set is None:
        return {}
    return {
        canonicalize_identifier(table.descriptor.table_name): table
        for table in bound.table_set.tables
    }


def _resolve_role(view_kind: PairViewKind, role: PairRole | None) -> PairRole | None:
    if role is not None:
        if type(role) is not PairRole:
            return None
        return role
    if view_kind is PairViewKind.INITIAL_SNAPSHOT:
        return PairRole.INITIAL_SNAPSHOT
    if view_kind is PairViewKind.HISTORY:
        return PairRole.HISTORY
    if view_kind is PairViewKind.ARCHIVE_REPLAY:
        return PairRole.ARCHIVE_REPLAY
    return None


def _validate_assessment(
    assessment: ProjectIdentityAssessment | None,
    *,
    before_snapshot_digest: DigestRef,
    current_snapshot_digest: DigestRef,
) -> _AssessmentState | None:
    if assessment is None:
        return None
    try:
        schema_version = getattr(assessment, "schema_version")
        rule_version = getattr(assessment, "rule_version")
        before_digest = getattr(assessment, "before_snapshot_digest")
        current_digest = getattr(assessment, "current_snapshot_digest")
        status = getattr(assessment, "status")
        comparable_columns = getattr(assessment, "comparable_columns")
        before_rows = getattr(assessment, "before_row_count")
        current_rows = getattr(assessment, "current_row_count")
        before_distinct = getattr(assessment, "before_distinct_entry_count")
        current_distinct = getattr(assessment, "current_distinct_entry_count")
        matched = getattr(assessment, "matched_entry_count")
        before_entry_digest = getattr(assessment, "before_entry_set_digest")
        current_entry_digest = getattr(assessment, "current_entry_set_digest")
        assessment_digest = getattr(assessment, "assessment_digest")
        diagnostics = getattr(assessment, "diagnostics")
        requires_continuation = getattr(assessment, "requires_continuation_confirmation")
        requires_submit = getattr(assessment, "requires_submit_confirmation")
    except AttributeError:
        return None
    if schema_version != "project-identity-assessment/v1" or rule_version != "version-manager-overlap/v1":
        return None
    if before_digest != before_snapshot_digest or current_digest != current_snapshot_digest:
        return None
    if type(status) is not IdentityStatus:
        return None
    if type(comparable_columns) is not tuple or any(
        type(column) is not str or column == "" for column in comparable_columns
    ):
        return None
    if len(set(comparable_columns)) != len(comparable_columns):
        return None
    if any(type(value) is not int or value < 0 for value in (before_rows, current_rows, before_distinct, current_distinct, matched)):
        return None
    if before_entry_digest is not None and type(before_entry_digest) is not DigestRef:
        return None
    if current_entry_digest is not None and type(current_entry_digest) is not DigestRef:
        return None
    if type(assessment_digest) is not DigestRef:
        return None
    if type(diagnostics) is not tuple:
        return None
    if type(requires_continuation) is not bool or type(requires_submit) is not bool:
        return None
    return _AssessmentState(
        status=status,
        assessment_digest=assessment_digest,
        requires_continuation_confirmation=requires_continuation,
        requires_submit_confirmation=requires_submit,
    )


def _continuation_diagnostic(
    pair_input: PairExecutionInput,
    assessment: _AssessmentState,
) -> str | None:
    binding = pair_input.continuation_binding
    if binding is None:
        return "PROJECT_IDENTITY_UNVERIFIABLE"
    if binding.action is not ContinuationAction.ALLOW_DETAILED_ON_UNVERIFIABLE:
        return "CONTINUATION_ACTION_INVALID"
    if binding.pair_id != pair_input.pair_id:
        return "CONTINUATION_PAIR_MISMATCH"
    assert pair_input.before is not None
    if binding.before_snapshot_digest != pair_input.before.snapshot.snapshot_digest:
        return "CONTINUATION_BEFORE_SNAPSHOT_MISMATCH"
    if binding.current_snapshot_digest != pair_input.current.snapshot.snapshot_digest:
        return "CONTINUATION_CURRENT_SNAPSHOT_MISMATCH"
    if binding.assessment_digest != assessment.assessment_digest:
        return "CONTINUATION_ASSESSMENT_MISMATCH"
    if binding.assessment_set_digest is None:
        return "CONTINUATION_ASSESSMENT_SET_MISSING"
    if not assessment.requires_continuation_confirmation:
        return "CONTINUATION_NOT_REQUIRED"
    return None


def _require_pair_id(pair_id: str) -> None:
    if type(pair_id) is not str or pair_id == "":
        raise ValueError("pair_id must be a non-empty string")
    if pair_id.startswith("/") or "\\" in pair_id or "\x00" in pair_id:
        raise ValueError("pair_id must not be a path-shaped identity")


def _failed(pair_id: str, diagnostic: str) -> FailedResult:
    return FailedResult(
        pair_id=pair_id,
        status=PairResultStatus.FAILED,
        diagnostics=(diagnostic,),
    )
