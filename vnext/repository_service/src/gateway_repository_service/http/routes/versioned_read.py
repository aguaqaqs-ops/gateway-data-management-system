"""Commit-pinned versioned read routes."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Path, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter, ValidationError

from gateway_repository_contracts import (
    GetVersionedCatalogResponse,
    ResolveVersionedRefResponse,
    StreamVersionedTableRowsQuery,
    VERSIONED_READ_ARROW_MEDIA_TYPE,
    UnknownTypePolicy,
    VersionedTableNameString,
)
from gateway_repository_contracts.types import CommitIdString
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

_COMMIT_ID_ADAPTER: TypeAdapter[CommitIdString] = TypeAdapter(CommitIdString)


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
        responses=versioned_read_json_responses(success_description="Versioned catalog"),
    )
    def get_versioned_catalog(
        request: Request,
        repository_id: UUID,
        commit_id: Annotated[str, Path(min_length=1, max_length=1024)],
        _authorized: Annotated[None, Depends(require_bearer_token)],
        _ready: Annotated[None, Depends(require_service_ready)],
    ) -> GetVersionedCatalogResponse:
        validated_commit_id = _validated_commit_id(commit_id)
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
        commit_id: Annotated[str, Path(min_length=1, max_length=1024)],
        _authorized: Annotated[None, Depends(require_bearer_token)],
        _ready: Annotated[None, Depends(require_service_ready)],
        table_name: Annotated[VersionedTableNameString, Query()],
        unknown_type_policy: Annotated[UnknownTypePolicy, Query()] = UnknownTypePolicy.REJECT,
    ) -> StreamingResponse:
        validated_commit_id = _validated_commit_id(commit_id)
        query = _validated_rows_query(table_name, unknown_type_policy)
        service = _read_service_from_runtime(_runtime_from_state(request))
        bridge = service.open_row_stream(repository_id, validated_commit_id, query)
        return VersionedReadStreamingResponse(
            bridge,
            bridge.iter_bytes(),
            media_type=VERSIONED_READ_ARROW_MEDIA_TYPE,
        )


def _runtime_from_state(request: Request) -> ServiceRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ServiceRuntime):
        raise RuntimeError("service runtime is not initialized")
    return runtime


def _read_service_from_runtime(runtime: ServiceRuntime) -> VersionedReadHttpService:
    return VersionedReadHttpService(
        runtime.versioned_read_application,
        dolt_runner=runtime.dolt_runner,
    )


def _validated_commit_id(commit_id: str) -> str:
    try:
        return _COMMIT_ID_ADAPTER.validate_python(commit_id)
    except ValidationError as exc:
        raise request_validation_failed(exc) from exc


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
