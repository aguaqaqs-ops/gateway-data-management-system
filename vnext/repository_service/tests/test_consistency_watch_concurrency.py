"""Concurrency tests for runtime consistency watch registration."""

from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor
import threading
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from gateway_repository_service.layout import repository_key
from gateway_repository_service.mutation_reconciliation import MutableConsistencyWatch
from support.recovery_harness import replay_create, start_runtime

pytestmark = pytest.mark.integration


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


@pytest.mark.serial
def test_concurrent_create_replay_keeps_both_repositories_under_readiness_watch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings, runtime = start_runtime(tmp_path)
    first_create_finished = threading.Event()
    register_together = threading.Barrier(2)
    register_succeeded_create = runtime.register_succeeded_create

    def register(repository_id: UUID) -> None:
        # execute() has returned and released the CREATE gate. The next request
        # may create while this successful request is about to update its watch.
        first_create_finished.set()
        register_together.wait(timeout=30)
        register_succeeded_create(repository_id)

    monkeypatch.setattr(runtime, "register_succeeded_create", register)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            try:
                first = pool.submit(replay_create, runtime, idempotency_key="concurrent-create-a")
                assert first_create_finished.wait(timeout=30)
                second = pool.submit(replay_create, runtime, idempotency_key="concurrent-create-b")
                response_a = first.result(timeout=30)
                response_b = second.result(timeout=30)
            finally:
                register_together.abort()

        repository_ids = {UUID(str(response_a.repository_id)), UUID(str(response_b.repository_id))}
        assert len(repository_ids) == 2
        assert set(runtime.consistency_watch.snapshot().create_repository_ids) == repository_ids
        assert runtime.is_ready()

        published = runtime.layout.published_repository(repository_key(UUID(str(response_b.repository_id))))
        shutil.rmtree(published)
        assert not runtime.is_ready()
    finally:
        register_together.abort()
        runtime.shutdown()
