"""Static in-process subject harness registry."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.runner.types import (
    CleanupReceipt,
    InvocationReceipt,
    ObservationSet,
    PhaseReceipt,
    RecoveryReceipt,
    SupportDecision,
)
from gateway_conformance.runner.runtime import HarnessRuntimeContext


@dataclass(frozen=True, slots=True, order=True)
class SubjectKey:
    track: str
    subject_kind: str
    subject_name: str


class SubjectHarness(Protocol):
    def preflight(self, plan: dict[str, object]) -> SupportDecision: ...

    def seed(self, context: HarnessRuntimeContext, plan: dict[str, object]) -> PhaseReceipt: ...

    def invoke(
        self, context: HarnessRuntimeContext, plan: dict[str, object]
    ) -> InvocationReceipt: ...

    def stabilize_and_observe(
        self,
        context: HarnessRuntimeContext,
        plan: dict[str, object],
        *,
        observation_point: str,
    ) -> ObservationSet: ...

    def drive_recovery(
        self, context: HarnessRuntimeContext, plan: dict[str, object]
    ) -> RecoveryReceipt: ...

    def cleanup_subject(self, context: HarnessRuntimeContext) -> CleanupReceipt: ...


HarnessFactory = Callable[[], SubjectHarness]


class SubjectHarnessRegistry:
    """Explicit registry; no dynamic import or string entrypoints."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._factories: dict[SubjectKey, HarnessFactory] = {}
        self._seen_instances: dict[SubjectKey, list[object]] = {}

    def register(self, key: SubjectKey, factory: HarnessFactory) -> None:
        with self._lock:
            if key in self._factories:
                raise ConformanceValidationError(f"duplicate harness registration for {key}")
            self._factories[key] = factory

    def resolve(self, key: SubjectKey) -> SubjectHarness:
        with self._lock:
            factory = self._factories.get(key)
            if factory is None:
                raise ConformanceValidationError(f"unknown subject harness: {key}")
            instance = factory()
            seen = self._seen_instances.setdefault(key, [])
            for prior in seen:
                if prior is instance:
                    raise ConformanceValidationError(
                        "harness factory must not reuse a previously returned instance"
                    )
            seen.append(instance)
            return instance

    def clear(self) -> None:
        with self._lock:
            self._factories.clear()
            self._seen_instances.clear()


def subject_key_from_manifest(manifest: dict[str, object]) -> SubjectKey:
    subject = manifest["subject"]
    if not isinstance(subject, dict):
        raise ConformanceValidationError("manifest subject must be an object")
    return SubjectKey(
        track=str(manifest["track"]),
        subject_kind=str(subject["kind"]),
        subject_name=str(subject["name"]),
    )
