"""Unit tests for process-local PermitPool."""

from __future__ import annotations

import threading

import pytest

from gateway_repository_service.admission import PermitPool


def test_permit_pool_rejects_non_positive_capacity() -> None:
    with pytest.raises(ValueError):
        PermitPool(0)
    with pytest.raises(ValueError):
        PermitPool(-1)


def test_try_acquire_returns_none_when_full() -> None:
    pool = PermitPool(2)
    first = pool.try_acquire()
    second = pool.try_acquire()
    assert first is not None
    assert second is not None
    assert pool.try_acquire() is None
    snap = pool.snapshot()
    assert snap.capacity == 2
    assert snap.in_use == 2
    assert snap.closed is False
    first.release()
    third = pool.try_acquire()
    assert third is not None
    assert pool.in_use == 2
    second.release()
    third.release()
    assert pool.in_use == 0


def test_lease_release_is_idempotent() -> None:
    pool = PermitPool(1)
    lease = pool.try_acquire()
    assert lease is not None
    lease.release()
    lease.release()
    assert pool.in_use == 0
    assert pool.try_acquire() is not None


def test_closed_pool_rejects_new_acquire_but_allows_release() -> None:
    pool = PermitPool(1)
    lease = pool.try_acquire()
    assert lease is not None
    pool.close()
    assert pool.closed is True
    assert pool.try_acquire() is None
    lease.release()
    assert pool.in_use == 0
    assert pool.try_acquire() is None


@pytest.mark.serial
def test_concurrent_release_does_not_over_issue_permits() -> None:
    capacity = 8
    pool = PermitPool(capacity)
    barrier = threading.Barrier(capacity)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            lease = pool.try_acquire()
            assert lease is not None
            barrier.wait(timeout=5.0)
            lease.release()
            lease.release()
        except BaseException as exc:  # noqa: BLE001 — collect for assertion
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(capacity)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10.0)
        assert not thread.is_alive()
    assert not errors
    assert pool.in_use == 0
    assert pool.try_acquire() is not None
