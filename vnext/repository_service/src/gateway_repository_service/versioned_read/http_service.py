"""HTTP orchestration for commit-pinned versioned reads."""

from __future__ import annotations

import threading
from uuid import UUID

from gateway_repository_contracts import (
    GetVersionedCatalogResponse,
    ResolveVersionedRefResponse,
    StreamVersionedTableRowsQuery,
)
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
    ) -> None:
        self._application = application
        self._dolt_runner = dolt_runner

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
    ) -> ArrowIpcStreamBridge:
        cancellation = threading.Event()
        stream_owner = object()
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
        return ArrowIpcStreamBridge(
            plan,
            rows,
            cancellation,
            dolt_runner=self._dolt_runner,
            stream_owner=stream_owner,
        )
