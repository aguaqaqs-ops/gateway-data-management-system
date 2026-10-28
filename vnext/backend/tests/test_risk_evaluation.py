"""S2 bounded Risk evaluation, annotation artifact and closure tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore
from gateway_backend.capabilities.comparison.contracts import (
    ComparisonFacts,
    ComparisonMode,
    ComparisonRecord,
    ComparisonRecordKind,
    ComparisonRecordsClosure,
    ComparisonSummary,
    ComparisonSchemaChanges,
    ComparisonTableFact,
    ComparisonTableStatus,
    OrderedRecord,
    PairResultStatus,
    SchemaEvolution,
)
from gateway_backend.capabilities.risk_evaluation import (
    AnnotationDetailPolicy,
    RISK_ANNOTATION_CONTRACT_VERSION,
    RISK_CONTRACT_VERSION,
    RISK_MODEL_VERSION,
    RiskAnnotationClosure,
    RiskEvaluationInput,
    RiskEvaluationStatus,
    RiskExecutionContext,
    RiskExecutionPolicy,
    RiskLevel,
    RiskOptions,
    RiskEvaluationResult,
    RiskRecordsAccess,
    RiskReasonCode,
    V1_RISK_RULE_SPECS,
    RiskRulesetSnapshot,
    evaluate_risk,
    validate_risk_annotation_closure,
    validate_risk_annotation_documents,
)


_COMPARISON_DIGEST = raw_blob_digest(b"risk-s2-comparison")
_FACTS_DIGEST = raw_blob_digest(b"risk-s2-facts")
_S1B_GOLDEN = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "golden"
    / "risk"
    / "s1b"
    / "structural-risk.json"
)


def _s1b_risk_golden_case(name: str) -> dict[str, object]:
    document = json.loads(_S1B_GOLDEN.read_text(encoding="utf-8"))
    assert document["contract_version"] == RISK_CONTRACT_VERSION
    assert document["model_version"] == RISK_MODEL_VERSION
    return document["cases"][name]


def _s1b_risk_projection(
    result: RiskEvaluationResult,
    store: InMemoryArtifactStore,
) -> dict[str, object]:
    report = result.risk_report
    table_risks = () if report is None else report.tables
    evidence: object = []
    if result.annotation_artifacts:
        payload = json.loads(store.locate(result.annotation_artifacts[0].content_ref))
        evidence = payload["annotations"][0]["reasons"][0]["evidence"]
    return {
        "status": result.status.value,
        "risk_level": None if not table_risks else table_risks[0].risk_level.value,
        "risk_levels": [item.risk_level.value for item in table_risks],
        "reason_codes": (
            [] if not table_risks else [item.value for item in table_risks[0].reason_codes]
        ),
        "annotation_count": len(result.annotation_artifacts),
        "evidence": evidence,
    }


def _assert_s1b_risk_golden(
    name: str,
    result: RiskEvaluationResult,
    store: InMemoryArtifactStore,
) -> None:
    expected = _s1b_risk_golden_case(name)
    actual = _s1b_risk_projection(result, store)
    assert {key: actual[key] for key in expected} == expected


def _ruleset() -> RiskRulesetSnapshot:
    return RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS)


def _facts(
    table: ComparisonTableFact,
    *,
    diagnostics: tuple[str, ...] = (),
) -> ComparisonFacts:
    return ComparisonFacts(
        comparison_digest=_COMPARISON_DIGEST,
        facts_core_digest=_FACTS_DIGEST,
        comparison_contract_version="backend-vnext/comparison/v3",
        projection_contract_version="backend-vnext/comparison-projection/v1",
        scalar_encoding_version=1,
        before_snapshot_digest=raw_blob_digest(b"risk-s2-before"),
        current_snapshot_digest=raw_blob_digest(b"risk-s2-current"),
        comparison_mode=ComparisonMode.DETAILED,
        direction="BEFORE_TO_CURRENT",
        summary=ComparisonSummary(
            status=PairResultStatus.CHANGED,
            table_count=1,
            unchanged_table_count=0,
            changed_table_count=1,
            added_table_count=int(table.status is ComparisonTableStatus.ADDED_TABLE),
            deleted_table_count=int(table.status is ComparisonTableStatus.DELETED_TABLE),
            schema_changed_table_count=int(
                table.status
                in {ComparisonTableStatus.SCHEMA_CHANGED, ComparisonTableStatus.SCHEMA_ONLY_CHANGED}
            ),
            degraded_table_count=int(table.status is ComparisonTableStatus.DEGRADED),
            row_added_count=table.row_added_count,
            row_deleted_count=table.row_deleted_count,
            row_modified_count=table.row_modified_count,
            suppressed_added_count=table.suppressed_added_count,
            suppressed_deleted_count=table.suppressed_deleted_count,
            diagnostics_count=len(diagnostics),
        ),
        tables=(table,),
        diagnostics=diagnostics,
    )


def _evaluate(
    table: ComparisonTableFact,
    *,
    options: RiskOptions | None = None,
    store: InMemoryArtifactStore | None = None,
    policy: RiskExecutionPolicy | None = None,
    diagnostics: tuple[str, ...] = (),
    records_access: RiskRecordsAccess | None = None,
    context: RiskExecutionContext | None = None,
) -> RiskEvaluationResult:
    return evaluate_risk(
        RiskEvaluationInput(
            comparison_facts=_facts(table, diagnostics=diagnostics),
            risk_ruleset=_ruleset(),
            risk_options=options or RiskOptions(),
            records_access=records_access,
        ),
        artifact_store=store,
        execution_policy=policy or RiskExecutionPolicy(),
        execution_context=context,
    )


def test_structural_risk_publishes_annotation_and_valid_closure() -> None:
    store = InMemoryArtifactStore()
    result = _evaluate(
        ComparisonTableFact(
            table_name="orders",
            status=ComparisonTableStatus.ADDED_TABLE,
            row_count_current=3,
        ),
        store=store,
    )

    assert result.status is RiskEvaluationStatus.READY
    assert result.risk_evaluation is not None
    assert result.risk_report is not None
    assert result.risk_closure is not None
    assert result.risk_report.tables[0].risk_level is RiskLevel.MEDIUM_LOW
    assert result.risk_report.tables[0].reason_codes == (RiskReasonCode.TABLE_ADDED,)
    assert len(result.annotation_artifacts) == 1
    _assert_s1b_risk_golden("whole_table_added", result, store)
    annotation_payload = json.loads(store.locate(result.annotation_artifacts[0].content_ref))
    assert annotation_payload["annotations"][0]["reasons"][0]["evidence"] == [["row_count", 3]]
    validate_risk_annotation_closure(result.risk_closure, store)


def test_deleted_table_risk_evidence_includes_table_row_count() -> None:
    store = InMemoryArtifactStore()
    result = _evaluate(
        ComparisonTableFact(
            table_name="orders",
            status=ComparisonTableStatus.DELETED_TABLE,
            row_count_before=5,
        ),
        store=store,
    )

    assert result.risk_report is not None
    assert result.risk_report.tables[0].reason_codes == (RiskReasonCode.TABLE_DELETED,)
    assert len(result.annotation_artifacts) == 1
    _assert_s1b_risk_golden("whole_table_deleted", result, store)
    annotation_payload = json.loads(store.locate(result.annotation_artifacts[0].content_ref))
    assert annotation_payload["annotations"][0]["reasons"][0]["evidence"] == [["row_count", 5]]


def test_added_columns_do_not_emit_schema_change_risk() -> None:
    table = ComparisonTableFact(
        table_name="orders",
        status=ComparisonTableStatus.UNCHANGED,
        schema_changes=ComparisonSchemaChanges(
            current_only_columns=("note",),
            schema_evolution=SchemaEvolution.COLUMNS_ADDED,
        ),
    )

    result = _evaluate(table, store=InMemoryArtifactStore())

    assert result.status is RiskEvaluationStatus.READY
    assert result.risk_report is not None
    assert result.risk_report.tables == ()
    assert result.annotation_artifacts == ()
    _assert_s1b_risk_golden("added_columns_only", result, InMemoryArtifactStore())


def test_standard_rows_are_row_targeted_and_digest_is_stable() -> None:
    records = (
        ComparisonRecord(
            table_name="orders",
            record_kind=ComparisonRecordKind.ROW_MODIFIED,
            row_identity=DigestRef("sha256:" + "01" * 32),
            changed_columns=("amount",),
        ),
    )
    table = ComparisonTableFact(
        table_name="orders",
        status=ComparisonTableStatus.MODIFIED,
        row_modified_count=1,
        records=records,
    )
    first = _evaluate(table, store=InMemoryArtifactStore())
    second = _evaluate(table, store=InMemoryArtifactStore())

    assert first.status is RiskEvaluationStatus.READY
    assert first.risk_evaluation is not None
    assert second.risk_evaluation is not None
    assert first.risk_evaluation.risk_evaluation_digest == second.risk_evaluation.risk_evaluation_digest
    assert first.risk_report is not None
    assert first.risk_report.tables[0].risk_level is RiskLevel.MEDIUM_HIGH


@pytest.mark.parametrize(
    ("table", "diagnostics", "reason"),
    (
        (
            ComparisonTableFact(table_name="orders", status=ComparisonTableStatus.DEGRADED),
            (),
            RiskReasonCode.KEY_DEGRADED,
        ),
        (
            ComparisonTableFact(table_name="orders", status=ComparisonTableStatus.MODIFIED),
            ("ORDERED_DIFF_UNSUPPORTED",),
            RiskReasonCode.ORDERED_DIFF_UNSUPPORTED_REVIEW_REQUIRED,
        ),
        (
            ComparisonTableFact(table_name="orders", status=ComparisonTableStatus.MODIFIED),
            ("RISK_UNCOVERED_TARGET:future_family",),
            RiskReasonCode.UNKNOWN_CHANGE_TARGET,
        ),
    ),
)
def test_degraded_ordered_and_unknown_targets_are_review_required(
    table: ComparisonTableFact,
    diagnostics: tuple[str, ...],
    reason: RiskReasonCode,
) -> None:
    result = _evaluate(table, store=InMemoryArtifactStore(), diagnostics=diagnostics)

    assert result.status is RiskEvaluationStatus.READY
    assert result.risk_report is not None
    assert result.risk_report.tables[0].risk_level is RiskLevel.UNKNOWN
    assert reason in result.risk_report.tables[0].reason_codes
    if reason in {
        RiskReasonCode.KEY_DEGRADED,
        RiskReasonCode.ORDERED_DIFF_UNSUPPORTED_REVIEW_REQUIRED,
    }:
        assert result.risk_closure is not None
        assert result.risk_closure.entries[0].artifact is None


def test_composite_signal_collapses_visible_changes_to_one_unknown_annotation() -> None:
    result = _evaluate(
        ComparisonTableFact(
            table_name="composite_signal_point",
            status=ComparisonTableStatus.MODIFIED,
            row_added_count=2,
            row_modified_count=3,
        ),
        store=InMemoryArtifactStore(),
    )

    assert result.risk_report is not None
    assert result.risk_report.tables[0].annotation_count == 1
    assert result.risk_report.tables[0].reason_codes == (
        RiskReasonCode.COMPOSITE_SIGNAL_CHANGE_REVIEW_REQUIRED,
    )
    assert result.risk_report.tables[0].risk_level is RiskLevel.UNKNOWN


def test_low_risk_filter_and_counts_only_do_not_require_artifact_store() -> None:
    result = _evaluate(
        ComparisonTableFact(table_name="orders", status=ComparisonTableStatus.ADDED_TABLE),
        options=RiskOptions(
            include_low_risk=False,
            annotation_detail_policy=AnnotationDetailPolicy.COUNTS_ONLY,
        ),
    )

    assert result.status is RiskEvaluationStatus.READY
    assert result.risk_report is not None
    assert result.risk_report.tables == ()
    assert result.risk_report.overall.risk_level is None


def test_counts_only_does_not_report_artifact_budget_or_no_record_closure() -> None:
    result = _evaluate(
        ComparisonTableFact(table_name="orders", status=ComparisonTableStatus.ADDED_TABLE),
        options=RiskOptions(annotation_detail_policy=AnnotationDetailPolicy.COUNTS_ONLY),
        store=InMemoryArtifactStore(),
    )

    assert result.status is RiskEvaluationStatus.READY
    assert result.risk_report is not None
    assert result.risk_report.tables[0].diagnostics == ()
    assert result.risk_closure is None


@dataclass
class _SetProbe:
    value: bool = True

    def is_set(self) -> bool:
        return self.value


def test_cancellation_returns_terminal_cancelled_without_outputs() -> None:
    result = _evaluate(
        ComparisonTableFact(table_name="orders", status=ComparisonTableStatus.ADDED_TABLE),
        store=InMemoryArtifactStore(),
        context=RiskExecutionContext(cancel_requested=_SetProbe()),
    )

    assert result.status is RiskEvaluationStatus.CANCELLED
    assert result.risk_evaluation is None
    assert result.risk_report is None
    assert result.risk_closure is None


def test_pair_annotation_cap_discards_partial_annotation_closure() -> None:
    records = tuple(
        ComparisonRecord(
            table_name="orders",
            record_kind=ComparisonRecordKind.ROW_ADDED,
            row_identity=DigestRef(f"sha256:{index:064x}"),
        )
        for index in (1, 2)
    )
    result = _evaluate(
        ComparisonTableFact(
            table_name="orders",
            status=ComparisonTableStatus.MODIFIED,
            row_added_count=2,
            records=records,
        ),
        store=InMemoryArtifactStore(),
        policy=RiskExecutionPolicy(max_annotations_per_pair=1),
    )

    assert result.status is RiskEvaluationStatus.DEGRADED
    assert result.risk_evaluation is not None
    assert result.risk_report is not None
    assert len(result.risk_report.tables) == 1
    assert result.risk_report.tables[0].table_name == "orders"
    assert result.risk_report.tables[0].risk_level is RiskLevel.UNKNOWN
    assert result.risk_report.tables[0].annotation_count == 0
    assert result.risk_report.tables[0].diagnostics == (
        "max_annotations_per_pair exceeded",
    )
    assert result.annotation_artifacts == ()
    assert result.risk_closure is None


def test_table_annotation_cap_emits_degraded_no_record_entry() -> None:
    records = tuple(
        ComparisonRecord(
            table_name="orders",
            record_kind=ComparisonRecordKind.ROW_ADDED,
            row_identity=DigestRef(f"sha256:{index:064x}"),
        )
        for index in (1, 2)
    )
    store = InMemoryArtifactStore()
    result = _evaluate(
        ComparisonTableFact(
            table_name="orders",
            status=ComparisonTableStatus.MODIFIED,
            row_added_count=2,
            records=records,
        ),
        store=store,
        policy=RiskExecutionPolicy(max_annotations_per_table=1),
    )

    assert result.status is RiskEvaluationStatus.DEGRADED
    assert result.risk_closure is not None
    assert result.risk_closure.entries[0].artifact is None
    assert result.risk_closure.entries[0].no_record_reason_codes == (RiskReasonCode.KEY_DEGRADED,)
    validate_risk_annotation_closure(result.risk_closure, store)


class _CountingRecordsAccess:
    def __init__(self, closure: ComparisonRecordsClosure | None) -> None:
        self.closure = closure
        self.calls = 0

    def get_records_closure(self) -> ComparisonRecordsClosure:
        self.calls += 1
        return self.closure  # type: ignore[return-value]

    def get_ordered_records(self, table_name: str) -> tuple[OrderedRecord, ...]:
        raise AssertionError(f"ordered records must not be read: {table_name}")


def test_counts_only_does_not_read_records_access() -> None:
    access = _CountingRecordsAccess(None)
    result = _evaluate(
        ComparisonTableFact(
            table_name="orders",
            status=ComparisonTableStatus.MODIFIED,
            row_added_count=1,
        ),
        options=RiskOptions(annotation_detail_policy=AnnotationDetailPolicy.COUNTS_ONLY),
        records_access=access,
    )

    assert result.status is RiskEvaluationStatus.READY
    assert access.calls == 0


def test_missing_records_closure_fails_when_row_targets_are_requested() -> None:
    access = _CountingRecordsAccess(None)
    result = _evaluate(
        ComparisonTableFact(
            table_name="orders",
            status=ComparisonTableStatus.MODIFIED,
            row_added_count=1,
        ),
        records_access=access,
    )

    assert result.status is RiskEvaluationStatus.FAILED
    assert result.risk_evaluation is None


def test_intentionally_suppressed_rows_keep_count_risk_without_record_closure() -> None:
    store = InMemoryArtifactStore()
    result = _evaluate(
        ComparisonTableFact(
            table_name="orders",
            status=ComparisonTableStatus.ADDED_TABLE,
            row_added_count=3,
            suppressed_added_count=3,
        ),
        store=store,
    )

    assert result.status is RiskEvaluationStatus.READY
    assert result.risk_report is not None
    assert result.risk_report.tables[0].annotation_count == 2
    assert len(result.annotation_artifacts) == 1
    annotation_payload = json.loads(
        store.locate(result.annotation_artifacts[0].content_ref)
    )
    row_annotation = next(
        item
        for item in annotation_payload["annotations"]
        if item["target"]["coverage"] == "ROW_RECORDS_SUPPRESSED"
    )
    assert row_annotation["reasons"][0]["evidence"] == [["count", 3]]


class _TamperedClosureStore(InMemoryArtifactStore):
    def __init__(self) -> None:
        super().__init__()
        self.tamper_ref: ArtifactRef | None = None

    def locate(self, ref: ArtifactRef) -> bytes:
        raw = super().locate(ref)
        if self.tamper_ref == ref:
            return b"{}"
        return raw


def test_tampered_closure_is_rejected() -> None:
    store = _TamperedClosureStore()
    result = _evaluate(
        ComparisonTableFact(table_name="orders", status=ComparisonTableStatus.ADDED_TABLE),
        store=store,
    )
    assert result.risk_closure is not None
    closure: RiskAnnotationClosure = result.risk_closure
    store.tamper_ref = closure.closure_ref

    with pytest.raises(ValueError, match="closure"):
        validate_risk_annotation_closure(closure, store)


def test_annotation_document_validator_rejects_malformed_record_fields() -> None:
    content = canonicalize_json_value(
        {
            "annotations": [
                {
                    "annotation_id": "orders:00000000",
                    "diagnostics": "",
                    "reasons": [
                        {
                            "evidence": [],
                            "message": "review required",
                            "reason_code": "KEY_DEGRADED",
                            "rule_id": "KEY_DEGRADED",
                        }
                    ],
                    "risk_level": "UNKNOWN",
                    "target": {
                        "before_row_identity": None,
                        "changed_columns": "",
                        "coverage": None,
                        "current_row_identity": None,
                        "position": None,
                        "position_range": None,
                        "row_identity": None,
                        "table_name": "orders",
                        "target_type": "TABLE",
                    },
                }
            ],
            "contract_version": RISK_ANNOTATION_CONTRACT_VERSION,
            "table_name": "orders",
        }
    )
    content_digest = raw_blob_digest(content)
    manifest = canonicalize_json_value(
        {
            "annotation_count": 1,
            "content_digest": content_digest.value,
            "contract_version": RISK_ANNOTATION_CONTRACT_VERSION,
            "record_format": "CANONICAL_JSON",
            "table_name": "orders",
        }
    )

    with pytest.raises(ValueError, match="record payload mismatch"):
        validate_risk_annotation_documents(
            content,
            manifest,
            table_name="orders",
            annotation_count=1,
            content_digest=content_digest,
        )

    noncanonical_evidence = json.loads(content)
    noncanonical_evidence["annotations"][0]["changed_columns"] = []
    noncanonical_evidence["annotations"][0]["diagnostics"] = []
    noncanonical_evidence["annotations"][0]["reasons"][0]["evidence"] = [
        ["z", 1],
        ["a", 2],
    ]
    content = canonicalize_json_value(noncanonical_evidence)
    content_digest = raw_blob_digest(content)
    manifest = canonicalize_json_value(
        {
            "annotation_count": 1,
            "content_digest": content_digest.value,
            "contract_version": RISK_ANNOTATION_CONTRACT_VERSION,
            "record_format": "CANONICAL_JSON",
            "table_name": "orders",
        }
    )
    with pytest.raises(ValueError, match="record payload mismatch"):
        validate_risk_annotation_documents(
            content,
            manifest,
            table_name="orders",
            annotation_count=1,
            content_digest=content_digest,
        )
