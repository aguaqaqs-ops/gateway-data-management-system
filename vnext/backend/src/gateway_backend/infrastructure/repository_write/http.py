"""Sync HTTP adapter for Repository upload, import, and operation polling."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import cast
from uuid import UUID

import httpx
from gateway_repository_client import RepositoryClient
from gateway_repository_client.errors import RepositoryClientTimeoutError

from gateway_backend.application.submission.errors import (
    RepositoryUploadMetadataMismatch,
    RepositoryWriteTimeoutError,
    RepositoryWriteTransportError,
)
from gateway_repository_contracts import (
    GetOperationResponse,
    IdempotencyKeyString,
    SubmitVersionedImportRequest,
    SubmitVersionedImportResponse,
    UploadArtifactResponse,
    VersionedOperation,
)
from gateway_repository_contracts.types import MediaTypeString, Sha256String

from gateway_backend.application.submission.ports import RepositoryWritePort
from gateway_backend.domain.submission.models import RepositoryArtifactRef
from gateway_backend.infrastructure.repository_write import wire_codec


@dataclass(frozen=True, slots=True)
class HttpRepositoryWriteClient:
    base_url: str
    bearer_token: str
    timeout_seconds: float = 30.0
    poll_deadline_seconds: float = 60.0
    transport: httpx.AsyncBaseTransport | None = None

    def upload_artifact(
        self,
        *,
        repository_id: str,
        idempotency_key: str,
        media_type: str,
        raw_sha256: str,
        body: bytes,
    ) -> RepositoryArtifactRef:
        response = cast(
            UploadArtifactResponse,
            _run(
            self._client().upload_artifact(
                repository_id=_as_uuid(repository_id),
                idempotency_key=_as_idempotency_key(idempotency_key),
                media_type=_as_media_type(media_type),
                raw_sha256=_wire_sha256(raw_sha256),
                body=body,
            )
            ),
        )
        artifact_ref = _artifact_ref_from_response(response)
        expected_size = len(body)
        expected_sha = _normalize_request_sha256(raw_sha256)
        actual_sha = _normalize_request_sha256(artifact_ref.raw_sha256)
        if artifact_ref.media_type != media_type:
            raise RepositoryUploadMetadataMismatch(
                "upload response media_type does not match request"
            )
        if artifact_ref.size_bytes != expected_size:
            raise RepositoryUploadMetadataMismatch(
                "upload response size_bytes does not match request body"
            )
        if actual_sha != expected_sha:
            raise RepositoryUploadMetadataMismatch(
                "upload response raw_sha256 does not match request"
            )
        return artifact_ref

    def submit_versioned_import(
        self,
        *,
        repository_id: str,
        idempotency_key: str,
        artifact_ref: RepositoryArtifactRef,
        expected_commit_id: str,
    ) -> str:
        repo_uuid = _as_uuid(repository_id)
        request = SubmitVersionedImportRequest.model_validate(
            json.loads(
                wire_codec.build_import_request_bytes(
                    repository_id=repository_id,
                    repository_artifact_ref=artifact_ref,
                    expected_commit_id=expected_commit_id,
                )
            )
        )
        if str(request.repository_id) != str(repo_uuid):
            raise ValueError("import request repository_id must match path repository_id")
        response = cast(
            SubmitVersionedImportResponse,
            _run(
                self._client().submit_versioned_import(
                    idempotency_key=_as_idempotency_key(idempotency_key),
                    request=request,
                )
            ),
        )
        return str(response.operation_id)

    def canonical_import_request_bytes(
        self,
        *,
        repository_id: str,
        artifact_ref: RepositoryArtifactRef,
        expected_commit_id: str,
    ) -> bytes:
        return wire_codec.build_import_request_bytes(
            repository_id=repository_id,
            repository_artifact_ref=artifact_ref,
            expected_commit_id=expected_commit_id,
        )

    def get_operation(
        self,
        *,
        repository_id: str,
        operation_id: str,
    ) -> VersionedOperation:
        response = cast(
            GetOperationResponse,
            _run(
                self._client().get_operation(
                    repository_id=_as_uuid(repository_id),
                    operation_id=_as_uuid(operation_id),
                )
            ),
        )
        return response.operation

    def wait_operation(
        self,
        *,
        repository_id: str,
        operation_id: str,
        deadline_seconds: float | None = None,
    ) -> VersionedOperation:
        try:
            return cast(
                VersionedOperation,
                _run(
                    self._client().wait_operation(
                        repository_id=_as_uuid(repository_id),
                        operation_id=_as_uuid(operation_id),
                        deadline_seconds=deadline_seconds,
                    )
                ),
            )
        except RepositoryClientTimeoutError as exc:
            raise RepositoryWriteTimeoutError(str(exc)) from exc

    def _client(self) -> RepositoryClient:
        return RepositoryClient(
            base_url=self.base_url,
            bearer_token=self.bearer_token,
            timeout_seconds=self.timeout_seconds,
            poll_deadline_seconds=self.poll_deadline_seconds,
            transport=self.transport,
        )


def _run(coro: object) -> object:
    try:
        return asyncio.run(coro)  # type: ignore[arg-type]
    except httpx.TransportError as exc:
        raise RepositoryWriteTransportError(str(exc)) from exc


def _as_uuid(value: str) -> UUID:
    return UUID(value)


def _as_idempotency_key(value: str) -> IdempotencyKeyString:
    return IdempotencyKeyString(value)


def _as_media_type(value: str) -> MediaTypeString:
    return MediaTypeString(value)


def _as_sha256(value: str) -> Sha256String:
    return Sha256String(value)


def _wire_sha256(value: str) -> Sha256String:
    return _as_sha256(value.removeprefix("sha256:"))


def _normalize_request_sha256(value: str) -> str:
    return value.removeprefix("sha256:")


def _artifact_ref_from_response(response: UploadArtifactResponse) -> RepositoryArtifactRef:
    return wire_codec.repository_artifact_ref_from_upload_response(response)


__all__ = ["HttpRepositoryWriteClient", "RepositoryWritePort"]
