"""Runner lifecycle sequence and failure injection tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway_conformance.runner.fake.harness import FakeSubjectHarness
from gateway_conformance.runner.lifecycle import execute_scenario_run
from gateway_conformance.runner.registry import SubjectHarnessRegistry
from gateway_conformance.runner.runtime import LogicalClock
from tests.runner_support import (
    build_command_scenario,
    build_data_scenario,
    build_recovery_scenario,
    default_env_versions,
    register_fake_harness,
)


def _run(
    root: Path,
    harness: FakeSubjectHarness,
    *,
    track: str = "data",
) -> None:
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, track=track, factory=lambda: harness)
    execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-life",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )


def test_data_track_phase_sequence(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    harness = FakeSubjectHarness()
    _run(root, harness)
    assert harness.phase_log == [
        "preflight",
        "seed",
        "invoke",
        "stabilize_and_observe:final",
        "cleanup_subject",
    ]
    for phase in ("preflight", "seed", "invoke", "stabilize_and_observe:final", "cleanup_subject"):
        assert harness.side_effect_counts[phase] == 1


def test_command_track_sequence(tmp_path: Path) -> None:
    root = build_command_scenario(tmp_path)
    harness = FakeSubjectHarness()
    _run(root, harness, track="command")
    assert "stabilize_and_observe:final" in harness.phase_log


def test_recovery_track_sequence(tmp_path: Path) -> None:
    root = build_recovery_scenario(tmp_path)
    harness = FakeSubjectHarness()
    _run(root, harness, track="recovery")
    assert harness.phase_log == [
        "preflight",
        "seed",
        "invoke",
        "stabilize_and_observe:after-failure",
        "drive_recovery",
        "stabilize_and_observe:after-recovery",
        "cleanup_subject",
    ]


@pytest.mark.parametrize(
    "fail_phase",
    ["seed", "invoke", "observe", "recovery"],
)
def test_phase_failure_stops_later_phases(tmp_path: Path, fail_phase: str) -> None:
    if fail_phase == "recovery":
        root = build_recovery_scenario(tmp_path)
        track = "recovery"
        harness = FakeSubjectHarness(recovery_behavior="fail")
    else:
        root = build_data_scenario(tmp_path)
        track = "data"
        harness = FakeSubjectHarness(
            seed_behavior="fail" if fail_phase == "seed" else "ok",
            invoke_behavior="fail" if fail_phase == "invoke" else "ok",
            observe_behavior="fail" if fail_phase == "observe" else "ok",
        )
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, track=track, factory=lambda: harness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-fail",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "HARNESS_ERROR"
    assert harness.side_effect_counts.get("cleanup_subject", 0) == 1
    if fail_phase == "seed":
        assert harness.side_effect_counts.get("invoke", 0) == 0
    if fail_phase in {"seed", "invoke"}:
        assert harness.side_effect_counts.get("stabilize_and_observe:final", 0) == 0


def test_cleanup_always_runs_on_match_with_leak(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    harness = FakeSubjectHarness(cleanup_status="LEAKED")
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, factory=lambda: harness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-leak",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert harness.side_effect_counts["cleanup_subject"] == 1
    assert outcome.result["status"] == "HARNESS_ERROR"
    assert outcome.result["comparison_outcome"] == "MATCH"
