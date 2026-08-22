"""ChangeSet closure artifact publication."""

from __future__ import annotations

from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import ArtifactStorePort, build_artifact_id, put_with_built_ref
from gateway_backend.capabilities.mutation_planning.contracts import (
    CHANGE_SET_CLOSURE_MEDIA_TYPE,
    MAX_CHANGE_SET_JSON_BYTES,
    ChangeSetArtifact,
    ChangeSetClosure,
    PublishedChangeSetClosure,
    change_set_closure_document,
    compute_change_set_closure_digest,
)


class MutationArtifactError(ValueError):
    """ChangeSet artifact bytes or digest failed validation."""


def publish_change_set_closure(
    store: ArtifactStorePort,
    closure: ChangeSetClosure,
) -> PublishedChangeSetClosure:
    artifact = ChangeSetArtifact(manifest=closure.manifest, mutations=closure.mutations)
    closure_bytes = canonicalize_json_value(change_set_closure_document(artifact))
    if len(closure_bytes) > MAX_CHANGE_SET_JSON_BYTES:
        raise MutationArtifactError("change-set closure exceeds max json bytes")
    expected_digest = compute_change_set_closure_digest(artifact)
    if closure.closure_digest != expected_digest:
        raise MutationArtifactError("closure digest mismatch before publication")
    closure_ref = put_with_built_ref(
        store,
        closure_bytes,
        artifact_id=build_artifact_id("change-set-closure", _digest_suffix(expected_digest)),
        media_type=CHANGE_SET_CLOSURE_MEDIA_TYPE,
    )
    if closure_ref.raw_sha256 != expected_digest:
        raise MutationArtifactError("published closure digest mismatch")
    published = PublishedChangeSetClosure(
        closure_ref=closure_ref,
        closure_digest=expected_digest,
    )
    validate_published_change_set_closure(store, published, expected_closure=closure)
    return published


def validate_published_change_set_closure(
    store: ArtifactStorePort,
    published: PublishedChangeSetClosure,
    *,
    expected_closure: ChangeSetClosure,
) -> None:
    payload = store.locate(published.closure_ref)
    if raw_blob_digest(payload) != published.closure_digest:
        raise MutationArtifactError("stored closure digest mismatch")
    artifact = ChangeSetArtifact(
        manifest=expected_closure.manifest,
        mutations=expected_closure.mutations,
    )
    if compute_change_set_closure_digest(artifact) != published.closure_digest:
        raise MutationArtifactError("published closure does not match expected artifact")


def _digest_suffix(digest: DigestRef) -> str:
    return digest.value.removeprefix("sha256:")[:16]
