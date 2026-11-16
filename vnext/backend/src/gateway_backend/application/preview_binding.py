"""Accepted Preview/READY binding identity, checked at T1, finalize and review reads."""
from __future__ import annotations

from dataclasses import asdict
from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_backend.domain.workspace.models import PreviewArtifactRef, PreviewResult


def _ref_document(ref: PreviewArtifactRef | None) -> object:
    return None if ref is None else [ref.artifact_id, ref.media_type, ref.size_bytes, ref.raw_sha256.value]


def derive_preview_ready_closure_digest(preview: PreviewResult) -> str:
    """Freeze the complete result binding, including audit absence, without another result."""
    canonical = preview.canonical
    payload = {
        "binding_contract_version": "backend-vnext/preview-ready-binding/v3",
        "preview_result_id": preview.preview_result_id,
        "workspace_id": preview.workspace_id,
        "upload_revision_id": preview.upload_revision_id,
        "generation": preview.generation,
        "repository_id": preview.repository_id,
        "business_baseline_node_id": preview.business_baseline_node_id,
        "business_baseline_commit_id": preview.business_baseline_commit_id,
        "baseline_head_version": preview.baseline_head_version,
        "ruleset_version": preview.ruleset_version,
        "contract_version": preview.contract_version,
        "provider_versions": dict(preview.provider_versions),
        "digests": asdict(preview.digests),
        "canonical": {
            "configuration_facts_digest": canonical.configuration_facts.facts_digest,
            "initial_canonical_state_digest": canonical.initial_canonical_state_digest.value,
            "baseline_canonical_state_digest": canonical.baseline_canonical_state_digest.value,
            "modified_canonical_state_digest": canonical.modified_canonical_state_digest.value,
            "storage_projection_ruleset_digest": canonical.storage_projection_ruleset_digest.value,
            "rules_semantically_equal": canonical.rules_semantically_equal,
            "canonical_table_set_closure_ref": _ref_document(canonical.canonical_table_set_closure_ref),
            "canonical_table_set_closure_digest": canonical.canonical_table_set_closure_digest.value,
            "canonicalization_manifest_ref": _ref_document(canonical.canonicalization_manifest_ref),
            "canonicalization_manifest_digest": canonical.canonicalization_manifest_digest.value,
        },
        "identity_assessment_set_digest": preview.identity_assessment_set_digest.value,
        "identity_pairs": [{
            "pair_id": pair.pair_id, "applicability": pair.applicability.value,
            "status": pair.status.value, "mode": pair.mode.value,
            "assessment_ref": _ref_document(pair.assessment_ref),
            "assessment_digest": None if pair.assessment_digest is None else pair.assessment_digest.value,
        } for pair in preview.identity_pairs],
        "comparison_pairs": [pair.model_dump(mode="json") for pair in preview.comparison_pairs],
        "bundle_artifact_id": preview.bundle_artifact_id,
        "ready_closure_artifact_id": preview.ready_closure_artifact_id,
        "operation_id": preview.operation_id,
    }
    return "v3:" + raw_blob_digest(canonicalize_json_value(payload)).value
