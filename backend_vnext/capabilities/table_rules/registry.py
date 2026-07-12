from __future__ import annotations

import re
from dataclasses import dataclass, field

from ...contracts.versions import TABLE_RULESET_VERSION
from ...core.identifiers import canonical_identifier
from .models import (
    TableArtifactScope,
    TableCompareKeyMode,
    TableKeyRule,
    TableRuleDefinition,
    TableRuleSource,
    TableStaticRole,
)
from .semantic import TableSemanticDecision, build_table_semantic_decision


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
PROTOCOL_CFG_TABLE_SEGMENTS: tuple[str, ...] = (
    "iec104",
    "iec61850c",
    "nr103d",
    "dev103",
    "dev104",
    "nbridge",
)
PROTOCOL_CFG_TABLE_SEGMENT_PATTERN = "|".join(re.escape(segment) for segment in PROTOCOL_CFG_TABLE_SEGMENTS)
PROTOCOL_OPTION_CFG_TABLE_PATTERN = re.compile(
    rf"^b\d+_n\d+_(?:{PROTOCOL_CFG_TABLE_SEGMENT_PATTERN})_cfg$",
    re.IGNORECASE,
)
PROTOCOL_DEVICE_CFG_TABLE_PATTERN = re.compile(
    rf"^b\d+_n\d+_(?:{PROTOCOL_CFG_TABLE_SEGMENT_PATTERN})_dev_cfg$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class TableRuleRegistry:
    table_ruleset_version: str = TABLE_RULESET_VERSION
    skipped_tables: TableRuleSource | None = None
    snapshot_only_tables: TableRuleSource | None = None
    browse_only_tables: TableRuleSource | None = None
    ordered_tables: TableRuleSource | None = None
    _standard_rules_by_table_name: dict[str, TableKeyRule] = field(init=False, repr=False, default_factory=dict)
    _ordered_rule: TableKeyRule = field(init=False, repr=False)
    _protocol_option_cfg_rule: TableKeyRule = field(init=False, repr=False)
    _protocol_device_cfg_rule: TableKeyRule = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.table_ruleset_version, str) or not self.table_ruleset_version:
            raise ValueError("table_ruleset_version must be a non-empty string")
        object.__setattr__(
            self,
            "skipped_tables",
            self.skipped_tables or TableRuleSource.from_sources(
                exact_table_names=DEFAULT_SKIPPED_TABLE_NAMES
            ),
        )
        object.__setattr__(
            self,
            "snapshot_only_tables",
            self.snapshot_only_tables or TableRuleSource.from_sources(
                regex_patterns=DEFAULT_SNAPSHOT_ONLY_TABLE_PATTERNS
            ),
        )
        object.__setattr__(
            self,
            "browse_only_tables",
            self.browse_only_tables or TableRuleSource.from_sources(
                exact_table_names=DEFAULT_BROWSE_ONLY_TABLE_NAMES
            ),
        )
        object.__setattr__(
            self,
            "ordered_tables",
            self.ordered_tables
            or TableRuleSource.from_sources(
                regex_patterns=tuple(rf"^b\d+_n\d+_{re.escape(family)}$" for family in IEC104_ORDERED_FAMILIES)
            ),
        )
        standard_rules = {
            "net_cfg": TableKeyRule(
                compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
                compare_key_columns=("board", "link_no"),
                ignored_columns=frozenset({"NO"}),
            ),
            **{
                table_name: TableKeyRule(
                    compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
                    compare_key_columns=("gid",),
                    artifact_scope=TableArtifactScope.UPDATE_ONLY,
                )
                for table_name in DEVICE_POINT_UPDATE_ONLY_TABLE_NAMES
            },
            "com_cfg": TableKeyRule(
                compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
                compare_key_columns=("index",),
                ignored_columns=frozenset({"NO"}),
            ),
            "pointref_forwardtbl": TableKeyRule(
                compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
                compare_key_columns=("refname",),
            ),
            "scdmod_para": TableKeyRule(
                compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
                compare_key_columns=("ied_model",),
                ignored_columns=frozenset({"NO"}),
            ),
            "app_cfg": TableKeyRule(
                compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
                compare_key_columns=("app_name",),
            ),
            "rdb_cfg": TableKeyRule(
                compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
                compare_key_columns=("NO",),
            ),
        }
        ordered_rule = TableKeyRule(
            compare_key_mode=TableCompareKeyMode.ORDERED_STABLE_KEY,
            compare_key_columns=("gid",),
            ignored_columns=frozenset({"no"}),
            artifact_scope=TableArtifactScope.ORDERED_SEMANTIC,
            position_column="no",
            stable_key_candidates=("gid",),
        )
        protocol_option_cfg_rule = TableKeyRule(
            compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
            compare_key_columns=("page_no", "no"),
        )
        protocol_device_cfg_rule = TableKeyRule(
            compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
            compare_key_columns=("gid",),
        )
        object.__setattr__(self, "_standard_rules_by_table_name", standard_rules)
        object.__setattr__(self, "_ordered_rule", ordered_rule)
        object.__setattr__(self, "_protocol_option_cfg_rule", protocol_option_cfg_rule)
        object.__setattr__(self, "_protocol_device_cfg_rule", protocol_device_cfg_rule)

    def classify_static_role(self, table_name: str) -> TableStaticRole:
        if self.skipped_tables.matches(table_name):
            return TableStaticRole.SKIP
        if self.snapshot_only_tables.matches(table_name):
            return TableStaticRole.SNAPSHOT_ONLY
        if self.browse_only_tables.matches(table_name):
            return TableStaticRole.BROWSE_ONLY
        if self.ordered_tables.matches(table_name):
            return TableStaticRole.ORDERED_DIFF
        return TableStaticRole.STANDARD_DIFF

    def key_rule_for_table(
        self,
        table_name: str,
        *,
        primary_key_columns: tuple[str, ...] = (),
    ) -> TableKeyRule | None:
        canonical_name = canonical_identifier(table_name)
        static_role = self.classify_static_role(table_name)
        if static_role == TableStaticRole.ORDERED_DIFF:
            return self._ordered_rule
        if static_role != TableStaticRole.STANDARD_DIFF:
            return None
        explicit = self._standard_rules_by_table_name.get(canonical_name)
        if explicit is not None:
            return explicit
        if canonical_name == DEVICE_CFG_UPDATE_ONLY_TABLE_NAME:
            return TableKeyRule(
                compare_key_mode=TableCompareKeyMode.RAW_PRIMARY_KEY,
                compare_key_columns=tuple(primary_key_columns),
                artifact_scope=TableArtifactScope.UPDATE_ONLY,
            )
        if PROTOCOL_OPTION_CFG_TABLE_PATTERN.fullmatch(table_name):
            return self._protocol_option_cfg_rule
        if PROTOCOL_DEVICE_CFG_TABLE_PATTERN.fullmatch(table_name):
            return self._protocol_device_cfg_rule
        return TableKeyRule(
            compare_key_mode=TableCompareKeyMode.RAW_PRIMARY_KEY,
            compare_key_columns=tuple(primary_key_columns),
        )

    def resolve_table_semantics(
        self,
        table_name: str,
        *,
        primary_key_columns: tuple[str, ...] = (),
    ) -> TableSemanticDecision:
        static_role = self.classify_static_role(table_name)
        key_rule = self.key_rule_for_table(
            table_name,
            primary_key_columns=primary_key_columns,
        )
        if key_rule is None:
            return build_table_semantic_decision(
                table_name=table_name,
                static_role=static_role,
                primary_key_columns=primary_key_columns,
            )
        return build_table_semantic_decision(
            table_name=table_name,
            static_role=static_role,
            compare_key_mode=key_rule.compare_key_mode,
            compare_key_columns=key_rule.compare_key_columns,
            ignored_columns=key_rule.ignored_columns,
            primary_key_columns=primary_key_columns,
        )

    def table_rule_definitions(self) -> tuple[TableRuleDefinition, ...]:
        definitions: list[TableRuleDefinition] = []
        definitions.extend(_source_rule_definitions(self.skipped_tables, TableStaticRole.SKIP))
        definitions.extend(_source_rule_definitions(self.snapshot_only_tables, TableStaticRole.SNAPSHOT_ONLY))
        definitions.extend(_source_rule_definitions(self.browse_only_tables, TableStaticRole.BROWSE_ONLY))
        definitions.extend(_source_rule_definitions(self.ordered_tables, TableStaticRole.ORDERED_DIFF))
        definitions.append(
            TableRuleDefinition(
                table_selector="net_cfg",
                static_role=TableStaticRole.STANDARD_DIFF,
                compare_key_columns=("board", "link_no"),
                ignored_columns=frozenset({"NO"}),
            )
        )
        definitions.extend(
            TableRuleDefinition(
                table_selector=table_name,
                static_role=TableStaticRole.STANDARD_DIFF,
                compare_key_columns=("gid",),
                artifact_scope=TableArtifactScope.UPDATE_ONLY,
            )
            for table_name in DEVICE_POINT_UPDATE_ONLY_TABLE_NAMES
        )
        definitions.append(
            TableRuleDefinition(
                table_selector=DEVICE_CFG_UPDATE_ONLY_TABLE_NAME,
                static_role=TableStaticRole.STANDARD_DIFF,
                artifact_scope=TableArtifactScope.UPDATE_ONLY,
            )
        )
        definitions.append(
            TableRuleDefinition(
                table_selector="com_cfg",
                static_role=TableStaticRole.STANDARD_DIFF,
                compare_key_columns=("index",),
                ignored_columns=frozenset({"NO"}),
            )
        )
        definitions.append(
            TableRuleDefinition(
                table_selector="pointref_forwardtbl",
                static_role=TableStaticRole.STANDARD_DIFF,
                compare_key_columns=("refname",),
            )
        )
        definitions.append(
            TableRuleDefinition(
                table_selector="scdmod_para",
                static_role=TableStaticRole.STANDARD_DIFF,
                compare_key_columns=("ied_model",),
                ignored_columns=frozenset({"NO"}),
            )
        )
        definitions.append(
            TableRuleDefinition(
                table_selector="app_cfg",
                static_role=TableStaticRole.STANDARD_DIFF,
                compare_key_columns=("app_name",),
            )
        )
        definitions.append(
            TableRuleDefinition(
                table_selector="rdb_cfg",
                static_role=TableStaticRole.STANDARD_DIFF,
                compare_key_columns=("NO",),
            )
        )
        definitions.extend(
            TableRuleDefinition(
                table_selector=pattern,
                static_role=TableStaticRole.STANDARD_DIFF,
                compare_key_columns=("page_no", "no"),
            )
            for pattern in (PROTOCOL_OPTION_CFG_TABLE_PATTERN.pattern,)
        )
        definitions.extend(
            TableRuleDefinition(
                table_selector=pattern,
                static_role=TableStaticRole.STANDARD_DIFF,
                compare_key_columns=("gid",),
            )
            for pattern in (PROTOCOL_DEVICE_CFG_TABLE_PATTERN.pattern,)
        )
        return tuple(definitions)


def _source_rule_definitions(
    source: TableRuleSource,
    static_role: TableStaticRole,
) -> tuple[TableRuleDefinition, ...]:
    definitions: list[TableRuleDefinition] = []
    for table_name in sorted(source.exact_table_names):
        definitions.append(
            TableRuleDefinition(
                table_selector=table_name,
                static_role=static_role,
                artifact_scope=(
                    TableArtifactScope.ORDERED_SEMANTIC
                    if static_role == TableStaticRole.ORDERED_DIFF
                    else TableArtifactScope.ALL_CHANGES
                ),
            )
        )
    for pattern in source.regex_patterns:
        definitions.append(
            TableRuleDefinition(
                table_selector=pattern,
                static_role=static_role,
                artifact_scope=(
                    TableArtifactScope.ORDERED_SEMANTIC
                    if static_role == TableStaticRole.ORDERED_DIFF
                    else TableArtifactScope.ALL_CHANGES
                ),
            )
        )
    return tuple(definitions)


def build_hardcoded_table_rule_registry() -> TableRuleRegistry:
    return TableRuleRegistry()


def default_table_rule_registry() -> TableRuleRegistry:
    return build_hardcoded_table_rule_registry()
