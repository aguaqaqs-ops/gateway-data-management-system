"""Recovery and fault protocol tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.runner.fake.harness import FakeSubjectHarness
from gateway_conformance.runner.lifecycle import execute_scenario_run
from gateway_conformance.runner.registry import SubjectHarnessRegistry
from gateway_conformance.runner.runtime import FaultSideChannel, LogicalClock
from tests.runner_support import default_env_versions, register_fake_harness
from tests.runner_support import build_recovery_scenario


def test_fault_not_consumed_is_harness_error(tmp_path: Path) -> None:
    root = build_recovery_scenario(tmp_path)
    from gateway_conformance.runner.types import InvocationReceipt

    class Harness(FakeSubjectHarness):
        def invoke(self, context, plan):  # type: ignore[no-untyped-def]
            self._record("invoke")
            return InvocationReceipt.completed()

    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, track="recovery", factory=Harness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-fault-miss",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "HARNESS_ERROR"


def test_fault_arm_and_consume_once(tmp_path: Path) -> None:
    root = build_recovery_scenario(tmp_path)
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, track="recovery")
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-recovery",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "PASSED"
    assert outcome.evidence["fault_receipt"] == {
        "armed": True,
        "consumed": True,
        "diagnostics": [],
    }


def test_fault_consume_without_arm_is_error() -> None:
    channel = FaultSideChannel()
    with pytest.raises(ConformanceValidationError, match="not armed"):
        channel.consume()


def test_fault_double_consume_is_error() -> None:
    channel = FaultSideChannel()
    channel.arm()
    channel.consume()
    with pytest.raises(ConformanceValidationError, match="already consumed"):
        channel.consume()


def test_recovery_observation_order(tmp_path: Path) -> None:
    root = build_recovery_scenario(tmp_path)
    harness = FakeSubjectHarness()
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, track="recovery", factory=lambda: harness)
    execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-order",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    failure_index = harness.phase_log.index("stabilize_and_observe:after-failure")
    recovery_index = harness.phase_log.index("drive_recovery")
    after_index = harness.phase_log.index("stabilize_and_observe:after-recovery")
    assert failure_index < recovery_index < after_index


def test_recovery_checkpoint_mismatch_prevents_passed(tmp_path: Path) -> None:
    root = build_recovery_scenario(tmp_path)
    from gateway_conformance.owner.validate import compute_owner_content_digest
    from gateway_conformance.runner.types import ActualObservation
    from gateway_conformance.scenario.validate import load_validated_scenario

    _manifest, closure = load_validated_scenario(root)
    envelope = closure.golden_envelopes["result"]
    binding = dict(envelope["contract_binding"])
    descriptor = dict(envelope["payload_descriptor"])

    def obs(value: dict[str, object], point: str) -> ActualObservation:
        digest = compute_owner_content_digest(
            value,
            owner=str(binding["owner"]),
            contract_id=str(binding["contract_id"]),
            semantic_version=str(binding["semantic_version"]),
            schema_id=str(descriptor["schema_id"]),
            schema_version=int(descriptor["schema_version"]),
        )
        return ActualObservation(
            expectation_id="result",
            observation_point=point,
            contract_binding=binding,
            payload_descriptor=descriptor,
            canonical_encoding_version=1,
            actual_content_digest=digest,
            payload={"storage": "inline", "value": value},
        )

    harness = FakeSubjectHarness(
        custom_observations={
            "after-failure": [obs({"checkpoints": ["bad"]}, "after-failure")],
            "after-recovery": [obs({"checkpoints": ["ok"]}, "after-recovery")],
        }
    )
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, track="recovery", factory=lambda: harness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-recovery-gate",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "ASSERTION_FAILED"
    checkpoints = {
        item["checkpoint"]: item["outcome"] for item in outcome.evidence["checkpoint_results"]
    }
    assert checkpoints["after_failure"] == "MISMATCH"
    assert checkpoints["after_recovery"] == "MATCH"
    after_failure_digest = next(
        item["content_digest"]
        for item in outcome.evidence["checkpoint_results"]
        if item["checkpoint"] == "after_failure"
    )
    assert after_failure_digest is not None
    obs_digests = {obs["actual_content_digest"] for obs in outcome.evidence["observations"]}
    result_actual = outcome.result["expectations"][0]["actual_content_digest"]
    assert result_actual in obs_digests
    assert result_actual == after_failure_digest


def test_recovery_gate_first_mismatch_digest_with_two_expectations(tmp_path: Path) -> None:
    """MAJ-024: A mismatches then matches; B mismatches on after-recovery only."""
    from gateway_shared_kernel import raw_blob_digest

    from gateway_conformance.owner.validate import compute_owner_content_digest
    from gateway_conformance.runner.types import ActualObservation
    from gateway_conformance.scenario.validate import load_validated_scenario
    from tests.support import _golden_envelope, base_manifest, write_scenario_tree

    manifest, golden_result = base_manifest(
        track="recovery",
        kind="recovery",
        include_fault=True,
        scenario_suffix="dual-expectation-gate",
    )
    aux_envelope = _golden_envelope(expectation_id="aux", kind="structured")
    golden_aux = json.dumps(aux_envelope, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    manifest["expected"] = sorted(
        [
            manifest["expected"][0],
            {
                "expectation_id": "aux",
                "kind": "structured",
                "path": "expected/aux.golden.json",
                "size_bytes": len(golden_aux),
                "raw_sha256": raw_blob_digest(golden_aux).value,
                "contract_binding": aux_envelope["contract_binding"],
                "content_digest": aux_envelope["content_digest"],
            },
        ],
        key=lambda entry: str(entry["expectation_id"]).encode("utf-8"),
    )
    root = tmp_path / "recovery" / "test-capability" / "dual-expectation-gate"
    root.mkdir(parents=True)
    (root / "expected").mkdir()
    (root / "expected" / "result.golden.json").write_bytes(golden_result)
    (root / "expected" / "aux.golden.json").write_bytes(golden_aux)
    write_scenario_tree(root, manifest, golden_bytes=golden_result)

    _manifest, closure = load_validated_scenario(root)
    result_env = closure.golden_envelopes["result"]
    aux_env = closure.golden_envelopes["aux"]
    result_binding = dict(result_env["contract_binding"])
    result_descriptor = dict(result_env["payload_descriptor"])
    aux_binding = dict(aux_env["contract_binding"])
    aux_descriptor = dict(aux_env["payload_descriptor"])

    def recovery_obs(value: dict[str, object], point: str) -> ActualObservation:
        digest = compute_owner_content_digest(
            value,
            owner=str(result_binding["owner"]),
            contract_id=str(result_binding["contract_id"]),
            semantic_version=str(result_binding["semantic_version"]),
            schema_id=str(result_descriptor["schema_id"]),
            schema_version=int(result_descriptor["schema_version"]),
        )
        return ActualObservation(
            expectation_id="result",
            observation_point=point,
            contract_binding=result_binding,
            payload_descriptor=result_descriptor,
            canonical_encoding_version=1,
            actual_content_digest=digest,
            payload={"storage": "inline", "value": value},
        )

    def aux_obs(value: dict[str, object], point: str) -> ActualObservation:
        digest = compute_owner_content_digest(
            value,
            owner=str(aux_binding["owner"]),
            contract_id=str(aux_binding["contract_id"]),
            semantic_version=str(aux_binding["semantic_version"]),
            schema_id=str(aux_descriptor["schema_id"]),
            schema_version=int(aux_descriptor["schema_version"]),
        )
        return ActualObservation(
            expectation_id="aux",
            observation_point=point,
            contract_binding=aux_binding,
            payload_descriptor=aux_descriptor,
            canonical_encoding_version=1,
            actual_content_digest=digest,
            payload={"storage": "inline", "value": value},
        )

    harness = FakeSubjectHarness(
        custom_observations={
            "after-failure": [
                recovery_obs({"checkpoints": ["bad"]}, "after-failure"),
                aux_obs({"status": "ok"}, "after-failure"),
            ],
            "after-recovery": [
                recovery_obs({"checkpoints": ["ok"]}, "after-recovery"),
                aux_obs({"status": "bad"}, "after-recovery"),
            ],
        }
    )
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, track="recovery", factory=lambda: harness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-dual-gate",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "ASSERTION_FAILED"
    by_id = {row["expectation_id"]: row for row in outcome.result["expectations"]}
    assert by_id["result"]["outcome"] == "MISMATCH"
    assert by_id["aux"]["outcome"] == "MISMATCH"
    assert by_id["result"]["actual_content_digest"] != by_id["result"]["expected_content_digest"]
    assert by_id["aux"]["actual_content_digest"] != by_id["aux"]["expected_content_digest"]
    after_failure_digest = next(
        item["content_digest"]
        for item in outcome.evidence["checkpoint_results"]
        if item["checkpoint"] == "after_failure"
    )
    assert by_id["result"]["actual_content_digest"] == after_failure_digest
