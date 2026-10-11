"""Immutable migrated table-ruleset snapshot. Not a hidden global registry."""

from __future__ import annotations

import re
from functools import cache

from gateway_backend.capabilities.table_rules.contracts import (
    FALLBACK_SELECTOR_VALUE,
    ORDERED_IDENTITY_COLUMN,
    ORDERED_POSITION_COLUMN,
    TABLE_RULESET_VERSION,
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
    table_ruleset_document,
    table_ruleset_from_document,
)

DEFAULT_SKIPPED_TABLE_NAMES: tuple[str, ...] = (
    "device_model_table",
    "scdmod_fcda",
    "scdmod_yk",
    "scdmod_dataset",
    "scdmod_rpt",
    "scdmod_ld",
    "scdmod_log",
    "scdmod_sgcb",
)
DEFAULT_SNAPSHOT_ONLY_TABLE_PATTERNS: tuple[str, ...] = (r"^forwardtable_.*$",)
DEFAULT_BROWSE_ONLY_TABLE_NAMES: tuple[str, ...] = (
    "version_manager",
    "device_model_cfg",
    "board_cfg",
    "dev_grp",
    "dev_list",
    "model_grp",
    "primary_equipment_object_cfg",
    "prot_list",
    "prot_right",
    "project",
    "rule_61850dev_praser_cfg",
    "rule_61850dev_praser_default_cfg",
    "rule_61850point_praser_cfg",
)
DEVICE_POINT_UPDATE_ONLY_TABLE_NAMES: tuple[str, ...] = (
    "device_st",
    "device_mx",
    "device_co",
    "device_sg",
    "device_sp",
    "device_cnt",
    "device_sn",
    "device_tap",
    "device_other",
    "device_disturb",
)
DEVICE_CFG_UPDATE_ONLY_TABLE_NAME = "device_cfg"
COMPOSITE_SIGNAL_POINT_TABLE_NAME = "composite_signal_point"
COMPOSITE_SIGNAL_POINT_KEY_COLUMNS: tuple[str, ...] = ("source_table", "point_gid")
COMPOSITE_SIGNAL_POINT_IGNORED_COLUMNS: tuple[str, ...] = (
    "dev_addr",
    "device_gid",
    "point_payload_json",
)
COMPOSITE_SIGNAL_POINT_COMPARE_EXCLUDED_COLUMNS: tuple[str, ...] = (
    "formula_ast_json",
    "point_name",
)
IEC104_ORDERED_FAMILIES: tuple[str, ...] = (
    "iec104_syx_list",
    "iec104_dyx_list",
    "iec104_yc_list",
    "iec104_syk_list",
    "iec104_dyk_list",
    "iec104_yt_list",
    "iec104_ym_list",
    "iec104_sc_list",
    "iec104_yp_list",
)
IEC104_ORDERED_TABLE_PATTERNS: tuple[str, ...] = tuple(
    rf"^b\d+_n\d+_{re.escape(family)}$" for family in IEC104_ORDERED_FAMILIES
)
PROTOCOL_CFG_TABLE_SEGMENTS: tuple[str, ...] = (
    "iec104",
    "iec61850c",
    "nr103d",
    "dev103",
    "dev104",
    "nbridge",
)
PROTOCOL_CFG_TABLE_SEGMENT_PATTERN = "|".join(
    re.escape(segment) for segment in PROTOCOL_CFG_TABLE_SEGMENTS
)
PROTOCOL_OPTION_CFG_TABLE_PATTERN = (
    rf"^b\d+_n\d+_(?:{PROTOCOL_CFG_TABLE_SEGMENT_PATTERN})_cfg$"
)
PROTOCOL_DEVICE_CFG_TABLE_PATTERN = (
    rf"^b\d+_n\d+_(?:{PROTOCOL_CFG_TABLE_SEGMENT_PATTERN})_dev_cfg$"
)
PRECEDENCE_RANK: dict[SelectorPrecedenceClass, int] = {
    SelectorPrecedenceClass.SKIP: 0,
    SelectorPrecedenceClass.SNAPSHOT_ONLY: 1,
    SelectorPrecedenceClass.BROWSE_ONLY: 2,
    SelectorPrecedenceClass.ORDERED_DIFF: 3,
    SelectorPrecedenceClass.STANDARD_EXACT: 4,
    SelectorPrecedenceClass.STANDARD_DEVICE_CFG: 5,
    SelectorPrecedenceClass.STANDARD_PROTOCOL_OPTION: 6,
    SelectorPrecedenceClass.STANDARD_PROTOCOL_DEVICE: 7,
    SelectorPrecedenceClass.STANDARD_RAW_PK_FALLBACK: 8,
}


def migrated_table_rule_records() -> tuple[TableRuleRecord, ...]:
    records = (
        *_skip_records(),
        *_snapshot_only_records(),
        *_browse_only_records(),
        *_ordered_records(),
        *_standard_exact_records(),
        _device_cfg_record(),
        *_protocol_records(),
        _raw_pk_fallback_record(),
    )
    return tuple(
        sorted(
            records,
            key=lambda record: (
                PRECEDENCE_RANK[record.precedence_class],
                record.selector.canonical_serialization(),
            ),
        )
    )


@cache
def migrated_table_ruleset_snapshot() -> TableRulesetSnapshot:
    draft = table_ruleset_document(TableRulesetSnapshot(table_ruleset_version=TABLE_RULESET_VERSION))
    draft["rules"] = [record.to_document() for record in migrated_table_rule_records()]
    return table_ruleset_from_document(draft)


def _skip_records() -> tuple[TableRuleRecord, ...]:
    return tuple(_skip_record(name) for name in DEFAULT_SKIPPED_TABLE_NAMES)


def _skip_record(name: str) -> TableRuleRecord:
    return TableRuleRecord(
        selector=TableRuleSelector(kind=TableRuleSelectorKind.EXACT, value=name),
        precedence_class=SelectorPrecedenceClass.SKIP,
        static_role=TableStaticRole.SKIP,
        table_storage=TableStorageDisposition.OMIT,
        canonical_key_policy=CanonicalKeyPolicy.NONE,
        ordered_policy=OrderedPolicy.NONE,
    )


def _snapshot_only_records() -> tuple[TableRuleRecord, ...]:
    return tuple(
        TableRuleRecord(
            selector=TableRuleSelector(kind=TableRuleSelectorKind.REGEX, value=pattern),
            precedence_class=SelectorPrecedenceClass.SNAPSHOT_ONLY,
            static_role=TableStaticRole.SNAPSHOT_ONLY,
            table_storage=TableStorageDisposition.PROJECT,
            canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY,
            ordered_policy=OrderedPolicy.NONE,
        )
        for pattern in DEFAULT_SNAPSHOT_ONLY_TABLE_PATTERNS
    )


def _browse_only_records() -> tuple[TableRuleRecord, ...]:
    return tuple(
        TableRuleRecord(
            selector=TableRuleSelector(kind=TableRuleSelectorKind.EXACT, value=name),
            precedence_class=SelectorPrecedenceClass.BROWSE_ONLY,
            static_role=TableStaticRole.BROWSE_ONLY,
            table_storage=TableStorageDisposition.PROJECT,
            canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY,
            ordered_policy=OrderedPolicy.NONE,
        )
        for name in DEFAULT_BROWSE_ONLY_TABLE_NAMES
    )


def _ordered_records() -> tuple[TableRuleRecord, ...]:
    return tuple(_ordered_record(pattern) for pattern in IEC104_ORDERED_TABLE_PATTERNS)


def _ordered_record(pattern: str) -> TableRuleRecord:
    return TableRuleRecord(
        selector=TableRuleSelector(kind=TableRuleSelectorKind.REGEX, value=pattern),
        precedence_class=SelectorPrecedenceClass.ORDERED_DIFF,
        static_role=TableStaticRole.ORDERED_DIFF,
        table_storage=TableStorageDisposition.PROJECT,
        canonical_key_policy=CanonicalKeyPolicy.EXPLICIT,
        ordered_policy=OrderedPolicy.GID_NO_V1,
        compare_key_mode=TableCompareKeyMode.ORDERED_STABLE_KEY,
        compare_key_columns=(ORDERED_IDENTITY_COLUMN,),
        artifact_scope=TableArtifactScope.ORDERED_SEMANTIC,
        position_column=ORDERED_POSITION_COLUMN,
        stable_key_candidates=(ORDERED_IDENTITY_COLUMN,),
        structural_columns=(ORDERED_POSITION_COLUMN,),
    )


def _standard_exact_records() -> tuple[TableRuleRecord, ...]:
    return (
        _explicit_standard_record(
            COMPOSITE_SIGNAL_POINT_TABLE_NAME,
            key_columns=COMPOSITE_SIGNAL_POINT_KEY_COLUMNS,
            ignored_columns=COMPOSITE_SIGNAL_POINT_IGNORED_COLUMNS,
            compare_excluded_columns=COMPOSITE_SIGNAL_POINT_COMPARE_EXCLUDED_COLUMNS,
        ),
        _explicit_standard_record("net_cfg", key_columns=("board", "link_no"), ignored_columns=("no",)),
        *_device_point_records(),
        _explicit_standard_record("com_cfg", key_columns=("index",), ignored_columns=("no",)),
        _explicit_standard_record("pointref_forwardtbl", key_columns=("refname",)),
        _explicit_standard_record("scdmod_para", key_columns=("ied_model",), ignored_columns=("no",)),
        _explicit_standard_record("app_cfg", key_columns=("app_name",)),
        _explicit_standard_record("rdb_cfg", key_columns=("no",)),
    )


def _device_point_records() -> tuple[TableRuleRecord, ...]:
    return tuple(
        _explicit_standard_record(
            name,
            key_columns=(ORDERED_IDENTITY_COLUMN,),
            artifact_scope=TableArtifactScope.UPDATE_ONLY,
        )
        for name in DEVICE_POINT_UPDATE_ONLY_TABLE_NAMES
    )


def _explicit_standard_record(
    name: str,
    *,
    key_columns: tuple[str, ...],
    ignored_columns: tuple[str, ...] = (),
    compare_excluded_columns: tuple[str, ...] = (),
    artifact_scope: TableArtifactScope = TableArtifactScope.ALL_CHANGES,
) -> TableRuleRecord:
    selector = TableRuleSelector(kind=TableRuleSelectorKind.EXACT, value=name)
    return TableRuleRecord(
        selector=selector,
        precedence_class=SelectorPrecedenceClass.STANDARD_EXACT,
        static_role=TableStaticRole.STANDARD_DIFF,
        table_storage=TableStorageDisposition.PROJECT,
        canonical_key_policy=CanonicalKeyPolicy.EXPLICIT,
        ordered_policy=OrderedPolicy.NONE,
        compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
        compare_key_columns=key_columns,
        ignored_columns=ignored_columns,
        compare_excluded_columns=compare_excluded_columns,
        artifact_scope=artifact_scope,
        dropped_columns=_ignored_drops(selector, ignored_columns),
    )


def _device_cfg_record() -> TableRuleRecord:
    return TableRuleRecord(
        selector=TableRuleSelector(
            kind=TableRuleSelectorKind.EXACT,
            value=DEVICE_CFG_UPDATE_ONLY_TABLE_NAME,
        ),
        precedence_class=SelectorPrecedenceClass.STANDARD_DEVICE_CFG,
        static_role=TableStaticRole.STANDARD_DIFF,
        table_storage=TableStorageDisposition.PROJECT,
        canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY,
        ordered_policy=OrderedPolicy.NONE,
        compare_key_mode=TableCompareKeyMode.RAW_PRIMARY_KEY,
        artifact_scope=TableArtifactScope.UPDATE_ONLY,
    )


def _protocol_records() -> tuple[TableRuleRecord, ...]:
    option_selector = TableRuleSelector(
        kind=TableRuleSelectorKind.REGEX,
        value=PROTOCOL_OPTION_CFG_TABLE_PATTERN,
    )
    device_selector = TableRuleSelector(
        kind=TableRuleSelectorKind.REGEX,
        value=PROTOCOL_DEVICE_CFG_TABLE_PATTERN,
    )
    return (
        TableRuleRecord(
            selector=option_selector,
            precedence_class=SelectorPrecedenceClass.STANDARD_PROTOCOL_OPTION,
            static_role=TableStaticRole.STANDARD_DIFF,
            table_storage=TableStorageDisposition.PROJECT,
            canonical_key_policy=CanonicalKeyPolicy.EXPLICIT,
            ordered_policy=OrderedPolicy.NONE,
            compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
            compare_key_columns=("page_no", "no"),
            artifact_scope=TableArtifactScope.ALL_CHANGES,
        ),
        TableRuleRecord(
            selector=device_selector,
            precedence_class=SelectorPrecedenceClass.STANDARD_PROTOCOL_DEVICE,
            static_role=TableStaticRole.STANDARD_DIFF,
            table_storage=TableStorageDisposition.PROJECT,
            canonical_key_policy=CanonicalKeyPolicy.EXPLICIT,
            ordered_policy=OrderedPolicy.NONE,
            compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
            compare_key_columns=(ORDERED_IDENTITY_COLUMN,),
            artifact_scope=TableArtifactScope.ALL_CHANGES,
        ),
    )


def _raw_pk_fallback_record() -> TableRuleRecord:
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


def _ignored_drops(
    selector: TableRuleSelector,
    ignored_columns: tuple[str, ...],
) -> tuple[DroppedColumn, ...]:
    reason = legacy_ignored_column_reason(selector)
    return tuple(DroppedColumn(name=name, reason=reason) for name in ignored_columns)
