"""Private Candidate A/B Dolt providers used by the P2-R1 feasibility probe."""

from __future__ import annotations

import asyncio
import csv
import os
import re
import threading
import time
from collections.abc import Coroutine, Iterator
from pathlib import Path
from typing import Any, Protocol, TypeVar, cast
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
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.process import (
    CgroupMemoryMeasurement,
    CgroupMemoryTracker,
    DiscardProcess,
    DoltRunner,
    MemorySampler,
    ProcessStream,
    ServerSupervisor,
    process_tree_rss_kib,
    windows_for_interval,
)
from gateway_repository_service.candidate_a.dolt_cli import CandidateADoltCli, DoltCliError
from gateway_repository_service.candidate_a.sql import (
    ProviderError,
    _catalog_from_schema_diff,
    _commit_literal,
    _metric_int,
    _observe_batch_metrics,
    _parse_create_statement,
    _parse_tagged_row,
    _row_bytes,
    _rows_bytes,
    _tagged_select_list,
    _tagged_select_list_for_catalog,
    quote_identifier,
)
from gateway_repository_service.settings import RepositoryServiceSettings

__all__ = [
    "OfflineCliProvider",
    "ProviderError",
    "Provider",
    "quote_identifier",
    "_catalog_from_schema_diff",
    "_commit_literal",
    "_metric_int",
    "_observe_batch_metrics",
    "_parse_create_statement",
    "_parse_tagged_row",
    "_row_bytes",
    "_rows_bytes",
    "_tagged_select_list",
]


def _baseline_memory_metrics(
    workflow_process_tree_rss_kib: int | None,
    provider_process_tree_rss_kib: int | None,
    arrow_memory_pool_bytes: int | None,
    cgroup_current_bytes: int | None,
) -> dict[str, int | None]:
    """Return the canonical baseline metrics shared by both providers."""

    return {
        "baseline_workflow_process_tree_rss_kib": workflow_process_tree_rss_kib,
        "baseline_provider_process_tree_rss_kib": provider_process_tree_rss_kib,
        "baseline_arrow_memory_pool_bytes": arrow_memory_pool_bytes,
        "cgroup_baseline_current_bytes": cgroup_current_bytes,
    }


def _memory_stat_delta(current: int | None, baseline: int | None) -> int | None:
    """Return non-negative stream memory-stat growth when both samples exist."""

    if current is None or baseline is None:
        return None
    return max(0, current - baseline)


def _cgroup_stream_metrics(
    workflow_baseline: CgroupMemoryMeasurement | None,
    stream_baseline: CgroupMemoryMeasurement | None,
    final: CgroupMemoryMeasurement | None,
) -> dict[str, int | bool | str | None]:
    """Build cgroup fields with separate workflow and stream baselines.

    The tracker is created before fixture import, so its reset stat is a
    workflow-level baseline.  Stream evidence must instead compare the final
    stat with the snapshot taken immediately before the measured query.
    """

    stream_anon = stream_baseline.anon_bytes if stream_baseline else None
    stream_file = stream_baseline.file_bytes if stream_baseline else None
    return {
        "cgroup_current_bytes": final.current_bytes if final else None,
        "cgroup_peak_bytes": final.peak_bytes if final else None,
        "cgroup_memory_peak_bytes": final.peak_bytes if final else None,
        "memory_limit_bytes": final.memory_limit_bytes if final else None,
        "effective_memory_limit_bytes": (
            final.effective_memory_limit_bytes if final else None
        ),
        "cgroup_baseline_peak_bytes": (
            workflow_baseline.peak_bytes if workflow_baseline else None
        ),
        "cgroup_reset_current_baseline_bytes": (
            final.reset_current_baseline_bytes if final else None
        ),
        "cgroup_stream_baseline_current_bytes": (
            stream_baseline.current_bytes if stream_baseline else None
        ),
        "cgroup_stat_anon_bytes": final.anon_bytes if final else None,
        "cgroup_stat_file_bytes": final.file_bytes if final else None,
        "cgroup_baseline_stat_anon_bytes": stream_anon,
        "cgroup_baseline_stat_file_bytes": stream_file,
        "cgroup_workflow_baseline_stat_anon_bytes": (
            workflow_baseline.baseline_anon_bytes if workflow_baseline else None
        ),
        "cgroup_workflow_baseline_stat_file_bytes": (
            workflow_baseline.baseline_file_bytes if workflow_baseline else None
        ),
        "cgroup_stat_anon_delta_bytes": _memory_stat_delta(
            final.anon_bytes if final else None, stream_anon
        ),
        "cgroup_stat_file_delta_bytes": _memory_stat_delta(
            final.file_bytes if final else None, stream_file
        ),
        "cgroup_scope_identity": final.scope_identity if final else None,
        "cgroup_per_workflow": final.per_workflow if final else False,
    }


def _pending_row_windows(
    rows_seen: int, pending_index: int, total_rows: int
) -> tuple[str, ...]:
    """Return windows for the pending row, not for the last emitted batch."""

    row_start = rows_seen + pending_index
    return windows_for_interval(row_start, row_start + 1, total_rows)


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
        *,
        table_plan: CompiledTablePlan | None = None,
    ) -> Iterator[pa.RecordBatch]: ...

    def marker_parent(self, marker: str) -> str | None: ...

    def marker_count(self, marker: str) -> int: ...

    def close(self) -> None: ...


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


def _empty_batch_metrics(*, encoded_line_applicable: bool) -> dict[str, object]:
    return {
        "total_rows": 0,
        "total_stream_payload_bytes": 0,
        "max_row_bytes": 0,
        "batch_count": 0,
        "max_batch_rows": 0,
        "max_batch_bytes": 0,
        "oversized_single_row": False,
        "oversized_row_count": 0,
        "max_oversized_row_bytes": 0,
        "oversized_batch_count": 0,
        "batch_contract_valid": True,
        "batch_contract_violation_count": 0,
        "encoded_line_bound": None,
        "max_encoded_line_bytes": 0,
        "encoded_line_bound_valid": None,
        "encoded_line_applicable": encoded_line_applicable,
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
        layout: DurableLayout,
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
        self._candidate_cli = CandidateADoltCli(settings, layout, repository, runner)

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
        try:
            self._candidate_cli.replay(replay_sql)
        except DoltCliError as exc:
            raise ProviderError(str(exc)) from exc

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

    def commit_reachable_from_main(self, commit_id: str) -> bool:
        head = self.head()
        if commit_id == head:
            return True
        rows = self._query_json(
            "commit_reachable",
            "SELECT COUNT(*) AS reachable FROM dolt_log "
            f"WHERE commit_hash = {_commit_literal(commit_id)};\n",
        )
        if not rows:
            raise ProviderError("Dolt did not return ancestry result")
        return int(_value(rows[0], "reachable", 0)) > 0

    def catalog(self, base_commit_id: str, target_commit_id: str) -> tuple[TableCatalog, ...]:
        try:
            return self._candidate_cli.catalog(base_commit_id, target_commit_id)
        except DoltCliError as exc:
            raise ProviderError(str(exc)) from exc

    def stream_table(
        self,
        commit_id: str,
        table: TableCatalog,
        policy: UnknownTypePolicy,
        *,
        table_plan: CompiledTablePlan | None = None,
    ) -> Iterator[pa.RecordBatch]:
        self.last_stream_metrics = {}
        self.last_plateau_peaks = _empty_plateau_peaks()
        plan = table_plan if table_plan is not None else compile_table_plan(table, policy)
        select_list, expected_header = _tagged_select_list(plan)
        query = _write_query(
            self.query_directory,
            f"SELECT {select_list} FROM {quote_identifier(table.name)} AS OF '{commit_id}';\n",
        )
        stream: ProcessStream | None = None
        workflow_baseline_cgroup = (
            self.cgroup.snapshot() if self.cgroup is not None else None
        )
        query_baseline_cgroup = (
            self.cgroup.snapshot() if self.cgroup is not None else None
        )
        stream_baseline_cgroup = query_baseline_cgroup
        baseline_arrow = pa.default_memory_pool().bytes_allocated()
        peak_arrow = baseline_arrow
        baseline_workflow = process_tree_rss_kib(os.getpid())
        workflow_peak = baseline_workflow
        sampler: MemorySampler | None = None
        baseline_provider = 0
        rows_seen = 0
        oversized_single_row = False
        oversized_row_bytes: int | None = None
        batch_metrics = _empty_batch_metrics(encoded_line_applicable=True)
        batch_metrics["encoded_line_bound"] = self.settings.max_stream_line_bytes
        batch_metrics["encoded_line_bound_valid"] = True
        old_field_limit = csv.field_size_limit()
        try:
            sampler = MemorySampler(
                os.getpid(),
                lambda: stream.running_pid if stream is not None else None,
                self.cgroup,
                self.settings.memory_sample_interval_seconds,
                baselines={
                    "workflow_process_tree": workflow_peak,
                    "provider_process_tree": None,
                    "arrow_memory_pool": baseline_arrow,
                    "cgroup": (
                        query_baseline_cgroup.current_bytes
                        if query_baseline_cgroup
                        else None
                    ),
                },
            )
            sampler.start()
            sampler.set_active(("first_10pct",))
            stream = self.runner.stream(
                "row_stream",
                ["sql", "--result-format=csv", "--binary-as-hex"],
                cwd=self.repository,
                timeout=self.settings.import_timeout_seconds,
                stdin_path=query,
            )
            baseline_provider = process_tree_rss_kib(stream.process.pid)
            sampler.set_baseline("provider_process_tree", baseline_provider)
            csv.field_size_limit(self.settings.max_stream_line_bytes)
            def decode_line(line: bytes) -> str:
                line_bytes = len(line)
                batch_metrics["max_encoded_line_bytes"] = max(
                    _metric_int(batch_metrics, "max_encoded_line_bytes"), line_bytes
                )
                if line_bytes > self.settings.max_stream_line_bytes:
                    batch_metrics["encoded_line_bound_valid"] = False
                    raise ProviderError("tagged CSV encoded line exceeded safety bound")
                return line.decode("utf-8")

            reader = csv.reader((decode_line(line) for line in stream), strict=True)
            header = next(reader, None)
            if header is None:
                return
            if header != expected_header:
                raise ProviderError("tagged CSV header mismatch")
            rows: list[NormalizedRow] = []
            rows_bytes = 0

            def emit(chunk: list[NormalizedRow]) -> pa.RecordBatch:
                nonlocal rows_seen, peak_arrow, workflow_peak
                start = rows_seen
                end = rows_seen + len(chunk)
                windows = windows_for_interval(start, end, table.row_count)
                sampler.set_active(windows)
                sampler.sample(windows)
                batch = plan.record_batch(chunk)
                peak_arrow = max(peak_arrow, pa.default_memory_pool().bytes_allocated())
                workflow_peak = max(workflow_peak, process_tree_rss_kib(os.getpid()))
                sampler.sample(windows)
                _observe_batch_metrics(
                    batch_metrics,
                    chunk,
                    row_bound=self.settings.record_batch_rows,
                    byte_bound=self.settings.record_batch_bytes,
                )
                rows_seen = end
                return batch

            for row in reader:
                parsed = _parse_tagged_row(row, plan)
                normalized_row = plan.normalize_row(parsed)
                chunks, rows, rows_bytes = accumulate_normalized_row(
                    rows,
                    rows_bytes,
                    normalized_row,
                    row_bound=self.settings.record_batch_rows,
                    byte_bound=self.settings.record_batch_bytes,
                )
                for chunk in chunks:
                    if len(chunk) == 1 and chunk[0].logical_size_bytes > self.settings.record_batch_bytes:
                        oversized_single_row = True
                        oversized_row_bytes = max(
                            oversized_row_bytes or 0,
                            chunk[0].logical_size_bytes,
                        )
                    yield emit(chunk)
                    sampler.sample()
                if rows:
                    sampler.set_active(
                        _pending_row_windows(rows_seen, len(rows) - 1, table.row_count)
                    )
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
                "plateau_peaks": plateau,
                "plateau_peaks_absolute": self.last_plateau_peaks_absolute,
                **_baseline_memory_metrics(
                    baseline_workflow,
                    baseline_provider,
                    baseline_arrow,
                    stream_baseline_cgroup.current_bytes
                    if stream_baseline_cgroup
                    else None,
                ),
                **_cgroup_stream_metrics(
                    workflow_baseline_cgroup,
                    stream_baseline_cgroup,
                    final_cgroup,
                ),
                "oversized_single_row": oversized_single_row,
                "oversized_row_bytes": oversized_row_bytes,
                "byte_bound_reason": "single_indivisible_row" if oversized_single_row else None,
                **batch_metrics,
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

    def discard_table_to_devnull(
        self, commit_id: str, table: TableCatalog
    ) -> dict[str, object]:
        """Run the stream SELECT while bypassing CSV and Arrow conversion.

        This is diagnostic-only evidence for separating Dolt CLI working-set
        growth from the Python framing/conversion path.
        """

        select_list, _ = _tagged_select_list_for_catalog(table, UnknownTypePolicy.STRINGIFY)
        query = _write_query(
            self.query_directory,
            f"SELECT {select_list} FROM {quote_identifier(table.name)} AS OF '{commit_id}';\n",
        )
        discard: DiscardProcess | None = None
        sampler: MemorySampler | None = None
        started_at = time.monotonic()
        stream_baseline_cgroup = (
            self.cgroup.snapshot() if self.cgroup is not None else None
        )
        baseline_arrow = pa.default_memory_pool().bytes_allocated()
        baseline_workflow = process_tree_rss_kib(os.getpid())
        try:
            # Start before spawn so CLI setup and query execution are covered.
            sampler = MemorySampler(
                os.getpid(),
                lambda: discard.process.pid if discard is not None else None,
                self.cgroup,
                self.settings.memory_sample_interval_seconds,
                baselines={
                    "workflow_process_tree": baseline_workflow,
                    "provider_process_tree": None,
                    "arrow_memory_pool": baseline_arrow,
                    "cgroup": (
                        stream_baseline_cgroup.current_bytes
                        if stream_baseline_cgroup
                        else None
                    ),
                    "cgroup_anon_bytes": (
                        stream_baseline_cgroup.anon_bytes
                        if stream_baseline_cgroup
                        else None
                    ),
                    "cgroup_file_bytes": (
                        stream_baseline_cgroup.file_bytes
                        if stream_baseline_cgroup
                        else None
                    ),
                },
                record_history=True,
            )
            sampler.start()
            discard = self.runner.discard(
                "row_stream_discard",
                ["sql", "--result-format=csv", "--binary-as-hex"],
                cwd=self.repository,
                timeout=self.settings.import_timeout_seconds,
                stdin_path=query,
            )
            sampler.set_baseline(
                "provider_process_tree",
                process_tree_rss_kib(discard.process.pid),
            )
            result = discard.close()
            finished_at = time.monotonic()
            sampler.sample()
            window_metrics = sampler.time_fraction_peaks(started_at, finished_at)
            final_cgroup = self.cgroup.snapshot() if self.cgroup is not None else None
            self.last_stream_peak_rss_kib = result.provider_peak_rss_kib
            self.last_stream_rss_delta_kib = max(
                0, result.provider_peak_rss_kib - result.provider_start_rss_kib
            )
            self.last_plateau_peaks = cast(
                dict[str, dict[str, int | None]],
                window_metrics["plateau_peaks"],
            )
            self.last_plateau_peaks_absolute = cast(
                dict[str, dict[str, int | None]],
                window_metrics["plateau_peaks_absolute"],
            )
            self.last_stream_metrics = {
                "workflow_process_tree_rss_kib": baseline_workflow,
                "provider_process_tree_rss_kib": result.provider_peak_rss_kib,
                "provider_start_rss_kib": result.provider_start_rss_kib,
                "provider_start_rss_anon_kib": result.provider_start_rss_anon_kib,
                "provider_start_rss_file_kib": result.provider_start_rss_file_kib,
                "provider_peak_rss_anon_kib": result.provider_peak_rss_anon_kib,
                "provider_peak_rss_file_kib": result.provider_peak_rss_file_kib,
                "arrow_memory_pool_baseline_bytes": baseline_arrow,
                "arrow_memory_pool_peak_bytes": baseline_arrow,
                "plateau_peaks": self.last_plateau_peaks,
                "plateau_peaks_absolute": self.last_plateau_peaks_absolute,
                "memory_stat_plateau": window_metrics["memory_stat_plateau"],
                "memory_stat_plateau_absolute": window_metrics[
                    "memory_stat_plateau_absolute"
                ],
                "window_basis": "time_fraction",
                **_baseline_memory_metrics(
                    baseline_workflow,
                    result.provider_start_rss_kib,
                    baseline_arrow,
                    stream_baseline_cgroup.current_bytes
                    if stream_baseline_cgroup
                    else None,
                ),
                "query_before_baseline": _baseline_memory_metrics(
                    baseline_workflow,
                    result.provider_start_rss_kib,
                    baseline_arrow,
                    stream_baseline_cgroup.current_bytes
                    if stream_baseline_cgroup
                    else None,
                ),
                **_cgroup_stream_metrics(
                    stream_baseline_cgroup,
                    stream_baseline_cgroup,
                    final_cgroup,
                ),
            }
            if result.exit_code != 0:
                raise ProviderError("Dolt discard stream failed")
            return {
                "mode": "discard_to_devnull",
                "stdout_target": "/dev/null",
                "provider_start_rss_anon_kib": result.provider_start_rss_anon_kib,
                "provider_start_rss_file_kib": result.provider_start_rss_file_kib,
                "provider_peak_rss_anon_kib": result.provider_peak_rss_anon_kib,
                "provider_peak_rss_file_kib": result.provider_peak_rss_file_kib,
                "provider_peak_rss_kib": result.provider_peak_rss_kib,
                "timed_out": result.timed_out,
                "stderr_tail": result.stderr_tail.decode("utf-8", errors="replace"),
                "duration_seconds": result.duration_seconds,
            }
        finally:
            if sampler is not None and not self.last_stream_metrics:
                sampler.stop()
            if discard is not None:
                discard.close()
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
        try:
            return self._candidate_cli.query_json(kind, sql, revision=revision)
        except DoltCliError as exc:
            raise ProviderError(str(exc)) from exc

    def _run(
        self,
        kind: str,
        args: list[str],
        timeout: float,
        *,
        stdin_path: Path | None = None,
    ) -> Any:
        try:
            return self._candidate_cli.run_cli(kind, args, timeout, stdin_path=stdin_path)
        except DoltCliError as exc:
            raise ProviderError(str(exc)) from exc


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
        layout: DurableLayout,
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
        *,
        table_plan: CompiledTablePlan | None = None,
    ) -> Iterator[pa.RecordBatch]:
        self.last_stream_metrics = {}
        self.last_plateau_peaks = _empty_plateau_peaks()
        baseline_rss = (
            process_tree_rss_kib(self.supervisor.process.pid)
            if self.supervisor.process is not None
            else 0
        )
        baseline_arrow = pa.default_memory_pool().bytes_allocated()
        workflow_baseline_cgroup = (
            self.cgroup.snapshot() if self.cgroup is not None else None
        )
        stream_baseline_cgroup: CgroupMemoryMeasurement | None = None
        baseline_workflow = process_tree_rss_kib(os.getpid())
        workflow_peak = baseline_workflow
        sampler: MemorySampler | None = None
        cursor: Any = None
        peak_rss = baseline_rss
        peak_arrow = baseline_arrow
        peak_cgroup = 0
        batch_index = 0
        exhausted = False
        rows_seen = 0
        oversized_single_row = False
        oversized_row_bytes: int | None = None
        max_fetched_payload_bytes = 0
        batch_metrics = _empty_batch_metrics(encoded_line_applicable=False)
        try:
            fetch_size = _safe_connector_fetch_size(table, self.settings)
            # Query-before baseline and sampler start intentionally precede
            # cursor.execute so execute/fetch/Arrow/yield are one measured
            # interval.  The same snapshot is used for memory.stat deltas.
            stream_baseline_cgroup = (
                self.cgroup.snapshot() if self.cgroup is not None else None
            )
            sampler = MemorySampler(
                os.getpid(),
                lambda: self.supervisor.process.pid if self.supervisor.process is not None else None,
                self.cgroup,
                self.settings.memory_sample_interval_seconds,
                baselines={
                    "workflow_process_tree": workflow_peak,
                    "provider_process_tree": baseline_rss,
                    "arrow_memory_pool": baseline_arrow,
                    "cgroup": (
                        stream_baseline_cgroup.current_bytes
                        if stream_baseline_cgroup
                        else None
                    ),
                },
            )
            sampler.start()
            sampler.set_active(("first_10pct",))
            cursor = self._call(self._open_cursor(table.name, commit_id))
            # Fetch a small, explicit connector bound. The splitter consumes
            # the returned rows immediately and never materializes a
            # row-bound-sized pending result.
            plan = table_plan if table_plan is not None else compile_table_plan(table, policy)
            pending: list[NormalizedRow] = []
            pending_bytes = 0

            def emit(chunk: list[NormalizedRow]) -> pa.RecordBatch:
                nonlocal rows_seen, peak_arrow, workflow_peak, peak_rss, peak_cgroup, batch_index
                start = rows_seen
                end = rows_seen + len(chunk)
                windows = windows_for_interval(start, end, table.row_count)
                sampler.set_active(windows)
                sampler.sample(windows)
                if self.supervisor.process is not None:
                    peak_rss = max(peak_rss, process_tree_rss_kib(self.supervisor.process.pid))
                batch = plan.record_batch(chunk)
                batch_index += 1
                workflow_peak = max(workflow_peak, process_tree_rss_kib(os.getpid()))
                peak_arrow = max(peak_arrow, pa.default_memory_pool().bytes_allocated())
                if self.cgroup is not None:
                    current = self.cgroup.snapshot()
                    peak_cgroup = max(peak_cgroup, current.peak_bytes or 0)
                sampler.sample(windows)
                _observe_batch_metrics(
                    batch_metrics,
                    chunk,
                    row_bound=self.settings.record_batch_rows,
                    byte_bound=self.settings.record_batch_bytes,
                )
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
                    normalized_row = plan.normalize_row(tuple(raw_candidate))
                    candidate_bytes = normalized_row.logical_size_bytes
                    fetched_payload += candidate_bytes
                    max_fetched_payload_bytes = max(max_fetched_payload_bytes, fetched_payload)
                    chunks, pending, pending_bytes = accumulate_normalized_row(
                        pending,
                        pending_bytes,
                        normalized_row,
                        row_bound=self.settings.record_batch_rows,
                        byte_bound=self.settings.record_batch_bytes,
                    )
                    for chunk in chunks:
                        if len(chunk) == 1 and chunk[0].logical_size_bytes > self.settings.record_batch_bytes:
                            oversized_single_row = True
                            oversized_row_bytes = max(
                                oversized_row_bytes or 0,
                                chunk[0].logical_size_bytes,
                            )
                        yield emit(chunk)
                        sampler.sample()
                    if pending:
                        sampler.set_active(
                            _pending_row_windows(
                                rows_seen, len(pending) - 1, table.row_count
                            )
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
                "cleanup_connection_reset": reset,
                "batch_count": batch_index,
                "connector_fetch_row_bound": self.settings.connector_fetch_row_bound,
                "connector_fetch_size": fetch_size,
                "connector_max_fetched_payload_bytes": max_fetched_payload_bytes,
                "connector_fetch_payload_bound_ok": max_fetched_payload_bytes <= self.settings.record_batch_bytes
                or (fetch_size == 1 and oversized_single_row),
                "plateau_peaks": plateau,
                "plateau_peaks_absolute": self.last_plateau_peaks_absolute,
                **_baseline_memory_metrics(
                    baseline_workflow,
                    baseline_rss,
                    baseline_arrow,
                    stream_baseline_cgroup.current_bytes
                    if stream_baseline_cgroup
                    else None,
                ),
                **_cgroup_stream_metrics(
                    workflow_baseline_cgroup,
                    stream_baseline_cgroup,
                    final_cgroup,
                ),
                "oversized_single_row": oversized_single_row,
                "oversized_row_bytes": oversized_row_bytes,
                "byte_bound_reason": "single_indivisible_row" if oversized_single_row else None,
                **batch_metrics,
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
