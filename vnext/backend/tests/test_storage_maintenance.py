"""Bounded maintenance owns enumeration; existing protection owns eligibility."""
from __future__ import annotations

import base64
import json
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
