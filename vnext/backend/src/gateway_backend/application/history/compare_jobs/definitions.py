"""History compare JobDefinition registry, decoders, and worker composition."""

from __future__ import annotations

from collections.abc import Mapping
from gateway_backend.application.history.ports import (
    HistoryControlTransaction as HistoryCompareControlTransaction,
)
from gateway_backend.application.job_definitions import JobDefinition
from gateway_backend.application.payloads import PayloadDecoder
from gateway_backend.operations.worker import ClaimedExecutor
from types import TracebackType
from typing import ContextManager

from gateway_backend.application.history.compare_jobs.assemble import (
    build_assemble_comparison_handler,
)
from gateway_backend.application.history.compare_jobs.checkpoint import (
    _active_history_compare_transaction,
)
from gateway_backend.application.history.compare_jobs.materialize import (
    build_materialize_inputs_handler,
)
from gateway_backend.application.history.compare_jobs.payload import (
    HISTORY_COMPARE_ASSEMBLE_DECODER,
    HISTORY_COMPARE_ASSEMBLE_HANDLER,
    HISTORY_COMPARE_MATERIALIZE_DECODER,
    HISTORY_COMPARE_MATERIALIZE_HANDLER,
    HISTORY_COMPARE_PUBLISH_DECODER,
    HISTORY_COMPARE_PUBLISH_HANDLER,
    HistoryCompareControlTransactionFactory,
    HistoryCompareRuntimeDependencies,
    decode_history_compare_payload,
    history_compare_assemble_job_definition,
    history_compare_materialize_job_definition,
    history_compare_publish_job_definition,
)
from gateway_backend.application.history.compare_jobs.publish import build_publish_result_handler

def history_compare_job_definitions() -> tuple[JobDefinition, ...]:
    return (
        history_compare_materialize_job_definition(),
        history_compare_assemble_job_definition(),
        history_compare_publish_job_definition(),
    )

def history_compare_payload_decoders() -> Mapping[str, PayloadDecoder]:
    decoder: PayloadDecoder = decode_history_compare_payload
    return {
        HISTORY_COMPARE_MATERIALIZE_DECODER: decoder,
        HISTORY_COMPARE_ASSEMBLE_DECODER: decoder,
        HISTORY_COMPARE_PUBLISH_DECODER: decoder,
    }

def bind_history_compare_transaction_factory(
    inner: HistoryCompareControlTransactionFactory,
) -> HistoryCompareControlTransactionFactory:
    class _BoundUnitOfWork:
        def __init__(self, wrapped: ContextManager[HistoryCompareControlTransaction]) -> None:
            self._wrapped = wrapped

        def __enter__(self) -> HistoryCompareControlTransaction:
            transaction = self._wrapped.__enter__()
            _active_history_compare_transaction.set(transaction)
            return transaction

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool | None:
            _active_history_compare_transaction.set(None)
            return self._wrapped.__exit__(exc_type, exc, tb)

    def factory() -> ContextManager[HistoryCompareControlTransaction]:
        return _BoundUnitOfWork(inner())

    return factory

def history_compare_composition_bundle(
    deps: HistoryCompareRuntimeDependencies,
) -> tuple[
    tuple[JobDefinition, ...],
    Mapping[str, ClaimedExecutor],
    Mapping[str, PayloadDecoder],
    HistoryCompareRuntimeDependencies,
]:
    bound_deps = HistoryCompareRuntimeDependencies(
        artifact_store=deps.artifact_store,
        repository_provider_factory=deps.repository_provider_factory,
        control_transaction_factory=bind_history_compare_transaction_factory(
            deps.control_transaction_factory
        ),
        snapshot_export_cache=deps.snapshot_export_cache,
        computation_cache=deps.computation_cache,
    )
    return (
        history_compare_job_definitions(),
        {
            HISTORY_COMPARE_MATERIALIZE_HANDLER: build_materialize_inputs_handler(bound_deps),
            HISTORY_COMPARE_ASSEMBLE_HANDLER: build_assemble_comparison_handler(bound_deps),
            HISTORY_COMPARE_PUBLISH_HANDLER: build_publish_result_handler(bound_deps),
        },
        dict(history_compare_payload_decoders()),
        bound_deps,
    )


__all__ = [
    "history_compare_job_definitions",
    "history_compare_payload_decoders",
    "bind_history_compare_transaction_factory",
    "history_compare_composition_bundle",
]
