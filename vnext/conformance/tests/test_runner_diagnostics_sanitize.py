"""Runner diagnostics sanitization tests."""

from __future__ import annotations

from pathlib import Path

from gateway_conformance.owner.validate import compute_owner_content_digest
from gateway_conformance.runner.fake.harness import FakeSubjectHarness
from gateway_conformance.runner.lifecycle import execute_scenario_run
from gateway_conformance.runner.registry import SubjectHarnessRegistry
from gateway_conformance.runner.runtime import HarnessRuntimeContext, LogicalClock
from gateway_conformance.runner.types import (
    ActualObservation,
    CleanupReceipt,
    Diagnostic,
    InvocationReceipt,
)
from tests.runner_support import build_data_scenario, default_env_versions, register_fake_harness


def test_harness_error_diagnostics_sanitize_host_paths(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    secret_path = "/root/secret/credentials.json"

    class ExplodingHarness(FakeSubjectHarness):
        def invoke(
            self, context: HarnessRuntimeContext, plan: dict[str, object]
        ) -> InvocationReceipt:
            raise RuntimeError(f"boom at {secret_path}")

    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, factory=ExplodingHarness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-sanitize",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "HARNESS_ERROR"
    messages = [item["message"] for item in outcome.result["diagnostics"]]
    assert messages
    joined = " ".join(messages)
    assert secret_path not in joined
    assert "/root/" not in joined
    assert "<path>" in joined


def test_invoke_failure_keeps_cleanup_diagnostics_separate(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)

    class InvokeFail(FakeSubjectHarness):
        def invoke(
            self, context: HarnessRuntimeContext, plan: dict[str, object]
        ) -> InvocationReceipt:
            return InvocationReceipt.failed(stable_code="invoke-broke")

    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, factory=InvokeFail)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-invoke-fail-diag",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "HARNESS_ERROR"
    top_codes = {item["code"] for item in outcome.evidence["diagnostics"]}
    cleanup_codes = {item["code"] for item in outcome.evidence["cleanup"]["diagnostics"]}
    assert "harness-error" in top_codes or "invoke-broke" in " ".join(
        item["message"] for item in outcome.evidence["diagnostics"]
    )
    assert top_codes != cleanup_codes or not cleanup_codes


def test_evidence_cleanup_and_observation_diagnostics_sanitize_paths(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    secret_path = "/root/secret/credentials.json"

    class LeakyCleanupHarness(FakeSubjectHarness):
        def cleanup_subject(self, context: HarnessRuntimeContext) -> CleanupReceipt:
            return CleanupReceipt(
                status="LEAKED",
                diagnostics=(Diagnostic(code="leak", message=f"leftover at {secret_path}"),),
            )

    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, factory=LeakyCleanupHarness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-evidence-sanitize",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    cleanup_messages = [item["message"] for item in outcome.evidence["cleanup"]["diagnostics"]]
    top_messages = [item["message"] for item in outcome.evidence["diagnostics"]]
    joined = " ".join(cleanup_messages + top_messages)
    assert secret_path not in joined
    assert "/root/" not in joined


def test_evidence_observation_wire_sanitizes_diagnostic_paths(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    secret_path = "/root/secret/observation.json"
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
    obs = ActualObservation(
        expectation_id="result",
        observation_point="final",
        contract_binding=binding,
        payload_descriptor=descriptor,
        canonical_encoding_version=1,
        actual_content_digest=digest,
        payload={"storage": "inline", "value": value},
        diagnostics=(Diagnostic(code="note", message=f"read {secret_path}"),),
    )
    harness = FakeSubjectHarness(custom_observations={"final": [obs]})
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, factory=lambda: harness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-obs-sanitize",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    obs_messages = [
        item["message"]
        for observation in outcome.evidence["observations"]
        for item in observation.get("diagnostics", [])
    ]
    joined = " ".join(obs_messages)
    assert secret_path not in joined
    assert "/root/" not in joined
