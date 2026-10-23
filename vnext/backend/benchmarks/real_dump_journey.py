"""Run the S2b and S4 real dump journeys from the host.

The source packages are read-only inputs. Journey checks use public HTTP APIs;
the public History result exposes a pair total and digests, while its bundle
contains artifact references without a public artifact-content endpoint. No row
values or row identifiers are emitted.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx
import pyarrow as pa
import pyarrow.ipc as pa_ipc
from gateway_repository_contracts import (
    GetVersionedCatalogResponse,
    encode_commit_id_path_segment,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.real_dump_census import (
    CompositeProjectionError,
    compare_composite_packages,
)

from tests.support.compose_gate_harness import (
    BACKEND_URL,
    BASELINE_NODE_ID,
    BEARER_TOKEN,
    COMPOSE_FILE,
    DEPLOY_ROOT,
    DEVICE_KEY,
    PROJECT_ID,
    SESSION_TOKEN,
    acquire_compose_gate_lock,
    build_compose_stack_images,
    cleanup_compose_project_artifacts,
    compose_auth_headers,
    compose_image_ids,
    release_compose_gate_lock,
    run_compose,
    start_three_container_stack,
    wait_http_ok,
    wait_repository_service_ready,
    worker_ready,
)

REPOSITORY_SERVICE_IMAGE = os.environ.get(
    "GATEWAY_REPOSITORY_SERVICE_IMAGE", "gateway-repository-service:local"
)
# Compose mounts this data root for repository-service; RepositoryServiceSettings.control_db_path
# appends service-state/repository-service.sqlite3.
REPOSITORY_SERVICE_CONTROL_DB_PATH = (
    "/var/lib/gateway/repository/service-state/repository-service.sqlite3"
)
REPOSITORY_IMPORT_CONTROL_ROW_SCRIPT = r"""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

database_path, operation_id = sys.argv[1:3]
temporary = tempfile.NamedTemporaryFile(prefix="repository-import-", suffix=".sqlite3", delete=False)
snapshot_path = Path(temporary.name)
temporary.close()
try:
    source = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    try:
        snapshot = sqlite3.connect(snapshot_path)
        try:
            source.backup(snapshot)
        finally:
            snapshot.close()
    finally:
        source.close()
    snapshot = sqlite3.connect(f"file:{snapshot_path}?mode=ro", uri=True)
    try:
        snapshot.row_factory = sqlite3.Row
        row = snapshot.execute(
            "SELECT status, created_at, started_at, completed_at "
            "FROM repository_import_operations WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Repository import operation row is missing")
        print(json.dumps({name: row[name] for name in (
            "status", "created_at", "started_at", "completed_at"
        )}, sort_keys=True))
    finally:
        snapshot.close()
finally:
    snapshot_path.unlink(missing_ok=True)
"""
ARCHIVER_TOKEN = "s2b-realdata-archiver-token"
HISTORY_READER_TOKEN = "s2b-realdata-history-reader-token"
PSEUDO_GID_MIN = 4_000_000_000
EXPECTED_PSEUDO_TOTALS = {
    "rd-t1-a-v1": 4,
    "rd-t1-a-v2": 4,
    "rd-t2-b-v1": 3_056,
    "rd-t2-b-v2": 2_674,
    "rd-t3-c-v1": 9_858,
    "rd-t3-c-v2": 9_858,
    "rd-t4-d-v1": 12_676,
    "rd-t4-d-v2": 12_688,
}
EXPECTED_PAIRINGS = {
    "rd-t1-a": ("rd-t1-a-v1", "rd-t1-a-v2"),
    "rd-t2-b": ("rd-t2-b-v1", "rd-t2-b-v2"),
    "rd-t3-c": ("rd-t3-c-v1", "rd-t3-c-v2"),
    "rd-t4-d": ("rd-t4-d-v1", "rd-t4-d-v2"),
}
S2B_DATASET_BASELINE = {
    "rd-t1-a-v1": {
        "preview_changed": 124,
        "preview_table_count": 124,
        "catalog_table_count": 124,
        "catalog_row_count_total": 3_729,
    },
    "rd-t1-a-v2": {
        "preview_changed": 4,
        "preview_table_count": 124,
        "catalog_table_count": 124,
        "catalog_row_count_total": 3_727,
    },
    "rd-t2-b-v1": {
        "preview_changed": 208,
        "preview_table_count": 208,
        "catalog_table_count": 208,
        "catalog_row_count_total": 73_648,
    },
    "rd-t2-b-v2": {
        "preview_changed": 57,
        "preview_table_count": 219,
        "catalog_table_count": 208,
        "catalog_row_count_total": 68_864,
    },
    "rd-t3-c-v1": {
        "preview_changed": 191,
        "preview_table_count": 191,
        "catalog_table_count": 191,
        "catalog_row_count_total": 122_251,
    },
    "rd-t3-c-v2": {
        "preview_changed": 54,
        "preview_table_count": 192,
        "catalog_table_count": 192,
        "catalog_row_count_total": 122_257,
    },
    "rd-t4-d-v1": {
        "preview_changed": 311,
        "preview_table_count": 311,
        "catalog_table_count": 311,
        "catalog_row_count_total": 246_359,
    },
    "rd-t4-d-v2": {
        "preview_changed": 26,
        "preview_table_count": 311,
        "catalog_table_count": 311,
        "catalog_row_count_total": 246_439,
    },
}
S2B_HISTORY_RECORD_COUNTS = {"t1": 12, "t2": 11_511, "t3": 744, "t4": 168}
TERMINAL_OPERATION_STATES = {"SUCCEEDED", "FAILED", "CANCELLED"}
INITIAL_OPERATION_TIMEOUT_SECONDS = 3_600
MINIMUM_OPERATION_TIMEOUT_SECONDS = 300

# Operation budgets are calibrated from timestamped runs at the same tier.
# Until that exact tier/step has completed once, use the DC30 one-hour ceiling.
MEASURED_OPERATION_WALL_SECONDS: dict[str, float] = {
    "t1:v1-preview": 52.974,
    "t1:v1-submit": 41.628,
    "t1:repeat-v1-preview": 63.081,
    "t1:v2-preview": 77.094,
    "t1:v2-submit": 41.548,
    "t1:history": 62.969,
    "t2:v1-preview": 722.371,
    "t2:v1-submit": 237.182,
    "t2:repeat-v1-preview": 603.787,
    "t2:v2-preview": 688.200,
    "t2:v2-submit": 237.113,
    "t2:history": 492.678,
    "t3:v1-preview": 1242.901,
    "t3:v1-submit": 482.609,
    "t3:repeat-v1-preview": 1365.530,
    "t3:v2-preview": 1528.324,
    "t3:v2-submit": 495.901,
    "t3:history": 962.548,
    "t4:v1-preview": 2577.296,
    "t4:v1-submit": 809.218,
    "t4:repeat-v1-preview": 2254.054,
    "t4:v2-preview": 2259.980,
    "t4:v2-submit": 810.961,
    "t4:history": 1364.042,
}
OPERATION_TIERS = ("t1", "t2", "t3", "t4")

JOURNEY_STEP_IDS = (
    "v1-workspace",
    "v1-upload",
    "v1-preview",
    "v1-submit",
    "v1-repository-read",
    "v1-approve",
    "v1-archive",
    "repeat-v1-workspace",
    "repeat-v1-upload",
    "repeat-v1-preview",
    "repeat-v1-submit",
    "v2-workspace",
    "v2-upload",
    "v2-preview",
    "v2-submit",
    "v2-repository-read",
    "v2-approve",
    "history",
    "cross-source-workspace",
    "cross-source-upload",
    "cross-source-preview",
    "cross-source-submit",
    "cross-source-approve",
    "cross-source-archive",
    "cross-replacement-workspace",
    "cross-replacement-upload",
    "cross-replacement-preview",
    "cross-replacement-submit",
    "cross-replacement-approve",
    "cross-replacement-archive",
)


class JourneyFailure(RuntimeError):
    """A bounded failure without response bodies that could contain row data."""


class WorkerStalledFailure(JourneyFailure):
    """A worker heartbeat stopped while its operation remained nonterminal."""

    def __init__(
        self,
        *,
        stage: str,
        operation_id: str,
        diagnostics: Path | None,
        diagnostic_error: str | None = None,
    ) -> None:
        super().__init__(f"{stage} worker_stalled")
        self.reason = "worker_stalled"
        self.stage = stage
        self.operation_id = operation_id
        self.diagnostics = diagnostics
        self.diagnostic_error = diagnostic_error


@dataclass(frozen=True, slots=True)
class WorkerHeartbeatStall:
    operation_id: str
    step_id: str | None
    last_heartbeat_monotonic: float
    stalled_seconds: float


class WorkerHeartbeatTracker:
    """Track the worker's published heartbeat events for active operations."""

    _TERMINAL_OPERATION_STATUSES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED"})

    _HEARTBEAT_RE = re.compile(
        r"operation_worker_event code=heartbeat_succeeded "
        r"operation_id=(?P<operation_id>\S+) step_id=(?P<step_id>\S+)"
    )

    def __init__(
        self,
        *,
        stall_threshold_seconds: int = 120,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if type(stall_threshold_seconds) is not int or stall_threshold_seconds < 1:
            raise ValueError("worker stall threshold must be a positive integer")
        self.stall_threshold_seconds = stall_threshold_seconds
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._last_heartbeat: dict[str, tuple[float, str]] = {}
        self._running_since: dict[str, float] = {}

    def observe_log_line(self, line: str, *, observed_at: float | None = None) -> bool:
        match = self._HEARTBEAT_RE.search(line)
        if match is None:
            return False
        now = self._monotonic() if observed_at is None else observed_at
        with self._lock:
            self._last_heartbeat[match.group("operation_id")] = (
                now,
                match.group("step_id"),
            )
        return True

    def check_running_operation(
        self,
        operation_id: str,
        status: object,
        *,
        now: float | None = None,
    ) -> WorkerHeartbeatStall | None:
        current_time = self._monotonic() if now is None else now
        with self._lock:
            running_since = self._running_since.get(operation_id)
            if status == "RUNNING":
                running_since = self._running_since.setdefault(operation_id, current_time)
            elif status in self._TERMINAL_OPERATION_STATUSES:
                self._running_since.pop(operation_id, None)
                self._last_heartbeat.pop(operation_id, None)
                return None
            elif running_since is None:
                return None
            last_heartbeat = self._last_heartbeat.get(operation_id)
            last_seen, step_id = (
                last_heartbeat
                if last_heartbeat is not None
                else (running_since if running_since is not None else current_time, None)
            )
        stalled_seconds = current_time - last_seen
        if stalled_seconds < self.stall_threshold_seconds:
            return None
        return WorkerHeartbeatStall(
            operation_id=operation_id,
            step_id=step_id,
            last_heartbeat_monotonic=last_seen,
            stalled_seconds=stalled_seconds,
        )


def _worker_stall_threshold_seconds() -> int:
    raw = os.environ.get("GATEWAY_REAL_DUMP_WORKER_STALL_SECONDS", "120")
    try:
        threshold = int(raw)
    except ValueError as exc:
        raise JourneyFailure("worker stall threshold must be a positive integer") from exc
    if threshold < 1:
        raise JourneyFailure("worker stall threshold must be a positive integer")
    return threshold


def _worker_stall_diagnostic_root() -> Path:
    configured_directory = os.environ.get("GATEWAY_REAL_DUMP_LOG_DIR")
    if configured_directory:
        configured_path = Path(configured_directory)
        if not configured_path.is_absolute():
            raise JourneyFailure("worker stall diagnostics must use an absolute log directory")
        configured = configured_path.resolve()
        if configured.is_relative_to(_repo_root().resolve()):
            raise JourneyFailure("worker stall diagnostics must be outside the worktree")
        parent = configured.parent
    else:
        parent = Path(tempfile.gettempdir()).resolve()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = parent / f"s4-stall-{timestamp}"
    path.mkdir(parents=True, mode=0o700)
    path.chmod(0o700)
    return path


def _capture_worker_thread_state(env: dict[str, str], root: Path) -> list[str]:
    result = run_compose(env, "ps", "-q", "worker", timeout=30.0)
    if result.returncode != 0:
        raise JourneyFailure("could not resolve worker container for stall diagnostics")
    container_ids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not container_ids:
        raise JourneyFailure("worker container is unavailable for stall diagnostics")
    top = subprocess.run(
        ["docker", "top", container_ids[0], "-eo", "pid"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    if top.returncode != 0:
        (root / "worker-processes.txt").write_text(
            f"docker top exit={top.returncode}\n{top.stdout}\n{top.stderr}",
            encoding="utf-8",
        )
        raise JourneyFailure("could not list worker host PIDs for stall diagnostics")
    host_pids = [
        line.strip()
        for line in top.stdout.splitlines()
        if line.strip().isdigit()
    ]
    (root / "worker-processes.txt").write_text(
        "\n".join(host_pids) + "\n",
        encoding="utf-8",
    )
    for pid in host_pids:
        task_root = Path("/proc") / pid / "task"
        process_root = root / f"worker-pid-{pid}"
        process_root.mkdir(mode=0o700)
        try:
            task_ids = sorted(path.name for path in task_root.iterdir())
        except OSError as exc:
            (process_root / "read-error.txt").write_text(
                f"task directory unavailable: {type(exc).__name__}\n",
                encoding="utf-8",
            )
            continue
        for task_id in task_ids:
            thread_root = process_root / f"thread-{task_id}"
            thread_root.mkdir(mode=0o700)
            for filename in ("comm", "wchan", "stack", "status"):
                source = task_root / task_id / filename
                try:
                    content = source.read_text(encoding="utf-8", errors="replace")
                except OSError as exc:
                    content = f"unavailable: {type(exc).__name__}\n"
                (thread_root / f"{filename}.txt").write_text(content, encoding="utf-8")
    return host_pids


def _capture_worker_python_stacks(host_pids: Sequence[str], root: Path) -> None:
    py_spy = shutil.which("py-spy")
    if py_spy is None:
        (root / "py-spy-unavailable.txt").write_text(
            "py-spy is not installed on the CT host\n",
            encoding="utf-8",
        )
        return
    for pid in host_pids:
        try:
            result = subprocess.run(
                [py_spy, "dump", "--native", "--pid", pid],
                check=False,
                capture_output=True,
                text=True,
                timeout=30.0,
            )
            content = (
                f"exit={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        except Exception as exc:
            content = f"py-spy failed: {type(exc).__name__}\n"
        (root / f"py-spy-pid-{pid}.txt").write_text(content, encoding="utf-8")


def _capture_container_inspections(env: dict[str, str], root: Path) -> None:
    for service in ("backend", "worker", "repository-service"):
        try:
            result = run_compose(env, "ps", "-q", service, timeout=30.0)
            container_ids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            if result.returncode != 0 or not container_ids:
                (root / f"docker-inspect-{service}.txt").write_text(
                    f"container lookup exit={result.returncode}\n{result.stderr}",
                    encoding="utf-8",
                )
                continue
            inspected = subprocess.run(
                ["docker", "inspect", *container_ids],
                check=False,
                capture_output=True,
                text=True,
                timeout=30.0,
            )
            (root / f"docker-inspect-{service}.json").write_text(
                inspected.stdout or inspected.stderr,
                encoding="utf-8",
            )
        except Exception as exc:
            (root / f"docker-inspect-{service}.txt").write_text(
                f"docker inspect failed: {type(exc).__name__}\n",
                encoding="utf-8",
            )


def _capture_submit_attempt_control_rows(
    env: dict[str, str],
    operation_id: str,
    root: Path,
    *,
    summary_out: dict[str, Any] | None = None,
) -> str:
    # The live DB is opened read-only and copied before querying. Only the
    # operation, submit attempt, step and lease fields needed by the S5 probe
    # and stall diagnosis are emitted.
    snapshot_script = """
import json, os, sqlite3, sys, tempfile
from pathlib import Path

database_path = Path(sys.argv[1])
operation_id = sys.argv[2]
source = sqlite3.connect(database_path.resolve().as_uri() + "?mode=ro", uri=True)
fd, snapshot_name = tempfile.mkstemp(prefix="gdds-s5-submit-control-")
os.close(fd)
try:
    snapshot = sqlite3.connect(snapshot_name)
    source.backup(snapshot)
    operation_row = snapshot.execute(
        "SELECT operation_id, status, created_at_us, updated_at_us, completed_at_us, business_refs "
        "FROM operation_records WHERE operation_id = ?",
        (operation_id,),
    ).fetchone()
    submit_attempt = None
    if operation_row is not None:
        business_refs = json.loads(bytes(operation_row[5]))
        if not isinstance(business_refs, list):
            raise ValueError("operation business_refs is not a list")
        submit_attempt_ids = [
            reference.get("value")
            for reference in business_refs
            if isinstance(reference, dict) and reference.get("kind") == "submit_attempt"
        ]
        if len(submit_attempt_ids) != 1 or not isinstance(submit_attempt_ids[0], str):
            raise ValueError("operation must reference exactly one submit_attempt")
        attempt_row = snapshot.execute(
            "SELECT submit_attempt_id, operation_id, repository_operation_id "
            "FROM submit_attempt_records WHERE submit_attempt_id = ?",
            (submit_attempt_ids[0],),
        ).fetchone()
        if attempt_row is not None and attempt_row[1] != operation_id:
            raise ValueError("submit_attempt belongs to a different operation")
        submit_attempt = None if attempt_row is None else {
            "submit_attempt_id": attempt_row[0],
            "repository_operation_id": attempt_row[2],
        }
    step_rows = snapshot.execute(
        "SELECT step_id, step_name, status, attempt_count, worker_id, "
        "lease_expires_at_us, created_at_us, updated_at_us, started_at_us, completed_at_us "
        "FROM step_records WHERE operation_id = ? ORDER BY step_name",
        (operation_id,),
    ).fetchall()
    steps = [
        {
            "step_id": row[0], "step_name": row[1], "status": row[2],
            "attempt_count": row[3], "owner": row[4],
            "lease_expires_at_us": row[5], "created_at_us": row[6],
            "updated_at_us": row[7], "started_at_us": row[8],
            "completed_at_us": row[9],
        }
        for row in step_rows
    ]
    operation = None if operation_row is None else {
        "operation_id": operation_row[0], "status": operation_row[1],
        "created_at_us": operation_row[2], "updated_at_us": operation_row[3],
        "completed_at_us": operation_row[4],
    }
    leases = [
        {
            "step_id": step["step_id"], "owner": step["owner"],
            "attempt_count": step["attempt_count"],
            "lease_expires_at_us": step["lease_expires_at_us"],
            "updated_at_us": step["updated_at_us"],
        }
        for step in steps if step["lease_expires_at_us"] is not None
    ]
    print(json.dumps({
        "operation": operation,
        "submit_attempt": submit_attempt,
        "steps": steps,
        "leases": leases,
    }, sort_keys=True))
    snapshot.close()
finally:
    source.close()
    Path(snapshot_name).unlink(missing_ok=True)
"""
    result = run_compose(
        env,
        "exec",
        "-T",
        "backend",
        "python",
        "-c",
        snapshot_script,
        "/var/lib/gateway/control/control.sqlite3",
        operation_id,
        timeout=60.0,
    )
    if result.returncode != 0:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root.chmod(0o700)
        error_path = root / "control-db-selected-rows-error.txt"
        error_path.write_text(
            f"snapshot/query exit={result.returncode}\n{result.stderr}",
            encoding="utf-8",
        )
        error_path.chmod(0o600)
        raise JourneyFailure("Submit attempt control DB query failed")
    try:
        summary = json.loads(result.stdout)
    except json.JSONDecodeError:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root.chmod(0o700)
        error_path = root / "control-db-selected-rows-error.txt"
        error_path.write_text(
            "snapshot/query returned invalid JSON\n",
            encoding="utf-8",
        )
        error_path.chmod(0o600)
        raise JourneyFailure("Submit attempt control DB query returned invalid JSON") from None
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    selected_rows_path = root / "control-db-selected-rows.json"
    selected_rows_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    selected_rows_path.chmod(0o600)
    if summary_out is not None:
        summary_out.update(summary)
    submit_attempt = summary.get("submit_attempt")
    repository_operation_id = (
        submit_attempt.get("repository_operation_id")
        if isinstance(submit_attempt, dict)
        else None
    )
    if not isinstance(repository_operation_id, str) or not repository_operation_id:
        raise JourneyFailure("Submit Repository operation id is missing from its attempt record")
    return repository_operation_id


def _capture_repository_import_status(
    *,
    repository_url: str,
    repository_id: str,
    operation_id: str,
    root: Path,
) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                f"{repository_url}/v1/repositories/{repository_id}/operations/{operation_id}",
                headers=compose_auth_headers(token=BEARER_TOKEN),
            )
    except httpx.HTTPError as exc:
        raise JourneyFailure("Repository public operation status request failed") from exc
    if response.status_code != 200:
        raise JourneyFailure(
            f"Repository public operation status returned HTTP {response.status_code}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise JourneyFailure("Repository public operation status response is invalid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("operation"), dict):
        raise JourneyFailure("Repository public operation response has an invalid shape")
    operation = payload["operation"]
    public_operation_id = operation.get("operation_id")
    status = operation.get("status")
    if public_operation_id != operation_id or not isinstance(status, str):
        raise JourneyFailure("Repository public operation identity or status is invalid")
    summary: dict[str, Any] = {
        "operation_id": operation_id,
        "http_status": response.status_code,
        "status": status,
    }
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    status_path = root / "repository-operation-public-status.json"
    status_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    status_path.chmod(0o600)
    return summary


def _read_repository_import_control_row(
    *,
    env: dict[str, str],
    operation_id: str,
    root: Path,
) -> dict[str, Any]:
    result = run_compose(
        env,
        "exec",
        "-T",
        "repository-service",
        "python",
        "-c",
        REPOSITORY_IMPORT_CONTROL_ROW_SCRIPT,
        REPOSITORY_SERVICE_CONTROL_DB_PATH,
        operation_id,
        timeout=60.0,
    )
    if result.returncode != 0:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root.chmod(0o700)
        error_path = root / "repository-import-control-row-error.txt"
        error_path.write_text(
            f"Repository control DB snapshot/query exit={result.returncode}\n",
            encoding="utf-8",
        )
        error_path.chmod(0o600)
        raise JourneyFailure("Repository import control DB query failed")
    try:
        row = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise JourneyFailure("Repository import control DB query returned invalid JSON") from exc
    required_fields = {
        "status",
        "created_at",
        "started_at",
        "completed_at",
    }
    if not isinstance(row, dict) or set(row) != required_fields:
        raise JourneyFailure("Repository import control DB row has an invalid shape")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    status_path = root / "repository-import-control-row.json"
    status_path.write_text(json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    status_path.chmod(0o600)
    return row


def _repository_import_timings(row: Mapping[str, Any]) -> tuple[float, float]:
    timestamps: dict[str, datetime] = {}
    for name in ("created_at", "started_at", "completed_at"):
        value = row.get(name)
        if type(value) is not str:
            raise JourneyFailure(f"Repository import {name} timestamp is missing")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise JourneyFailure(f"Repository import {name} timestamp is invalid") from exc
        if parsed.utcoffset() is None:
            raise JourneyFailure(f"Repository import {name} timestamp has no timezone")
        timestamps[name] = parsed
    elapsed = (timestamps["completed_at"] - timestamps["started_at"]).total_seconds()
    queued = (timestamps["started_at"] - timestamps["created_at"]).total_seconds()
    if elapsed < 0 or queued < 0:
        raise JourneyFailure("Repository import timestamps are not chronological")
    return round(elapsed, 3), round(queued, 3)


def _capture_submit_reconciliation_facts(
    *,
    env: dict[str, str],
    repository_url: str,
    repository_id: str,
    operation_id: str,
    root: Path,
    enforce_three_session_limit: bool,
) -> dict[str, Any]:
    control_summary: dict[str, Any] = {}
    repository_operation_id = _capture_submit_attempt_control_rows(
        env,
        operation_id,
        root,
        summary_out=control_summary,
    )
    operation = control_summary.get("operation")
    steps = control_summary.get("steps")
    if not isinstance(operation, Mapping) or not isinstance(steps, list):
        raise JourneyFailure("Submit reconciliation facts are missing from the control DB")
    reconciliation_step = next(
        (
            step
            for step in steps
            if isinstance(step, Mapping)
            and step.get("step_name") in {"await_import_result", "AwaitImportResult"}
        ),
        None,
    )
    if not isinstance(reconciliation_step, Mapping):
        raise JourneyFailure("Submit await_import_result step is missing from the control DB")
    sessions_used = reconciliation_step.get("attempt_count")
    if type(sessions_used) is not int or sessions_used < 1:
        raise JourneyFailure("Submit reconciliation session count is invalid")
    public_status = _capture_repository_import_status(
        repository_url=repository_url,
        repository_id=repository_id,
        operation_id=repository_operation_id,
        root=root,
    )
    repository_row = _read_repository_import_control_row(
        env=env,
        operation_id=repository_operation_id,
        root=root,
    )
    if repository_row.get("status") != public_status.get("status"):
        raise JourneyFailure("Repository public and control DB operation statuses disagree")
    if public_status.get("status") != "SUCCEEDED":
        raise JourneyFailure("Submit Repository import did not have a successful status record")
    elapsed, queue_seconds = _repository_import_timings(repository_row)
    remaining = max(0, 3 - sessions_used)
    if enforce_three_session_limit and sessions_used >= 3:
        raise JourneyFailure("t4 Submit exhausted the three-session reconciliation limit")
    return {
        "operation_id": operation_id,
        "repository_operation_id": repository_operation_id,
        "await_import_result_attempt_count": sessions_used,
        "reconciliation_session_limit": 3,
        "remaining_sessions": remaining,
        "session_margin": remaining,
        "repository_import_elapsed_seconds": elapsed,
        "repository_import_queue_seconds": queue_seconds,
        "repository_import_status": public_status.get("status"),
    }


def _capture_worker_stall_diagnostics(
    *,
    env: dict[str, str],
    repository_id: str,
    repository_url: str,
    operation_id: str,
    stage: str,
    stall: WorkerHeartbeatStall,
) -> Path:
    root = _worker_stall_diagnostic_root()
    previous_umask = os.umask(0o077)
    errors: list[str] = []
    try:
        (root / "stall.json").write_text(
            json.dumps(
                {
                    "failure_reason": "worker_stalled",
                    "stage": stage,
                    "operation_id": operation_id,
                    "step_id": stall.step_id,
                    "stall_threshold_seconds": _worker_stall_threshold_seconds(),
                    "observed_stalled_seconds": round(stall.stalled_seconds, 3),
                    "captured_at_utc": _utc_timestamp(),
                    "repository_id": repository_id,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        host_pids: list[str] = []
        try:
            host_pids = _capture_worker_thread_state(env, root)
        except Exception as exc:
            errors.append(f"worker thread state: {type(exc).__name__}")
        try:
            _capture_worker_python_stacks(host_pids, root)
        except Exception as exc:
            errors.append(f"worker Python stacks: {type(exc).__name__}")
        try:
            _capture_container_inspections(env, root)
        except Exception as exc:
            errors.append(f"container inspect: {type(exc).__name__}")

        try:
            repository_operation_id = _capture_submit_attempt_control_rows(env, operation_id, root)
        except Exception as exc:
            errors.append(f"control DB snapshot: {type(exc).__name__}")
        else:
            try:
                _capture_repository_import_status(
                    repository_url=repository_url,
                    repository_id=repository_id,
                    operation_id=repository_operation_id,
                    root=root,
                )
            except Exception as exc:
                errors.append(f"Repository import status: {type(exc).__name__}")

        try:
            logs = run_compose(env, "logs", "--no-color", "--timestamps", timeout=180.0)
            (root / "all-container-logs.txt").write_text(
                f"compose_logs_exit_code={logs.returncode}\n"
                f"stdout:\n{logs.stdout}\nstderr:\n{logs.stderr}",
                encoding="utf-8",
            )
        except Exception as exc:
            errors.append(f"all container logs: {type(exc).__name__}")
        if errors:
            (root / "diagnostic-errors.txt").write_text("\n".join(errors) + "\n", encoding="utf-8")
    finally:
        os.umask(previous_umask)
    return root


class WorkerHeartbeatMonitor:
    """Read worker heartbeat events and capture diagnostics before a stalled stack is torn down."""

    def __init__(
        self,
        *,
        env: dict[str, str],
        repository_id: str,
        repository_url: str,
        tracker: WorkerHeartbeatTracker | None = None,
        diagnostic_capture: Callable[..., Path] = _capture_worker_stall_diagnostics,
        popen: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
    ) -> None:
        self.env = env
        self.repository_id = repository_id
        self.repository_url = repository_url
        self.tracker = tracker or WorkerHeartbeatTracker(
            stall_threshold_seconds=_worker_stall_threshold_seconds()
        )
        self._diagnostic_capture = diagnostic_capture
        self._popen = popen
        self._process: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None

    def __enter__(self) -> WorkerHeartbeatMonitor:
        command = [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_FILE),
            "logs",
            "--follow",
            "--no-color",
            "--timestamps",
            "worker",
        ]
        try:
            self._process = self._popen(
                command,
                cwd=DEPLOY_ROOT,
                env=self.env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise JourneyFailure("could not start worker heartbeat log stream") from exc
        self._reader_thread = threading.Thread(
            target=self._read_heartbeat_log,
            name="real-dump-worker-heartbeat-log",
            daemon=True,
        )
        self._reader_thread.start()
        _emit_progress(
            "real-data journey",
            "worker_heartbeat_monitor_started",
            stall_threshold_seconds=self.tracker.stall_threshold_seconds,
            heartbeat_source="worker operation_worker_event code=heartbeat_succeeded logs",
        )
        return self

    def _read_heartbeat_log(self) -> None:
        if self._process is None or self._process.stdout is None:
            return
        for line in self._process.stdout:
            self.tracker.observe_log_line(line)

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5.0)
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=5.0)
        if process is not None and process.stdout is not None:
            process.stdout.close()

    def check_operation(self, operation_id: str, status: object, *, stage: str) -> None:
        if self._process is not None and self._process.poll() is not None:
            raise JourneyFailure("worker heartbeat log stream exited while an operation was active")
        stall = self.tracker.check_running_operation(operation_id, status)
        if stall is None:
            return
        diagnostics: Path | None = None
        diagnostic_error: str | None = None
        try:
            diagnostics = self._diagnostic_capture(
                env=self.env,
                repository_id=self.repository_id,
                repository_url=self.repository_url,
                operation_id=operation_id,
                stage=stage,
                stall=stall,
            )
        except Exception as exc:
            diagnostic_error = type(exc).__name__
        _emit_progress(
            stage,
            "worker_stalled",
            failure_reason="worker_stalled",
            operation_id=operation_id,
            step_id=stall.step_id,
            stalled_seconds=round(stall.stalled_seconds, 3),
            diagnostics=str(diagnostics) if diagnostics is not None else None,
            diagnostic_error=diagnostic_error,
        )
        raise WorkerStalledFailure(
            stage=stage,
            operation_id=operation_id,
            diagnostics=diagnostics,
            diagnostic_error=diagnostic_error,
        )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _real_dump_root() -> Path:
    raw = os.environ.get("GATEWAY_REAL_DUMP_ROOT", "").strip()
    if not raw:
        raise JourneyFailure("GATEWAY_REAL_DUMP_ROOT is required")
    root = Path(raw).resolve()
    if not root.is_dir():
        raise JourneyFailure("GATEWAY_REAL_DUMP_ROOT is not a directory")
    return root


def _read_metadata(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    try:
        datasets_document = json.loads((root / "datasets.json").read_text(encoding="utf-8"))
        census_document = json.loads(
            (_repo_root() / "docs/backend-vnext/refactoring/formal/plans/p5-arch-closure-s1-census.json")
            .read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise JourneyFailure("real dump metadata could not be read") from exc
    datasets = {
        str(item["dataset_id"]): cast(dict[str, Any], item)
        for item in datasets_document.get("datasets", [])
        if isinstance(item, dict) and type(item.get("dataset_id")) is str
    }
    census = {
        str(item["dataset_id"]): cast(dict[str, Any], item)
        for item in census_document.get("datasets", [])
        if isinstance(item, dict) and type(item.get("dataset_id")) is str
    }
    if set(datasets) != set(EXPECTED_PSEUDO_TOTALS) or set(census) != set(datasets):
        raise JourneyFailure("dataset census does not contain the eight expected datasets")
    for tier_id, (v1_id, v2_id) in EXPECTED_PAIRINGS.items():
        del tier_id
        if datasets[v1_id].get("pair_of") is not None:
            raise JourneyFailure("v1 dataset unexpectedly declares a pair")
        if datasets[v2_id].get("pair_of") != v1_id:
            raise JourneyFailure("dataset pairing differs from the accepted same-tier pairing")
    return datasets, census


def _dataset_package(root: Path, dataset: Mapping[str, Any]) -> tuple[bytes, dict[str, Any]]:
    dataset_id = str(dataset["dataset_id"])
    files = dataset.get("files")
    if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], dict):
        raise JourneyFailure(f"{dataset_id}: package manifest shape is invalid")
    file_info = cast(dict[str, Any], files[0])
    if Path(str(file_info["path"])).name != "package.tar.gz":
        raise JourneyFailure(f"{dataset_id}: dataset manifest package filename is unexpected")
    package_path = root / "packages" / f"{dataset_id}.tar.gz"
    payload = package_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if len(payload) != int(file_info["bytes"]) or digest != file_info["sha256"]:
        raise JourneyFailure(f"{dataset_id}: package size or SHA-256 differs from datasets.json")
    if dataset.get("has_logics_xml") is not True:
        raise JourneyFailure(f"{dataset_id}: logics.xml is required by DC22")
    return payload, file_info


def _ordered_tables(census: Mapping[str, Any]) -> dict[str, int]:
    projection = census.get("ordered_projection")
    if not isinstance(projection, dict) or projection.get("status") != "COMPLETE":
        raise JourneyFailure("ordered census must be COMPLETE before the journey")
    raw_tables = projection.get("tables")
    if not isinstance(raw_tables, dict):
        raise JourneyFailure("ordered census table map is invalid")
    result: dict[str, int] = {}
    for table_name, raw in raw_tables.items():
        if not isinstance(raw, dict) or raw.get("status") != "COMPLETE":
            raise JourneyFailure("ordered census contains a non-COMPLETE table")
        result[str(table_name)] = int(raw["pseudo_gid_count"])
    if sum(result.values()) != int(projection["pseudo_rows_total"]):
        raise JourneyFailure("ordered census pseudo count does not reconcile")
    return result


def _ordered_table_row_counts(census: Mapping[str, Any]) -> dict[str, int]:
    projection = census.get("ordered_projection")
    if not isinstance(projection, dict) or projection.get("status") != "COMPLETE":
        raise JourneyFailure("ordered census must be COMPLETE before the journey")
    raw_tables = projection.get("tables")
    if not isinstance(raw_tables, dict):
        raise JourneyFailure("ordered census has no table counts")
    result: dict[str, int] = {}
    for table_name, raw in raw_tables.items():
        if type(table_name) is not str or not isinstance(raw, dict) or raw.get("status") != "COMPLETE":
            raise JourneyFailure("ordered census contains a non-COMPLETE table")
        row_count = raw.get("row_count")
        if type(row_count) is not int or row_count < 0:
            raise JourneyFailure("ordered census has an invalid table row count")
        result[table_name] = row_count
    return result


def _write_compose_secrets(root: Path) -> dict[str, str]:
    root.mkdir(parents=True, exist_ok=True)
    bearer = root / "repository-bearer-token"
    bearer.write_text(f"{BEARER_TOKEN}\n", encoding="utf-8")
    session_file = root / "session.json"
    session_file.write_text(
        json.dumps(
            {
                "sessions": [
                    {
                        "token": SESSION_TOKEN,
                        "actor_id": "s2b-realdata-submitter",
                        "gateway_device_external_key": DEVICE_KEY,
                        "business_project_id": PROJECT_ID,
                        "permissions": [
                            "workspace_read",
                            "upload_submit_workspace",
                            "preview_workspace",
                            "review_submission",
                        ],
                    },
                    {
                        "token": ARCHIVER_TOKEN,
                        "actor_id": "s2b-realdata-archiver",
                        "gateway_device_external_key": DEVICE_KEY,
                        "business_project_id": PROJECT_ID,
                        "permissions": [
                            "workspace_read",
                            "review_submission",
                            "archive_submission",
                        ],
                    },
                    {
                        "token": HISTORY_READER_TOKEN,
                        "actor_id": "s2b-realdata-history-reader",
                        "gateway_device_external_key": DEVICE_KEY,
                        "business_project_id": PROJECT_ID,
                        "permissions": ["workspace_read", "read_project_history"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    internal_bearer = root / "internal-bearer-token"
    internal_bearer.write_text("s2b-realdata-internal-bearer\n", encoding="utf-8")
    mapping = root / "provisioned-mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "gateway_device_external_key": DEVICE_KEY,
                        "business_project_id": PROJECT_ID,
                        "repository_id": "pending-repository-seed",
                        "business_baseline_node_id": BASELINE_NODE_ID,
                        "business_baseline_commit_id": "pending-commit-seed",
                        "baseline_head_version": 0,
                        "enabled": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return {
        "GATEWAY_P2R2_BEARER_TOKEN_FILE": str(bearer),
        "GATEWAY_BACKEND_SESSION_FILE": str(session_file),
        "GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE": str(mapping),
        "GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE": str(internal_bearer),
        "GATEWAY_REPOSITORY_SERVICE_BEARER_TOKEN_FILE": str(bearer),
    }


def _compose_environment(
    secret_root: Path,
    project_name: str,
    *,
    write_secrets: bool = True,
) -> dict[str, str]:
    environment = os.environ.copy()
    if write_secrets:
        environment.update(_write_compose_secrets(secret_root))
    else:
        environment.update(
            {
                "GATEWAY_P2R2_BEARER_TOKEN_FILE": str(secret_root / "repository-bearer-token"),
                "GATEWAY_BACKEND_SESSION_FILE": str(secret_root / "session.json"),
                "GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE": str(secret_root / "provisioned-mapping.json"),
                "GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE": str(secret_root / "internal-bearer-token"),
                "GATEWAY_REPOSITORY_SERVICE_BEARER_TOKEN_FILE": str(secret_root / "repository-bearer-token"),
            }
        )
    environment.update(
        {
            "COMPOSE_PROJECT_NAME": project_name,
            "GATEWAY_COMPOSE_GATE_PREBUILT": "1",
        }
    )
    return environment


def _require(response: httpx.Response, expected: int, label: str) -> dict[str, Any]:
    if response.status_code != expected:
        try:
            body = response.json()
        except ValueError:
            body = {}
        error = body.get("code") if isinstance(body, dict) else None
        suffix = f" code={error}" if type(error) is str else ""
        raise JourneyFailure(f"{label}: HTTP {response.status_code}, expected {expected}{suffix}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise JourneyFailure(f"{label}: response was not JSON") from exc
    if not isinstance(payload, dict):
        raise JourneyFailure(f"{label}: response was not an object")
    return cast(dict[str, Any], payload)


def _require_one_of(
    response: httpx.Response,
    expected: set[int],
    label: str,
) -> dict[str, Any]:
    if response.status_code not in expected:
        _require(response, min(expected), label)
    return _require(response, response.status_code, label)


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _emit_progress(stage: str, event: str, **details: Any) -> None:
    print(
        json.dumps(
            {"event": event, "stage": stage, "timestamp_utc": _utc_timestamp(), **details},
            sort_keys=True,
        ),
        flush=True,
    )


def _parse_cpu_stat(payload: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in payload.splitlines():
        parts = line.split()
        if len(parts) != 2 or not re.fullmatch(r"[a-z][a-z0-9_.]*", parts[0]):
            raise JourneyFailure("container cpu.stat has an invalid row")
        try:
            value = int(parts[1])
        except ValueError as exc:
            raise JourneyFailure("container cpu.stat has a non-integer value") from exc
        if value < 0 or parts[0] in values:
            raise JourneyFailure("container cpu.stat contains an invalid counter")
        values[parts[0]] = value
    if "usage_usec" not in values:
        raise JourneyFailure("container cpu.stat has no usage_usec counter")
    return values


def _container_cpu_stats(env: Mapping[str, str]) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    for service in ("backend", "worker", "repository-service"):
        listed = run_compose(dict(env), "ps", "-q", service)
        container_ids = listed.stdout.strip().splitlines()
        if listed.returncode != 0 or len(container_ids) != 1:
            raise JourneyFailure(f"could not resolve the {service} container for cpu.stat")
        inspected = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Pid}}", container_ids[0]],
            check=False,
            capture_output=True,
            text=True,
            timeout=30.0,
        )
        if inspected.returncode != 0:
            raise JourneyFailure(f"could not inspect the {service} container for cpu.stat")
        pid = inspected.stdout.strip()
        if not pid.isdigit() or pid == "0":
            raise JourneyFailure(f"the {service} container has no running host pid")
        try:
            cgroup_lines = (Path("/proc") / pid / "cgroup").read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise JourneyFailure(f"could not read the {service} host cgroup") from exc
        unified_path = next(
            (line.partition("::")[2] for line in cgroup_lines if line.startswith("0::")),
            None,
        )
        if not unified_path:
            raise JourneyFailure(f"the {service} container is not in a unified cgroup")
        cgroup_root = Path("/sys/fs/cgroup").resolve()
        cpu_stat_path = (cgroup_root / unified_path.lstrip("/") / "cpu.stat").resolve()
        if not cpu_stat_path.is_relative_to(cgroup_root):
            raise JourneyFailure(f"the {service} cgroup path escaped the host cgroup root")
        try:
            stats[service] = _parse_cpu_stat(cpu_stat_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise JourneyFailure(f"could not read the {service} host cpu.stat") from exc
    return stats


def _step_measurement(
    *,
    started_monotonic: float,
    started_utc: str,
    cpu_start: Mapping[str, Mapping[str, int]],
    cpu_end: Mapping[str, Mapping[str, int]],
) -> dict[str, Any]:
    cpu_seconds: dict[str, float | None] = {}
    cpu_delta_usec: dict[str, int | None] = {}
    cpu_stat_reset_services: list[str] = []
    for service in ("backend", "worker", "repository-service"):
        delta = int(cpu_end[service]["usage_usec"]) - int(cpu_start[service]["usage_usec"])
        if delta < 0:
            cpu_delta_usec[service] = None
            cpu_seconds[service] = None
            cpu_stat_reset_services.append(service)
            continue
        cpu_delta_usec[service] = delta
        cpu_seconds[service] = round(delta / 1_000_000, 3)
    return {
        "started_at_utc": started_utc,
        "ended_at_utc": _utc_timestamp(),
        "wall_seconds": round(time.monotonic() - started_monotonic, 3),
        "cpu_seconds": cpu_seconds,
        "cpu_delta_usec": cpu_delta_usec,
        "cpu_stat_reset_services": cpu_stat_reset_services,
        "cpu_stat_start": cpu_start,
        "cpu_stat_end": cpu_end,
    }


def _operation_timeout_seconds(tier: str, step_id: str) -> int:
    if tier not in OPERATION_TIERS:
        raise JourneyFailure("operation timeout profile has an unknown tier")
    measured_wall_seconds = MEASURED_OPERATION_WALL_SECONDS.get(f"{tier}:{step_id}")
    timeout = (
        INITIAL_OPERATION_TIMEOUT_SECONDS
        if measured_wall_seconds is None
        else max(
            MINIMUM_OPERATION_TIMEOUT_SECONDS,
            math.ceil(measured_wall_seconds * 5),
        )
    )
    if timeout < MINIMUM_OPERATION_TIMEOUT_SECONDS:
        raise JourneyFailure("operation timeout profile is below the five minute minimum")
    return timeout


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True))


class JourneyStepRunner:
    def __init__(
        self,
        *,
        tier: str,
        env: Mapping[str, str],
        state: dict[str, Any],
        from_step: str | None,
        state_path: Path | None,
    ) -> None:
        self.tier = tier
        self.env = env
        self.state = state
        self.state_path = state_path
        self.from_index = 0 if from_step is None else JOURNEY_STEP_IDS.index(from_step)
        self.metrics: list[dict[str, Any]] = []

    def run(self, step_id: str, action: Callable[[], Any]) -> Any:
        index = JOURNEY_STEP_IDS.index(step_id)
        stage = f"{self.tier} {step_id}"
        if index < self.from_index:
            if step_id not in self.state:
                raise JourneyFailure(f"debug state is missing the completed step {step_id}")
            _emit_progress(stage, "step_reused")
            return self.state[step_id]

        started_utc = _utc_timestamp()
        started_monotonic = time.monotonic()
        cpu_start = _container_cpu_stats(self.env)
        _emit_progress(stage, "step_started", cpu_stat=cpu_start)
        try:
            value = action()
            cpu_end = _container_cpu_stats(self.env)
            measurement = _step_measurement(
                started_monotonic=started_monotonic,
                started_utc=started_utc,
                cpu_start=cpu_start,
                cpu_end=cpu_end,
            )
        except BaseException:
            try:
                cpu_end = _container_cpu_stats(self.env)
                measurement = _step_measurement(
                    started_monotonic=started_monotonic,
                    started_utc=started_utc,
                    cpu_start=cpu_start,
                    cpu_end=cpu_end,
                )
            except Exception as metric_error:
                measurement = {
                    "started_at_utc": started_utc,
                    "ended_at_utc": _utc_timestamp(),
                    "wall_seconds": round(time.monotonic() - started_monotonic, 3),
                    "cpu_stat_error": type(metric_error).__name__,
                }
            self.metrics.append({"step_id": step_id, **measurement})
            _emit_progress(stage, "step_failed", metrics=measurement)
            raise

        stored_value = _json_copy(value)
        self.state[step_id] = stored_value
        if self.state_path is not None:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
            temporary_path.write_text(
                json.dumps(self.state, sort_keys=True),
                encoding="utf-8",
            )
            temporary_path.replace(self.state_path)
        self.metrics.append({"step_id": step_id, **measurement})
        _emit_progress(stage, "step_succeeded", metrics=measurement)
        return value


def _poll_operation(
    client: httpx.Client,
    operation_id: str,
    *,
    stage: str,
    timeout_seconds: int = INITIAL_OPERATION_TIMEOUT_SECONDS,
    deadline: float | None = None,
    heartbeat_monitor: WorkerHeartbeatMonitor | None = None,
    accepted_monotonic: float | None = None,
    visible_probe: Callable[[], bool] | None = None,
    timing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    operation_started = time.monotonic()
    _emit_progress(stage, "operation_started", timeout_seconds=timeout_seconds)
    operation_deadline = time.monotonic() + timeout_seconds if deadline is None else deadline
    retry_count = 0
    while time.monotonic() < operation_deadline:
        response = client.get(f"/v1/operations/{operation_id}")
        if response.status_code == 503:
            retry_count += 1
            remaining = operation_deadline - time.monotonic()
            if remaining <= 0:
                break
            delay = min(2.0, remaining)
            _emit_progress(
                stage,
                "operation_status_retry",
                status_code=503,
                retry_count=retry_count,
                retry_delay_seconds=round(delay, 3),
                timeout_seconds=timeout_seconds,
            )
            time.sleep(delay)
            continue
        payload = _require(response, 200, "operation status")
        status = payload.get("status")
        if heartbeat_monitor is not None:
            heartbeat_monitor.check_operation(operation_id, status, stage=stage)
        if status in TERMINAL_OPERATION_STATES:
            if status != "SUCCEEDED":
                diagnostic = payload.get("diagnostic")
                code = diagnostic.get("code") if isinstance(diagnostic, dict) else "unknown"
                raise JourneyFailure(f"{stage} operation ended {status}, diagnostic={code}")
            if timing is not None and accepted_monotonic is not None:
                terminal_seconds = time.monotonic() - accepted_monotonic
                timing["operation_terminal_seconds"] = round(terminal_seconds, 3)
                timing["user_visible_seconds"] = timing.get(
                    "user_visible_seconds",
                    round(terminal_seconds, 3),
                )
                timing.setdefault("visibility_observation", "operation_terminal_result")
            _emit_progress(
                stage,
                "operation_succeeded",
                operation_status=status,
                timeout_seconds=timeout_seconds,
                operation_wall_seconds=round(time.monotonic() - operation_started, 3),
            )
            return payload
        if (
            timing is not None
            and accepted_monotonic is not None
            and visible_probe is not None
            and "user_visible_seconds" not in timing
            and visible_probe()
        ):
            timing["user_visible_seconds"] = round(
                time.monotonic() - accepted_monotonic,
                3,
            )
            timing["visibility_observation"] = "first_successful_result_read_probe"
        time.sleep(2.0)
    raise JourneyFailure(f"{stage} operation did not reach a terminal state before timeout")


def _workspace(client: httpx.Client) -> dict[str, Any]:
    response = client.post(
        "/v1/workspaces",
        json={
            "gateway_device_external_key": DEVICE_KEY,
            "business_project_id": PROJECT_ID,
        },
    )
    if response.status_code not in {200, 201}:
        _require(response, 201, "workspace")
    return _require(response, response.status_code, "workspace")


def _upload_revision(
    client: httpx.Client,
    *,
    workspace: Mapping[str, Any],
    package: bytes,
    idempotency_key: str,
) -> dict[str, Any]:
    expected_version = int(workspace["optimistic_version"])
    digest = hashlib.sha256(package).hexdigest()
    manifest = {
        "expected_workspace_version": expected_version,
        "input_completeness": "MODIFIED_ONLY",
        "artifacts": {
            "MODIFIED": {
                "part_name": "modified",
                "media_type": "application/gzip",
                "size_bytes": len(package),
                "raw_sha256": f"sha256:{digest}",
            }
        },
    }
    response = client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions",
        headers=compose_auth_headers(idempotency_key=idempotency_key),
        files={
            "manifest": ("manifest.json", json.dumps(manifest).encode("utf-8"), "application/json"),
            "modified": ("package.tar.gz", package, "application/gzip"),
        },
    )
    return _require_one_of(response, {200, 201}, "upload revision")


def _preview(
    client: httpx.Client,
    *,
    workspace: Mapping[str, Any],
    upload: Mapping[str, Any],
    baseline_node_id: str,
    baseline_head_version: int,
    idempotency_key: str,
    stage: str,
    operation_timeout_seconds: int,
    heartbeat_monitor: WorkerHeartbeatMonitor | None = None,
    collect_timing: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    response = client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/preview-operations",
        headers=compose_auth_headers(idempotency_key=idempotency_key),
        json={
            "expected_workspace_version": upload["optimistic_version"],
            "upload_revision_id": upload["upload_revision_id"],
            "generation": upload["generation"],
            "expected_baseline_node_id": baseline_node_id,
            "expected_baseline_head_version": baseline_head_version,
            "options": {},
        },
    )
    accepted = _require_one_of(response, {200, 202}, "preview acceptance")
    accepted_monotonic = time.monotonic()
    timing: dict[str, Any] = {}
    operation_id = str(accepted["operation_id"])

    def result_is_readable() -> bool:
        current_workspace = _workspace(client)
        result_id = current_workspace.get("current_preview_result_id")
        if type(result_id) is not str or not result_id:
            return False
        result_response = client.get(
            f"/v1/workspaces/{workspace['workspace_id']}/preview-results/{result_id}"
        )
        if result_response.status_code == 404:
            return False
        result_payload = _require(result_response, 200, "preview visibility probe")
        return result_payload.get("operation_id") == operation_id

    deadline = time.monotonic() + operation_timeout_seconds
    _poll_operation(
        client,
        operation_id,
        stage=stage,
        timeout_seconds=operation_timeout_seconds,
        deadline=deadline,
        heartbeat_monitor=heartbeat_monitor,
        accepted_monotonic=accepted_monotonic if collect_timing else None,
        visible_probe=result_is_readable if collect_timing else None,
        timing=timing if collect_timing else None,
    )
    refreshed = _workspace(client)
    result_id = refreshed.get("current_preview_result_id")
    if type(result_id) is not str or not result_id:
        raise JourneyFailure("preview did not publish a current result")
    result = _require(
        client.get(f"/v1/workspaces/{workspace['workspace_id']}/preview-results/{result_id}"),
        200,
        "preview result",
    )
    manifest_response = client.get(
        f"/v1/workspaces/{workspace['workspace_id']}/preview-results/{result_id}/bundle"
    )
    if manifest_response.status_code != 200:
        raise JourneyFailure(f"preview bundle: HTTP {manifest_response.status_code}")
    try:
        manifest = cast(dict[str, Any], json.loads(manifest_response.content))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JourneyFailure("preview bundle was not a JSON manifest") from exc
    summaries = manifest.get("pairs")
    if not isinstance(summaries, list) or not summaries:
        raise JourneyFailure("preview bundle did not include a pair summary")
    preview = {"workspace": refreshed, "result": result}
    if collect_timing:
        timing.setdefault(
            "user_visible_seconds",
            round(time.monotonic() - accepted_monotonic, 3),
        )
        timing.setdefault("visibility_observation", "post_terminal_result_read")
        timing["completion_seconds"] = round(time.monotonic() - accepted_monotonic, 3)
        timing["visibility_poll_interval_seconds"] = 2.0
        preview["operation_timing"] = timing
    return preview, manifest


def _assert_preview_summaries(
    manifest: Mapping[str, Any],
    *,
    unchanged: bool,
) -> dict[str, int]:
    pairs = manifest.get("pairs")
    if not isinstance(pairs, list) or len(pairs) != 1:
        raise JourneyFailure("preview manifest must have exactly one pair")
    totals: Counter[str] = Counter()
    for pair in pairs:
        if not isinstance(pair, dict) or not isinstance(pair.get("summary"), dict):
            raise JourneyFailure("preview pair summary is invalid")
        summary = cast(dict[str, Any], pair["summary"])
        table_count = int(summary.get("table_count", -1))
        changed = int(summary.get("changed_table_count", -1))
        degraded = int(summary.get("degraded_table_count", -1))
        failed = int(summary.get("failed_table_count", -1))
        if min(table_count, changed, degraded, failed) < 0 or table_count == 0:
            raise JourneyFailure("preview table summary is incomplete")
        if degraded or failed or (unchanged and changed):
            raise JourneyFailure("preview table summary violated no-degradation/no-change expectations")
        totals.update(
            {
                "pair_count": 1,
                "table_count": table_count,
                "changed_table_count": changed,
                "degraded_table_count": degraded,
                "failed_table_count": failed,
            }
        )
    return dict(totals)


def _assert_identity_pair(
    preview: Mapping[str, Any],
    *,
    expected_status: str,
    expected_mode: str,
) -> dict[str, str]:
    result = preview.get("result")
    if not isinstance(result, dict):
        raise JourneyFailure("Preview result is missing project identity facts")
    assessment_set_digest = result.get("identity_assessment_set_digest")
    if (
        type(assessment_set_digest) is not str
        or re.fullmatch(r"sha256:[0-9a-f]{64}", assessment_set_digest) is None
    ):
        raise JourneyFailure("Preview identity assessment set digest is invalid")
    pairs = result.get("identity_pairs")
    if not isinstance(pairs, list) or len(pairs) != 1 or not isinstance(pairs[0], dict):
        raise JourneyFailure("Preview identity assessment must contain exactly one pair")
    pair = cast(dict[str, Any], pairs[0])
    expected_applicability = (
        "NOT_APPLICABLE" if expected_status == "NOT_APPLICABLE" else "APPLICABLE"
    )
    if (
        pair.get("status") != expected_status
        or pair.get("mode") != expected_mode
        or pair.get("applicability") != expected_applicability
    ):
        raise JourneyFailure("Preview project identity differs from the expected assessment")
    return {
        "assessment_set_digest": assessment_set_digest,
        "applicability": expected_applicability,
        "status": expected_status,
        "mode": expected_mode,
    }


def _assert_s3_preview_summary(
    summary: Mapping[str, int],
    *,
    dataset_id: str,
    expected_changed: int,
) -> None:
    baseline = S2B_DATASET_BASELINE[dataset_id]
    if (
        summary.get("table_count") != baseline["preview_table_count"] + 1
        or summary.get("changed_table_count") != expected_changed
        or summary.get("degraded_table_count") != 0
        or summary.get("failed_table_count") != 0
    ):
        raise JourneyFailure(f"{dataset_id}: Preview summary differs from the S2b plus composite expectation")


def _assert_s3_catalog_summary(
    repository: Mapping[str, Any],
    *,
    dataset_id: str,
    composite_row_count: int,
) -> None:
    baseline = S2B_DATASET_BASELINE[dataset_id]
    if repository.get("catalog_table_count") != baseline["catalog_table_count"] + 1:
        raise JourneyFailure(f"{dataset_id}: Repository Catalog table count differs from the S2b plus composite expectation")
    if repository.get("composite_signal_point_row_count") != composite_row_count:
        raise JourneyFailure(f"{dataset_id}: Repository composite row count differs from offline projection")
    catalog_rows = repository.get("catalog_row_count_total")
    if type(catalog_rows) is not int or catalog_rows - composite_row_count != baseline["catalog_row_count_total"]:
        raise JourneyFailure(f"{dataset_id}: non-composite Repository row count differs from S2b")


def _assert_s3_history_count(
    *,
    tier: str,
    actual_record_count: int,
    composite_record_count: int,
) -> None:
    expected = S2B_HISTORY_RECORD_COUNTS[tier] + composite_record_count
    if actual_record_count != expected:
        raise JourneyFailure(f"{tier}: History record count differs from S2b plus composite records")


def _submit(
    client: httpx.Client,
    *,
    workspace: Mapping[str, Any],
    upload: Mapping[str, Any],
    preview: Mapping[str, Any],
    baseline_node_id: str,
    baseline_head_version: int,
    idempotency_key: str,
    stage: str,
    operation_timeout_seconds: int,
    expect_no_change: bool = False,
    identity_confirmations: Sequence[Mapping[str, str]] = (),
    heartbeat_monitor: WorkerHeartbeatMonitor | None = None,
    collect_timing: bool = False,
) -> dict[str, Any]:
    workspace_state = cast(Mapping[str, Any], preview["workspace"])
    preview_result = cast(Mapping[str, Any], preview["result"])
    request_started = time.monotonic()
    response = client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=compose_auth_headers(idempotency_key=idempotency_key),
        json={
            "expected_workspace_version": workspace_state["optimistic_version"],
            "upload_revision_id": upload["upload_revision_id"],
            "preview_result_id": preview_result["preview_result_id"],
            "generation": workspace_state["generation"],
            "expected_baseline_node_id": baseline_node_id,
            "expected_baseline_head_version": baseline_head_version,
            "options": {},
            "identity_confirmations": [dict(item) for item in identity_confirmations],
        },
    )
    if expect_no_change:
        payload = _require(response, 409, "no-change submit")
        if payload.get("code") != "NO_CANONICAL_CHANGE":
            raise JourneyFailure("repeat submit did not return NO_CANONICAL_CHANGE")
        no_change_result: dict[str, Any] = {"result": "NO_CANONICAL_CHANGE"}
        if collect_timing:
            elapsed = round(time.monotonic() - request_started, 3)
            no_change_result["operation_timing"] = {
                "user_visible_seconds": elapsed,
                "completion_seconds": elapsed,
                "visibility_observation": "synchronous_no_change_response",
            }
        return no_change_result
    accepted = _require_one_of(response, {200, 202}, "submit acceptance")
    accepted_monotonic = time.monotonic()
    operation_id = str(accepted["operation_id"])
    timing: dict[str, Any] = {"operation_id": operation_id}

    def submission_is_readable() -> bool:
        attempt_response = client.get(
            f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts/{accepted['submit_attempt_id']}"
        )
        if attempt_response.status_code == 404:
            return False
        attempt_payload = _require(attempt_response, 200, "submit visibility attempt")
        if attempt_payload.get("state") != "FINALIZED":
            return False
        submission_response = client.get(
            f"/v1/workspaces/{workspace['workspace_id']}/submissions/{attempt_payload['submission_id']}"
        )
        if submission_response.status_code == 404:
            return False
        _require(submission_response, 200, "submit visibility result")
        return True

    deadline = time.monotonic() + operation_timeout_seconds
    _poll_operation(
        client,
        operation_id,
        stage=stage,
        timeout_seconds=operation_timeout_seconds,
        deadline=deadline,
        heartbeat_monitor=heartbeat_monitor,
        accepted_monotonic=accepted_monotonic if collect_timing else None,
        visible_probe=submission_is_readable if collect_timing else None,
        timing=timing if collect_timing else None,
    )
    _emit_progress(stage, "submit_finalization_started")
    attempt: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        attempt_response = client.get(
            f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts/{accepted['submit_attempt_id']}"
        )
        attempt_payload = _require(attempt_response, 200, "submit attempt")
        if attempt_payload.get("state") in {"FINALIZED", "ABORTED"}:
            attempt = attempt_payload
            break
        time.sleep(2.0)
    if attempt is None or attempt.get("state") != "FINALIZED":
        raise JourneyFailure(f"{stage} attempt did not finalize")
    submission = _require(
        client.get(
            f"/v1/workspaces/{workspace['workspace_id']}/submissions/{attempt['submission_id']}"
        ),
        200,
        "submission read",
    )
    if type(submission.get("repository_commit_id")) is not str:
        raise JourneyFailure("submission did not expose its Repository commit id")
    _emit_progress(stage, "submit_finalized")
    if collect_timing:
        timing.setdefault(
            "user_visible_seconds",
            round(time.monotonic() - accepted_monotonic, 3),
        )
        timing.setdefault("visibility_observation", "post_terminal_submission_read")
        timing["completion_seconds"] = round(time.monotonic() - accepted_monotonic, 3)
        submission["operation_timing"] = timing
    return submission


def _canonical_state_digest_from_submission(
    submission: Mapping[str, Any],
    *,
    stage: str,
) -> str:
    digest = submission.get("canonical_business_digest")
    if type(digest) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
        raise JourneyFailure(f"{stage} did not expose a canonical state digest")
    return digest


def _approve(client: httpx.Client, submission_id: str, idempotency_key: str) -> None:
    _require_one_of(
        client.post(
            f"/v1/submissions/{submission_id}/review-events",
            headers=compose_auth_headers(token=ARCHIVER_TOKEN, idempotency_key=idempotency_key),
            json={"expected_review_version": 0, "action": "APPROVE"},
        ),
        {200, 201},
        "submission approval",
    )


def _archive(
    client: httpx.Client,
    submission_id: str,
    key_prefix: str,
    *,
    identity_exception_reason: str | None = None,
) -> dict[str, Any]:
    candidates = _require(
        client.get("/v1/archive-candidates", headers=compose_auth_headers(token=ARCHIVER_TOKEN)),
        200,
        "archive candidates",
    )
    raw_candidates = candidates.get("candidates")
    if not isinstance(raw_candidates, list):
        raise JourneyFailure("archive candidates response is invalid")
    selected = next(
        (
            cast(dict[str, Any], item)
            for item in raw_candidates
            if isinstance(item, dict) and item.get("submission_id") == submission_id
        ),
        None,
    )
    if selected is None:
        raise JourneyFailure("submission was not an archive candidate")
    preview = _require(
        client.post(
            "/v1/archive-plan-preview",
            headers=compose_auth_headers(token=ARCHIVER_TOKEN),
            json={"selected": selected},
        ),
        200,
        "archive plan preview",
    )
    if preview.get("can_start") is not False:
        raise JourneyFailure("archive plan should require explicit confirmation")
    raw_anomalies = preview.get("anomalies")
    if not isinstance(raw_anomalies, list):
        raise JourneyFailure("archive plan anomalies are invalid")
    anomalies = [cast(dict[str, Any], item) for item in raw_anomalies if isinstance(item, dict)]
    if len(anomalies) != len(raw_anomalies):
        raise JourneyFailure("archive plan contains an invalid anomaly")
    identity_anomalies = [
        item for item in anomalies if item.get("subject_kind") == "PROJECT_IDENTITY_EXCEPTION"
    ]
    other_anomalies = [
        item for item in anomalies if item.get("subject_kind") != "PROJECT_IDENTITY_EXCEPTION"
    ]
    if other_anomalies:
        raise JourneyFailure("archive plan contains an unexpected non-identity anomaly")
    if identity_exception_reason is None and identity_anomalies:
        raise JourneyFailure("archive plan has an unresolved project identity exception")
    if identity_exception_reason is not None and (
        len(identity_anomalies) != 1
        or identity_anomalies[0].get("target_submission_id") != submission_id
        or identity_anomalies[0].get("target_candidate_digest")
        != selected.get("expected_candidate_digest")
        or identity_anomalies[0].get("issue_code") != "PROJECT_IDENTITY_EXCEPTION"
    ):
        raise JourneyFailure("archive plan identity exception differs from the selected submission")
    head = cast(dict[str, Any], preview["head"])
    confirmation = _require_one_of(
        client.post(
            "/v1/archive-confirmations",
            headers=compose_auth_headers(
                token=ARCHIVER_TOKEN,
                idempotency_key=f"{key_prefix}-archive-confirm",
            ),
            json={
                "expected_baseline_node_id": head["business_baseline_node_id"],
                "expected_baseline_head_version": head["baseline_head_version"],
                "selected": selected,
                "candidate_set_digest": preview["candidate_set_digest"],
                "subject_digest": preview["selection_subject_digest"],
                "expected_sequence": 0,
                "action": "CONFIRM",
                "reason": "archive real dump submission after review",
            },
        ),
        {200, 201},
        "archive confirmation",
    )
    anomaly_resolution_refs: list[dict[str, Any]] = []
    if identity_exception_reason is not None:
        identity_anomaly = identity_anomalies[0]
        resolution = _require_one_of(
            client.post(
                "/v1/archive-anomaly-resolutions",
                headers=compose_auth_headers(
                    token=ARCHIVER_TOKEN,
                    idempotency_key=f"{key_prefix}-identity-resolution",
                ),
                json={
                    "expected_baseline_node_id": head["business_baseline_node_id"],
                    "expected_baseline_head_version": head["baseline_head_version"],
                    "selected": selected,
                    "candidate_set_digest": preview["candidate_set_digest"],
                    "subject_digest": identity_anomaly["subject_digest"],
                    "expected_sequence": 0,
                    "action": "ACKNOWLEDGE_IDENTITY_EXCEPTION",
                    "subject_kind": "PROJECT_IDENTITY_EXCEPTION",
                    "reason": identity_exception_reason,
                    "issue_code": identity_anomaly["issue_code"],
                    "target_submission_id": identity_anomaly["target_submission_id"],
                    "target_candidate_digest": identity_anomaly["target_candidate_digest"],
                },
            ),
            {200, 201},
            "identity exception resolution",
        )
        anomaly_resolution_refs.append(
            {"subject_digest": identity_anomaly["subject_digest"], "sequence": resolution["sequence"]}
        )
    ready = _require(
        client.post(
            "/v1/archive-plan-preview",
            headers=compose_auth_headers(token=ARCHIVER_TOKEN),
            json={"selected": selected},
        ),
        200,
        "confirmed archive plan preview",
    )
    if ready.get("can_start") is not True or ready.get("audit_validity") is not True:
        raise JourneyFailure("confirmed archive plan is not ready")
    ready_head = cast(dict[str, Any], ready["head"])
    archived = _require_one_of(
        client.post(
            "/v1/archives",
            headers=compose_auth_headers(
                token=ARCHIVER_TOKEN,
                idempotency_key=f"{key_prefix}-archive-start",
            ),
            json={
                "expected_baseline_node_id": ready_head["business_baseline_node_id"],
                "expected_baseline_head_version": ready_head["baseline_head_version"],
                "candidate_set_digest": ready["candidate_set_digest"],
                "selected": selected,
                "confirmation_refs": [
                    {
                        "subject_digest": ready["selection_subject_digest"],
                        "sequence": confirmation["sequence"],
                    }
                ],
                "anomaly_resolution_refs": anomaly_resolution_refs,
            },
        ),
        {200, 201},
        "archive start",
    )
    if type(archived.get("baseline_node_id")) is not str:
        raise JourneyFailure("archive did not advance the baseline node")
    return archived


def _repository_service_url(env: Mapping[str, str]) -> str:
    result = run_compose(cast(dict[str, str], dict(env)), "ps", "-q", "repository-service")
    container_id = result.stdout.strip().splitlines()
    if result.returncode != 0 or not container_id:
        raise JourneyFailure("could not resolve Repository Service container")
    inspected = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            container_id[0],
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    address = inspected.stdout.strip()
    if inspected.returncode != 0 or not address:
        raise JourneyFailure("Repository Service container has no reachable network address")
    return f"http://{address}:8000"


def _pseudo_counts_from_http(
    *,
    base_url: str,
    repository_id: str,
    commit_id: str,
    expected_tables: Mapping[str, int],
    expected_row_counts: Mapping[str, int],
) -> dict[str, Any]:
    if set(expected_tables) != set(expected_row_counts):
        raise JourneyFailure("ordered census pseudo and row counts do not cover the same tables")
    repository_client = httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {BEARER_TOKEN}"},
        timeout=300.0,
    )
    try:
        encoded = encode_commit_id_path_segment(commit_id)
        catalog_response = repository_client.get(
            f"/v1/repositories/{repository_id}/versioned/commits/{encoded}/catalog",
        )
        if catalog_response.status_code != 200:
            code = "unknown"
            try:
                error_payload = catalog_response.json()
                if isinstance(error_payload, dict) and isinstance(error_payload.get("code"), str):
                    code = error_payload["code"]
            except ValueError:
                pass
            raise JourneyFailure(
                f"Repository catalog HTTP {catalog_response.status_code} ({code})"
            )
        try:
            catalog = GetVersionedCatalogResponse.model_validate_json(catalog_response.content)
        except ValueError as exc:
            raise JourneyFailure("Repository catalog JSON response is invalid") from exc
        if catalog.catalog.commit_id != commit_id:
            raise JourneyFailure("Repository catalog commit ID differs from requested commit")
        composite_tables = [
            table
            for table in catalog.catalog.tables
            if table.name == "composite_signal_point"
        ]
        if len(composite_tables) != 1:
            raise JourneyFailure("Repository Catalog must contain one composite_signal_point table")

        actual: dict[str, int] = {}
        actual_row_counts: dict[str, int] = {}
        for table_name in sorted(expected_tables):
            response = repository_client.get(
                f"/v1/repositories/{repository_id}/versioned/commits/{encoded}/rows",
                params={"table_name": table_name},
            )
            if response.status_code != 200:
                raise JourneyFailure(f"Repository rows HTTP {response.status_code} for ordered table")
            pseudo_count = 0
            total = 0
            try:
                reader = pa_ipc.open_stream(response.content)
                if "gid" not in reader.schema.names:
                    raise JourneyFailure("ordered table Arrow schema has no gid column")
                gid_index = reader.schema.get_field_index("gid")
                for batch in reader:
                    gids = batch.column(gid_index)
                    total += batch.num_rows
                    pseudo_count += sum(
                        int(value.as_py()) >= PSEUDO_GID_MIN
                        for value in gids
                        if value.as_py() is not None
                    )
            except (pa.ArrowInvalid, ValueError, TypeError) as exc:
                raise JourneyFailure("Repository ordered table Arrow stream is invalid") from exc
            expected_rows = expected_row_counts[table_name]
            if total != expected_rows:
                raise JourneyFailure("Repository ordered row count differs from census")
            actual[table_name] = pseudo_count
            actual_row_counts[table_name] = total
        expected_total = sum(int(value) for value in expected_tables.values())
        actual_total = sum(actual.values())
        if actual_total != expected_total:
            raise JourneyFailure("Repository ordered pseudo row count differs from census")
        return {
            "ordered_table_count": len(actual),
            "ordered_row_count_total": sum(actual_row_counts.values()),
            "ordered_table_pseudo_counts": actual,
            "pseudo_rows_total": actual_total,
            "catalog_json_bytes": len(catalog_response.content),
            "catalog_table_count": len(catalog.catalog.tables),
            "catalog_row_count_total": sum(
                table.row_count for table in catalog.catalog.tables
            ),
            "composite_signal_point_row_count": composite_tables[0].row_count,
        }
    finally:
        repository_client.close()


def _measure_repository_commit_rows(
    *,
    base_url: str,
    repository_id: str,
    commit_id: str,
    scenario: str,
    scratch_root: Path,
) -> dict[str, Any]:
    """Measure public RS Arrow reads and Arrow-to-Python conversion without retaining rows."""
    repository_client = httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {BEARER_TOKEN}"},
        timeout=300.0,
    )
    try:
        encoded = encode_commit_id_path_segment(commit_id)
        wall_started = time.perf_counter()
        cpu_started = time.thread_time()
        catalog_response = repository_client.get(
            f"/v1/repositories/{repository_id}/versioned/commits/{encoded}/catalog",
        )
        catalog_wall = time.perf_counter() - wall_started
        catalog_cpu = time.thread_time() - cpu_started
        if catalog_response.status_code != 200:
            raise JourneyFailure(
                f"DC32 Repository catalog HTTP {catalog_response.status_code}"
            )
        try:
            catalog = GetVersionedCatalogResponse.model_validate_json(catalog_response.content)
        except ValueError as exc:
            raise JourneyFailure("DC32 Repository catalog response is invalid") from exc
        if catalog.catalog.commit_id != commit_id:
            raise JourneyFailure("DC32 Repository catalog commit identity changed")

        tables: list[dict[str, Any]] = []
        total_rows = 0
        total_arrow_bytes = 0
        largest: tuple[str, pa.Table] | None = None
        for table in catalog.catalog.tables:
            response_started = time.perf_counter()
            response_cpu_started = time.thread_time()
            response = repository_client.get(
                f"/v1/repositories/{repository_id}/versioned/commits/{encoded}/rows",
                params={"table_name": table.name},
            )
            response_wall = time.perf_counter() - response_started
            response_cpu = time.thread_time() - response_cpu_started
            if response.status_code != 200:
                raise JourneyFailure(
                    f"DC32 Repository rows HTTP {response.status_code} for table"
                )
            arrow_bytes = response.content
            decode_started = time.perf_counter()
            decode_cpu_started = time.thread_time()
            try:
                arrow_table = pa_ipc.open_stream(arrow_bytes).read_all()
            except (pa.ArrowInvalid, ValueError, TypeError) as exc:
                raise JourneyFailure("DC32 Repository Arrow stream is invalid") from exc
            decode_wall = time.perf_counter() - decode_started
            decode_cpu = time.thread_time() - decode_cpu_started
            if arrow_table.num_rows != table.row_count:
                raise JourneyFailure("DC32 Arrow row count differs from Repository Catalog")

            conversion_started = time.perf_counter()
            conversion_cpu_started = time.thread_time()
            converted_columns = [column.to_pylist() for column in arrow_table.columns]
            converted_row_count = len(converted_columns[0]) if converted_columns else 0
            conversion_wall = time.perf_counter() - conversion_started
            conversion_cpu = time.thread_time() - conversion_cpu_started
            if converted_row_count != table.row_count:
                raise JourneyFailure("DC32 Arrow-to-Python conversion lost rows")

            tables.append(
                {
                    "table_name": table.name,
                    "row_count": table.row_count,
                    "column_count": len(table.columns),
                    "arrow_response_bytes": len(arrow_bytes),
                    "rs_arrow_read": {
                        "wall_seconds": round(response_wall, 6),
                        "thread_cpu_seconds": round(response_cpu, 6),
                        "mib_per_second": _mib_per_second(len(arrow_bytes), response_wall),
                    },
                    "arrow_stream_decode": {
                        "wall_seconds": round(decode_wall, 6),
                        "thread_cpu_seconds": round(decode_cpu, 6),
                    },
                    "arrow_to_python": {
                        "wall_seconds": round(conversion_wall, 6),
                        "thread_cpu_seconds": round(conversion_cpu, 6),
                        "rows_materialized": converted_row_count,
                    },
                }
            )
            total_rows += table.row_count
            total_arrow_bytes += len(arrow_bytes)
            if largest is None or table.row_count > largest[1].num_rows:
                largest = (table.name, arrow_table)
            del converted_columns

        ipc_roundtrip: dict[str, Any] | None = None
        if largest is not None:
            scratch_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd, raw_path = tempfile.mkstemp(prefix="dc32-arrow-", suffix=".ipc", dir=scratch_root)
            os.fchmod(fd, 0o600)
            os.close(fd)
            ipc_path = Path(raw_path)
            table_name, largest_table = largest
            write_started = time.perf_counter()
            write_cpu_started = time.thread_time()
            with pa.OSFile(str(ipc_path), "wb") as sink:
                with pa_ipc.new_file(sink, largest_table.schema) as writer:
                    writer.write_table(largest_table)
            write_wall = time.perf_counter() - write_started
            write_cpu = time.thread_time() - write_cpu_started
            mmap_started = time.perf_counter()
            mmap_cpu_started = time.thread_time()
            buffer_hash = hashlib.sha256()
            with pa.memory_map(str(ipc_path), "r") as source:
                mapped = pa_ipc.open_file(source).read_all()
                for column in mapped.columns:
                    for chunk in column.chunks:
                        for buffer in chunk.buffers():
                            if buffer is not None:
                                buffer_hash.update(memoryview(buffer))
            mmap_wall = time.perf_counter() - mmap_started
            mmap_cpu = time.thread_time() - mmap_cpu_started
            ipc_roundtrip = {
                "table_name": table_name,
                "row_count": largest_table.num_rows,
                "column_count": largest_table.num_columns,
                "ipc_file_bytes": ipc_path.stat().st_size,
                "ipc_write": {
                    "wall_seconds": round(write_wall, 6),
                    "thread_cpu_seconds": round(write_cpu, 6),
                },
                "ipc_mmap_read_and_buffer_scan": {
                    "wall_seconds": round(mmap_wall, 6),
                    "thread_cpu_seconds": round(mmap_cpu, 6),
                    "sha256_prefix": buffer_hash.hexdigest()[:12],
                },
            }
            ipc_path.unlink(missing_ok=True)
        return {
            "scenario": scenario,
            "repository_id": repository_id,
            "commit_id": commit_id,
            "catalog": {
                "wall_seconds": round(catalog_wall, 6),
                "thread_cpu_seconds": round(catalog_cpu, 6),
                "response_bytes": len(catalog_response.content),
                "table_count": len(catalog.catalog.tables),
                "row_count_total": total_rows,
            },
            "total_arrow_response_bytes": total_arrow_bytes,
            "tables": tables,
            "arrow_ipc_roundtrip_largest_table": ipc_roundtrip,
        }
    finally:
        repository_client.close()


def _mib_per_second(size_bytes: int, seconds: float) -> float | None:
    if seconds <= 0:
        return None
    return round(size_bytes / (1024 * 1024) / seconds, 3)


def _write_private_dc32_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def _assert_initial_repository_commit_empty(
    *,
    base_url: str,
    repository_id: str,
    commit_id: str,
) -> dict[str, int]:
    repository_client = httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {BEARER_TOKEN}"},
        timeout=300.0,
    )
    try:
        encoded = encode_commit_id_path_segment(commit_id)
        response = repository_client.get(
            f"/v1/repositories/{repository_id}/versioned/commits/{encoded}/catalog",
        )
        if response.status_code != 200:
            raise JourneyFailure(f"initial Repository catalog HTTP {response.status_code}")
        try:
            catalog = GetVersionedCatalogResponse.model_validate_json(response.content)
        except ValueError as exc:
            raise JourneyFailure("initial Repository catalog JSON response is invalid") from exc
        if catalog.catalog.commit_id != commit_id:
            raise JourneyFailure("initial Repository Catalog commit ID differs from requested commit")
        if catalog.catalog.tables:
            raise JourneyFailure("initial Repository commit is not empty")
        return {"catalog_table_count": 0, "catalog_row_count_total": 0}
    finally:
        repository_client.close()


def _history_surface_ref(bundle: Mapping[str, Any]) -> Mapping[str, Any]:
    pairs = bundle.get("pairs")
    if not isinstance(pairs, list) or len(pairs) != 1 or not isinstance(pairs[0], Mapping):
        raise JourneyFailure("History bundle does not contain exactly one pair")
    pair_id = pairs[0].get("pair_id")
    if type(pair_id) is not str or not pair_id:
        raise JourneyFailure("History bundle pair has no identity")
    entries = bundle.get("closure_entries")
    if not isinstance(entries, list):
        raise JourneyFailure("History bundle has no closure entries")
    surface_path = f"pairs/{pair_id}/comparison-surface.json"
    surface_entries = [
        item
        for item in entries
        if isinstance(item, Mapping)
        and item.get("kind") == "SURFACE"
        and item.get("logical_path") == surface_path
    ]
    if len(surface_entries) != 1:
        raise JourneyFailure("History bundle does not contain exactly one surface artifact")
    surface_ref = surface_entries[0].get("artifact_ref")
    if not isinstance(surface_ref, Mapping):
        raise JourneyFailure("History surface artifact has no reference")
    return cast(Mapping[str, Any], surface_ref)


def _history_compare(
    client: httpx.Client,
    *,
    tier: str,
    v1_submission_id: str,
    v1_commit_id: str,
    v2_submission_id: str,
    v2_commit_id: str,
    idempotency_key: str,
    operation_timeout_seconds: int,
    heartbeat_monitor: WorkerHeartbeatMonitor | None = None,
    collect_timing: bool = False,
) -> tuple[dict[str, Any], str]:
    stage = f"{tier} History"
    _emit_progress(stage, "history_compare_started")
    response = client.post(
        "/v1/history-compares",
        headers=compose_auth_headers(token=HISTORY_READER_TOKEN, idempotency_key=idempotency_key),
        json={
            "nodes": [
                {"ref_kind": "submission", "ref_id": v1_submission_id},
                {"ref_kind": "submission", "ref_id": v2_submission_id},
            ]
        },
    )
    accepted = _require_one_of(response, {200, 202}, "History compare acceptance")
    operation_id = str(accepted["operation_id"])
    accepted_monotonic = time.monotonic()
    operation_started = accepted_monotonic
    timing: dict[str, Any] = {"operation_id": operation_id}
    _emit_progress(stage, "operation_started", timeout_seconds=operation_timeout_seconds)
    deadline = time.monotonic() + operation_timeout_seconds
    terminal: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        payload = _require(
            client.get(
                f"/v1/history-compares/{operation_id}",
                headers=compose_auth_headers(token=HISTORY_READER_TOKEN),
            ),
            200,
            "History compare status",
        )
        if heartbeat_monitor is not None:
            heartbeat_monitor.check_operation(operation_id, payload.get("status"), stage=stage)
        if payload.get("status") in TERMINAL_OPERATION_STATES:
            terminal = payload
            break
        time.sleep(2.0)
    if terminal is None or terminal.get("status") != "SUCCEEDED":
        diagnostic = terminal.get("diagnostic") if terminal is not None else None
        code = diagnostic.get("code") if isinstance(diagnostic, dict) else "timeout"
        raise JourneyFailure(f"{stage} compare did not succeed, diagnostic={code}")
    _emit_progress(
        stage,
        "operation_succeeded",
        operation_status=terminal["status"],
        timeout_seconds=operation_timeout_seconds,
        operation_wall_seconds=round(time.monotonic() - operation_started, 3),
    )
    if collect_timing:
        terminal_seconds = time.monotonic() - accepted_monotonic
        timing["operation_terminal_seconds"] = round(terminal_seconds, 3)
        timing["user_visible_seconds"] = round(terminal_seconds, 3)
        timing["visibility_observation"] = "terminal_history_result"
    result = terminal.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("pairs"), list) or len(result["pairs"]) != 1:
        raise JourneyFailure("History compare result has an unexpected pair count")
    pair = cast(dict[str, Any], result["pairs"][0])
    if pair.get("before_commit") != v1_commit_id or pair.get("current_commit") != v2_commit_id:
        raise JourneyFailure("History compare did not use the v1 and v2 Repository commits")
    bundle_response = client.get(
        f"/v1/history-compares/{operation_id}/bundle",
        headers=compose_auth_headers(token=HISTORY_READER_TOKEN),
    )
    if bundle_response.status_code != 200:
        raise JourneyFailure(f"History compare bundle HTTP {bundle_response.status_code}")
    try:
        bundle = cast(dict[str, Any], json.loads(bundle_response.content))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JourneyFailure("History compare bundle was not a JSON manifest") from exc
    if not isinstance(bundle.get("closure_entries"), list):
        raise JourneyFailure("History compare bundle does not have closure entries")
    _emit_progress(stage, "history_compare_succeeded")
    result_value: dict[str, Any] = {
        "operation_id": operation_id,
        "pair": pair,
        "bundle": bundle,
        "bundle_digest": result.get("bundle_digest"),
    }
    if collect_timing:
        timing["completion_seconds"] = round(time.monotonic() - accepted_monotonic, 3)
        result_value["operation_timing"] = timing
    return result_value, operation_id


def _keyless_fallback_candidates(census: Mapping[str, Any]) -> tuple[str, ...]:
    scan = census.get("effective_key_scan")
    if not isinstance(scan, dict):
        raise JourneyFailure("census has no effective-key scan")
    unresolved = scan.get("unresolved_tables")
    if not isinstance(unresolved, list) or any(type(item) is not str for item in unresolved):
        raise JourneyFailure("census effective-key unresolved table list is invalid")
    return tuple(sorted(set(cast(list[str], unresolved))))


def _offline_composite_comparison(
    *,
    tier: str,
    v1_id: str,
    v2_id: str,
    root: Path,
    datasets: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    v1_package, _v1_file = _dataset_package(root, datasets[v1_id])
    v2_package, _v2_file = _dataset_package(root, datasets[v2_id])
    started = time.monotonic()
    try:
        result = compare_composite_packages(
            v1_package,
            v2_package,
            pair_id=f"{tier}-composite-pair",
        )
    except CompositeProjectionError as exc:
        raise JourneyFailure(f"{tier}: offline composite comparison failed: {exc}") from exc
    elapsed = round(time.monotonic() - started, 3)
    counts = asdict(result)
    _emit_progress(
        f"{tier} offline composite comparison",
        "composite_counts_verified",
        counts=counts,
        elapsed_seconds=elapsed,
    )
    return {"counts": counts, "elapsed_seconds": elapsed}


def _run_tier(
    *,
    tier: str,
    v1_id: str,
    v2_id: str,
    root: Path,
    datasets: Mapping[str, dict[str, Any]],
    census: Mapping[str, dict[str, Any]],
    env: dict[str, str],
    project_name: str,
    repository_id: str,
    initial_commit_id: str,
    step_state: dict[str, Any],
    from_step: str | None,
    state_path: Path | None,
    offline_composite: Mapping[str, Any],
    heartbeat_monitor: WorkerHeartbeatMonitor | None = None,
    scope: str = "full",
    dc32_metrics: list[dict[str, Any]] | None = None,
    dc32_scratch_root: Path | None = None,
    dc32_session_root: Path | None = None,
    debug_t1_submit_probe: bool = False,
    debug_submit_probe_root: Path | None = None,
    debug_submit_probe_metrics: list[dict[str, Any]] | None = None,
    collect_timing: bool = False,
) -> dict[str, Any]:
    def record_operation_timing(operation: str, value: Mapping[str, Any]) -> None:
        timing = value.get("operation_timing")
        if dc32_metrics is not None and isinstance(timing, Mapping):
            dc32_metrics.append(
                {
                    "kind": "operation_timing",
                    "tier": tier,
                    "operation": operation,
                    "timing": dict(timing),
                }
            )

    def capture_submit_reconciliation(submission: Mapping[str, Any], *, version: str) -> None:
        capture_t4_evidence = tier == "t4" and dc32_metrics is not None
        capture_t1_debug = tier == "t1" and debug_t1_submit_probe
        if not capture_t4_evidence and not capture_t1_debug:
            return
        operation_timing = submission.get("operation_timing")
        operation_id = (
            operation_timing.get("operation_id")
            if isinstance(operation_timing, Mapping)
            else None
        )
        if type(operation_id) is not str:
            raise JourneyFailure(f"{tier} {version} Submit evidence identity is unavailable")
        if capture_t4_evidence:
            if dc32_session_root is None or dc32_metrics is None:
                raise JourneyFailure("t4 Submit evidence output root is unavailable")
            evidence_root = dc32_session_root / f"t4-{version}-submit"
        else:
            if debug_submit_probe_root is None or debug_submit_probe_metrics is None:
                raise JourneyFailure("t1 debug Submit probe output root is unavailable")
            evidence_root = debug_submit_probe_root / f"t1-{version}-submit"
        facts = _capture_submit_reconciliation_facts(
            env=env,
            repository_url=repository_url,
            repository_id=repository_id,
            operation_id=operation_id,
            root=evidence_root,
            enforce_three_session_limit=capture_t4_evidence,
        )
        if capture_t4_evidence:
            cast(list[dict[str, Any]], dc32_metrics).append(
                {
                    "kind": "submit_reconciliation",
                    "tier": tier,
                    "version": version,
                    "facts": facts,
                }
            )
        else:
            cast(list[dict[str, Any]], debug_submit_probe_metrics).append(
                {
                    "kind": "submit_reconciliation",
                    "tier": tier,
                    "version": version,
                    "facts": facts,
                }
            )
            _emit_progress(
                f"{tier} {version} Submit reconciliation probe",
                "facts_verified",
                **facts,
            )

    started = time.monotonic()
    v1_bytes, v1_file = _dataset_package(root, datasets[v1_id])
    v2_bytes, v2_file = _dataset_package(root, datasets[v2_id])
    composite_counts = cast(dict[str, Any], offline_composite["counts"])
    composite_v1_row_count = int(composite_counts["before_row_count"])
    composite_v2_row_count = int(composite_counts["current_row_count"])
    composite_changed = composite_counts["status"] not in {"UNCHANGED", "BUSINESS_EQUIVALENT"}
    v1_ordered = _ordered_tables(census[v1_id])
    v2_ordered = _ordered_tables(census[v2_id])
    v1_ordered_row_counts = _ordered_table_row_counts(census[v1_id])
    v2_ordered_row_counts = _ordered_table_row_counts(census[v2_id])
    v1_keyless_names = _keyless_fallback_candidates(census[v1_id])
    v2_keyless_names = _keyless_fallback_candidates(census[v2_id])
    if int(census[v1_id]["ordered_projection"]["pseudo_rows_total"]) != EXPECTED_PSEUDO_TOTALS[v1_id]:
        raise JourneyFailure(f"{v1_id}: census pseudo total differs from the accepted baseline")
    if int(census[v2_id]["ordered_projection"]["pseudo_rows_total"]) != EXPECTED_PSEUDO_TOTALS[v2_id]:
        raise JourneyFailure(f"{v2_id}: census pseudo total differs from the accepted baseline")
    if tier == "t1":
        depth = census[v1_id].get("logics_xml_max_depth")
        if depth != 1:
            raise JourneyFailure("t1 v1 logics.xml max depth differs from the accepted depth of 1")

    images = compose_image_ids(env)
    repository_url = _repository_service_url(env)
    initial_repository = _assert_initial_repository_commit_empty(
        base_url=repository_url,
        repository_id=repository_id,
        commit_id=initial_commit_id,
    )
    _emit_progress(
        f"{tier} initial Repository commit",
        "empty_initial_verified",
        **initial_repository,
    )
    if tier == "t4" and dc32_metrics is not None and dc32_scratch_root is not None:
        empty_baseline_read = _measure_repository_commit_rows(
            base_url=repository_url,
            repository_id=repository_id,
            commit_id=initial_commit_id,
            scenario="t4_v1_preview_empty_baseline",
            scratch_root=dc32_scratch_root,
        )
        dc32_metrics.append(
            {
                "kind": "repository_baseline_read",
                "tier": tier,
                "used_by_scenarios": ["t4_v1_preview"],
                "measurement": empty_baseline_read,
            }
        )
    runner = JourneyStepRunner(
        tier=tier,
        env=env,
        state=step_state,
        from_step=from_step,
        state_path=state_path,
    )

    with httpx.Client(
        base_url=BACKEND_URL,
        headers=compose_auth_headers(),
        timeout=600.0,
    ) as client:
        v1_workspace = runner.run("v1-workspace", lambda: _workspace(client))
        v1_upload = runner.run(
            "v1-upload",
            lambda: _upload_revision(
                client,
                workspace=cast(Mapping[str, Any], v1_workspace),
                package=v1_bytes,
                idempotency_key=f"{project_name}-{tier}-v1-upload",
            ),
        )

        def v1_preview_action() -> dict[str, Any]:
            preview, manifest = _preview(
                client,
                workspace=cast(Mapping[str, Any], v1_workspace),
                upload=cast(Mapping[str, Any], v1_upload),
                baseline_node_id=BASELINE_NODE_ID,
                baseline_head_version=0,
                idempotency_key=f"{project_name}-{tier}-v1-preview",
                stage=f"{tier} v1 Preview",
                operation_timeout_seconds=_operation_timeout_seconds(tier, "v1-preview"),
                heartbeat_monitor=heartbeat_monitor,
                collect_timing=collect_timing,
            )
            summary = _assert_preview_summaries(
                manifest,
                unchanged=False,
            )
            _assert_s3_preview_summary(
                summary,
                dataset_id=v1_id,
                expected_changed=S2B_DATASET_BASELINE[v1_id]["preview_table_count"] + 1,
            )
            _emit_progress(
                f"{tier} v1 Preview",
                "preview_summary_verified",
                summary=summary,
                source_census_table_count=int(census[v1_id]["table_count"]),
                composite_row_count=composite_v1_row_count,
            )
            return {
                "preview": preview,
                "manifest": manifest,
                "summary": summary,
                "keyless_fallback_candidates": list(v1_keyless_names),
            }

        v1_preview_state = cast(
            dict[str, Any],
            runner.run("v1-preview", v1_preview_action),
        )
        v1_preview = cast(dict[str, Any], v1_preview_state["preview"])
        record_operation_timing("v1_preview", v1_preview)
        v1_summary = cast(dict[str, int], v1_preview_state["summary"])
        v1_identity = _assert_identity_pair(
            v1_preview,
            expected_status="NOT_APPLICABLE",
            expected_mode="DETAILED",
        )

        v1_submission = runner.run(
            "v1-submit",
            lambda: _submit(
                client,
                workspace=cast(Mapping[str, Any], v1_workspace),
                upload=cast(Mapping[str, Any], v1_upload),
                preview=v1_preview,
                baseline_node_id=BASELINE_NODE_ID,
                baseline_head_version=0,
                idempotency_key=f"{project_name}-{tier}-v1-submit",
                stage=f"{tier} v1 Submit",
                operation_timeout_seconds=_operation_timeout_seconds(tier, "v1-submit"),
                heartbeat_monitor=heartbeat_monitor,
                collect_timing=collect_timing,
            ),
        )
        v1_submission = cast(dict[str, Any], v1_submission)
        record_operation_timing("v1_submit", v1_submission)
        capture_submit_reconciliation(v1_submission, version="v1")
        v1_submission_id = str(v1_submission["submission_id"])
        v1_commit_id = str(v1_submission["repository_commit_id"])
        v1_canonical_state_digest = _canonical_state_digest_from_submission(
            v1_submission,
            stage=f"{tier} v1 Submit",
        )
        if scope == "t4-v1-submit":
            return {
                "tier": tier,
                "scope": scope,
                "dataset": {
                    "dataset_id": v1_id,
                    "sha256": v1_file["sha256"],
                    "package_bytes": v1_file["bytes"],
                    "table_count": census[v1_id]["table_count"],
                    "row_count_total": census[v1_id]["row_count_total"],
                    "preview": v1_summary,
                    "identity": v1_identity,
                    "submit": {
                        "canonical_state_digest": v1_canonical_state_digest,
                        "submission_id": v1_submission_id,
                    },
                },
                "step_metrics": runner.metrics,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "conclusion": "PASS",
                "empty_initial_commit_id": initial_commit_id,
            }

        def v1_repository_read_action() -> dict[str, Any]:
            repository = _pseudo_counts_from_http(
                base_url=repository_url,
                repository_id=repository_id,
                commit_id=v1_commit_id,
                expected_tables=v1_ordered,
                expected_row_counts=v1_ordered_row_counts,
            )
            _assert_s3_catalog_summary(
                repository,
                dataset_id=v1_id,
                composite_row_count=composite_v1_row_count,
            )
            if repository["pseudo_rows_total"] != EXPECTED_PSEUDO_TOTALS[v1_id]:
                raise JourneyFailure(f"{v1_id}: committed pseudo row count differs from census")
            return repository

        v1_repository = cast(
            dict[str, Any],
            runner.run("v1-repository-read", v1_repository_read_action),
        )
        if dc32_metrics is not None and dc32_scratch_root is not None:
            v1_commit_read = _measure_repository_commit_rows(
                base_url=repository_url,
                repository_id=repository_id,
                commit_id=v1_commit_id,
                scenario=f"{tier}_v1_commit_baseline",
                scratch_root=dc32_scratch_root,
            )
            used_by_scenarios = [f"{tier}_v2_preview", f"{tier}_history"]
            if tier == "t4":
                used_by_scenarios.insert(0, "t4_repeat_v1_preview")
            dc32_metrics.append(
                {
                    "kind": "repository_baseline_read",
                    "tier": tier,
                    "used_by_scenarios": used_by_scenarios,
                    "measurement": v1_commit_read,
                }
            )
        def approve_v1_action() -> dict[str, bool]:
            _approve(client, v1_submission_id, f"{project_name}-{tier}-v1-review")
            return {"approved": True}

        runner.run("v1-approve", approve_v1_action)

        def archive_v1_action() -> dict[str, Any]:
            archive = _archive(client, v1_submission_id, f"{project_name}-{tier}-v1")
            if archive.get("baseline_commit_id") != v1_commit_id:
                raise JourneyFailure("v1 Archive did not promote the v1 Repository commit")
            return archive

        archive = cast(dict[str, Any], runner.run("v1-archive", archive_v1_action))
        baseline_node_id = str(archive["baseline_node_id"])
        baseline_head_version = int(archive["baseline_head_version"])

        if scope == "t4-identity":
            v2_workspace_partial = runner.run("v2-workspace", lambda: _workspace(client))
            v2_upload_partial = runner.run(
                "v2-upload",
                lambda: _upload_revision(
                    client,
                    workspace=cast(Mapping[str, Any], v2_workspace_partial),
                    package=v2_bytes,
                    idempotency_key=f"{project_name}-{tier}-v2-upload",
                ),
            )

            def v2_preview_partial_action() -> dict[str, Any]:
                preview, manifest = _preview(
                    client,
                    workspace=cast(Mapping[str, Any], v2_workspace_partial),
                    upload=cast(Mapping[str, Any], v2_upload_partial),
                    baseline_node_id=baseline_node_id,
                    baseline_head_version=baseline_head_version,
                    idempotency_key=f"{project_name}-{tier}-v2-preview",
                    stage=f"{tier} v2 Preview",
                    operation_timeout_seconds=_operation_timeout_seconds(tier, "v2-preview"),
                    heartbeat_monitor=heartbeat_monitor,
                    collect_timing=collect_timing,
                )
                summary = _assert_preview_summaries(manifest, unchanged=False)
                expected_changed = S2B_DATASET_BASELINE[v2_id]["preview_changed"] + int(
                    composite_changed
                )
                _assert_s3_preview_summary(
                    summary,
                    dataset_id=v2_id,
                    expected_changed=expected_changed,
                )
                identity = _assert_identity_pair(
                    preview,
                    expected_status="SAME_PROJECT",
                    expected_mode="DETAILED",
                )
                _emit_progress(
                    f"{tier} v2 Preview",
                    "preview_identity_and_summary_verified",
                    summary=summary,
                    identity=identity,
                    source_census_table_count=int(census[v2_id]["table_count"]),
                    composite_row_count=composite_v2_row_count,
                )
                return {"preview": preview, "summary": summary, "identity": identity}

            v2_partial_state = cast(
                dict[str, Any],
                runner.run("v2-preview", v2_preview_partial_action),
            )
            record_operation_timing("v2_preview", cast(Mapping[str, Any], v2_partial_state["preview"]))
            return {
                "tier": tier,
                "scope": scope,
                "datasets": [
                    {
                        "dataset_id": v1_id,
                        "sha256": v1_file["sha256"],
                        "package_bytes": v1_file["bytes"],
                        "table_count": census[v1_id]["table_count"],
                        "row_count_total": census[v1_id]["row_count_total"],
                        "logics_xml_max_depth": census[v1_id]["logics_xml_max_depth"],
                        "composite_signal_point_row_count": composite_v1_row_count,
                        "preview": v1_summary,
                        "identity": v1_identity,
                        "submit": {
                            "canonical_state_digest": v1_canonical_state_digest,
                            "submission_id": v1_submission_id,
                        },
                        "archive": archive,
                    },
                    {
                        "dataset_id": v2_id,
                        "sha256": v2_file["sha256"],
                        "package_bytes": v2_file["bytes"],
                        "table_count": census[v2_id]["table_count"],
                        "row_count_total": census[v2_id]["row_count_total"],
                        "logics_xml_max_depth": census[v2_id]["logics_xml_max_depth"],
                        "composite_signal_point_row_count": composite_v2_row_count,
                        "preview": v2_partial_state["summary"],
                        "identity": v2_partial_state["identity"],
                    },
                ],
                "initial_repository": initial_repository,
                "compose_image_ids": images,
                "offline_composite_elapsed_seconds": offline_composite["elapsed_seconds"],
                "step_metrics": runner.metrics,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "conclusion": "PASS",
                "empty_initial_commit_id": initial_commit_id,
            }

        repeat_workspace = runner.run(
            "repeat-v1-workspace",
            lambda: _workspace(client),
        )
        repeat_upload = runner.run(
            "repeat-v1-upload",
            lambda: _upload_revision(
                client,
                workspace=cast(Mapping[str, Any], repeat_workspace),
                package=v1_bytes,
                idempotency_key=f"{project_name}-{tier}-repeat-v1-upload",
            ),
        )

        def repeat_v1_preview_action() -> dict[str, Any]:
            preview, manifest = _preview(
                client,
                workspace=cast(Mapping[str, Any], repeat_workspace),
                upload=cast(Mapping[str, Any], repeat_upload),
                baseline_node_id=baseline_node_id,
                baseline_head_version=baseline_head_version,
                idempotency_key=f"{project_name}-{tier}-repeat-v1-preview",
                stage=f"{tier} repeat v1 Preview",
                operation_timeout_seconds=_operation_timeout_seconds(tier, "repeat-v1-preview"),
                heartbeat_monitor=heartbeat_monitor,
                collect_timing=collect_timing,
            )
            summary = _assert_preview_summaries(
                manifest,
                unchanged=True,
            )
            _assert_s3_preview_summary(
                summary,
                dataset_id=v1_id,
                expected_changed=0,
            )
            _emit_progress(
                f"{tier} repeat v1 Preview",
                "preview_summary_verified",
                summary=summary,
                source_census_table_count=int(census[v1_id]["table_count"]),
                composite_row_count=composite_v1_row_count,
            )
            if tuple(v1_keyless_names) != _keyless_fallback_candidates(census[v1_id]):
                raise JourneyFailure("keyless fallback candidates changed during repeated Preview")
            return {
                "preview": preview,
                "manifest": manifest,
                "summary": summary,
                "keyless_fallback_candidates": list(v1_keyless_names),
            }

        repeat_preview_state = cast(
            dict[str, Any],
            runner.run("repeat-v1-preview", repeat_v1_preview_action),
        )
        repeat_preview = cast(dict[str, Any], repeat_preview_state["preview"])
        record_operation_timing("repeat_v1_preview", repeat_preview)
        repeat_summary = cast(dict[str, int], repeat_preview_state["summary"])
        repeat_identity = _assert_identity_pair(
            repeat_preview,
            expected_status="SAME_PROJECT",
            expected_mode="DETAILED",
        )

        repeat_submit = runner.run(
            "repeat-v1-submit",
            lambda: _submit(
                client,
                workspace=cast(Mapping[str, Any], repeat_workspace),
                upload=cast(Mapping[str, Any], repeat_upload),
                preview=repeat_preview,
                baseline_node_id=baseline_node_id,
                baseline_head_version=baseline_head_version,
                idempotency_key=f"{project_name}-{tier}-repeat-v1-submit",
                stage=f"{tier} repeat v1 Submit",
                operation_timeout_seconds=_operation_timeout_seconds(tier, "repeat-v1-submit"),
                expect_no_change=True,
                heartbeat_monitor=heartbeat_monitor,
                collect_timing=collect_timing,
            ),
        )
        record_operation_timing("repeat_v1_submit", cast(Mapping[str, Any], repeat_submit))

        v2_workspace = runner.run("v2-workspace", lambda: _workspace(client))
        v2_upload = runner.run(
            "v2-upload",
            lambda: _upload_revision(
                client,
                workspace=cast(Mapping[str, Any], v2_workspace),
                package=v2_bytes,
                idempotency_key=f"{project_name}-{tier}-v2-upload",
            ),
        )

        def v2_preview_action() -> dict[str, Any]:
            preview, manifest = _preview(
                client,
                workspace=cast(Mapping[str, Any], v2_workspace),
                upload=cast(Mapping[str, Any], v2_upload),
                baseline_node_id=baseline_node_id,
                baseline_head_version=baseline_head_version,
                idempotency_key=f"{project_name}-{tier}-v2-preview",
                stage=f"{tier} v2 Preview",
                operation_timeout_seconds=_operation_timeout_seconds(tier, "v2-preview"),
                heartbeat_monitor=heartbeat_monitor,
                collect_timing=collect_timing,
            )
            summary = _assert_preview_summaries(
                manifest,
                unchanged=False,
            )
            expected_v2_changed = S2B_DATASET_BASELINE[v2_id]["preview_changed"] + int(
                composite_changed
            )
            _assert_s3_preview_summary(
                summary,
                dataset_id=v2_id,
                expected_changed=expected_v2_changed,
            )
            _emit_progress(
                f"{tier} v2 Preview",
                "preview_summary_verified",
                summary=summary,
                source_census_table_count=int(census[v2_id]["table_count"]),
                composite_changed=composite_changed,
                composite_row_count=composite_v2_row_count,
            )
            return {
                "preview": preview,
                "manifest": manifest,
                "summary": summary,
                "keyless_fallback_candidates": list(v2_keyless_names),
            }

        v2_preview_state = cast(
            dict[str, Any],
            runner.run("v2-preview", v2_preview_action),
        )
        v2_preview = cast(dict[str, Any], v2_preview_state["preview"])
        record_operation_timing("v2_preview", v2_preview)
        v2_summary = cast(dict[str, int], v2_preview_state["summary"])
        v2_identity = _assert_identity_pair(
            v2_preview,
            expected_status="SAME_PROJECT",
            expected_mode="DETAILED",
        )

        v2_submission = runner.run(
            "v2-submit",
            lambda: _submit(
                client,
                workspace=cast(Mapping[str, Any], v2_workspace),
                upload=cast(Mapping[str, Any], v2_upload),
                preview=v2_preview,
                baseline_node_id=baseline_node_id,
                baseline_head_version=baseline_head_version,
                idempotency_key=f"{project_name}-{tier}-v2-submit",
                stage=f"{tier} v2 Submit",
                operation_timeout_seconds=_operation_timeout_seconds(tier, "v2-submit"),
                heartbeat_monitor=heartbeat_monitor,
                collect_timing=collect_timing,
            ),
        )
        v2_submission = cast(dict[str, Any], v2_submission)
        record_operation_timing("v2_submit", v2_submission)
        capture_submit_reconciliation(v2_submission, version="v2")
        v2_submission_id = str(v2_submission["submission_id"])
        v2_commit_id = str(v2_submission["repository_commit_id"])
        v2_canonical_state_digest = _canonical_state_digest_from_submission(
            v2_submission,
            stage=f"{tier} v2 Submit",
        )
        def v2_repository_read_action() -> dict[str, Any]:
            repository = _pseudo_counts_from_http(
                base_url=repository_url,
                repository_id=repository_id,
                commit_id=v2_commit_id,
                expected_tables=v2_ordered,
                expected_row_counts=v2_ordered_row_counts,
            )
            _assert_s3_catalog_summary(
                repository,
                dataset_id=v2_id,
                composite_row_count=composite_v2_row_count,
            )
            if repository["pseudo_rows_total"] != EXPECTED_PSEUDO_TOTALS[v2_id]:
                raise JourneyFailure(f"{v2_id}: committed pseudo row count differs from census")
            return repository

        v2_repository = cast(
            dict[str, Any],
            runner.run("v2-repository-read", v2_repository_read_action),
        )
        if (
            tier == "t4"
            and dc32_metrics is not None
            and dc32_scratch_root is not None
        ):
            v2_commit_read = _measure_repository_commit_rows(
                base_url=repository_url,
                repository_id=repository_id,
                commit_id=v2_commit_id,
                scenario="t4_history_v2_commit",
                scratch_root=dc32_scratch_root,
            )
            dc32_metrics.append(
                {
                    "kind": "repository_history_read",
                    "tier": tier,
                    "measurement": v2_commit_read,
                }
            )
        def approve_v2_action() -> dict[str, bool]:
            _approve(client, v2_submission_id, f"{project_name}-{tier}-v2-review")
            return {"approved": True}

        runner.run("v2-approve", approve_v2_action)

        def history_action() -> dict[str, Any]:
            result, operation_id = _history_compare(
                client,
                tier=tier,
                v1_submission_id=v1_submission_id,
                v1_commit_id=v1_commit_id,
                v2_submission_id=v2_submission_id,
                v2_commit_id=v2_commit_id,
                idempotency_key=f"{project_name}-{tier}-history-compare",
                operation_timeout_seconds=_operation_timeout_seconds(tier, "history"),
                heartbeat_monitor=heartbeat_monitor,
                collect_timing=collect_timing,
            )
            _history_surface_ref(cast(Mapping[str, Any], result["bundle"]))
            return {"operation_id": operation_id, "result": result}

        history_state = cast(
            dict[str, Any],
            runner.run("history", history_action),
        )
    record_operation_timing("history", cast(Mapping[str, Any], history_state["result"]))

    history_result = cast(dict[str, Any], history_state["result"])
    history_pair = cast(dict[str, Any], history_result["pair"])
    api_record_count = int(history_pair["record_count"])
    if api_record_count < 0:
        raise JourneyFailure("History HTTP record_count must be non-negative")
    composite_record_count = int(composite_counts["history_record_count"])
    _assert_s3_history_count(
        tier=tier,
        actual_record_count=api_record_count,
        composite_record_count=composite_record_count,
    )
    repeat_keyless_names = v1_keyless_names
    return {
        "tier": tier,
        "datasets": [
            {
                "dataset_id": v1_id,
                "sha256": v1_file["sha256"],
                "package_bytes": v1_file["bytes"],
                "table_count": census[v1_id]["table_count"],
                "row_count_total": census[v1_id]["row_count_total"],
                "logics_xml_max_depth": census[v1_id]["logics_xml_max_depth"],
                "composite_signal_point_row_count": composite_v1_row_count,
                "canonical_state_digest": v1_canonical_state_digest,
                "storage_column_type_counts": census[v1_id]["storage_column_type_counts"],
                "repository": v1_repository,
                "preview": v1_summary,
                "identity": v1_identity,
                "keyless_fallback_tables": {
                    "count": len(v1_keyless_names),
                    "names": list(v1_keyless_names),
                    "source": "S1 census effective_key_scan.unresolved_tables",
                },
            },
            {
                "dataset_id": v2_id,
                "sha256": v2_file["sha256"],
                "package_bytes": v2_file["bytes"],
                "table_count": census[v2_id]["table_count"],
                "row_count_total": census[v2_id]["row_count_total"],
                "logics_xml_max_depth": census[v2_id]["logics_xml_max_depth"],
                "composite_signal_point_row_count": composite_v2_row_count,
                "canonical_state_digest": v2_canonical_state_digest,
                "storage_column_type_counts": census[v2_id]["storage_column_type_counts"],
                "repository": v2_repository,
                "preview": v2_summary,
                "identity": v2_identity,
                "keyless_fallback_tables": {
                    "count": len(v2_keyless_names),
                    "names": list(v2_keyless_names),
                    "source": "S1 census effective_key_scan.unresolved_tables",
                },
            },
        ],
        "repeat_v1": {
            "preview": repeat_summary,
            "identity": repeat_identity,
            "submit": repeat_submit,
            "keyless_fallback_candidates_unchanged": {
                "count": len(repeat_keyless_names),
                "names": list(repeat_keyless_names),
                "evidence": "all-table preview summary has changed_table_count=0",
            },
        },
        "history": {
            "record_count": api_record_count,
            "s2b_record_count": S2B_HISTORY_RECORD_COUNTS[tier],
            "composite_record_count": composite_record_count,
            "composite_signal_point": composite_counts,
            "bundle_digest": history_result.get("bundle_digest"),
            "surface_digest": history_pair.get("surface_digest"),
            "record_kind_counts": None,
            "detail_availability": (
                "public History HTTP exposes pair record_count and digests; "
                "bundle artifacts are references without public content retrieval"
            ),
        },
        "compose_image_ids": images,
        "initial_repository": initial_repository,
        "offline_composite_elapsed_seconds": offline_composite["elapsed_seconds"],
        "step_metrics": runner.metrics,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "conclusion": "PASS",
        "empty_initial_commit_id": initial_commit_id,
    }


def _run_cross_project(
    *,
    root: Path,
    datasets: Mapping[str, dict[str, Any]],
    census: Mapping[str, dict[str, Any]],
    env: dict[str, str],
    project_name: str,
    repository_id: str,
    initial_commit_id: str,
    heartbeat_monitor: WorkerHeartbeatMonitor | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    source_id, target_id = "rd-t1-a-v1", "rd-t2-b-v1"
    source_package, source_file = _dataset_package(root, datasets[source_id])
    target_package, target_file = _dataset_package(root, datasets[target_id])
    for dataset_id in (source_id, target_id):
        if int(census[dataset_id]["ordered_projection"]["pseudo_rows_total"]) != EXPECTED_PSEUDO_TOTALS[dataset_id]:
            raise JourneyFailure(f"{dataset_id}: census pseudo total differs from the accepted baseline")

    images = compose_image_ids(env)
    repository_url = _repository_service_url(env)
    initial_repository = _assert_initial_repository_commit_empty(
        base_url=repository_url,
        repository_id=repository_id,
        commit_id=initial_commit_id,
    )
    runner = JourneyStepRunner(
        tier="cross-project",
        env=env,
        state={},
        from_step=None,
        state_path=None,
    )

    with httpx.Client(
        base_url=BACKEND_URL,
        headers=compose_auth_headers(),
        timeout=600.0,
    ) as client:
        source_workspace = runner.run(
            "cross-source-workspace",
            lambda: _workspace(client),
        )
        source_upload = runner.run(
            "cross-source-upload",
            lambda: _upload_revision(
                client,
                workspace=cast(Mapping[str, Any], source_workspace),
                package=source_package,
                idempotency_key=f"{project_name}-cross-source-upload",
            ),
        )

        def source_preview_action() -> dict[str, Any]:
            preview, manifest = _preview(
                client,
                workspace=cast(Mapping[str, Any], source_workspace),
                upload=cast(Mapping[str, Any], source_upload),
                baseline_node_id=BASELINE_NODE_ID,
                baseline_head_version=0,
                idempotency_key=f"{project_name}-cross-source-preview",
                stage="cross-project source v1 Preview",
                operation_timeout_seconds=_operation_timeout_seconds("t1", "v1-preview"),
                heartbeat_monitor=heartbeat_monitor,
            )
            summary = _assert_preview_summaries(manifest, unchanged=False)
            _assert_s3_preview_summary(
                summary,
                dataset_id=source_id,
                expected_changed=S2B_DATASET_BASELINE[source_id]["preview_table_count"] + 1,
            )
            identity = _assert_identity_pair(
                preview,
                expected_status="NOT_APPLICABLE",
                expected_mode="DETAILED",
            )
            return {"preview": preview, "summary": summary, "identity": identity}

        source_preview_state = cast(
            dict[str, Any],
            runner.run("cross-source-preview", source_preview_action),
        )
        source_preview = cast(dict[str, Any], source_preview_state["preview"])
        source_submission = runner.run(
            "cross-source-submit",
            lambda: _submit(
                client,
                workspace=cast(Mapping[str, Any], source_workspace),
                upload=cast(Mapping[str, Any], source_upload),
                preview=source_preview,
                baseline_node_id=BASELINE_NODE_ID,
                baseline_head_version=0,
                idempotency_key=f"{project_name}-cross-source-submit",
                stage="cross-project source v1 Submit",
                operation_timeout_seconds=_operation_timeout_seconds("t1", "v1-submit"),
                heartbeat_monitor=heartbeat_monitor,
            ),
        )
        source_submission = cast(dict[str, Any], source_submission)
        source_submission_id = str(source_submission["submission_id"])
        source_commit_id = str(source_submission["repository_commit_id"])
        source_digest = _canonical_state_digest_from_submission(
            source_submission,
            stage="cross-project source v1 Submit",
        )
        runner.run(
            "cross-source-approve",
            lambda: _approve(
                client,
                source_submission_id,
                f"{project_name}-cross-source-review",
            ),
        )
        source_archive = cast(
            dict[str, Any],
            runner.run(
                "cross-source-archive",
                lambda: _archive(
                    client,
                    source_submission_id,
                    f"{project_name}-cross-source",
                ),
            ),
        )
        if source_archive.get("baseline_commit_id") != source_commit_id:
            raise JourneyFailure("cross-project source Archive did not promote its Repository commit")
        baseline_node_id = str(source_archive["baseline_node_id"])
        baseline_head_version = int(source_archive["baseline_head_version"])

        target_workspace = runner.run(
            "cross-replacement-workspace",
            lambda: _workspace(client),
        )
        target_upload = runner.run(
            "cross-replacement-upload",
            lambda: _upload_revision(
                client,
                workspace=cast(Mapping[str, Any], target_workspace),
                package=target_package,
                idempotency_key=f"{project_name}-cross-replacement-upload",
            ),
        )

        def target_preview_action() -> dict[str, Any]:
            preview, manifest = _preview(
                client,
                workspace=cast(Mapping[str, Any], target_workspace),
                upload=cast(Mapping[str, Any], target_upload),
                baseline_node_id=baseline_node_id,
                baseline_head_version=baseline_head_version,
                idempotency_key=f"{project_name}-cross-replacement-preview",
                stage="cross-project replacement Preview",
                operation_timeout_seconds=_operation_timeout_seconds("t2", "v1-preview"),
                heartbeat_monitor=heartbeat_monitor,
            )
            summary = _assert_preview_summaries(manifest, unchanged=False)
            identity = _assert_identity_pair(
                preview,
                expected_status="DIFFERENT_PROJECT",
                expected_mode="DATASET_REPLACEMENT",
            )
            _emit_progress(
                "cross-project replacement Preview",
                "preview_identity_and_summary_verified",
                summary=summary,
                identity=identity,
            )
            return {"preview": preview, "summary": summary, "identity": identity}

        target_preview_state = cast(
            dict[str, Any],
            runner.run("cross-replacement-preview", target_preview_action),
        )
        target_preview = cast(dict[str, Any], target_preview_state["preview"])
        target_identity = cast(dict[str, str], target_preview_state["identity"])
        target_submission = runner.run(
            "cross-replacement-submit",
            lambda: _submit(
                client,
                workspace=cast(Mapping[str, Any], target_workspace),
                upload=cast(Mapping[str, Any], target_upload),
                preview=target_preview,
                baseline_node_id=baseline_node_id,
                baseline_head_version=baseline_head_version,
                idempotency_key=f"{project_name}-cross-replacement-submit",
                stage="cross-project replacement Submit",
                operation_timeout_seconds=_operation_timeout_seconds("t2", "v1-submit"),
                identity_confirmations=(
                    {
                        "action": "ACCEPT_DATASET_REPLACEMENT",
                        "assessment_set_digest": target_identity["assessment_set_digest"],
                        "reason": (
                            "cross-project dataset replacement reviewed\n"
                            "approved for the dedicated replacement journey"
                        ),
                    },
                ),
                heartbeat_monitor=heartbeat_monitor,
            ),
        )
        target_submission = cast(dict[str, Any], target_submission)
        target_submission_id = str(target_submission["submission_id"])
        target_commit_id = str(target_submission["repository_commit_id"])
        target_digest = _canonical_state_digest_from_submission(
            target_submission,
            stage="cross-project replacement Submit",
        )
        runner.run(
            "cross-replacement-approve",
            lambda: _approve(
                client,
                target_submission_id,
                f"{project_name}-cross-replacement-review",
            ),
        )
        target_archive = cast(
            dict[str, Any],
            runner.run(
                "cross-replacement-archive",
                lambda: _archive(
                    client,
                    target_submission_id,
                    f"{project_name}-cross-replacement",
                    identity_exception_reason=(
                        "reviewed project identity exception\n"
                        "acknowledged before cross-project archive"
                    ),
                ),
            ),
        )
        if target_archive.get("baseline_commit_id") != target_commit_id:
            raise JourneyFailure("cross-project replacement Archive did not promote its Repository commit")

    return {
        "scope": "cross-project-t1-to-t2",
        "source": {
            "dataset_id": source_id,
            "sha256": source_file["sha256"],
            "package_bytes": source_file["bytes"],
            "table_count": census[source_id]["table_count"],
            "row_count_total": census[source_id]["row_count_total"],
            "preview": source_preview_state["summary"],
            "identity": source_preview_state["identity"],
            "canonical_state_digest": source_digest,
            "archive": source_archive,
        },
        "replacement": {
            "dataset_id": target_id,
            "sha256": target_file["sha256"],
            "package_bytes": target_file["bytes"],
            "table_count": census[target_id]["table_count"],
            "row_count_total": census[target_id]["row_count_total"],
            "preview": target_preview_state["summary"],
            "identity": target_identity,
            "canonical_state_digest": target_digest,
            "archive": target_archive,
        },
        "initial_repository": initial_repository,
        "compose_image_ids": images,
        "step_metrics": runner.metrics,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "conclusion": "PASS",
        "empty_initial_commit_id": initial_commit_id,
    }


def _persist_debug_state(path: Path, state: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    temporary_path.replace(path)


def _load_debug_state(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JourneyFailure("debug checkpoint could not be read") from exc
    if not isinstance(payload, dict):
        raise JourneyFailure("debug checkpoint is not an object")
    return cast(dict[str, Any], payload)


def _resume_stack(env: dict[str, str], state: Mapping[str, Any]) -> tuple[str, str]:
    stack = state.get("_stack")
    if not isinstance(stack, dict):
        raise JourneyFailure("debug checkpoint has no stack identity")
    repository_id = stack.get("repository_id")
    initial_commit_id = stack.get("initial_commit_id")
    if type(repository_id) is not str or type(initial_commit_id) is not str:
        raise JourneyFailure("debug checkpoint has an invalid stack identity")
    wait_repository_service_ready(env)
    wait_http_ok(f"{BACKEND_URL}/readyz")
    worker_ready(env)
    return repository_id, initial_commit_id


def _validate_project_name(project_name: str) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", project_name):
        raise JourneyFailure("Compose project name must use 1..63 lowercase letters, digits, '_' or '-' ")


def _save_compose_logs_before_teardown(env: dict[str, str], *, tier: str) -> Path:
    configured_directory = os.environ.get("GATEWAY_REAL_DUMP_LOG_DIR")
    log_directory = (
        Path(configured_directory)
        if configured_directory
        else Path(tempfile.gettempdir()) / "gdds-real-dump-compose-logs"
    )
    if not log_directory.is_absolute():
        raise JourneyFailure("real-dump Compose log directory must be absolute")
    log_directory = log_directory.resolve()
    if log_directory.is_relative_to(_repo_root().resolve()):
        raise JourneyFailure("real-dump Compose logs must be outside the worktree")
    log_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    log_path = log_directory / f"real-dump-{tier}-{timestamp}.compose.log"
    result = run_compose(env, "logs", "--no-color", "--timestamps", timeout=180.0)
    log_path.write_text(
        f"compose_logs_exit_code={result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}\n",
        encoding="utf-8",
    )
    _emit_progress(
        tier,
        "compose_logs_saved",
        log_file=log_path.name,
        compose_logs_exit_code=result.returncode,
    )
    return log_path


def run_journey(
    *,
    tier_filter: str | None = None,
    scope: str = "full",
    cross_project: bool = False,
    from_step: str | None = None,
    keep_stack: bool = False,
    requested_project_name: str | None = None,
    dc32_output: Path | None = None,
    debug_t1_submit_probe: bool = False,
) -> dict[str, Any]:
    root = _real_dump_root()
    datasets, census = _read_metadata(root)
    current_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_repo_root(),
        check=True,
        capture_output=True,
        text=True,
        timeout=10.0,
    ).stdout.strip()
    if keep_stack and tier_filter is None:
        raise JourneyFailure("--keep-stack requires --tier")
    if from_step is not None and not keep_stack:
        raise JourneyFailure("--from-step requires --keep-stack")
    if from_step is not None and requested_project_name is None:
        raise JourneyFailure("--from-step requires --project-name")
    if requested_project_name is not None and not keep_stack:
        raise JourneyFailure("--project-name is only used with --keep-stack")
    if dc32_output is not None and (
        tier_filter is not None
        or scope != "full"
        or cross_project
        or from_step is not None
        or keep_stack
    ):
        raise JourneyFailure("--dc32-output requires the complete fresh same-project journey")
    if scope not in {"full", "t4-identity", "t4-v1-submit"}:
        raise JourneyFailure("requested real-data scope is unknown")
    if scope == "t4-identity" and (tier_filter != "t4" or cross_project):
        raise JourneyFailure("--scope t4-identity requires --tier t4")
    if scope == "t4-v1-submit" and (tier_filter != "t4" or cross_project or from_step is not None):
        raise JourneyFailure("--scope t4-v1-submit requires a fresh t4 journey")
    if cross_project and (tier_filter is not None or keep_stack or from_step is not None):
        raise JourneyFailure("--cross-project cannot be combined with tier or debug controls")
    if debug_t1_submit_probe and (
        tier_filter != "t1"
        or scope != "full"
        or cross_project
        or from_step is not None
        or keep_stack
        or dc32_output is not None
    ):
        raise JourneyFailure("--debug-submit-probe-t1 requires a fresh full --tier t1 journey")
    if requested_project_name is None:
        project_name = f"s2b-realdata-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    else:
        project_name = requested_project_name
    _validate_project_name(project_name)

    dc32_output_path: Path | None = None
    dc32_metrics: list[dict[str, Any]] | None = None
    dc32_scratch_root: Path | None = None
    dc32_session_root: Path | None = None
    debug_submit_probe_root: Path | None = None
    debug_submit_probe_metrics: list[dict[str, Any]] | None = None
    debug_submit_probe_output: Path | None = None
    if dc32_output is not None:
        real_dump_runs = (root / "runs").resolve()
        dc32_output_path = dc32_output.resolve()
        if not dc32_output_path.is_relative_to(real_dump_runs):
            raise JourneyFailure("DC32 output must be stored under GATEWAY_REAL_DUMP_ROOT/runs")
        real_dump_runs.mkdir(mode=0o700, parents=True, exist_ok=True)
        real_dump_runs.chmod(0o700)
        dc32_metrics = []
        scratch_parent = Path(os.environ.get("TMPDIR", tempfile.gettempdir())).resolve()
        scratch_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        dc32_scratch_root = Path(
            tempfile.mkdtemp(prefix=f"{project_name}-dc32-", dir=scratch_parent)
        )
        dc32_scratch_root.chmod(0o700)
        dc32_session_root = real_dump_runs / f"{project_name}-submit-facts"
        dc32_session_root.mkdir(mode=0o700, exist_ok=False)
        dc32_session_root.chmod(0o700)
    if debug_t1_submit_probe:
        real_dump_runs = (root / "runs").resolve()
        real_dump_runs.mkdir(mode=0o700, parents=True, exist_ok=True)
        real_dump_runs.chmod(0o700)
        debug_submit_probe_root = real_dump_runs / f"{project_name}-debug-submit-probe"
        debug_submit_probe_root.mkdir(mode=0o700, exist_ok=False)
        debug_submit_probe_root.chmod(0o700)
        debug_submit_probe_metrics = []
        debug_submit_probe_output = debug_submit_probe_root / "t1-submit-probe.json"

    selected_tiers = (
        [("t1", EXPECTED_PAIRINGS["rd-t1-a"])]
        if cross_project
        else [
            (key.split("-")[1], pair)
            for key, pair in EXPECTED_PAIRINGS.items()
            if tier_filter is None or key.split("-")[1] == tier_filter
        ]
    )
    if not selected_tiers:
        raise JourneyFailure("requested real-data tier is unknown")

    original_prebuilt = os.environ.get("GATEWAY_COMPOSE_GATE_PREBUILT")
    os.environ.pop("GATEWAY_COMPOSE_GATE_PREBUILT", None)
    results: list[dict[str, Any]] = []
    state_paths: list[str] = []
    stack_start_seconds: dict[str, float] = {}
    project_root = root / "runs" / project_name
    if keep_stack:
        project_root.mkdir(parents=True, exist_ok=True)

    try:
        with (
            contextlib.nullcontext(project_root)
            if keep_stack
            else tempfile.TemporaryDirectory(prefix="gdds-s2b-realdata-")
        ) as temporary_root:
            base = Path(temporary_root) if not keep_stack else cast(Path, temporary_root)
            if from_step is not None:
                os.environ["GATEWAY_COMPOSE_GATE_PREBUILT"] = "1"
            else:
                first_tier = selected_tiers[0][0]
                first_secret_root = base / f"{first_tier}-secrets"
                first_env = _compose_environment(first_secret_root, project_name)
                if subprocess.run(
                    ["docker", "image", "inspect", REPOSITORY_SERVICE_IMAGE],
                    check=False,
                    capture_output=True,
                    timeout=30.0,
                ).returncode != 0:
                    raise JourneyFailure("the gate Repository Service image is missing")
                build_compose_stack_images(first_env)
                os.environ["GATEWAY_COMPOSE_GATE_PREBUILT"] = "1"

            for tier, (v1_id, v2_id) in selected_tiers:
                offline_composite = (
                    None
                    if cross_project
                    else _offline_composite_comparison(
                        tier=tier,
                        v1_id=v1_id,
                        v2_id=v2_id,
                        root=root,
                        datasets=datasets,
                    )
                )
                state_path = base / f"{tier}.state.json" if keep_stack else None
                if state_path is not None:
                    state_paths.append(str(state_path))
                if from_step is not None:
                    if state_path is None:
                        raise JourneyFailure("debug checkpoint path is unavailable")
                    step_state = _load_debug_state(state_path)
                else:
                    if state_path is not None and state_path.exists():
                        raise JourneyFailure(
                            "debug checkpoint already exists; choose a new --project-name "
                            "or resume with --from-step"
                        )
                    step_state = {}

                secret_root = base / f"{tier}-secrets"
                env = _compose_environment(
                    secret_root,
                    project_name,
                    write_secrets=from_step is None,
                )
                acquire_compose_gate_lock()
                stack_cleaned = False
                try:
                    try:
                        stack_started = time.monotonic()
                        if from_step is None:
                            repository_id, initial_commit_id = start_three_container_stack(
                                env,
                                secret_root,
                            )
                            step_state["_stack"] = {
                                "repository_id": repository_id,
                                "initial_commit_id": initial_commit_id,
                                "project_name": project_name,
                                "tier": tier,
                                "head": current_head,
                            }
                            if state_path is not None:
                                _persist_debug_state(state_path, step_state)
                        else:
                            repository_id, initial_commit_id = _resume_stack(env, step_state)
                        stack_start_seconds[tier] = round(time.monotonic() - stack_started, 3)
                        with WorkerHeartbeatMonitor(
                            env=env,
                            repository_id=repository_id,
                            repository_url=_repository_service_url(env),
                        ) as heartbeat_monitor:
                            if cross_project:
                                results.append(
                                    _run_cross_project(
                                        root=root,
                                        datasets=datasets,
                                        census=census,
                                        env=env,
                                        project_name=project_name,
                                        repository_id=repository_id,
                                        initial_commit_id=initial_commit_id,
                                        heartbeat_monitor=heartbeat_monitor,
                                    )
                                )
                            else:
                                if offline_composite is None:
                                    raise JourneyFailure(
                                        "same-tier composite comparison was not prepared"
                                    )
                                results.append(
                                    _run_tier(
                                        tier=tier,
                                        v1_id=v1_id,
                                        v2_id=v2_id,
                                        root=root,
                                        datasets=datasets,
                                        census=census,
                                        env=env,
                                        project_name=project_name,
                                        repository_id=repository_id,
                                        initial_commit_id=initial_commit_id,
                                        step_state=step_state,
                                        from_step=from_step,
                                        state_path=state_path,
                                        offline_composite=offline_composite,
                                        heartbeat_monitor=heartbeat_monitor,
                                        scope=scope,
                                        dc32_metrics=dc32_metrics,
                                        dc32_scratch_root=dc32_scratch_root,
                                        dc32_session_root=dc32_session_root,
                                        debug_t1_submit_probe=debug_t1_submit_probe,
                                        debug_submit_probe_root=debug_submit_probe_root,
                                        debug_submit_probe_metrics=debug_submit_probe_metrics,
                                        collect_timing=(
                                            dc32_output_path is not None or debug_t1_submit_probe
                                        ),
                                    )
                                )
                    except BaseException as error:
                        try:
                            _save_compose_logs_before_teardown(env, tier=tier)
                        except BaseException as log_error:
                            _emit_progress(
                                tier,
                                "compose_logs_save_failed",
                                diagnostic=type(log_error).__name__,
                            )
                        if dc32_output_path is not None and dc32_metrics is not None:
                            _write_private_dc32_json(
                                dc32_output_path,
                                {
                                    "schema_version": "s5-dc32-real-journey/v1",
                                    "head": current_head,
                                    "status": "FAILED",
                                    "failure_type": type(error).__name__,
                                    "measurements": dc32_metrics,
                                },
                            )
                        if (
                            debug_submit_probe_output is not None
                            and debug_submit_probe_metrics is not None
                        ):
                            _write_private_dc32_json(
                                debug_submit_probe_output,
                                {
                                    "schema_version": "s5-debug-submit-probe-t1/v1",
                                    "head": current_head,
                                    "status": "FAILED",
                                    "failure_type": type(error).__name__,
                                    "measurements": debug_submit_probe_metrics,
                                },
                            )
                        if isinstance(error, WorkerStalledFailure):
                            cleanup_compose_project_artifacts(env)
                            stack_cleaned = True
                        raise
                finally:
                    if not stack_cleaned:
                        if keep_stack:
                            release_compose_gate_lock()
                        else:
                            cleanup_compose_project_artifacts(env)
    finally:
        if original_prebuilt is None:
            os.environ.pop("GATEWAY_COMPOSE_GATE_PREBUILT", None)
        else:
            os.environ["GATEWAY_COMPOSE_GATE_PREBUILT"] = original_prebuilt
        if dc32_scratch_root is not None:
            shutil.rmtree(dc32_scratch_root, ignore_errors=True)

    journey_result: dict[str, Any] = {
        "head": current_head,
        "datasets": results,
        "stack_start_seconds": stack_start_seconds,
        "debug_project_name": project_name if keep_stack else None,
        "debug_state_files": state_paths if keep_stack else [],
        "conclusion": "PASS",
    }
    if dc32_output_path is not None and dc32_metrics is not None:
        _write_private_dc32_json(
            dc32_output_path,
            {
                "schema_version": "s5-dc32-real-journey/v1",
                "head": current_head,
                "status": "PASS",
                "measurement_count": len(dc32_metrics),
                "measurements": dc32_metrics,
            },
        )
    if debug_submit_probe_output is not None and debug_submit_probe_metrics is not None:
        _write_private_dc32_json(
            debug_submit_probe_output,
            {
                "schema_version": "s5-debug-submit-probe-t1/v1",
                "head": current_head,
                "status": "PASS",
                "measurement_count": len(debug_submit_probe_metrics),
                "measurements": debug_submit_probe_metrics,
            },
        )
        journey_result["debug_submit_probe"] = {
            "status": "PASS",
            "measurements": debug_submit_probe_metrics,
            "output": str(debug_submit_probe_output),
        }
    return journey_result


def validate_inputs() -> dict[str, Any]:
    root = _real_dump_root()
    datasets, census = _read_metadata(root)
    validated = []
    for dataset_id in sorted(datasets):
        _package, file_info = _dataset_package(root, datasets[dataset_id])
        ordered = _ordered_tables(census[dataset_id])
        validated.append(
            {
                "dataset_id": dataset_id,
                "sha256": file_info["sha256"],
                "package_bytes": file_info["bytes"],
                "table_count": census[dataset_id]["table_count"],
                "row_count_total": census[dataset_id]["row_count_total"],
                "pseudo_rows_total": sum(ordered.values()),
                "keyless_fallback_candidates": list(
                    _keyless_fallback_candidates(census[dataset_id])
                ),
            }
        )
    return {"datasets": validated, "conclusion": "INPUTS_VALID"}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate-inputs",
        action="store_true",
        help="check package hashes and the G8a census without starting containers",
    )
    parser.add_argument("--tier", choices=("t1", "t2", "t3", "t4"))
    parser.add_argument(
        "--scope",
        choices=("full", "t4-identity", "t4-v1-submit"),
        default="full",
    )
    parser.add_argument(
        "--cross-project",
        action="store_true",
        help="run the S4 t1 v1 to t2 v1 identity replacement journey",
    )
    parser.add_argument("--from-step", choices=JOURNEY_STEP_IDS)
    parser.add_argument("--keep-stack", action="store_true")
    parser.add_argument("--project-name")
    parser.add_argument(
        "--dc32-output",
        type=Path,
        help="write private S5/DC32 timing and Repository Arrow-read detail under runs/",
    )
    parser.add_argument(
        "--debug-submit-probe-t1",
        action="store_true",
        help="also capture v1/v2 Submit reconciliation facts during a fresh t1 debug journey",
    )
    arguments = parser.parse_args(argv)
    try:
        if arguments.validate_inputs and any(
            (
                arguments.tier is not None,
                arguments.scope != "full",
                arguments.cross_project,
                arguments.from_step is not None,
                arguments.keep_stack,
                arguments.project_name is not None,
                arguments.dc32_output is not None,
                arguments.debug_submit_probe_t1,
            )
        ):
            raise JourneyFailure("--validate-inputs cannot be combined with journey controls")
        result = (
            validate_inputs()
            if arguments.validate_inputs
            else run_journey(
                tier_filter=arguments.tier,
                scope=arguments.scope,
                cross_project=arguments.cross_project,
                from_step=arguments.from_step,
                keep_stack=arguments.keep_stack,
                requested_project_name=arguments.project_name,
                dc32_output=arguments.dc32_output,
                debug_t1_submit_probe=arguments.debug_submit_probe_t1,
            )
        )
        print(json.dumps(result, sort_keys=True))
    except WorkerStalledFailure as exc:
        print(
            json.dumps(
                {
                    "conclusion": "FAILED",
                    "reason": "worker_stalled",
                    "stage": exc.stage,
                    "operation_id": exc.operation_id,
                    "diagnostics": str(exc.diagnostics) if exc.diagnostics is not None else None,
                    "diagnostic_error": exc.diagnostic_error,
                },
                sort_keys=True,
            )
        )
        return 1
    except JourneyFailure as exc:
        print(json.dumps({"conclusion": "FAILED", "reason": str(exc)}))
        return 1
    except (OSError, subprocess.SubprocessError, httpx.HTTPError) as exc:
        print(json.dumps({"conclusion": "FAILED", "reason": type(exc).__name__}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
