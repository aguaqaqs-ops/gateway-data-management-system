"""Focused unit tests for upload concurrency admission."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from gateway_repository_contracts import REPOSITORY_IMPORT_MEDIA_TYPE, UploadRequestHeaders
from gateway_repository_service.admission import InflightKeyGate, PermitPool
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_store import (
    ClaimResult,
    EffectRecord,
    EffectStatus,
    MutationStore,
)
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.command import UploadArtifactCommand
from support.upload_harness import upload_sha256


def _settings(tmp_path: Path) -> RepositoryServiceSettings:
    return RepositoryServiceSettings(
        profile="test",
        bearer_token="test-token",
        data_root=tmp_path / "data-root",
        max_concurrent_uploads=8,
        min_free_disk_bytes=1,
        min_free_disk_fraction=0.01,
    )


def _headers(*, key: str, payload: bytes) -> UploadRequestHeaders:
    return UploadRequestHeaders(
        content_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        content_length=len(payload),
        idempotency_key=key,
        artifact_sha256=upload_sha256(payload),
    )


def _command(
    settings: RepositoryServiceSettings,
    *,
    pool: PermitPool,
    store: MutationStore | MagicMock | None = None,
    inflight: InflightKeyGate | None = None,
) -> UploadArtifactCommand:
    layout = DurableLayout.create_service(settings.data_root)
    return UploadArtifactCommand(
        settings=settings,
        layout=layout,
        mutation_store=store or MagicMock(spec=MutationStore),
        upload_admission=pool,
        upload_inflight=inflight if inflight is not None else InflightKeyGate(),
    )


@pytest.mark.parametrize("held", [8])
def test_ninth_upload_rejected_before_pending_and_body(tmp_path: Path, held: int) -> None:
    settings = _settings(tmp_path)
    pool = PermitPool(held)
    held_leases = [pool.try_acquire() for _ in range(held)]
    assert all(lease is not None for lease in held_leases)
    assert pool.in_use == held

    store = MagicMock(spec=MutationStore)
    store.hash_idempotency_key = MutationStore.hash_idempotency_key
    store.claim_or_lookup.return_value = ClaimResult(
        idempotency_id=1,
        is_new=True,
        fingerprint=b"fp",
        effect=None,
        terminal_not_published=False,
    )
    body_chunks: list[bytes] = []

    async def body() -> AsyncIterator[bytes]:
        body_chunks.append(b"chunk")
        yield b"chunk"

    command = _command(settings, pool=pool, store=store)
    payload = b"chunk"
    with pytest.raises(ServiceError) as exc_info:
        asyncio.run(
            command.execute(
                uuid4(),
                _headers(key="ninth", payload=payload),
                body(),
            )
        )
    assert exc_info.value.status_code == 429
    assert exc_info.value.code == "UPLOAD_CONCURRENCY_LIMIT"
    store.allocate_pending.assert_not_called()
    assert body_chunks == []
    assert pool.in_use == held
    for lease in held_leases:
        assert lease is not None
        lease.release()


def test_success_replay_does_not_consume_upload_permit(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    pool = PermitPool(1)
    held = pool.try_acquire()
    assert held is not None

    store = MagicMock(spec=MutationStore)
    store.hash_idempotency_key = MutationStore.hash_idempotency_key
    artifact_id = uuid4()
    store.claim_or_lookup.return_value = ClaimResult(
        idempotency_id=1,
        is_new=False,
        fingerprint=b"fp",
        effect=EffectRecord(
            effect_id=1,
            idempotency_id=1,
            resource_id=artifact_id,
            status=EffectStatus.SUCCEEDED,
            response_status=201,
            response_body={
                "artifact_ref": {
                    "artifact_id": str(artifact_id),
                    "media_type": REPOSITORY_IMPORT_MEDIA_TYPE,
                    "size_bytes": 4,
                    "raw_sha256": upload_sha256(b"data"),
                }
            },
        ),
        terminal_not_published=False,
    )
    body_pulled = False

    async def body() -> AsyncIterator[bytes]:
        nonlocal body_pulled
        body_pulled = True
        yield b"data"

    command = _command(settings, pool=pool, store=store)
    response = asyncio.run(
        command.execute(uuid4(), _headers(key="replay", payload=b"data"), body())
    )
    assert response.artifact_ref.artifact_id == artifact_id
    assert body_pulled is False
    assert pool.in_use == 1
    store.allocate_pending.assert_not_called()
    held.release()


def test_pending_same_key_does_not_consume_upload_permit(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    pool = PermitPool(1)
    held = pool.try_acquire()
    assert held is not None
    assert pool.in_use == 1

    store = MagicMock(spec=MutationStore)
    store.hash_idempotency_key = MutationStore.hash_idempotency_key
    store.claim_or_lookup.return_value = ClaimResult(
        idempotency_id=9,
        is_new=False,
        fingerprint=b"fp-pending",
        effect=EffectRecord(
            effect_id=9,
            idempotency_id=9,
            resource_id=uuid4(),
            status=EffectStatus.PENDING,
            response_status=None,
            response_body=None,
        ),
        terminal_not_published=False,
    )
    body_chunks: list[bytes] = []

    async def body() -> AsyncIterator[bytes]:
        body_chunks.append(b"x")
        yield b"x"

    command = _command(settings, pool=pool, store=store)
    with pytest.raises(ServiceError) as exc_info:
        asyncio.run(command.execute(uuid4(), _headers(key="inflight", payload=b"x"), body()))
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "IDEMPOTENCY_CONFLICT"
    assert pool.in_use == 1
    assert body_chunks == []
    store.allocate_pending.assert_not_called()
    held.release()


def test_validation_failure_releases_upload_permit(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    pool = PermitPool(1)
    store = MagicMock(spec=MutationStore)
    store.hash_idempotency_key = MutationStore.hash_idempotency_key
    store.claim_or_lookup.return_value = ClaimResult(
        idempotency_id=1,
        is_new=True,
        fingerprint=b"fp",
        effect=None,
        terminal_not_published=False,
    )

    async def body() -> AsyncIterator[bytes]:
        yield b"x"

    command = _command(settings, pool=pool, store=store)
    with patch(
        "gateway_repository_service.upload_artifact.command.is_repository_visible",
        return_value=False,
    ):
        with pytest.raises(ServiceError) as exc_info:
            asyncio.run(
                command.execute(uuid4(), _headers(key="missing-repo", payload=b"x"), body())
            )
    assert exc_info.value.status_code == 404
    assert pool.in_use == 0
    store.allocate_pending.assert_not_called()


def test_payload_too_large_releases_upload_permit(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings = settings.model_copy(update={"max_upload_bytes": 4})
    pool = PermitPool(1)
    store = MagicMock(spec=MutationStore)
    store.hash_idempotency_key = MutationStore.hash_idempotency_key
    store.claim_or_lookup.return_value = ClaimResult(
        idempotency_id=2,
        is_new=True,
        fingerprint=b"fp2",
        effect=None,
        terminal_not_published=False,
    )
    payload = b"12345"

    async def body() -> AsyncIterator[bytes]:
        yield payload

    command = _command(settings, pool=pool, store=store)
    with patch(
        "gateway_repository_service.upload_artifact.command.is_repository_visible",
        return_value=True,
    ):
        with pytest.raises(ServiceError) as exc_info:
            asyncio.run(
                command.execute(uuid4(), _headers(key="too-large", payload=payload), body())
            )
    assert exc_info.value.status_code == 413
    assert pool.in_use == 0


@pytest.mark.serial
@pytest.mark.parallel_safe
def test_closed_pool_denies_new_upload(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    pool = PermitPool(2)
    pool.close()
    store = MagicMock(spec=MutationStore)
    store.hash_idempotency_key = MutationStore.hash_idempotency_key
    store.claim_or_lookup.return_value = ClaimResult(
        idempotency_id=3,
        is_new=True,
        fingerprint=b"fp3",
        effect=None,
        terminal_not_published=False,
    )

    async def body() -> AsyncIterator[bytes]:
        yield b"z"

    command = _command(settings, pool=pool, store=store)
    with pytest.raises(ServiceError) as exc_info:
        asyncio.run(command.execute(uuid4(), _headers(key="closed", payload=b"z"), body()))
    assert exc_info.value.code == "UPLOAD_CONCURRENCY_LIMIT"
    store.allocate_pending.assert_not_called()


@pytest.mark.serial
def test_concurrent_same_key_loser_is_409_without_consuming_permit(tmp_path: Path) -> None:
    settings = _settings(tmp_path).model_copy(update={"max_concurrent_uploads": 1})
    pool = PermitPool(1)
    inflight = InflightKeyGate()
    store = MagicMock(spec=MutationStore)
    store.hash_idempotency_key = MutationStore.hash_idempotency_key
    store.claim_or_lookup.return_value = ClaimResult(
        idempotency_id=1,
        is_new=True,
        fingerprint=b"fp-race",
        effect=None,
        terminal_not_published=False,
    )
    winner_holding = threading.Event()
    release_winner = threading.Event()
    peak_in_use = 0
    peak_lock = threading.Lock()
    results: list[BaseException | object] = []

    def track_peak() -> None:
        nonlocal peak_in_use
        with peak_lock:
            peak_in_use = max(peak_in_use, pool.in_use)

    async def winner_body() -> AsyncIterator[bytes]:
        winner_holding.set()
        while not release_winner.wait(timeout=0.01):
            yield b""
        yield b"x"

    async def loser_body() -> AsyncIterator[bytes]:
        yield b"x"

    repository_id = uuid4()
    headers = _headers(key="same-key", payload=b"x")
    winner = _command(settings, pool=pool, store=store, inflight=inflight)
    loser = _command(settings, pool=pool, store=store, inflight=inflight)

    def run_winner() -> None:
        try:
            with (
                patch(
                    "gateway_repository_service.upload_artifact.command.is_repository_visible",
                    return_value=True,
                ),
                patch(
                    "gateway_repository_service.upload_artifact.command.assert_upload_disk_admission",
                    return_value=None,
                ),
            ):
                def allocate(*_a: object, **_k: object) -> EffectRecord:
                    track_peak()
                    return EffectRecord(
                        effect_id=1,
                        idempotency_id=1,
                        resource_id=uuid4(),
                        status=EffectStatus.PENDING,
                        response_status=None,
                        response_body=None,
                    )

                store.allocate_pending.side_effect = allocate
                asyncio.run(winner.execute(repository_id, headers, winner_body()))
        except BaseException as exc:  # noqa: BLE001 — collect for assertion
            results.append(exc)

    def run_loser() -> None:
        assert winner_holding.wait(timeout=5.0)
        track_peak()
        try:
            with patch(
                "gateway_repository_service.upload_artifact.command.is_repository_visible",
                return_value=True,
            ):
                asyncio.run(loser.execute(repository_id, headers, loser_body()))
                results.append("unexpected-success")
        except BaseException as exc:  # noqa: BLE001 — collect for assertion
            results.append(exc)
        finally:
            release_winner.set()

    threads = [
        threading.Thread(target=run_winner),
        threading.Thread(target=run_loser),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10.0)
        assert not thread.is_alive()

    track_peak()
    assert peak_in_use == 1
    assert pool.in_use == 0
    assert store.allocate_pending.call_count == 1
    assert any(
        isinstance(item, ServiceError)
        and item.status_code == 409
        and item.code == "IDEMPOTENCY_CONFLICT"
        for item in results
    )
    assert not any(
        isinstance(item, ServiceError) and item.status_code == 429 for item in results
    )
