"""Offline JSON Schema registry for owner payload schemas."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from gateway_conformance.paths import OWNER_REGISTRY_ROOT, SCHEMA_ROOT


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def owner_schema_registry() -> Registry:
    resources: list[tuple[str, Resource[Any]]] = []
    definitions_path = (
        SCHEMA_ROOT / "shared-kernel" / "canonical-encoding" / "v1" / "definitions.schema.json"
    )
    definitions = _load_json(definitions_path)
    resources.append(
        (
            definitions["$id"],
            Resource.from_contents(definitions, default_specification=DRAFT202012),
        )
    )
    for path in sorted(OWNER_REGISTRY_ROOT.glob("*.schema.json")):
        document = _load_json(path)
        schema_id = document.get("$id")
        if not isinstance(schema_id, str) or not schema_id:
            continue
        resources.append(
            (
                schema_id,
                Resource.from_contents(document, default_specification=DRAFT202012),
            )
        )
    return Registry().with_resources(resources)


@lru_cache(maxsize=32)
def validator_for_owner_schema(schema_path: Path) -> Draft202012Validator:
    schema = _load_json(schema_path)
    return Draft202012Validator(schema, registry=owner_schema_registry())
