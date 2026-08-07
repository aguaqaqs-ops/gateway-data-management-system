"""Bounded worker pool for durable Versioned import operations."""

from __future__ import annotations

import logging
import queue
import shutil
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID

from gateway_repository_contracts import SimpleError

from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.versioned_import.command import ImportOperationExecutor
from gateway_repository_service.versioned_import.faults import (
    ImportWorkerFaultInjector,
    NoOpImportWorkerFaultInjector,
)
from gateway_repository_service.versioned_import.locks import RepositoryLockRegistry
from gateway_repository_service.versioned_import.models import ImportOperationTransitionRejected
from gateway_repository_service.versioned_import.ports import (
    CancellationCallback,
    VersionedImportProvider,
)
from gateway_repository_service.versioned_import.store import ImportOperationStore
from gateway_repository_service.versioned_import.verification import IMPORT_REJECTED_CODE

_LOGGER = logging.getLogger(__name__)


class ImportWorkerShutdownError(RuntimeError):
    """Raised when import worker threads fail to stop within the configured timeout."""


class _CancellableProviderWrapper:
    """Delegates to an inner provider while threading cancellation into replay_sql."""

    def __init__(
        self,
        inner: VersionedImportProvider,
        cancellation: CancellationCallback,
    ) -> None:
        self._inner = inner
        self._cancellation = cancellation

    def read_ref(self, ref_name: str) -> str:
        return self._inner.read_ref(ref_name)

    def create_private_ref(self, private_ref: str, expected_commit: str) -> None:
        self._inner.create_private_ref(private_ref, expected_commit)

    def checkout_private_ref(self, private_ref: str) -> None:
        self._inner.checkout_private_ref(private_ref)

    def replay_sql(
        self,
        private_ref: str,
        replay_path: Any,
        cancellation: CancellationCallback | None = None,
    ) -> None:
        del cancellation

        def _combined() -> bool:
            return self._cancellation()

        return self._inner.replay_sql(private_ref, replay_path, cancellation=_combined)

    def commit_operation_marker(self, private_ref: str, marker: str) -> str:
        return self._inner.commit_operation_marker(private_ref, marker)

    def inspect_marker(self, marker: str) -> Any:
        return self._inner.inspect_marker(marker)

    def read_catalog(self, candidate: str) -> Any:
        return self._inner.read_catalog(candidate)

    def read_type_catalog(self, candidate: str) -> Any:
        return self._inner.read_type_catalog(candidate)

    def stream_table(self, candidate: str, table: Any, policy: Any) -> Any:
        return self._inner.stream_table(candidate, table, policy)

    def publish_main(self, expected_commit: str, candidate: str) -> Any:
        return self._inner.publish_main(expected_commit, candidate)

    def delete_private_ref(
        self,
        private_ref: str,
        expected_candidate: str | None = None,
    ) -> None:
        self._inner.delete_private_ref(private_ref, expected_candidate=expected_candidate)


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
        shutdown_event: threading.Event | None = None,
    ) -> None:
        self._settings = settings
        self._layout = layout
        self._store = store
        self._provider_factory = provider_factory
        self._locks = locks or RepositoryLockRegistry()
        self._fault_injector = fault_injector or NoOpImportWorkerFaultInjector()
        self._external_shutdown = shutdown_event
        self._work_queue: queue.Queue[tuple[UUID, UUID]] = queue.Queue()
        self._shutdown = threading.Event()
        self._stop_claiming = False
        self._notify = threading.Condition()
        self._round_robin_index = 0
        self._in_flight = 0
        self._in_flight_lock = threading.Lock()
        self._cancellation_tokens: dict[UUID, threading.Event] = {}
        self._cancellation_lock = threading.Lock()
        self._dispatcher: threading.Thread | None = None
        self._workers: list[threading.Thread] = []

    def start(self) -> None:
        if self._dispatcher is not None:
            return
        self._shutdown.clear()
        self._stop_claiming = False
        self._dispatcher = threading.Thread(
            target=self._dispatch_loop,
            name="import-worker-dispatcher",
            daemon=False,
        )
        self._dispatcher.start()
        for index in range(self._settings.max_import_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"import-worker-{index}",
                daemon=False,
            )
            worker.start()
            self._workers.append(worker)

    def begin_shutdown(self) -> None:
        self._stop_claiming = True
        with self._notify:
            self._notify.notify_all()

    def cancel_active_operations(self) -> None:
        with self._cancellation_lock:
            for event in self._cancellation_tokens.values():
                event.set()

    def stop(self, *, timeout: float | None = None) -> None:
        join_timeout = (
            timeout
            if timeout is not None
            else max(self._settings.import_shutdown_grace_seconds * 2, 5.0)
        )
        self.begin_shutdown()
        self._shutdown.set()
        with self._notify:
            self._notify.notify_all()
        timed_out: list[str] = []
        if self._dispatcher is not None:
            self._dispatcher.join(timeout=join_timeout)
            if self._dispatcher.is_alive():
                timed_out.append(self._dispatcher.name)
            self._dispatcher = None
        for worker in self._workers:
            worker.join(timeout=join_timeout)
            if worker.is_alive():
                timed_out.append(worker.name)
        self._workers.clear()
        if timed_out:
            message = f"import worker threads did not stop within {join_timeout}s: {', '.join(timed_out)}"
            _LOGGER.error(message)
            raise ImportWorkerShutdownError(message)

    def notify(self) -> None:
        with self._notify:
            self._notify.notify_all()

    def _is_shutting_down(self) -> bool:
        if self._shutdown.is_set():
            return True
        return self._external_shutdown is not None and self._external_shutdown.is_set()

    def _dispatch_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                claimed = self._try_claim_one()
                if claimed is not None:
                    self._work_queue.put(claimed)
                    continue
                with self._notify:
                    self._notify.wait(timeout=0.1)
            except Exception:
                _LOGGER.exception("import dispatcher failed while claiming queued operation")
                self._shutdown.wait(timeout=0.25)

    def _repository_has_barrier(self, repository_id: UUID) -> bool:
        return (
            self._locks.has_manual_barrier(repository_id)
            or self._store.has_unresolved_manual_barrier(repository_id)
        )

    def _try_claim_one(self) -> tuple[UUID, UUID] | None:
        if self._stop_claiming or self._is_shutting_down():
            return None
        with self._in_flight_lock:
            if self._in_flight >= self._settings.max_import_workers:
                return None
        candidates = self._store.list_earliest_queued_per_repository()
        if not candidates:
            return None
        ordered = self._rotate_candidates(candidates)
        for repository_id, operation_id, _enqueue_sequence in ordered:
            if self._repository_has_barrier(repository_id):
                continue
            if not self._locks.try_reserve(repository_id):
                continue
            claimed = self._store.claim_if_queued(operation_id)
            if claimed is None:
                self._locks.release_reservation(repository_id)
                continue
            with self._in_flight_lock:
                self._in_flight += 1
            return (operation_id, repository_id)
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
        while not self._shutdown.is_set():
            try:
                operation_id, repository_id = self._work_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._execute_operation(operation_id, repository_id)
            except Exception:
                _LOGGER.exception("import worker failed for operation %s", operation_id)
            finally:
                self._work_queue.task_done()

    def _cancellation_for(self, operation_id: UUID) -> Iterator[threading.Event]:
        event = threading.Event()
        with self._cancellation_lock:
            self._cancellation_tokens[operation_id] = event
        try:
            yield event
        finally:
            with self._cancellation_lock:
                self._cancellation_tokens.pop(operation_id, None)

    def _execute_operation(
        self,
        operation_id: UUID,
        repository_id: UUID,
    ) -> None:
        try:
            try:
                context = self._store.load_execution_context(operation_id)
            except Exception:
                _LOGGER.exception(
                    "failed to load execution context for operation %s",
                    operation_id,
                )
                if not self._is_shutting_down():
                    self._mark_context_load_failure(operation_id)
                return

            if context is None:
                _LOGGER.error("missing execution context for operation %s", operation_id)
                if not self._is_shutting_down():
                    self._mark_context_load_failure(operation_id)
                return

            with self._locks.repository_execution(repository_id):
                for cancellation_event in self._cancellation_for(operation_id):
                    if self._is_shutting_down():
                        return

                    def _interruption_check(
                        *,
                        _cancellation: threading.Event = cancellation_event,
                    ) -> bool:
                        return self._is_shutting_down() or _cancellation.is_set()

                    executor = ImportOperationExecutor(
                        settings=self._settings,
                        layout=self._layout,
                        store=self._store,
                        fault_injector=self._fault_injector,
                        interruption_check=_interruption_check,
                    )
                    provider = _CancellableProviderWrapper(
                        self._provider_factory(repository_id),
                        cancellation_event.is_set,
                    )
                    executor.execute(context, provider)
        finally:
            with self._in_flight_lock:
                self._in_flight = max(0, self._in_flight - 1)
            self._locks.release_reservation(repository_id)
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

    def _mark_context_load_failure(self, operation_id: UUID) -> None:
        try:
            self._store.mark_failed(
                operation_id,
                error=SimpleError(
                    code=IMPORT_REJECTED_CODE,
                    message="import operation context could not be loaded",
                    details={"reason": "operation_context_missing"},
                    request_id=None,
                ),
            )
        except ImportOperationTransitionRejected:
            _LOGGER.error(
                "cannot persist terminal failure for operation %s: status transition rejected",
                operation_id,
            )
        except Exception:
            _LOGGER.exception(
                "failed to persist terminal failure for operation %s",
                operation_id,
            )

    def wait_for_quiescence(self, *, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._in_flight_lock:
                if self._in_flight == 0 and self._work_queue.empty():
                    return True
            time.sleep(0.05)
        with self._in_flight_lock:
            return self._in_flight == 0 and self._work_queue.empty()
