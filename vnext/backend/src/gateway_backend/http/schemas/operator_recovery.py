"""Internal operator recovery HTTP DTOs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OperatorRecoveryRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    step_id: str
    command: Literal["RESUME_RECONCILE", "RETRY_FROM_CHECKPOINT", "ABORT_CONFIRMED_FAILURE"]
    expected_operation_optimistic_version: int = Field(ge=0)
    expected_step_optimistic_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=4096)


class OperatorRecoveryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    step_id: str
    command: Literal["RESUME_RECONCILE", "RETRY_FROM_CHECKPOINT", "ABORT_CONFIRMED_FAILURE"]
    disposition: Literal["APPLY", "IDEMPOTENT"]
