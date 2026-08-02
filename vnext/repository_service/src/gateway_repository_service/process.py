"""Controlled Dolt child-process and sql-server supervision boundary."""

from __future__ import annotations

import os
import selectors
import signal
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Iterator, Self

from gateway_repository_service.settings import RepositoryServiceSettings


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
        if len(self._data) < self.limit:
            available = self.limit - len(self._data)
            self._data.extend(data[:available])
        if len(data) > max(0, self.limit - len(self._data)):
            self.truncated = True

    def value(self) -> bytes:
        return bytes(self._data)


class DoltRunner:
    """Runs exact-version Dolt with bounded output and a private environment."""

    def __init__(self, settings: RepositoryServiceSettings, server_root: Path) -> None:
        self.settings = settings
        self.server_root = server_root.resolve()
        self.home = self.server_root / "provider" / "runner-home"
        self.home.mkdir(parents=True, exist_ok=True)
        self._validate_version()

    def _validate_version(self) -> None:
        result = self.run(
            "version",
            ["version"],
            cwd=self.server_root / "versioned",
            timeout=self.settings.metadata_timeout_seconds,
            capture_stdout=True,
        )
        version_text = result.stdout.decode("utf-8", errors="replace")
        if self.settings.dolt_version not in version_text:
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
    ) -> "ProcessStream":
        process, stdin_handle = self._start(command_kind, args, cwd=cwd, stdin_path=stdin_path)
        if stdin_handle is not None:
            stdin_handle.close()
        return ProcessStream(self, process, command_kind, timeout)

    def _start(
        self,
        command_kind: str,
        args: list[str],
        *,
        cwd: Path,
        stdin_path: Path | None,
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
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                close_fds=True,
                start_new_session=True,
            )
        except BaseException:
            if stdin_handle is not None:
                stdin_handle.close()
            raise
        return process, stdin_handle

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
        return CommandResult(
            command_kind=command_kind,
            exit_code=process.returncode if process.returncode is not None else -1,
            duration_seconds=time.monotonic() - started,
            stdout=stdout_capture.value(),
            stdout_tail=stdout_tail.value(),
            stderr_tail=stderr_tail.value(),
            timed_out=timed_out,
        )

    def terminate_and_reap(self, process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            process.wait()
            self.reap_adopted_dolt_children()
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=self.settings.terminate_grace_seconds)
            self.reap_adopted_dolt_children()
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
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


class ProcessStream:
    """Incremental stdout reader with cancellation and child reaping."""

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
        self.start_rss_kib = process_rss_kib(process.pid)
        self.stderr_tail = _Tail(runner.settings.output_tail_bytes)
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()
        self._monitor_stop = threading.Event()
        self.peak_rss_kib = 0
        self._monitor_thread = threading.Thread(target=self._monitor_rss, daemon=True)
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

    def _monitor_rss(self) -> None:
        while not self._monitor_stop.is_set():
            self.peak_rss_kib = max(self.peak_rss_kib, process_rss_kib(self.process.pid))
            self._monitor_stop.wait(0.02)

    def __iter__(self) -> Iterator[bytes]:
        if self.process.stdout is None:
            raise ProcessBoundaryError("stream stdout was not created")
        while True:
            if time.monotonic() - self.started > self.timeout:
                self.close(cancelled=True)
                raise TimeoutError(f"{self.command_kind} exceeded timeout")
            line = self.process.stdout.readline()
            if not line:
                break
            if len(line) > self.runner.settings.output_capture_bytes:
                self.close(cancelled=True)
                raise ProcessBoundaryError("stream line exceeded bounded output limit")
            yield line
        self.close()

    def close(self, *, cancelled: bool = False) -> CommandResult:
        if self._closed:
            return CommandResult(
                command_kind=self.command_kind,
                exit_code=self.process.returncode if self.process.returncode is not None else -1,
                duration_seconds=time.monotonic() - self.started,
                stdout=b"",
                stdout_tail=b"",
                stderr_tail=self.stderr_tail.value(),
                cancelled=cancelled,
            )
        if self.process.poll() is None:
            self.runner.terminate_and_reap(self.process)
        else:
            self.process.wait()
            self.runner.reap_adopted_dolt_children()
        self._stderr_thread.join(timeout=self.runner.settings.terminate_grace_seconds)
        self._monitor_stop.set()
        self._monitor_thread.join(timeout=self.runner.settings.terminate_grace_seconds)
        if self.process.stdout is not None:
            self.process.stdout.close()
        if self.process.stderr is not None:
            self.process.stderr.close()
        self._closed = True
        return CommandResult(
            command_kind=self.command_kind,
            exit_code=self.process.returncode if self.process.returncode is not None else -1,
            duration_seconds=time.monotonic() - self.started,
            stdout=b"",
            stdout_tail=b"",
            stderr_tail=self.stderr_tail.value(),
            cancelled=cancelled,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close(cancelled=exc_type is not None)


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
