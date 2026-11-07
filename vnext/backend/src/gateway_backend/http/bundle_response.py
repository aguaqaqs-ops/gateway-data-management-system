"""ASGI-owned bundle lifetime, including cancellation before iterator consumption."""

from __future__ import annotations

from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from gateway_backend.artifacts.bundle_download import PreparedBundleDownload


class BundleStreamingResponse(StreamingResponse):
    def __init__(self, prepared: PreparedBundleDownload) -> None:
        self._prepared = prepared
        try:
            super().__init__(
                prepared.stream,
                media_type="application/x-tar",
                headers={
                    "Content-Length": str(prepared.content_length),
                    "ETag": prepared.etag,
                    "Content-Disposition": f'attachment; filename="{prepared.filename}"',
                },
            )
        except BaseException:
            prepared.close()
            raise

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._prepared.close()
