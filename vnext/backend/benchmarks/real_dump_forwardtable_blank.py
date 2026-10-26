"""Count forwardtable row-state patterns without exporting source cell values.

This investigation reads the production SQL parser's source-order table
readers before canonical projection. It also validates each present target
table through the normal materialization and projection path so classifier
refusals are not bypassed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from gateway_shared_kernel import (
    BitScalar,
    DecimalScalar,
    Float32Scalar,
    Float64Scalar,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    UnsignedIntegerScalar,
)

from gateway_backend.capabilities.table_access.contracts import (
    NeverCancel,
    ParserInvocationContext,
    SqlParseRequest,
    SqlSourceInput,
)
from gateway_backend.capabilities.table_access.sql import parse_sql
from gateway_shared_kernel import raw_blob_digest

from benchmarks.real_dump_keyless_census import (
    CensusRefusal,
    DatasetSpec,
    _close_readers,
    _expected_specs,
    _failure_codes,
    _materialize_project,
    _parse_package,
)

_TARGET_TABLES = (
    "forwardtable_yc1",
    "forwardtable_yc2",
    "forwardtable_yk1",
    "forwardtable_yt1",
    "forwardtable_yx1",
    "forwardtable_yx2",
)
_DATASET_IDS = (
    "rd-t1-a-v1",
    "rd-t1-a-v2",
    "rd-t2-b-v1",
    "rd-t2-b-v2",
    "rd-t3-c-v1",
    "rd-t3-c-v2",
    "rd-t4-d-v1",
    "rd-t4-d-v2",
)
_PACKAGE_PAIRS = (
    ("rd-t1-a-v1", "rd-t1-a-v2"),
    ("rd-t2-b-v1", "rd-t2-b-v2"),
    ("rd-t3-c-v1", "rd-t3-c-v2"),
    ("rd-t4-d-v1", "rd-t4-d-v2"),
)


def _numeric_value(cell: object) -> Decimal | None:
    if isinstance(cell, (SignedIntegerScalar, UnsignedIntegerScalar, DecimalScalar)):
        try:
            value = Decimal(cell.decimal)
        except InvalidOperation:
            return None
        return value if value.is_finite() else None
    if isinstance(cell, Float32Scalar):
        try:
            value = struct.unpack(">f", bytes.fromhex(cell.bits_hex))[0]
        except (ValueError, struct.error):
            return None
        return Decimal.from_float(value) if math.isfinite(value) else None
    if isinstance(cell, Float64Scalar):
        try:
            value = struct.unpack(">d", bytes.fromhex(cell.bits_hex))[0]
        except (ValueError, struct.error):
            return None
        return Decimal.from_float(value) if math.isfinite(value) else None
    if isinstance(cell, BitScalar):
        return Decimal(int.from_bytes(cell.raw_bytes, "big"))
    return None


def _cell_state(cell: object) -> str:
    if isinstance(cell, NullScalar):
        return "NULL"
    if isinstance(cell, StringScalar) and cell.text == "":
        return "EMPTY_STRING"
    numeric = _numeric_value(cell)
    if numeric == 0:
        return "NUMERIC_ZERO"
    return "OTHER_NONEMPTY"


def _row_fingerprint(schema: tuple[tuple[str, str], ...], row: tuple[object, ...]) -> bytes:
    """Hash parsed cells only; fingerprints never leave process memory."""

    return hashlib.sha256(repr((schema, row)).encode("utf-8")).digest()


def _cell_fingerprint(cell: object) -> bytes:
    return hashlib.sha256(repr(cell).encode("utf-8")).digest()


def _parse_source_tables(spec: DatasetSpec) -> tuple[dict[str, Any], tuple[Any, ...]]:
    sql_bytes, _xml_bytes, _store = _parse_package(spec.package_path)
    context = ParserInvocationContext(NeverCancel())
    result = parse_sql(
        SqlParseRequest(
            source=SqlSourceInput(
                document_content_digest=raw_blob_digest(sql_bytes),
                sql_source_digest=raw_blob_digest(sql_bytes),
                parser_input_contract_version=1,
                encoding="utf-8",
                source_size_bytes=len(sql_bytes),
            ),
            sql_utf8=sql_bytes,
            context=context,
        )
    )
    if result.status.value != "COMPLETE":
        raise CensusRefusal(
            f"{spec.dataset_id}: source SQL parsing incomplete ({_failure_codes(result.diagnostics)})"
        )
    return ({table.descriptor.canonical_name: table for table in result.tables}, result.tables)


def _validate_classifier_and_projection(
    spec: DatasetSpec,
) -> dict[str, Any]:
    metadata, projected_tables = _materialize_project(spec)
    try:
        selected: dict[str, Any] = {}
        for table_name in _TARGET_TABLES:
            item = metadata.get(table_name)
            if item is None:
                continue
            if item.rule_category != "SNAPSHOT_ONLY" or not item.keyless:
                raise CensusRefusal(
                    f"{spec.dataset_id}/{table_name}: expected SNAPSHOT_ONLY keyless classification"
                )
            selected[table_name] = item
        return selected
    finally:
        _close_readers(projected_tables)


def _pattern_key(states: tuple[str, ...]) -> str:
    return ";".join(states)


def _pattern_entry(columns: tuple[str, ...], states: tuple[str, ...]) -> dict[str, Any]:
    return {
        "columns": list(columns),
        "states": list(states),
        "label": _pattern_key(states),
    }


def _gid_stats(rows: Sequence[tuple[object, ...]], gid_index: int) -> dict[str, Any]:
    counts: Counter[bytes] = Counter()
    null_rows = 0
    for row in rows:
        value = row[gid_index]
        if isinstance(value, NullScalar):
            null_rows += 1
        else:
            counts[_cell_fingerprint(value)] += 1
    duplicate_groups = sum(count > 1 for count in counts.values())
    duplicate_extra_rows = sum(count - 1 for count in counts.values() if count > 1)
    return {
        "row_count": len(rows),
        "gid_null_rows": null_rows,
        "gid_non_null_duplicate_group_count": duplicate_groups,
        "gid_non_null_duplicate_extra_rows": duplicate_extra_rows,
        "gid_non_null_unique": duplicate_groups == 0,
    }


def _source_order_stats(
    columns: tuple[str, ...], rows: Sequence[tuple[object, ...]]
) -> dict[str, Any]:
    gid_index = columns.index("gid")
    content_indexes = tuple(index for index, name in enumerate(columns) if name != "gid")
    row_states = [tuple(_cell_state(cell) for cell in row) for row in rows]
    point_rows = [
        index
        for index, states in enumerate(row_states)
        if any(states[column_index] == "OTHER_NONEMPTY" for column_index in content_indexes)
    ]
    point_row_set = set(point_rows)
    blank_proxy_rows = [index for index in range(len(rows)) if index not in point_row_set]

    point_gids = [rows[index][gid_index] for index in point_rows]
    gid_null_rows = sum(isinstance(value, NullScalar) for value in point_gids)
    gid_numbers = [_numeric_value(value) for value in point_gids]
    gid_non_numeric_rows = sum(
        not isinstance(value, NullScalar) and number is None
        for value, number in zip(point_gids, gid_numbers, strict=True)
    )
    comparable_pairs = 0
    descents = 0
    equal_pairs = 0
    for left, right in zip(gid_numbers, gid_numbers[1:]):
        if left is None or right is None:
            continue
        comparable_pairs += 1
        if right < left:
            descents += 1
        elif right == left:
            equal_pairs += 1
    order_evaluable: bool | None = (
        None
        if not point_gids
        else gid_null_rows == 0 and gid_non_numeric_rows == 0
    )
    non_decreasing: bool | None = (
        descents == 0 if order_evaluable is True else None
    )
    strictly_increasing: bool | None = (
        descents == 0 and equal_pairs == 0 if order_evaluable is True else None
    )
    point_gid_stats = _gid_stats([rows[index] for index in point_rows], gid_index)

    if point_rows:
        first_point = point_rows[0]
        last_point = point_rows[-1]
        leading = sum(index < first_point for index in blank_proxy_rows)
        interleaved = sum(first_point < index < last_point for index in blank_proxy_rows)
        trailing = sum(index > last_point for index in blank_proxy_rows)
        no_reference = 0
    else:
        leading = interleaved = trailing = 0
        no_reference = len(blank_proxy_rows)

    pattern_positions: dict[tuple[str, ...], Counter[str]] = defaultdict(Counter)
    for index, states in enumerate(row_states):
        if index in point_row_set:
            bucket = "point_proxy_rows"
        elif not point_rows:
            bucket = "no_point_proxy_reference_rows"
        elif index < point_rows[0]:
            bucket = "leading_blank_proxy_rows"
        elif index > point_rows[-1]:
            bucket = "trailing_blank_proxy_rows"
        else:
            bucket = "interleaved_blank_proxy_rows"
        pattern_positions[states][bucket] += 1

    return {
        "source_order_stage": "production SQL parser ParseResult / SqlTableReader, before business materialization and canonical projection",
        "row_count": len(rows),
        "non_empty_point_proxy": {
            "definition": "row with OTHER_NONEMPTY in at least one non-gid column",
            "row_count": len(point_rows),
            **point_gid_stats,
            "gid_non_numeric_rows": gid_non_numeric_rows,
            "gid_numeric_order_evaluable": order_evaluable,
            "gid_non_decreasing": non_decreasing,
            "gid_strictly_increasing": strictly_increasing,
            "gid_descending_adjacent_pair_count": descents,
            "gid_equal_adjacent_pair_count": equal_pairs,
            "gid_comparable_adjacent_pair_count": comparable_pairs,
        },
        "blank_point_proxy_distribution": {
            "definition": "row with no OTHER_NONEMPTY state in any non-gid column; not a business classification",
            "row_count": len(blank_proxy_rows),
            "leading_before_first_point_proxy_rows": leading,
            "interleaved_between_point_proxy_rows": interleaved,
            "trailing_after_last_point_proxy_rows": trailing,
            "no_point_proxy_reference_rows": no_reference,
        },
        "state_pattern_positions": [
            {
                "states": list(states),
                "label": _pattern_key(states),
                **dict(sorted(counts.items())),
            }
            for states, counts in sorted(pattern_positions.items())
        ],
    }


def _scan_table(
    spec: DatasetSpec,
    table_name: str,
    parsed: Any,
    projected_metadata: Any,
) -> dict[str, Any]:
    descriptor = parsed.descriptor
    columns = tuple(column.canonical_name for column in descriptor.columns)
    if "gid" not in columns:
        raise CensusRefusal(f"{spec.dataset_id}/{table_name}: gid column is absent")
    projected_columns = projected_metadata.columns
    if columns != projected_columns:
        raise CensusRefusal(f"{spec.dataset_id}/{table_name}: source/projection columns differ")
    if parsed.reader is None:
        raise CensusRefusal(f"{spec.dataset_id}/{table_name}: source parser reader unavailable")

    schema = tuple((column.canonical_name, column.sql_type) for column in descriptor.columns)
    rows: list[tuple[object, ...]] = []
    try:
        for row in parsed.reader.iter_rows():
            if len(row) != len(columns):
                raise CensusRefusal(f"{spec.dataset_id}/{table_name}: source row width mismatch")
            rows.append(tuple(row))
    finally:
        parsed.reader.close()
    if len(rows) != projected_metadata.row_count:
        raise CensusRefusal(f"{spec.dataset_id}/{table_name}: source/projection row counts differ")

    fingerprints: dict[bytes, list[int]] = defaultdict(list)
    row_states = [tuple(_cell_state(cell) for cell in row) for row in rows]
    for index, row in enumerate(rows):
        fingerprints[_row_fingerprint(schema, row)].append(index)
    duplicate_groups = [positions for positions in fingerprints.values() if len(positions) > 1]
    duplicate_group_indexes = {
        index for positions in duplicate_groups for index in positions
    }
    singleton_indexes = [
        positions[0] for positions in fingerprints.values() if len(positions) == 1
    ]
    duplicate_patterns: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for positions in duplicate_groups:
        duplicate_patterns[row_states[positions[0]]].append(len(positions))
    singleton_patterns: Counter[tuple[str, ...]] = Counter(
        row_states[index] for index in singleton_indexes
    )
    duplicate_group_rows = sum(len(positions) for positions in duplicate_groups)
    duplicate_extra_rows = sum(len(positions) - 1 for positions in duplicate_groups)
    gid_index = columns.index("gid")
    remaining_rows = [rows[index] for index in singleton_indexes]

    return {
        "dataset_id": spec.dataset_id,
        "table_name": table_name,
        "present": True,
        "columns": list(columns),
        "row_count": len(rows),
        "exact_duplicates": {
            "group_count": len(duplicate_groups),
            "extra_rows": duplicate_extra_rows,
            "rows_in_groups": duplicate_group_rows,
            "by_state_pattern": [
                {
                    **_pattern_entry(columns, states),
                    "group_count": len(multiplicities),
                    "row_count": sum(multiplicities),
                    "extra_rows": sum(value - 1 for value in multiplicities),
                }
                for states, multiplicities in sorted(duplicate_patterns.items())
            ],
        },
        "non_duplicate_rows": {
            "row_count": len(singleton_indexes),
            "by_state_pattern": [
                {
                    **_pattern_entry(columns, states),
                    "row_count": count,
                }
                for states, count in sorted(singleton_patterns.items())
            ],
        },
        "after_duplicate_groups_removed": _gid_stats(remaining_rows, gid_index),
        "source_order": {
            **_source_order_stats(columns, rows),
            "duplicate_group_row_count": len(duplicate_group_indexes),
        },
    }


def _empty_table_entry(dataset_id: str, table_name: str) -> dict[str, Any]:
    return {
        "dataset_id": dataset_id,
        "table_name": table_name,
        "present": False,
        "columns": [],
        "row_count": 0,
        "exact_duplicates": {
            "group_count": 0,
            "extra_rows": 0,
            "rows_in_groups": 0,
            "by_state_pattern": [],
        },
        "non_duplicate_rows": {"row_count": 0, "by_state_pattern": []},
        "after_duplicate_groups_removed": {
            "row_count": 0,
            "gid_null_rows": 0,
            "gid_non_null_duplicate_group_count": 0,
            "gid_non_null_duplicate_extra_rows": 0,
            "gid_non_null_unique": None,
        },
        "source_order": {
            "source_order_stage": "production SQL parser ParseResult / SqlTableReader, before business materialization and canonical projection",
            "row_count": 0,
            "non_empty_point_proxy": {
                "definition": "row with OTHER_NONEMPTY in at least one non-gid column",
                "row_count": 0,
                "gid_null_rows": 0,
                "gid_non_null_duplicate_group_count": 0,
                "gid_non_null_duplicate_extra_rows": 0,
                "gid_non_null_unique": None,
                "gid_non_numeric_rows": 0,
                "gid_numeric_order_evaluable": None,
                "gid_non_decreasing": None,
                "gid_strictly_increasing": None,
                "gid_descending_adjacent_pair_count": 0,
                "gid_equal_adjacent_pair_count": 0,
                "gid_comparable_adjacent_pair_count": 0,
            },
            "blank_point_proxy_distribution": {
                "definition": "row with no OTHER_NONEMPTY state in any non-gid column; not a business classification",
                "row_count": 0,
                "leading_before_first_point_proxy_rows": 0,
                "interleaved_between_point_proxy_rows": 0,
                "trailing_after_last_point_proxy_rows": 0,
                "no_point_proxy_reference_rows": 0,
            },
            "state_pattern_positions": [],
            "duplicate_group_row_count": 0,
        },
    }


def _build_report(specs: tuple[DatasetSpec, ...]) -> dict[str, Any]:
    if tuple(spec.dataset_id for spec in specs) != _DATASET_IDS:
        raise CensusRefusal("expected the eight t1–t4 v1/v2 datasets in fixed order")
    all_rows: dict[str, dict[str, dict[str, Any]]] = {dataset_id: {} for dataset_id in _DATASET_IDS}
    for spec in specs:
        print(f"classifier-validation {spec.dataset_id}", flush=True)
        projected = _validate_classifier_and_projection(spec)
        parsed_tables, raw_tables = _parse_source_tables(spec)
        try:
            for table_name in _TARGET_TABLES:
                parsed = parsed_tables.get(table_name)
                projected_metadata = projected.get(table_name)
                if parsed is None and projected_metadata is None:
                    all_rows[spec.dataset_id][table_name] = _empty_table_entry(
                        spec.dataset_id, table_name
                    )
                    continue
                if parsed is None or projected_metadata is None:
                    raise CensusRefusal(
                        f"{spec.dataset_id}/{table_name}: source/projection table presence differs"
                    )
                print(f"source-order-scan {spec.dataset_id}/{table_name}", flush=True)
                all_rows[spec.dataset_id][table_name] = _scan_table(
                    spec, table_name, parsed, projected_metadata
                )
        finally:
            for parsed in raw_tables:
                if parsed.reader is not None:
                    parsed.reader.close()

    tables: list[dict[str, Any]] = []
    for table_name in _TARGET_TABLES:
        datasets = [all_rows[dataset_id][table_name] for dataset_id in _DATASET_IDS]
        tables.append(
            {
                "table_name": table_name,
                "datasets": datasets,
                "version_changes": _version_changes(datasets),
            }
        )
    return {
        "schema": "gateway-vnext.real-dump-forwardtable-blank-investigation/v1",
        "datasets": list(_DATASET_IDS),
        "tables": tables,
        "method": {
            "row_stage": "production SQL parser ParseResult / SqlTableReader, before business materialization and canonical projection",
            "source_order_check": "parse_sql scans SQL statements in source order; parse_insert appends each tuple span; SqlTableReader.iter_rows yields the stored spans in order",
            "empty_point_business_definition": "not assigned; state patterns and status-only order proxies are reported for owner classification",
            "classifier_gate": "each present target is materialized and canonically projected first; anything other than SNAPSHOT_ONLY keyless is refused",
        },
    }


def _version_changes(datasets: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {item["dataset_id"]: item for item in datasets}
    changes: list[dict[str, Any]] = []
    metric_paths = (
        ("row_count", ("row_count",)),
        ("duplicate_group_count", ("exact_duplicates", "group_count")),
        ("duplicate_extra_rows", ("exact_duplicates", "extra_rows")),
        ("duplicate_group_rows", ("exact_duplicates", "rows_in_groups")),
        ("non_duplicate_rows", ("non_duplicate_rows", "row_count")),
        ("remaining_gid_null_rows", ("after_duplicate_groups_removed", "gid_null_rows")),
        (
            "remaining_gid_duplicate_groups",
            ("after_duplicate_groups_removed", "gid_non_null_duplicate_group_count"),
        ),
        (
            "remaining_gid_duplicate_extra_rows",
            ("after_duplicate_groups_removed", "gid_non_null_duplicate_extra_rows"),
        ),
        (
            "non_empty_point_proxy_rows",
            ("source_order", "non_empty_point_proxy", "row_count"),
        ),
        (
            "non_empty_point_gid_null_rows",
            ("source_order", "non_empty_point_proxy", "gid_null_rows"),
        ),
        (
            "non_empty_point_gid_duplicate_groups",
            (
                "source_order",
                "non_empty_point_proxy",
                "gid_non_null_duplicate_group_count",
            ),
        ),
        (
            "non_empty_point_gid_duplicate_extra_rows",
            (
                "source_order",
                "non_empty_point_proxy",
                "gid_non_null_duplicate_extra_rows",
            ),
        ),
        (
            "non_empty_point_gid_non_numeric_rows",
            ("source_order", "non_empty_point_proxy", "gid_non_numeric_rows"),
        ),
        (
            "non_empty_point_gid_comparable_adjacent_pairs",
            (
                "source_order",
                "non_empty_point_proxy",
                "gid_comparable_adjacent_pair_count",
            ),
        ),
        (
            "gid_descending_adjacent_pairs",
            (
                "source_order",
                "non_empty_point_proxy",
                "gid_descending_adjacent_pair_count",
            ),
        ),
        (
            "gid_equal_adjacent_pairs",
            (
                "source_order",
                "non_empty_point_proxy",
                "gid_equal_adjacent_pair_count",
            ),
        ),
        (
            "blank_proxy_leading_rows",
            (
                "source_order",
                "blank_point_proxy_distribution",
                "leading_before_first_point_proxy_rows",
            ),
        ),
        (
            "blank_proxy_interleaved_rows",
            (
                "source_order",
                "blank_point_proxy_distribution",
                "interleaved_between_point_proxy_rows",
            ),
        ),
        (
            "blank_proxy_trailing_rows",
            (
                "source_order",
                "blank_point_proxy_distribution",
                "trailing_after_last_point_proxy_rows",
            ),
        ),
        (
            "blank_proxy_without_point_reference_rows",
            (
                "source_order",
                "blank_point_proxy_distribution",
                "no_point_proxy_reference_rows",
            ),
        ),
    )
    for before_id, after_id in _PACKAGE_PAIRS:
        before = by_id[before_id]
        after = by_id[after_id]
        deltas: dict[str, int] = {}
        for label, path in metric_paths:
            before_value: Any = before
            after_value: Any = after
            for key in path:
                before_value = before_value[key]
                after_value = after_value[key]
            deltas[label] = int(after_value) - int(before_value)
        before_patterns = _pattern_counts(before)
        after_patterns = _pattern_counts(after)
        pattern_deltas = []
        for states in sorted(set(before_patterns) | set(after_patterns)):
            before_count = before_patterns.get(states, {})
            after_count = after_patterns.get(states, {})
            pattern_deltas.append(
                {
                    "columns": after["columns"] if after["present"] else before["columns"],
                    "states": list(states),
                    "label": _pattern_key(states),
                    "duplicate_group_count_delta": after_count.get("duplicate_group_count", 0)
                    - before_count.get("duplicate_group_count", 0),
                    "duplicate_row_count_delta": after_count.get("duplicate_row_count", 0)
                    - before_count.get("duplicate_row_count", 0),
                    "duplicate_extra_rows_delta": after_count.get("duplicate_extra_rows", 0)
                    - before_count.get("duplicate_extra_rows", 0),
                    "singleton_row_count_delta": after_count.get("singleton_row_count", 0)
                    - before_count.get("singleton_row_count", 0),
                    "point_proxy_row_count_delta": after_count.get("point_proxy_row_count", 0)
                    - before_count.get("point_proxy_row_count", 0),
                    "leading_blank_proxy_rows_delta": after_count.get("leading_blank_proxy_rows", 0)
                    - before_count.get("leading_blank_proxy_rows", 0),
                    "interleaved_blank_proxy_rows_delta": after_count.get("interleaved_blank_proxy_rows", 0)
                    - before_count.get("interleaved_blank_proxy_rows", 0),
                    "trailing_blank_proxy_rows_delta": after_count.get("trailing_blank_proxy_rows", 0)
                    - before_count.get("trailing_blank_proxy_rows", 0),
                    "no_point_proxy_reference_rows_delta": after_count.get(
                        "no_point_proxy_reference_rows", 0
                    )
                    - before_count.get("no_point_proxy_reference_rows", 0),
                }
            )
        changes.append(
            {
                "v1_dataset_id": before_id,
                "v2_dataset_id": after_id,
                "presence_changed": before["present"] != after["present"],
                "columns_changed": before["columns"] != after["columns"],
                "deltas": deltas,
                "non_empty_point_gid_non_decreasing_v1": before["source_order"][
                    "non_empty_point_proxy"
                ]["gid_non_decreasing"],
                "non_empty_point_gid_non_decreasing_v2": after["source_order"][
                    "non_empty_point_proxy"
                ]["gid_non_decreasing"],
                "non_empty_point_gid_order_evaluable_v1": before["source_order"][
                    "non_empty_point_proxy"
                ]["gid_numeric_order_evaluable"],
                "non_empty_point_gid_order_evaluable_v2": after["source_order"][
                    "non_empty_point_proxy"
                ]["gid_numeric_order_evaluable"],
                "pattern_deltas": pattern_deltas,
            }
        )
    return changes


def _pattern_counts(
    dataset: dict[str, Any],
) -> defaultdict[tuple[str, ...], Counter[str]]:
    result: defaultdict[tuple[str, ...], Counter[str]] = defaultdict(Counter)
    for entry in dataset["exact_duplicates"]["by_state_pattern"]:
        key = tuple(entry["states"])
        result[key]["duplicate_group_count"] += entry["group_count"]
        result[key]["duplicate_row_count"] += entry["row_count"]
        result[key]["duplicate_extra_rows"] += entry["extra_rows"]
    for entry in dataset["non_duplicate_rows"]["by_state_pattern"]:
        result[tuple(entry["states"])]["singleton_row_count"] += entry["row_count"]
    for entry in dataset["source_order"]["state_pattern_positions"]:
        key = tuple(entry["states"])
        result[key]["point_proxy_row_count"] += entry.get("point_proxy_rows", 0)
        result[key]["leading_blank_proxy_rows"] += entry.get("leading_blank_proxy_rows", 0)
        result[key]["interleaved_blank_proxy_rows"] += entry.get(
            "interleaved_blank_proxy_rows", 0
        )
        result[key]["trailing_blank_proxy_rows"] += entry.get("trailing_blank_proxy_rows", 0)
        result[key]["no_point_proxy_reference_rows"] += entry.get(
            "no_point_proxy_reference_rows", 0
        )
    return result


def _pattern_text(columns: Sequence[str], states: Sequence[str]) -> str:
    return "; ".join(f"{column}={state}" for column, state in zip(columns, states, strict=True))


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# `forwardtable_*` 空点行专项调查",
        "",
        "## 方法",
        "",
        "- 输入为调试节点上的 t1–t4 v1、v2 共 8 份真实数据；原始 SQL 与单元格值仅在进程内处理，不写入 JSON、日志或本报告。",
        "- 先通过现有 staging、业务物化与规范投影路径验证 auto-mode 分类；任一目标表不是 `SNAPSHOT_ONLY` 且 keyless 时立即拒绝，不绕过分类器。随后统计取自 production SQL parser 的 `ParseResult` / `SqlTableReader`，在业务物化和规范投影之前。原始解析列与投影列、原始读取行数与投影行数逐表核对。",
        "- 源顺序核对：`parse_sql` 按 SQL statement 扫描顺序调用 `parse_insert`；后者按 VALUES tuple 顺序追加 `TupleSpan`；`_assemble` 将 span 顺序交给 `SqlTableReader`，其 `iter_rows()` 顺序遍历 span。故此处记录的是各表 INSERT tuple 的源顺序，不是规范投影或重排后的顺序。",
        "- 完全重复按解析后的完整行（包含列名、SQL 类型和 typed cell）指纹分组。重复组模式按每列的 `NULL`、`EMPTY_STRING`、`NUMERIC_ZERO`、`OTHER_NONEMPTY` 分类；空字符串只匹配长度为零的字符串，数值零只匹配解析为数值类型且值为零的单元格。指纹只留在进程内。",
        "- “非重复行”指其完整行只出现一次；第 3 项移除完全重复组的全部行后检查其余（单例）行的 gid。NULL 单独计数，重复组只统计非 NULL gid。",
        "- 业务空点定义由 owner 判断，本报告不代为指定。为提供顺序量化，`non-empty point proxy` 暂定义为至少一个非 gid 列为 `OTHER_NONEMPTY` 的行；`blank point proxy` 是其补集。逐状态模式同时给出相对 proxy 行的首部、交错、尾部计数，owner 可按认定的模式汇总。",
        "- 顺序使用 proxy 行的 gid typed numeric 值；`gid_non_decreasing` 为非递减判断，另列下降相邻对和相等相邻对。存在 NULL 或非数值 gid 时标为不可判定，并报告数量。",
        "- v1→v2 差值为 v2 减 v1；缺表按零行、零组计，并另列是否出现/消失及 schema 是否变化。状态模式差值按完整列状态向量对应。",
        "",
        "## 状态标签",
        "",
        "| 标签 | 含义 |",
        "| --- | --- |",
        "| `NULL` | SQL NULL |",
        "| `EMPTY_STRING` | 空字符串 |",
        "| `NUMERIC_ZERO` | typed numeric value 等于 0（含 bit 数值 0） |",
        "| `OTHER_NONEMPTY` | 其余解析值；不输出值本身 |",
        "",
        "## 逐表统计",
        "",
    ]
    for table in report["tables"]:
        table_name = table["table_name"]
        lines.extend([f"### `{table_name}`", ""])
        lines.extend(
            [
                "| 数据集 | 列名 | 行数 | 重复组 | 重复多余行 | 重复组内行 | 非重复行 | 去重后 gid NULL | 去重后 gid 重复组 | 去重后非 NULL gid 唯一 | 非空点 proxy 行 | proxy gid NULL/非数值 | proxy gid 重复组 | proxy gid 非递减 | 下降点 | 相等点 | blank proxy 首部/交错/尾部/无参照 |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | --- | ---: | ---: | --- |",
            ]
        )
        for dataset in table["datasets"]:
            dup = dataset["exact_duplicates"]
            after_dup = dataset["after_duplicate_groups_removed"]
            order = dataset["source_order"]
            point = order["non_empty_point_proxy"]
            blank = order["blank_point_proxy_distribution"]
            lines.append(
                "| {dataset} | {columns} | {rows} | {groups} | {extra} | {group_rows} | {singletons} | "
                "{nulls} | {gid_groups} | {unique} | {point_rows} | {point_null}/{point_non_numeric} | "
                "{point_dups} | {monotonic} | {descents} | {equals} | {leading}/{interleaved}/{trailing}/{no_ref} |".format(
                    dataset=dataset["dataset_id"],
                    columns=", ".join(dataset["columns"]) or "—",
                    rows=dataset["row_count"],
                    groups=dup["group_count"],
                    extra=dup["extra_rows"],
                    group_rows=dup["rows_in_groups"],
                    singletons=dataset["non_duplicate_rows"]["row_count"],
                    nulls=after_dup["gid_null_rows"],
                    gid_groups=after_dup["gid_non_null_duplicate_group_count"],
                    unique=_bool_label(after_dup["gid_non_null_unique"]),
                    point_rows=point["row_count"],
                    point_null=point["gid_null_rows"],
                    point_non_numeric=point["gid_non_numeric_rows"],
                    point_dups=point["gid_non_null_duplicate_group_count"],
                    monotonic=_bool_label(point["gid_non_decreasing"]),
                    descents=point["gid_descending_adjacent_pair_count"],
                    equals=point["gid_equal_adjacent_pair_count"],
                    leading=blank["leading_before_first_point_proxy_rows"],
                    interleaved=blank["interleaved_between_point_proxy_rows"],
                    trailing=blank["trailing_after_last_point_proxy_rows"],
                    no_ref=blank["no_point_proxy_reference_rows"],
                )
            )
        lines.extend(["", "**按列状态模式的重复组、单例与源顺序分布**：", ""])
        lines.extend(
            [
                "| 数据集 | 完整列状态模式 | 重复组数 | 重复组行数 | 重复多余行 | 非重复行数 | proxy 点行 | proxy 首部 | proxy 交错 | proxy 尾部 | 无 proxy 参照 |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for dataset in table["datasets"]:
            columns = dataset["columns"]
            pattern_counts = _pattern_counts(dataset)
            for states in sorted(pattern_counts):
                counts = pattern_counts[states]
                lines.append(
                    "| {dataset} | {pattern} | {groups} | {dup_rows} | {extra} | {singletons} | "
                    "{point} | {leading} | {interleaved} | {trailing} | {no_ref} |".format(
                        dataset=dataset["dataset_id"],
                        pattern=_pattern_text(columns, states),
                        groups=counts.get("duplicate_group_count", 0),
                        dup_rows=counts.get("duplicate_row_count", 0),
                        extra=counts.get("duplicate_extra_rows", 0),
                        singletons=counts.get("singleton_row_count", 0),
                        point=counts.get("point_proxy_row_count", 0),
                        leading=counts.get("leading_blank_proxy_rows", 0),
                        interleaved=counts.get("interleaved_blank_proxy_rows", 0),
                        trailing=counts.get("trailing_blank_proxy_rows", 0),
                        no_ref=counts.get("no_point_proxy_reference_rows", 0),
                    )
                )
        lines.extend(["", "**v1→v2 计数变化**：", ""])
        lines.extend(
            [
                "| 数据对 | present/schema 变化 | 行数 | 重复组 | 重复多余行 | 重复组行 | 非重复行 | 去重后 gid NULL/重复组/重复多余行 | proxy 行 | proxy gid NULL/重复组/重复多余行/非数值 | 下降点 | 相等点 | blank 首部 | blank 交错 | blank 尾部/无参照 | proxy gid 非递减 v1→v2 |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | --- | --- |",
            ]
        )
        for change in table["version_changes"]:
            deltas = change["deltas"]
            lines.append(
                "| {pair} | {presence}/{schema} | {rows:+d} | {groups:+d} | {extra:+d} | {group_rows:+d} | "
                "{singletons:+d} | {nulls:+d}/{gid_groups:+d}/{gid_extra:+d} | {point:+d} | "
                "{point_null:+d}/{point_dups:+d}/{point_extra:+d}/{point_non_numeric:+d} | "
                "{descents:+d} | {equals:+d} | {leading:+d} | {interleaved:+d} | "
                "{trailing:+d}/{no_reference:+d} | {monotonic} |".format(
                    pair=f"{change['v1_dataset_id']}→{change['v2_dataset_id']}",
                    presence="yes" if change["presence_changed"] else "no",
                    schema="yes" if change["columns_changed"] else "no",
                    rows=deltas["row_count"],
                    groups=deltas["duplicate_group_count"],
                    extra=deltas["duplicate_extra_rows"],
                    group_rows=deltas["duplicate_group_rows"],
                    singletons=deltas["non_duplicate_rows"],
                    nulls=deltas["remaining_gid_null_rows"],
                    gid_groups=deltas["remaining_gid_duplicate_groups"],
                    gid_extra=deltas["remaining_gid_duplicate_extra_rows"],
                    point=deltas["non_empty_point_proxy_rows"],
                    point_null=deltas["non_empty_point_gid_null_rows"],
                    point_dups=deltas["non_empty_point_gid_duplicate_groups"],
                    point_extra=deltas["non_empty_point_gid_duplicate_extra_rows"],
                    point_non_numeric=deltas["non_empty_point_gid_non_numeric_rows"],
                    descents=deltas["gid_descending_adjacent_pairs"],
                    equals=deltas["gid_equal_adjacent_pairs"],
                    leading=deltas["blank_proxy_leading_rows"],
                    interleaved=deltas["blank_proxy_interleaved_rows"],
                    trailing=deltas["blank_proxy_trailing_rows"],
                    monotonic=(
                        f"{_bool_label(change['non_empty_point_gid_non_decreasing_v1'])}→"
                        f"{_bool_label(change['non_empty_point_gid_non_decreasing_v2'])} "
                        f"(可判定 {_bool_label(change['non_empty_point_gid_order_evaluable_v1'])}→"
                        f"{_bool_label(change['non_empty_point_gid_order_evaluable_v2'])})"
                    ),
                )
            )
        lines.extend(["", "**v1→v2 状态模式差值**：", ""])
        lines.extend(
            [
                "| 数据对 | 完整列状态模式 | 重复组数 | 重复组行数 | 重复多余行 | 非重复行数 | proxy 点行 | proxy 首部 | proxy 交错 | proxy 尾部 | 无 proxy 参照 |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for change in table["version_changes"]:
            for pattern in change["pattern_deltas"]:
                lines.append(
                    "| {pair} | {pattern} | {groups:+d} | {dup_rows:+d} | {extra:+d} | {singletons:+d} | "
                    "{point:+d} | {leading:+d} | {interleaved:+d} | {trailing:+d} | {no_ref:+d} |".format(
                        pair=f"{change['v1_dataset_id']}→{change['v2_dataset_id']}",
                        pattern=_pattern_text(pattern["columns"], pattern["states"])
                        if pattern["columns"]
                        else "—",
                        groups=pattern["duplicate_group_count_delta"],
                        dup_rows=pattern["duplicate_row_count_delta"],
                        extra=pattern["duplicate_extra_rows_delta"],
                        singletons=pattern["singleton_row_count_delta"],
                        point=pattern["point_proxy_row_count_delta"],
                        leading=pattern["leading_blank_proxy_rows_delta"],
                        interleaved=pattern["interleaved_blank_proxy_rows_delta"],
                        trailing=pattern["trailing_blank_proxy_rows_delta"],
                        no_ref=pattern["no_point_proxy_reference_rows_delta"],
                    )
                )
        lines.append("")

    lines.extend(_render_conclusions(report))
    return "\n".join(lines)


def _render_conclusions(report: dict[str, Any]) -> list[str]:
    observations = [
        (table["table_name"], dataset)
        for table in report["tables"]
        for dataset in table["datasets"]
        if dataset["present"]
    ]
    repeated = [
        (table_name, dataset)
        for table_name, dataset in observations
        if dataset["exact_duplicates"]["group_count"] > 0
    ]
    mixed_duplicate_modes = [
        (table_name, dataset)
        for table_name, dataset in repeated
        if len(dataset["exact_duplicates"]["by_state_pattern"]) > 1
    ]
    proxy_rows = [
        (table_name, dataset, dataset["source_order"]["non_empty_point_proxy"])
        for table_name, dataset in observations
        if dataset["source_order"]["non_empty_point_proxy"]["row_count"] > 0
    ]
    proxy_gid_exceptions = [
        (table_name, dataset, point)
        for table_name, dataset, point in proxy_rows
        if point["gid_null_rows"] > 0 or point["gid_non_null_duplicate_group_count"] > 0
    ]
    evaluated_order = [
        (table_name, dataset, point)
        for table_name, dataset, point in proxy_rows
        if point["gid_numeric_order_evaluable"]
    ]
    descending_order = [
        (table_name, dataset, point)
        for table_name, dataset, point in evaluated_order
        if point["gid_descending_adjacent_pair_count"] > 0
    ]
    unevaluable_order = [
        (table_name, dataset, point)
        for table_name, dataset, point in proxy_rows
        if not point["gid_numeric_order_evaluable"]
    ]
    interleaved_proxy = [
        (table_name, dataset, dataset["source_order"]["blank_point_proxy_distribution"])
        for table_name, dataset in observations
        if dataset["source_order"]["blank_point_proxy_distribution"][
            "interleaved_between_point_proxy_rows"
        ]
        > 0
    ]

    def labels(items: Sequence[tuple[str, dict[str, Any], dict[str, Any]]]) -> str:
        return "、".join(f"{name}/{item['dataset_id']}" for name, item, _ in items) or "无"

    mixed_labels = "、".join(
        f"{name}/{item['dataset_id']}"
        for name, item in mixed_duplicate_modes
    ) or "无"
    proxy_exception_labels = labels(proxy_gid_exceptions)
    descending_labels = labels(descending_order)
    unevaluable_labels = labels(unevaluable_order)
    interleaved_labels = "、".join(
        f"{name}/{item['dataset_id']}"
        for name, item, _distribution in interleaved_proxy
    ) or "无"

    return [
        "## 对 DC56 第 4 项的结论",
        "",
        f"- 重复行状态模式：有重复组的表/数据组合 {len(repeated)} 组；其中跨多个状态模式的组合 {len(mixed_duplicate_modes)} 组（{mixed_labels}）。其余有重复组的组合各自只有一种模式；具体模式与组数/行数见明细。该结果只比较列状态，不断定模式的业务含义。",
        f"- 非空点 gid 唯一性：按上述非 gid 列 proxy，有行的组合 {len(proxy_rows)} 组；gid NULL 或非 NULL 重复组的例外为 {proxy_exception_labels}。具体 NULL、重复组数及多余行数见明细。",
        f"- 源顺序与 gid：按 proxy 有行且 gid 可数值比较的组合 {len(evaluated_order)} 组；其中有下降点的组合 {len(descending_order)} 组（{descending_labels}）。gid 不可判定的组合 {len(unevaluable_order)} 组（{unevaluable_labels}）；相等相邻点另计于明细。",
        f"- 空点位置 proxy：存在 proxy 行交错分布的表/数据组合 {len(interleaved_proxy)} 组（{interleaved_labels}）；各组合的首部、交错、尾部行数以及逐模式位置计数见明细。空点模式须由 owner 确认后再解释该分布。",
        "- 本调查不定义空点行的业务语义，也不提出规则改动；如重复行并非同一业务空点模式，或顺序有业务含义且不能由 gid 恢复，按 DC56 另行立项条件处理。",
        "",
    ]


def _bool_label(value: bool | None) -> str:
    if value is None:
        return "不可判定"
    return "是" if value else "否"


def _write_private(path: Path, content: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    os.chmod(path, 0o600)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count forwardtable parsed row-state patterns without exporting cell values."
    )
    parser.add_argument("--packages-dir", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        specs = _expected_specs(args.packages_dir)
        report = _build_report(specs)
        _write_private(args.json_output, json.dumps(report, indent=2, sort_keys=True) + "\n")
        _write_private(args.markdown_output, _render_markdown(report))
    except CensusRefusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from None
    print(
        json.dumps(
            {
                "status": "COMPLETE",
                "dataset_count": len(specs),
                "table_count": len(_TARGET_TABLES),
                "dataset_table_count": len(_TARGET_TABLES) * len(specs),
                "json_output_mode": "0600",
                "markdown_output_mode": "0600",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
