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
from gateway_repository_service.candidate_a.errors import CandidateAError
from gateway_repository_service.candidate_a.ref_validation import commit_literal

# Re-export for probe providers that import _commit_literal from providers.
_commit_literal = commit_literal


class ProviderError(CandidateAError):
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


_PK_INDEX_PREFIX = re.compile(r"^\(\d+\)$")
_MAX_DDL_IDENTIFIER_CODE_POINTS = 64
_TABLE_CONSTRAINT_PREFIXES = (
    "UNIQUE ",
    "KEY ",
    "INDEX ",
    "CONSTRAINT ",
    "CHECK ",
    "FULLTEXT ",
    "SPATIAL ",
    "FOREIGN ",
)
_ALLOWED_TABLE_OPTION_PATTERN = re.compile(
    r"^\s*(?:"
    r"ENGINE\s*=\s*\S+"
    r"|DEFAULT\s+CHARSET\s*=\s*\S+"
    r"|CHARSET\s*=\s*\S+"
    r"|COLLATE\s*=\s*\S+"
    r"|AUTO_INCREMENT\s*=\s*\d+"
    r"|COMMENT\s*=(?:'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|`(?:[^`]|``)*`)"
    r")",
    re.I | re.S,
)


def _find_matching_paren(value: str, open_index: int) -> int:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(open_index, len(value)):
        character = value[index]
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
            if depth == 0:
                return index
    raise ProviderError("pinned CREATE TABLE body was malformed")


def _split_create_table_body(remainder: str) -> tuple[str, str]:
    opening = remainder.find("(")
    if opening < 0:
        raise ProviderError("pinned CREATE TABLE body was malformed")
    closing = _find_matching_paren(remainder, opening)
    body = remainder[opening + 1 : closing]
    if body.rstrip().endswith(","):
        raise ProviderError("pinned CREATE TABLE body was malformed")
    tail = remainder[closing + 1 :].strip()
    if tail.endswith(";"):
        tail = tail[:-1].strip()
    return body, tail


def _validate_table_options_tail(tail: str) -> None:
    remainder = tail.strip()
    while remainder:
        match = _ALLOWED_TABLE_OPTION_PATTERN.match(remainder)
        if match is None:
            raise ProviderError("pinned CREATE TABLE has unsupported table options")
        remainder = remainder[match.end():].strip()


def _validate_ddl_column_identifier(name: str) -> str:
    if not name:
        raise ProviderError("invalid pinned DDL identifier")
    code_points = 0
    for char in name:
        code_points += 1
        if code_points > _MAX_DDL_IDENTIFIER_CODE_POINTS:
            raise ProviderError("invalid pinned DDL identifier")
        ordinal = ord(char)
        if char == "\x00" or ordinal < 32 or ordinal == 127 or char in {"/", "\\"}:
            raise ProviderError("invalid pinned DDL identifier")
    return name


def _validate_ddl_table_identifier(name: str) -> str:
    return _validate_ddl_column_identifier(name)


def _parse_primary_key_column_ref(item: str) -> str:
    item = item.strip()
    if not item:
        raise ProviderError("invalid pinned DDL primary key column reference")
    column_name, suffix = _first_identifier(item)
    suffix = suffix.strip()
    if suffix and _PK_INDEX_PREFIX.fullmatch(suffix) is None:
        raise ProviderError("invalid pinned DDL primary key column reference")
    return _validate_ddl_column_identifier(column_name)


def _consume_index_like_constraint(rest: str) -> None:
    rest = rest.strip()
    if not rest.startswith("("):
        name_match = re.match(r"`(?:[^`]|``)*`|``(?:[^`]|``)*``|[A-Za-z_][A-Za-z0-9_$]*", rest)
        if name_match is None:
            raise ProviderError("pinned CREATE TABLE constraint was malformed")
        rest = rest[name_match.end():].strip()
        if not rest.startswith("("):
            raise ProviderError("pinned CREATE TABLE constraint was malformed")
    closing = _find_matching_paren(rest, 0)
    remainder = rest[closing + 1 :].strip()
    if remainder:
        raise ProviderError("pinned CREATE TABLE constraint was malformed")


def _consume_foreign_key_constraint(rest: str) -> None:
    rest = rest.strip()
    if not rest.startswith("("):
        raise ProviderError("pinned CREATE TABLE constraint was malformed")
    closing = _find_matching_paren(rest, 0)
    rest = rest[closing + 1 :].strip()
    references_match = re.match(r"REFERENCES\s+", rest, re.I)
    if references_match is None:
        raise ProviderError("pinned CREATE TABLE constraint was malformed")
    rest = rest[references_match.end():].strip()
    _, rest = _first_identifier(rest)
    rest = rest.strip()
    if rest.startswith("("):
        closing = _find_matching_paren(rest, 0)
        rest = rest[closing + 1 :].strip()
    while rest:
        on_match = re.match(
            r"ON\s+(DELETE|UPDATE)\s+(RESTRICT|CASCADE|SET\s+NULL|NO\s+ACTION)\s*",
            rest,
            re.I,
        )
        if on_match is None:
            raise ProviderError("pinned CREATE TABLE constraint was malformed")
        rest = rest[on_match.end():].strip()


def _consume_table_constraint(definition: str) -> None:
    stripped = definition.strip()
    if not stripped:
        raise ProviderError("pinned CREATE TABLE constraint was malformed")

    check_match = re.match(r"CHECK\s+", stripped, re.I)
    if check_match is not None:
        rest = stripped[check_match.end():].strip()
        if not rest.startswith("("):
            raise ProviderError("pinned CREATE TABLE constraint was malformed")
        closing = _find_matching_paren(rest, 0)
        if rest[closing + 1 :].strip():
            raise ProviderError("pinned CREATE TABLE constraint was malformed")
        return

    foreign_match = re.match(r"FOREIGN\s+KEY\s+", stripped, re.I)
    if foreign_match is not None:
        _consume_foreign_key_constraint(stripped[foreign_match.end():])
        return

    constraint_match = re.match(r"CONSTRAINT\s+", stripped, re.I)
    if constraint_match is not None:
        rest = stripped[constraint_match.end():].strip()
        _, rest = _first_identifier(rest)
        _consume_table_constraint(rest)
        return

    index_match = re.match(
        r"(?:FULLTEXT\s+(?:KEY\s+)?|SPATIAL\s+(?:KEY\s+)?|UNIQUE\s+(?:KEY\s+)?|(?:KEY|INDEX)\s+)",
        stripped,
        re.I,
    )
    if index_match is not None:
        _consume_index_like_constraint(stripped[index_match.end():])
        return

    raise ProviderError("pinned CREATE TABLE constraint was malformed")


def _consume_column_modifiers(tail: str) -> bool:
    remainder = tail.strip()
    inline_pk = False
    while remainder:
        if re.match(r"PRIMARY\s+KEY\b", remainder, re.I):
            inline_pk = True
            remainder = re.sub(r"PRIMARY\s+KEY\b", "", remainder, count=1, flags=re.I).strip()
            continue
        if re.match(r"NOT\s+NULL\b", remainder, re.I):
            remainder = re.sub(r"NOT\s+NULL\b", "", remainder, count=1, flags=re.I).strip()
            continue
        if re.match(r"NULL\b", remainder, re.I):
            remainder = re.sub(r"NULL\b", "", remainder, count=1, flags=re.I).strip()
            continue
        default_match = re.match(
            r"DEFAULT\s+(?:'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|`(?:[^`]|``)*`|\S+)",
            remainder,
            re.I,
        )
        if default_match is not None:
            remainder = remainder[default_match.end():].strip()
            continue
        comment_match = re.match(
            r"COMMENT\s+(?:'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|`(?:[^`]|``)*`)",
            remainder,
            re.I,
        )
        if comment_match is not None:
            remainder = remainder[comment_match.end():].strip()
            continue
        collate_match = re.match(r"COLLATE\s+\S+", remainder, re.I)
        if collate_match is not None:
            remainder = remainder[collate_match.end():].strip()
            continue
        if re.match(r"AUTO_INCREMENT\b", remainder, re.I):
            remainder = re.sub(r"AUTO_INCREMENT\b", "", remainder, count=1, flags=re.I).strip()
            continue
        if re.match(r"UNIQUE\b", remainder, re.I):
            remainder = re.sub(r"UNIQUE\b", "", remainder, count=1, flags=re.I).strip()
            continue
        generated_head = re.match(r"GENERATED\s+ALWAYS\s+AS\s*", remainder, re.I)
        if generated_head is not None:
            remainder = remainder[generated_head.end():].strip()
            if not remainder.startswith("("):
                raise ProviderError("invalid pinned DDL column definition")
            closing = _find_matching_paren(remainder, 0)
            remainder = remainder[closing + 1 :].strip()
            stored_match = re.match(r"(?:STORED|VIRTUAL)\b", remainder, re.I)
            if stored_match is not None:
                remainder = remainder[stored_match.end():].strip()
            continue
        raise ProviderError("invalid pinned DDL column definition")
    return inline_pk


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
        " GENERATED",
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
    match = re.match(r"\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?", ddl, re.I)
    if match is None:
        raise ProviderError("pinned schema diff did not contain CREATE TABLE")
    name, remainder = _first_identifier(ddl[match.end() :])
    name = _validate_ddl_table_identifier(name)
    if not remainder.lstrip().startswith("("):
        raise ProviderError("pinned CREATE TABLE body was malformed")
    opening = remainder.find("(")
    gap = remainder[:opening]
    if gap.strip():
        raise ProviderError("pinned CREATE TABLE body was malformed")
    body, options_tail = _split_create_table_body(remainder)
    _validate_table_options_tail(options_tail)
    definitions = _split_sql_items(body)
    columns: list[ColumnCatalog] = []
    primary_key: list[str] = []
    pk_defined = False
    for definition in definitions:
        if not definition.strip():
            raise ProviderError("pinned CREATE TABLE has empty column definition")
        stripped_definition = definition.strip()
        upper = stripped_definition.upper()
        if upper.startswith("PRIMARY KEY"):
            pk_match = re.fullmatch(
                r"PRIMARY\s+KEY\s*\((.*)\)\s*",
                stripped_definition,
                flags=re.I | re.S,
            )
            if pk_match is None:
                raise ProviderError("invalid pinned DDL primary key constraint")
            if pk_defined:
                raise ProviderError("pinned CREATE TABLE has multiple primary key definitions")
            key_body = pk_match.group(1)
            if not key_body.strip():
                raise ProviderError("pinned CREATE TABLE primary key is empty")
            primary_key = [
                _parse_primary_key_column_ref(item) for item in _split_sql_items(key_body)
            ]
            pk_defined = True
            continue
        if any(upper.startswith(prefix) for prefix in _TABLE_CONSTRAINT_PREFIXES):
            _consume_table_constraint(stripped_definition)
            continue
        column_name, rest = _first_identifier(definition)
        column_name = _validate_ddl_column_identifier(column_name)
        sql_type, tail = _column_type_and_tail(rest)
        inline_pk = _consume_column_modifiers(tail)
        nullable = not bool(re.search(r"\bNOT\s+NULL\b", tail, re.I))
        if inline_pk:
            if pk_defined:
                raise ProviderError("pinned CREATE TABLE has multiple primary key definitions")
            primary_key.append(column_name)
            pk_defined = True
        columns.append(ColumnCatalog(column_name, normalize_sql_type(sql_type, sql_type), nullable, None))
    if not columns:
        raise ProviderError("pinned CREATE TABLE has no columns")
    column_names = [column.name for column in columns]
    if len(column_names) != len(set(column_names)):
        raise ProviderError("pinned CREATE TABLE has duplicate column names")
    if len(primary_key) != len(set(primary_key)):
        raise ProviderError("pinned CREATE TABLE primary key has duplicate column names")
    declared_columns = set(column_names)
    for pk_name in primary_key:
        if pk_name not in declared_columns:
            raise ProviderError("pinned CREATE TABLE primary key references unknown column")
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
