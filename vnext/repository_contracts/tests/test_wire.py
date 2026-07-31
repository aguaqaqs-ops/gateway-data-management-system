"""Wire codec and schema loader tests."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from collections.abc import Mapping

from gateway_repository_contracts._json import (
    CONTROL_JSON_MAX_BYTES,
    JSONValue,
    parse_control_json,
    parse_json_document,
)
from gateway_repository_contracts.enums import FAILURE_CATEGORIES
from gateway_repository_contracts.errors import RepositoryContractError, RepositoryContractErrorCode
from gateway_repository_contracts.wire import (
    CONTRACT_ID,
    SEMANTIC_VERSION,
    WIRE_VERSION,
    encode_wire_object,
    load_schema_resource,
    parse_wire_object,
    require_wire_schema_version,
    schema_resource_names,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _schema_registry() -> Registry:
    resources_list: list[tuple[str, Resource[Any]]] = []
    for name in schema_resource_names():
        document = load_schema_resource(name)
        resources_list.append(
            (
                document["$id"],
                Resource.from_contents(document, default_specification=DRAFT202012),
            )
        )
    return Registry().with_resources(resources_list)


@pytest.mark.parametrize("name", schema_resource_names())
def test_schema_check_schema_passes(name: str) -> None:
    schema = load_schema_resource(name)
    Draft202012Validator.check_schema(schema)


def test_schema_refs_resolve_offline() -> None:
    registry = _schema_registry()
    for name in schema_resource_names():
        schema = load_schema_resource(name)
        Draft202012Validator(schema, registry=registry)


def test_schema_files_have_no_remote_ref() -> None:
    for name in schema_resource_names():
        text = (
            resources.files("gateway_repository_contracts")
            .joinpath("schemas", name)
            .read_text(encoding="utf-8")
        )
        assert "https://json-schema.org" in text
        assert "http://" not in text.replace("https://json-schema.org", "")


def test_load_schema_resource_rejects_non_allowlisted_name() -> None:
    with pytest.raises(RepositoryContractError) as exc:
        load_schema_resource("../secrets.json")
    assert exc.value.code is RepositoryContractErrorCode.SCHEMA_RESOURCE_FORBIDDEN


def test_wire_metadata_constants() -> None:
    assert CONTRACT_ID == "gateway-vnext.repository-service"
    assert SEMANTIC_VERSION == "1.0.0"
    assert WIRE_VERSION == 1


def test_wire_round_trip_is_deterministic() -> None:
    payload: Mapping[str, JSONValue] = {"wire_schema_version": 1, "alpha": 1, "zeta": True}
    first = encode_wire_object(dict(payload))
    second = encode_wire_object(parse_wire_object(first))
    assert first == second
    assert first == b'{"alpha":1,"wire_schema_version":1,"zeta":true}'


def test_parse_rejects_invalid_utf8() -> None:
    with pytest.raises(RepositoryContractError) as exc:
        parse_wire_object(b"\xff\xfe")
    assert exc.value.code is RepositoryContractErrorCode.WIRE_INVALID_UTF8


def test_parse_rejects_duplicate_member() -> None:
    with pytest.raises(RepositoryContractError) as exc:
        parse_wire_object(b'{"a":1,"a":2}')
    assert exc.value.code is RepositoryContractErrorCode.WIRE_DUPLICATE_MEMBER


def test_parse_rejects_trailing_document() -> None:
    with pytest.raises(RepositoryContractError) as exc:
        parse_wire_object(b'{"a":1}{}')
    assert exc.value.code is RepositoryContractErrorCode.WIRE_TRAILING_DATA


def test_parse_rejects_non_object_root() -> None:
    with pytest.raises(RepositoryContractError) as exc:
        parse_wire_object(b"[]")
    assert exc.value.code is RepositoryContractErrorCode.WIRE_NON_OBJECT_ROOT


def test_require_wire_schema_version_rejects_bool() -> None:
    with pytest.raises(RepositoryContractError) as exc:
        require_wire_schema_version(True)
    assert exc.value.code is RepositoryContractErrorCode.WIRE_BOOL_AS_INT


def test_parse_rejects_payload_over_limit() -> None:
    oversized = b" " * (CONTROL_JSON_MAX_BYTES + 1)
    with pytest.raises(RepositoryContractError) as exc:
        parse_wire_object(oversized)
    assert exc.value.code is RepositoryContractErrorCode.WIRE_PAYLOAD_TOO_LARGE


def test_python_enum_values_match_problem_schema() -> None:
    schema = load_schema_resource("problem-v1.schema.json")
    categories = schema["$defs"]["failureCategory"]["enum"]
    assert set(categories) == {item.value for item in FAILURE_CATEGORIES}


def test_nested_closed_object_scan_for_schemas() -> None:
    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "additionalProperties" in node:
                assert node["additionalProperties"] is False
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for name in schema_resource_names():
        walk(load_schema_resource(name))


def test_installed_package_resource_read() -> None:
    for name in schema_resource_names():
        raw = resources.files("gateway_repository_contracts").joinpath("schemas", name).read_bytes()
        assert json.loads(raw.decode("utf-8"))["$id"]


def test_parse_rejects_lone_surrogate() -> None:
    with pytest.raises(RepositoryContractError) as exc:
        parse_json_document('{"a":"\\ud800"}'.encode("utf-8"))
    assert exc.value.code is RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE


def test_parse_rejects_noncharacter() -> None:
    with pytest.raises(RepositoryContractError) as exc:
        parse_json_document('{"a":"\\uFFFF"}'.encode("utf-8"))
    assert exc.value.code is RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE


def test_parse_rejects_excessive_nesting() -> None:
    depth = 70
    payload = b"[" * depth + b"]" * depth
    with pytest.raises(RepositoryContractError) as exc:
        parse_json_document(payload)
    assert exc.value.code is RepositoryContractErrorCode.JSON_NESTING_TOO_DEEP


def test_parse_rejects_nan() -> None:
    with pytest.raises(RepositoryContractError) as exc:
        parse_json_document(b"NaN")
    assert exc.value.code in {
        RepositoryContractErrorCode.JSON_INCOMPATIBLE_VALUE,
        RepositoryContractErrorCode.WIRE_JSON_SYNTAX_INVALID,
    }


def test_parse_control_json_rejects_nested_duplicate_members() -> None:
    with pytest.raises(RepositoryContractError) as exc:
        parse_control_json(b'{"outer":{"a":1,"a":2}}')
    assert exc.value.code is RepositoryContractErrorCode.WIRE_DUPLICATE_MEMBER
