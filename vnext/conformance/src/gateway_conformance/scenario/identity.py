"""Scenario identity and path reversibility checks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from gateway_conformance.errors import ConformanceValidationError

_LOWER_KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def assert_lower_kebab(value: str, *, label: str) -> None:
    if not _LOWER_KEBAB.fullmatch(value):
        raise ConformanceValidationError(f"{label} must be lower-kebab-case")


def scenario_path_from_id(scenario_id: str) -> Path:
    parts = scenario_id.split(".")
    if len(parts) != 3:
        raise ConformanceValidationError("scenario_id must have exactly three segments")
    track, subject, scenario_name = parts
    assert_lower_kebab(subject, label="scenario_id subject")
    assert_lower_kebab(scenario_name, label="scenario_id name")
    return Path(track) / subject / scenario_name


def scenario_id_from_relative_path(relative_path: Path) -> str:
    parts = relative_path.parts
    if len(parts) != 3:
        raise ConformanceValidationError("scenario path must contain track, subject, and name")
    track, subject, scenario_name = parts[0], parts[1], parts[2]
    return f"{track}.{subject}.{scenario_name}"


def assert_id_path_reversible(manifest: dict[str, Any], scenario_root: Path) -> None:
    scenario_id = str(manifest["scenario_id"])
    track = str(manifest["track"])
    subject = manifest["subject"]
    subject_name = str(subject["name"])
    assert_lower_kebab(subject_name, label="subject.name")

    id_parts = scenario_id.split(".")
    if len(id_parts) != 3:
        raise ConformanceValidationError("scenario_id must have exactly three segments")
    if id_parts[0] != track:
        raise ConformanceValidationError("scenario_id track does not match track field")
    if id_parts[1] != subject_name:
        raise ConformanceValidationError("scenario_id subject does not match subject.name")

    expected_relative = scenario_path_from_id(scenario_id)
    actual_relative = Path(scenario_root.parts[-3]) / scenario_root.parts[-2] / scenario_root.name
    if expected_relative != actual_relative:
        raise ConformanceValidationError(
            "scenario_id does not map reversibly to scenario directory path"
        )
    reconstructed = scenario_id_from_relative_path(actual_relative)
    if reconstructed != scenario_id:
        raise ConformanceValidationError("scenario_id is not reversibly derived from path")


def assert_sorted_unique_bytes(items: list[str], *, label: str) -> None:
    if items != sorted(items, key=lambda item: item.encode("utf-8")):
        raise ConformanceValidationError(f"{label} must be sorted by UTF-8 bytes")
    if len(items) != len(set(items)):
        raise ConformanceValidationError(f"{label} contains duplicates")


def _semantic_binding_tuple(item: dict[str, Any]) -> tuple[str, str, str, str | None]:
    return (
        str(item["owner"]),
        str(item["contract_id"]),
        str(item["semantic_version"]),
        None if item.get("wire_schema_version") is None else str(item["wire_schema_version"]),
    )


def assert_manifest_ordering(manifest: dict[str, Any]) -> None:
    bindings = manifest["contract_bindings"]
    binding_ids = [str(item["binding_id"]) for item in bindings]
    assert_sorted_unique_bytes(binding_ids, label="contract_bindings")
    seen_semantics: set[tuple[str, str, str, str | None]] = set()
    for item in bindings:
        assert_lower_kebab(str(item["binding_id"]), label="contract_binding.binding_id")
        assert_lower_kebab(str(item["owner"]), label="contract_binding.owner")
        semantic = _semantic_binding_tuple(item)
        if semantic in seen_semantics:
            raise ConformanceValidationError(
                "contract_bindings contains duplicate semantic binding tuple"
            )
        seen_semantics.add(semantic)

    assets = manifest["input_assets"]
    logical_names = [str(item["logical_name"]) for item in assets]
    assert_sorted_unique_bytes(logical_names, label="input_assets")
    for item in assets:
        assert_lower_kebab(str(item["logical_name"]), label="input_asset.logical_name")

    expected = manifest["expected"]
    expectation_ids = [str(item["expectation_id"]) for item in expected]
    assert_sorted_unique_bytes(expectation_ids, label="expected")
    for item in expected:
        assert_lower_kebab(str(item["expectation_id"]), label="expected.expectation_id")

    profiles = [str(item) for item in manifest["required_profiles"]]
    assert_sorted_unique_bytes(profiles, label="required_profiles")


def assert_binding_references(manifest: dict[str, Any]) -> None:
    binding_ids = {str(item["binding_id"]) for item in manifest["contract_bindings"]}
    stimulus_binding = str(manifest["stimulus"]["contract_binding_id"])
    if stimulus_binding not in binding_ids:
        raise ConformanceValidationError("stimulus references unknown contract_binding_id")

    declared_input_names = {str(item["logical_name"]) for item in manifest["input_assets"]}
    stimulus_payload = manifest["stimulus"]["payload"]
    if stimulus_payload.get("storage") == "asset-ref":
        ref_name = str(stimulus_payload["logical_name"])
        if ref_name not in declared_input_names:
            raise ConformanceValidationError(
                "stimulus asset-ref logical_name is not declared in input_assets"
            )

    for asset in manifest["input_assets"]:
        content_binding = asset.get("content_binding")
        content_digest = asset.get("content_digest")
        if content_binding is not None and content_digest is None:
            raise ConformanceValidationError(
                "content_digest required when content_binding is present"
            )
        if content_binding is None and content_digest is not None:
            raise ConformanceValidationError(
                "content_binding required when content_digest is present"
            )
        if content_binding is not None:
            ref = str(content_binding["contract_binding_id"])
            if ref not in binding_ids:
                raise ConformanceValidationError(
                    "input asset references unknown contract_binding_id"
                )

    track = str(manifest["track"])
    has_fault = "fault" in manifest
    has_recovery = "recovery_trigger" in manifest
    if track == "recovery":
        if not has_fault or not has_recovery:
            raise ConformanceValidationError("recovery track requires fault and recovery_trigger")
        fault_binding = str(manifest["fault"]["contract_binding_id"])
        recovery_binding = str(manifest["recovery_trigger"]["contract_binding_id"])
        if fault_binding not in binding_ids:
            raise ConformanceValidationError("fault references unknown contract_binding_id")
        if recovery_binding not in binding_ids:
            raise ConformanceValidationError(
                "recovery_trigger references unknown contract_binding_id"
            )
    else:
        if has_fault or has_recovery:
            raise ConformanceValidationError(f"{track} track forbids fault and recovery_trigger")

    for entry in manifest["expected"]:
        owner_binding = entry["contract_binding"]
        matches = [
            item
            for item in manifest["contract_bindings"]
            if item["owner"] == owner_binding["owner"]
            and item["contract_id"] == owner_binding["contract_id"]
            and item["semantic_version"] == owner_binding["semantic_version"]
            and item.get("wire_schema_version") == owner_binding.get("wire_schema_version")
        ]
        if not matches:
            raise ConformanceValidationError(
                "expected contract_binding must match a declared contract_bindings entry"
            )
        if len(matches) != 1:
            raise ConformanceValidationError(
                "expected contract_binding must match exactly one contract_bindings entry"
            )
