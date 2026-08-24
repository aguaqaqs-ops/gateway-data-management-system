"""Module entrypoint and concrete composition for the operation worker."""

from __future__ import annotations

import logging
import signal
import threading
import time
from dataclasses import dataclass
from signal import Signals
from types import FrameType
from typing import Callable, cast

from pydantic import ValidationError

from gateway_backend.infrastructure.control_db import (
    ControlDbUnitOfWork,
    initialize_control_db,
)
from gateway_backend.operations import OperationRecord, OperationUnitOfWork, StepRecord
from gateway_backend.operations.worker import (
    ClaimedWork,
    StartupDisposition,
    WorkerEvent,
    WorkerEventCode,
    WorkerObserver,
)
from gateway_backend.operations.worker_lifecycle import WorkerLifecycleController
from gateway_backend.operations.worker_runtime import WorkerRuntime
from gateway_backend.operations.worker_startup import WorkerStartup
from gateway_backend.settings import OperationWorkerSettings

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EmptyWorkerRegistry:
    """Immutable pre-R4 registry; runnable records fail closed at startup."""

    def resolve(self, key: object) -> None:
        del key
        return None


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


def bootstrap_control_database(settings: OperationWorkerSettings) -> None:
    """Create only the configured DB parent, then initialize the control schema."""

    if type(settings) is not OperationWorkerSettings:
        raise ValueError("settings must be OperationWorkerSettings")
    parent = settings.control_db_path.parent
    parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    if not parent.is_dir():
        raise ValueError("control DB parent is not a directory")
    initialize_control_db(settings.control_db_path)


def build_worker_runtime(
    settings: OperationWorkerSettings,
    *,
    observer: WorkerObserver = _observe_event,
    monotonic: Callable[[], float] = time.monotonic,
) -> WorkerRuntime:
    """Compose the SQLite-backed worker while keeping policy ports empty/fail-closed."""

    if type(settings) is not OperationWorkerSettings:
        raise ValueError("settings must be OperationWorkerSettings")
    if not callable(observer):
        raise ValueError("observer must be callable")
    if not callable(monotonic):
        raise ValueError("monotonic must be callable")

    def read_uow_factory() -> OperationUnitOfWork:
        return ControlDbUnitOfWork(settings.control_db_path, read_only=True)

    def write_uow_factory() -> OperationUnitOfWork:
        return ControlDbUnitOfWork(settings.control_db_path)

    startup_observer = _StartupObserver(observer)
    startup = WorkerStartup(
        read_uow_factory=read_uow_factory,
        write_uow_factory=write_uow_factory,
        registry=EmptyWorkerRegistry(),
        recovery_hook=_fail_closed_recovery,
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
        write_uow_factory=write_uow_factory,
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
        # control_db_path is intentionally required and is normally supplied by the env prefix.
        configured = settings if settings is not None else OperationWorkerSettings()  # type: ignore[call-arg]
        previous_handlers = _install_signal_handlers(stop_requested)
        bootstrap_control_database(configured)
        runtime = build_worker_runtime(configured)
        runtime.run(stop_requested.is_set, stop_requested.wait)
    except ValidationError:
        _LOGGER.error("operation_worker_failed category=settings_invalid")
        return 1
    except Exception as exc:
        _LOGGER.error("operation_worker_failed category=%s", _failure_category(exc))
        return 1
    finally:
        if previous_handlers is not None:
            _restore_signal_handlers(previous_handlers)
    return 0


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
    if isinstance(error, TimeoutError):
        return "startup_timeout"
    return "worker_failure"


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "EmptyWorkerRegistry",
    "bootstrap_control_database",
    "build_worker_runtime",
    "main",
    "run",
]
