"""Test-only fault injection seams for Versioned import workers."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol


class ImportWorkerFaultPoint(StrEnum):
    AFTER_RUNNING_CLAIM = "after_running_claim"
    AFTER_PACKAGE_EXTRACTED = "after_package_extracted"
    AFTER_PRIVATE_REF_CREATED = "after_private_ref_created"
    AFTER_REPLAY_BEFORE_MARKER = "after_replay_before_marker"
    AFTER_MARKER_BEFORE_VERIFICATION = "after_marker_before_verification"
    AFTER_VERIFICATION_BEFORE_SECOND_MAIN_CHECK = "after_verification_before_second_main_check"
    AFTER_SECOND_MAIN_CHECK_BEFORE_PUBLISH = "after_second_main_check_before_publish"
    AFTER_MAIN_PUBLISH_BEFORE_SUCCEEDED = "after_main_publish_before_succeeded"
    AFTER_SUCCEEDED_BEFORE_PRIVATE_REF_CLEANUP = "after_succeeded_before_private_ref_cleanup"
    AFTER_SUCCEEDED_BEFORE_ARTIFACT_CLEANUP = "after_succeeded_before_artifact_cleanup"


class ImportWorkerFaultInjector(Protocol):
    def maybe_raise(self, point: ImportWorkerFaultPoint) -> None:
        """Raise when the configured point matches."""


class NoOpImportWorkerFaultInjector:
    """Default production injector that never injects faults."""

    def maybe_raise(self, point: ImportWorkerFaultPoint) -> None:
        return None


class ConfigurableImportWorkerFaultInjector:
    """Test-only injector configured with explicit fault points."""

    def __init__(self, *, points: frozenset[ImportWorkerFaultPoint] = frozenset()) -> None:
        self._points = points

    def maybe_raise(self, point: ImportWorkerFaultPoint) -> None:
        if point in self._points:
            raise RuntimeError(f"injected fault at {point.value}")
