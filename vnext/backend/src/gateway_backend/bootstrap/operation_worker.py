"""Module entrypoint and concrete composition for the operation worker."""

from __future__ import annotations

import logging
import signal
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from signal import Signals
from types import FrameType
from typing import Any, cast
from uuid import uuid4

from pydantic import ValidationError

from gateway_backend.artifacts import ArtifactRefLookupPort
from gateway_backend.application.job_definitions import (
    JobDefinition,
    JobDefinitionRegistry,
    JobWorkerComposition,
    build_job_worker_composition,
    validate_active_pairs_job_contract_versions,
)
from gateway_backend.application.recovery import RecoveryCapability, RecoveryPort
from gateway_backend.application.payloads import PayloadDecodeError, PayloadDecoder
from gateway_backend.application.history.compare_jobs import (
    HistoryCompareControlTransactionFactory,
    HistoryCompareRuntimeDependencies,
    history_compare_composition_bundle,
)
from gateway_backend.application.preview_jobs import (
    PREVIEW_JOB_KIND,
    PreviewRuntimeDependencies,
    RepositoryProviderFactory,
    bind_control_transaction_factory,
    build_preview_recovery_port,
    preview_composition_bundle,
)
from gateway_backend.application.canonical_metadata.manifest_reader import (
    ArtifactBackedCanonicalizationManifestReader,
)
from gateway_backend.application.submit_jobs import (
    SubmitRuntimeDependencies,
    bind_submit_control_transaction_factory,
    build_submit_recovery_port,
    submit_composition_bundle,
)
from gateway_backend.application.submit_jobs import SubmitControlTransactionFactory
from gateway_backend.application.submission.job_payload import SUBMIT_JOB_KIND
from gateway_backend.infrastructure.artifact_store import (
    BoundedArtifactStore,
    LocalArtifactStore,
    validate_artifact_root,
)
from gateway_backend.infrastructure.control_db import (
    ControlDbIntegrityError,
    ControlDbUnitOfWork,
    initialize_and_verify_control_db,
)
from gateway_backend.infrastructure.control_db.sqlite_mapping import (
    ProvisionedBaselineHeadRead,
    seed_provisioned_mappings,
)
from gateway_backend.infrastructure.repository_read import (
    build_http_repository_provider_factory,
    HttpRepositoryParentCatalogPort,
    load_repository_bearer_token,
)
from gateway_backend.infrastructure.repository_write import HttpRepositoryWriteClient
from gateway_backend.infrastructure.repository_write.terminal_evidence_codec import (
    WireRepositoryTerminalEvidenceDecodePort,
)
from gateway_backend.bootstrap.composition import build_submit_import_publication_port
from gateway_backend.operations import OperationRecord, OperationUnitOfWork, StepRecord
from gateway_backend.operations.contracts import JobStepKey
from gateway_backend.operations.recovery import (
    HandlerRecoveryCallback,
    HandlerRecoveryResult,
    RecoveryCapabilityValue,
    RecoveryPolicyOutcomeDisposition,
    StartupRecovery,
    build_recovery_routed_executor,
    build_startup_recovery,
)
from gateway_backend.operations.contracts import validate_opaque_id
from gateway_backend.operations.persistence import OperationLifecycleActions
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ClaimedWork,
    ReadUnitOfWorkFactory,
    RecoveryHook,
    StartupDisposition,
    WorkerEvent,
    WorkerEventCode,
    WorkerObserver,
    WorkerRegistry,
    WriteUnitOfWorkFactory,
)
from gateway_backend.operations.worker_lifecycle import WorkerLifecycleController
from gateway_backend.operations.worker_runtime import WorkerRuntime
from gateway_backend.operations.worker_startup import WorkerStartup
from gateway_backend.settings import OperationWorkerSettings

_LOGGER = logging.getLogger(__name__)


def _observe_event(event: WorkerEvent) -> None:
    """Write only bounded event fields; lease tokens and paths never enter logs."""

    _LOGGER.info(
        "operation_worker_event code=%s operation_id=%s step_id=%s worker_id=%s "
        "attempt=%s error_category=%s",
        event.code.value,
        event.operation_id or "-",
        event.step_id or "-",
        event.worker_id or "-",
        event.attempt if event.attempt is not None else "-",
        event.error_category or "-",
    )


def build_job_worker_composition_for_settings(
    settings: OperationWorkerSettings,
    *,
    definitions: tuple[JobDefinition, ...] = (),
    handlers: Mapping[str, ClaimedExecutor] | None = None,
    payload_decoders: Mapping[str, PayloadDecoder] | None = None,
) -> JobWorkerComposition:
    """Build the immutable R4 composition for one worker process."""

    if type(settings) is not OperationWorkerSettings:
        raise ValueError("settings must be OperationWorkerSettings")
    if type(definitions) is not tuple:
        raise ValueError("definitions must be a tuple")
    bound_handlers = {} if handlers is None else dict(handlers)
    bound_decoders = {} if payload_decoders is None else dict(payload_decoders)
    local_store = LocalArtifactStore(settings.artifact_root)
    artifact_store = BoundedArtifactStore(
        local_store,
        is_protected=lambda artifact_id: _artifact_is_protected(settings.control_db_path, artifact_id),
        unpinned_ttl=timedelta(hours=24),
    )
    return build_job_worker_composition(
        definitions,
        bound_handlers,
        artifact_store=artifact_store,
        decoders=bound_decoders,
    )


def build_production_preview_dependencies(
    settings: OperationWorkerSettings,
) -> tuple[PreviewRuntimeDependencies, WriteUnitOfWorkFactory]:
    """Compose production Preview ports: Bounded store, HTTP/Arrow adapter, mapping Head."""

    validate_artifact_root(settings.artifact_root)
    token = load_repository_bearer_token(settings.repository_bearer_token_file)
    bootstrap_control_database(settings)
    seed_provisioned_mappings(settings.control_db_path, settings.provisioned_mapping_file)
    local_store = LocalArtifactStore(settings.artifact_root)
    artifact_store = BoundedArtifactStore(
        local_store,
        is_protected=lambda artifact_id: _artifact_is_protected(settings.control_db_path, artifact_id),
        unpinned_ttl=timedelta(hours=24),
    )
    manifest_reader = ArtifactBackedCanonicalizationManifestReader(
        artifact_store=artifact_store,
        artifact_refs=artifact_store,
    )

    def control_transaction_factory() -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(
            settings.control_db_path,
            canonicalization_manifest_reader=manifest_reader,
        )

    preview_deps = PreviewRuntimeDependencies(
        artifact_store=artifact_store,
        repository_provider_factory=cast(
            RepositoryProviderFactory,
            build_http_repository_provider_factory(
                base_url=settings.repository_base_url,
                bearer_token=token,
                timeout_seconds=settings.repository_timeout_seconds,
            ),
        ),
        baseline_head_read=ProvisionedBaselineHeadRead(settings.control_db_path),
        control_transaction_factory=control_transaction_factory,
    )
    write_uow_factory = build_worker_write_uow_factory(control_transaction_factory)
    return preview_deps, write_uow_factory


def build_worker_write_uow_factory(
    control_transaction_factory: Callable[[], ControlDbUnitOfWork],
) -> WriteUnitOfWorkFactory:
    """Stack preview and submit transaction binders."""

    preview_bound = bind_control_transaction_factory(control_transaction_factory)
    return cast(
        WriteUnitOfWorkFactory,
        bind_submit_control_transaction_factory(
            cast(SubmitControlTransactionFactory, preview_bound)
        ),
    )


def build_production_submit_dependencies(
    settings: OperationWorkerSettings,
    *,
    preview_deps: PreviewRuntimeDependencies,
) -> SubmitRuntimeDependencies:
    """Compose production Submit ports on top of the shared Preview artifact store."""

    if type(settings) is not OperationWorkerSettings:
        raise ValueError("settings must be OperationWorkerSettings")
    if type(preview_deps) is not PreviewRuntimeDependencies:
        raise ValueError("preview_deps must be PreviewRuntimeDependencies")

    token = load_repository_bearer_token(settings.repository_bearer_token_file)
    manifest_reader = ArtifactBackedCanonicalizationManifestReader(
        artifact_store=preview_deps.artifact_store,
        artifact_refs=cast(ArtifactRefLookupPort, preview_deps.artifact_store),
    )

    def control_transaction_factory() -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(
            settings.control_db_path,
            canonicalization_manifest_reader=manifest_reader,
        )

    def submission_id_factory() -> str:
        return f"sub-{uuid4()}"

    return SubmitRuntimeDependencies(
        artifact_store=preview_deps.artifact_store,
        publication=build_submit_import_publication_port(
            repository_provider_factory=preview_deps.repository_provider_factory,
        ),
        parent_catalog=HttpRepositoryParentCatalogPort(
            base_url=settings.repository_base_url,
            bearer_token=token,
            timeout_seconds=settings.repository_timeout_seconds,
        ),
        repository_write=HttpRepositoryWriteClient(
            base_url=settings.repository_base_url,
            bearer_token=token,
            timeout_seconds=settings.repository_timeout_seconds,
        ),
        terminal_evidence_decode=WireRepositoryTerminalEvidenceDecodePort(),
        control_transaction_factory=control_transaction_factory,
        submission_id_factory=submission_id_factory,
    )


def _artifact_is_protected(db_path: Path, artifact_id: str) -> bool:
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        return unit_of_work.protection.is_protected(artifact_id)


def bootstrap_control_database(settings: OperationWorkerSettings) -> None:
    """Create only the configured DB parent, then initialize the control schema."""

    if type(settings) is not OperationWorkerSettings:
        raise ValueError("settings must be OperationWorkerSettings")
    parent = settings.control_db_path.parent
    parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    if not parent.is_dir():
        raise ValueError("control DB parent is not a directory")
    initialize_and_verify_control_db(settings.control_db_path)


def build_worker_runtime(
    settings: OperationWorkerSettings,
    *,
    observer: WorkerObserver = _observe_event,
    monotonic: Callable[[], float] = time.monotonic,
    job_definitions: tuple[JobDefinition, ...] = (),
    handlers: Mapping[str, ClaimedExecutor] | None = None,
    payload_decoders: Mapping[str, PayloadDecoder] | None = None,
    external_effect_recovery: RecoveryPort | None = None,
    preview_recovery: RecoveryPort | None = None,
    submit_recovery: RecoveryPort | None = None,
    write_uow_factory: WriteUnitOfWorkFactory | None = None,
    read_uow_factory: WriteUnitOfWorkFactory | None = None,
    now_factory: Callable[[], datetime] | None = None,
) -> WorkerRuntime:
    """Compose the SQLite-backed worker with the immutable R4 registry adapter."""

    if type(settings) is not OperationWorkerSettings:
        raise ValueError("settings must be OperationWorkerSettings")
    if not callable(observer):
        raise ValueError("observer must be callable")
    if not callable(monotonic):
        raise ValueError("monotonic must be callable")
    if type(job_definitions) is not tuple:
        raise ValueError("job_definitions must be a tuple")

    composition = build_job_worker_composition_for_settings(
        settings,
        definitions=job_definitions,
        handlers=handlers,
        payload_decoders=payload_decoders,
    )

    def default_read_uow_factory() -> OperationUnitOfWork:
        return ControlDbUnitOfWork(settings.control_db_path, read_only=True)

    def default_write_uow_factory() -> OperationUnitOfWork:
        return ControlDbUnitOfWork(settings.control_db_path)

    resolved_read_uow_factory = read_uow_factory or default_read_uow_factory
    resolved_write_uow_factory = write_uow_factory or default_write_uow_factory

    startup_observer = _StartupObserver(observer)
    jitter = _deterministic_jitter
    resolved_now_factory = now_factory or _utc_now_factory

    def capability_lookup(job_kind: str, step_name: str) -> RecoveryCapabilityValue:
        definition = composition.definition_registry.get(
            JobStepKey(job_kind=job_kind, step_name=step_name)
        )
        return RecoveryCapabilityValue(definition.recovery_capability.value)

    startup_recovery = build_startup_recovery(
        write_uow_factory=resolved_write_uow_factory,
        capability_lookup=capability_lookup,
        jitter=jitter,
        now_factory=resolved_now_factory,
    )
    recovery_registry = _build_recovery_aware_registry(
        composition,
        jitter=jitter,
        now_factory=resolved_now_factory,
        external_effect_recovery=external_effect_recovery,
        preview_recovery=preview_recovery,
        submit_recovery=submit_recovery,
    )
    startup = _R4WorkerStartup(
        read_uow_factory=resolved_read_uow_factory,
        write_uow_factory=resolved_write_uow_factory,
        registry=recovery_registry,
        definition_registry=composition.definition_registry,
        recovery_hook=_fail_closed_recovery,
        startup_recovery=startup_recovery,
        observer=startup_observer,
    )
    bounded_startup = _StartupBudget(
        startup,
        monotonic=monotonic,
        budget=settings.startup_retry_budget_seconds,
        observer=observer,
        startup_observer=startup_observer,
    )
    lifecycle = WorkerLifecycleController(
        monotonic=monotonic,
        drain_timeout=settings.graceful_drain_timeout_seconds,
    )
    return WorkerRuntime(
        startup=cast(WorkerStartup, bounded_startup),
        write_uow_factory=resolved_write_uow_factory,
        observer=observer,
        lifecycle=lifecycle,
        monotonic=monotonic,
        heartbeat_interval=settings.heartbeat_interval_seconds,
        lease_duration=settings.lease_duration_seconds,
        idle_poll=settings.idle_claim_poll_seconds,
        busy_backoff_min=settings.transient_backoff_initial_seconds,
        busy_backoff_max=settings.transient_backoff_max_seconds,
    )


def run(settings: OperationWorkerSettings | None = None) -> int:
    """Run the worker process and return zero only after a clean local drain."""

    stop_requested = threading.Event()
    previous_handlers: tuple[object, object] | None = None
    try:
        try:
            # Required paths and repository settings are normally supplied by the env prefix.
            configured = settings if settings is not None else OperationWorkerSettings()  # type: ignore[call-arg]
            previous_handlers = _install_signal_handlers(stop_requested)
            from gateway_backend.bootstrap.composition import (
                assert_workspace_registry_ready,
                build_workspace_job_registry,
            )

            assert_workspace_registry_ready(build_workspace_job_registry())
            preview_deps, submit_write_uow_factory = build_production_preview_dependencies(configured)
            submit_deps = build_production_submit_dependencies(configured, preview_deps=preview_deps)
            history_compare_deps = HistoryCompareRuntimeDependencies(
                artifact_store=preview_deps.artifact_store,
                repository_provider_factory=preview_deps.repository_provider_factory,
                control_transaction_factory=cast(
                    HistoryCompareControlTransactionFactory,
                    submit_write_uow_factory,
                ),
            )
            preview_definitions, preview_handlers, preview_decoders = preview_composition_bundle(
                preview_deps
            )
            submit_definitions, submit_handlers, submit_decoders, bound_submit_deps = (
                submit_composition_bundle(submit_deps)
            )
            history_definitions, history_handlers, history_decoders, bound_history_deps = (
                history_compare_composition_bundle(history_compare_deps)
            )
            write_uow_factory = cast(
                WriteUnitOfWorkFactory,
                bound_history_deps.control_transaction_factory,
            )
            runtime = build_worker_runtime(
                configured,
                job_definitions=preview_definitions + submit_definitions + history_definitions,
                handlers={**preview_handlers, **submit_handlers, **history_handlers},
                payload_decoders={**preview_decoders, **submit_decoders, **history_decoders},
                preview_recovery=build_preview_recovery_port(preview_deps),
                submit_recovery=build_submit_recovery_port(bound_submit_deps),
                write_uow_factory=write_uow_factory,
            )
        except ValidationError:
            _LOGGER.error("operation_worker_failed category=settings_invalid")
            return 1
        except ControlDbIntegrityError:
            _LOGGER.error("operation_worker_failed category=control_db_integrity")
            return 1
        except ValueError:
            _LOGGER.error("operation_worker_failed category=settings_invalid")
            return 1
        except Exception as exc:
            _LOGGER.error(
                "operation_worker_failed category=%s type=%s message=%s",
                _failure_category(exc),
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return 1
        try:
            runtime.run(stop_requested.is_set, stop_requested.wait)
        except Exception as exc:
            _LOGGER.error(
                "operation_worker_failed category=%s type=%s message=%s",
                _failure_category(exc),
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return 1
        return 0
    finally:
        if previous_handlers is not None:
            _restore_signal_handlers(previous_handlers)


def main() -> int:
    """Console-free module entrypoint used by the source-based backend image."""

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return run()


def _fail_closed_recovery(
    operation: OperationRecord,
    step: StepRecord,
) -> StartupDisposition:
    del operation, step
    return StartupDisposition.FATAL_BLOCK


def _deterministic_jitter(lower: float, _upper: float) -> float:
    return lower


def _utc_now_factory() -> datetime:
    return datetime.now(UTC)


def _adapt_recovery_port(port: RecoveryPort) -> HandlerRecoveryCallback:
    def recover(
        operation: OperationRecord,
        step: StepRecord,
        control: object,
        lease_session: object,
    ) -> HandlerRecoveryResult:
        outcome = port.recover(
            operation,
            step,
            cast(Any, control),
            cast(Any, lease_session),
        )
        return HandlerRecoveryResult(
            disposition=RecoveryPolicyOutcomeDisposition(outcome.disposition.value),
            diagnostic_code=outcome.diagnostic_code,
            reason=outcome.reason,
        )

    return recover


def _build_recovery_callbacks(
    composition: JobWorkerComposition,
    *,
    external_effect_recovery: RecoveryPort | None,
    now_factory: Callable[[], datetime],
    preview_recovery: RecoveryPort | None,
    submit_recovery: RecoveryPort | None,
) -> dict[JobStepKey, HandlerRecoveryCallback | None]:
    callbacks: dict[JobStepKey, HandlerRecoveryCallback | None] = {}
    for definition in composition.definition_registry.definitions():
        if (
            submit_recovery is not None
            and definition.key.job_kind == SUBMIT_JOB_KIND
            and definition.recovery_capability is RecoveryCapability.EXTERNAL_EFFECT
        ):
            callbacks[definition.key] = _adapt_recovery_port(submit_recovery)
        elif (
            external_effect_recovery is not None
            and definition.recovery_capability is RecoveryCapability.EXTERNAL_EFFECT
            and definition.key.job_kind != SUBMIT_JOB_KIND
        ):
            callbacks[definition.key] = _adapt_recovery_port(external_effect_recovery)
        elif preview_recovery is not None and definition.key.job_kind == PREVIEW_JOB_KIND:
            callbacks[definition.key] = _adapt_recovery_port(preview_recovery)
        else:
            callbacks[definition.key] = None
    return callbacks


@dataclass(frozen=True, slots=True)
class _RecoveryAwareWorkerRegistry:
    """Wrap resolved executors with claim-path recovery routing at the JobStepKey boundary."""

    _registry: WorkerRegistry
    _definition_registry: JobDefinitionRegistry
    _recovery_by_key: Mapping[JobStepKey, HandlerRecoveryCallback | None]
    _jitter: Callable[[float, float], float]
    _now_factory: Callable[[], datetime]

    def resolve(self, key: JobStepKey) -> ClaimedExecutor | None:
        executor = self._registry.resolve(key)
        if executor is None:
            return None
        definition = self._definition_registry.get(key)
        capability = RecoveryCapabilityValue(definition.recovery_capability.value)
        recovery = self._recovery_by_key.get(key)
        return build_recovery_routed_executor(
            executor,
            recovery,
            capability,
            jitter=self._jitter,
            now_factory=self._now_factory,
        )


def _build_recovery_aware_registry(
    composition: JobWorkerComposition,
    *,
    jitter: Callable[[float, float], float],
    now_factory: Callable[[], datetime],
    external_effect_recovery: RecoveryPort | None = None,
    preview_recovery: RecoveryPort | None = None,
    submit_recovery: RecoveryPort | None = None,
) -> WorkerRegistry:
    recovery_by_key = _build_recovery_callbacks(
        composition,
        external_effect_recovery=external_effect_recovery,
        now_factory=now_factory,
        preview_recovery=preview_recovery,
        submit_recovery=submit_recovery,
    )
    return _RecoveryAwareWorkerRegistry(
        _registry=composition.worker_registry,
        _definition_registry=composition.definition_registry,
        _recovery_by_key=recovery_by_key,
        _jitter=jitter,
        _now_factory=now_factory,
    )


class _R4WorkerStartup(WorkerStartup):
    """Extend startup validation with job_contract_version coverage before claim."""

    __slots__ = ("_definition_registry",)

    def __init__(
        self,
        *,
        read_uow_factory: ReadUnitOfWorkFactory,
        write_uow_factory: WriteUnitOfWorkFactory,
        registry: WorkerRegistry,
        definition_registry: JobDefinitionRegistry,
        recovery_hook: RecoveryHook,
        observer: WorkerObserver,
        startup_recovery: StartupRecovery | None = None,
        worker_id_factory: Callable[[], str] | None = None,
        lease_token_factory: Callable[[], str] | None = None,
        page_limit: int | None = None,
    ) -> None:
        init_kwargs: dict[str, object] = {
            "read_uow_factory": read_uow_factory,
            "write_uow_factory": write_uow_factory,
            "registry": registry,
            "recovery_hook": recovery_hook,
            "observer": observer,
        }
        if startup_recovery is not None:
            init_kwargs["startup_recovery"] = startup_recovery
        if worker_id_factory is not None:
            init_kwargs["worker_id_factory"] = worker_id_factory
        if lease_token_factory is not None:
            init_kwargs["lease_token_factory"] = lease_token_factory
        if page_limit is not None:
            init_kwargs["page_limit"] = page_limit
        super().__init__(**init_kwargs)  # type: ignore[arg-type]
        if type(definition_registry) is not JobDefinitionRegistry:
            raise ValueError("definition_registry must be JobDefinitionRegistry")
        self._definition_registry = definition_registry

    def _validate_topology_and_registry(self) -> Any:
        pairs = super()._validate_topology_and_registry()
        validate_active_pairs_job_contract_versions(
            self._definition_registry,
            ((pair.operation, pair.step) for pair in pairs),
        )
        return pairs

    def claim_one(self) -> ClaimedWork | None:
        if not self._ready:
            raise ValueError("worker startup gate has not reached READY")

        with self._write_uow_factory() as unit_of_work:
            store = unit_of_work.operations
            transaction_now = store.transaction_now
            candidates, _ = store.list_claim_candidates(
                transaction_now,
                limit=1,
            )
            if not candidates:
                return None

            candidate = candidates[0]
            operation = store.get_operation(candidate.operation_id)
            step = store.get_step(candidate.step_id)
            validate_active_pairs_job_contract_versions(
                self._definition_registry,
                ((operation, step),),
            )
            executor = self._resolve_executor(candidate.job_step_key)
            lease_token = self._lease_token_factory()
            validate_opaque_id(lease_token, "lease_token")
            claimed = OperationLifecycleActions(
                store,
                transaction_now=transaction_now,
            ).claim_one(self._worker_id, lease_token)
            if claimed is None:
                raise ValueError("claim candidate disappeared inside the write transaction")

            claimed_operation, claimed_step = claimed
            self._assert_claim_identity(
                candidate,
                claimed_operation,
                claimed_step,
                lease_token,
            )
            work = ClaimedWork(
                operation=claimed_operation,
                step=claimed_step,
                executor=executor,
            )

        self._observer(
            WorkerEvent(
                code=WorkerEventCode.CLAIM_SUCCEEDED,
                operation_id=work.operation.operation_id,
                step_id=work.step.step_id,
                worker_id=self._worker_id,
                attempt=work.step.attempt_count,
            )
        )
        return work


def _install_signal_handlers(
    stop_requested: threading.Event,
) -> tuple[object, object]:
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("operation worker signal handlers require the main thread")

    def request_drain(signum: int, frame: FrameType | None) -> None:
        del signum, frame
        stop_requested.set()

    previous_term = signal.signal(Signals.SIGTERM, request_drain)
    try:
        previous_int = signal.signal(Signals.SIGINT, request_drain)
    except BaseException:
        signal.signal(Signals.SIGTERM, cast(Callable[[int, FrameType | None], object], previous_term))
        raise
    return previous_term, previous_int


def _restore_signal_handlers(previous: tuple[object, object]) -> None:
    previous_term, previous_int = previous
    signal.signal(
        Signals.SIGTERM,
        cast(Callable[[int, FrameType | None], object], previous_term),
    )
    signal.signal(
        Signals.SIGINT,
        cast(Callable[[int, FrameType | None], object], previous_int),
    )


class _StartupBudget:
    """Bound retryable startup blocking without changing the Operations runtime port."""

    __slots__ = (
        "_delegate",
        "_deadline",
        "_monotonic",
        "_observer",
        "_startup_observer",
    )

    def __init__(
        self,
        delegate: WorkerStartup,
        *,
        monotonic: Callable[[], float],
        budget: float,
        observer: WorkerObserver,
        startup_observer: _StartupObserver,
    ) -> None:
        self._delegate = delegate
        self._deadline = monotonic() + budget
        self._monotonic = monotonic
        self._observer = observer
        self._startup_observer = startup_observer

    def startup(self) -> StartupDisposition:
        self._startup_observer.discard_ready()
        if self._monotonic() >= self._deadline:
            self._emit_timeout()
            return StartupDisposition.FATAL_BLOCK
        disposition = self._delegate.startup()
        if disposition is StartupDisposition.READY:
            if self._monotonic() >= self._deadline:
                self._startup_observer.discard_ready()
                self._emit_timeout()
                return StartupDisposition.FATAL_BLOCK
            self._startup_observer.publish_ready()
        return disposition

    def claim_one(self) -> ClaimedWork | None:
        return self._delegate.claim_one()

    def _emit_timeout(self) -> None:
        self._observer(
            WorkerEvent(
                code=WorkerEventCode.STARTUP_FAILED,
                error_category="startup_timeout",
            )
        )


class _StartupObserver:
    """Buffer only READY until the outer monotonic startup budget accepts it."""

    __slots__ = ("_observer", "_ready_event")

    def __init__(self, observer: WorkerObserver) -> None:
        self._observer = observer
        self._ready_event: WorkerEvent | None = None

    def __call__(self, event: WorkerEvent) -> None:
        if event.code is WorkerEventCode.WORKER_READY:
            self._ready_event = event
            return
        self._observer(event)

    def discard_ready(self) -> None:
        self._ready_event = None

    def publish_ready(self) -> None:
        event = self._ready_event
        self._ready_event = None
        if event is not None:
            self._observer(event)


def _failure_category(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "settings_invalid"
    if isinstance(error, PayloadDecodeError):
        return "payload_decode_failed"
    if isinstance(error, TimeoutError):
        return "startup_timeout"
    return "worker_failure"


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "bootstrap_control_database",
    "build_job_worker_composition_for_settings",
    "build_worker_runtime",
    "main",
    "run",
]
