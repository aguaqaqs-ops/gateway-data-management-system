"""Preview canonical binding fixtures shared across backend tests."""

from gateway_shared_kernel import DigestRef

from gateway_backend.domain.workspace.models import (
    PreviewArtifactRef,
    PreviewCanonicalBindings,
)


def make_preview_canonical_bindings() -> PreviewCanonicalBindings:
    closure_ref = PreviewArtifactRef(
        artifact_id="preview-canonical-closure-fixture",
        media_type="application/jcs",
        size_bytes=1,
        raw_sha256=DigestRef("sha256:" + "1" * 64),
    )
    manifest_ref = PreviewArtifactRef(
        artifact_id="preview-canonical-manifest-fixture",
        media_type="application/jcs",
        size_bytes=1,
        raw_sha256=DigestRef("sha256:" + "2" * 64),
    )
    return PreviewCanonicalBindings(
        canonical_table_set_closure_ref=closure_ref,
        canonical_table_set_closure_digest=closure_ref.raw_sha256,
        canonicalization_manifest_ref=manifest_ref,
        canonicalization_manifest_digest=DigestRef("sha256:" + "3" * 64),
        baseline_canonical_state_digest=DigestRef("sha256:" + "4" * 64),
        modified_canonical_state_digest=DigestRef("sha256:" + "5" * 64),
        storage_projection_ruleset_digest=DigestRef("sha256:" + "6" * 64),
    )
