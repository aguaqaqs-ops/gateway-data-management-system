"""Controlled Dolt child-process supervision boundary."""

from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Callable, Iterator, Literal, Self

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.settings import RepositoryServiceSettings

StreamCancellationCheck = Callable[[], bool]


def evaluate_stream_cancellation(cancellation: StreamCancellationCheck | None) -> bool:
    if cancellation is None:
        return False
    try:
        return cancellation()
    except Exception:
        return True


class ProcessBoundaryError(RuntimeError):
    """Raised when a Dolt process violates the private runner boundary."""


class ProcessStreamCancelledError(ProcessBoundaryError):
    """Raised when a Dolt row stream is cancelled before completion."""


def process_rss_kib(pid: int) -> int:
    try:
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return 0
    for line in status.splitlines():
        if line.startswith("VmRSS:"):
            fields = line.split()
            if len(fields) >= 2:
                return int(fields[1])
    return 0


def process_rss_breakdown_kib(pid: int) -> dict[str, int]:
    """Read the anonymous/file RSS components exposed by procfs."""

    try:
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return {"rss_anon_kib": 0, "rss_file_kib": 0}
    values = {"RssAnon:": "rss_anon_kib", "RssFile:": "rss_file_kib"}
    result = {key: 0 for key in values.values()}
    for line in status.splitlines():
        field, _, value = line.partition(":")
        output_key = values.get(f"{field}:")
        if output_key is None:
            continue
        parts = value.split()
        if parts:
            try:
                result[output_key] = int(parts[0])
            except ValueError:
                continue
    return result


def process_tree_pids(pid: int) -> tuple[int, ...]:
    """Return a best-effort snapshot of ``pid`` and all descendants."""

    pending = [pid]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        children_path = Path(f"/proc/{current}/task/{current}/children")
        try:
            children = [int(value) for value in children_path.read_text().split()]
        except (FileNotFoundError, OSError, ValueError):
            children = []
        pending.extend(children)
    return tuple(sorted(seen))


def process_tree_rss_kib(pid: int) -> int:
    return sum(process_rss_kib(child) for child in process_tree_pids(pid))


def process_tree_rss_breakdown_kib(pid: int) -> dict[str, int]:
    result = {"rss_anon_kib": 0, "rss_file_kib": 0}
    for child in process_tree_pids(pid):
        measurement = process_rss_breakdown_kib(child)
        for key in result:
            result[key] += measurement[key]
    return result


def cgroup_scope_identity(root: Path) -> str:
    """Return a stable opaque identity without publishing a host cgroup path."""

    return "sha256:" + hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CgroupMemoryMeasurement:
    current_bytes: int | None
    peak_bytes: int | None
    baseline_peak_bytes: int | None
    reset_current_baseline_bytes: int | None
    anon_bytes: int | None
    file_bytes: int | None
    baseline_anon_bytes: int | None
    baseline_file_bytes: int | None
    anon_delta_bytes: int | None
    file_delta_bytes: int | None
    scope_identity: str
    available: bool
    per_workflow: bool
    memory_limit_bytes: int | None = None
    effective_memory_limit_bytes: int | None = None


class CgroupMemoryTracker:
    """Read cgroup v2 memory without pretending cumulative peaks are per-run."""

    def __init__(self, root: Path = Path("/sys/fs/cgroup")) -> None:
        self.root = root
        self.current_path = root / "memory.current"
        self.peak_path = root / "memory.peak"
        self.baseline_peak = self._read(self.peak_path)
        self._peak_fd: int | None = None
        self.reset_baseline = self._reset_peak()
        self.reset_current_baseline = self._read(self.current_path)
        self.reset_stat = self._read_stat(self.root / "memory.stat")
        self.scope_identity = cgroup_scope_identity(self.root)
        self.per_workflow = self.reset_baseline is not None
        self.memory_limit_bytes = self._read(self.root / "memory.max")
        self.effective_memory_limit_bytes = self._effective_memory_limit()

    def _effective_memory_limit(self) -> int | None:
        limits: list[int] = []
        current = self.root
        while current != current.parent:
            if not (current / "memory.max").is_file():
                break
            value = self._read(current / "memory.max")
            if value is not None:
                limits.append(value)
            current = current.parent
        return min(limits) if limits else None

    @staticmethod
    def _read_stat(path: Path) -> dict[str, int]:
        try:
            lines = path.read_text(encoding="ascii").splitlines()
        except (FileNotFoundError, OSError):
            return {}
        result: dict[str, int] = {}
        for line in lines:
            key, _, value = line.partition(" ")
            try:
                result[key] = int(value.strip())
            except ValueError:
                continue
        return result

    @staticmethod
    def _read(path: Path) -> int | None:
        try:
            value = path.read_text(encoding="utf-8").strip()
        except (FileNotFoundError, OSError, ValueError):
            return None
        if value == "max":
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def _read_fd(self, descriptor: int) -> int | None:
        try:
            os.lseek(descriptor, 0, os.SEEK_SET)
            value = os.read(descriptor, 128).decode("ascii", errors="strict").strip()
            if value == "max":
                return None
            return int(value)
        except (OSError, ValueError, UnicodeError):
            return None

    def _reset_peak(self) -> int | None:
        try:
            descriptor = os.open(
                self.peak_path,
                os.O_RDWR | getattr(os, "O_CLOEXEC", 0),
            )
            os.write(descriptor, b"0")
            baseline = self._read_fd(descriptor)
            if baseline is None:
                os.close(descriptor)
                return None
            self._peak_fd = descriptor
            return baseline
        except (FileNotFoundError, OSError, PermissionError, ValueError, UnicodeError):
            if "descriptor" in locals():
                os.close(descriptor)
            return None

    def close(self) -> None:
        if self._peak_fd is not None:
            os.close(self._peak_fd)
            self._peak_fd = None

    def __enter__(self) -> "CgroupMemoryTracker":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def snapshot(self) -> CgroupMemoryMeasurement:
        current = self._read(self.current_path)
        peak = self._read_fd(self._peak_fd) if self._peak_fd is not None else None
        stat = self._read_stat(self.root / "memory.stat")
        anon = stat.get("anon")
        file_bytes = stat.get("file")
        baseline_anon = self.reset_stat.get("anon")
        baseline_file = self.reset_stat.get("file")
        return CgroupMemoryMeasurement(
            current_bytes=current,
            peak_bytes=peak,
            baseline_peak_bytes=self.reset_baseline,
            reset_current_baseline_bytes=self.reset_current_baseline,
            anon_bytes=anon,
            file_bytes=file_bytes,
            baseline_anon_bytes=baseline_anon,
            baseline_file_bytes=baseline_file,
            anon_delta_bytes=(max(0, anon - baseline_anon)
                              if anon is not None and baseline_anon is not None else None),
            file_delta_bytes=(max(0, file_bytes - baseline_file)
                              if file_bytes is not None and baseline_file is not None else None),
            scope_identity=self.scope_identity,
            available=current is not None and peak is not None,
            per_workflow=self.per_workflow,
            memory_limit_bytes=self.memory_limit_bytes,
            effective_memory_limit_bytes=self.effective_memory_limit_bytes,
        )


WINDOW_NAMES = ("first_10pct", "middle_10pct", "final_10pct")
MEMORY_SUBJECTS = (
    "workflow_process_tree",
    "provider_process_tree",
    "arrow_memory_pool",
    "cgroup",
)


def windows_for_interval(start_row: int, end_row: int, total_rows: int) -> tuple[str, ...]:
    total = max(total_rows, 1)
    ranges = {
        "first_10pct": (0, max(1, (total * 10 + 99) // 100)),
        "middle_10pct": ((total * 45) // 100, (total * 55 + 99) // 100),
        "final_10pct": ((total * 90) // 100, total),
    }
    return tuple(
        name
        for name, (window_start, window_end) in ranges.items()
        if start_row < window_end and end_row > window_start
    )


class MemorySampler:
    """Collect independent subject high-water marks for active row windows."""

    def __init__(
        self,
        workflow_pid: int,
        provider_pid: Callable[[], int | None],
        cgroup: CgroupMemoryTracker | None,
        interval_seconds: float,
        baselines: dict[str, int | None] | None = None,
        record_history: bool = False,
    ) -> None:
        self.workflow_pid = workflow_pid
        self.provider_pid = provider_pid
        self.cgroup = cgroup
        self.interval_seconds = interval_seconds
        self.baselines = baselines or {}
        self.record_history = record_history
        self._active: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._peaks: dict[str, dict[str, int | None]] = {
            subject: {window: None for window in WINDOW_NAMES}
            for subject in MEMORY_SUBJECTS
        }
        self.global_peaks: dict[str, int | None] = {
            subject: None for subject in MEMORY_SUBJECTS
        }
        self._absolute_peaks: dict[str, dict[str, int | None]] = {
            subject: {window: None for window in WINDOW_NAMES}
            for subject in MEMORY_SUBJECTS
        }
        self.global_delta_peaks: dict[str, int | None] = {
            subject: None for subject in MEMORY_SUBJECTS
        }
        self._history: list[
            tuple[float, dict[str, int | None], dict[str, int | None]]
        ] = []
        self._latest_cgroup_details: dict[str, int | None] = {
            "current_bytes": None,
            "anon_bytes": None,
            "file_bytes": None,
        }

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            self.sample()
            self._stop.wait(self.interval_seconds)

    def _snapshot(self) -> dict[str, int | None]:
        provider_pid = self.provider_pid()
        cgroup = self.cgroup.snapshot() if self.cgroup is not None else None
        self._latest_cgroup_details = {
            "current_bytes": cgroup.current_bytes if cgroup is not None else None,
            "anon_bytes": cgroup.anon_bytes if cgroup is not None else None,
            "file_bytes": cgroup.file_bytes if cgroup is not None else None,
        }
        return {
            "workflow_process_tree": process_tree_rss_kib(self.workflow_pid),
            "provider_process_tree": process_tree_rss_kib(provider_pid) if provider_pid else 0,
            "arrow_memory_pool": pa.default_memory_pool().bytes_allocated(),
            "cgroup": cgroup.current_bytes if cgroup is not None else None,
        }

    def sample(self, windows: tuple[str, ...] | None = None) -> None:
        snapshot = self._snapshot()
        sampled_at = time.monotonic()
        with self._lock:
            if self.record_history:
                self._history.append(
                    (
                        sampled_at,
                        dict(snapshot),
                        dict(self._latest_cgroup_details),
                    )
                )
            targets = set(windows) if windows is not None else set(self._active)
            for subject, value in snapshot.items():
                if value is not None:
                    self.global_peaks[subject] = max(self.global_peaks[subject] or 0, value)
                    baseline = self.baselines.get(subject)
                    delta = max(0, value - baseline) if baseline is not None else None
                    if delta is not None:
                        self.global_delta_peaks[subject] = max(
                            self.global_delta_peaks[subject] or 0, delta
                        )
                else:
                    delta = None
                for window in targets:
                    if value is not None:
                        self._absolute_peaks[subject][window] = max(
                            self._absolute_peaks[subject][window] or 0, value
                        )
                        if delta is not None:
                            self._peaks[subject][window] = max(
                                self._peaks[subject][window] or 0, delta
                            )

    def set_active(self, windows: tuple[str, ...]) -> None:
        with self._lock:
            self._active = set(windows)
        self.sample(windows)

    def set_baseline(self, subject: str, value: int | None) -> None:
        """Inject a subject baseline immediately after its process is spawned."""

        with self._lock:
            self.baselines[subject] = value

    def stop(self) -> dict[str, dict[str, int | None]]:
        self.sample()
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 20))
        with self._lock:
            return {
                subject: dict(values) for subject, values in self._peaks.items()
            }

    def absolute_peaks(self) -> dict[str, dict[str, int | None]]:
        with self._lock:
            return {
                subject: dict(values) for subject, values in self._absolute_peaks.items()
            }

    def time_fraction_peaks(
        self, started_at: float, finished_at: float
    ) -> dict[str, object]:
        """Classify optional history into diagnostic time-fraction windows.

        This is intentionally diagnostic-only.  Direct DEVNULL has no row
        framing, so it cannot claim formal row-window evidence.
        """

        duration = max(finished_at - started_at, 1e-9)
        windows = {
            "first_10pct": (0.0, 0.10),
            "middle_10pct": (0.45, 0.55),
            "final_10pct": (0.90, 1.0),
        }
        absolute: dict[str, dict[str, int | None]] = {
            subject: {window: None for window in windows}
            for subject in MEMORY_SUBJECTS
        }
        delta: dict[str, dict[str, int | None]] = {
            subject: {window: None for window in windows}
            for subject in MEMORY_SUBJECTS
        }
        stat_absolute: dict[str, dict[str, int | None]] = {
            key: {window: None for window in windows}
            for key in ("anon_bytes", "file_bytes")
        }
        stat_delta: dict[str, dict[str, int | None]] = {
            key: {window: None for window in windows}
            for key in ("anon_bytes", "file_bytes")
        }
        with self._lock:
            history = list(self._history)
        for sampled_at, snapshot, details in history:
            fraction = (sampled_at - started_at) / duration
            for window, (lower, upper) in windows.items():
                if not (lower <= fraction <= upper):
                    continue
                for subject in MEMORY_SUBJECTS:
                    value = snapshot.get(subject)
                    if value is not None:
                        current = absolute[subject][window]
                        absolute[subject][window] = max(current or 0, value)
                        baseline = self.baselines.get(subject)
                        if baseline is not None:
                            current_delta = delta[subject][window]
                            delta[subject][window] = max(
                                current_delta or 0, max(0, value - baseline)
                            )
                for key in ("anon_bytes", "file_bytes"):
                    value = details.get(key)
                    if value is None:
                        continue
                    current = stat_absolute[key][window]
                    stat_absolute[key][window] = max(current or 0, value)
                    baseline = self.baselines.get(f"cgroup_{key}")
                    if baseline is not None:
                        current_delta = stat_delta[key][window]
                        stat_delta[key][window] = max(
                            current_delta or 0, max(0, value - baseline)
                        )
        return {
            "plateau_peaks": delta,
            "plateau_peaks_absolute": absolute,
            "memory_stat_plateau": stat_delta,
            "memory_stat_plateau_absolute": stat_absolute,
            "window_basis": "time_fraction",
        }


_DOLT_VERSION_RE = re.compile(
    r"(?mi)^\s*dolt version\s+(?P<version>\d+\.\d+\.\d+)(?=\s|$)"
)


def parse_dolt_version(version_text: str) -> str | None:
    match = _DOLT_VERSION_RE.search(version_text)
    return match.group("version") if match is not None else None


@dataclass(frozen=True)
class CommandResult:
    command_kind: str
    exit_code: int
    duration_seconds: float
    stdout: bytes
    stdout_tail: bytes
    stderr_tail: bytes
    timed_out: bool = False
    cancelled: bool = False
    stdout_truncated: bool = False


class _Tail:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._data = bytearray()

    def append(self, data: bytes) -> None:
        self._data.extend(data)
        if len(self._data) > self.limit:
            del self._data[: len(self._data) - self.limit]

    def value(self) -> bytes:
        return bytes(self._data)


class _Capture:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._data = bytearray()
        self.truncated = False

    def append(self, data: bytes) -> None:
        available = max(0, self.limit - len(self._data))
        if len(data) > available:
            self.truncated = True
        self._data.extend(data[:available])

    def value(self) -> bytes:
        return bytes(self._data)


_OFFLINE_DOLT_CONFIG = {
    "versioncheck.disabled": "true",
    "metrics.disabled": "true",
}


@dataclass(frozen=True)
class _ProcessTerminationOutcome:
    error: BaseException | None = None

    def raise_if_failed(self) -> None:
        if self.error is not None:
            raise self.error


@dataclass
class _ProcessTerminationGate:
    outcome: _ProcessTerminationOutcome | None = None
    done: bool = False


class ActiveChildRegistry:
    """Tracks active Dolt child processes for production cancellation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._processes: set[subprocess.Popen[bytes]] = set()
        self._owners: dict[subprocess.Popen[bytes], object | None] = {}
        self._termination_gates: dict[subprocess.Popen[bytes], _ProcessTerminationGate] = {}

    def register(self, process: subprocess.Popen[bytes], *, owner: object | None = None) -> None:
        with self._condition:
            self._processes.add(process)
            self._owners[process] = owner

    def unregister(self, process: subprocess.Popen[bytes]) -> None:
        with self._condition:
            self._processes.discard(process)
            self._owners.pop(process, None)
            self._termination_gates.pop(process, None)
            self._condition.notify_all()

    def snapshot(self) -> tuple[subprocess.Popen[bytes], ...]:
        with self._condition:
            return tuple(self._processes)

    def snapshot_for_owner(self, owner: object) -> tuple[subprocess.Popen[bytes], ...]:
        with self._condition:
            return tuple(process for process in self._processes if self._owners.get(process) is owner)

    def begin_process_termination(
        self,
        process: subprocess.Popen[bytes],
    ) -> tuple[Literal["leader", "wait"], _ProcessTerminationGate]:
        with self._condition:
            gate = self._termination_gates.get(process)
            if gate is not None and not gate.done:
                return "wait", gate
            gate = _ProcessTerminationGate()
            self._termination_gates[process] = gate
            return "leader", gate

    def await_process_termination(
        self,
        gate: _ProcessTerminationGate,
        *,
        timeout: float | None = None,
    ) -> None:
        with self._condition:
            deadline = None if timeout is None else time.monotonic() + timeout
            while not gate.done:
                if timeout is not None:
                    remaining = deadline - time.monotonic() if deadline is not None else 0.0
                    if remaining <= 0:
                        break
                    self._condition.wait(timeout=remaining)
                else:
                    self._condition.wait()
            outcome = gate.outcome
        if outcome is not None:
            outcome.raise_if_failed()

    def publish_process_termination_outcome(
        self,
        process: subprocess.Popen[bytes],
        gate: _ProcessTerminationGate,
        outcome: _ProcessTerminationOutcome,
    ) -> None:
        with self._condition:
            if not gate.done:
                gate.outcome = outcome
                gate.done = True
            self._termination_gates.pop(process, None)
            self._condition.notify_all()


class DoltRunner:
    """Runs exact-version Dolt with bounded output and a private environment."""

    def __init__(
        self,
        settings: RepositoryServiceSettings,
        server_root: Path,
        *,
        home: Path | None = None,
        tmpdir: Path | None = None,
        cwd_roots: tuple[Path, ...] | None = None,
    ) -> None:
        self.settings = settings
        self.server_root = server_root.resolve()
        self.cwd_roots = tuple(path.resolve() for path in (cwd_roots or (server_root,)))
        self.home = (home if home is not None else self.server_root / "provider" / "runner-home").resolve()
        self.tmpdir = (tmpdir if tmpdir is not None else self.server_root / "provider").resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.tmpdir.mkdir(parents=True, exist_ok=True)
        self._active_children = ActiveChildRegistry()
        self._seed_private_dolt_config()
        self._validate_version()

    @classmethod
    def for_layout(
        cls, settings: RepositoryServiceSettings, layout: DurableLayout, *,
        home: Path | None = None, tmpdir: Path | None = None,
    ) -> DoltRunner:
        return cls(settings, layout.metadata_root,
            home=home if home is not None else layout.provider / "runner-home",
            tmpdir=tmpdir if tmpdir is not None else layout.provider_scratch,
            cwd_roots=layout.roots.paths())

    def terminate_active_children(self, grace_seconds: float | None = None) -> None:
        grace = grace_seconds if grace_seconds is not None else self.settings.terminate_grace_seconds
        for process in self._active_children.snapshot():
            if process.poll() is None:
                self.terminate_and_reap(process, grace_seconds=grace)
            else:
                self._active_children.unregister(process)

    def terminate_owned(self, owner: object, *, grace_seconds: float | None = None) -> None:
        grace = grace_seconds if grace_seconds is not None else self.settings.terminate_grace_seconds
        for process in self._active_children.snapshot_for_owner(owner):
            if process.poll() is None:
                self.terminate_and_reap(process, grace_seconds=grace)
            else:
                self._active_children.unregister(process)

    def has_active_children(self) -> bool:
        return bool(self._active_children.snapshot())

    def has_owned_children(self, owner: object) -> bool:
        return bool(self._active_children.snapshot_for_owner(owner))

    def _seed_private_dolt_config(self) -> None:
        """Keep the private runner HOME from reaching the network.

        Dolt queries the latest released version on the first command run
        under an unseeded HOME, which costs several seconds and contradicts
        the offline boundary this runner is meant to enforce.
        """

        config_directory = self.home / ".dolt"
        config_directory.mkdir(parents=True, exist_ok=True)
        config_path = config_directory / "config_global.json"
        if config_path.exists():
            existing = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = {}
        else:
            existing = {}
        merged = {**existing, **_OFFLINE_DOLT_CONFIG}
        if merged != existing:
            config_path.write_text(json.dumps(merged), encoding="utf-8")

    def _validate_version(self) -> None:
        result = self.run(
            "version",
            ["version"],
            cwd=self.server_root,
            timeout=self.settings.metadata_timeout_seconds,
            capture_stdout=True,
        )
        version_text = result.stdout.decode("utf-8", errors="replace")
        if parse_dolt_version(version_text) != self.settings.dolt_version:
            raise ProcessBoundaryError("Dolt exact version check failed")

    def run(
        self,
        command_kind: str,
        args: list[str],
        *,
        cwd: Path,
        timeout: float,
        stdin_path: Path | None = None,
        capture_stdout: bool = False,
        cancellation: StreamCancellationCheck | None = None,
        owner: object | None = None,
    ) -> CommandResult:
        if evaluate_stream_cancellation(cancellation):
            raise ProcessStreamCancelledError("command cancelled before start")
        if timeout <= 0:
            raise ProcessStreamCancelledError("command cancelled before start")
        process, stdin_handle = self._start(command_kind, args, cwd=cwd, stdin_path=stdin_path, owner=owner)
        try:
            return self._collect(
                process,
                command_kind=command_kind,
                timeout=timeout,
                capture_stdout=capture_stdout,
                cancellation=cancellation,
            )
        finally:
            if stdin_handle is not None:
                stdin_handle.close()

    def stream(
        self,
        command_kind: str,
        args: list[str],
        *,
        cwd: Path,
        timeout: float,
        stdin_path: Path | None = None,
        cancellation: StreamCancellationCheck | None = None,
        owner: object | None = None,
    ) -> "ProcessStream":
        if evaluate_stream_cancellation(cancellation):
            raise ProcessStreamCancelledError("stream cancelled")
        process, stdin_handle = self._start(
            command_kind,
            args,
            cwd=cwd,
            stdin_path=stdin_path,
            owner=owner,
        )
        if stdin_handle is not None:
            stdin_handle.close()
        return ProcessStream(
            self,
            process,
            command_kind,
            timeout,
            max_line_bytes=self.settings.max_stream_line_bytes,
            cancellation=cancellation,
        )

    def _start(
        self,
        command_kind: str,
        args: list[str],
        *,
        cwd: Path,
        stdin_path: Path | None,
        stdout_target: BinaryIO | int | None = None,
        owner: object | None = None,
    ) -> tuple[subprocess.Popen[bytes], BinaryIO | None]:
        resolved_cwd = cwd.resolve()
        if not any(resolved_cwd.is_relative_to(root) for root in getattr(self, "cwd_roots", (self.server_root,))):
            raise ProcessBoundaryError("child cwd is outside the server-owned root")
        if not resolved_cwd.is_dir():
            raise ProcessBoundaryError("child cwd is not a directory")
        if any("\x00" in arg for arg in args):
            raise ProcessBoundaryError("NUL in child argv")
        stdin_handle: BinaryIO | None = None
        if stdin_path is not None:
            stdin_handle = stdin_path.open("rb")
        environment = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(self.home),
            "LANG": "C",
            "LC_ALL": "C",
            "TMPDIR": str(getattr(self, "tmpdir", self.server_root / "provider")),
        }
        try:
            process = subprocess.Popen(
                [str(self.settings.dolt_binary), *args],
                cwd=resolved_cwd,
                env=environment,
                stdin=stdin_handle,
                stdout=subprocess.PIPE if stdout_target is None else stdout_target,
                stderr=subprocess.PIPE,
                shell=False,
                close_fds=True,
                start_new_session=True,
            )
        except BaseException:
            if stdin_handle is not None:
                stdin_handle.close()
            raise
        registry = getattr(self, "_active_children", None)
        if registry is not None:
            registry.register(process, owner=owner)
        return process, stdin_handle

    def _unregister_active_child(self, process: subprocess.Popen[bytes]) -> None:
        registry = getattr(self, "_active_children", None)
        if registry is not None:
            registry.unregister(process)

    def _collect(
        self,
        process: subprocess.Popen[bytes],
        *,
        command_kind: str,
        timeout: float,
        capture_stdout: bool,
        cancellation: StreamCancellationCheck | None = None,
    ) -> CommandResult:
        if process.stdout is None or process.stderr is None:
            raise ProcessBoundaryError("Dolt child pipes were not created")
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        stdout_tail = _Tail(self.settings.output_tail_bytes)
        stderr_tail = _Tail(self.settings.output_tail_bytes)
        stdout_capture = _Capture(self.settings.output_capture_bytes)
        started = time.monotonic()
        timed_out = False
        cancelled = False
        try:
            while selector.get_map():
                if evaluate_stream_cancellation(cancellation):
                    cancelled = True
                    self.terminate_and_reap(process)
                    break
                elapsed = time.monotonic() - started
                # Once the direct child has exited, stop waiting on inherited
                # pipe descriptors. Dolt can leave descriptors open briefly
                # in helper processes; waiting for EOF here can prevent the
                # Popen child from being reaped and can accumulate zombies.
                if process.poll() is not None:
                    break
                if elapsed > timeout:
                    timed_out = True
                    self.terminate_and_reap(process)
                    break
                for key, _ in selector.select(timeout=0.05):
                    stream = key.fileobj
                    file_descriptor = stream if isinstance(stream, int) else stream.fileno()
                    data = os.read(file_descriptor, 65536)
                    if not data:
                        selector.unregister(stream)
                        continue
                    if key.data == "stdout":
                        stdout_tail.append(data)
                        if capture_stdout:
                            stdout_capture.append(data)
                    else:
                        stderr_tail.append(data)
            if process.poll() is None:
                self.terminate_and_reap(process)
            else:
                process.wait()
                self.reap_adopted_dolt_children()
            # Pipes may still contain a final bounded tail after process exit,
            # but never block indefinitely on a descriptor inherited by a
            # helper. The direct child has already been waited/reaped above.
            for stream, tail, capture in (
                (process.stdout, stdout_tail, stdout_capture if capture_stdout else None),
                (process.stderr, stderr_tail, None),
            ):
                file_descriptor = stream.fileno()
                os.set_blocking(file_descriptor, False)
                drain_deadline = time.monotonic() + 0.2
                while time.monotonic() < drain_deadline:
                    try:
                        data = os.read(file_descriptor, 65536)
                    except BlockingIOError:
                        time.sleep(0.005)
                        continue
                    if not data:
                        break
                    tail.append(data)
                    if capture is not None:
                        capture.append(data)
        finally:
            selector.close()
            if process.poll() is None:
                self.terminate_and_reap(process)
            else:
                self._unregister_active_child(process)
        return CommandResult(
            command_kind=command_kind,
            exit_code=process.returncode if process.returncode is not None else -1,
            duration_seconds=time.monotonic() - started,
            stdout=stdout_capture.value(),
            stdout_tail=stdout_tail.value(),
            stderr_tail=stderr_tail.value(),
            timed_out=timed_out,
            cancelled=cancelled,
            stdout_truncated=stdout_capture.truncated,
        )

    def terminate_and_reap(
        self,
        process: subprocess.Popen[bytes],
        *,
        grace_seconds: float | None = None,
    ) -> None:
        active_children = getattr(self, "_active_children", None)
        gate: _ProcessTerminationGate | None = None
        if active_children is not None:
            role, gate = active_children.begin_process_termination(process)
            if role == "wait":
                active_children.await_process_termination(gate)
                return
        termination_error: BaseException | None = None
        try:
            grace = grace_seconds if grace_seconds is not None else self.settings.terminate_grace_seconds
            if process.poll() is not None:
                process.wait()
            else:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=grace)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
            self._unregister_active_child(process)
            self.reap_adopted_dolt_children()
        except BaseException as exc:
            termination_error = exc
            raise
        finally:
            if active_children is not None and gate is not None:
                active_children.publish_process_termination_outcome(
                    process,
                    gate,
                    _ProcessTerminationOutcome(error=termination_error),
                )

    @staticmethod
    def reap_adopted_dolt_children() -> None:
        """Reap orphaned Dolt helpers adopted by a PID-1 probe process.

        A container can run the Python supervisor as PID 1. Dolt may orphan a
        short-lived helper while processing a large SQL stream; the helper is
        then reparented to this process instead of an init supervisor. Only
        direct zombie children whose kernel command name is ``dolt`` are
        selected, leaving unrelated child processes and active Popen handles
        to their owners.
        """

        children_path = Path(f"/proc/{os.getpid()}/task/{os.getpid()}/children")
        try:
            child_pids = [int(value) for value in children_path.read_text().split()]
        except (FileNotFoundError, OSError, ValueError):
            return
        for pid in child_pids:
            try:
                status = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
                closing = status.rfind(")")
                state = status[closing + 2 : closing + 3]
                comm = status[status.find("(") + 1 : closing]
                if state != "Z" or comm != "dolt":
                    continue
                os.waitpid(pid, os.WNOHANG)
            except (ChildProcessError, FileNotFoundError, OSError, ValueError):
                continue


class ProcessStream:
    """Incremental stdout reader with cancellation and child reaping."""

    def __init__(
        self,
        runner: DoltRunner,
        process: subprocess.Popen[bytes],
        command_kind: str,
        timeout: float,
        *,
        max_line_bytes: int | None = None,
        cancellation: StreamCancellationCheck | None = None,
    ) -> None:
        self.runner = runner
        self.process = process
        self.command_kind = command_kind
        self.timeout = timeout
        self.max_line_bytes = max_line_bytes or runner.settings.output_capture_bytes
        self._cancellation = cancellation
        self.started = time.monotonic()
        self.start_rss_kib = process_tree_rss_kib(process.pid)
        start_breakdown = process_tree_rss_breakdown_kib(process.pid)
        self.start_rss_anon_kib = start_breakdown["rss_anon_kib"]
        self.start_rss_file_kib = start_breakdown["rss_file_kib"]
        self.stderr_tail = _Tail(runner.settings.output_tail_bytes)
        self._lifecycle_lock = threading.Lock()
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()
        self._monitor_stop = threading.Event()
        self.peak_rss_kib = self.start_rss_kib
        self.peak_rss_anon_kib = self.start_rss_anon_kib
        self.peak_rss_file_kib = self.start_rss_file_kib
        self._monitor_thread = threading.Thread(target=self._monitor_rss, daemon=True)
        self._monitor_thread.start()
        self._closed = False
        self._close_lock = threading.Lock()
        self._closed_result: CommandResult | None = None

    def _drain_stderr(self) -> None:
        if self.process.stderr is None:
            return
        while True:
            data = self.process.stderr.read(65536)
            if not data:
                return
            self.stderr_tail.append(data)

    def _monitor_rss(self) -> None:
        while not self._monitor_stop.is_set():
            with self._lifecycle_lock:
                if self._monitor_stop.is_set():
                    return
                self.peak_rss_kib = max(
                    self.peak_rss_kib, process_tree_rss_kib(self.process.pid)
                )
                breakdown = process_tree_rss_breakdown_kib(self.process.pid)
                self.peak_rss_anon_kib = max(
                    self.peak_rss_anon_kib, breakdown["rss_anon_kib"]
                )
                self.peak_rss_file_kib = max(
                    self.peak_rss_file_kib, breakdown["rss_file_kib"]
                )
            self._monitor_stop.wait(0.02)

    def _stop_rss_monitor(self) -> None:
        """Stop sampling before any caller can wait/reap the child."""

        with self._lifecycle_lock:
            self._monitor_stop.set()
        # See DiscardProcess._stop_rss_monitor: procfs sampling and child
        # lifecycle operations are serialized by this lock.
        self._monitor_thread.join()

    @property
    def running_pid(self) -> int | None:
        """Return the child PID only while it is still owned and running.

        The sampler can take one final sample after the stream reader has
        reaped the child.  Returning a reaped PID would allow a later process
        reusing that numeric PID to be misattributed to the Dolt stream.
        """

        with self._lifecycle_lock:
            return self.process.pid if self.process.poll() is None else None

    def _raise_if_cancelled(self, *, selector: selectors.BaseSelector | None = None) -> None:
        if not evaluate_stream_cancellation(self._cancellation):
            return
        if selector is not None:
            selector.close()
        self.close(cancelled=True)
        raise ProcessStreamCancelledError("stream cancelled")

    def __iter__(self) -> Iterator[bytes]:
        if self.process.stdout is None:
            raise ProcessBoundaryError("stream stdout was not created")
        file_descriptor = self.process.stdout.fileno()
        os.set_blocking(file_descriptor, False)
        selector = selectors.DefaultSelector()
        selector.register(file_descriptor, selectors.EVENT_READ)
        pending = bytearray()
        self._raise_if_cancelled(selector=selector)
        while True:
            remaining = self.timeout - (time.monotonic() - self.started)
            if remaining <= 0:
                selector.close()
                self.close(timed_out=True)
                raise TimeoutError(f"{self.command_kind} exceeded timeout")
            events = selector.select(timeout=min(0.05, remaining))
            if not events:
                self._raise_if_cancelled(selector=selector)
                continue
            try:
                data = os.read(file_descriptor, 65536)
            except BlockingIOError:
                self._raise_if_cancelled(selector=selector)
                continue
            self._raise_if_cancelled(selector=selector)
            if not data:
                selector.unregister(file_descriptor)
                selector.close()
                if pending:
                    if len(pending) > self.max_line_bytes:
                        self.close(cancelled=True)
                        raise ProcessBoundaryError("stream line exceeded bounded output limit")
                    yield bytes(pending)
                self.close()
                return
            pending.extend(data)
            if len(pending) > self.max_line_bytes and b"\n" not in pending:
                selector.close()
                self.close(cancelled=True)
                raise ProcessBoundaryError("stream line exceeded bounded output limit")
            while True:
                newline = pending.find(b"\n")
                if newline < 0:
                    break
                line = bytes(pending[: newline + 1])
                del pending[: newline + 1]
                if len(line) > self.max_line_bytes:
                    selector.close()
                    self.close(cancelled=True)
                    raise ProcessBoundaryError("stream line exceeded bounded output limit")
                self._raise_if_cancelled(selector=selector)
                yield line

    def close(self, *, cancelled: bool = False, timed_out: bool = False) -> CommandResult:
        with self._close_lock:
            if self._closed_result is not None:
                return self._closed_result
            with self._lifecycle_lock:
                process_running = self.process.poll() is None
            self._stop_rss_monitor()
            if process_running:
                self.runner.terminate_and_reap(self.process)
            else:
                self.process.wait()
                self.runner._unregister_active_child(self.process)
                self.runner.reap_adopted_dolt_children()
            self._stderr_thread.join(timeout=self.runner.settings.terminate_grace_seconds)
            if self.process.stdout is not None:
                self.process.stdout.close()
            if self.process.stderr is not None:
                self.process.stderr.close()
            self._closed = True
            self._closed_result = CommandResult(
                command_kind=self.command_kind,
                exit_code=self.process.returncode if self.process.returncode is not None else -1,
                duration_seconds=time.monotonic() - self.started,
                stdout=b"",
                stdout_tail=b"",
                stderr_tail=self.stderr_tail.value(),
                timed_out=timed_out,
                cancelled=cancelled,
            )
            return self._closed_result

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is TimeoutError:
            self.close(timed_out=True)
        elif exc_type is not None:
            self.close(cancelled=True)
        else:
            self.close()
