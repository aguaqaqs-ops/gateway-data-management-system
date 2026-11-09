"""SQLite derived indexes and cooperative ArtifactStore read leases."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, ContextManager

import pyarrow as pa
from gateway_shared_kernel import CanonicalEncodingError, DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts.computation_cache import (
    CACHE_ACTIVE_INTENT, COMPUTATION_CACHE_TTL_SECONDS, MAX_CACHE_MEMBER_REFS_BYTES,
    CacheOperationOwner, CacheReserve, ComputationCacheArtifactStore,
    ComputationCacheEntry, ComputationCacheKey, ComputationCacheKind,
    InvalidComputationCachePayload, decode_cache_manifest,
)
from gateway_backend.artifacts.serialize import artifact_ref_from_dict, artifact_ref_to_dict
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.infrastructure.control_db.sqlite_protection import SQLiteArtifactProtectionStore

if TYPE_CHECKING:
    from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork

_PRUNE_LIMIT = 64
_TOUCH_LIMIT = 64
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_DB_METADATA_BYTES = MAX_CACHE_MEMBER_REFS_BYTES * 64
_ROW_COLUMNS = """manifest_artifact_id, manifest_media_type, manifest_size_bytes,
                  manifest_raw_sha256, member_refs_json, format, expires_at_us"""


def _epoch_us(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("cache clock must be an aware UTC datetime")
    delta = value - _EPOCH
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def _values(key: ComputationCacheKey) -> tuple[str, str, str]:
    return key.repository_id, key.kind.value, key.task_digest.value


def _ttl_owner(values: tuple[str, str, str]) -> tuple[str, str]:
    repository, kind, digest = values
    return (f"{kind}-table-cache",
            "computation-" + hashlib.sha256("\0".join((repository, kind, digest)).encode()).hexdigest())


def _member_json(entry: ComputationCacheEntry) -> str:
    raw = canonicalize_json_value([artifact_ref_to_dict(ref) for ref in entry.member_refs])
    if len(raw) > MAX_CACHE_MEMBER_REFS_BYTES:
        raise ValueError("cache member reference document exceeds bound")
    return raw.decode()


def _text(value: object) -> str:
    if type(value) is not str:
        raise ValueError("cache text field is malformed")
    return value


def _integer(value: object) -> int:
    if type(value) is not int:
        raise ValueError("cache integer field is malformed")
    return value


def _entry_from_row(key: ComputationCacheKey, row: tuple[object, ...]) -> ComputationCacheEntry:
    try:
        return _parse_entry_row(key, row)
    except (TypeError, ValueError, RecursionError, CanonicalEncodingError):
        raise InvalidComputationCachePayload("invalid computation cache index payload") from None


def _parse_entry_row(key: ComputationCacheKey, row: tuple[object, ...]) -> ComputationCacheEntry:
    raw_members = _text(row[4])
    if len(raw_members.encode()) > MAX_CACHE_MEMBER_REFS_BYTES:
        raise ValueError("cache member references exceed bound")
    members = json.loads(raw_members)
    if (not isinstance(members, list) or len(members) > 7
            or any(not isinstance(ref, dict) for ref in members)
            or canonicalize_json_value(members).decode() != raw_members):
        raise ValueError("cache member references are malformed")
    return ComputationCacheEntry(
        key, _text(row[5]),
        ArtifactRef(_text(row[0]), _text(row[1]), _integer(row[2]), DigestRef(_text(row[3]))),
        tuple(artifact_ref_from_dict(ref) for ref in members),
    )


class SQLiteComputationCache:
    """Only bounded SQL; no hashing, artifact reads or computation in the transaction."""

    def __init__(
        self, connection: sqlite3.Connection, *, protection: SQLiteArtifactProtectionStore,
        now: datetime, read_only: bool = False,
        ttl: timedelta = timedelta(seconds=COMPUTATION_CACHE_TTL_SECONDS),
    ) -> None:
        if not connection.in_transaction:
            raise RuntimeError("computation cache requires an active transaction")
        if ttl.total_seconds() <= 0:
            raise ValueError("cache TTL must be positive")
        self._connection = connection
        self._protection = protection
        self._now = now
        self._now_us = _epoch_us(now)
        self._expires_us = _epoch_us(now + ttl)
        self._read_only = read_only

    def _writable(self) -> None:
        if self._read_only:
            raise RuntimeError("computation cache is read-only in this transaction")

    def lookup_and_pin(
        self, key: ComputationCacheKey, owner: CacheOperationOwner,
    ) -> ComputationCacheEntry | None:
        self._writable()
        self.prune_expired()
        row = self._connection.execute(
            f"SELECT {_ROW_COLUMNS} FROM computation_cache_entries "
            "WHERE repository_id=? AND kind=? AND task_digest=? AND expires_at_us>?",
            (*_values(key), self._now_us),
        ).fetchone()
        if row is None:
            return None
        original = tuple(row)
        try:
            entry = _entry_from_row(key, original)
        except InvalidComputationCachePayload:
            self._discard_row(_values(key), original)
            return None
        self.pin_refs(entry, owner)
        return entry

    def pin_refs(self, entry: ComputationCacheEntry, owner: CacheOperationOwner) -> None:
        self._writable()
        for ref in entry.refs:
            # Existing workflow protection under the same operation takes
            # precedence. Batch release removes only our own cache intent.
            self._connection.execute(
                """INSERT INTO artifact_protection_intents
                   (artifact_id,owner_kind,owner_id,intent,recorded_at_us)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(artifact_id,owner_kind,owner_id) DO NOTHING""",
                (ref.artifact_id, owner.owner_kind, owner.operation_id,
                 CACHE_ACTIVE_INTENT, self._now_us),
            )

    def release_operation_pins(self, owner: CacheOperationOwner) -> int:
        self._writable()
        return self._protection.clear_protection_intent(
            owner_kind=owner.owner_kind, owner_id=owner.operation_id,
            intent=CACHE_ACTIVE_INTENT,
        )

    def store(self, entry: ComputationCacheEntry, owner: CacheOperationOwner) -> None:
        self._writable()
        self.prune_expired()
        member_json = _member_json(entry)
        owner_kind, owner_id = _ttl_owner(_values(entry.key))
        self._protection.clear_protection(owner_kind=owner_kind, owner_id=owner_id)
        ref = entry.manifest_ref
        self._connection.execute(
            """INSERT INTO computation_cache_entries
               (repository_id,kind,task_digest,manifest_artifact_id,manifest_media_type,
                manifest_size_bytes,manifest_raw_sha256,member_refs_json,format,expires_at_us)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(repository_id,kind,task_digest) DO UPDATE SET
                 manifest_artifact_id=excluded.manifest_artifact_id,
                 manifest_media_type=excluded.manifest_media_type,
                 manifest_size_bytes=excluded.manifest_size_bytes,
                 manifest_raw_sha256=excluded.manifest_raw_sha256,
                 member_refs_json=excluded.member_refs_json,format=excluded.format,
                 expires_at_us=excluded.expires_at_us""",
            (*_values(entry.key), ref.artifact_id, ref.media_type, ref.size_bytes,
             ref.raw_sha256.value, member_json, entry.format, self._expires_us),
        )
        self._touch(entry)
        self._record_use(entry, owner.operation_id)

    def mark_used(self, entry: ComputationCacheEntry, owner: CacheOperationOwner) -> bool:
        self._writable()
        if not self._is_current(entry):
            return False
        self._touch(entry)
        self._record_use(entry, owner.operation_id)
        return True

    def _is_current(self, entry: ComputationCacheEntry) -> bool:
        row = self._connection.execute(
            f"SELECT {_ROW_COLUMNS} FROM computation_cache_entries "
            "WHERE repository_id=? AND kind=? AND task_digest=? AND expires_at_us>?",
            (*_values(entry.key), self._now_us),
        ).fetchone()
        if row is None:
            return False
        return tuple(row)[:6] == self._entry_row(entry)

    @staticmethod
    def _entry_row(entry: ComputationCacheEntry) -> tuple[object, ...]:
        ref = entry.manifest_ref
        return (ref.artifact_id, ref.media_type, ref.size_bytes, ref.raw_sha256.value,
                _member_json(entry), entry.format)

    def discard_if_same(self, entry: ComputationCacheEntry) -> bool:
        self._writable()
        return self._discard_row(_values(entry.key), self._entry_row(entry))

    def _discard_row(self, key: tuple[str, str, str], row: tuple[object, ...]) -> bool:
        deleted = self._connection.execute(
            """DELETE FROM computation_cache_entries
               WHERE repository_id=? AND kind=? AND task_digest=?
                 AND manifest_artifact_id IS ? AND manifest_media_type IS ?
                 AND manifest_size_bytes IS ? AND manifest_raw_sha256 IS ?
                 AND member_refs_json IS ? AND format IS ?""", (*key, *row[:6]),
        ).rowcount
        if deleted:
            owner_kind, owner_id = _ttl_owner(key)
            self._protection.clear_protection(owner_kind=owner_kind, owner_id=owner_id)
        return bool(deleted)

    def _touch(self, entry: ComputationCacheEntry) -> None:
        self._connection.execute(
            """UPDATE computation_cache_entries SET expires_at_us=?
               WHERE repository_id=? AND kind=? AND task_digest=?""",
            (self._expires_us, *_values(entry.key)),
        )
        owner_kind, owner_id = _ttl_owner(_values(entry.key))
        for ref in entry.refs:
            self._connection.execute(
                """INSERT INTO artifact_protection_intents
                   (artifact_id,owner_kind,owner_id,intent,recorded_at_us,expires_at_us)
                   VALUES (?,?,?,'ttl-cache',?,?)
                   ON CONFLICT(artifact_id,owner_kind,owner_id) DO UPDATE SET
                     recorded_at_us=excluded.recorded_at_us,expires_at_us=excluded.expires_at_us""",
                (ref.artifact_id, owner_kind, owner_id, self._now_us, self._expires_us),
            )

    def _record_use(self, entry: ComputationCacheEntry, producer_operation_id: str) -> None:
        self._connection.execute(
            """INSERT INTO computation_cache_uses
               (producer_operation_id,repository_id,kind,task_digest,manifest_artifact_id,expires_at_us)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(producer_operation_id,repository_id,kind,task_digest) DO UPDATE SET
                 manifest_artifact_id=excluded.manifest_artifact_id,
                 expires_at_us=excluded.expires_at_us""",
            (producer_operation_id, *_values(entry.key), entry.manifest_ref.artifact_id, self._expires_us),
        )

    def prune_expired(self) -> None:
        self._writable()
        rows = self._connection.execute(
            """SELECT repository_id,kind,task_digest FROM computation_cache_entries
               WHERE expires_at_us<=? ORDER BY expires_at_us LIMIT ?""",
            (self._now_us, _PRUNE_LIMIT),
        ).fetchall()
        for repository, kind, digest in rows:
            key = (repository, kind, digest)
            self._connection.execute(
                "DELETE FROM computation_cache_entries WHERE repository_id=? AND kind=? AND task_digest=?",
                key,
            )
            owner_kind, owner_id = _ttl_owner(key)
            self._protection.clear_protection(owner_kind=owner_kind, owner_id=owner_id)
        self._connection.execute(
            """DELETE FROM computation_cache_uses WHERE rowid IN
               (SELECT rowid FROM computation_cache_uses WHERE expires_at_us<=?
                ORDER BY expires_at_us LIMIT ?)""", (self._now_us, _PRUNE_LIMIT),
        )

    def touch_producer(self, *, producer_operation_id: str, repository_id: str) -> int:
        """D's optional T3 participant; caller owns its narrow SAVEPOINT."""
        self._writable()
        rows = self._connection.execute(
            """SELECT u.kind,u.task_digest,u.manifest_artifact_id FROM computation_cache_uses u
               JOIN computation_cache_entries e ON e.repository_id=u.repository_id
                 AND e.kind=u.kind AND e.task_digest=u.task_digest
                 AND e.manifest_artifact_id=u.manifest_artifact_id
               WHERE u.producer_operation_id=? AND u.repository_id=?
                 AND u.expires_at_us>? AND e.expires_at_us>?
               ORDER BY u.kind,u.task_digest LIMIT ?""",
            (producer_operation_id, repository_id, self._now_us, self._now_us, _TOUCH_LIMIT),
        ).fetchall()
        touched = 0
        for kind, digest, manifest_id in rows:
            try:
                key = ComputationCacheKey(repository_id, ComputationCacheKind(kind), DigestRef(digest))
            except (TypeError, ValueError, CanonicalEncodingError):
                raise InvalidComputationCachePayload("invalid computation cache use payload") from None
            row = self._connection.execute(
                f"SELECT {_ROW_COLUMNS} FROM computation_cache_entries "
                "WHERE repository_id=? AND kind=? AND task_digest=? AND expires_at_us>? "
                "AND manifest_artifact_id=?", (*_values(key), self._now_us, manifest_id),
            ).fetchone()
            if row is None:
                continue
            entry = _entry_from_row(key, tuple(row))
            self._touch(entry)
            self._record_use(entry, producer_operation_id)
            touched += 1
        return touched


def _retained_metadata_bytes(entry: ComputationCacheEntry) -> int:
    fields = (entry.key.repository_id, entry.key.task_digest.value, entry.format)
    size = 64 * 1024 + sum(len(value) * 64 for value in fields)
    for ref in entry.refs:
        size += 4096 + (len(ref.artifact_id) + len(ref.media_type) + len(ref.raw_sha256.value)) * 64
    return size + entry.manifest_ref.size_bytes * 64


class _ReadLease:
    def __init__(
        self, cache: ControlDbComputationCache, entry: ComputationCacheEntry,
        owner: CacheOperationOwner, payload: dict[str, object], stack: ExitStack,
        checkpoint: Callable[[], None], reserve: CacheReserve,
    ) -> None:
        self._cache = cache
        self._entry = entry
        self._owner = owner
        self._payload: dict[str, object] | None = payload
        self._stack: ExitStack | None = stack
        self._checkpoint = checkpoint
        self._reserve = reserve

    @property
    def entry(self) -> ComputationCacheEntry:
        return self._entry

    @property
    def payload(self) -> dict[str, object]:
        if self._payload is None:
            raise RuntimeError("cache lease is closed")
        return self._payload

    @contextmanager
    def open_buffer(self, ref: ArtifactRef) -> Iterator[pa.Buffer]:
        self._require_open()
        if ref not in self._entry.member_refs:
            raise ValueError("cache buffer is outside the registered member closure")
        self._checkpoint()
        with self._cache._store.open_buffer(ref, checkpoint=self._checkpoint) as buffer:
            yield buffer

    def mark_used(self) -> bool:
        self._require_open()
        self._checkpoint()
        with ExitStack() as reservations:
            try:
                reservations.enter_context(self._reserve(_DB_METADATA_BYTES))
            except MemoryError:
                return False
            with self._cache._uow() as uow:
                return uow.computation_cache.mark_used(self._entry, self._owner)

    def discard(self) -> bool:
        self._require_open()
        return self._cache.discard_if_same(self._entry)

    def close(self) -> None:
        stack, self._stack = self._stack, None
        self._payload = None
        if stack is not None:
            stack.close()

    def _require_open(self) -> None:
        if self._stack is None:
            raise RuntimeError("cache lease is closed")


class ControlDbComputationCache:
    """Root borrow always precedes DB mutation; hashes never hold a DB transaction."""

    def __init__(
        self, unit_of_work_factory: Callable[[], ContextManager[ControlDbUnitOfWork]],
        store: ComputationCacheArtifactStore,
    ) -> None:
        self._uow = unit_of_work_factory
        self._store = store

    def lookup_and_pin(
        self, key: ComputationCacheKey, *, owner: CacheOperationOwner,
        checkpoint: Callable[[], None], reserve: CacheReserve,
    ) -> _ReadLease | None:
        checkpoint()
        stack = ExitStack()
        entry = None
        try:
            stack.enter_context(self._store.read_session())
            with reserve(_DB_METADATA_BYTES):
                with self._uow() as uow:
                    entry = uow.computation_cache.lookup_and_pin(key, owner)
                if entry is None:
                    stack.close()
                    return None
                # Transfer the small parsed entry before releasing the DB input
                # precharge; retain manifest expansion through the last consumer.
                stack.enter_context(reserve(_retained_metadata_bytes(entry)))
            with reserve(64 * 1024):
                chunks = []
                for chunk in self._store.read_exact(entry.manifest_ref):
                    checkpoint()
                    chunks.append(chunk)
                raw = b"".join(chunks)
                payload = decode_cache_manifest(raw, entry)
                del chunks, raw
                for ref in entry.member_refs:
                    for _chunk in self._store.read_exact(ref):
                        checkpoint()
            checkpoint()
            return _ReadLease(self, entry, owner, payload, stack, checkpoint, reserve)
        except (InterruptedError, TimeoutError):
            stack.close()
            raise
        except MemoryError:
            stack.close()
            return None
        except (ManifestVerificationError, InvalidComputationCachePayload, OSError):
            try:
                if entry is not None:
                    self.discard_if_same(entry)
            finally:
                stack.close()
            return None
        except BaseException:
            stack.close()
            raise

    def store(
        self, entry: ComputationCacheEntry, blobs: tuple[tuple[ArtifactRef, bytes], ...], *,
        owner: CacheOperationOwner, checkpoint: Callable[[], None], reserve: CacheReserve,
    ) -> bool:
        checkpoint()
        try:
            with self._store.read_session(), reserve(
                _DB_METADATA_BYTES + _retained_metadata_bytes(entry) + 64 * 1024,
            ):
                try:
                    if tuple(ref for ref, _raw in blobs) != entry.refs:
                        raise ValueError("cache writes require the exact complete reference closure")
                except (TypeError, ValueError):
                    return False
                for ref, raw in blobs:
                    checkpoint()
                    try:
                        if len(raw) != ref.size_bytes or raw_blob_digest(raw) != ref.raw_sha256:
                            raise ValueError("cache candidate bytes differ from their reference")
                    except (TypeError, ValueError, CanonicalEncodingError):
                        return False
                    checkpoint()
                try:
                    _member_json(entry)
                    decode_cache_manifest(blobs[0][1], entry)
                except (InvalidComputationCachePayload, TypeError, ValueError, CanonicalEncodingError):
                    return False
                checkpoint()
                with self._uow() as uow:
                    uow.computation_cache.pin_refs(entry, owner)
                for ref, raw in blobs:
                    checkpoint()
                    self._store.put(raw, ref)
                for ref in entry.refs:
                    for _chunk in self._store.read_exact(ref):
                        checkpoint()
                checkpoint()
                with self._uow() as uow:
                    uow.computation_cache.store(entry, owner)
                return True
        except (InterruptedError, TimeoutError):
            raise
        except (ManifestVerificationError, OSError, MemoryError):
            # Optional candidate failure leaves no partial index. Existing
            # operation pins are released by the operation's normal finally.
            return False

    def discard_if_same(self, entry: ComputationCacheEntry) -> bool:
        with self._uow() as uow:
            return uow.computation_cache.discard_if_same(entry)

    def release_operation_pins(self, owner: CacheOperationOwner) -> int:
        with self._uow() as uow:
            return uow.computation_cache.release_operation_pins(owner)
