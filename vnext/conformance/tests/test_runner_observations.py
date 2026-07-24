"""Observation set validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway_conformance.runner.fake.harness import FakeSubjectHarness
from gateway_conformance.runner.lifecycle import execute_scenario_run
from gateway_conformance.runner.registry import SubjectHarnessRegistry
from gateway_conformance.runner.runtime import LogicalClock
from tests.runner_support import default_env_versions, register_fake_harness
from tests.runner_support import build_data_scenario


@pytest.mark.parametrize("mode", ["missing", "duplicate", "unexpected"])
def test_observation_set_violations_are_harness_error(tmp_path: Path, mode: str) -> None:
    root = build_data_scenario(tmp_path)
    harness = FakeSubjectHarness(observation_mode=mode)  # type: ignore[arg-type]
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, factory=lambda: harness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id=f"run-{mode}",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "HARNESS_ERROR"


def test_wrong_observation_point_rejected(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    from gateway_conformance.owner.validate import compute_owner_content_digest
    from gateway_conformance.runner.types import ActualObservation
    from gateway_conformance.scenario.validate import load_validated_scenario

    _manifest, closure = load_validated_scenario(root)
    envelope = closure.golden_envelopes["result"]
    binding = dict(envelope["contract_binding"])
    descriptor = dict(envelope["payload_descriptor"])
    value = {"status": "ok"}
    digest = compute_owner_content_digest(
        value,
        owner=str(binding["owner"]),
        contract_id=str(binding["contract_id"]),
        semantic_version=str(binding["semantic_version"]),
        schema_id=str(descriptor["schema_id"]),
        schema_version=int(descriptor["schema_version"]),
    )
    bad_obs = ActualObservation(
        expectation_id="result",
        observation_point="after-failure",
        contract_binding=binding,
        payload_descriptor=descriptor,
        canonical_encoding_version=1,
        actual_content_digest=digest,
        payload={"storage": "inline", "value": value},
    )
    harness = FakeSubjectHarness(
        custom_observations={"final": [bad_obs]},
    )
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, factory=lambda: harness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-wrong-point",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "HARNESS_ERROR"
