"""Legacy rule-resolution parity for the migrated table-ruleset snapshot."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from gateway_backend.capabilities.table_rules.contracts import (
    FALLBACK_SELECTOR_VALUE,
    ORDERED_POSITION_COLUMN,
    CanonicalKeyPolicy,
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
    compute_ruleset_digest,
    legacy_ignored_column_reason,
    table_ruleset_document,
    table_ruleset_from_document,
)
from gateway_backend.capabilities.table_rules.registry import (
    COMPOSITE_SIGNAL_POINT_IGNORED_COLUMNS,
    COMPOSITE_SIGNAL_POINT_KEY_COLUMNS,
    COMPOSITE_SIGNAL_POINT_TABLE_NAME,
    DEFAULT_BROWSE_ONLY_TABLE_NAMES,
    DEFAULT_SKIPPED_TABLE_NAMES,
    DEVICE_POINT_UPDATE_ONLY_TABLE_NAMES,
    IEC104_ORDERED_FAMILIES,
    PROTOCOL_DEVICE_CFG_TABLE_PATTERN,
    PROTOCOL_OPTION_CFG_TABLE_PATTERN,
    migrated_table_rule_records,
    migrated_table_ruleset_snapshot,
)
from gateway_backend.capabilities.table_rules.resolver import resolve_table_rule
from tests.support.table_rules import (
    fallback_record,
    net_cfg_record,
    ordered_record,
    ordered_syx_record,
    protocol_option_record,
    skip_record,
    snapshot_from_records,
)
from tests.support.table_rules_legacy_oracle import legacy_oracle_decision

_GOLDEN = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "golden"
    / "storage-projection"
    / "ruleset"
    / "valid"
    / "s2-migrated-matrix"
    / "document.json"
)
_COMPOSITE_IGNORED = frozenset(COMPOSITE_SIGNAL_POINT_IGNORED_COLUMNS)
_MIGRATED_RULE_COUNT = 52


@dataclass(frozen=True, slots=True)
class ParityCase:
    label: str
    table_name: str
    primary_key_columns: tuple[str, ...]
    static_role: TableStaticRole
    selector: str
    compare_key_mode: TableCompareKeyMode | None
    compare_key_columns: tuple[str, ...]
    ignored_columns: frozenset[str]
    artifact_scope: TableArtifactScope | None
    position_column: str | None = None
    stable_key_candidates: tuple[str, ...] = ()


def _skip_case(name: str) -> ParityCase:
    return ParityCase(
        label=f"skip:{name}",
        table_name=name,
        primary_key_columns=(),
        static_role=TableStaticRole.SKIP,
        selector=f"exact:{name}",
        compare_key_mode=None,
        compare_key_columns=(),
        ignored_columns=frozenset(),
        artifact_scope=None,
    )


def _browse_case(name: str) -> ParityCase:
    return ParityCase(
        label=f"browse:{name}",
        table_name=name,
        primary_key_columns=(),
        static_role=TableStaticRole.BROWSE_ONLY,
        selector=f"exact:{name}",
        compare_key_mode=None,
        compare_key_columns=(),
        ignored_columns=frozenset(),
        artifact_scope=None,
    )


def _ordered_case(family: str) -> ParityCase:
    table_name = f"b1_n1_{family}"
    pattern = rf"^b\d+_n\d+_{family}$"
    return ParityCase(
        label=f"ordered:{family}",
        table_name=table_name,
        primary_key_columns=(),
        static_role=TableStaticRole.ORDERED_DIFF,
        selector=f"regex:{pattern}",
        compare_key_mode=TableCompareKeyMode.ORDERED_STABLE_KEY,
        compare_key_columns=("gid",),
        ignored_columns=frozenset({ORDERED_POSITION_COLUMN}),
        artifact_scope=TableArtifactScope.ORDERED_SEMANTIC,
        position_column=ORDERED_POSITION_COLUMN,
        stable_key_candidates=("gid",),
    )


def _exact_standard(
    name: str,
    *,
    key_columns: tuple[str, ...],
    ignored: frozenset[str] = frozenset(),
    scope: TableArtifactScope = TableArtifactScope.ALL_CHANGES,
) -> ParityCase:
    return ParityCase(
        label=f"standard:{name}",
        table_name=name,
        primary_key_columns=(),
        static_role=TableStaticRole.STANDARD_DIFF,
        selector=f"exact:{name}",
        compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
        compare_key_columns=key_columns,
        ignored_columns=ignored,
        artifact_scope=scope,
    )


def _device_point_case(name: str) -> ParityCase:
    return _exact_standard(
        name,
        key_columns=("gid",),
        scope=TableArtifactScope.UPDATE_ONLY,
    )


LEGACY_PARITY_CASES: tuple[ParityCase, ...] = (
    *(_skip_case(name) for name in DEFAULT_SKIPPED_TABLE_NAMES),
    ParityCase(
        label="snapshot:forwardtable_demo",
        table_name="forwardtable_demo",
        primary_key_columns=(),
        static_role=TableStaticRole.SNAPSHOT_ONLY,
        selector=r"regex:^forwardtable_.*$",
        compare_key_mode=None,
        compare_key_columns=(),
        ignored_columns=frozenset(),
        artifact_scope=None,
    ),
    ParityCase(
        label="snapshot:FORWARDTABLE_X",
        table_name="FORWARDTABLE_X",
        primary_key_columns=(),
        static_role=TableStaticRole.SNAPSHOT_ONLY,
        selector=r"regex:^forwardtable_.*$",
        compare_key_mode=None,
        compare_key_columns=(),
        ignored_columns=frozenset(),
        artifact_scope=None,
    ),
    *(_browse_case(name) for name in DEFAULT_BROWSE_ONLY_TABLE_NAMES),
    *(_ordered_case(family) for family in IEC104_ORDERED_FAMILIES),
    _exact_standard(
        COMPOSITE_SIGNAL_POINT_TABLE_NAME,
        key_columns=COMPOSITE_SIGNAL_POINT_KEY_COLUMNS,
        ignored=_COMPOSITE_IGNORED,
    ),
    _exact_standard("net_cfg", key_columns=("board", "link_no"), ignored=frozenset({"no"})),
    ParityCase(
        label="standard:Net_Cfg-case",
        table_name="Net_Cfg",
        primary_key_columns=(),
        static_role=TableStaticRole.STANDARD_DIFF,
        selector="exact:net_cfg",
        compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
        compare_key_columns=("board", "link_no"),
        ignored_columns=frozenset({"no"}),
        artifact_scope=TableArtifactScope.ALL_CHANGES,
    ),
    ParityCase(
        label="standard:quoted-net_cfg",
        table_name=' "Net_Cfg" ',
        primary_key_columns=(),
        static_role=TableStaticRole.STANDARD_DIFF,
        selector="exact:net_cfg",
        compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
        compare_key_columns=("board", "link_no"),
        ignored_columns=frozenset({"no"}),
        artifact_scope=TableArtifactScope.ALL_CHANGES,
    ),
    _exact_standard("com_cfg", key_columns=("index",), ignored=frozenset({"no"})),
    _exact_standard("pointref_forwardtbl", key_columns=("refname",)),
    _exact_standard("scdmod_para", key_columns=("ied_model",), ignored=frozenset({"no"})),
    _exact_standard("app_cfg", key_columns=("app_name",)),
    _exact_standard("rdb_cfg", key_columns=("no",)),
    *(_device_point_case(name) for name in DEVICE_POINT_UPDATE_ONLY_TABLE_NAMES),
    ParityCase(
        label="device_cfg:with-pk",
        table_name="device_cfg",
        primary_key_columns=("gid",),
        static_role=TableStaticRole.STANDARD_DIFF,
        selector="exact:device_cfg",
        compare_key_mode=TableCompareKeyMode.RAW_PRIMARY_KEY,
        compare_key_columns=("gid",),
        ignored_columns=frozenset(),
        artifact_scope=TableArtifactScope.UPDATE_ONLY,
    ),
    ParityCase(
        label="device_cfg:empty-pk",
        table_name="device_cfg",
        primary_key_columns=(),
        static_role=TableStaticRole.STANDARD_DIFF,
        selector="exact:device_cfg",
        compare_key_mode=TableCompareKeyMode.RAW_PRIMARY_KEY,
        compare_key_columns=(),
        ignored_columns=frozenset(),
        artifact_scope=TableArtifactScope.UPDATE_ONLY,
    ),
    ParityCase(
        label="protocol-option:b1_n1_iec104_cfg",
        table_name="b1_n1_iec104_cfg",
        primary_key_columns=(),
        static_role=TableStaticRole.STANDARD_DIFF,
        selector=f"regex:{PROTOCOL_OPTION_CFG_TABLE_PATTERN}",
        compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
        compare_key_columns=("page_no", "no"),
        ignored_columns=frozenset(),
        artifact_scope=TableArtifactScope.ALL_CHANGES,
    ),
    ParityCase(
        label="protocol-option:uppercase",
        table_name="B1_N1_IEC104_CFG",
        primary_key_columns=(),
        static_role=TableStaticRole.STANDARD_DIFF,
        selector=f"regex:{PROTOCOL_OPTION_CFG_TABLE_PATTERN}",
        compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
        compare_key_columns=("page_no", "no"),
        ignored_columns=frozenset(),
        artifact_scope=TableArtifactScope.ALL_CHANGES,
    ),
    ParityCase(
        label="protocol-device:b1_n1_iec104_dev_cfg",
        table_name="b1_n1_iec104_dev_cfg",
        primary_key_columns=(),
        static_role=TableStaticRole.STANDARD_DIFF,
        selector=f"regex:{PROTOCOL_DEVICE_CFG_TABLE_PATTERN}",
        compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
        compare_key_columns=("gid",),
        ignored_columns=frozenset(),
        artifact_scope=TableArtifactScope.ALL_CHANGES,
    ),
    ParityCase(
        label="fallback:orders",
        table_name="orders",
        primary_key_columns=("id",),
        static_role=TableStaticRole.STANDARD_DIFF,
        selector=f"fallback:{FALLBACK_SELECTOR_VALUE}",
        compare_key_mode=TableCompareKeyMode.RAW_PRIMARY_KEY,
        compare_key_columns=("id",),
        ignored_columns=frozenset(),
        artifact_scope=TableArtifactScope.ALL_CHANGES,
    ),
    ParityCase(
        label="fallback:unknown-empty-pk",
        table_name="unknown_table",
        primary_key_columns=(),
        static_role=TableStaticRole.STANDARD_DIFF,
        selector=f"fallback:{FALLBACK_SELECTOR_VALUE}",
        compare_key_mode=TableCompareKeyMode.RAW_PRIMARY_KEY,
        compare_key_columns=(),
        ignored_columns=frozenset(),
        artifact_scope=TableArtifactScope.ALL_CHANGES,
    ),
)

NON_OVERLAP_CASES: tuple[tuple[str, str, TableStaticRole, str], ...] = (
    (
        "pointref_forwardtbl not snapshot-only",
        "pointref_forwardtbl",
        TableStaticRole.STANDARD_DIFF,
        "exact:pointref_forwardtbl",
    ),
    (
        "scdmod_para not skip",
        "scdmod_para",
        TableStaticRole.STANDARD_DIFF,
        "exact:scdmod_para",
    ),
    (
        "device_model_table skip",
        "device_model_table",
        TableStaticRole.SKIP,
        "exact:device_model_table",
    ),
    (
        "device_model_cfg browse",
        "device_model_cfg",
        TableStaticRole.BROWSE_ONLY,
        "exact:device_model_cfg",
    ),
    (
        "version_manager browse not skip",
        "version_manager",
        TableStaticRole.BROWSE_ONLY,
        "exact:version_manager",
    ),
    (
        "iec104 list ordered",
        "b1_n1_iec104_syx_list",
        TableStaticRole.ORDERED_DIFF,
        r"regex:^b\d+_n\d+_iec104_syx_list$",
    ),
    (
        "iec104 option cfg",
        "b1_n1_iec104_cfg",
        TableStaticRole.STANDARD_DIFF,
        f"regex:{PROTOCOL_OPTION_CFG_TABLE_PATTERN}",
    ),
    (
        "iec104 device cfg",
        "b1_n1_iec104_dev_cfg",
        TableStaticRole.STANDARD_DIFF,
        f"regex:{PROTOCOL_DEVICE_CFG_TABLE_PATTERN}",
    ),
)

def _snapshot_only_foo() -> TableRuleRecord:
    return TableRuleRecord(
        selector=TableRuleSelector(kind=TableRuleSelectorKind.REGEX, value=r"^foo$"),
        precedence_class=SelectorPrecedenceClass.SNAPSHOT_ONLY,
        static_role=TableStaticRole.SNAPSHOT_ONLY,
        table_storage=TableStorageDisposition.PROJECT,
        canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY,
        ordered_policy=OrderedPolicy.NONE,
    )


PRECEDENCE_CASES: tuple[tuple[str, TableRulesetSnapshot, str, str], ...] = (
    (
        "skip over snapshot regex",
        snapshot_from_records(skip_record("foo"), _snapshot_only_foo()),
        "foo",
        "exact:foo",
    ),
    (
        "standard exact over protocol",
        snapshot_from_records(net_cfg_record(), protocol_option_record(r"^net_cfg$"), fallback_record()),
        "net_cfg",
        "exact:net_cfg",
    ),
    (
        "protocol over fallback",
        snapshot_from_records(protocol_option_record(r"^orders$"), fallback_record()),
        "orders",
        r"regex:^orders$",
    ),
)

COLLISION_CASES: tuple[tuple[str, TableRulesetSnapshot, str], ...] = (
    (
        "ordered regex overlap",
        snapshot_from_records(ordered_syx_record(), ordered_record(r"^b1_n1_iec104_syx_list$")),
        "b1_n1_iec104_syx_list",
    ),
    (
        "protocol regex overlap",
        snapshot_from_records(protocol_option_record(r"^orders$"), protocol_option_record(r"^ord.*$")),
        "orders",
    ),
)


@pytest.fixture(scope="module")
def migrated_snapshot() -> TableRulesetSnapshot:
    return migrated_table_ruleset_snapshot()


@pytest.mark.parametrize("case", LEGACY_PARITY_CASES, ids=lambda case: case.label)
def test_legacy_parity_cases(migrated_snapshot: TableRulesetSnapshot, case: ParityCase) -> None:
    resolved = resolve_table_rule(
        migrated_snapshot,
        case.table_name,
        primary_key_columns=case.primary_key_columns,
    )
    decision = resolved.decision
    assert decision.static_role is case.static_role
    assert decision.selector.canonical_serialization() == case.selector
    assert decision.compare_key_mode is case.compare_key_mode
    assert decision.compare_key_columns == case.compare_key_columns
    assert frozenset(decision.ignored_columns) == case.ignored_columns
    assert decision.artifact_scope is case.artifact_scope
    assert decision.position_column == case.position_column
    assert decision.stable_key_candidates == case.stable_key_candidates


@pytest.mark.parametrize("case", LEGACY_PARITY_CASES, ids=lambda case: case.label)
def test_legacy_oracle_matches_parity_cases(case: ParityCase) -> None:
    oracle = legacy_oracle_decision(case.table_name, primary_key_columns=case.primary_key_columns)
    assert oracle.static_role == case.static_role.value
    assert oracle.compare_key_mode == (
        None if case.compare_key_mode is None else case.compare_key_mode.value
    )
    assert oracle.compare_key_columns == case.compare_key_columns
    assert oracle.ignored_columns == case.ignored_columns
    assert oracle.artifact_scope == (
        None if case.artifact_scope is None else case.artifact_scope.value
    )
    assert oracle.position_column == case.position_column
    assert oracle.stable_key_candidates == case.stable_key_candidates


@pytest.mark.parametrize("label,table_name,role,selector", NON_OVERLAP_CASES)
def test_default_matrix_non_overlap(
    migrated_snapshot: TableRulesetSnapshot,
    label: str,
    table_name: str,
    role: TableStaticRole,
    selector: str,
) -> None:
    del label
    resolved = resolve_table_rule(migrated_snapshot, table_name)
    assert resolved.decision.static_role is role
    assert resolved.decision.selector.canonical_serialization() == selector


@pytest.mark.parametrize("label,snapshot,table_name,selector", PRECEDENCE_CASES)
def test_selector_precedence_uses_rank_not_insertion_order(
    label: str,
    snapshot: TableRulesetSnapshot,
    table_name: str,
    selector: str,
) -> None:
    del label
    resolved = resolve_table_rule(snapshot, table_name, primary_key_columns=("id",))
    assert resolved.decision.selector.canonical_serialization() == selector


@pytest.mark.parametrize("label,snapshot,table_name", COLLISION_CASES)
def test_same_rank_selector_collision_fails_closed(
    label: str,
    snapshot: TableRulesetSnapshot,
    table_name: str,
) -> None:
    del label
    with pytest.raises(ValueError, match="incompatible selector collision"):
        resolve_table_rule(snapshot, table_name)


def test_duplicate_fallback_is_rejected_at_snapshot_construction() -> None:
    with pytest.raises(ValueError, match="duplicate selectors are forbidden"):
        snapshot_from_records(fallback_record(), fallback_record())


def test_ignored_columns_map_to_storage_drops() -> None:
    for record in migrated_table_rule_records():
        dropped_by_name = {item.name: item for item in record.dropped_columns}
        if record.ordered_policy is OrderedPolicy.GID_NO_V1:
            assert ORDERED_POSITION_COLUMN in record.ignored_columns
            assert ORDERED_POSITION_COLUMN in record.structural_columns
            assert ORDERED_POSITION_COLUMN not in dropped_by_name
            continue
        expected_reason = legacy_ignored_column_reason(record.selector)
        for name in record.ignored_columns:
            assert dropped_by_name[name].reason == expected_reason


def test_migrated_snapshot_digest_is_stable() -> None:
    first = migrated_table_ruleset_snapshot()
    second = migrated_table_ruleset_snapshot()
    document = table_ruleset_document(first)
    assert first.ruleset_digest == second.ruleset_digest
    assert compute_ruleset_digest(document) == first.ruleset_digest
    assert table_ruleset_from_document(document).ruleset_digest == first.ruleset_digest
    assert len(first.rules) == _MIGRATED_RULE_COUNT


def test_golden_migrated_matrix_round_trips() -> None:
    payload = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    snapshot = table_ruleset_from_document(payload)
    expected = migrated_table_ruleset_snapshot()
    assert snapshot.ruleset_digest == expected.ruleset_digest
    assert snapshot.rules == expected.rules


def test_empty_rules_snapshot_is_unclassified() -> None:
    snapshot = TableRulesetSnapshot(table_ruleset_version=1)
    with pytest.raises(ValueError, match="unclassified table"):
        resolve_table_rule(snapshot, "orders", primary_key_columns=("id",))
