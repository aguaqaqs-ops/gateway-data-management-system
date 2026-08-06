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
from gateway_repository_service.candidate_a.errors import CandidateAError
from gateway_repository_service.candidate_a.ref_validation import commit_literal, validate_commit_id
from gateway_repository_service.candidate_a.sql import (
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


class DoltCliError(CandidateAError):
    """Candidate A Dolt CLI execution failure."""


def write_query(directory: Path, sql: str) -> Path:
    path = directory / f"query-{uuid4().hex}.sql"
    path.write_text(sql, encoding="utf-8")
    return path


def json_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if "rows" in payload and "columns" in payload:
            columns = payload["columns"]
            if not isinstance(columns, list):
                raise DoltCliError("Dolt JSON columns was not a list")
            names: list[str] = []
            for column in columns:
                if isinstance(column, dict):
                    name = column.get("name", column.get("Name"))
                else:
                    name = column
                if not isinstance(name, str) or not name.strip():
                    raise DoltCliError("Dolt JSON column name is missing or empty")
                names.append(name.strip())
            if len(names) != len(set(names)):
                raise DoltCliError("Dolt JSON column names are not unique")
            raw_rows = payload["rows"]
            if not isinstance(raw_rows, list):
                raise DoltCliError("Dolt JSON rows was not a list")
            parsed: list[dict[str, Any]] = []
            for row in raw_rows:
                if not isinstance(row, list):
                    raise DoltCliError("Dolt JSON row was not a list")
                if len(row) != len(names):
                    raise DoltCliError("Dolt JSON row width does not match columns")
                parsed.append({name: cell for name, cell in zip(names, row, strict=True)})
            return parsed
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
            raise DoltCliError("Dolt JSON row was not an object")
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


def _create_statement_from_show_row(row: dict[str, Any]) -> str:
    for key, cell in row.items():
        if key.lower().replace(" ", "") == "createtable":
            return str(cell)
    raise DoltCliError("SHOW CREATE TABLE did not return DDL")


_ALLOWED_SHOW_TABLE_TYPES = frozenset({"BASE TABLE", "VIEW"})


def _normalized_row_keys(row: dict[str, Any]) -> set[str]:
    return {key.lower() for key in row}


def _require_unique_row_keys(row: dict[str, Any], kind: str) -> None:
    if len(row) != len(_normalized_row_keys(row)):
        raise DoltCliError(f"Dolt {kind} row has duplicate column names")


def _require_exact_row_keys(
    row: dict[str, Any],
    expected: frozenset[str],
    kind: str,
) -> None:
    _require_unique_row_keys(row, kind)
    actual = _normalized_row_keys(row)
    if actual != expected:
        raise DoltCliError(
            f"Dolt {kind} row schema mismatch: got {sorted(actual)}, expected {sorted(expected)}"
        )


def _parse_show_tables_row(row: dict[str, Any], kind: str) -> tuple[str, str]:
    _require_unique_row_keys(row, kind)
    keys = _normalized_row_keys(row)
    if len(keys) != 2:
        raise DoltCliError(f"Dolt {kind} row schema mismatch: expected 2 columns, got {len(keys)}")
    if "table_type" not in keys:
        raise DoltCliError(f"Dolt {kind} row schema mismatch: missing Table_type")
    tables_in = [key for key in keys if key.startswith("tables_in")]
    if len(tables_in) != 1:
        raise DoltCliError(f"Dolt {kind} row schema mismatch: missing unique Tables_in_* column")
    normalized_to_original = {key.lower(): key for key in row}
    raw_type = row[normalized_to_original["table_type"]]
    if not isinstance(raw_type, str) or not raw_type.strip():
        raise DoltCliError(f"Dolt {kind} Table_type is missing or invalid")
    table_type = raw_type.strip().upper()
    if table_type not in _ALLOWED_SHOW_TABLE_TYPES:
        raise DoltCliError(f"Dolt {kind} Table_type is not recognized: {raw_type!r}")
    raw_name = row[normalized_to_original[tables_in[0]]]
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise DoltCliError(f"Dolt {kind} table name is missing or invalid")
    return raw_name.strip(), table_type


def _require_show_create_row(row: dict[str, Any], table_name: str, kind: str) -> None:
    _require_unique_row_keys(row, kind)
    keys = _normalized_row_keys(row)
    if len(keys) != 2:
        raise DoltCliError(f"Dolt {kind} row schema mismatch: expected 2 columns, got {len(keys)}")
    normalized_to_original = {key.lower().replace(" ", ""): key for key in row}
    if "table" not in normalized_to_original:
        raise DoltCliError(f"Dolt {kind} row schema mismatch: missing Table column")
    if "createtable" not in normalized_to_original:
        raise DoltCliError(f"Dolt {kind} row schema mismatch: missing Create Table column")
    actual_table = str(row[normalized_to_original["table"]])
    if actual_table != table_name:
        raise DoltCliError(f"Dolt {kind} returned mismatched table name")


_EXACT_METADATA_ROW_SCHEMAS: dict[str, frozenset[str]] = {
    "read_ref": frozenset({"commit_id"}),
    "candidate_parent": frozenset({"parents"}),
    "catalog_count": frozenset({"row_count"}),
    "refs_for_commit": frozenset({"name"}),
    "marker_scan": frozenset({"commit_hash", "message", "parents"}),
}


def _validate_metadata_rows(kind: str, rows: list[dict[str, Any]]) -> None:
    if kind in _EXACT_METADATA_ROW_SCHEMAS:
        expected = _EXACT_METADATA_ROW_SCHEMAS[kind]
        for row in rows:
            _require_exact_row_keys(row, expected, kind)
        return
    if kind == "catalog_tables":
        for row in rows:
            _parse_show_tables_row(row, kind)


def _decode_metadata_json(stdout: bytes) -> Any:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        if len(pairs) != len({key for key, _ in pairs}):
            raise DoltCliError("Dolt metadata JSON contained duplicate keys")
        return dict(pairs)

    return json.loads(stdout.decode("utf-8"), object_pairs_hook=reject_duplicate_keys)


def _require_exactly_one_row(rows: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    if len(rows) != 1:
        raise DoltCliError(f"Dolt {kind} returned {len(rows)} rows, expected 1")
    return rows[0]


def _parse_non_negative_row_count(raw: Any, kind: str) -> int:
    if isinstance(raw, bool):
        raise DoltCliError(f"invalid {kind} row_count: {raw!r}")
    if isinstance(raw, int):
        if raw < 0:
            raise DoltCliError(f"invalid {kind} row_count: {raw!r}")
        return raw
    if isinstance(raw, float):
        if raw < 0 or not raw.is_integer():
            raise DoltCliError(f"invalid {kind} row_count: {raw!r}")
        return int(raw)
    if isinstance(raw, str):
        if not raw or not raw.isdigit():
            raise DoltCliError(f"invalid {kind} row_count: {raw!r}")
        return int(raw)
    raise DoltCliError(f"invalid {kind} row_count: {raw!r}")


_csv_field_limit_applied = False


def _ensure_csv_field_limit(limit: int) -> None:
    global _csv_field_limit_applied
    if _csv_field_limit_applied:
        return
    csv.field_size_limit(max(csv.field_size_limit(), limit))
    _csv_field_limit_applied = True


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
        _ensure_csv_field_limit(settings.max_stream_line_bytes)

    def replay(self, replay_sql: Path) -> None:
        self.run_cli(
            "replay",
            ["sql", "--result-format=csv"],
            self.settings.import_timeout_seconds,
            stdin_path=replay_sql,
        )

    def catalog(self, base_commit_id: str, target_commit_id: str) -> tuple[TableCatalog, ...]:
        validate_commit_id(base_commit_id)
        safe_target = validate_commit_id(target_commit_id)
        target_literal = commit_literal(safe_target)
        show_rows = self.query_json(
            "catalog_tables",
            f"SHOW FULL TABLES AS OF {target_literal};\n",
        )
        tables: list[TableCatalog] = []
        for row in show_rows:
            table_name, table_type = _parse_show_tables_row(row, "catalog_tables")
            if table_type == "VIEW":
                continue
            create_rows = self.query_json(
                "catalog_create",
                f"SHOW CREATE TABLE {quote_identifier(table_name)} AS OF {target_literal};\n",
            )
            create_row = _require_exactly_one_row(create_rows, "catalog_create")
            _require_show_create_row(create_row, table_name, "catalog_create")
            ddl = _create_statement_from_show_row(create_row)
            count_rows = self.query_json(
                "catalog_count",
                f"SELECT COUNT(*) AS row_count FROM {quote_identifier(table_name)} AS OF {target_literal};\n",
            )
            count_row = _require_exactly_one_row(count_rows, "catalog_count")
            raw_count = value(count_row, "row_count", 0)
            row_count = _parse_non_negative_row_count(raw_count, "catalog_count")
            tables.append(_parse_create_statement(ddl, row_count))
        return tuple(sorted(tables, key=lambda table: table.name))

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
            "oversized_single_row": False,
        }
        try:
            stream = self.runner.stream(
                "row_stream",
                ["sql", "--result-format=csv", "--binary-as-hex"],
                cwd=self.repository,
                timeout=self.settings.import_timeout_seconds,
                stdin_path=query,
            )

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
                rows = json_rows(_decode_metadata_json(result.stdout))
                _validate_metadata_rows(kind, rows)
                return rows
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
