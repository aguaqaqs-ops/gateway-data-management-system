"""Small closed immutable Preview bundle for lifecycle HTTP fixtures; no Dolt."""
from __future__ import annotations

from dataclasses import replace

from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore
from gateway_backend.capabilities.bundle_assembly import (
    BundleInput, BundlePairInput, BundleProfile, assemble_bundle,
)
from gateway_backend.domain.workspace.models import (
    PreviewComparisonPair, PreviewIdentityPair, PreviewResult,
    ProjectIdentityApplicability, ProjectIdentityMode, ProjectIdentityStatus,
)
from tests.support.surface_navigation import seed_navigation
from tests.test_bundle_assembly import _request, _surface_result


def closed_review_preview(
    preview: PreviewResult, refs: tuple[ArtifactRef, ...],
) -> tuple[PreviewResult, tuple[ArtifactRef, ...], dict[str, bytes]]:
    store = seed_navigation(InMemoryArtifactStore())
    full = preview.canonical.configuration_facts.initial_origin == "UPLOADED"
    ids = ("baseline_to_initial", "initial_to_modified") if full else ("initial_to_modified",)
    surface_result = _surface_result()
    surface = surface_result.surface
    assert surface is not None
    pairs = tuple(BundlePairInput(pair_id, index, index + 1, surface_result)
        for index, pair_id in enumerate(ids))
    bundle = assemble_bundle(_request(pairs,
        profile=BundleProfile.MULTI_PAIR if full else BundleProfile.SINGLE_PAIR,
        inputs=tuple(BundleInput(index, name, name) for index, name in enumerate(
            ("baseline", "initial", "modified") if full else ("baseline", "modified")))),
        source_store=store)
    assert bundle.bundle is not None
    identity_pairs = tuple(PreviewIdentityPair(pair_id, ProjectIdentityApplicability.NOT_APPLICABLE,
        ProjectIdentityStatus.NOT_APPLICABLE, ProjectIdentityMode.DETAILED, None, None) for pair_id in ids)
    identity_digest = raw_blob_digest(canonicalize_json_value({
        "schema": "project-identity-assessment-set/v1",
        "pairs": [[pair_id, "NOT_APPLICABLE", "NOT_APPLICABLE", None] for pair_id in ids]}))
    comparison_pairs = tuple(PreviewComparisonPair(pair_id=pair_id,
        before_snapshot_digest=preview.digests.snapshot_digest,
        current_snapshot_digest=preview.digests.snapshot_digest,
        comparison_digest=surface.comparison_digest.value,
        risk_digest=(surface.risk_evaluation_digest or DigestRef("sha256:" + "0" * 64)).value,
        surface_digest=next(pair.surface_digest.value for pair in bundle.bundle.pairs if pair.pair_id == pair_id),
        ruleset_digest=preview.canonical.storage_projection_ruleset_digest.value,
        structure_audit_artifact_id=None) for pair_id in ids)
    closure_refs = {ref.artifact_id: ref for ref in (*refs, *bundle.referenced_artifacts,
        bundle.bundle.manifest_ref)}
    # The caller owns canonical/source payloads; only the closure builder needs
    # their immutable references, so create its bytes without reading those files.
    from gateway_backend.application.checkpoints import ReadyClosureDocument, put_ready_closure
    ready = put_ready_closure(store, ReadyClosureDocument.build(
        tuple(closure_refs.values()), preview.contract_version))
    closure_refs[ready.artifact_id] = ready
    payloads = {ref.artifact_id: raw for ref, raw in store._artifacts.values()}
    return replace(preview, bundle_artifact_id=bundle.bundle.manifest_ref.artifact_id,
        ready_closure_artifact_id=ready.artifact_id,
        identity_pairs=identity_pairs, identity_assessment_set_digest=identity_digest,
        comparison_pairs=comparison_pairs,
        digests=replace(preview.digests, bundle_digest=bundle.bundle.bundle_digest.value,
            comparison_digest=comparison_pairs[-1].comparison_digest,
            surface_digest=comparison_pairs[-1].surface_digest,
            risk_digest=comparison_pairs[-1].risk_digest)), tuple(closure_refs.values()), payloads
