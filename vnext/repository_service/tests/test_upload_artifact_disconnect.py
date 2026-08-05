"""Disconnect handling tests for UploadArtifact."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from starlette.requests import ClientDisconnect

from gateway_repository_contracts import REPOSITORY_IMPORT_MEDIA_TYPE, UploadRequestHeaders
from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.mutation_store import (
    ClaimResult,
    EffectRecord,
    EffectStatus,
    MutationStore,
    configure_connection,
)
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.command import UploadArtifactCommand
from support.upload_harness import upload_sha256


def _settings(tmp_path: Path) -> RepositoryServiceSettings:
    return RepositoryServiceSettings(profile="test", data_root=tmp_path / "data-root")


def test_upload_disconnect_cleans_partial_staging_without_publication(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    layout = DurableLayout.create_service(settings.data_root)
    import sqlite3
    from unittest.mock import patch

    connection = sqlite3.connect(":memory:")
    configure_connection(connection)
    store = MutationStore(connection)
    repository_id = uuid4()
    artifact_id = uuid4()
    payload = b"partial-body"
    headers = UploadRequestHeaders(
        content_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        content_length=len(payload),
        idempotency_key="disconnect-upload",
        artifact_sha256=upload_sha256(payload),
    )

    async def disconnecting_body() -> AsyncIterator[bytes]:
        yield payload[:4]
        raise ClientDisconnect()

    command = UploadArtifactCommand(settings=settings, layout=layout, mutation_store=store)
    key = repository_key(repository_id)
    staging_dir, ready_dir = layout.repository_artifact_directories(key)

    with patch(
        "gateway_repository_service.upload_artifact.command.is_repository_visible",
        return_value=True,
    ), patch.object(MutationStore, "claim_or_lookup") as claim_mock, patch.object(
        MutationStore, "allocate_pending"
    ) as pending_mock, patch.object(
        MutationStore, "mark_succeeded", side_effect=AssertionError("must not succeed")
    ) as succeeded_mock:
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
            resource_id=artifact_id,
            status=EffectStatus.PENDING,
            response_status=None,
            response_body=None,
        )

        with pytest.raises(ClientDisconnect):
            asyncio.run(command.execute(repository_id, headers, disconnecting_body()))

        succeeded_mock.assert_not_called()

    assert list(staging_dir.glob(f"{artifact_id.hex}.*")) == []
    assert list(ready_dir.iterdir()) == []
