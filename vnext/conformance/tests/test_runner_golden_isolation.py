"""Golden isolation from harness plan and runtime context."""

from __future__ import annotations

from pathlib import Path
from typing import Any


from gateway_conformance.paths import FORBIDDEN_PROTOCOL_FIELDS
from gateway_conformance.runner.fake.harness import FakeSubjectHarness
from gateway_conformance.runner.lifecycle import execute_scenario_run
from gateway_conformance.runner.registry import SubjectHarnessRegistry
from gateway_conformance.runner.runtime import HarnessRuntimeContext, LogicalClock
from gateway_conformance.runner.types import PhaseReceipt
from gateway_conformance.runner.plan import build_harness_plan, RunParams
from gateway_conformance.scenario.validate import load_validated_scenario
from tests.runner_support import default_env_versions, register_fake_harness
from tests.runner_support import build_data_scenario

_EXTRA_FORBIDDEN = frozenset(
    {
        "fixture_root",
        "golden",
        "expected",
        "host",
        "golden_path",
        "expected_payload",
    }
)


def _walk_forbidden(value: Any, *, label: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_PROTOCOL_FIELDS or key in _EXTRA_FORBIDDEN:
                raise AssertionError(f"{label} leaked forbidden field {key}")
            _walk_forbidden(child, label=f"{label}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_forbidden(child, label=f"{label}[{index}]")


def test_plan_and_context_exclude_golden_material(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    captured: dict[str, Any] = {}

    class SpyHarness(FakeSubjectHarness):
        def seed(self, context: HarnessRuntimeContext, plan: dict[str, object]) -> PhaseReceipt:
            captured["plan"] = dict(plan)
            captured["context"] = context
            return super().seed(context, plan)

    registry = SubjectHarnessRegistry()
    register_fake_harness(registry, factory=SpyHarness)
    execute_scenario_run(
        root,
        profile="reference",
        provider_id=None,
        run_id="run-isolation",
        deterministic_seed="seed",
        clock=LogicalClock("2026-01-01T00:00:00Z"),
        environment_versions=default_env_versions(),
        registry=registry,
    )
    _walk_forbidden(captured["plan"], label="plan")
    context = captured["context"]
    assert not hasattr(context, "golden_envelopes")
    assert isinstance(context.resolver._assets, dict)  # noqa: SLF001


def test_build_plan_has_no_expected_payload(tmp_path: Path) -> None:
    root = build_data_scenario(tmp_path)
    manifest, closure = load_validated_scenario(root)
    plan = build_harness_plan(
        manifest,
        closure,
        RunParams(
            profile="reference",
            provider_id=None,
            run_id="run-1",
            deterministic_seed="seed",
            logical_time_start="2026-01-01T00:00:00Z",
        ),
    )
    _walk_forbidden(plan, label="plan")
