"""Visibility tests for CreateRepository dual-condition checks."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typing import cast

from gateway_repository_service.app import create_app
from gateway_repository_service.create_repository.visibility import (
    has_published_repository_tree,
    is_repository_visible,
)
from gateway_repository_service.layout import repository_key
from gateway_repository_service.mutation_fingerprints import create_repository_fingerprint_v1
from gateway_repository_service.mutation_store import IdempotencyScope, MutationStore
from gateway_repository_service.runtime import ServiceRuntime
from support.lifecycle_harness import lifecycle_settings


@pytest.mark.integration
def test_repository_visible_only_with_db_and_filesystem(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/v1/repositories",
            headers={
                "Authorization": "Bearer test-bearer-token",
                "Idempotency-Key": "visibility-key",
            },
        )
        runtime = cast(FastAPI, client.app).state.runtime
        repository_id = UUID(response.json()["repository_id"])
        assert is_repository_visible(runtime.mutation_store, runtime.layout, repository_id)

        published = runtime.layout.published_repository(repository_key(repository_id))
        published.rename(published.with_name(f"{published.name}-moved"))
        assert runtime.mutation_store.has_succeeded_create(repository_id)
        assert not has_published_repository_tree(runtime.layout, repository_id)
        assert not is_repository_visible(runtime.mutation_store, runtime.layout, repository_id)


@pytest.mark.integration
def test_db_only_repository_is_not_visible(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    runtime = ServiceRuntime.start(settings)
    try:
        repository_id = uuid4()
        scope = IdempotencyScope.for_create()
        key_hash = MutationStore.hash_idempotency_key("db-only")
        fingerprint = create_repository_fingerprint_v1()
        runtime.mutation_store.claim_or_lookup(scope, key_hash=key_hash, fingerprint=fingerprint)
        effect = runtime.mutation_store.allocate_pending(
            scope,
            key_hash=key_hash,
            fingerprint=fingerprint,
            resource_id=repository_id,
        )
        runtime.mutation_store.mark_succeeded(
            effect.effect_id,
            response_body={
                "repository_id": str(repository_id),
                "default_ref": "main",
                "initial_commit_id": "deadbeef",
            },
        )
        assert runtime.mutation_store.has_succeeded_create(repository_id)
        assert not is_repository_visible(runtime.mutation_store, runtime.layout, repository_id)
    finally:
        runtime.shutdown()
