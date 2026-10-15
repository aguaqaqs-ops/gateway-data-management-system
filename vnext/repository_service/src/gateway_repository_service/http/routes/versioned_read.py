"""Commit-pinned versioned read routes."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Path, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from gateway_repository_contracts import (
    COMMIT_ID_PATH_SEGMENT_PATTERN,
    GetVersionedCatalogResponse,
    MAX_COMMIT_ID_PATH_SEGMENT_LENGTH,
    ResolveVersionedRefResponse,
    StreamVersionedTableRowsQuery,
    VERSIONED_READ_ARROW_MEDIA_TYPE,
    UnknownTypePolicy,
    VersionedTableNameString,
    decode_commit_id_path_segment,
)
from gateway_repository_service.diagnostics import log_event
from gateway_repository_service.http.auth import require_bearer_token
from gateway_repository_service.http.openapi import (
    versioned_read_arrow_stream_response,
    versioned_read_json_responses,
)
from gateway_repository_service.http.readiness_guard import require_service_ready
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.versioned_read.http_service import VersionedReadHttpService
from gateway_repository_service.versioned_read.streaming_response import VersionedReadStreamingResponse
from gateway_repository_service.versioned_read.wire import request_validation_failed


def register_versioned_read_routes(app: FastAPI) -> None:
    @app.get(
        "/v1/repositories/{repository_id}/versioned/refs/{ref_name}",
        response_model=ResolveVersionedRefResponse,
        status_code=200,
        responses=versioned_read_json_responses(success_description="Resolved versioned ref"),
    )
    def resolve_versioned_ref(
        request: Request,
        repository_id: UUID,
        ref_name: Literal["main"],
        _authorized: Annotated[None, Depends(require_bearer_token)],
        _ready: Annotated[None, Depends(require_service_ready)],
    ) -> ResolveVersionedRefResponse:
        del ref_name
        service = _read_service_from_runtime(_runtime_from_state(request))
        return service.resolve_ref(repository_id)

    @app.get(
        "/v1/repositories/{repository_id}/versioned/commits/{commit_id}/catalog",
        response_model=GetVersionedCatalogResponse,
        status_code=200,
        responses=versioned_read_json_responses(
            success_description="Versioned catalog",
            response_limit_exceeded=True,
        ),
    )
    def get_versioned_catalog(
        request: Request,
        repository_id: UUID,
        commit_id: Annotated[
            str,
            Path(
                min_length=1,
                max_length=MAX_COMMIT_ID_PATH_SEGMENT_LENGTH,
                pattern=COMMIT_ID_PATH_SEGMENT_PATTERN,
                description="Canonical base64url (no padding) encoding of the logical CommitId.",
            ),
        ],
        _authorized: Annotated[None, Depends(require_bearer_token)],
        _ready: Annotated[None, Depends(require_service_ready)],
    ) -> GetVersionedCatalogResponse:
        validated_commit_id = _decoded_commit_id(commit_id)
        service = _read_service_from_runtime(_runtime_from_state(request))
        return service.get_catalog(repository_id, validated_commit_id)

    @app.get(
        "/v1/repositories/{repository_id}/versioned/commits/{commit_id}/rows",
        status_code=200,
        response_class=StreamingResponse,
        responses=versioned_read_arrow_stream_response(),
    )
    def stream_versioned_table_rows(
        request: Request,
        repository_id: UUID,
        commit_id: Annotated[
            str,
            Path(
                min_length=1,
                max_length=MAX_COMMIT_ID_PATH_SEGMENT_LENGTH,
                pattern=COMMIT_ID_PATH_SEGMENT_PATTERN,
                description="Canonical base64url (no padding) encoding of the logical CommitId.",
            ),
        ],
        _authorized: Annotated[None, Depends(require_bearer_token)],
        _ready: Annotated[None, Depends(require_service_ready)],
        table_name: Annotated[VersionedTableNameString, Query()],
        unknown_type_policy: Annotated[UnknownTypePolicy, Query()] = UnknownTypePolicy.REJECT,
    ) -> StreamingResponse:
        validated_commit_id = _decoded_commit_id(commit_id)
        query = _validated_rows_query(table_name, unknown_type_policy)
        runtime = _runtime_from_state(request)
        request_id = getattr(request.state, "request_id", None)
        request_id_str = str(request_id) if request_id is not None else None
        service = VersionedReadHttpService(
            runtime.versioned_read_application,
            dolt_runner=runtime.dolt_runner,
            row_stream_admission=runtime.row_stream_admission,
            request_id=request_id_str,
        )
        bridge, lease = service.open_row_stream(repository_id, validated_commit_id, query)
        try:
            return VersionedReadStreamingResponse(
                bridge,
                bridge.iter_bytes(),
                media_type=VERSIONED_READ_ARROW_MEDIA_TYPE,
                permit_lease=lease,
                request_id=request_id_str,
                repository_id=str(repository_id),
                admission_capacity=runtime.row_stream_admission.capacity,
            )
        except BaseException as construction_error:
            cleanup_error: BaseException | None = None
            try:
                bridge.close_sync(dolt_runner=runtime.dolt_runner)
            except BaseException as exc:
                cleanup_error = exc
            finally:
                if lease is not None:
                    lease.release()
                    log_event(
                        "row_stream_admission_released",
                        request_id=request_id_str,
                        repository_id=repository_id,
                        capacity=runtime.row_stream_admission.capacity,
                        result="released",
                        cleanup_outcome=(
                            "bridge_cleanup_error"
                            if cleanup_error is not None
                            else "construct_failed_closed"
                        ),
                    )
            if cleanup_error is not None:
                raise cleanup_error
            raise construction_error


def _runtime_from_state(request: Request) -> ServiceRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ServiceRuntime):
        raise RuntimeError("service runtime is not initialized")
    return runtime


def _read_service_from_runtime(runtime: ServiceRuntime) -> VersionedReadHttpService:
    return VersionedReadHttpService(
        runtime.versioned_read_application,
        dolt_runner=runtime.dolt_runner,
        row_stream_admission=runtime.row_stream_admission,
    )


def _decoded_commit_id(segment: str) -> str:
    try:
        return decode_commit_id_path_segment(segment)
    except ValueError as exc:
        validation_error = ValidationError.from_exception_data(
            "CommitIdString",
            [
                {
                    "type": "value_error",
                    "loc": ("commit_id",),
                    "input": segment,
                    "ctx": {"error": str(exc)},
                }
            ],
        )
        raise request_validation_failed(validation_error) from exc


def _validated_rows_query(
    table_name: str,
    unknown_type_policy: UnknownTypePolicy,
) -> StreamVersionedTableRowsQuery:
    try:
        return StreamVersionedTableRowsQuery(
            table_name=table_name,
            unknown_type_policy=unknown_type_policy,
        )
    except ValidationError as exc:
        raise request_validation_failed(exc) from exc
