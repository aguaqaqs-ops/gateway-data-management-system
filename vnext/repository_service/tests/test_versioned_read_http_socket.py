"""Real-socket HTTP tests for versioned read streaming failures."""

from __future__ import annotations

import http.client
import threading
import time
from collections.abc import Iterator
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]
import pytest
import uvicorn

from gateway_repository_service.arrow_mapping import SqlValueConversionError
from support.arrow_ipc_assertions import assert_lacks_stream_eos
from test_versioned_read_http_integration import (
    ReadHttpIntegrationEnvironment,
    _auth_headers,
    _rows_url,
    _seed_large_items_table,
    create_read_http_environment,
)

pytestmark = [pytest.mark.integration, pytest.mark.serial]


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
    path = _rows_url(env, commit_id)
    query = "table_name=items"
    headers = _auth_headers()

    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30.0)
    try:
        connection.request(
            "GET",
            f"{path}?{query}",
            headers={key: value for key, value in headers.items()},
        )
        response = connection.getresponse()
        assert response.status == 200
        body = b""
        while True:
            try:
                chunk = response.read(4096)
            except http.client.HTTPException:
                break
            if not chunk:
                break
            body += chunk
    finally:
        connection.close()
        server.should_exit = True
        thread.join(timeout=5.0)

    assert body
    assert_lacks_stream_eos(body)
