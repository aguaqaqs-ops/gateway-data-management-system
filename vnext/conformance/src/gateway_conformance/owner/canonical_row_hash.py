"""Canonical row hash capability scenario semantic checks."""

from __future__ import annotations

import json
from typing import Any, cast

from gateway_shared_kernel import (
    DigestKind,
    canonicalize_identifier,
    canonicalize_jcs,
    semantic_digest,
)

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.owner.arrow_row_hash_oracle import compute_table_content_identity
from gateway_conformance.owner.validate import (
    CANONICAL_TABLE_REQUEST_SCHEMA_ID,
    CANONICAL_TABLE_RESULT_SCHEMA_ID,
    validate_owner_payload,
)
from gateway_conformance.scenario.closure import ScenarioClosure
from gateway_conformance.strict_json import loads_strict_json_bytes

CANONICAL_ROW_HASH_SUBJECT = ("data", "capability", "canonical-row-hashes")
FORMAL_SCENARIO_ID = "data.canonical-row-hashes.mixed-scalars"
FORMAL_REQUIRED_PROFILES = ["integration", "provider-matrix", "reference"]
TABLE_STREAM_LOGICAL_NAME = "table-stream"
ORACLE_ANCHOR_LOGICAL_NAME = "row-hash-oracle-anchor"
FORMAL_INPUT_ASSET_NAMES = frozenset({TABLE_STREAM_LOGICAL_NAME})
FORMAL_OWNER_CLOSURE_ASSET_NAMES = frozenset({ORACLE_ANCHOR_LOGICAL_NAME})
ANCHOR_SCHEMA_VERSION = 1
_ANCHOR_ALLOWED_KEYS = frozenset(
    {
        "anchor_schema_version",
        "scenario_id",
        "row_count",
        "raw_content_digest",
        "sorted_row_hashes_hex",
    }
)


def assert_canonical_unsigned_decimal_string(value: str, *, label: str) -> None:
    if not value.isdigit():
        raise ConformanceValidationError(f"{label} must be a canonical unsigned decimal string")
    if value != "0" and value.startswith("0"):
        raise ConformanceValidationError(f"{label} must not have leading zeros")


def table_schema_digest_from_declared_fields(fields: list[dict[str, Any]]) -> str:
    projected: list[dict[str, Any]] = []
    for index, field in enumerate(fields):
        if not isinstance(field, dict):
            raise ConformanceValidationError(
                f"declared_table_schema.fields[{index}] must be an object"
            )
        name = field.get("name")
        nullable = field.get("nullable")
        semantic_type = field.get("semantic_type")
        if not isinstance(name, str) or not name:
            raise ConformanceValidationError(
                f"declared_table_schema.fields[{index}].name must be a non-empty string"
            )
        if type(nullable) is not bool:
            raise ConformanceValidationError(
                f"declared_table_schema.fields[{index}].nullable must be a boolean"
            )
        if not isinstance(semantic_type, dict):
            raise ConformanceValidationError(
                f"declared_table_schema.fields[{index}].semantic_type must be an object"
            )
        kind = semantic_type.get("kind")
        if kind == "null" and nullable is not True:
            raise ConformanceValidationError(
                f"declared_table_schema.fields[{index}].null kind requires nullable true"
            )
        projected.append(
            {
                "name": canonicalize_identifier(name),
                "nullable": nullable,
                "semantic_type": semantic_type,
            }
        )
    projected.sort(key=lambda item: str(item["name"]))
    payload_bytes = json.dumps({"fields": projected}, separators=(",", ":")).encode("utf-8")
    canonical_payload = canonicalize_jcs(payload_bytes)
    return semantic_digest(DigestKind.TABLE_SCHEMA, canonical_payload).digest_ref.value


def _stimulus_request_value(manifest: dict[str, Any]) -> dict[str, Any]:
    stimulus = manifest["stimulus"]
    payload = stimulus["payload"]
    if str(payload["storage"]) != "inline":
        raise ConformanceValidationError("canonical-row-hash stimulus must use inline request")
    value = payload["value"]
    if not isinstance(value, dict):
        raise ConformanceValidationError("canonical-row-hash stimulus value must be an object")
    return cast(
        dict[str, Any],
        validate_owner_payload(
            value,
            owner="canonical-row-hash-capability",
            contract_id="gateway-vnext.canonical-row-hash-compute-boundary",
            semantic_version="1.0.0",
            schema_id=CANONICAL_TABLE_REQUEST_SCHEMA_ID,
            schema_version=1,
        ),
    )


def _golden_result_value(closure: ScenarioClosure, manifest: dict[str, Any]) -> dict[str, Any]:
    expectation_id = None
    for entry in manifest["expected"]:
        if str(entry["expectation_id"]) == "row-hashes":
            expectation_id = "row-hashes"
            break
    if expectation_id is None:
        raise ConformanceValidationError(
            "canonical-row-hash scenario missing row-hashes expectation"
        )
    envelope = closure.golden_envelopes.get(expectation_id)
    if envelope is None:
        raise ConformanceValidationError("missing row-hashes golden envelope")
    payload = envelope["payload"]
    if str(payload["storage"]) != "inline":
        raise ConformanceValidationError("row-hashes golden must be inline structured payload")
    value = payload["value"]
    if not isinstance(value, dict):
        raise ConformanceValidationError("row-hashes golden value must be an object")
    return cast(
        dict[str, Any],
        validate_owner_payload(
            value,
            owner="canonical-row-hash-capability",
            contract_id="gateway-vnext.canonical-row-hash-compute-boundary",
            semantic_version="1.0.0",
            schema_id=CANONICAL_TABLE_RESULT_SCHEMA_ID,
            schema_version=1,
        ),
    )


def assert_canonical_row_hash_scenario_semantics(
    manifest: dict[str, Any], closure: ScenarioClosure
) -> None:
    subject = manifest["subject"]
    if (
        str(manifest["track"]) != CANONICAL_ROW_HASH_SUBJECT[0]
        or str(subject["kind"]) != CANONICAL_ROW_HASH_SUBJECT[1]
        or str(subject["name"]) != CANONICAL_ROW_HASH_SUBJECT[2]
    ):
        return

    request = _stimulus_request_value(manifest)
    result = _golden_result_value(closure, manifest)

    fields = request["declared_table_schema"]["fields"]
    if not isinstance(fields, list):
        raise ConformanceValidationError("declared_table_schema.fields must be an array")
    recomputed_schema = table_schema_digest_from_declared_fields(fields)
    if str(result["table_schema_digest"]) != recomputed_schema:
        raise ConformanceValidationError("table_schema_digest does not match declared schema")

    assets = manifest.get("input_assets", [])
    owner_closure = manifest.get("owner_closure_assets", [])
    if str(manifest["scenario_id"]) == FORMAL_SCENARIO_ID:
        if len(assets) != 1:
            raise ConformanceValidationError(
                "formal canonical-row-hash scenario requires exactly one harness input asset"
            )
        logical_names = {str(asset["logical_name"]) for asset in assets}
        if logical_names != FORMAL_INPUT_ASSET_NAMES:
            raise ConformanceValidationError("formal canonical-row-hash input asset set mismatch")
        if len(owner_closure) != 1:
            raise ConformanceValidationError(
                "formal canonical-row-hash scenario requires exactly one owner closure asset"
            )
        owner_names = {str(asset["logical_name"]) for asset in owner_closure}
        if owner_names != FORMAL_OWNER_CLOSURE_ASSET_NAMES:
            raise ConformanceValidationError(
                "formal canonical-row-hash owner closure asset set mismatch"
            )
    elif len(assets) != 1:
        raise ConformanceValidationError(
            "canonical-row-hash scenario requires exactly one input asset"
        )

    table_asset = next(
        (asset for asset in assets if str(asset["logical_name"]) == TABLE_STREAM_LOGICAL_NAME),
        None,
    )
    if table_asset is None:
        raise ConformanceValidationError("input asset logical_name must be table-stream")
    if table_asset.get("content_binding") is not None:
        raise ConformanceValidationError("table-stream asset must not declare content_binding")

    resolved = closure.assets.get(TABLE_STREAM_LOGICAL_NAME)
    if resolved is None:
        raise ConformanceValidationError("missing resolved table-stream asset bytes")

    if manifest["required_profiles"] != FORMAL_REQUIRED_PROFILES:
        raise ConformanceValidationError(
            "canonical-row-hash formal scenario required_profiles must be "
            "integration, provider-matrix, reference in that order"
        )

    ipc_bytes = resolved.raw
    row_count, raw_content_digest, sorted_hashes = compute_table_content_identity(
        ipc_bytes, cast(list[dict[str, Any]], fields)
    )
    if str(result["row_count"]) != row_count:
        raise ConformanceValidationError("row_count does not match input arrow stream")
    assert_canonical_unsigned_decimal_string(str(result["row_count"]), label="row_count")
    assert_canonical_unsigned_decimal_string(row_count, label="computed row_count")
    if str(result["raw_content_digest"]) != raw_content_digest:
        raise ConformanceValidationError("raw_content_digest does not match input arrow stream")

    if str(manifest["scenario_id"]) == FORMAL_SCENARIO_ID:
        _assert_oracle_anchor_asset(closure, row_count, raw_content_digest, sorted_hashes)


def _assert_oracle_anchor_asset(
    closure: ScenarioClosure,
    row_count: str,
    raw_content_digest: str,
    sorted_hashes: list[bytes],
) -> None:
    resolved = closure.owner_closure_assets.get(ORACLE_ANCHOR_LOGICAL_NAME)
    if resolved is None:
        raise ConformanceValidationError("missing row-hash-oracle-anchor owner closure bytes")
    payload = loads_strict_json_bytes(resolved.raw)
    extra = set(payload.keys()) - _ANCHOR_ALLOWED_KEYS
    if extra:
        raise ConformanceValidationError("oracle anchor has unknown fields")
    if int(payload.get("anchor_schema_version", -1)) != ANCHOR_SCHEMA_VERSION:
        raise ConformanceValidationError("oracle anchor schema version mismatch")
    if str(payload.get("scenario_id")) != FORMAL_SCENARIO_ID:
        raise ConformanceValidationError("oracle anchor scenario_id mismatch")
    if str(payload.get("row_count")) != row_count:
        raise ConformanceValidationError("oracle anchor row_count mismatch")
    if str(payload.get("raw_content_digest")) != raw_content_digest:
        raise ConformanceValidationError("oracle anchor raw_content_digest mismatch")
    anchor_hex = payload.get("sorted_row_hashes_hex")
    if not isinstance(anchor_hex, list):
        raise ConformanceValidationError("oracle anchor sorted_row_hashes_hex invalid")
    expected = [bytes.fromhex(str(item)) for item in anchor_hex]
    if expected != sorted_hashes:
        raise ConformanceValidationError("oracle anchor row hashes mismatch")
