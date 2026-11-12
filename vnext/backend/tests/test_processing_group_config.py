"""Pure processing-group wire/configuration boundary; no runtime or Dolt fixture."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from gateway_backend.device_identity import (
    device_create_key, device_initial_node_id, device_route_key, validate_scope_identity,
)
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.schemas.device_registration import DeviceRegistrationQuery, RegisterDeviceRequest
from gateway_backend.http.schemas.workspace import CreateWorkspaceRequest
from gateway_backend.processing_group_config import DeviceDirectory, ProcessingGroupsConfig

pytestmark = pytest.mark.unit
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures/processing-groups/v1"
VECTORS = json.loads((FIXTURES / "identity-vectors.json").read_bytes())
INVALID_IDENTITIES = [None, 1, True, "", "a" * 256, "\x00", "a\x00b", "\ud800", "\udfff"]


def _groups() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / "groups.json").read_bytes()))


def _directory() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / "device-directory.json").read_bytes()))


def _parse_directory(doc: dict[str, Any]) -> DeviceDirectory:
    return DeviceDirectory.from_bytes(json.dumps(doc).encode(), known_groups={"group-a", "group-b"})


@pytest.mark.parametrize("case", VECTORS)
def test_shared_identity_vectors(case: dict[str, str]) -> None:
    env, group, device = case["environment_id"], case["group_id"], case["gateway_device_external_key"]
    assert device_route_key(device) == case["route_key"]
    assert device_create_key(env, group, device) == case["create_key"]
    assert device_initial_node_id(env, group, device) == case["initial_node_id"]


@pytest.mark.parametrize("value", INVALID_IDENTITIES)
def test_identity_boundary_shared_by_directory_dto_and_session_context(value: Any) -> None:
    with pytest.raises(ValueError):
        validate_scope_identity(value)
    with pytest.raises(ValueError):
        CreateWorkspaceRequest(gateway_device_external_key=value, business_project_id="project")
    with pytest.raises(ValueError):
        IdentityContext("actor", value, "project", frozenset({"read"}))
    document = _directory()
    document["devices"][0]["gateway_device_external_key"] = value
    with pytest.raises(ValueError):
        _parse_directory(document)


@pytest.mark.parametrize("value", ["😀" * 255, "设备", "é", "e\u0301", " raw /device\\ ", "\uffff"])
def test_scope_uses_unicode_scalars_and_exact_bytes(value: str) -> None:
    assert validate_scope_identity(value) == value
    assert len(value.encode()) <= 1020
    assert CreateWorkspaceRequest(gateway_device_external_key=value, business_project_id=value).business_project_id == value


def test_typed_configuration_roundtrips_without_changing_per_group_deployment() -> None:
    config = ProcessingGroupsConfig.from_bytes((FIXTURES / "groups.json").read_bytes())
    directory = DeviceDirectory.from_bytes((FIXTURES / "device-directory.json").read_bytes(), known_groups=config.group_ids)
    config.require_directory(directory)
    assert ProcessingGroupsConfig.from_bytes(config.to_bytes()) == config
    assert DeviceDirectory.from_bytes(directory.to_bytes(), known_groups=config.group_ids) == directory
    assert config.groups[0].backend_endpoint == "http://127.0.0.1:8100"
    assert directory.require_reservation("设备一", "group-a").enabled is False
    # Global routing is deliberately absent from each group's deployment identity.
    assert "directory" not in config.groups[0].__dataclass_fields__


CONFIG_FAULTS = [
    (["schema_version"], True), (["environment_id"], "../bad"),
    (["host", "cpu_count"], True), (["host", "shared_cpu_reserve"], float("inf")),
    (["entry", "listen_address"], "127.0.0.1; include x"), (["entry", "listen_port"], 0),
    (["entry", "management_port"], 8080), (["entry", "image"], "nginx:latest"),
    (["groups", 0, "project"], "foo\nbar"), (["groups", 0, "backend_port"], True),
    (["groups", 0, "storage_config"], "/etc/../secret"),
    (["groups", 0, "session_directory"], "/etc/secret\n"),
    (["groups", 0, "images", "backend"], "https://other/image:1"),
    (["groups", 0, "images", "revision"], "main"),
    (["groups", 1, "group_id"], "group-a"), (["groups", 1, "project"], "gateway-group-a"),
    (["groups", 1, "backend_port"], 8100),
    (["groups", 1, "internal_token_file"], "/etc/gateway/group-a/internal.token"),
    (["groups"], []), (["groups"], [{}] * 33), (["unknown"], 1),
]


@pytest.mark.parametrize(("path", "value"), CONFIG_FAULTS)
def test_deployment_configuration_rejects_invalid_fields(path: list[Any], value: Any) -> None:
    doc = _groups()
    target = doc
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        ProcessingGroupsConfig.from_bytes(json.dumps(doc).encode())


@pytest.mark.parametrize("raw", [b'{}', b'[]', b'{"schema_version":1,"schema_version":1}', b'\xff', b' ' * (1024 * 1024 + 1)])
def test_groups_reject_invalid_document(raw: bytes) -> None:
    with pytest.raises(ValueError):
        ProcessingGroupsConfig.from_bytes(raw)


@pytest.mark.parametrize("fault", ["duplicate", "unknown-group", "bool", "extra", "too-many"])
def test_directory_reservations_are_strict_and_unique(fault: str) -> None:
    doc = _directory()
    if fault == "duplicate":
        doc["devices"].append({**doc["devices"][0], "enabled": True})
    elif fault == "unknown-group":
        doc["devices"][0]["group_id"] = "other"
    elif fault == "bool":
        doc["devices"][0]["enabled"] = 1
    elif fault == "extra":
        doc["devices"][0]["repository_id"] = "caller-chosen"
    else:
        doc["devices"] = [doc["devices"][0]] * 10001
    with pytest.raises(ValueError):
        _parse_directory(doc)


@pytest.mark.parametrize("fault", ["remove", "rebind-reserved", "disable", "environment"])
def test_append_does_not_release_or_rebind_existing_reservations(fault: str) -> None:
    old = _parse_directory(_directory())
    doc = _directory()
    if fault == "remove":
        doc["devices"].pop(0)
    elif fault == "rebind-reserved":
        doc["devices"][0]["group_id"] = "group-b"
    elif fault == "disable":
        doc["devices"][1]["enabled"] = False
    else:
        doc["environment_id"] = "other"
    with pytest.raises(ValueError):
        _parse_directory(doc).require_append_only(old)


def test_append_can_enable_reserved_and_add_new_devices() -> None:
    old = _parse_directory(_directory())
    doc = _directory()
    doc["devices"][0]["enabled"] = True
    doc["devices"].append(dict(gateway_device_external_key="new", group_id="group-b", enabled=False))
    _parse_directory(doc).require_append_only(old)


def test_registration_dto_has_exact_fields_and_bounded_query() -> None:
    request = dict(environment_id="test-env", group_id="group-a", gateway_device_external_key="设备一", business_project_id="project")
    assert RegisterDeviceRequest(**request).gateway_device_external_key == "设备一"
    with pytest.raises(ValueError):
        RegisterDeviceRequest.model_validate({**request, "repository_id": "caller-chosen"})
    with pytest.raises(ValueError):
        DeviceRegistrationQuery(device="x" * 256)


@pytest.mark.parametrize("raw", [b'[]', b'{"schema_version":1,"schema_version":1}', b'\xff', b' ' * (8 * 1024 * 1024 + 1)])
def test_directory_rejects_invalid_or_oversized_document(raw: bytes) -> None:
    with pytest.raises(ValueError):
        DeviceDirectory.from_bytes(raw, known_groups={"group-a"})


def test_registration_openapi_schema_defines_required_and_unknown_fields() -> None:
    schema = RegisterDeviceRequest.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"environment_id", "group_id", "gateway_device_external_key", "business_project_id"}
    assert schema["properties"]["gateway_device_external_key"]["maxLength"] == 255


@pytest.mark.parametrize("identity", ["设" * 86, "😀" * 255])
def test_manual_close_uses_scope_character_domain_without_widening_opaque_ids(identity: str) -> None:
    from gateway_backend.application.archive.contracts import compute_close_request_fingerprint
    from gateway_backend.application.archive.errors import ArchiveRequestValidation

    request: dict[str, Any] = dict(repository_id="repository", gateway_device_external_key=identity,
        business_project_id=identity, submission_id="submission", expected_review_version=0,
        expected_baseline_node_id="node", expected_baseline_head_version=0, reason="closed")
    assert compute_close_request_fingerprint(**request).startswith("sha256:")
    with pytest.raises(ArchiveRequestValidation):
        compute_close_request_fingerprint(**{**request, "repository_id": "库" * 86})
