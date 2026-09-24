"""File-based helper for HTTP in-flight read barrier process tests."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import httpx
import pytest

from gateway_backend.http.inflight_barrier import (
    INFLIGHT_BARRIER_ENV,
    _ENTERED_DIR_NAME,
    _RELEASE_FILE_NAME,
)


class HttpInflightReadBarrier:
    """Coordinate subprocess history GETs with the env-gated in-flight middleware."""

    def __init__(self, tmp_path: Path) -> None:
        self.barrier_dir = tmp_path / "http-inflight-barrier"
        self.barrier_dir.mkdir(parents=True, exist_ok=True)
        self._entered_dir = self.barrier_dir / _ENTERED_DIR_NAME
        self._entered_dir.mkdir(parents=True, exist_ok=True)
        self._release_file = self.barrier_dir / _RELEASE_FILE_NAME

    def barrier_dir_for_env(self) -> str:
        return str(self.barrier_dir)

    def apply_to_environment(self, environment: dict[str, str]) -> None:
        environment[INFLIGHT_BARRIER_ENV] = self.barrier_dir_for_env()

    def wait_entered(self, n: int = 1, *, timeout_seconds: float = 5.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if len(list(self._entered_dir.iterdir())) >= n:
                return
            time.sleep(0.01)
        entered = len(list(self._entered_dir.iterdir()))
        raise TimeoutError(
            f"expected {n} in-flight history GETs to enter the barrier, saw {entered}"
        )

    def release(self) -> None:
        self._release_file.write_text("release\n", encoding="utf-8")

    def wait_drain_started(
        self,
        base_url: str,
        process: subprocess.Popen[str],
        *,
        margin_seconds: float = 1.0,
        timeout_seconds: float = 5.0,
    ) -> None:
        """Wait until uvicorn closes the listening socket, then allow drain wait margin."""

        drain_started_deadline = time.monotonic() + timeout_seconds
        socket_closed = False
        while time.monotonic() < drain_started_deadline:
            if process.poll() is not None:
                pytest.fail("server exited before the listening socket closed during drain")
            try:
                httpx.get(f"{base_url}/readyz", timeout=0.3)
            except httpx.HTTPError:
                socket_closed = True
                break
            time.sleep(0.02)
        else:
            if not socket_closed:
                pytest.fail("drain never closed the listening socket")
        time.sleep(margin_seconds)
        if process.poll() is not None:
            pytest.fail("server exited before in-flight reads completed")
