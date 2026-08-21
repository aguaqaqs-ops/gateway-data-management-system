"""S2 pair binding, identity applicability and deterministic planning tests."""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache

import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.capabilities.comparison import (
    ArtifactScope,
    BaselineReconstructionResult,
    BaselineReconstructionStatus,
    BoundSnapshotInput,
    ComparisonPlan,
    ContinuationAction,
    DatasetReplacementResult,
    FailedResult,
    IdentityGateBlockedResult,
    IdentityStatus,
    InitialSnapshotResult,
    InputCompleteness,
    PairResultKind,
    PairResultStatus,
    PairRole,
    PairViewKind,
    TableComparisonTask,
    TrustedFlowApplicabilityBinding,
    UnverifiableContinuationBinding,
    bind_pair_input,
    plan_pair,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationPolicy,
    SnapshotTable,
    SnapshotTableSet,
)
from tests.support.snapshot_materialization import materialize_sql, parse_fixture

pytestmark = pytest.mark.unit

_ASSESSMENT_DIGEST = raw_blob_digest(b"assessment")
_ASSESSMENT_SET_DIGEST = raw_blob_digest(b"assessment-set")
_FLOW_DIGEST = raw_blob_digest(b"trusted-flow")

PAIR_APPLICABILITY_CASES = (
    ("initial", PairViewKind.INITIAL_SNAPSHOT, PairRole.INITIAL_SNAPSHOT),
    ("history", PairViewKind.HISTORY, PairRole.HISTORY),
    ("archive", PairViewKind.ARCHIVE_REPLAY, PairRole.ARCHIVE_REPLAY),
)
IDENTITY_GATE_CASES = (
    ("different", IdentityStatus.DIFFERENT_PROJECT, PairResultKind.DATASET_REPLACEMENT),
    ("unverifiable", IdentityStatus.UNVERIFIABLE, PairResultKind.IDENTITY_GATE_BLOCKED),
)


@dataclass(frozen=True, slots=True)
class _Assessment:
    schema_version: str
    rule_version: str
    before_snapshot_digest: DigestRef
    current_snapshot_digest: DigestRef
    status: IdentityStatus
    comparable_columns: tuple[str, ...] = ()
    before_row_count: int = 0
    current_row_count: int = 0
    before_distinct_entry_count: int = 0
    current_distinct_entry_count: int = 0
    matched_entry_count: int = 0
    before_entry_set_digest: DigestRef | None = None
    current_entry_set_digest: DigestRef | None = None
    assessment_digest: DigestRef = _ASSESSMENT_DIGEST
    diagnostics: tuple[object, ...] = ()
    requires_continuation_confirmation: bool = False
    requires_submit_confirmation: bool = False


@lru_cache(maxsize=4)
def _bound(relative_path: str = "sql/valid/s2-minimal-create-insert/input.sql") -> BoundSnapshotInput:
    result = materialize_sql(
        parse_fixture(relative_path),
        policy=MaterializationPolicy.READERS_REQUIRED,
    )
    assert result.snapshot is not None
    assert result.summary is not None
    assert result.table_set is not None
    return BoundSnapshotInput(result.snapshot, result.summary, result.table_set)


def _assessment(bound: BoundSnapshotInput, status: IdentityStatus) -> _Assessment:
    return _Assessment(
        schema_version="project-identity-assessment/v1",
        rule_version="version-manager-overlap/v1",
        before_snapshot_digest=bound.snapshot.snapshot_digest,
        current_snapshot_digest=bound.snapshot.snapshot_digest,
        status=status,
        requires_continuation_confirmation=status is IdentityStatus.UNVERIFIABLE,
    )


def _continuation(pair_id: str, bound: BoundSnapshotInput) -> UnverifiableContinuationBinding:
    return UnverifiableContinuationBinding(
        action=ContinuationAction.ALLOW_DETAILED_ON_UNVERIFIABLE,
        pair_id=pair_id,
        before_snapshot_digest=bound.snapshot.snapshot_digest,
        current_snapshot_digest=bound.snapshot.snapshot_digest,
        assessment_digest=_ASSESSMENT_DIGEST,
        assessment_set_digest=_ASSESSMENT_SET_DIGEST,
        policy_version="policy-v1",
    )


def _rename_tables(bound: BoundSnapshotInput, names: tuple[str, ...]) -> BoundSnapshotInput:
    assert bound.table_set is not None
    assert bound.summary.tables
    base_descriptor = bound.summary.tables[0]
    descriptors = tuple(
        replace(
            base_descriptor,
            table_name=name,
            display_table_name=name,
        )
        for name in names
    )
    tables = tuple(
        SnapshotTable(
            descriptor=descriptor,
            reader=bound.table_set.tables[0].reader,
            diagnostics=bound.table_set.tables[0].diagnostics,
            artifact=None,
            batch_reader=bound.table_set.tables[0].batch_reader,
        )
        for descriptor in descriptors
    )
    summary = replace(
        bound.summary,
        table_count=len(descriptors),
        tables=descriptors,
    )
    table_set = SnapshotTableSet(
        snapshot_id=bound.table_set.snapshot_id,
        snapshot_digest=bound.table_set.snapshot_digest,
        table_ruleset_version=bound.table_set.table_ruleset_version,
        tables=tables,
        diagnostics=bound.table_set.diagnostics,
    )
    return BoundSnapshotInput(bound.snapshot, summary, table_set)


def test_initial_snapshot_is_not_a_comparison_and_does_not_open_readers() -> None:
    current = _bound()
    bound = bind_pair_input(
        pair_id="initial-1",
        view_kind=PairViewKind.INITIAL_SNAPSHOT,
        current=current,
    )
    result = plan_pair(bound)

    assert isinstance(result, InitialSnapshotResult)
    assert result.kind is PairResultKind.INITIAL_SNAPSHOT
    assert result.status is PairResultStatus.NOT_APPLICABLE


@pytest.mark.parametrize(
    "label, view_kind, pair_role",
    PAIR_APPLICABILITY_CASES,
    ids=("initial", "history", "archive"),
)
def test_pair_applicability_case_table(
    label: str,
    view_kind: PairViewKind,
    pair_role: PairRole,
) -> None:
    del label
    current = _bound()
    if view_kind is PairViewKind.INITIAL_SNAPSHOT:
        pair_input = bind_pair_input(
            pair_id="applicability-initial",
            view_kind=view_kind,
            pair_role=pair_role,
            current=current,
        )
        result = plan_pair(pair_input)
        assert isinstance(result, InitialSnapshotResult)
        return

    flow = TrustedFlowApplicabilityBinding(
        view_kind=view_kind,
        binding_digest=_FLOW_DIGEST,
    )
    pair_input = bind_pair_input(
        pair_id=f"applicability-{view_kind.value.lower()}",
        view_kind=view_kind,
        pair_role=pair_role,
        before=current,
        current=current,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        trusted_flow_binding=flow,
    )
    result = plan_pair(pair_input)
    assert isinstance(result, ComparisonPlan)
    assert result.identity_status is IdentityStatus.NOT_APPLICABLE


def test_same_project_builds_sorted_tasks_without_opening_readers() -> None:
    before = _rename_tables(_bound(), ("zeta", "alpha"))
    current = _rename_tables(_bound(), ("alpha", "middle"))
    assessment = _Assessment(
        schema_version="project-identity-assessment/v1",
        rule_version="version-manager-overlap/v1",
        before_snapshot_digest=before.snapshot.snapshot_digest,
        current_snapshot_digest=current.snapshot.snapshot_digest,
        status=IdentityStatus.SAME_PROJECT,
    )
    bound = bind_pair_input(
        pair_id="pair-1",
        view_kind=PairViewKind.PAIR_COMPARISON,
        pair_role=PairRole.INITIAL_TO_MODIFIED,
        before=before,
        current=current,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        identity_assessment=assessment,
    )
    result = plan_pair(bound)

    assert isinstance(result, ComparisonPlan)
    assert [task.table_name for task in result.tasks] == ["alpha", "middle", "zeta"]
    assert all(isinstance(task, TableComparisonTask) for task in result.tasks)
    assert result.identity_status is IdentityStatus.SAME_PROJECT


def test_different_project_short_circuits_detailed_planner() -> None:
    before = _bound()
    current = _bound()
    assessment = _assessment(before, IdentityStatus.DIFFERENT_PROJECT)
    bound = bind_pair_input(
        pair_id="replacement-1",
        view_kind=PairViewKind.PAIR_COMPARISON,
        pair_role=PairRole.BASELINE_TO_INITIAL,
        before=before,
        current=current,
        artifact_scope=ArtifactScope.UPDATE_ONLY,
        identity_assessment=assessment,
    )

    result = plan_pair(bound)
    assert isinstance(result, DatasetReplacementResult)
    assert result.kind is PairResultKind.DATASET_REPLACEMENT
    assert result.facts is None or result.facts.records_ref is None
    assert result.records_closure is None


@pytest.mark.parametrize(
    "label, status, expected_kind",
    IDENTITY_GATE_CASES,
    ids=("different", "unverifiable"),
)
def test_identity_gate_case_table_is_flow_neutral(
    label: str,
    status: IdentityStatus,
    expected_kind: PairResultKind,
) -> None:
    del label
    bound = _bound()
    pair_input = bind_pair_input(
        pair_id=f"identity-case-{status.value.lower()}",
        view_kind=PairViewKind.PAIR_COMPARISON,
        pair_role=PairRole.INITIAL_TO_MODIFIED,
        before=bound,
        current=bound,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        identity_assessment=_assessment(bound, status),
    )
    result = plan_pair(pair_input)
    assert not isinstance(result, ComparisonPlan)
    assert result.kind is expected_kind


def test_unverifiable_requires_revalidated_continuation_before_planning() -> None:
    bound = _bound()
    assessment = _assessment(bound, IdentityStatus.UNVERIFIABLE)
    blocked_input = bind_pair_input(
        pair_id="unverifiable-1",
        view_kind=PairViewKind.PAIR_COMPARISON,
        pair_role=PairRole.INITIAL_TO_MODIFIED,
        before=bound,
        current=bound,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        identity_assessment=assessment,
    )
    blocked = plan_pair(blocked_input)
    assert isinstance(blocked, IdentityGateBlockedResult)
    assert blocked.kind is PairResultKind.IDENTITY_GATE_BLOCKED

    continued_input = bind_pair_input(
        pair_id="unverifiable-1",
        view_kind=PairViewKind.PAIR_COMPARISON,
        pair_role=PairRole.INITIAL_TO_MODIFIED,
        before=bound,
        current=bound,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        identity_assessment=assessment,
        continuation_binding=_continuation("unverifiable-1", bound),
    )
    continued = plan_pair(continued_input)
    assert isinstance(continued, ComparisonPlan)
    assert continued.identity_status is IdentityStatus.UNVERIFIABLE
    assert continued.diagnostics == ("PROJECT_IDENTITY_UNVERIFIABLE",)


def test_continuation_digest_mismatch_remains_blocked() -> None:
    bound = _bound()
    assessment = _assessment(bound, IdentityStatus.UNVERIFIABLE)
    continuation = replace(
        _continuation("unverifiable-2", bound),
        pair_id="unverifiable-2",
        assessment_digest=raw_blob_digest(b"wrong-assessment"),
    )
    pair_input = bind_pair_input(
        pair_id="unverifiable-2",
        view_kind=PairViewKind.PAIR_COMPARISON,
        pair_role=PairRole.INITIAL_TO_MODIFIED,
        before=bound,
        current=bound,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        identity_assessment=assessment,
        continuation_binding=continuation,
    )
    result = plan_pair(pair_input)
    assert isinstance(result, IdentityGateBlockedResult)
    assert result.diagnostics == ("CONTINUATION_ASSESSMENT_MISMATCH",)


def test_modified_only_requires_available_pinned_baseline() -> None:
    current = _bound()
    unavailable = BaselineReconstructionResult(
        status=BaselineReconstructionStatus.UNAVAILABLE,
        diagnostics=("BASELINE_NOT_FOUND",),
    )
    result = bind_pair_input(
        pair_id="modified-only-1",
        view_kind=PairViewKind.PAIR_COMPARISON,
        pair_role=PairRole.INITIAL_TO_MODIFIED,
        current=current,
        input_completeness=InputCompleteness.MODIFIED_ONLY,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        identity_assessment=_assessment(current, IdentityStatus.SAME_PROJECT),
        baseline_reconstruction=unavailable,
    )
    assert isinstance(result, FailedResult)
    assert result.kind is PairResultKind.FAILED
    assert result.diagnostics == ("BASELINE_PAIR_UNAVAILABLE",)


def test_history_requires_trusted_not_applicable_binding() -> None:
    before = _bound()
    current = _bound()
    flow = TrustedFlowApplicabilityBinding(
        view_kind=PairViewKind.HISTORY,
        binding_digest=_FLOW_DIGEST,
    )
    pair_input = bind_pair_input(
        pair_id="history-1",
        view_kind=PairViewKind.HISTORY,
        pair_role=PairRole.HISTORY,
        before=before,
        current=current,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        trusted_flow_binding=flow,
    )
    result = plan_pair(pair_input)
    assert isinstance(result, ComparisonPlan)
    assert result.identity_status is IdentityStatus.NOT_APPLICABLE

    forged = bind_pair_input(
        pair_id="history-2",
        view_kind=PairViewKind.HISTORY,
        pair_role=PairRole.HISTORY,
        before=before,
        current=current,
        artifact_scope=ArtifactScope.ALL_CHANGES,
    )
    assert isinstance(forged, FailedResult)
    assert forged.diagnostics == ("TRUSTED_APPLICABILITY_BINDING_REQUIRED",)


def test_invalid_assessment_snapshot_binding_fails_before_planning() -> None:
    bound = _bound()
    assessment = replace(
        _assessment(bound, IdentityStatus.SAME_PROJECT),
        current_snapshot_digest=raw_blob_digest(b"wrong-current"),
    )
    result = bind_pair_input(
        pair_id="invalid-assessment-1",
        view_kind=PairViewKind.PAIR_COMPARISON,
        pair_role=PairRole.INITIAL_TO_MODIFIED,
        before=bound,
        current=bound,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        identity_assessment=assessment,
    )
    assert isinstance(result, FailedResult)
    assert result.diagnostics == ("IDENTITY_ASSESSMENT_INVALID",)
