"""Run evidence bundle packaging."""

from __future__ import annotations

from typing import Any

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.scenario.identity import assert_lower_kebab
from gateway_conformance.protocol.digest import compute_run_evidence_content_digest
from gateway_conformance.protocol.validate import validate_run_evidence_bundle
from gateway_conformance.runner.diagnostics import sanitize_diagnostic
from gateway_conformance.runner.compare import recompute_actual_digest
from gateway_conformance.runner.types import ActualObservation, CleanupStatus, Diagnostic


def validate_environment_versions(
    environment_versions: list[dict[str, str]],
) -> list[dict[str, str]]:
    validated: list[dict[str, str]] = []
    seen_components: set[str] = set()
    for item in environment_versions:
        if set(item.keys()) != {"component", "version"}:
            raise ConformanceValidationError(
                "environment_versions entry must have only component and version"
            )
        component = str(item["component"])
        version = str(item["version"])
        if not component or not version:
            raise ConformanceValidationError(
                "environment_versions component and version must be non-empty"
            )
        assert_lower_kebab(component, label="environment_versions.component")
        if component in seen_components:
            raise ConformanceValidationError("environment_versions component must be unique")
        seen_components.add(component)
        validated.append({"component": component, "version": version})
    return validated


def _observation_wire(observation: ActualObservation) -> dict[str, Any]:
    recomputed = recompute_actual_digest(observation)
    if recomputed != observation.actual_content_digest:
        raise ConformanceValidationError("observation actual_content_digest does not match payload")
    wire = observation.to_wire()
    payload = dict(wire["payload"])
    return {
        "harness_protocol_version": wire["harness_protocol_version"],
        "expectation_id": wire["expectation_id"],
        "observation_point": wire["observation_point"],
        "contract_binding": wire["contract_binding"],
        "payload_descriptor": wire["payload_descriptor"],
        "canonical_encoding_version": wire["canonical_encoding_version"],
        "actual_content_digest": recomputed,
        "payload": payload,
        "diagnostics": [sanitize_diagnostic(d).to_wire() for d in observation.diagnostics],
    }


def package_run_evidence(
    *,
    plan: dict[str, Any],
    environment_versions: list[dict[str, str]],
    observations: list[ActualObservation],
    checkpoint_results: list[dict[str, Any]],
    fault_receipt: dict[str, Any] | None,
    cleanup: CleanupStatus,
    diagnostics: list[Diagnostic],
    cleanup_diagnostics: list[Diagnostic] | None = None,
) -> dict[str, Any]:
    sanitized_runner = [sanitize_diagnostic(item) for item in diagnostics]
    sanitized_cleanup = [sanitize_diagnostic(item) for item in (cleanup_diagnostics or [])]
    sorted_observations = sorted(
        [_observation_wire(item) for item in observations],
        key=lambda item: (str(item["observation_point"]), str(item["expectation_id"])),
    )
    sorted_checkpoints = sorted(
        checkpoint_results,
        key=lambda item: str(item["checkpoint"]),
    )
    sorted_env = sorted(environment_versions, key=lambda item: str(item["component"]))
    evidence: dict[str, Any] = {
        "run_evidence_schema_version": 1,
        "execution_key": dict(plan["execution_key"]),
        "run_id": str(plan["run_id"]),
        "environment_versions": sorted_env,
        "fault_receipt": fault_receipt,
        "observations": sorted_observations,
        "checkpoint_results": sorted_checkpoints,
        "cleanup": {
            "status": cleanup,
            "diagnostics": [item.to_wire() for item in sanitized_cleanup],
        },
        "diagnostics": sorted(
            [item.to_wire() for item in sanitized_runner],
            key=lambda item: (str(item["code"]), str(item["message"])),
        ),
        "content_digest": "sha256:" + "0" * 64,
    }
    evidence["content_digest"] = compute_run_evidence_content_digest(evidence)
    validate_run_evidence_bundle(evidence)
    return evidence
