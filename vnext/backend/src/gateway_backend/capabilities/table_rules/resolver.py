"""Deterministic table-rule resolution against an injected snapshot."""

from __future__ import annotations

import hashlib
import re
from re import Pattern

from gateway_shared_kernel import DigestRef
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.table_rules.contracts import (
    ComparisonRole,
    ComparisonRuleSet,
    ComparisonRuleView,
    LegacyRuleDecision,
    OrderedComparisonRule,
    ResolvedTableRule,
    SelectorPrecedenceClass,
    TableCompareKeyMode,
    TableRuleRecord,
    TableRuleSelectorKind,
    TableRulesetSnapshot,
    TableStaticRole,
    TableArtifactScope,
    canonicalize_rule_identifier,
)
from gateway_backend.capabilities.table_rules.registry import PRECEDENCE_RANK

_PROTOCOL_CLASSES = frozenset(
    {
        SelectorPrecedenceClass.STANDARD_PROTOCOL_OPTION,
        SelectorPrecedenceClass.STANDARD_PROTOCOL_DEVICE,
    }
)
_NO_KEY_ROLES = frozenset(
    {
        TableStaticRole.SKIP,
        TableStaticRole.SNAPSHOT_ONLY,
        TableStaticRole.BROWSE_ONLY,
    }
)


def resolve_table_rule(
    snapshot: TableRulesetSnapshot,
    table_name: str,
    *,
    primary_key_columns: tuple[str, ...] = (),
) -> ResolvedTableRule:
    if type(snapshot) is not TableRulesetSnapshot:
        raise ValueError("snapshot must be TableRulesetSnapshot")
    if type(primary_key_columns) is not tuple:
        raise ValueError("primary_key_columns must be a tuple")
    canonical_table = canonicalize_rule_identifier(table_name)
    winner = _winning_record(snapshot, table_name)
    return ResolvedTableRule(
        canonical_table=canonical_table,
        decision=_decision_from_record(winner, primary_key_columns),
        record=winner,
    )


def comparison_rule_set(snapshot: TableRulesetSnapshot) -> ComparisonRuleSet:
    if type(snapshot) is not TableRulesetSnapshot:
        raise ValueError("snapshot must be TableRulesetSnapshot")
    return ComparisonRuleSet(snapshot=snapshot)


def resolve_comparison_rule_view(
    rule_set: ComparisonRuleSet,
    table_name: str,
    *,
    primary_key_columns: tuple[str, ...] = (),
) -> ComparisonRuleView | None:
    if type(rule_set) is not ComparisonRuleSet:
        raise ValueError("rule_set must be ComparisonRuleSet")
    resolved = resolve_table_rule(
        rule_set.snapshot,
        table_name,
        primary_key_columns=primary_key_columns,
    )
    record = resolved.record
    role = {
        TableStaticRole.STANDARD_DIFF: ComparisonRole.STANDARD,
        TableStaticRole.ORDERED_DIFF: ComparisonRole.ORDERED,
        TableStaticRole.BROWSE_ONLY: ComparisonRole.BROWSE_ONLY,
        TableStaticRole.SNAPSHOT_ONLY: ComparisonRole.SNAPSHOT_ONLY,
    }.get(record.static_role)
    if role is None:
        return None
    effective_key_columns = resolved.decision.compare_key_columns
    scope = record.artifact_scope or TableArtifactScope.ALL_CHANGES
    ordered = None
    if role is ComparisonRole.ORDERED:
        ordered = OrderedComparisonRule(
            position_column=record.position_column or "no",
            stable_key_candidates=record.stable_key_candidates,
            row_identity_key=effective_key_columns,
            blank_row_policy="PSEUDO_BLANK_BY_MISSING_STABLE_KEY",
        )
    _validate_effective_compare_exclusions(
        resolved.decision.compare_excluded_columns,
        effective_key_columns,
        ordered,
    )
    document = {
        "artifact_scope": scope.value,
        "canonical_table": resolved.canonical_table,
        "compare_excluded_columns": list(resolved.decision.compare_excluded_columns),
        "compare_key_mode": None if record.compare_key_mode is None else record.compare_key_mode.value,
        "effective_key_columns": list(effective_key_columns),
        "ordered": None
        if ordered is None
        else {
            "blank_row_policy": ordered.blank_row_policy,
            "position_column": ordered.position_column,
            "row_identity_key": list(ordered.row_identity_key),
            "stable_key_candidates": list(ordered.stable_key_candidates),
        },
        "role": role.value,
        "schema": "gateway-vnext.comparison-rule-view/v1",
    }
    digest = DigestRef.from_raw_digest(hashlib.sha256(canonicalize_json_value(document)).digest())
    return ComparisonRuleView(
        canonical_table=resolved.canonical_table,
        comparison_role=role,
        artifact_scope=scope,
        compare_key_mode=record.compare_key_mode,
        effective_key_columns=effective_key_columns,
        compare_excluded_columns=resolved.decision.compare_excluded_columns,
        ordered=ordered,
        comparison_rule_digest=digest,
    )


def _winning_record(snapshot: TableRulesetSnapshot, table_name: str) -> TableRuleRecord:
    matches = [rule for rule in snapshot.rules if _selector_matches(rule, table_name)]
    if matches:
        return _unique_winner(matches)
    fallbacks = [
        rule
        for rule in snapshot.rules
        if rule.precedence_class is SelectorPrecedenceClass.STANDARD_RAW_PK_FALLBACK
    ]
    if not fallbacks:
        raise ValueError("unclassified table")
    return _unique_winner(fallbacks)


def _unique_winner(matches: list[TableRuleRecord]) -> TableRuleRecord:
    min_rank = min(PRECEDENCE_RANK[rule.precedence_class] for rule in matches)
    winners = [rule for rule in matches if PRECEDENCE_RANK[rule.precedence_class] == min_rank]
    if len(winners) != 1:
        raise ValueError("incompatible selector collision")
    return winners[0]


def _selector_matches(rule: TableRuleRecord, table_name: str) -> bool:
    selector = rule.selector
    if selector.kind is TableRuleSelectorKind.EXACT:
        return canonicalize_rule_identifier(table_name) == selector.value
    if selector.kind is TableRuleSelectorKind.FALLBACK:
        return False
    compiled = _compile_selector(selector.value)
    if rule.precedence_class in _PROTOCOL_CLASSES:
        return compiled.fullmatch(table_name) is not None
    return compiled.search(table_name) is not None


def _compile_selector(pattern: str) -> Pattern[str]:
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise ValueError("selector regex is malformed") from exc


def _decision_from_record(
    record: TableRuleRecord,
    primary_key_columns: tuple[str, ...],
) -> LegacyRuleDecision:
    if record.static_role in _NO_KEY_ROLES:
        return LegacyRuleDecision(
            selector=record.selector,
            static_role=record.static_role,
            compare_excluded_columns=record.compare_excluded_columns,
        )
    compare_key_columns = record.compare_key_columns
    if record.compare_key_mode is TableCompareKeyMode.RAW_PRIMARY_KEY:
        compare_key_columns = tuple(
            canonicalize_rule_identifier(column) for column in primary_key_columns
        )
    return LegacyRuleDecision(
        selector=record.selector,
        static_role=record.static_role,
        compare_key_mode=record.compare_key_mode,
        compare_key_columns=compare_key_columns,
        ignored_columns=record.ignored_columns,
        compare_excluded_columns=record.compare_excluded_columns,
        artifact_scope=record.artifact_scope,
        position_column=record.position_column,
        stable_key_candidates=record.stable_key_candidates,
    )


def _validate_effective_compare_exclusions(
    compare_excluded_columns: tuple[str, ...],
    effective_key_columns: tuple[str, ...],
    ordered: OrderedComparisonRule | None,
) -> None:
    protected = set(effective_key_columns)
    if ordered is not None:
        protected.update(ordered.stable_key_candidates)
        protected.update(ordered.row_identity_key)
        protected.add(ordered.position_column)
    if set(compare_excluded_columns) & protected:
        raise ValueError("compare-excluded columns must not be effective keys or ordered structure")
