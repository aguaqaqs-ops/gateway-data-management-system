"""Operation runtime public contract surface."""

from gateway_backend.operations.contracts import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    BusinessReference,
    JobStepKey,
    OperationDiagnostic,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
    operation_record_from_document,
    step_record_from_document,
)
from gateway_backend.operations.state import (
    TransitionDisposition,
    WritePrecondition,
    validate_operation_transition,
    validate_step_transition,
    validate_write_precondition,
)

__all__ = [
    "OPERATION_RUNTIME_CONTRACT_VERSION",
    "BusinessReference",
    "JobStepKey",
    "OperationDiagnostic",
    "OperationRecord",
    "OperationStatus",
    "StepRecord",
    "StepStatus",
    "TransitionDisposition",
    "WritePrecondition",
    "operation_record_from_document",
    "step_record_from_document",
    "validate_operation_transition",
    "validate_step_transition",
    "validate_write_precondition",
]
