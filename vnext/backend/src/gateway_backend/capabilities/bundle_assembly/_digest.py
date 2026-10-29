"""Canonical bundle manifest and digest helpers."""

from __future__ import annotations

from collections.abc import Iterable

from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.bundle_assembly.contracts import (
    BUNDLE_CONTRACT_VERSION,
    BundleArtifactKind,
    BundleArtifactManifest,
    BundleAssemblyStatus,
    BundleClosureEntry,
    BundleInput,
    BundlePair,
    BundlePairFailure,
    BundleProfile,
)


def integrity_payload(ref: object) -> dict[str, object]:
    return {
        "media_type": ref.media_type,  # type: ignore[attr-defined]
        "raw_sha256": ref.raw_sha256.value,  # type: ignore[attr-defined]
        "size_bytes": ref.size_bytes,  # type: ignore[attr-defined]
    }


def closure_semantic_payload(closure: BundleArtifactManifest) -> dict[str, object]:
    return {
        "entries": [_closure_entry_payload(item) for item in closure.entries]
    }


def _closure_entry_payload(item: BundleClosureEntry) -> dict[str, object]:
    payload: dict[str, object] = {
        "integrity": integrity_payload(item.artifact_ref),
        "kind": item.kind.value,
        "logical_path": item.logical_path,
        "shared": item.shared,
    }
    if item.kind is BundleArtifactKind.SNAPSHOT_TABLE:
        payload["table_bindings"] = [binding.to_document() for binding in item.table_bindings]
    else:
        payload["pair_id"] = item.pair_id
        payload["table_name"] = item.table_name
    return payload


def manifest_semantic_payload(
    *,
    profile: BundleProfile,
    status: BundleAssemblyStatus,
    inputs: Iterable[BundleInput],
    pairs: Iterable[BundlePair],
    failed_pairs: Iterable[BundlePairFailure],
    closure: BundleArtifactManifest,
    diagnostics: Iterable[str],
) -> dict[str, object]:
    return {
        "bundle_contract_version": BUNDLE_CONTRACT_VERSION,
        "bundle_profile": profile.value,
        "closure": closure_semantic_payload(closure),
        "diagnostics": list(sorted(diagnostics)),
        "failed_pairs": [item.to_document() for item in sorted(failed_pairs, key=lambda item: item.pair_id)],
        "inputs": [item.to_document() for item in sorted(inputs, key=lambda item: item.input_index)],
        "pairs": [
            {
                "before_input_index": item.before_input_index,
                "comparison_digest": item.comparison_digest.value,
                "current_input_index": item.current_input_index,
                "pair_id": item.pair_id,
                "risk_evaluation_digest": (
                    None
                    if item.risk_evaluation_digest is None
                    else item.risk_evaluation_digest.value
                ),
                "status": item.status.value,
                "summary": {key: value for key, value in item.summary},
                "surface_digest": item.surface_digest.value,
            }
            for item in sorted(pairs, key=lambda item: item.pair_id)
        ],
        "status": status.value,
    }


def manifest_digest_payload(
    *,
    profile: BundleProfile,
    status: BundleAssemblyStatus,
    inputs: Iterable[BundleInput],
    pairs: Iterable[BundlePair],
    failed_pairs: Iterable[BundlePairFailure],
    closure: BundleArtifactManifest,
    diagnostics: Iterable[str],
) -> dict[str, object]:
    return manifest_semantic_payload(
        profile=profile,
        status=status,
        inputs=inputs,
        pairs=pairs,
        failed_pairs=failed_pairs,
        closure=closure,
        diagnostics=diagnostics,
    )


def compute_bundle_digest(
    *,
    profile: BundleProfile,
    status: BundleAssemblyStatus,
    inputs: Iterable[BundleInput],
    pairs: Iterable[BundlePair],
    failed_pairs: Iterable[BundlePairFailure],
    closure: BundleArtifactManifest,
    diagnostics: Iterable[str],
) -> DigestRef:
    payload = manifest_digest_payload(
        profile=profile,
        status=status,
        inputs=inputs,
        pairs=pairs,
        failed_pairs=failed_pairs,
        closure=closure,
        diagnostics=diagnostics,
    )
    return raw_blob_digest(canonicalize_json_value(payload))


def closure_digest(closure: BundleArtifactManifest) -> DigestRef:
    return raw_blob_digest(canonicalize_json_value(closure_semantic_payload(closure)))


def manifest_bytes(
    *,
    profile: BundleProfile,
    status: BundleAssemblyStatus,
    inputs: Iterable[BundleInput],
    pairs: Iterable[BundlePair],
    failed_pairs: Iterable[BundlePairFailure],
    closure: BundleArtifactManifest,
    closure_manifest_digest: DigestRef,
    bundle_digest: DigestRef,
    diagnostics: Iterable[str],
) -> bytes:
    payload = manifest_semantic_payload(
        profile=profile,
        status=status,
        inputs=inputs,
        pairs=pairs,
        failed_pairs=failed_pairs,
        closure=closure,
        diagnostics=diagnostics,
    )
    return canonicalize_json_value(
        {
            **payload,
            "bundle_digest": bundle_digest.value,
            "closure_manifest_digest": closure_manifest_digest.value,
            "closure_entries": [item.to_document() for item in closure.entries],
        }
    )


def closure_bytes(
    *,
    bundle_digest: DigestRef,
    closure: BundleArtifactManifest,
    manifest_digest: DigestRef,
) -> bytes:
    return canonicalize_json_value(
        {
            "bundle_contract_version": BUNDLE_CONTRACT_VERSION,
            "bundle_digest": bundle_digest.value,
            "bundle_manifest_digest": manifest_digest.value,
            **closure_semantic_payload(closure),
            "closure_entries": [item.to_document() for item in closure.entries],
        }
    )
