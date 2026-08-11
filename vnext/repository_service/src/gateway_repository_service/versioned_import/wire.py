"""Wire mapping for versioned import operation polling."""

from __future__ import annotations

from gateway_repository_contracts import (
    GetOperationResponse,
    MAX_OPERATION_JSON_BYTES,
    SERVICE_NOT_READY_CODE,
)
from gateway_repository_service.http.errors import ServiceError

_SERVICE_NOT_READY_MESSAGE = "service is not ready"


def build_operation_response(operation_response: GetOperationResponse) -> GetOperationResponse:
    wire_size = len(operation_response.model_dump_json().encode("utf-8"))
    if wire_size > MAX_OPERATION_JSON_BYTES:
        raise ServiceError(
            code=SERVICE_NOT_READY_CODE,
            message=_SERVICE_NOT_READY_MESSAGE,
            status_code=503,
        )
    return operation_response
