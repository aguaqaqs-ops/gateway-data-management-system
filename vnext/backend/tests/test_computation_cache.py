"""Derived cache transactions, reference closure, TTL and live filesystem borrows."""
from __future__ import annotations

from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id

import json
import sqlite3
from contextlib import closing, nullcontext
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ContextManager

import pytest
from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts.computation_cache import (
    COMPUTATION_CACHE_TTL_SECONDS,
    CacheOperationOwner,
    ComputationCacheEntry,
    ComputationCacheKey,
    ComputationCacheKind,
    InvalidComputationCachePayload,
    decode_cache_manifest,
    encode_cache_manifest,
)
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.infrastructure.artifact_store import LocalArtifactStore
from gateway_backend.infrastructure.control_db.computation_cache import ControlDbComputationCache
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork

pytestmark = pytest.mark.unit
NOW = datetime(2026, 11, 9, tzinfo=UTC)
PAYLOAD: dict[str, object] = {"complete": True, "answer": 42}
WRITER = CacheOperationOwner("preview-operation", "producer-1")
READER = CacheOperationOwner("history-compare-operation", "reader-1")
DEEP_JSON = "[" * 2000 + "0" + "]" * 2000


def _checkpoint() -> None:
    pass


def _reserve(_size: int) -> ContextManager[object]:
    return nullcontext()


def _ref(artifact_id: str, raw: bytes, media_type: str = "application/octet-stream") -> ArtifactRef:
    return ArtifactRef(build_artifact_id(ArtifactLocation.DURABLE, "test-fixture", artifact_id), media_type, len(raw), raw_blob_digest(raw))


def _value(
    seed: str = "first", *, kind: ComputationCacheKind = ComputationCacheKind.COMPARISON,
    task: bytes = b"complete-task",
) -> tuple[ComputationCacheEntry, tuple[tuple[ArtifactRef, bytes], ...]]:
    key = ComputationCacheKey("repository-1", kind, raw_blob_digest(task))
    members = tuple((
        _ref(f"cache-{seed}-member-{index}", raw), raw,
    ) for index, raw in enumerate(
        (b"first independent member", b"second independent member")
        if kind is ComputationCacheKind.COMPARISON else (b"complete candidate events",)
    ))
    refs = tuple(ref for ref, _raw in members)
    raw = encode_cache_manifest(key, format="fixture-cache/v1", member_refs=refs, payload=PAYLOAD)
    manifest = _ref(f"cache-{seed}-manifest", raw, "application/json")
    return ComputationCacheEntry(key, "fixture-cache/v1", manifest, refs), ((manifest, raw), *members)


@dataclass(slots=True)
class CacheFixture:
    db_path: Path
    local: LocalArtifactStore
    now: datetime = NOW

    def transaction(self) -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(self.db_path, now=lambda: self.now)

    def adapter(self) -> ControlDbComputationCache:
        return ControlDbComputationCache(unit_of_work_factory=self.transaction, store=self.local)

    def protected(self, refs: tuple[ArtifactRef, ...]) -> tuple[bool, ...]:
        with self.transaction() as uow:
            return tuple(uow.protection.is_protected(ref.artifact_id) for ref in refs)


@pytest.fixture
def cache_fixture(db_path: Path, tmp_path: Path) -> CacheFixture:
    return CacheFixture(db_path, LocalArtifactStore(tmp_path / "artifacts"))


@pytest.mark.parametrize("kind", tuple(ComputationCacheKind))
def test_complete_cache_value_is_scoped_and_uses_real_member_buffers(
    cache_fixture: CacheFixture, kind: ComputationCacheKind,
) -> None:
    cache = cache_fixture.adapter()
    entry, blobs = _value(kind=kind)
    assert cache.store(entry, blobs, owner=WRITER, checkpoint=_checkpoint, reserve=_reserve)
    cache.release_operation_pins(WRITER)
    wrong_keys = (
        replace(entry.key, repository_id="repository-2"),
        replace(entry.key, kind=(ComputationCacheKind.RISK if kind is ComputationCacheKind.COMPARISON
                                 else ComputationCacheKind.COMPARISON)),
        replace(entry.key, task_digest=raw_blob_digest(b"another-directed-task")),
    )
    for key in wrong_keys:
        assert cache.lookup_and_pin(key, owner=READER, checkpoint=_checkpoint, reserve=_reserve) is None
    lease = cache.lookup_and_pin(entry.key, owner=READER, checkpoint=_checkpoint, reserve=_reserve)
    assert lease is not None
    with closing(lease):
        assert lease.entry == entry and lease.payload == PAYLOAD
        for ref, raw in blobs[1:]:
            with lease.open_buffer(ref) as buffer:
                assert buffer.to_pybytes() == raw
        assert lease.mark_used()
    assert cache_fixture.protected(entry.refs) == (True,) * len(entry.refs)
    cache.release_operation_pins(READER)


MANIFEST_FAULTS = ("scope", "kind", "digest", "format", "members", "payload", "noncanonical", "deep")


@pytest.mark.parametrize("fault", MANIFEST_FAULTS)
def test_manifest_envelope_rejects_unregistered_scope_and_reference_closure(fault: str) -> None:
    entry, blobs = _value()
    raw = blobs[0][1]
    assert decode_cache_manifest(raw, entry) == PAYLOAD
    document = json.loads(raw)
    if fault == "scope":
        document["repository_id"] = "repository-2"
    elif fault == "kind":
        document["kind"] = "risk"
    elif fault == "digest":
        document["task_digest"] = raw_blob_digest(b"other-task").value
    elif fault == "format":
        document["format"] = "another-cache/v1"
    elif fault == "members":
        document["member_refs"] = []
    elif fault == "payload":
        document["payload"] = []
    if fault == "deep":
        corrupted = DEEP_JSON.encode()
    else:
        corrupted = raw + b"\n" if fault == "noncanonical" else canonicalize_json_value(document)
    with pytest.raises(InvalidComputationCachePayload):
        decode_cache_manifest(corrupted, entry)


FILE_FAULTS = ("member-missing", "member-raw", "manifest-missing", "manifest-raw", "member-index-deep")


@pytest.mark.parametrize("fault", FILE_FAULTS)
def test_bad_cache_file_discards_only_the_registered_value_and_closes_its_borrow(
    cache_fixture: CacheFixture, fault: str,
) -> None:
    cache = cache_fixture.adapter()
    entry, blobs = _value()
    healthy, healthy_blobs = _value("healthy", task=b"independent-healthy-task")
    assert cache.store(entry, blobs, owner=WRITER, checkpoint=_checkpoint, reserve=_reserve)
    assert cache.store(healthy, healthy_blobs, owner=WRITER, checkpoint=_checkpoint, reserve=_reserve)
    cache.release_operation_pins(WRITER)
    if fault == "member-index-deep":
        with cache_fixture.transaction() as uow:
            uow.connection.execute("""UPDATE computation_cache_entries SET member_refs_json=?
                WHERE repository_id=? AND kind=? AND task_digest=?""",
                (DEEP_JSON, entry.key.repository_id, entry.key.kind.value, entry.key.task_digest.value))
    else:
        target = entry.manifest_ref if fault.startswith("manifest") else entry.member_refs[0]
        path, _sidecar = cache_fixture.local._validated_paths(target.artifact_id)  # noqa: SLF001
        if fault.endswith("missing"):
            path.unlink()
        else:
            path.write_bytes(b"!" * target.size_bytes)
    assert cache.lookup_and_pin(entry.key, owner=READER, checkpoint=_checkpoint, reserve=_reserve) is None
    cache.release_operation_pins(READER)
    assert cache_fixture.protected(entry.refs) == (False,) * len(entry.refs)
    with cache_fixture.local.cleanup_session() as acquired:
        assert acquired
    lease = cache.lookup_and_pin(healthy.key, owner=READER, checkpoint=_checkpoint, reserve=_reserve)
    assert lease is not None
    with closing(lease):
        assert lease.entry == healthy
    cache.release_operation_pins(READER)
    with cache_fixture.transaction() as uow:
        assert [row[0] for row in uow.connection.execute(
            "SELECT manifest_artifact_id FROM computation_cache_entries",
        )] == [healthy.manifest_ref.artifact_id]


def test_successful_use_extends_ttl_from_transaction_time(cache_fixture: CacheFixture) -> None:
    cache = cache_fixture.adapter()
    entry, blobs = _value()
    assert cache.store(entry, blobs, owner=WRITER, checkpoint=_checkpoint, reserve=_reserve)
    cache.release_operation_pins(WRITER)
    cache_fixture.now = NOW + timedelta(seconds=COMPUTATION_CACHE_TTL_SECONDS - 1)
    lease = cache.lookup_and_pin(entry.key, owner=READER, checkpoint=_checkpoint, reserve=_reserve)
    assert lease is not None
    with closing(lease):
        assert lease.mark_used()
    cache.release_operation_pins(READER)
    cache_fixture.now = NOW + timedelta(seconds=COMPUTATION_CACHE_TTL_SECONDS + 1)
    lease = cache.lookup_and_pin(entry.key, owner=READER, checkpoint=_checkpoint, reserve=_reserve)
    assert lease is not None
    lease.close()
    cache.release_operation_pins(READER)
    # Opening a candidate without successful pair use does not restart its TTL.
    cache_fixture.now = NOW + timedelta(seconds=2 * COMPUTATION_CACHE_TTL_SECONDS)
    assert cache.lookup_and_pin(entry.key, owner=READER, checkpoint=_checkpoint, reserve=_reserve) is None
    assert cache_fixture.protected(entry.refs) == (False,) * len(entry.refs)


def test_overlapping_leases_close_before_narrow_operation_pin_release(
    cache_fixture: CacheFixture,
) -> None:
    cache = cache_fixture.adapter()
    entry, blobs = _value()
    assert cache.store(entry, blobs, owner=WRITER, checkpoint=_checkpoint, reserve=_reserve)
    cache.release_operation_pins(WRITER)
    with cache_fixture.transaction() as uow:
        uow.set_artifact_protection((entry.manifest_ref,), owner_kind=READER.owner_kind,
            owner_id=READER.operation_id, intent="workflow-checkpoint")
    first = cache.lookup_and_pin(entry.key, owner=READER, checkpoint=_checkpoint, reserve=_reserve)
    second = cache.lookup_and_pin(entry.key, owner=READER, checkpoint=_checkpoint, reserve=_reserve)
    assert first is not None and second is not None
    try:
        first.close()
        with cache_fixture.local.cleanup_session() as acquired:
            assert not acquired
        with second.open_buffer(entry.member_refs[0]) as buffer:
            assert buffer.to_pybytes() == blobs[1][1]
    finally:
        first.close()
        second.close()
    with cache_fixture.local.cleanup_session() as acquired:
        assert acquired
    cache_fixture.now = NOW + timedelta(seconds=COMPUTATION_CACHE_TTL_SECONDS + 1)
    assert cache.lookup_and_pin(entry.key, owner=READER, checkpoint=_checkpoint, reserve=_reserve) is None
    assert cache_fixture.protected(entry.refs) == (True,) * len(entry.refs)
    assert cache.release_operation_pins(READER) == len(entry.member_refs)
    assert cache_fixture.protected(entry.refs) == (True, False, False)
    with cache_fixture.transaction() as uow:
        assert uow.connection.execute(
            "SELECT intent FROM artifact_protection_intents WHERE artifact_id = ? AND owner_kind = ? AND owner_id = ?",
            (entry.manifest_ref.artifact_id, READER.owner_kind, READER.operation_id),
        ).fetchone()[0] == "workflow-checkpoint"


def test_stale_reader_cannot_discard_or_touch_a_new_writer(cache_fixture: CacheFixture) -> None:
    cache = cache_fixture.adapter()
    original, original_blobs = _value()
    replacement, replacement_blobs = _value("replacement")
    assert cache.store(original, original_blobs, owner=WRITER, checkpoint=_checkpoint, reserve=_reserve)
    cache.release_operation_pins(WRITER)
    stale = cache.lookup_and_pin(original.key, owner=READER, checkpoint=_checkpoint, reserve=_reserve)
    assert stale is not None
    try:
        assert cache.store(replacement, replacement_blobs, owner=WRITER, checkpoint=_checkpoint, reserve=_reserve)
        assert not stale.discard()
        assert not stale.mark_used()
        with stale.open_buffer(original.member_refs[0]) as buffer:
            assert buffer.to_pybytes() == original_blobs[1][1]
        current = cache.lookup_and_pin(original.key, owner=READER, checkpoint=_checkpoint, reserve=_reserve)
        assert current is not None
        with closing(current):
            assert current.entry == replacement
        assert not cache.discard_if_same(original)
        assert cache.discard_if_same(replacement)
        assert cache_fixture.protected(original.refs) == (True,) * len(original.refs)
    finally:
        stale.close()
        cache.release_operation_pins(READER)
        cache.release_operation_pins(WRITER)


def test_partial_file_write_never_publishes_an_index_or_use(
    cache_fixture: CacheFixture, monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = cache_fixture.adapter()
    entry, blobs = _value()
    real_put = cache_fixture.local.put
    written: list[ArtifactRef] = []

    def fail_last_member(raw: bytes, ref: ArtifactRef) -> ArtifactRef:
        assert cache_fixture.protected(entry.refs) == (True,) * len(entry.refs)
        if ref == entry.member_refs[-1]:
            raise ManifestVerificationError("injected last-member write failure")
        written.append(real_put(raw, ref))
        return ref

    monkeypatch.setattr(cache_fixture.local, "put", fail_last_member)
    assert not cache.store(entry, blobs, owner=WRITER, checkpoint=_checkpoint, reserve=_reserve)
    assert written
    assert cache.lookup_and_pin(entry.key, owner=READER, checkpoint=_checkpoint, reserve=_reserve) is None
    with cache_fixture.transaction() as uow:
        for table in ("computation_cache_entries", "computation_cache_uses"):
            assert uow.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    cache.release_operation_pins(WRITER)
    cache.release_operation_pins(READER)
    assert cache_fixture.protected(entry.refs) == (False,) * len(entry.refs)


def test_index_and_all_ttl_protection_share_the_caller_transaction(cache_fixture: CacheFixture) -> None:
    entry, _blobs = _value()
    with pytest.raises(RuntimeError, match="caller rollback"):
        with cache_fixture.transaction() as uow:
            uow.computation_cache.store(entry, WRITER)
            raise RuntimeError("caller rollback")
    with cache_fixture.transaction() as uow:
        for table in ("computation_cache_entries", "computation_cache_uses", "artifact_protection_intents"):
            assert uow.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
        uow.computation_cache.store(entry, WRITER)
        original_expiry = uow.connection.execute(
            "SELECT expires_at_us FROM computation_cache_entries",
        ).fetchone()[0]
    cache_fixture.now = NOW + timedelta(hours=12)
    with pytest.raises(RuntimeError, match="touch rollback"):
        with cache_fixture.transaction() as uow:
            assert uow.computation_cache.touch_producer(
                producer_operation_id=WRITER.operation_id, repository_id=entry.key.repository_id) == 1
            raise RuntimeError("touch rollback")
    with cache_fixture.transaction() as uow:
        assert uow.connection.execute(
            "SELECT expires_at_us FROM computation_cache_entries",
        ).fetchone()[0] == original_expiry
        assert uow.connection.execute(
            "SELECT expires_at_us FROM computation_cache_uses",
        ).fetchone()[0] == original_expiry
        assert {row[0] for row in uow.connection.execute(
            "SELECT expires_at_us FROM artifact_protection_intents",
        )} == {original_expiry}


def test_unknown_sql_failure_rolls_back_replacement_index_ttl_and_use(
    cache_fixture: CacheFixture,
) -> None:
    cache = cache_fixture.adapter()
    original, original_blobs = _value()
    replacement, replacement_blobs = _value("replacement")
    assert cache.store(original, original_blobs, owner=WRITER, checkpoint=_checkpoint, reserve=_reserve)
    cache.release_operation_pins(WRITER)
    original_lease = cache.lookup_and_pin(original.key, owner=READER, checkpoint=_checkpoint, reserve=_reserve)
    assert original_lease is not None
    with cache_fixture.transaction() as uow:
        uow.connection.execute("""CREATE TRIGGER fail_cache_use BEFORE INSERT ON computation_cache_uses
            BEGIN SELECT cache_test_missing_function(); END""")
    try:
        with pytest.raises(sqlite3.OperationalError, match="cache_test_missing_function"):
            cache.store(replacement, replacement_blobs, owner=WRITER, checkpoint=_checkpoint, reserve=_reserve)
        with pytest.raises(sqlite3.OperationalError, match="cache_test_missing_function"):
            original_lease.mark_used()
    finally:
        original_lease.close()
        with cache_fixture.transaction() as uow:
            uow.connection.execute("DROP TRIGGER fail_cache_use")
    lease = cache.lookup_and_pin(original.key, owner=READER, checkpoint=_checkpoint, reserve=_reserve)
    assert lease is not None
    with closing(lease):
        assert lease.entry == original
    cache.release_operation_pins(WRITER)
    cache.release_operation_pins(READER)
    assert cache_fixture.protected(original.refs) == (True,) * len(original.refs)
    assert cache_fixture.protected(replacement.refs) == (False,) * len(replacement.refs)
    with cache_fixture.transaction() as uow:
        assert {row[0] for row in uow.connection.execute(
            "SELECT manifest_artifact_id FROM computation_cache_uses",
        )} == {original.manifest_ref.artifact_id}


def test_producer_touch_matches_current_scope_and_manifest_only(cache_fixture: CacheFixture) -> None:
    current, _ = _value("current", task=b"current-task")
    replaced, _ = _value("old", task=b"replaced-task")
    replacement, _ = _value("new", task=b"replaced-task")
    missing, _ = _value("missing", task=b"missing-task")
    expired, _ = _value("expired", task=b"expired-task")
    other_writer = CacheOperationOwner("preview-operation", "producer-2")
    cache_fixture.now = NOW - timedelta(seconds=COMPUTATION_CACHE_TTL_SECONDS + 1)
    with cache_fixture.transaction() as uow:
        uow.computation_cache.store(expired, WRITER)
    cache_fixture.now = NOW
    with cache_fixture.transaction() as uow:
        for entry in (current, replaced, missing):
            uow.computation_cache.store(entry, WRITER)
        uow.computation_cache.store(replacement, other_writer)
        assert uow.computation_cache.discard_if_same(missing)
    cache_fixture.now = NOW + timedelta(hours=12)
    with cache_fixture.transaction() as uow:
        assert uow.computation_cache.touch_producer(
            producer_operation_id=WRITER.operation_id, repository_id="another-repository") == 0
        assert uow.computation_cache.touch_producer(
            producer_operation_id="another-producer", repository_id=current.key.repository_id) == 0
        assert uow.computation_cache.touch_producer(
            producer_operation_id=WRITER.operation_id, repository_id=current.key.repository_id) == 1
        rows = dict(uow.connection.execute(
            "SELECT manifest_artifact_id, expires_at_us FROM computation_cache_entries",
        ))
        assert rows[current.manifest_ref.artifact_id] > rows[replacement.manifest_ref.artifact_id]


def _seed_expiring_entries(cache_fixture: CacheFixture) -> tuple[ComputationCacheEntry, ...]:
    entries = []
    for index in range(65):
        cache_fixture.now = NOW + timedelta(seconds=index)
        entry, _ = _value(f"expiry-{index}", task=f"task-{index}".encode())
        with cache_fixture.transaction() as uow:
            uow.computation_cache.store(entry, WRITER)
        entries.append(entry)
    cache_fixture.now = NOW + timedelta(seconds=COMPUTATION_CACHE_TTL_SECONDS + 65)
    return tuple(entries)


def test_expiry_cleanup_removes_at_most_64_entries_and_uses_per_sweep(cache_fixture: CacheFixture) -> None:
    entries = _seed_expiring_entries(cache_fixture)
    with cache_fixture.transaction() as uow:
        uow.computation_cache.prune_expired()
        for table in ("computation_cache_entries", "computation_cache_uses"):
            assert uow.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1
    assert cache_fixture.protected(entries[-1].refs) == (False,) * len(entries[-1].refs)


def test_expired_direct_lookup_never_hits_beyond_the_cleanup_batch(cache_fixture: CacheFixture) -> None:
    entries = _seed_expiring_entries(cache_fixture)
    with cache_fixture.transaction() as uow:
        assert uow.computation_cache.lookup_and_pin(entries[-1].key, READER) is None


def test_optional_budget_rejection_does_not_discard_a_healthy_value_or_swallow_cancel(
    cache_fixture: CacheFixture,
) -> None:
    cache = cache_fixture.adapter()
    entry, blobs = _value()
    assert cache.store(entry, blobs, owner=WRITER, checkpoint=_checkpoint, reserve=_reserve)
    cache.release_operation_pins(WRITER)

    denied = True
    cancelled = False

    def deny_reservation(_size: int) -> ContextManager[object]:
        if denied:
            raise MemoryError("optional cache budget denied")
        return nullcontext()

    def cancel() -> None:
        raise InterruptedError("current operation cancelled")

    def current_checkpoint() -> None:
        if cancelled:
            cancel()

    def ttl_snapshot() -> tuple[tuple[tuple[object, ...], ...], ...]:
        with cache_fixture.transaction() as uow:
            return tuple(tuple(tuple(row) for row in uow.connection.execute(
                f"SELECT * FROM {table} ORDER BY rowid",
            )) for table in ("computation_cache_entries", "computation_cache_uses", "artifact_protection_intents"))

    assert cache.lookup_and_pin(entry.key, owner=READER, checkpoint=_checkpoint, reserve=deny_reservation) is None
    assert not cache.store(entry, blobs, owner=WRITER, checkpoint=_checkpoint, reserve=deny_reservation)
    with pytest.raises(InterruptedError, match="current operation cancelled"):
        cache.lookup_and_pin(entry.key, owner=READER, checkpoint=cancel, reserve=_reserve)
    denied = False
    lease = cache.lookup_and_pin(entry.key, owner=READER, checkpoint=current_checkpoint, reserve=deny_reservation)
    assert lease is not None
    cache_fixture.now = NOW + timedelta(hours=12)
    before = ttl_snapshot()
    try:
        denied = True
        assert not lease.mark_used()
        assert ttl_snapshot() == before
        denied = False
        cancelled = True
        with pytest.raises(InterruptedError, match="current operation cancelled"):
            lease.mark_used()
        assert ttl_snapshot() == before
    finally:
        lease.close()
    cache.release_operation_pins(READER)
    cache.release_operation_pins(WRITER)
    with cache_fixture.local.cleanup_session() as acquired:
        assert acquired
