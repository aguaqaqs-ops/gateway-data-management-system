"""JSON Schema Draft 2020-12 self-tests for vector schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from tests.schema_paths import SCHEMA_FILES, SCHEMA_ROOT


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_registry() -> Registry:
    resources: list[tuple[str, Resource[Any]]] = []
    for name in SCHEMA_FILES:
        document = _load_json(SCHEMA_ROOT / name)
        schema_id = document["$id"]
        resources.append((schema_id, Resource.from_contents(document, default_specification=DRAFT202012)))
    return Registry().with_resources(resources)


def _validator_for(schema_name: str) -> Draft202012Validator:
    schema = _load_json(SCHEMA_ROOT / schema_name)
    registry = _build_registry()
    return Draft202012Validator(schema, registry=registry)


@pytest.mark.parametrize("schema_name", SCHEMA_FILES)
def test_schema_is_valid_draft_2020_12(schema_name: str) -> None:
    schema = _load_json(SCHEMA_ROOT / schema_name)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert isinstance(schema["$id"], str) and schema["$id"]
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        pytest.fail(f"{schema_name} failed meta-schema validation: {exc}")


def test_jcs_case_schema_accepts_valid_envelope() -> None:
    validator = _validator_for("jcs-case.schema.json")
    instance = {
        "case_schema_version": 1,
        "case_id": "jcs.object.ascii-key-order",
        "operation": "canonicalize-jcs",
        "input": {"json_utf8_base64url": "e30"},
        "expected": {"canonical_bytes_base64url": "e30"},
    }
    validator.validate(instance)


def test_jcs_case_schema_rejects_unknown_property() -> None:
    validator = _validator_for("jcs-case.schema.json")
    instance = {
        "case_schema_version": 1,
        "case_id": "jcs.object.ascii-key-order",
        "operation": "canonicalize-jcs",
        "input": {"json_utf8_base64url": "e30"},
        "expected": {"canonical_bytes_base64url": "e30"},
        "extra": True,
    }
    with pytest.raises(ValidationError):
        validator.validate(instance)


def test_vector_set_schema_accepts_shape() -> None:
    validator = _validator_for("vector-set.schema.json")
    zero = "sha256:" + ("0" * 64)
    instance = {
        "vector_set_schema_version": 1,
        "vector_set_id": "gateway-vnext.shared-kernel.canonical-encoding.v1",
        "owner": "shared-kernel",
        "contract_binding": {
            "contract_id": "gateway-vnext.shared-canonical-encoding",
            "semantic_version": "1.0.0",
        },
        "canonical_encoding_version": 1,
        "files": [
            {
                "path": "digest.jsonl",
                "media_type": "application/x-ndjson",
                "case_schema_id": "gateway-vnext.canonical-encoding.digest-case.v1",
                "case_count": 0,
                "size_bytes": 0,
                "raw_sha256": zero,
            },
            {
                "path": "invalid.jsonl",
                "media_type": "application/x-ndjson",
                "case_schema_id": "gateway-vnext.canonical-encoding.invalid-case.v1",
                "case_count": 0,
                "size_bytes": 0,
                "raw_sha256": zero,
            },
            {
                "path": "jcs.jsonl",
                "media_type": "application/x-ndjson",
                "case_schema_id": "gateway-vnext.canonical-encoding.jcs-case.v1",
                "case_count": 0,
                "size_bytes": 0,
                "raw_sha256": zero,
            },
            {
                "path": "scalar.jsonl",
                "media_type": "application/x-ndjson",
                "case_schema_id": "gateway-vnext.canonical-encoding.scalar-case.v1",
                "case_count": 0,
                "size_bytes": 0,
                "raw_sha256": zero,
            },
        ],
        "vector_set_content_digest": zero,
    }
    validator.validate(instance)


def test_invalid_case_schema_requires_expected_error() -> None:
    validator = _validator_for("invalid-case.schema.json")
    instance = {
        "case_schema_version": 1,
        "case_id": "invalid.jcs.duplicate-member",
        "operation": "canonicalize-jcs",
        "input": {"json_utf8_base64url": "e30"},
        "expected_error": {"code": "CANONICAL_JCS_DUPLICATE_MEMBER"},
    }
    validator.validate(instance)

    bad = {
        "case_schema_version": 1,
        "case_id": "invalid.jcs.duplicate-member",
        "operation": "canonicalize-jcs",
        "input": {"json_utf8_base64url": "e30"},
        "expected": {"canonical_bytes_base64url": "e30"},
    }
    with pytest.raises(ValidationError):
        validator.validate(bad)


def test_declared_type_decimal_requires_precision_and_scale() -> None:
    validator = _validator_for("scalar-case.schema.json")
    valid = {
        "case_schema_version": 1,
        "case_id": "scalar.decimal.zero",
        "operation": "encode-typed-scalar",
        "input": {
            "declared_type": {"kind": "decimal", "precision": 10, "scale": 2},
            "typed_value": {"kind": "decimal", "decimal": "0"},
        },
        "expected": {
            "payload_base64url": "MA",
            "scalar_frame_base64url": "EgEw",
        },
    }
    validator.validate(valid)

    invalid = {
        "case_schema_version": 1,
        "case_id": "scalar.decimal.missing-bounds",
        "operation": "encode-typed-scalar",
        "input": {
            "declared_type": {"kind": "decimal"},
            "typed_value": {"kind": "decimal", "decimal": "0"},
        },
        "expected": {
            "payload_base64url": "MA",
            "scalar_frame_base64url": "EgEw",
        },
    }
    with pytest.raises(ValidationError):
        validator.validate(invalid)


def test_base64url_schema_rejects_length_mod_4_eq_1() -> None:
    schema = {
        "$ref": "gateway-vnext.canonical-encoding.definitions.v1#/$defs/base64url"
    }
    registry = _build_registry()
    validator = Draft202012Validator(schema, registry=registry)
    validator.validate("e30")
    validator.validate("")
    validator.validate("AA")
    with pytest.raises(ValidationError):
        validator.validate("A")
    with pytest.raises(ValidationError):
        validator.validate("AAAAA")


def test_anomaly_envelope_schema_rejects_empty_object() -> None:
    schema = {
        "$ref": "gateway-vnext.canonical-encoding.definitions.v1#/$defs/anomalyEnvelope"
    }
    registry = _build_registry()
    validator = Draft202012Validator(schema, registry=registry)
    validator.validate(
        {
            "declared_type": {"kind": "date"},
            "raw_base64url": "YmFk",
            "raw_encoding": "utf8",
            "reason": "owner-reason",
        }
    )
    with pytest.raises(ValidationError):
        validator.validate({})
    with pytest.raises(ValidationError):
        validator.validate(
            {
                "declared_type": "date",
                "raw_base64url": "YmFk",
                "raw_encoding": "utf8",
                "reason": "owner-reason",
            }
        )
