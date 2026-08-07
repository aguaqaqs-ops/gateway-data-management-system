"""Process-local repository writer ownership for Versioned import workers."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID


class RepositoryLockRegistry:
    """Tracks active repositories and serializes per-repository Dolt writers."""

    def __init__(self) -> None:
        self._scheduler_lock = threading.Lock()
        self._active_repositories: set[UUID] = set()
        self._repository_locks_guard = threading.Lock()
        self._repository_locks: dict[UUID, threading.Lock] = {}

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

    def _lock_for(self, repository_id: UUID) -> threading.Lock:
        with self._repository_locks_guard:
            existing = self._repository_locks.get(repository_id)
            if existing is not None:
                return existing
            created = threading.Lock()
            self._repository_locks[repository_id] = created
            return created
