"""Operation HTTP DTOs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

class OperationDiagnosticResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class OperationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    job_kind: str
    status: str
    optimistic_version: int
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    diagnostic: OperationDiagnosticResponse | None = None
