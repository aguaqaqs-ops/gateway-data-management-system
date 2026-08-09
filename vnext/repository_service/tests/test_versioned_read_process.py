"""Serial integration tests for ProcessStream cancellation and child reap."""

from __future__ import annotations

import os
import signal
import threading
import time
from pathlib import Path

import pytest

from gateway_repository_service.candidate_a.dolt_cli import write_query
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.process import (
    DoltRunner,
    ProcessBoundaryError,
    ProcessStream,
)
from support.lifecycle_harness import lifecycle_settings


def _wait_until_pid_reaped(pid: int, *, timeout_seconds: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not Path(f"/proc/{pid}").exists():
            return
        time.sleep(0.02)
    raise AssertionError(f"process {pid} was not reaped")


@pytest.fixture
def dolt_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[DoltRunner, Path]:
    settings = lifecycle_settings(tmp_path)
    layout = DurableLayout.create_for_probe(settings.data_root)
    repository = layout.staging_artifacts / "cancel-repo"
    repository.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(DoltRunner, "_validate_version", lambda self: None)
    runner = DoltRunner(settings, layout.root)
    runner.run(
        "init",
        [
            "init",
            f"--name={settings.author_name}",
            f"--email={settings.author_email}",
            "--initial-branch=main",
        ],
        cwd=repository,
        timeout=settings.metadata_timeout_seconds,
    )
    return runner, repository


def _blocking_sql_query(layout: DurableLayout, rows: int) -> Path:
    values = ", ".join(f"({index})" for index in range(rows))
    sql = (
        "CREATE TABLE IF NOT EXISTS stream_probe (id BIGINT NOT NULL PRIMARY KEY);\n"
        f"INSERT INTO stream_probe (id) VALUES {values};\n"
        "SELECT id FROM stream_probe ORDER BY id;\n"
    )
    return write_query(layout.staging_artifacts, sql)


@pytest.mark.integration
@pytest.mark.serial
def test_process_stream_cancellation_reaps_child(tmp_path: Path, dolt_runner: tuple[DoltRunner, Path]) -> None:
    runner, repository = dolt_runner
    settings = lifecycle_settings(tmp_path)
    layout = DurableLayout.create_for_probe(settings.data_root)
    query = _blocking_sql_query(layout, 4096)
    cancel = threading.Event()
    started = threading.Event()
    observed_pid: list[int] = []
    errors: list[BaseException] = []

    def consume() -> None:
        try:
            stream = runner.stream(
                "row_stream",
                ["sql", "--result-format=csv"],
                cwd=repository,
                timeout=settings.import_timeout_seconds,
                stdin_path=query,
                cancellation=cancel.is_set,
            )
            started.set()
            observed_pid.append(stream.running_pid or -1)
            for _line in stream:
                cancel.set()
        except ProcessBoundaryError as exc:
            if str(exc) != "stream cancelled":
                errors.append(exc)
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=consume)
    worker.start()
    assert started.wait(timeout=5.0)
    cancel.set()
    worker.join(timeout=10.0)
    assert not worker.is_alive()
    assert errors == []
    assert observed_pid and observed_pid[0] > 0
    _wait_until_pid_reaped(observed_pid[0])
    query.unlink(missing_ok=True)


@pytest.mark.integration
@pytest.mark.serial
def test_process_stream_cancel_before_start_raises(tmp_path: Path, dolt_runner: tuple[DoltRunner, Path]) -> None:
    runner, repository = dolt_runner
    settings = lifecycle_settings(tmp_path)
    layout = DurableLayout.create_for_probe(settings.data_root)
    query = _blocking_sql_query(layout, 1)
    with pytest.raises(ProcessBoundaryError, match="stream cancelled"):
        stream = runner.stream(
            "row_stream",
            ["sql", "--result-format=csv"],
            cwd=repository,
            timeout=settings.import_timeout_seconds,
            stdin_path=query,
            cancellation=lambda: True,
        )
        list(stream)
    query.unlink(missing_ok=True)


@pytest.mark.integration
@pytest.mark.serial
def test_process_stream_close_is_idempotent(tmp_path: Path, dolt_runner: tuple[DoltRunner, Path]) -> None:
    runner, repository = dolt_runner
    settings = lifecycle_settings(tmp_path)
    layout = DurableLayout.create_for_probe(settings.data_root)
    query = _blocking_sql_query(layout, 4)
    process, _stdin = runner._start(
        "row_stream",
        ["sql", "--result-format=csv"],
        cwd=repository,
        stdin_path=query,
    )
    stream = ProcessStream(runner, process, "row_stream", settings.import_timeout_seconds)
    first = stream.close(cancelled=True)
    second = stream.close(cancelled=True)
    assert first.cancelled is True
    assert second.cancelled is True
    assert process.poll() is not None
    query.unlink(missing_ok=True)


@pytest.mark.integration
@pytest.mark.serial
def test_dolt_runner_stream_close_on_cancel_sends_term(
    tmp_path: Path,
    dolt_runner: tuple[DoltRunner, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, repository = dolt_runner
    settings = lifecycle_settings(tmp_path)
    layout = DurableLayout.create_for_probe(settings.data_root)
    query = _blocking_sql_query(layout, 8192)
    signals: list[tuple[int, int]] = []
    original_killpg = os.killpg

    def recording_killpg(pid: int, sig: int) -> None:
        signals.append((pid, sig))
        original_killpg(pid, sig)

    stream = runner.stream(
        "row_stream",
        ["sql", "--result-format=csv"],
        cwd=repository,
        timeout=settings.import_timeout_seconds,
        stdin_path=query,
    )
    child_pid = stream.running_pid
    assert child_pid is not None
    monkeypatch.setattr("gateway_repository_service.process.os.killpg", recording_killpg)
    stream.close(cancelled=True)
    assert (child_pid, signal.SIGTERM) in signals
    _wait_until_pid_reaped(child_pid)
    query.unlink(missing_ok=True)


@pytest.mark.integration
@pytest.mark.serial
def test_process_stream_callback_exception_still_reaps_child(
    tmp_path: Path,
    dolt_runner: tuple[DoltRunner, Path],
) -> None:
    runner, repository = dolt_runner
    settings = lifecycle_settings(tmp_path)
    layout = DurableLayout.create_for_probe(settings.data_root)
    query = _blocking_sql_query(layout, 4096)
    observed_pid: list[int] = []

    call_count = 0

    def broken_callback() -> bool:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return False
        raise RuntimeError("callback failed")

    stream = runner.stream(
        "row_stream",
        ["sql", "--result-format=csv"],
        cwd=repository,
        timeout=settings.import_timeout_seconds,
        stdin_path=query,
        cancellation=broken_callback,
    )
    observed_pid.append(stream.running_pid or -1)
    with pytest.raises(ProcessBoundaryError, match="stream cancelled"):
        list(stream)
    assert observed_pid[0] > 0
    _wait_until_pid_reaped(observed_pid[0])
    query.unlink(missing_ok=True)
