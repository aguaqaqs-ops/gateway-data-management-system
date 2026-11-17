"""Offline Dolt CLI provider."""

from __future__ import annotations

import csv
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol
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
    DoltRunner,
    MemorySampler,
    ProcessStream,
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


def _write_query(directory: Path, sql: str, *, max_bytes: int) -> Path:
    raw = sql.encode("utf-8")
    if len(raw) > max_bytes:
        raise ProviderError("query scratch size exceeds configured limit")
    path = directory / f"query-{uuid4().hex}.sql"
    path.write_bytes(raw)
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
        self.query_directory = layout.query_directory
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
            max_bytes=self.settings.scratch_file_max_bytes,
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
