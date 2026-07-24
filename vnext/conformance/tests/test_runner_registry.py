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
    registry.register(key, FakeSubjectHarness, harness_provenance="test-only")
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

    registry.register(key, FakeSubjectHarness, harness_provenance="test-only")
    with pytest.raises(ConformanceValidationError, match="duplicate harness registration"):
        registry.register(key, other_factory, harness_provenance="test-only")
    with pytest.raises(ConformanceValidationError, match="duplicate harness registration"):
        registry.register(key, FakeSubjectHarness, harness_provenance="test-only")


def test_registry_1000_fresh_resolve_without_false_reuse() -> None:
    registry = SubjectHarnessRegistry()
    key = SubjectKey(track="data", subject_kind="capability", subject_name="test-capability")
    registry.register(key, FakeSubjectHarness, harness_provenance="test-only")
    for _ in range(1000):
        registry.resolve(key)


def test_registry_rejects_singleton_factory_reuse() -> None:
    registry = SubjectHarnessRegistry()
    key = SubjectKey(track="data", subject_kind="capability", subject_name="test-capability")
    shared = FakeSubjectHarness()
    registry.register(key, lambda: shared, harness_provenance="test-only")
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

    registry.register(key, alternating, harness_provenance="test-only")
    registry.resolve(key)
    registry.resolve(key)
    with pytest.raises(
        ConformanceValidationError, match="must not reuse a previously returned instance"
    ):
        registry.resolve(key)


def test_registry_resolve_returns_distinct_instances() -> None:
    registry = SubjectHarnessRegistry()
    key = SubjectKey(track="data", subject_kind="capability", subject_name="test-capability")
    registry.register(key, FakeSubjectHarness, harness_provenance="test-only")
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


def test_formal_production_register_does_not_invoke_factory() -> None:
    from gateway_conformance.runner.registry import (
        FORMAL_PRODUCTION_SUBJECT_KEY,
        SubjectHarnessRegistry,
    )
    from gateway_conformance.runner.runtime import HarnessRuntimeContext
    from gateway_conformance.runner.types import (
        CleanupReceipt,
        InvocationReceipt,
        ObservationSet,
        PhaseReceipt,
        RecoveryReceipt,
        SupportDecision,
    )

    calls = {"n": 0}

    class CountingHarness:
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

    def factory() -> CountingHarness:
        calls["n"] += 1
        return CountingHarness()

    registry = SubjectHarnessRegistry()
    registry.register(FORMAL_PRODUCTION_SUBJECT_KEY, factory)
    assert calls["n"] == 0
    registry.resolve(FORMAL_PRODUCTION_SUBJECT_KEY)
    assert calls["n"] == 1


def test_formal_production_register_rejects_fake_class_factory() -> None:
    from gateway_conformance.runner.fake.harness import FakeSubjectHarness
    from gateway_conformance.runner.registry import (
        FORMAL_PRODUCTION_SUBJECT_KEY,
        SubjectHarnessRegistry,
    )

    registry = SubjectHarnessRegistry()
    with pytest.raises(ConformanceValidationError, match="fake harness cannot register"):
        registry.register(
            FORMAL_PRODUCTION_SUBJECT_KEY,
            FakeSubjectHarness,
            harness_provenance="production",
        )


def test_registry_source_has_no_dynamic_import() -> None:
    package_root = Path(__file__).resolve().parents[1] / "src" / "gateway_conformance" / "runner"
    forbidden = ("importlib", "__import__", "subprocess")
    for source in package_root.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in text, (source, marker)
