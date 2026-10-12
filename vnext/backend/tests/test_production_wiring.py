"""Production Session/Scope/Head and Repository adapter wiring tests."""

from __future__ import annotations

import io
from pathlib import Path
from uuid import UUID

import httpx
import pyarrow as pa
import pyarrow.ipc as ipc
import pytest

from gateway_backend.application.history.compare_jobs import history_compare_job_definitions
from gateway_backend.application.preview_jobs import preview_job_definitions
from gateway_backend.capabilities.table_rules.contracts import RULESET_VERSION
from gateway_backend.bootstrap.operation_worker import build_production_preview_dependencies
from gateway_backend.capabilities.snapshot_materialization.contracts import RepositoryRef
from gateway_backend.domain.workspace.models import BaselineHead, InputCompleteness
from gateway_backend.http.auth import LiveFileSessionPort
from gateway_backend.bootstrap.composition import (
    HttpRepositoryMainResolvePort,
    build_workspace_job_registry,
    prepare_backend_runtime,
)
from gateway_backend.application.submit_registry import submit_job_definitions
from gateway_backend.artifacts import ArtifactRef
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore
from gateway_backend.infrastructure.control_db import ControlDbUnitOfWork
from gateway_shared_kernel import DigestRef, raw_blob_digest
from tests.support.preview_fixtures import (
    make_canonical_artifact_fixture,
    make_preview_canonical_bindings,
)
from tests.support.workspace_fixtures import FixedScopeResolutionPort, make_identity
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


def _authoritative_baseline_head(db_path: Path) -> BaselineHead:
    return ProvisionedBaselineHeadRead(db_path).get_current_head(TEST_MAPPING_REPOSITORY_ID)


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
    runtime = prepare_backend_runtime(settings, skip_repository_ready_probe=True)
    assert type(runtime.workspace_http.session_port) is LiveFileSessionPort
    assert type(runtime.workspace_http.scope_resolution).__name__ == "ProvisionedScopeResolution"
    assert type(runtime.workspace_http.baseline_head_read) is ProvisionedBaselineHeadRead
    assert type(runtime.workspace_http.main_resolve) is HttpRepositoryMainResolvePort
    registry = build_workspace_job_registry()
    expected_definitions = (
        preview_job_definitions() + submit_job_definitions() + history_compare_job_definitions()
    )
    expected_keys = {definition.key for definition in expected_definitions}
    assert {definition.key for definition in registry.definitions()} == expected_keys
    for definition in expected_definitions:
        resolved = registry.get(definition.key)
        assert resolved.decoder_identity == definition.decoder_identity
        assert resolved.handler_identity == definition.handler_identity


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


def _arrow_ipc_batches(*groups: list[int]) -> bytes:
    schema = pa.schema([("id", pa.int64())])
    buffer = io.BytesIO()
    with ipc.new_stream(buffer, schema) as writer:
        for values in groups:
            writer.write_batch(pa.record_batch([values], schema=schema))
    return buffer.getvalue()


def test_http_arrow_streams_record_batches_without_session_row_cache() -> None:
    catalog = {
        "commit_id": COMMIT_ID,
        "tables": [
            {
                "name": "items",
                "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                "primary_key": ["id"],
                "row_count": 3,
            }
        ],
    }
    encoded = encode_commit_id_path(COMMIT_ID)
    catalog_path = f"/v1/repositories/{REPO_ID}/versioned/commits/{encoded}/catalog"
    rows_path = f"/v1/repositories/{REPO_ID}/versioned/commits/{encoded}/rows"
    arrow_bytes = _arrow_ipc_batches([1, 2], [3])
    row_requests = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == catalog_path:
            return httpx.Response(200, json={"catalog": catalog}, headers={"X-Request-ID": "req-catalog"})
        if request.url.path == rows_path:
            row_requests["count"] += 1
            return httpx.Response(
                200,
                content=arrow_bytes,
                headers={
                    "X-Request-ID": f"req-rows-{row_requests['count']}",
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
    session = factory(str(REPO_ID), COMMIT_ID).open_ref(
        RepositoryRef(repository_id=str(REPO_ID), ref=COMMIT_ID),
        None,
    )
    reader = session.open_table_reader("items")
    assert tuple(reader.stream_rows()) == ((1,), (2,), (3,))
    assert not hasattr(session, "_rows")
    assert row_requests["count"] == 1
    assert tuple(session.open_table_reader("items").stream_rows()) == ((1,), (2,), (3,))
    assert row_requests["count"] == 2
    session.close()


def _repository_catalog_transport(
    commit_id: str = COMMIT_ID,
    *,
    include_main_resolve: bool = False,
    main_commit_id: str = "commit-main",
) -> httpx.MockTransport:
    catalog = {
        "commit_id": commit_id,
        "tables": [
            {
                "name": "items",
                "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                "primary_key": ["id"],
                "row_count": 1,
            }
        ],
    }
    encoded = encode_commit_id_path(commit_id)
    catalog_path = f"/v1/repositories/{REPO_ID}/versioned/commits/{encoded}/catalog"
    rows_path = f"/v1/repositories/{REPO_ID}/versioned/commits/{encoded}/rows"
    main_path = f"/v1/repositories/{REPO_ID}/versioned/refs/main"

    def handler(request: httpx.Request) -> httpx.Response:
        if include_main_resolve and request.url.path == main_path:
            return httpx.Response(
                200,
                json={"ref_name": "main", "commit_id": main_commit_id},
                headers={"X-Request-ID": "req-main"},
            )
        if request.url.path == catalog_path:
            return httpx.Response(200, json={"catalog": catalog}, headers={"X-Request-ID": "req-catalog"})
        if request.url.path == rows_path:
            return httpx.Response(
                200,
                content=_arrow_ipc_table(),
                headers={
                    "X-Request-ID": "req-rows",
                    "Content-Type": "application/vnd.apache.arrow.stream",
                },
            )
        return httpx.Response(404, json={"code": "NOT_FOUND"}, headers={"X-Request-ID": "req-miss"})

    return httpx.MockTransport(handler)


def test_http_repository_main_resolve_uses_exact_wire() -> None:
    path = f"/v1/repositories/{REPO_ID}/versioned/refs/main"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.headers.get("Authorization") == f"Bearer {TEST_REPOSITORY_TOKEN}"
        assert request.url.path == path
        return httpx.Response(
            200,
            json={"ref_name": "main", "commit_id": "commit-main"},
            headers={"X-Request-ID": "req-main"},
        )

    port = HttpRepositoryMainResolvePort(
        base_url="http://repository.test",
        bearer_token=TEST_REPOSITORY_TOKEN,
        timeout_seconds=30.0,
        transport=httpx.MockTransport(handler),
    )
    assert port.resolve_main_expected_commit(repository_id=str(REPO_ID)) == "commit-main"


def test_http_arrow_repository_session_only_streams_requested_table() -> None:
    catalog = {
        "commit_id": COMMIT_ID,
        "tables": [
            {
                "name": "items",
                "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                "primary_key": ["id"],
                "row_count": 1,
            },
            {
                "name": "other",
                "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                "primary_key": ["id"],
                "row_count": 1,
            },
        ],
    }
    encoded = encode_commit_id_path(COMMIT_ID)
    catalog_path = f"/v1/repositories/{REPO_ID}/versioned/commits/{encoded}/catalog"
    rows_path = f"/v1/repositories/{REPO_ID}/versioned/commits/{encoded}/rows"
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == catalog_path:
            return httpx.Response(200, json={"catalog": catalog}, headers={"X-Request-ID": "req-catalog"})
        if request.url.path == rows_path:
            table_name = request.url.params.get("table_name")
            requested.append(str(table_name))
            payload = _arrow_ipc_table() if table_name == "items" else _arrow_ipc_batches([9])
            return httpx.Response(
                200,
                content=payload,
                headers={
                    "X-Request-ID": f"req-{table_name}",
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
    session = factory(str(REPO_ID), COMMIT_ID).open_ref(
        RepositoryRef(repository_id=str(REPO_ID), ref=COMMIT_ID),
        None,
    )
    assert requested == []
    assert not hasattr(session, "_rows")
    reader = session.open_table_reader("items")
    assert tuple(reader.stream_rows())
    reader.close()
    assert requested == ["items"]
    session.close()


def test_bundle_artifact_closure_maps_surface_and_hidden_records_refs() -> None:
    from dataclasses import replace

    from gateway_backend.application.preview_jobs import surface_artifact_closure
    from gateway_backend.capabilities.bundle_assembly._refs import collect_surface_refs
    from gateway_backend.capabilities.comparison.contracts import (
        ComparisonRecordsClosure,
        ComparisonTableFact,
        ComparisonTableStatus,
        RecordsArtifactFamily,
        RecordsClosureEntry,
    )
    from gateway_backend.capabilities.surface_assembly import (
        assemble_surface,
        compute_surface_digest,
        validate_surface,
    )
    from gateway_backend.capabilities.surface_assembly.contracts import SurfaceProjectionRef
    from tests.test_surface_assembly import _facts, _ref, _request as _surface_request

    ordered_ref = _ref("ordered-manifest")
    projection_ref = _ref("projection-body")
    risk_ref = _ref("projection-risk")
    records_ref = _ref("hidden-records", "application/octet-stream")
    records_manifest_ref = _ref("hidden-records-manifest")
    records_closure_ref = _ref("hidden-records-closure")
    result = assemble_surface(
        _surface_request(_facts(ComparisonTableFact(table_name="orders", status=ComparisonTableStatus.UNCHANGED)))
    )
    assert result.surface is not None
    table = replace(
        result.surface.tables[0],
        ordered_extension={"ordering_manifest_ref": ordered_ref},
    )
    surface = replace(
        result.surface,
        tables=(table,),
        projections=(
            SurfaceProjectionRef(
                projection_id="proj-1",
                projection_kind="summary",
                projection_ref=projection_ref,
                projection_digest=projection_ref.raw_sha256,
                risk_summary_ref=risk_ref,
            ),
        ),
        refs=replace(result.surface.refs, records_closure_ref=records_closure_ref),
    )
    surface = replace(surface, surface_digest=compute_surface_digest(surface))
    validate_surface(surface)

    records_closure = ComparisonRecordsClosure(
        comparison_digest=surface.comparison_digest,
        facts_core_digest=raw_blob_digest(b"facts"),
        records=(
            RecordsClosureEntry(
                table_name="orders",
                family=RecordsArtifactFamily.STANDARD,
                records_ref=records_ref,
                records_manifest_ref=records_manifest_ref,
                records_manifest_digest=records_manifest_ref.raw_sha256,
                records_content_digest=records_ref.raw_sha256,
                record_count=1,
            ),
        ),
        closure_manifest_digest=records_closure_ref.raw_sha256,
    )
    closure = surface_artifact_closure(surface, "pair-1", records_closure)
    paths = {binding.logical_path for binding in closure.entries}
    assert any(path.startswith("pairs/pair-1/ordered/") for path in paths)
    assert any(path.startswith("pairs/pair-1/projections/") for path in paths)
    assert "pairs/pair-1/comparison/records/orders/standard/rows.bin" in paths
    assert "pairs/pair-1/comparison/records/orders/standard/manifest.json" in paths
    covered = {binding.source_ref for binding in closure.entries}
    for ref in collect_surface_refs(surface):
        assert ref in covered


def _seed_protected_artifacts(artifact_root: Path, refs: tuple[ArtifactRef, ...], payloads: dict[str, bytes]) -> None:
    store = LocalArtifactStore(artifact_root)
    for ref in refs:
        store.put(payloads[ref.artifact_id], ref)


_PAYLOAD_INITIAL = b"a"
_PAYLOAD_MODIFIED = b"ab"
_PAYLOAD_CLOSURE = b"c"
_SHA_INITIAL = raw_blob_digest(_PAYLOAD_INITIAL).value
_SHA_MODIFIED = raw_blob_digest(_PAYLOAD_MODIFIED).value
_SHA_CLOSURE = raw_blob_digest(_PAYLOAD_CLOSURE).value
_PREVIEW_CANONICAL_DIGEST = "sha256:" + "p" * 62 + "ca"


def _production_submit_preview_refs() -> tuple[ArtifactRef, ...]:
    return (
        ArtifactRef(
            artifact_id="initial-1",
            media_type="application/gzip",
            size_bytes=len(_PAYLOAD_INITIAL),
            raw_sha256=DigestRef(_SHA_INITIAL),
        ),
        ArtifactRef(
            artifact_id="modified-1",
            media_type="application/gzip",
            size_bytes=len(_PAYLOAD_MODIFIED),
            raw_sha256=DigestRef(_SHA_MODIFIED),
        ),
        ArtifactRef(
            artifact_id="closure-1",
            media_type="application/json",
            size_bytes=len(_PAYLOAD_CLOSURE),
            raw_sha256=DigestRef(_SHA_CLOSURE),
        ),
        *make_canonical_artifact_fixture().refs,
    )


def test_accept_submit_returns_202_with_production_runtime(tmp_path: Path) -> None:
    from dataclasses import replace
    from datetime import UTC, datetime
    from fastapi.testclient import TestClient

    from gateway_backend.app import create_app
    from gateway_backend.application.workspace import create_or_get_workspace
    from gateway_backend.domain.workspace.models import (
        PreviewResult,
        PreviewResultDigests,
        SourceArtifactBinding,
        SourceArtifactRole,
        UploadRevision,
    )
    from gateway_backend.http.dependencies import ClosableAdmissionGate
    from tests.support.runtime_settings import TEST_SESSION_TOKEN

    fixed_now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
    transport = _repository_catalog_transport(
        TEST_MAPPING_COMMIT_ID,
        include_main_resolve=True,
    )
    prepare_backend_runtime_paths(tmp_path)
    artifact_root = tmp_path / "artifacts"
    settings = make_backend_settings(
        tmp_path,
        control_db_path=tmp_path / "control" / "control.sqlite3",
        artifact_root=artifact_root,
        repository_bearer_token_file=tmp_path / "repository-bearer-token",
    )
    runtime = prepare_backend_runtime(
        settings,
        skip_repository_ready_probe=True,
        repository_transport=transport,
    )
    db_path = tmp_path / "control" / "control.sqlite3"
    baseline_head = _authoritative_baseline_head(db_path)
    protected_refs = _production_submit_preview_refs()
    canonical_fixture = make_canonical_artifact_fixture()
    payloads = {
        "initial-1": _PAYLOAD_INITIAL,
        "modified-1": _PAYLOAD_MODIFIED,
        "closure-1": _PAYLOAD_CLOSURE,
        **canonical_fixture.payloads,
    }
    _seed_protected_artifacts(
        artifact_root,
        protected_refs,
        payloads,
    )
    scope_resolution = FixedScopeResolutionPort(
        repository_id=TEST_MAPPING_REPOSITORY_ID,
        baseline_head=baseline_head,
    )
    context = make_identity(permissions=frozenset({"upload_submit_workspace", "workspace_read"}))
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        created = create_or_get_workspace(
            context=context,
            scope_resolution=scope_resolution,
            repository=unit_of_work.workspace,
            created_at=fixed_now,
        )
        workspace = created.workspace
        upload_revision = UploadRevision(
            upload_revision_id="ur-accept-1",
            workspace_id=workspace.workspace_id,
            generation=1,
            input_completeness=InputCompleteness.FULL,
            source_artifacts={
                SourceArtifactRole.INITIAL: SourceArtifactBinding(
                    artifact_id="initial-1",
                    media_type="application/gzip",
                    size_bytes=len(_PAYLOAD_INITIAL),
                    raw_sha256=_SHA_INITIAL,
                ),
                SourceArtifactRole.MODIFIED: SourceArtifactBinding(
                    artifact_id="modified-1",
                    media_type="application/gzip",
                    size_bytes=len(_PAYLOAD_MODIFIED),
                    raw_sha256=_SHA_MODIFIED,
                ),
            },
            idempotency_key="upload-key-accept",
            request_fingerprint="fp-upload-accept",
            created_by="actor-1",
            created_at=fixed_now,
        )
        preview = PreviewResult(
            preview_result_id="pr-accept-1",
            workspace_id=workspace.workspace_id,
            upload_revision_id=upload_revision.upload_revision_id,
            generation=1,
            repository_id=TEST_MAPPING_REPOSITORY_ID,
            business_baseline_node_id=baseline_head.business_baseline_node_id,
            business_baseline_commit_id=baseline_head.business_baseline_commit_id,
            baseline_head_version=baseline_head.baseline_head_version,
            ruleset_version=RULESET_VERSION,
            contract_version="contract-1",
            provider_versions={"comparison": "v1"},
            digests=PreviewResultDigests(
                source_digest="d-source",
                input_digest="d-input",
                snapshot_digest="d-snapshot",
                comparison_digest="d-comparison",
                risk_digest="d-risk",
                surface_digest="d-surface",
                bundle_digest=_PREVIEW_CANONICAL_DIGEST,
            ),
            canonical=make_preview_canonical_bindings(),
            bundle_artifact_id="bundle-1",
            ready_closure_artifact_id="closure-1",
            operation_id="op-preview-accept-1",
            created_at=fixed_now,
        )
        unit_of_work.workspace.save_upload_revision(upload_revision)
        unit_of_work.workspace.save_preview_result(preview)
        updated_workspace = replace(
            workspace,
            repository_id=TEST_MAPPING_REPOSITORY_ID,
            generation=1,
            optimistic_version=workspace.optimistic_version + 1,
            current_upload_revision_id=upload_revision.upload_revision_id,
            current_preview_result_id=preview.preview_result_id,
            updated_at=fixed_now,
        )
        unit_of_work.workspace.save_workspace(
            updated_workspace,
            expected_version=workspace.optimistic_version,
        )
        unit_of_work.set_artifact_protection(
            protected_refs,
            owner_kind="current-preview",
            owner_id=updated_workspace.workspace_id,
            intent="current-preview",
        )
        unit_of_work.set_artifact_protection(
            protected_refs,
            owner_kind="preview-operation",
            owner_id=preview.operation_id,
            intent="preview-operation",
        )
    workspace_http = replace(
        runtime.workspace_http,
        admission_gate=ClosableAdmissionGate(limit=8),
    )
    client = TestClient(create_app(workspace_http=workspace_http))
    response = client.post(
        f"/v1/workspaces/{updated_workspace.workspace_id}/submit-attempts",
        headers={
            "Authorization": f"Bearer {TEST_SESSION_TOKEN}",
            "Idempotency-Key": "submit-accept-202",
            "Content-Type": "application/json",
        },
        json={
            "expected_workspace_version": updated_workspace.optimistic_version,
            "upload_revision_id": upload_revision.upload_revision_id,
            "preview_result_id": preview.preview_result_id,
            "generation": upload_revision.generation,
            "expected_baseline_node_id": baseline_head.business_baseline_node_id,
            "expected_baseline_head_version": baseline_head.baseline_head_version,
            "options": {},
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["state"] == "PREPARED"
    assert body["submit_attempt_id"].startswith("sa-")
    assert body["operation_id"].startswith("op-")
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        attempt = unit_of_work.submission.get_submit_attempt(body["submit_attempt_id"])
        operation = unit_of_work.operations.get_operation(body["operation_id"])
    assert attempt is not None
    assert operation is not None


def test_production_runtime_exposes_archive_routes(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from gateway_backend.app import create_app

    prepare_backend_runtime_paths(tmp_path)
    settings = make_backend_settings(
        tmp_path,
        control_db_path=tmp_path / "control" / "control.sqlite3",
        artifact_root=tmp_path / "artifacts",
        repository_bearer_token_file=tmp_path / "repository-bearer-token",
    )
    runtime = prepare_backend_runtime(settings, skip_repository_ready_probe=True)
    client = TestClient(
        create_app(
            workspace_http=runtime.workspace_http,
            history_http=runtime.history_http,
        )
    )
    schema = client.get("/openapi.json").json()
    assert "/v1/archive-candidates" in schema["paths"]
    assert "/v1/archives" in schema["paths"]
    assert "/v1/archives/{archive_result_id}" in schema["paths"]


def test_production_runtime_exposes_review_routes(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from gateway_backend.app import create_app

    prepare_backend_runtime_paths(tmp_path)
    settings = make_backend_settings(
        tmp_path,
        control_db_path=tmp_path / "control" / "control.sqlite3",
        artifact_root=tmp_path / "artifacts",
        repository_bearer_token_file=tmp_path / "repository-bearer-token",
    )
    runtime = prepare_backend_runtime(settings, skip_repository_ready_probe=True)
    client = TestClient(
        create_app(
            workspace_http=runtime.workspace_http,
            history_http=runtime.history_http,
        )
    )
    schema = client.get("/openapi.json").json()
    assert "/v1/submissions/{submission_id}/review-events" in schema["paths"]
    assert "/v1/submissions/{submission_id}/review" in schema["paths"]


def test_production_runtime_exposes_history_route(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from gateway_backend.app import create_app

    prepare_backend_runtime_paths(tmp_path)
    settings = make_backend_settings(
        tmp_path,
        control_db_path=tmp_path / "control" / "control.sqlite3",
        artifact_root=tmp_path / "artifacts",
        repository_bearer_token_file=tmp_path / "repository-bearer-token",
    )
    runtime = prepare_backend_runtime(settings, skip_repository_ready_probe=True)
    client = TestClient(
        create_app(
            workspace_http=runtime.workspace_http,
            history_http=runtime.history_http,
        )
    )
    schema = client.get("/openapi.json").json()
    assert "/v1/history" in schema["paths"]
