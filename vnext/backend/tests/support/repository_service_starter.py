"""Subprocess entrypoint used by submit_job_harness to host Repository Service."""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import uvicorn

from gateway_repository_service.app import create_app  # type: ignore[import-not-found]
from gateway_repository_service.http.readiness import LifecycleReadiness  # type: ignore[import-not-found]
from gateway_repository_service.runtime import ServiceRuntime  # type: ignore[import-not-found]
from support.lifecycle_harness import lifecycle_settings  # type: ignore[import-not-found]


def _wait_until_server_started(server: uvicorn.Server, *, timeout_seconds: float = 15.0) -> int:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if server.started and server.servers:
            sockets = server.servers[0].sockets
            if sockets:
                _host, port = sockets[0].getsockname()
                return int(port)
        time.sleep(0.01)
    raise RuntimeError("uvicorn server did not start in time")


def _wait_until_ready(base_url: str, bearer_token: str, *, timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    request = urllib.request.Request(
        f"{base_url}/readyz",
        headers={"Authorization": f"Bearer {bearer_token}"},
    )
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(request, timeout=2.0) as response:
                if response.status == 200:
                    return
        except urllib.error.URLError:
            pass
        time.sleep(0.05)
    raise RuntimeError("repository service did not become ready in time")


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: repository_service_starter.py <tmp_path> <bearer_token> <port_file>", file=sys.stderr)
        return 2

    tmp_path = Path(sys.argv[1])
    bearer_token = sys.argv[2]
    port_file = Path(sys.argv[3])

    settings = lifecycle_settings(tmp_path, bearer_token=bearer_token)
    runtime = ServiceRuntime.start(settings)
    app = create_app(settings, enable_lifecycle=False)
    app.state.runtime = runtime
    app.state.auth_state = runtime.auth_state
    app.state.readiness = LifecycleReadiness(runtime)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=False)
    thread.start()
    try:
        port = _wait_until_server_started(server)
        base_url = f"http://127.0.0.1:{port}"
        _wait_until_ready(base_url, bearer_token)
        port_file.write_text(
            json.dumps({"base_url": base_url, "bearer_token": bearer_token}),
            encoding="utf-8",
        )
        while not server.should_exit:
            time.sleep(0.1)
    finally:
        server.should_exit = True
        thread.join(timeout=20.0)
        runtime.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
