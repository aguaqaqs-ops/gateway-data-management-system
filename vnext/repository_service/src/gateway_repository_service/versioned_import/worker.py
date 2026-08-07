"""Bounded worker pool for durable Versioned import operations."""

from __future__ import annotations

import logging
import queue
import shutil
import threading
from collections.abc import Callable
from uuid import UUID

from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.versioned_import.command import ImportOperationExecutor
from gateway_repository_service.versioned_import.faults import (
    ImportWorkerFaultInjector,
    NoOpImportWorkerFaultInjector,
)
from gateway_repository_service.versioned_import.locks import RepositoryLockRegistry
from gateway_repository_service.versioned_import.ports import VersionedImportProvider
from gateway_repository_service.versioned_import.store import ImportOperationStore

_LOGGER = logging.getLogger(__name__)


class ImportWorkerPool:
    """Claims queued import operations and executes them with bounded concurrency."""

    def __init__(
        self,
        *,
        settings: RepositoryServiceSettings,
        layout: DurableLayout,
        store: ImportOperationStore,
        provider_factory: Callable[[UUID], VersionedImportProvider],
        locks: RepositoryLockRegistry | None = None,
        fault_injector: ImportWorkerFaultInjector | None = None,
    ) -> None:
        self._settings = settings
        self._layout = layout
        self._store = store
        self._provider_factory = provider_factory
        self._locks = locks or RepositoryLockRegistry()
        self._fault_injector = fault_injector or NoOpImportWorkerFaultInjector()
        self._work_queue: queue.Queue[UUID] = queue.Queue()
        self._shutdown = threading.Event()
        self._notify = threading.Condition()
        self._round_robin_index = 0
        self._in_flight = 0
        self._in_flight_lock = threading.Lock()
        self._dispatcher: threading.Thread | None = None
        self._workers: list[threading.Thread] = []

    def start(self) -> None:
        if self._dispatcher is not None:
            return
        self._shutdown.clear()
        self._dispatcher = threading.Thread(
            target=self._dispatch_loop,
            name="import-worker-dispatcher",
            daemon=True,
        )
        self._dispatcher.start()
        for index in range(self._settings.max_import_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"import-worker-{index}",
                daemon=True,
            )
            worker.start()
            self._workers.append(worker)

    def stop(self, *, timeout: float = 5.0) -> None:
        self._shutdown.set()
        with self._notify:
            self._notify.notify_all()
        if self._dispatcher is not None:
            self._dispatcher.join(timeout=timeout)
            self._dispatcher = None
        for worker in self._workers:
            worker.join(timeout=timeout)
        self._workers.clear()

    def notify(self) -> None:
        with self._notify:
            self._notify.notify_all()

    def _dispatch_loop(self) -> None:
        while not self._shutdown.is_set():
            claimed = self._try_claim_one()
            if claimed is not None:
                self._work_queue.put(claimed)
                continue
            with self._notify:
                self._notify.wait(timeout=0.1)

    def _try_claim_one(self) -> UUID | None:
        with self._in_flight_lock:
            if self._in_flight >= self._settings.max_import_workers:
                return None
        candidates = self._store.list_earliest_queued_per_repository()
        if not candidates:
            return None
        ordered = self._rotate_candidates(candidates)
        for repository_id, operation_id, _enqueue_sequence in ordered:
            if self._store.has_unresolved_manual_barrier(repository_id):
                continue
            if not self._locks.try_reserve(repository_id):
                continue
            claimed = self._store.claim_if_queued(operation_id)
            if claimed is None:
                self._locks.release_reservation(repository_id)
                continue
            with self._in_flight_lock:
                self._in_flight += 1
            return operation_id
        return None

    def _rotate_candidates(
        self,
        candidates: list[tuple[UUID, UUID, int]],
    ) -> list[tuple[UUID, UUID, int]]:
        if not candidates:
            return []
        start = self._round_robin_index % len(candidates)
        self._round_robin_index = (start + 1) % len(candidates)
        return candidates[start:] + candidates[:start]

    def _worker_loop(self) -> None:
        executor = ImportOperationExecutor(
            settings=self._settings,
            layout=self._layout,
            store=self._store,
            fault_injector=self._fault_injector,
        )
        while not self._shutdown.is_set():
            try:
                operation_id = self._work_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._execute_operation(executor, operation_id)
            except Exception:
                _LOGGER.exception("import worker failed for operation %s", operation_id)
            finally:
                self._work_queue.task_done()

    def _execute_operation(
        self,
        executor: ImportOperationExecutor,
        operation_id: UUID,
    ) -> None:
        context = self._store.load_execution_context(operation_id)
        if context is None:
            with self._in_flight_lock:
                self._in_flight = max(0, self._in_flight - 1)
            return
        try:
            with self._locks.repository_execution(context.repository_id):
                provider = self._provider_factory(context.repository_id)
                executor.execute(context, provider)
        finally:
            with self._in_flight_lock:
                self._in_flight = max(0, self._in_flight - 1)
            self._locks.release_reservation(context.repository_id)
            self.notify()
            staging_dir = self._layout.staging_artifacts / f"import-{operation_id.hex}"
            if staging_dir.exists():
                try:
                    shutil.rmtree(staging_dir)
                except OSError:
                    _LOGGER.exception(
                        "failed to remove import staging for operation %s",
                        operation_id,
                    )
