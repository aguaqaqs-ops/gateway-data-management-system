"""HTTP contract tests using a real loopback server and private SQLite."""

import base64
import gzip
import hashlib
import hmac
from http.client import HTTPConnection
import json
import queue
import secrets
import socket
import subprocess
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from gdds_directory import db, importer
from gdds_directory.http_service import DirectoryServer

HEADER = b"region1,region2,project_name,station_code,pinyin_initials,pinyin_full\n"
DATA = HEADER + "江苏,苏州,名称,SZ-0142,mc,ming cheng\n浙江,宁波,另一,NB-1,ly,\n".encode()


def build_static(root: Path) -> Path:
    root.mkdir()
    (root / ".vite").mkdir()
    (root / "assets").mkdir()
    outputs = {"assets/index-123.js": b"built javascript", "assets/index-123.css": b"body{}",
               "assets/lazy-123.js": b"lazy chunk", "assets/data-123.json": b'{"built":true}',
               "assets/font-123.woff2": b"font", "assets/module-123.wasm": b"wasm",
               "assets/地图-123.svg": b"<svg/>"}
    for name, content in outputs.items():
        (root / name).write_bytes(content)
    (root / "index.html").write_text(
        '<script type="module" src="/assets/index-123.js"></script>', encoding="utf-8",
    )
    (root / ".vite" / "manifest.json").write_text(json.dumps({
        "index.html": {"file": "assets/index-123.js", "isEntry": True,
                       "css": ["assets/index-123.css"],
                       "assets": [name for name in outputs if not name.endswith((".js", ".css"))],
                       "dynamicImports": ["src/lazy.ts"]},
        "src/lazy.ts": {"file": "assets/lazy-123.js", "isDynamicEntry": True},
    }), encoding="utf-8")
    return root


@pytest.fixture
def http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Path, Path, int]]:
    def forbidden(*args: object, **kwargs: object) -> Any:
        pytest.fail("HTTP handler must not spawn a subprocess", pytrace=False)

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    static = build_static(tmp_path / "dist")
    sentinel = tmp_path / "gateway-sentinel"
    sentinel.write_text("gateway", encoding="utf-8")
    (static / "escape").symlink_to(sentinel)
    database = private / "directory.sqlite"
    monkeypatch.setenv("GDDS_DIRECTORY_STATIC_DIR", str(static))
    server = DirectoryServer(("127.0.0.1", 0), database, static,
                             "https://directory.example/", "https://gateway.example/")
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield database, sentinel, int(server.server_address[1])
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def request(port: int, method: str, path: str, body: bytes | None = None,
            headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request(method, path, body, headers or {})
        response = conn.getresponse()
        return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
    finally:
        conn.close()


def initialise(path: Path) -> list[importer.Project]:
    conn = db.connect(path)
    try:
        projects, errors = importer.parse(DATA)
        assert not errors
        importer.apply(conn, projects, DATA)
        return projects
    finally:
        conn.close()


def post(port: int, value: object) -> tuple[int, dict[str, str], dict[str, Any]]:
    status, headers, payload = request(port, "POST", "/api/handoffs", json.dumps(value).encode())
    return status, headers, json.loads(payload)


def put_session(path: Path, project: importer.Project, expiry: datetime,
                *, pending: bool = False) -> str:
    token = "dir-" + secrets.token_urlsafe(32)
    session = json.dumps({"token": token, "actor_id": "test1",
                          "gateway_device_external_key": project.device_key,
                          "business_project_id": project.project_id,
                          "permissions": ["workspace_read"],
                          "expires_at": expiry.strftime("%Y-%m-%dT%H:%M:%SZ")})
    conn = db.connect(path)
    try:
        conn.execute("""INSERT OR REPLACE INTO provisioning
            (device_key,environment_id,group_id,current_session,pending_session,repository_id,
             initial_node_id,initial_commit_id,provisioned_at)
             VALUES (?, 'env', 'group', ?, ?, 'repo', 'node', 'commit', '2026-01-01T00:00:00Z')""",
                     (project.device_key, session, session if pending else None))
        conn.commit()
    finally:
        conn.close()
    return token


def test_catalog_etag_gzip_and_read_only(http: tuple[Path, Path, int]) -> None:
    path, sentinel, port = http
    status, _, body = request(port, "GET", "/api/catalog")
    assert status == 503 and json.loads(body)["code"] == "CATALOG_EMPTY"
    assert not path.exists()
    initialise(path)
    original = hashlib.sha256(path.read_bytes()).digest()
    sentinel_hash = hashlib.sha256(sentinel.read_bytes()).digest()
    status, headers, body = request(port, "GET", "/api/catalog", headers={"Accept-Encoding": "gzip;q=0.5"})
    assert status == 200 and headers["content-encoding"] == "gzip"
    catalog = json.loads(gzip.decompress(body))
    assert len(catalog["projects"]) == 2
    assert any(not project["pinyin_full"] for project in catalog["projects"])
    assert not any(p["provisioned"] for p in catalog["projects"])
    status, _, body = request(port, "GET", "/api/catalog", headers={"If-None-Match": headers["etag"]})
    assert status == 304 and body == b""
    status, headers, _ = request(port, "GET", "/api/catalog", headers={"Accept-Encoding": "gzip;q=0"})
    assert status == 200 and "content-encoding" not in headers
    assert hashlib.sha256(path.read_bytes()).digest() == original
    assert hashlib.sha256(sentinel.read_bytes()).digest() == sentinel_hash


def test_existing_invalid_schema_is_unavailable(http: tuple[Path, Path, int]) -> None:
    path, _, port = http
    path.touch(mode=0o600)
    status, _, body = request(port, "GET", "/api/catalog")
    assert status == 503 and json.loads(body)["code"] == "CATALOG_UNAVAILABLE"


def test_static_and_unknown_api(http: tuple[Path, Path, int]) -> None:
    _, _, port = http
    assert request(port, "GET", "/")[2] == request(port, "GET", "/index.html")[2]
    for path in ("/escape", "/%2e%2e/gateway-sentinel", "/missing", "/api/missing"):
        status, _, _ = request(port, "GET", path)
        assert status == 404
    assert json.loads(request(port, "GET", "/healthz")[2]) == {"status": "ok"}


def test_static_only_serves_build_outputs(http: tuple[Path, Path, int]) -> None:
    database, sentinel, port = http
    static = database.parent.parent / "dist"
    private_names = [".env", ".env.production", "package-lock.json", "vite.config.ts",
                     "index.html.bak", "index.html~", "directory.sqlite", "src/App.tsx",
                     "assets/config.json", "assets/source.js.map", "assets/index-old.js"]
    for name in private_names:
        target = static / name
        target.parent.mkdir(exist_ok=True)
        target.write_text("private", encoding="utf-8")
        assert request(port, "GET", "/" + name)[0] == 404
    assert request(port, "GET", "/.vite/manifest.json")[0] == 404
    for name in ("index-123.js", "index-123.css", "lazy-123.js", "data-123.json",
                 "font-123.woff2", "module-123.wasm", "%E5%9C%B0%E5%9B%BE-123.svg"):
        assert request(port, "GET", "/assets/" + name)[0] == 200
    assert request(port, "GET", "/assets/../index.html")[0] == 404
    # Recheck root containment when reading, not only when loading the manifest.
    asset = static / "assets/index-123.js"
    asset.unlink()
    asset.symlink_to(sentinel)
    assert request(port, "GET", "/assets/index-123.js")[0] == 404


@pytest.mark.parametrize("fault", ["source-root", "missing-output", "escape", "no-entry"])
def test_static_rejects_incomplete_or_invalid_build(tmp_path: Path, fault: str) -> None:
    static = build_static(tmp_path / "dist")
    manifest = static / ".vite/manifest.json"
    if fault == "source-root":
        manifest.unlink()
        (static / "index.html").write_text('<script src="/src/main.tsx"></script>')
    elif fault == "missing-output":
        (static / "assets/lazy-123.js").unlink()
    elif fault == "escape":
        manifest.write_text(json.dumps({"index.html": {"file": "../secret", "isEntry": True}}))
    else:
        manifest.write_text(json.dumps({"src/main.tsx": {"file": "assets/index-123.js"}}))
    with pytest.raises(db.ConfigurationError, match="GDDS_DIRECTORY_STATIC_DIR"):
        DirectoryServer(("127.0.0.1", 0), tmp_path / "directory.sqlite", static,
                        "https://directory.example/", "https://gateway.example/")


class ObservedServer(DirectoryServer):
    max_requests = 2

    def __init__(self, root: Path) -> None:
        self.entered: queue.Queue[None] = queue.Queue()
        self.completed: queue.Queue[None] = queue.Queue()
        self.workers: list[threading.Thread] = []
        super().__init__(("127.0.0.1", 0), root / "directory.sqlite", build_static(root / "dist"),
                         "https://directory.example/", "https://gateway.example/")

    def finish_request(self, request: socket.socket | tuple[bytes, socket.socket], client_address: tuple[str, int]) -> None:
        self.workers.append(threading.current_thread())
        self.entered.put(None)
        super().finish_request(request, client_address)

    def process_request_thread(self, request: socket.socket | tuple[bytes, socket.socket], client_address: tuple[str, int]) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.completed.put(None)


@pytest.fixture
def bounded_http(tmp_path: Path) -> Iterator[ObservedServer]:
    server = ObservedServer(tmp_path)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        assert not thread.is_alive()


def receive_until_closed(client: socket.socket) -> bytes:
    data = b""
    try:
        while chunk := client.recv(4096):
            data += chunk
    except ConnectionResetError:
        pass
    return data


@pytest.mark.parametrize("partial", [
    b"GET /healthz HTTP/1.0",
    b"GET /healthz HTTP/1.0\r\nX-Incomplete: value",
    b"POST /api/handoffs HTTP/1.0\r\nContent-Length: 100\r\n\r\n{",
])
@pytest.mark.parametrize("limit", ["idle", "deadline"])
def test_incomplete_http_requests_expire(
    bounded_http: ObservedServer, partial: bytes, limit: str,
) -> None:
    server = bounded_http
    # Prove each limit independently; the absolute deadline must interrupt even
    # an otherwise live read, so trickling cannot extend a connection forever.
    server.io_timeout = 0.2 if limit == "idle" else 10
    server.request_deadline = 0.2 if limit == "deadline" else 10
    with socket.create_connection(("127.0.0.1", int(server.server_address[1])), timeout=3) as client:
        client.sendall(partial)
        server.entered.get(timeout=3)
        receive_until_closed(client)
        server.completed.get(timeout=3)
    assert request(int(server.server_address[1]), "GET", "/healthz")[0] == 200


def test_concurrency_rejects_excess_and_releases_capacity(bounded_http: ObservedServer) -> None:
    server = bounded_http
    with (socket.create_connection(("127.0.0.1", int(server.server_address[1])), timeout=3) as first,
          socket.create_connection(("127.0.0.1", int(server.server_address[1])), timeout=3) as second):
        first.sendall(b"GET /healthz HTTP/1.0\r\nX-Incomplete:")
        second.sendall(b"POST /api/handoffs HTTP/1.0\r\nContent-Length: 100\r\n\r\n{")
        server.entered.get(timeout=3)
        server.entered.get(timeout=3)
        with socket.create_connection(("127.0.0.1", int(server.server_address[1])), timeout=3) as excess:
            assert receive_until_closed(excess) == b""
        assert server.entered.empty()
        first.shutdown(socket.SHUT_RDWR)
        server.completed.get(timeout=3)
        assert request(int(server.server_address[1]), "GET", "/healthz")[0] == 200


def test_close_interrupts_incomplete_requests_and_joins_workers(bounded_http: ObservedServer) -> None:
    server = bounded_http
    with (socket.create_connection(("127.0.0.1", int(server.server_address[1])), timeout=3) as first,
          socket.create_connection(("127.0.0.1", int(server.server_address[1])), timeout=3) as second):
        first.sendall(b"GET /healthz HTTP/1.0\r\nX-Incomplete:")
        second.sendall(b"POST /api/handoffs HTTP/1.0\r\nContent-Length: 100\r\n\r\n{")
        server.entered.get(timeout=3)
        server.entered.get(timeout=3)
        server.shutdown()
        closing = threading.Thread(target=server.server_close)
        closing.start()
        closing.join(timeout=3)
        assert not closing.is_alive()
        assert len(server.workers) == 2 and all(not worker.is_alive() for worker in server.workers)
        receive_until_closed(first)
        receive_until_closed(second)


def test_truncated_body_is_rejected_even_if_json_is_complete(bounded_http: ObservedServer) -> None:
    with socket.create_connection(("127.0.0.1", int(bounded_http.server_address[1])), timeout=3) as client:
        body = b'{"device_key":"dev-0000000000000000"}'
        client.sendall(b"POST /api/handoffs HTTP/1.0\r\nContent-Length: "
                       + str(len(body) + 1).encode() + b"\r\n\r\n" + body)
        client.shutdown(socket.SHUT_WR)
        response = receive_until_closed(client)
        headers, payload = response.split(b"\r\n\r\n", 1)
        assert headers.startswith(b"HTTP/1.0 400 ")
        assert json.loads(payload)["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize(("payload", "expected"), [
    ({}, "INVALID_REQUEST"),
    ({"device_key": "invalid"}, "INVALID_REQUEST"),
    ({"device_key": "dev-0000000000000000", "return_query": ""}, "INVALID_REQUEST"),
    ({"device_key": "dev-0000000000000000", "return_query": "https://evil.example"}, "INVALID_REQUEST"),
    ({"device_key": "dev-0000000000000000", "return_query": "?q=x#fragment"}, "INVALID_REQUEST"),
    ({"device_key": "dev-0000000000000000", "return_query": "?q=\ud800"}, "INVALID_REQUEST"),
    ({"device_key": "dev-0000000000000000", "return_query": "?" + "x" * 1000}, "INVALID_REQUEST"),
    (b"[" * 1200 + b"0" + b"]" * 1200, "INVALID_REQUEST"),
    ({"device_key": "dev-0000000000000000"}, "DEVICE_NOT_FOUND"),
])
def test_handoff_rejects_invalid_and_unknown(
    http: tuple[Path, Path, int], payload: object, expected: str,
) -> None:
    path, _, port = http
    initialise(path)
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    status, headers, raw_response = request(port, "POST", "/api/handoffs", body)
    response = json.loads(raw_response)
    assert status == (404 if expected == "DEVICE_NOT_FOUND" else 400)
    assert response["code"] == expected
    assert headers["cache-control"] == "no-store"


def test_handoff_states_and_utf8_fragment(http: tuple[Path, Path, int]) -> None:
    path, _, port = http
    project = initialise(path)[0]
    req = {"device_key": project.device_key, "return_query": "?r1=江苏&page=1"}
    assert post(port, req)[2]["code"] == "DEVICE_NOT_PROVISIONED"
    future = datetime.now(UTC) + timedelta(days=1)
    put_session(path, project, future, pending=True)
    assert post(port, req)[2]["code"] == "SESSION_UPDATING"
    put_session(path, project, datetime.now(UTC) - timedelta(days=1))
    assert post(port, req)[2]["code"] == "SESSION_EXPIRED"
    token = put_session(path, project, future)
    digest_before = hashlib.sha256(path.read_bytes()).digest()
    status, headers, response = post(port, req)
    assert status == 200 and headers["cache-control"] == "no-store"
    prefix = "https://gateway.example/#gdds-handoff="
    url = response["gateway_url"]
    if not url.startswith(prefix):
        pytest.fail("handoff URL has unexpected prefix", pytrace=False)
    encoded = url[len(prefix):]
    if "=" in encoded:
        pytest.fail("handoff fragment contains padding", pytrace=False)
    decoded = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    current_token = decoded.pop("token")
    if not hmac.compare_digest(current_token, token):
        pytest.fail("handoff token did not match current credential", pytrace=False)
    assert decoded["gateway_device_external_key"] == project.device_key
    assert decoded["business_project_id"] == project.project_id
    assert decoded["display"]["region1"] == "江苏"
    assert decoded["return_url"] == "https://directory.example/?r1=江苏&page=1"
    assert hashlib.sha256(path.read_bytes()).digest() == digest_before
    conn = db.connect(path)
    try:
        conn.execute("UPDATE projects SET removed=1 WHERE device_key=?", (project.device_key,))
        conn.commit()
    finally:
        conn.close()
    assert post(port, req)[2]["code"] == "DEVICE_NOT_FOUND"


@pytest.mark.parametrize("query", [
    "?r1=" + "江" * 50 + "&r2=" + "苏" * 50 + "&q=" + "站" * 20 + "&scope=region&page=2",
    "?q=" + "江" * 997,
])
def test_handoff_unicode_query_restores_complete_position(
    http: tuple[Path, Path, int], query: str,
) -> None:
    path, _, port = http
    project = initialise(path)[0]
    put_session(path, project, datetime.now(UTC) + timedelta(days=1))
    params = parse_qs(query[1:])
    assert len("?" + urlencode(params, doseq=True)) > 1000
    status, _, response = post(port, {"device_key": project.device_key, "return_query": query})
    assert status == 200
    fragment = response["gateway_url"].split("#gdds-handoff=", 1)[1]
    decoded = json.loads(base64.urlsafe_b64decode(fragment + "=" * (-len(fragment) % 4)))
    # Do not include the credential-bearing response in assertions/snapshots.
    returned = urlsplit(decoded["return_url"])
    assert returned.scheme == "https" and returned.netloc == "directory.example"
    assert parse_qs(returned.query) == params
