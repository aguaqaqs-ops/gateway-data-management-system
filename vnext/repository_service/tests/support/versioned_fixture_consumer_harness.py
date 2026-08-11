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
from uuid import UUID

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
_SUMMARY_ALLOWED_KEYS = frozenset({"status", "repository_id", "c0", "c1", "c2", "main_commit"})


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
    server_thread_started: bool = True


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


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        seen.add(key)
        payload[key] = value
    return payload


def _join_server_thread(
    server: uvicorn.Server,
    server_thread: threading.Thread,
    *,
    started: bool,
) -> list[Exception]:
    if not started:
        return []
    server.should_exit = True
    server_thread.join(timeout=10.0)
    if server_thread.is_alive():
        return [AssertionError("uvicorn server thread did not stop")]
    return []


def _best_effort_release_runtime_resources(runtime: ServiceRuntime) -> list[Exception]:
    errors: list[Exception] = []
    try:
        runtime.dolt_runner.terminate_active_children()
    except Exception as exc:
        errors.append(exc)
    try:
        runtime.control_store.close()
    except Exception as exc:
        errors.append(exc)
    try:
        runtime.root_lock.release()
    except Exception as exc:
        errors.append(exc)
    return errors


def _shutdown_runtime(runtime: ServiceRuntime) -> tuple[list[Exception], BridgeShutdownError | None]:
    errors: list[Exception] = []
    shutdown_error: BridgeShutdownError | None = None
    try:
        runtime.shutdown()
    except BridgeShutdownError as exc:
        shutdown_error = exc
    except Exception as exc:
        errors.append(exc)
    errors.extend(_best_effort_release_runtime_resources(runtime))
    try:
        if runtime.control_store.is_open():
            errors.append(AssertionError("control store still open after shutdown"))
    except Exception as exc:
        errors.append(exc)
    try:
        if runtime.root_lock.is_held():
            errors.append(AssertionError("root lock still held after shutdown"))
    except Exception as exc:
        errors.append(exc)
    return errors, shutdown_error


def _finalize_environment_cleanup(
    env: FixtureConsumerEnvironment,
    *,
    errors: list[Exception],
    shutdown_error: BridgeShutdownError | None,
) -> None:
    try:
        _wait_until(
            lambda: BRIDGE_REGISTRY.snapshot() == (),
            timeout_seconds=10.0,
            message="bridge registry did not drain during fixture consumer cleanup",
        )
    except Exception as exc:
        errors.append(exc)
    try:
        _wait_until(
            lambda: env.runtime.dolt_runner._active_children.snapshot() == (),
            timeout_seconds=10.0,
            message="active dolt children did not drain during fixture consumer cleanup",
        )
    except Exception as exc:
        errors.append(exc)
    data_root = env.data_root
    if data_root.exists():
        try:
            shutil.rmtree(data_root)
        except Exception as exc:
            errors.append(exc)
    if data_root.exists():
        errors.append(AssertionError(f"temporary durable root still exists: {data_root}"))
    if shutdown_error is not None:
        errors.append(shutdown_error)
    if len(errors) == 1:
        raise errors[0]
    if len(errors) > 1:
        raise ExceptionGroup("fixture consumer environment shutdown failures", errors)


def _cleanup_partial_startup(
    *,
    runtime: ServiceRuntime,
    server: uvicorn.Server | None,
    server_thread: threading.Thread | None,
    server_thread_started: bool,
    data_root: Path,
) -> None:
    errors: list[Exception] = []
    if server is not None and server_thread is not None:
        errors.extend(_join_server_thread(server, server_thread, started=server_thread_started))
    runtime_errors, shutdown_error = _shutdown_runtime(runtime)
    errors.extend(runtime_errors)
    if data_root.exists():
        try:
            shutil.rmtree(data_root)
        except Exception as exc:
            errors.append(exc)
    if data_root.exists():
        errors.append(AssertionError(f"temporary durable root still exists: {data_root}"))
    if shutdown_error is not None:
        errors.append(shutdown_error)
    if len(errors) == 1:
        raise errors[0]
    if len(errors) > 1:
        raise ExceptionGroup("fixture consumer partial startup cleanup failures", errors)


def start_fixture_consumer_environment(
    tmp_path: Path,
    *,
    bearer_token: str,
) -> FixtureConsumerEnvironment:
    settings = lifecycle_settings(tmp_path, bearer_token=bearer_token)
    runtime = ServiceRuntime.start(settings)
    server: uvicorn.Server | None = None
    server_thread: threading.Thread | None = None
    server_thread_started = False
    try:
        app = create_app(settings, enable_lifecycle=False)
        app.state.runtime = runtime
        app.state.auth_state = runtime.auth_state
        app.state.readiness = LifecycleReadiness(runtime)
        config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
        server = uvicorn.Server(config)
        server_thread = threading.Thread(target=server.run, daemon=False)
        server_thread.start()
        server_thread_started = True
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
            server_thread_started=True,
        )
    except Exception:
        _cleanup_partial_startup(
            runtime=runtime,
            server=server,
            server_thread=server_thread,
            server_thread_started=server_thread_started,
            data_root=settings.data_root,
        )
        raise


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
    pgid: int | None = None,
    timeout_seconds: float = 10.0,
) -> None:
    resolved_pgid = pgid
    if resolved_pgid is None and process is not None:
        try:
            resolved_pgid = os.getpgid(process.pid)
        except ProcessLookupError:
            resolved_pgid = None
    if resolved_pgid is None:
        return
    try:
        os.killpg(resolved_pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            break
        try:
            os.killpg(resolved_pgid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.02)
    try:
        os.killpg(resolved_pgid, signal.SIGKILL)
    except ProcessLookupError:
        return
    if process is not None and process.poll() is None:
        process.wait(timeout=timeout_seconds)


def parse_consumer_summary(stdout: str) -> dict[str, Any] | None:
    if not stdout or "\n" in stdout or "\r" in stdout:
        return None
    try:
        parsed = json.loads(stdout, object_pairs_hook=_reject_duplicate_json_keys)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    if set(parsed) != _SUMMARY_ALLOWED_KEYS:
        return None
    if parsed.get("status") != "ok":
        return None
    repository_id = parsed.get("repository_id")
    if not isinstance(repository_id, str) or not repository_id:
        return None
    try:
        UUID(repository_id)
    except ValueError:
        return None
    for field in ("c0", "c1", "c2", "main_commit"):
        value = parsed.get(field)
        if not isinstance(value, str) or not value:
            return None
    return parsed


def _parse_consumer_summary(stdout: str) -> dict[str, Any] | None:
    return parse_consumer_summary(stdout)


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
    process_pgid = os.getpgid(process.pid)
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
        stop_fixture_consumer_process(process, pgid=process_pgid)
        stdout, stderr = process.communicate(timeout=10.0)
        return ConsumerRunResult(
            returncode=process.returncode if process.returncode is not None else 1,
            stdout=stdout,
            stderr=stderr,
            summary=_parse_consumer_summary(stdout),
            timed_out=timed_out,
        )
    finally:
        stop_fixture_consumer_process(process, pgid=process_pgid)


def shutdown_fixture_consumer_environment(env: FixtureConsumerEnvironment | None) -> None:
    if env is None:
        return
    errors = _join_server_thread(
        env.server,
        env.server_thread,
        started=env.server_thread_started,
    )
    runtime_errors, shutdown_error = _shutdown_runtime(env.runtime)
    errors.extend(runtime_errors)
    _finalize_environment_cleanup(env, errors=errors, shutdown_error=shutdown_error)
