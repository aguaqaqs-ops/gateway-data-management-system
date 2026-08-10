"""Test-only ASGI harness for HTTP shell behavior that must not ship in production."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, field_validator

from gateway_repository_contracts import REPOSITORY_IMPORT_MEDIA_TYPE, OperationStatus
from gateway_repository_service.app import create_app
from gateway_repository_service.auth_state import AuthState
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
from gateway_repository_service.http.auth import require_bearer_token
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.http.readiness import ReadinessPort
from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.mutation_fingerprints import (
    create_repository_fingerprint_v1,
    upload_artifact_fingerprint_v1,
)
from gateway_repository_service.mutation_store import (
    ArtifactLifecycleRecord,
    IdempotencyKeyHash,
    IdempotencyScope,
)
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.provider_lifecycle import OfflineCliCapabilityGate
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.locks import RepositoryLockRegistry
from gateway_repository_service.versioned_import.store import ImportOperationStore
from gateway_repository_service.versioned_read.application import VersionedReadApplication


class ReadyReadiness:
    def is_ready(self) -> bool:
        return True

    def not_ready_message(self) -> str:
        return "service is not ready"


class _ValidationProbeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_field: str


class _CustomValidatorBody(BaseModel):
    value: str

    @field_validator("value")
    @classmethod
    def reject_value(cls, value: str) -> str:
        del cls
        raise ValueError("rejected")


class _NestedInnerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inner_field: str


class _NestedOuterBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nested: _NestedInnerBody


def create_test_client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def create_create_route_test_app(settings: RepositoryServiceSettings) -> FastAPI:
    app = create_app(settings, enable_lifecycle=False)
    app.state.auth_state = AuthState(bearer_token=settings.resolve_bearer_token())
    app.state.readiness = ReadyReadiness()
    return app


def create_test_http_app(
    settings: RepositoryServiceSettings | None = None,
    *,
    readiness: ReadinessPort | None = None,
) -> FastAPI:
    configured = settings or RepositoryServiceSettings(profile="test", bearer_token="test-token")
    app = create_app(configured, readiness=readiness, enable_lifecycle=False)
    app.state.auth_state = AuthState(bearer_token=configured.resolve_bearer_token())

    @app.post("/_test/validate")
    def validation_probe(body: _ValidationProbeBody) -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/_test/auth-required")
    def auth_required_probe(_authorized: Annotated[None, Depends(require_bearer_token)]) -> dict[str, str]:
        return {"status": "authorized"}

    @app.get("/_test/service-error")
    def service_error_probe() -> dict[str, str]:
        raise ServiceError(
            code="TEST_SERVICE_ERROR",
            message="deliberate service error",
            status_code=418,
            details={"probe": True},
        )

    @app.get("/_test/unhandled-error")
    def unhandled_error_probe() -> dict[str, str]:
        raise RuntimeError("probe")

    @app.post("/_test/custom-validator")
    def custom_validator_probe(body: _CustomValidatorBody) -> dict[str, str]:
        return {"status": "ok", "value": body.value}

    @app.post("/_test/nested-validate")
    def nested_validation_probe(body: _NestedOuterBody) -> dict[str, str]:
        return {"status": "ok", "inner": body.nested.inner_field}

    return app


def assert_request_id_header(response: Any) -> str:
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert request_id != ""
    return str(request_id)


PRODUCTION_OPENAPI_PATHS = {
    "/healthz",
    "/readyz",
    "/v1/repositories",
    "/v1/repositories/{repository_id}/artifacts",
    "/v1/repositories/{repository_id}/versioned/imports",
    "/v1/repositories/{repository_id}/operations/{operation_id}",
    "/v1/repositories/{repository_id}/versioned/refs/{ref_name}",
    "/v1/repositories/{repository_id}/versioned/commits/{commit_id}/catalog",
    "/v1/repositories/{repository_id}/versioned/commits/{commit_id}/rows",
}


@dataclass
class ImportHttpTestEnvironment:
    settings: RepositoryServiceSettings
    layout: DurableLayout
    runtime: ServiceRuntime
    client: TestClient
    control_store: ControlStore
    notify_calls: list[int] = field(default_factory=list)
    notify_queued_visible: list[bool] = field(default_factory=list)

    def close(self) -> None:
        if self.control_store.is_open():
            self.control_store.close()

    def seed_repository(self, repository_id: UUID | None = None) -> UUID:
        resolved = repository_id or uuid4()
        scope = IdempotencyScope.for_create()
        effect = self.runtime.mutation_store.allocate_pending(
            scope,
            key_hash=IdempotencyKeyHash.from_raw_key(f"create-{resolved}"),
            fingerprint=create_repository_fingerprint_v1(),
            resource_id=resolved,
        )
        self.runtime.mutation_store.mark_succeeded(
            effect.effect_id,
            response_body={
                "repository_id": str(resolved),
                "default_ref": "main",
                "initial_commit_id": "commit-0",
            },
        )
        published = self.layout.published_repository(repository_key(resolved))
        (published / ".dolt").mkdir(parents=True, exist_ok=True)
        return resolved

    def seed_artifact(
        self,
        repository_id: UUID,
        *,
        artifact_id: UUID | None = None,
        payload: bytes = b"artifact-bytes",
    ) -> tuple[UUID, int, str]:
        resolved = artifact_id or uuid4()
        size_bytes = len(payload)
        raw_sha256 = hashlib.sha256(payload).hexdigest()
        ready_path = artifact_ready_path(self.layout, repository_id, resolved)
        ready_path.parent.mkdir(parents=True, exist_ok=True)
        ready_path.write_bytes(payload)
        scope = IdempotencyScope.for_upload(repository_id)
        effect = self.runtime.mutation_store.allocate_pending(
            scope,
            key_hash=IdempotencyKeyHash.from_raw_key(f"upload-{resolved}"),
            fingerprint=upload_artifact_fingerprint_v1(
                media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
                declared_size=size_bytes,
                raw_sha256_hex=raw_sha256,
            ),
            resource_id=resolved,
        )
        self.runtime.mutation_store.mark_succeeded(
            effect.effect_id,
            response_body={
                "artifact_ref": {
                    "artifact_id": str(resolved),
                    "media_type": REPOSITORY_IMPORT_MEDIA_TYPE,
                    "size_bytes": size_bytes,
                    "raw_sha256": raw_sha256,
                }
            },
            artifact_lifecycle=ArtifactLifecycleRecord(
                artifact_id=resolved,
                repository_id=repository_id,
                media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
                size_bytes=size_bytes,
                raw_sha256=raw_sha256,
            ),
        )
        return resolved, size_bytes, raw_sha256


def create_import_http_environment(tmp_path: Path, **settings_kwargs: object) -> ImportHttpTestEnvironment:
    dolt_stub = tmp_path / "dolt-stub"
    dolt_stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    dolt_stub.chmod(0o755)
    settings = RepositoryServiceSettings(
        profile="test",
        data_root=tmp_path / "data-root",
        bearer_token="test-bearer-token",
        dolt_binary=dolt_stub,
        **settings_kwargs,  # type: ignore[arg-type]
    )
    layout = DurableLayout.create_for_probe(settings.data_root)
    control_store = ControlStore.open(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=1000,
    )
    import_store = ImportOperationStore(
        control_store.connection,
        transaction_lock=control_store.transaction_lock,
    )
    notify_calls: list[int] = []
    notify_queued_visible: list[bool] = []

    def _notify() -> None:
        notify_calls.append(1)
        observer = sqlite3.connect(settings.control_db_path, timeout=5.0)
        try:
            row = observer.execute(
                """
                SELECT COUNT(*) AS queued_count
                FROM repository_import_operations
                WHERE status = ?
                """,
                (OperationStatus.QUEUED.value,),
            ).fetchone()
            notify_queued_visible.append(row is not None and int(row[0]) > 0)
        finally:
            observer.close()

    worker_pool = MagicMock()
    worker_pool.notify.side_effect = _notify
    root_lock = MagicMock()
    root_lock.is_held.return_value = True
    provider_gate = MagicMock(spec=OfflineCliCapabilityGate)
    provider_gate.executable_path.return_value = settings.dolt_binary
    runtime = ServiceRuntime(
        settings=settings,
        layout=layout,
        root_lock=root_lock,
        control_store=control_store,
        mutation_store=import_store.mutation_store,
        import_store=import_store,
        import_locks=RepositoryLockRegistry(),
        import_worker_pool=worker_pool,
        versioned_read_application=MagicMock(spec=VersionedReadApplication),
        dolt_runner=MagicMock(spec=DoltRunner),
        provider_gate=provider_gate,
        auth_state=AuthState(bearer_token=settings.resolve_bearer_token()),
        _stopping=threading.Event(),
    )
    app = create_app(settings, enable_lifecycle=False)
    app.state.auth_state = runtime.auth_state
    app.state.readiness = ReadyReadiness()
    app.state.runtime = runtime
    client = create_test_client(app)
    return ImportHttpTestEnvironment(
        settings=settings,
        layout=layout,
        runtime=runtime,
        client=client,
        control_store=control_store,
        notify_calls=notify_calls,
        notify_queued_visible=notify_queued_visible,
    )


def import_request_body(
    *,
    repository_id: UUID,
    artifact_id: UUID,
    size_bytes: int,
    raw_sha256: str,
    expected_commit_id: str = "commit-0",
) -> dict[str, object]:
    return {
        "repository_id": str(repository_id),
        "artifact_ref": {
            "artifact_id": str(artifact_id),
            "media_type": REPOSITORY_IMPORT_MEDIA_TYPE,
            "size_bytes": size_bytes,
            "raw_sha256": raw_sha256,
        },
        "target_ref": "main",
        "expected_commit_id": expected_commit_id,
    }


def import_headers(
    *,
    token: str = "test-bearer-token",
    idempotency_key: str = "import-key-1",
    request_id: str | None = None,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": idempotency_key,
        "Content-Type": "application/json",
    }
    if request_id is not None:
        headers["X-Request-ID"] = request_id
    return headers
