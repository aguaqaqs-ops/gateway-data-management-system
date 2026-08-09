"""Shared correctness workflow and measurements for both P2-R1 providers."""

from __future__ import annotations

import re
import os
import pickle
import signal
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from uuid import UUID, uuid4

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_service.arrow_mapping import (
    CompiledTablePlan,
    UnknownSqlTypeError,
    UnknownTypePolicy,
    TableCatalog,
    compile_table_plan,
)
from gateway_repository_service.filesystem import (
    StorageSnapshot,
    filesystem_quiesce,
    storage_root_identity,
    storage_snapshot,
    tree_storage_bytes,
)
from gateway_repository_service.fixtures import Fixture, Workload
from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.locking import DurableRootLock
from gateway_repository_service.process import (
    DoltRunner,
    ProcessBoundaryError,
    WorkflowCgroupScope,
    current_cgroup_membership,
    fork_exec_gated,
    release_gated_process,
    terminate_process_group_and_reap,
)
from gateway_repository_service.publication import atomic_publish
from gateway_repository_service.providers import (
    OfflineCliProvider,
    Provider,
    ProviderError,
    SqlServerProvider,
)
from gateway_repository_service.settings import RepositoryServiceSettings


class Candidate(StrEnum):
    A = "candidate_a_offline_cli"
    B = "candidate_b_sql_server"


@dataclass(frozen=True)
class WorkflowMeasurement:
    candidate: Candidate
    workload: StrEnum
    sample_kind: str
    correctness: bool
    hard_gates: dict[str, bool]
    initial_commit_id: str | None
    new_commit_id: str | None
    total_rows: int
    batch_metrics: dict[str, object]
    time_to_first_batch_seconds: float | None
    total_stream_seconds: float | None
    stream_peak_rss_kib: int
    stream_rss_delta_kib: int
    memory_evidence: dict[str, object]
    plateau_peaks: dict[str, dict[str, int | None]]
    plateau_peaks_absolute: dict[str, dict[str, int | None]]
    provider_startup_seconds: float | None
    import_seconds: float | None
    rows_per_second: float | None
    peak_rss_kib: int
    cancel_cleanup_seconds: float | None
    logical_bytes_before: int
    logical_bytes_after: int
    allocated_bytes_before: int
    allocated_bytes_after: int
    staging_high_water_bytes: int
    storage_quiesced: bool
    storage_snapshots: dict[str, dict[str, object]]
    storage_deltas: dict[str, dict[str, object]]
    storage_snapshot_complete: bool
    error: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "candidate": self.candidate.value,
            "workload": self.workload.value,
            "sample_kind": self.sample_kind,
            "correctness": self.correctness,
            "hard_gates": self.hard_gates,
            "initial_commit_id": self.initial_commit_id,
            "new_commit_id": self.new_commit_id,
            "total_rows": self.total_rows,
            **self.batch_metrics,
            "time_to_first_batch_seconds": self.time_to_first_batch_seconds,
            "total_stream_seconds": self.total_stream_seconds,
            "stream_peak_rss_kib": self.stream_peak_rss_kib,
            "stream_rss_delta_kib": self.stream_rss_delta_kib,
            "memory_evidence": self.memory_evidence,
            "plateau_peaks": self.plateau_peaks,
            "plateau_peaks_absolute": self.plateau_peaks_absolute,
            "provider_startup_seconds": self.provider_startup_seconds,
            "import_seconds": self.import_seconds,
            "rows_per_second": self.rows_per_second,
            "peak_rss_kib": self.peak_rss_kib,
            "cancel_cleanup_seconds": self.cancel_cleanup_seconds,
            "logical_bytes_before": self.logical_bytes_before,
            "logical_bytes_after": self.logical_bytes_after,
            "allocated_bytes_before": self.allocated_bytes_before,
            "allocated_bytes_after": self.allocated_bytes_after,
            "staging_high_water_bytes": self.staging_high_water_bytes,
            "storage_quiesced": self.storage_quiesced,
            "storage_snapshots": self.storage_snapshots,
            "storage_deltas": self.storage_deltas,
            "storage_snapshot_complete": self.storage_snapshot_complete,
            "error": self.error,
        }


def run_workflow(
    settings: RepositoryServiceSettings,
    candidate: Candidate,
    fixture: Fixture,
    *,
    sample_kind: str,
    run_unknown_reject: bool = True,
    base_fixture: Fixture | None = None,
    root_parent: Path | None = None,
    restart_before_stream: bool = False,
) -> WorkflowMeasurement:
    """Run a diagnostic workflow in the current process.

    The formal matrix uses ``run_workflow_isolated`` below. Keeping this
    direct entry point makes small local correctness probes cheap while
    ensuring they cannot be mistaken for formal bounded evidence.
    """

    return _run_workflow_in_process(
        settings,
        candidate,
        fixture,
        sample_kind=sample_kind,
        run_unknown_reject=run_unknown_reject,
        base_fixture=base_fixture,
        root_parent=root_parent,
        restart_before_stream=restart_before_stream,
    )


def _run_workflow_in_process(
    settings: RepositoryServiceSettings,
    candidate: Candidate,
    fixture: Fixture,
    *,
    sample_kind: str,
    run_unknown_reject: bool = True,
    base_fixture: Fixture | None = None,
    root_parent: Path | None = None,
    restart_before_stream: bool = False,
) -> WorkflowMeasurement:
    if root_parent is not None:
        root_parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix="gateway-p2r1-", dir=str(root_parent) if root_parent is not None else None
    ) as temporary:
        root = Path(temporary) / "data-root"
        layout = DurableLayout.create_for_probe(root)
        with DurableRootLock(layout.service_lock):
            return _run_locked(
                settings,
                candidate,
                fixture,
                layout,
                sample_kind=sample_kind,
                run_unknown_reject=run_unknown_reject,
                base_fixture=base_fixture,
                restart_before_stream=restart_before_stream,
            )


def run_workflow_isolated(
    settings: RepositoryServiceSettings,
    candidate: Candidate,
    fixture: Fixture,
    *,
    sample_kind: str,
    run_unknown_reject: bool = True,
    base_fixture: Fixture | None = None,
    root_parent: Path | None = None,
    restart_before_stream: bool = False,
    worker_operation: str = "workflow",
) -> WorkflowMeasurement | dict[str, object]:
    """Run one sample in a fresh exec'd worker attached to its own cgroup."""

    if settings.cgroup_root is None:
        raise ProcessBoundaryError("formal sample requires a delegated cgroup root")
    target_container = os.environ.get("GATEWAY_P2R1_TARGET_CONTAINER") == "1"
    expected_supervisor = os.environ.get(
        "GATEWAY_REPOSITORY_CGROUP_SUPERVISOR_CONTROL_GROUP"
    )
    layout_verified = os.environ.get("GATEWAY_REPOSITORY_CGROUP_LAYOUT_VERIFIED") == "1"
    if target_container and (expected_supervisor is None or not layout_verified):
        raise ProcessBoundaryError("formal target cgroup identity is unavailable")
    if expected_supervisor is not None and current_cgroup_membership() != expected_supervisor:
        raise ProcessBoundaryError(
            "formal supervisor PID is not in the launcher-authorized supervisor cgroup"
        )
    if root_parent is not None:
        root_parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix="gateway-p2r1-worker-", dir=str(root_parent) if root_parent is not None else None
    ) as temporary:
        temp_root = Path(temporary)
        payload_path = temp_root / "payload.pickle"
        result_path = temp_root / "result.pickle"
        scope = WorkflowCgroupScope(
            settings.cgroup_root,
            grace_seconds=settings.terminate_grace_seconds,
            memory_limit_bytes=(
                settings.v8_memory_safety_ceiling_bytes
                if settings.measurement_methodology_version
                == settings.v8_measurement_methodology_version
                else None
            ),
        )
        pid: int | None = None
        gate_write: int | None = None
        status: int | None = None
        worker_error: str | None = None
        cleanup_error: str | None = None
        try:
            scope.create()
            sample_path = scope.path
            if sample_path is None:
                raise ProcessBoundaryError("workflow cgroup path was not created")
            worker_settings = settings.model_copy(update={"cgroup_root": sample_path})
            with payload_path.open("wb") as handle:
                pickle.dump(
                    {
                        "settings": worker_settings,
                        "candidate": candidate,
                        "fixture": fixture,
                        "sample_kind": sample_kind,
                        "run_unknown_reject": run_unknown_reject,
                        "base_fixture": base_fixture,
                        "root_parent": root_parent,
                        "restart_before_stream": restart_before_stream,
                        "worker_operation": worker_operation,
                    },
                    handle,
                    protocol=pickle.HIGHEST_PROTOCOL,
                )
                handle.flush()
                os.fsync(handle.fileno())
            pid, gate_write = fork_exec_gated(
                [
                    sys.executable,
                    "-m",
                    "gateway_repository_service.workflow_worker",
                    str(payload_path),
                    str(result_path),
                ]
            )
            scope.attach(pid)
            if expected_supervisor is not None and current_cgroup_membership() != expected_supervisor:
                raise ProcessBoundaryError("supervisor PID moved during worker setup")
            release_gated_process(gate_write)
            gate_write = None
            status = _wait_worker(pid, worker_settings)
            # A worker launched in the container PID namespace can orphan a
            # short-lived Dolt helper to matrix PID 1.  Reap those adopted
            # children from the supervisor before inspecting/removing the
            # sample cgroup.
            DoltRunner.reap_adopted_dolt_children()
            if status != 0:
                worker_error = f"worker exited abnormally (status={status})"
        except BaseException as exc:
            worker_error = f"{type(exc).__name__}: {_sanitize_error(str(exc))}"
            if gate_write is not None:
                try:
                    os.close(gate_write)
                except OSError:
                    pass
            if pid is not None:
                _terminate_worker(pid, settings)
        finally:
            if pid is not None and status is None:
                _terminate_worker(pid, settings)
            DoltRunner.reap_adopted_dolt_children()
            try:
                scope.cleanup()
            except ProcessBoundaryError as exc:
                cleanup_error = f"cleanup failure: {type(exc).__name__}: {_sanitize_error(str(exc))}"
            finally:
                if gate_write is not None:
                    try:
                        os.close(gate_write)
                    except OSError:
                        pass
        if worker_error is not None or cleanup_error is not None:
            details = "; ".join(
                value for value in (worker_error, cleanup_error) if value is not None
            )
            if worker_operation == "discard":
                return _failed_discard_measurement(candidate, fixture, sample_kind, details)
            return _failed_measurement(candidate, fixture, sample_kind, details)
        if worker_error is None and result_path.is_file():
            try:
                with result_path.open("rb") as handle:
                    result = pickle.load(handle)
                if not isinstance(
                    result, dict if worker_operation == "discard" else WorkflowMeasurement
                ):
                    raise TypeError("worker result has an unexpected type")
                return result
            except (EOFError, OSError, pickle.PickleError, TypeError, ValueError) as exc:
                if worker_operation == "discard":
                    return _failed_discard_measurement(
                        candidate,
                        fixture,
                        sample_kind,
                        f"worker result invalid: {type(exc).__name__}",
                    )
                return _failed_measurement(
                    candidate,
                    fixture,
                    sample_kind,
                    f"worker result invalid: {type(exc).__name__}",
                )
        error = f"worker exited without a result (status={status})"
        if worker_operation == "discard":
            return _failed_discard_measurement(candidate, fixture, sample_kind, error)
        return _failed_measurement(candidate, fixture, sample_kind, error)


def run_offline_discard_workflow_isolated(
    settings: RepositoryServiceSettings,
    fixture: Fixture,
    *,
    sample_kind: str,
    root_parent: Path | None = None,
) -> dict[str, object]:
    result = run_workflow_isolated(
        settings,
        Candidate.A,
        fixture,
        sample_kind=sample_kind,
        root_parent=root_parent,
        worker_operation="discard",
    )
    if isinstance(result, dict):
        return result
    return _failed_discard_measurement(
        Candidate.A,
        fixture,
        sample_kind,
        "discard worker returned a workflow measurement",
    )


def _wait_worker(pid: int, settings: RepositoryServiceSettings) -> int:
    deadline = time.monotonic() + settings.import_timeout_seconds + settings.server_start_timeout_seconds
    while time.monotonic() < deadline:
        waited, status = os.waitpid(pid, os.WNOHANG)
        if waited == pid:
            DoltRunner.reap_adopted_dolt_children()
            return status
        time.sleep(0.02)
    _terminate_worker(pid, settings)
    DoltRunner.reap_adopted_dolt_children()
    return -signal.SIGKILL


def _terminate_worker(pid: int, settings: RepositoryServiceSettings) -> None:
    terminate_process_group_and_reap(pid, settings.terminate_grace_seconds)
    DoltRunner.reap_adopted_dolt_children()


W3_STORAGE_SNAPSHOT_ORDER = (
    "base_post_commit_close",
    "base_post_restart_validation",
    "delta_post_commit_close",
    "delta_post_restart_validation",
)


def _quiesced_storage_snapshot(
    root: Path, target: Path, stage: str, *, provider_closed: bool
) -> dict[str, object]:
    """Capture one comparable storage point only after provider shutdown."""

    if not provider_closed:
        raise ProviderError(f"storage snapshot {stage} taken while provider is open")
    DoltRunner.reap_adopted_dolt_children()
    filesystem_quiesce(root)
    snapshot: StorageSnapshot = storage_snapshot(target)
    if not snapshot["complete"]:
        raise ProviderError(f"storage snapshot {stage} is incomplete")
    result: dict[str, object] = dict(snapshot)
    result.update(
        {
            "stage": stage,
            "quiesce_status": "quiesced",
            "provider_closed": True,
            "server_reaped": True,
        }
    )
    return result


def _storage_delta(
    before: dict[str, object], after: dict[str, object]
) -> dict[str, object]:
    logical_before = before.get("logical_bytes")
    logical_after = after.get("logical_bytes")
    allocated_before = before.get("allocated_bytes")
    allocated_after = after.get("allocated_bytes")
    if not all(
        isinstance(value, int)
        for value in (logical_before, logical_after, allocated_before, allocated_after)
    ):
        raise ProviderError("storage snapshot delta has incomplete byte totals")
    logical_before_int = cast(int, logical_before)
    logical_after_int = cast(int, logical_after)
    allocated_before_int = cast(int, allocated_before)
    allocated_after_int = cast(int, allocated_after)
    before_items = before.get("files")
    after_items = after.get("files")
    before_list = before_items if isinstance(before_items, list) else []
    after_list = after_items if isinstance(after_items, list) else []
    before_files = {
        str(item.get("relative_path")): item
        for item in before_list
        if isinstance(item, dict) and isinstance(item.get("relative_path"), str)
    }
    after_files = {
        str(item.get("relative_path")): item
        for item in after_list
        if isinstance(item, dict) and isinstance(item.get("relative_path"), str)
    }
    changed_files = [
        {
            "relative_path": path,
            "before": before_files.get(path),
            "after": after_files.get(path),
        }
        for path in sorted(set(before_files) | set(after_files))
        if before_files.get(path) != after_files.get(path)
    ]
    return {
        "before_stage": before.get("stage"),
        "after_stage": after.get("stage"),
        "logical_delta_bytes": logical_after_int - logical_before_int,
        "allocated_delta_bytes": allocated_after_int - allocated_before_int,
        "allocated_delta_semantics": "signed_net_allocated_blocks",
        "physical_reclamation_observed": allocated_after_int - allocated_before_int < 0,
        "changed_files": changed_files,
    }


def _snapshot_bytes(snapshot: dict[str, object], key: str) -> int:
    value = snapshot.get(key)
    if not isinstance(value, int):
        raise ProviderError(f"storage snapshot field {key} is incomplete")
    return value


def _empty_batch_metrics() -> dict[str, object]:
    return {
        "total_stream_payload_bytes": 0,
        "max_row_bytes": 0,
        "batch_count": 0,
        "max_batch_rows": 0,
        "max_batch_bytes": 0,
        "oversized_single_row": False,
        "oversized_row_count": 0,
        "max_oversized_row_bytes": 0,
        "oversized_batch_count": 0,
        "batch_contract_valid": False,
        "batch_contract_violation_count": 0,
        "encoded_line_bound": None,
        "max_encoded_line_bytes": 0,
        "encoded_line_bound_valid": None,
        "encoded_line_applicable": None,
    }


def _batch_metric_int(metrics: Mapping[str, object], key: str) -> int:
    value = metrics.get(key)
    return int(value) if isinstance(value, (int, float, str)) else 0


def _merge_batch_metrics(
    total: dict[str, object], current: Mapping[str, object]
) -> None:
    total["total_stream_payload_bytes"] = (
        _batch_metric_int(total, "total_stream_payload_bytes")
        + _batch_metric_int(current, "total_stream_payload_bytes")
    )
    total["max_row_bytes"] = max(
        _batch_metric_int(total, "max_row_bytes"),
        _batch_metric_int(current, "max_row_bytes"),
    )
    total["batch_count"] = _batch_metric_int(total, "batch_count") + _batch_metric_int(
        current, "batch_count"
    )
    total["max_batch_rows"] = max(
        _batch_metric_int(total, "max_batch_rows"),
        _batch_metric_int(current, "max_batch_rows"),
    )
    total["max_batch_bytes"] = max(
        _batch_metric_int(total, "max_batch_bytes"),
        _batch_metric_int(current, "max_batch_bytes"),
    )
    total["oversized_single_row"] = bool(total["oversized_single_row"]) or bool(
        current.get("oversized_single_row", False)
    )
    total["oversized_row_count"] = _batch_metric_int(
        total, "oversized_row_count"
    ) + _batch_metric_int(current, "oversized_row_count")
    total["oversized_batch_count"] = _batch_metric_int(
        total, "oversized_batch_count"
    ) + _batch_metric_int(current, "oversized_batch_count")
    total["max_oversized_row_bytes"] = max(
        _batch_metric_int(total, "max_oversized_row_bytes"),
        _batch_metric_int(current, "max_oversized_row_bytes"),
    )
    total["batch_contract_valid"] = bool(total["batch_contract_valid"]) and bool(
        current.get("batch_contract_valid", False)
    )
    total["batch_contract_violation_count"] = (
        _batch_metric_int(total, "batch_contract_violation_count")
        + _batch_metric_int(current, "batch_contract_violation_count")
    )
    if current.get("encoded_line_applicable") is True:
        total["encoded_line_applicable"] = True
        total["encoded_line_bound"] = current.get("encoded_line_bound")
        total["max_encoded_line_bytes"] = max(
            _batch_metric_int(total, "max_encoded_line_bytes"),
            _batch_metric_int(current, "max_encoded_line_bytes"),
        )
        current_valid = current.get("encoded_line_bound_valid")
        total["encoded_line_bound_valid"] = (
            bool(total["encoded_line_bound_valid"])
            if total["encoded_line_bound_valid"] is not None
            else True
        ) and current_valid is True
    elif total["encoded_line_applicable"] is None:
        total["encoded_line_applicable"] = current.get("encoded_line_applicable")


def _failed_measurement(
    candidate: Candidate, fixture: Fixture, sample_kind: str, error: str
) -> WorkflowMeasurement:
    plateau: dict[str, dict[str, int | None]] = {
        subject: {window: None for window in ("first_10pct", "middle_10pct", "final_10pct")}
        for subject in ("workflow_process_tree", "provider_process_tree", "arrow_memory_pool", "cgroup")
    }
    plateau_absolute = {
        subject: dict(values) for subject, values in plateau.items()
    }
    return WorkflowMeasurement(
        candidate=candidate,
        workload=fixture.workload,
        sample_kind=sample_kind,
        correctness=False,
        hard_gates={
            "workflow": False,
            "cancellation": False,
            "restart": False,
            "bounded_stream": False,
            "unknown_type": False,
        },
        initial_commit_id=None,
        new_commit_id=None,
        total_rows=0,
        batch_metrics=_empty_batch_metrics(),
        time_to_first_batch_seconds=None,
        total_stream_seconds=None,
        stream_peak_rss_kib=0,
        stream_rss_delta_kib=0,
        memory_evidence={"coverage": "unavailable", "plateau_peaks": plateau},
        plateau_peaks=plateau,
        plateau_peaks_absolute=plateau_absolute,
        provider_startup_seconds=None,
        import_seconds=None,
        rows_per_second=None,
        peak_rss_kib=0,
        cancel_cleanup_seconds=None,
        logical_bytes_before=0,
        logical_bytes_after=0,
        allocated_bytes_before=0,
        allocated_bytes_after=0,
        staging_high_water_bytes=0,
        storage_quiesced=False,
        storage_snapshots={},
        storage_deltas={},
        storage_snapshot_complete=False,
        error=error,
    )


def _failed_discard_measurement(
    candidate: Candidate, fixture: Fixture, sample_kind: str, error: str
) -> dict[str, object]:
    plateau = {
        subject: {window: None for window in ("first_10pct", "middle_10pct", "final_10pct")}
        for subject in ("workflow_process_tree", "provider_process_tree", "arrow_memory_pool", "cgroup")
    }
    return {
        "candidate": candidate.value,
        "workload": fixture.workload.value,
        "sample_kind": sample_kind,
        "correctness": False,
        "hard_gates": {"workflow": False, "cancellation": False, "restart": False},
        "initial_commit_id": None,
        "new_commit_id": None,
        "total_rows": 0,
        "time_to_first_batch_seconds": None,
        "total_stream_seconds": None,
        "stream_peak_rss_kib": 0,
        "stream_rss_delta_kib": 0,
        "memory_evidence": {"coverage": "unavailable", "plateau_peaks": plateau},
        "plateau_peaks": plateau,
        "plateau_peaks_absolute": {
            subject: dict(values) for subject, values in plateau.items()
        },
        "provider_startup_seconds": None,
        "import_seconds": None,
        "rows_per_second": None,
        "peak_rss_kib": 0,
        "cancel_cleanup_seconds": None,
        "logical_bytes_before": 0,
        "logical_bytes_after": 0,
        "allocated_bytes_before": 0,
        "allocated_bytes_after": 0,
        "staging_high_water_bytes": 0,
        "storage_quiesced": False,
        "storage_snapshots": {},
        "storage_deltas": {},
        "storage_snapshot_complete": False,
        "diagnostic_correctness_scope": "catalog_and_exit_only",
        "error": error,
    }


def _run_locked(
    settings: RepositoryServiceSettings,
    candidate: Candidate,
    fixture: Fixture,
    layout: DurableLayout,
    *,
    sample_kind: str,
    run_unknown_reject: bool,
    base_fixture: Fixture | None,
    restart_before_stream: bool = False,
) -> WorkflowMeasurement:
    initial_commit: str | None = None
    new_commit: str | None = None
    base_catalog: tuple[TableCatalog, ...] = ()
    provider: Provider | None = None
    error: str | None = None
    correctness = False
    hard_gates = {
        "workflow": False,
        "cancellation": False,
        "restart": False,
        "bounded_stream": False,
        "unknown_type": False,
    }
    first_batch_seconds: float | None = None
    stream_seconds: float | None = None
    provider_startup_seconds: float | None = None
    import_seconds: float | None = None
    cancel_seconds: float | None = None
    total_rows = 0
    batch_metrics = _empty_batch_metrics()
    batch_metrics["batch_contract_valid"] = True
    stream_peak_rss_kib = 0
    stream_rss_delta_kib = 0
    plateau_peaks: dict[str, dict[str, int | None]] = {
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
    plateau_peaks_absolute: dict[str, dict[str, int | None]] = {
        subject: dict(values) for subject, values in plateau_peaks.items()
    }
    memory_evidence: dict[str, object] = {
        "coverage": "unavailable",
        "reason": "stream did not complete",
        "plateau_peaks": plateau_peaks,
        "plateau_peaks_absolute": plateau_peaks_absolute,
    }
    cancellation_metrics: dict[str, object] = {}
    staging_high_water = 0
    logical_before = 0
    allocated_before = 0
    logical_after = 0
    allocated_after = 0
    storage_quiesced = False
    storage_snapshots: dict[str, dict[str, object]] = {}
    storage_deltas: dict[str, dict[str, object]] = {}
    storage_snapshot_complete = False
    restart_evidence: dict[str, object] = {}
    provider_shutdown = False
    try:
        repository_id = UUID(int=uuid4().int)
        key = repository_key(repository_id)
        staged = layout.staging_repository(key, uuid4().hex[:12])
        common = OfflineCliProvider(settings, layout, staged, DoltRunner(settings, layout.root))
        common.initialize_repository()
        staging_high_water = max(staging_high_water, tree_storage_bytes(layout.staging)[0])
        target = layout.published_repository(key)
        layout.assert_publication_devices(staged, target.parent)
        atomic_publish(staged, target)
        layout.assert_same_filesystem()
        filesystem_quiesce(layout.root)
        logical_before, allocated_before = tree_storage_bytes(target)
        runner = DoltRunner(settings, layout.root)
        provider = _make_provider(settings, layout, target, runner, candidate)
        startup_started = time.monotonic()
        provider.open()
        provider_shutdown = False
        provider_startup_seconds = time.monotonic() - startup_started
        initial_commit = provider.head()
        expected_parent = initial_commit
        replay_fixture = base_fixture or fixture
        import_started = time.monotonic()
        provider.replay(replay_fixture.replay_sql)
        if base_fixture is not None:
            base_marker = f"gateway-versioned-import operation_id={uuid4()}"
            base_commit = provider.commit_marker(base_marker)
            if provider.marker_parent(base_marker) != initial_commit:
                raise ProviderError("base marker parent does not equal initial commit")
            expected_parent = base_commit
        marker = f"gateway-versioned-import operation_id={uuid4()}"
        if base_fixture is not None:
            # W3 uses four symmetric, quiesced points.  The first two describe
            # the base lifecycle; the delta is applied only after the base
            # restart validation has been measured.
            provider.close()
            provider = None
            provider_shutdown = True
            storage_snapshots["base_post_commit_close"] = _quiesced_storage_snapshot(
                layout.root,
                target,
                "base_post_commit_close",
                provider_closed=provider_shutdown,
            )
            provider = _make_provider(
                settings, layout, target, DoltRunner(settings, layout.root), candidate
            )
            provider.open()
            provider_shutdown = False
            if provider.head() != expected_parent:
                raise ProviderError("reopen did not preserve W3 base commit")
            initial_catalog = provider.catalog(initial_commit, initial_commit)
            if initial_catalog:
                raise ProviderError("initial commit unexpectedly contained user tables")
            base_catalog = provider.catalog(initial_commit, expected_parent)
            _assert_catalog_exact(base_catalog, base_fixture)
            base_rows = _stream_and_validate(provider, expected_parent, base_catalog, base_fixture)
            if base_rows != base_fixture.rows:
                raise ProviderError("base pinned read row count mismatch")
            provider.close()
            provider = None
            provider_shutdown = True
            storage_snapshots["base_post_restart_validation"] = _quiesced_storage_snapshot(
                layout.root,
                target,
                "base_post_restart_validation",
                provider_closed=provider_shutdown,
            )
            storage_deltas["base_restart_delta"] = _storage_delta(
                storage_snapshots["base_post_commit_close"],
                storage_snapshots["base_post_restart_validation"],
            )
            logical_before = _snapshot_bytes(
                storage_snapshots["base_post_restart_validation"], "logical_bytes"
            )
            allocated_before = _snapshot_bytes(
                storage_snapshots["base_post_restart_validation"], "allocated_bytes"
            )
            provider = _make_provider(
                settings, layout, target, DoltRunner(settings, layout.root), candidate
            )
            provider.open()
            provider_shutdown = False
            if provider.head() != expected_parent:
                raise ProviderError("base commit changed before delta replay")
            provider.replay(fixture.replay_sql)
        new_commit = provider.commit_marker(marker)
        import_seconds = time.monotonic() - import_started
        if provider.head() != new_commit:
            raise ProviderError("main does not point to marker commit")
        if provider.marker_count(marker) != 1:
            raise ProviderError("operation marker is not unique")
        if provider.marker_parent(marker) != expected_parent:
            raise ProviderError("marker parent does not equal initial commit")
        initial_catalog = provider.catalog(initial_commit, initial_commit)
        if initial_catalog:
            raise ProviderError("initial commit unexpectedly contained user tables")
        actual_catalog = provider.catalog(initial_commit, new_commit)
        _assert_catalog_exact(actual_catalog, fixture)
        if base_fixture is not None and expected_parent is None:
            raise ProviderError("base commit was not created")

        if base_fixture is not None:
            # Measure the commit-only point, validate the new immutable state,
            # then measure the symmetric post-restart point.  The final reopen
            # below is intentionally reserved for stream/cancel evidence.
            provider.close()
            provider = None
            provider_shutdown = True
            storage_snapshots["delta_post_commit_close"] = _quiesced_storage_snapshot(
                layout.root,
                target,
                "delta_post_commit_close",
                provider_closed=provider_shutdown,
            )
            provider = _make_provider(
                settings, layout, target, DoltRunner(settings, layout.root), candidate
            )
            provider.open()
            provider_shutdown = False
            if provider.head() != new_commit or provider.marker_count(marker) != 1:
                raise ProviderError("delta restart did not preserve commit/ref/marker")
            if provider.catalog(initial_commit, new_commit) != actual_catalog:
                raise ProviderError("delta restart catalog changed")
            if provider.catalog(initial_commit, initial_commit) != initial_catalog:
                raise ProviderError("delta restart changed old immutable catalog")
            if provider.catalog(initial_commit, expected_parent) != base_catalog:
                raise ProviderError("delta restart changed base immutable catalog")
            delta_rows = _stream_and_validate(provider, new_commit, actual_catalog, fixture)
            if delta_rows != fixture.rows:
                raise ProviderError("delta restart new pinned read row count mismatch")
            base_rows_restart = _stream_and_validate(
                provider, expected_parent, base_catalog, base_fixture
            )
            if base_rows_restart != base_fixture.rows:
                raise ProviderError("delta restart old pinned read row count mismatch")
            provider.close()
            provider = None
            provider_shutdown = True
            storage_snapshots["delta_post_restart_validation"] = _quiesced_storage_snapshot(
                layout.root,
                target,
                "delta_post_restart_validation",
                provider_closed=provider_shutdown,
            )
            storage_deltas["delta_commit_delta"] = _storage_delta(
                storage_snapshots["base_post_restart_validation"],
                storage_snapshots["delta_post_commit_close"],
            )
            storage_deltas["delta_restart_delta"] = _storage_delta(
                storage_snapshots["delta_post_commit_close"],
                storage_snapshots["delta_post_restart_validation"],
            )
            storage_deltas["comparable_delta"] = _storage_delta(
                storage_snapshots["base_post_restart_validation"],
                storage_snapshots["delta_post_restart_validation"],
            )
            logical_before = _snapshot_bytes(
                storage_snapshots["base_post_restart_validation"], "logical_bytes"
            )
            allocated_before = _snapshot_bytes(
                storage_snapshots["base_post_restart_validation"], "allocated_bytes"
            )
            logical_after = _snapshot_bytes(
                storage_snapshots["delta_post_restart_validation"], "logical_bytes"
            )
            allocated_after = _snapshot_bytes(
                storage_snapshots["delta_post_restart_validation"], "allocated_bytes"
            )
            storage_snapshot_complete = all(
                bool(storage_snapshots.get(stage, {}).get("complete"))
                and storage_snapshots[stage].get("quiesce_status") == "quiesced"
                and storage_snapshots[stage].get("provider_closed") is True
                for stage in W3_STORAGE_SNAPSHOT_ORDER
            )
            if not storage_snapshot_complete:
                raise ProviderError("W3 storage snapshot lifecycle is incomplete")
            provider = _make_provider(
                settings, layout, target, DoltRunner(settings, layout.root), candidate
            )
            provider.open()
            provider_shutdown = False

        if restart_before_stream:
            if provider is None:
                raise ProviderError("pre-stream restart has no active provider")
            previous_provider = provider
            provider = None
            provider_shutdown = True
            restart_started = time.monotonic()
            before_identity = _provider_identity(previous_provider)
            provider = _restart_provider_for_stream(
                settings,
                layout,
                target,
                candidate,
                previous_provider,
                initial_commit=initial_commit,
                new_commit=new_commit,
                actual_catalog=actual_catalog,
            )
            provider_shutdown = False
            restart_evidence = {
                "enabled": True,
                "before_provider_identity": before_identity,
                "after_provider_identity": _provider_identity(provider),
                "identity_changed": before_identity != _provider_identity(provider),
                "shutdown_reap_quiesce": True,
                "duration_seconds": time.monotonic() - restart_started,
                "head_preserved": provider.head() == new_commit,
                "catalog_preserved": provider.catalog(initial_commit, new_commit)
                == actual_catalog,
                "storage_identity": storage_root_identity(target),
            }

        stream_start = time.monotonic()
        first_seen = False
        for table in actual_catalog:
            plan = compile_table_plan(table, UnknownTypePolicy.STRINGIFY)
            for batch in provider.stream_table(
                new_commit,
                table,
                UnknownTypePolicy.STRINGIFY,
                table_plan=plan,
            ):
                if not first_seen:
                    first_batch_seconds = time.monotonic() - stream_start
                    first_seen = True
                _assert_batch_contract(batch, plan)
                _assert_fixture_values(fixture, table.name, batch.to_pylist())
                total_rows += batch.num_rows
            _merge_batch_metrics(
                batch_metrics,
                cast(Mapping[str, object], getattr(provider, "last_stream_metrics", {})),
            )
        stream_seconds = time.monotonic() - stream_start
        stream_peak_rss_kib = int(getattr(provider, "last_stream_peak_rss_kib", 0))
        stream_rss_delta_kib = int(getattr(provider, "last_stream_rss_delta_kib", 0))
        if total_rows != sum(table.row_count for table in actual_catalog):
            raise ProviderError("stream row count mismatch")
        if base_fixture is not None:
            base_rows_after = _stream_and_validate(
                provider, expected_parent, base_catalog, base_fixture
            )
            if base_rows_after != base_fixture.rows:
                raise ProviderError("old pinned commit changed after new commit")
        if first_batch_seconds is None or stream_seconds <= 0:
            raise ProviderError("stream did not produce a measurable batch")
        memory_evidence = dict(getattr(provider, "last_stream_metrics", {}))
        if restart_evidence:
            memory_evidence["restart_diagnostic"] = restart_evidence
        plateau_peaks = dict(
            getattr(
                provider,
                "last_plateau_peaks",
                plateau_peaks,
            )
        )
        plateau_peaks_absolute = dict(
            getattr(provider, "last_plateau_peaks_absolute", plateau_peaks_absolute)
        )
        memory_evidence["plateau_peaks"] = plateau_peaks
        memory_evidence["plateau_peaks_absolute"] = plateau_peaks_absolute
        memory_evidence["baseline_coverage"] = _baseline_memory_coverage(memory_evidence)
        memory_evidence["cgroup_stat_coverage"] = bool(
            memory_evidence.get("cgroup_stat_anon_bytes") is not None
            and memory_evidence.get("cgroup_stat_file_bytes") is not None
            and memory_evidence.get("cgroup_baseline_stat_anon_bytes") is not None
            and memory_evidence.get("cgroup_baseline_stat_file_bytes") is not None
            and memory_evidence.get("cgroup_stat_anon_delta_bytes") is not None
            and memory_evidence.get("cgroup_stat_file_delta_bytes") is not None
        )
        memory_evidence["coverage"] = (
            "available"
            if memory_evidence.get("cgroup_per_workflow") is True
            and memory_evidence.get("baseline_coverage") is True
            and memory_evidence.get("cgroup_stat_coverage") is True
            and _complete_plateau_peaks(plateau_peaks, allow_zero=True)
            and _complete_plateau_peaks(plateau_peaks_absolute)
            else "inconclusive"
        )
        hard_gates["bounded_stream"] = memory_evidence["coverage"] == "available"
        hard_gates["bounded_stream"] = bool(hard_gates["bounded_stream"]) and bool(
            batch_metrics["batch_contract_valid"]
            and _batch_metric_int(batch_metrics, "batch_contract_violation_count") == 0
        )

        first_table = actual_catalog[0]
        cancelled = provider.stream_table(new_commit, first_table, UnknownTypePolicy.STRINGIFY)
        next(cancelled)
        cancel_start = time.monotonic()
        close = getattr(cancelled, "close", None)
        if callable(close):
            close()
        cancel_seconds = time.monotonic() - cancel_start
        cancellation_metrics = dict(getattr(provider, "last_stream_metrics", {}))
        memory_evidence["cancellation_connection_reset"] = bool(
            cancellation_metrics.get("cleanup_connection_reset", False)
        )
        memory_evidence["cancellation_cleanup_duration_seconds"] = cancel_seconds
        hard_gates["cancellation"] = cancel_seconds < settings.terminate_grace_seconds * 2
        reread_rows = sum(
            batch.num_rows
            for batch in provider.stream_table(new_commit, first_table, UnknownTypePolicy.STRINGIFY)
        )
        if reread_rows != first_table.row_count:
            raise ProviderError("read after cancellation was contaminated")

        if run_unknown_reject:
            unknown = next(
                (table for table in actual_catalog if table.name == "unknown_types"), None
            )
            if unknown is not None:
                try:
                    list(provider.stream_table(new_commit, unknown, UnknownTypePolicy.REJECT))
                except UnknownSqlTypeError:
                    hard_gates["unknown_type"] = True
                else:
                    raise ProviderError("unknown type did not reject")
            else:
                hard_gates["unknown_type"] = True
        else:
            hard_gates["unknown_type"] = True

        provider.close()
        provider = None
        provider_shutdown = True
        if base_fixture is None:
            restart_runner = DoltRunner(settings, layout.root)
            restarted = _make_provider(settings, layout, target, restart_runner, candidate)
            restarted.open()
            provider_shutdown = False
            try:
                if restarted.head() != new_commit or restarted.marker_count(marker) != 1:
                    raise ProviderError("restart did not preserve commit/ref/marker")
                if restarted.catalog(initial_commit, new_commit) != actual_catalog:
                    raise ProviderError("restart catalog changed")
                if restarted.catalog(initial_commit, initial_commit) != initial_catalog:
                    raise ProviderError("restart changed old immutable catalog")
            finally:
                restarted.close()
                provider_shutdown = True
            filesystem_quiesce(layout.root)
            logical_after, allocated_after = tree_storage_bytes(target)
            storage_quiesced = True
        else:
            storage_quiesced = storage_snapshot_complete
        hard_gates["restart"] = storage_quiesced
        hard_gates["workflow"] = True
        correctness = _workflow_correctness(hard_gates)
    except Exception as exc:
        error = type(exc).__name__ + ": " + _sanitize_error(str(exc))
    finally:
        if provider is not None:
            try:
                provider.close()
                provider = None
                provider_shutdown = True
            except Exception as exc:
                provider_shutdown = False
                if error is None:
                    error = type(exc).__name__ + ": " + _sanitize_error(str(exc))
        try:
            filesystem_quiesce(layout.root)
            storage_quiesced = provider_shutdown
        except Exception as exc:
            storage_quiesced = False
            if error is None:
                error = type(exc).__name__ + ": " + _sanitize_error(str(exc))

    total_seconds = stream_seconds or 0.0
    if error is not None:
        correctness = False
        hard_gates["workflow"] = False
    rows_per_second = total_rows / total_seconds if total_seconds > 0 else None
    return WorkflowMeasurement(
        candidate=candidate,
        workload=fixture.workload,
        sample_kind=sample_kind,
        correctness=correctness,
        hard_gates=hard_gates,
        initial_commit_id=initial_commit,
        new_commit_id=new_commit,
        total_rows=total_rows,
        batch_metrics=batch_metrics,
        time_to_first_batch_seconds=first_batch_seconds,
        total_stream_seconds=stream_seconds,
        stream_peak_rss_kib=stream_peak_rss_kib,
        stream_rss_delta_kib=stream_rss_delta_kib,
        provider_startup_seconds=provider_startup_seconds,
        import_seconds=import_seconds,
        rows_per_second=rows_per_second,
        peak_rss_kib=_as_int(memory_evidence.get("workflow_process_tree_rss_kib", 0)),
        memory_evidence=memory_evidence,
        plateau_peaks=plateau_peaks,
        plateau_peaks_absolute=plateau_peaks_absolute,
        cancel_cleanup_seconds=cancel_seconds,
        logical_bytes_before=logical_before,
        logical_bytes_after=logical_after,
        allocated_bytes_before=allocated_before,
        allocated_bytes_after=allocated_after,
        staging_high_water_bytes=staging_high_water,
        storage_quiesced=storage_quiesced,
        storage_snapshots=storage_snapshots,
        storage_deltas=storage_deltas,
        storage_snapshot_complete=storage_snapshot_complete if base_fixture is not None else True,
        error=error,
    )


def _make_provider(
    settings: RepositoryServiceSettings,
    layout: DurableLayout,
    repository: Path,
    runner: DoltRunner,
    candidate: Candidate,
) -> Provider:
    if candidate == Candidate.A:
        return OfflineCliProvider(settings, layout, repository, runner)
    return SqlServerProvider(settings, layout, repository, runner)


def _restart_provider_for_stream(
    settings: RepositoryServiceSettings,
    layout: DurableLayout,
    target: Path,
    candidate: Candidate,
    provider: Provider,
    *,
    initial_commit: str,
    new_commit: str,
    actual_catalog: tuple[TableCatalog, ...],
) -> Provider:
    """Reopen a clean provider before the diagnostic stream begins."""

    provider.close()
    replacement: Provider | None = None
    try:
        replacement = _make_provider(
            settings, layout, target, DoltRunner(settings, layout.root), candidate
        )
        replacement.open()
        if replacement.head() != new_commit:
            raise ProviderError("pre-stream restart changed the main ref")
        if replacement.catalog(initial_commit, new_commit) != actual_catalog:
            raise ProviderError("pre-stream restart changed the catalog")
        return replacement
    except BaseException:
        if replacement is not None:
            replacement.close()
        raise


def _provider_identity(provider: Provider) -> dict[str, object]:
    supervisor = getattr(provider, "supervisor", None)
    process = getattr(supervisor, "process", None)
    pid = getattr(process, "pid", None)
    return {
        "provider_type": type(provider).__name__,
        "server_pid": pid if isinstance(pid, int) else None,
    }


def _run_offline_discard_in_process(
    settings: RepositoryServiceSettings,
    fixture: Fixture,
    *,
    sample_kind: str = "diagnostic",
    root_parent: Path | None = None,
) -> dict[str, object]:
    """Measure Candidate A's SELECT path without CSV or Arrow conversion."""

    if root_parent is not None:
        root_parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix="gateway-p2r1-discard-",
        dir=str(root_parent) if root_parent is not None else None,
    ) as temporary:
        root = Path(temporary) / "data-root"
        layout = DurableLayout.create_for_probe(root)
        with DurableRootLock(layout.service_lock):
            repository_id = UUID(int=uuid4().int)
            key = repository_key(repository_id)
            staged = layout.staging_repository(key, uuid4().hex[:12])
            common = OfflineCliProvider(
                settings, layout, staged, DoltRunner(settings, layout.root)
            )
            common.initialize_repository()
            target = layout.published_repository(key)
            layout.assert_publication_devices(staged, target.parent)
            atomic_publish(staged, target)
            provider = OfflineCliProvider(
                settings,
                layout,
                target,
                DoltRunner(settings, layout.root),
            )
            try:
                provider.open()
                initial_commit = provider.head()
                provider.replay(fixture.replay_sql)
                new_commit = provider.commit_marker(
                    f"gateway-p2r1-discard operation_id={uuid4()}"
                )
                catalog = provider.catalog(initial_commit, new_commit)
                _assert_catalog_exact(catalog, fixture)
                tables = [
                    provider.discard_table_to_devnull(new_commit, table)
                    for table in catalog
                ]
                metrics = dict(provider.last_stream_metrics)
                plateau = dict(provider.last_plateau_peaks)
                plateau_absolute = dict(provider.last_plateau_peaks_absolute)
                metrics["coverage"] = (
                    "available"
                    if metrics.get("cgroup_per_workflow") is True
                    and metrics.get("baseline_arrow_memory_pool_bytes") is not None
                    and all(
                        all(value is not None for value in values.values())
                        for values in plateau.values()
                    )
                    and all(
                        all(value is not None for value in values.values())
                        for values in cast(
                            dict[str, dict[str, int | None]],
                            metrics.get("memory_stat_plateau", {}),
                        ).values()
                    )
                    else "inconclusive"
                )
                provider_result = tables[-1] if tables else {}
                return {
                    "candidate": Candidate.A.value,
                    "workload": fixture.workload.value,
                    "sample_kind": sample_kind,
                    "fixture_rows": fixture.rows,
                    "new_commit_id": new_commit,
                    "tables": tables,
                    "correctness": all(
                        isinstance(table, dict)
                        and table.get("timed_out") is False
                        for table in tables
                    ),
                    "hard_gates": {
                        "workflow": True,
                        "cancellation": True,
                        "restart": True,
                    },
                    "error": None,
                    "stream_peak_rss_kib": int(
                        metrics.get("provider_process_tree_rss_kib", 0)
                    ),
                    "stream_rss_delta_kib": int(
                        metrics.get("provider_process_tree_rss_kib", 0)
                        - metrics.get("baseline_provider_process_tree_rss_kib", 0)
                    ),
                    "peak_rss_kib": int(
                        metrics.get("provider_process_tree_rss_kib", 0)
                    ),
                    "total_rows": fixture.rows,
                    "memory_evidence": metrics,
                    "plateau_peaks": plateau,
                    "plateau_peaks_absolute": plateau_absolute,
                    "provider_startup_seconds": None,
                    "import_seconds": None,
                    "rows_per_second": None,
                    "time_to_first_batch_seconds": None,
                    "total_stream_seconds": (
                        float(cast(int | float, provider_result["duration_seconds"]))
                        if isinstance(provider_result, dict)
                        and isinstance(provider_result.get("duration_seconds"), (int, float))
                        else None
                    ),
                    "cancel_cleanup_seconds": None,
                    "initial_commit_id": initial_commit,
                    "logical_bytes_before": 0,
                    "logical_bytes_after": 0,
                    "allocated_bytes_before": 0,
                    "allocated_bytes_after": 0,
                    "staging_high_water_bytes": 0,
                    "storage_quiesced": False,
                    "storage_snapshots": {},
                    "storage_deltas": {},
                    "storage_snapshot_complete": False,
                    "diagnostic_correctness_scope": "catalog_and_exit_only",
                    "diagnostic_kind": "offline_cli_discard_to_devnull",
                }
            finally:
                provider.close()


def run_offline_discard_diagnostic(
    settings: RepositoryServiceSettings,
    fixture: Fixture,
    *,
    sample_kind: str = "diagnostic",
    root_parent: Path | None = None,
) -> dict[str, object]:
    """Run one direct-DEVNULL diagnostic in the current process.

    Formal matrix code never calls this helper; target diagnostics use the
    isolated wrapper so the provider tracker is attached to the sample cgroup.
    """

    return _run_offline_discard_in_process(
        settings,
        fixture,
        sample_kind=sample_kind,
        root_parent=root_parent,
    )


def _sanitize_error(message: str) -> str:
    return re.sub(r"/[A-Za-z0-9_.:/-]+", "<path>", message)[:512]


def _as_int(value: object) -> int:
    return int(value) if isinstance(value, (int, float, str)) else 0


def _complete_plateau_peaks(value: object, *, allow_zero: bool = False) -> bool:
    if not isinstance(value, dict):
        return False
    subjects = (
        "workflow_process_tree",
        "provider_process_tree",
        "arrow_memory_pool",
        "cgroup",
    )
    windows = ("first_10pct", "middle_10pct", "final_10pct")
    return all(
        isinstance(value.get(subject), dict)
        and all(
            isinstance(value[subject].get(window), (int, float))
            and (
                float(value[subject][window]) >= 0
                if allow_zero
                else float(value[subject][window]) > 0
            )
            for window in windows
        )
        for subject in subjects
    )


def _assert_catalog_exact(actual: tuple[TableCatalog, ...], fixture: Fixture) -> None:
    expected = fixture.expected_tables
    if len(actual) != len(expected):
        raise ProviderError("user table set mismatch")
    for actual_table, expected_table in zip(actual, expected, strict=True):
        if actual_table.name != expected_table.name:
            raise ProviderError("table order/name mismatch")
        if actual_table.row_count != expected_table.row_count:
            raise ProviderError(f"row count mismatch for {actual_table.name}")
        if actual_table.primary_key != expected_table.primary_key:
            raise ProviderError(f"primary key mismatch for {actual_table.name}")
        if len(actual_table.columns) != len(expected_table.columns):
            raise ProviderError(f"column count mismatch for {actual_table.name}")
        for actual_column, expected_column in zip(
            actual_table.columns, expected_table.columns, strict=True
        ):
            if (
                actual_column.name != expected_column.name
                or actual_column.sql_type != expected_column.sql_type
                or actual_column.nullable != expected_column.nullable
                or actual_column.primary_key_position != expected_column.primary_key_position
            ):
                raise ProviderError(
                    f"column mismatch for {actual_table.name}.{expected_column.name}"
                )


def _assert_batch_contract(batch: pa.RecordBatch, plan: CompiledTablePlan) -> None:
    table = plan.catalog
    if batch.num_columns != len(table.columns):
        raise ProviderError(f"Arrow column count mismatch for {table.name}")
    for index, column in enumerate(table.columns):
        field = batch.schema.field(index)
        expected_field = plan.expected_schema.field(index)
        if (
            field.name != column.name
            or field.type != expected_field.type
            or field.nullable != column.nullable
            or (field.metadata or {}) != (expected_field.metadata or {})
        ):
            raise ProviderError(
                f"Arrow field contract mismatch for {table.name}.{column.name}"
            )


def _stream_and_validate(
    provider: Provider,
    commit_id: str,
    catalog: tuple[TableCatalog, ...],
    fixture: Fixture,
) -> int:
    rows = 0
    for table in catalog:
        plan = compile_table_plan(table, UnknownTypePolicy.STRINGIFY)
        for batch in provider.stream_table(
            commit_id,
            table,
            UnknownTypePolicy.STRINGIFY,
            table_plan=plan,
        ):
            _assert_batch_contract(batch, plan)
            _assert_fixture_values(fixture, table.name, batch.to_pylist())
            rows += batch.num_rows
    return rows


def _assert_fixture_values(
    fixture: Fixture, table_name: str, rows: list[dict[str, object]]
) -> None:
    if fixture.workload == Workload.W0:
        if table_name == "known_types":
            by_id = {_as_int(row["id"]): row for row in rows}
            first = by_id.get(1)
            second = by_id.get(2)
            if first is None or second is None:
                raise ProviderError("W0 known_types rows missing")
            expected_first = {
                "char_value": "utf8",
                "varchar_value": "hello",
                "text_value": "世界",
                "binary_value": b"\x00\xff",
                "varbinary_value": b"\x01\x02",
                "blob_value": b"\x00\x01\x02",
            }
            expected_second = {
                "char_value": "null",
                "binary_value": b"\x00\x00",
                "varbinary_value": b"\x00",
                "blob_value": b"",
                "bool_value": None,
            }
            if any(first.get(key) != value for key, value in expected_first.items()):
                raise ProviderError("W0 known value oracle mismatch")
            if any(second.get(key) != value for key, value in expected_second.items()):
                raise ProviderError("W0 null/empty value oracle mismatch")
        elif table_name == "unknown_types":
            by_id = {_as_int(row["id"]): row for row in rows}
            if by_id.get(1, {}).get("unknown_value") != "a" or by_id.get(2, {}).get("unknown_value") is not None:
                raise ProviderError("W0 unknown stringify oracle mismatch")
        return
    if table_name != "records":
        return
    expected_ids = {1, fixture.rows // 2, fixture.rows}
    for row in rows:
        row_id = _as_int(row["id"])
        if row_id not in expected_ids:
            continue
        is_delta = fixture.workload in {Workload.W3_1, Workload.W3_10}
        changed_limit = 400 if fixture.workload == Workload.W3_1 else 4_000
        if is_delta and row_id <= changed_limit:
            expected_payload = f"changed-{row_id - 1:08d}"
        else:
            payload_width = 1800 if fixture.workload == Workload.W2 else 170
            expected_payload = f"payload-{(row_id - 1) % 1000:04d}-" + ("x" * payload_width)
        if row.get("payload") != expected_payload:
            raise ProviderError("representative row oracle mismatch")
        expected_flag = _expected_representative_flag(row_id)
        if row.get("flag") != expected_flag:
            raise ProviderError("representative NULL/value oracle mismatch")


def _expected_representative_flag(row_id: int) -> bool | None:
    """Return the representative fixture flag for a one-based row id."""

    index = row_id - 1
    return None if index % 17 == 0 else bool(index % 2)


def _baseline_memory_coverage(memory_evidence: Mapping[str, object]) -> bool:
    """Require all canonical per-workflow baseline subjects to be present."""

    return all(
        memory_evidence.get(field) is not None
        for field in (
            "baseline_workflow_process_tree_rss_kib",
            "baseline_provider_process_tree_rss_kib",
            "baseline_arrow_memory_pool_bytes",
            "cgroup_baseline_current_bytes",
        )
    )


def _workflow_correctness(hard_gates: dict[str, bool]) -> bool:
    """Return provider correctness without conflating scaling evidence.

    Bounded-stream plateau coverage is evaluated by the unified scaling gate;
    it is not a row-value correctness failure for a normal workload whose
    tiny stream cannot populate every plateau window.
    """

    return all(
        hard_gates.get(name) is True
        for name in ("workflow", "cancellation", "restart", "unknown_type")
    )
