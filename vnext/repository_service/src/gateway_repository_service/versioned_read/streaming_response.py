"""Streaming HTTP response that always awaits bridge cleanup."""

from __future__ import annotations

from collections.abc import AsyncIterable

from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from gateway_repository_service.admission import PermitLease
from gateway_repository_service.diagnostics import log_event
from gateway_repository_service.versioned_read.arrow_bridge import ArrowIpcStreamBridge


class VersionedReadStreamingResponse(StreamingResponse):
    """Ensure Arrow bridge cleanup completes even when Starlette aborts the body stream."""

    def __init__(
        self,
        bridge: ArrowIpcStreamBridge,
        content: AsyncIterable[bytes],
        *,
        media_type: str,
        permit_lease: PermitLease | None = None,
        request_id: str | None = None,
        repository_id: str | None = None,
        admission_capacity: int | None = None,
    ) -> None:
        self._bridge = bridge
        self._permit_lease = permit_lease
        self._request_id = request_id
        self._repository_id = repository_id
        self._admission_capacity = admission_capacity
        super().__init__(content, media_type=media_type)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            cleanup_error: BaseException | None = None
            try:
                await self._bridge.aclose()
            except BaseException as exc:
                cleanup_error = exc
            finally:
                if self._permit_lease is not None:
                    self._permit_lease.release()
                    log_event(
                        "row_stream_admission_released",
                        request_id=self._request_id,
                        repository_id=self._repository_id,
                        capacity=self._admission_capacity,
                        result="released",
                        cleanup_outcome="bridge_cleanup_error"
                        if cleanup_error is not None
                        else "closed",
                    )
            if cleanup_error is not None:
                raise cleanup_error
