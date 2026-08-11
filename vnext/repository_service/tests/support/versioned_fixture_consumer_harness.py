"""External-process harness for the Versioned fixture consumer E2E test."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx2 as httpx
import uvicorn

from gateway_repository_service.app import create_app
from gateway_repository_service.http.readiness import LifecycleReadiness
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.versioned_read.arrow_bridge import BRIDGE_REGISTRY, BridgeShutdownError
from support.lifecycle_harness import lifecycle_settings

REPO_ROOT = Path(__file__).resolve().parents[3]
CLIENT_PROJECT = REPO_ROOT / "repository_client"
CONSUMER_SCRIPT = CLIENT_PROJECT / "tests" / "support" / "versioned_fixture_consumer.py"
FIXTURE_ROOT = CLIENT_PROJECT / "tests" / "fixtures" / "versioned_v1"


@dataclass
class ConsumerRunResult:
    returncode: int
    stdout: str
    stderr: str
    summary: dict[str, Any] | None
    timed_out: bool = False


@dataclass
class FixtureConsumerEnvironment:
    settings: RepositoryServiceSettings
    runtime: ServiceRuntime
    server: uvicorn.Server
    server_thread: threading.Thread
    base_url: str
    bearer_token: str
    data_root: Path


def _wait_until(condition: Any, *, timeout_seconds: float, message: str) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError(message)


def _wait_until_server_started(server: uvicorn.Server, *, timeout_seconds: float = 10.0) -> int:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if server.started and server.servers:
            sockets = server.servers[0].sockets
            if sockets:
                _host, port = sockets[0].getsockname()
                return int(port)
        time.sleep(0.01)
    raise AssertionError("uvicorn server did not start in time")


def _wait_until_ready(base_url: str, bearer_token: str, *, timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    headers = {"Authorization": f"Bearer {bearer_token}"}
    while time.monotonic() < deadline:
        try:
            with httpx.Client(base_url=base_url, timeout=2.0) as client:
                response = client.get("/readyz", headers=headers)
                if response.status_code == 200:
                    return
        except httpx.HTTPError:
            pass
        time.sleep(0.05)
    raise AssertionError("service did not become ready in time")


def start_fixture_consumer_environment(
    tmp_path: Path,
    *,
    bearer_token: str,
) -> FixtureConsumerEnvironment:
    settings = lifecycle_settings(tmp_path, bearer_token=bearer_token)
    runtime = ServiceRuntime.start(settings)
    app = create_app(settings, enable_lifecycle=False)
    app.state.runtime = runtime
    app.state.auth_state = runtime.auth_state
    app.state.readiness = LifecycleReadiness(runtime)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    port = _wait_until_server_started(server)
    base_url = f"http://127.0.0.1:{port}"
    _wait_until_ready(base_url, bearer_token)
    return FixtureConsumerEnvironment(
        settings=settings,
        runtime=runtime,
        server=server,
        server_thread=server_thread,
        base_url=base_url,
        bearer_token=bearer_token,
        data_root=settings.data_root,
    )


def _consumer_env(bearer_token: str, base_url: str) -> dict[str, str]:
    env = os.environ.copy()
    for inherited_name in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
        env.pop(inherited_name, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env[_ENV_NAME_BASE_URL] = base_url
    env[_ENV_NAME_BEARER_TOKEN] = bearer_token
    env[_ENV_NAME_FIXTURE_ROOT] = str(FIXTURE_ROOT.resolve())
    return env


_ENV_NAME_BASE_URL = "GATEWAY_REPOSITORY_BASE_URL"
_ENV_NAME_BEARER_TOKEN = "GATEWAY_REPOSITORY_BEARER_TOKEN"
_ENV_NAME_FIXTURE_ROOT = "GATEWAY_VERSIONED_FIXTURE_ROOT"


def _consumer_command() -> list[str]:
    return [
        "uv",
        "run",
        "--project",
        str(CLIENT_PROJECT),
        "--locked",
        "--offline",
        "python",
        str(CONSUMER_SCRIPT),
    ]


def stop_fixture_consumer_process(
    process: subprocess.Popen[str] | None,
    *,
    timeout_seconds: float = 10.0,
) -> None:
    if process is None:
        return
    if process.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return
        time.sleep(0.02)
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except ProcessLookupError:
        return
    process.wait(timeout=timeout_seconds)


def _parse_consumer_summary(stdout: str) -> dict[str, Any] | None:
    if not stdout.strip():
        return None
    last_line = stdout.strip().splitlines()[-1]
    try:
        parsed = json.loads(last_line)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def run_fixture_consumer_subprocess(
    env: FixtureConsumerEnvironment,
    *,
    timeout_seconds: float = 180.0,
    command: list[str] | None = None,
) -> ConsumerRunResult:
    process = subprocess.Popen(
        command or _consumer_command(),
        cwd=CLIENT_PROJECT,
        env=_consumer_env(env.bearer_token, env.base_url),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return ConsumerRunResult(
            returncode=process.returncode if process.returncode is not None else 1,
            stdout=stdout,
            stderr=stderr,
            summary=_parse_consumer_summary(stdout),
            timed_out=False,
        )
    except subprocess.TimeoutExpired:
        timed_out = True
        stop_fixture_consumer_process(process)
        stdout, stderr = process.communicate(timeout=10.0)
        return ConsumerRunResult(
            returncode=process.returncode if process.returncode is not None else 1,
            stdout=stdout,
            stderr=stderr,
            summary=_parse_consumer_summary(stdout),
            timed_out=timed_out,
        )
    finally:
        stop_fixture_consumer_process(process)


def shutdown_fixture_consumer_environment(env: FixtureConsumerEnvironment | None) -> None:
    if env is None:
        return
    env.server.should_exit = True
    env.server_thread.join(timeout=10.0)
    if env.server_thread.is_alive():
        raise AssertionError("uvicorn server thread did not stop")
    shutdown_error: BridgeShutdownError | None = None
    try:
        env.runtime.shutdown()
    except BridgeShutdownError as exc:
        shutdown_error = exc
        env.runtime.dolt_runner.terminate_active_children()
        if env.runtime.control_store.is_open():
            env.runtime.control_store.close()
        if env.runtime.root_lock.is_held():
            env.runtime.root_lock.release()
    _wait_until(
        lambda: BRIDGE_REGISTRY.snapshot() == (),
        timeout_seconds=10.0,
        message="bridge registry did not drain during fixture consumer cleanup",
    )
    _wait_until(
        lambda: env.runtime.dolt_runner._active_children.snapshot() == (),
        timeout_seconds=10.0,
        message="active dolt children did not drain during fixture consumer cleanup",
    )
    data_root = env.data_root
    if data_root.exists():
        shutil.rmtree(data_root)
    if data_root.exists():
        raise AssertionError(f"temporary durable root still exists: {data_root}")
    if shutdown_error is not None:
        raise shutdown_error
