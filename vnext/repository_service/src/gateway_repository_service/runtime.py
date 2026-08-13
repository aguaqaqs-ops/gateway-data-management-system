"""Service composition root and durable lifecycle orchestration."""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, field
from uuid import UUID

from gateway_repository_service.admission import (
    InflightKeyGate,
    PermitPool,
    UploadCancelRegistry,
)
from gateway_repository_service.artifact_cleaner import (
    ArtifactCleaner,
    ArtifactCleanerLifecycle,
    ArtifactCleanerShutdownError,
    NoOpArtifactCleaner,
)
from gateway_repository_service.auth_state import AuthState
from gateway_repository_service.capacity import (
    has_free_disk_admission,
    is_durable_root_writable,
)
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
from gateway_repository_service.diagnostics import log_event, operational_limits
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
from gateway_repository_service.versioned_import.faults import (
    ImportAdmissionFaultInjector,
    NoOpImportAdmissionFaultInjector,
)
from gateway_repository_service.versioned_import.locks import RepositoryLockRegistry
from gateway_repository_service.versioned_import.provider import CandidateAImportProvider
from gateway_repository_service.versioned_import.recovery import ImportStartupReconciler
from gateway_repository_service.versioned_import.store import ImportOperationStore
from gateway_repository_service.versioned_import.worker import (
    ImportWorkerPool,
    ImportWorkerShutdownError,
)
from gateway_repository_service.versioned_read.application import VersionedReadApplication
from gateway_repository_service.versioned_read.arrow_bridge import BRIDGE_REGISTRY, BridgeShutdownError
from gateway_repository_service.versioned_read.provider import CandidateAReadProvider

_LOGGER = logging.getLogger(__name__)


class ServiceStartupError(RuntimeError):
    """Raised when durable lifecycle initialization fails."""


class AdmissionDrainTimeoutError(RuntimeError):
    """Raised when upload/row-stream permits remain after shutdown drain grace."""

    def __init__(self, *, upload_in_use: int, row_stream_in_use: int) -> None:
        self.upload_in_use = upload_in_use
        self.row_stream_in_use = row_stream_in_use
        super().__init__(
            "admission permits still held after shutdown drain grace: "
            f"upload_in_use={upload_in_use} row_stream_in_use={row_stream_in_use}"
        )


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
    versioned_read_application: VersionedReadApplication
    dolt_runner: DoltRunner
    provider_gate: OfflineCliCapabilityGate
    auth_state: AuthState
    upload_admission: PermitPool = field(default_factory=lambda: PermitPool(8), repr=False)
    row_stream_admission: PermitPool = field(default_factory=lambda: PermitPool(8), repr=False)
    upload_inflight: InflightKeyGate = field(default_factory=InflightKeyGate, repr=False)
    upload_cancels: UploadCancelRegistry = field(
        default_factory=UploadCancelRegistry,
        repr=False,
    )
    artifact_cleaner: ArtifactCleanerLifecycle = field(
        default_factory=NoOpArtifactCleaner,
        repr=False,
    )
    admission_fault_injector: ImportAdmissionFaultInjector = field(
        default_factory=NoOpImportAdmissionFaultInjector,
        repr=False,
    )
    reconciliation_failures: tuple[str, ...] = ()
    consistency_watch: MutableConsistencyWatch = field(
        default_factory=MutableConsistencyWatch,
        repr=False,
    )
    _stopping: threading.Event = field(default_factory=threading.Event, repr=False)

    @classmethod
    def start(
        cls,
        settings: RepositoryServiceSettings,
        *,
        admission_fault_injector: ImportAdmissionFaultInjector | None = None,
        artifact_cleaner: ArtifactCleanerLifecycle | None = None,
    ) -> "ServiceRuntime":
        stack = ExitStack()
        try:
            bearer_token = settings.resolve_bearer_token()
            layout = DurableLayout.create_service(settings.data_root)
            root_lock = DurableRootLock(layout.service_lock)
            root_lock.acquire()

            def _release_root() -> None:
                if root_lock.is_held():
                    root_lock.release()

            stack.callback(_release_root)
            control_store = ControlStore.open(
                settings.control_db_path,
                expected_version=CONTROL_DB_USER_VERSION,
                busy_timeout_ms=settings.sqlite_busy_timeout_ms,
            )

            def _close_db() -> None:
                if control_store.is_open():
                    control_store.close()

            stack.callback(_close_db)
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
                import_store=import_store,
            ).reconcile()
            import_locks = RepositoryLockRegistry()
            provider_factory = cls._build_provider_factory(
                settings=settings,
                layout=layout,
                dolt_runner=dolt_runner,
            )
            import_reconciliation = ImportStartupReconciler(
                settings=settings,
                layout=layout,
                store=import_store,
                provider_factory=provider_factory,
            ).reconcile()
            if import_reconciliation.blocking_failures:
                raise ServiceStartupError(
                    "import startup recovery is blocked: "
                    + "; ".join(import_reconciliation.blocking_failures)
                )
            if not is_durable_root_writable(layout.service_state):
                raise ServiceStartupError("durable root is not writable")
            if artifact_cleaner is not None:
                cleaner = artifact_cleaner
            else:
                cleaner = ArtifactCleaner(
                    settings=settings,
                    layout=layout,
                    import_store=import_store,
                    mutation_store=mutation_store,
                )
            if isinstance(cleaner, ArtifactCleaner):
                cleaner.reclaim_until_disk_admission(
                    admitted=lambda: has_free_disk_admission(layout.root, settings),
                )
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
            stack.callback(
                lambda: import_worker_pool.stop(timeout=settings.import_shutdown_grace_seconds)
            )
            import_worker_pool.start()
            import_worker_pool.notify()
            read_provider_factory = cls._build_read_provider_factory(
                settings=settings,
                layout=layout,
                dolt_runner=dolt_runner,
            )
            versioned_read_application = VersionedReadApplication(
                mutation_store,
                layout,
                read_provider_factory,
            )
            upload_admission = PermitPool(settings.max_concurrent_uploads)
            row_stream_admission = PermitPool(settings.max_concurrent_row_streams)
            upload_inflight = InflightKeyGate()
            upload_cancels = UploadCancelRegistry()
            if isinstance(cleaner, ArtifactCleaner):
                cleaner.start()
                stack.callback(
                    lambda: cleaner.stop(timeout=settings.import_shutdown_grace_seconds)
                )
            import_worker_pool.set_lifecycle_notify(
                lambda: _notify_artifact_cleaner(cleaner)
            )
            stack.pop_all()
            runtime = cls(
                settings=settings,
                layout=layout,
                root_lock=root_lock,
                control_store=control_store,
                mutation_store=mutation_store,
                import_store=import_store,
                import_locks=import_locks,
                import_worker_pool=import_worker_pool,
                versioned_read_application=versioned_read_application,
                dolt_runner=dolt_runner,
                provider_gate=provider_gate,
                auth_state=AuthState(bearer_token=bearer_token),
                upload_admission=upload_admission,
                row_stream_admission=row_stream_admission,
                upload_inflight=upload_inflight,
                upload_cancels=upload_cancels,
                artifact_cleaner=cleaner,
                admission_fault_injector=admission_fault_injector or NoOpImportAdmissionFaultInjector(),
                reconciliation_failures=reconciliation.blocking_failures,
                consistency_watch=MutableConsistencyWatch.from_watch(reconciliation.consistency_watch),
                _stopping=stopping,
            )
            log_event(
                "runtime_start",
                result="started",
                capacity=upload_admission.capacity,
                in_use=0,
                extra_fields=operational_limits(settings),
                logger=_LOGGER,
            )
            return runtime
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

    @staticmethod
    def _build_read_provider_factory(
        *,
        settings: RepositoryServiceSettings,
        layout: DurableLayout,
        dolt_runner: DoltRunner,
    ) -> Callable[[UUID], CandidateAReadProvider]:
        def provider_factory(repository_id: UUID) -> CandidateAReadProvider:
            repository_path = layout.published_repository(repository_key(repository_id))
            return CandidateAReadProvider(
                settings,
                layout,
                repository_path,
                dolt_runner,
            )

        return provider_factory

    def shutdown(self) -> None:
        self._stopping.set()
        self.upload_admission.close()
        self.row_stream_admission.close()
        log_event(
            "runtime_shutdown",
            result="closing_admission",
            capacity=self.upload_admission.capacity,
            in_use=self.upload_admission.in_use,
            logger=_LOGGER,
        )
        self.upload_cancels.cancel_all()
        grace = self.settings.import_shutdown_grace_seconds
        cleanup_errors: list[Exception] = []
        bridge_shutdown_error: BridgeShutdownError | None = None
        cleaner_join_failed = False
        worker_join_failed = False

        if not self._wait_for_admission_drain(timeout=grace):
            log_event(
                "runtime_shutdown",
                result="drain_pending",
                capacity=self.upload_admission.capacity,
                in_use=self.upload_admission.in_use,
                logger=_LOGGER,
            )

        try:
            try:
                try:
                    self.import_worker_pool.begin_shutdown()
                    if not self.import_worker_pool.wait_for_quiescence(timeout=grace):
                        self.import_worker_pool.cancel_active_operations()
                        self.dolt_runner.terminate_active_children(grace_seconds=grace)
                except Exception as exc:
                    _LOGGER.exception("import worker pre-stop failed")
                    cleanup_errors.append(exc)
                finally:
                    try:
                        self.import_worker_pool.stop(timeout=grace * 2)
                    except ImportWorkerShutdownError as exc:
                        _LOGGER.exception("import worker pool join failed; retaining durable ownership")
                        cleanup_errors.append(exc)
                        worker_join_failed = True
                        self.dolt_runner.terminate_active_children(grace_seconds=grace)
                        try:
                            self.import_worker_pool.stop(timeout=grace)
                        except ImportWorkerShutdownError as retry_exc:
                            _LOGGER.exception("import worker pool still running after second stop")
                            cleanup_errors.append(retry_exc)
                            worker_join_failed = True
                        except Exception as retry_exc:
                            _LOGGER.exception("import worker pool second stop failed")
                            cleanup_errors.append(retry_exc)
                    except Exception:
                        _LOGGER.exception("import worker pool did not stop cleanly")
                        self.dolt_runner.terminate_active_children(grace_seconds=grace)
                        try:
                            self.import_worker_pool.stop(timeout=grace)
                        except ImportWorkerShutdownError as exc:
                            _LOGGER.exception("import worker pool still running after second stop")
                            cleanup_errors.append(exc)
                            worker_join_failed = True
                        except Exception as exc:
                            _LOGGER.exception("import worker pool still running after second stop")
                            cleanup_errors.append(exc)
            except Exception as exc:
                _LOGGER.exception("import worker shutdown failed")
                cleanup_errors.append(exc)

            try:
                self.artifact_cleaner.stop(timeout=grace)
            except ArtifactCleanerShutdownError as exc:
                _LOGGER.exception("artifact cleaner join failed; retaining durable ownership")
                cleanup_errors.append(exc)
                cleaner_join_failed = True
            except Exception as exc:
                _LOGGER.exception("artifact cleaner stop failed")
                cleanup_errors.append(exc)
        finally:
            try:
                BRIDGE_REGISTRY.close_all(
                    self.dolt_runner,
                    join_timeout_seconds=grace,
                )
            except BridgeShutdownError as exc:
                bridge_shutdown_error = exc
            except Exception as exc:
                _LOGGER.exception("bridge registry close_all failed")
                cleanup_errors.append(exc)

            drained = self._wait_for_admission_drain(timeout=grace)
            upload_snap = self.upload_admission.snapshot()
            row_snap = self.row_stream_admission.snapshot()
            retain_ownership = (
                cleaner_join_failed
                or worker_join_failed
                or not drained
                or upload_snap.in_use != 0
                or row_snap.in_use != 0
            )
            if retain_ownership:
                if cleaner_join_failed:
                    result = "cleaner_join_failed"
                    cleanup_outcome = "cleaner_alive_after_join_timeout"
                elif worker_join_failed:
                    result = "worker_join_failed"
                    cleanup_outcome = "worker_alive_after_join_timeout"
                else:
                    result = "permit_leak"
                    cleanup_outcome = "permit_in_use_after_drain_wait"
                log_event(
                    "runtime_shutdown",
                    result=result,
                    capacity=upload_snap.capacity,
                    in_use=upload_snap.in_use + row_snap.in_use,
                    cleanup_outcome=cleanup_outcome,
                    logger=_LOGGER,
                )
                if not cleaner_join_failed and not worker_join_failed:
                    drain_error = AdmissionDrainTimeoutError(
                        upload_in_use=upload_snap.in_use,
                        row_stream_in_use=row_snap.in_use,
                    )
                    cleanup_errors.append(drain_error)
                log_event(
                    "runtime_shutdown",
                    result="stopped",
                    capacity=upload_snap.capacity,
                    in_use=upload_snap.in_use + row_snap.in_use,
                    cleanup_outcome="durable_retained",
                    logger=_LOGGER,
                )
            else:
                try:
                    if self.control_store.is_open():
                        self.control_store.close()
                except Exception as exc:
                    _LOGGER.exception("control store close failed")
                    cleanup_errors.append(exc)
                finally:
                    try:
                        if self.root_lock.is_held():
                            self.root_lock.release()
                    except Exception as exc:
                        _LOGGER.exception("root lock release failed")
                        cleanup_errors.append(exc)

                log_event(
                    "runtime_shutdown",
                    result="stopped",
                    capacity=upload_snap.capacity,
                    in_use=self.upload_admission.in_use + self.row_stream_admission.in_use,
                    cleanup_outcome="durable_released",
                    logger=_LOGGER,
                )

            if bridge_shutdown_error is not None:
                if cleanup_errors:
                    raise ExceptionGroup(
                        "runtime shutdown cleanup failures",
                        [bridge_shutdown_error, *cleanup_errors],
                    ) from bridge_shutdown_error
                raise bridge_shutdown_error
            if cleanup_errors:
                if len(cleanup_errors) == 1:
                    raise cleanup_errors[0]
                raise ExceptionGroup("runtime shutdown cleanup failures", cleanup_errors)

    def _wait_for_admission_drain(self, *, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.upload_admission.in_use == 0 and self.row_stream_admission.in_use == 0:
                return True
            time.sleep(0.01)
        return self.upload_admission.in_use == 0 and self.row_stream_admission.in_use == 0

    def is_accepting_import_effects(self) -> bool:
        return not self._stopping.is_set()

    def is_stopping(self) -> bool:
        return self._stopping.is_set()

    def register_succeeded_create(self, repository_id: UUID) -> None:
        self.consistency_watch.register_succeeded_create(repository_id)

    def register_succeeded_upload(
        self,
        repository_id: UUID,
        artifact_id: UUID,
        size_bytes: int,
    ) -> None:
        self.consistency_watch.register_succeeded_upload(repository_id, artifact_id, size_bytes)
        self.notify_artifact_lifecycle()

    def notify_artifact_lifecycle(self) -> None:
        _notify_artifact_cleaner(self.artifact_cleaner)

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
                ttl_seconds=self.settings.artifact_ttl_seconds,
                forget=self.consistency_watch,
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


def _notify_artifact_cleaner(cleaner: ArtifactCleanerLifecycle) -> None:
    notify = getattr(cleaner, "notify", None)
    if callable(notify):
        notify()
