"""Filesystem-backed bounded artifact store with digest read-back and cleanup."""

from __future__ import annotations

from gateway_backend.artifacts.location import ArtifactLocation

import secrets
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager, nullcontext

import pyarrow as pa
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
from typing import ContextManager
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.infrastructure.artifact_store.scratch import ScratchFile

DEFAULT_UNPINNED_TTL = timedelta(hours=24)
_STREAM_CHUNK_SIZE = 64 * 1024


class BoundedArtifactStore:
    """Publish bounded bytes and classify cleanup without exposing host paths."""

    def __init__(
        self,
        local_store: LocalArtifactStore,
        *,
        protection_uow: Callable[[], ContextManager[ControlDbUnitOfWork]] | None = None,
        unpinned_ttl: timedelta = DEFAULT_UNPINNED_TTL,
    ) -> None:
        self._local_store = local_store
        self._protection_uow = protection_uow
        self._unpinned_ttl = unpinned_ttl
        self._published_at_by_artifact_id: dict[str, datetime] = {}

    def put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
        published = self._local_store.put(raw_bytes, ref)
        self._published_at_by_artifact_id[published.artifact_id] = datetime.now(UTC)
        return published

    def restore_canonical_from_exact_commit(
        self, raw_bytes: bytes, ref: ArtifactRef, *, checkpoint: Callable[[], None],
    ) -> ArtifactRef:
        return self._local_store.restore_canonical_from_exact_commit(raw_bytes, ref, checkpoint=checkpoint)

    def locate(self, ref: ArtifactRef) -> bytes:
        return self._local_store.locate(ref)

    @contextmanager
    def open_buffer(self, ref: ArtifactRef, *, checkpoint: Callable[[], None] | None = None) -> Iterator[pa.Buffer]:
        with self._local_store.open_buffer(ref, checkpoint=checkpoint) as buffer:
            yield buffer

    def get_ref(self, artifact_id: str) -> ArtifactRef:
        return self._local_store.get_ref(artifact_id)

    def put_stream(
        self,
        location: ArtifactLocation,
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
        artifact_id = build_artifact_id(location, kind, secrets.token_hex(16))
        validate_artifact_id(artifact_id)
        ref = ArtifactRef(artifact_id=artifact_id, media_type=media_type,
            size_bytes=declared_size, raw_sha256=declared_raw_sha256)
        published = self._local_store.put_chunks(stream, ref)
        self._published_at_by_artifact_id[published.artifact_id] = datetime.now(UTC)
        return published

    def read_exact(self, ref: ArtifactRef) -> Iterator[bytes]:
        return self._local_store.read_exact(ref)

    @contextmanager
    def read_session(self) -> Iterator[None]:
        with self._local_store.read_session():
            yield

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
        if self._protection_uow is None:
            raise RuntimeError("protection store is not configured")
        when = recorded_at or datetime.now(UTC)
        with self.read_session(), self._protection_uow() as uow:
            return uow.protection.set_protection(tuple(refs), owner_kind=owner_kind,
                owner_id=owner_id, intent=intent, recorded_at=when)

    def put_from_path(
        self, source: ScratchFile, ref: ArtifactRef, *, checkpoint: Callable[[], None], byte_limit: int,
    ) -> ArtifactRef:
        published = self._local_store.put_from_path(source, ref, checkpoint=checkpoint, byte_limit=byte_limit)
        self._published_at_by_artifact_id[published.artifact_id] = datetime.now(UTC)
        return published

    def classify_cleanup(self, ref: ArtifactRef, now: datetime) -> CleanupDecision:
        with self.read_session():
            with nullcontext(None) if self._protection_uow is None else self._protection_uow() as uow:
                protected = uow is not None and uow.protection.is_protected(ref.artifact_id)
            return self._classify(ref, now, protected=protected)

    def _classify(self, ref: ArtifactRef, now: datetime, *, protected: bool) -> CleanupDecision:
        if protected:
            return CleanupDecision(classification=CleanupClassification.PROTECTED)
        try:
            published_at = self._published_at_by_artifact_id.get(ref.artifact_id)
            if published_at is None:
                published_at = self._local_store.published_at(ref)
        except FileNotFoundError:
            return CleanupDecision(classification=CleanupClassification.ELIGIBLE_AFTER)
        eligible_after = published_at + self._unpinned_ttl
        return CleanupDecision(classification=CleanupClassification.ELIGIBLE_AFTER if now >= eligible_after
            else CleanupClassification.MANUAL_REVIEW, eligible_after=eligible_after)

    def delete_eligible(
        self, ref: ArtifactRef, *, expected_classification: CleanupClassification, now: datetime,
    ) -> DeleteDisposition:
        try:
            with self._local_store.cleanup_session(ref.artifact_id) as acquired:
                if not acquired:
                    return DeleteDisposition.RETRYABLE_FAILURE
                # This factory deliberately opens only the short DB transaction.
                # A protection UoW would acquire SH after EX and invert the order.
                with nullcontext(None) if self._protection_uow is None else self._protection_uow() as uow:
                    protected = uow is not None and uow.protection.is_protected(ref.artifact_id)
                    decision = self._classify(ref, now, protected=protected)
                    if decision.classification is not expected_classification or decision.classification is not CleanupClassification.ELIGIBLE_AFTER:
                        return DeleteDisposition.RETRYABLE_FAILURE
                    deleted = self._local_store.delete_object(ref)
                if deleted:
                    self._published_at_by_artifact_id.pop(ref.artifact_id, None)
                return DeleteDisposition.DELETED if deleted else DeleteDisposition.ABSENT
        except (OSError, ManifestVerificationError):
            return DeleteDisposition.RETRYABLE_FAILURE


def artifact_binding_from_ref(ref: ArtifactRef) -> SourceArtifactBinding:
    return SourceArtifactBinding(
        artifact_id=ref.artifact_id,
        media_type=ref.media_type,
        size_bytes=ref.size_bytes,
        raw_sha256=ref.raw_sha256.value,
    )
