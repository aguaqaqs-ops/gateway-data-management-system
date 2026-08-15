"""Private snapshot hold CLI: lock, WAL checkpoint, ready JSON, and signal-safe hold."""

from __future__ import annotations

import json
import os
import signal
import sqlite3
from pathlib import Path

import pytest

from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION
from gateway_repository_service.locking import DurableRootLock, RootLockBusy
from gateway_repository_service.runtime import ServiceRuntime, ServiceStartupError
from support.snapshot_admin_harness import (
    SnapshotHoldEnvironment,
    assert_safe_ready_json,
    run_hold,
    run_snapshot_admin,
    set_control_db_user_version,
    spawn_hold,
    terminate_hold,
    wait_ready_json,
)

CONTROL_DB_FAULTS = (
    "missing",
    "garbage",
    "older",
    "newer",
)


def _digest(path: Path) -> bytes:
    return path.read_bytes()


def test_missing_command_exits_2() -> None:
    result = run_snapshot_admin()
    assert result.returncode == 2
    assert result.stdout == ""


def test_unknown_command_exits_2() -> None:
    result = run_snapshot_admin("check")
    assert result.returncode == 2
    assert result.stdout == ""


def test_missing_data_root_exits_4(tmp_path: Path) -> None:
    result = run_hold(tmp_path / "missing-root")
    assert result.returncode == 4
    assert result.stdout == ""
    assert "ready" not in result.stdout
    assert "Traceback" not in result.stderr


def test_uninitialized_layout_exits_4(tmp_path: Path) -> None:
    data_root = tmp_path / "empty-root"
    data_root.mkdir()
    result = run_hold(data_root)
    assert result.returncode == 4
    assert result.stdout == ""
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("fault", CONTROL_DB_FAULTS)
def test_malformed_control_db_exits_4_without_create_or_migrate(
    tmp_path: Path,
    fault: str,
) -> None:
    with SnapshotHoldEnvironment.create(tmp_path) as env:
        db_path = env.settings.control_db_path
        env.close()
        if fault == "missing":
            db_path.unlink()
            Path(str(db_path) + "-wal").unlink(missing_ok=True)
            Path(str(db_path) + "-shm").unlink(missing_ok=True)
        elif fault == "garbage":
            db_path.write_bytes(b"not-a-database")
        elif fault == "older":
            set_control_db_user_version(db_path, 1)
        else:
            set_control_db_user_version(db_path, CONTROL_DB_USER_VERSION + 1)

        existed_before = db_path.exists()
        before = _digest(db_path) if existed_before else b""
        result = env.run_hold()
        assert result.returncode == 4
        assert result.stdout == ""
        assert "ready" not in result.stdout
        assert "Traceback" not in result.stderr
        if fault == "missing":
            assert not db_path.exists()
        else:
            assert db_path.exists()
            assert _digest(db_path) == before
            connection = sqlite3.connect(db_path)
            try:
                if fault == "older":
                    assert int(connection.execute("PRAGMA user_version").fetchone()[0]) == 1
                elif fault == "newer":
                    assert (
                        int(connection.execute("PRAGMA user_version").fetchone()[0])
                        == CONTROL_DB_USER_VERSION + 1
                    )
            except sqlite3.Error:
                assert fault == "garbage"
            finally:
                connection.close()


def test_symlink_layout_component_exits_4(tmp_path: Path) -> None:
    with SnapshotHoldEnvironment.create(tmp_path) as env:
        env.close()
        target = tmp_path / "escaped-versioned"
        target.mkdir()
        env.layout.versioned.rmdir()
        env.layout.versioned.symlink_to(target)
        result = env.run_hold()
        assert result.returncode == 4
        assert result.stdout == ""
        assert "Traceback" not in result.stderr


def test_checkpoint_truncate_is_quiescent_without_helper(tmp_path: Path) -> None:
    with SnapshotHoldEnvironment.create(tmp_path) as env:
        env.seed_uncheckpointed_write()
        assert env.wal_path.exists()
        assert env.wal_path.stat().st_size > 0
        result = env.control_store.checkpoint_wal_truncate()
        assert result.is_quiescent()
        assert not env.wal_path.exists() or env.wal_path.stat().st_size == 0


@pytest.mark.serial
def test_hold_checkpoints_and_holds_root_lock(tmp_path: Path) -> None:
    with SnapshotHoldEnvironment.create(tmp_path) as env:
        env.seed_uncheckpointed_write()
        assert env.wal_path.stat().st_size > 0
        env.close()
        process = env.spawn_hold()
        try:
            payload = wait_ready_json(process)
            raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
            assert_safe_ready_json(payload, raw)
            assert not env.wal_path.exists() or env.wal_path.stat().st_size == 0
            with pytest.raises(RootLockBusy):
                DurableRootLock(env.layout.service_lock).acquire()
            second = env.run_hold()
            assert second.returncode == 3
            assert second.stdout == ""
            assert "ready" not in second.stdout
            with pytest.raises(ServiceStartupError, match="durable root lock is held"):
                ServiceRuntime.start(env.settings)
        finally:
            exit_code = terminate_hold(process)
        assert exit_code == 0
        with DurableRootLock(env.layout.service_lock):
            pass


@pytest.mark.serial
def test_running_holder_makes_hold_fail_closed(tmp_path: Path) -> None:
    with SnapshotHoldEnvironment.create(tmp_path) as env:
        env.close()
        holder = DurableRootLock(env.layout.service_lock)
        try:
            holder.acquire()
            result = env.run_hold()
            assert result.returncode == 3
            assert result.stdout == ""
            assert "ready" not in result.stdout
            assert "Traceback" not in result.stderr
        finally:
            holder.release()


@pytest.mark.serial
def test_active_sqlite_writer_makes_checkpoint_fail_closed(tmp_path: Path) -> None:
    with SnapshotHoldEnvironment.create(tmp_path) as env:
        env.begin_immediate()
        result = env.run_hold()
        assert result.returncode == 5
        assert result.stdout == ""
        assert "ready" not in result.stdout
        assert "Traceback" not in result.stderr
        env.control_store.connection.rollback()


@pytest.mark.serial
@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_ready_signal_releases_lock(tmp_path: Path, sig: int) -> None:
    with SnapshotHoldEnvironment.create(tmp_path) as env:
        env.close()
        process = env.spawn_hold()
        try:
            payload = wait_ready_json(process)
            assert payload["status"] == "ready"
            exit_code = terminate_hold(process, sig=sig)
        except Exception:
            terminate_hold(process, sig=signal.SIGKILL)
            raise
        assert exit_code == 0
        with DurableRootLock(env.layout.service_lock):
            pass


@pytest.mark.serial
def test_signal_before_ready_fails_closed_and_releases_lock(tmp_path: Path) -> None:
    with SnapshotHoldEnvironment.create(tmp_path) as env:
        env.begin_immediate()
        process = env.spawn_hold()
        try:
            exit_code = terminate_hold(process, sig=signal.SIGINT)
        finally:
            env.control_store.connection.rollback()
        assert exit_code != 0
        assert process.stdout is not None
        leftover = process.stdout.read()
        assert "ready" not in leftover
        with DurableRootLock(env.layout.service_lock):
            pass


@pytest.mark.serial
def test_broken_stdout_fails_closed_and_releases_lock(tmp_path: Path) -> None:
    with SnapshotHoldEnvironment.create(tmp_path) as env:
        env.close()
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        process = spawn_hold(env.data_root, stdout=write_fd)
        try:
            os.close(write_fd)
            exit_code = process.wait(timeout=10)
        except Exception:
            os.close(write_fd)
            terminate_hold(process, sig=signal.SIGKILL)
            raise
        assert exit_code == 1
        stderr = process.stderr.read() if process.stderr is not None else ""
        assert "Traceback" not in stderr
        with DurableRootLock(env.layout.service_lock):
            pass


@pytest.mark.serial
def test_ready_json_omits_host_paths_and_secrets(tmp_path: Path) -> None:
    with SnapshotHoldEnvironment.create(tmp_path) as env:
        env.close()
        process = env.spawn_hold()
        try:
            payload = wait_ready_json(process)
            raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
            assert_safe_ready_json(payload, raw)
            assert str(env.data_root) not in raw
            assert "service.lock" not in raw
        finally:
            assert terminate_hold(process) == 0
