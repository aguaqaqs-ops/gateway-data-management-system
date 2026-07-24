"""Owner contract registry for R1 test owners."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.paths import OWNER_REGISTRY_ROOT

_REGISTRY_FILE = OWNER_REGISTRY_ROOT / "registry.json"


@dataclass(frozen=True, slots=True)
class OwnerSchemaContract:
    owner: str
    contract_id: str
    semantic_version: str
    schema_id: str
    schema_version: int
    schema_file: str
    digest_kind: str


def _contract_key(contract_id: str, semantic_version: str) -> str:
    return f"{contract_id}@{semantic_version}"


def _schema_key(schema_id: str, schema_version: int) -> str:
    return f"{schema_id}@{schema_version}"


@lru_cache(maxsize=1)
def _load_registry() -> dict[str, Any]:
    loaded: object = json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ConformanceValidationError("owner registry must be an object")
    return loaded


def resolve_owner_schema(
    *,
    owner: str,
    contract_id: str,
    semantic_version: str,
    schema_id: str,
    schema_version: int,
) -> OwnerSchemaContract:
    registry = _load_registry()
    owner_entry = registry.get("owners", {}).get(owner)
    if owner_entry is None:
        raise ConformanceValidationError(f"unknown semantic owner: {owner}")
    contracts = owner_entry.get("contracts", {})
    contract = contracts.get(_contract_key(contract_id, semantic_version))
    if contract is None:
        raise ConformanceValidationError(
            f"unknown owner contract: {owner}/{contract_id}@{semantic_version}"
        )
    schema = contract.get("schemas", {}).get(_schema_key(schema_id, schema_version))
    if schema is None:
        raise ConformanceValidationError(f"unknown owner schema: {schema_id}@{schema_version}")
    return OwnerSchemaContract(
        owner=owner,
        contract_id=contract_id,
        semantic_version=semantic_version,
        schema_id=schema_id,
        schema_version=schema_version,
        schema_file=str(schema["schema_file"]),
        digest_kind=str(schema["digest_kind"]),
    )


def schema_path_for(contract: OwnerSchemaContract) -> Path:
    return OWNER_REGISTRY_ROOT / contract.schema_file
