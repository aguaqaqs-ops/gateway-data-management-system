"""Read the existing published metadata without introducing a transport identity."""

from __future__ import annotations

import json
from dataclasses import dataclass

from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import ArtifactRef
from gateway_backend.capabilities.bundle_assembly._assembly import (
    _bundle_artifact_id,
    _entries_from_document,
    _embedded_refs,
)
from gateway_backend.capabilities.bundle_assembly._digest import closure_semantic_payload
from gateway_backend.capabilities.bundle_assembly._refs import validate_bundle_ref
from gateway_backend.capabilities.bundle_assembly.contracts import (
    BUNDLE_CLOSURE_MEDIA_TYPE,
    BUNDLE_CONTRACT_VERSION,
    MAX_BUNDLE_CLOSURE_JSON_BYTES,
    MAX_BUNDLE_MANIFEST_JSON_BYTES,
    BundleArtifactKind,
    BundleArtifactManifest,
    BundleClosureEntry,
)


class BundleIntegrityError(ValueError):
    """Published bundle bytes contradict their owning contract."""


@dataclass(frozen=True, slots=True)
class BundleTransportMetadata:
    bundle_digest: str
    closure_ref: ArtifactRef
    expected_closure_bytes: bytes
    entries: tuple[BundleClosureEntry, ...]
    pair_digests: tuple[tuple[str, str, str], ...]


def read_bundle_transport_metadata(raw: bytes) -> BundleTransportMetadata:
    """Resolve the original closure using the assembler's existing content identity.

    The expected bytes are only a verification/lookup input. The download reader
    must still read the published closure artifact and send those original bytes.
    """
    try:
        if len(raw) > MAX_BUNDLE_MANIFEST_JSON_BYTES:
            raise ValueError("bundle manifest exceeds its JSON budget")
        document = json.loads(raw)
        if type(document) is not dict or canonicalize_json_value(document) != raw:
            raise ValueError("bundle manifest must be a canonical object")
        semantic_keys = {
            "bundle_contract_version", "bundle_profile", "closure", "diagnostics",
            "failed_pairs", "inputs", "pairs", "status",
        }
        if set(document) != semantic_keys | {
            "bundle_digest", "closure_entries", "closure_manifest_digest",
        }:
            raise ValueError("bundle manifest fields do not match the current contract")
        if document["bundle_contract_version"] != BUNDLE_CONTRACT_VERSION:
            raise ValueError("bundle contract version mismatch")
        semantic = {key: document[key] for key in semantic_keys}
        digest = raw_blob_digest(canonicalize_json_value(semantic))
        if document["bundle_digest"] != digest.value:
            raise ValueError("bundle digest mismatch")
        entries = _entries_from_document(document)
        closure = BundleArtifactManifest(entries)
        if closure.entries != entries:
            raise ValueError("bundle closure entries must be in canonical order")
        payload = closure_semantic_payload(closure)
        if document["closure"] != payload:
            raise ValueError("bundle closure semantic entries mismatch")
        if raw_blob_digest(canonicalize_json_value(payload)).value != document["closure_manifest_digest"]:
            raise ValueError("bundle closure digest mismatch")
        for entry in entries:
            validate_bundle_ref(entry.artifact_ref)
            if entry.logical_path in {"manifest.json", "artifact-closure.json"} or "\0" in entry.logical_path:
                raise ValueError("bundle closure path is reserved or invalid")
        pairs = document["pairs"]
        if type(pairs) is not list or not pairs:
            raise ValueError("bundle must contain published pairs")
        pair_ids: set[str] = set()
        pair_digests: list[tuple[str, str, str]] = []
        for pair in pairs:
            if type(pair) is not dict or type(pair.get("pair_id")) is not str:
                raise ValueError("bundle pair is malformed")
            pair_id = pair["pair_id"]
            if pair_id in pair_ids:
                raise ValueError("bundle pair identity is repeated")
            pair_ids.add(pair_id)
            surfaces = [entry for entry in entries if entry.kind is BundleArtifactKind.SURFACE and entry.pair_id == pair_id]
            if len(surfaces) != 1:
                raise ValueError("bundle pair surface is not closed")
            pair_digests.append((pair_id, pair["surface_digest"], pair["comparison_digest"]))
        expected = canonicalize_json_value({
            "bundle_contract_version": BUNDLE_CONTRACT_VERSION,
            "bundle_digest": digest.value,
            "bundle_manifest_digest": digest.value,
            **payload,
            "closure_entries": [entry.to_document() for entry in entries],
        })
        if len(expected) > MAX_BUNDLE_CLOSURE_JSON_BYTES:
            raise ValueError("bundle closure exceeds its JSON budget")
        ref = ArtifactRef(
            artifact_id=_bundle_artifact_id("closure", expected),
            media_type=BUNDLE_CLOSURE_MEDIA_TYPE,
            size_bytes=len(expected),
            raw_sha256=raw_blob_digest(expected),
        )
        return BundleTransportMetadata(digest.value, ref, expected, entries, tuple(pair_digests))
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise BundleIntegrityError("bundle metadata failed integrity verification") from exc


def validate_bundle_member_metadata(
    entry: BundleClosureEntry, raw: bytes, *,
    refs: set[ArtifactRef], pair_digests: tuple[tuple[str, str, str], ...],
) -> None:
    """Validate bounded JSON reference metadata against the final published closure."""
    try:
        document = json.loads(raw)
        if any(ref not in refs for ref in _embedded_refs(document)):
            raise ValueError("bundle member reference is outside the final closure")
        if entry.kind is BundleArtifactKind.SURFACE:
            if type(document) is not dict:
                raise ValueError("bundle surface must be an object")
            matching = [item for item in pair_digests if item[0] == entry.pair_id]
            if len(matching) != 1 or (
                document.get("surface_digest") != matching[0][1]
                or document.get("comparison_digest") != matching[0][2]
            ):
                raise ValueError("bundle pair surface digest link mismatch")
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise BundleIntegrityError("bundle member metadata failed integrity verification") from exc
