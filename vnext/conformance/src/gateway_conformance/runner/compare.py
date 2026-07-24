"""Runner comparison authority."""

from __future__ import annotations

from typing import Any

from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.owner.validate import (
    compute_golden_content_digest,
    compute_owner_content_digest,
)
from gateway_conformance.runner.types import ActualObservation, ComparisonRow
from gateway_conformance.scenario.closure import ScenarioClosure


def _binding_key(binding: dict[str, Any]) -> tuple[str, str, str, str | None]:
    return (
        str(binding["owner"]),
        str(binding["contract_id"]),
        str(binding["semantic_version"]),
        None if binding.get("wire_schema_version") is None else str(binding["wire_schema_version"]),
    )


def _descriptor_key(descriptor: dict[str, Any]) -> tuple[str, str, int, int, str]:
    return (
        str(descriptor["media_type"]),
        str(descriptor["schema_id"]),
        int(descriptor["schema_version"]),
        int(descriptor["canonical_encoding_version"]),
        str(descriptor["comparison_mode"]),
    )


def _payload_value(observation: ActualObservation) -> Any:
    payload = observation.payload
    storage = str(payload["storage"])
    if storage == "inline":
        return payload["value"]
    if storage == "artifact-closure-ref":
        raise ConformanceValidationError("artifact-closure-ref actual payload not supported in R2")
    raise ConformanceValidationError(f"unsupported actual payload storage: {storage}")


def recompute_actual_digest(observation: ActualObservation) -> str:
    binding = observation.contract_binding
    descriptor = observation.payload_descriptor
    value = _payload_value(observation)
    kind_mode = str(descriptor["comparison_mode"])
    if kind_mode == "artifact-closure":
        if not isinstance(value, dict):
            raise ConformanceValidationError("artifact closure value must be object")
        manifest_value = value.get("manifest")
        if manifest_value is None:
            raise ConformanceValidationError("artifact closure missing manifest")
        digest = compute_owner_content_digest(
            manifest_value,
            owner=str(binding["owner"]),
            contract_id=str(binding["contract_id"]),
            semantic_version=str(binding["semantic_version"]),
            schema_id=str(descriptor["schema_id"]),
            schema_version=int(descriptor["schema_version"]),
        )
        if str(value.get("content_digest")) != digest:
            raise ConformanceValidationError("artifact closure inner content_digest mismatch")
        return digest
    return compute_owner_content_digest(
        value,
        owner=str(binding["owner"]),
        contract_id=str(binding["contract_id"]),
        semantic_version=str(binding["semantic_version"]),
        schema_id=str(descriptor["schema_id"]),
        schema_version=int(descriptor["schema_version"]),
    )


def expected_digest_from_golden(envelope: dict[str, Any]) -> str:
    computed = compute_golden_content_digest(envelope)
    declared = str(envelope["content_digest"])
    if computed != declared:
        raise ConformanceValidationError("golden envelope content_digest mismatch")
    return computed


def _compare_payload_bytes(
    expected_envelope: dict[str, Any], observation: ActualObservation
) -> bool:
    mode = str(observation.payload_descriptor["comparison_mode"])
    expected_payload = expected_envelope["payload"]
    actual_value = _payload_value(observation)
    if mode == "exact-canonical":
        if str(expected_payload["storage"]) != "inline":
            raise ConformanceValidationError("structured golden must be inline")
        expected_value = expected_payload["value"]
        return canonicalize_json_value(expected_value) == canonicalize_json_value(actual_value)
    if mode == "recovery-checkpoints":
        if str(expected_payload["storage"]) != "inline":
            raise ConformanceValidationError("recovery golden must be inline")
        expected_value = expected_payload["value"]
        return canonicalize_json_value(expected_value) == canonicalize_json_value(actual_value)
    if mode == "artifact-closure":
        if str(expected_payload["storage"]) != "closure":
            raise ConformanceValidationError("artifact golden must be closure")
        expected_closure = expected_payload["value"]
        if not isinstance(actual_value, dict):
            return False
        return canonicalize_json_value(expected_closure) == canonicalize_json_value(actual_value)
    raise ConformanceValidationError(f"unsupported comparison mode: {mode}")


def validate_observation_set(
    observations: list[ActualObservation],
    *,
    observation_point: str,
    requested_ids: list[str],
) -> None:
    if observations:
        for item in observations:
            if item.observation_point != observation_point:
                raise ConformanceValidationError("observation_point mismatch")
    seen: set[str] = set()
    for item in observations:
        if item.expectation_id in seen:
            raise ConformanceValidationError("duplicate observation")
        seen.add(item.expectation_id)
    expected_set = set(requested_ids)
    actual_set = {item.expectation_id for item in observations}
    if actual_set != expected_set:
        if actual_set - expected_set:
            raise ConformanceValidationError("unexpected observation")
        raise ConformanceValidationError("missing observation")


def compare_observations(
    closure: ScenarioClosure,
    observations: list[ActualObservation],
    *,
    manifest_entries: list[dict[str, Any]],
) -> list[ComparisonRow]:
    rows: list[ComparisonRow] = []
    by_id = {str(item["expectation_id"]): item for item in manifest_entries}
    for observation in sorted(observations, key=lambda item: item.expectation_id):
        entry = by_id.get(observation.expectation_id)
        if entry is None:
            raise ConformanceValidationError("unknown expectation in observation")
        envelope = closure.golden_envelopes[observation.expectation_id]
        if str(entry["kind"]) != str(envelope["kind"]):
            raise ConformanceValidationError("observation kind mismatch")
        if _binding_key(entry["contract_binding"]) != _binding_key(observation.contract_binding):
            raise ConformanceValidationError("observation contract_binding mismatch")
        if _binding_key(envelope["contract_binding"]) != _binding_key(observation.contract_binding):
            raise ConformanceValidationError("observation binding does not match golden")
        if _descriptor_key(envelope["payload_descriptor"]) != _descriptor_key(
            observation.payload_descriptor
        ):
            raise ConformanceValidationError("observation payload_descriptor mismatch")
        if observation.canonical_encoding_version != 1:
            raise ConformanceValidationError("canonical_encoding_version must be 1")
        recomputed = recompute_actual_digest(observation)
        if recomputed != observation.actual_content_digest:
            raise ConformanceValidationError("actual_content_digest does not match payload")
        expected_digest = expected_digest_from_golden(envelope)
        payload_match = _compare_payload_bytes(envelope, observation)
        digest_match = recomputed == expected_digest and payload_match
        rows.append(
            ComparisonRow(
                expectation_id=observation.expectation_id,
                expected_content_digest=expected_digest,
                actual_content_digest=recomputed,
                outcome="MATCH" if digest_match else "MISMATCH",
            )
        )
    return rows


def compare_checkpoint(
    closure: ScenarioClosure,
    observations: list[ActualObservation],
    *,
    checkpoint: str,
    manifest_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    if not observations:
        return {"checkpoint": checkpoint, "outcome": "NOT_RUN", "content_digest": None}
    rows = compare_observations(closure, observations, manifest_entries=manifest_entries)
    if any(row.outcome == "MISMATCH" for row in rows):
        outcome = "MISMATCH"
    elif rows:
        outcome = "MATCH"
    else:
        outcome = "NOT_RUN"
    digest = None
    expectation_digests: dict[str, str] = {}
    if outcome != "NOT_RUN":
        mismatch = next((row for row in rows if row.outcome == "MISMATCH"), None)
        chosen = mismatch or rows[0]
        digest = chosen.actual_content_digest
        for row in rows:
            if row.actual_content_digest is not None:
                expectation_digests[row.expectation_id] = row.actual_content_digest
    expectation_outcomes = {row.expectation_id: row.outcome for row in rows}
    return {
        "checkpoint": checkpoint,
        "outcome": outcome,
        "content_digest": digest,
        "expectation_digests": expectation_digests,
        "expectation_outcomes": expectation_outcomes,
    }
