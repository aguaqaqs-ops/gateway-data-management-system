"""Upload HTTP DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ArtifactManifestPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_name: str
    media_type: str
    size_bytes: int = Field(ge=0)
    raw_sha256: str


class UploadArtifactsManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    INITIAL: ArtifactManifestPart | None = None
    MODIFIED: ArtifactManifestPart


class UploadManifestPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_workspace_version: int = Field(ge=0)
    input_completeness: Literal["FULL", "MODIFIED_ONLY"]
    artifacts: UploadArtifactsManifest


class SourceArtifactResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    media_type: str
    size_bytes: int
    raw_sha256: str


class UploadRevisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_revision_id: str
    workspace_id: str
    generation: int
    input_completeness: str
    source_artifacts: dict[str, SourceArtifactResponse]
    optimistic_version: int
    created_at: datetime
