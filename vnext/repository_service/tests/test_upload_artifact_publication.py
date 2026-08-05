"""Publication boundary tests for UploadArtifact."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typing import cast

from gateway_repository_service.app import create_app
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.publication import FaultPoint
from gateway_repository_service.upload_artifact.adapters import ArtifactFilesystemPublicationAdapter
from gateway_repository_service.upload_artifact.command import UploadArtifactCommand
from support.lifecycle_harness import dolt_available, lifecycle_settings
from support.upload_harness import create_repository, upload_headers


class _BeforeRenameFaultInjector:
    def after_pending(self) -> None:
        return None

    def after_partial_body(self) -> None:
        return None

    def after_complete_close(self) -> None:
        return None

    def publication_fault(self) -> FaultPoint:
        return FaultPoint.BEFORE_RENAME


class _NoReplacePublicationPort:
    def publish_file(self, staging: Path, target: Path, *, fault: FaultPoint = FaultPoint.NONE) -> None:
        del staging, fault
        raise FileExistsError(target)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_upload_publication_fault_is_fail_closed(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    payload = b"fault-before-rename"
    with TestClient(create_app(settings)) as client:
        repository_id = create_repository(client, idempotency_key="create-fault")
        runtime = cast(FastAPI, client.app).state.runtime
        command = UploadArtifactCommand(
            settings=settings,
            layout=runtime.layout,
            mutation_store=runtime.mutation_store,
            fault_injector=_BeforeRenameFaultInjector(),
        )
        with pytest.raises(RuntimeError, match="fault injected before publication rename"):
            import asyncio
            from collections.abc import AsyncIterator

            async def body() -> AsyncIterator[bytes]:
                yield payload

            from gateway_repository_contracts import UploadRequestHeaders

            headers = UploadRequestHeaders.model_validate(
                {
                    "content_type": upload_headers(payload=payload)["Content-Type"],
                    "content_length": len(payload),
                    "idempotency_key": "fault-before-rename",
                    "artifact_sha256": upload_headers(payload=payload)["X-Artifact-SHA256"],
                }
            )
            asyncio.run(command.execute(repository_id, headers, body()))

        key = repository_id.hex
        ready_dir = settings.data_root / "artifacts" / key / "ready"
        assert list(ready_dir.iterdir()) == []


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_upload_no_partial_ready_artifact_on_failure(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    payload = b"no-ready-partial"
    with TestClient(create_app(settings)) as client:
        repository_id = create_repository(client, idempotency_key="create-no-ready")
        runtime = cast(FastAPI, client.app).state.runtime
        command = UploadArtifactCommand(
            settings=settings,
            layout=runtime.layout,
            mutation_store=runtime.mutation_store,
            publication_port=_NoReplacePublicationPort(),
        )

        import asyncio
        from collections.abc import AsyncIterator

        async def body() -> AsyncIterator[bytes]:
            yield payload

        from gateway_repository_contracts import UploadRequestHeaders

        headers = UploadRequestHeaders.model_validate(
            {
                "content_type": upload_headers(payload=payload)["Content-Type"],
                "content_length": len(payload),
                "idempotency_key": "no-ready-partial",
                "artifact_sha256": upload_headers(payload=payload)["X-Artifact-SHA256"],
            }
        )
        with pytest.raises(ServiceError) as exc_info:
            asyncio.run(command.execute(repository_id, headers, body()))
        assert exc_info.value.status_code == 409

        ready_dir = settings.data_root / "artifacts" / repository_id.hex / "ready"
        assert list(ready_dir.iterdir()) == []


def test_atomic_file_publication_no_replace_preserves_existing_target(tmp_path: Path) -> None:
    adapter = ArtifactFilesystemPublicationAdapter()
    staging = tmp_path / "files" / "staging"
    target = tmp_path / "files" / "ready" / "artifact"
    staging.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    staging.write_bytes(b"new")
    target.write_bytes(b"old")
    with pytest.raises(FileExistsError):
        adapter.publish_file(staging, target)
    assert target.read_bytes() == b"old"
