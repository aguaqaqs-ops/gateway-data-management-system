"""Deterministic table-rule resolution against an injected snapshot."""

from __future__ import annotations

import re
from re import Pattern

from gateway_backend.capabilities.table_rules.contracts import (
    LegacyRuleDecision,
    ResolvedTableRule,
    SelectorPrecedenceClass,
    TableCompareKeyMode,
    TableRuleRecord,
    TableRuleSelectorKind,
    TableRulesetSnapshot,
    TableStaticRole,
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
        return LegacyRuleDecision(selector=record.selector, static_role=record.static_role)
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
        artifact_scope=record.artifact_scope,
        position_column=record.position_column,
        stable_key_candidates=record.stable_key_candidates,
    )
