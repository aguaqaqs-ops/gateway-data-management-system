"""Harness public capability API and runner token dispatch lifecycle tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from gateway_conformance.runner.fake.harness import FakeSubjectHarness
from gateway_conformance.runner.lifecycle import execute_scenario_run
from gateway_conformance.runner.registry import SubjectHarnessRegistry
from gateway_conformance.runner.runtime import (
    FaultSideChannel,
    FaultConsumeFacade,
    HarnessRuntimeContext,
    LogicalClock,
    ProfileView,
    RunIdentity,
    VerifiedAssetResolver,
    build_harness_context,
    capability_token_registry_sizes,
    register_fault_channel,
    unregister_run_tokens,
)
from gateway_conformance.runner.types import PhaseReceipt
from tests.runner_support import (
    build_data_scenario,
    build_recovery_scenario,
    default_env_versions,
    register_fake_harness,
)


@pytest.fixture(autouse=True)
def _assert_token_registries_empty() -> Iterator[None]:
    assert capability_token_registry_sizes() == (0, 0)
    yield
    assert capability_token_registry_sizes() == (0, 0)


def test_data_run_fault_receipt_is_null(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-no-fault",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "PASSED"
    assert outcome.evidence["fault_receipt"] is None


def test_harness_public_capability_surface_on_data_run(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)

    class ProbeHarness(FakeSubjectHarness):
        def seed(self, context: HarnessRuntimeContext, plan: dict[str, object]) -> PhaseReceipt:
            assert context.fault is None
            assert not hasattr(context, "_logical_clock")
            assert not hasattr(context, "deadline_tick")
            assert not hasattr(context.clock, "_clock")
            assert context.clock.now_iso() == "2026-01-01T00:00:00Z"
            assert getattr(context.clock, "tick", None) is None
            assert getattr(context.clock, "advance_iso", None) is None
            return super().seed(context, plan)

    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, factory=ProbeHarness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-probe",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "PASSED"
    assert outcome.evidence["fault_receipt"] is None


def test_recovery_run_still_records_fault_receipt(tmp_path: Path) -> None:
    root = build_recovery_scenario(tmp_path)
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, track="recovery")
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-recovery-fault",
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


def test_fault_facade_uses_token_dispatch() -> None:
    channel = FaultSideChannel()
    channel.arm()
    token = register_fault_channel(channel)
    try:
        facade = FaultConsumeFacade(token)
        assert getattr(facade.consume, "__closure__", None) is None
        facade.consume()
        assert channel.consumed
    finally:
        unregister_run_tokens(clock_token=None, fault_token=token)


def test_fault_channel_cannot_assign_consumed_field() -> None:
    channel = FaultSideChannel()
    channel.arm()
    with pytest.raises(AttributeError):
        channel.consumed = True  # type: ignore[misc]
    assert channel.receipt()["consumed"] is False


def test_build_harness_context_tokens_and_frozen_clock() -> None:
    clock = LogicalClock("2026-05-01T00:00:00Z")
    channel = FaultSideChannel()
    channel.arm()
    context, tokens = build_harness_context(
        identity=RunIdentity(run_id="r", deterministic_seed="s"),
        clock=clock,
        profile=ProfileView(profile="reference", provider_id=None),
        resolver=VerifiedAssetResolver({}),
        fault=channel,
    )
    try:
        assert tokens.fault_token is not None
        assert not hasattr(context.clock, "_clock")
        assert context.clock.now_iso() == "2026-05-01T00:00:00Z"
        clock.advance_iso("2099-01-01T00:00:00Z")
        assert context.clock.now_iso() == "2026-05-01T00:00:00Z"
        assert context.fault is not None
        context.fault.consume()
        assert channel.consumed
    finally:
        unregister_run_tokens(
            clock_token=tokens.clock_token,
            fault_token=tokens.fault_token,
        )


@pytest.mark.parametrize(
    ("factory", "track", "expected_status"),
    [
        (lambda: FakeSubjectHarness(), "data", "PASSED"),
        (lambda: FakeSubjectHarness(observation_mode="mismatch"), "data", "ASSERTION_FAILED"),
        (lambda: FakeSubjectHarness(preflight_behavior="unsupported"), "data", "UNSUPPORTED"),
    ],
)
def test_execute_scenario_run_clears_token_registry(
    tmp_path: Path,
    factory: object,
    track: str,
    expected_status: str,
) -> None:
    root = (
        build_recovery_scenario(tmp_path) if track == "recovery" else build_data_scenario(tmp_path)
    )
    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, track=track, factory=factory)  # type: ignore[arg-type]
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id=f"run-token-clear-{expected_status}",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == expected_status


def test_seed_failure_clears_token_registry(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)

    class FailingSeedHarness(FakeSubjectHarness):
        def seed(self, context: HarnessRuntimeContext, plan: dict[str, object]) -> PhaseReceipt:
            return PhaseReceipt(phase="seed", outcome="FAILED", stable_code="seed-broke")

    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, factory=FailingSeedHarness)
    outcome = execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-seed-fail",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    assert outcome.result["status"] == "HARNESS_ERROR"
