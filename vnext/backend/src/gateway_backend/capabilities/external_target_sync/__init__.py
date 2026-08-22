"""Public surface of the External Target Sync capability."""

from gateway_backend.capabilities.external_target_sync.contracts import (
    EXTERNAL_TARGET_SYNC_CONTRACT_VERSION,
    REFERENCE_EXECUTOR_CHECKPOINT_CONTRACT_VERSION,
    ExternalApplyFailureCode,
    ExternalApplyInput,
    ExternalApplyPhase,
    ExternalApplyResult,
    ExternalApplyStatus,
    ExternalSyncOutcome,
    ReferenceExecutorCheckpoint,
    TargetRegistration,
    compute_reference_executor_checkpoint_digest,
    reference_executor_checkpoint_from_document,
    target_registration_from_document,
)

__all__ = [
    "EXTERNAL_TARGET_SYNC_CONTRACT_VERSION",
    "REFERENCE_EXECUTOR_CHECKPOINT_CONTRACT_VERSION",
    "ExternalApplyFailureCode",
    "ExternalApplyInput",
    "ExternalApplyPhase",
    "ExternalApplyResult",
    "ExternalApplyStatus",
    "ExternalSyncOutcome",
    "ReferenceExecutorCheckpoint",
    "TargetRegistration",
    "compute_reference_executor_checkpoint_digest",
    "reference_executor_checkpoint_from_document",
    "target_registration_from_document",
]
