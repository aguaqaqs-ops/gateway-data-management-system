"""Reproducible RepositoryImportArtifact v1 writer (tar+zstd).

The package contains exactly two USTAR regular files, in this order:

    manifest.json
    replay.sql

This module is the identity-projection helper. The pinned USTAR+zstd packer
and 16/200 MiB gates are owned by storage_projection.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from gateway_backend.capabilities.storage_projection.contracts import WrittenImportPackage
from gateway_backend.capabilities.storage_projection.package import (
    MANIFEST_ENTRY_NAME,
    REPLAY_SQL_ENTRY_NAME,
    PackageError,
    pack_repository_import_entries,
)

__all__ = [
    "MANIFEST_ENTRY_NAME",
    "REPLAY_SQL_ENTRY_NAME",
    "RepositoryImportArtifactError",
    "WrittenImportPackage",
    "build_repository_import_package",
    "write_repository_import_package",
]


class RepositoryImportArtifactError(ValueError):
    """Raised when a v1 import package cannot be written."""


def build_repository_import_package(
    *,
    manifest: Mapping[str, object],
    replay_sql: bytes,
) -> WrittenImportPackage:
    if type(replay_sql) is not bytes:
        raise RepositoryImportArtifactError("replay.sql must be bytes")
    try:
        manifest_bytes = json.dumps(dict(manifest), separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    except (TypeError, ValueError) as exc:
        raise RepositoryImportArtifactError(str(exc) or "manifest.json is not serializable") from exc
    try:
        return pack_repository_import_entries(manifest_bytes, replay_sql)
    except PackageError as exc:
        raise RepositoryImportArtifactError(str(exc)) from exc


def write_repository_import_package(
    path: Path,
    *,
    manifest: Mapping[str, object],
    replay_sql: bytes,
) -> WrittenImportPackage:
    written = build_repository_import_package(manifest=manifest, replay_sql=replay_sql)
    path.write_bytes(written.payload)
    return written
