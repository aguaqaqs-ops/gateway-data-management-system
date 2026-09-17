"""Production HTTP server entrypoint with admission-first shutdown."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from types import FrameType

import uvicorn
from uvicorn.config import Config

from gateway_backend.http.shutdown import begin_http_pre_drain

_HTTP_GRACEFUL_SHUTDOWN_SECONDS = 180


class AdmissionFirstUvicornServer(uvicorn.Server):
    """Run Uvicorn with readiness/admission pre-drain before connection shutdown."""

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        self._begin_http_pre_drain_sync()
        super().handle_exit(sig, frame)

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        self._begin_http_pre_drain_sync()
        await super().shutdown(sockets)

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        port_file = os.environ.get("GATEWAY_BACKEND_HTTP_PORT_FILE")
        if port_file is None:
            return
        if not self.servers:
            return
        bound_sockets = self.servers[0].sockets
        if not bound_sockets:
            return
        _host, port = bound_sockets[0].getsockname()
        host = "127.0.0.1" if str(_host) in {"0.0.0.0", "::"} else str(_host)
        Path(port_file).write_text(
            json.dumps({"base_url": f"http://{host}:{port}"}),
            encoding="utf-8",
        )

    def _begin_http_pre_drain_sync(self) -> None:
        if not self.started:
            return
        begin_http_pre_drain(self.config.loaded_app)


def main() -> int:
    host = os.environ.get("GATEWAY_BACKEND_HTTP_HOST", "0.0.0.0")
    port = 0 if os.environ.get("GATEWAY_BACKEND_HTTP_PORT_FILE") else int(
        os.environ.get("GATEWAY_BACKEND_HTTP_PORT", "8000")
    )
    log_level = os.environ.get("GATEWAY_BACKEND_HTTP_LOG_LEVEL", "info")
    config = Config(
        "gateway_backend.app:create_app",
        factory=True,
        host=host,
        port=port,
        log_level=log_level,
        timeout_graceful_shutdown=_HTTP_GRACEFUL_SHUTDOWN_SECONDS,
    )
    server = AdmissionFirstUvicornServer(config)
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
