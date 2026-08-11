"""Streaming HTTP response that always awaits bridge cleanup."""

from __future__ import annotations

from collections.abc import AsyncIterable

from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from gateway_repository_service.versioned_read.arrow_bridge import ArrowIpcStreamBridge


class VersionedReadStreamingResponse(StreamingResponse):
    """Ensure Arrow bridge cleanup completes even when Starlette aborts the body stream."""

    def __init__(
        self,
        bridge: ArrowIpcStreamBridge,
        content: AsyncIterable[bytes],
        *,
        media_type: str,
    ) -> None:
        self._bridge = bridge
        super().__init__(content, media_type=media_type)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._bridge.aclose()
