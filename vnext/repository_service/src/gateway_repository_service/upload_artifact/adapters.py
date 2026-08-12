"""Private adapters for UploadArtifact."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from gateway_repository_service.publication import FaultPoint, atomic_publish_artifact_file


class StreamingFileSinkAdapter:
    """Writes upload chunks to a request-owned staging file with incremental SHA-256."""

    def __init__(self, staging_path: Path) -> None:
        self._staging_path = staging_path
        self._handle = staging_path.open("xb")
        self._hasher = hashlib.sha256()
        self._received_bytes = 0
        self._closed = False

    def write_chunk(self, chunk: bytes) -> None:
        if self._closed:
            raise RuntimeError("artifact body sink is already closed")
        if not chunk:
            return
        self._handle.write(chunk)
        self._hasher.update(chunk)
        self._received_bytes += len(chunk)

    def close(self) -> tuple[int, str]:
        if self._closed:
            raise RuntimeError("artifact body sink is already closed")
        self._closed = True
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()
        return self._received_bytes, self._hasher.hexdigest()

    def abort(self) -> None:
        if not self._closed:
            self._closed = True
            self._handle.close()
        if self._staging_path.exists():
            self._staging_path.unlink()


class ArtifactFilesystemPublicationAdapter:
    """Production-owned adapter over the shared file publication primitive."""

    def publish_file(
        self,
        staging: Path,
        target: Path,
        *,
        fault: FaultPoint = FaultPoint.NONE,
    ) -> None:
        atomic_publish_artifact_file(staging, target, fault=fault)
