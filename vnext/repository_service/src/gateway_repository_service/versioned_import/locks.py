"""Process-local repository writer ownership for Versioned import workers."""

from __future__ import annotations

import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from uuid import UUID


class RepositoryLockRegistry:
    """Tracks active repositories and serializes per-repository Dolt writers."""

    def __init__(self, *, max_repository_lock_entries: int = 1024) -> None:
        self._scheduler_lock = threading.Lock()
        self._active_repositories: set[UUID] = set()
        self._manual_barrier_repositories: set[UUID] = set()
        self._repository_locks_guard = threading.Lock()
        self._repository_locks: dict[UUID, threading.Lock] = {}
        self._max_repository_lock_entries = max_repository_lock_entries

    def seed_manual_barriers(self, repository_ids: Iterable[UUID]) -> None:
        with self._scheduler_lock:
            self._manual_barrier_repositories.update(repository_ids)

    def has_manual_barrier(self, repository_id: UUID) -> bool:
        with self._scheduler_lock:
            return repository_id in self._manual_barrier_repositories

    def clear_manual_barrier(self, repository_id: UUID) -> None:
        with self._scheduler_lock:
            self._manual_barrier_repositories.discard(repository_id)

    def try_reserve(self, repository_id: UUID) -> bool:
        with self._scheduler_lock:
            if repository_id in self._active_repositories:
                return False
            self._active_repositories.add(repository_id)
            return True

    def release_reservation(self, repository_id: UUID) -> None:
        with self._scheduler_lock:
            self._active_repositories.discard(repository_id)

    def is_active(self, repository_id: UUID) -> bool:
        with self._scheduler_lock:
            return repository_id in self._active_repositories

    @contextmanager
    def repository_execution(self, repository_id: UUID) -> Iterator[None]:
        lock = self._lock_for(repository_id)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()
            self.evict_idle_repository_locks(self._max_repository_lock_entries)

    def evict_idle_repository_locks(self, max_entries: int) -> None:
        if max_entries <= 0:
            return
        with self._repository_locks_guard:
            if len(self._repository_locks) <= max_entries:
                return
            with self._scheduler_lock:
                active = set(self._active_repositories)
            evictable = [
                repository_id
                for repository_id, lock in self._repository_locks.items()
                if repository_id not in active and not lock.locked()
            ]
            while len(self._repository_locks) > max_entries and evictable:
                repository_id = evictable.pop()
                self._repository_locks.pop(repository_id, None)

    def _lock_for(self, repository_id: UUID) -> threading.Lock:
        with self._repository_locks_guard:
            existing = self._repository_locks.get(repository_id)
            if existing is not None:
                return existing
            created = threading.Lock()
            self._repository_locks[repository_id] = created
            return created
