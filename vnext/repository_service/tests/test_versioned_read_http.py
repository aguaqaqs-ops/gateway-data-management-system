"""HTTP unit tests for commit-pinned versioned read routes."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock
from uuid import UUID

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.ipc as pa_ipc  # type: ignore[import-untyped]
import pytest

from gateway_repository_contracts import (
    COMMIT_NOT_FOUND_CODE,
    REF_NOT_FOUND_CODE,
    REPOSITORY_NOT_FOUND_CODE,
    TABLE_NOT_FOUND_CODE,
    UNKNOWN_SQL_TYPE_CODE,
    VERSIONED_READ_ARROW_MEDIA_TYPE,
    UnknownTypePolicy,
)
from gateway_repository_service.arrow_mapping import (
    ColumnCatalog,
    TableCatalog,
    UnknownSqlTypeError,
    compile_table_plan,
)
from gateway_repository_service.http.readiness import ReadinessPort
from gateway_repository_service.versioned_read.arrow_bridge import ArrowIpcStreamBridge
from gateway_repository_service.versioned_read.errors import (
    CommitNotFoundError,
    MainRefNotFoundError,
    ProviderUnavailableError,
    RepositoryNotVisibleError,
    TableNotFoundError,
    VersionedReadError,
)
from support.http_harness import (
    PRODUCTION_OPENAPI_PATHS,
    ImportHttpTestEnvironment,
    assert_request_id_header,
    create_import_http_environment,
)

pytestmark = pytest.mark.unit


class NotReadyReadiness(ReadinessPort):
    def is_ready(self) -> bool:
        return False

    def not_ready_message(self) -> str:
        return "service is not ready"


@pytest.fixture
def env(tmp_path: Path) -> Iterator[ImportHttpTestEnvironment]:
    environment = create_import_http_environment(tmp_path)
    yield environment
    environment.close()


def _auth_headers(*, token: str = "test-bearer-token", request_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if request_id is not None:
        headers["X-Request-ID"] = request_id
    return headers


def _items_table(row_count: int = 1) -> TableCatalog:
    return TableCatalog(
        "items",
        (
            ColumnCatalog(
                name="id",
                sql_type="BIGINT",
                nullable=False,
                primary_key_position=1,
            ),
        ),
        row_count=row_count,
    )


def _plan_and_batches(row_count: int = 1) -> tuple[Any, list[pa.RecordBatch]]:
    table = _items_table(row_count=row_count)
    plan = compile_table_plan(table, UnknownTypePolicy.REJECT)
    if row_count == 0:
        return plan, []
    normalized = [plan.normalize_row((index + 1,)) for index in range(row_count)]
    return plan, [plan.record_batch(normalized)]


def _read_app(env: ImportHttpTestEnvironment) -> MagicMock:
    return cast(MagicMock, env.runtime.versioned_read_application)


def _configure_resolve(env: ImportHttpTestEnvironment, commit_id: str = "commit-1") -> UUID:
    repository_id = env.seed_repository()
    _read_app(env).resolve_main.return_value = commit_id
    return repository_id


def test_resolve_requires_auth(env: ImportHttpTestEnvironment) -> None:
    repository_id = _configure_resolve(env)
    response = env.client.get(
        f"/v1/repositories/{repository_id}/versioned/refs/main",
        headers=_auth_headers(token="wrong"),
    )
    assert response.status_code == 401


def test_resolve_requires_readiness(tmp_path: Path) -> None:
    environment = create_import_http_environment(tmp_path)
    try:
        app = cast(Any, environment.client.app)
        app.state.readiness = NotReadyReadiness()
        repository_id = _configure_resolve(environment)
        response = environment.client.get(
            f"/v1/repositories/{repository_id}/versioned/refs/main",
            headers=_auth_headers(),
        )
        assert response.status_code == 503
        assert response.json()["code"] == "SERVICE_NOT_READY"
    finally:
        environment.close()


def test_resolve_returns_commit_id(env: ImportHttpTestEnvironment) -> None:
    repository_id = _configure_resolve(env, "opaque-commit")
    response = env.client.get(
        f"/v1/repositories/{repository_id}/versioned/refs/main",
        headers=_auth_headers(request_id="abc123"),
    )
    assert response.status_code == 200
    assert response.json() == {"ref_name": "main", "commit_id": "opaque-commit"}
    assert_request_id_header(response)


def test_resolve_auto_generates_request_id(env: ImportHttpTestEnvironment) -> None:
    repository_id = _configure_resolve(env)
    response = env.client.get(
        f"/v1/repositories/{repository_id}/versioned/refs/main",
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    assert_request_id_header(response)


@pytest.mark.parametrize(
    ("side_effect", "status_code", "error_code"),
    [
        (RepositoryNotVisibleError("missing"), 404, REPOSITORY_NOT_FOUND_CODE),
        (MainRefNotFoundError("missing"), 404, REF_NOT_FOUND_CODE),
        (ProviderUnavailableError("down"), 503, "SERVICE_NOT_READY"),
    ],
)
def test_resolve_error_matrix(
    env: ImportHttpTestEnvironment,
    side_effect: Exception,
    status_code: int,
    error_code: str,
) -> None:
    repository_id = env.seed_repository()
    _read_app(env).resolve_main.side_effect = side_effect
    response = env.client.get(
        f"/v1/repositories/{repository_id}/versioned/refs/main",
        headers=_auth_headers(),
    )
    assert response.status_code == status_code
    body = response.json()
    assert body["code"] == error_code
    request_id = assert_request_id_header(response)
    assert body["request_id"] == request_id


class _UnmappedVersionedReadError(VersionedReadError):
    pass


def test_resolve_maps_unclassified_versioned_read_error_to_internal_error(
    env: ImportHttpTestEnvironment,
) -> None:
    repository_id = env.seed_repository()
    _read_app(env).resolve_main.side_effect = _UnmappedVersionedReadError("boom")
    response = env.client.get(
        f"/v1/repositories/{repository_id}/versioned/refs/main",
        headers=_auth_headers(),
    )
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"


@pytest.mark.parametrize(
  ("method_name", "path"),
  [
      ("resolve_main", "/v1/repositories/{repository_id}/versioned/refs/main"),
      (
          "get_catalog",
          "/v1/repositories/{repository_id}/versioned/commits/commit-1/catalog",
      ),
      (
          "open_table_rows",
          "/v1/repositories/{repository_id}/versioned/commits/commit-1/rows?table_name=items",
      ),
  ],
)
def test_versioned_read_maps_unexpected_exception_to_internal_error(
    env: ImportHttpTestEnvironment,
    method_name: str,
    path: str,
) -> None:
    repository_id = env.seed_repository()
    getattr(_read_app(env), method_name).side_effect = RuntimeError("boom")
    response = env.client.get(
        path.format(repository_id=repository_id),
        headers=_auth_headers(),
    )
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"


def test_catalog_returns_wire_shape(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    table = _items_table()
    _read_app(env).get_catalog.return_value = (table,)
    response = env.client.get(
        f"/v1/repositories/{repository_id}/versioned/commits/commit-1/catalog",
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["catalog"]["commit_id"] == "commit-1"
    assert payload["catalog"]["tables"][0]["name"] == "items"
    assert payload["catalog"]["tables"][0]["primary_key"] == ["id"]


@pytest.mark.parametrize(
    ("side_effect", "status_code", "error_code"),
    [
        (RepositoryNotVisibleError("missing"), 404, REPOSITORY_NOT_FOUND_CODE),
        (CommitNotFoundError("missing"), 404, COMMIT_NOT_FOUND_CODE),
        (ProviderUnavailableError("down"), 503, "SERVICE_NOT_READY"),
    ],
)
def test_catalog_error_matrix(
    env: ImportHttpTestEnvironment,
    side_effect: Exception,
    status_code: int,
    error_code: str,
) -> None:
    repository_id = env.seed_repository()
    _read_app(env).get_catalog.side_effect = side_effect
    response = env.client.get(
        f"/v1/repositories/{repository_id}/versioned/commits/commit-1/catalog",
        headers=_auth_headers(),
    )
    assert response.status_code == status_code
    body = response.json()
    assert body["code"] == error_code
    request_id = assert_request_id_header(response)
    assert body["request_id"] == request_id


def test_catalog_malformed_provider_shape_maps_to_503(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    invalid = TableCatalog(
        "",
        (
            ColumnCatalog(
                name="id",
                sql_type="BIGINT",
                nullable=False,
                primary_key_position=1,
            ),
        ),
        row_count=0,
    )
    _read_app(env).get_catalog.return_value = (invalid,)
    response = env.client.get(
        f"/v1/repositories/{repository_id}/versioned/commits/commit-1/catalog",
        headers=_auth_headers(),
    )
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_NOT_READY"


def test_rows_returns_arrow_stream(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    plan, batches = _plan_and_batches()
    _read_app(env).open_table_rows.return_value = (plan, iter(batches))
    response = env.client.get(
        f"/v1/repositories/{repository_id}/versioned/commits/commit-1/rows",
        params={"table_name": "items"},
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(VERSIONED_READ_ARROW_MEDIA_TYPE)
    reader = pa_ipc.open_stream(response.content)
    decoded = list(reader)
    assert len(decoded) == 1
    assert decoded[0].column("id").to_pylist() == [1]


def test_rows_empty_table_returns_schema_and_eos(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    plan, _ = _plan_and_batches(row_count=0)
    _read_app(env).open_table_rows.return_value = (plan, iter(()))
    response = env.client.get(
        f"/v1/repositories/{repository_id}/versioned/commits/commit-1/rows",
        params={"table_name": "items"},
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    reader = pa_ipc.open_stream(response.content)
    assert reader.schema == plan.expected_schema
    assert list(reader) == []


@pytest.mark.parametrize(
    ("side_effect", "status_code", "error_code"),
    [
        (RepositoryNotVisibleError("missing"), 404, REPOSITORY_NOT_FOUND_CODE),
        (CommitNotFoundError("missing"), 404, COMMIT_NOT_FOUND_CODE),
        (TableNotFoundError("missing"), 404, TABLE_NOT_FOUND_CODE),
        (UnknownSqlTypeError("unknown", table="items", column="payload"), 422, UNKNOWN_SQL_TYPE_CODE),
        (ProviderUnavailableError("down"), 503, "SERVICE_NOT_READY"),
    ],
)
def test_rows_preflight_error_matrix(
    env: ImportHttpTestEnvironment,
    side_effect: Exception,
    status_code: int,
    error_code: str,
) -> None:
    repository_id = env.seed_repository()
    _read_app(env).open_table_rows.side_effect = side_effect
    response = env.client.get(
        f"/v1/repositories/{repository_id}/versioned/commits/commit-1/rows",
        params={"table_name": "items"},
        headers=_auth_headers(),
    )
    assert response.status_code == status_code
    body = response.json()
    assert body["code"] == error_code
    request_id = assert_request_id_header(response)
    assert body["request_id"] == request_id


def test_rows_rejects_invalid_table_name(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    response = env.client.get(
        f"/v1/repositories/{repository_id}/versioned/commits/commit-1/rows",
        params={"table_name": " bad"},
        headers=_auth_headers(),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_rows_defaults_unknown_type_policy_to_reject(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    plan, batches = _plan_and_batches()
    _read_app(env).open_table_rows.return_value = (plan, iter(batches))
    env.client.get(
        f"/v1/repositories/{repository_id}/versioned/commits/commit-1/rows",
        params={"table_name": "items"},
        headers=_auth_headers(),
    )
    _read_app(env).open_table_rows.assert_called_once()
    call = _read_app(env).open_table_rows.call_args
    assert call.args[3] == UnknownTypePolicy.REJECT


def test_rows_preflight_completes_before_response_body(env: ImportHttpTestEnvironment) -> None:
    repository_id = env.seed_repository()
    plan, batches = _plan_and_batches()
    calls: list[str] = []

    def open_rows(*_args: object, **_kwargs: object) -> tuple[Any, Iterator[pa.RecordBatch]]:
        calls.append("preflight")
        return plan, iter(batches)

    _read_app(env).open_table_rows.side_effect = open_rows
    response = env.client.get(
        f"/v1/repositories/{repository_id}/versioned/commits/commit-1/rows",
        params={"table_name": "items"},
        headers=_auth_headers(),
    )
    assert calls == ["preflight"]
    assert response.status_code == 200
    assert response.content


def test_arrow_bridge_backpressure_and_first_batch_barrier() -> None:
    plan, batches = _plan_and_batches()
    release = threading.Event()
    started = threading.Event()

    def gated_batches() -> Iterator[pa.RecordBatch]:
        started.set()
        assert release.wait(timeout=2.0)
        yield from batches

    cancellation = threading.Event()
    bridge = ArrowIpcStreamBridge(plan, gated_batches(), cancellation)

    async def consume() -> bytes:
        chunks: list[bytes] = []
        async for chunk in bridge.iter_bytes():
            chunks.append(chunk)
        return b"".join(chunks)

    import asyncio

    async def run() -> tuple[bytes, bool]:
        task = asyncio.create_task(consume())
        assert started.wait(timeout=2.0)
        await asyncio.sleep(0.05)
        assert not task.done()
        release.set()
        return await task, started.is_set()

    body, was_started = asyncio.run(run())
    assert was_started
    assert body
    reader = pa_ipc.open_stream(body)
    assert list(reader)


def test_production_openapi_paths(env: ImportHttpTestEnvironment) -> None:
    paths = env.client.get("/openapi.json").json()["paths"]
    assert set(paths.keys()) == PRODUCTION_OPENAPI_PATHS


def test_openapi_rows_declares_binary_arrow_media(env: ImportHttpTestEnvironment) -> None:
    schema = env.client.get("/openapi.json").json()
    rows_path = schema["paths"]["/v1/repositories/{repository_id}/versioned/commits/{commit_id}/rows"]["get"]
    assert rows_path.get("requestBody") is None
    success_content = rows_path["responses"]["200"]["content"]
    assert "application/json" not in success_content
    success = success_content[VERSIONED_READ_ARROW_MEDIA_TYPE]
    assert success["schema"]["type"] == "string"
    assert success["schema"]["format"] == "binary"
    assert rows_path["responses"]["200"]["headers"]["X-Request-ID"]["schema"]["type"] == "string"
    table_param = rows_path["parameters"]
    assert any(item.get("name") == "table_name" for item in table_param)
    policy_param = next(item for item in table_param if item.get("name") == "unknown_type_policy")
    assert policy_param["schema"]["default"] == "REJECT"
    commit_param = next(
        item for item in rows_path["parameters"] if item.get("name") == "commit_id" and item.get("in") == "path"
    )
    assert commit_param["schema"]["minLength"] == 1
    assert commit_param["schema"]["maxLength"] == 1024
    table_name_param = next(item for item in table_param if item.get("name") == "table_name")
    assert table_name_param["schema"]["minLength"] == 1
    assert table_name_param["schema"]["maxLength"] == 64
    assert "pattern" in table_name_param["schema"]


def test_openapi_read_routes_declare_simple_error_and_request_id(env: ImportHttpTestEnvironment) -> None:
    paths = env.client.get("/openapi.json").json()["paths"]
    for path in (
        "/v1/repositories/{repository_id}/versioned/refs/{ref_name}",
        "/v1/repositories/{repository_id}/versioned/commits/{commit_id}/catalog",
        "/v1/repositories/{repository_id}/versioned/commits/{commit_id}/rows",
    ):
        operation = paths[path]["get"]
        for status_code in ("401", "404", "422", "503"):
            response = operation["responses"][status_code]
            assert response["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/SimpleError"
            }
            assert response["headers"]["X-Request-ID"]["schema"]["type"] == "string"
        assert operation["responses"]["200"]["headers"]["X-Request-ID"]["schema"]["type"] == "string"


def test_openapi_has_no_json_rows_or_latest_terms(env: ImportHttpTestEnvironment) -> None:
    paths = env.client.get("/openapi.json").json()["paths"]
    read_paths = {
        "/v1/repositories/{repository_id}/versioned/refs/{ref_name}",
        "/v1/repositories/{repository_id}/versioned/commits/{commit_id}/catalog",
        "/v1/repositories/{repository_id}/versioned/commits/{commit_id}/rows",
    }
    serialized = json.dumps({path: paths[path] for path in read_paths})
    lowered = serialized.lower()
    assert "json rows" not in lowered
    assert "latest" not in lowered
    assert "checkpoint" not in lowered
    assert "digest" not in lowered


def test_get_routes_have_no_request_body(env: ImportHttpTestEnvironment) -> None:
    openapi = env.client.get("/openapi.json").json()["paths"]
    for path in (
        "/v1/repositories/{repository_id}/versioned/refs/{ref_name}",
        "/v1/repositories/{repository_id}/versioned/commits/{commit_id}/catalog",
        "/v1/repositories/{repository_id}/versioned/commits/{commit_id}/rows",
    ):
        assert openapi[path]["get"].get("requestBody") is None
