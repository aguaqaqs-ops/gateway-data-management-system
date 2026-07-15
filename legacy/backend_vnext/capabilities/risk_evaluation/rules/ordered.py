from __future__ import annotations

from collections import defaultdict

from ..models import (
    RiskAnnotation,
    RiskFacts,
    RiskLevel,
    RiskReason,
    RiskScope,
    RiskTarget,
    RiskTargetType,
)
from ..rule_registry import RiskRulesetSnapshot
from ...comparison.ordered.models import OrderedRecord, OrderedSemanticKind


_INSERT_KINDS = {
    OrderedSemanticKind.DATA_INSERT,
    OrderedSemanticKind.BLANK_INSERT_INTERVAL,
}
_DELETE_KINDS = {
    OrderedSemanticKind.DATA_DELETE,
    OrderedSemanticKind.BLANK_DELETE_INTERVAL,
}
_STRUCTURAL_KINDS = _INSERT_KINDS | _DELETE_KINDS
_BLANK_KINDS = {
    OrderedSemanticKind.BLANK_INSERT_INTERVAL,
    OrderedSemanticKind.BLANK_DELETE_INTERVAL,
}


def build_ordered_annotations(
    fact: RiskFacts,
    risk_ruleset: RiskRulesetSnapshot,
) -> tuple[RiskAnnotation, ...]:
    if fact.risk_scope is not RiskScope.ORDERED_TABLE:
        return ()
    if fact.ordered_extension is None:
        return ()
    if fact.ordered_extension.replay_guarantee != "EXACT":
        return _unknown_ordered_annotations(fact, risk_ruleset)
    if not fact.ordered_records:
        if _ordered_summary_has_changes(fact):
            return (_unknown_table_annotation(fact, risk_ruleset),)
        return ()

    annotations: list[RiskAnnotation] = []
    paired_entity_keys: set[str] = set()

    for delete_record, insert_record in _replacement_pairs(fact.ordered_records):
        paired_entity_keys.add(delete_record.entity_key)
        paired_entity_keys.add(insert_record.entity_key)
        annotations.append(_replacement_annotation(fact, risk_ruleset, delete_record, insert_record))

    content_update_entity_keys: set[str] = set()
    for record in fact.ordered_records:
        if record.semantic_kind is not OrderedSemanticKind.CONTENT_UPDATE:
            continue
        annotation = _content_update_annotation(fact, risk_ruleset, record)
        if annotation is None:
            continue
        content_update_entity_keys.add(record.entity_key)
        annotations.append(annotation)

    move_entity_keys: set[str] = set()
    for record in fact.ordered_records:
        if record.semantic_kind is not OrderedSemanticKind.MOVE:
            continue
        move_entity_keys.add(record.entity_key)
        annotations.append(_move_annotation(fact, risk_ruleset, record))

    unpaired_structural = tuple(
        record
        for record in fact.ordered_records
        if record.semantic_kind in _STRUCTURAL_KINDS and record.entity_key not in paired_entity_keys
    )
    annotations.extend(_structural_annotations(fact, risk_ruleset, unpaired_structural))
    structural_entity_keys = {record.entity_key for record in unpaired_structural}

    handled_entity_keys = paired_entity_keys | content_update_entity_keys | move_entity_keys | structural_entity_keys
    for record in fact.ordered_records:
        if record.entity_key in handled_entity_keys:
            continue
        annotations.append(_unknown_ordered_annotation(fact, risk_ruleset, record))

    return tuple(annotations)


def _replacement_pairs(
    records: tuple[OrderedRecord, ...],
) -> tuple[tuple[OrderedRecord, OrderedRecord], ...]:
    deletes_by_position: dict[int, list[OrderedRecord]] = defaultdict(list)
    inserts_by_position: dict[int, list[OrderedRecord]] = defaultdict(list)
    for record in records:
        if record.semantic_kind is OrderedSemanticKind.DATA_DELETE and record.before_position is not None:
            deletes_by_position[record.before_position].append(record)
        elif record.semantic_kind is OrderedSemanticKind.DATA_INSERT and record.after_position is not None:
            inserts_by_position[record.after_position].append(record)

    pairs: list[tuple[OrderedRecord, OrderedRecord]] = []
    for position in sorted(set(deletes_by_position) & set(inserts_by_position)):
        deletes = sorted(deletes_by_position[position], key=lambda item: item.entity_key)
        inserts = sorted(inserts_by_position[position], key=lambda item: item.entity_key)
        pairs.extend(zip(deletes, inserts, strict=False))
    return tuple(pairs)


def _replacement_annotation(
    fact: RiskFacts,
    risk_ruleset: RiskRulesetSnapshot,
    delete_record: OrderedRecord,
    insert_record: OrderedRecord,
) -> RiskAnnotation:
    position = delete_record.before_position
    return RiskAnnotation(
        annotation_id="",
        target=RiskTarget(
            target_type=RiskTargetType.ROW_PAIR,
            table_name=fact.table_name,
            before_row_identity=delete_record.entity_key,
            current_row_identity=insert_record.entity_key,
            position=position,
            before_entity_key=delete_record.entity_key,
            after_entity_key=insert_record.entity_key,
            before_position=delete_record.before_position,
            after_position=insert_record.after_position,
        ),
        risk_level=_risk_level_for_rule(
            risk_ruleset,
            "ORDERED_REPLACEMENT",
            fallback=RiskLevel.MEDIUM_LOW,
        ),
        reasons=(
            RiskReason(
                reason_code="ORDERED_REPLACEMENT",
                message="Ordered row delete and insert share the same position.",
                rule_id="ORDERED_REPLACEMENT",
                evidence={
                    "before_entity_key": delete_record.entity_key,
                    "after_entity_key": insert_record.entity_key,
                    "position": position,
                },
            ),
        ),
        diagnostics=fact.diagnostics,
    )


def _content_update_annotation(
    fact: RiskFacts,
    risk_ruleset: RiskRulesetSnapshot,
    record: OrderedRecord,
) -> RiskAnnotation | None:
    changed_lower = {column.lower() for column in record.changed_columns}
    if changed_lower == {"name"}:
        rule_id = "ORDERED_NAME_UPDATE"
        fallback = RiskLevel.LOW
        message = "Ordered row name field changed."
    elif any(column != "name" for column in changed_lower):
        rule_id = "ORDERED_CONTENT_UPDATE"
        fallback = RiskLevel.MEDIUM_LOW
        message = "Ordered row content field changed."
    else:
        return None

    return RiskAnnotation(
        annotation_id="",
        target=_ordered_row_target(fact, record, changed_columns=record.changed_columns),
        risk_level=_risk_level_for_rule(risk_ruleset, rule_id, fallback=fallback),
        reasons=(
            RiskReason(
                reason_code=rule_id,
                message=message,
                rule_id=rule_id,
                evidence={
                    "entity_key": record.entity_key,
                    "changed_columns": list(record.changed_columns),
                    "before_position": record.before_position,
                    "after_position": record.after_position,
                },
            ),
        ),
        diagnostics=fact.diagnostics,
    )


def _move_annotation(
    fact: RiskFacts,
    risk_ruleset: RiskRulesetSnapshot,
    record: OrderedRecord,
) -> RiskAnnotation:
    return RiskAnnotation(
        annotation_id="",
        target=_ordered_row_target(fact, record),
        risk_level=_risk_level_for_rule(
            risk_ruleset,
            "ORDERED_MOVE",
            fallback=RiskLevel.MEDIUM_HIGH,
        ),
        reasons=(
            RiskReason(
                reason_code="ORDERED_MOVE",
                message="Ordered row position changed.",
                rule_id="ORDERED_MOVE",
                evidence={
                    "entity_key": record.entity_key,
                    "before_position": record.before_position,
                    "after_position": record.after_position,
                },
            ),
        ),
        diagnostics=fact.diagnostics,
    )


def _structural_annotations(
    fact: RiskFacts,
    risk_ruleset: RiskRulesetSnapshot,
    structural_records: tuple[OrderedRecord, ...],
) -> tuple[RiskAnnotation, ...]:
    if not structural_records:
        return ()
    annotations: list[RiskAnnotation] = []
    tail_records: list[OrderedRecord] = []
    for record in structural_records:
        if _is_tail_structural(fact, record):
            tail_records.append(record)
            continue
        annotations.append(_structural_row_annotation(fact, risk_ruleset, record))
    annotations.extend(_tail_structural_annotations(fact, risk_ruleset, tuple(tail_records)))
    return tuple(annotations)


def _structural_row_annotation(
    fact: RiskFacts,
    risk_ruleset: RiskRulesetSnapshot,
    record: OrderedRecord,
) -> RiskAnnotation:
    risk_level, reason_code, message = _structural_risk_info(fact, record)
    return RiskAnnotation(
        annotation_id="",
        target=_ordered_row_target(fact, record),
        risk_level=_risk_level_for_rule(risk_ruleset, reason_code, fallback=risk_level),
        reasons=(
            RiskReason(
                reason_code=reason_code,
                message=message,
                rule_id=reason_code,
                evidence={
                    "semantic_kind": record.semantic_kind.value,
                    "entity_key": record.entity_key,
                    "before_position": record.before_position,
                    "after_position": record.after_position,
                },
            ),
        ),
        diagnostics=fact.diagnostics,
    )


def _tail_structural_annotations(
    fact: RiskFacts,
    risk_ruleset: RiskRulesetSnapshot,
    tail_records: tuple[OrderedRecord, ...],
) -> tuple[RiskAnnotation, ...]:
    intervals = _tail_structural_intervals(tail_records)
    annotations: list[RiskAnnotation] = []
    for interval in intervals:
        if len(interval) == 1:
            annotations.append(_structural_row_annotation(fact, risk_ruleset, interval[0]))
            continue
        annotations.append(_tail_interval_annotation(fact, risk_ruleset, interval))
    return tuple(annotations)


def _tail_structural_intervals(
    tail_records: tuple[OrderedRecord, ...],
) -> tuple[tuple[OrderedRecord, ...], ...]:
    sorted_records = tuple(
        sorted(
            tail_records,
            key=lambda record: (
                record.semantic_kind.value,
                _structural_reason_code(record),
                _structural_position(record) or 0,
                record.entity_key,
            ),
        )
    )
    intervals: list[tuple[OrderedRecord, ...]] = []
    current: list[OrderedRecord] = []
    current_key: tuple[str, str] | None = None
    previous_position: int | None = None
    for record in sorted_records:
        position = _structural_position(record)
        key = (record.semantic_kind.value, _structural_reason_code(record))
        if (
            current
            and current_key == key
            and position is not None
            and previous_position is not None
            and position == previous_position + 1
        ):
            current.append(record)
            previous_position = position
            continue
        if current:
            intervals.append(tuple(current))
        current = [record]
        current_key = key
        previous_position = position
    if current:
        intervals.append(tuple(current))
    return tuple(intervals)


def _tail_interval_annotation(
    fact: RiskFacts,
    risk_ruleset: RiskRulesetSnapshot,
    interval: tuple[OrderedRecord, ...],
) -> RiskAnnotation:
    first = interval[0]
    positions = tuple(
        position
        for record in interval
        if (position := _structural_position(record)) is not None
    )
    position_start = min(positions)
    position_end = max(positions)
    risk_level, reason_code, message = _structural_risk_info(fact, first)
    return RiskAnnotation(
        annotation_id="",
        target=RiskTarget(
            target_type=RiskTargetType.ROW_INTERVAL,
            table_name=fact.table_name,
            position_range=(position_start, position_end),
            coverage="INTERVAL_ROWS",
            row_side=_ordered_interval_row_side(first),
            position_start=position_start,
            position_end=position_end,
            row_count=len(interval),
            interval_id=f"{_ordered_interval_row_side(first)}-{position_start:06d}-{position_end:06d}",
        ),
        risk_level=_risk_level_for_rule(risk_ruleset, reason_code, fallback=risk_level),
        reasons=(
            RiskReason(
                reason_code=reason_code,
                message=message,
                rule_id=reason_code,
                evidence={
                    "semantic_kinds": sorted({record.semantic_kind.value for record in interval}),
                    "entity_keys": [record.entity_key for record in interval],
                    "position_start": position_start,
                    "position_end": position_end,
                    "row_count": len(interval),
                },
            ),
        ),
        diagnostics=fact.diagnostics,
    )


def _structural_risk_info(
    fact: RiskFacts,
    record: OrderedRecord,
) -> tuple[RiskLevel, str, str]:
    blank = record.semantic_kind in _BLANK_KINDS
    if _is_tail_structural(fact, record):
        return (
            RiskLevel.LOW,
            "ORDERED_TAIL_BLANK_INTERVAL" if blank else "ORDERED_TAIL_INSERT_DELETE",
            "Ordered table tail-only structural change.",
        )
    return (
        RiskLevel.MEDIUM_HIGH,
        "ORDERED_MIDDLE_BLANK_INTERVAL" if blank else "ORDERED_MIDDLE_INSERT_DELETE",
        "Ordered table non-tail structural change.",
    )


def _structural_reason_code(record: OrderedRecord) -> str:
    return "ORDERED_TAIL_BLANK_INTERVAL" if record.semantic_kind in _BLANK_KINDS else "ORDERED_TAIL_INSERT_DELETE"


def _structural_position(record: OrderedRecord) -> int | None:
    if record.semantic_kind in _INSERT_KINDS:
        return record.after_position
    if record.semantic_kind in _DELETE_KINDS:
        return record.before_position
    return None


def _is_tail_structural(
    fact: RiskFacts,
    record: OrderedRecord,
) -> bool:
    if record.semantic_kind in _INSERT_KINDS:
        return (
            record.after_position is not None
            and fact.before_row_count is not None
            and record.after_position > fact.before_row_count
        )
    if record.semantic_kind in _DELETE_KINDS:
        return (
            record.before_position is not None
            and fact.after_row_count is not None
            and record.before_position > fact.after_row_count
        )
    return False


def _unknown_ordered_annotations(
    fact: RiskFacts,
    risk_ruleset: RiskRulesetSnapshot,
) -> tuple[RiskAnnotation, ...]:
    if fact.ordered_records:
        return tuple(_unknown_ordered_annotation(fact, risk_ruleset, record) for record in fact.ordered_records)
    if _ordered_summary_has_changes(fact):
        return (_unknown_table_annotation(fact, risk_ruleset),)
    return ()


def _unknown_ordered_annotation(
    fact: RiskFacts,
    risk_ruleset: RiskRulesetSnapshot,
    record: OrderedRecord,
) -> RiskAnnotation:
    return RiskAnnotation(
        annotation_id="",
        target=_ordered_row_target(fact, record, changed_columns=record.changed_columns),
        risk_level=_risk_level_for_rule(risk_ruleset, "ORDERED_RISK_UNKNOWN", fallback=RiskLevel.UNKNOWN),
        reasons=(
            RiskReason(
                reason_code="ORDERED_RISK_UNKNOWN",
                message="Ordered diff target is not classified by the current risk rules.",
                rule_id="ORDERED_RISK_UNKNOWN",
                evidence={
                    "semantic_kind": record.semantic_kind.value,
                    "entity_key": record.entity_key,
                    "before_position": record.before_position,
                    "after_position": record.after_position,
                    "ordered_replay_guarantee": (
                        None
                        if fact.ordered_extension is None
                        else fact.ordered_extension.replay_guarantee
                    ),
                },
            ),
        ),
        diagnostics=fact.diagnostics,
    )


def _unknown_table_annotation(
    fact: RiskFacts,
    risk_ruleset: RiskRulesetSnapshot,
) -> RiskAnnotation:
    return RiskAnnotation(
        annotation_id="",
        target=RiskTarget(
            target_type=RiskTargetType.TABLE,
            table_name=fact.table_name,
        ),
        risk_level=_risk_level_for_rule(risk_ruleset, "ORDERED_RISK_UNKNOWN", fallback=RiskLevel.UNKNOWN),
        reasons=(
            RiskReason(
                reason_code="ORDERED_RISK_UNKNOWN",
                message="Ordered table diff is not classified by the current risk rules.",
                rule_id="ORDERED_RISK_UNKNOWN",
                evidence={
                    "degraded": fact.degraded,
                    "classification_complete": False,
                    "degraded_reasons": list(fact.degraded_reasons),
                },
            ),
        ),
        diagnostics=fact.diagnostics,
    )


def _ordered_row_target(
    fact: RiskFacts,
    record: OrderedRecord,
    *,
    changed_columns: tuple[str, ...] = (),
) -> RiskTarget:
    position = record.after_position if record.after_position is not None else record.before_position
    return RiskTarget(
        target_type=RiskTargetType.ROW,
        table_name=fact.table_name,
        row_identity=record.entity_key,
        changed_columns=changed_columns,
        position=position,
        row_side=_ordered_row_side(record),
        entity_key=record.entity_key,
        before_entity_key=record.entity_key if record.before_position is not None else None,
        after_entity_key=record.entity_key if record.after_position is not None else None,
        before_position=record.before_position,
        after_position=record.after_position,
    )


def _ordered_row_side(record: OrderedRecord) -> str:
    if record.before_position is not None and record.after_position is not None:
        return "both"
    if record.before_position is not None:
        return "before"
    return "after"


def _ordered_interval_row_side(record: OrderedRecord) -> str:
    if record.semantic_kind in _DELETE_KINDS:
        return "before"
    return "after"


def _risk_level_for_rule(
    risk_ruleset: RiskRulesetSnapshot,
    rule_id: str,
    *,
    fallback: RiskLevel,
) -> RiskLevel:
    rule = risk_ruleset.rule_by_id(rule_id)
    return rule.severity_policy if rule is not None else fallback


def _ordered_summary_has_changes(fact: RiskFacts) -> bool:
    ordered_extension = fact.ordered_extension
    if ordered_extension is None or ordered_extension.ordered_summary is None:
        return False
    for value in ordered_extension.ordered_summary.values():
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return True
    return False
