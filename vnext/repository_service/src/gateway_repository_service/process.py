"""Controlled Dolt child-process and sql-server supervision boundary."""

from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Callable, Iterator, Self

import pyarrow as pa  # type: ignore[import-untyped]

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


class WorkflowCgroupScope:
    """Own one delegated child cgroup without moving the supervisor into it."""

    def __init__(
        self,
        root: Path | None,
        *,
        grace_seconds: float = 2.0,
        memory_limit_bytes: int | None = None,
    ) -> None:
        self.root = root.resolve() if root is not None else None
        self.grace_seconds = grace_seconds
        self.memory_limit_bytes = memory_limit_bytes
        self.path: Path | None = None
        self.active = False

    def create(self) -> Path:
        if self.root is None or not self.root.is_dir():
            raise ProcessBoundaryError("delegated cgroup root is unavailable")
        candidate = self.root / f"gateway-p2r1-{uuid.uuid4().hex}"
        try:
            candidate.mkdir()
        except (FileExistsError, OSError, PermissionError) as exc:
            try:
                candidate.rmdir()
            except OSError:
                pass
            raise ProcessBoundaryError("cannot create delegated workflow cgroup") from exc
        self.path = candidate
        self.active = True
        if self.memory_limit_bytes is not None:
            try:
                (candidate / "memory.max").write_text(
                    str(self.memory_limit_bytes), encoding="ascii"
                )
                configured = (candidate / "memory.max").read_text(
                    encoding="ascii"
                ).strip()
            except OSError as exc:
                self.active = False
                candidate.rmdir()
                raise ProcessBoundaryError(
                    "cannot configure workflow cgroup memory safety ceiling"
                ) from exc
            if configured != str(self.memory_limit_bytes):
                self.active = False
                candidate.rmdir()
                raise ProcessBoundaryError(
                    "workflow cgroup memory safety ceiling was not verified"
                )
        return candidate

    def attach(self, pid: int) -> None:
        if not self.active or self.path is None:
            raise ProcessBoundaryError("workflow cgroup is not active")
        procs = self.path / "cgroup.procs"
        try:
            procs.write_text(str(pid), encoding="ascii")
            members = {int(value) for value in procs.read_text(encoding="ascii").split()}
        except (OSError, ValueError) as exc:
            raise ProcessBoundaryError("cannot attach worker to delegated cgroup") from exc
        if pid not in members:
            raise ProcessBoundaryError("worker PID was not observed in delegated cgroup")

    def _members(self) -> set[int]:
        if self.path is None:
            return set()
        try:
            return {
                int(value)
                for value in self.path.joinpath("cgroup.procs")
                .read_text(encoding="ascii")
                .split()
            }
        except (OSError, ValueError) as exc:
            raise ProcessBoundaryError("cannot inspect workflow cgroup during cleanup") from exc

    @staticmethod
    def _member_details(members: set[int]) -> str:
        details: list[str] = []
        for pid in sorted(members):
            try:
                status = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
                closing = status.rfind(")")
                state = status[closing + 2 : closing + 3]
                comm = status[status.find("(") + 1 : closing]
            except (FileNotFoundError, OSError, ValueError):
                state = "?"
                comm = "gone"
            details.append(f"pid={pid},state={state},comm={comm[:64]}")
        return ";".join(details)

    def _terminate_members(self, members: set[int]) -> None:
        for pid in sorted(members):
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                continue

    def _kill_members(self, members: set[int]) -> None:
        for pid in sorted(members):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                continue

    def cleanup(self) -> None:
        if not self.active or self.path is None:
            return
        deadline = time.monotonic() + self.grace_seconds
        members = self._members()
        while members and time.monotonic() < deadline:
            time.sleep(0.02)
            members = self._members()
        if members:
            self._terminate_members(members)
            deadline = time.monotonic() + self.grace_seconds
            while members and time.monotonic() < deadline:
                time.sleep(0.02)
                members = self._members()
        if members:
            self._kill_members(members)
            deadline = time.monotonic() + self.grace_seconds
            while members and time.monotonic() < deadline:
                time.sleep(0.02)
                members = self._members()
        if members:
            details = self._member_details(members)
            raise ProcessBoundaryError(
                f"workflow cgroup still contains processes ({details})"
            )
        try:
            self.path.rmdir()
        except OSError as exc:
            raise ProcessBoundaryError("cannot remove workflow cgroup") from exc
        self.active = False

    def __enter__(self) -> "WorkflowCgroupScope":
        self.create()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.cleanup()


def current_cgroup_membership(pid: int | None = None) -> str | None:
    process_id = os.getpid() if pid is None else pid
    try:
        lines = Path(f"/proc/{process_id}/cgroup").read_text(encoding="ascii").splitlines()
    except (FileNotFoundError, OSError):
        return None
    for line in lines:
        fields = line.split(":", 2)
        if len(fields) == 3 and fields[0] == "0":
            return fields[2]
    return None


def cgroup_scope_identity(root: Path) -> str:
    """Return a stable opaque identity without publishing a host cgroup path."""

    return "sha256:" + hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CgroupTopology:
    """The launcher-authorized cgroup topology visible to the target."""

    delegated_root: Path
    supervisor: Path
    samples: Path
    parent_control_group: str
    slice_control_group: str
    service_control_group: str
    delegated_control_group: str
    supervisor_control_group: str
    layout_version: str

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "CgroupTopology":
        def path_field(name: str) -> Path:
            raw = value.get(name)
            if not isinstance(raw, str) or not raw.startswith("/"):
                raise ProcessBoundaryError(f"cgroup layout field {name} is not absolute")
            return Path(raw).resolve()

        def control_group_field(name: str) -> str:
            raw = value.get(name)
            if not isinstance(raw, str) or not raw.startswith("/"):
                raise ProcessBoundaryError(
                    f"cgroup layout field {name} is not an absolute ControlGroup"
                )
            return raw.rstrip("/") or "/"

        layout_version = value.get("layout_version")
        if not isinstance(layout_version, str) or not layout_version:
            raise ProcessBoundaryError("cgroup layout version is missing")
        delegated_root = path_field("delegated_root")
        supervisor = path_field("supervisor")
        samples = path_field("samples")
        if supervisor.parent != delegated_root or samples.parent != delegated_root:
            raise ProcessBoundaryError("supervisor and samples are not delegated-root siblings")
        if supervisor == samples or delegated_root in (supervisor, samples):
            raise ProcessBoundaryError("cgroup layout has invalid sibling topology")
        return cls(
            delegated_root=delegated_root,
            supervisor=supervisor,
            samples=samples,
            parent_control_group=control_group_field("parent_control_group"),
            slice_control_group=control_group_field("slice_control_group"),
            service_control_group=control_group_field("service_control_group"),
            delegated_control_group=control_group_field("delegated_control_group"),
            supervisor_control_group=control_group_field("supervisor_control_group"),
            layout_version=layout_version,
        )


def load_cgroup_topology(path: Path | None) -> CgroupTopology | None:
    """Load the launcher-produced topology; no inferred formal root is allowed."""

    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        raise ProcessBoundaryError("cgroup layout manifest is unavailable") from exc
    if not isinstance(value, dict):
        raise ProcessBoundaryError("cgroup layout manifest is not an object")
    return CgroupTopology.from_dict(value)


def resolve_current_cgroup(root_mount: Path, *, pid: int | None = None) -> Path:
    """Resolve the exact cgroup containing ``pid`` below a delegated mount.

    Target containers receive a delegated service-subtree mount, while ``/proc``
    exposes the host-relative cgroup path. The launcher supplies the service's
    actual ControlGroup, so this function can map the process suffix into the mount
    without ever deriving a host path from a unit name.
    """

    root = root_mount.resolve()
    process_id = os.getpid() if pid is None else pid
    try:
        direct_members = {
            int(value)
            for value in (root / "cgroup.procs").read_text(encoding="ascii").split()
        }
    except (FileNotFoundError, OSError, ValueError):
        direct_members = set()
    if process_id in direct_members:
        return root
    membership = current_cgroup_membership(pid)
    if membership is None:
        raise ProcessBoundaryError("current process cgroup membership is unavailable")
    control_group = os.environ.get("GATEWAY_REPOSITORY_CGROUP_CONTROL_GROUP")
    if control_group:
        normalized = control_group.rstrip("/") or "/"
        if membership != normalized and not membership.startswith(normalized + "/"):
            raise ProcessBoundaryError(
                "current process is outside the delegated cgroup parent ControlGroup"
            )
        suffix = membership[len(normalized) :].lstrip("/")
        candidate = root / suffix if suffix else root
    elif root == Path("/sys/fs/cgroup"):
        candidate = root / membership.lstrip("/")
    else:
        # Local unit tests and diagnostic callers may already pass the exact
        # cgroup directory. Formal target invocations always provide the
        # ControlGroup metadata above.
        candidate = root
    if not candidate.is_dir():
        raise ProcessBoundaryError("exact current cgroup directory is unavailable")
    return candidate


def fork_exec_gated(argv: list[str]) -> tuple[int, int]:
    """Fork a session leader that cannot exec until its parent releases a pipe."""

    if not argv or any("\x00" in item for item in argv):
        raise ProcessBoundaryError("invalid gated process argv")
    gate_read, gate_write = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(gate_write)
        try:
            os.setsid()
            if os.read(gate_read, 1) != b"1":
                raise RuntimeError("gated process release was not received")
            os.close(gate_read)
            os.execv(argv[0], argv)
        finally:
            os._exit(127)
    os.close(gate_read)
    return pid, gate_write


def release_gated_process(gate_write: int) -> None:
    try:
        os.write(gate_write, b"1")
    finally:
        os.close(gate_write)


def terminate_process_group_and_reap(pid: int, grace_seconds: float = 2.0) -> None:
    """Terminate a gated/exec'd process group and always reap its direct child."""

    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        try:
            waited, _ = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return
        if waited == pid:
            return
        time.sleep(0.01)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass


def _direct_cgroup_pids(path: Path) -> set[int]:
    try:
        return {
            int(value)
            for value in (path / "cgroup.procs").read_text(encoding="ascii").split()
        }
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise ProcessBoundaryError("cannot read cgroup.procs") from exc


def _enabled_controllers(path: Path) -> set[str]:
    try:
        return set((path / "cgroup.subtree_control").read_text(encoding="ascii").split())
    except (FileNotFoundError, OSError) as exc:
        raise ProcessBoundaryError("cannot read cgroup.subtree_control") from exc


def _require_cgroup_files(path: Path) -> None:
    if not path.is_dir() or not all(
        (path / name).is_file()
        for name in (
            "memory.current",
            "memory.peak",
            "memory.stat",
            "cgroup.procs",
            "cgroup.threads",
            "cgroup.subtree_control",
        )
    ):
        raise ProcessBoundaryError("delegated cgroup memory controls are unavailable")


def preflight_cgroup(
    root: Path | None,
    topology: CgroupTopology | None = None,
    *,
    memory_limit_bytes: int | None = None,
) -> Path:
    """Exercise real cgroup creation, migration, memory reads, and cleanup."""

    if root is None:
        raise ProcessBoundaryError("formal runner requires a delegated cgroup root")
    if topology is not None:
        root_path = topology.samples
        if root.resolve() != topology.samples:
            raise ProcessBoundaryError("formal sample root does not match cgroup layout")
        delegated_root = topology.delegated_root
        supervisor = topology.supervisor
        current_membership = current_cgroup_membership()
        if current_membership != topology.supervisor_control_group:
            raise ProcessBoundaryError("current matrix PID is not in the supervisor cgroup")
        if topology.supervisor_control_group != topology.delegated_control_group + "/supervisor":
            raise ProcessBoundaryError("supervisor ControlGroup is not under delegated root")
        if topology.parent_control_group != topology.slice_control_group and not topology.parent_control_group.startswith(
            topology.slice_control_group.rstrip("/") + "/"
        ):
            raise ProcessBoundaryError("per-run slice is outside the declared parent slice")
        if topology.service_control_group.rsplit("/", 1)[0] != topology.parent_control_group:
            raise ProcessBoundaryError("runner service is not a per-run slice sibling")
        if topology.delegated_control_group.rsplit("/", 1)[0] != topology.parent_control_group:
            raise ProcessBoundaryError("container cgroup is not a per-run slice sibling")
        if topology.delegated_control_group.startswith(
            topology.service_control_group.rstrip("/") + "/"
        ):
            raise ProcessBoundaryError("container cgroup must not be inside runner service subtree")
        _require_cgroup_files(delegated_root)
        _require_cgroup_files(supervisor)
        _require_cgroup_files(root_path)
        if _direct_cgroup_pids(delegated_root) or _direct_cgroup_pids(root_path):
            raise ProcessBoundaryError("delegated root and samples must have no direct processes")
        if os.getpid() not in _direct_cgroup_pids(supervisor):
            raise ProcessBoundaryError("current matrix PID is not a direct supervisor member")
        for cgroup in (delegated_root, root_path):
            if not {"memory", "pids"}.issubset(_enabled_controllers(cgroup)):
                raise ProcessBoundaryError("delegated cgroup controllers are not enabled")
    else:
        root_path = resolve_current_cgroup(root.resolve()) if os.environ.get(
            "GATEWAY_REPOSITORY_CGROUP_CONTROL_GROUP"
        ) else root.resolve()
        delegated_root = root_path
        supervisor = None
    if not root_path.is_dir():
        raise ProcessBoundaryError("delegated cgroup root is unavailable")
    expected_parent = os.environ.get("GATEWAY_REPOSITORY_CGROUP_CONTROL_GROUP")
    membership = current_cgroup_membership()
    if expected_parent and (
        membership is None
        or (membership != expected_parent and not membership.startswith(expected_parent.rstrip("/") + "/"))
    ):
        raise ProcessBoundaryError("target supervisor is not under the delegated cgroup parent")
    if topology is None:
        _require_cgroup_files(root_path)
    scope = WorkflowCgroupScope(root_path, memory_limit_bytes=memory_limit_bytes)
    worker_pid: int | None = None
    gate_write: int | None = None
    try:
        scope.create()
        cgroup_path = scope.path
        if cgroup_path is None:
            raise ProcessBoundaryError("workflow cgroup path was not created")
        if topology is not None:
            _require_cgroup_files(cgroup_path)
        elif not all(
            (cgroup_path / name).is_file()
            for name in ("memory.current", "memory.peak", "memory.stat", "cgroup.procs")
        ):
            raise ProcessBoundaryError(
                "delegated cgroup memory controls are unavailable"
            )
        worker_pid, gate_write = fork_exec_gated(
            [sys.executable, "-c", "import time; time.sleep(0.2)"]
        )
        scope.attach(worker_pid)
        members = {
            int(value)
            for value in (cgroup_path / "cgroup.procs").read_text(encoding="ascii").split()
        }
        if worker_pid not in members:
            raise ProcessBoundaryError("preflight worker PID was not observed in child cgroup")
        if topology is not None:
            if os.getpid() not in _direct_cgroup_pids(supervisor):  # type: ignore[arg-type]
                raise ProcessBoundaryError("matrix PID left supervisor during preflight")
        if cgroup_path is None:
            raise ProcessBoundaryError("workflow cgroup path was not created")
        tracker = CgroupMemoryTracker(cgroup_path)
        try:
            snapshot = tracker.snapshot()
            if not tracker.per_workflow or not snapshot.available:
                raise ProcessBoundaryError("delegated cgroup memory controls are unavailable")
            if memory_limit_bytes is not None and (
                snapshot.memory_limit_bytes != memory_limit_bytes
                or snapshot.effective_memory_limit_bytes is None
                or snapshot.effective_memory_limit_bytes < memory_limit_bytes
            ):
                raise ProcessBoundaryError(
                    "delegated cgroup memory safety ceiling is not effective"
                )
        finally:
            tracker.close()
        if gate_write is not None:
            release_gated_process(gate_write)
            gate_write = None
        waited, status = os.waitpid(worker_pid, 0)
        if waited != worker_pid or status != 0:
            raise ProcessBoundaryError("preflight worker did not exit normally")
        worker_pid = None
        scope.cleanup()
        if topology is not None and (
            _direct_cgroup_pids(root_path) or _direct_cgroup_pids(delegated_root)
        ):
            raise ProcessBoundaryError("delegated cgroup topology retained a direct process")
        return root_path
    except BaseException:
        if gate_write is not None:
            try:
                os.close(gate_write)
            except OSError:
                pass
        if worker_pid is not None:
            terminate_process_group_and_reap(worker_pid)
        if scope.active:
            scope.cleanup()
        raise


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


class ActiveChildRegistry:
    """Tracks active Dolt child processes for production cancellation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._processes: set[subprocess.Popen[bytes]] = set()
        self._owners: dict[subprocess.Popen[bytes], object | None] = {}
        self._terminating: set[subprocess.Popen[bytes]] = set()

    def register(self, process: subprocess.Popen[bytes], *, owner: object | None = None) -> None:
        with self._lock:
            self._processes.add(process)
            self._owners[process] = owner

    def unregister(self, process: subprocess.Popen[bytes]) -> None:
        with self._lock:
            self._processes.discard(process)
            self._owners.pop(process, None)
            self._terminating.discard(process)

    def snapshot(self) -> tuple[subprocess.Popen[bytes], ...]:
        with self._lock:
            return tuple(self._processes)

    def snapshot_for_owner(self, owner: object) -> tuple[subprocess.Popen[bytes], ...]:
        with self._lock:
            return tuple(process for process in self._processes if self._owners.get(process) is owner)

    def claim_for_termination(self, owner: object) -> tuple[subprocess.Popen[bytes], ...]:
        with self._lock:
            claimed: list[subprocess.Popen[bytes]] = []
            for process in self._processes:
                if self._owners.get(process) is not owner:
                    continue
                if process in self._terminating:
                    continue
                if process.poll() is not None:
                    continue
                self._terminating.add(process)
                claimed.append(process)
            return tuple(claimed)

    def release_termination_claim(self, process: subprocess.Popen[bytes]) -> None:
        with self._lock:
            self._terminating.discard(process)


class DoltRunner:
    """Runs exact-version Dolt with bounded output and a private environment."""

    def __init__(self, settings: RepositoryServiceSettings, server_root: Path) -> None:
        self.settings = settings
        self.server_root = server_root.resolve()
        self.home = self.server_root / "provider" / "runner-home"
        self.home.mkdir(parents=True, exist_ok=True)
        self._active_children = ActiveChildRegistry()
        self._seed_private_dolt_config()
        self._validate_version()

    def terminate_active_children(self, grace_seconds: float | None = None) -> None:
        grace = grace_seconds if grace_seconds is not None else self.settings.terminate_grace_seconds
        for process in self._active_children.snapshot():
            if process.poll() is None:
                self.terminate_and_reap(process, grace_seconds=grace)
            else:
                self._active_children.unregister(process)

    def terminate_owned(self, owner: object, *, grace_seconds: float | None = None) -> None:
        grace = grace_seconds if grace_seconds is not None else self.settings.terminate_grace_seconds
        for process in self._active_children.claim_for_termination(owner):
            try:
                if process.poll() is None:
                    self.terminate_and_reap(process, grace_seconds=grace)
                else:
                    self._active_children.unregister(process)
            except BaseException:
                self._active_children.release_termination_claim(process)
                raise

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
            cwd=self.server_root / "versioned",
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
    ) -> CommandResult:
        process, stdin_handle = self._start(command_kind, args, cwd=cwd, stdin_path=stdin_path)
        try:
            return self._collect(
                process,
                command_kind=command_kind,
                timeout=timeout,
                capture_stdout=capture_stdout,
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
            raise ProcessBoundaryError("stream cancelled")
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

    def discard(
        self,
        command_kind: str,
        args: list[str],
        *,
        cwd: Path,
        timeout: float,
        stdin_path: Path | None = None,
    ) -> "DiscardProcess":
        """Run a diagnostic stream with child stdout directly attached to DEVNULL."""

        devnull = open(os.devnull, "wb")
        try:
            process, stdin_handle = self._start(
                command_kind,
                args,
                cwd=cwd,
                stdin_path=stdin_path,
                stdout_target=devnull,
            )
        finally:
            devnull.close()
        if stdin_handle is not None:
            stdin_handle.close()
        return DiscardProcess(self, process, command_kind, timeout)

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
        if not resolved_cwd.is_relative_to(self.server_root):
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
            "TMPDIR": str(self.server_root / "provider"),
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
        try:
            while selector.get_map():
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
            self._unregister_active_child(process)
        return CommandResult(
            command_kind=command_kind,
            exit_code=process.returncode if process.returncode is not None else -1,
            duration_seconds=time.monotonic() - started,
            stdout=stdout_capture.value(),
            stdout_tail=stdout_tail.value(),
            stderr_tail=stderr_tail.value(),
            timed_out=timed_out,
            stdout_truncated=stdout_capture.truncated,
        )

    def terminate_and_reap(
        self,
        process: subprocess.Popen[bytes],
        *,
        grace_seconds: float | None = None,
    ) -> None:
        grace = grace_seconds if grace_seconds is not None else self.settings.terminate_grace_seconds
        if process.poll() is not None:
            process.wait()
            self._unregister_active_child(process)
            self.reap_adopted_dolt_children()
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=grace)
            self._unregister_active_child(process)
            self.reap_adopted_dolt_children()
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        self._unregister_active_child(process)
        self.reap_adopted_dolt_children()

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


@dataclass(frozen=True)
class DiscardResult:
    command_kind: str
    exit_code: int
    duration_seconds: float
    stderr_tail: bytes
    timed_out: bool
    provider_start_rss_kib: int
    provider_peak_rss_kib: int
    provider_start_rss_anon_kib: int
    provider_start_rss_file_kib: int
    provider_peak_rss_anon_kib: int
    provider_peak_rss_file_kib: int


class DiscardProcess:
    """Supervise a child whose stdout is directly attached to DEVNULL."""

    def __init__(
        self,
        runner: DoltRunner,
        process: subprocess.Popen[bytes],
        command_kind: str,
        timeout: float,
    ) -> None:
        self.runner = runner
        self.process = process
        self.command_kind = command_kind
        self.timeout = timeout
        self.started = time.monotonic()
        self.start_rss_kib = process_tree_rss_kib(process.pid)
        start_breakdown = process_tree_rss_breakdown_kib(process.pid)
        self.start_rss_anon_kib = start_breakdown["rss_anon_kib"]
        self.start_rss_file_kib = start_breakdown["rss_file_kib"]
        self.peak_rss_kib = self.start_rss_kib
        self.peak_rss_anon_kib = self.start_rss_anon_kib
        self.peak_rss_file_kib = self.start_rss_file_kib
        self.stderr_tail = _Tail(runner.settings.output_tail_bytes)
        self._lifecycle_lock = threading.Lock()
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()
        self._monitor_stop = threading.Event()
        self._monitor_thread = threading.Thread(target=self._monitor, daemon=True)
        self._monitor_thread.start()
        self._closed = False

    def _drain_stderr(self) -> None:
        if self.process.stderr is None:
            return
        while True:
            data = self.process.stderr.read(65536)
            if not data:
                return
            self.stderr_tail.append(data)

    def _monitor(self) -> None:
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
        # The monitor performs all procfs reads while holding the lifecycle
        # lock.  Acquiring the lock above therefore proves that an in-flight
        # sample has finished; an unbounded join then guarantees that no
        # monitor iteration can race a subsequent reap or PID reuse.
        self._monitor_thread.join()

    def close(self) -> DiscardResult:
        if self._closed:
            return DiscardResult(
                self.command_kind,
                self.process.returncode if self.process.returncode is not None else -1,
                time.monotonic() - self.started,
                self.stderr_tail.value(),
                False,
                self.start_rss_kib,
                self.peak_rss_kib,
                self.start_rss_anon_kib,
                self.start_rss_file_kib,
                self.peak_rss_anon_kib,
                self.peak_rss_file_kib,
            )
        timed_out = False
        deadline = self.started + self.timeout
        process_finished = False
        while True:
            with self._lifecycle_lock:
                process_finished = self.process.poll() is not None
            if process_finished:
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.02)
        if not process_finished:
            timed_out = True
            self._stop_rss_monitor()
            self.runner.terminate_and_reap(self.process)
        else:
            self._stop_rss_monitor()
            self.process.wait()
            self.runner.reap_adopted_dolt_children()
        self._stderr_thread.join(timeout=max(1.0, self.runner.settings.terminate_grace_seconds * 2))
        self._closed = True
        return DiscardResult(
            self.command_kind,
            self.process.returncode if self.process.returncode is not None else -1,
            time.monotonic() - self.started,
            self.stderr_tail.value(),
            timed_out,
            self.start_rss_kib,
            self.peak_rss_kib,
            self.start_rss_anon_kib,
            self.start_rss_file_kib,
            self.peak_rss_anon_kib,
            self.peak_rss_file_kib,
        )


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
        raise ProcessBoundaryError("stream cancelled")

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


class ServerSupervisor:
    """Owns one service-local long-lived Dolt SQL server."""

    def __init__(self, runner: DoltRunner, data_dir: Path, runtime_dir: Path) -> None:
        self.runner = runner
        self.data_dir = data_dir.resolve()
        self.runtime_dir = runtime_dir.resolve()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.socket_path = self.runtime_dir / "dolt.sock"
        self.process: subprocess.Popen[bytes] | None = None
        self.stdout_tail = _Tail(runner.settings.output_tail_bytes)
        self.stderr_tail = _Tail(runner.settings.output_tail_bytes)
        self._drain_threads: list[threading.Thread] = []

    def start(self, timeout: float) -> None:
        if self.process is not None:
            raise RuntimeError("sql-server is already running")
        args = [
            "sql-server",
            f"--data-dir={self.data_dir}",
            f"--doltcfg-dir={self.runtime_dir / 'doltcfg'}",
            "--host=127.0.0.1",
            "--port=3306",
            f"--socket={self.socket_path}",
            "--event-scheduler=OFF",
            "--loglevel=error",
            "--logformat=json",
            "--max-connections=32",
        ]
        process, stdin_handle = self.runner._start(
            "sql_server_start", args, cwd=self.data_dir, stdin_path=None
        )
        if stdin_handle is not None:
            stdin_handle.close()
        self.process = process
        self._start_drain_threads(process)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise ProcessBoundaryError("sql-server exited before readiness")
            if self.socket_path.exists():
                try:
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                        connection.settimeout(0.2)
                        connection.connect(str(self.socket_path))
                    return
                except OSError:
                    pass
            time.sleep(0.05)
        self.stop()
        raise TimeoutError("sql-server readiness timeout")

    def stop(self) -> None:
        process = self.process
        self.process = None
        if process is not None:
            self.runner.terminate_and_reap(process)
            for thread in self._drain_threads:
                thread.join(timeout=self.runner.settings.terminate_grace_seconds)
            self._drain_threads.clear()
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass

    def _start_drain_threads(self, process: subprocess.Popen[bytes]) -> None:
        if process.stdout is not None:
            thread = threading.Thread(
                target=self._drain_pipe, args=(process.stdout, self.stdout_tail), daemon=True
            )
            thread.start()
            self._drain_threads.append(thread)
        if process.stderr is not None:
            thread = threading.Thread(
                target=self._drain_pipe, args=(process.stderr, self.stderr_tail), daemon=True
            )
            thread.start()
            self._drain_threads.append(thread)

    @staticmethod
    def _drain_pipe(pipe: BinaryIO, tail: _Tail) -> None:
        while True:
            data = pipe.read(65536)
            if not data:
                return
            tail.append(data)
