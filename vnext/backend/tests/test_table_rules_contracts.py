"""Table Rules injection-surface tests. Full rule matrix remains R4."""

from __future__ import annotations

import pytest
from gateway_backend.capabilities.table_rules.contracts import (
    TABLE_RULESET_VERSION,
    TableCompareKey,
    TableRulesetSnapshot,
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
