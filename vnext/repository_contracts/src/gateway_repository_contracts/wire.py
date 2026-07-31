"""Repository service wire contract metadata and schema loading."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from gateway_repository_contracts._json import (
    CONTROL_JSON_MAX_BYTES,
    JSONValue,
    encode_jcs_bytes,
    parse_control_json,
)
from gateway_repository_contracts.errors import RepositoryContractError, RepositoryContractErrorCode

CONTRACT_ID = "gateway-vnext.repository-service"
SEMANTIC_VERSION = "1.0.0"
WIRE_VERSION = 1

_SCHEMA_ALLOWLIST: frozenset[str] = frozenset(
    {
        "identities-v1.schema.json",
        "problem-v1.schema.json",
        "stream-metadata-v1.schema.json",
        "stream-envelope-v1.schema.json",
        "stream-framing-v1.schema.json",
    }
)


def load_schema_resource(name: str) -> dict[str, Any]:
    """Load a packaged schema resource from the fixed allowlist."""
    if name not in _SCHEMA_ALLOWLIST:
        raise RepositoryContractError(
            RepositoryContractErrorCode.SCHEMA_RESOURCE_FORBIDDEN,
            "schema resource forbidden",
        )
    package = resources.files("gateway_repository_contracts").joinpath("schemas", name)
    if not package.is_file():
        raise RepositoryContractError(
            RepositoryContractErrorCode.SCHEMA_NOT_FOUND,
            "schema resource not found",
        )
    loaded = json.loads(package.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise RepositoryContractError(
            RepositoryContractErrorCode.SCHEMA_NOT_FOUND,
            "schema resource must be object",
        )
    return loaded


def schema_resource_names() -> tuple[str, ...]:
    return tuple(sorted(_SCHEMA_ALLOWLIST))


def require_wire_schema_version(value: object) -> int:
    if value is None:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_SCHEMA_VERSION_MISSING,
            "wire_schema_version is required",
        )
    if type(value) is not int or isinstance(value, bool):
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_BOOL_AS_INT
            if isinstance(value, bool)
            else RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            "wire_schema_version must be integer",
        )
    if value != WIRE_VERSION:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_SCHEMA_VERSION_MISMATCH,
            "wire_schema_version mismatch",
        )
    return value


def require_wire_version(value: object) -> int:
    if value is None:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_SCHEMA_VERSION_MISSING,
            "wire_version is required",
        )
    if type(value) is not int or isinstance(value, bool):
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_BOOL_AS_INT
            if isinstance(value, bool)
            else RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            "wire_version must be integer",
        )
    if value != WIRE_VERSION:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_SCHEMA_VERSION_MISMATCH,
            "wire_version mismatch",
        )
    return value


def encode_wire_object(payload: dict[str, JSONValue]) -> bytes:
    return encode_jcs_bytes(payload)


def parse_wire_object(
    payload: bytes, *, max_bytes: int = CONTROL_JSON_MAX_BYTES
) -> dict[str, JSONValue]:
    return parse_control_json(payload, max_bytes=max_bytes)


def schema_files_in_source_tree(root: Path) -> dict[str, Path]:
    schema_dir = root / "src" / "gateway_repository_contracts" / "schemas"
    return {name: schema_dir / name for name in sorted(_SCHEMA_ALLOWLIST)}
