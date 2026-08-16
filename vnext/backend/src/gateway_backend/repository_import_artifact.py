"""Reproducible RepositoryImportArtifact v1 writer (tar+zstd).

The package contains exactly two USTAR regular files, in this order:

    manifest.json
    replay.sql

Headers are pinned (mtime 0, uid/gid 0, empty uname/gname, mode 0644, no pax)
so size/SHA do not depend on the wall clock or host identity.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import compression.zstd

MANIFEST_ENTRY_NAME = "manifest.json"
REPLAY_SQL_ENTRY_NAME = "replay.sql"
_FILE_MODE = 0o644


class RepositoryImportArtifactError(ValueError):
    """Raised when a v1 import package cannot be written."""


@dataclass(frozen=True, slots=True)
class WrittenImportPackage:
    payload: bytes
    size_bytes: int
    sha256: str


def build_repository_import_package(
    *,
    manifest: Mapping[str, object],
    replay_sql: bytes,
) -> WrittenImportPackage:
    if type(replay_sql) is not bytes:
        raise RepositoryImportArtifactError("replay.sql must be bytes")
    manifest_bytes = json.dumps(dict(manifest), separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    tar_bytes = _build_ustar(
        (
            (MANIFEST_ENTRY_NAME, manifest_bytes),
            (REPLAY_SQL_ENTRY_NAME, replay_sql),
        )
    )
    payload = compression.zstd.compress(tar_bytes)
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    return WrittenImportPackage(payload=payload, size_bytes=len(payload), sha256=digest)


def write_repository_import_package(
    path: Path,
    *,
    manifest: Mapping[str, object],
    replay_sql: bytes,
) -> WrittenImportPackage:
    written = build_repository_import_package(manifest=manifest, replay_sql=replay_sql)
    path.write_bytes(written.payload)
    return written


def _build_ustar(entries: tuple[tuple[str, bytes], ...]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, payload in entries:
            if name not in {MANIFEST_ENTRY_NAME, REPLAY_SQL_ENTRY_NAME}:
                raise RepositoryImportArtifactError(f"unexpected tar entry {name!r}")
            info = tarfile.TarInfo(name=name)
            info.type = tarfile.REGTYPE
            info.size = len(payload)
            info.mode = _FILE_MODE
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()
