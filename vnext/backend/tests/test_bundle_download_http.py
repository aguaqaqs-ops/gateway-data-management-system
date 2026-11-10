"""Public route and real job wiring owner for complete Preview/History tar downloads."""

from __future__ import annotations

from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from gateway_backend.application.preview_jobs import (
    PREVIEW_ASSEMBLE_HANDLER, PREVIEW_MATERIALIZE_HANDLER, PREVIEW_PUBLISH_HANDLER,
)
from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.bootstrap.composition import LocalArtifactBundleReader
from gateway_backend.domain.workspace.models import InputCompleteness
from gateway_backend.infrastructure.artifact_store import BoundedArtifactStore, LocalArtifactStore
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from tests.support.history_compare_job_harness import build_history_compare_harness, run_through_step, HistoryCompareJobHarness
from tests.support.http_workspace_harness import WorkspaceHttpTestEnvironment, create_workspace_http_environment
from tests.support.preview_job_harness import (
    build_preview_harness, claim_next_step, insert_preview_operation, run_claimed_handler,
)
from tests.support.workspace_fixtures import make_identity
from tests.test_bundle_download import assert_complete_tar
from tests.test_preview_read_http import _preview_result, _seed_upload, _seed_workspace

pytestmark = pytest.mark.unit


def _copy_artifacts(source: InMemoryArtifactStore, target: LocalArtifactStore) -> None:
    for ref, raw in source._artifacts.values():
        target.put(raw, ref)


def _history_http_job(
    root: Path, store: LocalArtifactStore, node_count: int = 2,
) -> tuple[WorkspaceHttpTestEnvironment, HistoryCompareJobHarness]:
    from gateway_backend.application.history.compare_jobs import (
        HISTORY_COMPARE_ASSEMBLE_HANDLER, HISTORY_COMPARE_MATERIALIZE_HANDLER, HISTORY_COMPARE_PUBLISH_HANDLER,
    )
    from tests.support.http_workspace_harness import BASELINE_HEAD
    nodes = (
        (BASELINE_HEAD.business_baseline_node_id, BASELINE_HEAD.business_baseline_commit_id),
        ("bn-b", "commit-b"), ("bn-c", "commit-c"),
    )[:node_count]
    harness = build_history_compare_harness(root / "job", artifact_store=BoundedArtifactStore(store), node_specs=nodes)
    env = create_workspace_http_environment(
        root / "http", db_path=harness.db_path,
        identity=make_identity(permissions=frozenset({"read_project_history"})),
        extra_sessions={"denied": make_identity(permissions=frozenset({"workspace_read"})),
                        "foreign": make_identity(device_key="other", permissions=frozenset({"read_project_history"}))},
        artifact_store=BoundedArtifactStore(store), bundle_reader=LocalArtifactBundleReader(store),
    )
    # Use the real HTTP acceptance rather than the job-only harness's unbound
    # operation fixture: public reads require its exact acceptance business_ref.
    accepted = env.client.post("/v1/history-compares", headers=env.auth_headers(idempotency_key="tar-http"),
        json={"nodes": [{"ref_kind": "baseline_node", "ref_id": node} for node, _commit in nodes]})
    assert accepted.status_code == 202, accepted.text
    harness.operation_id = accepted.json()["operation_id"]
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as uow:
        operation = uow.operations.get_operation(harness.operation_id)
    assert operation.job_payload is not None
    harness.job_payload = operation.job_payload
    for handler in (HISTORY_COMPARE_MATERIALIZE_HANDLER, HISTORY_COMPARE_ASSEMBLE_HANDLER, HISTORY_COMPARE_PUBLISH_HANDLER):
        run_through_step(harness, handler)
    from gateway_backend.application.checkpoints import load_checkpoint_envelope
    from gateway_backend.application.history.compare_jobs import HISTORY_COMPARE_STEP_ASSEMBLE, history_compare_step_id
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as uow:
        step = uow.operations.get_step(history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE))
    assert step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, step.checkpoint_ref)
    _assert_published_download_is_protected(harness.db_path, store, store.get_ref(str(envelope.job_state["bundle_artifact_id"])))
    return env, harness


@pytest.mark.parametrize(("mode", "project_id", "pair_count"), (
    (InputCompleteness.MODIFIED_ONLY, "project-a", 1),
    (InputCompleteness.FULL, "project-a", 2),
    (InputCompleteness.MODIFIED_ONLY, "project-b", 1),
))
def test_preview_job_outputs_download_as_complete_tar(
    tmp_path: Path, mode: InputCompleteness, project_id: str, pair_count: int,
) -> None:
    harness = build_preview_harness(
        tmp_path / "job", input_completeness=mode,
        include_identity_table=True, identity_project_id=project_id,
    )
    harness.seed_workspace()
    operation_id = "op-tar-preview"
    insert_preview_operation(harness, operation_id)
    for handler in (PREVIEW_MATERIALIZE_HANDLER, PREVIEW_ASSEMBLE_HANDLER, PREVIEW_PUBLISH_HANDLER):
        session, control, operation, step = claim_next_step(harness)
        run_claimed_handler(harness, handler, session, control, operation, step)
    store = LocalArtifactStore(tmp_path / "download")
    _copy_artifacts(harness.artifact_store, store)
    env = create_workspace_http_environment(
        tmp_path / "http", db_path=harness.db_path,
        artifact_store=BoundedArtifactStore(store), bundle_reader=LocalArtifactBundleReader(store),
    )
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as uow:
        workspace = uow.workspace.get_workspace(harness.upload_revision.workspace_id)
    assert workspace is not None and workspace.current_preview_result_id is not None
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as uow:
        published = uow.workspace.get_preview_result(workspace.current_preview_result_id)
    assert published is not None
    _assert_published_download_is_protected(harness.db_path, store, store.get_ref(published.bundle_artifact_id))
    url = f"/v1/workspaces/{workspace.workspace_id}/preview-results/{workspace.current_preview_result_id}/bundle"
    response = env.client.get(url, headers=env.auth_headers())
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/x-tar"
    assert len(response.content) == int(response.headers["content-length"])
    manifest = assert_complete_tar(response.content)
    assert len(cast(list[object], manifest["pairs"])) == pair_count
    assert response.headers["etag"] == f'"{manifest["bundle_digest"]}"'
    if project_id == "project-b":
        assert b"DATASET_REPLACEMENT" in response.content


@pytest.mark.parametrize("node_count", (2, 3))
def test_history_job_outputs_download_as_complete_tar(tmp_path: Path, node_count: int) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    env, harness = _history_http_job(tmp_path, store, node_count)
    response = env.client.get(f"/v1/history-compares/{harness.operation_id}/bundle", headers=env.auth_headers())
    assert response.status_code == 200, response.text
    assert len(response.content) == int(response.headers["content-length"])
    manifest = assert_complete_tar(response.content)
    assert len(cast(list[object], manifest["pairs"])) == node_count - 1


def _assert_published_download_is_protected(db_path: Path, store: LocalArtifactStore, manifest_ref: ArtifactRef) -> None:
    from gateway_backend.capabilities.bundle_assembly.transport import read_bundle_transport_metadata
    metadata = read_bundle_transport_metadata(store.locate(manifest_ref))
    with ControlDbUnitOfWork(db_path, read_only=True) as uow:
        assert uow.protection.is_protected(manifest_ref.artifact_id)
        assert uow.protection.is_protected(metadata.closure_ref.artifact_id)
        for entry in metadata.entries:
            assert uow.protection.is_protected(entry.artifact_ref.artifact_id)


def test_production_assembler_and_http_preserve_shared_empty_tables_schemas_and_long_paths(tmp_path: Path) -> None:
    import io
    import tarfile
    from dataclasses import replace
    import pyarrow as pa
    import pyarrow.parquet as pq  # type: ignore[import-untyped]
    from gateway_backend.artifacts import put_with_built_ref
    from gateway_backend.capabilities.bundle_assembly import (
        BundleArtifactBinding, BundleArtifactClosure, BundleArtifactKind, BundleInput,
        BundlePairInput, BundleProfile, assemble_bundle,
    )
    from gateway_backend.capabilities.surface_assembly import compute_surface_digest
    from tests.test_bundle_assembly import _request, _surface_result
    from tests.test_bundle_download import PAX_PATHS

    store = LocalArtifactStore(tmp_path / "artifacts")
    refs = []
    for name, scalar_type in (("int", pa.int64()), ("text", pa.string())):
        sink = pa.BufferOutputStream()
        pq.write_table(pa.table({"id": pa.array([], type=scalar_type)}), sink)
        refs.append(put_with_built_ref(store, sink.getvalue().to_pybytes(), artifact_id=build_artifact_id(ArtifactLocation.DURABLE, "test-fixture", f"empty-{name}"), media_type="application/vnd.apache.parquet"))
    shared = []
    for index, path in enumerate(PAX_PATHS):
        ref = put_with_built_ref(store, bytes([index]), artifact_id=build_artifact_id(ArtifactLocation.DURABLE, "test-fixture", f"long-path-{index}"), media_type="application/octet-stream")
        shared.append(BundleArtifactBinding(ref, "shared/" + path, BundleArtifactKind.OTHER, shared=True))
    pairs = []
    for index, ref in enumerate(refs):
        pair_id = f"pair-{index}"
        surface_result = _surface_result(table_name="empty")
        assert surface_result.surface is not None
        surface = surface_result.surface
        table = replace(surface.tables[0], table_refs=replace(surface.tables[0].table_refs,
            current_table_ref=ref, before_table_ref=refs[0] if index == 1 else None))
        surface = replace(surface, tables=(table,))
        surface = replace(surface, surface_digest=compute_surface_digest(surface))
        surface_result = replace(surface_result, surface=surface)
        bindings = [BundleArtifactBinding(ref, f"pairs/{pair_id}/tables/current/empty/rows.parquet", BundleArtifactKind.SNAPSHOT_TABLE,
                                         pair_id=pair_id, table_name="empty")]
        if index == 1:
            # A second pair/side shares the first schema's same actual rows file.
            bindings.append(BundleArtifactBinding(refs[0], f"pairs/{pair_id}/tables/before/empty/rows.parquet", BundleArtifactKind.SNAPSHOT_TABLE,
                                                  pair_id=pair_id, table_name="empty"))
        pairs.append(BundlePairInput(pair_id, index, index + 1, surface_result, BundleArtifactClosure(tuple(bindings))))
    result = assemble_bundle(_request(tuple(pairs), profile=BundleProfile.MULTI_PAIR,
        inputs=(BundleInput(0, "a", "A"), BundleInput(1, "b", "B"), BundleInput(2, "c", "C")),
        shared=BundleArtifactClosure(tuple(shared))), source_store=store)
    assert result.bundle is not None, result.diagnostics
    (tmp_path / "http").mkdir()
    env = create_workspace_http_environment(tmp_path / "http", bundle_reader=LocalArtifactBundleReader(store))
    workspace = _seed_workspace(env.client, env.auth_headers())
    upload = _seed_upload(env.client, env.auth_headers(), workspace)
    preview = _preview_result(workspace, upload)
    preview = replace(preview, bundle_artifact_id=result.bundle.manifest_ref.artifact_id,
                      digests=replace(preview.digests, bundle_digest=result.bundle.bundle_digest.value))
    env.repository.save_preview_result(preview)
    response = env.client.get(f"/v1/workspaces/{workspace['workspace_id']}/preview-results/{preview.preview_result_id}/bundle", headers=env.auth_headers())
    assert response.status_code == 200, response.text
    manifest = assert_complete_tar(response.content)
    entries = cast(list[dict[str, object]], manifest["closure_entries"])
    snapshots = [entry for entry in entries if entry["kind"] == "SNAPSHOT_TABLE"]
    assert len(snapshots) == 2
    assert sorted(len(cast(list[object], entry["table_bindings"])) for entry in snapshots) == [1, 2]
    with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:") as archive:
        assert all("shared/" + path in archive.getnames() for path in PAX_PATHS)
        schemas = []
        for entry in snapshots:
            source = archive.extractfile(str(entry["logical_path"]))
            assert source is not None
            table = pq.read_table(pa.BufferReader(source.read()))
            assert table.num_rows == 0
            schemas.append(table.schema)
        assert schemas[0] != schemas[1]


@pytest.fixture(params=("preview", "history"))
def bundle_route(request: pytest.FixtureRequest, tmp_path: Path) -> tuple[WorkspaceHttpTestEnvironment, str, LocalArtifactStore, str]:
    store = LocalArtifactStore(tmp_path / "artifacts")
    if request.param == "history":
        env, harness = _history_http_job(tmp_path, store)
        from gateway_backend.application.checkpoints import load_checkpoint_envelope
        from gateway_backend.application.history.compare_jobs import HISTORY_COMPARE_STEP_ASSEMBLE, history_compare_step_id
        with ControlDbUnitOfWork(harness.db_path, read_only=True) as uow:
            step = uow.operations.get_step(history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE))
        assert step.checkpoint_ref is not None
        envelope = load_checkpoint_envelope(harness.artifact_store, step.checkpoint_ref)
        artifact_id = str(envelope.job_state["bundle_artifact_id"])
        return env, f"/v1/history-compares/{harness.operation_id}/bundle", store, artifact_id
    from tests.test_bundle_download import published_bundle
    published, ref = published_bundle(tmp_path / "published")
    (tmp_path / "http").mkdir()
    env = create_workspace_http_environment(
        tmp_path / "http",
        extra_sessions={"denied": make_identity(permissions=frozenset({"preview_workspace"})),
                        "foreign": make_identity(device_key="other")},
        bundle_reader=LocalArtifactBundleReader(published),
    )
    workspace = _seed_workspace(env.client, env.auth_headers())
    upload = _seed_upload(env.client, env.auth_headers(), workspace)
    from gateway_backend.capabilities.bundle_assembly import read_bundle_transport_metadata
    result = _preview_result(workspace, upload)
    result = replace(result, bundle_artifact_id=ref.artifact_id,
        digests=replace(result.digests, bundle_digest=read_bundle_transport_metadata(published.locate(ref)).bundle_digest))
    env.repository.save_preview_result(result)
    return env, f"/v1/workspaces/{workspace['workspace_id']}/preview-results/{result.preview_result_id}/bundle", published, ref.artifact_id


@pytest.mark.parametrize(("headers", "expected"), (
    ({}, 401), ({"Authorization": "Bearer denied"}, 403), ({"Authorization": "Bearer foreign"}, 404),
))
def test_bundle_authorizes_before_any_artifact_read(
    bundle_route: tuple[WorkspaceHttpTestEnvironment, str, LocalArtifactStore, str],
    monkeypatch: pytest.MonkeyPatch, headers: dict[str, str], expected: int,
) -> None:
    env, url, store, _artifact_id = bundle_route
    def forbidden() -> None:
        raise AssertionError("artifact read session entered before authorization")
    monkeypatch.setattr(store, "read_session", forbidden)
    response = env.client.get(url, headers=headers)
    assert response.status_code == expected


@pytest.mark.parametrize("fault", ("manifest-missing", "closure-missing", "member-missing", "member-size", "member-digest"))
def test_bundle_preflight_failure_is_a_typed_response_before_success_headers(
    bundle_route: tuple[WorkspaceHttpTestEnvironment, str, LocalArtifactStore, str], fault: str,
) -> None:
    from gateway_backend.capabilities.bundle_assembly.transport import read_bundle_transport_metadata
    env, url, store, artifact_id = bundle_route
    ref = store.get_ref(artifact_id)
    metadata = read_bundle_transport_metadata(store.locate(ref))
    target_ref = (ref if fault == "manifest-missing" else metadata.closure_ref if fault == "closure-missing"
                  else metadata.entries[-1].artifact_ref)
    path = store._object_path(target_ref.artifact_id)
    raw = path.read_bytes()
    path.unlink()
    missing = fault.endswith("missing")
    if not missing:
        path.write_bytes(raw + b"x" if fault == "member-size" else bytes([raw[0] ^ 1]) + raw[1:])
    response = env.client.get(url, headers=env.auth_headers())
    assert response.status_code == (404 if missing else 503)
    expected_code = ("ARTIFACT_UNAVAILABLE" if "/history-compares/" in url else "RESOURCE_NOT_FOUND") if missing else "BUNDLE_INTEGRITY_FAILURE"
    assert response.json()["code"] == expected_code
    assert response.headers["content-type"] == "application/json"
    assert "etag" not in response.headers
    assert str(store.artifact_root) not in json.dumps(response.json())


def test_bundle_rejects_a_complete_valid_artifact_from_a_different_result(
    bundle_route: tuple[WorkspaceHttpTestEnvironment, str, LocalArtifactStore, str],
) -> None:
    from gateway_shared_kernel.jcs import canonicalize_json_value
    from gateway_backend.application.checkpoints import load_checkpoint_envelope, put_checkpoint_envelope
    from gateway_backend.application.history.compare_jobs import HISTORY_COMPARE_STEP_ASSEMBLE, history_compare_step_id
    from gateway_backend.artifacts import artifact_ref_to_dict
    from gateway_backend.application.bundle_download import prepare_bundle_download
    from gateway_backend.capabilities.bundle_assembly import BundlePairInput, assemble_bundle
    from tests.test_bundle_assembly import _request, _surface_result

    env, url, store, artifact_id = bundle_route
    other = assemble_bundle(_request((BundlePairInput("other-pair", 0, 1, _surface_result(table_name="other-table")),)), source_store=store)
    assert other.bundle is not None
    # The pointed-to artifact is complete and independently valid; the owning
    # result/checkpoint still advertises the original result's digest.
    valid = prepare_bundle_download(store, other.bundle.manifest_ref.artifact_id)
    assert_complete_tar(b"".join(valid.stream), expected_digest=other.bundle.bundle_digest.value)
    valid.close()
    with ControlDbUnitOfWork(env.db_path) as uow:
        if "/history-compares/" in url:
            operation_id = url.split("/")[-2]
            step_id = history_compare_step_id(operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
            step = uow.operations.get_step(step_id)
            assert step.checkpoint_ref is not None
            envelope = load_checkpoint_envelope(store, step.checkpoint_ref)
            assert envelope.job_state["bundle_artifact_id"] == artifact_id
            changed = replace(envelope, job_state={**envelope.job_state, "bundle_artifact_id": other.bundle.manifest_ref.artifact_id})
            ref = put_checkpoint_envelope(store, changed)
            uow.connection.execute("UPDATE step_records SET checkpoint_ref=? WHERE step_id=?",
                (canonicalize_json_value(artifact_ref_to_dict(ref)), step_id))
        else:
            preview_id = url.split("/")[-2]
            row = uow.connection.execute("SELECT binding FROM preview_result_records WHERE preview_result_id=?", (preview_id,)).fetchone()
            assert row is not None
            binding = json.loads(row[0])
            assert binding["bundle_artifact_id"] == artifact_id
            binding["bundle_artifact_id"] = other.bundle.manifest_ref.artifact_id
            uow.connection.execute("UPDATE preview_result_records SET binding=? WHERE preview_result_id=?",
                (canonicalize_json_value(binding), preview_id))
    response = env.client.get(url, headers=env.auth_headers())
    assert response.status_code == 503
    assert response.json()["code"] == "BUNDLE_INTEGRITY_FAILURE"
    assert "etag" not in response.headers
    with store.cleanup_session() as acquired:
        assert acquired
