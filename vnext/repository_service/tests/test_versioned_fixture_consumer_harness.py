"""Unit tests for Versioned fixture consumer external-process harness."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gateway_repository_service.versioned_read.arrow_bridge import (
    BridgeJoinTimeoutError,
    BridgeShutdownError,
)
from support.versioned_fixture_consumer_harness import (
    FixtureConsumerEnvironment,
    parse_consumer_summary,
    run_fixture_consumer_subprocess,
    shutdown_fixture_consumer_environment,
    start_fixture_consumer_environment,
    stop_fixture_consumer_process,
)

_VALID_SUMMARY = (
    '{"status":"ok","repository_id":"018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11",'
    '"c0":"commit-c0","c1":"commit-c1","c2":"commit-c2","main_commit":"commit-c2"}'
)


def _minimal_env() -> FixtureConsumerEnvironment:
    return FixtureConsumerEnvironment(
        settings=MagicMock(),
        runtime=MagicMock(),
        server=MagicMock(),
        server_thread=MagicMock(),
        base_url="http://127.0.0.1:9",
        bearer_token="token",
        data_root=Path("/tmp/unused"),
    )


@pytest.mark.unit
def test_shutdown_runtime_best_effort_on_generic_shutdown_fault() -> None:
    runtime = MagicMock()
    runtime.shutdown.side_effect = RuntimeError("generic-shutdown-fault")
    runtime.control_store.is_open.side_effect = [True, False]
    runtime.root_lock.is_held.side_effect = [True, False]
    runtime.dolt_runner._active_children.snapshot.return_value = ()
    server_thread = MagicMock()
    server_thread.is_alive.return_value = False
    env = FixtureConsumerEnvironment(
        settings=MagicMock(),
        runtime=runtime,
        server=MagicMock(should_exit=False),
        server_thread=server_thread,
        base_url="http://127.0.0.1:9",
        bearer_token="token",
        data_root=Path("/tmp/unused"),
    )
    with (
        patch(
            "support.versioned_fixture_consumer_harness.BRIDGE_REGISTRY.snapshot",
            return_value=(),
        ),
        patch.object(Path, "exists", return_value=False),
        pytest.raises(RuntimeError, match="generic-shutdown-fault"),
    ):
        shutdown_fixture_consumer_environment(env)
    runtime.dolt_runner.terminate_active_children.assert_called_once()
    runtime.control_store.close.assert_called_once()
    runtime.root_lock.release.assert_called_once()


@pytest.mark.unit
def test_shutdown_runtime_best_effort_when_close_raises() -> None:
    runtime = MagicMock()
    runtime.shutdown.side_effect = RuntimeError("generic-shutdown-fault")
    runtime.control_store.is_open.return_value = True
    runtime.control_store.close.side_effect = RuntimeError("close-fault")
    runtime.root_lock.is_held.return_value = True
    runtime.dolt_runner._active_children.snapshot.return_value = ()
    server_thread = MagicMock()
    server_thread.is_alive.return_value = False
    env = FixtureConsumerEnvironment(
        settings=MagicMock(),
        runtime=runtime,
        server=MagicMock(should_exit=False),
        server_thread=server_thread,
        base_url="http://127.0.0.1:9",
        bearer_token="token",
        data_root=Path("/tmp/unused"),
    )
    with (
        patch(
            "support.versioned_fixture_consumer_harness.BRIDGE_REGISTRY.snapshot",
            return_value=(),
        ),
        patch.object(Path, "exists", return_value=False),
    ):
        with pytest.raises(ExceptionGroup, match="fixture consumer environment shutdown failures") as exc_info:
            shutdown_fixture_consumer_environment(env)
    errors = exc_info.value.exceptions
    assert any(isinstance(exc, RuntimeError) and str(exc) == "generic-shutdown-fault" for exc in errors)
    assert any(isinstance(exc, RuntimeError) and str(exc) == "close-fault" for exc in errors)
    assert any(
        isinstance(exc, AssertionError) and "root lock still held" in str(exc) for exc in errors
    )
    runtime.root_lock.release.assert_called_once()


@pytest.mark.unit
def test_shutdown_fixture_consumer_environment_reraises_bridge_shutdown_error() -> None:
    runtime = MagicMock()
    runtime.shutdown.side_effect = BridgeShutdownError((BridgeJoinTimeoutError("join timeout"),))
    runtime.dolt_runner._active_children.snapshot.return_value = ()
    runtime.control_store.is_open.side_effect = [True, False]
    runtime.root_lock.is_held.side_effect = [True, False]
    server_thread = MagicMock()
    server_thread.is_alive.return_value = False
    env = FixtureConsumerEnvironment(
        settings=MagicMock(),
        runtime=runtime,
        server=MagicMock(should_exit=False),
        server_thread=server_thread,
        base_url="http://127.0.0.1:9",
        bearer_token="token",
        data_root=Path("/tmp/unused"),
    )
    with (
        patch(
            "support.versioned_fixture_consumer_harness.BRIDGE_REGISTRY.snapshot",
            return_value=(),
        ),
        patch.object(Path, "exists", return_value=False),
        pytest.raises(BridgeShutdownError),
    ):
        shutdown_fixture_consumer_environment(env)


@pytest.mark.unit
def test_shutdown_fixture_consumer_environment_still_shuts_down_runtime_when_join_fails() -> None:
    runtime = MagicMock()
    runtime.shutdown.return_value = None
    runtime.control_store.is_open.return_value = False
    runtime.root_lock.is_held.return_value = False
    runtime.dolt_runner._active_children.snapshot.return_value = ()
    server_thread = MagicMock()
    server_thread.is_alive.return_value = True
    env = FixtureConsumerEnvironment(
        settings=MagicMock(),
        runtime=runtime,
        server=MagicMock(should_exit=False),
        server_thread=server_thread,
        base_url="http://127.0.0.1:9",
        bearer_token="token",
        data_root=Path("/tmp/unused"),
    )
    with (
        patch(
            "support.versioned_fixture_consumer_harness.BRIDGE_REGISTRY.snapshot",
            return_value=(),
        ),
        patch.object(Path, "exists", return_value=False),
        pytest.raises(AssertionError, match="uvicorn server thread did not stop"),
    ):
        shutdown_fixture_consumer_environment(env)
    runtime.shutdown.assert_called_once()


@pytest.mark.unit
def test_shutdown_fixture_consumer_environment_rejects_open_control_store() -> None:
    runtime = MagicMock()
    runtime.shutdown.return_value = None
    runtime.control_store.is_open.return_value = True
    runtime.root_lock.is_held.return_value = False
    runtime.dolt_runner._active_children.snapshot.return_value = ()
    server_thread = MagicMock()
    server_thread.is_alive.return_value = False
    env = FixtureConsumerEnvironment(
        settings=MagicMock(),
        runtime=runtime,
        server=MagicMock(should_exit=False),
        server_thread=server_thread,
        base_url="http://127.0.0.1:9",
        bearer_token="token",
        data_root=Path("/tmp/unused"),
    )
    with (
        patch(
            "support.versioned_fixture_consumer_harness.BRIDGE_REGISTRY.snapshot",
            return_value=(),
        ),
        patch.object(Path, "exists", return_value=False),
        pytest.raises(AssertionError, match="control store still open"),
    ):
        shutdown_fixture_consumer_environment(env)


@pytest.mark.unit
def test_start_fixture_consumer_environment_cleans_up_on_create_app_failure(tmp_path: Path) -> None:
    runtime = MagicMock()
    runtime.shutdown.return_value = None
    runtime.control_store.is_open.return_value = False
    runtime.root_lock.is_held.return_value = False
    with (
        patch(
            "support.versioned_fixture_consumer_harness.lifecycle_settings",
            return_value=MagicMock(data_root=tmp_path / "data"),
        ),
        patch(
            "support.versioned_fixture_consumer_harness.ServiceRuntime.start",
            return_value=runtime,
        ),
        patch(
            "support.versioned_fixture_consumer_harness.create_app",
            side_effect=RuntimeError("create_app failed"),
        ),
        pytest.raises(RuntimeError, match="create_app failed"),
    ):
        start_fixture_consumer_environment(tmp_path, bearer_token="token")
    runtime.shutdown.assert_called_once()


@pytest.mark.unit
def test_start_fixture_consumer_environment_cleans_up_on_readiness_failure(tmp_path: Path) -> None:
    runtime = MagicMock()
    runtime.shutdown.return_value = None
    runtime.control_store.is_open.return_value = False
    runtime.root_lock.is_held.return_value = False
    with (
        patch(
            "support.versioned_fixture_consumer_harness.lifecycle_settings",
            return_value=MagicMock(data_root=tmp_path / "data"),
        ),
        patch(
            "support.versioned_fixture_consumer_harness.ServiceRuntime.start",
            return_value=runtime,
        ),
        patch(
            "support.versioned_fixture_consumer_harness.create_app",
            return_value=MagicMock(),
        ),
        patch(
            "support.versioned_fixture_consumer_harness._wait_until_server_started",
            return_value=12345,
        ),
        patch(
            "support.versioned_fixture_consumer_harness._wait_until_ready",
            side_effect=AssertionError("service did not become ready in time"),
        ),
        pytest.raises(AssertionError, match="service did not become ready"),
    ):
        start_fixture_consumer_environment(tmp_path, bearer_token="token")
    runtime.shutdown.assert_called_once()


@pytest.mark.integration
@pytest.mark.serial
def test_run_fixture_consumer_subprocess_kills_on_timeout() -> None:
    env = _minimal_env()
    with patch(
        "support.versioned_fixture_consumer_harness._consumer_command",
        return_value=[sys.executable, "-c", "import time; time.sleep(30)"],
    ):
        result = run_fixture_consumer_subprocess(env, timeout_seconds=1.0)
    assert result.timed_out is True
    assert result.returncode != 0
    assert result.summary is None


@pytest.mark.integration
@pytest.mark.serial
def test_stop_fixture_consumer_process_reaps_running_child() -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stop_fixture_consumer_process(process, timeout_seconds=5.0)
        assert process.poll() is not None
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if not Path(f"/proc/{process.pid}").exists():
                return
            time.sleep(0.02)
        raise AssertionError(f"process {process.pid} was not reaped")
    finally:
        stop_fixture_consumer_process(process)


@pytest.mark.integration
@pytest.mark.serial
def test_stop_fixture_consumer_process_kills_exited_parent_group_child() -> None:
    pgid: int | None = None
    child_pid: int | None = None
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import subprocess,sys;"
            "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']);"
            "print(child.pid, flush=True)",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        pgid = os.getpgid(process.pid)
        try:
            stdout_bytes, _stderr = process.communicate(timeout=10.0)
        except subprocess.TimeoutExpired as exc:
            stdout_bytes = exc.output if isinstance(exc.output, bytes) else b""
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5.0)
        child_pid = int(stdout_bytes.decode().strip())
        stop_fixture_consumer_process(None, pgid=pgid, timeout_seconds=5.0)
        with pytest.raises(ProcessLookupError):
            os.killpg(pgid, 0)
    finally:
        if pgid is not None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(pgid, signal.SIGKILL)
        if child_pid is not None:
            with contextlib.suppress(ProcessLookupError):
                os.kill(child_pid, signal.SIGKILL)


@pytest.mark.unit
def test_parse_consumer_summary_rejects_multiline_stdout() -> None:
    assert parse_consumer_summary('{"status":"ok"}\n{"status":"ok"}\n') is None


@pytest.mark.unit
def test_parse_consumer_summary_rejects_leading_and_trailing_blank_lines() -> None:
    assert parse_consumer_summary(f"\n{_VALID_SUMMARY}") is None
    assert parse_consumer_summary(f"{_VALID_SUMMARY}\n") is None


@pytest.mark.unit
def test_parse_consumer_summary_rejects_duplicate_status_key() -> None:
    assert parse_consumer_summary('{"status":"ok","status":"bad","repository_id":"x"}') is None


@pytest.mark.unit
def test_parse_consumer_summary_rejects_duplicate_commit_field() -> None:
    payload = (
        '{"status":"ok","repository_id":"018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11",'
        '"c0":"a","c1":"first","c1":"second","c2":"c","main_commit":"c"}'
    )
    assert parse_consumer_summary(payload) is None


@pytest.mark.unit
def test_parse_consumer_summary_rejects_extra_key() -> None:
    payload = (
        '{"status":"ok","repository_id":"018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11",'
        '"c0":"a","c1":"b","c2":"c","main_commit":"c","extra":"x"}'
    )
    assert parse_consumer_summary(payload) is None


@pytest.mark.unit
def test_parse_consumer_summary_accepts_valid_summary() -> None:
    summary = parse_consumer_summary(_VALID_SUMMARY)
    assert summary is not None
    assert summary["status"] == "ok"


@pytest.mark.unit
def test_parse_consumer_summary_rejects_timeout_fault_consumer_shape() -> None:
    assert parse_consumer_summary('{"status":"timeout"}') is None
