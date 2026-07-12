from __future__ import annotations

from collections.abc import Mapping, Sequence

from .models import (
    OrderedEntityKeyKind,
    OrderedReplayValidation,
    OrderedSemanticKind,
    OrderedSemanticOp,
)


def validate_ordered_replay(
    *,
    before_rows: tuple[dict[str, object], ...],
    after_rows: tuple[dict[str, object], ...],
    semantic_ops: tuple[OrderedSemanticOp, ...],
    position_field: str,
) -> OrderedReplayValidation:
    replayed_rows = _replay_current_rows(
        before_rows=before_rows,
        after_row_count=len(after_rows),
        semantic_ops=semantic_ops,
    )
    if replayed_rows is None:
        return OrderedReplayValidation(
            semantic_replay_passed=False,
            artifact_replay_passed=False,
            mismatch_count=1,
            mismatch_examples=({"reason": "semantic_replay_failed"},),
        )

    replayed = _normalize_rows_for_current_slot_space(replayed_rows, position_field=position_field)
    expected = _normalize_rows_for_current_slot_space(after_rows, position_field=position_field)
    mismatches = _mismatch_examples(replayed, expected)
    passed = not mismatches and len(replayed) == len(expected)
    return OrderedReplayValidation(
        semantic_replay_passed=passed,
        artifact_replay_passed=passed,
        mismatch_count=len(mismatches),
        mismatch_examples=tuple(mismatches[:5]),
    )


def _replay_current_rows(
    *,
    before_rows: tuple[dict[str, object], ...],
    after_row_count: int,
    semantic_ops: tuple[OrderedSemanticOp, ...],
) -> list[dict[str, object]] | None:
    consumed_before_positions: set[int] = set()
    current_rows_by_position: dict[int, dict[str, object]] = {}
    moves_by_key: dict[str, OrderedSemanticOp] = {}
    updates_by_key: dict[str, OrderedSemanticOp] = {}

    def consume(before_position: int | None) -> bool:
        if before_position is None:
            return True
        if before_position in consumed_before_positions:
            return False
        consumed_before_positions.add(before_position)
        return True

    def place(after_position: int | None, payload: Mapping[str, object] | None) -> bool:
        if after_position is None or payload is None:
            return False
        if after_position < 1 or after_position > after_row_count:
            return False
        if after_position in current_rows_by_position:
            return False
        current_rows_by_position[after_position] = dict(payload)
        return True

    for op in semantic_ops:
        if op.semantic_kind == OrderedSemanticKind.MOVE:
            moves_by_key[op.row_key] = op
            continue
        if op.semantic_kind == OrderedSemanticKind.CONTENT_UPDATE:
            updates_by_key[op.row_key] = op
            continue
        if op.semantic_kind in {
            OrderedSemanticKind.DATA_INSERT,
            OrderedSemanticKind.BLANK_INSERT_INTERVAL,
        }:
            if not place(op.after_position, op.payload_after):
                return None
            continue
        if op.semantic_kind in {
            OrderedSemanticKind.DATA_DELETE,
            OrderedSemanticKind.BLANK_DELETE_INTERVAL,
        }:
            if not consume(op.before_position):
                return None
            continue

    for row_key, move in moves_by_key.items():
        update = updates_by_key.pop(row_key, None)
        if not consume(move.before_position):
            return None
        payload_after = update.payload_after if update is not None else move.payload_after
        if not place(move.after_position, payload_after):
            return None

    for update in updates_by_key.values():
        if not consume(update.before_position):
            return None
        if not place(update.after_position, update.payload_after):
            return None

    slots: list[dict[str, object] | None] = [None] * after_row_count
    for after_position, payload in current_rows_by_position.items():
        slots[after_position - 1] = payload

    next_open_slot = 0
    for before_position, row in enumerate(before_rows, start=1):
        if before_position in consumed_before_positions:
            continue
        while next_open_slot < after_row_count and slots[next_open_slot] is not None:
            next_open_slot += 1
        if next_open_slot >= after_row_count:
            return None
        slots[next_open_slot] = dict(row)

    if any(slot is None for slot in slots):
        return None
    return [slot for slot in slots if slot is not None]


def _normalize_rows_for_current_slot_space(
    rows: Sequence[Mapping[str, object]],
    *,
    position_field: str,
) -> list[dict[str, object]]:
    return [
        _row_with_position(
            row=dict(row),
            position_field=position_field,
            position=row_index,
        )
        for row_index, row in enumerate(rows, start=1)
    ]


def _mismatch_examples(
    replayed: list[dict[str, object]],
    expected: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    mismatches: list[dict[str, object]] = []
    for index, (replayed_row, expected_row) in enumerate(zip(replayed, expected, strict=False), start=1):
        if replayed_row != dict(expected_row):
            mismatches.append(
                {
                    "row_index": index,
                    "replayed": replayed_row,
                    "expected": dict(expected_row),
                }
            )
    if len(replayed) != len(expected):
        mismatches.append(
            {
                "row_count_mismatch": True,
                "replayed_count": len(replayed),
                "expected_count": len(expected),
            }
        )
    return mismatches


def _row_with_position(
    *,
    row: dict[str, object],
    position_field: str,
    position: int,
) -> dict[str, object]:
    row[position_field] = position
    return row
