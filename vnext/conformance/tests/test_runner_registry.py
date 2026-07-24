"""Subject harness registry contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.runner.fake.harness import FakeSubjectHarness
from gateway_conformance.runner.registry import SubjectHarnessRegistry, SubjectKey


def test_registry_register_and_resolve() -> None:
    registry = SubjectHarnessRegistry()
    key = SubjectKey(track="data", subject_kind="capability", subject_name="test-capability")
    registry.register(key, FakeSubjectHarness)
    harness = registry.resolve(key)
    assert isinstance(harness, FakeSubjectHarness)


def test_registry_unknown_subject() -> None:
    registry = SubjectHarnessRegistry()
    key = SubjectKey(track="data", subject_kind="capability", subject_name="missing")
    with pytest.raises(ConformanceValidationError, match="unknown subject harness"):
        registry.resolve(key)


def test_registry_duplicate_registration() -> None:
    registry = SubjectHarnessRegistry()
    key = SubjectKey(track="data", subject_kind="capability", subject_name="test-capability")

    def other_factory() -> FakeSubjectHarness:
        return FakeSubjectHarness(preflight_behavior="unsupported")

    registry.register(key, FakeSubjectHarness)
    with pytest.raises(ConformanceValidationError, match="duplicate harness registration"):
        registry.register(key, other_factory)
    with pytest.raises(ConformanceValidationError, match="duplicate harness registration"):
        registry.register(key, FakeSubjectHarness)


def test_registry_1000_fresh_resolve_without_false_reuse() -> None:
    registry = SubjectHarnessRegistry()
    key = SubjectKey(track="data", subject_kind="capability", subject_name="test-capability")
    registry.register(key, FakeSubjectHarness)
    for _ in range(1000):
        registry.resolve(key)


def test_registry_rejects_singleton_factory_reuse() -> None:
    registry = SubjectHarnessRegistry()
    key = SubjectKey(track="data", subject_kind="capability", subject_name="test-capability")
    shared = FakeSubjectHarness()
    registry.register(key, lambda: shared)
    registry.resolve(key)
    with pytest.raises(
        ConformanceValidationError, match="must not reuse a previously returned instance"
    ):
        registry.resolve(key)


def test_registry_rejects_alternating_singleton_pool() -> None:
    registry = SubjectHarnessRegistry()
    key = SubjectKey(track="data", subject_kind="capability", subject_name="test-capability")
    a = FakeSubjectHarness()
    b = FakeSubjectHarness()
    counter = {"n": 0}

    def alternating() -> FakeSubjectHarness:
        counter["n"] += 1
        return a if counter["n"] % 2 == 1 else b

    registry.register(key, alternating)
    registry.resolve(key)
    registry.resolve(key)
    with pytest.raises(
        ConformanceValidationError, match="must not reuse a previously returned instance"
    ):
        registry.resolve(key)


def test_registry_resolve_returns_distinct_instances() -> None:
    registry = SubjectHarnessRegistry()
    key = SubjectKey(track="data", subject_kind="capability", subject_name="test-capability")
    registry.register(key, FakeSubjectHarness)
    first = registry.resolve(key)
    second = registry.resolve(key)
    assert first is not second


def test_registry_resolves_slots_only_harness() -> None:
    from gateway_conformance.runner.runtime import HarnessRuntimeContext
    from gateway_conformance.runner.types import (
        CleanupReceipt,
        InvocationReceipt,
        ObservationSet,
        PhaseReceipt,
        RecoveryReceipt,
        SupportDecision,
    )

    class SlotsHarness:
        __slots__ = ()

        def preflight(self, plan: dict[str, object]) -> SupportDecision:
            return SupportDecision(support="SUPPORTED")

        def seed(self, context: HarnessRuntimeContext, plan: dict[str, object]) -> PhaseReceipt:
            return PhaseReceipt(phase="seed", outcome="COMPLETED")

        def invoke(
            self, context: HarnessRuntimeContext, plan: dict[str, object]
        ) -> InvocationReceipt:
            return InvocationReceipt.completed()

        def stabilize_and_observe(
            self, context: HarnessRuntimeContext, plan: dict[str, object], *, observation_point: str
        ) -> ObservationSet:
            return ObservationSet(
                observations=(),
                receipt=PhaseReceipt(phase="stabilize_and_observe", outcome="COMPLETED"),
            )

        def drive_recovery(
            self, context: HarnessRuntimeContext, plan: dict[str, object]
        ) -> RecoveryReceipt:
            return RecoveryReceipt.completed()

        def cleanup_subject(self, context: HarnessRuntimeContext) -> CleanupReceipt:
            return CleanupReceipt(status="CLEAN")

    registry = SubjectHarnessRegistry()
    key = SubjectKey(track="data", subject_kind="capability", subject_name="test-capability")
    registry.register(key, SlotsHarness)
    assert isinstance(registry.resolve(key), SlotsHarness)


def test_registry_source_has_no_dynamic_import() -> None:
    package_root = Path(__file__).resolve().parents[1] / "src" / "gateway_conformance" / "runner"
    forbidden = ("importlib", "__import__", "subprocess")
    for source in package_root.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in text, (source, marker)
