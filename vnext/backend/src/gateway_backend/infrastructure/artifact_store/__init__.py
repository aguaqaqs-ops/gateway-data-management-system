"""Filesystem-backed artifact store infrastructure adapter."""

from gateway_backend.infrastructure.artifact_store.bounded_store import BoundedArtifactStore
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore
from gateway_backend.infrastructure.artifact_store.protection import SQLiteArtifactProtectionStore

__all__ = [
    "BoundedArtifactStore",
    "LocalArtifactStore",
    "SQLiteArtifactProtectionStore",
]
