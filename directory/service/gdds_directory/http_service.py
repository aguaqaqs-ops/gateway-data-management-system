"""Read-only directory HTTP and static service."""

import base64
import gzip
import json
import mimetypes
import re
import sqlite3
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from . import db

DEVICE_KEY = re.compile(r"dev-[0-9a-f]{16}\Z")
JSON_TYPE = "application/json; charset=utf-8"


def _json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _accepts_gzip(value: str) -> bool:
    for entry in value.split(","):
        parts = entry.split(";")
        if parts[0].strip().lower() != "gzip":
            continue
        quality = 1.0
        for param in parts[1:]:
            name, separator, raw = param.strip().partition("=")
            if separator and name.lower() == "q":
                try:
                    quality = float(raw)
                except ValueError:
                    return False
        return 0 < quality <= 1
    return False


class DirectoryServer(ThreadingHTTPServer):
    def __init__(
        self, address: tuple[str, int], database: Path, static: Path,
        public_url: str, gateway_url: str,
    ) -> None:
        self.database = database
        self.static = static.resolve()
        self.public_url = public_url
        self.gateway_url = gateway_url
        super().__init__(address, DirectoryHandler)

    def handle_error(self, request: object, client_address: object) -> None:
        # Never print request data or a handler traceback that might contain a secret.
        return


class DirectoryHandler(BaseHTTPRequestHandler):
    server: DirectoryServer

    def log_message(self, format: str, *args: object) -> None:
        # Requests and responses may contain credentials; do not emit access logs.
        return

    def respond(
        self, status: int, body: bytes, content_type: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def error_json(self, status: int, code: str, message: str, *, no_store: bool = False) -> None:
        headers = {"Cache-Control": "no-store"} if no_store else None
        self.respond(status, _json({"code": code, "message": message}), JSON_TYPE, headers)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/healthz":
            self.respond(200, _json({"status": "ok"}), JSON_TYPE)
        elif path == "/api/catalog":
            self.catalog()
        elif path.startswith("/api/"):
            self.error_json(404, "NOT_FOUND", "接口不存在")
        else:
            self.static_file(path)

    def catalog(self) -> None:
        try:
            conn = db.connect(self.server.database, create=False, readonly=True)
            try:
                conn.execute("BEGIN")
                metadata = conn.execute(
                    "SELECT catalog_version, imported_at FROM metadata WHERE id=1"
                ).fetchone()
                if metadata is None:
                    self.error_json(503, "CATALOG_EMPTY", "目录尚未导入")
                    return
                version, imported_at = metadata
                etag = '"' + version + '"'
                if self.headers.get("If-None-Match") == etag:
                    self.respond(304, b"", JSON_TYPE, {"ETag": etag, "Vary": "Accept-Encoding"})
                    return
                rows = conn.execute("""SELECT p.device_key,p.station_code,p.name,p.region1,p.region2,
                    p.pinyin_initials,p.pinyin_full,
                    (v.current_session IS NOT NULL AND v.repository_id IS NOT NULL
                     AND v.initial_node_id IS NOT NULL AND v.initial_commit_id IS NOT NULL
                     AND v.provisioned_at IS NOT NULL)
                    FROM projects p LEFT JOIN provisioning v ON p.device_key=v.device_key
                    WHERE p.removed=0""").fetchall()
                projects: list[dict[str, Any]] = [
                    {"device_key": row[0], "station_code": row[1], "name": row[2],
                     "region1": row[3], "region2": row[4], "pinyin_initials": json.loads(row[5]),
                     "pinyin_full": json.loads(row[6]), "provisioned": bool(row[7])}
                    for row in rows
                ]
                projects.sort(key=lambda p: (
                    p["pinyin_full"][0] if p["pinyin_full"] else p["name"],
                    p["name"], p["station_code"],
                ))
                payload = _json({"catalog_version": version, "imported_at": imported_at,
                                 "projects": projects})
            finally:
                conn.close()
            headers = {"ETag": etag, "Vary": "Accept-Encoding"}
            if _accepts_gzip(self.headers.get("Accept-Encoding", "")):
                payload = gzip.compress(payload, mtime=0)
                headers["Content-Encoding"] = "gzip"
            self.respond(200, payload, JSON_TYPE, headers)
        except FileNotFoundError:
            if self.server.database.parent.is_dir() and not self.server.database.exists():
                self.error_json(503, "CATALOG_EMPTY", "目录尚未导入")
            else:
                self.error_json(503, "CATALOG_UNAVAILABLE", "目录暂时不可用")
        except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
            self.error_json(503, "CATALOG_UNAVAILABLE", "目录暂时不可用")

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/handoffs":
            self.error_json(404, "NOT_FOUND", "接口不存在")
            return
        try:
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or self.headers.get("Transfer-Encoding") is not None:
                raise ValueError("invalid length")
            length = int(lengths[0])
            if length < 0 or length > 8192:
                raise ValueError("invalid length")
            request = json.loads(self.rfile.read(length), object_pairs_hook=_unique_object)
            if not isinstance(request, dict) or set(request) - {"device_key", "return_query"}:
                raise ValueError("invalid object")
            device = request.get("device_key")
            query = request.get("return_query", "")
            if not isinstance(device, str) or not DEVICE_KEY.fullmatch(device):
                raise ValueError("invalid device")
            if not isinstance(query, str) or ("return_query" in request and (
                not query.startswith("?") or len(query) > 1000
                or any(ord(c) < 32 or ord(c) == 127 or c == "#" for c in query)
            )):
                raise ValueError("invalid return query")
        except (ValueError, UnicodeDecodeError):
            self.close_connection = True
            self.error_json(400, "INVALID_REQUEST", "请求不合法", no_store=True)
            return
        try:
            conn = db.connect(self.server.database, create=False, readonly=True)
            try:
                conn.execute("BEGIN")
                row = conn.execute("""SELECT p.project_id,p.region1,p.region2,p.name,p.station_code,
                    v.current_session,v.pending_session,v.repository_id,v.initial_node_id,
                    v.initial_commit_id,v.provisioned_at
                    FROM projects p LEFT JOIN provisioning v ON p.device_key=v.device_key
                    WHERE p.device_key=? AND p.removed=0""", (device,)).fetchone()
            finally:
                conn.close()
            if row is None:
                self.error_json(404, "DEVICE_NOT_FOUND", "设备不存在", no_store=True)
                return
            if row[5] is None or any(item is None for item in row[7:]):
                self.error_json(409, "DEVICE_NOT_PROVISIONED", "设备尚未开通", no_store=True)
                return
            if row[6] is not None:
                self.error_json(409, "SESSION_UPDATING", "会话续期尚未完成", no_store=True)
                return
            session = json.loads(row[5], object_pairs_hook=_unique_object)
            if (session["gateway_device_external_key"] != device
                    or session["business_project_id"] != row[0]
                    or not isinstance(session["token"], str) or not session["token"]):
                raise ValueError("invalid session scope")
            expiry = datetime.fromisoformat(session["expires_at"].replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                raise ValueError("invalid expiry")
            if expiry <= datetime.now(UTC):
                self.error_json(409, "SESSION_EXPIRED", "会话已过期", no_store=True)
                return
            payload = {
                "v": 1, "token": session["token"], "gateway_device_external_key": device,
                "business_project_id": row[0],
                "display": {"region1": row[1], "region2": row[2], "project_name": row[3],
                            "station_code": row[4]},
                "return_url": self.server.public_url + query,
            }
            encoded = base64.urlsafe_b64encode(_json(payload)).decode().rstrip("=")
            self.respond(200, _json({"gateway_url": self.server.gateway_url
                                    + "#gdds-handoff=" + encoded}), JSON_TYPE,
                         {"Cache-Control": "no-store"})
        except FileNotFoundError:
            if self.server.database.parent.is_dir() and not self.server.database.exists():
                self.error_json(404, "DEVICE_NOT_FOUND", "设备不存在", no_store=True)
            else:
                self.error_json(503, "CATALOG_UNAVAILABLE", "目录暂时不可用", no_store=True)
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, AttributeError):
            self.error_json(503, "CATALOG_UNAVAILABLE", "目录暂时不可用", no_store=True)

    def static_file(self, path: str) -> None:
        try:
            candidate = (self.server.static / unquote(path).lstrip("/")).resolve()
            if candidate == self.server.static:
                candidate = (self.server.static / "index.html").resolve()
            if not candidate.is_relative_to(self.server.static) or not candidate.is_file():
                raise FileNotFoundError
            content = candidate.read_bytes()
        except (OSError, ValueError):
            self.error_json(404, "NOT_FOUND", "页面不存在")
            return
        self.respond(200, content, mimetypes.guess_type(candidate.name)[0]
                     or "application/octet-stream")
