"""Integration tests for CreateRepository with real Dolt."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typing import cast

from gateway_repository_service.app import create_app
from gateway_repository_service.create_repository.visibility import is_repository_visible
from gateway_repository_service.layout import repository_key
from gateway_repository_service.providers import OfflineCliProvider
from gateway_repository_service.process import DoltRunner
from support.lifecycle_harness import lifecycle_settings


def _auth_headers(*, idempotency_key: str = "integration-create-1") -> dict[str, str]:
    return {
        "Authorization": "Bearer test-bearer-token",
        "Idempotency-Key": idempotency_key,
    }


@pytest.mark.integration
def test_create_repository_returns_real_ids_and_published_tree(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        response = client.post("/v1/repositories", headers=_auth_headers())
        assert response.status_code == 201
        body = response.json()
        repository_id = UUID(body["repository_id"])
        assert body["default_ref"] == "main"
        assert len(body["initial_commit_id"]) > 0

        runtime = cast(FastAPI, client.app).state.runtime
        published = settings.data_root / "versioned" / repository_key(repository_id)
        assert published.is_dir()
        assert (published / ".dolt").is_dir()

        provider = OfflineCliProvider(
            settings,
            runtime.layout,
            published,
            DoltRunner(settings, runtime.layout.root),
        )
        assert provider.head() == body["initial_commit_id"]
        assert is_repository_visible(runtime.mutation_store, runtime.layout, repository_id)
