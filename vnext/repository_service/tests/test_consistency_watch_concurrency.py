"""Concurrency tests for runtime consistency watch registration."""

from __future__ import annotations

import shutil
import threading
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from gateway_repository_service.layout import repository_key
from gateway_repository_service.mutation_reconciliation import MutableConsistencyWatch
from support.lifecycle_harness import dolt_available
from support.recovery_harness import replay_create, start_runtime

pytestmark = pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")


def test_concurrent_create_registration_preserves_both_repositories() -> None:
    watch = MutableConsistencyWatch()
    repo_a = uuid4()
    repo_b = uuid4()
    barrier = threading.Barrier(2)

    def register(repository_id: UUID) -> None:
        barrier.wait()
        watch.register_succeeded_create(repository_id)

    threads = [
        threading.Thread(target=register, args=(repo_a,)),
        threading.Thread(target=register, args=(repo_b,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    snapshot = watch.snapshot()
    assert repo_a in snapshot.create_repository_ids
    assert repo_b in snapshot.create_repository_ids


def test_concurrent_upload_registration_preserves_both_artifacts() -> None:
    watch = MutableConsistencyWatch()
    repo_a = uuid4()
    repo_b = uuid4()
    artifact_a = uuid4()
    artifact_b = uuid4()
    barrier = threading.Barrier(2)

    def register(repository_id: UUID, artifact_id: UUID, size_bytes: int) -> None:
        barrier.wait()
        watch.register_succeeded_upload(repository_id, artifact_id, size_bytes)

    threads = [
        threading.Thread(target=register, args=(repo_a, artifact_a, 11)),
        threading.Thread(target=register, args=(repo_b, artifact_b, 22)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    snapshot = watch.snapshot()
    assert (repo_a, artifact_a, 11) in snapshot.upload_artifacts
    assert (repo_b, artifact_b, 22) in snapshot.upload_artifacts


def test_concurrent_create_replay_keeps_both_repositories_under_readiness_watch(
    tmp_path: Path,
) -> None:
    settings, runtime = start_runtime(tmp_path)
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def worker(idempotency_key: str) -> None:
        try:
            barrier.wait()
            replay_create(runtime, idempotency_key=idempotency_key)
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("concurrent-create-a",)),
        threading.Thread(target=worker, args=("concurrent-create-b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []

    try:
        assert runtime.is_ready()
        snapshot = runtime.consistency_watch.snapshot()
        assert len(snapshot.create_repository_ids) == 2

        victim_id = snapshot.create_repository_ids[0]
        published = runtime.layout.published_repository(repository_key(victim_id))
        shutil.rmtree(published)
        assert not runtime.is_ready()
    finally:
        runtime.shutdown()
