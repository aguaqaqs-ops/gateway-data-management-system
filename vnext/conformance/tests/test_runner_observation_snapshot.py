"""Observation deep-snapshot trust boundary (BLK-002)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gateway_conformance.runner.fake.harness import FakeSubjectHarness
from gateway_conformance.runner.lifecycle import execute_scenario_run
from gateway_conformance.runner.registry import SubjectHarnessRegistry
from gateway_conformance.runner.runtime import HarnessRuntimeContext, LogicalClock
from gateway_conformance.runner.types import CleanupReceipt, ObservationSet
from tests.runner_support import build_data_scenario, default_env_versions, register_fake_harness


def test_cleanup_mutate_binding_does_not_change_evidence(tmp_path: Path) -> None:
    stored: list[Any] = []

    class Harness(FakeSubjectHarness):
        def stabilize_and_observe(
            self,
            context: HarnessRuntimeContext,
            plan: dict[str, object],
            *,
            observation_point: str,
        ) -> ObservationSet:
            result = super().stabilize_and_observe(
                context, plan, observation_point=observation_point
            )
            stored.extend(result.observations)
            return result

        def cleanup_subject(self, context: HarnessRuntimeContext) -> CleanupReceipt:
            for obs in stored:
                obs.contract_binding["wire_schema_version"] = 999
            return super().cleanup_subject(context)

    root = build_data_scenario(tmp_path)
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, factory=Harness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-bind",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "PASSED"
    ev_obs = outcome.evidence["observations"][0]
    assert ev_obs["contract_binding"].get("wire_schema_version") is None


def test_cleanup_mutate_descriptor_media_type(tmp_path: Path) -> None:
    stored: list[Any] = []

    class Harness(FakeSubjectHarness):
        def stabilize_and_observe(
            self,
            context: HarnessRuntimeContext,
            plan: dict[str, object],
            *,
            observation_point: str,
        ) -> ObservationSet:
            result = super().stabilize_and_observe(
                context, plan, observation_point=observation_point
            )
            stored.extend(result.observations)
            return result

        def cleanup_subject(self, context: HarnessRuntimeContext) -> CleanupReceipt:
            for obs in stored:
                obs.payload_descriptor["media_type"] = "application/x-mutated"
            return super().cleanup_subject(context)

    root = build_data_scenario(tmp_path)
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, factory=Harness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-desc",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "PASSED"
    assert (
        outcome.evidence["observations"][0]["payload_descriptor"]["media_type"]
        == "application/json"
    )
