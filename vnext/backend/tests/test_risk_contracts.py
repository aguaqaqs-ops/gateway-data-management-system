"""S1 public Risk contracts, ruleset snapshot and digest tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.artifacts import ArtifactRef
from gateway_backend.capabilities.comparison.contracts import (
    ComparisonFacts,
    ComparisonRecordsClosure,
    ComparisonSummary,
    ComparisonTableFact,
    ComparisonTableStatus,
    ComparisonMode,
    OrderedRecord,
    PairResultStatus,
)
from gateway_backend.capabilities.risk_evaluation import (
    RISK_CONTRACT_VERSION,
    RISK_MODEL_VERSION,
    RiskAnnotation,
    RiskEvaluation,
    RiskEvaluationInput,
    RiskFacts,
    RiskLevel,
    RiskOptions,
    RiskReason,
    RiskReasonCode,
    RiskRecordsAccess,
    RiskReport,
    RiskRuleId,
    RiskRulesetSnapshot,
    RiskRowChangeStats,
    RiskScope,
    RiskSummary,
    RiskTableRisk,
    RiskTarget,
    RiskTargetType,
    V1_RISK_RULE_SPECS,
    compute_risk_evaluation_digest,
    risk_evaluation_digest_payload,
    risk_ruleset_document,
    risk_ruleset_from_document,
)


_DIGEST = raw_blob_digest(b"risk-test")
_OTHER_DIGEST = raw_blob_digest(b"risk-other")


def _ruleset() -> RiskRulesetSnapshot:
    return RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS)


def _ruleset_digest() -> DigestRef:
    digest = _ruleset().risk_ruleset_digest
    assert digest is not None
    return digest


def _facts() -> ComparisonFacts:
    table = ComparisonTableFact(table_name="orders", status=ComparisonTableStatus.UNCHANGED)
    summary = ComparisonSummary(
        status=PairResultStatus.UNCHANGED,
        table_count=1,
        unchanged_table_count=1,
        changed_table_count=0,
        added_table_count=0,
        deleted_table_count=0,
        schema_changed_table_count=0,
        degraded_table_count=0,
        row_added_count=0,
        row_deleted_count=0,
        row_modified_count=0,
        suppressed_added_count=0,
        suppressed_deleted_count=0,
        diagnostics_count=0,
    )
    return ComparisonFacts(
        comparison_digest=_DIGEST,
        facts_core_digest=_OTHER_DIGEST,
        comparison_contract_version="backend-vnext/comparison/v3",
        projection_contract_version="backend-vnext/comparison-projection/v1",
        scalar_encoding_version=1,
        before_snapshot_digest=raw_blob_digest(b"before"),
        current_snapshot_digest=raw_blob_digest(b"current"),
        comparison_mode=ComparisonMode.DETAILED,
        direction="BEFORE_TO_CURRENT",
        summary=summary,
        tables=(table,),
    )


def _closure() -> ComparisonRecordsClosure:
    return ComparisonRecordsClosure(
        comparison_digest=_DIGEST,
        facts_core_digest=_OTHER_DIGEST,
        records=(),
        closure_manifest_digest=raw_blob_digest(b"closure"),
    )


class _RecordsAccess:
    def get_records_closure(self) -> ComparisonRecordsClosure:
        return _closure()

    def get_ordered_records(self, table_name: str) -> tuple[OrderedRecord, ...]:
        assert table_name == "orders"
        return ()


def _table_risk(*, annotation_ref: ArtifactRef | None = None) -> RiskTableRisk:
    return RiskTableRisk(
        table_name="orders",
        risk_level=RiskLevel.MEDIUM_LOW,
        reason_codes=(RiskReasonCode.TABLE_ADDED,),
        annotation_count=1,
        source_table_status=ComparisonTableStatus.ADDED_TABLE,
        annotation_ref=annotation_ref,
    )


def test_v1_rules_freeze_rule_ids_scopes_reasons_and_levels() -> None:
    assert tuple(rule.rule_id for rule in V1_RISK_RULE_SPECS) == tuple(
        sorted((RiskRuleId(item) for item in RiskRuleId), key=lambda item: item.value)
    )
    levels = {rule.rule_id: rule.severity_policy.default_level for rule in V1_RISK_RULE_SPECS}
    assert levels[RiskRuleId.TABLE_ADDED] is RiskLevel.MEDIUM_LOW
    assert levels[RiskRuleId.TABLE_DELETED] is RiskLevel.MEDIUM_HIGH
    assert levels[RiskRuleId.SCHEMA_CHANGED] is RiskLevel.MEDIUM_HIGH
    assert levels[RiskRuleId.ROW_ADDED] is RiskLevel.MEDIUM_LOW
    assert levels[RiskRuleId.ROW_DELETED] is RiskLevel.MEDIUM_LOW
    assert levels[RiskRuleId.ROW_MODIFIED] is RiskLevel.MEDIUM_HIGH
    assert levels[RiskRuleId.KEY_DEGRADED] is RiskLevel.UNKNOWN
    assert levels[RiskRuleId.ORDERED_DIFF_UNSUPPORTED] is RiskLevel.UNKNOWN
    assert levels[RiskRuleId.COMPARISON_FAILED] is RiskLevel.HIGH
    assert levels[RiskRuleId.COMPOSITE_SIGNAL_POINT] is RiskLevel.UNKNOWN
    assert levels[RiskRuleId.UNKNOWN_CHANGE_TARGET] is RiskLevel.UNKNOWN


def test_ruleset_document_round_trip_and_digest_are_stable() -> None:
    snapshot = _ruleset()
    document = risk_ruleset_document(snapshot)
    restored = risk_ruleset_from_document(document)
    assert restored == snapshot
    assert restored.risk_ruleset_digest == snapshot.risk_ruleset_digest

    reordered_object_keys = {
        "rules": document["rules"],
        "risk_ruleset_version": document["risk_ruleset_version"],
        "risk_model_version": document["risk_model_version"],
        "risk_ruleset_id": document["risk_ruleset_id"],
        "contract_version": document["contract_version"],
    }
    assert risk_ruleset_from_document(reordered_object_keys).risk_ruleset_digest == snapshot.risk_ruleset_digest


def _unknown_field(document: dict[str, object]) -> dict[str, object]:
    return {**document, "provider": "hidden"}


def _missing_rules(document: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in document.items() if key != "rules"}


def _duplicate_rule(document: dict[str, object]) -> dict[str, object]:
    rules = document["rules"]
    assert isinstance(rules, list)
    return {**document, "rules": [rules[0], rules[0]]}


def _misordered_rules(document: dict[str, object]) -> dict[str, object]:
    rules = document["rules"]
    assert isinstance(rules, list)
    return {**document, "rules": [rules[1], rules[0], *rules[2:]]}


MALFORMED_RULESET_DOCUMENTS: tuple[
    tuple[str, Callable[[dict[str, object]], dict[str, object]], str], ...
] = (
    ("unknown field", _unknown_field, "unknown fields"),
    ("missing rules", _missing_rules, "rules"),
    (
        "duplicate rule",
        _duplicate_rule,
        "repeat rule_id",
    ),
    (
        "misordered rules",
        _misordered_rules,
        "canonical rule_id order",
    ),
)


@pytest.mark.parametrize("label,mutate,expected", MALFORMED_RULESET_DOCUMENTS)
def test_malformed_ruleset_documents_fail_closed(
    label: str,
    mutate: Callable[[dict[str, object]], dict[str, object]],
    expected: str,
) -> None:
    del label
    document = risk_ruleset_document(_ruleset())
    with pytest.raises(ValueError, match=expected):
        risk_ruleset_from_document(mutate(document))


def test_ruleset_digest_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="does not match"):
        RiskRulesetSnapshot(
            rules=V1_RISK_RULE_SPECS,
            risk_ruleset_digest=DigestRef("sha256:" + "22" * 32),
        )


def test_risk_contract_models_serialize_without_engine_assumptions() -> None:
    reason = RiskReason(
        reason_code=RiskReasonCode.TABLE_ADDED,
        message="table was added",
        rule_id=RiskRuleId.TABLE_ADDED,
        evidence=(("count", 1),),
    )
    annotation = RiskAnnotation(
        annotation_id="orders:table-added",
        risk_level=RiskLevel.MEDIUM_LOW,
        target=RiskTarget(target_type=RiskTargetType.TABLE, table_name="orders"),
        reasons=(reason,),
    )
    facts = RiskFacts(
        comparison_digest=_DIGEST,
        table_name="orders",
        table_status=ComparisonTableStatus.ADDED_TABLE,
        risk_scope=RiskScope.TABLE,
        row_change_stats=RiskRowChangeStats(row_added_count=1),
    )
    table_risk = _table_risk()
    summary = RiskSummary(
        risk_level=RiskLevel.MEDIUM_LOW,
        reason_codes=(RiskReasonCode.TABLE_ADDED,),
        table_count=1,
        annotation_count=1,
    )
    digest = compute_risk_evaluation_digest(
        comparison_digest=_DIGEST,
        risk_contract_version=RISK_CONTRACT_VERSION,
        risk_model_version=RISK_MODEL_VERSION,
        risk_ruleset_digest=_ruleset_digest(),
        risk_options=RiskOptions(),
        table_risks=(table_risk,),
    )
    evaluation = RiskEvaluation(
        risk_evaluation_digest=digest,
        risk_contract_version=RISK_CONTRACT_VERSION,
        risk_model_version=RISK_MODEL_VERSION,
        risk_ruleset_digest=_ruleset_digest(),
        comparison_digest=_DIGEST,
        summary=summary,
        table_risks=(table_risk,),
    )
    report = RiskReport(
        risk_report_contract_version=RISK_CONTRACT_VERSION,
        risk_evaluation_digest=digest,
        overall=summary,
        tables=(table_risk,),
    )

    annotation_document = annotation.to_document()
    reasons = annotation_document["reasons"]
    assert isinstance(reasons, list)
    assert isinstance(reasons[0], dict)
    assert reasons[0]["reason_code"] == "TABLE_ADDED"
    assert facts.to_document()["risk_scope"] == "TABLE"
    assert evaluation.to_document()["risk_evaluation_digest"] == digest.value
    assert report.to_document()["overall"] == summary.to_document()


def test_r5_facts_and_records_access_are_the_only_input_boundary() -> None:
    ruleset = _ruleset()
    request = RiskEvaluationInput(
        comparison_facts=_facts(),
        risk_ruleset=ruleset,
        records_access=_RecordsAccess(),
        requested_tables=("orders",),
    )
    assert isinstance(request.records_access, RiskRecordsAccess)
    assert request.records_access is not None
    assert request.records_access.get_records_closure().comparison_digest == _DIGEST
    assert request.to_document()["risk_options"] == RiskOptions().to_document()

    with pytest.raises(ValueError, match="risk_model_version"):
        RiskEvaluationInput(
            comparison_facts=_facts(),
            risk_ruleset=ruleset,
            risk_model_version="backend-vnext/other-model/v1",
        )
    with pytest.raises(ValueError, match="canonical order"):
        RiskEvaluationInput(
            comparison_facts=_facts(),
            risk_ruleset=ruleset,
            requested_tables=("users", "orders"),
        )


def test_digest_excludes_artifact_refs_diagnostics_and_path_identity() -> None:
    ref = ArtifactRef(
        artifact_id="risk-annotations-orders",
        media_type="application/json",
        size_bytes=4,
        raw_sha256=raw_blob_digest(b"blob"),
    )
    first = _table_risk(annotation_ref=ref)
    second = replace(first, annotation_ref=None, diagnostics=("diagnostic-only",))
    assert risk_evaluation_digest_payload(
        comparison_digest=_DIGEST,
        risk_contract_version=RISK_CONTRACT_VERSION,
        risk_model_version=RISK_MODEL_VERSION,
        risk_ruleset_digest=_ruleset_digest(),
        risk_options=RiskOptions(),
        table_risks=(first,),
    ) == risk_evaluation_digest_payload(
        comparison_digest=_DIGEST,
        risk_contract_version=RISK_CONTRACT_VERSION,
        risk_model_version=RISK_MODEL_VERSION,
        risk_ruleset_digest=_ruleset_digest(),
        risk_options=RiskOptions(),
        table_risks=(second,),
    )
    with pytest.raises(ValueError, match="forbidden key"):
        RiskReason(
            reason_code=RiskReasonCode.TABLE_ADDED,
            message="bad evidence",
            rule_id=RiskRuleId.TABLE_ADDED,
            evidence=(("host_path", "/tmp/secret"),),
        )
