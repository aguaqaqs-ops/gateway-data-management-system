"""Operation HTTP DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gateway_backend.http.schemas.constraints import NonNegativeIJsonInt


class OperationDiagnosticDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=128, pattern=r"^[A-Z][A-Z0-9_.:-]*$")
    side: Literal["INITIAL", "MODIFIED"]
    table_name: str | None = Field(max_length=255)
    column_name: str | None = Field(max_length=255)


class OperationDiagnosticResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: list[OperationDiagnosticDetailResponse] | None = Field(default=None, max_length=100)
    omitted_count: NonNegativeIJsonInt | None = None


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
