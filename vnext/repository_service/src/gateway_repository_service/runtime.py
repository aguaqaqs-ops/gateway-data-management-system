"""Service composition root and durable lifecycle orchestration."""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, field
from uuid import UUID

from gateway_repository_service.auth_state import AuthState
from gateway_repository_service.capacity import (
    has_free_disk_admission,
    is_durable_root_writable,
)
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.locking import DurableRootLock
from gateway_repository_service.mutation_reconciliation import (
    MutableConsistencyWatch,
    ReconciliationError,
    SynchronousMutationReconciler,
    filesystem_watch_failures,
    import_artifact_watch_failures,
)
from gateway_repository_service.mutation_store import MutationStore, configure_connection
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.provider_lifecycle import OfflineCliCapabilityGate
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.versioned_import.locks import RepositoryLockRegistry
from gateway_repository_service.versioned_import.provider import CandidateAImportProvider
from gateway_repository_service.versioned_import.recovery import ImportStartupReconciler
from gateway_repository_service.versioned_import.store import ImportOperationStore
from gateway_repository_service.versioned_import.worker import ImportWorkerPool

_LOGGER = logging.getLogger(__name__)


class ServiceStartupError(RuntimeError):
    """Raised when durable lifecycle initialization fails."""


@dataclass
class ServiceRuntime:
    settings: RepositoryServiceSettings
    layout: DurableLayout
    root_lock: DurableRootLock
    control_store: ControlStore
    mutation_store: MutationStore
    import_store: ImportOperationStore
    import_locks: RepositoryLockRegistry
    import_worker_pool: ImportWorkerPool
    dolt_runner: DoltRunner
    provider_gate: OfflineCliCapabilityGate
    auth_state: AuthState
    reconciliation_failures: tuple[str, ...] = ()
    consistency_watch: MutableConsistencyWatch = field(
        default_factory=MutableConsistencyWatch,
        repr=False,
    )
    _stopping: threading.Event = field(default_factory=threading.Event, repr=False)

    @classmethod
    def start(cls, settings: RepositoryServiceSettings) -> "ServiceRuntime":
        stack = ExitStack()
        try:
            bearer_token = settings.resolve_bearer_token()
            layout = DurableLayout.create_service(settings.data_root)
            root_lock = DurableRootLock(layout.service_lock)
            root_lock.acquire()
            stack.callback(root_lock.release)
            control_store = ControlStore.open(
                settings.control_db_path,
                expected_version=CONTROL_DB_USER_VERSION,
                busy_timeout_ms=settings.sqlite_busy_timeout_ms,
            )
            stack.callback(control_store.close)
            configure_connection(control_store.connection)
            mutation_store = MutationStore(
                control_store.connection,
                transaction_lock=control_store.transaction_lock,
            )
            import_store = ImportOperationStore(
                control_store.connection,
                transaction_lock=control_store.transaction_lock,
            )
            provider_gate = OfflineCliCapabilityGate.verify(settings, layout)
            dolt_runner = DoltRunner(settings, layout.root)
            reconciliation = SynchronousMutationReconciler(
                settings=settings,
                layout=layout,
                mutation_store=mutation_store,
            ).reconcile()
            import_locks = RepositoryLockRegistry()
            provider_factory = cls._build_provider_factory(
                settings=settings,
                layout=layout,
                dolt_runner=dolt_runner,
            )
            ImportStartupReconciler(
                settings=settings,
                layout=layout,
                store=import_store,
                provider_factory=provider_factory,
            ).reconcile()
            import_locks.seed_manual_barriers(import_store.list_repositories_with_manual_barrier())
            if not is_durable_root_writable(layout.service_state):
                raise ServiceStartupError("durable root is not writable")
            if not has_free_disk_admission(layout.root, settings):
                raise ServiceStartupError("durable root free disk is below admission threshold")
            stopping = threading.Event()
            import_worker_pool = ImportWorkerPool(
                settings=settings,
                layout=layout,
                store=import_store,
                provider_factory=provider_factory,
                locks=import_locks,
                shutdown_event=stopping,
            )
            import_worker_pool.start()
            import_worker_pool.notify()
            stack.pop_all()
            return cls(
                settings=settings,
                layout=layout,
                root_lock=root_lock,
                control_store=control_store,
                mutation_store=mutation_store,
                import_store=import_store,
                import_locks=import_locks,
                import_worker_pool=import_worker_pool,
                dolt_runner=dolt_runner,
                provider_gate=provider_gate,
                auth_state=AuthState(bearer_token=bearer_token),
                reconciliation_failures=reconciliation.blocking_failures,
                consistency_watch=MutableConsistencyWatch.from_watch(reconciliation.consistency_watch),
                _stopping=stopping,
            )
        except ReconciliationError as exc:
            raise ServiceStartupError(str(exc)) from exc
        except ServiceStartupError:
            raise
        except Exception as exc:
            raise ServiceStartupError(str(exc)) from exc
        finally:
            stack.close()

    @staticmethod
    def _build_provider_factory(
        *,
        settings: RepositoryServiceSettings,
        layout: DurableLayout,
        dolt_runner: DoltRunner,
    ) -> Callable[[UUID], CandidateAImportProvider]:
        def provider_factory(repository_id: UUID) -> CandidateAImportProvider:
            repository_path = layout.published_repository(repository_key(repository_id))
            return CandidateAImportProvider(
                settings,
                layout,
                repository_path,
                dolt_runner,
            )

        return provider_factory

    def shutdown(self) -> None:
        self._stopping.set()
        self.import_worker_pool.begin_shutdown()
        grace = self.settings.import_shutdown_grace_seconds
        try:
            if not self.import_worker_pool.wait_for_quiescence(timeout=grace):
                self.import_worker_pool.cancel_active_operations()
                self.dolt_runner.terminate_active_children(grace_seconds=grace)
            try:
                self.import_worker_pool.stop(timeout=grace * 2)
            except Exception:
                _LOGGER.exception("import worker pool did not stop cleanly")
                self.dolt_runner.terminate_active_children(grace_seconds=grace)
                try:
                    self.import_worker_pool.stop(timeout=grace)
                except Exception:
                    _LOGGER.exception("import worker pool still running after second stop")
        finally:
            if self.control_store.is_open():
                self.control_store.close()
            if self.root_lock.is_held():
                self.root_lock.release()

    def is_accepting_import_effects(self) -> bool:
        return not self._stopping.is_set()

    def register_succeeded_create(self, repository_id: UUID) -> None:
        self.consistency_watch.register_succeeded_create(repository_id)

    def register_succeeded_upload(
        self,
        repository_id: UUID,
        artifact_id: UUID,
        size_bytes: int,
    ) -> None:
        self.consistency_watch.register_succeeded_upload(repository_id, artifact_id, size_bytes)

    def _readiness_failure(self) -> str | None:
        try:
            if self._stopping.is_set():
                return "service is shutting down"
            if not self.root_lock.is_held():
                return "root lock is not held"
            if not self._control_db_ready():
                return "control database is unavailable"
            if self.reconciliation_failures:
                return "mutation ledger and filesystem are inconsistent"
            watch_snapshot = self.consistency_watch.snapshot()
            if filesystem_watch_failures(watch_snapshot, self.layout):
                return "mutation ledger and filesystem are inconsistent"
            if import_artifact_watch_failures(
                self.import_store,
                self.mutation_store,
                watch_snapshot,
                self.layout,
            ):
                return "mutation ledger and filesystem are inconsistent"
            if not self._provider_ready():
                return "provider is unavailable"
            if not is_durable_root_writable(self.layout.service_state):
                return "durable root is not writable"
            if not has_free_disk_admission(self.layout.root, self.settings):
                return "free disk admission failed"
            return None
        except Exception:
            return "readiness check failed"

    def _control_db_ready(self) -> bool:
        if not self.control_store.is_open():
            return False
        try:
            self.control_store.connection.execute("SELECT 1")
        except Exception:
            return False
        return True

    def _provider_ready(self) -> bool:
        binary = self.provider_gate.executable_path()
        return binary.is_file() and os.access(binary, os.X_OK)

    def is_ready(self) -> bool:
        return self._readiness_failure() is None

    def not_ready_message(self) -> str:
        failure = self._readiness_failure()
        if failure is None:
            return "service is not ready"
        return failure
