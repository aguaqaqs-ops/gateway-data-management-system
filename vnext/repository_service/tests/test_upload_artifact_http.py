"""HTTP tests for POST /v1/repositories/{repository_id}/artifacts."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from gateway_repository_contracts import REPOSITORY_IMPORT_MEDIA_TYPE, UploadRequestHeaders
from gateway_repository_service.app import create_app
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_store import (
    ClaimResult,
    EffectRecord,
    EffectStatus,
    MutationStore,
    configure_connection,
)
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.command import UploadArtifactCommand
from support.http_harness import PRODUCTION_OPENAPI_PATHS, ReadyReadiness, assert_request_id_header, create_test_client
from support.lifecycle_harness import lifecycle_settings
from support.upload_harness import chunked_payload, create_repository, upload_headers, upload_sha256

ALLOWED_OPENAPI_PATHS = PRODUCTION_OPENAPI_PATHS


def _route_test_client(settings: RepositoryServiceSettings) -> TestClient:
    from gateway_repository_service.auth_state import AuthState

    app = create_app(settings, enable_lifecycle=False)
    app.state.auth_state = AuthState(bearer_token=settings.resolve_bearer_token())
    app.state.readiness = ReadyReadiness()
    return create_test_client(app)


def _upload(
    client: TestClient,
    repository_id: UUID,
    *,
    payload: bytes = b"artifact-bytes",
    idempotency_key: str = "upload-http-1",
    headers: dict[str, str] | None = None,
    content: str | bytes | Iterable[bytes] | None = None,
) -> Any:
    request_headers = headers or upload_headers(
        idempotency_key=idempotency_key,
        payload=payload,
    )
    body = content if content is not None else payload
    return client.post(
        f"/v1/repositories/{repository_id}/artifacts",
        headers=request_headers,
        content=body,
    )


def _command_with_mocked_pending(
    settings: RepositoryServiceSettings,
    *,
    repository_id: UUID,
    headers: UploadRequestHeaders,
    chunks: list[bytes],
) -> None:
    layout = DurableLayout.create_service(settings.data_root)
    import sqlite3

    connection = sqlite3.connect(":memory:")
    configure_connection(connection)
    command = UploadArtifactCommand(settings=settings, layout=layout, mutation_store=MutationStore(connection))

    async def body() -> AsyncIterator[bytes]:
        for chunk in chunks:
            yield chunk

    with patch(
        "gateway_repository_service.upload_artifact.command.is_repository_visible",
        return_value=True,
    ), patch.object(MutationStore, "claim_or_lookup") as claim_mock, patch.object(
        MutationStore, "allocate_pending"
    ) as pending_mock:
        claim_mock.return_value = ClaimResult(
            idempotency_id=1,
            is_new=True,
            fingerprint=b"fingerprint",
            effect=None,
            terminal_not_published=False,
        )
        pending_mock.return_value = EffectRecord(
            effect_id=1,
            idempotency_id=1,
            resource_id=uuid4(),
            status=EffectStatus.PENDING,
            response_status=None,
            response_body=None,
        )
        with pytest.raises(ServiceError) as exc_info:
            asyncio.run(command.execute(repository_id, headers, body()))
        raise exc_info.value


@pytest.mark.integration
def test_upload_artifact_happy_path(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        repository_id = create_repository(client)
        payload = b"artifact-bytes"
        response = _upload(client, repository_id, payload=payload, idempotency_key="happy-path")

    assert response.status_code == 201
    body = response.json()
    assert body["artifact_ref"]["size_bytes"] == len(payload)
    assert body["artifact_ref"]["raw_sha256"] == upload_sha256(payload)
    assert body["artifact_ref"]["media_type"] == REPOSITORY_IMPORT_MEDIA_TYPE
    UUID(body["artifact_ref"]["artifact_id"])
    assert_request_id_header(response)


@pytest.mark.integration
def test_upload_artifact_accepts_zero_length_body(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    payload = b""
    with TestClient(create_app(settings)) as client:
        repository_id = create_repository(client, idempotency_key="create-zero")
        response = _upload(
            client,
            repository_id,
            payload=payload,
            idempotency_key="upload-zero",
        )

    assert response.status_code == 201
    assert response.json()["artifact_ref"]["size_bytes"] == 0


@pytest.mark.integration
def test_upload_artifact_streams_multi_chunk_body(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    payload = b"a" * 10_000
    with TestClient(create_app(settings)) as client:
        repository_id = create_repository(client, idempotency_key="create-chunked")
        response = client.post(
            f"/v1/repositories/{repository_id}/artifacts",
            headers=upload_headers(idempotency_key="chunked-upload", payload=payload),
            content=chunked_payload(payload, chunk_size=4_096),
        )

    assert response.status_code == 201
    assert response.json()["artifact_ref"]["raw_sha256"] == upload_sha256(payload)


@pytest.mark.integration
def test_upload_artifact_accepts_declared_size_at_limit(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    settings = settings.model_copy(update={"max_upload_bytes": 32})
    payload = b"x" * 32
    with TestClient(create_app(settings)) as client:
        repository_id = create_repository(client, idempotency_key="create-at-limit")
        response = _upload(client, repository_id, payload=payload, idempotency_key="at-limit")

    assert response.status_code == 201
    assert response.json()["artifact_ref"]["size_bytes"] == 32


def test_upload_artifact_rejects_unsupported_media_type(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    client = _route_test_client(settings)
    payload = b"x"
    with patch.object(
        UploadArtifactCommand,
        "execute",
        side_effect=AssertionError("upload command must not run"),
    ):
        response = client.post(
            f"/v1/repositories/{uuid4()}/artifacts",
            headers=upload_headers(
                idempotency_key="bad-media",
                payload=payload,
                content_type="application/gzip",
            ),
            content=payload,
        )

    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_upload_artifact_rejects_tar_gz_media_type(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    client = _route_test_client(settings)
    payload = b"x"
    with patch.object(UploadArtifactCommand, "execute", side_effect=AssertionError("must not run")):
        response = client.post(
            f"/v1/repositories/{uuid4()}/artifacts",
            headers=upload_headers(
                idempotency_key="tar-gz",
                payload=payload,
                content_type="application/vnd.gateway.repository-import.v1+tar+gz",
            ),
            content=payload,
        )
    assert response.status_code == 415


def test_upload_artifact_rejects_multipart_content_type(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    client = _route_test_client(settings)
    with patch.object(UploadArtifactCommand, "execute", side_effect=AssertionError("must not run")):
        response = client.post(
            f"/v1/repositories/{uuid4()}/artifacts",
            headers={
                **upload_headers(idempotency_key="multipart"),
                "Content-Type": "multipart/form-data; boundary=abc",
            },
            content=b"ignored",
        )
    assert response.status_code == 415


@pytest.mark.integration
def test_upload_artifact_rejects_declared_size_above_limit(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    settings = settings.model_copy(update={"max_upload_bytes": 16})
    payload = b"x" * 17
    with TestClient(create_app(settings)) as client:
        repository_id = create_repository(client, idempotency_key="create-too-large")
        with patch.object(MutationStore, "allocate_pending", side_effect=AssertionError("must not run")):
            response = client.post(
                f"/v1/repositories/{repository_id}/artifacts",
                headers=upload_headers(idempotency_key="too-large", payload=payload),
                content=payload,
            )
    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_upload_artifact_rejects_short_body(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    declared = b"12345"
    actual = b"12"
    headers = UploadRequestHeaders(
        content_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        content_length=len(declared),
        idempotency_key="short-body",
        artifact_sha256=upload_sha256(declared),
    )
    with pytest.raises(ServiceError) as exc_info:
        _command_with_mocked_pending(
            settings,
            repository_id=uuid4(),
            headers=headers,
            chunks=[actual],
        )
    assert exc_info.value.code == "UPLOAD_BODY_MISMATCH"


def test_upload_artifact_rejects_long_body(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    declared = b"12345"
    actual = b"123456"
    headers = UploadRequestHeaders(
        content_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        content_length=len(declared),
        idempotency_key="long-body",
        artifact_sha256=upload_sha256(declared),
    )
    with pytest.raises(ServiceError) as exc_info:
        _command_with_mocked_pending(
            settings,
            repository_id=uuid4(),
            headers=headers,
            chunks=[actual],
        )
    assert exc_info.value.code == "UPLOAD_BODY_MISMATCH"


def test_upload_artifact_rejects_sha_mismatch(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    payload = b"payload"
    headers = UploadRequestHeaders(
        content_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        content_length=len(payload),
        idempotency_key="sha-mismatch",
        artifact_sha256="a" * 64,
    )
    with pytest.raises(ServiceError) as exc_info:
        _command_with_mocked_pending(
            settings,
            repository_id=uuid4(),
            headers=headers,
            chunks=[payload],
        )
    assert exc_info.value.code == "UPLOAD_DIGEST_MISMATCH"


@pytest.mark.integration
def test_upload_artifact_returns_404_for_missing_repository(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    payload = b"x"
    with TestClient(create_app(settings)) as client:
        with patch.object(MutationStore, "allocate_pending", side_effect=AssertionError("must not run")):
            response = client.post(
                f"/v1/repositories/{uuid4()}/artifacts",
                headers=upload_headers(idempotency_key="missing-repo", payload=payload),
                content=payload,
            )
    assert response.status_code == 404
    assert response.json()["code"] == "REPOSITORY_NOT_FOUND"


@pytest.mark.integration
def test_upload_artifact_returns_503_when_disk_measurement_unavailable(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    payload = b"x"
    with TestClient(create_app(settings)) as client:
        repository_id = create_repository(client, idempotency_key="create-disk-unavailable")
        with patch(
            "gateway_repository_service.upload_artifact.command.assert_upload_disk_admission",
            side_effect=__import__(
                "gateway_repository_service.capacity",
                fromlist=["CapacityAdmissionError"],
            ).CapacityAdmissionError("durable root disk measurement is unavailable"),
        ), patch.object(MutationStore, "allocate_pending", side_effect=AssertionError("must not run")):
            response = client.post(
                f"/v1/repositories/{repository_id}/artifacts",
                headers=upload_headers(idempotency_key="disk-unavailable", payload=payload),
                content=payload,
            )
    assert response.status_code == 503
    assert response.json()["code"] == "DISK_ADMISSION_DENIED"


def test_upload_artifact_requires_auth(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    client = _route_test_client(settings)
    payload = b"x"
    headers = upload_headers(idempotency_key="no-auth", payload=payload)
    headers.pop("Authorization")
    response = client.post(
        f"/v1/repositories/{uuid4()}/artifacts",
        headers=headers,
        content=payload,
    )
    assert response.status_code == 401


def test_openapi_exposes_upload_route(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    client = _route_test_client(settings)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    body = response.json()
    paths = set(body["paths"].keys())
    assert paths == ALLOWED_OPENAPI_PATHS
    upload = body["paths"]["/v1/repositories/{repository_id}/artifacts"]["post"]
    assert "429" in upload["responses"]
    assert "413" in upload["responses"]
    assert "503" in upload["responses"]
