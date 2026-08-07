"""Idempotency tests for CreateRepository."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typing import cast

from gateway_repository_service.app import create_app
from gateway_repository_service.mutation_fingerprints import CREATE_REPOSITORY_FINGERPRINT_V1
from gateway_repository_service.mutation_store import IdempotencyScope, MutationStore
from support.lifecycle_harness import lifecycle_settings


def _auth_headers(*, idempotency_key: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer test-bearer-token",
        "Idempotency-Key": idempotency_key,
    }


@pytest.mark.integration
def test_same_key_replays_original_201_body(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        first = client.post("/v1/repositories", headers=_auth_headers(idempotency_key="replay-key"))
        second = client.post("/v1/repositories", headers=_auth_headers(idempotency_key="replay-key"))

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()


@pytest.mark.integration
def test_different_fingerprint_conflict_returns_409(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        runtime = cast(FastAPI, client.app).state.runtime
        store = runtime.mutation_store
        scope = IdempotencyScope.for_create()
        key_hash = MutationStore.hash_idempotency_key("conflict-key")
        store.claim_or_lookup(
            scope,
            key_hash=key_hash,
            fingerprint=CREATE_REPOSITORY_FINGERPRINT_V1,
        )
        store.allocate_pending(
            scope,
            key_hash=key_hash,
            fingerprint=CREATE_REPOSITORY_FINGERPRINT_V1,
            resource_id=uuid4(),
        )
        with patch(
            "gateway_repository_service.create_repository.command.create_repository_fingerprint_v1",
            return_value=b"different-fingerprint",
        ):
            response = client.post(
                "/v1/repositories",
                headers=_auth_headers(idempotency_key="conflict-key"),
            )

    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_CONFLICT"
