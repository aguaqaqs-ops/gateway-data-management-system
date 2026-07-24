"""Runner comparison authority tests."""

from __future__ import annotations

from pathlib import Path

from gateway_conformance.runner.fake.harness import FakeSubjectHarness
from gateway_conformance.runner.lifecycle import execute_scenario_run
from gateway_conformance.runner.registry import SubjectHarnessRegistry
from gateway_conformance.runner.runtime import LogicalClock
from tests.runner_support import default_env_versions, register_fake_harness
from tests.runner_support import build_data_scenario


def test_match_on_aligned_payload(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-match",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["comparison_outcome"] == "MATCH"
    row = outcome.result["expectations"][0]
    assert row["outcome"] == "MATCH"
    assert row["actual_content_digest"] == row["expected_content_digest"]


def test_mismatch_on_divergent_payload(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    harness = FakeSubjectHarness(observation_mode="mismatch")
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, factory=lambda: harness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-mismatch",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "ASSERTION_FAILED"
    assert outcome.result["comparison_outcome"] == "MISMATCH"


def test_runner_rejects_forged_digest(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    from gateway_conformance.owner.validate import compute_owner_content_digest
    from gateway_conformance.runner.types import ActualObservation
    from gateway_conformance.scenario.validate import load_validated_scenario

    _manifest, closure = load_validated_scenario(root)
    envelope = closure.golden_envelopes["result"]
    binding = dict(envelope["contract_binding"])
    descriptor = dict(envelope["payload_descriptor"])
    value = {"status": "ok"}
    compute_owner_content_digest(
        value,
        owner=str(binding["owner"]),
        contract_id=str(binding["contract_id"]),
        semantic_version=str(binding["semantic_version"]),
        schema_id=str(descriptor["schema_id"]),
        schema_version=int(descriptor["schema_version"]),
    )
    forged = ActualObservation(
        expectation_id="result",
        observation_point="final",
        contract_binding=binding,
        payload_descriptor=descriptor,
        canonical_encoding_version=1,
        actual_content_digest="sha256:" + "f" * 64,
        payload={"storage": "inline", "value": value},
    )
    harness = FakeSubjectHarness(custom_observations={"final": [forged]})
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, factory=lambda: harness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-forged",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "HARNESS_ERROR"
    assert outcome.evidence["observations"] == []
    forged_digest = "sha256:" + "f" * 64
    for item in outcome.evidence.get("observations", []):
        assert item.get("actual_content_digest") != forged_digest


def test_wire_schema_version_mismatch_is_harness_error(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    from gateway_conformance.owner.validate import compute_owner_content_digest
    from gateway_conformance.runner.types import ActualObservation
    from gateway_conformance.scenario.validate import load_validated_scenario

    _manifest, closure = load_validated_scenario(root)
    envelope = closure.golden_envelopes["result"]
    binding = dict(envelope["contract_binding"])
    binding["wire_schema_version"] = 999
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
    obs = ActualObservation(
        expectation_id="result",
        observation_point="final",
        contract_binding=binding,
        payload_descriptor=descriptor,
        canonical_encoding_version=1,
        actual_content_digest=digest,
        payload={"storage": "inline", "value": value},
    )
    harness = FakeSubjectHarness(custom_observations={"final": [obs]})
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, factory=lambda: harness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-wire",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "HARNESS_ERROR"
