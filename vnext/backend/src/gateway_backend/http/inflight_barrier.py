"""Test-only HTTP in-flight read barrier for process-level shutdown evidence."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from fastapi import FastAPI
from starlette.types import ASGIApp, Receive, Scope, Send

INFLIGHT_BARRIER_ENV = "GATEWAY_BACKEND_HTTP_TEST_INFLIGHT_BARRIER_DIR"
_RELEASE_FILE_NAME = "release"
_ENTERED_DIR_NAME = "entered"
_BARRIER_WAIT_TIMEOUT_SECONDS = 30.0
_BARRIER_POLL_INTERVAL_SECONDS = 0.01


def maybe_add_inflight_barrier_middleware(app: FastAPI) -> None:
    barrier_dir = os.environ.get(INFLIGHT_BARRIER_ENV, "").strip()
    if not barrier_dir:
        return
    app.add_middleware(HttpInflightReadBarrierMiddleware)


def _matches_barrier_path(path: str, method: str) -> bool:
    if method != "GET":
        return False
    if path == "/v1/history":
        return True
    return path.startswith("/v1/history-compares/")


class HttpInflightReadBarrierMiddleware:
    """Block selected history GETs until the test releases the barrier directory."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        barrier_dir = os.environ.get(INFLIGHT_BARRIER_ENV, "").strip()
        self._barrier_dir = Path(barrier_dir) if barrier_dir else None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or self._barrier_dir is None:
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path", ""))
        method = str(scope.get("method", "")).upper()
        if not _matches_barrier_path(path, method):
            await self.app(scope, receive, send)
            return
        entered_dir = self._barrier_dir / _ENTERED_DIR_NAME
        entered_dir.mkdir(parents=True, exist_ok=True)
        entered_marker = entered_dir / f"{time.time_ns()}.entered"
        entered_marker.write_text(path, encoding="utf-8")
        release_file = self._barrier_dir / _RELEASE_FILE_NAME
        deadline = time.monotonic() + _BARRIER_WAIT_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if release_file.is_file():
                break
            await asyncio.sleep(_BARRIER_POLL_INTERVAL_SECONDS)
        else:
            raise TimeoutError(
                f"in-flight read barrier timed out waiting for release file: {release_file}"
            )
        await self.app(scope, receive, send)
