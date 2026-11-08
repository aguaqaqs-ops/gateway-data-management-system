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
    artifact_id="backend-package-1",
    media_type="application/vnd.gateway.repository-import.v1+tar+zstd",
    size_bytes=12,
    raw_sha256=DigestRef("sha256:" + "aa" * 32),
)


def test_backend_and_repository_refs_are_distinct_nominal_types() -> None:
    backend = backend_artifact_ref_from_store_ref(_STORE_REF)
    repository = repository_artifact_ref_from_upload_response(
        artifact_id="repo-artifact-uuid",
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
            artifact_id="repo-1",
            media_type="application/octet-stream",
            size_bytes=1,
            raw_sha256="sha256:" + "cc" * 32,
        ),
        "backend",
    ),
    (
        "backend-ref-used-as-repository",
        BackendArtifactRef(
            artifact_id="backend-1",
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
