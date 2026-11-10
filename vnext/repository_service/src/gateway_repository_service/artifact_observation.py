"""Bounded physical observation of one RS-owned ready artifact; no online scan."""
from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID

from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.upload_artifact.admission_pin import open_owned_ready_artifact


def observe_ready_artifact(layout: DurableLayout, repository_id: UUID, artifact_id: UUID) -> dict[str, object]:
    descriptor, directory = open_owned_ready_artifact(layout, repository_id, artifact_id)
    try:
        info = os.fstat(descriptor)
        return {"service_owner": "repository_service", "repository_id": str(repository_id),
            "artifact_id": str(artifact_id), "location": "rs-artifacts",
            "logical_bytes": info.st_size, "allocated_bytes": info.st_blocks * 512,
            "device": info.st_dev, "inode": info.st_ino, "payload_mtime_ns": info.st_mtime_ns,
            "observed_at": datetime.now(UTC).isoformat()}
    finally:
        os.close(descriptor)
        os.close(directory)
