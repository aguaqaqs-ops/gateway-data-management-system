"""Helpers for Table Rules contract tests. Not a production registry."""

from __future__ import annotations

from gateway_backend.capabilities.table_rules.contracts import (
    FALLBACK_SELECTOR_VALUE,
    CanonicalKeyPolicy,
    DroppedColumn,
    OrderedPolicy,
    SelectorPrecedenceClass,
    TableArtifactScope,
    TableCompareKeyMode,
    TableRuleRecord,
    TableRuleSelector,
    TableRuleSelectorKind,
    TableRulesetSnapshot,
    TableStaticRole,
    TableStorageDisposition,
    legacy_ignored_column_reason,
    table_ruleset_from_document,
    table_ruleset_document,
)


def skip_record(name: str = "device_model_table") -> TableRuleRecord:
    return TableRuleRecord(
        selector=TableRuleSelector(kind=TableRuleSelectorKind.EXACT, value=name),
        precedence_class=SelectorPrecedenceClass.SKIP,
        static_role=TableStaticRole.SKIP,
        table_storage=TableStorageDisposition.OMIT,
        canonical_key_policy=CanonicalKeyPolicy.NONE,
        ordered_policy=OrderedPolicy.NONE,
    )


def net_cfg_record() -> TableRuleRecord:
    selector = TableRuleSelector(kind=TableRuleSelectorKind.EXACT, value="net_cfg")
    return TableRuleRecord(
        selector=selector,
        precedence_class=SelectorPrecedenceClass.STANDARD_EXACT,
        static_role=TableStaticRole.STANDARD_DIFF,
        table_storage=TableStorageDisposition.PROJECT,
        canonical_key_policy=CanonicalKeyPolicy.EXPLICIT,
        ordered_policy=OrderedPolicy.NONE,
        compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
        compare_key_columns=("board", "link_no"),
        ignored_columns=("no",),
        artifact_scope=TableArtifactScope.ALL_CHANGES,
        dropped_columns=(DroppedColumn(name="no", reason=legacy_ignored_column_reason(selector)),),
    )


def ordered_syx_record() -> TableRuleRecord:
    return ordered_record(r"^b\d+_n\d+_iec104_syx_list$")


def ordered_record(pattern: str) -> TableRuleRecord:
    return TableRuleRecord(
        selector=TableRuleSelector(kind=TableRuleSelectorKind.REGEX, value=pattern),
        precedence_class=SelectorPrecedenceClass.ORDERED_DIFF,
        static_role=TableStaticRole.ORDERED_DIFF,
        table_storage=TableStorageDisposition.PROJECT,
        canonical_key_policy=CanonicalKeyPolicy.EXPLICIT,
        ordered_policy=OrderedPolicy.GID_NO_V1,
        compare_key_mode=TableCompareKeyMode.ORDERED_STABLE_KEY,
        compare_key_columns=("gid",),
        artifact_scope=TableArtifactScope.ORDERED_SEMANTIC,
        position_column="no",
        stable_key_candidates=("gid",),
        structural_columns=("no",),
    )


def fallback_record() -> TableRuleRecord:
    return TableRuleRecord(
        selector=TableRuleSelector(kind=TableRuleSelectorKind.FALLBACK, value=FALLBACK_SELECTOR_VALUE),
        precedence_class=SelectorPrecedenceClass.STANDARD_RAW_PK_FALLBACK,
        static_role=TableStaticRole.STANDARD_DIFF,
        table_storage=TableStorageDisposition.PROJECT,
        canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY,
        ordered_policy=OrderedPolicy.NONE,
        compare_key_mode=TableCompareKeyMode.RAW_PRIMARY_KEY,
        artifact_scope=TableArtifactScope.ALL_CHANGES,
    )


def protocol_option_record(pattern: str, *, key_columns: tuple[str, ...] = ("page_no", "no")) -> TableRuleRecord:
    return TableRuleRecord(
        selector=TableRuleSelector(kind=TableRuleSelectorKind.REGEX, value=pattern),
        precedence_class=SelectorPrecedenceClass.STANDARD_PROTOCOL_OPTION,
        static_role=TableStaticRole.STANDARD_DIFF,
        table_storage=TableStorageDisposition.PROJECT,
        canonical_key_policy=CanonicalKeyPolicy.EXPLICIT,
        ordered_policy=OrderedPolicy.NONE,
        compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
        compare_key_columns=key_columns,
        artifact_scope=TableArtifactScope.ALL_CHANGES,
    )


def keyless_record(name: str = "notes") -> TableRuleRecord:
    return TableRuleRecord(
        selector=TableRuleSelector(kind=TableRuleSelectorKind.EXACT, value=name),
        precedence_class=SelectorPrecedenceClass.STANDARD_EXACT,
        static_role=TableStaticRole.STANDARD_DIFF,
        table_storage=TableStorageDisposition.PROJECT,
        canonical_key_policy=CanonicalKeyPolicy.EXPLICIT_KEYLESS,
        ordered_policy=OrderedPolicy.NONE,
        artifact_scope=TableArtifactScope.ALL_CHANGES,
    )


def snapshot_from_records(*records: TableRuleRecord) -> TableRulesetSnapshot:
    draft = table_ruleset_document(
        TableRulesetSnapshot(table_ruleset_version=1)
    )
    draft["rules"] = [record.to_document() for record in records]
    return table_ruleset_from_document(draft)
