"""Candidate A SQL, catalog, and stream helpers shared by probe and production paths."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from gateway_repository_service.arrow_mapping import (
    ColumnCatalog,
    CompiledTablePlan,
    NormalizedRow,
    SPATIAL_SQL_TYPES,
    TableCatalog,
    TemporalSqlTypeKind,
    UnknownTypePolicy,
    compile_table_plan,
    classify_temporal_sql_type,
    normalize_sql_type,
)
from gateway_repository_service.candidate_a.errors import CandidateAError
from gateway_repository_service.candidate_a.ref_validation import commit_literal

# Re-export for probe providers that import _commit_literal from providers.
_commit_literal = commit_literal


class ProviderError(CandidateAError):
    """Candidate A SQL/catalog execution failure shared with probe providers."""


@dataclass(frozen=True)
class _TableConstraintRefs:
    index_column_lists: tuple[tuple[str, ...], ...] = ()
    foreign_keys: tuple[tuple[tuple[str, ...], str, tuple[str, ...]], ...] = ()


@dataclass(frozen=True)
class _TableNameIndex:
    lower_to_exact: dict[str, str]
    ambiguous_lower: frozenset[str]


@dataclass(frozen=True)
class ParenthesizedScanResult:
    significant_content: bool
    balanced: bool
    comment_closed: bool


@dataclass
class _ColumnModifierState:
    inline_pk: bool = False
    nullable: bool | None = None
    has_default: bool = False
    has_on_update: bool = False
    has_comment: bool = False
    has_collate: bool = False
    has_auto_increment: bool = False
    has_unique: bool = False
    has_generated: bool = False


_INTEGER_SQL_TYPES = frozenset({
    "TINYINT",
    "SMALLINT",
    "MEDIUMINT",
    "INT",
    "BIGINT",
})


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


def _parse_constraint_column_ref(item: str) -> str:
    item = item.strip()
    if not item:
        raise ProviderError("pinned CREATE TABLE constraint was malformed")
    column_name, suffix = _first_identifier(item)
    suffix = suffix.strip()
    if suffix and _PK_INDEX_PREFIX.fullmatch(suffix) is None:
        raise ProviderError("pinned CREATE TABLE constraint was malformed")
    return _validate_ddl_column_identifier(column_name)


def _parse_constraint_column_list(key_body: str) -> tuple[str, ...]:
    items = _split_sql_items(key_body)
    if not items or any(not item.strip() for item in items):
        raise ProviderError("pinned CREATE TABLE constraint was malformed")
    return tuple(_parse_constraint_column_ref(item) for item in items)


def _validate_ddl_identifier_token(token: str) -> str:
    token = token.strip()
    if token.startswith("`"):
        return _validate_ddl_column_identifier(_unquote_identifier(token))
    return _validate_ddl_column_identifier(token)


_QUOTED_SQL_LITERAL_PATTERN = re.compile(
    r"(?:'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|`(?:[^`]|``)*`)",
    re.S,
)
_CHECK_NOT_ENFORCED_VERSION_COMMENT = re.compile(r"/\*!\d+\s+NOT ENFORCED\s*\*/", re.I)
_SPATIAL_SRID_VERSION_COMMENT = re.compile(r"/\*!\d+\s+SRID\s+(\d+)\s*\*/", re.I)


def _extract_trailing_spatial_srid_version_comment(tail: str) -> tuple[str, int | None]:
    tail = tail.strip()
    match = _SPATIAL_SRID_VERSION_COMMENT.search(tail)
    if match is None or match.end() != len(tail):
        return tail, None
    return tail[: match.start()].strip(), int(match.group(1))


def _scan_parenthesized_sql_content(inner: str) -> ParenthesizedScanResult:
    state = "normal"
    depth = 0
    significant = False
    index = 0
    length = len(inner)
    while index < length:
        character = inner[index]
        if state == "normal":
            if character == "(":
                depth += 1
                index += 1
                continue
            if character == ")":
                depth -= 1
                if depth < 0:
                    return ParenthesizedScanResult(False, False, True)
                index += 1
                continue
            if character == "'":
                state = "single_quote"
                significant = True
                index += 1
                continue
            if character == '"':
                state = "double_quote"
                significant = True
                index += 1
                continue
            if character == "`":
                state = "backtick"
                significant = True
                index += 1
                continue
            if character == "/" and index + 1 < length and inner[index + 1] == "*":
                state = "block_comment"
                index += 2
                continue
            if character == "-" and index + 1 < length and inner[index + 1] == "-":
                state = "line_comment"
                index += 2
                continue
            if character == "#":
                state = "hash_comment"
                index += 1
                continue
            if not character.isspace():
                significant = True
            index += 1
            continue
        if state == "single_quote":
            if character == "\\" and index + 1 < length:
                index += 2
                continue
            if character == "'":
                state = "normal"
            index += 1
            continue
        if state == "double_quote":
            if character == "\\" and index + 1 < length:
                index += 2
                continue
            if character == '"':
                state = "normal"
            index += 1
            continue
        if state == "backtick":
            if character == "`":
                state = "normal"
            index += 1
            continue
        if state == "block_comment":
            if character == "*" and index + 1 < length and inner[index + 1] == "/":
                state = "normal"
                index += 2
                continue
            index += 1
            continue
        if state in {"line_comment", "hash_comment"}:
            if character == "\n":
                state = "normal"
            index += 1
            continue
        index += 1
    balanced = depth == 0 and state in {"normal", "line_comment", "hash_comment"}
    comment_closed = state in {"normal", "line_comment", "hash_comment"}
    return ParenthesizedScanResult(significant, balanced, comment_closed)


def _validate_parenthesized_sql_content(inner: str) -> None:
    scan = _scan_parenthesized_sql_content(inner)
    if not scan.balanced or not scan.comment_closed or not scan.significant_content:
        raise ProviderError("invalid pinned DDL column definition")


def _consume_sql_literal_or_expression(rest: str) -> str:
    rest = rest.lstrip()
    if not rest:
        raise ProviderError("invalid pinned DDL column definition")
    if rest.startswith("("):
        closing = _find_matching_paren(rest, 0)
        inner = rest[1:closing]
        _validate_parenthesized_sql_content(inner)
        return rest[closing + 1 :].lstrip()
    quoted_match = _QUOTED_SQL_LITERAL_PATTERN.match(rest)
    if quoted_match is not None:
        return rest[quoted_match.end() :].lstrip()
    depth = 0
    quote: str | None = None
    escaped = False
    consumed = 0
    for index, character in enumerate(rest):
        if escaped:
            escaped = False
            consumed = index + 1
            continue
        if quote is not None:
            if character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            consumed = index + 1
            continue
        if character in {"'", '"', "`"}:
            quote = character
            consumed = index + 1
            continue
        if character == "(":
            depth += 1
            consumed = index + 1
            continue
        if character == ")":
            depth -= 1
            consumed = index + 1
            continue
        if character.isspace() and depth == 0:
            break
        consumed = index + 1
    if consumed == 0:
        raise ProviderError("invalid pinned DDL column definition")
    return rest[consumed:].lstrip()


def _validate_constraint_column_list_members(
    column_names: tuple[str, ...],
    declared_columns: set[str],
) -> None:
    if len(column_names) != len(set(column_names)):
        raise ProviderError("pinned CREATE TABLE constraint was malformed")
    for column_name in column_names:
        if column_name not in declared_columns:
            raise ProviderError("pinned CREATE TABLE primary key references unknown column")


def _validate_constraint_declared_columns(
    table_name: str,
    declared_columns: set[str],
    constraints: _TableConstraintRefs,
    all_table_columns: dict[str, set[str]],
    table_name_index: _TableNameIndex,
) -> None:
    for index_columns in constraints.index_column_lists:
        _validate_constraint_column_list_members(index_columns, declared_columns)
    for local_columns, ref_table, ref_columns in constraints.foreign_keys:
        _validate_constraint_column_list_members(local_columns, declared_columns)
        if len(ref_columns) != len(set(ref_columns)):
            raise ProviderError("pinned CREATE TABLE constraint was malformed")
        if ref_table == table_name:
            _validate_constraint_column_list_members(ref_columns, declared_columns)
        else:
            parent_columns = _resolve_referenced_table_columns(
                ref_table,
                all_table_columns,
                table_name_index,
            )
            if parent_columns is not None:
                for ref_column in ref_columns:
                    if ref_column not in parent_columns:
                        raise ProviderError(
                            "pinned CREATE TABLE foreign key references unknown column"
                        )


def _resolve_referenced_table_columns(
    ref_table: str,
    all_table_columns: dict[str, set[str]],
    table_name_index: _TableNameIndex,
) -> set[str] | None:
    if ref_table in all_table_columns:
        return all_table_columns[ref_table]
    ref_lower = ref_table.lower()
    if ref_lower in table_name_index.ambiguous_lower:
        raise ProviderError("pinned schema diff has ambiguous foreign key referenced table")
    exact_name = table_name_index.lower_to_exact.get(ref_lower)
    if exact_name is None:
        return None
    return all_table_columns[exact_name]


def _build_table_name_index(
    parsed: list[tuple[TableCatalog, _TableConstraintRefs]],
) -> _TableNameIndex:
    lower_to_exact: dict[str, str] = {}
    ambiguous_lower: set[str] = set()
    for table, _ in parsed:
        lower_name = table.name.lower()
        existing = lower_to_exact.get(lower_name)
        if existing is not None and existing != table.name:
            ambiguous_lower.add(lower_name)
        else:
            lower_to_exact[lower_name] = table.name
    return _TableNameIndex(lower_to_exact=lower_to_exact, ambiguous_lower=frozenset(ambiguous_lower))


def _validate_schema_diff_table_names(
    parsed: list[tuple[TableCatalog, _TableConstraintRefs]],
) -> None:
    seen_exact: set[str] = set()
    seen_lower: dict[str, str] = {}
    for table, _ in parsed:
        if table.name in seen_exact:
            raise ProviderError("pinned schema diff has duplicate table names")
        seen_exact.add(table.name)
        lower_name = table.name.lower()
        if lower_name in seen_lower and seen_lower[lower_name] != table.name:
            raise ProviderError("pinned schema diff has duplicate table names")
        seen_lower[lower_name] = table.name


def _is_on_update_eligible_type(sql_type: str) -> bool:
    classification, _ = classify_temporal_sql_type(sql_type)
    return classification == TemporalSqlTypeKind.VALID


def _is_integer_sql_type(sql_type: str) -> bool:
    upper = " ".join(sql_type.upper().split())
    if upper.endswith(" UNSIGNED"):
        base = upper.removesuffix(" UNSIGNED")
        return base in _INTEGER_SQL_TYPES
    return upper in _INTEGER_SQL_TYPES


def _validate_column_modifier_state(sql_type: str, state: _ColumnModifierState) -> None:
    if state.has_generated:
        if (
            state.has_default
            or state.has_on_update
            or state.has_auto_increment
            or state.has_unique
            or state.inline_pk
        ):
            raise ProviderError("invalid pinned DDL column definition")
    if state.has_on_update and not _is_on_update_eligible_type(sql_type):
        raise ProviderError("invalid pinned DDL column definition")
    if state.has_auto_increment:
        if state.nullable is True:
            raise ProviderError("invalid pinned DDL column definition")
        if not _is_integer_sql_type(sql_type):
            raise ProviderError("invalid pinned DDL column definition")


def _consume_index_like_constraint(rest: str) -> tuple[str, ...]:
    rest = rest.strip()
    if not rest.startswith("("):
        name_match = re.match(r"`(?:[^`]|``)*`|``(?:[^`]|``)*``|[A-Za-z_][A-Za-z0-9_$]*", rest)
        if name_match is None:
            raise ProviderError("pinned CREATE TABLE constraint was malformed")
        _validate_ddl_identifier_token(rest[: name_match.end()])
        rest = rest[name_match.end():].strip()
        if not rest.startswith("("):
            raise ProviderError("pinned CREATE TABLE constraint was malformed")
    opening_paren = rest.find("(")
    closing = _find_matching_paren(rest, opening_paren)
    index_columns = _parse_constraint_column_list(rest[opening_paren + 1 : closing])
    remainder = rest[closing + 1 :].strip()
    comment_match = re.match(
        r"COMMENT\s+(?:'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|`(?:[^`]|``)*`)",
        remainder,
        re.I,
    )
    if comment_match is not None:
        remainder = remainder[comment_match.end():].strip()
    if remainder:
        raise ProviderError("pinned CREATE TABLE constraint was malformed")
    return index_columns


def _consume_foreign_key_constraint(
    rest: str,
) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    rest = rest.strip()
    if not rest.startswith("("):
        raise ProviderError("pinned CREATE TABLE constraint was malformed")
    closing = _find_matching_paren(rest, 0)
    local_cols = _parse_constraint_column_list(rest[1 : closing])
    rest = rest[closing + 1 :].strip()
    references_match = re.match(r"REFERENCES\s+", rest, re.I)
    if references_match is None:
        raise ProviderError("pinned CREATE TABLE constraint was malformed")
    rest = rest[references_match.end():].strip()
    ref_table, rest = _first_identifier(rest)
    _validate_ddl_table_identifier(ref_table)
    rest = rest.strip()
    if not rest.startswith("("):
        raise ProviderError("pinned CREATE TABLE constraint was malformed")
    ref_closing = _find_matching_paren(rest, 0)
    ref_cols = _parse_constraint_column_list(rest[1 : ref_closing])
    if len(local_cols) != len(ref_cols):
        raise ProviderError("pinned CREATE TABLE constraint was malformed")
    rest = rest[ref_closing + 1 :].strip()
    seen_actions: set[str] = set()
    while rest:
        on_match = re.match(
            r"ON\s+(DELETE|UPDATE)\s+(RESTRICT|CASCADE|SET\s+NULL|NO\s+ACTION)\s*",
            rest,
            re.I,
        )
        if on_match is None:
            raise ProviderError("pinned CREATE TABLE constraint was malformed")
        action_kind = on_match.group(1).upper()
        if action_kind in seen_actions:
            raise ProviderError("pinned CREATE TABLE constraint was malformed")
        seen_actions.add(action_kind)
        rest = rest[on_match.end():].strip()
    return local_cols, ref_table, ref_cols


def _consume_table_constraint(definition: str) -> _TableConstraintRefs:
    stripped = definition.strip()
    if not stripped:
        raise ProviderError("pinned CREATE TABLE constraint was malformed")

    check_match = re.match(r"CHECK\s+", stripped, re.I)
    if check_match is not None:
        rest = stripped[check_match.end():].strip()
        if not rest.startswith("("):
            raise ProviderError("pinned CREATE TABLE constraint was malformed")
        closing = _find_matching_paren(rest, 0)
        if not rest[1 : closing].strip():
            raise ProviderError("pinned CREATE TABLE constraint was malformed")
        remainder = rest[closing + 1 :].strip()
        version_comment_match = _CHECK_NOT_ENFORCED_VERSION_COMMENT.match(remainder)
        if version_comment_match is not None:
            remainder = remainder[version_comment_match.end():].strip()
        if remainder:
            raise ProviderError("pinned CREATE TABLE constraint was malformed")
        return _TableConstraintRefs()

    foreign_match = re.match(r"FOREIGN\s+KEY\s+", stripped, re.I)
    if foreign_match is not None:
        foreign_key = _consume_foreign_key_constraint(stripped[foreign_match.end():])
        return _TableConstraintRefs((), (foreign_key,))

    constraint_match = re.match(r"CONSTRAINT\s+", stripped, re.I)
    if constraint_match is not None:
        rest = stripped[constraint_match.end():].strip()
        constraint_name, rest = _first_identifier(rest)
        _validate_ddl_column_identifier(constraint_name)
        return _consume_table_constraint(rest)

    index_match = re.match(
        r"(?:FULLTEXT\s+(?:KEY\s+)?|SPATIAL\s+(?:KEY\s+)?|UNIQUE\s+(?:KEY\s+)?|(?:KEY|INDEX)\s+)",
        stripped,
        re.I,
    )
    if index_match is not None:
        index_columns = _consume_index_like_constraint(stripped[index_match.end():])
        return _TableConstraintRefs((index_columns,), ())

    raise ProviderError("pinned CREATE TABLE constraint was malformed")


def _consume_column_modifiers(tail: str) -> _ColumnModifierState:
    remainder = tail.strip()
    state = _ColumnModifierState()
    while remainder:
        if re.match(r"PRIMARY\s+KEY\b", remainder, re.I):
            if state.inline_pk:
                raise ProviderError("invalid pinned DDL column definition")
            state.inline_pk = True
            remainder = re.sub(r"PRIMARY\s+KEY\b", "", remainder, count=1, flags=re.I).strip()
            continue
        if re.match(r"NOT\s+NULL\b", remainder, re.I):
            if state.nullable is not None:
                raise ProviderError("invalid pinned DDL column definition")
            state.nullable = False
            remainder = re.sub(r"NOT\s+NULL\b", "", remainder, count=1, flags=re.I).strip()
            continue
        if re.match(r"NULL\b", remainder, re.I):
            if state.nullable is not None:
                raise ProviderError("invalid pinned DDL column definition")
            state.nullable = True
            remainder = re.sub(r"NULL\b", "", remainder, count=1, flags=re.I).strip()
            continue
        if re.match(r"DEFAULT\s+", remainder, re.I):
            if state.has_default or state.has_generated or state.has_auto_increment:
                raise ProviderError("invalid pinned DDL column definition")
            state.has_default = True
            remainder = re.sub(r"DEFAULT\s+", "", remainder, count=1, flags=re.I).strip()
            remainder = _consume_sql_literal_or_expression(remainder)
            continue
        if re.match(r"ON\s+UPDATE\s+", remainder, re.I):
            if state.has_on_update or state.has_generated:
                raise ProviderError("invalid pinned DDL column definition")
            state.has_on_update = True
            remainder = re.sub(r"ON\s+UPDATE\s+", "", remainder, count=1, flags=re.I).strip()
            remainder = _consume_sql_literal_or_expression(remainder)
            continue
        comment_match = re.match(
            r"COMMENT\s+(?:'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|`(?:[^`]|``)*`)",
            remainder,
            re.I,
        )
        if comment_match is not None:
            if state.has_comment:
                raise ProviderError("invalid pinned DDL column definition")
            state.has_comment = True
            remainder = remainder[comment_match.end():].strip()
            continue
        collate_match = re.match(r"COLLATE\s+\S+", remainder, re.I)
        if collate_match is not None:
            if state.has_collate:
                raise ProviderError("invalid pinned DDL column definition")
            state.has_collate = True
            remainder = remainder[collate_match.end():].strip()
            continue
        if re.match(r"AUTO_INCREMENT\b", remainder, re.I):
            if state.has_auto_increment or state.has_generated or state.has_default:
                raise ProviderError("invalid pinned DDL column definition")
            state.has_auto_increment = True
            remainder = re.sub(r"AUTO_INCREMENT\b", "", remainder, count=1, flags=re.I).strip()
            continue
        if re.match(r"UNIQUE\b", remainder, re.I):
            if state.has_unique or state.has_generated:
                raise ProviderError("invalid pinned DDL column definition")
            state.has_unique = True
            remainder = re.sub(r"UNIQUE\b", "", remainder, count=1, flags=re.I).strip()
            continue
        generated_head = re.match(r"GENERATED\s+ALWAYS\s+AS\s*", remainder, re.I)
        if generated_head is not None:
            if (
                state.has_generated
                or state.has_default
                or state.has_on_update
                or state.has_auto_increment
                or state.inline_pk
                or state.has_unique
            ):
                raise ProviderError("invalid pinned DDL column definition")
            state.has_generated = True
            remainder = remainder[generated_head.end():].strip()
            if not remainder.startswith("("):
                raise ProviderError("invalid pinned DDL column definition")
            closing = _find_matching_paren(remainder, 0)
            inner = remainder[1:closing]
            _validate_parenthesized_sql_content(inner)
            remainder = remainder[closing + 1 :].strip()
            stored_match = re.match(r"(?:STORED|VIRTUAL)\b", remainder, re.I)
            if stored_match is not None:
                remainder = remainder[stored_match.end():].strip()
            continue
        raise ProviderError("invalid pinned DDL column definition")
    return state


def _column_type_and_tail(rest: str) -> tuple[str, str]:
    keywords = (
        " NOT ",
        " NULL",
        " DEFAULT",
        " ON UPDATE",
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


def _parse_create_statement_with_constraints(
    ddl: str, row_count: int
) -> tuple[TableCatalog, _TableConstraintRefs]:
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
    index_column_lists: list[tuple[str, ...]] = []
    foreign_keys: list[tuple[tuple[str, ...], str, tuple[str, ...]]] = []
    auto_increment_columns: set[str] = set()
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
        if upper.startswith("PRIMARY") and not upper.startswith("PRIMARY KEY"):
            raise ProviderError("pinned CREATE TABLE constraint was malformed")
        if any(upper.startswith(prefix) for prefix in _TABLE_CONSTRAINT_PREFIXES):
            table_constraints = _consume_table_constraint(stripped_definition)
            index_column_lists.extend(table_constraints.index_column_lists)
            foreign_keys.extend(table_constraints.foreign_keys)
            continue
        column_name, rest = _first_identifier(definition)
        column_name = _validate_ddl_column_identifier(column_name)
        sql_type, tail = _column_type_and_tail(rest)
        tail, spatial_srid = _extract_trailing_spatial_srid_version_comment(tail)
        modifier_state = _consume_column_modifiers(tail)
        if spatial_srid is not None:
            base_type = " ".join(sql_type.upper().split())
            if base_type not in SPATIAL_SQL_TYPES:
                raise ProviderError("invalid pinned DDL column definition")
            sql_type = f"{sql_type} SRID {spatial_srid}"
        _validate_column_modifier_state(sql_type, modifier_state)
        if modifier_state.nullable is False:
            nullable = False
        elif modifier_state.nullable is True:
            nullable = True
        else:
            nullable = not bool(re.search(r"\bNOT\s+NULL\b", tail, re.I))
        if modifier_state.has_auto_increment and nullable:
            raise ProviderError("invalid pinned DDL column definition")
        if modifier_state.inline_pk:
            if pk_defined:
                raise ProviderError("pinned CREATE TABLE has multiple primary key definitions")
            primary_key.append(column_name)
            pk_defined = True
        if modifier_state.has_auto_increment:
            auto_increment_columns.add(column_name)
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
    primary_key_set = set(primary_key)
    for column_name in auto_increment_columns:
        if column_name not in primary_key_set:
            raise ProviderError("invalid pinned DDL column definition")
    positions = {name: index for index, name in enumerate(primary_key, 1)}
    columns = [
        ColumnCatalog(column.name, column.sql_type, column.nullable, positions.get(column.name))
        for column in columns
    ]
    for column in columns:
        if column.primary_key_position is not None and column.nullable:
            raise ProviderError("pinned CREATE TABLE primary key column is nullable")
    constraints = _TableConstraintRefs(
        tuple(index_column_lists),
        tuple(foreign_keys),
    )
    table_name_index = _TableNameIndex(
        lower_to_exact={name.lower(): name},
        ambiguous_lower=frozenset(),
    )
    _validate_constraint_declared_columns(
        name,
        declared_columns,
        constraints,
        {name: declared_columns},
        table_name_index,
    )
    return TableCatalog(name, tuple(columns), row_count), constraints


def _parse_create_statement(ddl: str, row_count: int) -> TableCatalog:
    table, _ = _parse_create_statement_with_constraints(ddl, row_count)
    return table


def _catalog_from_schema_diff(
    rows: list[dict[str, Any]], counts: dict[str, int]
) -> tuple[TableCatalog, ...]:
    parsed: list[tuple[TableCatalog, _TableConstraintRefs]] = []
    for row in rows:
        ddl = row.get("to_create_statement")
        if ddl in (None, ""):
            continue
        table, constraints = _parse_create_statement_with_constraints(str(ddl), 0)
        parsed.append((table, constraints))
    if not parsed and any(row.get("to_create_statement") not in (None, "") for row in rows):
        raise ProviderError("pinned schema diff did not produce a target catalog")
    _validate_schema_diff_table_names(parsed)
    table_name_index = _build_table_name_index(parsed)
    all_table_columns = {
        table.name: {column.name for column in table.columns} for table, _ in parsed
    }
    tables: dict[str, TableCatalog] = {}
    for table, constraints in parsed:
        if table.name in tables:
            raise ProviderError("pinned schema diff has duplicate table names")
        _validate_constraint_declared_columns(
            table.name,
            all_table_columns[table.name],
            constraints,
            all_table_columns,
            table_name_index,
        )
        tables[table.name] = TableCatalog(
            table.name,
            table.columns,
            counts.get(table.name, 0),
        )
    return tuple(tables[name] for name in sorted(tables))


def _tagged_select_list(plan: CompiledTablePlan) -> tuple[str, list[str]]:
    expressions: list[str] = []
    header: list[str] = []
    for index, column_plan in enumerate(plan.columns):
        column = column_plan.column
        source = quote_identifier(column.name)
        null_name = f"__gateway_null_{index}"
        value_name = f"__gateway_value_{index}"
        value_expression = (
            f"HEX({source})"
            if column_plan.hex_cell
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


def _tagged_select_list_for_catalog(
    table: TableCatalog,
    policy: UnknownTypePolicy,
) -> tuple[str, list[str]]:
    return _tagged_select_list(compile_table_plan(table, policy))


def _parse_tagged_row(row: list[str], plan: CompiledTablePlan) -> tuple[Any, ...]:
    if len(row) != len(plan.columns) * 2:
        raise ProviderError("tagged CSV column count mismatch")
    values: list[Any] = []
    for index, column_plan in enumerate(plan.columns):
        null_bit, value = row[index * 2 : index * 2 + 2]
        if null_bit not in {"0", "1"}:
            raise ProviderError("tagged CSV null bit was invalid")
        if null_bit == "1":
            values.append(None)
        elif column_plan.hex_cell:
            try:
                if column_plan.bit_width is not None:
                    width = column_plan.bit_width
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
    normalized_rows: list[NormalizedRow],
    *,
    row_bound: int,
    byte_bound: int,
) -> int:
    payload_bytes = sum(row.logical_size_bytes for row in normalized_rows)
    row_count = len(normalized_rows)
    row_sizes = [row.logical_size_bytes for row in normalized_rows]
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
