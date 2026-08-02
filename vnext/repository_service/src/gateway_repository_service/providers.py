"""Private Candidate A/B Dolt providers used by the P2-R1 feasibility probe."""

from __future__ import annotations

import asyncio
import csv
import json
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
from gateway_repository_service.process import DoltRunner, ProcessStream, ServerSupervisor, process_rss_kib
from gateway_repository_service.settings import RepositoryServiceSettings


class ProviderError(RuntimeError):
    """Provider execution or correctness failure."""


class Provider(Protocol):
    repository: Path

    def open(self) -> None: ...

    def replay(self, replay_sql: Path) -> None: ...

    def commit_marker(self, marker: str) -> str: ...

    def head(self) -> str: ...

    def catalog(self, commit_id: str) -> tuple[TableCatalog, ...]: ...

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


def _parse_catalog_rows(
    column_rows: list[dict[str, Any]],
    key_rows: list[dict[str, Any]],
    counts: dict[str, int],
) -> tuple[TableCatalog, ...]:
    key_positions = {
        (str(_value(row, "TABLE_NAME")), str(_value(row, "COLUMN_NAME"))): int(
            _value(row, "ORDINAL_POSITION")
        )
        for row in key_rows
    }
    by_table: dict[str, list[ColumnCatalog]] = {}
    for row in column_rows:
        table = str(_value(row, "TABLE_NAME"))
        column = str(_value(row, "COLUMN_NAME"))
        nullable = str(_value(row, "IS_NULLABLE")).upper() == "YES"
        sql_type = normalize_sql_type(
            str(_value(row, "DATA_TYPE")), str(_value(row, "COLUMN_TYPE"))
        )
        by_table.setdefault(table, []).append(
            ColumnCatalog(column, sql_type, nullable, key_positions.get((table, column)))
        )
    tables = [
        TableCatalog(name, tuple(columns), counts.get(name, 0))
        for name, columns in sorted(by_table.items())
    ]
    return tuple(tables)


def _catalog_sql() -> tuple[str, str]:
    columns = """
SELECT TABLE_NAME, COLUMN_NAME, IS_NULLABLE, DATA_TYPE, COLUMN_TYPE, ORDINAL_POSITION
FROM information_schema.columns
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, ORDINAL_POSITION
"""
    keys = """
SELECT TABLE_NAME, COLUMN_NAME, ORDINAL_POSITION
FROM information_schema.key_column_usage
WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'PRIMARY'
ORDER BY TABLE_NAME, ORDINAL_POSITION
"""
    return columns.strip() + "\n", keys.strip() + "\n"


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
        self._run(
            "initial_commit",
            [
                "commit",
                "--allow-empty",
                "--message=gateway-versioned-initial",
                f"--author={self.settings.author}",
            ],
            self.settings.metadata_timeout_seconds,
        )

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

    def catalog(self, commit_id: str) -> tuple[TableCatalog, ...]:
        columns_sql, keys_sql = _catalog_sql()
        columns = self._query_json("catalog_columns", columns_sql)
        keys = self._query_json("catalog_keys", keys_sql)
        counts: dict[str, int] = {}
        for row in columns:
            table = str(_value(row, "TABLE_NAME"))
            if table in counts:
                continue
            count_rows = self._query_json(
                "catalog_count",
                f"SELECT COUNT(*) AS row_count FROM {quote_identifier(table)} AS OF '{commit_id}';\n",
            )
            counts[table] = int(_value(count_rows[0], "row_count", 0))
        return _parse_catalog_rows(columns, keys, counts)

    def stream_table(
        self,
        commit_id: str,
        table: TableCatalog,
        policy: UnknownTypePolicy,
    ) -> Iterator[pa.RecordBatch]:
        select_list = ", ".join(
            (
                f"HEX({quote_identifier(column.name)}) AS {quote_identifier(column.name)}"
                if arrow_type(column.sql_type, UnknownTypePolicy.STRINGIFY)[0] == pa.binary()
                else quote_identifier(column.name)
            )
            for column in table.columns
        )
        query = _write_query(
            self.query_directory,
            f"SELECT {select_list} FROM {quote_identifier(table.name)} AS OF '{commit_id}';\n",
        )
        stream: ProcessStream | None = None
        try:
            stream = self.runner.stream(
                "row_stream",
                ["sql", "--result-format=csv", "--binary-as-hex"],
                cwd=self.repository,
                timeout=self.settings.import_timeout_seconds,
                stdin_path=query,
            )
            reader = csv.reader((line.decode("utf-8") for line in stream))
            header = next(reader, None)
            if header is None:
                return
            rows: list[tuple[Any, ...]] = []
            for row in reader:
                rows.append(tuple(None if value in {"", "NULL", "\\N"} else value for value in row))
                if len(rows) >= self.settings.record_batch_rows:
                    yield record_batch(table, rows, policy)
                    rows = []
            if rows:
                yield record_batch(table, rows, policy)
            result = stream.close()
            self.last_stream_peak_rss_kib = max(
                self.last_stream_peak_rss_kib, stream.peak_rss_kib
            )
            self.last_stream_rss_delta_kib = max(
                self.last_stream_rss_delta_kib,
                max(0, stream.peak_rss_kib - stream.start_rss_kib),
            )
            if result.exit_code != 0:
                raise ProviderError("Dolt row stream failed")
        finally:
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

    def catalog(self, commit_id: str) -> tuple[TableCatalog, ...]:
        columns_sql, keys_sql = _catalog_sql()
        columns = self._execute(columns_sql)
        keys = self._execute(keys_sql)
        counts: dict[str, int] = {}
        for row in columns:
            table = str(_value(row, "TABLE_NAME"))
            if table not in counts:
                count_rows = self._execute(
                    f"SELECT COUNT(*) AS row_count FROM {quote_identifier(table)} AS OF '{commit_id}'"
                )
                counts[table] = int(_value(count_rows[0], "row_count", 0))
        return _parse_catalog_rows(columns, keys, counts)

    def stream_table(
        self,
        commit_id: str,
        table: TableCatalog,
        policy: UnknownTypePolicy,
    ) -> Iterator[pa.RecordBatch]:
        cursor = self._call(self._open_cursor(table.name, commit_id))
        baseline_rss = (
            process_rss_kib(self.supervisor.process.pid)
            if self.supervisor.process is not None
            else 0
        )
        peak_rss = baseline_rss
        try:
            while True:
                rows = self._call(cursor.fetchmany(self.settings.record_batch_rows))
                if not rows:
                    break
                if self.supervisor.process is not None:
                    peak_rss = max(peak_rss, process_rss_kib(self.supervisor.process.pid))
                yield record_batch(table, [tuple(row) for row in rows], policy)
        finally:
            self.last_stream_peak_rss_kib = max(self.last_stream_peak_rss_kib, peak_rss)
            self.last_stream_rss_delta_kib = max(
                self.last_stream_rss_delta_kib, max(0, peak_rss - baseline_rss)
            )
            self._call(self._drain_and_close_cursor(cursor))

    async def _open_cursor(self, table: str, commit_id: str) -> Any:
        cursor = await self.connection.cursor(buffered=False)
        await cursor.execute(f"SELECT * FROM {quote_identifier(table)} AS OF '{commit_id}'")
        return cursor

    async def _drain_and_close_cursor(self, cursor: Any) -> None:
        while await cursor.fetchmany(self.settings.record_batch_rows):
            pass
        await cursor.close()

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
