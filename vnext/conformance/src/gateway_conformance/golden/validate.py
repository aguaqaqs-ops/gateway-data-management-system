"""Golden envelope semantic validation."""

from __future__ import annotations

from typing import Any

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.golden.security import assert_golden_payload_safe
from gateway_conformance.owner.validate import compute_golden_content_digest


def assert_manifest_envelope_binding(
    manifest_entry: dict[str, Any],
    envelope: dict[str, Any],
) -> None:
    if str(manifest_entry["expectation_id"]) != str(envelope["expectation_id"]):
        raise ConformanceValidationError("golden expectation_id mismatch")
    if str(manifest_entry["kind"]) != str(envelope["kind"]):
        raise ConformanceValidationError("golden kind mismatch")

    manifest_binding = manifest_entry["contract_binding"]
    envelope_binding = envelope["contract_binding"]
    for key in ("owner", "contract_id", "semantic_version"):
        if manifest_binding[key] != envelope_binding[key]:
            raise ConformanceValidationError(f"golden contract_binding.{key} mismatch")
    if manifest_binding.get("wire_schema_version") != envelope_binding.get("wire_schema_version"):
        raise ConformanceValidationError("golden contract_binding.wire_schema_version mismatch")

    if str(manifest_entry["content_digest"]) != str(envelope["content_digest"]):
        raise ConformanceValidationError("golden content_digest mismatch")

    kind = str(envelope["kind"])
    payload = envelope["payload"]
    descriptor = envelope["payload_descriptor"]
    if kind in {"structured", "recovery"}:
        if payload["storage"] != "inline":
            raise ConformanceValidationError(f"{kind} golden must use inline payload")
        expected_mode = "exact-canonical" if kind == "structured" else "recovery-checkpoints"
        if descriptor["comparison_mode"] != expected_mode:
            raise ConformanceValidationError("golden comparison_mode mismatch for kind")
        assert_golden_payload_safe(payload["value"])
    elif kind == "artifact":
        if payload["storage"] != "closure":
            raise ConformanceValidationError("artifact golden must use closure payload")
        if descriptor["comparison_mode"] != "artifact-closure":
            raise ConformanceValidationError("artifact golden comparison_mode mismatch")
        assert_golden_payload_safe(payload["value"])
    computed = compute_golden_content_digest(envelope)
    if computed != str(envelope["content_digest"]):
        raise ConformanceValidationError("golden envelope content_digest does not match payload")


def validate_golden_bindings(
    manifest: dict[str, Any], envelopes: dict[str, dict[str, Any]]
) -> None:
    for entry in manifest["expected"]:
        expectation_id = str(entry["expectation_id"])
        envelope = envelopes.get(expectation_id)
        if envelope is None:
            raise ConformanceValidationError(f"missing golden envelope for {expectation_id}")
        assert_manifest_envelope_binding(entry, envelope)
