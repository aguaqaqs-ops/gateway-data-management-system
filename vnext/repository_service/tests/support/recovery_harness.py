"""Shared helpers for synchronous mutation recovery tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from gateway_repository_contracts import (
    CreateRepositoryResponse,
    REPOSITORY_IMPORT_MEDIA_TYPE,
    UploadArtifactResponse,
    UploadRequestHeaders,
)
from gateway_repository_service.create_repository.command import CreateRepositoryCommand
from gateway_repository_service.create_repository.ports import NoOpCreateRepositoryFaultInjector
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.mutation_fingerprints import (
    create_repository_fingerprint_v1,
    upload_artifact_fingerprint_v1,
)
from gateway_repository_service.mutation_store import (
    EffectStatus,
    IdempotencyScope,
    MutationStore,
)
from gateway_repository_service.publication import FaultPoint
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.command import UploadArtifactCommand
from gateway_repository_service.upload_artifact.ports import NoOpUploadArtifactFaultInjector
from support.lifecycle_harness import lifecycle_settings
from support.upload_harness import upload_sha256

CreateFaultPoint = Literal[
    "after_pending",
    "after_staging",
    "after_dolt_init",
    "before_rename",
    "after_rename",
    "after_succeeded",
]
UploadFaultPoint = Literal[
    "after_pending",
    "after_partial_body",
    "after_complete_close",
    "before_rename",
    "after_rename",
    "after_succeeded",
]


class CreateFaultInjector(NoOpCreateRepositoryFaultInjector):
    def __init__(self, point: CreateFaultPoint) -> None:
        self._point = point

    def after_pending(self) -> None:
        if self._point == "after_pending":
            raise RuntimeError("fault injected after pending")

    def after_staging(self) -> None:
        if self._point == "after_staging":
            raise RuntimeError("fault injected after staging")

    def after_dolt_init(self) -> None:
        if self._point == "after_dolt_init":
            raise RuntimeError("fault injected after dolt init")

    def publication_fault(self) -> FaultPoint:
        if self._point == "before_rename":
            return FaultPoint.BEFORE_RENAME
        if self._point == "after_rename":
            return FaultPoint.AFTER_RENAME
        return FaultPoint.NONE

    def after_succeeded_before_response(self) -> None:
        if self._point == "after_succeeded":
            raise RuntimeError("fault injected after succeeded")


class UploadFaultInjector(NoOpUploadArtifactFaultInjector):
    def __init__(self, point: UploadFaultPoint) -> None:
        self._point = point

    def after_pending(self) -> None:
        if self._point == "after_pending":
            raise RuntimeError("fault injected after pending")

    def after_partial_body(self) -> None:
        if self._point == "after_partial_body":
            raise RuntimeError("fault injected after partial body")

    def after_complete_close(self) -> None:
        if self._point == "after_complete_close":
            raise RuntimeError("fault injected after complete close")

    def publication_fault(self) -> FaultPoint:
        if self._point == "before_rename":
            return FaultPoint.BEFORE_RENAME
        if self._point == "after_rename":
            return FaultPoint.AFTER_RENAME
        return FaultPoint.NONE

    def after_succeeded_before_response(self) -> None:
        if self._point == "after_succeeded":
            raise RuntimeError("fault injected after succeeded")


@dataclass
class UploadBody:
    payload: bytes
    _sent: bool = False

    def __aiter__(self) -> UploadBody:
        return self

    async def __anext__(self) -> bytes:
        if self._sent:
            raise StopAsyncIteration
        self._sent = True
        return self.payload


def start_runtime(tmp_path: Path) -> tuple[RepositoryServiceSettings, ServiceRuntime]:
    settings = lifecycle_settings(tmp_path)
    return settings, ServiceRuntime.start(settings)


def restart_runtime(settings: RepositoryServiceSettings) -> ServiceRuntime:
    return ServiceRuntime.start(settings)


def count_effects(store: MutationStore) -> int:
    row = store._connection.execute("SELECT COUNT(*) FROM synchronous_mutation_effects").fetchone()
    assert row is not None
    return int(row[0])


def is_terminal_not_published(
    store: MutationStore,
    *,
    scope: IdempotencyScope,
    idempotency_key: str,
) -> bool:
    key_hash = MutationStore.hash_idempotency_key(idempotency_key)
    row = store._connection.execute(
        """
        SELECT terminal_not_published
        FROM mutation_idempotency
        WHERE mutation_kind = ? AND repository_scope = ? AND key_hash = ?
        """,
        (scope.mutation_kind.value, scope.repository_scope(), key_hash.digest),
    ).fetchone()
    if row is None:
        return False
    return bool(row["terminal_not_published"])


def effect_status(
    store: MutationStore,
    *,
    scope: IdempotencyScope,
    idempotency_key: str,
) -> EffectStatus | None:
    key_hash = MutationStore.hash_idempotency_key(idempotency_key)
    row = store._connection.execute(
        """
        SELECT e.status
        FROM synchronous_mutation_effects AS e
        JOIN mutation_idempotency AS i ON i.id = e.idempotency_id
        WHERE i.mutation_kind = ? AND i.repository_scope = ? AND i.key_hash = ?
        """,
        (scope.mutation_kind.value, scope.repository_scope(), key_hash.digest),
    ).fetchone()
    if row is None:
        return None
    return EffectStatus(str(row["status"]))


def run_create_until_fault(
    runtime: ServiceRuntime,
    *,
    idempotency_key: str,
    point: CreateFaultPoint,
) -> None:
    command = CreateRepositoryCommand(
        settings=runtime.settings,
        layout=runtime.layout,
        mutation_store=runtime.mutation_store,
        fault_injector=CreateFaultInjector(point),
    )
    with pytest.raises(RuntimeError):
        command.execute(idempotency_key)


def upload_request_headers(*, idempotency_key: str, payload: bytes) -> UploadRequestHeaders:
    return UploadRequestHeaders(
        content_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        content_length=len(payload),
        idempotency_key=idempotency_key,
        artifact_sha256=upload_sha256(payload),
    )


async def run_upload_until_fault(
    runtime: ServiceRuntime,
    *,
    repository_id: UUID,
    idempotency_key: str,
    payload: bytes,
    point: UploadFaultPoint,
) -> None:
    headers = upload_request_headers(idempotency_key=idempotency_key, payload=payload)
    command = UploadArtifactCommand(
        settings=runtime.settings,
        layout=runtime.layout,
        mutation_store=runtime.mutation_store,
        fault_injector=UploadFaultInjector(point),
    )
    with pytest.raises(RuntimeError):
        body = cast(AsyncIterator[bytes], UploadBody(payload))
        await command.execute(repository_id, headers, body)


def replay_create(
    runtime: ServiceRuntime,
    *,
    idempotency_key: str,
) -> CreateRepositoryResponse:
    command = CreateRepositoryCommand(
        settings=runtime.settings,
        layout=runtime.layout,
        mutation_store=runtime.mutation_store,
    )
    return command.execute(idempotency_key)


async def replay_upload(
    runtime: ServiceRuntime,
    *,
    repository_id: UUID,
    idempotency_key: str,
    payload: bytes,
) -> UploadArtifactResponse:
    headers = upload_request_headers(idempotency_key=idempotency_key, payload=payload)
    command = UploadArtifactCommand(
        settings=runtime.settings,
        layout=runtime.layout,
        mutation_store=runtime.mutation_store,
    )
    body = cast(AsyncIterator[bytes], UploadBody(payload))
    return await command.execute(repository_id, headers, body)


def assert_create_replay_conflict(runtime: ServiceRuntime, *, idempotency_key: str) -> None:
    with pytest.raises(ServiceError) as exc_info:
        replay_create(runtime, idempotency_key=idempotency_key)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "IDEMPOTENCY_CONFLICT"


async def assert_upload_replay_conflict(
    runtime: ServiceRuntime,
    *,
    repository_id: UUID,
    idempotency_key: str,
    payload: bytes,
) -> None:
    with pytest.raises(ServiceError) as exc_info:
        await replay_upload(
            runtime,
            repository_id=repository_id,
            idempotency_key=idempotency_key,
            payload=payload,
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "IDEMPOTENCY_CONFLICT"


def create_repository_for_upload(runtime: ServiceRuntime, *, idempotency_key: str = "recovery-create") -> UUID:
    response = replay_create(runtime, idempotency_key=idempotency_key)
    return UUID(str(response.repository_id))


def staging_dirs_for_key(layout: DurableLayout, repository_id: UUID) -> list[Path]:
    key = repository_key(repository_id)
    return list(layout.staging_versioned.glob(f"{key}.*"))


def upload_staging_files(layout: DurableLayout, repository_id: UUID, artifact_id: UUID) -> list[Path]:
    key = repository_key(repository_id)
    staging_dir, _ready = layout.repository_artifact_directories(key)
    return list(staging_dir.glob(f"{artifact_id.hex}.*"))


def upload_fingerprint(payload: bytes) -> bytes:
    return upload_artifact_fingerprint_v1(
        media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        declared_size=len(payload),
        raw_sha256_hex=upload_sha256(payload),
    )


def create_fingerprint() -> bytes:
    return create_repository_fingerprint_v1()


def assert_no_sensitive_leaks(
    text: str, *, idempotency_key: str, token: str, data_root: str, payload: str
) -> None:
    assert idempotency_key not in text
    assert token not in text
    assert data_root not in text
    if payload:
        assert payload not in text


def ready_client(runtime: ServiceRuntime) -> TestClient:
    from gateway_repository_service.app import create_app

    app = create_app(runtime.settings, enable_lifecycle=False)
    app.state.runtime = runtime
    app.state.auth_state = runtime.auth_state
    from gateway_repository_service.http.readiness import LifecycleReadiness

    app.state.readiness = LifecycleReadiness(runtime)
    return TestClient(app)
