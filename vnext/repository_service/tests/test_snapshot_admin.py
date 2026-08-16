"""Private snapshot hold/check CLI: lock, checkpoint, integrity, and Dolt probe."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from gateway_repository_contracts import encode_commit_id_path_segment
from gateway_repository_service.app import create_app
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION
from gateway_repository_service.locking import DurableRootLock, RootLockBusy
from gateway_repository_service.mutation_fingerprints import CREATE_REPOSITORY_FINGERPRINT_V1
from gateway_repository_service.mutation_store import IdempotencyScope, MutationStore
from gateway_repository_service.runtime import ServiceRuntime, ServiceStartupError
from support.http_harness import import_headers
from support.import_admission_crash_harness import build_import_package_bytes
from support.lifecycle_harness import lifecycle_settings
from support.snapshot_admin_harness import (
    RestoreProcedureError,
    SnapshotHoldEnvironment,
    assert_empty_restore_target,
    assert_safe_passed_json,
    assert_safe_ready_json,
    copy_whole_root,
    list_dolt_pids,
    run_check,
    run_hold,
    run_snapshot_admin,
    set_control_db_user_version,
    snapshot_admin_command,
    snapshot_admin_env,
    snapshot_check_temp_homes,
    snapshot_query_temps,
    spawn_hold,
    terminate_hold,
    wait_ready_json,
)
from support.upload_harness import create_repository, upload_headers, upload_sha256

pytestmark = pytest.mark.serial

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
    result = run_snapshot_admin("restore")
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


@pytest.mark.parametrize("command", ["hold", "check"])
@pytest.mark.parametrize("fault", ["missing", "symlink"])
def test_admin_requires_existing_regular_root_lock(
    tmp_path: Path,
    command: str,
    fault: str,
) -> None:
    with SnapshotHoldEnvironment.create(tmp_path) as env:
        env.close()
        env.layout.service_lock.unlink()
        escaped = tmp_path / "escaped-lock"
        if fault == "symlink":
            escaped.touch()
            env.layout.service_lock.symlink_to(escaped)
        result = run_snapshot_admin(command, "--data-root", str(env.data_root))
        assert result.returncode == 4
        assert result.stdout == ""
        assert "Traceback" not in result.stderr
        if fault == "missing":
            assert not env.layout.service_lock.exists()
        else:
            assert env.layout.service_lock.is_symlink()


@pytest.mark.parametrize("command", ["hold", "check"])
def test_admin_rejects_symlink_data_root(tmp_path: Path, command: str) -> None:
    with SnapshotHoldEnvironment.create(tmp_path / "real") as env:
        env.close()
        linked_root = tmp_path / "linked-root"
        linked_root.symlink_to(env.data_root, target_is_directory=True)
        result = run_snapshot_admin(command, "--data-root", str(linked_root))
    assert result.returncode == 4
    assert result.stdout == ""
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("command", ["hold", "check"])
def test_admin_rejects_control_database_symlink(tmp_path: Path, command: str) -> None:
    with SnapshotHoldEnvironment.create(tmp_path) as env:
        db_path = env.settings.control_db_path
        env.close()
        escaped = tmp_path / "escaped-control.sqlite3"
        db_path.rename(escaped)
        before = escaped.read_bytes()
        db_path.symlink_to(escaped)
        result = run_snapshot_admin(command, "--data-root", str(env.data_root))
    assert result.returncode == 4
    assert result.stdout == ""
    assert "Traceback" not in result.stderr
    assert escaped.read_bytes() == before


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


@dataclass(frozen=True)
class CheckFault:
    name: str
    exit_code: int
    needs_dolt: bool = False


CHECK_FAULTS = (
    CheckFault("layout_marker_garbage", 4),
    CheckFault("component_symlink", 4),
    CheckFault("component_cross_root", 4),
    CheckFault("component_missing", 4),
    CheckFault("optional_component_symlink", 4),
    CheckFault("control_db_missing", 4),
    CheckFault("control_db_garbage", 4),
    CheckFault("control_db_older", 4),
    CheckFault("control_db_newer", 4),
    CheckFault("control_db_schema", 4),
    CheckFault("control_db_fk", 4),
    CheckFault("control_db_nonquiescent_wal", 4),
    CheckFault("artifact_missing_required", 6),
    CheckFault("artifact_digest_mismatch", 6),
    CheckFault("artifact_symlink", 6),
    CheckFault("dolt_unreadable", 6, needs_dolt=True),
)

_UNIT_CHECK_FAULTS = tuple(fault for fault in CHECK_FAULTS if not fault.needs_dolt)
_DOLT_CHECK_FAULTS = tuple(fault for fault in CHECK_FAULTS if fault.needs_dolt)


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _insert_artifact_lifecycle(
    env: SnapshotHoldEnvironment,
    *,
    repository_id: UUID,
    artifact_id: UUID,
    payload: bytes,
    created_at: str,
    raw_sha256: str | None = None,
    bytes_deleted_at: str | None = None,
    cleanup_seq: int = 1,
) -> None:
    digest = raw_sha256 or hashlib.sha256(payload).hexdigest()
    env.control_store.connection.execute(
        """
        INSERT INTO artifact_lifecycle (
            artifact_id, repository_scope, media_type, size_bytes, raw_sha256,
            created_at, updated_at, cleanup_seq, bytes_deleted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(artifact_id),
            repository_id.hex,
            "application/vnd.gateway.repository-import.v1+tar+gz",
            len(payload),
            digest,
            created_at,
            created_at,
            cleanup_seq,
            bytes_deleted_at,
        ),
    )
    env.control_store.connection.commit()


def _corrupt_published_dolt(data_root: Path, repository_id: UUID) -> None:
    dolt_dir = data_root / "versioned" / repository_id.hex / ".dolt"
    files = [path for path in dolt_dir.rglob("*") if path.is_file()]
    for path in files:
        path.write_bytes(b"corrupt")


def _plant_ready_bytes(
    env: SnapshotHoldEnvironment,
    repository_id: UUID,
    artifact_id: UUID,
    payload: bytes,
) -> Path:
    ready = env.layout.artifacts / repository_id.hex / "ready"
    ready.mkdir(parents=True, exist_ok=True)
    path = ready / artifact_id.hex
    path.write_bytes(payload)
    return path


def _apply_unit_check_fault(env: SnapshotHoldEnvironment, tmp_path: Path, fault: str) -> None:
    db_path = env.settings.control_db_path
    if fault == "layout_marker_garbage":
        env.close()
        env.layout.layout_marker.write_text("not-json", encoding="utf-8")
        return
    if fault == "component_symlink":
        env.close()
        other = env.data_root / "other-versioned"
        other.mkdir()
        env.layout.versioned.rmdir()
        env.layout.versioned.symlink_to(other)
        return
    if fault == "component_cross_root":
        env.close()
        escaped = tmp_path / "escaped-versioned"
        escaped.mkdir()
        env.layout.versioned.rmdir()
        env.layout.versioned.symlink_to(escaped)
        return
    if fault == "component_missing":
        env.close()
        env.layout.provider.rmdir()
        return
    if fault == "optional_component_symlink":
        env.close()
        env.layout.artifacts.symlink_to(tmp_path / "escaped-artifacts", target_is_directory=True)
        return
    if fault == "control_db_missing":
        env.close()
        db_path.unlink()
        Path(str(db_path) + "-wal").unlink(missing_ok=True)
        Path(str(db_path) + "-shm").unlink(missing_ok=True)
        return
    if fault == "control_db_garbage":
        env.close()
        db_path.write_bytes(b"not-a-database")
        return
    if fault == "control_db_older":
        env.close()
        set_control_db_user_version(db_path, 1)
        return
    if fault == "control_db_newer":
        env.close()
        set_control_db_user_version(db_path, CONTROL_DB_USER_VERSION + 1)
        return
    if fault == "control_db_schema":
        env.close()
        connection = sqlite3.connect(db_path)
        try:
            connection.execute("DROP TABLE artifact_residual")
            connection.commit()
        finally:
            connection.close()
        return
    if fault == "control_db_fk":
        env.close()
        connection = sqlite3.connect(db_path)
        try:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                """
                INSERT INTO synchronous_mutation_effects (
                    idempotency_id, resource_id, status, updated_at
                ) VALUES (?, ?, 'PENDING', ?)
                """,
                (99_999, str(uuid4()), _now_iso()),
            )
            connection.commit()
        finally:
            connection.close()
        return
    if fault == "control_db_nonquiescent_wal":
        env.close()
        Path(f"{db_path}-wal").write_bytes(b"not-a-quiescent-wal")
        return

    repository_id = uuid4()
    artifact_id = uuid4()
    payload = b"snapshot-check-artifact"
    if fault == "artifact_missing_required":
        _insert_artifact_lifecycle(
            env,
            repository_id=repository_id,
            artifact_id=artifact_id,
            payload=payload,
            created_at=_now_iso(),
        )
        env.close()
        return
    if fault == "artifact_digest_mismatch":
        _insert_artifact_lifecycle(
            env,
            repository_id=repository_id,
            artifact_id=artifact_id,
            payload=payload,
            created_at=_now_iso(),
        )
        _plant_ready_bytes(env, repository_id, artifact_id, b"different-bytes")
        env.close()
        return
    if fault == "artifact_symlink":
        _insert_artifact_lifecycle(
            env,
            repository_id=repository_id,
            artifact_id=artifact_id,
            payload=payload,
            created_at=_now_iso(),
        )
        ready = env.layout.artifacts / repository_id.hex / "ready"
        ready.mkdir(parents=True, exist_ok=True)
        target = tmp_path / "escaped-artifact"
        target.write_bytes(payload)
        (ready / artifact_id.hex).symlink_to(target)
        env.close()
        return
    raise AssertionError(f"unknown unit check fault {fault}")


def test_check_passes_empty_initialized_root(tmp_path: Path) -> None:
    with SnapshotHoldEnvironment.create(tmp_path) as env:
        staging_residual = env.layout.staging_versioned / "ordinary-residual"
        staging_residual.mkdir(parents=True, exist_ok=True)
        (staging_residual / "leftover").write_text("ok", encoding="utf-8")
        extra = env.layout.versioned / "not-a-registered-repo"
        extra.mkdir()
        env.close()
        wal_path = Path(f"{env.settings.control_db_path}-wal")
        shm_path = Path(f"{env.settings.control_db_path}-shm")
        wal_path.unlink(missing_ok=True)
        shm_path.unlink(missing_ok=True)
        result = env.run_check()
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    raw = result.stdout.strip()
    assert_safe_passed_json(payload, raw)
    assert payload["repository_count"] == 0
    assert payload["artifact_count"] == 0
    assert result.stdout.count("\n") == 1
    assert not wal_path.exists()
    assert not shm_path.exists()
    assert not snapshot_check_temp_homes()


def test_dolt_initialization_failure_is_redacted_content_error(tmp_path: Path) -> None:
    with SnapshotHoldEnvironment.create(tmp_path) as env:
        repository_id = uuid4()
        mutation_store = MutationStore(
            env.control_store.connection,
            transaction_lock=env.control_store.transaction_lock,
        )
        effect = mutation_store.allocate_pending(
            IdempotencyScope.for_create(),
            key_hash=MutationStore.hash_idempotency_key("snapshot-missing-dolt"),
            fingerprint=CREATE_REPOSITORY_FINGERPRINT_V1,
            resource_id=repository_id,
        )
        mutation_store.mark_succeeded(effect.effect_id, response_body={})
        published = env.layout.published_repository(repository_id.hex)
        (published / ".dolt").mkdir(parents=True)
        env.close()
        missing_dolt = tmp_path / "missing-dolt"
        result = env.run_check(env={"GATEWAY_REPOSITORY_DOLT_BINARY": str(missing_dolt)})
    assert result.returncode == 6
    assert result.stdout == ""
    assert result.stderr.strip() == "registered repository is unreadable"
    assert "Traceback" not in result.stderr
    assert str(tmp_path) not in result.stderr
    assert not snapshot_check_temp_homes()


@pytest.mark.serial
def test_signal_during_dolt_check_reaps_child_and_releases_lock(tmp_path: Path) -> None:
    with SnapshotHoldEnvironment.create(tmp_path) as env:
        repository_id = uuid4()
        mutation_store = MutationStore(
            env.control_store.connection,
            transaction_lock=env.control_store.transaction_lock,
        )
        effect = mutation_store.allocate_pending(
            IdempotencyScope.for_create(),
            key_hash=MutationStore.hash_idempotency_key("snapshot-signal-dolt"),
            fingerprint=CREATE_REPOSITORY_FINGERPRINT_V1,
            resource_id=repository_id,
        )
        mutation_store.mark_succeeded(effect.effect_id, response_body={})
        published = env.layout.published_repository(repository_id.hex)
        (published / ".dolt").mkdir(parents=True)
        env.close()

        marker = tmp_path / "fake-dolt-running"
        fake_dolt = tmp_path / "fake-dolt"
        fake_dolt.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = version ]; then\n"
            "  echo 'dolt version 2.1.11'\n"
            "  exit 0\n"
            "fi\n"
            f"echo $$ > '{marker}'\n"
            "exec sleep 30\n",
            encoding="utf-8",
        )
        fake_dolt.chmod(0o755)
        process = subprocess.Popen(
            [
                *snapshot_admin_command("check", "--data-root", str(env.data_root)),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=snapshot_admin_env(
                {"GATEWAY_REPOSITORY_DOLT_BINARY": str(fake_dolt)}
            ),
        )
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not marker.exists():
            time.sleep(0.01)
        assert marker.exists()
        child_pid = int(marker.read_text(encoding="utf-8"))
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=5.0)

    assert process.returncode == 1
    assert stdout == ""
    assert stderr.strip() == "snapshot check interrupted"
    assert not Path(f"/proc/{child_pid}").exists()
    with DurableRootLock(env.layout.service_lock):
        pass
    assert not snapshot_check_temp_homes()


def test_check_allows_eligible_missing_artifact_bytes(tmp_path: Path) -> None:
    created_at = (datetime.now(UTC) - timedelta(hours=48)).replace(microsecond=0).isoformat()
    with SnapshotHoldEnvironment.create(tmp_path) as env:
        _insert_artifact_lifecycle(
            env,
            repository_id=uuid4(),
            artifact_id=uuid4(),
            payload=b"expired-orphan",
            created_at=created_at,
        )
        env.close()
        result = env.run_check()
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert_safe_passed_json(payload, result.stdout.strip())
    assert payload["artifact_count"] == 1


@pytest.mark.parametrize("fault", _UNIT_CHECK_FAULTS, ids=lambda item: item.name)
def test_check_faults_fail_closed_without_passed_json(
    tmp_path: Path,
    fault: CheckFault,
) -> None:
    with SnapshotHoldEnvironment.create(tmp_path) as env:
        _apply_unit_check_fault(env, tmp_path, fault.name)
        result = env.run_check()
    assert result.returncode == fault.exit_code
    assert result.stdout == ""
    assert "passed" not in result.stdout
    assert "Traceback" not in result.stderr
    assert str(tmp_path) not in result.stderr
    assert "/" not in result.stdout


@pytest.mark.integration
@pytest.mark.serial
def test_check_passes_valid_whole_root(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    payload = b"snapshot-check-ready-bytes"
    with TestClient(create_app(settings)) as client:
        first = create_repository(client, idempotency_key="check-root-one")
        second = create_repository(client, idempotency_key="check-root-two")
        uploaded = client.post(
            f"/v1/repositories/{first}/artifacts",
            headers=upload_headers(idempotency_key="check-upload", payload=payload),
            content=payload,
        )
        assert uploaded.status_code == 201
        artifact_id = UUID(uploaded.json()["artifact_ref"]["artifact_id"])
    before_temps = snapshot_check_temp_homes()
    result = run_check(settings.data_root)
    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    assert_safe_passed_json(parsed, result.stdout.strip())
    assert parsed["repository_count"] == 2
    assert parsed["artifact_count"] == 1
    assert str(first) not in result.stdout
    assert str(second) not in result.stdout
    assert str(artifact_id) not in result.stdout
    assert str(settings.data_root) not in result.stdout
    assert snapshot_check_temp_homes() == before_temps
    assert snapshot_query_temps(settings.data_root) == []


@pytest.mark.integration
@pytest.mark.serial
def test_running_service_makes_check_fail_before_provider(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        ready = client.get("/readyz")
        assert ready.status_code == 200
        before = list_dolt_pids()
        result = run_check(settings.data_root)
        after = list_dolt_pids()
    assert result.returncode == 3
    assert result.stdout == ""
    assert "passed" not in result.stdout
    assert "Traceback" not in result.stderr
    assert after <= before


@pytest.mark.integration
@pytest.mark.serial
@pytest.mark.parametrize("fault", _DOLT_CHECK_FAULTS, ids=lambda item: item.name)
def test_multi_repository_check_does_not_omit_and_hides_paths(
    tmp_path: Path,
    fault: CheckFault,
) -> None:
    settings = lifecycle_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        first = create_repository(client, idempotency_key="check-multi-one")
        second = create_repository(client, idempotency_key="check-multi-two")
        first_hex = first.hex
        second_hex = second.hex
    _corrupt_published_dolt(settings.data_root, second)
    before_temps = snapshot_check_temp_homes()
    result = run_check(settings.data_root)
    assert result.returncode == fault.exit_code
    assert result.stdout == ""
    assert "passed" not in result.stdout
    assert first_hex not in result.stderr
    assert second_hex not in result.stderr
    assert str(settings.data_root) not in result.stderr
    assert "Traceback" not in result.stderr
    assert snapshot_check_temp_homes() == before_temps


@pytest.mark.integration
def test_check_does_not_mutate_business_files_schema_or_head(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    payload = b"immutable-artifact"
    with TestClient(create_app(settings)) as client:
        created = client.post(
            "/v1/repositories",
            headers={
                "Authorization": "Bearer test-bearer-token",
                "Idempotency-Key": "check-immutable",
            },
        )
        assert created.status_code == 201
        repository_id = UUID(created.json()["repository_id"])
        head = created.json()["initial_commit_id"]
        uploaded = client.post(
            f"/v1/repositories/{repository_id}/artifacts",
            headers=upload_headers(idempotency_key="check-immutable-upload", payload=payload),
            content=payload,
        )
        assert uploaded.status_code == 201
        artifact_id = UUID(uploaded.json()["artifact_ref"]["artifact_id"])
    ready_path = settings.data_root / "artifacts" / repository_id.hex / "ready" / artifact_id.hex
    before_db = settings.control_db_path.read_bytes()
    before_artifact = ready_path.read_bytes()
    connection = sqlite3.connect(settings.control_db_path)
    try:
        before_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    finally:
        connection.close()
    result = run_check(settings.data_root)
    assert result.returncode == 0, result.stderr
    payload_json = json.loads(result.stdout)
    assert_safe_passed_json(payload_json, result.stdout.strip())
    connection = sqlite3.connect(settings.control_db_path)
    try:
        after_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    finally:
        connection.close()
    assert after_version == before_version == CONTROL_DB_USER_VERSION
    assert ready_path.read_bytes() == before_artifact == payload
    assert settings.control_db_path.read_bytes() == before_db
    assert hashlib.sha256(before_artifact).hexdigest() == upload_sha256(payload)
    with TestClient(create_app(settings)) as client:
        replay = client.post(
            "/v1/repositories",
            headers={
                "Authorization": "Bearer test-bearer-token",
                "Idempotency-Key": "check-immutable",
            },
        )
    assert replay.status_code == 201
    assert replay.json()["initial_commit_id"] == head


@pytest.mark.integration
@pytest.mark.serial
def test_dolt_probe_failure_reaps_children_and_query_temp(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        repository_id = create_repository(client, idempotency_key="check-reap")
    _corrupt_published_dolt(settings.data_root, repository_id)
    before_temps = snapshot_check_temp_homes()
    result = run_check(settings.data_root)
    assert result.returncode == 6
    assert result.stdout == ""
    assert snapshot_check_temp_homes() == before_temps
    staging_artifacts = settings.data_root / "staging" / "artifacts"
    assert not staging_artifacts.exists() or not list(staging_artifacts.glob("query-*.sql"))


_AUTH_HEADERS = {"Authorization": "Bearer test-bearer-token"}
_IMPORT_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class IncompleteRestoreShape:
    name: str
    exit_code: int
    needs_dolt: bool = False


INCOMPLETE_RESTORE_SHAPES = (
    IncompleteRestoreShape("sqlite_only", 4),
    IncompleteRestoreShape("partial_component", 4),
    IncompleteRestoreShape("single_dolt", 6, needs_dolt=True),
)
_UNIT_INCOMPLETE_SHAPES = tuple(shape for shape in INCOMPLETE_RESTORE_SHAPES if not shape.needs_dolt)
_DOLT_INCOMPLETE_SHAPES = tuple(shape for shape in INCOMPLETE_RESTORE_SHAPES if shape.needs_dolt)


def _poll_succeeded(client: TestClient, repository_id: UUID, operation_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + _IMPORT_TIMEOUT_SECONDS
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(
            f"/v1/repositories/{repository_id}/operations/{operation_id}",
            headers=_AUTH_HEADERS,
        )
        assert response.status_code == 200
        operation = response.json()["operation"]
        assert isinstance(operation, dict)
        last = operation
        if operation["status"] in {"SUCCEEDED", "FAILED"}:
            assert operation["status"] == "SUCCEEDED", operation
            return operation
        time.sleep(0.05)
    raise AssertionError(f"import did not finish: {last}")


def _import_package(
    client: TestClient,
    *,
    repository_id: UUID,
    expected_commit_id: str,
    payload: bytes,
    idempotency_prefix: str,
) -> dict[str, Any]:
    uploaded = client.post(
        f"/v1/repositories/{repository_id}/artifacts",
        headers=upload_headers(idempotency_key=f"{idempotency_prefix}-upload", payload=payload),
        content=payload,
    )
    assert uploaded.status_code == 201, uploaded.text
    submitted = client.post(
        f"/v1/repositories/{repository_id}/versioned/imports",
        headers=import_headers(idempotency_key=f"{idempotency_prefix}-import"),
        content=json.dumps(
            {
                "repository_id": str(repository_id),
                "artifact_ref": uploaded.json()["artifact_ref"],
                "target_ref": "main",
                "expected_commit_id": expected_commit_id,
                "verification_policy": "STRUCTURAL",
                "unknown_type_policy": "REJECT",
            }
        ),
    )
    assert submitted.status_code == 202, submitted.text
    return _poll_succeeded(client, repository_id, str(submitted.json()["operation_id"]))


def _read_snapshot_facts(
    client: TestClient,
    repository_id: UUID,
    commit_id: str,
) -> dict[str, Any]:
    ready = client.get("/readyz")
    assert ready.status_code == 200
    ref = client.get(
        f"/v1/repositories/{repository_id}/versioned/refs/main",
        headers=_AUTH_HEADERS,
    )
    assert ref.status_code == 200, ref.text
    catalog = client.get(
        (
            f"/v1/repositories/{repository_id}/versioned/commits/"
            f"{encode_commit_id_path_segment(commit_id)}/catalog"
        ),
        headers=_AUTH_HEADERS,
    )
    assert catalog.status_code == 200, catalog.text
    return {"ref": ref.json(), "catalog": catalog.json()}


def _records_row_count(catalog_body: dict[str, Any]) -> int:
    tables = catalog_body["catalog"]["tables"]
    assert isinstance(tables, list)
    records = next(table for table in tables if table["name"] == "records")
    count = records["row_count"]
    assert isinstance(count, int)
    return count


def _file_digests(root: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            mapping[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return mapping


def _snapshot_archive_while_held(data_root: Path, archive: Path) -> dict[str, object]:
    process = spawn_hold(data_root)
    try:
        payload = wait_ready_json(process)
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        assert_safe_ready_json(payload, raw)
        copy_whole_root(data_root, archive)
    finally:
        assert terminate_hold(process) == 0
    return payload


def _apply_incomplete_restore(archive: Path, dest: Path, shape: str) -> None:
    assert_empty_restore_target(dest)
    if shape == "sqlite_only":
        dest.mkdir(parents=True)
        service_state = dest / "service-state"
        service_state.mkdir()
        copied = 0
        for path in (archive / "service-state").iterdir():
            if path.name.startswith("repository-service.sqlite3"):
                shutil.copy2(path, service_state / path.name)
                copied += 1
        assert copied > 0
        return
    if shape == "partial_component":
        shutil.copytree(archive, dest, symlinks=True)
        shutil.rmtree(dest / "control")
        return
    if shape == "single_dolt":
        shutil.copytree(archive, dest, symlinks=True)
        published = sorted(path for path in (dest / "versioned").iterdir() if path.is_dir())
        assert len(published) >= 2
        shutil.rmtree(published[-1])
        return
    raise AssertionError(f"unknown incomplete restore {shape}")


def test_restore_procedure_rejects_non_empty_overlay_target(tmp_path: Path) -> None:
    with SnapshotHoldEnvironment.create(tmp_path / "src") as src:
        src.close()
        archive = tmp_path / "archive"
        copy_whole_root(src.data_root, archive)
    with SnapshotHoldEnvironment.create(tmp_path / "dest") as dest:
        dest.close()
        before = _file_digests(dest.data_root)
        with pytest.raises(RestoreProcedureError, match="not empty"):
            copy_whole_root(archive, dest.data_root)
        assert _file_digests(dest.data_root) == before


@pytest.mark.integration
@pytest.mark.serial
def test_restore_procedure_rejects_live_root(tmp_path: Path) -> None:
    with SnapshotHoldEnvironment.create(tmp_path / "src") as src:
        src.close()
        archive = tmp_path / "archive"
        copy_whole_root(src.data_root, archive)
    settings = lifecycle_settings(tmp_path / "live")
    with TestClient(create_app(settings)) as client:
        assert client.get("/readyz").status_code == 200
        with pytest.raises(RestoreProcedureError, match="live"):
            copy_whole_root(archive, settings.data_root)


@pytest.mark.parametrize("shape", _UNIT_INCOMPLETE_SHAPES, ids=lambda item: item.name)
def test_incomplete_restore_copy_fails_check(tmp_path: Path, shape: IncompleteRestoreShape) -> None:
    with SnapshotHoldEnvironment.create(tmp_path / "src") as src:
        src.close()
        archive = tmp_path / "archive"
        copy_whole_root(src.data_root, archive)
    before = _file_digests(archive)
    dest = tmp_path / "restore" / "data-root"
    _apply_incomplete_restore(archive, dest, shape.name)
    result = run_check(dest)
    assert result.returncode == shape.exit_code
    assert result.stdout == ""
    assert "passed" not in result.stdout
    assert "Traceback" not in result.stderr
    assert _file_digests(archive) == before


@pytest.mark.integration
@pytest.mark.serial
@pytest.mark.parametrize("shape", _DOLT_INCOMPLETE_SHAPES, ids=lambda item: item.name)
def test_incomplete_restore_copy_fails_check_with_dolt(
    tmp_path: Path,
    shape: IncompleteRestoreShape,
) -> None:
    settings = lifecycle_settings(tmp_path / "src")
    with TestClient(create_app(settings)) as client:
        create_repository(client, idempotency_key="restore-one")
        create_repository(client, idempotency_key="restore-two")
    archive = tmp_path / "archive"
    _snapshot_archive_while_held(settings.data_root, archive)
    before = _file_digests(archive)
    dest = tmp_path / "restore" / "data-root"
    _apply_incomplete_restore(archive, dest, shape.name)
    result = run_check(dest)
    assert result.returncode == shape.exit_code
    assert result.stdout == ""
    assert "passed" not in result.stdout
    assert "Traceback" not in result.stderr
    assert str(tmp_path) not in result.stderr
    assert _file_digests(archive) == before
    assert snapshot_query_temps(dest) == []


@pytest.mark.integration
@pytest.mark.serial
def test_whole_root_restore_preserves_public_facts(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path / "src")
    payload = build_import_package_bytes()
    before_temps = snapshot_check_temp_homes()
    before_pids = list_dolt_pids()
    with TestClient(create_app(settings)) as client:
        created = client.post(
            "/v1/repositories",
            headers={**_AUTH_HEADERS, "Idempotency-Key": "restore-create"},
        )
        assert created.status_code == 201, created.text
        repository_id = UUID(created.json()["repository_id"])
        initial_commit_id = str(created.json()["initial_commit_id"])
        operation = _import_package(
            client,
            repository_id=repository_id,
            expected_commit_id=initial_commit_id,
            payload=payload,
            idempotency_prefix="restore-c1",
        )
        commit_id = str(operation["result"]["commit_id"])
        snapshot_facts = _read_snapshot_facts(client, repository_id, commit_id)
        assert snapshot_facts["ref"]["commit_id"] == commit_id
        assert _records_row_count(snapshot_facts["catalog"]) == 1

    archive = tmp_path / "archive"
    _snapshot_archive_while_held(settings.data_root, archive)

    with TestClient(create_app(settings)) as client:
        mutated = create_repository(client, idempotency_key="restore-mutation")
        mutation_ref = client.get(
            f"/v1/repositories/{mutated}/versioned/refs/main",
            headers=_AUTH_HEADERS,
        )
        assert mutation_ref.status_code == 200

    restore_settings = lifecycle_settings(tmp_path / "restore")
    copy_whole_root(archive, restore_settings.data_root)
    result = run_check(restore_settings.data_root)
    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    assert_safe_passed_json(parsed, result.stdout.strip())

    with TestClient(create_app(restore_settings)) as client:
        restored_facts = _read_snapshot_facts(client, repository_id, commit_id)
        assert restored_facts["ref"] == snapshot_facts["ref"]
        assert restored_facts["catalog"] == snapshot_facts["catalog"]
        missing = client.get(
            f"/v1/repositories/{mutated}/versioned/refs/main",
            headers=_AUTH_HEADERS,
        )
        assert missing.status_code == 404

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and list_dolt_pids() - before_pids:
        time.sleep(0.05)
    assert not (list_dolt_pids() - before_pids)
    assert snapshot_check_temp_homes() == before_temps
    assert snapshot_query_temps(settings.data_root) == []
    assert snapshot_query_temps(restore_settings.data_root) == []
