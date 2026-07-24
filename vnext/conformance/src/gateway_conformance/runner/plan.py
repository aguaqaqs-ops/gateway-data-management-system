"""Build validated harness plan DTO from scenario closure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.protocol.validate import validate_harness_plan
from gateway_conformance.runner.types import HARNESS_PROTOCOL_VERSION
from gateway_conformance.scenario.closure import ScenarioClosure
from gateway_conformance.scenario.identity import assert_sorted_unique_bytes


@dataclass(frozen=True, slots=True)
class RunParams:
    profile: str
    provider_id: str | None
    run_id: str
    deterministic_seed: str
    logical_time_start: str


def _verified_asset_wire(asset: dict[str, Any], closure: ScenarioClosure) -> dict[str, Any]:
    logical_name = str(asset["logical_name"])
    resolved = closure.assets.get(logical_name)
    if resolved is None:
        raise ConformanceValidationError(f"plan references unknown asset: {logical_name}")
    base: dict[str, Any] = {
        "logical_name": logical_name,
        "media_type": str(asset["media_type"]),
        "size_bytes": int(asset["size_bytes"]),
        "raw_sha256": str(asset["raw_sha256"]),
    }
    if "path" in asset:
        base["path"] = str(asset["path"])
    else:
        base["ref"] = str(asset["ref"])
    return base


def build_harness_plan(
    manifest: dict[str, Any],
    closure: ScenarioClosure,
    params: RunParams,
) -> dict[str, Any]:
    observation_requests: list[dict[str, Any]] = []
    for entry in manifest["expected"]:
        expectation_id = str(entry["expectation_id"])
        envelope = closure.golden_envelopes.get(expectation_id)
        if envelope is None:
            raise ConformanceValidationError(f"missing golden for expectation {expectation_id}")
        observation_requests.append(
            {
                "expectation_id": expectation_id,
                "kind": str(entry["kind"]),
                "contract_binding": dict(entry["contract_binding"]),
                "payload_descriptor": dict(envelope["payload_descriptor"]),
            }
        )
    exp_ids = [str(item["expectation_id"]) for item in observation_requests]
    assert_sorted_unique_bytes(exp_ids, label="observation_requests")

    bindings = [dict(item) for item in manifest["contract_bindings"]]
    binding_ids = [str(item["binding_id"]) for item in bindings]
    assert_sorted_unique_bytes(binding_ids, label="contract_bindings")
    bindings.sort(key=lambda item: str(item["binding_id"]))

    verified_assets = [_verified_asset_wire(asset, closure) for asset in manifest["input_assets"]]
    verified_assets.sort(key=lambda item: str(item["logical_name"]))

    plan: dict[str, Any] = {
        "harness_protocol_version": HARNESS_PROTOCOL_VERSION,
        "execution_key": {
            "scenario_id": str(manifest["scenario_id"]),
            "profile": params.profile,
            "provider_id": params.provider_id,
            "fixture_content_digest": str(manifest["fixture_content_digest"]),
        },
        "run_id": params.run_id,
        "subject": dict(manifest["subject"]),
        "contract_bindings": bindings,
        "logical_time_start": params.logical_time_start,
        "deterministic_seed": params.deterministic_seed,
        "verified_assets": verified_assets,
        "stimulus": dict(manifest["stimulus"]),
        "observation_requests": observation_requests,
    }
    if "fault" in manifest:
        plan["fault"] = dict(manifest["fault"])
    if "recovery_trigger" in manifest:
        plan["recovery_trigger"] = dict(manifest["recovery_trigger"])
    validate_harness_plan(plan)
    return plan
