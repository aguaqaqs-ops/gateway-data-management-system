from __future__ import annotations

from collections.abc import Mapping

from ...core.digests import DigestRef


def build_bundle_digest(bundle: object) -> DigestRef:
    payload_for_digest = getattr(bundle, "payload_for_digest", None)
    if not callable(payload_for_digest):
        raise TypeError("bundle must provide payload_for_digest()")
    payload = payload_for_digest()
    if not isinstance(payload, Mapping):
        raise TypeError("bundle payload_for_digest() must return a mapping")
    artifact_closure_manifest_digest = getattr(bundle, "artifact_closure_manifest_digest", None)
    if artifact_closure_manifest_digest is None:
        raise ValueError("artifact_closure_manifest_digest is required to build bundle digest")
    return DigestRef.from_payload(
        {
            "bundle_contract_version": getattr(bundle, "bundle_contract_version"),
            "bundle_manifest": payload,
            "artifact_closure_manifest_digest": DigestRef.parse(str(artifact_closure_manifest_digest)).to_payload(),
        }
    )


def build_bundle_closure_digest(closure: object) -> DigestRef:
    payload_for_digest = getattr(closure, "payload_for_digest", None)
    if not callable(payload_for_digest):
        raise TypeError("closure must provide payload_for_digest()")
    payload = payload_for_digest()
    if not isinstance(payload, Mapping):
        raise TypeError("closure payload_for_digest() must return a mapping")
    return DigestRef.from_payload(payload)

