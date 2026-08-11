"""Unit tests for Versioned fixture consumer external-process harness."""

from __future__ import annotations

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
    run_fixture_consumer_subprocess,
    shutdown_fixture_consumer_environment,
    stop_fixture_consumer_process,
)

pytestmark = pytest.mark.unit


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


def test_shutdown_fixture_consumer_environment_reraises_bridge_shutdown_error() -> None:
    runtime = MagicMock()
    runtime.shutdown.side_effect = BridgeShutdownError((BridgeJoinTimeoutError("join timeout"),))
    runtime.dolt_runner._active_children.snapshot.return_value = ()
    runtime.control_store.is_open.return_value = True
    runtime.root_lock.is_held.return_value = True
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


def test_run_fixture_consumer_subprocess_kills_on_timeout() -> None:
    env = _minimal_env()
    with patch(
        "support.versioned_fixture_consumer_harness._consumer_command",
        return_value=[sys.executable, "-c", "import time; time.sleep(30)"],
    ):
        result = run_fixture_consumer_subprocess(env, timeout_seconds=1.0)
    assert result.timed_out is True
    assert result.returncode != 0


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
