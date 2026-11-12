"""CREATE owner recovers one original effect without restarting its runtime."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from typing import cast
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from gateway_repository_service.app import create_app
from gateway_repository_service.create_repository.adapters import DoltCreateAdapter
from gateway_repository_service.create_repository.command import CreateRepositoryCommand
from gateway_repository_service.create_repository.execution import CreateExecutionOwner
from gateway_repository_service.create_repository.ports import NoOpCreateRepositoryFaultInjector
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.layout import repository_key
from gateway_repository_service.mutation_fingerprints import create_repository_fingerprint_v1
from gateway_repository_service.mutation_store import EffectStatus, MutationStore, StoredEffectView
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.runtime import ServiceRuntime
from support.lifecycle_harness import lifecycle_settings


class BeforeInitialize(NoOpCreateRepositoryFaultInjector):
    def after_pending(self) -> None:
        raise OSError("initialize interrupted")


def original(runtime: ServiceRuntime, key: str) -> StoredEffectView:
    effect = runtime.mutation_store.lookup_create_effect(key_hash=MutationStore.hash_idempotency_key(key),
        fingerprint=create_repository_fingerprint_v1())
    assert effect is not None
    return effect


@pytest.mark.integration
@pytest.mark.parametrize("terminal", [False, True])
def test_unpublished_create_retries_original_effect_in_same_runtime(tmp_path: Path, terminal: bool) -> None:
    runtime = ServiceRuntime.start(lifecycle_settings(tmp_path))
    try:
        command = CreateRepositoryCommand(settings=runtime.settings, layout=runtime.layout,
            mutation_store=runtime.mutation_store, fault_injector=BeforeInitialize())
        with pytest.raises(OSError):
            command.execute("original")
        effect = original(runtime, "original")
        if terminal:
            runtime.mutation_store.mark_terminal_not_published(effect.scope, key_hash=effect.key_hash,
                fingerprint=effect.fingerprint, effect_id=effect.effect_id)
        response = CreateRepositoryCommand(settings=runtime.settings, layout=runtime.layout,
            mutation_store=runtime.mutation_store).execute("original")
        recovered = original(runtime, "original")
        assert str(response.repository_id) == str(effect.resource_id)
        assert recovered.effect_id == effect.effect_id
        assert recovered.status == EffectStatus.SUCCEEDED
        assert not recovered.terminal_not_published
    finally:
        runtime.shutdown()


@pytest.mark.integration
def test_published_create_response_is_recovered_before_ledger_success(tmp_path: Path) -> None:
    runtime = ServiceRuntime.start(lifecycle_settings(tmp_path))
    try:
        command = CreateRepositoryCommand(settings=runtime.settings, layout=runtime.layout, mutation_store=runtime.mutation_store)
        with patch.object(runtime.mutation_store, "mark_succeeded", side_effect=OSError("ledger commit lost")):
            with pytest.raises(OSError):
                command.execute("published")
        effect = original(runtime, "published")
        assert effect.status == EffectStatus.PENDING
        response = command.execute("published")
        assert str(response.repository_id) == str(effect.resource_id)
        assert original(runtime, "published").effect_id == effect.effect_id
        assert command.execute("published") == response
    finally:
        runtime.shutdown()


@pytest.mark.integration
@pytest.mark.parametrize("target_kind", ["file", "directory", "symlink"])
def test_bad_publication_evidence_stays_unresolved_and_preserves_target(tmp_path: Path, target_kind: str) -> None:
    runtime = ServiceRuntime.start(lifecycle_settings(tmp_path))
    try:
        command = CreateRepositoryCommand(settings=runtime.settings, layout=runtime.layout,
            mutation_store=runtime.mutation_store, fault_injector=BeforeInitialize())
        with pytest.raises(OSError):
            command.execute("bad-evidence")
        effect = original(runtime, "bad-evidence")
        target = runtime.layout.published_repository(repository_key(effect.resource_id))
        if target_kind == "file":
            target.write_text("preserve")
        elif target_kind == "directory":
            target.mkdir()
            (target / "preserve").write_text("preserve")
        else:
            target.symlink_to(tmp_path, target_is_directory=True)
        with pytest.raises(ServiceError) as raised:
            CreateRepositoryCommand(settings=runtime.settings, layout=runtime.layout,
                mutation_store=runtime.mutation_store).execute("bad-evidence")
        assert raised.value.code == "CREATE_REPOSITORY_UNRESOLVED"
        assert target.exists()
        assert original(runtime, "bad-evidence").status == EffectStatus.PENDING
        assert not original(runtime, "bad-evidence").terminal_not_published
    finally:
        runtime.shutdown()


@pytest.mark.integration
@pytest.mark.serial
def test_inflight_create_keeps_same_key_busy_until_executor_finishes(tmp_path: Path) -> None:
    runtime = ServiceRuntime.start(lifecycle_settings(tmp_path))
    entered, release = Event(), Event()
    class BlockingCreate:
        def initialize_and_head(self, staging: Path) -> str:
            entered.set()
            assert release.wait(timeout=10)
            return DoltCreateAdapter(runtime.settings, runtime.layout).initialize_and_head(staging)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            command = CreateRepositoryCommand(settings=runtime.settings, layout=runtime.layout,
                mutation_store=runtime.mutation_store, create_port=BlockingCreate())
            pending = pool.submit(command.execute, "same-key")
            try:
                assert entered.wait(timeout=10)
                with pytest.raises(ServiceError) as raised:
                    CreateRepositoryCommand(settings=runtime.settings, layout=runtime.layout,
                        mutation_store=runtime.mutation_store).execute("same-key")
                assert raised.value.code == "CREATE_REPOSITORY_BUSY"
            finally:
                release.set()
            response = pending.result(timeout=10)
        assert command.execute("same-key") == response
    finally:
        release.set()
        runtime.shutdown()


def test_unconfirmed_dolt_exit_retains_create_owner() -> None:
    owner = CreateExecutionOwner()
    class Runner:
        def has_active_children(self) -> bool:
            return True
    owner.runner = cast(DoltRunner, Runner())
    with pytest.raises(ServiceError, match="unresolved"):
        with owner.admit():
            pass
    assert owner.in_use
    with pytest.raises(ServiceError) as raised:
        with owner.admit():
            pass
    assert raised.value.code == "CREATE_REPOSITORY_UNRESOLVED"


@pytest.mark.integration
def test_deployment_identity_requires_rs_bearer_and_returns_cached_facts(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        assert client.get("/internal/v1/deployment-identity").status_code == 401
        response = client.get("/internal/v1/deployment-identity", headers={"Authorization": "Bearer test-bearer-token"})
        assert response.status_code == 200
        assert settings.deployment_config is not None
        storage = settings.deployment_config.storage
        assert response.json() == {"environment_id": storage.environment_id, "group_id": storage.group_id,
            "storage_digest": storage.digest}
