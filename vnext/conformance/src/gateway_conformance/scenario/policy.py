"""Governance policy validation for provenance and fault contracts."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.paths import GOVERNANCE_ROOT

_OPAQUE_REFERENCE = re.compile(r"^[a-z0-9]+(?:[-.:][a-z0-9]+)*$")
_OPAQUE_COLON_PREFIXES = frozenset({"approval", "review-ticket"})
_OPAQUE_REST = re.compile(r"^[a-z0-9]+(?:[-.][a-z0-9]+)*$")
_FORBIDDEN_LOCATOR_SCHEME = re.compile(
    r"^(?:https?|file|ftp|javascript|data|blob|mailto|about|vbscript|"
    r"wss?|ssh|jar|chrome|view-source):",
    re.IGNORECASE,
)
_WINDOWS_DRIVE = re.compile(r"^[a-zA-Z]:(?:$|[^a-z0-9])")


@lru_cache(maxsize=1)
def _sanitization_policies() -> dict[str, Any]:
    loaded: object = json.loads(
        (GOVERNANCE_ROOT / "sanitization-policies.json").read_text(encoding="utf-8")
    )
    if not isinstance(loaded, dict):
        raise ConformanceValidationError("sanitization policies must be an object")
    return loaded


@lru_cache(maxsize=1)
def _approval_authorities() -> dict[str, Any]:
    loaded: object = json.loads(
        (GOVERNANCE_ROOT / "approval-authorities.json").read_text(encoding="utf-8")
    )
    if not isinstance(loaded, dict):
        raise ConformanceValidationError("approval authorities must be an object")
    return loaded


@lru_cache(maxsize=1)
def _fault_legality() -> dict[str, Any]:
    loaded: object = json.loads(
        (GOVERNANCE_ROOT / "fault-legality.json").read_text(encoding="utf-8")
    )
    if not isinstance(loaded, dict):
        raise ConformanceValidationError("fault legality must be an object")
    return loaded


@lru_cache(maxsize=1)
def _recovery_legality() -> dict[str, Any]:
    loaded: object = json.loads(
        (GOVERNANCE_ROOT / "recovery-legality.json").read_text(encoding="utf-8")
    )
    if not isinstance(loaded, dict):
        raise ConformanceValidationError("recovery legality must be an object")
    return loaded


def _assert_opaque_reference(value: str, *, label: str) -> None:
    if not value or value != value.strip():
        raise ConformanceValidationError(f"{label} must be a non-empty opaque reference")
    if _OPAQUE_REFERENCE.fullmatch(value) is None:
        raise ConformanceValidationError(
            f"{label} must be an opaque reference (lower-kebab/colon token)"
        )
    if ":" in value:
        prefix, rest = value.split(":", 1)
        if prefix not in _OPAQUE_COLON_PREFIXES or _OPAQUE_REST.fullmatch(rest) is None:
            raise ConformanceValidationError(f"{label} must not be a resolvable locator")
    if _FORBIDDEN_LOCATOR_SCHEME.search(value) is not None or _WINDOWS_DRIVE.match(value):
        raise ConformanceValidationError(f"{label} must not be a resolvable locator")


def _binding_by_id(manifest: dict[str, Any], binding_id: str, *, label: str) -> dict[str, Any]:
    binding = next(
        (item for item in manifest["contract_bindings"] if str(item["binding_id"]) == binding_id),
        None,
    )
    if not isinstance(binding, dict):
        raise ConformanceValidationError(f"{label} references unknown contract_binding_id")
    return binding


def _contract_entry(
    legality: dict[str, Any],
    binding: dict[str, Any],
    *,
    unknown_owner: str,
    unknown_contract: str,
) -> dict[str, Any]:
    owner = str(binding["owner"])
    contract_id = str(binding["contract_id"])
    semantic_version = str(binding["semantic_version"])
    owner_entry = legality.get("owners", {}).get(owner)
    if not isinstance(owner_entry, dict):
        raise ConformanceValidationError(unknown_owner)
    contract_key = f"{contract_id}@{semantic_version}"
    contracts = owner_entry.get("contracts", {})
    if not isinstance(contracts, dict):
        raise ConformanceValidationError(unknown_contract)
    contract_entry = contracts.get(contract_key)
    if not isinstance(contract_entry, dict):
        raise ConformanceValidationError(unknown_contract)
    return contract_entry


def _assert_parameters(
    parameters: object,
    schema: object | None,
    *,
    label: str,
) -> None:
    if schema is None:
        return
    if not isinstance(schema, dict):
        raise ConformanceValidationError(f"{label} parameters_schema must be an object")
    payload: object = {} if parameters is None else parameters
    try:
        Draft202012Validator(schema).validate(payload)
    except ValidationError as exc:
        raise ConformanceValidationError(f"{label} parameters invalid: {exc.message}") from exc


def assert_provenance_policy(manifest: dict[str, Any]) -> None:
    provenance = manifest["provenance"]
    if provenance["kind"] == "HANDCRAFTED":
        return
    if provenance["kind"] != "SANITIZED_REGRESSION":
        raise ConformanceValidationError("unsupported provenance kind")
    policy = provenance["sanitization_policy"]
    policy_id = str(policy["policy_id"])
    version = int(policy["version"])
    policies = _sanitization_policies().get("policies", {})
    entry = policies.get(policy_id)
    if entry is None:
        raise ConformanceValidationError("unknown sanitization policy_id")
    if version not in entry.get("versions", []):
        raise ConformanceValidationError("unknown sanitization policy version")
    approval = provenance["approval"]
    authority = str(approval["authority"])
    reference = str(approval["reference"])
    authorities = _approval_authorities().get("authorities", {})
    if authority not in authorities:
        raise ConformanceValidationError("unknown approval authority")
    _assert_opaque_reference(str(provenance["source_reference"]), label="source_reference")
    _assert_opaque_reference(reference, label="approval.reference")


def assert_fault_legality(manifest: dict[str, Any]) -> None:
    if "fault" not in manifest:
        return
    legality = _fault_legality()
    fault = manifest["fault"]
    binding = _binding_by_id(manifest, str(fault["contract_binding_id"]), label="fault")
    contract_entry = _contract_entry(
        legality,
        binding,
        unknown_owner="unknown fault owner",
        unknown_contract="unknown fault contract/version",
    )
    target = str(fault["target"])
    if target not in contract_entry.get("targets", []):
        raise ConformanceValidationError("unknown fault target")
    boundary = str(fault["boundary"])
    action = str(fault["action"])
    boundaries = contract_entry.get("boundaries", {})
    boundary_entry = boundaries.get(boundary)
    if boundary_entry is None:
        raise ConformanceValidationError("unknown fault boundary")
    if action not in boundary_entry:
        raise ConformanceValidationError("unknown fault action for boundary")
    allowed_profiles = set(contract_entry.get("profiles", []))
    for profile in manifest.get("required_profiles", []):
        if str(profile) not in allowed_profiles:
            raise ConformanceValidationError("fault illegal for required profile")
    _assert_parameters(
        fault.get("parameters"),
        contract_entry.get("parameters_schema"),
        label="fault",
    )


def assert_recovery_legality(manifest: dict[str, Any]) -> None:
    if "recovery_trigger" not in manifest:
        return
    legality = _recovery_legality()
    recovery = manifest["recovery_trigger"]
    binding = _binding_by_id(
        manifest, str(recovery["contract_binding_id"]), label="recovery_trigger"
    )
    contract_entry = _contract_entry(
        legality,
        binding,
        unknown_owner="unknown recovery owner",
        unknown_contract="unknown recovery contract/version",
    )
    kind = str(recovery["kind"])
    if kind not in contract_entry.get("kinds", []):
        raise ConformanceValidationError("unknown recovery_trigger kind")
    allowed_profiles = set(contract_entry.get("profiles", []))
    for profile in manifest.get("required_profiles", []):
        if str(profile) not in allowed_profiles:
            raise ConformanceValidationError("recovery illegal for required profile")
    _assert_parameters(
        recovery.get("parameters"),
        contract_entry.get("parameters_schema"),
        label="recovery_trigger",
    )
