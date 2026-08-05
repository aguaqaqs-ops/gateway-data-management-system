"""Publication boundary tests for CreateRepository."""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway_repository_service.create_repository.adapters import FilesystemPublicationAdapter
from gateway_repository_service.create_repository.command import CreateRepositoryCommand
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.publication import FaultPoint
from gateway_repository_service.runtime import ServiceRuntime
from support.lifecycle_harness import dolt_available, lifecycle_settings


class _BeforeRenameFaultInjector:
    def publication_fault(self) -> FaultPoint:
        return FaultPoint.BEFORE_RENAME


class _NoReplacePublicationPort:
    def publish(self, staging: Path, target: Path, *, fault: FaultPoint = FaultPoint.NONE) -> None:
        del staging, fault
        raise FileExistsError(target)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_create_repository_publication_fault_is_fail_closed(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    runtime = ServiceRuntime.start(settings)
    try:
        command = CreateRepositoryCommand(
            settings=settings,
            layout=runtime.layout,
            mutation_store=runtime.mutation_store,
            fault_injector=_BeforeRenameFaultInjector(),
        )
        with pytest.raises(RuntimeError, match="fault injected before publication rename"):
            command.execute("fault-before-rename")

        published_dirs = list((settings.data_root / "versioned").iterdir())
        assert published_dirs == []
    finally:
        runtime.shutdown()


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_create_repository_no_replace_conflict_cleans_staging(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    runtime = ServiceRuntime.start(settings)
    try:
        command = CreateRepositoryCommand(
            settings=settings,
            layout=runtime.layout,
            mutation_store=runtime.mutation_store,
            publication_port=_NoReplacePublicationPort(),
        )
        with pytest.raises(ServiceError) as exc_info:
            command.execute("no-replace-conflict")

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "IDEMPOTENCY_CONFLICT"
        assert list(runtime.layout.staging_versioned.iterdir()) == []
    finally:
        runtime.shutdown()


def test_atomic_publication_no_replace_preserves_existing_target(tmp_path: Path) -> None:
    layout = DurableLayout.create_for_probe(tmp_path / "root")
    adapter = FilesystemPublicationAdapter()
    key = "d" * 32
    staging = layout.staging_repository(key, "source")
    (staging / "payload").write_text("new", encoding="utf-8")
    target = layout.published_repository(key)
    target.mkdir(parents=True)
    (target / "payload").write_text("old", encoding="utf-8")
    with pytest.raises(FileExistsError):
        adapter.publish(staging, target)
    assert (target / "payload").read_text(encoding="utf-8") == "old"
