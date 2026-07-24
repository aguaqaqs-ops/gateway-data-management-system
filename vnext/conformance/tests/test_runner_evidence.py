"""Run evidence packaging tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.protocol.digest import compute_run_evidence_content_digest
from gateway_conformance.protocol.validate import validate_run_evidence_bundle
from gateway_conformance.runner.fake.harness import FakeSubjectHarness
from gateway_conformance.runner.lifecycle import execute_scenario_run
from gateway_conformance.runner.registry import SubjectHarnessRegistry
from gateway_conformance.runner.runtime import LogicalClock
from tests.runner_support import default_env_versions, register_fake_harness
from tests.runner_support import build_data_scenario


def test_invalid_environment_versions_returns_four_state(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    harness = FakeSubjectHarness()
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, factory=lambda: harness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-bad-env",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=[{"component": "x", "version": "1", "extra": "nope"}],
        registry=registry,
    )
    assert outcome.result["status"] == "HARNESS_ERROR"
    assert harness.phase_log == []


def test_evidence_digest_valid(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-evidence",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    validate_run_evidence_bundle(outcome.evidence)


def test_evidence_tamper_rejected(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-evidence-tamper",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    tampered = dict(outcome.evidence)
    tampered["content_digest"] = "sha256:" + "a" * 64
    with pytest.raises(ConformanceValidationError, match="content_digest mismatch"):
        validate_run_evidence_bundle(tampered)


def test_evidence_stable_ordering(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-evidence-order",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=[
            {"component": "zeta", "version": "1"},
            {"component": "alpha", "version": "1"},
        ],
        registry=registry,
    )
    components = [item["component"] for item in outcome.evidence["environment_versions"]]
    assert components == sorted(components)
    recomputed = compute_run_evidence_content_digest(outcome.evidence)
    assert recomputed == outcome.evidence["content_digest"]
