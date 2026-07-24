"""Deterministic runner identity tests."""

from __future__ import annotations

import json
from pathlib import Path

from gateway_conformance.runner.lifecycle import execute_scenario_run
from gateway_conformance.runner.registry import SubjectHarnessRegistry
from gateway_conformance.runner.runtime import LogicalClock
from tests.runner_support import default_env_versions, register_fake_harness
from tests.runner_support import build_data_scenario


def test_identical_inputs_produce_identical_result_and_evidence(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry)

    def run_once() -> tuple[str, str]:
        outcome = execute_scenario_run(
            root,
            profile="reference",
            provider_id=None,
            run_id="run-deterministic",
            deterministic_seed="seed-fixed",
            clock=LogicalClock("2026-01-01T00:00:00Z"),
            environment_versions=default_env_versions(),
            registry=registry,
        )
        result_bytes = json.dumps(outcome.result, sort_keys=True, separators=(",", ":"))
        return result_bytes, str(outcome.evidence["content_digest"])

    first_result, first_digest = run_once()
    second_result, second_digest = run_once()
    assert first_result == second_result
    assert first_digest == second_digest
