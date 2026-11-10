"""The RS owner keeps cleanup available during recoverable capacity rejection."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gateway_repository_service import runtime_preflight as preflight
from gateway_repository_service.artifact_cleaner import ArtifactCleaner
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.settings import RepositoryServiceSettings
from support.lifecycle_harness import prepare_test_roots
from support.storage_layout import write_storage_layout
from gateway_repository_service.storage_roots import RepositoryRoots
from support.artifact_cleanup_contract import (
    BASE_NOW, mark_succeeded_consumed, seed_artifact, seed_create_succeeded, write_ready,
)

pytestmark = [pytest.mark.integration, pytest.mark.serial]


def test_rs_readiness_low_water_allows_actual_cleaner_and_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    roots = prepare_test_roots(RepositoryRoots.under(tmp_path / "roots"))
    storage = write_storage_layout(roots)
    resources = tmp_path / "resources.json"
    document = json.loads((Path(__file__).parents[2] / "fixtures/runtime-config/v1/resource-profile.json").read_bytes())
    document.update(environment_id="test", group_id="test")
    resources.write_text(json.dumps(document))
    settings = RepositoryServiceSettings(profile="test", bearer_token="test", storage_layout_file=storage,
        resource_profile_file=resources, artifact_cleanup_interval_seconds=3600, artifact_ttl_seconds=3600)
    config = settings.deployment_config
    assert config is not None
    monkeypatch.setattr(preflight, "check_resources", lambda *_: None)
    monkeypatch.setattr(preflight, "mounts", lambda: tuple(preflight.Mount(index, "1:1", root.source,
        root.path, config.storage.filesystems[root.filesystem_id].expected_source, True)
        for index, root in enumerate(config.storage.roots.values())))
    runtime = ServiceRuntime.start(settings)
    try:
        assert runtime.is_ready()
        seed_create_succeeded(runtime.mutation_store)
        seed_artifact(runtime.mutation_store)
        ready = write_ready(runtime.layout)
        mark_succeeded_consumed(runtime.import_store, key="low-water")
        cleaner = runtime.artifact_cleaner
        assert isinstance(cleaner, ArtifactCleaner)
        cleaner._clock = lambda: BASE_NOW
        real_capacity = preflight.check_capacity

        def capacity(path: Path, minimum: int, fraction: float) -> tuple[int, int]:
            if ready.exists():
                raise preflight.CapacityUnavailable("injected physical low-water observation")
            return real_capacity(path, minimum, fraction)

        monkeypatch.setattr(preflight, "check_capacity", capacity)
        assert not runtime.is_ready()
        cleaner.sweep_once()
        assert not ready.exists()
        assert runtime.is_ready()
    finally:
        runtime.shutdown()
