"""HTTP orchestration for commit-pinned versioned reads."""

from __future__ import annotations

import threading
from uuid import UUID

from gateway_repository_contracts import (
    GetVersionedCatalogResponse,
    ResolveVersionedRefResponse,
    SERVICE_NOT_READY_CODE,
    StreamVersionedTableRowsQuery,
)
from gateway_repository_service.admission import PermitLease, PermitPool
from gateway_repository_service.diagnostics import log_event
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.versioned_read.arrow_bridge import ArrowIpcStreamBridge
from gateway_repository_service.versioned_read.ports import VersionedReadPort
from gateway_repository_service.versioned_read.wire import (
    build_catalog_response,
    build_resolve_response,
    raise_read_error,
)


class VersionedReadHttpService:
    """Maps HTTP inputs to the private read application boundary."""

    def __init__(
        self,
        application: VersionedReadPort,
        *,
        dolt_runner: DoltRunner | None = None,
        row_stream_admission: PermitPool | None = None,
        request_id: str | None = None,
    ) -> None:
        self._application = application
        self._dolt_runner = dolt_runner
        self._row_stream_admission = row_stream_admission
        self._request_id = request_id

    def resolve_ref(self, repository_id: UUID) -> ResolveVersionedRefResponse:
        try:
            commit_id = self._application.resolve_main(repository_id)
        except Exception as exc:
            raise_read_error(exc)
        return build_resolve_response(commit_id)

    def get_catalog(self, repository_id: UUID, commit_id: str) -> GetVersionedCatalogResponse:
        try:
            tables = self._application.get_catalog(repository_id, commit_id)
        except Exception as exc:
            raise_read_error(exc)
        return build_catalog_response(commit_id, tables)

    def open_row_stream(
        self,
        repository_id: UUID,
        commit_id: str,
        query: StreamVersionedTableRowsQuery,
    ) -> tuple[ArrowIpcStreamBridge, PermitLease | None]:
        lease = self._acquire_row_stream_permit(repository_id)
        cancellation = threading.Event()
        stream_owner = object()
        try:
            try:
                plan, rows = self._application.open_table_rows(
                    repository_id,
                    commit_id,
                    query.table_name,
                    query.unknown_type_policy,
                    cancellation=cancellation.is_set,
                    stream_owner=stream_owner,
                )
            except Exception as exc:
                raise_read_error(exc)
            bridge = ArrowIpcStreamBridge(
                plan,
                rows,
                cancellation,
                dolt_runner=self._dolt_runner,
                stream_owner=stream_owner,
            )
            return bridge, lease
        except Exception:
            if lease is not None:
                lease.release()
                snap = (
                    self._row_stream_admission.snapshot()
                    if self._row_stream_admission is not None
                    else None
                )
                log_event(
                    "row_stream_admission_released",
                    request_id=self._request_id,
                    repository_id=repository_id,
                    capacity=snap.capacity if snap is not None else None,
                    in_use=snap.in_use if snap is not None else None,
                    result="released",
                    cleanup_outcome="open_failed",
                )
            raise

    def _acquire_row_stream_permit(self, repository_id: UUID) -> PermitLease | None:
        pool = self._row_stream_admission
        if pool is None:
            return None
        lease = pool.try_acquire()
        snap = pool.snapshot()
        if lease is None:
            log_event(
                "row_stream_admission_denied",
                request_id=self._request_id,
                repository_id=repository_id,
                capacity=snap.capacity,
                in_use=snap.in_use,
                result="denied",
                code=SERVICE_NOT_READY_CODE,
            )
            raise ServiceError(
                code=SERVICE_NOT_READY_CODE,
                message="service is not ready",
                status_code=503,
            )
        log_event(
            "row_stream_admission_acquired",
            request_id=self._request_id,
            repository_id=repository_id,
            capacity=snap.capacity,
            in_use=snap.in_use,
            result="acquired",
        )
        return lease
