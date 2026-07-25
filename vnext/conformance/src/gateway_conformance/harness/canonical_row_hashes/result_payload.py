"""Build canonical-table-result observation payloads."""

from __future__ import annotations

import json
from typing import Any

from gateway_shared_kernel import canonicalize_jcs

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.owner.arrow_row_hash_oracle import compute_table_content_identity
from gateway_conformance.owner.canonical_row_hash import table_schema_digest_from_declared_fields
from gateway_conformance.owner.validate import compute_owner_content_digest
from gateway_conformance.runner.types import ActualObservation


def declared_fields_from_plan(plan: dict[str, object]) -> list[dict[str, Any]]:
    stimulus = plan["stimulus"]
    if not isinstance(stimulus, dict):
        raise ConformanceValidationError("stimulus must be an object")
    payload = stimulus["payload"]
    if not isinstance(payload, dict):
        raise ConformanceValidationError("stimulus payload must be an object")
    value = payload["value"]
    if not isinstance(value, dict):
        raise ConformanceValidationError("stimulus value must be an object")
    declared = value.get("declared_table_schema")
    if not isinstance(declared, dict):
        raise ConformanceValidationError("declared_table_schema missing")
    fields = declared.get("fields")
    if not isinstance(fields, list):
        raise ConformanceValidationError("declared_table_schema.fields must be an array")
    return [dict(item) for item in fields if isinstance(item, dict)]


def request_jcs_from_plan(plan: dict[str, object]) -> bytes:
    stimulus = plan["stimulus"]
    payload = cast_payload(stimulus)
    value = payload["value"]
    if not isinstance(value, dict):
        raise ConformanceValidationError("stimulus value must be an object")
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return canonicalize_jcs(encoded)


def cast_payload(stimulus: object) -> dict[str, Any]:
    if not isinstance(stimulus, dict):
        raise ConformanceValidationError("stimulus must be an object")
    payload = stimulus["payload"]
    if not isinstance(payload, dict):
        raise ConformanceValidationError("stimulus payload must be an object")
    return payload


def result_value_from_reference_ipc(
    ipc_bytes: bytes,
    fields: list[dict[str, Any]],
    *,
    contract_binding: dict[str, str],
) -> dict[str, Any]:
    row_count, raw_content_digest, _sorted_hashes = compute_table_content_identity(
        ipc_bytes, fields
    )
    table_schema_digest = table_schema_digest_from_declared_fields(fields)
    return {
        "result_schema_version": 1,
        "contract_binding": {
            "contract_id": contract_binding["contract_id"],
            "semantic_version": contract_binding["semantic_version"],
        },
        "canonical_encoding_version": 1,
        "arrow_mapping_schema_version": 1,
        "table_schema_digest": table_schema_digest,
        "row_count": row_count,
        "raw_content_digest": raw_content_digest,
        "diagnostics": [],
    }


def result_value_from_compute_jcs(result_jcs: bytes) -> dict[str, Any]:
    canonical = canonicalize_jcs(result_jcs)
    payload = json.loads(canonical)
    if not isinstance(payload, dict):
        raise ConformanceValidationError("compute result must be an object")
    return payload


def build_row_hashes_observation(
    plan: dict[str, object],
    *,
    observation_point: str,
    value: dict[str, Any],
) -> ActualObservation:
    requests = plan["observation_requests"]
    if not isinstance(requests, list):
        raise ConformanceValidationError("observation_requests must be an array")
    request = None
    for raw in requests:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("expectation_id")) == "row-hashes":
            request = raw
            break
    if request is None:
        raise ConformanceValidationError("missing row-hashes observation request")
    binding = dict(request["contract_binding"])
    descriptor = dict(request["payload_descriptor"])
    digest = compute_owner_content_digest(
        value,
        owner=str(binding["owner"]),
        contract_id=str(binding["contract_id"]),
        semantic_version=str(binding["semantic_version"]),
        schema_id=str(descriptor["schema_id"]),
        schema_version=int(descriptor["schema_version"]),
    )
    return ActualObservation(
        expectation_id="row-hashes",
        observation_point=observation_point,
        contract_binding=binding,
        payload_descriptor=descriptor,
        canonical_encoding_version=1,
        actual_content_digest=digest,
        payload={"storage": "inline", "value": value},
    )
