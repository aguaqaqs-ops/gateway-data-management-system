from __future__ import annotations

from ...comparison.models import ComparisonRecordKind, ComparisonTableStatus
from ....core.digests import canonical_json_bytes
from ...table_rules.registry import DEVICE_POINT_UPDATE_ONLY_TABLE_NAMES
from ..models import (
    RiskAnnotation,
    RiskFacts,
    RiskLevel,
    RiskReason,
    RiskTarget,
    RiskTargetType,
    RiskScope,
)
from ..rule_registry import RiskRulesetSnapshot


def build_standard_annotations(
    fact: RiskFacts,
    risk_ruleset: RiskRulesetSnapshot,
) -> tuple[RiskAnnotation, ...]:
    if fact.risk_scope is not RiskScope.STANDARD_ROWS or fact.degraded:
        return ()
    if fact.table_status in {ComparisonTableStatus.UNCHANGED, ComparisonTableStatus.BUSINESS_EQUIVALENT}:
        return ()

    annotations: list[RiskAnnotation] = []
    row_change_stats = fact.row_change_stats
    standard_records = fact.standard_records
    added_records = tuple(
        record
        for record in standard_records
        if record.record_kind is ComparisonRecordKind.ROW_ADDED
    )
    deleted_records = tuple(
        record
        for record in standard_records
        if record.record_kind is ComparisonRecordKind.ROW_DELETED
    )
    added_count = len(added_records)
    if added_count == 0 and row_change_stats is not None and row_change_stats.row_added_count:
        added_count = row_change_stats.row_added_count
    deleted_count = len(deleted_records)
    if deleted_count == 0 and row_change_stats is not None and row_change_stats.row_deleted_count:
        deleted_count = row_change_stats.row_deleted_count
    modified_records = tuple(
        record
        for record in standard_records
        if record.record_kind is ComparisonRecordKind.ROW_MODIFIED
    )
    modified_count = len(modified_records)
    if modified_count == 0 and row_change_stats is not None and row_change_stats.row_modified_count:
        modified_count = row_change_stats.row_modified_count

    if added_records:
        annotations.extend(
            _row_annotation(
                fact=fact,
                risk_ruleset=risk_ruleset,
                rule_id="STANDARD_INSERT",
                reason_code="STANDARD_INSERT",
                message="standard rows inserted",
                target_type=RiskTargetType.ROW,
                evidence=_evidence(fact, row_count=1),
                record=record,
                row_side="after",
            )
            for record in added_records
        )
    if deleted_records:
        annotations.extend(
            _row_annotation(
                fact=fact,
                risk_ruleset=risk_ruleset,
                rule_id="STANDARD_DELETE",
                reason_code="STANDARD_DELETE",
                message="standard rows deleted",
                target_type=RiskTargetType.ROW,
                evidence=_evidence(fact, row_count=1),
                record=record,
                row_side="before",
            )
            for record in deleted_records
        )
    if added_count and not added_records:
        annotations.append(
            _summary_annotation(
                fact=fact,
                risk_ruleset=risk_ruleset,
                rule_id="STANDARD_INSERT",
                reason_code="STANDARD_INSERT",
                message="standard rows inserted",
                target_type=RiskTargetType.ROW,
                evidence=_evidence(fact, row_count=added_count),
            )
        )
    if deleted_count and not deleted_records:
        annotations.append(
            _summary_annotation(
                fact=fact,
                risk_ruleset=risk_ruleset,
                rule_id="STANDARD_DELETE",
                reason_code="STANDARD_DELETE",
                message="standard rows deleted",
                target_type=RiskTargetType.ROW,
                evidence=_evidence(fact, row_count=deleted_count),
            )
        )
    if _is_device_point_table(fact.table_name) and modified_count:
        name_only_records, content_records = _device_point_update_records(modified_records)
        if not modified_records and modified_count:
            annotations.append(
                _summary_annotation(
                    fact=fact,
                risk_ruleset=risk_ruleset,
                rule_id="DEVICE_POINT_CONTENT_UPDATE",
                reason_code="DEVICE_POINT_CONTENT_UPDATE",
                message="device point content changed",
                target_type=RiskTargetType.ROW_PAIR,
                evidence=_evidence(fact, row_count=modified_count),
            )
        )
        if name_only_records:
            annotations.extend(
                _row_annotation(
                    fact=fact,
                    risk_ruleset=risk_ruleset,
                    rule_id="DEVICE_POINT_NAME_UPDATE",
                    reason_code="DEVICE_POINT_NAME_UPDATE",
                    message="device point name changed",
                    target_type=RiskTargetType.ROW_PAIR,
                    evidence=_evidence(fact, row_count=1, changed_columns=("name",)),
                    record=record,
                )
                for record in name_only_records
            )
        if content_records:
            annotations.extend(
                _row_annotation(
                    fact=fact,
                    risk_ruleset=risk_ruleset,
                    rule_id="DEVICE_POINT_CONTENT_UPDATE",
                    reason_code="DEVICE_POINT_CONTENT_UPDATE",
                    message="device point content changed",
                    target_type=RiskTargetType.ROW_PAIR,
                    evidence=_evidence(fact, row_count=1),
                    record=record,
                )
                for record in content_records
            )
    elif modified_count or (not annotations and fact.table_status is ComparisonTableStatus.MODIFIED):
        if modified_records:
            annotations.extend(
                _row_annotation(
                    fact=fact,
                    risk_ruleset=risk_ruleset,
                    rule_id="STANDARD_UPDATE",
                    reason_code="STANDARD_UPDATE",
                    message="standard rows updated",
                    target_type=RiskTargetType.ROW_PAIR,
                    evidence=_evidence(fact, row_count=1),
                    record=record,
                )
                for record in modified_records
            )
        else:
            annotations.append(
                _summary_annotation(
                    fact=fact,
                    risk_ruleset=risk_ruleset,
                    rule_id="STANDARD_UPDATE",
                    reason_code="STANDARD_UPDATE",
                    message="standard rows updated",
                    target_type=RiskTargetType.ROW_PAIR,
                    evidence=_evidence(fact, row_count=modified_count or None),
                )
            )

    return tuple(annotations)


def _is_device_point_table(table_name: str) -> bool:
    return table_name in DEVICE_POINT_UPDATE_ONLY_TABLE_NAMES


def _device_point_update_records(records) -> tuple[tuple[object, ...], tuple[object, ...]]:
    name_only_records: list[object] = []
    content_records: list[object] = []
    for record in records:
        changed_columns = tuple(record.changed_columns or ())
        if changed_columns and set(changed_columns) <= {"name"}:
            name_only_records.append(record)
        else:
            content_records.append(record)
    return tuple(name_only_records), tuple(content_records)


def _evidence(
    fact: RiskFacts,
    *,
    row_count: int | None = None,
    changed_columns: tuple[str, ...] = (),
) -> dict[str, object]:
    evidence: dict[str, object] = {"table_status": fact.table_status.value}
    if row_count is not None:
        evidence["row_count"] = row_count
    if changed_columns:
        evidence["changed_columns"] = list(changed_columns)
    if fact.row_change_stats is not None:
        evidence["row_change_stats"] = fact.row_change_stats.to_payload()
    return evidence


def _row_annotation(
    *,
    fact: RiskFacts,
    risk_ruleset: RiskRulesetSnapshot,
    rule_id: str,
    reason_code: str,
    message: str,
    target_type: RiskTargetType,
    evidence: dict[str, object],
    record,
    row_side: str | None = None,
) -> RiskAnnotation:
    rule = risk_ruleset.rule_by_id(rule_id)
    risk_level = rule.severity_policy if rule is not None else RiskLevel.MEDIUM_LOW
    entity_key = _standard_record_entity_key(record)
    if target_type is RiskTargetType.ROW_PAIR:
        target = RiskTarget(
            target_type=target_type,
            table_name=fact.table_name,
            row_identity=entity_key,
            before_row_identity=entity_key,
            current_row_identity=entity_key,
            entity_key=entity_key,
            before_entity_key=entity_key,
            after_entity_key=entity_key,
        )
    else:
        target = RiskTarget(
            target_type=target_type,
            table_name=fact.table_name,
            row_identity=entity_key,
            entity_key=entity_key,
            row_side=row_side,
        )
        if row_side == "before":
            target = RiskTarget(
                target_type=target_type,
                table_name=fact.table_name,
                row_identity=entity_key,
                before_row_identity=entity_key,
                entity_key=entity_key,
                before_entity_key=entity_key,
                row_side=row_side,
            )
        elif row_side == "after":
            target = RiskTarget(
                target_type=target_type,
                table_name=fact.table_name,
                row_identity=entity_key,
                current_row_identity=entity_key,
                entity_key=entity_key,
                after_entity_key=entity_key,
                row_side=row_side,
            )
    return _annotation(
        fact=fact,
        target=target,
        risk_level=risk_level,
        rule_id=rule_id,
        reason_code=rule.reason_code if rule is not None else reason_code,
        message=message,
        evidence=evidence,
    )


def _summary_annotation(
    *,
    fact: RiskFacts,
    risk_ruleset: RiskRulesetSnapshot,
    rule_id: str,
    reason_code: str,
    message: str,
    target_type: RiskTargetType,
    evidence: dict[str, object],
) -> RiskAnnotation:
    rule = risk_ruleset.rule_by_id(rule_id)
    risk_level = rule.severity_policy if rule is not None else RiskLevel.MEDIUM_LOW
    return _annotation(
        fact=fact,
        target=RiskTarget(
            target_type=target_type,
            table_name=fact.table_name,
        ),
        risk_level=risk_level,
        rule_id=rule_id,
        reason_code=rule.reason_code if rule is not None else reason_code,
        message=message,
        evidence=evidence,
    )


def _annotation(
    *,
    fact: RiskFacts,
    target: RiskTarget,
    risk_level: RiskLevel,
    rule_id: str,
    reason_code: str,
    message: str,
    evidence: dict[str, object],
) -> RiskAnnotation:
    return RiskAnnotation(
        annotation_id="",
        target=target,
        risk_level=risk_level,
        reasons=(
            RiskReason(
                reason_code=reason_code,
                message=message,
                rule_id=rule_id,
                evidence=evidence,
            ),
        ),
        diagnostics=fact.diagnostics,
    )


def _standard_record_entity_key(record) -> str:
    return canonical_json_bytes(record.row_identity or ()).decode("utf-8")
