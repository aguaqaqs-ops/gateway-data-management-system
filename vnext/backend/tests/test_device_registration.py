"""Registration's fixed scope, original key, short transactions and drain boundary."""
from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import cast
from unittest.mock import patch
from uuid import uuid4
from fastapi import FastAPI

import pytest

from gateway_backend.application.provisioning.contracts import (
    CreatedRepository, Registration, RegistrationConflict, RepositoryIdentity,
)
from gateway_backend.application.provisioning.registration import DeviceRegistration
from gateway_backend.device_identity import device_create_key, device_initial_node_id
from gateway_backend.http.dependencies import ClosableAdmissionGate
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, initialize_control_db
from gateway_backend.infrastructure.control_db.sqlite_mapping import seed_provisioned_mappings
from gateway_backend.infrastructure.control_db.sqlite_registration import SQLiteRegistrationStore
from tests.support.http_workspace_harness import create_workspace_http_environment, TEST_INTERNAL_BEARER

pytestmark = pytest.mark.unit
ENV, GROUP, DIGEST = "test-env", "group-a", "sha256:" + "a" * 64
AUTH = {"Authorization": "Bearer " + TEST_INTERNAL_BEARER}
BODY = {"environment_id": ENV, "group_id": GROUP, "gateway_device_external_key": "new-device", "business_project_id": "project"}


class Repository:
    def __init__(self, database: Path) -> None:
        self.database = database
        self.keys: list[str] = []
        self.identity = RepositoryIdentity(ENV, GROUP, DIGEST)
        self.created = CreatedRepository(str(uuid4()), "a" * 32)
        self.lose_response = False
        self.barrier: asyncio.Event | None = None

    async def get_deployment_identity(self) -> RepositoryIdentity:
        return self.identity

    async def create_repository(self, *, idempotency_key: str) -> CreatedRepository:
        # A second writer can enter here: the registration read transaction has ended.
        with ControlDbUnitOfWork(self.database):
            pass
        self.keys.append(idempotency_key)
        if self.barrier is not None:
            await self.barrier.wait()
        if self.lose_response:
            self.lose_response = False
            raise OSError("response lost")
        return self.created


def application(database: Path) -> tuple[DeviceRegistration, Repository]:
    repository = Repository(database)
    app = DeviceRegistration(store=SQLiteRegistrationStore(database, ENV, GROUP), environment=ENV,
        group=GROUP, storage_digest=DIGEST, reservation=lambda device: None, repository=repository)
    return app, repository


async def register(app: DeviceRegistration, *, device: str = "new-device", project: str = "project") -> Registration:
    return await app.register(environment=ENV, group=GROUP, device=device, project=project)


@pytest.mark.asyncio
async def test_registration_replay_keeps_initial_and_head_and_uses_one_key(tmp_path: Path) -> None:
    database = tmp_path / "control.db"
    initialize_control_db(database)
    app, repository = application(database)
    first = await register(app)
    assert first.initial_node_id == device_initial_node_id(ENV, GROUP, "new-device")
    assert repository.keys == [device_create_key(ENV, GROUP, "new-device")]
    from tests.support.baseline_fixtures import apply_baseline_head_state
    from tests.support.workspace_fixtures import make_baseline_head
    apply_baseline_head_state(database, repository_id=first.repository_id, device_key="new-device", project_id="project",
        baseline_head=make_baseline_head(version=7, commit_id="advanced-commit"))
    assert await register(app) == first
    assert app.query("new-device") == first
    assert len(repository.keys) == 1
    with ControlDbUnitOfWork(database, read_only=True) as uow:
        assert uow.connection.execute("SELECT optimistic_version FROM baseline_head_records").fetchone()[0] == 7
    with pytest.raises(RegistrationConflict):
        await register(app, project="other-project")
    with ControlDbUnitOfWork(database) as uow:
        uow.connection.execute("UPDATE provisioned_scope_mappings SET enabled = 0")
    with pytest.raises(RegistrationConflict):
        await register(app)
    assert len(repository.keys) == 1


@pytest.mark.asyncio
async def test_response_loss_and_db_failure_replay_original_repository(tmp_path: Path) -> None:
    database = tmp_path / "control.db"
    initialize_control_db(database)
    app, repository = application(database)
    repository.lose_response = True
    from gateway_backend.application.provisioning.contracts import RegistrationDependencyUnavailable
    with pytest.raises(RegistrationDependencyUnavailable):
        await register(app)
    from gateway_backend.infrastructure.control_db.sqlite_mapping import _apply_seed_record
    def fail_before_commit(connection: sqlite3.Connection, record: dict[str, object], *, seed_now: datetime) -> None:
        _apply_seed_record(connection, record, seed_now=seed_now)
        raise OSError("commit unavailable")
    with patch("gateway_backend.infrastructure.control_db.sqlite_registration._apply_seed_record", side_effect=fail_before_commit):
        with pytest.raises(OSError):
            await register(app)
    assert app.query("new-device") is None
    result = await register(app)
    assert result.repository_id == repository.created.repository_id
    assert repository.keys == [device_create_key(ENV, GROUP, "new-device")] * 3


@pytest.mark.parametrize("same_project", [True, False])
@pytest.mark.asyncio
async def test_concurrent_device_registration_has_one_fixed_scope(tmp_path: Path, same_project: bool) -> None:
    database = tmp_path / "control.db"
    initialize_control_db(database)
    app, repository = application(database)
    repository.barrier = asyncio.Event()
    first = asyncio.create_task(register(app))
    second = asyncio.create_task(register(app, project="project" if same_project else "other"))
    await asyncio.sleep(0)
    assert len(repository.keys) == 2
    repository.barrier.set()
    results = await asyncio.gather(first, second, return_exceptions=True)
    if same_project:
        assert results[0] == results[1]
    else:
        assert sum(isinstance(result, RegistrationConflict) for result in results) == 1
    assert len(set(repository.keys)) == 1
    with ControlDbUnitOfWork(database, read_only=True) as uow:
        for table in ("provisioned_scope_mappings", "baseline_node_records", "baseline_head_records"):
            assert uow.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_wrong_rs_identity_and_reservation_fail_before_create(tmp_path: Path) -> None:
    database = tmp_path / "control.db"
    initialize_control_db(database)
    app, repository = application(database)
    repository.identity = RepositoryIdentity(ENV, "other", DIGEST)
    from gateway_backend.application.provisioning.contracts import RegistrationDependencyUnavailable
    with pytest.raises(RegistrationDependencyUnavailable):
        await register(app)
    repository.identity = RepositoryIdentity(ENV, GROUP, DIGEST)
    def reject(_device: str) -> None:
        raise ValueError("bad directory")
    app.reservation = reject
    with pytest.raises(RegistrationConflict):
        await register(app)
    assert not repository.keys


def test_internal_routes_and_empty_seed_preserve_online_records(tmp_path: Path) -> None:
    env = create_workspace_http_environment(tmp_path, admission_gate=ClosableAdmissionGate())
    app, repository = application(env.db_path)
    cast(FastAPI, env.client.app).state.device_registration = app
    path = "/internal/v1/devices/register"
    assert env.client.post(path, json=BODY).status_code == 401
    first = env.client.post(path, json=BODY, headers=AUTH)
    assert first.status_code == 200
    assert env.client.post(path, json=BODY, headers=AUTH).json() == first.json()
    query = "/internal/v1/devices/registration"
    assert env.client.get(query, params={"device": "new-device"}, headers=AUTH).json() == first.json()
    assert env.client.get(query + "?device=a&device=b", headers=AUTH).status_code == 422
    assert env.client.get(query + "?device=new-device&extra=x", headers=AUTH).status_code == 422
    assert env.client.get(query, params={"device": "absent"}, headers=AUTH).status_code == 404
    empty = tmp_path / "empty.json"
    empty.write_text('{"mappings":[]}')
    seed_provisioned_mappings(env.db_path, empty)
    assert app.query("new-device") is not None
    gate = cast(ClosableAdmissionGate, cast(FastAPI, env.client.app).state.admission_gate)
    gate.close()
    assert env.client.post(path, json=BODY, headers=AUTH).status_code == 503
    assert len(repository.keys) == 1


@pytest.mark.parametrize("field,value", [
    ("gateway_device_external_key", "\uffff"), ("business_project_id", "\U0010ffff"),
    ("gateway_device_external_key", "a" * 256), ("business_project_id", "\x00"),
])
def test_registration_http_identity_validation_precedes_effect(tmp_path: Path, field: str, value: str) -> None:
    env = create_workspace_http_environment(tmp_path, admission_gate=ClosableAdmissionGate())
    app, repository = application(env.db_path)
    cast(FastAPI, env.client.app).state.device_registration = app
    assert env.client.post("/internal/v1/devices/register", json={**BODY, field: value}, headers=AUTH).status_code == 422
    assert not repository.keys


def test_registration_body_is_bounded_and_rejects_duplicate_keys(tmp_path: Path) -> None:
    env = create_workspace_http_environment(tmp_path, admission_gate=ClosableAdmissionGate())
    path = "/internal/v1/devices/register"
    assert env.client.post(path, content=b" " * 8193, headers=AUTH).status_code == 413
    raw = json.dumps(BODY)[:-1] + ',"group_id":"other"}'
    assert env.client.post(path, content=raw, headers={**AUTH, "Content-Type": "application/json"}).status_code == 422


@pytest.mark.serial
def test_admitted_registration_remains_visible_to_drain_until_complete(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    entered, release = Event(), Event()
    env = create_workspace_http_environment(tmp_path, admission_gate=ClosableAdmissionGate())
    app, repository = application(env.db_path)
    class BlockingRepository(Repository):
        async def create_repository(self, *, idempotency_key: str) -> CreatedRepository:
            entered.set()
            assert await asyncio.to_thread(release.wait, 10)
            return await super().create_repository(idempotency_key=idempotency_key)
    app.repository = BlockingRepository(env.db_path)
    cast(FastAPI, env.client.app).state.device_registration = app
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(env.client.post, "/internal/v1/devices/register", json=BODY, headers=AUTH)
        try:
            assert entered.wait(timeout=10)
            snapshot = env.client.post("/internal/v1/maintenance/drain", headers=AUTH)
            assert snapshot.json() == {"accepting_new_work": False, "in_flight": 1}
            assert env.client.post("/internal/v1/devices/register", json=BODY, headers=AUTH).status_code == 503
        finally:
            release.set()
        assert pending.result(timeout=10).status_code == 200
    assert env.client.get("/internal/v1/maintenance/drain", headers=AUTH).json()["in_flight"] == 0
    assert not repository.keys


def test_empty_group_bootstrap_keeps_ordinary_bearer_unauthorized(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    from gateway_backend.app import create_app
    from tests.support.runtime_settings import make_backend_settings, prepare_backend_runtime_paths
    prepare_backend_runtime_paths(tmp_path)
    settings = make_backend_settings(tmp_path)
    settings.provisioned_mapping_file.write_text('{"mappings":[]}')
    settings.session_file.write_text('{"sessions":[]}')
    with patch("gateway_backend.bootstrap.composition.assert_repository_service_ready"):
        with TestClient(create_app(settings)) as client:
            assert client.get("/readyz").status_code == 200
            assert client.get("/v1/operations/absent", headers={"Authorization": "Bearer arbitrary"}).status_code == 401
            with ControlDbUnitOfWork(settings.control_db_path, read_only=True) as uow:
                assert uow.connection.execute("SELECT count(*) FROM provisioned_scope_mappings").fetchone()[0] == 0
