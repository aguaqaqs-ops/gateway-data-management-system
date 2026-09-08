"""Filesystem-backed bounded artifact store with digest read-back and cleanup."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime, timedelta

from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.artifacts.bounded_store import (
    CleanupClassification,
    CleanupDecision,
    DeleteDisposition,
    VerifyReadableResult,
)
from gateway_backend.artifacts.digest import build_artifact_id
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.artifacts.types import ArtifactRef, validate_artifact_id
from gateway_backend.domain.workspace.models import SourceArtifactBinding
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore
from gateway_backend.infrastructure.artifact_store.protection import SQLiteArtifactProtectionStore

DEFAULT_UNPINNED_TTL = timedelta(hours=24)
_STREAM_CHUNK_SIZE = 64 * 1024


class BoundedArtifactStore:
    """Publish bounded bytes and classify cleanup without exposing host paths."""

    def __init__(
        self,
        local_store: LocalArtifactStore,
        *,
        protection_store: SQLiteArtifactProtectionStore | None = None,
        unpinned_ttl: timedelta = DEFAULT_UNPINNED_TTL,
    ) -> None:
        self._local_store = local_store
        self._protection_store = protection_store
        self._unpinned_ttl = unpinned_ttl
        self._published_at_by_artifact_id: dict[str, datetime] = {}

    def put_stream(
        self,
        kind: str,
        stream: Iterable[bytes],
        *,
        declared_size: int,
        declared_raw_sha256: DigestRef,
        media_type: str,
    ) -> ArtifactRef:
        if type(kind) is not str or not kind:
            raise ValueError("kind must be a non-empty string")
        if type(declared_size) is not int or declared_size < 0:
            raise ValueError("declared_size must be a non-negative integer")
        if type(media_type) is not str or not media_type:
            raise ValueError("media_type must be a non-empty string")
        raw_bytes, digest = _consume_bounded_stream(
            stream,
            declared_size=declared_size,
            declared_raw_sha256=declared_raw_sha256,
        )
        artifact_id = build_artifact_id(kind, secrets.token_hex(8))
        validate_artifact_id(artifact_id)
        ref = ArtifactRef(
            artifact_id=artifact_id,
            media_type=media_type,
            size_bytes=len(raw_bytes),
            raw_sha256=digest,
        )
        published = self._local_store.put(raw_bytes, ref)
        self._published_at_by_artifact_id[published.artifact_id] = datetime.now(UTC)
        return published

    def read_exact(self, ref: ArtifactRef) -> Iterator[bytes]:
        raw_bytes = self._local_store.locate(ref)
        for offset in range(0, len(raw_bytes), _STREAM_CHUNK_SIZE):
            yield raw_bytes[offset : offset + _STREAM_CHUNK_SIZE]

    def verify_readable(
        self,
        ref: ArtifactRef,
        *,
        expected_size: int,
        expected_raw_sha256: DigestRef,
    ) -> VerifyReadableResult:
        try:
            raw_bytes = self._local_store.locate(ref)
        except ManifestVerificationError as exc:
            return VerifyReadableResult(verified=False, reason=str(exc))
        if len(raw_bytes) != expected_size:
            return VerifyReadableResult(verified=False, reason="size_bytes mismatch")
        if raw_blob_digest(raw_bytes).value != expected_raw_sha256.value:
            return VerifyReadableResult(verified=False, reason="raw_sha256 mismatch")
        return VerifyReadableResult(verified=True)

    def set_protection(
        self,
        refs: Iterable[ArtifactRef],
        *,
        owner_kind: str,
        owner_id: str,
        intent: str,
        recorded_at: datetime | None = None,
    ) -> bool:
        if self._protection_store is None:
            raise RuntimeError("protection store is not configured")
        when = recorded_at or datetime.now(UTC)
        return self._protection_store.set_protection(
            tuple(refs),
            owner_kind=owner_kind,
            owner_id=owner_id,
            intent=intent,
            recorded_at=when,
        )

    def classify_cleanup(self, ref: ArtifactRef, now: datetime) -> CleanupDecision:
        if self._protection_store is not None and self._protection_store.is_protected(ref.artifact_id):
            return CleanupDecision(classification=CleanupClassification.PROTECTED)
        published_at = self._artifact_published_at(ref)
        eligible_after = published_at + self._unpinned_ttl
        if now >= eligible_after:
            return CleanupDecision(
                classification=CleanupClassification.ELIGIBLE_AFTER,
                eligible_after=eligible_after,
            )
        return CleanupDecision(
            classification=CleanupClassification.MANUAL_REVIEW,
            eligible_after=eligible_after,
        )

    def delete_eligible(
        self,
        ref: ArtifactRef,
        *,
        expected_classification: CleanupClassification,
        now: datetime,
    ) -> DeleteDisposition:
        decision = self.classify_cleanup(ref, now)
        if decision.classification is CleanupClassification.PROTECTED:
            return DeleteDisposition.RETRYABLE_FAILURE
        if decision.classification is not expected_classification:
            return DeleteDisposition.RETRYABLE_FAILURE
        if decision.classification is not CleanupClassification.ELIGIBLE_AFTER:
            return DeleteDisposition.RETRYABLE_FAILURE
        target, sidecar = self._local_store._validated_paths(ref.artifact_id)  # noqa: SLF001
        deleted = False
        if target.is_file():
            target.unlink()
            deleted = True
        if sidecar.is_file():
            sidecar.unlink()
            deleted = True
        if not deleted:
            return DeleteDisposition.ABSENT
        self._local_store._refs_by_artifact_id.pop(ref.artifact_id, None)  # noqa: SLF001
        return DeleteDisposition.DELETED

    def _artifact_published_at(self, ref: ArtifactRef) -> datetime:
        recorded = self._published_at_by_artifact_id.get(ref.artifact_id)
        if recorded is not None:
            return recorded
        target, _sidecar = self._local_store._validated_paths(ref.artifact_id)  # noqa: SLF001
        if not target.is_file():
            raise ManifestVerificationError("artifact bytes are missing")
        mtime = target.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=UTC)


def _consume_bounded_stream(
    stream: Iterable[bytes],
    *,
    declared_size: int,
    declared_raw_sha256: DigestRef,
) -> tuple[bytes, DigestRef]:
    hasher = hashlib.sha256()
    chunks: list[bytes] = []
    total = 0
    for chunk in stream:
        if type(chunk) is not bytes:
            raise ManifestVerificationError("stream chunks must be bytes")
        total += len(chunk)
        if total > declared_size:
            raise ManifestVerificationError("stream exceeds declared_size")
        hasher.update(chunk)
        chunks.append(chunk)
    raw_bytes = b"".join(chunks)
    if len(raw_bytes) != declared_size:
        raise ManifestVerificationError("stream shorter than declared_size")
    digest = raw_blob_digest(raw_bytes)
    if digest.value != declared_raw_sha256.value:
        raise ManifestVerificationError("declared_raw_sha256 mismatch")
    return raw_bytes, digest


def artifact_binding_from_ref(ref: ArtifactRef) -> SourceArtifactBinding:
    return SourceArtifactBinding(
        artifact_id=ref.artifact_id,
        media_type=ref.media_type,
        size_bytes=ref.size_bytes,
        raw_sha256=ref.raw_sha256.value,
    )
