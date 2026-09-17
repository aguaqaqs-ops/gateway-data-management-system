"""Preview job payload decoder contract tests."""

from __future__ import annotations

import pytest

from gateway_backend.application.payloads import PayloadDecodeError
from gateway_backend.application.preview_jobs import decode_preview_payload
from gateway_backend.domain.workspace.models import InputCompleteness, SourceArtifactRole
from tests.support.preview_job_harness import (
    IDEMPOTENCY_KEY,
    WORKSPACE_ID,
    build_upload_revision,
    store_source_package,
)
from gateway_backend.artifacts import InMemoryArtifactStore

pytestmark = pytest.mark.unit

_BINDING = {
    "artifact_id": "artifact-1",
    "media_type": "application/gzip",
    "size_bytes": 10,
    "raw_sha256": "sha256:" + "ab" * 32,
}


def _base_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "workspace_id": WORKSPACE_ID,
        "upload_revision_id": "ur-1",
        "generation": 1,
        "repository_id": "repo-1",
        "business_baseline_node_id": "node-1",
        "business_baseline_commit_id": "commit-base",
        "baseline_head_version": 3,
        "input_completeness": InputCompleteness.FULL.value,
        "source_artifacts": {
            SourceArtifactRole.INITIAL.value: _BINDING,
            SourceArtifactRole.MODIFIED.value: _BINDING,
        },
        "source_digests": {
            SourceArtifactRole.INITIAL.value: _BINDING["raw_sha256"],
            SourceArtifactRole.MODIFIED.value: _BINDING["raw_sha256"],
        },
        "input_digest": "fp-preview",
        "ruleset_version": "v2",
        "capability_contract_versions": {},
        "provider_versions": {},
        "ready_closure_contract_version": "v1",
        "idempotency_identity": {
            "workspace_id": WORKSPACE_ID,
            "idempotency_key": IDEMPOTENCY_KEY,
        },
        "options": {},
    }
    payload.update(overrides)
    return payload


def test_decode_preview_payload_accepts_full_closure() -> None:
    decoded = decode_preview_payload(_base_payload())
    assert decoded.input_completeness is InputCompleteness.FULL
    assert decoded.idempotency_identity.idempotency_key == IDEMPOTENCY_KEY
    assert SourceArtifactRole.INITIAL in decoded.source_artifacts


def test_decode_preview_payload_accepts_modified_only_closure() -> None:
    payload = _base_payload(
        input_completeness=InputCompleteness.MODIFIED_ONLY.value,
        source_artifacts={SourceArtifactRole.MODIFIED.value: _BINDING},
        source_digests={SourceArtifactRole.MODIFIED.value: _BINDING["raw_sha256"]},
    )
    decoded = decode_preview_payload(payload)
    assert decoded.input_completeness is InputCompleteness.MODIFIED_ONLY
    assert SourceArtifactRole.INITIAL not in decoded.source_artifacts


PAYLOAD_SHAPE_FAULTS = (
    ("unknown_field", {"unexpected": True}, "unknown preview payload keys"),
    ("missing_idempotency", {"idempotency_identity": {"workspace_id": WORKSPACE_ID}}, "idempotency_key"),
    (
        "full_missing_initial",
        {
            "source_artifacts": {SourceArtifactRole.MODIFIED.value: _BINDING},
            "source_digests": {SourceArtifactRole.MODIFIED.value: _BINDING["raw_sha256"]},
        },
        "FULL preview requires INITIAL",
    ),
    (
        "modified_only_with_initial",
        {
            "input_completeness": InputCompleteness.MODIFIED_ONLY.value,
            "source_artifacts": {
                SourceArtifactRole.INITIAL.value: _BINDING,
                SourceArtifactRole.MODIFIED.value: _BINDING,
            },
            "source_digests": {
                SourceArtifactRole.INITIAL.value: _BINDING["raw_sha256"],
                SourceArtifactRole.MODIFIED.value: _BINDING["raw_sha256"],
            },
        },
        "MODIFIED_ONLY preview forbids INITIAL",
    ),
)


@pytest.mark.parametrize(("label", "overrides", "message"), PAYLOAD_SHAPE_FAULTS)
def test_decode_preview_payload_rejects_invalid_shapes(
    label: str,
    overrides: dict[str, object],
    message: str,
) -> None:
    del label
    with pytest.raises(PayloadDecodeError, match=message):
        decode_preview_payload(_base_payload(**overrides))


def test_build_preview_job_payload_round_trips_through_decoder() -> None:
    store = InMemoryArtifactStore()
    modified = store_source_package(store, b"CREATE TABLE t (id INT NOT NULL PRIMARY KEY);", artifact_id="m")
    initial = store_source_package(store, b"CREATE TABLE t (id INT NOT NULL PRIMARY KEY);", artifact_id="i")
    revision = build_upload_revision(
        input_completeness=InputCompleteness.FULL,
        initial_binding=initial,
        modified_binding=modified,
    )
    from gateway_backend.http.orchestration.preview_acceptance import build_preview_job_payload

    payload_bytes = build_preview_job_payload(
        workspace_id=WORKSPACE_ID,
        upload_revision=revision,
        repository_id="repo-1",
        business_baseline_node_id="node-1",
        business_baseline_commit_id="commit-base",
        baseline_head_version=3,
        idempotency_key=IDEMPOTENCY_KEY,
    )
    import json

    decoded = decode_preview_payload(json.loads(payload_bytes))
    assert decoded.upload_revision_id == revision.upload_revision_id
