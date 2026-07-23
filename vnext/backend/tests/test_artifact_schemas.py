"""JSON Schema authority and runtime-validator alignment tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from gateway_backend.artifacts import (
    artifact_manifest_from_dict,
    artifact_ref_from_dict,
)
from gateway_backend.canonical_row_hash_artifact import (
    CanonicalRowHashesArtifactManifest,
)

SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "schemas" / "artifacts" / "v1"
VECTOR_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "vectors" / "artifacts" / "v1"
SCHEMA_FILES = (
    "definitions.schema.json",
    "artifact-ref.schema.json",
    "canonical-row-hashes-artifact.schema.json",
    "artifact-manifest.schema.json",
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def schema_registry() -> Registry:
    resources: list[tuple[str, Resource[Any]]] = []
    for name in SCHEMA_FILES:
        document = load_json(SCHEMA_ROOT / name)
        resources.append(
            (
                document["$id"],
                Resource.from_contents(document, default_specification=DRAFT202012),
            )
        )
    return Registry().with_resources(resources)


def validator(schema_name: str) -> Draft202012Validator:
    return Draft202012Validator(load_json(SCHEMA_ROOT / schema_name), registry=schema_registry())


@pytest.mark.parametrize("schema_name", SCHEMA_FILES)
def test_schema_meta_validation(schema_name: str) -> None:
    Draft202012Validator.check_schema(load_json(SCHEMA_ROOT / schema_name))


@pytest.mark.parametrize(
    ("fixture_name", "schema_name"),
    [
        ("canonical-row-hashes-ref.json", "artifact-ref.schema.json"),
        ("canonical-row-hashes-manifest.json", "artifact-manifest.schema.json"),
    ],
)
def test_valid_fixtures_pass_schema_and_runtime(fixture_name: str, schema_name: str) -> None:
    payload = load_json(VECTOR_ROOT / "valid" / fixture_name)
    validator(schema_name).validate(payload)
    if schema_name == "artifact-ref.schema.json":
        artifact_ref_from_dict(payload)
    else:
        artifact_manifest_from_dict(
            payload,
            content_parser=CanonicalRowHashesArtifactManifest.from_wire_dict,
        )


@pytest.mark.parametrize(
    ("fixture_name", "schema_name"),
    [
        ("ref-with-host-path.json", "artifact-ref.schema.json"),
        ("ref-missing-raw-sha256.json", "artifact-ref.schema.json"),
        ("manifest-wrong-version.json", "artifact-manifest.schema.json"),
    ],
)
def test_structurally_invalid_fixtures_fail_schema_and_runtime(
    fixture_name: str, schema_name: str
) -> None:
    payload = load_json(VECTOR_ROOT / "invalid" / fixture_name)
    with pytest.raises(ValidationError):
        validator(schema_name).validate(payload)
    with pytest.raises(ValueError):
        if schema_name == "artifact-ref.schema.json":
            artifact_ref_from_dict(payload)
        else:
            artifact_manifest_from_dict(
                payload,
                content_parser=CanonicalRowHashesArtifactManifest.from_wire_dict,
            )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("artifact_ref_schema_version", 2),
        ("size_bytes", 2**53),
        ("retention_class", "unknown"),
        ("media_type", "application/octet-stream"),
        ("content_schema_id", "gateway-vnext.unknown.v1"),
    ],
)
def test_ref_schema_and_runtime_reject_same_closed_mutations(field: str, value: object) -> None:
    payload = load_json(VECTOR_ROOT / "valid" / "canonical-row-hashes-ref.json")
    mutated = copy.deepcopy(payload)
    mutated[field] = value
    with pytest.raises(ValidationError):
        validator("artifact-ref.schema.json").validate(mutated)
    with pytest.raises(ValueError):
        artifact_ref_from_dict(mutated)


@pytest.mark.parametrize(
    "logical_ref",
    [
        "gateway-vnext.artifacts/v1/ref/" + ("a" * 64) + "/item",
        "gateway-vnext.artifacts/v1/ref/namespace/" + ("a" * 129),
    ],
)
def test_ref_schema_and_runtime_reject_oversized_logical_segments(
    logical_ref: str,
) -> None:
    payload = load_json(VECTOR_ROOT / "valid" / "canonical-row-hashes-ref.json")
    payload["logical_ref"] = logical_ref
    with pytest.raises(ValidationError):
        validator("artifact-ref.schema.json").validate(payload)
    with pytest.raises(ValueError, match="length limit"):
        artifact_ref_from_dict(payload)


def test_all_public_object_schemas_close_unknown_fields() -> None:
    for schema_name in SCHEMA_FILES:
        document = load_json(SCHEMA_ROOT / schema_name)
        stack = [document]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if node.get("type") == "object" and "properties" in node:
                    assert node.get("additionalProperties") is False, (
                        schema_name,
                        node,
                    )
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
