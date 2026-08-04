from __future__ import annotations

import asyncio
import datetime as dt
import decimal
import re
import subprocess
import sys
import pickle
import json
import os
import signal
import textwrap
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator, cast

import pyarrow as pa  # type: ignore[import-untyped]
import pytest
import gateway_repository_service.matrix as matrix_module
import gateway_repository_service.process as process_module
import gateway_repository_service.providers as providers_module
import gateway_repository_service.target_gate as target_gate_module

from gateway_repository_service.arrow_mapping import (
    ColumnCatalog,
    TableCatalog,
    UnknownTypePolicy,
    arrow_type,
    normalize_rows,
)
from gateway_repository_service.fixtures import (
    ScaleWorkload,
    Workload,
    generate_fixture,
    generate_scale_fixture,
)
from gateway_repository_service.layout import ProbeLayout
from gateway_repository_service.matrix import (
    BYTE_BOUND,
    V8_BYTE_BOUND,
    EXPECTED_SAMPLE_KINDS,
    NORMAL_WORKLOADS,
    ROW_BOUNDS,
    SCALE_WORKLOADS,
    V8_METHODOLOGY,
    _coverage,
    _bounded_stream_gate,
    _record_bounded_gate,
    _measurement_metadata,
    _observe_storage_record,
    _candidate_storage_provenance,
    _resolve_probe_data_root,
    _validate_target_storage_root,
    _w3_lifecycle_evidence_valid,
    _v8_batch_contract_valid,
    _v8_coverage,
    _v8_resource_advisory,
    _v8_ratio_observation,
    _summarize_v8,
    _support_envelope,
    run_a_paired_devnull_diagnostic,
    run_matrix,
    run_v8_a_w0_smoke,
    run_v8_matrix,
    run_scaling_diagnostic,
    _summarize,
)
from gateway_repository_service.process import (
    CgroupTopology,
    CgroupMemoryMeasurement,
    CgroupMemoryTracker,
    DiscardProcess,
    DoltRunner,
    ProcessBoundaryError,
    ProcessStream,
    MemorySampler,
    WorkflowCgroupScope,
    parse_dolt_version,
    preflight_cgroup,
    process_tree_pids,
    process_rss_breakdown_kib,
    process_tree_rss_breakdown_kib,
    windows_for_interval,
    resolve_current_cgroup,
)
from gateway_repository_service.providers import (
    OfflineCliProvider,
    SqlServerProvider,
    _safe_connector_fetch_size,
    _baseline_memory_metrics,
    _cgroup_stream_metrics,
    _parse_create_statement,
    _parse_tagged_row,
    _pending_row_windows,
    _rows_bytes,
    _observe_batch_metrics,
    _tagged_select_list,
)
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.storage import StorageLayout, StorageLayoutError
from gateway_repository_service.filesystem import storage_root_identity
from gateway_repository_service.filesystem import storage_snapshot
from gateway_repository_service.workflow import (
    Candidate,
    _expected_representative_flag,
    _wait_worker,
    _baseline_memory_coverage,
    _storage_delta,
    _workflow_correctness,
    _restart_provider_for_stream,
    run_workflow_isolated,
)
import gateway_repository_service.workflow_worker as workflow_worker
import gateway_repository_service.workflow as workflow_module


def test_authority_methodology_version_matches_settings() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    authority = repository_root / (
        "docs/backend-vnext/refactoring/formal/plans/"
        "p2-r1-runtime-provider-feasibility.md"
    )
    match = re.search(
        r"Measurement methodology version[:：]\s*`([^`]+)`",
        authority.read_text(encoding="utf-8"),
    )
    assert match is not None
    assert match.group(1) == RepositoryServiceSettings().v8_measurement_methodology_version


def _test_plateau_peaks() -> dict[str, dict[str, int]]:
    return {
        subject: {
            "first_10pct": 1,
            "middle_10pct": 1,
            "final_10pct": 1,
        }
        for subject in (
            "workflow_process_tree",
            "provider_process_tree",
            "arrow_memory_pool",
            "cgroup",
        )
    }


def test_candidate_a_sampler_spawn_and_provider_baseline_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []

    class FakeSampler:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.provider_pid = cast(Callable[[], int | None], _args[1])

        def start(self) -> None:
            events.append("sampler-start")

        def set_active(self, _windows: object) -> None:
            pass

        def set_baseline(self, subject: str, _value: int) -> None:
            if subject == "provider_process_tree":
                events.append("provider-baseline-injection")

        def sample(self, _windows: object = None) -> None:
            pass

        def stop(self) -> dict[str, dict[str, int]]:
            assert self.provider_pid() is None
            events.append("reaped-provider-not-sampled")
            return _test_plateau_peaks()

        def absolute_peaks(self) -> dict[str, dict[str, int]]:
            return _test_plateau_peaks()

    class FakeProcess:
        pid = 123
        returncode: int | None = None

        def poll(self) -> int | None:
            return self.returncode

    class FakeStream:
        process = FakeProcess()
        start_rss_kib = 1
        peak_rss_kib = 1

        @property
        def running_pid(self) -> int | None:
            return self.process.pid if self.process.poll() is None else None

        def __iter__(self) -> Iterator[bytes]:
            yield b"__gateway_null_0,__gateway_value_0\n"
            yield b"0,value\n"

        def close(self) -> SimpleNamespace:
            self.process.returncode = 0
            return SimpleNamespace(exit_code=0)

    class FakeRunner:
        def stream(self, *_args: object, **_kwargs: object) -> FakeStream:
            events.append("cli-spawn")
            return FakeStream()

    monkeypatch.setattr(providers_module, "MemorySampler", FakeSampler)

    def fake_rss(pid: int) -> int:
        if pid == 123:
            events.append("provider-baseline")
        return 1

    monkeypatch.setattr(providers_module, "process_tree_rss_kib", fake_rss)
    provider: Any = OfflineCliProvider.__new__(OfflineCliProvider)
    provider.settings = RepositoryServiceSettings(record_batch_rows=1)
    provider.repository = tmp_path / "repo"
    provider.query_directory = tmp_path
    provider.runner = FakeRunner()
    provider.cgroup = None
    provider.last_stream_peak_rss_kib = 0
    provider.last_stream_rss_delta_kib = 0
    provider.last_stream_metrics = {}
    provider.last_plateau_peaks = _test_plateau_peaks()
    provider.last_plateau_peaks_absolute = _test_plateau_peaks()
    table = TableCatalog("t", (ColumnCatalog("value", "VARCHAR(8)", False, None),), 1)

    list(provider.stream_table("commit", table, UnknownTypePolicy.REJECT))

    assert events.index("sampler-start") < events.index("cli-spawn")
    assert events.index("cli-spawn") < events.index("provider-baseline")
    assert events.index("provider-baseline") < events.index("provider-baseline-injection")
    assert "reaped-provider-not-sampled" in events


def test_process_stream_running_pid_excludes_reaped_child() -> None:
    class FakeProcess:
        pid = 123
        returncode: int | None = None

        def poll(self) -> int | None:
            return self.returncode

    stream: Any = ProcessStream.__new__(ProcessStream)
    stream.process = FakeProcess()
    stream._lifecycle_lock = threading.Lock()
    assert stream.running_pid == 123
    stream.process.returncode = 0
    assert stream.running_pid is None


@pytest.mark.parametrize("process_kind", ("stream", "discard"))
def test_internal_rss_monitor_stops_before_process_reap(
    process_kind: str,
) -> None:
    events: list[str] = []

    class FakeProcess:
        pid = 123
        returncode: int | None = None
        stdout = None
        stderr = None

        def poll(self) -> None:
            return None

        def wait(self) -> None:
            events.append("wait")
            self.returncode = 0

    process = FakeProcess()
    def terminate_and_reap(_process: object) -> None:
        events.append("reap")
        process.returncode = 0

    runner = SimpleNamespace(
        settings=SimpleNamespace(
            terminate_grace_seconds=0.01,
        ),
        terminate_and_reap=terminate_and_reap,
        reap_adopted_dolt_children=lambda: events.append("adopted-reap"),
    )
    obj: Any = (
        ProcessStream.__new__(ProcessStream)
        if process_kind == "stream"
        else DiscardProcess.__new__(DiscardProcess)
    )
    obj.runner = runner
    obj.process = process
    obj.command_kind = "test"
    obj.started = time.monotonic() - 1
    obj.timeout = 0
    obj._closed = False
    obj._lifecycle_lock = threading.Lock()
    obj._stop_rss_monitor = lambda: events.append("monitor-stop")
    obj._stderr_thread = SimpleNamespace(join=lambda **_kwargs: events.append("stderr-join"))
    obj.stderr_tail = SimpleNamespace(value=lambda: b"")
    obj.start_rss_kib = 0
    obj.peak_rss_kib = 0
    obj.start_rss_anon_kib = 0
    obj.start_rss_file_kib = 0
    obj.peak_rss_anon_kib = 0
    obj.peak_rss_file_kib = 0

    obj.close()

    assert events.index("monitor-stop") < events.index("reap")


@pytest.mark.parametrize("process_kind", ("stream", "discard"))
def test_internal_rss_monitor_cannot_sample_after_stop_before_reap(
    process_kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stopped internal monitor cannot attribute a reused PID to the child."""

    sample_started = threading.Event()
    release_sample = threading.Event()
    sampled_returncodes: list[int | None] = []

    class FakeProcess:
        pid = 123
        returncode: int | None = None

    process = FakeProcess()

    def sample(_pid: int) -> int:
        sampled_returncodes.append(process.returncode)
        sample_started.set()
        release_sample.wait(timeout=1.0)
        return 1

    monkeypatch.setattr(process_module, "process_tree_rss_kib", sample)
    monkeypatch.setattr(
        process_module,
        "process_tree_rss_breakdown_kib",
        lambda _pid: {"rss_anon_kib": 1, "rss_file_kib": 0},
    )

    obj: Any = (
        ProcessStream.__new__(ProcessStream)
        if process_kind == "stream"
        else DiscardProcess.__new__(DiscardProcess)
    )
    obj.process = process
    obj._lifecycle_lock = threading.Lock()
    obj._monitor_stop = threading.Event()
    obj._monitor_thread = threading.Thread(
        target=(obj._monitor_rss if process_kind == "stream" else obj._monitor),
        daemon=True,
    )
    obj.peak_rss_kib = 0
    obj.peak_rss_anon_kib = 0
    obj.peak_rss_file_kib = 0
    obj._monitor_thread.start()
    assert sample_started.wait(timeout=1.0)

    stopper = threading.Thread(target=obj._stop_rss_monitor)
    stopper.start()
    release_sample.set()
    stopper.join(timeout=1.0)
    assert not stopper.is_alive()
    assert not obj._monitor_thread.is_alive()

    # Simulate wait/reap and immediate PID reuse only after the monitor has
    # joined.  No sample may be attributed to the post-reap process.
    process.returncode = 0
    time.sleep(0.03)
    assert sampled_returncodes == [None]


def test_scaling_diagnostic_publishes_total_record_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    records = [
        {
            "candidate": Candidate.B.value,
            "workload": "S10",
            "record_batch_row_bound": 256,
            "sample_kind": "warmup",
            "matrix_kind": "scaling",
        },
        {
            "candidate": Candidate.B.value,
            "workload": "S10",
            "record_batch_row_bound": 256,
            "sample_kind": "measured-1",
            "matrix_kind": "scaling",
        },
    ]
    monkeypatch.setattr(matrix_module, "_collect_scaling_records", lambda *_args, **_kwargs: records)
    monkeypatch.setattr(matrix_module, "_annotate_storage", lambda _records: None)
    monkeypatch.setattr(matrix_module, "_summarize", lambda *_args, **_kwargs: {"records": 0})
    monkeypatch.setattr(matrix_module, "_write_artifacts", lambda *_args, **_kwargs: None)
    summary = run_scaling_diagnostic(RepositoryServiceSettings(), tmp_path / "scaling.jsonl")
    assert summary["records"] == 2
    assert summary["scaling_records"] == 2
    assert summary["unique_measurement_keys"] == 2


def test_candidate_b_sampler_precedes_cursor_execute(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []

    class FakeSampler:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def start(self) -> None:
            events.append("sampler-start")

        def set_active(self, _windows: object) -> None:
            pass

        def sample(self, _windows: object = None) -> None:
            pass

        def stop(self) -> dict[str, dict[str, int]]:
            return _test_plateau_peaks()

        def absolute_peaks(self) -> dict[str, dict[str, int]]:
            return _test_plateau_peaks()

    class FakeCursor:
        def __init__(self) -> None:
            self.calls = 0

        async def fetchmany(self, _size: int) -> list[tuple[str, ...]]:
            self.calls += 1
            return [("value",)] if self.calls == 1 else []

        async def close(self) -> None:
            pass

    cursor = FakeCursor()

    async def open_cursor(_table: str, _commit_id: str) -> FakeCursor:
        events.append("cursor-execute")
        return cursor

    monkeypatch.setattr(providers_module, "MemorySampler", FakeSampler)
    monkeypatch.setattr(providers_module, "process_tree_rss_kib", lambda _pid: 1)
    provider: Any = SqlServerProvider.__new__(SqlServerProvider)
    provider.settings = RepositoryServiceSettings(record_batch_rows=1)
    provider.repository = tmp_path / "repo"
    provider.query_directory = tmp_path
    provider.supervisor = SimpleNamespace(process=SimpleNamespace(pid=456))
    provider.cgroup = None
    provider.last_stream_peak_rss_kib = 0
    provider.last_stream_rss_delta_kib = 0
    provider.last_stream_metrics = {}
    provider.last_plateau_peaks = _test_plateau_peaks()
    provider.last_plateau_peaks_absolute = _test_plateau_peaks()
    provider._open_cursor = open_cursor
    provider._call = lambda coroutine: asyncio.run(coroutine)
    table = TableCatalog("t", (ColumnCatalog("value", "VARCHAR(8)", False, None),), 1)

    list(provider.stream_table("commit", table, UnknownTypePolicy.REJECT))

    assert events.index("sampler-start") < events.index("cursor-execute")


def test_restart_diagnostic_closes_old_opens_new_then_streams(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []

    class FakeProvider:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            events.append(f"{self.name}-close")

        def open(self) -> None:
            events.append(f"{self.name}-open")

        def head(self) -> str:
            return "new"

        def catalog(self, _initial: str, _new: str) -> tuple[TableCatalog, ...]:
            return ()

        def stream_table(self, *_args: object, **_kwargs: object) -> Iterator[Any]:
            events.append(f"{self.name}-stream")
            return iter(())

    replacement = FakeProvider("new")

    def fake_factory(*_args: object, **_kwargs: object) -> FakeProvider:
        events.append("new-provider")
        return replacement

    monkeypatch.setattr(workflow_module, "_make_provider", fake_factory)
    layout = ProbeLayout.create(tmp_path / "layout")
    old: Any = FakeProvider("old")
    current = _restart_provider_for_stream(
        RepositoryServiceSettings(),
        layout,
        tmp_path / "target",
        Candidate.B,
        old,
        initial_commit="initial",
        new_commit="new",
        actual_catalog=(),
    )
    list(current.stream_table("new", TableCatalog("t", (), 0), UnknownTypePolicy.REJECT))

    assert events == ["old-close", "new-provider", "new-open", "new-stream"]


def test_discard_diagnostic_uses_target_root_and_persists_provenance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target_root = tmp_path / "named-volume-root"
    target_root.mkdir()
    captured_roots: list[Path] = []
    digest = "sha256:" + "a" * 64
    revision = "b" * 40

    monkeypatch.setenv("GATEWAY_P2R1_TARGET_CONTAINER", "1")
    monkeypatch.setattr(
        matrix_module,
        "_resolve_probe_data_root",
        lambda _settings, _data_root, target: target_root if target else None,
    )
    monkeypatch.setattr(
        matrix_module,
        "_measurement_metadata",
        lambda *_args, **_kwargs: {
            "measurement_methodology_version": "p2-r1-audit-corrective-v7",
            "image_digest": digest,
            "build_revision": revision,
            "cache_condition": "retained-dependency-cache",
            "metadata_complete": True,
        },
    )
    monkeypatch.setattr(
        matrix_module,
        "_diagnostic_storage_metadata",
        lambda _root, *, target_container: {
            "filesystem_type": "xfs",
            "volume_backend": "volume",
            "storage_root_identity": _TEST_STORAGE_IDENTITY,
            "storage_mount_verified": target_container,
            "storage_layout_version": "p2-r1-storage-layout-v1",
            "storage_volume_project": "gateway-p2r1-test",
        },
    )

    def fake_discard(
        _settings: RepositoryServiceSettings,
        fixture: Any,
        *,
        root_parent: Path,
    ) -> dict[str, object]:
        captured_roots.append(root_parent)
        return {
            "candidate": Candidate.A.value,
            "workload": fixture.workload.value,
            "fixture_rows": fixture.rows,
        }

    monkeypatch.setattr(matrix_module, "run_offline_discard_diagnostic", fake_discard)
    output = tmp_path / "discard.jsonl"
    summary = matrix_module.run_offline_discard_diagnostic_matrix(
        RepositoryServiceSettings(),
        output,
        image_digest=digest,
        build_revision=revision,
        cache_condition="retained-dependency-cache",
    )

    assert captured_roots == [target_root] * len(SCALE_WORKLOADS)
    assert summary["methodology_version"] == "p2-r1-audit-corrective-v7"
    environment = cast(dict[str, object], summary["measurement_environment"])
    assert environment["image_digests"] == [digest]
    assert environment["build_revisions"] == [revision]
    assert environment["storage_mount_verified"] is True
    raw = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(raw) == len(SCALE_WORKLOADS)
    assert all(row["image_digest"] == digest for row in raw)
    assert all(row["build_revision"] == revision for row in raw)
    assert all(row["storage_mount_verified"] is True for row in raw)


@pytest.mark.parametrize("failure_stage", ["open", "head", "catalog"])
def test_restart_replacement_closes_on_validation_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure_stage: str
) -> None:
    events: list[str] = []

    class FailingReplacement:
        def open(self) -> None:
            events.append("replacement-open")
            if failure_stage == "open":
                raise RuntimeError("open failure")

        def head(self) -> str:
            events.append("replacement-head")
            if failure_stage == "head":
                raise RuntimeError("head failure")
            return "new"

        def catalog(self, _initial: str, _new: str) -> tuple[TableCatalog, ...]:
            events.append("replacement-catalog")
            if failure_stage == "catalog":
                raise RuntimeError("catalog failure")
            return ()

        def close(self) -> None:
            events.append("replacement-close")

    class PreviousProvider:
        def close(self) -> None:
            events.append("previous-close")

    replacement = FailingReplacement()
    monkeypatch.setattr(
        workflow_module,
        "_make_provider",
        lambda *_args, **_kwargs: replacement,
    )
    layout = ProbeLayout.create(tmp_path / "layout")

    with pytest.raises(RuntimeError):
        _restart_provider_for_stream(
            RepositoryServiceSettings(),
            layout,
            tmp_path / "target",
            Candidate.B,
            cast(Any, PreviousProvider()),
            initial_commit="initial",
            new_commit="new",
            actual_catalog=(),
        )

    assert events[0] == "previous-close"
    assert events[-1] == "replacement-close"


def test_sized_character_and_binary_types_are_known() -> None:
    assert arrow_type("CHAR(4)", UnknownTypePolicy.REJECT)[0] == pa.string()
    assert arrow_type("VARCHAR(32)", UnknownTypePolicy.REJECT)[0] == pa.string()
    assert arrow_type("BINARY(2)", UnknownTypePolicy.REJECT)[0] == pa.binary()
    assert arrow_type("VARBINARY(8)", UnknownTypePolicy.REJECT)[0] == pa.binary()


def test_tagged_csv_distinguishes_null_empty_literal_and_binary() -> None:
    table = TableCatalog(
        "t",
        (
            ColumnCatalog("text_value", "VARCHAR(8)", True, None),
            ColumnCatalog("bytes_value", "VARBINARY(8)", True, None),
        ),
        4,
    )
    _, header = _tagged_select_list(table)
    assert header == [
        "__gateway_null_0",
        "__gateway_value_0",
        "__gateway_null_1",
        "__gateway_value_1",
    ]
    assert _parse_tagged_row(["1", "", "1", ""], table) == (None, None)
    assert _parse_tagged_row(["0", "", "0", ""], table) == ("", b"")
    assert _parse_tagged_row(["0", "NULL", "0", "00FF"], table) == ("NULL", b"\x00\xff")


def test_provider_baseline_metrics_use_one_canonical_schema() -> None:
    metrics = _baseline_memory_metrics(11, 22, 0, 44)
    assert metrics == {
        "baseline_workflow_process_tree_rss_kib": 11,
        "baseline_provider_process_tree_rss_kib": 22,
        "baseline_arrow_memory_pool_bytes": 0,
        "cgroup_baseline_current_bytes": 44,
    }


def test_cgroup_stat_delta_uses_stream_baseline_and_retains_workflow_baseline() -> None:
    workflow = CgroupMemoryMeasurement(
        current_bytes=100,
        peak_bytes=120,
        baseline_peak_bytes=90,
        reset_current_baseline_bytes=100,
        anon_bytes=70,
        file_bytes=30,
        baseline_anon_bytes=40,
        baseline_file_bytes=20,
        anon_delta_bytes=30,
        file_delta_bytes=10,
        scope_identity="sha256:" + "a" * 64,
        available=True,
        per_workflow=True,
    )
    stream = CgroupMemoryMeasurement(
        current_bytes=200,
        peak_bytes=220,
        baseline_peak_bytes=90,
        reset_current_baseline_bytes=100,
        anon_bytes=140,
        file_bytes=80,
        baseline_anon_bytes=40,
        baseline_file_bytes=20,
        anon_delta_bytes=100,
        file_delta_bytes=60,
        scope_identity="sha256:" + "a" * 64,
        available=True,
        per_workflow=True,
    )
    final = CgroupMemoryMeasurement(
        current_bytes=250,
        peak_bytes=280,
        baseline_peak_bytes=90,
        reset_current_baseline_bytes=100,
        anon_bytes=155,
        file_bytes=95,
        baseline_anon_bytes=40,
        baseline_file_bytes=20,
        anon_delta_bytes=115,
        file_delta_bytes=75,
        scope_identity="sha256:" + "a" * 64,
        available=True,
        per_workflow=True,
    )
    metrics = _cgroup_stream_metrics(workflow, stream, final)
    assert metrics["cgroup_workflow_baseline_stat_anon_bytes"] == 40
    assert metrics["cgroup_workflow_baseline_stat_file_bytes"] == 20
    assert metrics["cgroup_baseline_stat_anon_bytes"] == 140
    assert metrics["cgroup_baseline_stat_file_bytes"] == 80
    assert metrics["cgroup_stat_anon_delta_bytes"] == 15
    assert metrics["cgroup_stat_file_delta_bytes"] == 15


def test_pending_row_windows_advance_within_1024_row_batches() -> None:
    total_rows = 10_000
    assert _pending_row_windows(0, 999, total_rows) == ("first_10pct",)
    assert _pending_row_windows(0, 1_000, total_rows) == ()
    assert _pending_row_windows(4_096, 403, total_rows) == ()
    assert _pending_row_windows(4_096, 404, total_rows) == ("middle_10pct",)
    assert _pending_row_windows(8_192, 807, total_rows) == ()
    assert _pending_row_windows(8_192, 808, total_rows) == ("final_10pct",)


def test_baseline_coverage_requires_canonical_arrow_field() -> None:
    complete = _baseline_memory_metrics(11, 22, 0, 44)
    assert _baseline_memory_coverage(dict(complete))

    legacy_only = dict(complete)
    del legacy_only["baseline_arrow_memory_pool_bytes"]
    legacy_only["arrow_memory_pool_baseline_bytes"] = 0
    assert not _baseline_memory_coverage(legacy_only)


def test_target_probe_root_uses_settings_data_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "named-volume"
    root.mkdir()
    manifest = StorageLayout(
        "p2-r1-storage-layout-v1",
        root,
        root,
        "volume",
        True,
        "project_repository-data",
        "project",
        storage_root_identity(root),
        "xfs",
    )
    monkeypatch.setattr(matrix_module, "_load_storage_layout", lambda: manifest)
    monkeypatch.setenv("GATEWAY_P2R1_PROJECT_NAME", "project")
    settings = RepositoryServiceSettings(data_root=root)
    assert _resolve_probe_data_root(settings, None, True) == root
    assert _resolve_probe_data_root(settings, None, False) is None
    with pytest.raises(RuntimeError, match="data root"):
        _resolve_probe_data_root(settings, tmp_path / "explicit", True)


def test_target_probe_root_rejects_overlay_or_unverified_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "named-volume"
    root.mkdir()
    manifest = StorageLayout(
        "p2-r1-storage-layout-v1",
        root,
        root,
        "volume",
        True,
        "project_repository-data",
        "project",
        storage_root_identity(root),
        "overlayfs",
    )
    monkeypatch.setattr(matrix_module, "_load_storage_layout", lambda: manifest)
    monkeypatch.setenv("GATEWAY_P2R1_PROJECT_NAME", "project")
    with pytest.raises(RuntimeError, match="overlayfs"):
        _validate_target_storage_root(root)
    readonly = StorageLayout(
        "p2-r1-storage-layout-v1",
        root,
        root,
        "volume",
        False,
        "project_repository-data",
        "project",
        storage_root_identity(root),
        "xfs",
    )
    monkeypatch.setattr(matrix_module, "_load_storage_layout", lambda: readonly)
    with pytest.raises(RuntimeError, match="writable named volume"):
        _validate_target_storage_root(root)


def test_volume_backend_environment_alone_cannot_prove_target_mount(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "named-volume"
    root.mkdir()
    monkeypatch.setenv("GATEWAY_P2R1_VOLUME_BACKEND", "named-volume")
    monkeypatch.delenv("GATEWAY_P2R1_STORAGE_LAYOUT", raising=False)
    monkeypatch.setattr(matrix_module, "_load_storage_layout", lambda: None)
    with pytest.raises(RuntimeError, match="manifest"):
        _validate_target_storage_root(root)


def test_summary_storage_environment_comes_from_raw_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        matrix_module,
        "_filesystem_type",
        lambda _path=Path("."): (_ for _ in ()).throw(AssertionError("cwd was measured")),
    )
    summary = _summarize(
        [
            {
                "filesystem_type": "xfs",
                "volume_backend": "volume",
                "storage_root_identity": "sha256:" + "1" * 64,
                "storage_mount_verified": True,
            }
        ],
        RepositoryServiceSettings(),
    )
    environment = summary["measurement_environment"]
    assert isinstance(environment, dict)
    assert environment["filesystem_types"] == ["xfs"]
    assert environment["volume_backends"] == ["volume"]
    assert environment["storage_mount_verified"] is True


def test_storage_layout_rejects_wrong_project_or_destination(tmp_path: Path) -> None:
    root = tmp_path / "volume"
    root.mkdir()
    manifest = StorageLayout(
        "p2-r1-storage-layout-v1",
        root,
        root,
        "volume",
        True,
        "project_repository-data",
        "project",
        storage_root_identity(root),
        "xfs",
    )
    with pytest.raises(StorageLayoutError, match="another Compose project"):
        manifest.validate_root(root, project="other")
    with pytest.raises(StorageLayoutError, match="data root"):
        manifest.validate_root(tmp_path / "other", project="project")


def test_pinned_create_parser_preserves_schema_mutation_shape() -> None:
    old = _parse_create_statement(
        "CREATE TABLE `records` (`id` int NOT NULL, `payload` varchar(8), PRIMARY KEY (`id`));",
        2,
    )
    new = _parse_create_statement(
        "CREATE TABLE `records` (`id` int NOT NULL, `payload` varchar(8), `extra` char(4) NULL, PRIMARY KEY (`id`));",
        2,
    )
    assert [column.name for column in old.columns] == ["id", "payload"]
    assert [column.name for column in new.columns] == ["id", "payload", "extra"]
    assert old != new


def test_provider_pinned_catalog_does_not_return_new_column_for_old_commit(tmp_path: Path) -> None:
    settings = RepositoryServiceSettings()
    layout = ProbeLayout.create(tmp_path / "root")
    repository = layout.staging_repository("d" * 32, "schema")
    provider = OfflineCliProvider(settings, layout, repository, DoltRunner(settings, layout.root))
    provider.initialize_repository()
    initial = provider.head()
    old_sql = tmp_path / "old.sql"
    old_sql.write_text("CREATE TABLE records (id INT NOT NULL PRIMARY KEY, payload VARCHAR(8));")
    provider.replay(old_sql)
    old_commit = provider.commit_marker("old")
    new_sql = tmp_path / "new.sql"
    new_sql.write_text("ALTER TABLE records ADD COLUMN extra CHAR(4) NULL;")
    provider.replay(new_sql)
    new_commit = provider.commit_marker("new")
    old_catalog = provider.catalog(initial, old_commit)
    new_catalog = provider.catalog(initial, new_commit)
    assert [column.name for column in old_catalog[0].columns] == ["id", "payload"]
    assert [column.name for column in new_catalog[0].columns] == ["id", "payload", "extra"]


def test_scale_fixture_has_same_shape_and_deterministic_rows(tmp_path: Path) -> None:
    first = generate_scale_fixture(tmp_path / "a", ScaleWorkload.S10)
    second = generate_scale_fixture(tmp_path / "b", ScaleWorkload.S10)
    assert first.expected_tables == second.expected_tables
    assert first.replay_sql.read_bytes() == second.replay_sql.read_bytes()
    assert first.expected_tables[0].columns == second.expected_tables[0].columns


def test_process_stream_timeout_during_blocked_wait() -> None:
    settings = RepositoryServiceSettings(output_capture_bytes=64)
    runner = DoltRunner.__new__(DoltRunner)
    runner.settings = settings
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2)"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stream = ProcessStream(runner, process, "test_timeout", 0.05)
    with pytest.raises(TimeoutError):
        next(iter(stream))
    assert process.poll() is not None


def test_process_stream_rejects_unterminated_oversized_line() -> None:
    settings = RepositoryServiceSettings(output_capture_bytes=32)
    runner = DoltRunner.__new__(DoltRunner)
    runner.settings = settings
    process = subprocess.Popen(
        [sys.executable, "-c", "import sys,time; sys.stdout.write('x'*128); sys.stdout.flush(); time.sleep(1)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stream = ProcessStream(runner, process, "test_line_bound", 1.0)
    with pytest.raises(Exception, match="output limit"):
        next(iter(stream))
    assert process.poll() is not None


def test_process_tree_and_cgroup_measurement_scope(tmp_path: Path) -> None:
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.2)"])
    try:
        assert child.pid in process_tree_pids(child.pid)
    finally:
        child.terminate()
        child.wait()
    cgroup = tmp_path / "cgroup"
    cgroup.mkdir()
    (cgroup / "memory.current").write_text("100")
    (cgroup / "memory.peak").write_text("200")
    (cgroup / "memory.stat").write_text("anon 70\nfile 30\n")
    with CgroupMemoryTracker(cgroup) as tracker:
        assert tracker.per_workflow
        measurement = tracker.snapshot()
        assert measurement.available
        assert measurement.reset_current_baseline_bytes == 100
        assert measurement.anon_bytes == 70
        assert measurement.file_bytes == 30
        assert measurement.baseline_anon_bytes == 70
        assert measurement.baseline_file_bytes == 30
        assert measurement.anon_delta_bytes == 0
        assert measurement.file_delta_bytes == 0


def test_representative_flag_oracle_matches_fixture_index_distribution() -> None:
    assert _expected_representative_flag(1) is None
    assert _expected_representative_flag(2) is True
    assert _expected_representative_flag(3) is False
    assert _expected_representative_flag(18) is None
    assert _expected_representative_flag(19) is False


def test_bounded_evidence_failure_does_not_mask_workflow_correctness() -> None:
    assert _workflow_correctness(
        {
            "workflow": True,
            "cancellation": True,
            "restart": True,
            "unknown_type": True,
            "bounded_stream": False,
        }
    )
    assert not _workflow_correctness(
        {
            "workflow": False,
            "cancellation": True,
            "restart": True,
            "unknown_type": True,
            "bounded_stream": True,
        }
    )


def test_worker_wait_reaps_adopted_dolt_children(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reaped: list[bool] = []
    monkeypatch.setattr(
        DoltRunner,
        "reap_adopted_dolt_children",
        staticmethod(lambda: reaped.append(True)),
    )
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    status = _wait_worker(child.pid, RepositoryServiceSettings())
    assert os.waitstatus_to_exitcode(status) == 0
    assert reaped


def test_workflow_cgroup_cleanup_terminates_residual_members(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "samples"
    root.mkdir()
    scope = WorkflowCgroupScope(root, grace_seconds=0.01)
    scope.create()
    assert scope.path is not None
    procs = scope.path / "cgroup.procs"
    procs.write_text("123\n", encoding="ascii")
    killed: list[tuple[int, signal.Signals]] = []
    def fake_kill(pid: int, signum: int) -> None:
        killed.append((pid, signal.Signals(signum)))
        procs.write_text("", encoding="ascii")

    monkeypatch.setattr(os, "kill", fake_kill)
    real_rmdir = os.rmdir

    def fake_rmdir(path: str | os.PathLike[str]) -> None:
        Path(path).joinpath("cgroup.procs").unlink()
        real_rmdir(path)

    monkeypatch.setattr(os, "rmdir", fake_rmdir)
    scope.cleanup()
    assert killed == [(123, signal.SIGTERM)]
    assert not scope.active


def test_cgroup_stat_baseline_and_delta_are_distinct(tmp_path: Path) -> None:
    cgroup = tmp_path / "cgroup"
    cgroup.mkdir()
    (cgroup / "memory.current").write_text("100")
    (cgroup / "memory.peak").write_text("200")
    (cgroup / "memory.stat").write_text("anon 70\nfile 30\n")
    with CgroupMemoryTracker(cgroup) as tracker:
        (cgroup / "memory.stat").write_text("anon 90\nfile 50\n")
        measurement = tracker.snapshot()
    assert measurement.baseline_anon_bytes == 70
    assert measurement.baseline_file_bytes == 30
    assert measurement.anon_bytes == 90
    assert measurement.file_bytes == 50
    assert measurement.anon_delta_bytes == 20
    assert measurement.file_delta_bytes == 20


def test_resolve_current_cgroup_uses_actual_control_group(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mount = tmp_path / "delegated"
    exact = mount / "docker-test.scope"
    exact.mkdir(parents=True)
    monkeypatch.setenv(
        "GATEWAY_REPOSITORY_CGROUP_CONTROL_GROUP",
        "/system.slice/gateway-p2r1.slice",
    )
    monkeypatch.setattr(
        process_module,
        "current_cgroup_membership",
        lambda _pid=None: "/system.slice/gateway-p2r1.slice/docker-test.scope",
    )
    assert resolve_current_cgroup(mount) == exact


def test_cgroup_topology_requires_empty_root_sibling_paths() -> None:
    topology = CgroupTopology.from_dict(
        {
            "layout_version": "p2-r1-cgroup-layout-v1",
            "delegated_root": "/sys/fs/cgroup/gateway-p2r1/container.scope",
            "supervisor": "/sys/fs/cgroup/gateway-p2r1/container.scope/supervisor",
            "samples": "/sys/fs/cgroup/gateway-p2r1/container.scope/samples",
            "parent_control_group": "/gateway-p2r1.slice/gateway-p2r1-runner.slice",
            "slice_control_group": "/gateway-p2r1.slice",
            "service_control_group": "/gateway-p2r1.slice/gateway-p2r1-runner.slice/runner.service",
            "delegated_control_group": "/gateway-p2r1.slice/gateway-p2r1-runner.slice/container.scope",
            "supervisor_control_group": "/gateway-p2r1.slice/gateway-p2r1-runner.slice/container.scope/supervisor",
        }
    )
    assert topology.supervisor.parent == topology.delegated_root
    assert topology.samples.parent == topology.delegated_root
    with pytest.raises(Exception, match="siblings"):
        CgroupTopology.from_dict(
            {
                "layout_version": "p2-r1-cgroup-layout-v1",
                "delegated_root": "/root",
                "supervisor": "/root/supervisor",
                "samples": "/root/supervisor/samples",
                "parent_control_group": "/parent/gateway-p2r1-runner.slice",
                "slice_control_group": "/parent",
                "service_control_group": "/parent/gateway-p2r1-runner.slice/runner.service",
                "delegated_control_group": "/parent/gateway-p2r1-runner.slice/container",
                "supervisor_control_group": "/parent/gateway-p2r1-runner.slice/container/supervisor",
            }
        )


def test_formal_matrix_does_not_resolve_current_cgroup(monkeypatch: pytest.MonkeyPatch) -> None:
    source = matrix_module.run_matrix.__code__.co_names
    assert "resolve_current_cgroup" not in source


def test_target_gate_propagates_verified_supervisor_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    layout = {
        "layout_version": "p2-r1-cgroup-layout-v1",
        "delegated_root": "/sys/fs/cgroup/container.scope",
        "supervisor": "/sys/fs/cgroup/container.scope/supervisor",
        "samples": "/sys/fs/cgroup/container.scope/samples",
        "parent_control_group": "/slice/gateway-p2r1-runner.slice",
        "slice_control_group": "/slice",
        "service_control_group": "/slice/gateway-p2r1-runner.slice/runner.service",
        "delegated_control_group": "/slice/gateway-p2r1-runner.slice/container.scope",
        "supervisor_control_group": "/slice/gateway-p2r1-runner.slice/container.scope/supervisor",
    }
    (tmp_path / "cgroup-layout.json").write_text(json.dumps(layout), encoding="utf-8")
    (tmp_path / "argv.json").write_text(json.dumps(["--output", "/tmp/result.jsonl"]), encoding="utf-8")
    (tmp_path / "release").touch()
    monkeypatch.setenv("GATEWAY_P2R1_TARGET_CONTAINER", "1")
    monkeypatch.setattr(
        process_module,
        "current_cgroup_membership",
        lambda _pid=None: layout["supervisor_control_group"],
    )
    captured: dict[str, str | list[str]] = {}
    monkeypatch.setattr(
        os,
        "execv",
        lambda executable, argv: captured.update(executable=executable, argv=argv),
    )
    target_gate_module.main(tmp_path)
    assert cast(list[str], captured["argv"])[-1] == "/tmp/result.jsonl"
    assert os.environ["GATEWAY_REPOSITORY_CGROUP_LAYOUT_VERIFIED"] == "1"
    assert (
        os.environ["GATEWAY_REPOSITORY_CGROUP_SUPERVISOR_CONTROL_GROUP"]
        == layout["supervisor_control_group"]
    )
    monkeypatch.delenv("GATEWAY_REPOSITORY_CGROUP_LAYOUT_VERIFIED", raising=False)
    monkeypatch.delenv("GATEWAY_REPOSITORY_CGROUP_SUPERVISOR_CONTROL_GROUP", raising=False)
    monkeypatch.delenv("GATEWAY_REPOSITORY_CGROUP_DELEGATED_CONTROL_GROUP", raising=False)


def test_formal_workflow_requires_propagated_supervisor_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GATEWAY_P2R1_TARGET_CONTAINER", "1")
    monkeypatch.delenv("GATEWAY_REPOSITORY_CGROUP_SUPERVISOR_CONTROL_GROUP", raising=False)
    monkeypatch.delenv("GATEWAY_REPOSITORY_CGROUP_LAYOUT_VERIFIED", raising=False)
    fixture = generate_fixture(tmp_path / "fixture", Workload.W0)
    with pytest.raises(ProcessBoundaryError, match="cgroup identity"):
        run_workflow_isolated(
            RepositoryServiceSettings(cgroup_root=tmp_path / "cgroup"),
            Candidate.A,
            fixture,
            sample_kind="warmup",
        )
    monkeypatch.delenv("GATEWAY_P2R1_TARGET_CONTAINER", raising=False)


def test_launcher_uses_unique_project_for_every_compose_lifecycle_command() -> None:
    launcher = Path(__file__).parents[2] / "deploy/p2r1-cache/p2r1-target-launcher.sh"
    compose_lines = [
        line.strip()
        for line in launcher.read_text(encoding="utf-8").splitlines()
        if "docker compose" in line
    ]
    assert compose_lines
    assert all('-p "$PROJECT_NAME"' in line for line in compose_lines)
    assert "down --remove-orphans" not in launcher.read_text(encoding="utf-8")


def test_launcher_links_docker_to_per_run_slice_and_exports_before_down() -> None:
    launcher = Path(__file__).parents[2] / "deploy/p2r1-cache/p2r1-target-launcher.sh"
    source = launcher.read_text(encoding="utf-8")
    compose = (launcher.parents[2] / "deploy/compose.yaml").read_text(encoding="utf-8")
    assert 'systemctl show "$UNIT" -p ControlGroup --value' in source
    assert 'GATEWAY_P2R1_CGROUP_PARENT="$PARENT_SLICE"' in source
    assert 'grep -Eq \'^gateway-p2r1-[a-z0-9][a-z0-9_]*\\.slice$\'' in source
    assert 'GATEWAY_P2R1_CGROUP_PARENT:-/gateway-p2r1-unconfigured.service' not in source
    assert "cgroup_parent: ${GATEWAY_P2R1_CGROUP_PARENT:-gateway-p2r1-unconfigured.slice}" in compose
    assert "    entrypoint: []" in compose
    assert 'docker cp "$container_id:$raw_target"' in source
    assert "--profile p2-r1 down -v" in source
    assert "export_artifacts || true" not in source
    assert "supervisor_cgroup/cgroup.subtree_control" not in source


def test_launcher_stops_before_export_and_preserves_volume_on_failure() -> None:
    launcher = Path(__file__).parents[2] / "deploy/p2r1-cache/p2r1-target-launcher.sh"
    source = launcher.read_text(encoding="utf-8")
    assert "stop_target_and_wait" in source
    assert "docker stop -t 5" in source
    assert "docker kill" in source
    assert "down;" in source
    assert "retaining probe volume" in source
    assert "recovery quarantine project=" in source
    assert 'ARTIFACT_EXPORT_FAILED" -eq 0' in source


def test_launcher_uses_positive_clean_residual_predicates() -> None:
    launcher = Path(__file__).parents[2] / "deploy/p2r1-cache/p2r1-target-launcher.sh"
    source = launcher.read_text(encoding="utf-8")
    assert "project_runtime_is_clean()" in source
    assert "project_is_clean()" in source
    assert "project_runtime_has_residuals" not in source
    assert "project_has_residuals" not in source
    assert "if project_is_clean; then" in source
    assert "if project_runtime_is_clean; then" in source
    assert "if ! project_is_clean; then" not in source
    assert "if ! project_runtime_is_clean; then" not in source


def test_launcher_run_id_cannot_add_a_systemd_slice_level() -> None:
    launcher = Path(__file__).parents[2] / "deploy/p2r1-cache/p2r1-target-launcher.sh"
    source = launcher.read_text(encoding="utf-8")
    assert 'RUN_ID="$(date +%Y%m%d%H%M%S)_$$"' in source
    assert 'RUN_ID="$(date +%Y%m%d%H%M%S)-$$"' not in source


def test_launcher_cleanup_residual_semantics_with_stub_docker(tmp_path: Path) -> None:
    """Exercise success/failure cleanup branches with project-scoped fake Docker state."""

    launcher = Path(__file__).parents[2] / "deploy/p2r1-cache/p2r1-target-launcher.sh"
    source = launcher.read_text(encoding="utf-8")
    helpers = source[source.index("  project_runtime_is_clean()"): source.index("  cleanup_target()")]
    cleanup = source[source.index("  cleanup_target()"): source.index("  on_exit()")]
    script = textwrap.dedent(
        """
        set -eu
        state="$FAKE_DOCKER_STATE"
        log="$state/log"
        docker() {
          command="$1"
          shift
          case "$command" in
            compose)
              action=""
              with_volume=0
              for argument do
                case "$argument" in
                  ps) action="ps" ;;
                  down) action="down" ;;
                  -v) with_volume=1 ;;
                esac
              done
              if test "$action" = ps; then
                test -f "$state/container" && cat "$state/container"
                return 0
              fi
              test "$action" = down || return 0
              if test "${KEEP_CONTAINER_ON_DOWN:-0}" -eq 0; then rm -f "$state/container"; fi
              if test "${KEEP_NETWORK_ON_DOWN:-0}" -eq 0; then rm -f "$state/network"; fi
              if test "$with_volume" -eq 1; then
                if test "${KEEP_VOLUME_ON_DOWN:-0}" -eq 0; then rm -f "$state/volume"; fi
                echo down-v >> "$log"
              else
                if test "${REMOVE_VOLUME_ON_DOWN:-0}" -eq 1; then rm -f "$state/volume"; fi
                echo down >> "$log"
              fi
              ;;
            ps)
              test -f "$state/container" && cat "$state/container"
              ;;
            network)
              if test "${1:-}" = ls; then test -f "$state/network" && cat "$state/network"; fi
              if test "${1:-}" = rm; then
                test "${FORCE_CLEANUP_FAIL:-0}" -eq 0 && rm -f "$state/network"
              fi
              ;;
            volume)
              if test "${1:-}" = ls; then test -f "$state/volume" && cat "$state/volume"; fi
                if test "${1:-}" = inspect; then test -f "$state/volume"; return $?; fi
              if test "${1:-}" = rm; then
                test "${FORCE_CLEANUP_FAIL:-0}" -eq 0 && rm -f "$state/volume"
              fi
              ;;
            rm)
              test "${FORCE_CLEANUP_FAIL:-0}" -eq 0 && rm -f "$state/container"
              ;;
          esac
        }
        stop_target_and_wait() { return 0; }
        export_artifacts() { ARTIFACT_EXPORT_COMPLETE=1; return 0; }
        cleanup_failed=0
        """
    ) + helpers + cleanup + textwrap.dedent(
        """
        cleanup_target || true
        printf 'cleanup_failed=%s\\n' "$cleanup_failed"
        test -f "$state/container" && echo container=present || echo container=absent
        test -f "$state/network" && echo network=present || echo network=absent
        test -f "$state/volume" && echo volume=present || echo volume=absent
        """
    )

    scenarios = (
        ({"target_status": "0", "KEEP_VOLUME_ON_DOWN": "1"}, "cleanup_failed=0\ncontainer=absent\nnetwork=absent\nvolume=absent"),
        ({"target_status": "0", "KEEP_CONTAINER_ON_DOWN": "1"}, "cleanup_failed=0\ncontainer=absent\nnetwork=absent\nvolume=absent"),
        ({"target_status": "1", "KEEP_CONTAINER_ON_DOWN": "1", "KEEP_NETWORK_ON_DOWN": "1"}, "cleanup_failed=0\ncontainer=absent\nnetwork=absent\nvolume=present"),
        ({"target_status": "1", "REMOVE_VOLUME_ON_DOWN": "1"}, "cleanup_failed=1\ncontainer=absent\nnetwork=absent\nvolume=absent"),
        ({"target_status": "0", "KEEP_CONTAINER_ON_DOWN": "1", "KEEP_NETWORK_ON_DOWN": "1", "KEEP_VOLUME_ON_DOWN": "1", "FORCE_CLEANUP_FAIL": "1"}, "cleanup_failed=1\ncontainer=present\nnetwork=present\nvolume=present"),
    )
    for settings, expected in scenarios:
        state = tmp_path / settings["target_status"] / str(len(list(tmp_path.glob("*"))))
        state.mkdir(parents=True)
        for name, value in (("container", "cid"), ("network", "net"), ("volume", "vol")):
            (state / name).write_text(value + "\n", encoding="utf-8")
        env = os.environ.copy()
        env.update(
            {
                "FAKE_DOCKER_STATE": str(state),
                "PROJECT_NAME": "gateway-p2r1-test",
                "COMPOSE_FILE": "compose.yaml",
                "compose_started": "1",
                "container_id": "cid",
                "target_status": settings["target_status"],
                "ARTIFACT_EXPORT_ATTEMPTED": "1",
                "ARTIFACT_EXPORT_COMPLETE": "1" if settings["target_status"] == "0" else "0",
                "ARTIFACT_EXPORT_FAILED": "0" if settings["target_status"] == "0" else "1",
                "probe_volume_ids": "vol",
                "container_cgroup": "",
                "supervisor_cgroup": "",
                "samples_cgroup": "",
            }
        )
        env.update(settings)
        result = subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        assert expected in result.stdout


def test_utf8_row_bytes_use_encoded_length() -> None:
    assert _rows_bytes([("😀", "中文")]) == len("😀中文".encode("utf-8"))


_TEST_STORAGE_IDENTITY = "sha256:" + "1" * 64
_TEST_W3_SNAPSHOT_STAGES = (
    "base_post_commit_close",
    "base_post_restart_validation",
    "delta_post_commit_close",
    "delta_post_restart_validation",
)
_TEST_W3_DELTA_STAGES = {
    "base_restart_delta": (
        "base_post_commit_close",
        "base_post_restart_validation",
    ),
    "delta_commit_delta": (
        "base_post_restart_validation",
        "delta_post_commit_close",
    ),
    "delta_restart_delta": (
        "delta_post_commit_close",
        "delta_post_restart_validation",
    ),
    "comparable_delta": (
        "base_post_restart_validation",
        "delta_post_restart_validation",
    ),
}


def _valid_w3_evidence() -> dict[str, object]:
    snapshots: dict[str, dict[str, object]] = {
        stage: {
            "stage": stage,
            "complete": True,
            "provider_closed": True,
            "server_reaped": True,
            "quiesce_status": "quiesced",
            "logical_bytes": 110
            if stage in {"delta_post_commit_close", "delta_post_restart_validation"}
            else 100,
            "allocated_bytes": 110
            if stage in {"delta_post_commit_close", "delta_post_restart_validation"}
            else 100,
            "files": [],
            "storage_root_identity": _TEST_STORAGE_IDENTITY,
        }
        for stage in _TEST_W3_SNAPSHOT_STAGES
    }
    evidence: dict[str, object] = {
        "storage_snapshots": snapshots,
    }
    _rebuild_w3_deltas(evidence)
    deltas = cast(dict[str, dict[str, object]], evidence["storage_deltas"])
    evidence.update(
        {
            "storage_snapshot_complete": True,
            "storage_lifecycle_complete": True,
            "storage_snapshot_order": list(_TEST_W3_SNAPSHOT_STAGES),
            "base_restart_delta": deltas["base_restart_delta"],
            "delta_commit_delta": deltas["delta_commit_delta"],
            "delta_restart_delta": deltas["delta_restart_delta"],
            "comparable_delta": deltas["comparable_delta"],
        }
    )
    return evidence


def _rebuild_w3_deltas(evidence: dict[str, object]) -> None:
    snapshots = cast(dict[str, dict[str, object]], evidence["storage_snapshots"])
    deltas = {
        name: _storage_delta(snapshots[before], snapshots[after])
        for name, (before, after) in _TEST_W3_DELTA_STAGES.items()
    }
    evidence["storage_deltas"] = deltas
    evidence.update(
        {
            "base_restart_delta": deltas["base_restart_delta"],
            "delta_commit_delta": deltas["delta_commit_delta"],
            "delta_restart_delta": deltas["delta_restart_delta"],
            "comparable_delta": deltas["comparable_delta"],
        }
    )


def test_w3_is_annotated_before_raw_persistence() -> None:
    baselines: dict[str, int] = {}
    w1 = {
        "candidate": Candidate.A.value,
        "workload": "W1",
        "sample_kind": "measured-1",
        "logical_delta_bytes": 100,
    }
    w3 = {
        "candidate": Candidate.A.value,
        "workload": "W3-1pct",
        "sample_kind": "measured-1",
        "change_ratio": 0.01,
        "logical_delta_bytes": 10,
        "allocated_delta_bytes": 10,
        "quiesce_status": "quiesced",
        "storage_snapshot_complete": True,
        "storage_lifecycle_complete": True,
        "storage_mount_verified": True,
        "storage_root_identity": "sha256:" + "1" * 64,
        "storage_snapshot_order": [
            "base_post_commit_close",
            "base_post_restart_validation",
            "delta_post_commit_close",
            "delta_post_restart_validation",
        ],
    }
    w3.update(_valid_w3_evidence())
    _observe_storage_record(w1, baselines)
    _observe_storage_record(w3, baselines)
    assert w3["storage_evidence_status"] == "available"
    assert w3["w1_full_commit_logical_bytes"] == 100
    assert w3["logical_delta_vs_w1_full_ratio"] == 0.1


def test_storage_delta_preserves_signed_physical_reclamation() -> None:
    before = {
        "stage": "base_post_restart_validation",
        "logical_bytes": 100,
        "allocated_bytes": 200,
        "files": [],
    }
    after = {
        "stage": "delta_post_restart_validation",
        "logical_bytes": 120,
        "allocated_bytes": 180,
        "files": [],
    }
    delta = _storage_delta(before, after)
    assert delta["logical_delta_bytes"] == 20
    assert delta["allocated_delta_bytes"] == -20
    assert delta["allocated_delta_semantics"] == "signed_net_allocated_blocks"
    assert delta["physical_reclamation_observed"] is True


def test_w3_storage_missing_lifecycle_is_inconclusive() -> None:
    record = {
        "candidate": Candidate.B.value,
        "workload": "W3-1pct",
        "sample_kind": "measured-1",
        "logical_delta_bytes": 10,
        "allocated_delta_bytes": -10,
        "quiesce_status": "quiesced",
        "change_ratio": 0.01,
    }
    baselines = {Candidate.B.value: 100}
    _observe_storage_record(record, baselines)
    assert record["storage_evidence_status"] == "inconclusive"


def test_storage_snapshot_excludes_symlink_and_deduplicates_hardlink(tmp_path: Path) -> None:
    root = tmp_path / "storage"
    root.mkdir()
    source = root / "source.bin"
    source.write_bytes(b"payload")
    os.link(source, root / "hardlink.bin")
    (root / "symlink.bin").symlink_to(source)
    snapshot = storage_snapshot(root)
    assert snapshot["complete"] is True
    assert snapshot["logical_bytes"] == len(b"payload")
    assert len(snapshot["files"]) == 1
    assert snapshot["files"][0]["relative_path"] in {"source.bin", "hardlink.bin"}


def test_provider_tracker_uses_sample_cgroup_root(tmp_path: Path) -> None:
    root = tmp_path / "delegated"
    root.mkdir()
    (root / "memory.current").write_text("100")
    (root / "memory.peak").write_text("200")
    (root / "memory.stat").write_text("anon 100\nfile 0\n")
    (root / "cgroup.procs").write_text("")
    scope = WorkflowCgroupScope(root)
    scope.create()
    assert scope.path is not None
    (scope.path / "memory.current").write_text("10")
    (scope.path / "memory.peak").write_text("20")
    (scope.path / "memory.stat").write_text("anon 10\nfile 0\n")
    (scope.path / "cgroup.procs").write_text("")
    try:
        settings = RepositoryServiceSettings(cgroup_root=scope.path)
        layout = ProbeLayout.create(tmp_path / "layout")
        runner = DoltRunner.__new__(DoltRunner)
        provider = OfflineCliProvider(settings, layout, tmp_path / "repo", runner)
        assert provider.cgroup is not None
        assert provider.cgroup.root == scope.path
        provider.close()
    finally:
        for child in scope.path.iterdir() if scope.path is not None else ():
            if child.name != "cgroup.procs":
                child.unlink()
        scope.active = False


def test_process_rss_breakdown_reports_anon_and_file_components() -> None:
    current = process_rss_breakdown_kib(os.getpid())
    tree = process_tree_rss_breakdown_kib(os.getpid())
    assert set(current) == {"rss_anon_kib", "rss_file_kib"}
    assert set(tree) == {"rss_anon_kib", "rss_file_kib"}
    assert all(value >= 0 for value in current.values())
    assert all(value >= 0 for value in tree.values())


def test_memory_sampler_accepts_provider_baseline_after_spawn() -> None:
    sampler = MemorySampler(
        workflow_pid=os.getpid(),
        provider_pid=lambda: None,
        cgroup=None,
        interval_seconds=0.01,
        baselines={"provider_process_tree": None},
    )
    sampler.set_baseline("provider_process_tree", 123)
    assert sampler.baselines["provider_process_tree"] == 123


def test_discard_runner_attaches_stdout_directly_to_devnull(tmp_path: Path) -> None:
    settings = RepositoryServiceSettings(output_tail_bytes=64)
    runner = DoltRunner.__new__(DoltRunner)
    runner.settings = settings
    runner.server_root = tmp_path
    runner.home = tmp_path / "home"
    runner.home.mkdir()
    runner.settings = settings.model_copy(update={"dolt_binary": Path(sys.executable)})
    discard = runner.discard(
        "discard-test",
        ["-c", "import sys; sys.stdout.write('x' * 4000000)"],
        cwd=tmp_path,
        timeout=2.0,
    )
    assert discard.process.stdout is None
    result = discard.close()
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.provider_peak_rss_anon_kib >= 0
    assert result.provider_peak_rss_file_kib >= 0


def test_scaling_diagnostic_defaults_to_candidate_b(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_collect(*_args: object, **kwargs: object) -> list[dict[str, object]]:
        captured["candidates"] = kwargs["candidates"]
        return []

    monkeypatch.setattr(matrix_module, "_collect_scaling_records", fake_collect)
    summary = run_scaling_diagnostic(
        RepositoryServiceSettings(), tmp_path / "scaling.jsonl"
    )
    assert captured["candidates"] == (Candidate.B,)
    assert summary["selected_provider"] is None
    assert summary["p2_r1_exit"] == "no-go"


def test_restart_before_stream_is_forwarded_to_worker_api(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_run(*_args: object, **kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(workflow_module, "_run_workflow_in_process", fake_run)
    fixture = generate_scale_fixture(tmp_path, ScaleWorkload.S10)
    workflow_module.run_workflow(
        RepositoryServiceSettings(),
        Candidate.B,
        fixture,
        sample_kind="diagnostic",
        restart_before_stream=True,
    )
    assert captured["restart_before_stream"] is True


def test_memory_sampler_exposes_absolute_and_baseline_delta() -> None:
    sampler = MemorySampler(
        workflow_pid=1,
        provider_pid=lambda: None,
        cgroup=None,
        interval_seconds=0.01,
        baselines={
            "workflow_process_tree": 100,
            "provider_process_tree": 50,
            "arrow_memory_pool": 10,
            "cgroup": 0,
        },
    )
    snapshots: Iterator[dict[str, int | None]] = iter(
        [
            {
                "workflow_process_tree": 120,
                "provider_process_tree": 70,
                "arrow_memory_pool": 30,
                "cgroup": 40,
            },
            {
                "workflow_process_tree": 140,
                "provider_process_tree": 80,
                "arrow_memory_pool": 50,
                "cgroup": 60,
            },
        ]
    )
    sampler._snapshot = lambda: next(snapshots)  # type: ignore[method-assign]
    sampler.set_active(("first_10pct",))
    delta = sampler.stop()
    assert delta["workflow_process_tree"]["first_10pct"] == 40
    assert sampler.absolute_peaks()["workflow_process_tree"]["first_10pct"] == 140


def test_subset_and_missing_scaling_cannot_produce_go() -> None:
    summary = _summarize([], RepositoryServiceSettings())
    assert summary["round_exit"] == "no-go"
    assert summary["selected_provider"] is None
    matrix = summary["candidate_matrix"]
    assert isinstance(matrix, dict)
    assert all(result["bounded_stream_status"] == "inconclusive" for result in matrix.values())


def test_s10_large_batch_overlaps_all_plateau_windows() -> None:
    assert windows_for_interval(0, 1024, 10_000) == ("first_10pct",)
    assert windows_for_interval(4_500, 5_500, 10_000) == ("middle_10pct",)
    assert windows_for_interval(9_000, 10_000, 10_000) == ("final_10pct",)


def test_coverage_rejects_duplicate_and_missing_scaling_keys() -> None:
    rows = [
        {
            "matrix_kind": "scaling",
            "candidate": "candidate_a_offline_cli",
            "workload": "S10",
            "record_batch_row_bound": 256,
            "sample_kind": "warmup",
        }
    ] * 2
    complete, reason, counts = _coverage(rows, "scaling")
    assert not complete
    assert "missing" in reason
    assert counts["duplicates"] == 1


def test_plateau_gate_requires_all_four_subjects_and_three_windows() -> None:
    plateau: dict[str, dict[str, int | None]] = {
        subject: {window: 100 for window in ("first_10pct", "middle_10pct", "final_10pct")}
        for subject in (
            "workflow_process_tree",
            "provider_process_tree",
            "arrow_memory_pool",
            "cgroup",
        )
    }
    record = {
        "memory_evidence": {
            "coverage": "available",
            "baseline_coverage": True,
            "cgroup_stat_coverage": True,
        },
        "plateau_peaks": plateau,
        "plateau_peaks_absolute": {subject: dict(values) for subject, values in plateau.items()},
    }
    assert _record_bounded_gate(record)
    plateau["cgroup"]["final_10pct"] = None
    assert not _record_bounded_gate(record)


def test_dolt_version_parser_is_exact() -> None:
    assert parse_dolt_version("dolt version 2.1.11\n") == "2.1.11"
    assert parse_dolt_version("dolt version 12.1.11\n") == "12.1.11"
    assert parse_dolt_version("dolt version 2.1.11-dev\n") is None
    assert parse_dolt_version("not a dolt version") is None


def _complete_gate_records() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    plateau = {
        subject: {window: 100 for window in ("first_10pct", "middle_10pct", "final_10pct")}
        for subject in (
            "workflow_process_tree",
            "provider_process_tree",
            "arrow_memory_pool",
            "cgroup",
        )
    }
    absolute_plateau = {
        subject: dict(values) for subject, values in plateau.items()
    }
    for candidate in Candidate:
        for workload in NORMAL_WORKLOADS:
            for sample in EXPECTED_SAMPLE_KINDS:
                record: dict[str, object] = {
                    "matrix_kind": "normal",
                    "candidate": candidate.value,
                    "workload": workload.value,
                    "sample_kind": sample,
                    "correctness": True,
                    "error": None,
                    "import_seconds": 1.0,
                    "hard_gates": {"bounded_stream": True},
                    "bounded_stream_record_gate": True,
                    "memory_evidence": {
                        "coverage": "available",
                        "baseline_coverage": True,
                        "cgroup_stat_coverage": True,
                    },
                    "plateau_peaks": plateau,
                    "plateau_peaks_absolute": absolute_plateau,
                    "metadata_complete": True,
                    "storage_mount_verified": True,
                    "volume_backend": "volume",
                    "filesystem_type": "xfs",
                    "storage_root_identity": _TEST_STORAGE_IDENTITY,
                    "storage_layout_version": "p2-r1-storage-layout-v1",
                    "logical_bytes_before": 100,
                    "logical_bytes_after": 200,
                    "allocated_bytes_before": 100,
                    "allocated_bytes_after": 200,
                    "storage_quiesced": True,
                    "change_ratio": 0.01
                    if workload.value == "W3-1pct"
                    else 0.10
                    if workload.value == "W3-10pct"
                    else None,
                    "logical_delta_bytes": 100
                    if workload.value == "W1"
                    else 10
                    if workload.value.startswith("W3")
                    else None,
                    "allocated_delta_bytes": 100
                    if workload.value == "W1"
                    else 10
                    if workload.value.startswith("W3")
                    else None,
                    "quiesce_status": "quiesced"
                    if workload.value.startswith("W3")
                    else "not_applicable",
                }
                if workload.value.startswith("W3"):
                    record.update(_valid_w3_evidence())
                records.append(record)
        for scale in SCALE_WORKLOADS:
            for bound in ROW_BOUNDS:
                for sample in EXPECTED_SAMPLE_KINDS:
                    records.append(
                        {
                            "matrix_kind": "scaling",
                            "candidate": candidate.value,
                            "workload": scale.value,
                            "record_batch_row_bound": bound,
                            "record_batch_byte_bound": BYTE_BOUND,
                            "sample_kind": sample,
                            "correctness": True,
                            "error": None,
                            "hard_gates": {"bounded_stream": True},
                            "bounded_stream_record_gate": True,
                            "memory_evidence": {
                                "coverage": "available",
                                "baseline_coverage": True,
                                "cgroup_stat_coverage": True,
                            },
                            "plateau_peaks": plateau,
                            "plateau_peaks_absolute": absolute_plateau,
                            "metadata_complete": True,
                            "storage_mount_verified": True,
                            "volume_backend": "volume",
                            "filesystem_type": "xfs",
                            "storage_root_identity": _TEST_STORAGE_IDENTITY,
                            "storage_layout_version": "p2-r1-storage-layout-v1",
                        }
                    )
    return records


@pytest.mark.parametrize("workload", ["W0", "W1", "W2", "W3-1pct", "S10"])
def test_candidate_storage_provenance_covers_normal_and_scaling_records(
    workload: str,
) -> None:
    records = _complete_gate_records()
    target = next(
        row
        for row in records
        if row.get("candidate") == Candidate.A.value
        and row.get("workload") == workload
        and (workload not in {scale.value for scale in SCALE_WORKLOADS} or row.get("record_batch_row_bound") == 256)
        and row.get("sample_kind") == "warmup"
    )
    target["storage_mount_verified"] = False
    summary = _summarize(records, RepositoryServiceSettings())
    candidate_matrix = cast(dict[str, dict[str, object]], summary["candidate_matrix"])
    candidate = candidate_matrix[Candidate.A.value]
    assert candidate["storage_provenance_complete"] is False
    assert candidate["hard_gate"] is False
    assert summary["selected_provider"] != Candidate.A.value


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("volume_backend", "unknown"),
        ("filesystem_type", "overlayfs"),
        ("storage_root_identity", "not-an-identity"),
        ("storage_layout_version", "p2-r1-storage-layout-v0"),
    ],
)
def test_candidate_storage_provenance_rejects_invalid_canonical_fields(
    field: str, value: object
) -> None:
    records = _complete_gate_records()
    target = next(row for row in records if row.get("candidate") == Candidate.A.value)
    target[field] = value
    complete, reason = _candidate_storage_provenance(records, Candidate.A.value)
    assert complete is False
    assert reason != "complete"
    summary = _summarize(records, RepositoryServiceSettings())
    matrix = cast(dict[str, dict[str, object]], summary["candidate_matrix"])
    assert matrix[Candidate.A.value]["hard_gate"] is False


@pytest.mark.parametrize(
    "mutator",
    [
        lambda evidence: evidence["storage_snapshots"]["base_post_commit_close"].__setitem__("stage", "wrong"),
        lambda evidence: evidence["storage_snapshots"]["base_post_commit_close"].__setitem__("complete", False),
        lambda evidence: evidence["storage_snapshots"]["base_post_commit_close"].__setitem__("provider_closed", False),
        lambda evidence: evidence["storage_snapshots"]["base_post_commit_close"].__setitem__("server_reaped", False),
        lambda evidence: evidence["storage_snapshots"]["base_post_commit_close"].__setitem__("quiesce_status", "pending"),
        lambda evidence: evidence["storage_snapshots"]["base_post_commit_close"].__setitem__("storage_root_identity", "sha256:" + "2" * 64),
        lambda evidence: evidence["storage_snapshots"]["base_post_commit_close"].__setitem__("files", {}),
        lambda evidence: evidence["storage_deltas"]["comparable_delta"].__setitem__("before_stage", "wrong"),
        lambda evidence: evidence["storage_deltas"]["comparable_delta"].__setitem__("allocated_delta_semantics", "unsigned"),
        lambda evidence: evidence["storage_deltas"]["comparable_delta"].__setitem__("changed_files", {}),
    ],
)
def test_w3_raw_lifecycle_tampering_is_inconclusive(mutator: Callable[[dict[str, object]], None]) -> None:
    evidence = _valid_w3_evidence()
    mutator(evidence)
    record: dict[str, object] = {
        "candidate": Candidate.A.value,
        "workload": "W3-1pct",
        "sample_kind": "measured-1",
        "storage_root_identity": _TEST_STORAGE_IDENTITY,
        "storage_mount_verified": True,
        "logical_delta_bytes": 10,
        "allocated_delta_bytes": 10,
        "change_ratio": 0.01,
        **evidence,
    }
    assert _w3_lifecycle_evidence_valid(record) is False
    baselines = {Candidate.A.value: 100}
    _observe_storage_record(record, baselines)
    assert record["storage_evidence_status"] == "inconclusive"


@pytest.mark.parametrize(
    "mutator",
    [
        lambda evidence: evidence["storage_deltas"]["comparable_delta"].__setitem__(
            "logical_delta_bytes", 11
        ),
        lambda evidence: evidence["storage_deltas"]["comparable_delta"].__setitem__(
            "allocated_delta_bytes", 11
        ),
    ],
)
def test_w3_delta_arithmetic_tampering_is_rejected(
    mutator: Callable[[dict[str, object]], None],
) -> None:
    evidence = _valid_w3_evidence()
    mutator(evidence)
    record = {
        "storage_root_identity": _TEST_STORAGE_IDENTITY,
        **evidence,
    }
    assert _w3_lifecycle_evidence_valid(record) is False


def test_w3_changed_files_are_derived_from_snapshot_difference() -> None:
    evidence = _valid_w3_evidence()
    snapshots = cast(dict[str, dict[str, object]], evidence["storage_snapshots"])
    before_file = {
        "relative_path": "data.bin",
        "inode": 10,
        "st_size": 4,
        "st_blocks": 1,
        "link_count": 1,
    }
    after_file = {**before_file, "inode": 11, "st_size": 8}
    snapshots["base_post_restart_validation"]["files"] = [before_file]
    snapshots["delta_post_commit_close"]["files"] = [after_file]
    snapshots["delta_post_restart_validation"]["files"] = [after_file]
    _rebuild_w3_deltas(evidence)
    record = {
        "storage_root_identity": _TEST_STORAGE_IDENTITY,
        **evidence,
    }
    assert _w3_lifecycle_evidence_valid(record) is True
    comparable = cast(dict[str, object], record["storage_deltas"])["comparable_delta"]
    assert cast(dict[str, object], comparable)["changed_files"] == [
        {"relative_path": "data.bin", "before": before_file, "after": after_file}
    ]


@pytest.mark.parametrize(
    "changed_files",
    [
        [
            {
                "relative_path": "outside.bin",
                "before": None,
                "after": {
                    "relative_path": "outside.bin",
                    "inode": 1,
                    "st_size": 1,
                    "st_blocks": 1,
                    "link_count": 1,
                },
            }
        ],
        [
            {
                "relative_path": "data.bin",
                "before": None,
                "after": None,
            }
        ],
        [
            {
                "relative_path": "data.bin",
                "before": None,
                "after": {
                    "relative_path": "data.bin",
                    "inode": 1,
                    "st_size": 1,
                    "st_blocks": 1,
                    "link_count": 1,
                },
            },
            {
                "relative_path": "data.bin",
                "before": None,
                "after": {
                    "relative_path": "data.bin",
                    "inode": 1,
                    "st_size": 1,
                    "st_blocks": 1,
                    "link_count": 1,
                },
            },
        ],
    ],
)
def test_w3_changed_files_tampering_is_rejected(
    changed_files: list[dict[str, object]],
) -> None:
    evidence = _valid_w3_evidence()
    deltas = cast(dict[str, dict[str, object]], evidence["storage_deltas"])
    deltas["comparable_delta"]["changed_files"] = changed_files
    record = {
        "storage_root_identity": _TEST_STORAGE_IDENTITY,
        **evidence,
    }
    assert _w3_lifecycle_evidence_valid(record) is False


@pytest.mark.parametrize("extra_key", ["extra_delta"])
def test_w3_delta_key_set_is_exact(extra_key: str) -> None:
    evidence = _valid_w3_evidence()
    deltas = cast(dict[str, dict[str, object]], evidence["storage_deltas"])
    deltas[extra_key] = dict(deltas["comparable_delta"])
    record = {
        "storage_root_identity": _TEST_STORAGE_IDENTITY,
        **evidence,
    }
    assert _w3_lifecycle_evidence_valid(record) is False


def test_w3_snapshot_identity_is_independent_from_volume_root_identity() -> None:
    record: dict[str, object] = {
        "candidate": Candidate.A.value,
        "workload": "W3-1pct",
        "sample_kind": "measured-1",
        "storage_root_identity": "sha256:" + "9" * 64,
        "storage_mount_verified": True,
        "logical_delta_bytes": 10,
        "allocated_delta_bytes": 0,
        "change_ratio": 0.01,
        "quiesce_status": "quiesced",
        **_valid_w3_evidence(),
    }
    snapshots = cast(dict[str, dict[str, object]], record["storage_snapshots"])
    for snapshot in snapshots.values():
        snapshot["storage_root_identity"] = "sha256:" + "8" * 64
    assert _w3_lifecycle_evidence_valid(record) is True
    _observe_storage_record(record, {Candidate.A.value: 100})
    assert record["storage_evidence_status"] == "available"


@pytest.mark.parametrize("allocated_delta", [-10, 0, 10])
def test_w3_signed_allocated_delta_allows_reclamation_and_zero(
    allocated_delta: int,
) -> None:
    evidence = _valid_w3_evidence()
    snapshots = cast(dict[str, dict[str, object]], evidence["storage_snapshots"])
    for stage in ("delta_post_commit_close", "delta_post_restart_validation"):
        snapshots[stage]["allocated_bytes"] = 100 + allocated_delta
    _rebuild_w3_deltas(evidence)
    record: dict[str, object] = {
        "candidate": Candidate.A.value,
        "workload": "W3-1pct",
        "sample_kind": "measured-1",
        "storage_root_identity": _TEST_STORAGE_IDENTITY,
        "storage_mount_verified": True,
        "logical_delta_bytes": 10,
        "allocated_delta_bytes": allocated_delta,
        "change_ratio": 0.01,
        "quiesce_status": "quiesced",
        **evidence,
    }
    _observe_storage_record(record, {Candidate.A.value: 100})
    assert record["storage_evidence_status"] == "available"
    assert record["physical_reclamation_observed"] is (allocated_delta < 0)


def test_complete_formal_pass_selects_a_and_noise_is_aggregated() -> None:
    records = _complete_gate_records()
    noisy = next(
        row
        for row in records
        if row.get("matrix_kind") == "scaling"
        and row.get("candidate") == Candidate.A.value
        and row.get("workload") == ScaleWorkload.S10.value
        and row.get("record_batch_row_bound") == 256
        and row.get("sample_kind") == "measured-1"
    )
    noisy["plateau_peaks"] = {
        subject: {window: 50 for window in ("first_10pct", "middle_10pct", "final_10pct")}
        for subject in ("workflow_process_tree", "provider_process_tree", "arrow_memory_pool", "cgroup")
    }
    summary = _summarize(records, RepositoryServiceSettings())
    assert summary["selected_provider"] == Candidate.A.value
    assert summary["p2_r1_exit"] == "go"
    status, _, ratios = _bounded_stream_gate(Candidate.A.value, [r for r in records if r["matrix_kind"] == "scaling"])
    assert status == "pass"
    assert ratios["bound_256_workflow_process_tree_first_10pct_ratio"] == 1.0


def test_warmup_correctness_failure_blocks_selection() -> None:
    records = _complete_gate_records()
    warmup = next(
        row
        for row in records
        if row.get("candidate") == Candidate.A.value
        and row.get("workload") == "W0"
        and row.get("sample_kind") == "warmup"
    )
    warmup["correctness"] = False
    summary = _summarize(records, RepositoryServiceSettings())
    assert summary["selected_provider"] == Candidate.B.value
    matrix = cast(dict[str, dict[str, object]], summary["candidate_matrix"])
    assert cast(int, matrix[Candidate.A.value]["correctness_failures"]) > 0


def test_formal_cgroup_preflight_fails_closed_without_delegation(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="delegated cgroup"):
        preflight_cgroup(tmp_path)


def test_preflight_rejects_supervisor_outside_declared_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GATEWAY_REPOSITORY_CGROUP_CONTROL_GROUP", "/gateway-p2r1.slice")
    with pytest.raises(Exception, match="delegated cgroup parent"):
        preflight_cgroup(tmp_path)


def test_formal_runner_preflight_fails_before_creating_artifacts(tmp_path: Path) -> None:
    output = tmp_path / "audit-rerun.jsonl"
    with pytest.raises(Exception, match="delegated cgroup"):
        run_matrix(
            RepositoryServiceSettings(cgroup_root=tmp_path),
            output,
            image_digest="sha256:test",
            build_revision="test",
            cache_condition="test",
        )
    assert not output.exists()


def test_formal_runner_retains_incomplete_raw(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = tmp_path / "incomplete.jsonl"

    def fake_preflight(_: Path | None) -> None:
        return

    def fake_collect(*args: object, **kwargs: object) -> list[dict[str, object]]:
        sink = cast(Callable[[dict[str, object]], None], kwargs["record_sink"])
        sink({"record_type": "measurement", "sample_kind": "warmup"})
        raise RuntimeError("synthetic collection stop")

    monkeypatch.setattr(matrix_module, "preflight_cgroup", fake_preflight)
    monkeypatch.setattr(matrix_module, "_collect_normal_records", fake_collect)
    with pytest.raises(RuntimeError, match="synthetic collection stop"):
        matrix_module.run_matrix(
            RepositoryServiceSettings(cgroup_root=tmp_path),
            output,
            image_digest="sha256:" + "0" * 64,
            build_revision="a" * 40,
            cache_condition="retained-dependency-cache",
        )
    assert output.exists()
    raw = output.read_text(encoding="utf-8").splitlines()
    assert '"record_type": "run_status"' in raw[-1]
    assert not output.with_suffix(".summary.json").exists()
    assert not output.with_suffix(".md").exists()


def test_finalization_rejects_stale_raw_w3_annotation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "stale-w3.jsonl"

    monkeypatch.setattr(matrix_module, "preflight_cgroup", lambda _: None)

    def fake_normal(*args: object, **kwargs: object) -> list[dict[str, object]]:
        sink = cast(Callable[[dict[str, object]], None], kwargs["record_sink"])
        record: dict[str, object] = {
            "record_type": "measurement",
            "candidate": Candidate.A.value,
            "workload": "W3-1pct",
            "sample_kind": "measured-1",
            "change_ratio": 0.01,
            "logical_delta_bytes": 1,
            "allocated_delta_bytes": 1,
            "quiesce_status": "quiesced",
        }
        sink(record)
        record["logical_delta_bytes"] = 2
        return [record]

    monkeypatch.setattr(matrix_module, "_collect_normal_records", fake_normal)
    monkeypatch.setattr(matrix_module, "_collect_scaling_records", lambda *args, **kwargs: [])
    with pytest.raises(RuntimeError, match="persisted raw records"):
        run_matrix(
            RepositoryServiceSettings(cgroup_root=tmp_path),
            output,
            image_digest="sha256:" + "0" * 64,
            build_revision="a" * 40,
            cache_condition="retained-dependency-cache",
        )
    assert '"status": "incomplete"' in output.read_text(encoding="utf-8")
    assert not output.with_suffix(".summary.json").exists()


def test_raw_reservation_is_exclusive(tmp_path: Path) -> None:
    output = tmp_path / "reserved.jsonl"
    handle = matrix_module._reserve_raw(output)
    try:
        with pytest.raises(FileExistsError):
            matrix_module._reserve_raw(output)
    finally:
        handle.close()


def test_worker_result_is_atomically_published(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload_path = tmp_path / "payload.pickle"
    result_path = tmp_path / "result.pickle"
    with payload_path.open("wb") as handle:
        pickle.dump({"value": 7}, handle)
    monkeypatch.setattr(workflow_worker, "_run_workflow_in_process", lambda **_: {"ok": True})
    monkeypatch.setattr(sys, "argv", ["workflow_worker", str(payload_path), str(result_path)])
    workflow_worker.main()
    with result_path.open("rb") as handle:
        assert pickle.load(handle) == {"ok": True}
    assert not list(tmp_path.glob(".result.pickle.*.tmp"))


def test_true_scale_growth_fails_conservative_ratio_gate() -> None:
    records = _complete_gate_records()
    for row in records:
        if (
            row.get("candidate") == Candidate.A.value
            and row.get("matrix_kind") == "scaling"
            and row.get("workload") == ScaleWorkload.S100.value
        ):
            plateau = {
                subject: dict(values)
                for subject, values in cast(
                    dict[str, dict[str, int]], row["plateau_peaks"]
                ).items()
            }
            plateau["workflow_process_tree"] = {
                window: 200 for window in ("first_10pct", "middle_10pct", "final_10pct")
            }
            row["plateau_peaks"] = plateau
    status, reason, _ = _bounded_stream_gate(
        Candidate.A.value, [row for row in records if row["matrix_kind"] == "scaling"]
    )
    assert status == "fail"
    assert "ratio" in reason


def test_all_zero_delta_scale_evidence_is_bounded() -> None:
    records = _complete_gate_records()
    for row in records:
        if row.get("matrix_kind") == "scaling":
            row["plateau_peaks"] = {
                subject: {window: 0 for window in ("first_10pct", "middle_10pct", "final_10pct")}
                for subject in ("workflow_process_tree", "provider_process_tree", "arrow_memory_pool", "cgroup")
            }
    status, reason, ratios = _bounded_stream_gate(
        Candidate.A.value, [row for row in records if row["matrix_kind"] == "scaling"]
    )
    assert status == "pass"
    assert "within" in reason
    assert ratios["bound_256_cgroup_first_10pct_ratio"] == 1.0


def test_mixed_zero_and_positive_scale_evidence_is_inconclusive() -> None:
    records = _complete_gate_records()
    for row in records:
        if (
            row.get("matrix_kind") == "scaling"
            and row.get("candidate") == Candidate.A.value
            and row.get("workload") == ScaleWorkload.S10.value
        ):
            row["plateau_peaks"] = {
                subject: {window: 0 for window in ("first_10pct", "middle_10pct", "final_10pct")}
                for subject in ("workflow_process_tree", "provider_process_tree", "arrow_memory_pool", "cgroup")
            }
    status, reason, _ = _bounded_stream_gate(
        Candidate.A.value, [row for row in records if row["matrix_kind"] == "scaling"]
    )
    assert status == "inconclusive"
    assert "zero/positive" in reason


def test_connector_fetch_size_is_width_aware() -> None:
    bounded = TableCatalog(
        "bounded",
        (ColumnCatalog("payload", "VARCHAR(2048)", False, None),),
        100,
    )
    unbounded = TableCatalog(
        "unbounded",
        (ColumnCatalog("payload", "BLOB", True, None),),
        100,
    )
    settings = RepositoryServiceSettings(connector_fetch_row_bound=32)
    assert 1 < _safe_connector_fetch_size(bounded, settings) <= 32
    assert _safe_connector_fetch_size(unbounded, settings) == 1


def test_fake_provenance_is_not_complete() -> None:
    metadata = _measurement_metadata(
        RepositoryServiceSettings(),
        image_digest="sha256:test",
        build_revision="test",
        cache_condition="test",
    )
    assert metadata["metadata_complete"] is False


def test_memory_sampler_time_fraction_windows_keep_absolute_and_delta() -> None:
    sampler = MemorySampler(
        workflow_pid=1,
        provider_pid=lambda: None,
        cgroup=None,
        interval_seconds=0.01,
        baselines={
            "workflow_process_tree": 100,
            "provider_process_tree": 50,
            "arrow_memory_pool": 10,
            "cgroup": 1000,
            "cgroup_anon_bytes": 200,
            "cgroup_file_bytes": 300,
        },
        record_history=True,
    )
    sampler._history = [  # noqa: SLF001 - deterministic sampler fixture
        (
            100.5,
            {
                "workflow_process_tree": 120,
                "provider_process_tree": 70,
                "arrow_memory_pool": 30,
                "cgroup": 1100,
            },
            {"anon_bytes": 220, "file_bytes": 340},
        ),
        (
            105.0,
            {
                "workflow_process_tree": 140,
                "provider_process_tree": 90,
                "arrow_memory_pool": 40,
                "cgroup": 1300,
            },
            {"anon_bytes": 260, "file_bytes": 380},
        ),
        (
            109.5,
            {
                "workflow_process_tree": 160,
                "provider_process_tree": 110,
                "arrow_memory_pool": 50,
                "cgroup": 1500,
            },
            {"anon_bytes": 300, "file_bytes": 420},
        ),
    ]
    result = sampler.time_fraction_peaks(100.0, 110.0)
    delta = cast(dict[str, dict[str, int | None]], result["plateau_peaks"])
    absolute = cast(
        dict[str, dict[str, int | None]], result["plateau_peaks_absolute"]
    )
    stat_delta = cast(
        dict[str, dict[str, int | None]], result["memory_stat_plateau"]
    )
    assert result["window_basis"] == "time_fraction"
    assert delta["workflow_process_tree"]["first_10pct"] == 20
    assert delta["workflow_process_tree"]["middle_10pct"] == 40
    assert delta["workflow_process_tree"]["final_10pct"] == 60
    assert absolute["cgroup"]["middle_10pct"] == 1300
    assert stat_delta["anon_bytes"]["final_10pct"] == 100


def test_a_paired_devnull_diagnostic_is_no_go_and_keeps_variants(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(matrix_module, "SCALE_WORKLOADS", (ScaleWorkload.S10,))
    monkeypatch.setattr(matrix_module, "ROW_BOUNDS", (256,))
    monkeypatch.setattr(
        matrix_module, "EXPECTED_SAMPLE_KINDS", ("warmup", "measured-1")
    )
    monkeypatch.setattr(matrix_module, "_collect_scaling_records", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(matrix_module, "_summarize", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        matrix_module,
        "_write_artifacts",
        lambda output, records, _summary: output.write_text(
            "".join(json.dumps(row) + "\n" for row in records), encoding="utf-8"
        ),
    )
    monkeypatch.setattr(
        matrix_module,
        "_measurement_metadata",
        lambda *_args, **_kwargs: {"metadata_complete": True},
    )
    monkeypatch.setattr(
        matrix_module,
        "_diagnostic_storage_metadata",
        lambda *_args, **_kwargs: {
            "filesystem_type": "xfs",
            "volume_backend": "volume",
            "storage_root_identity": "sha256:" + "a" * 64,
            "storage_mount_verified": True,
            "storage_layout_version": "p2-r1-storage-layout-v1",
            "storage_volume_project": "diagnostic-project",
        },
    )

    def fake_discard(*_args: object, **kwargs: object) -> dict[str, object]:
        return {
            "candidate": Candidate.A.value,
            "workload": ScaleWorkload.S10.value,
            "sample_kind": kwargs["sample_kind"],
            "correctness": True,
            "memory_evidence": {
                "coverage": "available",
                "window_basis": "time_fraction",
            },
            "plateau_peaks": _test_plateau_peaks(),
            "plateau_peaks_absolute": _test_plateau_peaks(),
            "error": None,
        }

    monkeypatch.setattr(
        matrix_module, "run_offline_discard_workflow_isolated", fake_discard
    )
    monkeypatch.setattr(matrix_module, "run_offline_discard_diagnostic", fake_discard)
    summary = run_a_paired_devnull_diagnostic(
        RepositoryServiceSettings(), tmp_path / "a-paired.jsonl"
    )
    assert summary["diagnostic_kind"] == "candidate_a_paired_devnull"
    assert summary["selected_provider"] is None
    assert summary["p2_r1_exit"] == "no-go"
    assert summary["devnull_records"] == 2
    raw = (tmp_path / "a-paired.jsonl").read_text(encoding="utf-8").splitlines()
    assert all(json.loads(line).get("diagnostic_variant") == "devnull" for line in raw)


def test_v8_rows_bytes_have_deterministic_null_utf8_binary_scalar_semantics() -> None:
    assert _rows_bytes([(None, "世界", b"\x00\xff", 42)]) == 6 + 2 + 2


def test_v8_provider_rows_share_arrow_normalized_payload_accounting() -> None:
    table = TableCatalog(
        "payloads",
        (
            ColumnCatalog("number", "INT", False, None),
            ColumnCatalog("text", "VARCHAR(32)", True, None),
            ColumnCatalog("flag", "BOOLEAN", True, None),
            ColumnCatalog("blob", "BINARY(2)", True, None),
        ),
        1,
    )
    policy = UnknownTypePolicy.STRINGIFY
    candidate_a = normalize_rows(
        table, [("7", "世界", "TRUE", b"\x00\xff")], policy
    )
    candidate_b = normalize_rows(
        table, [(7, "世界", True, b"\x00\xff")], policy
    )
    assert candidate_a == candidate_b
    assert _rows_bytes(candidate_a) == _rows_bytes(candidate_b)


def test_v8_provider_shape_normalizes_temporal_numeric_values_identically() -> None:
    table = TableCatalog(
        "shapes",
        (
            ColumnCatalog("ts", "TIMESTAMP(6)", False, None),
            ColumnCatalog("dt", "DATETIME(6)", False, None),
            ColumnCatalog("time", "TIME(6)", False, None),
            ColumnCatalog("decimal_value", "DECIMAL(10,2)", False, None),
            ColumnCatalog("float_value", "FLOAT", False, None),
            ColumnCatalog("bits", "BIT(8)", False, None),
        ),
        1,
    )
    policy = UnknownTypePolicy.STRINGIFY
    timezone = dt.timezone(dt.timedelta(hours=2))
    candidate_a = normalize_rows(
        table,
        [
            (
                "2025-01-01 12:00:00+02:00",
                "2025-01-01 12:00:00",
                "01:02:03",
                "12.50",
                "1.5",
                "aa",
            )
        ],
        policy,
    )
    candidate_b = normalize_rows(
        table,
        [
            (
                dt.datetime(2025, 1, 1, 12, tzinfo=timezone),
                dt.datetime(2025, 1, 1, 12),
                dt.timedelta(hours=1, minutes=2, seconds=3),
                decimal.Decimal("12.50"),
                1.5,
                170,
            )
        ],
        policy,
    )
    assert candidate_a == candidate_b
    assert _rows_bytes(candidate_a) == _rows_bytes(candidate_b)


def _v8_memory_evidence_for_test(peak: int = 100) -> dict[str, object]:
    plateau = {
        subject: {
            "first_10pct": 0,
            "middle_10pct": 0,
            "final_10pct": 0,
        }
        for subject in (
            "workflow_process_tree",
            "provider_process_tree",
            "arrow_memory_pool",
            "cgroup",
        )
    }
    return {
        "coverage": "available",
        "baseline_coverage": True,
        "cgroup_stat_coverage": True,
        "plateau_peaks": plateau,
        "plateau_peaks_absolute": plateau,
        "memory_limit_bytes": 8 * 1024 * 1024 * 1024,
        "effective_memory_limit_bytes": 8 * 1024 * 1024 * 1024,
        "cgroup_memory_peak_bytes": peak,
    }


def _v8_record_for_test(
    *,
    matrix_kind: str,
    workload: str,
    sample_kind: str,
    row_bound: int = 1024,
    correctness: bool = True,
    error: str | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "candidate": Candidate.A.value,
        "matrix_kind": matrix_kind,
        "workload": workload,
        "sample_kind": sample_kind,
        "record_batch_row_bound": row_bound,
        "record_batch_byte_bound": V8_BYTE_BOUND,
        "correctness": correctness,
        "error": error,
        "hard_gates": {
            "workflow": correctness,
            "cancellation": correctness,
            "restart": correctness,
            "unknown_type": correctness,
        },
        "memory_evidence": _v8_memory_evidence_for_test(),
        "total_rows": 1,
        "batch_count": 1,
        "batch_contract_valid": True,
        "batch_contract_violation_count": 0,
        "total_stream_payload_bytes": 1,
        "max_row_bytes": 1,
        "max_batch_rows": 1,
        "max_batch_bytes": 1,
        "oversized_single_row": False,
        "oversized_row_count": 0,
        "max_oversized_row_bytes": 0,
        "oversized_batch_count": 0,
        "byte_bound_reason": None,
        "encoded_line_applicable": False,
        "encoded_line_bound_valid": None,
        "metadata_complete": True,
        "storage_mount_verified": True,
        "volume_backend": "volume",
        "filesystem_type": "xfs",
        "storage_root_identity": "sha256:" + "a" * 64,
        "storage_layout_version": "p2-r1-storage-layout-v1",
        "support_envelope": "validated",
        "methodology_version": V8_METHODOLOGY,
    }
    if workload in {Workload.W3_1.value, Workload.W3_10.value}:
        record.update(
            {
                **_valid_w3_evidence(),
                "storage_evidence_status": "available",
                "storage_snapshot_complete": True,
                "storage_mount_verified": True,
            }
        )
    return record


def test_v8_coverage_retains_failed_key_but_fails_decision() -> None:
    records = [
        _v8_record_for_test(
            matrix_kind="normal",
            workload=workload.value,
            sample_kind=sample,
            correctness=not (workload == Workload.W1 and sample == "measured-1"),
            error="ProviderError" if workload == Workload.W1 and sample == "measured-1" else None,
        )
        for workload in NORMAL_WORKLOADS
        for sample in EXPECTED_SAMPLE_KINDS
    ]
    records.extend(
        _v8_record_for_test(
            matrix_kind="scaling",
            workload=scale.value,
            row_bound=bound,
            sample_kind=sample,
        )
        for scale in SCALE_WORKLOADS
        for bound in ROW_BOUNDS
        for sample in EXPECTED_SAMPLE_KINDS
    )
    normal_complete, normal_counts = _v8_coverage(records, "normal")
    scaling_complete, scaling_counts = _v8_coverage(records, "scaling")
    assert normal_complete is True
    assert scaling_complete is True
    assert normal_counts["actual"] == 30
    assert scaling_counts["actual"] == 36
    summary = _summarize_v8(records, RepositoryServiceSettings())
    assert summary["records"] == 66
    assert summary["unique_measurement_keys"] == 66
    assert summary["formal_status"] == "no-go"
    assert summary["selected_provider"] is None
    assert summary["candidate_b_status"] == "reserved_not_evaluated"


def test_v8_batch_contract_and_multiple_oversized_rows() -> None:
    metrics: dict[str, object] = {
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
    }
    _observe_batch_metrics(metrics, [("x" * 5,)], row_bound=1024, byte_bound=4)
    _observe_batch_metrics(metrics, [("y" * 6,)], row_bound=1024, byte_bound=4)
    assert metrics["oversized_single_row"] is True
    assert metrics["oversized_row_count"] == 2
    assert metrics["batch_contract_valid"] is True
    assert metrics["max_oversized_row_bytes"] == 6
    assert metrics["oversized_batch_count"] == 2
    invalid_metrics: dict[str, object] = {
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
    }
    _observe_batch_metrics(
        invalid_metrics, [("a" * 3,), ("b" * 3,)], row_bound=1024, byte_bound=4
    )
    assert invalid_metrics["oversized_single_row"] is False
    assert invalid_metrics["batch_contract_valid"] is False
    assert invalid_metrics["batch_contract_violation_count"] == 1
    assert _v8_batch_contract_valid(
        {
            "batch_contract_valid": True,
            "batch_contract_violation_count": 0,
            "total_rows": 2,
            "total_stream_payload_bytes": 2,
            "batch_count": 1,
            "max_batch_rows": 2,
            "max_batch_bytes": 2,
            "max_row_bytes": 1,
            "oversized_row_count": 0,
            "max_oversized_row_bytes": 0,
            "oversized_batch_count": 0,
            "byte_bound_reason": None,
            "record_batch_byte_bound": V8_BYTE_BOUND,
            "record_batch_row_bound": 1024,
            "oversized_single_row": False,
        }
    ) is True

    invalid_multi_row: dict[str, object] = {
        "total_rows": 2,
        "total_stream_payload_bytes": 6,
        "batch_count": 1,
        "max_batch_rows": 2,
        "max_batch_bytes": 6,
        "max_row_bytes": 3,
        "oversized_row_count": 0,
        "max_oversized_row_bytes": 0,
        "oversized_batch_count": 0,
        "byte_bound_reason": None,
        "oversized_single_row": False,
        "batch_contract_valid": False,
        "batch_contract_violation_count": 1,
        "record_batch_row_bound": 1024,
        "record_batch_byte_bound": V8_BYTE_BOUND,
    }
    assert _v8_batch_contract_valid(invalid_multi_row) is False

    mixed: dict[str, object] = {
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
    }
    _observe_batch_metrics(
        mixed, [("a",)] * 100, row_bound=1024, byte_bound=V8_BYTE_BOUND
    )
    _observe_batch_metrics(
        mixed, [("b" * (V8_BYTE_BOUND + 1),)], row_bound=1024, byte_bound=V8_BYTE_BOUND
    )
    mixed.update(
        {
            "byte_bound_reason": "single_indivisible_row",
            "record_batch_byte_bound": V8_BYTE_BOUND,
            "record_batch_row_bound": 1024,
        }
    )
    assert mixed["max_batch_rows"] == 100
    assert _v8_batch_contract_valid(mixed) is True


def test_v8_ratio_is_advisory_and_resource_includes_failed_evidence() -> None:
    rows: list[dict[str, object]] = []
    for scale in SCALE_WORKLOADS:
        for bound in ROW_BOUNDS:
            for sample in (f"measured-{index}" for index in range(1, 6)):
                row = _v8_record_for_test(
                    matrix_kind="scaling",
                    workload=scale.value,
                    sample_kind=sample,
                    row_bound=bound,
                )
                row["memory_evidence"] = _v8_memory_evidence_for_test(
                    2_000_000_000 if scale == ScaleWorkload.S100 else 100
                )
                rows.append(row)
    status, ratios, reason = _v8_ratio_observation(rows)
    assert status in {"pass", "warning"}
    assert reason is None
    assert ratios
    advisory = _v8_resource_advisory(rows)
    assert advisory["observed_max_workflow_cgroup_peak_bytes"] == 2_000_000_000
    assert advisory["affects_formal_decision"] is False


def test_v8_ratio_warning_does_not_enter_the_hard_gate() -> None:
    records = [
        _v8_record_for_test(
            matrix_kind="normal",
            workload=workload.value,
            sample_kind=sample,
        )
        for workload in NORMAL_WORKLOADS
        for sample in EXPECTED_SAMPLE_KINDS
    ]
    records.extend(
        _v8_record_for_test(
            matrix_kind="scaling",
            workload=scale.value,
            row_bound=bound,
            sample_kind=sample,
        )
        for scale in SCALE_WORKLOADS
        for bound in ROW_BOUNDS
        for sample in EXPECTED_SAMPLE_KINDS
    )
    for row in records:
        if row["matrix_kind"] == "scaling" and row["workload"] == ScaleWorkload.S100.value:
            evidence = _v8_memory_evidence_for_test(2_000_000_000)
            plateau = cast(dict[str, dict[str, int]], evidence["plateau_peaks"])
            absolute = cast(
                dict[str, dict[str, int]], evidence["plateau_peaks_absolute"]
            )
            for subject in plateau:
                for window in plateau[subject]:
                    plateau[subject][window] = 200
                    absolute[subject][window] = 200
            row["memory_evidence"] = evidence
            row["plateau_peaks"] = plateau
            row["plateau_peaks_absolute"] = absolute
    summary = _summarize_v8(records, RepositoryServiceSettings())
    candidate = cast(dict[str, dict[str, object]], summary["candidate_matrix"])[Candidate.A.value]
    assert candidate["scale_ratio_observation"] == "warning"
    assert candidate["hard_gate"] is True
    assert summary["selected_provider"] == Candidate.A.value


def test_v8_runner_is_a_only_and_publishes_exact_66_records(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GATEWAY_P2R1_TARGET_CONTAINER", "1")
    sample_root = tmp_path / "samples"
    sample_root.mkdir()
    data_root = tmp_path / "repository"
    data_root.mkdir()
    monkeypatch.setattr(
        matrix_module,
        "_resolve_probe_data_root",
        lambda *_args, **_kwargs: data_root,
    )
    monkeypatch.setattr(
        matrix_module,
        "load_cgroup_topology",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        matrix_module,
        "preflight_cgroup",
        lambda *_args, **_kwargs: sample_root,
    )
    calls: list[tuple[str, tuple[Candidate, ...], int]] = []

    def fake_normal(
        _settings: RepositoryServiceSettings,
        _fixture_root: Path,
        _probe_root: Path,
        workloads: tuple[Workload, ...],
        _measured_runs: int,
        **kwargs: object,
    ) -> list[dict[str, object]]:
        selected = cast(tuple[Candidate, ...], kwargs["candidates"])
        byte_bound = cast(int, kwargs["byte_bound"])
        calls.append(("normal", selected, byte_bound))
        rows = [
            _v8_record_for_test(
                matrix_kind="normal",
                workload=workload.value,
                sample_kind=sample,
            )
            for workload in workloads
            for sample in EXPECTED_SAMPLE_KINDS
        ]
        sink = cast(Callable[[dict[str, object]], None], kwargs["record_sink"])
        for row in rows:
            sink(row)
        return rows

    def fake_scaling(
        _settings: RepositoryServiceSettings,
        _fixture_root: Path,
        _probe_root: Path,
        _measured_runs: int,
        **kwargs: object,
    ) -> list[dict[str, object]]:
        selected = cast(tuple[Candidate, ...], kwargs["candidates"])
        byte_bound = cast(int, kwargs["byte_bound"])
        calls.append(("scaling", selected, byte_bound))
        rows = [
            _v8_record_for_test(
                matrix_kind="scaling",
                workload=scale.value,
                row_bound=bound,
                sample_kind=sample,
            )
            for scale in SCALE_WORKLOADS
            for bound in ROW_BOUNDS
            for sample in EXPECTED_SAMPLE_KINDS
        ]
        sink = cast(Callable[[dict[str, object]], None], kwargs["record_sink"])
        for row in rows:
            sink(row)
        return rows

    monkeypatch.setattr(matrix_module, "_collect_normal_records", fake_normal)
    monkeypatch.setattr(matrix_module, "_collect_scaling_records", fake_scaling)
    output = tmp_path / "v8" / "p2-r1-v8.jsonl"
    summary = run_v8_matrix(
        RepositoryServiceSettings(cgroup_root=sample_root), output
    )
    assert calls == [
        ("normal", (Candidate.A,), V8_BYTE_BOUND),
        ("scaling", (Candidate.A,), V8_BYTE_BOUND),
    ]
    assert summary["records"] == 66
    assert summary["expected_records"] == 66
    assert summary["candidate_b_status"] == "reserved_not_evaluated"
    assert summary["selected_provider"] == Candidate.A.value


def test_v8_a_w0_smoke_is_a_only_v8_and_diagnostic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GATEWAY_P2R1_TARGET_CONTAINER", "1")
    sample_root = tmp_path / "samples"
    sample_root.mkdir()
    data_root = tmp_path / "repository"
    data_root.mkdir()
    monkeypatch.setattr(matrix_module, "_resolve_probe_data_root", lambda *_args, **_kwargs: data_root)
    monkeypatch.setattr(matrix_module, "load_cgroup_topology", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(matrix_module, "preflight_cgroup", lambda *_args, **_kwargs: sample_root)

    def fake_normal(*args: object, **kwargs: object) -> list[dict[str, object]]:
        assert cast(tuple[Candidate, ...], kwargs["candidates"]) == (Candidate.A,)
        assert cast(int, kwargs["byte_bound"]) == V8_BYTE_BOUND
        row = _v8_record_for_test(
            matrix_kind="normal",
            workload=Workload.W0.value,
            sample_kind="warmup",
        )
        sink = cast(Callable[[dict[str, object]], None], kwargs["record_sink"])
        sink(row)
        return [row]

    monkeypatch.setattr(matrix_module, "_collect_normal_records", fake_normal)
    output = tmp_path / "a-w0.jsonl"
    summary = run_v8_a_w0_smoke(RepositoryServiceSettings(cgroup_root=sample_root), output)
    assert summary["diagnostic_only"] is True
    assert summary["formal_decision"] is False
    assert summary["selected_provider"] is None
    assert summary["methodology_version"] == V8_METHODOLOGY
    raw = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
    assert raw["diagnostic_only"] is True
    assert raw["record_batch_byte_bound"] == V8_BYTE_BOUND
    assert raw["candidate"] == Candidate.A.value
    report = output.with_suffix(".md").read_text(encoding="utf-8")
    assert "status: `diagnostic_only`" in report
    assert "| Result |" in report
    assert "| not_evaluated |" in report
    assert "| fail |" not in report


def test_v8_record_contract_and_w2_split_are_hard_requirements() -> None:
    record = _v8_record_for_test(
        matrix_kind="normal",
        workload=Workload.W2.value,
        sample_kind="warmup",
    )
    assert matrix_module._v8_record_contract_valid(record) is True
    record["record_batch_row_bound"] = 256
    assert matrix_module._v8_record_contract_valid(record) is False
    record["record_batch_row_bound"] = 1024
    record["methodology_version"] = "p2-r1-audit-corrective-v7"
    assert matrix_module._v8_record_contract_valid(record) is False
    record["methodology_version"] = V8_METHODOLOGY
    record["oversized_row_count"] = 1
    record["oversized_single_row"] = True
    record["oversized_batch_count"] = 1
    record["max_oversized_row_bytes"] = V8_BYTE_BOUND + 1
    record["max_row_bytes"] = V8_BYTE_BOUND + 1
    record["max_batch_bytes"] = V8_BYTE_BOUND + 1
    record["total_stream_payload_bytes"] = V8_BYTE_BOUND + 1
    record["byte_bound_reason"] = "single_indivisible_row"
    assert _v8_batch_contract_valid(record) is True
    record["byte_bound_reason"] = None
    assert _v8_batch_contract_valid(record) is False


def test_v8_support_envelope_uses_commit_fixture_size(tmp_path: Path) -> None:
    fixture = generate_scale_fixture(tmp_path, ScaleWorkload.S100)
    assert _support_envelope(fixture) == "validated"
