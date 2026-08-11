"""Real-socket HTTP tests for versioned read streaming failures."""

from __future__ import annotations

import http.client
import threading
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

import httpx2 as httpx
import pyarrow as pa  # type: ignore[import-untyped]
import pytest
import uvicorn

from gateway_repository_service.arrow_mapping import SqlValueConversionError
from support.arrow_ipc_assertions import (
    assert_lacks_stream_eos,
    count_decoded_rows_without_error,
)
from test_versioned_read_http_integration import (
    ReadHttpIntegrationEnvironment,
    _auth_headers,
    _rows_url,
    _seed_large_items_table,
    create_read_http_environment,
)

pytestmark = [pytest.mark.integration, pytest.mark.serial]

_FULL_TABLE_ROW_COUNT = 2500
HTTP_CHUNKED_TERMINATOR = b"0\r\n\r\n"


def _wait_until_server_started(server: uvicorn.Server, *, timeout_seconds: float = 5.0) -> int:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if server.started and server.servers:
            sockets = server.servers[0].sockets
            if sockets:
                _host, port = sockets[0].getsockname()
                return int(port)
        time.sleep(0.01)
    raise AssertionError("uvicorn server did not start in time")


def _fetch_raw_response_bytes(host: str, port: int, path: str, headers: dict[str, str]) -> bytes:
    connection = http.client.HTTPConnection(host, port, timeout=30.0)
    try:
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        assert response.status == 200
        chunks: list[bytes] = []
        while True:
            try:
                chunk = response.read(65536)
            except http.client.IncompleteRead as exc:
                chunks.append(exc.partial)
                break
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        connection.close()


@pytest.fixture
def read_http_socket_env(tmp_path: Any) -> Iterator[ReadHttpIntegrationEnvironment]:
    env = create_read_http_environment(tmp_path)
    try:
        yield env
    finally:
        env.close()


def test_http_socket_midstream_failure_aborts_without_eos(
    read_http_socket_env: ReadHttpIntegrationEnvironment,
) -> None:
    env = read_http_socket_env
    commit_id = _seed_large_items_table(env, sql_name="socket-fail.sql", marker_suffix="21")
    original_open = env.runtime.versioned_read_application.open_table_rows

    def exploding_open(*args: Any, **kwargs: Any) -> tuple[Any, Iterator[pa.RecordBatch]]:
        plan, rows = original_open(*args, **kwargs)

        def _explode() -> Iterator[pa.RecordBatch]:
            for index, batch in enumerate(rows):
                yield batch
                if index == 0:
                    raise SqlValueConversionError(table="items", column="label", sql_type="VARCHAR(32)")

        return plan, _explode()

    env.runtime.versioned_read_application.open_table_rows = exploding_open  # type: ignore[method-assign]

    config = uvicorn.Config(env.app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    port = _wait_until_server_started(server)
    path = f"{_rows_url(env, commit_id)}?table_name=items"
    url = f"http://127.0.0.1:{port}{path}"
    headers = _auth_headers()

    body = b""
    transport_error: BaseException | None = None
    try:
        with httpx.Client(timeout=30.0) as client:
            with client.stream("GET", url, headers=headers) as response:
                assert response.status_code == 200
                assert "chunked" in response.headers.get("transfer-encoding", "").lower()
                try:
                    for chunk in response.iter_bytes():
                        body += chunk
                except (httpx.RemoteProtocolError, httpx.ReadError) as exc:
                    transport_error = exc
    finally:
        parsed = urlparse(url)
        raw_wire = _fetch_raw_response_bytes(parsed.hostname or "127.0.0.1", port, path, headers)
        server.should_exit = True
        thread.join(timeout=5.0)

    decoded_rows = count_decoded_rows_without_error(body)
    assert body
    assert_lacks_stream_eos(body)
    assert 0 < decoded_rows < _FULL_TABLE_ROW_COUNT
    assert transport_error is not None
    assert isinstance(transport_error, (httpx.RemoteProtocolError, httpx.ReadError))
    assert HTTP_CHUNKED_TERMINATOR not in raw_wire
    assert not thread.is_alive()
