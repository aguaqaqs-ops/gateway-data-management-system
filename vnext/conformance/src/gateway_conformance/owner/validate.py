"""Owner schema validation and content digest computation."""

from __future__ import annotations

from typing import Any

import jsonschema
from jsonschema import Draft202012Validator

from gateway_shared_kernel import DigestKind, semantic_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.owner.registry import (
    OwnerSchemaContract,
    resolve_owner_schema,
    schema_path_for,
)
from gateway_conformance.owner.schema_registry import validator_for_owner_schema
from gateway_conformance.strict_json import loads_strict_json_bytes

CANONICAL_TABLE_REQUEST_SCHEMA_ID = "gateway-vnext.canonical-table-request.v1"
CANONICAL_TABLE_RESULT_SCHEMA_ID = "gateway-vnext.canonical-table-result.v1"

_DIGEST_KIND_BY_NAME = {
    "scenario-input": DigestKind.SCENARIO_INPUT,
    "scenario-fixture": DigestKind.SCENARIO_FIXTURE,
    "canonical-table-result": DigestKind.CANONICAL_TABLE_RESULT,
}


def _digest_kind(name: str) -> DigestKind:
    kind = _DIGEST_KIND_BY_NAME.get(name)
    if kind is None:
        raise ConformanceValidationError(f"unknown owner digest kind: {name}")
    return kind


def _load_schema_validator(contract: OwnerSchemaContract) -> Draft202012Validator:
    return validator_for_owner_schema(schema_path_for(contract))


def _digest_projection(value: Any, *, schema_id: str) -> Any:
    if schema_id == CANONICAL_TABLE_RESULT_SCHEMA_ID:
        if not isinstance(value, dict):
            raise ConformanceValidationError("canonical table result must be an object")
        projected = dict(value)
        projected.pop("diagnostics", None)
        return projected
    return value


def validate_owner_payload(
    value: Any,
    *,
    owner: str,
    contract_id: str,
    semantic_version: str,
    schema_id: str,
    schema_version: int,
) -> Any:
    contract = resolve_owner_schema(
        owner=owner,
        contract_id=contract_id,
        semantic_version=semantic_version,
        schema_id=schema_id,
        schema_version=schema_version,
    )
    validator = _load_schema_validator(contract)
    try:
        validator.validate(value)
    except jsonschema.ValidationError as exc:
        raise ConformanceValidationError(exc.message) from exc
    return value


def compute_owner_content_digest(
    value: Any,
    *,
    owner: str,
    contract_id: str,
    semantic_version: str,
    schema_id: str,
    schema_version: int,
) -> str:
    contract = resolve_owner_schema(
        owner=owner,
        contract_id=contract_id,
        semantic_version=semantic_version,
        schema_id=schema_id,
        schema_version=schema_version,
    )
    validate_owner_payload(
        value,
        owner=owner,
        contract_id=contract_id,
        semantic_version=semantic_version,
        schema_id=schema_id,
        schema_version=schema_version,
    )
    projected = _digest_projection(value, schema_id=schema_id)
    payload_bytes = canonicalize_json_value(projected)
    kind = _digest_kind(contract.digest_kind)
    return semantic_digest(kind, payload_bytes).digest_ref.value


def compute_structured_asset_content_digest(
    raw: bytes,
    *,
    content_binding: dict[str, Any],
    contract_binding: dict[str, Any] | None = None,
) -> str:
    try:
        parsed = loads_strict_json_bytes(raw)
    except ConformanceValidationError as exc:
        raise ConformanceValidationError("structured input asset is not valid strict JSON") from exc
    if contract_binding is None:
        raise ConformanceValidationError("structured asset requires contract binding for digest")
    return compute_owner_content_digest(
        parsed,
        owner=str(contract_binding["owner"]),
        contract_id=str(contract_binding["contract_id"]),
        semantic_version=str(contract_binding["semantic_version"]),
        schema_id=str(content_binding["schema_id"]),
        schema_version=int(content_binding["schema_version"]),
    )


def compute_golden_content_digest(envelope: dict[str, Any]) -> str:
    binding = envelope["contract_binding"]
    descriptor = envelope["payload_descriptor"]
    payload = envelope["payload"]
    kind = str(envelope["kind"])
    if kind in {"structured", "recovery"}:
        if payload.get("storage") != "inline":
            raise ConformanceValidationError(f"{kind} golden must use inline payload")
        return compute_owner_content_digest(
            payload["value"],
            owner=str(binding["owner"]),
            contract_id=str(binding["contract_id"]),
            semantic_version=str(binding["semantic_version"]),
            schema_id=str(descriptor["schema_id"]),
            schema_version=int(descriptor["schema_version"]),
        )
    if kind == "artifact":
        if payload.get("storage") != "closure":
            raise ConformanceValidationError("artifact golden must use closure payload")
        closure_value = payload["value"]
        manifest_value = closure_value["manifest"]
        digest = compute_owner_content_digest(
            manifest_value,
            owner=str(binding["owner"]),
            contract_id=str(binding["contract_id"]),
            semantic_version=str(binding["semantic_version"]),
            schema_id=str(descriptor["schema_id"]),
            schema_version=int(descriptor["schema_version"]),
        )
        if str(closure_value.get("content_digest")) != digest:
            raise ConformanceValidationError("artifact closure inner content_digest mismatch")
        return digest
    raise ConformanceValidationError(f"unsupported golden kind: {kind}")
