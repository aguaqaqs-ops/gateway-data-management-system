"""JSON Schema Draft 2020-12 helpers for fixture oracle schemas."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from gateway_conformance.paths import SCHEMA_FILES, SCHEMA_ROOT
from gateway_conformance.errors import ConformanceValidationError


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def schema_registry() -> Registry:
    resources: list[tuple[str, Resource[Any]]] = []
    for name in SCHEMA_FILES:
        document = _load_json(SCHEMA_ROOT / name)
        resources.append(
            (
                document["$id"],
                Resource.from_contents(document, default_specification=DRAFT202012),
            )
        )
    return Registry().with_resources(resources)


@lru_cache(maxsize=8)
def validator_for_schema_file(schema_name: str) -> Draft202012Validator:
    schema = _load_json(SCHEMA_ROOT / schema_name)
    return Draft202012Validator(schema, registry=schema_registry())


def validate_scenario_manifest(manifest: dict[str, Any]) -> None:
    version = manifest.get("manifest_schema_version")
    if version == 1:
        validator_for_schema_file("scenario-manifest-v1.schema.json").validate(manifest)
        return
    if version == 2:
        validator_for_schema_file("scenario-manifest-v2.schema.json").validate(manifest)
        return
    raise ConformanceValidationError(
        f"unsupported manifest_schema_version for scenario manifest: {version!r}"
    )


def validate_golden_envelope(envelope: dict[str, Any]) -> None:
    validator_for_schema_file("golden-envelope-v1.schema.json").validate(envelope)


def validate_harness_protocol(plan: dict[str, Any]) -> None:
    validator_for_schema_file("harness-protocol-v1.schema.json").validate(plan)


def validate_runner_result(result: dict[str, Any]) -> None:
    validator_for_schema_file("runner-result-v1.schema.json").validate(result)


def validate_run_evidence(evidence: dict[str, Any]) -> None:
    validator_for_schema_file("run-evidence-v1.schema.json").validate(evidence)


def validate_or_raise(validator_name: str, instance: dict[str, Any]) -> None:
    mapping = {
        "scenario-manifest": validate_scenario_manifest,
        "golden-envelope": validate_golden_envelope,
        "harness-protocol": validate_harness_protocol,
        "runner-result": validate_runner_result,
        "run-evidence": validate_run_evidence,
    }
    try:
        mapping[validator_name](instance)
    except ValidationError as exc:
        raise ValidationError(exc.message) from exc
