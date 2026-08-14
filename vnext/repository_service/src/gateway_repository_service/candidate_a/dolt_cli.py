"""Candidate A Dolt CLI primitives shared by probe and production import paths."""

from __future__ import annotations

import csv
import json
import threading
from collections import OrderedDict
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from uuid import uuid4

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_service.arrow_mapping import (
    CompiledTablePlan,
    NormalizedRow,
    TableCatalog,
    UnknownTypePolicy,
    accumulate_normalized_row,
    compile_table_plan,
)
from gateway_repository_service.candidate_a.errors import CandidateAError, DoltCliStreamCancelledError
from gateway_repository_service.candidate_a.ref_validation import (
    commit_literal,
    opaque_commit_literal,
    validate_commit_id,
)
from gateway_repository_service.candidate_a.sql import (
    _metric_int,
    _observe_batch_metrics,
    _parse_create_statement,
    _parse_tagged_row,
    _tagged_select_list,
    quote_identifier,
)
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.process import (
    CommandResult,
    DoltRunner,
    ProcessStream,
    StreamCancellationCheck,
    evaluate_stream_cancellation,
)
from gateway_repository_service.settings import RepositoryServiceSettings


class DoltCliError(CandidateAError):
    """Candidate A Dolt CLI execution failure."""


def write_query(directory: Path, sql: str) -> Path:
    path = directory / f"query-{uuid4().hex}.sql"
    path.write_text(sql, encoding="utf-8")
    return path


def _require_exact_envelope_keys(payload: dict[str, Any], expected: frozenset[str]) -> None:
    actual = set(payload.keys())
    if actual != expected:
        raise DoltCliError(
            f"Dolt JSON envelope mismatch: got {sorted(actual)}, expected {sorted(expected)}"
        )


def _descriptor_unique_keys(descriptor: dict[str, Any]) -> None:
    if len(descriptor) != len({key.lower() for key in descriptor}):
        raise DoltCliError("Dolt JSON column descriptor has duplicate keys")


def _column_label_from_descriptor(column: dict[str, Any]) -> str:
    has_name = "name" in column
    has_Name = "Name" in column
    if has_name and has_Name:
        raise DoltCliError("Dolt JSON column descriptor has conflicting name aliases")
    _descriptor_unique_keys(column)
    if not has_name and not has_Name:
        raise DoltCliError("Dolt JSON column name is missing or empty")
    name = column["name"] if has_name else column["Name"]
    if not isinstance(name, str) or name == "":
        raise DoltCliError("Dolt JSON column name is missing or empty")
    return name


def json_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if not payload:
            return []
        if "rows" in payload and "columns" in payload:
            _require_exact_envelope_keys(payload, frozenset({"rows", "columns"}))
            columns = payload["columns"]
            if not isinstance(columns, list):
                raise DoltCliError("Dolt JSON columns was not a list")
            names: list[str] = []
            for column in columns:
                if isinstance(column, dict):
                    name = _column_label_from_descriptor(column)
                else:
                    name = column
                if not isinstance(name, str) or name == "":
                    raise DoltCliError("Dolt JSON column name is missing or empty")
                names.append(name)
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
        if "rows" in payload:
            _require_exact_envelope_keys(payload, frozenset({"rows"}))
            return json_rows(payload["rows"])
        raise DoltCliError("Dolt JSON envelope was not recognized")
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


_SHOW_CREATE_ROW_KEYS = frozenset({"table", "create table"})


def _extract_show_create_fields(row: dict[str, Any], table_name: str, kind: str) -> str:
    _require_unique_row_keys(row, kind)
    if len(row) != 2:
        raise DoltCliError(f"Dolt {kind} row schema mismatch: expected 2 columns, got {len(row)}")
    table_key: str | None = None
    create_table_key: str | None = None
    for key in row:
        lowered = key.lower()
        if lowered not in _SHOW_CREATE_ROW_KEYS:
            raise DoltCliError(
                f"Dolt {kind} row schema mismatch: got {sorted(row.keys())}, "
                f"expected Table and Create Table"
            )
        if lowered == "table":
            table_key = key
        else:
            create_table_key = key
    if table_key is None or create_table_key is None:
        raise DoltCliError(f"Dolt {kind} row schema mismatch: missing Table column")
    raw_table = row[table_key]
    if not isinstance(raw_table, str) or raw_table == "":
        raise DoltCliError(f"Dolt {kind} Table column is missing or invalid")
    if raw_table != table_name:
        raise DoltCliError(f"Dolt {kind} returned mismatched table name")
    raw_ddl = row[create_table_key]
    if not isinstance(raw_ddl, str) or raw_ddl == "":
        raise DoltCliError(f"Dolt {kind} Create Table column is missing or invalid")
    return raw_ddl


_ALLOWED_SHOW_TABLE_TYPES = frozenset({"BASE TABLE", "VIEW"})
_TABLES_IN_COLUMN_PREFIX = "tables_in_"


def _is_show_tables_in_key(key: str) -> bool:
    return key.startswith(_TABLES_IN_COLUMN_PREFIX) and len(key) > len(_TABLES_IN_COLUMN_PREFIX)


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
    tables_in = [key for key in keys if _is_show_tables_in_key(key)]
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
    if not isinstance(raw_name, str) or raw_name == "":
        raise DoltCliError(f"Dolt {kind} table name is missing or invalid")
    return raw_name, table_type


_EXACT_METADATA_ROW_SCHEMAS: dict[str, frozenset[str]] = {
    "read_ref": frozenset({"commit_id"}),
    "candidate_parent": frozenset({"parents"}),
    "commit_exists": frozenset({"commit_hash"}),
    "catalog_count": frozenset({"row_count"}),
    "branch_heads": frozenset({"name", "hash"}),
    "marker_commits": frozenset({"commit_hash", "message"}),
    "marker_direct_refs": frozenset({"name", "parents"}),
}


def _validate_metadata_rows(kind: str, rows: list[dict[str, Any]]) -> None:
    if kind in _EXACT_METADATA_ROW_SCHEMAS:
        expected = _EXACT_METADATA_ROW_SCHEMAS[kind]
        for row in rows:
            _require_exact_row_keys(row, expected, kind)
        return
    if kind == "catalog_tables":
        seen_table_names: set[str] = set()
        for row in rows:
            table_name, _ = _parse_show_tables_row(row, kind)
            if table_name in seen_table_names:
                raise DoltCliError(f"Dolt {kind} returned duplicate table names")
            seen_table_names.add(table_name)
        return


def _column_names_from_envelope(columns: Any, kind: str) -> list[str]:
    if not isinstance(columns, list):
        raise DoltCliError("Dolt JSON columns was not a list")
    names: list[str] = []
    for column in columns:
        if isinstance(column, dict):
            name = _column_label_from_descriptor(column)
        else:
            name = column
        if not isinstance(name, str) or name == "":
            raise DoltCliError("Dolt JSON column name is missing or empty")
        names.append(name)
    if len(names) != len({name.lower() for name in names}):
        raise DoltCliError(f"Dolt {kind} envelope has duplicate column names")
    return names


def _validate_metadata_columns(kind: str, columns: Any) -> None:
    names = _column_names_from_envelope(columns, kind)
    if kind in _EXACT_METADATA_ROW_SCHEMAS:
        expected = _EXACT_METADATA_ROW_SCHEMAS[kind]
        actual = {name.lower() for name in names}
        if actual != expected:
            raise DoltCliError(
                f"Dolt {kind} envelope column schema mismatch: "
                f"got {sorted(actual)}, expected {sorted(expected)}"
            )
        return
    if kind == "catalog_tables":
        keys = {name.lower() for name in names}
        if len(keys) != 2:
            raise DoltCliError(
                f"Dolt {kind} envelope column schema mismatch: expected 2 columns, got {len(keys)}"
            )
        if "table_type" not in keys:
            raise DoltCliError(f"Dolt {kind} envelope column schema mismatch: missing Table_type")
        tables_in = [key for key in keys if _is_show_tables_in_key(key)]
        if len(tables_in) != 1:
            raise DoltCliError(
                f"Dolt {kind} envelope column schema mismatch: missing unique Tables_in_* column"
            )


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


def parse_commit_exists_rows(
    rows: list[dict[str, Any]],
    commit_id: str,
    *,
    kind: str = "commit_exists",
) -> bool:
    if len(rows) == 0:
        return False
    if len(rows) > 1:
        raise DoltCliError(f"Dolt {kind} returned {len(rows)} rows, expected 0 or 1")
    row = rows[0]
    raw = value(row, "commit_hash", 0)
    if not isinstance(raw, str) or raw == "":
        raise DoltCliError(f"Dolt {kind} commit_hash is missing or invalid")
    if raw != commit_id:
        raise DoltCliError(f"Dolt {kind} commit_hash mismatch")
    return True


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


# Per-session memoization for the few commit targets a single workflow re-reads
# (initial, expected parent, candidate).  This is not a memory budget: catalogs
# are retained until the session is dropped.  A node-wide catalog cache with a
# real byte bound belongs to the capacity stage.
_CATALOG_MEMO_ENTRIES = 4


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
        self._catalog_cache: OrderedDict[str, tuple[TableCatalog, ...]] = OrderedDict()
        self._catalog_cache_lock = threading.Lock()
        _ensure_csv_field_limit(settings.max_stream_line_bytes)

    def _get_cached_catalog(self, commit_id: str) -> tuple[TableCatalog, ...] | None:
        with self._catalog_cache_lock:
            catalog = self._catalog_cache.get(commit_id)
            if catalog is None:
                return None
            self._catalog_cache.move_to_end(commit_id)
            return catalog

    def _store_cached_catalog(self, commit_id: str, catalog: tuple[TableCatalog, ...]) -> None:
        with self._catalog_cache_lock:
            self._catalog_cache.pop(commit_id, None)
            while len(self._catalog_cache) >= _CATALOG_MEMO_ENTRIES:
                self._catalog_cache.popitem(last=False)
            self._catalog_cache[commit_id] = catalog

    def _load_table_schema(
        self,
        table_name: str,
        target_literal: str,
        *,
        cancellation: StreamCancellationCheck | None = None,
        call_timeout: Callable[[float], float] | None = None,
    ) -> TableCatalog:
        create_rows = self.query_json(
            "catalog_create",
            f"SHOW CREATE TABLE {quote_identifier(table_name)} AS OF {target_literal};\n",
            cancellation=cancellation,
            call_timeout=call_timeout,
        )
        create_row = _require_exactly_one_row(create_rows, "catalog_create")
        ddl = _extract_show_create_fields(create_row, table_name, "catalog_create")
        parsed = _parse_create_statement(ddl, 0)
        if parsed.name != table_name:
            raise DoltCliError("Dolt catalog_create DDL table name mismatch")
        return parsed

    def _load_table_catalog(
        self,
        table_name: str,
        target_literal: str,
        *,
        cancellation: StreamCancellationCheck | None = None,
        call_timeout: Callable[[float], float] | None = None,
    ) -> TableCatalog:
        parsed = self._load_table_schema(
            table_name,
            target_literal,
            cancellation=cancellation,
            call_timeout=call_timeout,
        )
        count_rows = self.query_json(
            "catalog_count",
            f"SELECT COUNT(*) AS row_count FROM {quote_identifier(table_name)} AS OF {target_literal};\n",
            cancellation=cancellation,
            call_timeout=call_timeout,
        )
        count_row = _require_exactly_one_row(count_rows, "catalog_count")
        raw_count = value(count_row, "row_count", 0)
        row_count = _parse_non_negative_row_count(raw_count, "catalog_count")
        return TableCatalog(parsed.name, parsed.columns, row_count)

    def replay(self, replay_sql: Path) -> None:
        self.run_cli(
            "replay",
            ["sql", "--result-format=csv"],
            self.settings.import_timeout_seconds,
            stdin_path=replay_sql,
        )

    def catalog(
        self,
        base_commit_id: str,
        target_commit_id: str,
        *,
        cancellation: StreamCancellationCheck | None = None,
        call_timeout: Callable[[float], float] | None = None,
    ) -> tuple[TableCatalog, ...]:
        validate_commit_id(base_commit_id)
        safe_target = validate_commit_id(target_commit_id)
        cached = self._get_cached_catalog(safe_target)
        if cached is not None:
            return cached
        target_literal = commit_literal(safe_target)
        show_rows = self.query_json(
            "catalog_tables",
            f"SHOW FULL TABLES AS OF {target_literal};\n",
            cancellation=cancellation,
            call_timeout=call_timeout,
        )
        table_names: list[str] = []
        for row in show_rows:
            table_name, table_type = _parse_show_tables_row(row, "catalog_tables")
            if table_type == "VIEW":
                continue
            table_names.append(table_name)
        workers = min(self.settings.catalog_parallel_workers, len(table_names)) or 1
        if workers <= 1:
            tables = [
                self._load_table_catalog(
                    name,
                    target_literal,
                    cancellation=cancellation,
                    call_timeout=call_timeout,
                )
                for name in table_names
            ]
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                tables = list(
                    executor.map(
                        lambda name: self._load_table_catalog(
                            name,
                            target_literal,
                            cancellation=cancellation,
                            call_timeout=call_timeout,
                        ),
                        table_names,
                    )
                )
        catalog = tuple(sorted(tables, key=lambda table: table.name))
        self._store_cached_catalog(safe_target, catalog)
        return catalog

    def type_catalog(
        self,
        base_commit_id: str,
        target_commit_id: str,
        *,
        cancellation: StreamCancellationCheck | None = None,
        call_timeout: Callable[[float], float] | None = None,
    ) -> tuple[TableCatalog, ...]:
        validate_commit_id(base_commit_id)
        safe_target = validate_commit_id(target_commit_id)
        target_literal = commit_literal(safe_target)
        show_rows = self.query_json(
            "catalog_tables",
            f"SHOW FULL TABLES AS OF {target_literal};\n",
            cancellation=cancellation,
            call_timeout=call_timeout,
        )
        table_names: list[str] = []
        for row in show_rows:
            table_name, table_type = _parse_show_tables_row(row, "catalog_tables")
            if table_type == "VIEW":
                continue
            table_names.append(table_name)
        workers = min(self.settings.catalog_parallel_workers, len(table_names)) or 1
        if workers <= 1:
            tables = [
                self._load_table_schema(
                    name,
                    target_literal,
                    cancellation=cancellation,
                    call_timeout=call_timeout,
                )
                for name in table_names
            ]
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                tables = list(
                    executor.map(
                        lambda name: self._load_table_schema(
                            name,
                            target_literal,
                            cancellation=cancellation,
                            call_timeout=call_timeout,
                        ),
                        table_names,
                    )
                )
        return tuple(sorted(tables, key=lambda table: table.name))

    def commit_exists(self, commit_id: str) -> bool:
        target_literal = opaque_commit_literal(commit_id)
        rows = self.query_json(
            "commit_exists",
            f"SELECT commit_hash FROM dolt_commits WHERE commit_hash = {target_literal};\n",
        )
        return parse_commit_exists_rows(rows, commit_id)

    def catalog_at(self, commit_id: str) -> tuple[TableCatalog, ...]:
        cached = self._get_cached_catalog(commit_id)
        if cached is not None:
            return cached
        target_literal = opaque_commit_literal(commit_id)
        show_rows = self.query_json(
            "catalog_tables",
            f"SHOW FULL TABLES AS OF {target_literal};\n",
        )
        table_names: list[str] = []
        for row in show_rows:
            table_name, table_type = _parse_show_tables_row(row, "catalog_tables")
            if table_type == "VIEW":
                continue
            table_names.append(table_name)
        workers = min(self.settings.catalog_parallel_workers, len(table_names)) or 1
        if workers <= 1:
            tables = [self._load_table_catalog(name, target_literal) for name in table_names]
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                tables = list(
                    executor.map(
                        lambda name: self._load_table_catalog(name, target_literal),
                        table_names,
                    )
                )
        catalog = tuple(sorted(tables, key=lambda table: table.name))
        self._store_cached_catalog(commit_id, catalog)
        return catalog

    def stream_table(
        self,
        commit_id: str,
        table: TableCatalog,
        policy: UnknownTypePolicy,
        *,
        table_plan: CompiledTablePlan | None = None,
        cancellation: StreamCancellationCheck | None = None,
        call_timeout: Callable[[float], float] | None = None,
    ) -> Iterator[pa.RecordBatch]:
        safe_commit_id = validate_commit_id(commit_id)
        return self._stream_table_impl(
            safe_commit_id,
            opaque_commit_literal(safe_commit_id),
            table,
            policy,
            table_plan=table_plan,
            cancellation=cancellation,
            call_timeout=call_timeout,
        )

    def stream_table_at(
        self,
        commit_id: str,
        table: TableCatalog,
        policy: UnknownTypePolicy,
        *,
        table_plan: CompiledTablePlan | None = None,
        cancellation: StreamCancellationCheck | None = None,
        stream_owner: object | None = None,
    ) -> Iterator[pa.RecordBatch]:
        target_literal = opaque_commit_literal(commit_id)
        return self._stream_table_impl(
            commit_id,
            target_literal,
            table,
            policy,
            table_plan=table_plan,
            cancellation=cancellation,
            stream_owner=stream_owner,
        )

    def _stream_table_impl(
        self,
        commit_id: str,
        target_literal: str,
        table: TableCatalog,
        policy: UnknownTypePolicy,
        *,
        table_plan: CompiledTablePlan | None,
        cancellation: StreamCancellationCheck | None,
        stream_owner: object | None = None,
        call_timeout: Callable[[float], float] | None = None,
    ) -> Iterator[pa.RecordBatch]:
        del commit_id
        plan = table_plan if table_plan is not None else compile_table_plan(table, policy)
        select_list, expected_header = _tagged_select_list(plan)
        query = write_query(
            self.query_directory,
            f"SELECT {select_list} FROM {quote_identifier(table.name)} AS OF {target_literal};\n",
        )
        stream: ProcessStream | None = None
        stream_closed = False
        batch_metrics: dict[str, object] = {
            "max_encoded_line_bytes": 0,
            "encoded_line_bound_valid": True,
            "encoded_line_bound": self.settings.max_stream_line_bytes,
            "oversized_single_row": False,
        }
        stream_timeout = self._effective_call_timeout(
            self.settings.import_timeout_seconds,
            call_timeout=call_timeout,
        )
        try:
            if evaluate_stream_cancellation(cancellation):
                raise DoltCliStreamCancelledError("row stream cancelled before start")
            if stream_timeout <= 0:
                raise DoltCliStreamCancelledError("row stream cancelled before start")
            stream = self.runner.stream(
                "row_stream",
                ["sql", "--result-format=csv", "--binary-as-hex"],
                cwd=self.repository,
                timeout=stream_timeout,
                stdin_path=query,
                cancellation=cancellation,
                owner=stream_owner,
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
                if result.exit_code != 0 or result.timed_out or result.cancelled:
                    raise DoltCliError("Dolt row stream failed")
                return
            if header != expected_header:
                raise DoltCliError("tagged CSV header mismatch")
            rows: list[NormalizedRow] = []
            rows_bytes = 0

            def _raise_if_cancelled() -> None:
                if evaluate_stream_cancellation(cancellation):
                    raise DoltCliStreamCancelledError("row stream cancelled")

            def emit(chunk: list[NormalizedRow]) -> pa.RecordBatch:
                _raise_if_cancelled()
                batch = plan.record_batch(chunk)
                _observe_batch_metrics(
                    batch_metrics,
                    chunk,
                    row_bound=self.settings.record_batch_rows,
                    byte_bound=self.settings.record_batch_bytes,
                )
                return batch

            for row in reader:
                _raise_if_cancelled()
                parsed = _parse_tagged_row(row, plan)
                normalized_row = plan.normalize_row(parsed)
                _raise_if_cancelled()
                chunks, rows, rows_bytes = accumulate_normalized_row(
                    rows,
                    rows_bytes,
                    normalized_row,
                    row_bound=self.settings.record_batch_rows,
                    byte_bound=self.settings.record_batch_bytes,
                )
                for chunk in chunks:
                    yield emit(chunk)
            if rows:
                _raise_if_cancelled()
                yield emit(rows)
            _raise_if_cancelled()
            result = stream.close()
            stream_closed = True
            if result.exit_code != 0 or result.timed_out or result.cancelled:
                raise DoltCliError("Dolt row stream failed")
        finally:
            if stream is not None and not stream_closed:
                stream.close(cancelled=evaluate_stream_cancellation(cancellation))
            query.unlink(missing_ok=True)

    def query_json(
        self,
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
        cancellation: StreamCancellationCheck | None = None,
        call_timeout: Callable[[float], float] | None = None,
    ) -> list[dict[str, Any]]:
        query = write_query(self.query_directory, sql)
        args: list[str] = []
        if revision is not None:
            args.append(f"--branch={revision}")
        args.extend(["sql", "--result-format=json"])
        effective_timeout = self._effective_call_timeout(
            self.settings.metadata_timeout_seconds,
            call_timeout=call_timeout,
        )
        try:
            result = self.run_cli(
                kind,
                args,
                effective_timeout,
                stdin_path=query,
                cancellation=cancellation,
            )
            if result.stdout_truncated:
                raise DoltCliError("Dolt metadata output was truncated")
            try:
                decoded = _decode_metadata_json(result.stdout)
                rows = json_rows(decoded)
                _validate_metadata_rows(kind, rows)
                if isinstance(decoded, dict) and "rows" in decoded and "columns" in decoded:
                    _validate_metadata_columns(kind, decoded["columns"])
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
        cancellation: StreamCancellationCheck | None = None,
    ) -> CommandResult:
        if evaluate_stream_cancellation(cancellation):
            raise DoltCliStreamCancelledError(f"Dolt command cancelled: {kind}")
        if timeout <= 0:
            raise DoltCliStreamCancelledError(f"Dolt command cancelled: {kind}")
        result = self.runner.run(
            kind,
            args,
            cwd=self.repository,
            timeout=timeout,
            stdin_path=stdin_path,
            capture_stdout=True,
            cancellation=cancellation,
        )
        if result.timed_out or result.cancelled or result.exit_code != 0:
            raise DoltCliError(f"Dolt command failed: {kind}")
        return result

    def _effective_call_timeout(
        self,
        per_call_timeout: float,
        *,
        call_timeout: Callable[[float], float] | None,
    ) -> float:
        if call_timeout is None:
            return per_call_timeout
        return call_timeout(per_call_timeout)
