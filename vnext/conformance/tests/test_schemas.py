"""JSON Schema metaschema and offline ref tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from gateway_conformance.paths import SCHEMA_FILES, SCHEMA_ROOT
from gateway_conformance.schemas import (
    validate_golden_envelope,
    validate_harness_protocol,
    validate_runner_result,
    validate_run_evidence,
    validate_scenario_manifest,
)


def _load_json(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return loaded


def _build_registry() -> Registry:
    resources: list[tuple[str, Resource[object]]] = []
    for name in SCHEMA_FILES:
        document = _load_json(SCHEMA_ROOT / name)
        schema_id = cast(str, document["$id"])
        resources.append(
            (
                schema_id,
                Resource.from_contents(document, default_specification=DRAFT202012),
            )
        )
    return Registry().with_resources(resources)


@pytest.mark.parametrize("schema_name", SCHEMA_FILES)
def test_schema_is_valid_draft_2020_12(schema_name: str) -> None:
    schema = _load_json(SCHEMA_ROOT / schema_name)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert isinstance(schema["$id"], str) and schema["$id"]
    Draft202012Validator.check_schema(schema)


def test_schema_refs_resolve_offline() -> None:
    registry = _build_registry()
    for name in SCHEMA_FILES:
        schema = _load_json(SCHEMA_ROOT / name)
        Draft202012Validator(schema, registry=registry)


def test_schema_files_have_no_remote_ref() -> None:
    for name in SCHEMA_FILES:
        text = (SCHEMA_ROOT / name).read_text(encoding="utf-8")
        assert "https://json-schema.org" in text
        assert "http://" not in text.replace("https://json-schema.org", "")


def test_scenario_manifest_rejects_unknown_field() -> None:
    manifest = {
        "manifest_schema_version": 1,
        "scenario_id": "data.test-capability.minimal",
        "track": "data",
        "subject": {"kind": "capability", "name": "test-capability"},
        "description": "x",
        "provenance": {"kind": "HANDCRAFTED"},
        "contract_bindings": [
            {
                "binding_id": "subject",
                "owner": "test-capability",
                "contract_id": "gateway-vnext.test-contract",
                "semantic_version": "1.0.0",
            }
        ],
        "canonical_encoding_version": 1,
        "input_assets": [],
        "stimulus": {
            "contract_binding_id": "subject",
            "payload": {"storage": "inline", "value": {}},
        },
        "input_digest": "sha256:" + "0" * 64,
        "fixture_content_digest": "sha256:" + "0" * 64,
        "expected": [
            {
                "expectation_id": "result",
                "kind": "structured",
                "path": "expected/result.golden.json",
                "size_bytes": 1,
                "raw_sha256": "sha256:" + "0" * 64,
                "contract_binding": {
                    "owner": "test-capability",
                    "contract_id": "gateway-vnext.test-contract",
                    "semantic_version": "1.0.0",
                },
                "content_digest": "sha256:" + "0" * 64,
            }
        ],
        "required_profiles": ["reference"],
        "legacy_classification": "NOT_APPLICABLE",
        "extra": True,
    }
    with pytest.raises(ValidationError):
        validate_scenario_manifest(manifest)


def test_runner_result_rejects_invalid_status_union() -> None:
    result = {
        "runner_result_schema_version": 1,
        "execution_key": {
            "scenario_id": "data.test-capability.minimal",
            "profile": "reference",
            "provider_id": None,
            "fixture_content_digest": "sha256:" + "0" * 64,
        },
        "run_id": "run-1",
        "contract_bindings": [
            {
                "binding_id": "subject",
                "owner": "test-capability",
                "contract_id": "gateway-vnext.test-contract",
                "semantic_version": "1.0.0",
            }
        ],
        "status": "MAYBE",
        "comparison_outcome": "NOT_RUN",
        "expectations": [
            {
                "expectation_id": "result",
                "expected_content_digest": "sha256:" + "0" * 64,
                "actual_content_digest": None,
                "outcome": "NOT_RUN",
            }
        ],
        "evidence_ref": None,
        "cleanup": {"status": "CLEAN", "diagnostics": []},
        "diagnostics": [],
    }
    with pytest.raises(ValidationError):
        validate_runner_result(result)


def test_harness_protocol_and_evidence_validate_minimal_shapes() -> None:
    plan = {
        "harness_protocol_version": 1,
        "execution_key": {
            "scenario_id": "data.test-capability.minimal",
            "profile": "reference",
            "provider_id": None,
            "fixture_content_digest": "sha256:" + "0" * 64,
        },
        "run_id": "run-1",
        "subject": {"kind": "capability", "name": "test-capability"},
        "contract_bindings": [
            {
                "binding_id": "subject",
                "owner": "test-capability",
                "contract_id": "gateway-vnext.test-contract",
                "semantic_version": "1.0.0",
            }
        ],
        "logical_time_start": "2026-01-01T00:00:00Z",
        "deterministic_seed": "seed",
        "verified_assets": [],
        "stimulus": {
            "contract_binding_id": "subject",
            "payload": {"storage": "inline", "value": {}},
        },
        "observation_requests": [
            {
                "expectation_id": "result",
                "kind": "structured",
                "contract_binding": {
                    "owner": "test-capability",
                    "contract_id": "gateway-vnext.test-contract",
                    "semantic_version": "1.0.0",
                },
                "payload_descriptor": {
                    "media_type": "application/json",
                    "schema_id": "gateway-vnext.test-result.v1",
                    "schema_version": 1,
                    "canonical_encoding_version": 1,
                    "comparison_mode": "exact-canonical",
                },
            }
        ],
    }
    validate_harness_protocol(plan)
    evidence = {
        "run_evidence_schema_version": 1,
        "execution_key": plan["execution_key"],
        "run_id": "run-1",
        "environment_versions": [{"component": "gateway-conformance", "version": "0.1.0"}],
        "fault_receipt": None,
        "observations": [],
        "checkpoint_results": [],
        "cleanup": {"status": "CLEAN", "diagnostics": []},
        "diagnostics": [],
        "content_digest": "sha256:" + "0" * 64,
    }
    validate_run_evidence(evidence)
    observation_requests = cast(list[dict[str, Any]], plan["observation_requests"])
    validate_golden_envelope(
        {
            "golden_envelope_schema_version": 1,
            "expectation_id": "result",
            "kind": "structured",
            "contract_binding": observation_requests[0]["contract_binding"],
            "payload_descriptor": {
                "media_type": "application/json",
                "schema_id": "gateway-vnext.test-result.v1",
                "schema_version": 1,
                "canonical_encoding_version": 1,
                "comparison_mode": "exact-canonical",
            },
            "content_digest": "sha256:" + "0" * 64,
            "payload": {"storage": "inline", "value": {}},
        }
    )
