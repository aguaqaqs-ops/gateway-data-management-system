"""Concurrency tests for shared control-store transaction locking."""

from __future__ import annotations

import threading
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from gateway_repository_contracts import RepositoryArtifactRef, UnknownTypePolicy, VerificationPolicy
from gateway_repository_service.mutation_store import IdempotencyKeyHash, IdempotencyScope, MutationKind
from gateway_repository_service.versioned_import import ImportRequestBinding, versioned_import_fingerprint_v1
from support.import_worker_harness import MEDIA_TYPE, WorkerTestEnvironment

REPOSITORY_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")


@pytest.mark.serial
def test_dispatcher_and_mutation_store_do_not_nested_transaction(tmp_path: Path) -> None:
    env = WorkerTestEnvironment(tmp_path)
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def claim_worker() -> None:
        try:
            barrier.wait()
            binding = ImportRequestBinding(
                repository_id=REPOSITORY_ID,
                artifact_ref=RepositoryArtifactRef(
                    artifact_id=uuid4(),
                    media_type=MEDIA_TYPE,
                    size_bytes=1,
                    raw_sha256="a" * 64,
                ),
                target_ref="main",
                expected_commit_id="commit-main",
                verification_policy=VerificationPolicy.STRUCTURAL,
                unknown_type_policy=UnknownTypePolicy.REJECT,
            )
            key_hash = IdempotencyKeyHash.from_raw_key(f"nested-{uuid4()}")
            fingerprint = versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash)
            env.store.claim_or_enqueue(binding, key_hash=key_hash, fingerprint=fingerprint)
        except BaseException as exc:
            errors.append(exc)

    def mutation_worker() -> None:
        try:
            barrier.wait()
            scope = IdempotencyScope(
                mutation_kind=MutationKind.CREATE_REPOSITORY,
                repository_id=None,
            )
            key_hash = IdempotencyKeyHash.from_raw_key(f"create-{uuid4()}")
            env.mutation_store.claim_or_lookup(
                scope,
                key_hash=key_hash,
                fingerprint=b"create-fingerprint",
            )
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=claim_worker),
        threading.Thread(target=mutation_worker),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    env.close()
    assert errors == []
