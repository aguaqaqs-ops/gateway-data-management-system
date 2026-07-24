"""Runner preflight contract tests."""

from __future__ import annotations

from pathlib import Path


from gateway_conformance.runner.fake.harness import FakeSubjectHarness
from gateway_conformance.runner.types import SupportDecision
from gateway_conformance.runner.lifecycle import execute_scenario_run
from gateway_conformance.runner.registry import SubjectHarnessRegistry
from gateway_conformance.runner.runtime import LogicalClock
from tests.runner_support import default_env_versions, register_fake_harness
from tests.runner_support import build_data_scenario


def test_preflight_supported_passes(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-preflight-ok",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "PASSED"


def test_preflight_unsupported_has_no_subject_side_effects(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    registry = SubjectHarnessRegistry()
    harness = FakeSubjectHarness(preflight_behavior="unsupported")
    register_fake_harness(registry, factory=lambda: harness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-unsupported",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "UNSUPPORTED"
    assert outcome.result["comparison_outcome"] == "NOT_RUN"
    codes = [item["code"] for item in outcome.result["diagnostics"]]
    assert "unsupported-reason" in codes
    assert all(item["outcome"] == "NOT_RUN" for item in outcome.result["expectations"])
    assert harness.phase_log == ["preflight"]
    assert harness.side_effect_counts.get("seed", 0) == 0
    assert harness.side_effect_counts.get("invoke", 0) == 0
    assert harness.side_effect_counts.get("cleanup_subject", 0) == 0


def test_preflight_invalid_support_maps_to_harness_error(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)

    class BadHarness(FakeSubjectHarness):
        def preflight(self, plan: dict[str, object]) -> SupportDecision:
            from gateway_conformance.errors import ConformanceValidationError

            raise ConformanceValidationError("invalid preflight receipt")

    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, factory=BadHarness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-bad-preflight",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "HARNESS_ERROR"
