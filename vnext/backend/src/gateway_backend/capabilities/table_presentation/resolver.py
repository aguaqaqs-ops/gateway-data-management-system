"""Resolve frozen comments and the two-side column union without changing schema identity."""

from __future__ import annotations

import re
from dataclasses import dataclass

from gateway_backend.capabilities.snapshot_materialization.contracts import SnapshotColumnDescriptor
from gateway_backend.capabilities.table_presentation.metadata import TablePresentation
from gateway_backend.capabilities.table_presentation.rules import COLUMN_ORDER_RULES


@dataclass(frozen=True, slots=True)
class PresentedColumn:
    name: str
    display_name: str
    scalar_type: str | None
    nullable: bool
    present_in: str
    pinned: bool
    display_order: int


def table_display_name(
    name: str, before: TablePresentation | None, current: TablePresentation | None,
) -> str:
    return (current.comment if current else None) or (before.comment if before else None) or name


def present_columns(
    table_name: str,
    before: tuple[SnapshotColumnDescriptor, ...],
    current: tuple[SnapshotColumnDescriptor, ...],
    *,
    before_presentation: TablePresentation | None = None,
    current_presentation: TablePresentation | None = None,
    side: str | None = None,
) -> tuple[PresentedColumn, ...]:
    """Arrays remain in canonical name order; display_order owns rendering order.

    A replacement side is resolved independently and cannot borrow opposite comments.
    Empty current columns are also valid for a deleted table.
    """
    if side not in {None, "BEFORE", "CURRENT"}:
        raise ValueError("invalid presentation side")
    if side == "BEFORE":
        current, current_presentation = (), None
    elif side == "CURRENT":
        before, before_presentation = (), None
    old = {c.name: c for c in before}
    new = {c.name: c for c in current}
    if len(old) != len(before) or len(new) != len(current):
        raise ValueError("duplicate column names")
    names = set(old) | set(new)
    primary = [c.name for c in current or before]
    rule = next((order for pattern, order in COLUMN_ORDER_RULES
                 if re.fullmatch(pattern, table_name)), ())
    order = [n for n in rule if n in primary]
    order.extend(n for n in primary if n not in order)
    order.extend(c.name for c in before if c.name not in order)
    positions = {name: i for i, name in enumerate(order)}
    old_comments = {} if before_presentation is None else {
        c.name: c.comment for c in before_presentation.columns}
    new_comments = {} if current_presentation is None else {
        c.name: c.comment for c in current_presentation.columns}
    pinned = ({"no"} & names) | ({"name"} if "name" in names else {"description"} & names)
    return tuple(PresentedColumn(
        name=name,
        display_name=new_comments.get(name) or old_comments.get(name) or name,
        scalar_type=(new.get(name) or old[name]).scalar_type,
        nullable=(new.get(name) or old[name]).nullable,
        present_in="BOTH" if name in old and name in new else (
            "CURRENT" if name in new else "BEFORE"),
        pinned=name in pinned,
        display_order=positions[name],
    ) for name in sorted(names, key=lambda n: n.encode("utf-8")))
