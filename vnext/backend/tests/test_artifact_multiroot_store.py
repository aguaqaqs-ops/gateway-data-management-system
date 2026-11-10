"""Artifact publication, root borrowing and protection semantic barriers."""
from __future__ import annotations

import errno
import os
import tempfile
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import pytest
from gateway_shared_kernel import raw_blob_digest

from gateway_backend.artifacts import ArtifactRef
from gateway_backend.artifacts.bounded_store import CleanupClassification, DeleteDisposition
from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.infrastructure.artifact_store import BoundedArtifactStore, LocalArtifactStore
from gateway_backend.infrastructure.artifact_store.scratch import ScratchSpace
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from tests.support.artifact_layout import open_test_store, make_artifact_layout as make_layout

pytestmark = pytest.mark.unit
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def ref_for(location: ArtifactLocation, raw: bytes, *, identity: str = 'object') -> ArtifactRef:
    return ArtifactRef(build_artifact_id(location, 'test-object', identity), 'application/octet-stream',
        len(raw), raw_blob_digest(raw))


@pytest.mark.parametrize('location', tuple(ArtifactLocation))
def test_object_has_one_root_and_complete_atomic_identity(tmp_path: Path, location: ArtifactLocation) -> None:
    store = open_test_store(tmp_path / 'objects')
    ref = ref_for(location, b'content')
    store.put(b'content', ref)
    directory = store.object_directory(ref.artifact_id)
    assert set(path.name for path in directory.iterdir()) == {'payload', 'ref.jcs'}
    assert store.get_ref(ref.artifact_id) == ref
    assert store.locate(ref) == b'content'
    assert list(store.layout.root(location).rglob('ref.jcs')) == [directory / 'ref.jcs']
    for other in ArtifactLocation:
        if other is not location:
            assert not list(store.layout.root(other).rglob('ref.jcs'))
    # A fresh adapter reads the published metadata rather than a process cache.
    fresh = open_test_store(tmp_path / 'objects')
    assert fresh.get_ref(ref.artifact_id) == ref
    (directory / 'ref.jcs').write_text('{}')
    with pytest.raises(ManifestVerificationError):
        fresh.get_ref(ref.artifact_id)


def test_same_id_publish_is_idempotent_and_conflict_never_overwrites(tmp_path: Path) -> None:
    store = open_test_store(tmp_path / 'objects')
    ref = ref_for(ArtifactLocation.COMPARISON, b'content')
    with ThreadPoolExecutor(max_workers=4) as executor:
        assert list(executor.map(lambda _: store.put(b'content', ref), range(8))) == [ref] * 8
    with pytest.raises(ManifestVerificationError):
        store.put(b'changed', replace(ref, raw_sha256=raw_blob_digest(b'changed')))
    store.payload_path(ref.artifact_id).write_bytes(b'damaged')
    with pytest.raises(ManifestVerificationError):
        store.put(b'content', ref)
    assert store.payload_path(ref.artifact_id).read_bytes() == b'damaged'


def test_stream_failure_never_publishes_ref_or_partial_payload(tmp_path: Path) -> None:
    store = open_test_store(tmp_path / 'objects')
    ref = ref_for(ArtifactLocation.DURABLE, b'content')
    def broken() -> Iterator[bytes]:
        yield b'con'
        raise OSError(errno.ENOSPC, 'isolated writer failure')
    with pytest.raises(ManifestVerificationError):
        store.put_chunks(broken(), ref)
    with pytest.raises(ManifestVerificationError):
        store.get_ref(ref.artifact_id)
    assert not list((store.layout.durable / '.staging').iterdir())


@pytest.fixture
def second_filesystem(tmp_path: Path) -> Iterator[Path]:
    # Explicit test-only scratch on a genuinely different local filesystem.
    parent = Path('/dev/shm')
    assert parent.is_dir() and parent.stat().st_dev != tmp_path.stat().st_dev
    with tempfile.TemporaryDirectory(prefix='gateway-artifact-test-', dir=parent) as directory:
        yield Path(directory)


@pytest.mark.parametrize('cancelled', (False, True))
def test_cross_filesystem_copy_preserves_source_until_owner_closes(
    tmp_path: Path, second_filesystem: Path, cancelled: bool,
) -> None:
    store = open_test_store(tmp_path / 'objects')
    raw = b'x' * (160 * 1024)
    ref = ref_for(ArtifactLocation.EXPORT, raw)
    calls = 0
    def checkpoint() -> None:
        nonlocal calls
        calls += 1
        if cancelled and calls == 3:
            raise InterruptedError('cancelled copy')
    with ScratchSpace(second_filesystem).file(owner='upload-context') as (source, handle):
        handle.write(raw)
        handle.flush()
        assert os.fstat(handle.fileno()).st_dev != store.layout.export.stat().st_dev
        if cancelled:
            with pytest.raises(InterruptedError):
                store.put_from_path(source, ref, checkpoint=checkpoint, byte_limit=len(raw))
            with pytest.raises(ManifestVerificationError):
                store.get_ref(ref.artifact_id)
        else:
            assert store.put_from_path(source, ref, checkpoint=checkpoint, byte_limit=len(raw)) == ref
            assert store.locate(ref) == raw
        with source.open_read() as preserved:
            assert preserved.read() == raw
    assert not list(second_filesystem.iterdir())
    assert not list((store.layout.export / '.staging').iterdir())


def test_cross_root_closure_borrow_blocks_cleanup_and_allows_publication(tmp_path: Path) -> None:
    local = open_test_store(tmp_path / 'objects')
    cleaner = BoundedArtifactStore(open_test_store(tmp_path / 'objects'), unpinned_ttl=timedelta(0))
    refs = [ref_for(location, location.value.encode()) for location in ArtifactLocation]
    for ref in refs:
        local.put(ref.artifact_id.split(':')[1].encode(), ref)
    with local.read_session():
        for ref in refs:
            assert local.get_ref(ref.artifact_id) == ref
            assert b''.join(local.read_exact(ref)) == ref.artifact_id.split(':')[1].encode()
            assert cleaner.delete_eligible(ref, expected_classification=CleanupClassification.ELIGIBLE_AFTER,
                now=NOW + timedelta(days=365)) is DeleteDisposition.RETRYABLE_FAILURE
        extra = ref_for(ArtifactLocation.COMPARISON, b'new', identity='new')
        assert local.put(b'new', extra) == extra  # No SH to EX upgrade in a cache store.
    for ref in refs:
        assert cleaner.delete_eligible(ref, expected_classification=CleanupClassification.ELIGIBLE_AFTER,
            now=NOW + timedelta(days=365)) is DeleteDisposition.DELETED
        assert cleaner.delete_eligible(ref, expected_classification=CleanupClassification.ELIGIBLE_AFTER,
            now=NOW + timedelta(days=365)) is DeleteDisposition.ABSENT


@pytest.mark.serial
def test_pin_holds_root_before_db_and_remains_protected_after_commit(tmp_path: Path, db_path: Path) -> None:
    local = open_test_store(tmp_path / 'objects')
    cleaner = BoundedArtifactStore(open_test_store(tmp_path / 'objects'),
        protection_uow=lambda: ControlDbUnitOfWork(db_path), unpinned_ttl=timedelta(0))
    ref = ref_for(ArtifactLocation.DURABLE, b'content')
    local.put(b'content', ref)
    pinned, release = Event(), Event()
    def pin() -> None:
        with ControlDbUnitOfWork(db_path, artifact_borrow=local.read_session) as uow:
            uow.protection.set_protection((ref,), owner_kind='attempt', owner_id='attempt-1', intent='frozen', recorded_at=NOW)
            pinned.set()
            assert release.wait(5)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(pin)
        try:
            assert pinned.wait(5)
            assert cleaner.delete_eligible(ref, expected_classification=CleanupClassification.ELIGIBLE_AFTER,
                now=NOW + timedelta(days=365)) is DeleteDisposition.RETRYABLE_FAILURE
        finally:
            release.set()
        future.result(timeout=5)
    assert cleaner.classify_cleanup(ref, NOW).classification is CleanupClassification.PROTECTED
    assert cleaner.delete_eligible(ref, expected_classification=CleanupClassification.ELIGIBLE_AFTER,
        now=NOW + timedelta(days=365)) is DeleteDisposition.RETRYABLE_FAILURE
    assert local.locate(ref) == b'content'


@pytest.mark.serial
def test_borrow_can_close_on_another_http_thread_and_nested_borrows_remain(tmp_path: Path) -> None:
    store = open_test_store(tmp_path / 'objects')
    cleaner = open_test_store(tmp_path / 'objects')
    outer, inner = store.read_session(), store.read_session()
    outer.__enter__()
    inner.__enter__()
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(outer.__exit__, None, None, None).result(timeout=5)
    with cleaner.cleanup_session(build_artifact_id(ArtifactLocation.EXPORT, 'test-object', 'one')) as acquired:
        assert not acquired
    inner.__exit__(None, None, None)
    with cleaner.cleanup_session(build_artifact_id(ArtifactLocation.EXPORT, 'test-object', 'one')) as acquired:
        assert acquired


@pytest.mark.parametrize('fault', ('symlink', 'root-replaced', 'readonly', 'nested'))
def test_root_and_server_owned_path_boundaries_fail_closed(tmp_path: Path, fault: str) -> None:
    layout = make_layout(tmp_path / 'objects')
    if fault == 'nested':
        with pytest.raises(ValueError):
            type(layout)(layout.durable, layout.durable / 'nested', layout.comparison, layout.export)
        return
    store = LocalArtifactStore(layout, staging_max_bytes=1024)
    ref = ref_for(ArtifactLocation.DURABLE, b'content')
    if fault == 'symlink':
        (layout.durable / 'objects').symlink_to(tmp_path, target_is_directory=True)
    elif fault == 'root-replaced':
        layout.durable.rename(tmp_path / 'old-durable')
        layout.durable.mkdir()
    else:
        layout.durable.chmod(0o555)
    try:
        with pytest.raises(ManifestVerificationError):
            store.put(b'content', ref)
    finally:
        if fault == 'readonly':
            layout.durable.chmod(0o755)


def test_budget_and_unowned_file_rejected_before_consumption(tmp_path: Path) -> None:
    store = LocalArtifactStore(make_layout(tmp_path / 'objects'), staging_max_bytes=3)
    ref = ref_for(ArtifactLocation.DURABLE, b'content')
    with pytest.raises(ManifestVerificationError, match='limit'):
        store.put(b'content', ref)
    with pytest.raises(ValueError, match='owned scratch'):
        store.put_from_path(tmp_path / 'caller-file', ref, checkpoint=lambda: None, byte_limit=100)  # type: ignore[arg-type]
    assert not (store.layout.durable / '.staging').exists()


def test_exact_commit_repair_requires_closed_readers_and_preserves_pins(tmp_path: Path, db_path: Path) -> None:
    local = open_test_store(tmp_path / 'objects')
    bounded = BoundedArtifactStore(local, protection_uow=lambda: ControlDbUnitOfWork(db_path))
    ref = ref_for(ArtifactLocation.CANONICAL, b'content')
    bounded.put(b'content', ref)
    bounded.set_protection((ref,), owner_kind='baseline-head', owner_id='head-1', intent='canonical-head')
    local.payload_path(ref.artifact_id).write_bytes(b'corrupt')
    with local.read_session():
        with pytest.raises(ManifestVerificationError, match='readers close'):
            bounded.restore_canonical_from_exact_commit(b'content', ref, checkpoint=lambda: None)
    assert bounded.restore_canonical_from_exact_commit(b'content', ref, checkpoint=lambda: None) == ref
    assert bounded.locate(ref) == b'content'
    assert bounded.classify_cleanup(ref, NOW + timedelta(days=365)).classification is CleanupClassification.PROTECTED
    with pytest.raises(ValueError, match='canonical'):
        bounded.restore_canonical_from_exact_commit(b'content', ref_for(ArtifactLocation.DURABLE, b'content'), checkpoint=lambda: None)


def test_directory_sync_failure_keeps_complete_object_and_retry_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_backend.infrastructure.artifact_store import local_store as module
    local = open_test_store(tmp_path / 'objects')
    ref = ref_for(ArtifactLocation.DURABLE, b'content')
    directory = local.object_directory(ref.artifact_id)
    original = module.fsync_directory
    def failed_after_rename(path: Path) -> None:
        if path == directory.parent and directory.exists():
            raise OSError(errno.EIO, 'isolated directory sync failure')
        original(path)
    with monkeypatch.context() as scoped:
        scoped.setattr(module, 'fsync_directory', failed_after_rename)
        with pytest.raises(ManifestVerificationError):
            local.put(b'content', ref)
    assert local.locate(ref) == b'content'
    assert local.put(b'content', ref) == ref


def test_startup_rejects_missing_no_replace_capability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from gateway_backend.infrastructure.artifact_store import atomic_publish
    local = open_test_store(tmp_path / 'objects')
    monkeypatch.setattr(atomic_publish, '_RENAME', None)
    with pytest.raises(OSError):
        local.check_publication_support()
    assert not any(local.layout.durable.iterdir())
