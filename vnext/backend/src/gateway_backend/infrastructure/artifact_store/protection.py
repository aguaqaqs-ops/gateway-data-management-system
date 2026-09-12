"""Re-export the control-DB protection participant for ArtifactStore callers."""

from gateway_backend.infrastructure.control_db.sqlite_protection import SQLiteArtifactProtectionStore

__all__ = ["SQLiteArtifactProtectionStore"]
