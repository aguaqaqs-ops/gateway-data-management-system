"""Malformed harness receipt mutation tests (MAJ-007)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from gateway_conformance.runner.fake.harness import FakeSubjectHarness
from gateway_conformance.runner.lifecycle import execute_scenario_run
from gateway_conformance.runner.registry import SubjectHarnessRegistry
from gateway_conformance.runner.runtime import HarnessRuntimeContext, LogicalClock
from gateway_conformance.runner.types import (
    CleanupReceipt,
    InvocationReceipt,
    PhaseOutcome,
    PhaseReceipt,
    RecoveryReceipt,
)
from tests.runner_support import (
    build_data_scenario,
    build_recovery_scenario,
    default_env_versions,
    register_fake_harness,
)


def _run_data(tmp_path: Path, harness: FakeSubjectHarness) -> dict[str, str]:
    root = build_data_scenario(tmp_path)
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, factory=lambda: harness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-receipt",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    return {"status": str(outcome.result["status"])}


def test_seed_invalid_outcome_is_harness_error(tmp_path: Path) -> None:
    class BadSeed(FakeSubjectHarness):
        def seed(self, context: HarnessRuntimeContext, plan: dict[str, object]) -> PhaseReceipt:
            return PhaseReceipt(
                phase="seed",
                outcome=cast(PhaseOutcome, "INVALID"),
            )

    assert _run_data(tmp_path, BadSeed())["status"] == "HARNESS_ERROR"


def test_seed_completed_with_stable_code_is_harness_error(tmp_path: Path) -> None:
    class BadSeed(FakeSubjectHarness):
        def seed(self, context: HarnessRuntimeContext, plan: dict[str, object]) -> PhaseReceipt:
            return PhaseReceipt(phase="seed", outcome="COMPLETED", stable_code="oops")

    assert _run_data(tmp_path, BadSeed())["status"] == "HARNESS_ERROR"


def test_invoke_failed_without_stable_code_is_harness_error(tmp_path: Path) -> None:
    class BadInvoke(FakeSubjectHarness):
        def invoke(
            self, context: HarnessRuntimeContext, plan: dict[str, object]
        ) -> InvocationReceipt:
            return InvocationReceipt(phase="invoke", outcome="FAILED", stable_code=None)

    assert _run_data(tmp_path, BadInvoke())["status"] == "HARNESS_ERROR"


def test_seed_invalid_diagnostic_code_is_harness_error(tmp_path: Path) -> None:
    class BadSeed(FakeSubjectHarness):
        def seed(self, context: HarnessRuntimeContext, plan: dict[str, object]) -> PhaseReceipt:
            from gateway_conformance.runner.types import Diagnostic, PhaseReceipt

            return PhaseReceipt(
                phase="seed",
                outcome="COMPLETED",
                diagnostics=(Diagnostic(code="BAD CODE", message="x"),),
            )

    assert _run_data(tmp_path, BadSeed())["status"] == "HARNESS_ERROR"


def test_cleanup_invalid_status_is_harness_error(tmp_path: Path) -> None:
    class BadCleanup(FakeSubjectHarness):
        def cleanup_subject(self, context: HarnessRuntimeContext) -> CleanupReceipt:
            return CleanupReceipt(status=cast(Any, "BROKEN"))

    assert _run_data(tmp_path, BadCleanup())["status"] == "HARNESS_ERROR"


def test_recovery_mismatch_then_recovery_failed_preserves_mismatch(tmp_path: Path) -> None:
    from gateway_conformance.owner.validate import compute_owner_content_digest
    from gateway_conformance.runner.types import ActualObservation
    from gateway_conformance.scenario.validate import load_validated_scenario

    root = build_recovery_scenario(tmp_path)
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

    class FailRecovery(FakeSubjectHarness):
        custom_observations = None

        def __init__(self) -> None:
            super().__init__(
                custom_observations={
                    "after-failure": [obs({"checkpoints": ["bad"]}, "after-failure")],
                }
            )

        def drive_recovery(
            self, context: HarnessRuntimeContext, plan: dict[str, object]
        ) -> RecoveryReceipt:
            return RecoveryReceipt.failed(stable_code="recovery-broke")

    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, track="recovery", factory=FailRecovery)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-recovery-partial",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "HARNESS_ERROR"
    assert outcome.result["comparison_outcome"] == "MISMATCH"
    assert outcome.result["expectations"][0]["outcome"] == "MISMATCH"
    assert outcome.evidence["checkpoint_results"][0]["outcome"] == "MISMATCH"
