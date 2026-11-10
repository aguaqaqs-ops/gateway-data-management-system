"""Bounded maintenance owns enumeration; existing protection owns eligibility."""
from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from gateway_shared_kernel import raw_blob_digest

from gateway_backend.artifacts import ArtifactRef
from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
from gateway_backend.artifacts.scratch import ScratchLimitExceeded
from gateway_backend.infrastructure.artifact_store.bounded_store import BoundedArtifactStore
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore
from gateway_backend.infrastructure.artifact_store.maintenance import ArtifactMaintenance
from gateway_backend.infrastructure.artifact_store.scratch import ScratchSpace
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from tests.support.artifact_layout import open_test_store


def _maintenance(tmp_path: Path, db_path: Path) -> tuple[LocalArtifactStore, BoundedArtifactStore, ArtifactMaintenance]:
    local = open_test_store(tmp_path / 'artifacts')
    root = tmp_path / 'scratch'
    root.mkdir()
    bounded = BoundedArtifactStore(local, protection_uow=lambda: ControlDbUnitOfWork(db_path))
    return local, bounded, ArtifactMaintenance(local, bounded, scratch_root=root,
        owner_active=lambda owner: owner == 'operation:still-running', grace=timedelta(0))


def _put(local: LocalArtifactStore, location: ArtifactLocation, nonce: str = '') -> ArtifactRef:
    ref = ArtifactRef(build_artifact_id(location, 'test-cleanup', nonce), 'application/json', 2, raw_blob_digest(b'{}'))
    local.put(b'{}', ref)
    return ref


def test_round_robin_preserves_strong_owners_and_skips_borrowed_roots(tmp_path: Path, db_path: Path) -> None:
    local, bounded, maintenance = _maintenance(tmp_path, db_path)
    refs = [_put(local, location) for location in ArtifactLocation]
    bounded.set_protection((refs[0],), owner_kind='Attempt', owner_id='attempt-1', intent='frozen')
    when = datetime.now(UTC) + timedelta(days=2)
    with local.layout.read_session((ArtifactLocation.CANONICAL,)):
        first = maintenance.run(now=when)
    assert first.visits <= 1024 and first.candidates <= 32
    assert set(first.skipped_roots) == {"canonical", "staging:canonical"}
    assert local.get_ref(refs[0].artifact_id) == refs[0]
    assert local.get_ref(refs[1].artifact_id) == refs[1]
    assert {item.location for item in first.items if item.disposition == 'deleted'} == {'comparison', 'export'}
    second = maintenance.run(cursor=first.cursor, now=when)
    assert any(item.location == 'canonical' and item.disposition == 'deleted' for item in second.items)
    assert local.get_ref(refs[0].artifact_id) == refs[0]


def test_unknowns_budget_and_cursor_cannot_escape_roots(tmp_path: Path, db_path: Path) -> None:
    local, _, maintenance = _maintenance(tmp_path, db_path)
    # One crowded valid shard forces scan exhaustion without yielding objects.
    objects = local.layout.durable / 'objects'
    objects.mkdir()
    for number in range(256):
        (objects / f'{number:02x}').mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'sentinel').write_bytes(b'keep')
    (local.layout.export / 'unexpected').symlink_to(outside, target_is_directory=True)
    _put(local, ArtifactLocation.COMPARISON)
    result = maintenance.run(now=datetime.now(UTC) + timedelta(days=2))
    assert result.visits <= 1024 and result.cursor is not None
    assert result.candidates <= 32
    assert any(item.disposition == 'manual_review' for item in result.items)
    assert any(item.location == 'comparison' and item.disposition == 'deleted' for item in result.items)
    assert (outside / 'sentinel').read_bytes() == b'keep'
    document = json.loads(base64.urlsafe_b64decode(result.cursor))
    document['lanes'][0]['stack'] = [['../outside', 0]]
    bad = base64.urlsafe_b64encode(json.dumps(document).encode()).decode()
    with pytest.raises(ValueError, match='cursor'):
        maintenance.run(cursor=bad)


def test_temporary_cleanup_requires_known_inactive_unlocked_owner(tmp_path: Path, db_path: Path) -> None:
    local, _, maintenance = _maintenance(tmp_path, db_path)
    root = maintenance.scratch_root
    stale = root / 'scratch-abandoned'
    stale.mkdir()
    (stale / 'owner.json').write_text(json.dumps({'version': 1, 'owner': 'upload:crashed'}))
    (stale / ('file-' + 'a' * 32)).write_bytes(b'old')
    active = root / 'scratch-business'
    active.mkdir()
    (active / 'owner.json').write_text(json.dumps({'version': 1, 'owner': 'operation:still-running'}))
    unknown = root / 'scratch-unknown'
    unknown.mkdir()
    (unknown / 'owner.json').write_text('{}')
    staging = local.layout.durable / '.staging' / 'object-abandoned'
    staging.mkdir(parents=True)
    (staging / 'owner.json').write_text(json.dumps({'version': 1, 'owner': 'upload:crashed'}))
    (staging / 'payload').write_bytes(b'incomplete')
    space = ScratchSpace(root, max_bytes=16)
    with space.session(owner='upload:live') as session, session.file(byte_limit=16) as (_, output):
        output.write(b'live')
        result = maintenance.run()
        assert any(item.reason == 'temporary owner is active' for item in result.items)
    assert not stale.exists() and not staging.exists()
    assert active.exists() and unknown.exists()
    assert any(item.reason == 'business owner remains active' for item in result.items)


@pytest.mark.parametrize('failure', ('cap', 'writer'))
def test_scratch_shared_cap_and_all_exit_cleanup(tmp_path: Path, failure: str) -> None:
    root = tmp_path / 'scratch'
    root.mkdir()
    space = ScratchSpace(root, max_bytes=7)
    with pytest.raises(ScratchLimitExceeded if failure == 'cap' else OSError):
        with space.session(owner='operation:test') as session:
            with session.file(byte_limit=7) as (first, one), session.file(byte_limit=7) as (_, two):
                one.write(b'1234')
                one.flush()
                with first.open_read() as source:
                    assert source.read() == b'1234'
                if failure == 'cap':
                    two.write(b'5678')
                else:
                    raise OSError(28, 'injected ENOSPC')
    assert not list(root.iterdir())


def test_scratch_root_identity_and_expired_source_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / 'scratch'
    root.mkdir()
    space = ScratchSpace(root, max_bytes=16)
    with space.file(owner='upload:test') as (source, output):
        output.write(b'a')
    with pytest.raises(OSError):
        with source.open_read():
            pass
    root.rename(tmp_path / 'old')
    root.mkdir()
    with pytest.raises(ValueError, match='identity'):
        with space.session(owner='upload:test'):
            pass


def test_cleanup_cli_uses_configured_metadata_and_bounded_result(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from gateway_backend.bootstrap.storage_admin import main
    from gateway_backend.infrastructure.control_db.database import initialize_control_db
    from tests.support.artifact_layout import write_deployment_files
    storage, resources = write_deployment_files(tmp_path / 'storage')
    initialize_control_db(tmp_path / 'storage/metadata/control.sqlite3')
    local = open_test_store(tmp_path / 'storage')
    ref = _put(local, ArtifactLocation.EXPORT)
    path = local.payload_path(ref.artifact_id)
    os.utime(path, (0, 0))
    assert main(['--storage-layout', str(storage), '--resource-profile', str(resources),
                 'cleanup', '--max-candidates', '1']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['candidates'] == 1 and result['visits'] <= 1024
    assert result['items'][0]['disposition'] == 'deleted'
    assert not path.exists()


@pytest.mark.parametrize('fault', ('limit', 'cancel', 'write'))
def test_http_arrow_spool_failure_closes_stream_and_owned_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str,
) -> None:
    import asyncio
    from collections.abc import AsyncIterator
    from typing import cast
    from gateway_repository_client.arrow_stream import ArrowIpcByteStream
    from gateway_backend.artifacts.scratch import scratch_scope
    from gateway_backend.infrastructure.artifact_store.scratch import _BudgetedFile
    from gateway_backend.infrastructure.repository_read.http_arrow import _spool_arrow_ipc
    root = tmp_path / 'spool'
    root.mkdir()
    closed: list[bool] = []
    class Stream:
        async def __aenter__(self) -> Stream:
            return self
        async def __aexit__(self, *args: object) -> None:
            closed.append(True)
        async def aiter_bytes(self) -> AsyncIterator[bytes]:
            yield b'1234'
            if fault == 'cancel':
                raise asyncio.CancelledError()
            yield b'5678'
    if fault == 'write':
        def full_disk(self: object, data: object) -> int:
            raise OSError(28, 'injected ENOSPC')
        monkeypatch.setattr(_BudgetedFile, 'write', full_disk)
    error = {'limit': ScratchLimitExceeded, 'cancel': asyncio.CancelledError, 'write': OSError}[fault]
    with ScratchSpace(root, max_bytes=7).session(owner='operation:read') as session, scratch_scope(session):
        with pytest.raises(error):
            asyncio.run(_spool_arrow_ipc(cast(ArrowIpcByteStream, Stream())))
        with os.scandir(root) as entries:
            owner = next(entries)
        assert {child.name for child in Path(owner.path).iterdir()} == {'owner.json'}
    assert closed == [True]
    assert not list(root.iterdir())


def test_writer_close_failure_still_removes_owned_scratch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import pyarrow as pa
    from gateway_backend.artifacts.scratch import scratch_scope
    from gateway_backend.capabilities.comparison.artifacts import (
        RecordsPublicationContext, RecordsPublicationPolicy, _write_arrow_parquet,
    )
    from gateway_backend.infrastructure.artifact_store.scratch import _BudgetedFile
    root = tmp_path / 'scratch'
    root.mkdir()
    original_close = _BudgetedFile.close
    raised: list[bool] = []
    def failed_close(self: _BudgetedFile) -> None:
        original_close(self)
        if not raised:
            raised.append(True)
            raise OSError('injected scratch close failure')
    monkeypatch.setattr(_BudgetedFile, 'close', failed_close)
    schema = pa.schema([('id', pa.int64())])
    with ScratchSpace(root, max_bytes=1024**2).session(owner='operation:comparison') as session, scratch_scope(session):
        with pytest.raises(OSError, match='close failure'):
            _write_arrow_parquet((pa.RecordBatch.from_arrays([pa.array([1])], schema=schema),),
                schema, RecordsPublicationPolicy(), RecordsPublicationContext())
    assert not list(root.iterdir())


def test_temporary_io_failure_keeps_owner_for_a_later_bounded_retry(tmp_path: Path, db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, maintenance = _maintenance(tmp_path, db_path)
    owner = maintenance.scratch_root / 'scratch-retryable'
    owner.mkdir()
    (owner / 'owner.json').write_text(json.dumps({'version': 1, 'owner': 'upload:ended'}))
    payload = owner / ('file-' + 'b' * 32)
    payload.write_bytes(b'derived')
    original_unlink = Path.unlink
    def fail_unlink(path: Path, missing_ok: bool = False) -> None:
        if path == payload:
            raise OSError(5, 'injected unlink I/O failure')
        original_unlink(path, missing_ok=missing_ok)
    with monkeypatch.context() as injected:
        injected.setattr(Path, 'unlink', fail_unlink)
        result = maintenance.run()
    assert any(item.disposition == 'retryable_failure' for item in result.items)
    assert payload.exists() and (owner / 'owner.json').is_file()
    retried = maintenance.run()
    assert any(item.disposition == 'deleted' and item.location == 'scratch' for item in retried.items)
    assert not owner.exists()


@pytest.mark.parametrize('missing', ('durable', 'scratch'))
def test_cleanup_cli_skips_unavailable_slot_and_continues_other_roots(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], missing: str,
) -> None:
    from gateway_backend.bootstrap.storage_admin import main
    from gateway_backend.infrastructure.artifact_store.layout import ArtifactStoreLayout
    from gateway_backend.infrastructure.control_db.database import initialize_control_db
    from tests.support.artifact_layout import write_deployment_files
    storage, resources = write_deployment_files(tmp_path / 'storage')
    initialize_control_db(tmp_path / 'storage/metadata/control.sqlite3')
    local = open_test_store(tmp_path / 'storage')
    ref = _put(local, ArtifactLocation.EXPORT)
    payload = local.payload_path(ref.artifact_id)
    os.utime(payload, (0, 0))
    absent = tmp_path / 'storage' / missing
    absent.rmdir()
    if missing == 'durable':
        with pytest.raises(ValueError, match='existing writable'):
            ArtifactStoreLayout(**{location.value: tmp_path / 'storage' / location.value for location in ArtifactLocation})
    assert main(['--storage-layout', str(storage), '--resource-profile', str(resources), 'cleanup']) == 0
    result = json.loads(capsys.readouterr().out)
    assert any(item['location'] == missing and item['disposition'] == 'manual_review' for item in result['items'])
    assert any(item['location'] == 'export' and item['disposition'] == 'deleted' for item in result['items'])
    assert result['cursor'] is not None
    assert not absent.exists() and not payload.exists()


def test_scratch_scan_budget_defers_entries_without_losing_cross_call_progress(
    tmp_path: Path, db_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_backend.infrastructure.artifact_store import maintenance as module
    _, _, maintenance = _maintenance(tmp_path, db_path)
    root = maintenance.scratch_root
    for number in range(9):
        owner = root / f'scratch-owner-{number:06d}'
        owner.mkdir()
        (owner / 'owner.json').write_text(json.dumps({'version': 1, 'owner': f'upload:ended-{number}'}))
        for member in range(63):
            (owner / f'file-{member:032x}').write_bytes(b'derived')
    actual_visits = 0
    original_entry, original_scandir, original_unlink = module._entry, os.scandir, Path.unlink
    def counted_entry(path: Path, cookie: int) -> tuple[str | None, int]:
        nonlocal actual_visits
        actual_visits += 1
        return original_entry(path, cookie)
    class Entries:
        def __init__(self, path: Path) -> None:
            self.entries = original_scandir(path)
        def __enter__(self) -> Entries:
            return self
        def __exit__(self, *args: object) -> None:
            self.entries.close()
        def __iter__(self) -> Entries:
            return self
        def __next__(self) -> os.DirEntry[str]:
            nonlocal actual_visits
            actual_visits += 1
            return next(self.entries)
    def counted_unlink(path: Path, missing_ok: bool = False) -> None:
        nonlocal actual_visits
        actual_visits += 1
        original_unlink(path, missing_ok=missing_ok)
    cursor = None
    deleted = 0
    with monkeypatch.context() as counted:
        counted.setattr(module, '_entry', counted_entry)
        counted.setattr(os, 'scandir', Entries)
        counted.setattr(Path, 'unlink', counted_unlink)
        for attempt in range(3):
            before = actual_visits
            result = maintenance.run(cursor=cursor)
            assert actual_visits - before <= result.visits <= 1024
            assert result.candidates <= 32
            assert not any(item.disposition == 'manual_review' for item in result.items)
            deleted += sum(item.disposition == 'deleted' for item in result.items)
            cursor = result.cursor
            if attempt == 0:
                assert cursor is not None and deleted < 9
            if cursor is None:
                break
    assert cursor is None and deleted == 9
    assert not list(root.iterdir())
