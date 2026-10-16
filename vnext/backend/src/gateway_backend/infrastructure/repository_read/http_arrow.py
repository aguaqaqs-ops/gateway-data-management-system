"""Sync HTTP/Arrow adapter for exact-commit Repository table access."""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import cast
from uuid import UUID

import httpx
import pyarrow as pa
import pyarrow.ipc as ipc
from gateway_repository_client import RepositoryClient
from gateway_repository_client.arrow_stream import ArrowIpcByteStream
from gateway_repository_client.errors import (
    RepositoryClientError,
    RepositoryProtocolError,
    RepositoryStreamError,
)
from gateway_repository_contracts import GetVersionedCatalogResponse
from gateway_repository_contracts import RESPONSE_LIMIT_EXCEEDED_CODE, SERVICE_NOT_READY_CODE
from gateway_shared_kernel import canonicalize_identifier

from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationDiagnosticCode,
    RepositoryCatalogTable,
    RepositoryColumn,
    RepositoryProviderError,
    RepositoryRef,
    RepositoryRefTimeoutPolicy,
    RepositoryTableCatalog,
)

_REPOSITORY_SERVER_CONTRACT_VERSION = 1
_REPOSITORY_ROW_STREAM_IDLE_TIMEOUT_SECONDS = 300.0


class HttpArrowRepositoryTableAccessProvider:
    """Exact-commit Repository table access over HTTP and Arrow IPC."""

    def __init__(
        self,
        *,
        base_url: str,
        bearer_token: str,
        timeout_seconds: float,
        repository_id: str,
        commit_id: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if type(base_url) is not str or not base_url:
            raise ValueError("base_url must be a non-empty string")
        if type(bearer_token) is not str or not bearer_token:
            raise ValueError("bearer_token must be a non-empty string")
        self._base_url = base_url
        self._bearer_token = bearer_token
        self._timeout_seconds = timeout_seconds
        self._repository_id = repository_id
        self._commit_id = commit_id
        self._transport = transport

    def open_ref(
        self,
        repository_ref: RepositoryRef,
        timeout_policy: RepositoryRefTimeoutPolicy | None,
    ) -> HttpArrowRepositoryRefSession:
        if repository_ref.repository_id != self._repository_id:
            raise RepositoryProviderError(
                MaterializationDiagnosticCode.REPOSITORY_REF_NOT_FOUND,
                "repository_id does not match the bound adapter",
            )
        if repository_ref.ref != self._commit_id:
            raise RepositoryProviderError(
                MaterializationDiagnosticCode.REPOSITORY_REF_NOT_FOUND,
                "commit id does not match the bound adapter",
            )
        timeout_seconds = self._timeout_seconds
        if timeout_policy is not None and timeout_policy.open_ref_timeout_ms is not None:
            timeout_seconds = timeout_policy.open_ref_timeout_ms / 1000.0
        return HttpArrowRepositoryRefSession(
            client=_client(
                base_url=self._base_url,
                bearer_token=self._bearer_token,
                timeout_seconds=timeout_seconds,
                transport=self._transport,
            ),
            repository_id=self._repository_id,
            commit_id=self._commit_id,
        )


class HttpArrowRepositoryRefSession:
    def __init__(
        self,
        *,
        client: RepositoryClient,
        repository_id: str,
        commit_id: str,
    ) -> None:
        self._client = client
        self._repository_id = repository_id
        self._commit_id = commit_id
        self._catalog: RepositoryTableCatalog | None = None
        self._closed = False

    def pinned_commit_hash(self) -> str:
        return self._commit_id

    def get_catalog(self) -> RepositoryTableCatalog:
        self._ensure_open()
        if self._catalog is None:
            response = cast(GetVersionedCatalogResponse, _run(self._load_catalog()))
            self._catalog = _catalog_from_response(
                repository_id=self._repository_id,
                ref=self._commit_id,
                commit_id=self._commit_id,
                response=response,
            )
        return self._catalog

    def open_table_reader(self, table_name: str) -> HttpArrowRepositoryTableReader:
        self._ensure_open()
        catalog = self.get_catalog()
        canonical = canonicalize_identifier(table_name)
        matched = None
        for table in catalog.tables:
            if canonicalize_identifier(table.table_name) == canonical:
                matched = table
                break
        if matched is None:
            raise RepositoryProviderError(
                MaterializationDiagnosticCode.REPOSITORY_TABLE_NOT_FOUND,
                f"table {table_name!r} is not in the catalog",
                table=table_name,
            )
        return HttpArrowRepositoryTableReader(matched, self._iter_table_rows)

    def export_table_artifact(self, table_name: str, export_format: str) -> None:
        del table_name, export_format
        return None

    def close(self) -> None:
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RepositoryProviderError(
                MaterializationDiagnosticCode.REPOSITORY_SESSION_CLOSE_FAILED,
                "repository session is closed",
            )

    async def _load_catalog(self) -> GetVersionedCatalogResponse:
        try:
            return cast(
                GetVersionedCatalogResponse,
                await self._client.get_versioned_catalog(
                    repository_id=_as_uuid(self._repository_id),
                    commit_id=self._commit_id,
                ),
            )
        except (RepositoryClientError, RepositoryProtocolError, httpx.HTTPError) as exc:
            raise _repository_read_error("catalog read", exc) from exc

    def _iter_table_rows(self, table_name: str) -> Iterator[tuple[object | None, ...]]:
        try:
            ipc_path = cast(str, _run(self._spool_table_ipc(table_name)))
        except (
            RepositoryClientError,
            RepositoryProtocolError,
            RepositoryStreamError,
            httpx.HTTPError,
            OSError,
        ) as exc:
            raise _repository_read_error("table row read", exc, table=table_name) from exc
        try:
            yield from _iter_rows_from_ipc_path(ipc_path)
        except (OSError, pa.ArrowException, ValueError) as exc:
            raise RepositoryProviderError(
                MaterializationDiagnosticCode.REPOSITORY_TABLE_READ_FAILED,
                f"table row decoding failed: {type(exc).__name__}",
                table=table_name,
            ) from exc
        finally:
            Path(ipc_path).unlink(missing_ok=True)

    async def _spool_table_ipc(self, table_name: str) -> str:
        stream = self._client.stream_versioned_table_rows(
            repository_id=_as_uuid(self._repository_id),
            commit_id=self._commit_id,
            table_name=table_name,
        )
        return await _spool_arrow_ipc(stream)


class HttpArrowRepositoryTableReader:
    def __init__(
        self,
        table: RepositoryCatalogTable,
        rows_factory: Callable[[str], Iterator[tuple[object | None, ...]]],
    ) -> None:
        self._table = table
        self._rows_factory = rows_factory
        self._closed = False

    def catalog_table(self) -> RepositoryCatalogTable:
        return self._table

    def column_order(self) -> tuple[str, ...]:
        return tuple(column.name for column in self._table.columns)

    def stream_rows(self) -> Iterator[tuple[object | None, ...]]:
        yield from self._rows_factory(self._table.table_name)

    def close(self) -> None:
        self._closed = True


def build_http_repository_provider_factory(
    *,
    base_url: str,
    bearer_token: str,
    timeout_seconds: float,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Callable[[str, str], HttpArrowRepositoryTableAccessProvider]:
    if type(bearer_token) is not str or bearer_token == "":
        raise ValueError("repository bearer token is missing")
    bound_token = bearer_token

    def factory(repository_id: str, commit_id: str) -> HttpArrowRepositoryTableAccessProvider:
        if bound_token == "":
            raise ValueError("repository bearer token is missing")
        return HttpArrowRepositoryTableAccessProvider(
            base_url=base_url,
            bearer_token=bound_token,
            timeout_seconds=timeout_seconds,
            repository_id=repository_id,
            commit_id=commit_id,
            transport=transport,
        )

    return factory


def _client(
    *,
    base_url: str,
    bearer_token: str,
    timeout_seconds: float,
    transport: httpx.AsyncBaseTransport | None,
) -> RepositoryClient:
    return RepositoryClient(
        base_url=base_url,
        bearer_token=bearer_token,
        timeout_seconds=timeout_seconds,
        stream_idle_timeout_seconds=_REPOSITORY_ROW_STREAM_IDLE_TIMEOUT_SECONDS,
        transport=transport,
    )


def _run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


def _as_uuid(repository_id: str) -> UUID:
    try:
        return UUID(repository_id)
    except ValueError as exc:
        raise RepositoryProviderError(
            MaterializationDiagnosticCode.REPOSITORY_REF_NOT_FOUND,
            "repository_id must be a UUID",
        ) from exc


def _repository_read_error(
    operation: str,
    exc: BaseException,
    *,
    table: str | None = None,
) -> RepositoryProviderError:
    code = (
        MaterializationDiagnosticCode.REPOSITORY_CATALOG_LOAD_FAILED
        if operation == "catalog read"
        else MaterializationDiagnosticCode.REPOSITORY_TABLE_READ_FAILED
    )
    if isinstance(exc, RepositoryClientError):
        wire_code = exc.error.code
        retryable = (
            wire_code == SERVICE_NOT_READY_CODE
            or (exc.status_code >= 500 and wire_code != RESPONSE_LIMIT_EXCEEDED_CODE)
        )
        detail = f"{wire_code}: {exc.error.message}"
    elif isinstance(exc, RepositoryProtocolError):
        retryable = False
        detail = f"repository protocol error: {exc.message}"
    elif isinstance(exc, RepositoryStreamError):
        retryable = True
        detail = exc.message
    elif isinstance(exc, httpx.HTTPError):
        retryable = True
        detail = f"repository transport error: {type(exc).__name__}"
    elif isinstance(exc, OSError):
        retryable = True
        detail = f"repository stream I/O error: {type(exc).__name__}"
    else:
        retryable = False
        detail = f"repository read error: {type(exc).__name__}"
    return RepositoryProviderError(
        code,
        f"{operation} failed ({detail})",
        retryable=retryable,
        table=table,
    )


async def _spool_arrow_ipc(stream: ArrowIpcByteStream) -> str:
    handle = tempfile.NamedTemporaryFile(prefix="gateway-arrow-", suffix=".ipc", delete=False)
    path = handle.name
    try:
        with handle:
            async with stream:
                async for chunk in stream.aiter_bytes():
                    handle.write(chunk)
    except BaseException:
        Path(path).unlink(missing_ok=True)
        raise
    return path


def _iter_rows_from_ipc_path(path: str) -> Iterator[tuple[object | None, ...]]:
    with Path(path).open("rb") as handle:
        reader = ipc.open_stream(handle)
        for batch in reader:
            columns = [batch.column(index).to_pylist() for index in range(batch.num_columns)]
            if not columns:
                continue
            for values in zip(*columns, strict=True):
                yield tuple(values)


def _catalog_from_response(
    *,
    repository_id: str,
    ref: str,
    commit_id: str,
    response: GetVersionedCatalogResponse,
) -> RepositoryTableCatalog:
    tables: list[RepositoryCatalogTable] = []
    for table in response.catalog.tables:
        columns = tuple(
            RepositoryColumn(
                name=str(column.name),
                ordinal=index,
                scalar_type=str(column.sql_type),
                nullable=bool(column.nullable),
            )
            for index, column in enumerate(table.columns)
        )
        tables.append(
            RepositoryCatalogTable(
                table_name=str(table.name),
                columns=columns,
                primary_key_columns=tuple(str(name) for name in table.primary_key),
                row_count=int(table.row_count),
            )
        )
    return RepositoryTableCatalog(
        repository_id=repository_id,
        repository_ref=ref,
        resolved_commit_hash=commit_id,
        repository_server_contract_version=_REPOSITORY_SERVER_CONTRACT_VERSION,
        tables=tuple(tables),
    )
