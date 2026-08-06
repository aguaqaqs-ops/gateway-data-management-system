"""Candidate A SQL, catalog, and stream helpers shared by probe and production paths."""

from __future__ import annotations

import re
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_service.arrow_mapping import (
    ColumnCatalog,
    TableCatalog,
    UnknownTypePolicy,
    arrow_type,
    normalize_sql_type,
)
from gateway_repository_service.candidate_a.ref_validation import commit_literal

# Re-export for probe providers that import _commit_literal from providers.
_commit_literal = commit_literal


class ProviderError(RuntimeError):
    """Candidate A SQL/catalog execution failure shared with probe providers."""


def quote_identifier(identifier: str) -> str:
    if not identifier or "\x00" in identifier or "/" in identifier or "\\" in identifier:
        raise ValueError("invalid SQL identifier")
    return "`" + identifier.replace("`", "``") + "`"


def _split_sql_items(body: str) -> list[str]:
    items: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    for index, character in enumerate(body):
        if escaped:
            escaped = False
            continue
        if quote is not None:
            if character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"', "`"}:
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "," and depth == 0:
            items.append(body[start:index].strip())
            start = index + 1
    trailing = body[start:].strip()
    if trailing:
        items.append(trailing)
    return items


def _unquote_identifier(value: str) -> str:
    value = value.strip()
    if value.startswith("`") and value.endswith("`"):
        return value[1:-1].replace("``", "`")
    return value.strip("\"")


def _first_identifier(value: str) -> tuple[str, str]:
    value = value.lstrip()
    if value.startswith("`"):
        end = value.find("`", 1)
        while end >= 0 and end + 1 < len(value) and value[end + 1] == "`":
            end = value.find("`", end + 2)
        if end < 0:
            raise ProviderError("invalid pinned DDL identifier")
        return _unquote_identifier(value[: end + 1]), value[end + 1 :].lstrip()
    match = re.match(r"([A-Za-z_][A-Za-z0-9_$]*)\s+(.*)$", value, re.S)
    if match is None:
        raise ProviderError("invalid pinned DDL column definition")
    return match.group(1), match.group(2).lstrip()


def _column_type_and_tail(rest: str) -> tuple[str, str]:
    keywords = (
        " NOT ",
        " NULL",
        " DEFAULT",
        " PRIMARY",
        " UNIQUE",
        " COMMENT",
        " COLLATE",
        " CHARACTER",
        " AUTO_INCREMENT",
        " CHECK",
        " REFERENCES",
    )
    depth = 0
    quote: str | None = None
    escaped = False
    upper = rest.upper()
    for index, character in enumerate(rest):
        if escaped:
            escaped = False
            continue
        if quote is not None:
            if character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"', "`"}:
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character.isspace() and depth == 0:
            tail = upper[index:]
            if any(tail.startswith(keyword) for keyword in keywords):
                return rest[:index].strip(), rest[index:].strip()
    return rest.strip(), ""


def _parse_create_statement(ddl: str, row_count: int) -> TableCatalog:
    match = re.search(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?", ddl, re.I)
    if match is None:
        raise ProviderError("pinned schema diff did not contain CREATE TABLE")
    name, remainder = _first_identifier(ddl[match.end() :])
    opening = remainder.find("(")
    closing = remainder.rfind(")")
    if opening < 0 or closing <= opening:
        raise ProviderError("pinned CREATE TABLE body was malformed")
    body = remainder[opening + 1 : closing]
    definitions = _split_sql_items(body)
    columns: list[ColumnCatalog] = []
    primary_key: list[str] = []
    for definition in definitions:
        upper = definition.strip().upper()
        if upper.startswith("PRIMARY KEY"):
            key_body = definition[definition.find("(") + 1 : definition.rfind(")")]
            primary_key = [_unquote_identifier(item.split()[0]) for item in _split_sql_items(key_body)]
            continue
        if upper.startswith(("UNIQUE ", "KEY ", "INDEX ", "CONSTRAINT ", "CHECK ")):
            continue
        column_name, rest = _first_identifier(definition)
        sql_type, tail = _column_type_and_tail(rest)
        nullable = not bool(re.search(r"\bNOT\s+NULL\b", tail, re.I))
        if re.search(r"\bPRIMARY\s+KEY\b", tail, re.I):
            primary_key.append(column_name)
        columns.append(ColumnCatalog(column_name, normalize_sql_type(sql_type, sql_type), nullable, None))
    positions = {name: index for index, name in enumerate(primary_key, 1)}
    columns = [
        ColumnCatalog(column.name, column.sql_type, column.nullable, positions.get(column.name))
        for column in columns
    ]
    return TableCatalog(name, tuple(columns), row_count)


def _catalog_from_schema_diff(
    rows: list[dict[str, Any]], counts: dict[str, int]
) -> tuple[TableCatalog, ...]:
    tables: dict[str, TableCatalog] = {}
    for row in rows:
        ddl = row.get("to_create_statement")
        if ddl in (None, ""):
            continue
        table = _parse_create_statement(str(ddl), 0)
        tables[table.name] = TableCatalog(table.name, table.columns, counts.get(table.name, 0))
    if not tables and any(row.get("to_create_statement") not in (None, "") for row in rows):
        raise ProviderError("pinned schema diff did not produce a target catalog")
    return tuple(tables[name] for name in sorted(tables))


def _tagged_select_list(table: TableCatalog) -> tuple[str, list[str]]:
    expressions: list[str] = []
    header: list[str] = []
    for index, column in enumerate(table.columns):
        source = quote_identifier(column.name)
        null_name = f"__gateway_null_{index}"
        value_name = f"__gateway_value_{index}"
        value_expression = (
            f"HEX({source})"
            if pa.types.is_binary(arrow_type(column.sql_type, UnknownTypePolicy.STRINGIFY)[0])
            else source
        )
        expressions.extend(
            [
                f"CASE WHEN {source} IS NULL THEN 1 ELSE 0 END AS {quote_identifier(null_name)}",
                f"{value_expression} AS {quote_identifier(value_name)}",
            ]
        )
        header.extend([null_name, value_name])
    return ", ".join(expressions), header


def _parse_tagged_row(row: list[str], table: TableCatalog) -> tuple[Any, ...]:
    if len(row) != len(table.columns) * 2:
        raise ProviderError("tagged CSV column count mismatch")
    values: list[Any] = []
    for index, column in enumerate(table.columns):
        null_bit, value = row[index * 2 : index * 2 + 2]
        if null_bit not in {"0", "1"}:
            raise ProviderError("tagged CSV null bit was invalid")
        if null_bit == "1":
            values.append(None)
        elif pa.types.is_binary(arrow_type(column.sql_type, UnknownTypePolicy.STRINGIFY)[0]):
            try:
                _, metadata = arrow_type(column.sql_type, UnknownTypePolicy.STRINGIFY)
                if b"gateway.bit_width" in metadata:
                    width = int(metadata[b"gateway.bit_width"])
                    value = value.zfill(max(2, (width + 3) // 4))
                if value.startswith(("0x", "0X")):
                    value = value[2:]
                values.append(bytes.fromhex(value))
            except ValueError as exc:
                raise ProviderError("tagged CSV binary value was not HEX") from exc
        else:
            values.append(value)
    return tuple(values)


def _rows_bytes(rows: list[tuple[Any, ...]]) -> int:
    return sum(
        sum(
            0
            if value is None
            else len(value.encode("utf-8"))
            if isinstance(value, str)
            else len(value)
            if isinstance(value, bytes)
            else len(str(value).encode("utf-8"))
            for value in row
        )
        for row in rows
    )


def _row_bytes(row: tuple[Any, ...]) -> int:
    return _rows_bytes([row])


def _metric_int(metrics: dict[str, object], key: str) -> int:
    value = metrics.get(key)
    return int(value) if isinstance(value, (int, float, str)) else 0


def _observe_batch_metrics(
    metrics: dict[str, object],
    rows: list[tuple[Any, ...]],
    *,
    row_bound: int,
    byte_bound: int,
) -> int:
    payload_bytes = _rows_bytes(rows)
    row_count = len(rows)
    row_sizes = [_row_bytes(row) for row in rows]
    row_bytes = max(row_sizes, default=0)
    metrics["total_rows"] = _metric_int(metrics, "total_rows") + row_count
    metrics["total_stream_payload_bytes"] = (
        _metric_int(metrics, "total_stream_payload_bytes") + payload_bytes
    )
    metrics["max_row_bytes"] = max(_metric_int(metrics, "max_row_bytes"), row_bytes)
    metrics["batch_count"] = _metric_int(metrics, "batch_count") + 1
    metrics["max_batch_rows"] = max(_metric_int(metrics, "max_batch_rows"), row_count)
    metrics["max_batch_bytes"] = max(_metric_int(metrics, "max_batch_bytes"), payload_bytes)
    oversized_rows = [size for size in row_sizes if size > byte_bound]
    if oversized_rows:
        metrics["oversized_row_count"] = _metric_int(
            metrics, "oversized_row_count"
        ) + len(oversized_rows)
        metrics["max_oversized_row_bytes"] = max(
            _metric_int(metrics, "max_oversized_row_bytes"), max(oversized_rows)
        )
    oversized_single_row = row_count == 1 and bool(oversized_rows)
    metrics["oversized_single_row"] = bool(metrics["oversized_single_row"]) or oversized_single_row
    if oversized_single_row:
        metrics["oversized_batch_count"] = _metric_int(
            metrics, "oversized_batch_count"
        ) + 1
    valid = 1 <= row_count <= row_bound and (
        payload_bytes <= byte_bound or oversized_single_row
    )
    if not valid:
        metrics["batch_contract_valid"] = False
        metrics["batch_contract_violation_count"] = (
            _metric_int(metrics, "batch_contract_violation_count") + 1
        )
    return payload_bytes
