from __future__ import annotations

import pytest

from gateway_backend.capabilities.snapshot_materialization.contracts import SnapshotColumnDescriptor
from gateway_backend.capabilities.table_presentation.contracts import ColumnPresentation, TablePresentation
from gateway_backend.capabilities.table_presentation.resolver import present_columns, table_display_name
from gateway_backend.capabilities.table_presentation.rules import COLUMN_ORDER_RULES, PRESENTATION_RULES_VERSION

pytestmark = pytest.mark.unit


def columns(*names: str) -> tuple[SnapshotColumnDescriptor, ...]:
    return tuple(SnapshotColumnDescriptor(name, name, False, "INT") for name in names)


def test_union_uses_current_business_order_then_before_only_ddl_order() -> None:
    old = TablePresentation("device_st", "旧表", (ColumnPresentation("old_b", "旧乙"), ColumnPresentation("old_a", "旧甲"), ColumnPresentation("name", "旧名称")))
    new = TablePresentation("device_st", "新表", (ColumnPresentation("new", None), ColumnPresentation("dev_addr", "地址"), ColumnPresentation("name", "新名称")))
    result = present_columns("device_st", columns("old_b", "old_a", "name"), columns("new", "dev_addr", "name"), before_presentation=old, current_presentation=new)
    assert [c.name for c in result] == ["dev_addr", "name", "new", "old_a", "old_b"]
    assert [c.name for c in sorted(result, key=lambda c: c.display_order)] == ["name", "dev_addr", "new", "old_b", "old_a"]
    by_name = {c.name: c for c in result}
    assert by_name["old_b"].present_in == "BEFORE" and by_name["old_b"].display_name == "旧乙"
    assert by_name["name"].present_in == "BOTH" and by_name["name"].display_name == "新名称"
    assert by_name["name"].pinned
    assert table_display_name("device_st", old, new) == "新表"


@pytest.mark.parametrize("side", ["BEFORE", "CURRENT"])
def test_replacement_columns_only_borrow_same_side_metadata(side: str) -> None:
    before = TablePresentation("x", "旧", (ColumnPresentation("name", "旧名"),))
    current = TablePresentation("x", "新", (ColumnPresentation("name", None),))
    result = present_columns("x", columns("name"), columns("name"), before_presentation=before, current_presentation=current, side=side)
    assert result[0].present_in == side
    assert result[0].display_name == ("旧名" if side == "BEFORE" else "name")


@pytest.mark.parametrize("names,pinned", [(('no','name','description'), {'no','name'}), (('no','description'), {'no','description'}), (('x',), set())])
def test_pinning_uses_union_columns(names: tuple[str, ...], pinned: set[str]) -> None:
    result = present_columns("unknown", columns(*names), ())
    assert {c.name for c in result if c.pinned} == pinned
    assert sorted(c.display_order for c in result) == list(range(len(names)))


def test_registry_preserves_twenty_business_reorders_without_legacy_widths() -> None:
    assert PRESENTATION_RULES_VERSION == 1
    assert len(COLUMN_ORDER_RULES) == 20
    result = present_columns("b1_n2_iec104_yc_list", (), columns("gid", "dev_addr", "name", "no", "future"))
    assert [c.name for c in sorted(result, key=lambda c: c.display_order)] == ["no", "name", "dev_addr", "gid", "future"]
