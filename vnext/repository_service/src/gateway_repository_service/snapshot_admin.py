"""Private operator CLI for quiescent whole-root snapshot hold and check.

Invocation (operator/runbook, not a public API):

    python -m gateway_repository_service.snapshot_admin hold [--data-root PATH]
    python -m gateway_repository_service.snapshot_admin check [--data-root PATH]

``hold`` binds an existing durable root, takes the exclusive root lock, runs
``PRAGMA wal_checkpoint(TRUNCATE)``, flushes one machine-readable ready JSON
line, then holds the lock until SIGINT or SIGTERM. Helper liveness is the
snapshot window; there is no ready file, stdin protocol, or daemon.

``check`` takes the same exclusive lock, opens the control DB read-only, verifies
layout/SQLite integrity/artifact bindings and offline Dolt readability, then
flushes one passed JSON line and exits. It does not copy, repair, migrate, or
start the Service.

Private exit codes:

- ``0``: hold ready JSON was flushed and SIGINT/SIGTERM ended the hold, or
  check passed JSON was flushed
- ``2``: usage / argparse error
- ``3``: durable root lock is busy
- ``4``: layout or control DB missing, malformed, unreadable, wrong version,
  schema, integrity, or foreign-key failure
- ``5``: WAL checkpoint busy, leftover frames, or checkpoint error
- ``6``: restored artifact binding or registered Dolt repository is invalid
- ``1``: signal before ready, stdout failure, or other bounded failure

JSON summaries never include host paths, secrets, SQL, repository identifiers,
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
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from gateway_repository_service.artifact_retention import (
    decide_artifact_bytes_deletion,
    retention_explains_missing_ready_bytes,
)
from gateway_repository_service.control_db import (
    CONTROL_DB_USER_VERSION,
    ControlDbError,
    ControlDbNewerVersionError,
    ControlStore,
)
from gateway_repository_service.layout import LAYOUT_FORMAT_VERSION, DurableLayout, LayoutError
from gateway_repository_service.locking import DurableRootLock, RootLockBusy
from gateway_repository_service.mutation_store import (
    ArtifactLifecycleRecord,
    MutationStore,
    MutationStoreInvariantError,
)
from gateway_repository_service.process import DoltRunner, ProcessBoundaryError
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.admission_pin import (
    OwnedPathError,
    open_owned_ready_artifact,
)
from gateway_repository_service.upload_artifact.visibility import verify_published_artifact_fd
from gateway_repository_service.versioned_import.models import ImportStoreInvariantError
from gateway_repository_service.versioned_import.store import ImportOperationStore

SNAPSHOT_ADMIN_SCHEMA_VERSION = 1

EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_LOCK_BUSY = 3
EXIT_LAYOUT_OR_CONTROL_DB = 4
EXIT_CHECKPOINT = 5
EXIT_CONTENT = 6

_REQUIRED_EXISTING_COMPONENTS = ("control", "versioned", "service_state", "provider")
_HEAD_PROBE_SQL = "SELECT HASHOF('main') AS commit_id;\n"


class SnapshotContentError(RuntimeError):
    """Raised when restored durable content does not match control bindings."""


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


def _open_control_store_readonly(settings: RepositoryServiceSettings) -> ControlStore:
    return ControlStore.open_readonly(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
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


def _emit_json_summary(summary: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(summary, separators=(",", ":"), sort_keys=True) + "\n")
    sys.stdout.flush()


def _emit_ready_json(*, checkpoint_busy: int, checkpoint_log: int, checkpointed: int) -> None:
    _emit_json_summary(
        {
            "action": "hold",
            "checkpoint": {
                "busy": checkpoint_busy,
                "checkpointed": checkpointed,
                "log": checkpoint_log,
            },
            "control_db_user_version": CONTROL_DB_USER_VERSION,
            "layout_format_version": LAYOUT_FORMAT_VERSION,
            "schema_version": SNAPSHOT_ADMIN_SCHEMA_VERSION,
            "status": "ready",
        }
    )


def _emit_passed_json(*, repository_count: int, artifact_count: int) -> None:
    _emit_json_summary(
        {
            "action": "check",
            "artifact_count": artifact_count,
            "control_db_user_version": CONTROL_DB_USER_VERSION,
            "layout_format_version": LAYOUT_FORMAT_VERSION,
            "repository_count": repository_count,
            "schema_version": SNAPSHOT_ADMIN_SCHEMA_VERSION,
            "status": "passed",
        }
    )


def _missing_ready_bytes_are_explained(
    import_store: ImportOperationStore,
    lifecycle: ArtifactLifecycleRecord,
    *,
    ttl_seconds: int,
) -> bool:
    references = import_store.list_artifact_references_readonly(lifecycle.artifact_id)
    consumed_operation_artifact_id = None
    if lifecycle.consumed_by_operation_id is not None:
        for reference in references:
            if reference.operation_id == lifecycle.consumed_by_operation_id:
                consumed_operation_artifact_id = reference.result_artifact_id
                break
    if retention_explains_missing_ready_bytes(
        lifecycle=lifecycle,
        repository_id=lifecycle.repository_id,
        references=references,
        ttl_seconds=ttl_seconds,
        consumed_operation_artifact_id=consumed_operation_artifact_id,
    ):
        return True
    return decide_artifact_bytes_deletion(
        lifecycle=lifecycle,
        references=references,
        now=datetime.now(UTC),
        ttl_seconds=ttl_seconds,
    ).eligible


def _verify_artifact_bindings(
    layout: DurableLayout,
    control_store: ControlStore,
    settings: RepositoryServiceSettings,
) -> int:
    mutation_store = MutationStore(control_store.connection, transaction_lock=control_store.transaction_lock)
    import_store = ImportOperationStore(
        control_store.connection,
        transaction_lock=control_store.transaction_lock,
    )
    try:
        lifecycles = mutation_store.list_artifact_lifecycles()
    except MutationStoreInvariantError as exc:
        raise SnapshotContentError("restored artifact binding is invalid") from exc
    for lifecycle in lifecycles:
        file_fd = -1
        ready_dir_fd = -1
        try:
            file_fd, ready_dir_fd = open_owned_ready_artifact(
                layout,
                lifecycle.repository_id,
                lifecycle.artifact_id,
            )
        except OwnedPathError as exc:
            message = str(exc)
            if "missing" in message and _missing_ready_bytes_are_explained(
                import_store,
                lifecycle,
                ttl_seconds=settings.artifact_ttl_seconds,
            ):
                continue
            raise SnapshotContentError("restored artifact binding is invalid") from exc
        try:
            if not verify_published_artifact_fd(
                file_fd,
                size_bytes=lifecycle.size_bytes,
                raw_sha256=lifecycle.raw_sha256,
            ):
                raise SnapshotContentError("restored artifact binding is invalid")
        finally:
            if file_fd >= 0:
                os.close(file_fd)
            if ready_dir_fd >= 0:
                os.close(ready_dir_fd)
    return len(lifecycles)


def _assert_published_repository(layout: DurableLayout, repository_id: UUID) -> Path:
    published = layout.published_repository(repository_id.hex)
    try:
        metadata = published.lstat()
    except OSError as exc:
        raise SnapshotContentError("registered repository is unreadable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise SnapshotContentError("registered repository is unreadable")
    try:
        resolved = published.resolve()
    except OSError as exc:
        raise SnapshotContentError("registered repository is unreadable") from exc
    if not resolved.is_relative_to(layout.root):
        raise SnapshotContentError("registered repository is unreadable")
    dolt_dir = published / ".dolt"
    try:
        dolt_metadata = dolt_dir.lstat()
    except OSError as exc:
        raise SnapshotContentError("registered repository is unreadable") from exc
    if stat.S_ISLNK(dolt_metadata.st_mode) or not stat.S_ISDIR(dolt_metadata.st_mode):
        raise SnapshotContentError("registered repository is unreadable")
    return published


def _parse_head_commit_id(stdout: bytes) -> str:
    payload = json.loads(stdout.decode("utf-8"))
    rows: object
    if isinstance(payload, dict) and "rows" in payload:
        rows = payload["rows"]
    else:
        rows = payload
    if not isinstance(rows, list) or not rows:
        raise SnapshotContentError("registered repository is unreadable")
    first = rows[0]
    commit_id: object
    if isinstance(first, dict):
        commit_id = first.get("commit_id")
        if commit_id is None:
            values = list(first.values())
            commit_id = values[0] if values else None
    elif isinstance(first, list) and first:
        commit_id = first[0]
    else:
        commit_id = first
    if not isinstance(commit_id, str) or not commit_id:
        raise SnapshotContentError("registered repository is unreadable")
    return commit_id


def _probe_registered_repositories(
    settings: RepositoryServiceSettings,
    layout: DurableLayout,
    control_store: ControlStore,
) -> int:
    mutation_store = MutationStore(control_store.connection, transaction_lock=control_store.transaction_lock)
    try:
        repository_ids = mutation_store.list_succeeded_create_repository_ids()
    except MutationStoreInvariantError as exc:
        raise SnapshotContentError("registered repository is unreadable") from exc
    published_paths = [_assert_published_repository(layout, repository_id) for repository_id in repository_ids]
    if not published_paths:
        return 0
    with tempfile.TemporaryDirectory(prefix="snapshot-check-dolt-") as temp:
        home = Path(temp) / "home"
        tmpdir = Path(temp) / "tmp"
        home.mkdir()
        tmpdir.mkdir()
        query_path = home / "probe.sql"
        query_path.write_text(_HEAD_PROBE_SQL, encoding="utf-8")
        runner: DoltRunner | None = None
        try:
            runner = DoltRunner(settings, layout.root, home=home, tmpdir=tmpdir)
            for published in published_paths:
                try:
                    result = runner.run(
                        "head",
                        ["sql", "--result-format=json"],
                        cwd=published,
                        timeout=settings.metadata_timeout_seconds,
                        stdin_path=query_path,
                        capture_stdout=True,
                    )
                except (ProcessBoundaryError, OSError) as exc:
                    raise SnapshotContentError("registered repository is unreadable") from exc
                if result.timed_out or result.cancelled or result.exit_code != 0:
                    raise SnapshotContentError("registered repository is unreadable")
                try:
                    _parse_head_commit_id(result.stdout)
                except (json.JSONDecodeError, UnicodeDecodeError, SnapshotContentError) as exc:
                    raise SnapshotContentError("registered repository is unreadable") from exc
        finally:
            if runner is not None:
                runner.terminate_active_children()
    return len(published_paths)


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


def _run_check(settings: RepositoryServiceSettings) -> int:
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
            control_store = _open_control_store_readonly(settings)
            control_store.verify_readonly_integrity()
        except (ControlDbNewerVersionError, ControlDbError, sqlite3.Error) as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_LAYOUT_OR_CONTROL_DB

        try:
            artifact_count = _verify_artifact_bindings(layout, control_store, settings)
            repository_count = _probe_registered_repositories(settings, layout, control_store)
        except (SnapshotContentError, MutationStoreInvariantError, ImportStoreInvariantError) as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_CONTENT
        except sqlite3.Error as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_LAYOUT_OR_CONTROL_DB

        control_store.close()
        control_store = None

        try:
            _emit_passed_json(
                repository_count=repository_count,
                artifact_count=artifact_count,
            )
        except BrokenPipeError:
            print("snapshot check output is unavailable", file=sys.stderr)
            _discard_broken_stdout()
            return EXIT_FAILURE
        except OSError as exc:
            if exc.errno not in {errno.EPIPE, errno.EINVAL}:
                raise
            print("snapshot check output is unavailable", file=sys.stderr)
            _discard_broken_stdout()
            return EXIT_FAILURE
        return 0
    finally:
        if control_store is not None:
            control_store.close()
        if root_lock is not None and root_lock.is_held():
            root_lock.release()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Private operator CLI for quiescent durable-root snapshot hold and check"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    hold_parser = subparsers.add_parser("hold")
    hold_parser.add_argument("--data-root", type=Path)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--data-root", type=Path)
    args = parser.parse_args(argv)

    settings = RepositoryServiceSettings()
    if args.data_root is not None:
        settings = settings.model_copy(update={"data_root": args.data_root})

    if args.command == "hold":
        raise SystemExit(_run_hold(settings))
    if args.command == "check":
        raise SystemExit(_run_check(settings))
    raise SystemExit(EXIT_USAGE)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        _discard_broken_stdout()
        raise SystemExit(EXIT_FAILURE)
