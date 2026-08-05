"""Tests for synchronous mutation ledger and idempotency metadata."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from gateway_repository_contracts import REPOSITORY_IMPORT_MEDIA_TYPE
from gateway_repository_service.control_db import ControlStore
from gateway_repository_service.mutation_fingerprints import (
    CREATE_REPOSITORY_FINGERPRINT_V1,
    create_repository_fingerprint_v1,
    upload_artifact_fingerprint_v1,
)
from gateway_repository_service.mutation_store import (
    DuplicateEffectClaim,
    EffectStatus,
    FingerprintConflict,
    IdempotencyKeyHash,
    IdempotencyScope,
    IdempotencyTerminalNotPublished,
    MutationKind,
    MutationStore,
    configure_connection,
)

REPOSITORY_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
OTHER_REPOSITORY_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11")
SHA256 = "a" * 64
OTHER_SHA256 = "b" * 64


@pytest.fixture
def store(tmp_path: Path) -> MutationStore:
    db_path = tmp_path / "service-state" / "repository-service.sqlite3"
    control_store = ControlStore.open(db_path, expected_version=2, busy_timeout_ms=1000)
    control_store.close()
    connection = sqlite3.connect(db_path)
    configure_connection(connection)
    return MutationStore(connection)


def _create_scope() -> IdempotencyScope:
    return IdempotencyScope(mutation_kind=MutationKind.CREATE_REPOSITORY)


def _upload_scope(repository_id: UUID = REPOSITORY_ID) -> IdempotencyScope:
    return IdempotencyScope(
        mutation_kind=MutationKind.UPLOAD_ARTIFACT,
        repository_id=repository_id,
    )


def _upload_fingerprint(*, declared_size: int = 12, raw_sha256_hex: str = SHA256) -> bytes:
    return upload_artifact_fingerprint_v1(
        media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        declared_size=declared_size,
        raw_sha256_hex=raw_sha256_hex,
    )


def test_create_fingerprint_is_versioned_constant() -> None:
    assert create_repository_fingerprint_v1() == CREATE_REPOSITORY_FINGERPRINT_V1


def test_upload_fingerprint_golden_vector() -> None:
    fingerprint = upload_artifact_fingerprint_v1(
        media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        declared_size=12,
        raw_sha256_hex=SHA256,
    )
    assert fingerprint.startswith(b"upload_artifact/v1\x00")
    assert fingerprint.endswith(bytes.fromhex(SHA256))


def test_idempotency_key_hash_repr_does_not_include_raw_key() -> None:
    key_hash = IdempotencyKeyHash.from_raw_key("secret-key")
    rendered = repr(key_hash)
    assert "secret-key" not in rendered
    assert "IdempotencyKeyHash(" in rendered


def test_same_key_same_fingerprint_replays_stored_response(store: MutationStore) -> None:
    scope = _create_scope()
    key_hash = IdempotencyKeyHash.from_raw_key("create-1")
    fingerprint = create_repository_fingerprint_v1()
    resource_id = uuid4()
    response_body = {
        "repository_id": str(resource_id),
        "default_ref": "main",
        "initial_commit_id": "commit-1",
    }

    pending = store.allocate_pending(
        scope,
        key_hash=key_hash,
        fingerprint=fingerprint,
        resource_id=resource_id,
    )
    store.mark_succeeded(
        pending.effect_id,
        response_status=201,
        response_body=response_body,
    )

    replay = store.get_stored_response(scope, key_hash=key_hash, fingerprint=fingerprint)
    assert replay == (201, response_body)


def test_same_key_different_fingerprint_conflicts(store: MutationStore) -> None:
    scope = _create_scope()
    key_hash = IdempotencyKeyHash.from_raw_key("create-1")
    first = create_repository_fingerprint_v1()
    store.allocate_pending(scope, key_hash=key_hash, fingerprint=first, resource_id=uuid4())

    with pytest.raises(FingerprintConflict):
        store.allocate_pending(
            scope,
            key_hash=key_hash,
            fingerprint=first + b"x",
            resource_id=uuid4(),
        )


def test_kind_and_scope_isolation(store: MutationStore) -> None:
    key_hash = IdempotencyKeyHash.from_raw_key("shared-key")
    create_scope = _create_scope()
    upload_scope = _upload_scope()
    create_pending = store.allocate_pending(
        create_scope,
        key_hash=key_hash,
        fingerprint=create_repository_fingerprint_v1(),
        resource_id=uuid4(),
    )
    upload_pending = store.allocate_pending(
        upload_scope,
        key_hash=key_hash,
        fingerprint=_upload_fingerprint(),
        resource_id=uuid4(),
    )
    assert create_pending.effect_id != upload_pending.effect_id


def test_upload_scope_isolation_by_repository(store: MutationStore) -> None:
    key_hash = IdempotencyKeyHash.from_raw_key("upload-key")
    first = store.allocate_pending(
        _upload_scope(REPOSITORY_ID),
        key_hash=key_hash,
        fingerprint=_upload_fingerprint(),
        resource_id=uuid4(),
    )
    second = store.allocate_pending(
        _upload_scope(OTHER_REPOSITORY_ID),
        key_hash=key_hash,
        fingerprint=_upload_fingerprint(),
        resource_id=uuid4(),
    )
    assert first.effect_id != second.effect_id


def test_pending_to_succeeded_lifecycle(store: MutationStore) -> None:
    scope = _create_scope()
    key_hash = IdempotencyKeyHash.from_raw_key("create-2")
    fingerprint = create_repository_fingerprint_v1()
    pending = store.allocate_pending(
        scope,
        key_hash=key_hash,
        fingerprint=fingerprint,
        resource_id=uuid4(),
    )
    assert pending.status == EffectStatus.PENDING

    succeeded = store.mark_succeeded(
        pending.effect_id,
        response_status=201,
        response_body={"repository_id": str(pending.resource_id), "default_ref": "main", "initial_commit_id": "c1"},
    )
    assert succeeded.status == EffectStatus.SUCCEEDED
    assert succeeded.response_status == 201


def test_terminal_not_published_blocks_new_effect(store: MutationStore) -> None:
    scope = _create_scope()
    key_hash = IdempotencyKeyHash.from_raw_key("create-terminal")
    fingerprint = create_repository_fingerprint_v1()
    store.claim_or_lookup(scope, key_hash=key_hash, fingerprint=fingerprint)
    store.mark_terminal_not_published(scope, key_hash=key_hash)

    with pytest.raises(IdempotencyTerminalNotPublished):
        store.allocate_pending(
            scope,
            key_hash=key_hash,
            fingerprint=fingerprint,
            resource_id=uuid4(),
        )


def test_duplicate_pending_claim_is_rejected(store: MutationStore) -> None:
    scope = _create_scope()
    key_hash = IdempotencyKeyHash.from_raw_key("create-dup")
    fingerprint = create_repository_fingerprint_v1()
    store.allocate_pending(scope, key_hash=key_hash, fingerprint=fingerprint, resource_id=uuid4())

    with pytest.raises(DuplicateEffectClaim):
        store.allocate_pending(
            scope,
            key_hash=key_hash,
            fingerprint=fingerprint,
            resource_id=uuid4(),
        )


def test_concurrent_same_key_claim_has_single_effect_owner(tmp_path: Path) -> None:
    db_path = tmp_path / "service-state" / "repository-service.sqlite3"
    ControlStore.open(db_path, expected_version=2, busy_timeout_ms=1000).close()

    barrier = threading.Barrier(2)
    results: list[EffectStatus | BaseException] = []

    def worker() -> None:
        connection = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
        configure_connection(connection)
        mutation_store = MutationStore(connection)
        scope = _create_scope()
        key_hash = IdempotencyKeyHash.from_raw_key("concurrent-key")
        fingerprint = create_repository_fingerprint_v1()
        barrier.wait()
        try:
            effect = mutation_store.allocate_pending(
                scope,
                key_hash=key_hash,
                fingerprint=fingerprint,
                resource_id=uuid4(),
            )
            results.append(effect.status)
        except BaseException as exc:
            results.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    successes = [item for item in results if isinstance(item, EffectStatus)]
    failures = [item for item in results if isinstance(item, BaseException)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], DuplicateEffectClaim)


def test_claim_or_lookup_returns_existing_effect(store: MutationStore) -> None:
    scope = _create_scope()
    key_hash = IdempotencyKeyHash.from_raw_key("lookup-key")
    fingerprint = create_repository_fingerprint_v1()
    pending = store.allocate_pending(
        scope,
        key_hash=key_hash,
        fingerprint=fingerprint,
        resource_id=uuid4(),
    )

    claim = store.claim_or_lookup(scope, key_hash=key_hash, fingerprint=fingerprint)
    assert claim.is_new is False
    assert claim.effect is not None
    assert claim.effect.effect_id == pending.effect_id


def test_mutation_store_sql_does_not_persist_raw_key() -> None:
    ddl = (Path(__file__).resolve().parents[1] / "src" / "gateway_repository_service" / "control_db.py").read_text(
        encoding="utf-8"
    )
    assert "idempotency_key" not in ddl.lower()
    assert "key_hash" in ddl
    store_source = (Path(__file__).resolve().parents[1] / "src" / "gateway_repository_service" / "mutation_store.py").read_text(
        encoding="utf-8"
    )
    insert_columns = [
        part.split("VALUES", 1)[0].lower()
        for part in store_source.split("INSERT INTO")[1:]
    ]
    assert insert_columns
    for columns in insert_columns:
        assert "idempotency_key" not in columns
        assert "raw_key" not in columns
