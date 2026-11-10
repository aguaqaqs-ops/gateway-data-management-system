"""Explicit bounded maintenance of configured backend storage."""
from __future__ import annotations

import argparse
import json
import os
import stat
import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

from gateway_backend.deployment_config import DeploymentConfig
from gateway_backend.infrastructure.artifact_store.bounded_store import BoundedArtifactStore
from gateway_backend.bootstrap.storage_layout import maintenance_layout_from_config
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore
from gateway_backend.infrastructure.artifact_store.layout import directory_identity, descriptor_mount_id
from gateway_backend.infrastructure.control_db.schema import verify_control_db_file
from gateway_backend.infrastructure.artifact_store.maintenance import ArtifactMaintenance
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.operations.store import RecordNotFound, StoreBusy, UnsupportedSchemaVersion, CorruptPersistedRecord


def _database_file_identity(database: Path, metadata: Path) -> tuple[int, int]:
    root_device, _root_inode, root_mount = directory_identity(metadata)
    descriptor = os.open(database, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_size == 0
                or info.st_dev != root_device or descriptor_mount_id(descriptor) != root_mount):
            raise ValueError('existing initialized ordinary control database is required')
        return info.st_dev, info.st_ino
    finally:
        os.close(descriptor)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-layout', type=Path, required=True)
    parser.add_argument('--resource-profile', type=Path, required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    cleanup = commands.add_parser('cleanup', help='one bounded pass; retain cursor for continuation')
    cleanup.add_argument('--max-candidates', type=int, default=32)
    cleanup.add_argument('--cursor')
    cleanup.add_argument('--orphan-grace-seconds', type=int, default=86400,
                         help='use zero only after explicitly draining inactive temporary owners')
    args = parser.parse_args(argv)
    try:
        if not 0 <= args.orphan_grace_seconds <= 86400:
            raise ValueError('orphan grace must be between zero and 86400 seconds')
        deployment = DeploymentConfig.load(args.storage_layout, args.resource_profile)
        local = LocalArtifactStore(maintenance_layout_from_config(deployment.storage),
            staging_max_bytes=deployment.resources.temporary.staging_max_bytes_per_object)
        metadata = Path(deployment.storage.roots['be-metadata'].path)
        metadata_identity = directory_identity(metadata)
        database = metadata / 'control.sqlite3'
        database_identity = _database_file_identity(database, metadata)
        # Read-only verification precedes any connection profile/WAL writes.
        verify_control_db_file(database, require_initialized=True)

        def check_database_identity() -> None:
            try:
                if (directory_identity(metadata) != metadata_identity
                        or _database_file_identity(database, metadata) != database_identity):
                    raise ValueError('changed')
            except (OSError, ValueError, StopIteration):
                # Loss of deletion authority stops the entire pass, unlike an
                # unavailable artifact slot that can be skipped independently.
                raise RuntimeError('maintenance protection database unavailable or changed') from None

        @contextmanager
        def transaction(*, read_only: bool = False) -> Iterator[ControlDbUnitOfWork]:
            check_database_identity()
            with ControlDbUnitOfWork(database, read_only=read_only, require_existing=True) as uow:
                check_database_identity()
                yield uow

        def active(owner: str) -> bool:
            check_database_identity()
            if owner.startswith(('upload:', 'request:')):
                # Upload contexts exist before an operation; their held flock
                # owns liveness. A crashed receiver leaves no durable authority.
                return False
            with transaction(read_only=True) as uow:
                try:
                    operation = uow.operations.get_operation(owner.removeprefix('operation:'))
                except RecordNotFound:
                    return False
                return not operation.status.is_final_terminal()

        bounded = BoundedArtifactStore(local, protection_uow=transaction)
        maintenance = ArtifactMaintenance(local, bounded,
            scratch_root=Path(deployment.storage.roots['be-scratch'].path), owner_active=active,
            grace=timedelta(seconds=args.orphan_grace_seconds))
        result = maintenance.run(max_candidates=args.max_candidates, cursor=args.cursor)
        print(json.dumps(asdict(result), sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError, sqlite3.DatabaseError, StoreBusy, UnsupportedSchemaVersion, CorruptPersistedRecord) as exc:
        parser.exit(2, f'backend storage maintenance refused: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
