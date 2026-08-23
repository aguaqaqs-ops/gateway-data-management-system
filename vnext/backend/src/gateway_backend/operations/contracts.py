"""Operation runtime public contract identity owned by gateway_backend.operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

OPERATION_RUNTIME_CONTRACT_VERSION = "backend-vnext/operation-runtime/v1"


class OperationStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"
    MANUAL_RECOVERY_REQUIRED = "MANUAL_RECOVERY_REQUIRED"


class StepStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    MANUAL_RECOVERY_REQUIRED = "MANUAL_RECOVERY_REQUIRED"


@dataclass(frozen=True, slots=True)
class JobStepKey:
    """Stable JobDefinition registry identity; does not hold handlers or callables."""

    job_kind: str
    step_name: str
