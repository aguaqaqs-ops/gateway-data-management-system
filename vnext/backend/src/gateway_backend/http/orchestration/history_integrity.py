"""History compare integrity acknowledgement orchestration."""

from __future__ import annotations

from datetime import datetime

from gateway_backend.application.history.contracts import IntegrityAcknowledgementStatus
from gateway_backend.application.history.errors import HistoryCompareIntegrityAckConflict
from gateway_backend.application.history.ports import HistoryControlUnitOfWorkFactory
from gateway_backend.http.errors import ApiError
from gateway_backend.http.schemas.history import (
    IntegrityAcknowledgementResponse,
    IntegrityIncidentResponse,
)


def acknowledge_integrity_incident(
    *,
    operation_id: str,
    acknowledgement_status: str,
    resolution_reference: str,
    unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    now: datetime,
) -> IntegrityAcknowledgementResponse:
    if acknowledgement_status != IntegrityAcknowledgementStatus.ACKNOWLEDGED.value:
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="acknowledgement_status must be ACKNOWLEDGED",
            status_code=422,
        )
    with unit_of_work_factory() as unit_of_work:
        acceptance = unit_of_work.history_compare.get_acceptance_by_operation_id(operation_id)
        if acceptance is None:
            raise ApiError(
                code="RESOURCE_NOT_FOUND",
                message="resource not found",
                status_code=404,
            )
        existing = unit_of_work.history_compare.get_integrity_by_operation_id(operation_id)
        if existing is None:
            raise ApiError(
                code="RESOURCE_NOT_FOUND",
                message="resource not found",
                status_code=404,
            )
        try:
            updated = unit_of_work.history_compare.acknowledge_integrity(
                operation_id=operation_id,
                resolution_reference=resolution_reference,
                updated_at=now,
            )
        except HistoryCompareIntegrityAckConflict as exc:
            raise ApiError(
                code="IDEMPOTENCY_CONFLICT",
                message="integrity resolution_reference conflict",
                status_code=409,
            ) from exc
        except ValueError as exc:
            raise ApiError(
                code="HISTORY_INTEGRITY_FAILURE",
                message=str(exc),
                status_code=503,
            ) from exc
    incident = IntegrityIncidentResponse.from_record(updated)
    return IntegrityAcknowledgementResponse(**incident.model_dump())
