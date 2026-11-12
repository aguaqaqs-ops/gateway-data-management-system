"""HTTP contract tests using a real loopback server and private SQLite."""

import base64
import gzip
import hashlib
import hmac
import http.client
import json
import secrets
import subprocess
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from gdds_directory import db, importer
from gdds_directory.http_service import DirectoryServer

HEADER = b"region1,region2,project_name,station_code,pinyin_initials,pinyin_full\n"
DATA = HEADER + "江苏,苏州,名称,SZ-0142,mc,ming cheng\n浙江,宁波,另一,NB-1,ly,\n".encode()


@pytest.fixture
def http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Path, Path, int]]:
    def forbidden(*args: object, **kwargs: object) -> Any:
        pytest.fail("HTTP handler must not spawn a subprocess", pytrace=False)

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    static = tmp_path / "dist"
    static.mkdir()
    (static / "index.html").write_text("directory", encoding="utf-8")
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
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
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
    assert request(port, "GET", "/")[2] == b"directory"
    for path in ("/escape", "/%2e%2e/gateway-sentinel", "/missing", "/api/missing"):
        status, _, _ = request(port, "GET", path)
        assert status == 404
    assert json.loads(request(port, "GET", "/healthz")[2]) == {"status": "ok"}


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
