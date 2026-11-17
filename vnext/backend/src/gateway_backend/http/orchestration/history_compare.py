"""History compare HTTP DTO mapping and acceptance orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from gateway_backend.application.history.compare import (
    HistoryCompareAcceptanceResult as ApplicationHistoryCompareAcceptanceResult,
    accept_history_compare,
)
from gateway_backend.application.history.contracts import (
    HistoryCompareAcceptCommand,
    HistoryCompareListPage,
    HistoryCompareResultRead,
    HistoryNodeRef,
)
from gateway_backend.application.history.ports import (
    BundleReaderPort,
    HistoryControlUnitOfWorkFactory,
)
from gateway_backend.application.history.results import preflight_history_result
from gateway_backend.application.job_definitions import JobDefinitionRegistry
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.dependencies import AdmissionGatePort, acquire_new_work
from gateway_backend.http.errors import ApiError, map_domain_exception
from gateway_backend.http.schemas.history import (
    HistoryCompareAcceptResponse,
    HistoryCompareDiagnosticResponse,
    HistoryCompareListItemResponse,
    HistoryCompareListResponse,
    HistoryComparePairResultResponse,
    HistoryCompareResultInputResponse,
    HistoryCompareResultResponse,
    HistoryNodeRefResponse,
)
from gateway_backend.http.schemas.operation import OperationDiagnosticDetailResponse
from gateway_backend.operations.contracts import OperationStatus


@dataclass(frozen=True, slots=True)
class HistoryCompareAcceptanceResult:
    response: HistoryCompareAcceptResponse
    replay: bool


def accept_compare_operation(
    *,
    command: HistoryCompareAcceptCommand,
    unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    job_registry: JobDefinitionRegistry,
    admission_gate: AdmissionGatePort,
    comparison_ruleset_digest: str,
    now: datetime,
    result_retention_seconds: int = 86_400,
    history_scope_active_limit: int = 2,
    operation_queue_limit: int = 32,
    artifact_store: object | None = None,
    bundle_reader: BundleReaderPort | None = None,
    resolve_current_identity: Callable[[], IdentityContext] | None = None,
) -> HistoryCompareAcceptanceResult:
    try:
        with acquire_new_work(
            admission_gate,
            closed_code="ADMISSION_CONFLICT",
            closed_status=409,
        ):
            result = accept_history_compare(
                command=command,
                unit_of_work_factory=unit_of_work_factory,
                job_registry=job_registry,
                comparison_ruleset_digest=comparison_ruleset_digest,
                now=now,
                result_retention_seconds=result_retention_seconds,
                history_scope_active_limit=history_scope_active_limit,
                operation_queue_limit=operation_queue_limit,
                resolve_current_identity=resolve_current_identity,
                preflight=(
                    None
                    if artifact_store is None or bundle_reader is None
                    else lambda operation, acceptance: preflight_history_result(
                        operation=operation,
                        acceptance=acceptance,
                        unit_of_work_factory=unit_of_work_factory,
                        artifact_store=artifact_store,
                        bundle_reader=bundle_reader,
                    )
                ),
            )
    except ApiError:
        raise
    except Exception as exc:
        mapped = map_domain_exception(exc)
        if mapped is None:
            raise
        raise mapped from exc
    return HistoryCompareAcceptanceResult(
        response=history_compare_acceptance_to_response(result),
        replay=result.replay,
    )


def history_compare_acceptance_to_response(
    result: ApplicationHistoryCompareAcceptanceResult,
) -> HistoryCompareAcceptResponse:
    return HistoryCompareAcceptResponse(
        operation_id=result.operation_id,
        status=public_operation_status(result.status),
        replayed=result.replay,
    )


def history_compare_list_to_response(
    page: HistoryCompareListPage,
) -> HistoryCompareListResponse:
    return HistoryCompareListResponse(
        items=[
            HistoryCompareListItemResponse(
                operation_id=item.operation_id,
                nodes=[
                    HistoryNodeRefResponse(ref_kind=node.ref_kind.value, ref_id=node.ref_id)
                    for node in item.nodes
                ],
                status=public_operation_status(item.status),
                accepted_at=item.accepted_at,
                completed_at=item.completed_at,
                result_expires_at=item.result_expires_at,
            )
            for item in page.items
        ],
        next_cursor=page.next_cursor,
    )


def history_compare_result_to_response(
    read_result: HistoryCompareResultRead,
) -> HistoryCompareResultResponse:
    diagnostic = None
    if read_result.diagnostic is not None:
        diagnostic = HistoryCompareDiagnosticResponse(
            code=read_result.diagnostic.code,
            message=read_result.diagnostic.message,
            details=(
                None
                if read_result.diagnostic.details is None
                else [
                    OperationDiagnosticDetailResponse(
                        code=item.code,
                        side=item.side.value,
                        table_name=item.table_name,
                        column_name=item.column_name,
                    )
                    for item in read_result.diagnostic.details
                ]
            ),
            omitted_count=read_result.diagnostic.omitted_count,
        )
    result = None
    if read_result.result is not None:
        data = read_result.result
        result = HistoryCompareResultInputResponse(
            input={
                "nodes": [
                    {
                        "ref_kind": node.ref_kind.value,
                        "ref_id": node.ref_id,
                        "commit_id": node.commit_id,
                    }
                    for node in data.nodes
                ],
                "commits": [node.commit_id for node in data.nodes],
            },
            pairs=[
                HistoryComparePairResultResponse(
                    pair_id=pair.pair_id,
                    before_ref=HistoryNodeRefResponse(
                        ref_kind=pair.before_ref.ref_kind.value,
                        ref_id=pair.before_ref.ref_id,
                    ),
                    before_commit=pair.before_commit,
                    current_ref=HistoryNodeRefResponse(
                        ref_kind=pair.current_ref.ref_kind.value,
                        ref_id=pair.current_ref.ref_id,
                    ),
                    current_commit=pair.current_commit,
                    comparison_digest=pair.comparison_digest,
                    risk_digest=pair.risk_digest,
                    surface_digest=pair.surface_digest,
                    record_count=pair.record_count,
                )
                for pair in data.pairs
            ],
            bundle_digest=data.bundle_digest,
            completed_at=data.completed_at,
        )
    return HistoryCompareResultResponse(
        operation_id=read_result.operation_id,
        status=public_operation_status(read_result.status),
        diagnostic=diagnostic,
        result=result,
    )


def public_operation_status(
    status: OperationStatus,
) -> Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]:
    if status is OperationStatus.QUEUED:
        return "QUEUED"
    if status is OperationStatus.RUNNING:
        return "RUNNING"
    if status is OperationStatus.SUCCEEDED:
        return "SUCCEEDED"
    if status is OperationStatus.FAILED:
        return "FAILED"
    if status is OperationStatus.CANCELLED:
        return "CANCELLED"
    return cast(Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"], status.value)


def build_history_compare_accept_command(
    *,
    context: object,
    idempotency_key: str,
    node_refs: tuple[HistoryNodeRef, ...],
) -> HistoryCompareAcceptCommand:
    if type(context) is not IdentityContext:
        raise TypeError("context must be IdentityContext")
    return HistoryCompareAcceptCommand(
        context=context,
        idempotency_key=idempotency_key,
        node_refs=node_refs,
    )
