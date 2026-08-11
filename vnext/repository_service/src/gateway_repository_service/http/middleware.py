"""HTTP middleware for Repository Service."""

from __future__ import annotations

from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestIdMiddleware:
    """Attach a server-generated opaque request ID to every response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if not any(name.lower() == b"x-request-id" for name, _ in headers):
                    headers.append((b"x-request-id", request_id.encode("latin-1")))
                    message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_request_id)
