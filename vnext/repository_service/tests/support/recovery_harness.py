"""Shared helpers for synchronous mutation recovery tests."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from collections.abc import AsyncIterator
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
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.mutation_store import (
    EffectStatus,
    IdempotencyScope,
    MutationStore,
    configure_connection,
)
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.command import UploadArtifactCommand
from support.crash_recovery_worker import CRASH_EXIT_CODE
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

_WORKER = Path(__file__).with_name("crash_recovery_worker.py")


class UploadBody:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self._sent = False

    def __aiter__(self) -> UploadBody:
        return self

    async def __anext__(self) -> bytes:
        if self._sent:
            raise StopAsyncIteration
        self._sent = True
        return self._payload


def start_runtime(tmp_path: Path) -> tuple[RepositoryServiceSettings, ServiceRuntime]:
    settings = lifecycle_settings(tmp_path)
    return settings, ServiceRuntime.start(settings)


def restart_runtime(settings: RepositoryServiceSettings) -> ServiceRuntime:
    return ServiceRuntime.start(settings)


def layout_for_settings(settings: RepositoryServiceSettings) -> DurableLayout:
    return DurableLayout.create_service(settings.data_root)


def _worker_env() -> dict[str, str]:
    env = os.environ.copy()
    tests_root = str(_WORKER.parent.parent)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = tests_root if not existing else f"{tests_root}{os.pathsep}{existing}"
    return env


def _worker_command(*args: str) -> list[str]:
    return [sys.executable, str(_WORKER), *args]


def _run_worker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _worker_command(*args),
        check=False,
        capture_output=True,
        text=True,
        env=_worker_env(),
    )


def setup_create_subprocess(
    settings: RepositoryServiceSettings,
    *,
    idempotency_key: str,
) -> subprocess.CompletedProcess[str]:
    return _run_worker(
        "--data-root",
        str(settings.data_root),
        "--dolt-binary",
        str(settings.dolt_binary),
        "--dolt-version",
        settings.dolt_version,
        "--mode",
        "setup_create",
        "--idempotency-key",
        idempotency_key,
    )


def crash_create_subprocess(
    settings: RepositoryServiceSettings,
    *,
    idempotency_key: str,
    point: CreateFaultPoint,
) -> subprocess.CompletedProcess[str]:
    completed = _run_worker(
        "--data-root",
        str(settings.data_root),
        "--dolt-binary",
        str(settings.dolt_binary),
        "--dolt-version",
        settings.dolt_version,
        "--mode",
        "crash_create",
        "--idempotency-key",
        idempotency_key,
        "--fault-point",
        point,
    )
    assert completed.returncode == CRASH_EXIT_CODE, completed.stderr
    return completed


def crash_upload_subprocess(
    settings: RepositoryServiceSettings,
    *,
    repository_id: UUID,
    idempotency_key: str,
    payload: bytes,
    point: UploadFaultPoint,
) -> subprocess.CompletedProcess[str]:
    completed = _run_worker(
        "--data-root",
        str(settings.data_root),
        "--dolt-binary",
        str(settings.dolt_binary),
        "--dolt-version",
        settings.dolt_version,
        "--mode",
        "crash_upload",
        "--idempotency-key",
        idempotency_key,
        "--fault-point",
        point,
        "--repository-id",
        str(repository_id),
        "--payload-hex",
        payload.hex(),
    )
    assert completed.returncode == CRASH_EXIT_CODE, completed.stderr
    return completed


def setup_repository_for_upload(
    settings: RepositoryServiceSettings,
    *,
    idempotency_key: str = "recovery-create",
) -> UUID:
    completed = setup_create_subprocess(settings, idempotency_key=idempotency_key)
    assert completed.returncode == 0, completed.stderr
    return get_create_resource_id(settings, idempotency_key)


def open_mutation_store(settings: RepositoryServiceSettings) -> MutationStore:
    connection = sqlite3.connect(settings.control_db_path)
    configure_connection(connection)
    return MutationStore(connection)


def count_effects(store: MutationStore) -> int:
    row = store._connection.execute("SELECT COUNT(*) FROM synchronous_mutation_effects").fetchone()
    assert row is not None
    return int(row[0])


def get_create_resource_id(settings: RepositoryServiceSettings, idempotency_key: str) -> UUID:
    store = open_mutation_store(settings)
    try:
        key_hash = MutationStore.hash_idempotency_key(idempotency_key)
        row = store._connection.execute(
            """
            SELECT e.resource_id
            FROM synchronous_mutation_effects AS e
            JOIN mutation_idempotency AS i ON i.id = e.idempotency_id
            WHERE i.mutation_kind = 'create_repository'
              AND i.repository_scope = ''
              AND i.key_hash = ?
            """,
            (key_hash.digest,),
        ).fetchone()
        assert row is not None
        return UUID(str(row["resource_id"]))
    finally:
        store._connection.close()


def get_upload_resource_id(
    settings: RepositoryServiceSettings,
    repository_id: UUID,
    idempotency_key: str,
) -> UUID:
    store = open_mutation_store(settings)
    try:
        scope = IdempotencyScope.for_upload(repository_id)
        key_hash = MutationStore.hash_idempotency_key(idempotency_key)
        row = store._connection.execute(
            """
            SELECT e.resource_id
            FROM synchronous_mutation_effects AS e
            JOIN mutation_idempotency AS i ON i.id = e.idempotency_id
            WHERE i.mutation_kind = 'upload_artifact'
              AND i.repository_scope = ?
              AND i.key_hash = ?
            """,
            (scope.repository_scope(), key_hash.digest),
        ).fetchone()
        assert row is not None
        return UUID(str(row["resource_id"]))
    finally:
        store._connection.close()


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


def upload_request_headers(*, idempotency_key: str, payload: bytes) -> UploadRequestHeaders:
    return UploadRequestHeaders(
        content_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        content_length=len(payload),
        idempotency_key=idempotency_key,
        artifact_sha256=upload_sha256(payload),
    )


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
    response = command.execute(idempotency_key)
    runtime.register_succeeded_create(UUID(str(response.repository_id)))
    return response


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
        upload_admission=runtime.upload_admission,
    )
    body = cast(AsyncIterator[bytes], UploadBody(payload))
    response = await command.execute(repository_id, headers, body)
    artifact_ref = response.artifact_ref
    runtime.register_succeeded_upload(
        repository_id,
        UUID(str(artifact_ref.artifact_id)),
        artifact_ref.size_bytes,
    )
    return response


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


def staging_dirs_for_key(layout: DurableLayout, repository_id: UUID) -> list[Path]:
    key = repository_key(repository_id)
    return list(layout.staging_versioned.glob(f"{key}.*"))


def upload_staging_files(layout: DurableLayout, repository_id: UUID, artifact_id: UUID) -> list[Path]:
    key = repository_key(repository_id)
    staging_dir, _ready = layout.repository_artifact_directories(key)
    return list(staging_dir.glob(f"{artifact_id.hex}.*"))


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
    from gateway_repository_service.http.readiness import LifecycleReadiness

    app = create_app(runtime.settings, enable_lifecycle=False)
    app.state.runtime = runtime
    app.state.auth_state = runtime.auth_state
    app.state.readiness = LifecycleReadiness(runtime)
    return TestClient(app)


def assert_create_crash_disk_evidence(
    settings: RepositoryServiceSettings,
    *,
    repository_id: UUID,
    idempotency_key: str,
    point: CreateFaultPoint,
) -> None:
    layout = layout_for_settings(settings)
    published = layout.published_repository(repository_key(repository_id))
    staging = staging_dirs_for_key(layout, repository_id)
    if point == "after_pending":
        assert staging == []
        assert not published.exists()
    elif point == "after_staging":
        assert staging
        assert not (staging[0] / ".dolt").exists()
        assert not published.exists()
    elif point == "after_dolt_init":
        assert staging
        assert (staging[0] / ".dolt").is_dir()
        assert not published.exists()
    elif point == "before_rename":
        assert staging
        assert (staging[0] / ".dolt").is_dir()
        assert not published.exists()
    elif point == "after_rename":
        assert published.is_dir()
        assert (published / ".dolt").is_dir()
    elif point == "after_succeeded":
        assert published.is_dir()
        store = open_mutation_store(settings)
        try:
            assert (
                effect_status(
                    store,
                    scope=IdempotencyScope.for_create(),
                    idempotency_key=idempotency_key,
                )
                == EffectStatus.SUCCEEDED
            )
        finally:
            store._connection.close()


def assert_upload_crash_disk_evidence(
    settings: RepositoryServiceSettings,
    *,
    repository_id: UUID,
    artifact_id: UUID,
    payload: bytes,
    point: UploadFaultPoint,
) -> None:
    layout = layout_for_settings(settings)
    from gateway_repository_service.upload_artifact.visibility import artifact_ready_path

    ready_path = artifact_ready_path(layout, repository_id, artifact_id)
    staging_files = upload_staging_files(layout, repository_id, artifact_id)
    if point == "after_pending":
        assert staging_files == []
        assert not ready_path.exists()
    elif point == "after_partial_body":
        assert staging_files
        assert staging_files[0].stat().st_size < len(payload)
        assert not ready_path.exists()
    elif point == "after_complete_close":
        assert staging_files
        assert staging_files[0].stat().st_size == len(payload)
        assert not ready_path.exists()
    elif point == "before_rename":
        assert staging_files
        assert staging_files[0].stat().st_size == len(payload)
        assert not ready_path.exists()
    elif point in {"after_rename", "after_succeeded"}:
        assert ready_path.is_file()
        assert ready_path.stat().st_size == len(payload)
