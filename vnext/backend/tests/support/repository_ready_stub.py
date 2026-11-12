"""Repository readiness and authenticated deployment identity for HTTP process tests."""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from gateway_backend.deployment_config import StorageLayoutConfig


class _ReadyHandler(BaseHTTPRequestHandler):
    expected_bearer: str = ""
    storage_layout_file: Path

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def do_GET(self) -> None:
        if self.path == "/readyz":
            body = b'{"status":"ok"}'
        elif self.path == "/internal/v1/deployment-identity":
            authorization = self.headers.get("Authorization", "")
            if authorization != f"Bearer {self.expected_bearer}":
                self.send_error(401)
                return
            storage = StorageLayoutConfig.load(self.storage_layout_file)
            body = json.dumps({"environment_id": storage.environment_id, "group_id": storage.group_id,
                "storage_digest": storage.digest}).encode()
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    if len(sys.argv) != 4:
        print(
            "usage: repository_ready_stub.py <bearer_token> <port_file> <storage_layout_file>",
            file=sys.stderr,
        )
        return 2

    bearer_token = sys.argv[1]
    port_file = Path(sys.argv[2])
    _ReadyHandler.expected_bearer = bearer_token
    _ReadyHandler.storage_layout_file = Path(sys.argv[3])
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
