"""Table Rules injection-surface and R4 public contract tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from gateway_backend.capabilities.table_rules.contracts import (
    RULESET_ID,
    RULESET_VERSION,
    STORAGE_PROJECTION_VERSION,
    TABLE_RULESET_CONTRACT_VERSION,
    TABLE_RULESET_VERSION,
    CanonicalKeyPolicy,
    DroppedColumn,
    OrderedPolicy,
    SelectorPrecedenceClass,
    TableArtifactScope,
    TableCompareKey,
    TableCompareKeyMode,
    TableRuleRecord,
    TableRuleSelector,
    TableRuleSelectorKind,
    TableRulesetSnapshot,
    TableStaticRole,
    TableStorageDisposition,
    compute_ruleset_digest,
    table_ruleset_document,
    table_ruleset_from_document,
)
from gateway_shared_kernel import DigestRef
from tests.support.table_rules import (
    net_cfg_record,
    ordered_syx_record,
    skip_record,
    snapshot_from_records,
)

_GOLDEN = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "golden"
    / "storage-projection"
    / "ruleset"
)


def test_empty_compare_keys_mean_ddl_pk_or_keyless() -> None:
    snapshot = TableRulesetSnapshot(table_ruleset_version=TABLE_RULESET_VERSION)
    assert snapshot.compare_keys == ()
    assert snapshot.table_ruleset_version == 1


def test_compare_keys_are_canonical_table_and_key_columns() -> None:
    snapshot = TableRulesetSnapshot(
        table_ruleset_version=1,
        compare_keys=(
            TableCompareKey(canonical_table="orders", key_columns=("id", "seq")),
        ),
    )
    assert snapshot.compare_keys[0].canonical_table == "orders"
    assert snapshot.compare_keys[0].key_columns == ("id", "seq")


def test_compare_key_rejects_empty_or_duplicate_columns() -> None:
    with pytest.raises(ValueError, match="key_columns must not be empty"):
        TableCompareKey(canonical_table="t", key_columns=())
    with pytest.raises(ValueError, match="key_columns must not contain duplicates"):
        TableCompareKey(canonical_table="t", key_columns=("id", "id"))


def test_ruleset_rejects_duplicate_canonical_table() -> None:
    first = TableCompareKey(canonical_table="t", key_columns=("id",))
    second = TableCompareKey(canonical_table="t", key_columns=("code",))
    with pytest.raises(ValueError, match="compare_keys must not repeat canonical_table"):
        TableRulesetSnapshot(table_ruleset_version=1, compare_keys=(first, second))


def test_additive_r3_snapshot_defaults_match_s0_identity() -> None:
    snapshot = TableRulesetSnapshot(table_ruleset_version=TABLE_RULESET_VERSION)
    assert snapshot.rules == ()
    assert snapshot.ruleset_digest is None
    assert snapshot.ruleset_id == RULESET_ID
    assert snapshot.ruleset_version == RULESET_VERSION
    assert snapshot.contract_version == TABLE_RULESET_CONTRACT_VERSION
    assert snapshot.storage_projection_version == STORAGE_PROJECTION_VERSION


def test_selector_serialization_is_deterministic() -> None:
    exact = TableRuleSelector(kind=TableRuleSelectorKind.EXACT, value=' "Net_Cfg" ')
    regex = TableRuleSelector(kind=TableRuleSelectorKind.REGEX, value=r"^forwardtable_.*$")
    fallback = TableRuleSelector(kind=TableRuleSelectorKind.FALLBACK, value="*")
    assert exact.canonical_serialization() == "exact:net_cfg"
    assert regex.canonical_serialization() == r"regex:^forwardtable_.*$"
    assert fallback.canonical_serialization() == "fallback:*"


def test_ruleset_document_round_trip_and_digest_stable() -> None:
    snapshot = snapshot_from_records(net_cfg_record(), ordered_syx_record())
    document = table_ruleset_document(snapshot)
    again = table_ruleset_from_document(document)
    assert again.ruleset_digest == snapshot.ruleset_digest
    assert compute_ruleset_digest(document) == snapshot.ruleset_digest
    assert compute_ruleset_digest(table_ruleset_document(again)) == snapshot.ruleset_digest


def test_golden_valid_ruleset_document_round_trips() -> None:
    payload = json.loads((_GOLDEN / "valid" / "s1-net-cfg" / "document.json").read_text(encoding="utf-8"))
    snapshot = table_ruleset_from_document(payload)
    assert snapshot.rules[0].selector.canonical_serialization() == "exact:net_cfg"
    assert snapshot.ruleset_digest == compute_ruleset_digest(payload)


def _duplicate_selector_document() -> dict[str, object]:
    record = net_cfg_record().to_document()
    document = table_ruleset_document(TableRulesetSnapshot(table_ruleset_version=1))
    document["rules"] = [record, record]
    return document


def _unknown_field_document() -> dict[str, object]:
    document = table_ruleset_document(snapshot_from_records(skip_record()))
    document["provider"] = "hidden"
    return document


def _digest_mismatch_snapshot() -> None:
    snapshot = snapshot_from_records(skip_record())
    TableRulesetSnapshot(
        table_ruleset_version=1,
        rules=snapshot.rules,
        ruleset_digest=DigestRef("sha256:" + "22" * 32),
    )


MALFORMED_RULESET_CASES: tuple[tuple[str, Callable[[], dict[str, object]], str], ...] = (
    (
        "duplicate selectors",
        _duplicate_selector_document,
        "duplicate selectors are forbidden",
    ),
    (
        "unknown fields",
        _unknown_field_document,
        "unknown fields",
    ),
)


MALFORMED_RECORD_CASES: tuple[tuple[str, Callable[[], TableRuleRecord], str], ...] = (
    (
        "ignored key",
        lambda: TableRuleRecord(
            selector=TableRuleSelector(kind=TableRuleSelectorKind.EXACT, value="rdb_cfg"),
            precedence_class=SelectorPrecedenceClass.STANDARD_EXACT,
            static_role=TableStaticRole.STANDARD_DIFF,
            table_storage=TableStorageDisposition.PROJECT,
            canonical_key_policy=CanonicalKeyPolicy.EXPLICIT,
            ordered_policy=OrderedPolicy.NONE,
            compare_key_mode=TableCompareKeyMode.EXPLICIT_KEY,
            compare_key_columns=("no",),
            ignored_columns=("no",),
            artifact_scope=TableArtifactScope.ALL_CHANGES,
            dropped_columns=(
                DroppedColumn(name="no", reason="legacy_ignored_column:rdb_cfg"),
            ),
        ),
        "ignored columns must not be effective key columns",
    ),
    (
        "ordered no drop",
        lambda: TableRuleRecord(
            selector=TableRuleSelector(
                kind=TableRuleSelectorKind.REGEX,
                value=r"^b\d+_n\d+_iec104_syx_list$",
            ),
            precedence_class=SelectorPrecedenceClass.ORDERED_DIFF,
            static_role=TableStaticRole.ORDERED_DIFF,
            table_storage=TableStorageDisposition.PROJECT,
            canonical_key_policy=CanonicalKeyPolicy.EXPLICIT,
            ordered_policy=OrderedPolicy.GID_NO_V1,
            compare_key_mode=TableCompareKeyMode.ORDERED_STABLE_KEY,
            compare_key_columns=("gid",),
            ignored_columns=("no",),
            artifact_scope=TableArtifactScope.ORDERED_SEMANTIC,
            position_column="no",
            stable_key_candidates=("gid",),
            structural_columns=("no",),
            dropped_columns=(
                DroppedColumn(
                    name="no",
                    reason="legacy_ignored_column:^b\\d+_n\\d+_iec104_syx_list$",
                ),
            ),
        ),
        "ordered no must not be DROP_FROM_STORAGE",
    ),
)


@pytest.mark.parametrize("label,factory,match", MALFORMED_RULESET_CASES)
def test_malformed_ruleset_documents_fail_closed(
    label: str,
    factory: Callable[[], dict[str, object]],
    match: str,
) -> None:
    del label
    with pytest.raises(ValueError, match=match):
        table_ruleset_from_document(factory())


@pytest.mark.parametrize("label,factory,match", MALFORMED_RECORD_CASES)
def test_malformed_rule_records_fail_closed(
    label: str,
    factory: Callable[[], TableRuleRecord],
    match: str,
) -> None:
    del label
    with pytest.raises(ValueError, match=match):
        factory()


@pytest.mark.parametrize(
    "case,excluded,match",
    (
        ("storage-drop", ("no",), "must not overlap"),
        ("effective-key", ("board",), "must not include keys"),
        ("dropped-column", ("aux",), "must be retained in storage"),
    ),
    ids=("overlap-with-storage-drop", "overlap-with-effective-key", "dropped-column"),
)
def test_compare_excluded_columns_cannot_conflict_with_storage_or_keys(
    case: str,
    excluded: tuple[str, ...],
    match: str,
) -> None:
    record = net_cfg_record()
    if case == "dropped-column":
        record = replace(
            record,
            ignored_columns=(),
            dropped_columns=(DroppedColumn(name="aux", reason="manual_rule"),),
        )
    with pytest.raises(ValueError, match=match):
        replace(record, compare_excluded_columns=excluded)


def test_digest_mismatch_fails_closed() -> None:
    with pytest.raises(ValueError, match="ruleset_digest does not match"):
        _digest_mismatch_snapshot()


def test_golden_duplicate_selector_is_rejected() -> None:
    payload = json.loads(
        (_GOLDEN / "malformed" / "s1-duplicate-selector" / "document.json").read_text(encoding="utf-8")
    )
    with pytest.raises(ValueError, match="duplicate selectors are forbidden"):
        table_ruleset_from_document(payload)
