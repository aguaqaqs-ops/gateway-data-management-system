"""Explicit bounded maintenance of configured backend storage."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

from gateway_backend.deployment_config import DeploymentConfig
from gateway_backend.infrastructure.artifact_store.bounded_store import BoundedArtifactStore
from gateway_backend.bootstrap.storage_layout import artifact_layout_from_config
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore
from gateway_backend.infrastructure.artifact_store.maintenance import ArtifactMaintenance
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.operations.store import RecordNotFound


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
        if args.orphan_grace_seconds < 0:
            raise ValueError('orphan grace cannot be negative')
        deployment = DeploymentConfig.load(args.storage_layout, args.resource_profile)
        local = LocalArtifactStore(artifact_layout_from_config(deployment.storage),
            staging_max_bytes=deployment.resources.temporary.staging_max_bytes_per_object)
        database = Path(deployment.storage.roots['be-metadata'].path) / 'control.sqlite3'
        if not database.is_file():
            raise ValueError('existing backend control database is required')

        def active(owner: str) -> bool:
            if owner.startswith('upload:'):
                # Upload contexts exist before an operation; their held flock
                # owns liveness. A crashed receiver leaves no durable authority.
                return False
            with ControlDbUnitOfWork(database, read_only=True) as uow:
                try:
                    operation = uow.operations.get_operation(owner.removeprefix('operation:'))
                except RecordNotFound:
                    return False
                return not operation.status.is_final_terminal()

        bounded = BoundedArtifactStore(local, protection_uow=lambda: ControlDbUnitOfWork(database))
        maintenance = ArtifactMaintenance(local, bounded,
            scratch_root=Path(deployment.storage.roots['be-scratch'].path), owner_active=active,
            grace=timedelta(seconds=args.orphan_grace_seconds))
        result = maintenance.run(max_candidates=args.max_candidates, cursor=args.cursor)
        print(json.dumps(asdict(result), sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, f'backend storage maintenance refused: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
