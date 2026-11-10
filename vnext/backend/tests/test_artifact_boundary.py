"""Artifact references and nominal type boundary tests."""

from __future__ import annotations

import pytest

from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts import (
    ArtifactRef,
)
from gateway_backend.application.submission.artifact_refs import (
    NominalArtifactRefError,
    assert_backend_ref_not_repository_ref,
    assert_repository_ref_not_backend_ref,
    backend_artifact_ref_from_store_ref,
    repository_artifact_ref_from_upload_response,
    store_ref_from_backend_artifact_ref,
)
from gateway_backend.domain.submission.models import BackendArtifactRef, RepositoryArtifactRef
_STORE_REF = ArtifactRef(
    artifact_id="a1:durable:52e6ceb803ffbf0d00f02752bb8a4746ef5014fb2a6f435936d26e04ab55476e",
    media_type="application/vnd.gateway.repository-import.v1+tar+zstd",
    size_bytes=12,
    raw_sha256=DigestRef("sha256:" + "aa" * 32),
)


def test_backend_and_repository_refs_are_distinct_nominal_types() -> None:
    backend = backend_artifact_ref_from_store_ref(_STORE_REF)
    repository = repository_artifact_ref_from_upload_response(
        artifact_id="00000000-0000-4000-8000-000000000002",
        media_type=_STORE_REF.media_type,
        size_bytes=_STORE_REF.size_bytes,
        raw_sha256=_STORE_REF.raw_sha256.value,
    )
    assert type(backend) is BackendArtifactRef
    assert type(repository) is RepositoryArtifactRef
    assert backend.artifact_id != repository.artifact_id


def test_store_ref_round_trip_preserves_backend_identity() -> None:
    backend = backend_artifact_ref_from_store_ref(_STORE_REF)
    roundtrip = store_ref_from_backend_artifact_ref(backend)
    assert roundtrip == _STORE_REF


NOMINAL_REF_CROSS_TYPE_FAULTS: tuple[tuple[str, object, str], ...] = (
    (
        "repository-ref-used-as-backend",
        RepositoryArtifactRef(
            artifact_id="00000000-0000-4000-8000-000000000001",
            media_type="application/octet-stream",
            size_bytes=1,
            raw_sha256="sha256:" + "cc" * 32,
        ),
        "backend",
    ),
    (
        "backend-ref-used-as-repository",
        BackendArtifactRef(
            artifact_id="a1:durable:435f49de32cd1a29d1267152362b62049d5cdc3bdb1d4c82c752b5bee6072f61",
            media_type="application/octet-stream",
            size_bytes=1,
            raw_sha256="sha256:" + "bb" * 32,
        ),
        "repository",
    ),
)


@pytest.mark.parametrize(("case_id", "ref", "expected_kind"), NOMINAL_REF_CROSS_TYPE_FAULTS)
def test_nominal_ref_cross_type_substitution_is_rejected(
    case_id: str,
    ref: object,
    expected_kind: str,
) -> None:
    if expected_kind == "backend":
        with pytest.raises(NominalArtifactRefError):
            assert_backend_ref_not_repository_ref(ref)
        return
    with pytest.raises(NominalArtifactRefError):
        assert_repository_ref_not_backend_ref(ref)


@pytest.mark.parametrize("artifact_id", ["legacy-ref", "a1:unknown:" + "a" * 64,
    "00000000-0000-4000-8000-000000000001"])
def test_backend_nominal_ref_requires_location_protocol(artifact_id: str) -> None:
    with pytest.raises(ValueError):
        BackendArtifactRef(artifact_id, "application/json", 0, "sha256:" + "0" * 64)


@pytest.mark.parametrize("artifact_id", ["legacy-ref", "a1:durable:" + "a" * 64,
    "00000000000040008000000000000001", "00000000-0000-4000-8000-00000000000A"])
def test_repository_nominal_ref_requires_its_canonical_uuid(artifact_id: str) -> None:
    with pytest.raises(ValueError):
        RepositoryArtifactRef(artifact_id, "application/json", 0, "sha256:" + "0" * 64)


@pytest.mark.parametrize("artifact_id", ["legacy-table", "a1:unknown:" + "a" * 64,
    "00000000-0000-4000-8000-000000000001"])
def test_snapshot_table_binding_requires_backend_location_identity(artifact_id: str) -> None:
    from gateway_backend.application.submission.contracts import SnapshotTableBinding
    with pytest.raises(ValueError, match="a1:"):
        SnapshotTableBinding("orders", artifact_id, "application/octet-stream", 0, "sha256:" + "0" * 64)


@pytest.mark.parametrize("owner", ["preview", "history"])
def test_checkpoint_bundle_binding_must_belong_to_its_ready_closure(owner: str) -> None:
    from gateway_backend.application.history.compare_jobs import _assert_history_bundle_binding
    from gateway_backend.application.preview_jobs import _assert_preview_bundle_binding
    from gateway_backend.application.payloads import CheckpointDecodeError
    validators = {"preview": _assert_preview_bundle_binding, "history": _assert_history_bundle_binding}
    state: dict[str, object] = {"bundle_artifact_id": "a1:export:" + "f" * 64}
    with pytest.raises(CheckpointDecodeError, match="outside its ready closure"):
        validators[owner](state, (_STORE_REF,))
