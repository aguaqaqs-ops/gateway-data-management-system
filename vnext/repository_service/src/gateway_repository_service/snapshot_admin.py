"""Private operator CLI for quiescent whole-root snapshot hold.

Invocation (operator/runbook, not a public API):

    python -m gateway_repository_service.snapshot_admin hold [--data-root PATH]

The helper binds an existing durable root, takes the exclusive root lock, runs
``PRAGMA wal_checkpoint(TRUNCATE)``, flushes one machine-readable ready JSON
line, then holds the lock until SIGINT or SIGTERM. Helper liveness is the
snapshot window; there is no ready file, stdin protocol, or daemon.

Private exit codes:

- ``0``: ready JSON was flushed; SIGINT/SIGTERM ended the hold
- ``2``: usage / argparse error
- ``3``: durable root lock is busy
- ``4``: layout or control DB missing, malformed, unreadable, or wrong version
- ``5``: WAL checkpoint busy, leftover frames, or checkpoint error
- ``1``: signal before ready, stdout failure, or other bounded failure

Ready JSON fields: ``schema_version``, ``action=hold``, ``status=ready``,
``layout_format_version``, ``control_db_user_version``, and ``checkpoint``
busy/log/checkpointed counts. stdout never includes host paths, secrets, SQL,
or provider stderr. stderr is stable and human-readable.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import signal
import sqlite3
import stat
import sys
import threading
from pathlib import Path

from gateway_repository_service.control_db import (
    CONTROL_DB_USER_VERSION,
    ControlDbError,
    ControlDbNewerVersionError,
    ControlStore,
)
from gateway_repository_service.layout import LAYOUT_FORMAT_VERSION, DurableLayout, LayoutError
from gateway_repository_service.locking import DurableRootLock, RootLockBusy
from gateway_repository_service.settings import RepositoryServiceSettings

HOLD_PROTOCOL_SCHEMA_VERSION = 1

EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_LOCK_BUSY = 3
EXIT_LAYOUT_OR_CONTROL_DB = 4
EXIT_CHECKPOINT = 5

_REQUIRED_EXISTING_COMPONENTS = ("control", "versioned", "service_state", "provider")


def _assert_root_containment(layout: DurableLayout) -> None:
    root = layout.root
    for attribute in _REQUIRED_EXISTING_COMPONENTS:
        path = getattr(layout, attribute)
        try:
            resolved = path.resolve()
        except OSError as exc:
            raise LayoutError("layout component is unavailable") from exc
        if not resolved.is_relative_to(root):
            raise LayoutError("layout component escapes the durable root")
        if not path.exists():
            continue
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise LayoutError("layout component is unavailable") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise LayoutError("layout component is a symlink")
        if not stat.S_ISDIR(metadata.st_mode):
            raise LayoutError("layout component is not a directory")

    marker = layout.layout_marker
    try:
        marker_metadata = marker.lstat()
    except OSError as exc:
        raise LayoutError("control layout marker is unreadable") from exc
    if stat.S_ISLNK(marker_metadata.st_mode):
        raise LayoutError("control layout marker is a symlink")
    if not stat.S_ISREG(marker_metadata.st_mode):
        raise LayoutError("control layout marker is invalid")


def _bind_snapshot_layout(settings: RepositoryServiceSettings) -> DurableLayout:
    data_root = settings.data_root.expanduser().resolve()
    if not data_root.is_dir():
        raise LayoutError("data root does not exist")
    layout = DurableLayout.bind_existing(data_root)
    _assert_root_containment(layout)
    try:
        layout.assert_same_filesystem()
    except RuntimeError as exc:
        raise LayoutError("publication components must share one filesystem") from exc
    return layout


def _open_control_store(settings: RepositoryServiceSettings) -> ControlStore:
    ControlStore.preflight_exact_version(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
    )
    return ControlStore.open(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=settings.sqlite_busy_timeout_ms,
        allow_migration=False,
    )


def _discard_broken_stdout() -> None:
    try:
        sys.stdout.flush()
    except OSError:
        pass
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(devnull, sys.stdout.fileno())
        finally:
            os.close(devnull)
    except OSError:
        try:
            sys.stdout.close()
        except OSError:
            pass


def _emit_ready_json(*, checkpoint_busy: int, checkpoint_log: int, checkpointed: int) -> None:
    summary = {
        "action": "hold",
        "checkpoint": {
            "busy": checkpoint_busy,
            "checkpointed": checkpointed,
            "log": checkpoint_log,
        },
        "control_db_user_version": CONTROL_DB_USER_VERSION,
        "layout_format_version": LAYOUT_FORMAT_VERSION,
        "schema_version": HOLD_PROTOCOL_SCHEMA_VERSION,
        "status": "ready",
    }
    sys.stdout.write(json.dumps(summary, separators=(",", ":"), sort_keys=True) + "\n")
    sys.stdout.flush()


def _run_hold(settings: RepositoryServiceSettings) -> int:
    stop = threading.Event()
    ready_emitted = False

    def _handle_signal(_signum: int, _frame: object) -> None:
        nonlocal ready_emitted
        stop.set()
        if not ready_emitted:
            raise SystemExit(EXIT_FAILURE)

    previous_int = signal.signal(signal.SIGINT, _handle_signal)
    previous_term = signal.signal(signal.SIGTERM, _handle_signal)
    root_lock: DurableRootLock | None = None
    control_store: ControlStore | None = None
    try:
        try:
            layout = _bind_snapshot_layout(settings)
        except LayoutError as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_LAYOUT_OR_CONTROL_DB

        root_lock = DurableRootLock(layout.service_lock)
        try:
            root_lock.acquire()
        except RootLockBusy:
            print("durable root lock is held by a running service", file=sys.stderr)
            return EXIT_LOCK_BUSY

        try:
            control_store = _open_control_store(settings)
        except (ControlDbNewerVersionError, ControlDbError, sqlite3.Error) as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_LAYOUT_OR_CONTROL_DB

        try:
            checkpoint = control_store.checkpoint_wal_truncate()
        except ControlDbError as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_CHECKPOINT
        if not checkpoint.is_quiescent():
            print("control database checkpoint did not complete", file=sys.stderr)
            return EXIT_CHECKPOINT

        control_store.close()
        control_store = None

        try:
            _emit_ready_json(
                checkpoint_busy=checkpoint.busy,
                checkpoint_log=checkpoint.log,
                checkpointed=checkpoint.checkpointed,
            )
        except BrokenPipeError:
            print("snapshot hold output is unavailable", file=sys.stderr)
            _discard_broken_stdout()
            return EXIT_FAILURE
        except OSError as exc:
            if exc.errno not in {errno.EPIPE, errno.EINVAL}:
                raise
            print("snapshot hold output is unavailable", file=sys.stderr)
            _discard_broken_stdout()
            return EXIT_FAILURE

        ready_emitted = True
        stop.wait()
        return 0
    except KeyboardInterrupt:
        if ready_emitted:
            return 0
        return EXIT_FAILURE
    finally:
        if control_store is not None:
            control_store.close()
        if root_lock is not None and root_lock.is_held():
            root_lock.release()
        signal.signal(signal.SIGINT, previous_int)
        signal.signal(signal.SIGTERM, previous_term)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Private operator CLI for quiescent durable-root snapshot hold"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    hold_parser = subparsers.add_parser("hold")
    hold_parser.add_argument("--data-root", type=Path)
    args = parser.parse_args(argv)

    settings = RepositoryServiceSettings()
    if args.data_root is not None:
        settings = settings.model_copy(update={"data_root": args.data_root})

    if args.command == "hold":
        raise SystemExit(_run_hold(settings))
    raise SystemExit(EXIT_USAGE)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        _discard_broken_stdout()
        raise SystemExit(EXIT_FAILURE)
