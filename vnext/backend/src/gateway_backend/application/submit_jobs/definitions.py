"""Submit decoders, transaction binding, and worker composition."""

from __future__ import annotations

from collections.abc import Mapping
from gateway_backend.application.job_definitions import JobDefinition
from gateway_backend.application.payloads import PayloadDecoder
from gateway_backend.application.submission.ports import (
    SubmitControlTransaction,
    SubmitControlUnitOfWorkFactory,
    SubmitFinalizeControlTransaction,
)
from gateway_backend.application.submit_registry import (
    AWAIT_IMPORT_DECODER,
    AWAIT_IMPORT_HANDLER,
    PREPARE_IMPORT_DECODER,
    PREPARE_IMPORT_HANDLER,
    SUBMIT_IMPORT_DECODER,
    SUBMIT_IMPORT_HANDLER,
    submit_job_definitions,
)
from gateway_backend.operations.worker import ClaimedExecutor
from types import TracebackType
from typing import ContextManager

from gateway_backend.application.submit_jobs.await_result import build_await_import_result_handler
from gateway_backend.application.submit_jobs.checkpoint import _active_submit_transaction
from gateway_backend.application.submit_jobs.payload import (
    SubmitControlTransactionFactory,
    SubmitRuntimeDependencies,
    decode_submit_payload,
)
from gateway_backend.application.submit_jobs.prepare import build_prepare_import_handler
from gateway_backend.application.submit_jobs.submit import build_submit_import_handler

def submit_payload_decoders() -> Mapping[str, PayloadDecoder]:
    decoder: PayloadDecoder = decode_submit_payload
    return {
        PREPARE_IMPORT_DECODER: decoder,
        SUBMIT_IMPORT_DECODER: decoder,
        AWAIT_IMPORT_DECODER: decoder,
    }

def bind_submit_control_transaction_factory(
    inner: SubmitControlTransactionFactory,
) -> SubmitControlTransactionFactory:
    """Bind the active submit transaction for checkpoint and crossing writes."""

    class _BoundUnitOfWork:
        def __init__(self, wrapped: ContextManager[SubmitFinalizeControlTransaction]) -> None:
            self._wrapped = wrapped

        def __enter__(self) -> SubmitFinalizeControlTransaction:
            transaction = self._wrapped.__enter__()
            _active_submit_transaction.set(transaction)
            return transaction

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool | None:
            _active_submit_transaction.set(None)
            return self._wrapped.__exit__(exc_type, exc, tb)

    def factory() -> ContextManager[SubmitFinalizeControlTransaction]:
        return _BoundUnitOfWork(inner())

    return factory

def submit_composition_bundle(
    deps: SubmitRuntimeDependencies,
) -> tuple[
    tuple[JobDefinition, ...],
    Mapping[str, ClaimedExecutor],
    Mapping[str, PayloadDecoder],
    SubmitRuntimeDependencies,
]:
    bound_deps = SubmitRuntimeDependencies(
        artifact_store=deps.artifact_store,
        publication=deps.publication,
        parent_catalog=deps.parent_catalog,
        repository_write=deps.repository_write,
        terminal_evidence_decode=deps.terminal_evidence_decode,
        control_transaction_factory=bind_submit_control_transaction_factory(
            deps.control_transaction_factory
        ),
        submission_id_factory=deps.submission_id_factory,
        now_factory=deps.now_factory,
    )
    return (
        submit_job_definitions(),
        {
            PREPARE_IMPORT_HANDLER: build_prepare_import_handler(bound_deps),
            SUBMIT_IMPORT_HANDLER: build_submit_import_handler(bound_deps),
            AWAIT_IMPORT_HANDLER: build_await_import_result_handler(bound_deps),
        },
        dict(submit_payload_decoders()),
        bound_deps,
    )

def read_write_factory(
    factory: SubmitControlTransactionFactory,
) -> SubmitControlUnitOfWorkFactory:
    def unit_of_work_factory(
        *, read_only: bool = False
    ) -> ContextManager[SubmitControlTransaction]:
        del read_only
        return factory()

    return unit_of_work_factory


__all__ = [
    "submit_payload_decoders",
    "bind_submit_control_transaction_factory",
    "submit_composition_bundle",
    "read_write_factory",
]
