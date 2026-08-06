"""Candidate A Dolt CLI primitives shared by probe and production import paths."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_service.arrow_mapping import (
    TableCatalog,
    UnknownTypePolicy,
    arrow_type,
    normalize_rows,
    record_batch,
)
from gateway_repository_service.candidate_a.ref_validation import commit_literal, validate_commit_id
from gateway_repository_service.candidate_a.sql import (
    _catalog_from_schema_diff,
    _metric_int,
    _observe_batch_metrics,
    _parse_create_statement,
    _parse_tagged_row,
    _row_bytes,
    _tagged_select_list,
    quote_identifier,
)
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.process import CommandResult, DoltRunner, ProcessStream
from gateway_repository_service.settings import RepositoryServiceSettings


class DoltCliError(RuntimeError):
    """Candidate A Dolt CLI execution failure."""


def write_query(directory: Path, sql: str) -> Path:
    path = directory / f"query-{uuid4().hex}.sql"
    path.write_text(sql, encoding="utf-8")
    return path


def json_rows(payload: Any) -> list[dict[str, Any]]:
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
                raise DoltCliError("Dolt JSON rows was not a list")
            return [
                {name: cell for name, cell in zip(names, row, strict=False)}
                for row in raw_rows
                if isinstance(row, list)
            ]
        for key in ("rows", "rowData", "data"):
            if key in payload:
                return json_rows(payload[key])
        return [payload]
    if not isinstance(payload, list):
        raise DoltCliError("Dolt JSON result was not a row list")
    rows: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            rows.append(item)
        elif isinstance(item, list):
            rows.append({str(index): cell for index, cell in enumerate(item)})
        else:
            raise DoltCliError("Dolt JSON row was not an object")
    return rows


def value(row: dict[str, Any], name: str, index: int | None = None) -> Any:
    if name in row:
        return row[name]
    lowered = {key.lower(): value for key, value in row.items()}
    if name.lower() in lowered:
        return lowered[name.lower()]
    if index is not None and str(index) in row:
        return row[str(index)]
    raise DoltCliError(f"missing result column {name}")


class CandidateADoltCli:
    """Narrow Candidate A offline CLI session without probe measurement wrappers."""

    def __init__(
        self,
        settings: RepositoryServiceSettings,
        layout: DurableLayout,
        repository: Path,
        runner: DoltRunner,
    ) -> None:
        self.settings = settings
        self.layout = layout
        self.repository = repository
        self.runner = runner
        self.query_directory = layout.staging_artifacts

    def replay(self, replay_sql: Path) -> None:
        self.run_cli(
            "replay",
            ["sql", "--result-format=csv"],
            self.settings.import_timeout_seconds,
            stdin_path=replay_sql,
        )

    def catalog(self, base_commit_id: str, target_commit_id: str) -> tuple[TableCatalog, ...]:
        safe_base = validate_commit_id(base_commit_id)
        safe_target = validate_commit_id(target_commit_id)
        diff_sql = (
            "SELECT * FROM dolt_schema_diff("
            f"{commit_literal(safe_base)}, {commit_literal(safe_target)});\n"
        )
        diff = self.query_json("catalog_schema_diff", diff_sql)
        counts: dict[str, int] = {}
        ddl_tables = [
            _parse_create_statement(str(value(row, "to_create_statement")), 0).name
            for row in diff
            if row.get("to_create_statement") not in (None, "")
        ]
        for table in ddl_tables:
            count_rows = self.query_json(
                "catalog_count",
                f"SELECT COUNT(*) AS row_count FROM {quote_identifier(table)} AS OF {commit_literal(safe_target)};\n",
            )
            counts[table] = int(value(count_rows[0], "row_count", 0))
        return _catalog_from_schema_diff(diff, counts)

    def stream_table(
        self,
        commit_id: str,
        table: TableCatalog,
        policy: UnknownTypePolicy,
    ) -> Iterator[pa.RecordBatch]:
        safe_commit_id = validate_commit_id(commit_id)
        select_list, expected_header = _tagged_select_list(table)
        for column in table.columns:
            arrow_type(column.sql_type, policy)
        query = write_query(
            self.query_directory,
            f"SELECT {select_list} FROM {quote_identifier(table.name)} AS OF {commit_literal(safe_commit_id)};\n",
        )
        stream: ProcessStream | None = None
        stream_closed = False
        batch_metrics: dict[str, object] = {
            "max_encoded_line_bytes": 0,
            "encoded_line_bound_valid": True,
            "encoded_line_bound": self.settings.max_stream_line_bytes,
        }
        old_field_limit = csv.field_size_limit()
        try:
            stream = self.runner.stream(
                "row_stream",
                ["sql", "--result-format=csv", "--binary-as-hex"],
                cwd=self.repository,
                timeout=self.settings.import_timeout_seconds,
                stdin_path=query,
            )
            csv.field_size_limit(self.settings.max_stream_line_bytes)

            def decode_line(line: bytes) -> str:
                line_bytes = len(line)
                batch_metrics["max_encoded_line_bytes"] = max(
                    _metric_int(batch_metrics, "max_encoded_line_bytes"),
                    line_bytes,
                )
                if line_bytes > self.settings.max_stream_line_bytes:
                    batch_metrics["encoded_line_bound_valid"] = False
                    raise DoltCliError("tagged CSV encoded line exceeded safety bound")
                return line.decode("utf-8")

            reader = csv.reader((decode_line(line) for line in stream), strict=True)
            header = next(reader, None)
            if header is None:
                result = stream.close()
                stream_closed = True
                if result.exit_code != 0 or result.timed_out:
                    raise DoltCliError("Dolt row stream failed")
                return
            if header != expected_header:
                raise DoltCliError("tagged CSV header mismatch")
            rows: list[tuple[Any, ...]] = []
            rows_bytes = 0

            def emit(chunk: list[tuple[Any, ...]]) -> pa.RecordBatch:
                batch = record_batch(table, chunk, policy)
                _observe_batch_metrics(
                    batch_metrics,
                    chunk,
                    row_bound=self.settings.record_batch_rows,
                    byte_bound=self.settings.record_batch_bytes,
                )
                return batch

            for row in reader:
                parsed = _parse_tagged_row(row, table)
                normalized = normalize_rows(table, [parsed], policy)[0]
                parsed_bytes = _row_bytes(normalized)
                if rows and (
                    len(rows) >= self.settings.record_batch_rows
                    or rows_bytes + parsed_bytes > self.settings.record_batch_bytes
                ):
                    yield emit(rows)
                    rows = []
                    rows_bytes = 0
                if parsed_bytes > self.settings.record_batch_bytes:
                    yield emit([normalized])
                else:
                    rows.append(normalized)
                    rows_bytes += parsed_bytes
            if rows:
                yield emit(rows)
            result = stream.close()
            stream_closed = True
            if result.exit_code != 0 or result.timed_out:
                raise DoltCliError("Dolt row stream failed")
        finally:
            csv.field_size_limit(old_field_limit)
            if stream is not None and not stream_closed:
                stream.close()
            query.unlink(missing_ok=True)

    def query_json(
        self,
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
    ) -> list[dict[str, Any]]:
        query = write_query(self.query_directory, sql)
        args: list[str] = []
        if revision is not None:
            args.append(f"--branch={revision}")
        args.extend(["sql", "--result-format=json"])
        try:
            result = self.run_cli(
                kind,
                args,
                self.settings.metadata_timeout_seconds,
                stdin_path=query,
            )
            try:
                return json_rows(json.loads(result.stdout.decode("utf-8")))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise DoltCliError("Dolt metadata was not valid JSON") from exc
        finally:
            query.unlink(missing_ok=True)

    def run_cli(
        self,
        kind: str,
        args: list[str],
        timeout: float,
        *,
        stdin_path: Path | None = None,
    ) -> CommandResult:
        result = self.runner.run(
            kind,
            args,
            cwd=self.repository,
            timeout=timeout,
            stdin_path=stdin_path,
            capture_stdout=True,
        )
        if result.timed_out or result.exit_code != 0:
            raise DoltCliError(f"Dolt command failed: {kind}")
        return result
