from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ....core.identifiers import canonical_identifier
from .models import OrderedEntityKeyKind, OrderedPreparedRow


@dataclass(frozen=True, slots=True)
class OrderedPreparationError(Exception):
    reason: str

    def __init__(self, reason: str) -> None:
        Exception.__init__(self, reason)
        object.__setattr__(self, "reason", reason)


def prepare_ordered_rows(
    *,
    rows: Sequence[Sequence[object] | Mapping[str, object]],
    columns: Sequence[str],
    stable_key_field: str,
    position_field: str,
    pseudo_key_start: int = 2_000_000_000,
    side: str,
) -> tuple[OrderedPreparedRow, ...]:
    if not isinstance(side, str) or not side.strip():
        raise ValueError("side must be a non-empty string")
    canonical_columns = tuple(canonical_identifier(column) for column in columns if canonical_identifier(column))
    stable_key_field = canonical_identifier(stable_key_field)
    position_field = canonical_identifier(position_field)
    if stable_key_field not in canonical_columns:
        raise OrderedPreparationError("ORDERED_STABLE_KEY_MISSING")
    if position_field not in canonical_columns:
        raise OrderedPreparationError("ORDERED_POSITION_FIELD_MISSING")

    positioned_rows: list[tuple[int, int, dict[str, object]]] = []
    seen_positions: set[int] = set()
    for row_index, row in enumerate(rows):
        row_mapping = _row_to_mapping(row=row, columns=canonical_columns)
        position = _normalize_int(_lookup_value(row_mapping, position_field))
        if position is None or position <= 0:
            raise OrderedPreparationError("invalid_position_value")
        if position in seen_positions:
            raise OrderedPreparationError("duplicate_position")
        seen_positions.add(position)
        positioned_rows.append((position, row_index, row_mapping))

    positioned_rows.sort(key=lambda item: (item[0], item[1]))
    if [item[0] for item in positioned_rows] != list(range(1, len(positioned_rows) + 1)):
        raise OrderedPreparationError("invalid_position_sequence")

    prepared_rows: list[OrderedPreparedRow] = []
    used_stable_values: set[int] = set()
    seen_row_keys: set[str] = set()
    next_pseudo = pseudo_key_start
    for position, _, row_mapping in positioned_rows:
        stable_value = _normalize_int(
            _lookup_value(row_mapping, stable_key_field),
            zero_is_missing=True,
        )
        if stable_value is None:
            while next_pseudo in used_stable_values:
                next_pseudo += 1
            stable_value = next_pseudo
            next_pseudo += 1
            used_stable_values.add(stable_value)
            row_key = f"{stable_key_field}={stable_value}@{side}"
            entity_key_kind = OrderedEntityKeyKind.PSEUDO_BLANK
            blank_signature = _blank_signature(
                row=row_mapping,
                stable_key_field=stable_key_field,
                position_field=position_field,
            )
        else:
            used_stable_values.add(stable_value)
            row_key = f"{stable_key_field}={stable_value}"
            entity_key_kind = OrderedEntityKeyKind.REAL_STABLE
            blank_signature = None

        if row_key in seen_row_keys:
            raise OrderedPreparationError("duplicate_stable_key")
        seen_row_keys.add(row_key)
        prepared_rows.append(
            OrderedPreparedRow(
                row_key=row_key,
                entity_key_kind=entity_key_kind,
                position=position,
                row=row_mapping,
                blank_signature=blank_signature,
            )
        )
    return tuple(prepared_rows)


def _row_to_mapping(
    *,
    row: Sequence[object] | Mapping[str, object],
    columns: Sequence[str],
) -> dict[str, object]:
    if isinstance(row, Mapping):
        return {canonical_identifier(key): value for key, value in row.items() if canonical_identifier(key)}
    if len(row) != len(columns):
        raise OrderedPreparationError("row_width_mismatch")
    return {canonical_identifier(column): value for column, value in zip(columns, row)}


def _blank_signature(
    *,
    row: Mapping[str, object],
    stable_key_field: str,
    position_field: str,
) -> tuple[tuple[str, object], ...]:
    ignored = {stable_key_field.lower(), position_field.lower()}
    return tuple((column, row[column]) for column in row if column.lower() not in ignored)


def _lookup_value(row: Mapping[str, object], field_name: str) -> object | None:
    lowered = {column.lower(): value for column, value in row.items()}
    return lowered.get(field_name.lower())


def _normalize_int(value: object | None, *, zero_is_missing: bool = False) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        if zero_is_missing and value == 0:
            return None
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        normalized = int(text)
    except ValueError:
        return None
    if zero_is_missing and normalized == 0:
        return None
    return normalized
