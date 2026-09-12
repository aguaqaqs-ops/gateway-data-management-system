"""Workspace HTTP DTOs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CreateWorkspaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gateway_device_external_key: str
    business_project_id: str


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    gateway_device_external_key: str
    business_project_id: str
    state: str
    generation: int
    current_upload_revision_id: str | None = None
    current_preview_result_id: str | None = None
    optimistic_version: int
    created_at: datetime
    updated_at: datetime
