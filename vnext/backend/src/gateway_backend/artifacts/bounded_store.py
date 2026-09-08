"""Bounded artifact store port for upload/preview publication."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts.types import ArtifactRef


class CleanupClassification(StrEnum):
    PROTECTED = "protected"
    ELIGIBLE_AFTER = "eligible_after"
    MANUAL_REVIEW = "manual_review"


class DeleteDisposition(StrEnum):
    DELETED = "deleted"
    ABSENT = "absent"
    RETRYABLE_FAILURE = "retryable_failure"


@dataclass(frozen=True, slots=True)
class CleanupDecision:
    classification: CleanupClassification
    eligible_after: datetime | None = None


@dataclass(frozen=True, slots=True)
class VerifyReadableResult:
    verified: bool
    reason: str | None = None


@runtime_checkable
class BoundedArtifactStorePort(Protocol):
    def put_stream(
        self,
        kind: str,
        stream: Iterable[bytes],
        *,
        declared_size: int,
        declared_raw_sha256: DigestRef,
        media_type: str,
    ) -> ArtifactRef:
        """Persist bounded bytes and return the exact minimal ref."""

    def read_exact(self, ref: ArtifactRef) -> Iterator[bytes]:
        """Return bounded chunks for one exact ref."""

    def verify_readable(
        self,
        ref: ArtifactRef,
        *,
        expected_size: int,
        expected_raw_sha256: DigestRef,
    ) -> VerifyReadableResult:
        """Read back bytes and verify declared integrity."""

    def set_protection(
        self,
        refs: Iterable[ArtifactRef],
        *,
        owner_kind: str,
        owner_id: str,
        intent: str,
    ) -> bool:
        """Record protection intent; returns False when idempotent replay."""

    def classify_cleanup(self, ref: ArtifactRef, now: datetime) -> CleanupDecision:
        """Classify one artifact for bounded cleanup eligibility."""

    def delete_eligible(
        self,
        ref: ArtifactRef,
        *,
        expected_classification: CleanupClassification,
        now: datetime,
    ) -> DeleteDisposition:
        """Delete one artifact only when cleanup classification still matches."""
