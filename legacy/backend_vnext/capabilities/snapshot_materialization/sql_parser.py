from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal
import hashlib
import re
from time import perf_counter
from typing import Any, Final

from ...core.digests import DigestRef
from .models import SnapshotTableColumn, canonical_identifier
from .versions import FAST_ROW_DIGEST_VERSION


CREATE_TABLE_RE: Final = re.compile(
    r"^CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>.+?)\s*\(",
    re.IGNORECASE | re.DOTALL,
)
DROP_TABLE_RE: Final = re.compile(
    r"^DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?P<name>.+?)(?:\s+CASCADE|\s+RESTRICT)?$",
    re.IGNORECASE | re.DOTALL,
)
INSERT_TABLE_RE: Final = re.compile(
    r"^INSERT\s+INTO\s+(?P<table>.+?)(?:\s*\((?P<columns>.*?)\))?\s+VALUES\s*(?P<values>.*)$",
    re.IGNORECASE | re.DOTALL,
)
STOP_COLUMN_TYPE_TOKENS: Final = {
    "AUTO_INCREMENT",
    "CHECK",
    "CHARACTER",
    "COLLATE",
    "COMMENT",
    "CONSTRAINT",
    "DEFAULT",
    "GENERATED",
    "KEY",
    "NOT",
    "NULL",
    "ON",
    "PRIMARY",
    "REFERENCES",
    "UNIQUE",
    "VISIBLE",
    "INVISIBLE",
}


@dataclass(frozen=True, slots=True)
class ParsedTableDefinition:
    table_name: str
    display_table_name: str
    raw_create_sql: str
    columns: tuple[SnapshotTableColumn, ...]
    primary_key_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParsedInsertStatement:
    table_name: str
    display_table_name: str
    column_names: tuple[str, ...] | None
    row_count: int
    raw_sql: str
    values_start: int
    values_end: int


@dataclass(frozen=True, slots=True)
class ParsedSqlParserMetrics:
    statement_count: int = 0
    create_statement_count: int = 0
    insert_statement_count: int = 0
    insert_row_count: int = 0
    skipped_insert_statement_count: int = 0
    statement_classify_duration_ms: int = 0
    create_parse_duration_ms: int = 0
    insert_parse_duration_ms: int = 0
    digest_duration_ms: int = 0
    finalize_duration_ms: int = 0
    max_statement_size_bytes: int = 0

    def to_payload(self) -> dict[str, object]:
        return {
            "parser_statement_count": self.statement_count,
            "parser_create_statement_count": self.create_statement_count,
            "parser_insert_statement_count": self.insert_statement_count,
            "parser_insert_row_count": self.insert_row_count,
            "parser_skipped_insert_statement_count": self.skipped_insert_statement_count,
            "parser_statement_classify_duration_ms": self.statement_classify_duration_ms,
            "parser_create_parse_duration_ms": self.create_parse_duration_ms,
            "parser_insert_parse_duration_ms": self.insert_parse_duration_ms,
            "parser_digest_duration_ms": self.digest_duration_ms,
            "parser_finalize_duration_ms": self.finalize_duration_ms,
            "parser_max_statement_size_bytes": self.max_statement_size_bytes,
        }


@dataclass(slots=True)
class _ParserMetricsBuilder:
    statement_count: int = 0
    create_statement_count: int = 0
    insert_statement_count: int = 0
    insert_row_count: int = 0
    skipped_insert_statement_count: int = 0
    statement_classify_duration_ms: int = 0
    create_parse_duration_ms: int = 0
    insert_parse_duration_ms: int = 0
    digest_duration_ms: int = 0
    finalize_duration_ms: int = 0
    max_statement_size_bytes: int = 0

    def build(self) -> ParsedSqlParserMetrics:
        return ParsedSqlParserMetrics(
            statement_count=self.statement_count,
            create_statement_count=self.create_statement_count,
            insert_statement_count=self.insert_statement_count,
            insert_row_count=self.insert_row_count,
            skipped_insert_statement_count=self.skipped_insert_statement_count,
            statement_classify_duration_ms=self.statement_classify_duration_ms,
            create_parse_duration_ms=self.create_parse_duration_ms,
            insert_parse_duration_ms=self.insert_parse_duration_ms,
            digest_duration_ms=self.digest_duration_ms,
            finalize_duration_ms=self.finalize_duration_ms,
            max_statement_size_bytes=self.max_statement_size_bytes,
        )


@dataclass(frozen=True, slots=True)
class ParsedTableBundle:
    definition: ParsedTableDefinition
    insert_statements: tuple[ParsedInsertStatement, ...]
    row_count: int
    raw_sql_digest: DigestRef
    fast_row_digest: DigestRef
    parse_skipped_insert_statement_count: int = 0
    parse_skipped_row_count: int = 0
    _rows: tuple[tuple[object, ...], ...] | None = field(default=None, repr=False)

    @property
    def rows(self) -> tuple[tuple[object, ...], ...]:
        rows = self._rows
        if rows is not None:
            return rows
        materialized_rows: list[tuple[object, ...]] = []
        for insert in self.insert_statements:
            materialized_rows.extend(_expand_insert_rows(insert, self.definition))
        rows = tuple(materialized_rows)
        object.__setattr__(self, "_rows", rows)
        return rows


@dataclass(frozen=True, slots=True)
class ParsedSqlDump:
    tables: dict[str, ParsedTableBundle]
    ignored_statement_count: int = 0
    dropped_table_count: int = 0
    parse_skipped_insert_table_count: int = 0
    parse_skipped_insert_statement_count: int = 0
    parse_skipped_insert_row_count: int = 0
    metrics: ParsedSqlParserMetrics = field(default_factory=ParsedSqlParserMetrics)
    unsupported_statements: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class _TableAccumulator:
    definition: ParsedTableDefinition | None = None
    raw_create_sql: str | None = None
    pending_inserts: list[ParsedInsertStatement] = field(default_factory=list)
    insert_statements: list[ParsedInsertStatement] = field(default_factory=list)
    row_count: int = 0
    raw_sql_hasher: Any | None = None
    fast_row_hasher: Any | None = None
    skip_insert_row_parsing: bool = False
    parse_skipped_insert_statement_count: int = 0
    parse_skipped_row_count: int = 0

    def register_create(
        self,
        definition: ParsedTableDefinition,
        raw_sql: str,
        *,
        skip_insert_row_parsing: bool = False,
        metrics: _ParserMetricsBuilder | None = None,
    ) -> None:
        self.definition = definition
        self.raw_create_sql = raw_sql
        self.skip_insert_row_parsing = skip_insert_row_parsing
        self._ensure_raw_sql_hasher()
        digest_started_at = perf_counter()
        _update_digest_chunk(self.raw_sql_hasher, raw_sql)
        if metrics is not None:
            metrics.digest_duration_ms += _elapsed_ms(digest_started_at)
        if self.pending_inserts:
            self._flush_pending_inserts(metrics=metrics)

    def register_insert(
        self,
        insert: ParsedInsertStatement,
        *,
        metrics: _ParserMetricsBuilder | None = None,
    ) -> None:
        self._ensure_raw_sql_hasher()
        digest_started_at = perf_counter()
        _update_digest_chunk(self.raw_sql_hasher, insert.raw_sql)
        self._ensure_fast_row_hasher()
        _update_digest_chunk_span(
            self.fast_row_hasher,
            insert.raw_sql,
            insert.values_start,
            insert.values_end,
        )
        if metrics is not None:
            metrics.digest_duration_ms += _elapsed_ms(digest_started_at)
        self.row_count += insert.row_count
        if self.definition is None:
            self.pending_inserts.append(insert)
            return
        if self.skip_insert_row_parsing:
            self.parse_skipped_insert_statement_count += 1
            self.parse_skipped_row_count += insert.row_count
            if metrics is not None:
                metrics.skipped_insert_statement_count += 1
            return
        self.insert_statements.append(insert)

    def finalize(self, *, metrics: _ParserMetricsBuilder | None = None) -> ParsedTableBundle | None:
        if self.definition is None:
            return None
        if self.pending_inserts:
            self._flush_pending_inserts(metrics=metrics)
        if self.raw_create_sql is None:
            raise ValueError("table accumulator is missing CREATE TABLE SQL")
        if self.raw_sql_hasher is None:
            raise ValueError("table accumulator is missing raw SQL digest state")
        self._ensure_fast_row_hasher()
        return ParsedTableBundle(
            definition=self.definition,
            insert_statements=tuple(self.insert_statements),
            row_count=self.row_count,
            raw_sql_digest=DigestRef.from_hex(self.raw_sql_hasher.hexdigest()),
            fast_row_digest=DigestRef.from_hex(self.fast_row_hasher.hexdigest()),
            parse_skipped_insert_statement_count=self.parse_skipped_insert_statement_count,
            parse_skipped_row_count=self.parse_skipped_row_count,
        )

    def _ensure_raw_sql_hasher(self) -> None:
        if self.raw_sql_hasher is None:
            self.raw_sql_hasher = hashlib.sha256()

    def _ensure_fast_row_hasher(self) -> None:
        if self.fast_row_hasher is None:
            self.fast_row_hasher = hashlib.sha256()
            _update_digest_chunk(self.fast_row_hasher, FAST_ROW_DIGEST_VERSION)

    def _flush_pending_inserts(self, *, metrics: _ParserMetricsBuilder | None = None) -> None:
        assert self.definition is not None
        if self.skip_insert_row_parsing:
            self.parse_skipped_insert_statement_count += len(self.pending_inserts)
            self.parse_skipped_row_count += sum(insert.row_count for insert in self.pending_inserts)
            if metrics is not None:
                metrics.skipped_insert_statement_count += len(self.pending_inserts)
            self.pending_inserts.clear()
            return
        self.insert_statements.extend(self.pending_inserts)
        self.pending_inserts.clear()


def split_sql_statements(sql_text: str) -> list[str]:
    return list(iter_sql_statements(sql_text))


def iter_sql_statements(sql_text: str) -> Iterator[str]:
    parts: list[str] = []
    segment_start = 0
    i = 0
    length = len(sql_text)
    while i < length:
        ch = sql_text[i]
        if ch == "'":
            i = _skip_quoted_text(sql_text, i, "'")
            continue
        if ch == '"':
            i = _skip_quoted_text(sql_text, i, '"')
            continue
        if ch == "`":
            i = _skip_quoted_text(sql_text, i, "`")
            continue
        if ch == "#" and _is_line_comment(sql_text, i):
            if segment_start < i:
                parts.append(sql_text[segment_start:i])
            i = _consume_line_comment(sql_text, i + 1)
            segment_start = i
            continue
        if (
            ch == "-"
            and i + 1 < length
            and sql_text[i + 1] == "-"
            and _is_line_comment(sql_text, i)
        ):
            if segment_start < i:
                parts.append(sql_text[segment_start:i])
            i = _consume_line_comment(sql_text, i + 2)
            segment_start = i
            continue
        if ch == "/" and i + 1 < length and sql_text[i + 1] == "*":
            if segment_start < i:
                parts.append(sql_text[segment_start:i])
            i = _consume_block_comment(sql_text, i + 2)
            segment_start = i
            continue
        if ch == ";":
            if segment_start < i:
                parts.append(sql_text[segment_start:i])
            statement = "".join(parts).strip()
            if statement:
                yield statement
            parts.clear()
            i += 1
            segment_start = i
            continue
        i += 1
    if segment_start < length:
        parts.append(sql_text[segment_start:length])
    statement = "".join(parts).strip()
    if statement:
        yield statement


def iter_sql_statements_from_chunks(chunks: Iterable[str]) -> Iterator[str]:
    parts: list[str] = []
    quote: str | None = None
    escape = False
    line_comment = False
    block_comment = False
    pending_prefix = ""
    for chunk in chunks:
        if pending_prefix:
            chunk = pending_prefix + chunk
            pending_prefix = ""
        if not chunk:
            continue
        segment_start = 0
        i = 0
        length = len(chunk)
        while i < length:
            ch = chunk[i]
            if line_comment:
                if ch in "\r\n":
                    line_comment = False
                    i += 1
                    segment_start = i
                    continue
                i += 1
                continue
            if block_comment:
                if ch == "*" and i + 1 < length and chunk[i + 1] == "/":
                    block_comment = False
                    i += 2
                    segment_start = i
                    continue
                i += 1
                continue
            if quote is not None:
                if escape:
                    escape = False
                elif ch == "\\" and quote != "`":
                    escape = True
                elif ch == quote:
                    quote = None
                i += 1
                continue
            if ch in {"'", '"', "`"}:
                quote = ch
                i += 1
                continue
            if ch == "#" and _is_line_comment(chunk, i):
                if segment_start < i:
                    parts.append(chunk[segment_start:i])
                line_comment = True
                i += 1
                continue
            if (
                ch == "-"
                and i + 1 < length
                and chunk[i + 1] == "-"
                and _is_line_comment(chunk, i)
            ):
                if segment_start < i:
                    parts.append(chunk[segment_start:i])
                line_comment = True
                i += 2
                continue
            if ch == "/" and i + 1 < length and chunk[i + 1] == "*":
                if segment_start < i:
                    parts.append(chunk[segment_start:i])
                block_comment = True
                i += 2
                continue
            if ch == ";":
                if segment_start < i:
                    parts.append(chunk[segment_start:i])
                statement = "".join(parts).strip()
                if statement:
                    yield statement
                parts.clear()
                i += 1
                segment_start = i
                continue
            i += 1
        if not line_comment and not block_comment and segment_start < length:
            append_end = length
            if quote is None and chunk[-1:] in {"-", "/"}:
                append_end = length - 1
                pending_prefix = chunk[-1]
            if segment_start < append_end:
                parts.append(chunk[segment_start:append_end])
    if pending_prefix:
        parts.append(pending_prefix)
    statement = "".join(parts).strip()
    if statement:
        yield statement


def _classify_statement(statement: str) -> str:
    if _starts_with_ci(statement, "DROP TABLE"):
        return "DROP_TABLE"
    if _starts_with_ci(statement, "CREATE TABLE"):
        return "CREATE_TABLE"
    if _starts_with_ci(statement, "INSERT INTO"):
        return "INSERT_INTO"
    if _starts_with_any_ci(statement, ("LOCK TABLES", "UNLOCK TABLES", "SET ", "USE ")):
        return "IGNORED"
    if _starts_with_any_ci(
        statement,
        ("ALTER TABLE", "TRUNCATE TABLE", "RENAME TABLE", "CREATE INDEX"),
    ):
        return "IGNORED_DDL"
    if _starts_with_any_ci(
        statement,
        ("CREATE ", "ALTER ", "DROP ", "TRUNCATE ", "RENAME ", "LOAD ", "CALL "),
    ):
        return "UNSUPPORTED"
    return "OTHER"


def _starts_with_any_ci(text: str, prefixes: tuple[str, ...]) -> bool:
    return any(_starts_with_ci(text, prefix) for prefix in prefixes)


def _starts_with_ci(text: str, prefix: str) -> bool:
    return text[: len(prefix)].upper() == prefix


def parse_mysql_dump(
    sql_text: str,
    *,
    should_skip_insert_rows: Callable[[ParsedTableDefinition], bool] | None = None,
) -> ParsedSqlDump:
    return parse_mysql_dump_statements(
        iter_sql_statements(sql_text),
        should_skip_insert_rows=should_skip_insert_rows,
    )


def parse_mysql_dump_chunks(
    chunks: Iterable[str],
    *,
    should_skip_insert_rows: Callable[[ParsedTableDefinition], bool] | None = None,
) -> ParsedSqlDump:
    return parse_mysql_dump_statements(
        iter_sql_statements_from_chunks(chunks),
        should_skip_insert_rows=should_skip_insert_rows,
    )


def parse_mysql_dump_statements(
    statements: Iterable[str],
    *,
    should_skip_insert_rows: Callable[[ParsedTableDefinition], bool] | None = None,
) -> ParsedSqlDump:
    accumulators: dict[str, _TableAccumulator] = {}
    ignored_statement_count = 0
    dropped_table_count = 0
    unsupported_statements: list[str] = []
    metrics = _ParserMetricsBuilder()

    for statement in statements:
        stripped = statement.strip()
        if not stripped:
            continue
        metrics.statement_count += 1
        metrics.max_statement_size_bytes = max(
            metrics.max_statement_size_bytes,
            len(stripped.encode("utf-8")),
        )
        classify_started_at = perf_counter()
        statement_kind = _classify_statement(stripped)
        metrics.statement_classify_duration_ms += _elapsed_ms(classify_started_at)
        if statement_kind == "DROP_TABLE":
            dropped_table_count += 1
            table_name = _parse_drop_table_name(stripped)
            accumulators.pop(table_name, None)
            continue
        if statement_kind == "CREATE_TABLE":
            create_parse_started_at = perf_counter()
            definition = _parse_create_table(stripped)
            metrics.create_parse_duration_ms += _elapsed_ms(create_parse_started_at)
            metrics.create_statement_count += 1
            accumulator = accumulators.setdefault(definition.table_name, _TableAccumulator())
            skip_insert_row_parsing = (
                False
                if should_skip_insert_rows is None
                else should_skip_insert_rows(definition)
            )
            accumulator.register_create(
                definition,
                stripped,
                skip_insert_row_parsing=skip_insert_row_parsing,
                metrics=metrics,
            )
            continue
        if statement_kind == "INSERT_INTO":
            insert_parse_started_at = perf_counter()
            insert = _parse_insert_statement(stripped)
            metrics.insert_parse_duration_ms += _elapsed_ms(insert_parse_started_at)
            metrics.insert_statement_count += 1
            metrics.insert_row_count += insert.row_count
            accumulator = accumulators.setdefault(insert.table_name, _TableAccumulator())
            accumulator.register_insert(insert, metrics=metrics)
            continue
        if statement_kind == "IGNORED":
            ignored_statement_count += 1
            continue
        if statement_kind == "IGNORED_DDL":
            ignored_statement_count += 1
            continue
        ignored_statement_count += 1
        if statement_kind == "UNSUPPORTED":
            unsupported_statements.append(stripped[:240])

    tables: dict[str, ParsedTableBundle] = {}
    finalize_started_at = perf_counter()
    for table_name, accumulator in accumulators.items():
        bundle = accumulator.finalize(metrics=metrics)
        if bundle is None:
            continue
        tables[table_name] = bundle
    metrics.finalize_duration_ms += _elapsed_ms(finalize_started_at)
    parse_skipped_bundles = [
        bundle for bundle in tables.values() if bundle.parse_skipped_insert_statement_count > 0
    ]
    return ParsedSqlDump(
        tables=tables,
        ignored_statement_count=ignored_statement_count,
        dropped_table_count=dropped_table_count,
        parse_skipped_insert_table_count=len(parse_skipped_bundles),
        parse_skipped_insert_statement_count=sum(
            bundle.parse_skipped_insert_statement_count for bundle in parse_skipped_bundles
        ),
        parse_skipped_insert_row_count=sum(
            bundle.parse_skipped_row_count for bundle in parse_skipped_bundles
        ),
        metrics=metrics.build(),
        unsupported_statements=tuple(unsupported_statements),
    )


def _parse_create_table(statement: str) -> ParsedTableDefinition:
    match = CREATE_TABLE_RE.match(statement)
    if match is None:
        raise ValueError(f"unsupported CREATE TABLE statement: {statement[:120]}")
    table_name_display, table_name = _parse_identifier_expression(match.group("name"))
    body_start = match.end() - 1
    body_end = _find_matching_paren(statement, body_start)
    body = statement[body_start + 1 : body_end]
    items = [item.strip() for item in _split_top_level(body, ",") if item.strip()]

    columns: list[SnapshotTableColumn] = []
    table_level_primary_key: tuple[str, ...] | None = None
    inline_primary_key_columns: list[str] = []
    for item in items:
        upper = item.lstrip().upper()
        if upper.startswith("PRIMARY KEY"):
            table_level_primary_key = _parse_constraint_identifier_list(item)
            continue
        if upper.startswith(
            (
                "UNIQUE KEY",
                "UNIQUE INDEX",
                "KEY ",
                "INDEX ",
                "FULLTEXT KEY",
                "SPATIAL KEY",
                "CONSTRAINT ",
                "FOREIGN KEY",
                "CHECK ",
            )
        ):
            continue
        column = _parse_column_definition(item)
        columns.append(column)
        if _column_definition_has_inline_primary_key(item):
            inline_primary_key_columns.append(column.name)

    primary_key_columns = (
        table_level_primary_key
        or tuple(inline_primary_key_columns)
        or ()
    )
    table_comment = _parse_table_comment(statement[body_end + 1 :])
    return ParsedTableDefinition(
        table_name=table_name,
        display_table_name=table_comment or table_name_display,
        raw_create_sql=statement,
        columns=tuple(columns),
        primary_key_columns=primary_key_columns,
    )


def _parse_insert_statement(statement: str) -> ParsedInsertStatement:
    match = INSERT_TABLE_RE.match(statement)
    if match is None:
        raise ValueError(f"unsupported INSERT INTO statement: {statement[:120]}")
    table_name_display, table_name = _parse_identifier_expression(match.group("table"))
    columns_text = match.group("columns")
    column_names = (
        None
        if columns_text is None
        else tuple(
            canonical_identifier(part)
            for part in (_parse_identifier_expression(item)[0] for item in _split_top_level(columns_text, ","))
        )
    )
    values_start, values_end = _trim_insert_values_span(statement, *match.span("values"))
    return ParsedInsertStatement(
        table_name=table_name,
        display_table_name=table_name_display,
        column_names=column_names,
        row_count=_count_insert_rows_span(statement, values_start, values_end),
        raw_sql=statement,
        values_start=values_start,
        values_end=values_end,
    )


def _trim_insert_values_span(statement: str, start: int, end: int) -> tuple[int, int]:
    while start < end and statement[start].isspace():
        start += 1
    while end > start and statement[end - 1].isspace():
        end -= 1
    if end > start and statement[end - 1] == ";":
        end -= 1
        while end > start and statement[end - 1].isspace():
            end -= 1
    return start, end


def _insert_values_text(insert: ParsedInsertStatement) -> str:
    return insert.raw_sql[insert.values_start : insert.values_end]


def _expand_insert_rows(
    insert: ParsedInsertStatement,
    definition: ParsedTableDefinition,
) -> list[tuple[object, ...]]:
    rows = _parse_insert_rows(_insert_values_text(insert))
    columns = definition.columns
    if insert.column_names is None:
        expected_width = len(columns)
        expanded_rows: list[tuple[object, ...]] = []
        for row in rows:
            if len(row) != expected_width:
                raise ValueError(
                    f"row for {definition.table_name} has {len(row)} values but expected {expected_width}"
                )
            expanded_rows.append(tuple(row))
        return expanded_rows

    column_index_by_name = {
        column.name: index for index, column in enumerate(columns)
    }
    requested_indices = []
    for column_name in insert.column_names:
        if column_name not in column_index_by_name:
            raise ValueError(
                f"INSERT column {column_name} does not exist in {definition.table_name}"
            )
        requested_indices.append(column_index_by_name[column_name])

    expanded_rows = []
    for row in rows:
        if len(row) != len(requested_indices):
            raise ValueError(
                f"row for {definition.table_name} has {len(row)} values but expected {len(requested_indices)}"
            )
        expanded = [None] * len(columns)
        for index, value in zip(requested_indices, row, strict=True):
            expanded[index] = value
        expanded_rows.append(tuple(expanded))
    return expanded_rows


def _iter_expand_insert_rows(
    insert: ParsedInsertStatement,
    definition: ParsedTableDefinition,
) -> Iterator[tuple[object, ...]]:
    rows = _iter_parse_insert_rows(_insert_values_text(insert))
    columns = definition.columns
    if insert.column_names is None:
        expected_width = len(columns)
        for row in rows:
            if len(row) != expected_width:
                raise ValueError(
                    f"row for {definition.table_name} has {len(row)} values but expected {expected_width}"
                )
            yield tuple(row)
        return

    column_index_by_name = {
        column.name: index for index, column in enumerate(columns)
    }
    requested_indices = []
    for column_name in insert.column_names:
        if column_name not in column_index_by_name:
            raise ValueError(
                f"INSERT column {column_name} does not exist in {definition.table_name}"
            )
        requested_indices.append(column_index_by_name[column_name])

    for row in rows:
        if len(row) != len(requested_indices):
            raise ValueError(
                f"row for {definition.table_name} has {len(row)} values but expected {len(requested_indices)}"
            )
        expanded = [None] * len(columns)
        for index, value in zip(requested_indices, row, strict=True):
            expanded[index] = value
        yield tuple(expanded)


def _extract_insert_values_text(statement: str) -> str:
    match = INSERT_TABLE_RE.match(statement)
    if match is None:
        raise ValueError(f"unsupported INSERT INTO statement: {statement[:120]}")
    values_text = match.group("values").strip()
    if values_text.endswith(";"):
        values_text = values_text[:-1].rstrip()
    return values_text


def _parse_insert_rows(values_text: str) -> tuple[tuple[object, ...], ...]:
    return tuple(_iter_parse_insert_rows(values_text))


def _iter_parse_insert_rows(values_text: str) -> Iterator[tuple[object, ...]]:
    current_row: list[str] = []
    depth = 0
    in_quote = False
    escape = False
    for char in values_text:
        if in_quote:
            current_row.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == "'":
                in_quote = False
            continue
        if char == "'":
            in_quote = True
            current_row.append(char)
            continue
        if char == "(":
            if depth > 0:
                current_row.append(char)
            depth += 1
            continue
        if char == ")" and depth > 0:
            depth -= 1
            if depth == 0:
                row_payload = "".join(current_row)
                yield tuple(
                    _parse_literal(item)
                    for item in _split_row_values(row_payload)
                    if item.strip()
                )
                current_row = []
                continue
            current_row.append(char)
            continue
        if depth > 0:
            current_row.append(char)


def _count_insert_rows(values_text: str) -> int:
    return _count_insert_rows_span(values_text, 0, len(values_text))


def _count_insert_rows_span(text: str, start: int, end: int) -> int:
    row_count = 0
    depth = 0
    in_quote = False
    escape = False
    for index in range(start, end):
        char = text[index]
        if in_quote:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == "'":
                in_quote = False
            continue
        if char == "'":
            in_quote = True
            continue
        if char == "(":
            if depth == 0:
                row_count += 1
            depth += 1
            continue
        if char == ")" and depth > 0:
            depth -= 1
    return row_count


def _split_row_values(row_payload: str) -> tuple[str, ...]:
    values: list[str] = []
    current: list[str] = []
    depth = 0
    in_quote = False
    escape = False
    for char in row_payload:
        if in_quote:
            current.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == "'":
                in_quote = False
            continue
        if char == "'":
            in_quote = True
            current.append(char)
            continue
        if char == "(":
            depth += 1
            current.append(char)
            continue
        if char == ")" and depth > 0:
            depth -= 1
            current.append(char)
            continue
        if char == "," and depth == 0:
            values.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    tail = "".join(current).strip()
    if tail:
        values.append(tail)
    return tuple(values)


def _update_digest_chunk(hasher: Any, text: str) -> None:
    raw_bytes = text.encode("utf-8")
    hasher.update(len(raw_bytes).to_bytes(8, "big"))
    hasher.update(raw_bytes)


def _update_digest_chunk_span(hasher: Any, text: str, start: int, end: int) -> None:
    raw_bytes = text[start:end].encode("utf-8")
    hasher.update(len(raw_bytes).to_bytes(8, "big"))
    hasher.update(raw_bytes)


def _elapsed_ms(started_at: float) -> int:
    return max(0, int(round((perf_counter() - started_at) * 1000)))


def _parse_column_definition(item: str) -> SnapshotTableColumn:
    match = re.match(r"^\s*(?P<name>\S+)\s+(?P<tail>.+)$", item, re.DOTALL)
    if match is None:
        raise ValueError(f"unsupported column definition: {item[:120]}")
    display_name, canonical_name = _parse_identifier_expression(match.group("name"))
    tail = match.group("tail").strip()
    tokens = _split_top_level_words(tail)
    scalar_type_tokens: list[str] = []
    for token in tokens:
        if token.upper() in STOP_COLUMN_TYPE_TOKENS:
            break
        scalar_type_tokens.append(token)
    scalar_type = " ".join(scalar_type_tokens).strip() or None
    nullable = True
    upper_tokens = [token.upper() for token in tokens]
    for index in range(len(upper_tokens) - 1):
        if upper_tokens[index] == "NOT" and upper_tokens[index + 1] == "NULL":
            nullable = False
            break
    return SnapshotTableColumn(
        name=canonical_name,
        display_name=display_name,
        scalar_type=scalar_type,
        nullable=nullable,
    )


def _column_definition_has_inline_primary_key(item: str) -> bool:
    return re.search(r"\bPRIMARY\s+KEY\b", item, re.IGNORECASE) is not None


def _parse_constraint_identifier_list(item: str) -> tuple[str, ...]:
    paren_start = item.find("(")
    if paren_start < 0:
        raise ValueError(f"PRIMARY KEY constraint missing columns: {item[:120]}")
    paren_end = _find_matching_paren(item, paren_start)
    inner = item[paren_start + 1 : paren_end]
    return tuple(
        _parse_identifier_expression(part)[1]
        for part in _split_top_level(inner, ",")
        if part.strip()
    )


def _parse_row_tuple(row_text: str) -> tuple[object, ...]:
    text = row_text.strip()
    if not text.startswith("(") or not text.endswith(")"):
        raise ValueError(f"unsupported row tuple: {text[:120]}")
    inner = text[1:-1]
    values = [_parse_literal(item) for item in _split_top_level(inner, ",") if item.strip()]
    return tuple(values)


def _parse_literal(token: str) -> object:
    text = token.strip()
    if not text:
        raise ValueError("empty SQL literal")
    if text.upper() == "NULL":
        return None
    if text.upper() == "TRUE":
        return True
    if text.upper() == "FALSE":
        return False
    if (text.startswith("'") and text.endswith("'")) or (
        text.startswith('"') and text.endswith('"')
    ):
        return _unescape_sql_string(text[1:-1], text[0])
    if text.startswith(("0x", "0X")) and re.fullmatch(r"0[xX][0-9A-Fa-f]+", text):
        return int(text, 16)
    if re.fullmatch(r"[+-]?\d+", text):
        return int(text)
    if re.fullmatch(r"[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?", text):
        return Decimal(text)
    return text


def _unescape_sql_string(value: str, quote_char: str) -> str:
    result: list[str] = []
    i = 0
    length = len(value)
    while i < length:
        ch = value[i]
        if ch == "\\" and i + 1 < length:
            next_char = value[i + 1]
            escape_map = {
                "0": "\0",
                "b": "\b",
                "n": "\n",
                "r": "\r",
                "t": "\t",
                "Z": "\x1a",
                "\\": "\\",
                "'": "'",
                '"': '"',
                "%": "%",
                "_": "_",
            }
            result.append(escape_map.get(next_char, next_char))
            i += 2
            continue
        if ch == quote_char and i + 1 < length and value[i + 1] == quote_char:
            result.append(quote_char)
            i += 2
            continue
        result.append(ch)
        i += 1
    return "".join(result)


def _parse_drop_table_name(statement: str) -> str:
    match = DROP_TABLE_RE.match(statement)
    if match is None:
        raise ValueError(f"unsupported DROP TABLE statement: {statement[:120]}")
    _, table_name = _parse_identifier_expression(match.group("name"))
    return table_name


def _split_top_level(text: str, delimiter: str) -> list[str]:
    parts: list[str] = []
    buffer: list[str] = []
    depth = 0
    quote: str | None = None
    i = 0
    length = len(text)
    while i < length:
        ch = text[i]
        if quote is None:
            if ch == delimiter and depth == 0:
                parts.append("".join(buffer))
                buffer.clear()
                i += 1
                continue
            if ch == "(":
                depth += 1
            elif ch == ")" and depth > 0:
                depth -= 1
            elif ch in {"'", '"', "`"}:
                quote = ch
            buffer.append(ch)
            i += 1
            continue
        buffer.append(ch)
        if ch == "\\":
            if i + 1 < length:
                buffer.append(text[i + 1])
                i += 2
                continue
        if ch == quote:
            if quote in {"'", '"'} and i + 1 < length and text[i + 1] == quote:
                buffer.append(text[i + 1])
                i += 2
                continue
            quote = None
        i += 1
    parts.append("".join(buffer))
    return parts


def _split_top_level_words(text: str) -> list[str]:
    words: list[str] = []
    buffer: list[str] = []
    depth = 0
    quote: str | None = None
    i = 0
    length = len(text)
    while i < length:
        ch = text[i]
        if quote is None:
            if ch.isspace() and depth == 0:
                if buffer:
                    words.append("".join(buffer))
                    buffer.clear()
                i += 1
                continue
            if ch == "(":
                depth += 1
            elif ch == ")" and depth > 0:
                depth -= 1
            elif ch in {"'", '"', "`"}:
                quote = ch
            buffer.append(ch)
            i += 1
            continue
        buffer.append(ch)
        if ch == "\\":
            if i + 1 < length:
                buffer.append(text[i + 1])
                i += 2
                continue
        if ch == quote:
            if quote in {"'", '"'} and i + 1 < length and text[i + 1] == quote:
                buffer.append(text[i + 1])
                i += 2
                continue
            quote = None
        i += 1
    if buffer:
        words.append("".join(buffer))
    return words


def _parse_identifier_expression(text: str) -> tuple[str, str]:
    parts = _split_identifier_parts(text)
    if not parts:
        raise ValueError("empty identifier expression")
    display_parts = tuple(_unquote_identifier_part(part) for part in parts)
    canonical_parts = tuple(canonical_identifier(part) for part in display_parts)
    display = ".".join(display_parts)
    canonical = ".".join(canonical_parts)
    return display, canonical


def _parse_table_comment(table_options: str) -> str | None:
    match = re.search(
        r"\bCOMMENT\s*=\s*(?P<quote>['\"])(?P<comment>(?:\\.|(?!\1).)*)(?P=quote)",
        table_options,
        re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        return None
    comment = match.group("comment")
    quote = match.group("quote")
    if quote == "'":
        comment = comment.replace("''", "'")
    elif quote == '"':
        comment = comment.replace('""', '"')
    comment = re.sub(r"\\(.)", r"\1", comment)
    comment = comment.strip()
    return comment or None


def _split_identifier_parts(text: str) -> list[str]:
    parts: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    i = 0
    length = len(text)
    while i < length:
        ch = text[i]
        if quote is None and ch == ".":
            parts.append("".join(buffer).strip())
            buffer.clear()
            i += 1
            continue
        buffer.append(ch)
        if quote is None and ch in {"'", '"', "`"}:
            quote = ch
        elif quote is not None:
            if ch == "\\":
                if i + 1 < length:
                    buffer.append(text[i + 1])
                    i += 2
                    continue
            if ch == quote:
                if quote in {"'", '"'} and i + 1 < length and text[i + 1] == quote:
                    buffer.append(text[i + 1])
                    i += 2
                    continue
                quote = None
        i += 1
    parts.append("".join(buffer).strip())
    return [part for part in parts if part]


def _unquote_identifier_part(text: str) -> str:
    stripped = text.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"`", '"', "'"}:
        inner = stripped[1:-1]
        if stripped[0] == "`":
            return inner.replace("``", "`")
        if stripped[0] == '"':
            return inner.replace('""', '"')
        return inner.replace("''", "'")
    return stripped


def _find_matching_paren(text: str, open_index: int) -> int:
    if text[open_index] != "(":
        raise ValueError("open_index must point to an opening parenthesis")
    depth = 1
    quote: str | None = None
    i = open_index + 1
    length = len(text)
    while i < length:
        ch = text[i]
        if quote is None:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i
            elif ch in {"'", '"', "`"}:
                quote = ch
            i += 1
            continue
        if ch == "\\":
            i += 2
            continue
        if ch == quote:
            if quote in {"'", '"'} and i + 1 < length and text[i + 1] == quote:
                i += 2
                continue
            quote = None
        i += 1
    raise ValueError("unbalanced parentheses in SQL statement")


def _copy_quoted_text(
    sql_text: str,
    start_index: int,
    buffer: list[str],
    quote_char: str,
) -> int:
    buffer.append(quote_char)
    i = start_index + 1
    length = len(sql_text)
    while i < length:
        ch = sql_text[i]
        buffer.append(ch)
        if ch == "\\" and i + 1 < length:
            buffer.append(sql_text[i + 1])
            i += 2
            continue
        if ch == quote_char:
            if quote_char in {"'", '"'} and i + 1 < length and sql_text[i + 1] == quote_char:
                buffer.append(sql_text[i + 1])
                i += 2
                continue
            return i + 1
        i += 1
    return length


def _skip_quoted_text(sql_text: str, start_index: int, quote_char: str) -> int:
    i = start_index + 1
    length = len(sql_text)
    while i < length:
        ch = sql_text[i]
        if ch == "\\" and i + 1 < length:
            i += 2
            continue
        if ch == quote_char:
            if quote_char in {"'", '"'} and i + 1 < length and sql_text[i + 1] == quote_char:
                i += 2
                continue
            return i + 1
        i += 1
    return length


def _is_line_comment(sql_text: str, start_index: int) -> bool:
    if sql_text[start_index] == "#":
        return True
    if sql_text[start_index : start_index + 2] != "--":
        return False
    next_index = start_index + 2
    return next_index >= len(sql_text) or sql_text[next_index].isspace()


def _consume_line_comment(sql_text: str, start_index: int) -> int:
    i = start_index
    length = len(sql_text)
    while i < length and sql_text[i] not in "\r\n":
        i += 1
    return i


def _consume_block_comment(sql_text: str, start_index: int) -> int:
    end = sql_text.find("*/", start_index)
    if end < 0:
        return len(sql_text)
    return end + 2
