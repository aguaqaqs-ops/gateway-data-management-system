"""Sync HTTP/Arrow adapter for exact-commit Repository table access."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Iterator
from typing import cast
from uuid import UUID

import httpx
import pyarrow as pa
import pyarrow.ipc as ipc
from gateway_repository_client import RepositoryClient
from gateway_repository_client.arrow_stream import ArrowIpcByteStream
from gateway_repository_contracts import GetVersionedCatalogResponse
from gateway_shared_kernel import canonicalize_identifier

from gateway_backend.capabilities.snapshot_materialization._digest import (
    compare_schema_digest,
    fast_row_digest_of,
    fast_row_hash,
    raw_content_digest_of,
    raw_state_digest_of,
    row_content_hash,
    snapshot_digest_of,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    DIGEST_CONTRACT_VERSION,
    ROW_MATERIALIZATION_PROFILE,
    SCALAR_ENCODING_VERSION,
    SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION,
    SUMMARY_CONTRACT_VERSION,
    DegradedReason,
    HiddenFinalSummary,
    MaterializationDiagnosticCode,
    MaterializationStage,
    RepositoryCatalogTable,
    RepositoryColumn,
    RepositoryProviderError,
    RepositoryRef,
    RepositoryRefTimeoutPolicy,
    RepositoryTableCatalog,
    SnapshotColumnDescriptor,
    SnapshotTableDescriptor,
)
from gateway_backend.capabilities.snapshot_materialization.scalar_encoding import (
    encode_repository_row,
    map_repository_column,
)
from gateway_backend.capabilities.table_access.contracts import PARSER_VERSION
from gateway_backend.capabilities.table_rules.contracts import TABLE_RULESET_VERSION

_REPOSITORY_SERVER_CONTRACT_VERSION = 1


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
        self._rows: dict[str, tuple[tuple[object | None, ...], ...]] = {}
        self._hidden: HiddenFinalSummary | None = None
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

    def read_hidden_summary(self) -> HiddenFinalSummary | None:
        self._ensure_open()
        catalog = self.get_catalog()
        for table in catalog.tables:
            self._rows.setdefault(canonicalize_identifier(table.table_name), self._load_rows(table.table_name))
        if self._hidden is None:
            self._hidden = _hidden_summary_from_catalog(catalog, self._rows)
        return self._hidden

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
        rows = self._rows.get(canonical)
        if rows is None:
            rows = self._load_rows(matched.table_name)
            self._rows[canonical] = rows
        return HttpArrowRepositoryTableReader(matched, rows)

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
        return cast(
            GetVersionedCatalogResponse,
            await self._client.get_versioned_catalog(
                repository_id=_as_uuid(self._repository_id),
                commit_id=self._commit_id,
            ),
        )

    def _load_rows(self, table_name: str) -> tuple[tuple[object | None, ...], ...]:
        return cast(
            tuple[tuple[object | None, ...], ...],
            _run(self._load_rows_async(table_name)),
        )

    async def _load_rows_async(self, table_name: str) -> tuple[tuple[object | None, ...], ...]:
        stream = self._client.stream_versioned_table_rows(
            repository_id=_as_uuid(self._repository_id),
            commit_id=self._commit_id,
            table_name=table_name,
        )
        raw = await _read_arrow_bytes(stream)
        return _tuples_from_ipc(raw)


class HttpArrowRepositoryTableReader:
    def __init__(
        self,
        table: RepositoryCatalogTable,
        rows: tuple[tuple[object | None, ...], ...],
    ) -> None:
        self._table = table
        self._rows = rows
        self._closed = False

    def catalog_table(self) -> RepositoryCatalogTable:
        return self._table

    def column_order(self) -> tuple[str, ...]:
        return tuple(column.name for column in self._table.columns)

    def stream_rows(self) -> Iterator[tuple[object | None, ...]]:
        yield from self._rows

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


async def _read_arrow_bytes(stream: ArrowIpcByteStream) -> bytes:
    chunks: list[bytes] = []
    async with stream:
        async for chunk in stream.aiter_bytes():
            chunks.append(chunk)
    return b"".join(chunks)


def _tuples_from_ipc(raw: bytes) -> tuple[tuple[object | None, ...], ...]:
    reader = ipc.open_stream(pa.BufferReader(raw))
    rows: list[tuple[object | None, ...]] = []
    for batch in reader:
        columns = [batch.column(index).to_pylist() for index in range(batch.num_columns)]
        if not columns:
            continue
        for values in zip(*columns, strict=True):
            rows.append(tuple(values))
    return tuple(rows)


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


def _hidden_summary_from_catalog(
    catalog: RepositoryTableCatalog,
    rows: dict[str, tuple[tuple[object | None, ...], ...]],
) -> HiddenFinalSummary:
    descriptors: list[SnapshotTableDescriptor] = []
    for table in catalog.tables:
        canonical = canonicalize_identifier(table.table_name)
        mapped = tuple(map_repository_column(column) for column in table.columns)
        source_columns = tuple(item.source for item in mapped)
        column_names = tuple(item.canonical_name for item in source_columns)
        compare_keys = tuple(canonicalize_identifier(name) for name in table.primary_key_columns)
        schema = compare_schema_digest(canonical, column_names, compare_keys)
        table_rows = rows.get(canonical, ())
        encoded = tuple(
            encode_repository_row(table.columns, tuple(row), table=canonical).cells
            for row in table_rows
        )
        row_hashes = tuple(row_content_hash(source_columns, row) for row in encoded)
        fast_hashes = tuple(fast_row_hash(source_columns, row) for row in encoded)
        columns = tuple(
            SnapshotColumnDescriptor(
                name=item.canonical_name,
                display_name=item.display_name,
                nullable=item.nullable,
                scalar_type=item.sql_type,
            )
            for item in source_columns
        )
        descriptors.append(
            SnapshotTableDescriptor(
                table_name=canonical,
                display_table_name=table.display_table_name or table.table_name,
                columns=columns,
                primary_key_columns=compare_keys,
                compare_key_columns=compare_keys,
                row_count=len(encoded),
                materialization_stage=MaterializationStage.FINAL,
                compare_schema_digest=schema,
                table_ruleset_version=TABLE_RULESET_VERSION,
                row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
                scalar_encoding_version=SCALAR_ENCODING_VERSION,
                fast_row_digest=fast_row_digest_of(fast_hashes),
                raw_content_digest=raw_content_digest_of(row_hashes),
                degraded_reason=DegradedReason.KEYLESS if not compare_keys else None,
            )
        )
    tables = tuple(descriptors)
    snapshot_id = hashlib.sha256(
        f"{catalog.repository_id}:{catalog.resolved_commit_hash}".encode("utf-8")
    ).hexdigest()[:32]
    return HiddenFinalSummary(
        snapshot_id=snapshot_id,
        snapshot_digest=snapshot_digest_of(
            stage=MaterializationStage.FINAL,
            parser_version=PARSER_VERSION,
            table_ruleset_version=TABLE_RULESET_VERSION,
            tables=tables,
        ),
        raw_state_digest=raw_state_digest_of(tables),
        materialization_stage=MaterializationStage.FINAL,
        parser_version=PARSER_VERSION,
        table_ruleset_version=TABLE_RULESET_VERSION,
        summary_contract_version=SUMMARY_CONTRACT_VERSION,
        scalar_encoding_version=SCALAR_ENCODING_VERSION,
        snapshot_materialization_contract_version=SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION,
        digest_contract_version=DIGEST_CONTRACT_VERSION,
        tables=tables,
    )
