"""Shared helpers for private snapshot hold CLI tests."""

from __future__ import annotations

import json
import os
import select
import signal
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.settings import RepositoryServiceSettings
from support.lifecycle_harness import lifecycle_settings

HOLD_BUSY_TIMEOUT_MS = 200
HOLD_READY_TIMEOUT_SECONDS = 8.0
HOLD_EXIT_TIMEOUT_SECONDS = 5.0

FORBIDDEN_SUMMARY_SUBSTRINGS = (
    "token",
    "secret",
    "password",
    "pragma",
    "stderr",
    "traceback",
    "credential",
    "sql",
)


def snapshot_admin_command(*args: str) -> list[str]:
    return [sys.executable, "-m", "gateway_repository_service.snapshot_admin", *args]


def snapshot_admin_env(
    extra: dict[str, str] | None = None,
    *,
    busy_timeout_ms: int = HOLD_BUSY_TIMEOUT_MS,
) -> dict[str, str]:
    merged = os.environ.copy()
    merged.setdefault("GATEWAY_REPOSITORY_PROFILE", "test")
    merged["GATEWAY_REPOSITORY_SQLITE_BUSY_TIMEOUT_MS"] = str(busy_timeout_ms)
    if extra is not None:
        merged.update(extra)
    return merged


def run_snapshot_admin(
    *args: str,
    env: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        snapshot_admin_command(*args),
        check=False,
        capture_output=True,
        text=True,
        env=snapshot_admin_env(env),
        timeout=timeout,
    )


def run_hold(
    data_root: Path,
    *,
    env: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> subprocess.CompletedProcess[str]:
    return run_snapshot_admin("hold", "--data-root", str(data_root), env=env, timeout=timeout)


def spawn_hold(
    data_root: Path,
    *,
    env: dict[str, str] | None = None,
    stdout: int | None = subprocess.PIPE,
) -> subprocess.Popen[str]:
    return subprocess.Popen(
        snapshot_admin_command("hold", "--data-root", str(data_root)),
        stdout=stdout,
        stderr=subprocess.PIPE,
        text=True,
        env=snapshot_admin_env(env),
    )


def wait_ready_json(
    process: subprocess.Popen[str],
    *,
    timeout_seconds: float = HOLD_READY_TIMEOUT_SECONDS,
) -> dict[str, object]:
    stdout = process.stdout
    assert stdout is not None
    ready, _, _ = select.select([stdout], [], [], timeout_seconds)
    if not ready:
        terminate_hold(process)
        stderr = process.stderr.read() if process.stderr is not None else ""
        raise AssertionError(f"timed out waiting for ready JSON; stderr={stderr!r}")
    line = stdout.readline()
    if process.poll() is not None and not line:
        stderr = process.stderr.read() if process.stderr is not None else ""
        raise AssertionError(
            f"hold exited {process.returncode} before ready JSON; stderr={stderr!r}"
        )
    parsed = json.loads(line)
    assert isinstance(parsed, dict)
    return parsed


def terminate_hold(
    process: subprocess.Popen[str],
    *,
    sig: int = signal.SIGTERM,
    timeout_seconds: float = HOLD_EXIT_TIMEOUT_SECONDS,
) -> int:
    if process.poll() is None:
        try:
            process.send_signal(sig)
        except ProcessLookupError:
            pass
    try:
        return process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=HOLD_EXIT_TIMEOUT_SECONDS)
        raise


def set_control_db_user_version(path: Path, version: int) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(f"PRAGMA user_version = {int(version)}")
        connection.commit()
    finally:
        connection.close()


def assert_safe_ready_json(payload: dict[str, object], raw: str) -> None:
    assert payload["action"] == "hold"
    assert payload["status"] == "ready"
    assert payload["schema_version"] == 1
    assert payload["layout_format_version"] == 1
    assert payload["control_db_user_version"] == CONTROL_DB_USER_VERSION
    checkpoint = payload["checkpoint"]
    assert isinstance(checkpoint, dict)
    assert checkpoint["busy"] == 0
    assert checkpoint["log"] == checkpoint["checkpointed"]
    assert "/" not in raw
    lowered = raw.lower()
    for token in FORBIDDEN_SUMMARY_SUBSTRINGS:
        assert token not in lowered


def run_check(
    data_root: Path,
    *,
    env: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> subprocess.CompletedProcess[str]:
    return run_snapshot_admin("check", "--data-root", str(data_root), env=env, timeout=timeout)


def assert_safe_passed_json(payload: dict[str, object], raw: str) -> None:
    assert payload["action"] == "check"
    assert payload["status"] == "passed"
    assert payload["schema_version"] == 1
    assert payload["layout_format_version"] == 1
    assert payload["control_db_user_version"] == CONTROL_DB_USER_VERSION
    assert isinstance(payload["repository_count"], int)
    assert isinstance(payload["artifact_count"], int)
    assert int(payload["repository_count"]) >= 0
    assert int(payload["artifact_count"]) >= 0
    assert "/" not in raw
    lowered = raw.lower()
    for token in FORBIDDEN_SUMMARY_SUBSTRINGS:
        assert token not in lowered


def list_dolt_pids() -> set[int]:
    pids: set[int] = set()
    proc = Path("/proc")
    if not proc.is_dir():
        return pids
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            comm = (entry / "comm").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if comm == "dolt":
            pids.add(int(entry.name))
    return pids


def snapshot_check_temp_homes() -> list[Path]:
    return list(Path("/tmp").glob("snapshot-check-dolt-*"))


@dataclass
class SnapshotHoldEnvironment:
    settings: RepositoryServiceSettings
    layout: DurableLayout
    control_store: ControlStore

    @classmethod
    def create(
        cls,
        tmp_path: Path,
        *,
        sqlite_busy_timeout_ms: int = HOLD_BUSY_TIMEOUT_MS,
    ) -> SnapshotHoldEnvironment:
        settings = lifecycle_settings(tmp_path).model_copy(
            update={"sqlite_busy_timeout_ms": sqlite_busy_timeout_ms}
        )
        layout = DurableLayout.create_service(settings.data_root)
        control_store = ControlStore.open(
            settings.control_db_path,
            expected_version=CONTROL_DB_USER_VERSION,
            busy_timeout_ms=sqlite_busy_timeout_ms,
        )
        return cls(settings=settings, layout=layout, control_store=control_store)

    @property
    def data_root(self) -> Path:
        return self.settings.data_root

    @property
    def wal_path(self) -> Path:
        return Path(str(self.settings.control_db_path) + "-wal")

    def close(self) -> None:
        if self.control_store.is_open():
            self.control_store.close()

    def seed_uncheckpointed_write(self) -> None:
        self.control_store.connection.execute("PRAGMA wal_autocheckpoint = 0")
        self.control_store.connection.execute(
            """
            INSERT INTO artifact_residual (
                artifact_id, repository_scope, kind, name, parent_name, dev, ino, created_at
            ) VALUES (?, ?, 'stage', 'hold-probe', '', 1, 1, ?)
            """,
            (
                "00000000-0000-0000-0000-000000000001",
                "a" * 32,
                "2026-01-01T00:00:00+00:00",
            ),
        )
        self.control_store.connection.commit()

    def begin_immediate(self) -> None:
        self.control_store.connection.execute("BEGIN IMMEDIATE")

    def run_hold(
        self,
        *,
        env: dict[str, str] | None = None,
        timeout: float = 15.0,
    ) -> subprocess.CompletedProcess[str]:
        return run_hold(self.data_root, env=env, timeout=timeout)

    def run_check(
        self,
        *,
        env: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> subprocess.CompletedProcess[str]:
        return run_check(self.data_root, env=env, timeout=timeout)

    def spawn_hold(
        self,
        *,
        env: dict[str, str] | None = None,
        stdout: int | None = subprocess.PIPE,
    ) -> subprocess.Popen[str]:
        return spawn_hold(self.data_root, env=env, stdout=stdout)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
