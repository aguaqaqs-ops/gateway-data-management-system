"""JSON Schema Draft 2020-12 helpers for vector case envelopes."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from gateway_shared_kernel.testing.paths import (
    CASE_SCHEMA_FILE_BY_ID,
    SCHEMA_FILES,
    SCHEMA_ROOT,
)


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


def validator_for_case_schema_id(case_schema_id: str) -> Draft202012Validator:
    file_name = CASE_SCHEMA_FILE_BY_ID[case_schema_id]
    return validator_for_schema_file(file_name)


def validate_case_envelope(case_schema_id: str, case: dict[str, Any]) -> None:
    validator_for_case_schema_id(case_schema_id).validate(case)


def validate_vector_set_manifest(manifest: dict[str, Any]) -> None:
    validator_for_schema_file("vector-set.schema.json").validate(manifest)
