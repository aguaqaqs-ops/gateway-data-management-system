"""Preview JobDefinition registry, decoders, and worker composition."""

from __future__ import annotations

from collections.abc import Mapping
from gateway_backend.application.job_definitions import JobDefinition
from gateway_backend.application.payloads import (
    CheckpointDecodeError,
    PayloadDecodeError,
    PayloadDecoder,
)
from gateway_backend.application.recovery import (
    DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
    RecoveryOutcome,
    RecoveryOutcomeDisposition,
    RecoveryPort,
)
from gateway_backend.application.workspace.ports import (
    WorkspaceControlTransaction as PreviewControlTransaction,
)
from gateway_backend.operations.contracts import (
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
)
from gateway_backend.operations.lease_session import LeaseSession
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
)
from types import TracebackType
from typing import (
    ContextManager,
    cast,
)

from gateway_backend.application.preview_jobs.assemble import build_assemble_preview_handler
from gateway_backend.application.preview_jobs.checkpoint import _active_preview_transaction
from gateway_backend.application.preview_jobs.materialize import build_materialize_inputs_handler
from gateway_backend.application.preview_jobs.payload import (
    PREVIEW_ASSEMBLE_DECODER,
    PREVIEW_ASSEMBLE_HANDLER,
    PREVIEW_MATERIALIZE_DECODER,
    PREVIEW_MATERIALIZE_HANDLER,
    PREVIEW_PUBLISH_DECODER,
    PREVIEW_PUBLISH_HANDLER,
    PREVIEW_STEP_PUBLISH,
    PreviewControlTransactionFactory,
    PreviewJobError,
    PreviewRuntimeDependencies,
    decode_preview_payload,
    preview_assemble_job_definition,
    preview_materialize_job_definition,
    preview_publish_job_definition,
)
from gateway_backend.application.preview_jobs.publish import build_publish_preview_handler

def preview_job_definitions() -> tuple[JobDefinition, ...]:
    return (
        preview_materialize_job_definition(),
        preview_assemble_job_definition(),
        preview_publish_job_definition(),
    )

def preview_payload_decoders() -> Mapping[str, PayloadDecoder]:
    decoder: PayloadDecoder = decode_preview_payload
    return {
        PREVIEW_MATERIALIZE_DECODER: decoder,
        PREVIEW_ASSEMBLE_DECODER: decoder,
        PREVIEW_PUBLISH_DECODER: decoder,
    }

def bind_control_transaction_factory(
    inner: PreviewControlTransactionFactory,
) -> PreviewControlTransactionFactory:
    """Bind the active preview transaction for publish-time workspace writes."""

    class _BoundUnitOfWork:
        def __init__(self, wrapped: ContextManager[PreviewControlTransaction]) -> None:
            self._wrapped = wrapped

        def __enter__(self) -> PreviewControlTransaction:
            transaction = self._wrapped.__enter__()
            _active_preview_transaction.set(transaction)
            return transaction

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool | None:
            _active_preview_transaction.set(None)
            return self._wrapped.__exit__(exc_type, exc, tb)

    def factory() -> ContextManager[PreviewControlTransaction]:
        return _BoundUnitOfWork(inner())

    return factory

def preview_composition_bundle(
    deps: PreviewRuntimeDependencies,
) -> tuple[tuple[JobDefinition, ...], Mapping[str, ClaimedExecutor], Mapping[str, PayloadDecoder]]:
    bound_deps = PreviewRuntimeDependencies(
        artifact_store=deps.artifact_store,
        repository_provider_factory=deps.repository_provider_factory,
        baseline_head_read=deps.baseline_head_read,
        control_transaction_factory=bind_control_transaction_factory(
            deps.control_transaction_factory
        ),
        snapshot_export_cache=deps.snapshot_export_cache,
        computation_cache=deps.computation_cache,
    )
    return (
        preview_job_definitions(),
        {
            PREVIEW_MATERIALIZE_HANDLER: build_materialize_inputs_handler(bound_deps),
            PREVIEW_ASSEMBLE_HANDLER: build_assemble_preview_handler(bound_deps),
            PREVIEW_PUBLISH_HANDLER: build_publish_preview_handler(bound_deps),
        },
        dict(preview_payload_decoders()),
    )

def build_preview_recovery_port(deps: PreviewRuntimeDependencies) -> RecoveryPort:
    class _PreviewRecoveryPort:
        def recover(
            self,
            operation: OperationRecord,
            step: StepRecord,
            control: ExecutionControl,
            lease_session: LeaseSession,
        ) -> RecoveryOutcome:
            if (
                operation.status is OperationStatus.SUCCEEDED
                and step.status is StepStatus.SUCCEEDED
                and operation.ready_closure_ref is not None
            ):
                return RecoveryOutcome(
                    disposition=RecoveryOutcomeDisposition.PUBLISHED,
                    diagnostic_code=None,
                    reason=None,
                )
            if step.step_name == PREVIEW_STEP_PUBLISH:
                handler = build_publish_preview_handler(deps)
                try:
                    acknowledgment = handler(operation, step, control, lease_session)
                except (PreviewJobError, CheckpointDecodeError, PayloadDecodeError) as exc:
                    return RecoveryOutcome(
                        disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
                        diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
                        reason=str(exc),
                    )
                if acknowledgment is ExecutorAcknowledgment.PUBLISHED:
                    return RecoveryOutcome(
                        disposition=RecoveryOutcomeDisposition.PUBLISHED,
                        diagnostic_code=None,
                        reason=None,
                    )
            return RecoveryOutcome(
                disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
                diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
                reason="preview recovery requires a runnable handler replay",
            )

    return cast(RecoveryPort, _PreviewRecoveryPort())


__all__ = [
    "preview_job_definitions",
    "preview_payload_decoders",
    "bind_control_transaction_factory",
    "preview_composition_bundle",
    "build_preview_recovery_port",
]
