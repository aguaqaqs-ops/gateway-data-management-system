"""Private Candidate A/B Dolt providers used by the P2-R1 feasibility probe."""

from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import threading
from collections.abc import Coroutine, Iterator
from pathlib import Path
from typing import Any, Protocol, TypeVar
from uuid import uuid4

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_service.arrow_mapping import (
    ColumnCatalog,
    TableCatalog,
    UnknownTypePolicy,
    arrow_type,
    record_batch,
    normalize_sql_type,
)
from gateway_repository_service.layout import ProbeLayout
from gateway_repository_service.process import (
    CgroupMemoryTracker,
    DoltRunner,
    MemorySampler,
    ProcessStream,
    ServerSupervisor,
    process_tree_rss_kib,
    windows_for_interval,
)
from gateway_repository_service.settings import RepositoryServiceSettings


class ProviderError(RuntimeError):
    """Provider execution or correctness failure."""


class Provider(Protocol):
    repository: Path

    def open(self) -> None: ...

    def replay(self, replay_sql: Path) -> None: ...

    def commit_marker(self, marker: str) -> str: ...

    def head(self) -> str: ...

    def catalog(self, base_commit_id: str, target_commit_id: str) -> tuple[TableCatalog, ...]: ...

    def stream_table(
        self,
        commit_id: str,
        table: TableCatalog,
        policy: UnknownTypePolicy,
    ) -> Iterator[pa.RecordBatch]: ...

    def marker_parent(self, marker: str) -> str | None: ...

    def marker_count(self, marker: str) -> int: ...

    def close(self) -> None: ...


def quote_identifier(identifier: str) -> str:
    if not identifier or "\x00" in identifier or "/" in identifier or "\\" in identifier:
        raise ValueError("invalid SQL identifier")
    return "`" + identifier.replace("`", "``") + "`"


def _write_query(directory: Path, sql: str) -> Path:
    path = directory / f"query-{uuid4().hex}.sql"
    path.write_text(sql, encoding="utf-8")
    return path


def _json_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if "rows" in payload and "columns" in payload:
            columns = payload["columns"]
            names = [
                str(column.get("name", column.get("Name")))
                if isinstance(column, dict)
                else str(column)
                for column in columns
            ]
            raw_rows = payload["rows"]
            if not isinstance(raw_rows, list):
                raise ProviderError("Dolt JSON rows was not a list")
            return [
                {name: value for name, value in zip(names, row, strict=False)}
                for row in raw_rows
                if isinstance(row, list)
            ]
        for key in ("rows", "rowData", "data"):
            if key in payload:
                return _json_rows(payload[key])
        return [payload]
    if not isinstance(payload, list):
        raise ProviderError("Dolt JSON result was not a row list")
    rows: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            rows.append(item)
        elif isinstance(item, list):
            rows.append({str(index): value for index, value in enumerate(item)})
        else:
            raise ProviderError("Dolt JSON row was not an object")
    return rows


def _value(row: dict[str, Any], name: str, index: int | None = None) -> Any:
    if name in row:
        return row[name]
    lowered = {key.lower(): value for key, value in row.items()}
    if name.lower() in lowered:
        return lowered[name.lower()]
    if index is not None and str(index) in row:
        return row[str(index)]
    raise ProviderError(f"missing result column {name}")


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


def _commit_literal(commit_id: str) -> str:
    if not re.fullmatch(r"[0-9a-zA-Z_-]+", commit_id):
        raise ProviderError("invalid commit identifier")
    return "'" + commit_id.replace("'", "''") + "'"


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
    """Conservative pre-Arrow bound for the in-flight Python row batch."""

    return sum(
        sum(
            len(value.encode("utf-8"))
            if isinstance(value, str)
            else len(value)
            if isinstance(value, bytes)
            else 16
            for value in row
        )
        for row in rows
    )


def _row_bytes(row: tuple[Any, ...]) -> int:
    return _rows_bytes([row])


def _column_max_bytes(sql_type: str) -> int | None:
    """Return a conservative decoded-width bound, or None if it is unbounded."""

    upper = sql_type.upper()
    sized = re.fullmatch(r"(?:CHAR|VARCHAR)\((\d+)\)", upper)
    if sized is not None:
        return int(sized.group(1)) * 4 + 16
    sized_binary = re.fullmatch(r"(?:BINARY|VARBINARY)\((\d+)\)", upper)
    if sized_binary is not None:
        return int(sized_binary.group(1)) + 16
    fixed = {
        "BOOLEAN": 1,
        "TINYINT": 1,
        "TINYINT UNSIGNED": 1,
        "SMALLINT": 2,
        "SMALLINT UNSIGNED": 2,
        "MEDIUMINT": 4,
        "MEDIUMINT UNSIGNED": 4,
        "INT": 4,
        "INT UNSIGNED": 4,
        "BIGINT": 8,
        "BIGINT UNSIGNED": 8,
        "FLOAT": 4,
        "DOUBLE": 8,
        "DATE": 16,
        "TIME(6)": 32,
        "DATETIME(6)": 32,
        "TIMESTAMP(6)": 32,
    }
    if upper in fixed:
        return fixed[upper] + 16
    bit = re.fullmatch(r"BIT\((\d+)\)", upper)
    if bit is not None:
        return (int(bit.group(1)) + 7) // 8 + 16
    decimal = re.fullmatch(r"DECIMAL\((\d+),(\d+)\)", upper)
    if decimal is not None:
        return int(decimal.group(1)) // 2 + 24
    return None


def _safe_connector_fetch_size(table: TableCatalog, settings: RepositoryServiceSettings) -> int:
    widths = [_column_max_bytes(column.sql_type) for column in table.columns]
    if any(width is None for width in widths):
        return 1
    row_width = max(1, sum(width for width in widths if width is not None))
    return max(
        1,
        min(
            settings.connector_fetch_row_bound,
            settings.record_batch_bytes // row_width,
        ),
    )


def _empty_plateau_peaks() -> dict[str, dict[str, int | None]]:
    return {
        subject: {
            "first_10pct": None,
            "middle_10pct": None,
            "final_10pct": None,
        }
        for subject in (
            "workflow_process_tree",
            "provider_process_tree",
            "arrow_memory_pool",
            "cgroup",
        )
    }


def _iter_fixture_sql(path: Path) -> Iterator[str]:
    """Frame trusted deterministic probe statements without loading the file."""

    buffer: list[str] = []
    quote: str | None = None
    escaped = False
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            for character in line:
                buffer.append(character)
                if escaped:
                    escaped = False
                    continue
                if character == "\\" and quote is not None:
                    escaped = True
                    continue
                if character in {"'", '"', "`"}:
                    if quote == character:
                        quote = None
                    elif quote is None:
                        quote = character
                elif character == ";" and quote is None:
                    statement = "".join(buffer).strip()
                    if statement:
                        yield statement
                    buffer.clear()
    trailing = "".join(buffer).strip()
    if trailing:
        yield trailing


class OfflineCliProvider:
    def __init__(
        self,
        settings: RepositoryServiceSettings,
        layout: ProbeLayout,
        repository: Path,
        runner: DoltRunner,
    ) -> None:
        self.settings = settings
        self.layout = layout
        self.repository = repository
        self.runner = runner
        self.query_directory = layout.staging_artifacts
        self.last_stream_peak_rss_kib = 0
        self.last_stream_rss_delta_kib = 0
        self.last_stream_metrics: dict[str, Any] = {}
        self.cgroup = (
            CgroupMemoryTracker(settings.cgroup_root)
            if settings.cgroup_root is not None
            else None
        )
        self.last_plateau_peaks = _empty_plateau_peaks()
        self.last_plateau_peaks_absolute = _empty_plateau_peaks()

    def initialize_repository(self) -> None:
        self._run(
            "init",
            [
                "init",
                f"--name={self.settings.author_name}",
                f"--email={self.settings.author_email}",
                "--initial-branch=main",
            ],
            self.settings.metadata_timeout_seconds,
        )

    def open(self) -> None:
        return

    def replay(self, replay_sql: Path) -> None:
        self._run(
            "replay",
            ["sql", "--result-format=csv"],
            self.settings.import_timeout_seconds,
            stdin_path=replay_sql,
        )

    def commit_marker(self, marker: str) -> str:
        self._run("stage", ["add", "--all"], self.settings.metadata_timeout_seconds)
        self._run(
            "operation_marker_commit",
            ["commit", "--message", marker, f"--author={self.settings.author}"],
            self.settings.import_timeout_seconds,
        )
        return self.head()

    def head(self) -> str:
        rows = self._query_json("head", "SELECT HASHOF('main') AS commit_id;\n")
        if not rows:
            raise ProviderError("Dolt did not return main hash")
        return str(_value(rows[0], "commit_id", 0))

    def catalog(self, base_commit_id: str, target_commit_id: str) -> tuple[TableCatalog, ...]:
        diff_sql = (
            "SELECT * FROM dolt_schema_diff("
            f"{_commit_literal(base_commit_id)}, {_commit_literal(target_commit_id)});\n"
        )
        diff = self._query_json("catalog_schema_diff", diff_sql)
        counts: dict[str, int] = {}
        ddl_tables = [
            _parse_create_statement(str(_value(row, "to_create_statement")), 0).name
            for row in diff
            if row.get("to_create_statement") not in (None, "")
        ]
        for table in ddl_tables:
            count_rows = self._query_json(
                "catalog_count",
                f"SELECT COUNT(*) AS row_count FROM {quote_identifier(table)} AS OF {_commit_literal(target_commit_id)};\n",
            )
            counts[table] = int(_value(count_rows[0], "row_count", 0))
        return _catalog_from_schema_diff(diff, counts)

    def stream_table(
        self,
        commit_id: str,
        table: TableCatalog,
        policy: UnknownTypePolicy,
    ) -> Iterator[pa.RecordBatch]:
        self.last_stream_metrics = {}
        self.last_plateau_peaks = _empty_plateau_peaks()
        select_list, expected_header = _tagged_select_list(table)
        for column in table.columns:
            arrow_type(column.sql_type, policy)
        query = _write_query(
            self.query_directory,
            f"SELECT {select_list} FROM {quote_identifier(table.name)} AS OF '{commit_id}';\n",
        )
        stream: ProcessStream | None = None
        baseline_cgroup = self.cgroup.snapshot() if self.cgroup is not None else None
        baseline_arrow = pa.default_memory_pool().bytes_allocated()
        peak_arrow = baseline_arrow
        baseline_workflow = process_tree_rss_kib(os.getpid())
        workflow_peak = baseline_workflow
        sampler: MemorySampler | None = None
        rows_seen = 0
        oversized_single_row = False
        oversized_row_bytes: int | None = None
        old_field_limit = csv.field_size_limit()
        try:
            stream = self.runner.stream(
                "row_stream",
                ["sql", "--result-format=csv", "--binary-as-hex"],
                cwd=self.repository,
                timeout=self.settings.import_timeout_seconds,
                stdin_path=query,
            )
            baseline_provider = process_tree_rss_kib(stream.process.pid)
            sampler = MemorySampler(
                os.getpid(),
                lambda: stream.process.pid if stream is not None else None,
                self.cgroup,
                self.settings.memory_sample_interval_seconds,
                baselines={
                    "workflow_process_tree": workflow_peak,
                    "provider_process_tree": baseline_provider,
                    "arrow_memory_pool": baseline_arrow,
                    "cgroup": baseline_cgroup.current_bytes if baseline_cgroup else None,
                },
            )
            sampler.start()
            sampler.set_active(("first_10pct",))
            csv.field_size_limit(self.settings.max_stream_line_bytes)
            reader = csv.reader((line.decode("utf-8") for line in stream), strict=True)
            header = next(reader, None)
            if header is None:
                return
            if header != expected_header:
                raise ProviderError("tagged CSV header mismatch")
            rows: list[tuple[Any, ...]] = []
            rows_bytes = 0

            def emit(chunk: list[tuple[Any, ...]]) -> pa.RecordBatch:
                nonlocal rows_seen, peak_arrow, workflow_peak
                start = rows_seen
                end = rows_seen + len(chunk)
                windows = windows_for_interval(start, end, table.row_count)
                sampler.set_active(windows)
                sampler.sample(windows)
                batch = record_batch(table, chunk, policy)
                peak_arrow = max(peak_arrow, pa.default_memory_pool().bytes_allocated())
                workflow_peak = max(workflow_peak, process_tree_rss_kib(os.getpid()))
                sampler.sample(windows)
                rows_seen = end
                return batch

            for row in reader:
                parsed = _parse_tagged_row(row, table)
                parsed_bytes = _row_bytes(parsed)
                if rows and (
                    len(rows) >= self.settings.record_batch_rows
                    or rows_bytes + parsed_bytes > self.settings.record_batch_bytes
                ):
                    yield emit(rows)
                    sampler.sample()
                    rows = []
                    rows_bytes = 0
                if parsed_bytes > self.settings.record_batch_bytes:
                    oversized_single_row = True
                    oversized_row_bytes = max(oversized_row_bytes or 0, parsed_bytes)
                    yield emit([parsed])
                    sampler.sample()
                else:
                    rows.append(parsed)
                    rows_bytes += parsed_bytes
                    sampler.sample(windows_for_interval(rows_seen, rows_seen + 1, table.row_count))
            if rows:
                yield emit(rows)
            result = stream.close()
            self.last_stream_peak_rss_kib = max(
                self.last_stream_peak_rss_kib, stream.peak_rss_kib
            )
            self.last_stream_rss_delta_kib = max(
                self.last_stream_rss_delta_kib,
                max(0, stream.peak_rss_kib - stream.start_rss_kib),
            )
            final_cgroup = self.cgroup.snapshot() if self.cgroup is not None else None
            plateau = sampler.stop() if sampler is not None else _empty_plateau_peaks()
            self.last_plateau_peaks = plateau
            self.last_plateau_peaks_absolute = (
                sampler.absolute_peaks() if sampler is not None else _empty_plateau_peaks()
            )
            self.last_stream_metrics = {
                "workflow_process_tree_rss_kib": workflow_peak,
                "provider_process_tree_rss_kib": stream.peak_rss_kib,
                "arrow_memory_pool_peak_bytes": peak_arrow,
                "arrow_memory_pool_baseline_bytes": baseline_arrow,
                "cgroup_current_bytes": final_cgroup.current_bytes if final_cgroup else None,
                "cgroup_peak_bytes": final_cgroup.peak_bytes if final_cgroup else None,
                "cgroup_baseline_peak_bytes": baseline_cgroup.peak_bytes if baseline_cgroup else None,
                "cgroup_reset_current_baseline_bytes": final_cgroup.reset_current_baseline_bytes if final_cgroup else None,
                "cgroup_stat_anon_bytes": final_cgroup.anon_bytes if final_cgroup else None,
                "cgroup_stat_file_bytes": final_cgroup.file_bytes if final_cgroup else None,
                "cgroup_baseline_stat_anon_bytes": (
                    baseline_cgroup.baseline_anon_bytes if baseline_cgroup else None
                ),
                "cgroup_baseline_stat_file_bytes": (
                    baseline_cgroup.baseline_file_bytes if baseline_cgroup else None
                ),
                "cgroup_stat_anon_delta_bytes": (
                    final_cgroup.anon_delta_bytes if final_cgroup else None
                ),
                "cgroup_stat_file_delta_bytes": (
                    final_cgroup.file_delta_bytes if final_cgroup else None
                ),
                "cgroup_scope_identity": (
                    final_cgroup.scope_identity if final_cgroup else None
                ),
                "cgroup_baseline_current_bytes": baseline_cgroup.current_bytes if baseline_cgroup else None,
                "cgroup_per_workflow": final_cgroup.per_workflow if final_cgroup else False,
                "plateau_peaks": plateau,
                "plateau_peaks_absolute": self.last_plateau_peaks_absolute,
                "baseline_workflow_process_tree_rss_kib": baseline_workflow,
                "baseline_provider_process_tree_rss_kib": baseline_provider,
                "baseline_arrow_memory_pool_bytes": baseline_arrow,
                "oversized_single_row": oversized_single_row,
                "oversized_row_bytes": oversized_row_bytes,
                "byte_bound_reason": "single_indivisible_row" if oversized_single_row else None,
            }
            if result.exit_code != 0:
                raise ProviderError("Dolt row stream failed")
        finally:
            csv.field_size_limit(old_field_limit)
            if sampler is not None and not self.last_stream_metrics:
                plateau = sampler.stop()
                self.last_plateau_peaks = plateau
                self.last_plateau_peaks_absolute = sampler.absolute_peaks()
            if stream is not None:
                stream.close()
            query.unlink(missing_ok=True)

    def marker_parent(self, marker: str) -> str | None:
        rows = self._query_json(
            "marker_log",
            "SELECT commit_hash, message FROM dolt_log;\n",
        )
        matching = [index for index, row in enumerate(rows) if _value(row, "message", 1) == marker]
        if len(matching) != 1:
            return None
        index = matching[0]
        if index + 1 >= len(rows):
            return None
        return str(_value(rows[index + 1], "commit_hash", 0))

    def marker_count(self, marker: str) -> int:
        rows = self._query_json("marker_log", "SELECT message FROM dolt_log;\n")
        return sum(1 for row in rows if _value(row, "message", 0) == marker)

    def close(self) -> None:
        if self.cgroup is not None:
            self.cgroup.close()
        return

    def _query_json(self, kind: str, sql: str, revision: str | None = None) -> list[dict[str, Any]]:
        query = _write_query(self.query_directory, sql)
        args = [] if revision is None else [f"--branch={revision}"]
        args.extend(["sql", "--result-format=json"])
        try:
            result = self._run(kind, args, self.settings.metadata_timeout_seconds, stdin_path=query)
            try:
                return _json_rows(json.loads(result.stdout.decode("utf-8")))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ProviderError("Dolt metadata was not valid JSON") from exc
        finally:
            query.unlink(missing_ok=True)

    def _run(
        self,
        kind: str,
        args: list[str],
        timeout: float,
        *,
        stdin_path: Path | None = None,
    ) -> Any:
        result = self.runner.run(
            kind,
            args,
            cwd=self.repository,
            timeout=timeout,
            stdin_path=stdin_path,
            capture_stdout=True,
        )
        if result.timed_out or result.exit_code != 0:
            raise ProviderError(f"Dolt command failed: {kind}")
        return result


T = TypeVar("T")


class _AsyncLoop:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def call(self, coroutine: Coroutine[Any, Any, T]) -> T:
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        return future.result()

    def close(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5.0)
        self.loop.close()


class SqlServerProvider:
    def __init__(
        self,
        settings: RepositoryServiceSettings,
        layout: ProbeLayout,
        repository: Path,
        runner: DoltRunner,
    ) -> None:
        self.settings = settings
        self.layout = layout
        self.repository = repository
        self.runner = runner
        self.supervisor = ServerSupervisor(runner, layout.versioned, layout.provider / "sql-server")
        self.loop = _AsyncLoop()
        self.connection: Any = None
        self.query_directory = layout.staging_artifacts
        self.last_stream_peak_rss_kib = 0
        self.last_stream_rss_delta_kib = 0
        self.last_stream_metrics: dict[str, Any] = {}
        self.cgroup = (
            CgroupMemoryTracker(settings.cgroup_root)
            if settings.cgroup_root is not None
            else None
        )
        self.last_plateau_peaks = _empty_plateau_peaks()
        self.last_plateau_peaks_absolute = _empty_plateau_peaks()

    def open(self) -> None:
        # Initialization is a filesystem-scoped Dolt operation. All SQL mutation after
        # publication is owned by the service-owned server and one connector session.
        self.supervisor.start(self.settings.server_start_timeout_seconds)
        self.loop.call(self._connect())
        self._execute("SET GLOBAL dolt_stats_enabled = 0")
        self._execute("CALL dolt_stats_stop()")
        self._execute("CALL dolt_stats_purge()")

    async def _connect(self) -> None:
        try:
            import mysql.connector.aio as mysql_aio
        except ImportError as exc:
            raise ProviderError("mysql-connector-python aio API is unavailable") from exc
        self.connection = await mysql_aio.connect(
            unix_socket=str(self.supervisor.socket_path),
            user="root",
            database=self.repository.name,
            autocommit=True,
        )

    def replay(self, replay_sql: Path) -> None:
        self._call(self._replay(replay_sql))

    async def _replay(self, replay_sql: Path) -> None:
        cursor = await self.connection.cursor(buffered=False)
        try:
            for statement in _iter_fixture_sql(replay_sql):
                await cursor.execute(statement)
                await cursor.fetchall()
        finally:
            await cursor.close()

    def commit_marker(self, marker: str) -> str:
        self._execute("CALL DOLT_ADD('-A')")
        rows = self._execute(
            "CALL DOLT_COMMIT('-m', %s, '--author', %s)",
            (marker, self.settings.author),
        )
        if not rows:
            raise ProviderError("DOLT_COMMIT returned no hash")
        return self.head()

    def head(self) -> str:
        rows = self._execute("SELECT HASHOF('main') AS commit_id")
        if not rows:
            raise ProviderError("sql-server did not return main hash")
        return str(_value(rows[0], "commit_id", 0))

    def catalog(self, base_commit_id: str, target_commit_id: str) -> tuple[TableCatalog, ...]:
        diff_sql = (
            "SELECT * FROM dolt_schema_diff("
            f"{_commit_literal(base_commit_id)}, {_commit_literal(target_commit_id)})"
        )
        diff = self._execute(diff_sql)
        counts: dict[str, int] = {}
        ddl_tables = [
            _parse_create_statement(str(_value(row, "to_create_statement")), 0).name
            for row in diff
            if row.get("to_create_statement") not in (None, "")
        ]
        for table in ddl_tables:
            count_rows = self._execute(
                f"SELECT COUNT(*) AS row_count FROM {quote_identifier(table)} AS OF {_commit_literal(target_commit_id)}"
            )
            counts[table] = int(_value(count_rows[0], "row_count", 0))
        return _catalog_from_schema_diff(diff, counts)

    def stream_table(
        self,
        commit_id: str,
        table: TableCatalog,
        policy: UnknownTypePolicy,
    ) -> Iterator[pa.RecordBatch]:
        self.last_stream_metrics = {}
        self.last_plateau_peaks = _empty_plateau_peaks()
        baseline_rss = (
            process_tree_rss_kib(self.supervisor.process.pid)
            if self.supervisor.process is not None
            else 0
        )
        baseline_arrow = pa.default_memory_pool().bytes_allocated()
        baseline_cgroup = self.cgroup.snapshot() if self.cgroup is not None else None
        baseline_workflow = process_tree_rss_kib(os.getpid())
        workflow_peak = baseline_workflow
        sampler: MemorySampler | None = None
        cursor: Any = None
        peak_rss = baseline_rss
        peak_arrow = baseline_arrow
        peak_cgroup = baseline_cgroup.peak_bytes if baseline_cgroup and baseline_cgroup.peak_bytes else 0
        batch_index = 0
        exhausted = False
        rows_seen = 0
        oversized_single_row = False
        oversized_row_bytes: int | None = None
        max_fetched_payload_bytes = 0
        try:
            sampler = MemorySampler(
                os.getpid(),
                lambda: self.supervisor.process.pid if self.supervisor.process is not None else None,
                self.cgroup,
                self.settings.memory_sample_interval_seconds,
                baselines={
                    "workflow_process_tree": workflow_peak,
                    "provider_process_tree": baseline_rss,
                    "arrow_memory_pool": baseline_arrow,
                    "cgroup": baseline_cgroup.current_bytes if baseline_cgroup else None,
                },
            )
            sampler.start()
            sampler.set_active(("first_10pct",))
            # Fetch a small, explicit connector bound. The splitter consumes
            # the returned rows immediately and never materializes a
            # row-bound-sized pending result.
            fetch_size = _safe_connector_fetch_size(table, self.settings)
            cursor = self._call(self._open_cursor(table.name, commit_id))
            pending: list[tuple[Any, ...]] = []
            pending_bytes = 0

            def emit(chunk: list[tuple[Any, ...]]) -> pa.RecordBatch:
                nonlocal rows_seen, peak_arrow, workflow_peak, peak_rss, peak_cgroup, batch_index
                start = rows_seen
                end = rows_seen + len(chunk)
                windows = windows_for_interval(start, end, table.row_count)
                sampler.set_active(windows)
                sampler.sample(windows)
                if self.supervisor.process is not None:
                    peak_rss = max(peak_rss, process_tree_rss_kib(self.supervisor.process.pid))
                batch = record_batch(table, chunk, policy)
                batch_index += 1
                workflow_peak = max(workflow_peak, process_tree_rss_kib(os.getpid()))
                peak_arrow = max(peak_arrow, pa.default_memory_pool().bytes_allocated())
                if self.cgroup is not None:
                    current = self.cgroup.snapshot()
                    peak_cgroup = max(peak_cgroup, current.peak_bytes or 0)
                sampler.sample(windows)
                rows_seen = end
                return batch

            while True:
                sampler.sample()
                rows = self._call(cursor.fetchmany(fetch_size))
                sampler.sample()
                if not rows:
                    exhausted = True
                    break
                fetched_payload = 0
                for raw_candidate in rows:
                    candidate = tuple(raw_candidate)
                    candidate_bytes = _row_bytes(candidate)
                    fetched_payload += candidate_bytes
                    max_fetched_payload_bytes = max(max_fetched_payload_bytes, fetched_payload)
                    if pending and (
                        len(pending) >= self.settings.record_batch_rows
                        or pending_bytes + candidate_bytes > self.settings.record_batch_bytes
                    ):
                        yield emit(pending)
                        sampler.sample()
                        pending = []
                        pending_bytes = 0
                    if candidate_bytes > self.settings.record_batch_bytes:
                        oversized_single_row = True
                        oversized_row_bytes = max(oversized_row_bytes or 0, candidate_bytes)
                        yield emit([candidate])
                        sampler.sample()
                    else:
                        pending.append(candidate)
                        pending_bytes += candidate_bytes
                        sampler.sample(
                            windows_for_interval(rows_seen, rows_seen + 1, table.row_count)
                        )
            if pending:
                yield emit(pending)
        finally:
            self.last_stream_peak_rss_kib = max(self.last_stream_peak_rss_kib, peak_rss)
            self.last_stream_rss_delta_kib = max(
                self.last_stream_rss_delta_kib, max(0, peak_rss - baseline_rss)
            )
            reset = not exhausted
            if cursor is not None:
                try:
                    self._call(cursor.close())
                except Exception:
                    reset = True
            if reset:
                self._reset_connection()
            final_cgroup = self.cgroup.snapshot() if self.cgroup is not None else None
            plateau = sampler.stop() if sampler is not None else _empty_plateau_peaks()
            self.last_plateau_peaks = plateau
            self.last_plateau_peaks_absolute = (
                sampler.absolute_peaks() if sampler is not None else _empty_plateau_peaks()
            )
            self.last_stream_metrics = {
                "workflow_process_tree_rss_kib": workflow_peak,
                "provider_process_tree_rss_kib": peak_rss,
                "baseline_workflow_process_tree_rss_kib": baseline_workflow,
                "baseline_provider_process_tree_rss_kib": baseline_rss,
                "arrow_memory_pool_peak_bytes": peak_arrow,
                "arrow_memory_pool_baseline_bytes": baseline_arrow,
                "cgroup_current_bytes": final_cgroup.current_bytes if final_cgroup else None,
                "cgroup_peak_bytes": peak_cgroup,
                "cgroup_reset_current_baseline_bytes": final_cgroup.reset_current_baseline_bytes if final_cgroup else None,
                "cgroup_stat_anon_bytes": final_cgroup.anon_bytes if final_cgroup else None,
                "cgroup_stat_file_bytes": final_cgroup.file_bytes if final_cgroup else None,
                "cgroup_baseline_stat_anon_bytes": (
                    baseline_cgroup.baseline_anon_bytes if baseline_cgroup else None
                ),
                "cgroup_baseline_stat_file_bytes": (
                    baseline_cgroup.baseline_file_bytes if baseline_cgroup else None
                ),
                "cgroup_stat_anon_delta_bytes": (
                    final_cgroup.anon_delta_bytes if final_cgroup else None
                ),
                "cgroup_stat_file_delta_bytes": (
                    final_cgroup.file_delta_bytes if final_cgroup else None
                ),
                "cgroup_scope_identity": (
                    final_cgroup.scope_identity if final_cgroup else None
                ),
                "cgroup_baseline_current_bytes": baseline_cgroup.current_bytes if baseline_cgroup else None,
                "cgroup_per_workflow": final_cgroup.per_workflow if final_cgroup else False,
                "cleanup_connection_reset": reset,
                "batch_count": batch_index,
                "connector_fetch_row_bound": self.settings.connector_fetch_row_bound,
                "connector_fetch_size": fetch_size,
                "connector_max_fetched_payload_bytes": max_fetched_payload_bytes,
                "connector_fetch_payload_bound_ok": max_fetched_payload_bytes <= self.settings.record_batch_bytes
                or (fetch_size == 1 and oversized_single_row),
                "plateau_peaks": plateau,
                "plateau_peaks_absolute": self.last_plateau_peaks_absolute,
                "oversized_single_row": oversized_single_row,
                "oversized_row_bytes": oversized_row_bytes,
                "byte_bound_reason": "single_indivisible_row" if oversized_single_row else None,
            }

    async def _open_cursor(self, table: str, commit_id: str) -> Any:
        cursor = await self.connection.cursor(buffered=False)
        await cursor.execute(f"SELECT * FROM {quote_identifier(table)} AS OF '{commit_id}'")
        return cursor

    async def _reset_connection_async(self) -> None:
        if self.connection is not None:
            try:
                await self.connection.close()
            except Exception:
                pass
        self.connection = None
        await self._connect()

    def _reset_connection(self) -> None:
        self._call(self._reset_connection_async())

    def marker_parent(self, marker: str) -> str | None:
        rows = self._execute("SELECT commit_hash, message FROM dolt_log")
        matching = [index for index, row in enumerate(rows) if _value(row, "message", 1) == marker]
        if len(matching) != 1 or matching[0] + 1 >= len(rows):
            return None
        return str(_value(rows[matching[0] + 1], "commit_hash", 0))

    def marker_count(self, marker: str) -> int:
        rows = self._execute("SELECT message FROM dolt_log")
        return sum(1 for row in rows if _value(row, "message", 0) == marker)

    def close(self) -> None:
        if self.connection is not None:
            try:
                self._call(self.connection.close())
            finally:
                self.connection = None
        self.supervisor.stop()
        if self.cgroup is not None:
            self.cgroup.close()
        self.loop.close()

    def _execute(self, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        return self._call(self._execute_async(sql, params))

    async def _execute_async(
        self, sql: str, params: tuple[Any, ...] | None
    ) -> list[dict[str, Any]]:
        cursor = await self.connection.cursor(buffered=False)
        try:
            await cursor.execute(sql, params)
            rows = await cursor.fetchall()
            description = cursor.description or []
            names = [str(item[0]) for item in description]
            return [
                {name: value for name, value in zip(names, row, strict=False)} for row in rows
            ]
        finally:
            await cursor.close()

    def _call(self, coroutine: Coroutine[Any, Any, T]) -> T:
        try:
            return self.loop.call(coroutine)
        except Exception as exc:
            raise ProviderError(f"sql-server operation failed: {type(exc).__name__}") from exc
