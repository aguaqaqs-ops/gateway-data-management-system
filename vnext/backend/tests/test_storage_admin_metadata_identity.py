"""Maintenance must not use another control DB through metadata symlinks."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from gateway_shared_kernel import raw_blob_digest
from gateway_backend.artifacts import ArtifactRef
from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
from gateway_backend.bootstrap.storage_admin import main
from gateway_backend.infrastructure.artifact_store.bounded_store import BoundedArtifactStore
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, initialize_control_db
from tests.support.artifact_layout import write_deployment_files, open_test_store


@pytest.mark.parametrize('alias', ('metadata-root', 'database'))
def test_cleanup_rejects_other_protection_database_through_symlinks(tmp_path: Path, alias: str) -> None:
    storage, resources = write_deployment_files(tmp_path / 'storage')
    metadata = tmp_path / 'storage/metadata'
    db = metadata / 'control.sqlite3'
    initialize_control_db(db)
    store = open_test_store(tmp_path / 'storage')
    ref = ArtifactRef(build_artifact_id(ArtifactLocation.EXPORT, 'test-protected', alias),
        'application/json', 2, raw_blob_digest(b'{}'))
    store.put(b'{}', ref)
    bounded = BoundedArtifactStore(store, protection_uow=lambda: ControlDbUnitOfWork(db))
    bounded.set_protection((ref,), owner_kind='Attempt', owner_id='attempt-frozen', intent='frozen')
    payload = store.payload_path(ref.artifact_id)
    os.utime(payload, (0, 0))
    other = tmp_path / 'other-metadata'
    other.mkdir()
    other_db = other / 'control.sqlite3'
    initialize_control_db(other_db)
    if alias == 'metadata-root':
        metadata.rename(tmp_path / 'original-metadata')
        metadata.symlink_to(other, target_is_directory=True)
    else:
        db.rename(metadata / 'original.sqlite3')
        db.symlink_to(other_db)
    try:
        code = main(['--storage-layout', str(storage), '--resource-profile', str(resources), 'cleanup'])
    except SystemExit as exc:
        code = exc.code
    assert payload.is_file(), 'cleanup deleted an actual Attempt-protected object using another empty protection DB'
    assert code == 2


@pytest.mark.parametrize('fault', ('missing', 'empty', 'uninitialized', 'wrong-schema'))
def test_cleanup_refuses_uninitialized_or_wrong_schema_without_creating_a_database(tmp_path: Path, fault: str) -> None:
    import sqlite3
    storage, resources = write_deployment_files(tmp_path / 'storage')
    db = tmp_path / 'storage/metadata/control.sqlite3'
    if fault == 'empty':
        db.write_bytes(b'')
    elif fault in {'uninitialized', 'wrong-schema'}:
        with sqlite3.connect(db) as connection:
            connection.execute('VACUUM' if fault == 'uninitialized' else 'CREATE TABLE unrelated (n INTEGER)')
    before = db.read_bytes() if db.exists() else None
    with pytest.raises(SystemExit) as caught:
        main(['--storage-layout', str(storage), '--resource-profile', str(resources), 'cleanup'])
    assert caught.value.code == 2
    assert (db.read_bytes() if db.exists() else None) == before
    assert not Path(str(db) + '-wal').exists()
    assert not Path(str(db) + '-shm').exists()


def test_existing_only_control_transaction_cannot_create_a_replacement_database(tmp_path: Path) -> None:
    import sqlite3
    db = tmp_path / 'missing.sqlite3'
    with pytest.raises(sqlite3.OperationalError):
        with ControlDbUnitOfWork(db, require_existing=True):
            pytest.fail('missing authority must not open a transaction')
    assert not db.exists()
