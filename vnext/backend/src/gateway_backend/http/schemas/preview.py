"""Preview HTTP DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StartPreviewOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_workspace_version: int = Field(ge=0)
    upload_revision_id: str
    generation: int = Field(ge=0)
    expected_baseline_node_id: str
    expected_baseline_head_version: int = Field(ge=0)
    options: StartPreviewOptions = Field(default_factory=StartPreviewOptions)


class OperationAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    workspace_id: str
    upload_revision_id: str
    generation: int
    status: Literal["QUEUED"]


class PreviewArtifactRefResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    media_type: str
    size_bytes: int
    raw_sha256: str


class PreviewIdentityPairResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pair_id: str
    applicability: Literal["APPLICABLE", "NOT_APPLICABLE"]
    status: Literal["SAME_PROJECT", "DIFFERENT_PROJECT", "UNVERIFIABLE", "NOT_APPLICABLE"]
    mode: Literal["DETAILED", "DATASET_REPLACEMENT"]
    assessment_ref: PreviewArtifactRefResponse | None
    assessment_digest: str | None


class PreviewResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview_result_id: str
    workspace_id: str
    upload_revision_id: str
    generation: int
    operation_id: str
    business_baseline_node_id: str
    business_baseline_commit_id: str
    derived_stale: bool
    bundle_digest: str
    identity_assessment_set_digest: str
    identity_pairs: list[PreviewIdentityPairResponse]
    created_at: datetime
