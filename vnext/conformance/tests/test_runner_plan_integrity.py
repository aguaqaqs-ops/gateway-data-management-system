"""Runner plan authority isolation probes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gateway_conformance.runner.fake.harness import FakeSubjectHarness
from gateway_conformance.runner.lifecycle import execute_scenario_run
from gateway_conformance.runner.registry import SubjectHarnessRegistry
from gateway_conformance.runner.runtime import HarnessRuntimeContext, LogicalClock
from gateway_conformance.runner.types import PhaseReceipt
from tests.runner_support import build_data_scenario, default_env_versions, register_fake_harness


def test_harness_plan_mutation_does_not_change_result_identity(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    captured_key: dict[str, Any] = {}

    class SpyHarness(FakeSubjectHarness):
        def seed(self, context: HarnessRuntimeContext, plan: dict[str, object]) -> PhaseReceipt:
            execution_key = plan["execution_key"]
            assert isinstance(execution_key, dict)
            captured_key["before"] = dict(execution_key)
            execution_key["scenario_id"] = "data.test-capability.mutated"
            return super().seed(context, plan)

    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, factory=SpyHarness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-plan-integrity",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "PASSED"
    assert outcome.result["execution_key"]["scenario_id"] == "data.test-capability.minimal"
    assert outcome.evidence["execution_key"]["scenario_id"] == "data.test-capability.minimal"
    assert captured_key["before"]["scenario_id"] == "data.test-capability.minimal"


def test_harness_illegal_scenario_id_on_harness_plan_does_not_poison_authority(
    tmp_path: Path,
) -> None:
    root = build_data_scenario(tmp_path)

    class MutatorHarness(FakeSubjectHarness):
        def seed(self, context: HarnessRuntimeContext, plan: dict[str, object]) -> PhaseReceipt:
            execution_key = plan["execution_key"]
            assert isinstance(execution_key, dict)
            execution_key["scenario_id"] = "not-a-valid-id"
            return super().seed(context, plan)

    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, factory=MutatorHarness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-plan-bad-id",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "PASSED"
    assert outcome.result["execution_key"]["scenario_id"] == "data.test-capability.minimal"
