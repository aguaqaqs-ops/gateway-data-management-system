"""HTTP middleware for Repository Service."""

from __future__ import annotations

import time
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from gateway_repository_service.diagnostics import log_event


class RequestIdMiddleware:
    """Attach a server-generated opaque request ID and completion diagnostics."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        status_code = 500
        bytes_sent = 0

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, bytes_sent
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 500))
                headers = list(message.get("headers", []))
                if not any(name.lower() == b"x-request-id" for name, _ in headers):
                    headers.append((b"x-request-id", request_id.encode("latin-1")))
                    message = {**message, "headers": headers}
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                if isinstance(body, (bytes, bytearray, memoryview)):
                    bytes_sent += len(body)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            duration_ms = int((time.perf_counter() - started) * 1000)
            log_event(
                "http_request_completed",
                request_id=request_id,
                duration_ms=duration_ms,
                size_bytes=bytes_sent,
                result="completed",
                code=str(status_code),
            )
