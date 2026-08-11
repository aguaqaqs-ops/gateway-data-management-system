"""Typed async client for the Gateway Repository Service."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from uuid import UUID

import httpx
from pydantic import TypeAdapter, ValidationError

from gateway_repository_contracts import (
    CommitIdString,
    CreateRepositoryResponse,
    GetOperationResponse,
    GetVersionedCatalogResponse,
    IdempotencyKeyString,
    MainRefLiteral,
    MAX_CATALOG_JSON_BYTES,
    ResolveVersionedRefResponse,
    StreamVersionedTableRowsQuery,
    SubmitVersionedImportRequest,
    SubmitVersionedImportResponse,
    UnknownTypePolicy,
    UploadArtifactResponse,
    VersionedOperation,
    VersionedTableNameString,
)
from gateway_repository_contracts.types import MediaTypeString, Sha256String
from gateway_repository_client.arrow_stream import ArrowIpcByteStream
from gateway_repository_client.deadline import validate_deadline_seconds
from gateway_repository_client.errors import RepositoryClientError, RepositoryProtocolError
from gateway_repository_client.paths import encode_commit_id_path, encode_path_segment
from gateway_repository_client.poll import (
    DEFAULT_POLL_DEADLINE_SECONDS,
    Clock,
    wait_for_operation,
)
from gateway_repository_client.protocol import parse_json_response
from gateway_repository_client.retry import (
    RETRYABLE_STATUS_CODES,
    Sleeper,
    retry_idempotent_request,
)
from gateway_repository_client.upload import (
    NonRewindableBody,
    NonRewindableUploadSourceError,
    RewindableBody,
    UploadBodySource,
    coerce_upload_body_source,
)

_COMMIT_ID_ADAPTER: TypeAdapter[CommitIdString] = TypeAdapter(CommitIdString)
_IDEMPOTENCY_KEY_ADAPTER: TypeAdapter[IdempotencyKeyString] = TypeAdapter(IdempotencyKeyString)
_MEDIA_TYPE_ADAPTER: TypeAdapter[MediaTypeString] = TypeAdapter(MediaTypeString)
_SHA256_ADAPTER: TypeAdapter[Sha256String] = TypeAdapter(Sha256String)
_TABLE_NAME_ADAPTER: TypeAdapter[VersionedTableNameString] = TypeAdapter(VersionedTableNameString)


class RepositoryClient:
    """Async facade for Repository Service V1 mutations and commit-pinned reads."""

    def __init__(
        self,
        *,
        base_url: str,
        bearer_token: str,
        timeout_seconds: float | None = None,
        request_timeout_seconds: float = 30.0,
        stream_idle_timeout_seconds: float = 30.0,
        poll_deadline_seconds: float = DEFAULT_POLL_DEADLINE_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
        sleeper: Sleeper | None = None,
        clock: Clock | None = None,
    ) -> None:
        resolved_request_timeout = (
            timeout_seconds if timeout_seconds is not None else request_timeout_seconds
        )
        self._base_url = base_url.rstrip("/")
        self._bearer_token = bearer_token
        self._request_timeout = httpx.Timeout(resolved_request_timeout)
        self._stream_timeout = httpx.Timeout(
            None,
            connect=resolved_request_timeout,
            read=stream_idle_timeout_seconds,
            write=resolved_request_timeout,
            pool=resolved_request_timeout,
        )
        self._poll_deadline_seconds = poll_deadline_seconds
        self._transport = transport
        self._sleeper = sleeper
        self._clock = clock

    async def create_repository(
        self,
        *,
        idempotency_key: IdempotencyKeyString,
    ) -> CreateRepositoryResponse:
        validated_key = _validate_idempotency_key(idempotency_key)

        async def _send() -> CreateRepositoryResponse:
            async with self._json_client() as client:
                request = client.build_request(
                    "POST",
                    "/v1/repositories",
                    headers={
                        "Authorization": f"Bearer {self._bearer_token}",
                        "Idempotency-Key": validated_key,
                    },
                )
                response = await client.send(request, stream=True)
                return await parse_json_response(
                    response,
                    expected_status=201,
                    model=CreateRepositoryResponse,
                )

        return await retry_idempotent_request(
            _send,
            sleeper=self._sleeper,
            clock=self._clock,
        )

    async def upload_artifact(
        self,
        *,
        repository_id: UUID,
        idempotency_key: IdempotencyKeyString,
        media_type: MediaTypeString,
        raw_sha256: Sha256String,
        body: UploadBodySource | bytes | bytearray | RewindableBody | NonRewindableBody,
    ) -> UploadArtifactResponse:
        validated_key = _validate_idempotency_key(idempotency_key)
        validated_media_type = _validate_media_type(media_type)
        validated_sha256 = _validate_sha256(raw_sha256)
        source = coerce_upload_body_source(body)

        async def _send() -> UploadArtifactResponse:
            async with self._json_client() as client:
                request = client.build_request(
                    "POST",
                    f"/v1/repositories/{repository_id}/artifacts",
                    headers={
                        "Authorization": f"Bearer {self._bearer_token}",
                        "Content-Type": validated_media_type,
                        "Content-Length": str(source.declared_size),
                        "Idempotency-Key": validated_key,
                        "X-Artifact-SHA256": validated_sha256,
                    },
                    content=_async_chunk_stream(source),
                )
                response = await client.send(request, stream=True)
                return await parse_json_response(
                    response,
                    expected_status=201,
                    model=UploadArtifactResponse,
                )

        if source.rewindable:
            return await retry_idempotent_request(
                _send,
                sleeper=self._sleeper,
                clock=self._clock,
            )
        try:
            return await _send()
        except (
            httpx.TransportError,
            httpx.HTTPStatusError,
            RepositoryClientError,
            RepositoryProtocolError,
        ) as exc:
            status_code = _retryable_status_code(exc)
            if status_code is not None:
                raise NonRewindableUploadSourceError(
                    status_code=status_code,
                    message="upload source is not rewindable for retry",
                ) from exc
            raise

    async def submit_versioned_import(
        self,
        *,
        idempotency_key: IdempotencyKeyString,
        request: SubmitVersionedImportRequest,
    ) -> SubmitVersionedImportResponse:
        validated_key = _validate_idempotency_key(idempotency_key)
        repository_id = request.repository_id
        body = request.model_dump(mode="json")
        path = f"/v1/repositories/{repository_id}/versioned/imports"

        async def _send() -> SubmitVersionedImportResponse:
            async with self._json_client() as client:
                request = client.build_request(
                    "POST",
                    path,
                    headers={
                        "Authorization": f"Bearer {self._bearer_token}",
                        "Idempotency-Key": validated_key,
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                response = await client.send(request, stream=True)
                return await parse_json_response(
                    response,
                    expected_status=202,
                    model=SubmitVersionedImportResponse,
                )

        return await retry_idempotent_request(
            _send,
            sleeper=self._sleeper,
            clock=self._clock,
        )

    async def get_operation(
        self,
        *,
        repository_id: UUID,
        operation_id: UUID,
        deadline_at: float | None = None,
    ) -> GetOperationResponse:
        async def _send() -> GetOperationResponse:
            async with self._json_client() as client:
                request = client.build_request(
                    "GET",
                    f"/v1/repositories/{repository_id}/operations/{operation_id}",
                    headers={"Authorization": f"Bearer {self._bearer_token}"},
                )
                response = await client.send(request, stream=True)
                return await parse_json_response(
                    response,
                    expected_status=200,
                    model=GetOperationResponse,
                )

        return await retry_idempotent_request(
            _send,
            sleeper=self._sleeper,
            clock=self._clock,
            deadline_at=deadline_at,
        )

    async def wait_operation(
        self,
        *,
        repository_id: UUID,
        operation_id: UUID,
        deadline_seconds: float | None = None,
    ) -> VersionedOperation:
        resolved_deadline = (
            self._poll_deadline_seconds if deadline_seconds is None else deadline_seconds
        )
        validate_deadline_seconds(resolved_deadline)
        now = self._clock or time.monotonic
        deadline_at = now() + resolved_deadline

        async def _fetch() -> VersionedOperation:
            response = await self.get_operation(
                repository_id=repository_id,
                operation_id=operation_id,
                deadline_at=deadline_at,
            )
            return response.operation

        return await wait_for_operation(
            _fetch,
            deadline_at=deadline_at,
            clock=self._clock,
            sleeper=self._sleeper,
        )

    async def resolve_versioned_ref(
        self,
        *,
        repository_id: UUID,
        ref_name: MainRefLiteral = "main",
    ) -> ResolveVersionedRefResponse:
        encoded_ref = encode_path_segment(ref_name)

        async def _send() -> ResolveVersionedRefResponse:
            async with self._json_client() as client:
                request = client.build_request(
                    "GET",
                    f"/v1/repositories/{repository_id}/versioned/refs/{encoded_ref}",
                    headers={"Authorization": f"Bearer {self._bearer_token}"},
                )
                response = await client.send(request, stream=True)
                return await parse_json_response(
                    response,
                    expected_status=200,
                    model=ResolveVersionedRefResponse,
                )

        return await retry_idempotent_request(
            _send,
            sleeper=self._sleeper,
            clock=self._clock,
        )

    async def get_versioned_catalog(
        self,
        *,
        repository_id: UUID,
        commit_id: CommitIdString,
    ) -> GetVersionedCatalogResponse:
        validated_commit_id = _validate_commit_id(commit_id)
        encoded_commit_id = encode_commit_id_path(validated_commit_id)

        async def _send() -> GetVersionedCatalogResponse:
            async with self._json_client() as client:
                request = client.build_request(
                    "GET",
                    f"/v1/repositories/{repository_id}"
                    f"/versioned/commits/{encoded_commit_id}/catalog",
                    headers={"Authorization": f"Bearer {self._bearer_token}"},
                )
                response = await client.send(request, stream=True)
                return await parse_json_response(
                    response,
                    expected_status=200,
                    model=GetVersionedCatalogResponse,
                    max_body_bytes=MAX_CATALOG_JSON_BYTES,
                )

        return await retry_idempotent_request(
            _send,
            sleeper=self._sleeper,
            clock=self._clock,
        )

    def stream_versioned_table_rows(
        self,
        *,
        repository_id: UUID,
        commit_id: CommitIdString,
        table_name: VersionedTableNameString,
        unknown_type_policy: UnknownTypePolicy = UnknownTypePolicy.REJECT,
    ) -> ArrowIpcByteStream:
        validated_commit_id = _validate_commit_id(commit_id)
        encoded_commit_id = encode_commit_id_path(validated_commit_id)
        query = StreamVersionedTableRowsQuery.model_validate(
            {
                "table_name": _validate_table_name(table_name),
                "unknown_type_policy": unknown_type_policy,
            }
        )
        params = query.model_dump(mode="json")
        path = (
            f"/v1/repositories/{repository_id}"
            f"/versioned/commits/{encoded_commit_id}/rows"
        )

        async def _open_attempt() -> tuple[httpx.AsyncClient, httpx.Response]:
            client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._stream_timeout,
                transport=self._transport,
            )
            try:
                request = client.build_request(
                    "GET",
                    path,
                    headers={"Authorization": f"Bearer {self._bearer_token}"},
                    params=params,
                )
                response = await client.send(request, stream=True)
            except BaseException:
                await client.aclose()
                raise
            return client, response

        return ArrowIpcByteStream(
            open_attempt=_open_attempt,
            sleeper=self._sleeper,
        )

    def _json_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._request_timeout,
            transport=self._transport,
        )


async def _async_chunk_stream(source: UploadBodySource) -> AsyncIterator[bytes]:
    for chunk in source.open_chunks():
        yield chunk


def _validate_commit_id(commit_id: str) -> str:
    try:
        return _COMMIT_ID_ADAPTER.validate_python(commit_id)
    except ValidationError as exc:
        raise ValueError("commit_id is invalid") from exc


def _validate_idempotency_key(idempotency_key: str) -> str:
    try:
        return _IDEMPOTENCY_KEY_ADAPTER.validate_python(idempotency_key)
    except ValidationError as exc:
        raise ValueError("idempotency_key is invalid") from exc


def _validate_media_type(media_type: str) -> str:
    try:
        return _MEDIA_TYPE_ADAPTER.validate_python(media_type)
    except ValidationError as exc:
        raise ValueError("media_type is invalid") from exc


def _validate_sha256(raw_sha256: str) -> str:
    try:
        return _SHA256_ADAPTER.validate_python(raw_sha256)
    except ValidationError as exc:
        raise ValueError("raw_sha256 is invalid") from exc


def _validate_table_name(table_name: str) -> str:
    try:
        return _TABLE_NAME_ADAPTER.validate_python(table_name)
    except ValidationError as exc:
        raise ValueError("table_name is invalid") from exc


def _retryable_status_code(exc: Exception) -> int | None:
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code in RETRYABLE_STATUS_CODES:
            return exc.response.status_code
        return None
    if isinstance(exc, RepositoryClientError):
        if exc.status_code in RETRYABLE_STATUS_CODES:
            return exc.status_code
        return None
    if isinstance(exc, RepositoryProtocolError):
        if exc.status_code in RETRYABLE_STATUS_CODES:
            return exc.status_code
        return None
    if isinstance(exc, httpx.TransportError):
        return 503
    return None
