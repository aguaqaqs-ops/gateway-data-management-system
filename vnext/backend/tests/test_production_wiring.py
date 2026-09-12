"""Production Session/Scope/Head and Repository adapter wiring tests."""

from __future__ import annotations

import io
from pathlib import Path
from uuid import UUID

import httpx
import pyarrow as pa
import pyarrow.ipc as ipc
import pytest

from gateway_backend.bootstrap.operation_worker import build_production_preview_dependencies
from gateway_backend.http.auth import BearerSessionPort
from gateway_backend.http.runtime import prepare_backend_runtime
from gateway_backend.infrastructure.control_db.sqlite_mapping import ProvisionedBaselineHeadRead
from gateway_backend.infrastructure.repository_read.http_arrow import (
    HttpArrowRepositoryTableAccessProvider,
    build_http_repository_provider_factory,
)
from gateway_repository_client.paths import encode_commit_id_path
from tests.support.runtime_settings import (
    TEST_MAPPING_COMMIT_ID,
    TEST_MAPPING_REPOSITORY_ID,
    TEST_REPOSITORY_TOKEN,
    make_backend_settings,
    make_operation_worker_settings,
    prepare_backend_runtime_paths,
)

pytestmark = pytest.mark.unit

REPO_ID = UUID(TEST_MAPPING_REPOSITORY_ID)
COMMIT_ID = "commit-c1"


def _arrow_ipc_table() -> bytes:
    table = pa.table({"id": [1]})
    buffer = io.BytesIO()
    with ipc.new_stream(buffer, table.schema) as writer:
        writer.write_table(table)
    return buffer.getvalue()


def test_prepare_backend_runtime_uses_provisioned_identity_ports(tmp_path: Path) -> None:
    prepare_backend_runtime_paths(tmp_path)
    settings = make_backend_settings(
        tmp_path,
        control_db_path=tmp_path / "control" / "control.sqlite3",
        artifact_root=tmp_path / "artifacts",
        repository_bearer_token_file=tmp_path / "repository-bearer-token",
    )
    runtime = prepare_backend_runtime(settings)
    assert type(runtime.workspace_http.session_port) is BearerSessionPort
    assert type(runtime.workspace_http.scope_resolution).__name__ == "ProvisionedScopeResolution"
    assert type(runtime.workspace_http.baseline_head_read) is ProvisionedBaselineHeadRead


def test_production_worker_wires_http_arrow_adapter_and_mapping_head(tmp_path: Path) -> None:
    prepare_backend_runtime_paths(tmp_path)
    settings = make_operation_worker_settings(
        tmp_path,
        control_db_path=tmp_path / "control" / "control.sqlite3",
        artifact_root=tmp_path / "artifacts",
        repository_bearer_token_file=tmp_path / "repository-bearer-token",
        provisioned_mapping_file=tmp_path / "provisioned-mapping.json",
    )
    deps, _write_uow = build_production_preview_dependencies(settings)
    assert type(deps.baseline_head_read) is ProvisionedBaselineHeadRead
    provider = deps.repository_provider_factory(TEST_MAPPING_REPOSITORY_ID, TEST_MAPPING_COMMIT_ID)
    assert type(provider) is HttpArrowRepositoryTableAccessProvider
    head = deps.baseline_head_read.get_current_head(TEST_MAPPING_REPOSITORY_ID)
    assert head.business_baseline_commit_id == TEST_MAPPING_COMMIT_ID


def test_http_arrow_adapter_reads_exact_commit_catalog_and_rows() -> None:
    catalog = {
        "commit_id": COMMIT_ID,
        "tables": [
            {
                "name": "items",
                "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                "primary_key": ["id"],
                "row_count": 1,
            }
        ],
    }
    encoded = encode_commit_id_path(COMMIT_ID)
    catalog_path = f"/v1/repositories/{REPO_ID}/versioned/commits/{encoded}/catalog"
    rows_path = f"/v1/repositories/{REPO_ID}/versioned/commits/{encoded}/rows"
    arrow_bytes = _arrow_ipc_table()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == f"Bearer {TEST_REPOSITORY_TOKEN}"
        if request.url.path == catalog_path:
            return httpx.Response(
                200,
                json={"catalog": catalog},
                headers={"X-Request-ID": "req-catalog"},
            )
        if request.url.path == rows_path:
            assert request.url.params.get("table_name") == "items"
            return httpx.Response(
                200,
                content=arrow_bytes,
                headers={
                    "X-Request-ID": "req-rows",
                    "Content-Type": "application/vnd.apache.arrow.stream",
                },
            )
        return httpx.Response(404, json={"code": "NOT_FOUND"}, headers={"X-Request-ID": "req-miss"})

    factory = build_http_repository_provider_factory(
        base_url="http://repository.test",
        bearer_token=TEST_REPOSITORY_TOKEN,
        timeout_seconds=30.0,
        transport=httpx.MockTransport(handler),
    )
    provider = factory(str(REPO_ID), COMMIT_ID)
    assert type(provider) is HttpArrowRepositoryTableAccessProvider
    from gateway_backend.capabilities.snapshot_materialization.contracts import RepositoryRef

    session = provider.open_ref(
        RepositoryRef(repository_id=str(REPO_ID), ref=COMMIT_ID),
        None,
    )
    loaded = session.get_catalog()
    assert loaded.repository_id == str(REPO_ID)
    assert loaded.resolved_commit_hash == COMMIT_ID
    assert loaded.tables[0].table_name == "items"
    reader = session.open_table_reader("items")
    rows = tuple(reader.stream_rows())
    assert rows == ((1,),)
    session.close()
