"""HTTP contract tests for preview result reads and bundle streaming."""

from __future__ import annotations

from tests.support.configuration_fact_faults import (
    CONFIGURATION_BODY_FAULTS, corrupt_configuration_body, forbid_configuration_object_reads,
)

from tests.support.configuration_facts import preview_result_with_facts

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from gateway_backend.domain.workspace.models import PreviewResult, PreviewResultDigests
from tests.support.preview_fixtures import make_preview_canonical_bindings
from tests.support.http_workspace_harness import (
    BASELINE_HEAD,
    InMemoryBundleReader,
    WorkspaceHttpTestEnvironment,
    create_workspace_http_environment,
)
from tests.support.upload_http_packages import upload_files
from tests.support.workspace_fixtures import (
    make_baseline_head,
    make_identity,
    make_not_applicable_preview_identity,
)

pytestmark = pytest.mark.unit

BUNDLE_BYTES = b"bundle-bytes"


def _seed_workspace(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    return cast(dict[str, Any], client.post(
        "/v1/workspaces",
        headers=headers,
        json={
            "gateway_device_external_key": "device-1",
            "business_project_id": "project-1",
        },
    ).json())


def _seed_upload(
    client: TestClient,
    headers: dict[str, str],
    workspace: dict[str, Any],
) -> dict[str, Any]:
    return cast(dict[str, Any], client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions",
        headers={**headers, "Idempotency-Key": "upload-read"},
        files=upload_files(expected_version=workspace["optimistic_version"]),
    ).json())


def _preview_result(workspace: dict[str, Any], upload: dict[str, Any], operation_id: str = "op-read") -> PreviewResult:
    identity_digest, identity_pairs = make_not_applicable_preview_identity()
    return preview_result_with_facts(
        preview_result_id="pr-read-1",
        workspace_id=workspace["workspace_id"],
        upload_revision_id=upload["upload_revision_id"],
        generation=upload["generation"],
        repository_id="repo-1",
        business_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        business_baseline_commit_id=BASELINE_HEAD.business_baseline_commit_id,
        baseline_head_version=BASELINE_HEAD.baseline_head_version,
        ruleset_version="v1",
        contract_version="v1",
        provider_versions={},
        digests=PreviewResultDigests(
            source_digest="d1",
            input_digest="d2",
            snapshot_digest="d3",
            comparison_digest="d4",
            risk_digest="d5",
            surface_digest="d6",
            bundle_digest="bundle-digest",
        ),
        canonical=make_preview_canonical_bindings(),
        identity_assessment_set_digest=identity_digest,
        identity_pairs=identity_pairs,
        bundle_artifact_id="bundle-artifact-1",
        ready_closure_artifact_id="closure-1",
        operation_id=operation_id,
        created_at=datetime(2024, 6, 1, 12, 0, tzinfo=UTC),
    )


@pytest.fixture
def env(tmp_path: Path) -> WorkspaceHttpTestEnvironment:
    return create_workspace_http_environment(tmp_path)


def test_get_preview_result_returns_derived_stale(env: WorkspaceHttpTestEnvironment) -> None:
    workspace = _seed_workspace(env.client, env.auth_headers())
    upload = _seed_upload(env.client, env.auth_headers(), workspace)
    result = _preview_result(workspace, upload)
    env.repository.save_preview_result(result)
    env.baseline_head_read.heads["repo-1"] = make_baseline_head(version=99, commit_id="commit-new")
    response = env.client.get(
        f"/v1/workspaces/{workspace['workspace_id']}/preview-results/{result.preview_result_id}",
        headers=env.auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["derived_stale"] is True
    assert body["bundle_digest"] == "bundle-digest"
    assert body["identity_assessment_set_digest"] == result.identity_assessment_set_digest.value
    assert body["identity_pairs"][0]["status"] == "NOT_APPLICABLE"


def test_get_preview_result_hides_cross_scope(tmp_path: Path) -> None:
    owner_env = create_workspace_http_environment(tmp_path)
    workspace = _seed_workspace(owner_env.client, owner_env.auth_headers())
    upload = _seed_upload(owner_env.client, owner_env.auth_headers(), workspace)
    result = _preview_result(workspace, upload)
    owner_env.repository.save_preview_result(result)
    other_root = tmp_path / "other"
    other_root.mkdir()
    other_env = create_workspace_http_environment(
        other_root,
        identity=make_identity(actor_id="actor-2", device_key="device-2", project_id="project-2"),
    )
    response = other_env.client.get(
        f"/v1/workspaces/{workspace['workspace_id']}/preview-results/{result.preview_result_id}",
        headers=other_env.auth_headers(),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_read_preview_bundle_streams_logical_bytes(env: WorkspaceHttpTestEnvironment) -> None:
    workspace = _seed_workspace(env.client, env.auth_headers())
    upload = _seed_upload(env.client, env.auth_headers(), workspace)
    result = _preview_result(workspace, upload)
    env.repository.save_preview_result(result)
    bundle_reader = env.bundle_reader
    assert isinstance(bundle_reader, InMemoryBundleReader)
    bundle_reader.register(result.bundle_artifact_id, "preview.tar", BUNDLE_BYTES, bundle_digest=result.digests.bundle_digest)
    response = env.client.get(
        f"/v1/workspaces/{workspace['workspace_id']}/preview-results/{result.preview_result_id}/bundle",
        headers=env.auth_headers(),
    )
    assert response.status_code == 200
    assert response.content == BUNDLE_BYTES
    assert "preview.tar" in response.headers["content-disposition"]
    assert "bundle-artifact-1" not in response.text
    assert str(env.db_path) not in response.text


@pytest.mark.parametrize("fault", CONFIGURATION_BODY_FAULTS)
def test_preview_point_read_filters_workspace_before_configuration_decode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str,
) -> None:
    env = create_workspace_http_environment(tmp_path, extra_sessions={
        "other-reader": make_identity(actor_id="other-actor"),
        "denied": make_identity(permissions=frozenset({"preview_workspace"})),
    })
    workspace = _seed_workspace(env.client, env.auth_headers())
    upload = _seed_upload(env.client, env.auth_headers(), workspace)
    result = _preview_result(workspace, upload)
    env.repository.save_preview_result(result)
    message = corrupt_configuration_body(env.db_path, kind="preview", target_id=result.preview_result_id, fault=fault)
    other_headers = {"Authorization": "Bearer other-reader"}
    other = _seed_workspace(env.client, other_headers)
    own_url = f"/v1/workspaces/{other['workspace_id']}/preview-results/{result.preview_result_id}"
    target_url = f"/v1/workspaces/{workspace['workspace_id']}/preview-results/{result.preview_result_id}"
    assert env.client.get(own_url, headers=other_headers).status_code == 404
    assert env.client.get(target_url, headers=other_headers).status_code == 404
    with forbid_configuration_object_reads(monkeypatch):
        assert env.client.get(target_url, headers={"Authorization": "Bearer denied"}).status_code == 403
    with TestClient(env.client.app, raise_server_exceptions=True) as strict_client:
        with pytest.raises(ValueError, match=message):
            strict_client.get(target_url, headers=env.auth_headers())
