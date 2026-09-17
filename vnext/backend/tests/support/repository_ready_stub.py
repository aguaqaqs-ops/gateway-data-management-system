"""Minimal subprocess-hosted Repository Service /readyz stub for HTTP process tests."""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _ReadyHandler(BaseHTTPRequestHandler):
    expected_bearer: str = ""

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def do_GET(self) -> None:
        if self.path != "/readyz":
            self.send_error(404)
            return
        authorization = self.headers.get("Authorization", "")
        if authorization != f"Bearer {self.expected_bearer}":
            self.send_error(401)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "usage: repository_ready_stub.py <bearer_token> <port_file>",
            file=sys.stderr,
        )
        return 2

    bearer_token = sys.argv[1]
    port_file = Path(sys.argv[2])
    _ReadyHandler.expected_bearer = bearer_token
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ReadyHandler)
    host = str(server.server_address[0])
    port = int(server.server_address[1])
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    port_file.write_text(
        json.dumps({"base_url": f"http://{host}:{port}"}),
        encoding="utf-8",
    )
    try:
        server.serve_forever()
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
