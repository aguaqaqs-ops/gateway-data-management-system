"""Wire mapping for versioned import operation polling."""

from __future__ import annotations

from gateway_repository_contracts import (
    GetOperationResponse,
    MAX_OPERATION_JSON_BYTES,
    RESPONSE_LIMIT_EXCEEDED_CODE,
)
from gateway_repository_service.http.errors import ServiceError

def build_operation_response(operation_response: GetOperationResponse) -> GetOperationResponse:
    wire_size = len(operation_response.model_dump_json().encode("utf-8"))
    if wire_size > MAX_OPERATION_JSON_BYTES:
        raise ServiceError(
            code=RESPONSE_LIMIT_EXCEEDED_CODE,
            message="response limit exceeded",
            status_code=500,
        )
    return operation_response
