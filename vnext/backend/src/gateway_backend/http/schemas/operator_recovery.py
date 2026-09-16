"""Internal operator recovery HTTP DTOs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from gateway_backend.http.schemas.constraints import (
    BoundedDiagnosticReason,
    BoundedOpaqueId,
    NonNegativeIJsonInt,
)


class OperatorRecoveryRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: BoundedOpaqueId
    step_id: BoundedOpaqueId
    command: Literal["RESUME_RECONCILE", "RETRY_FROM_CHECKPOINT", "ABORT_CONFIRMED_FAILURE"]
    expected_operation_optimistic_version: NonNegativeIJsonInt
    expected_step_optimistic_version: NonNegativeIJsonInt
    reason: BoundedDiagnosticReason


class OperatorRecoveryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    step_id: str
    command: Literal["RESUME_RECONCILE", "RETRY_FROM_CHECKPOINT", "ABORT_CONFIRMED_FAILURE"]
    disposition: Literal["APPLY", "IDEMPOTENT"]
