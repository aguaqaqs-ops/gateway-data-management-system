"""HTTP dependency container and admission gate."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from fastapi import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from gateway_backend.application.job_definitions import JobDefinitionRegistry
from gateway_backend.application.submission.ports import (
    BaselineCanonicalDigestPort,
    RepositoryMainResolvePort,
    WorkspaceControlUnitOfWorkFactory,
)
from gateway_backend.artifacts.bounded_store import BoundedArtifactStorePort
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.submission.models import SubmitAttempt, Submission
from gateway_backend.domain.workspace.models import BaselineHead, InputCompleteness
from gateway_backend.application.workspace.ports import (
    BaselineHeadReadPort,
    ScopeResolutionPort,
    WorkspaceRepository,
)
from gateway_backend.application.control_transactions import ControlDbUnitOfWorkFactory
from gateway_backend.application.history.ports import HistoryControlUnitOfWorkFactory, HistorySnapshotLoaderPort
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.errors import ApiError
from gateway_backend.operations.contracts import OperationRecord, StepRecord
from gateway_backend.operations.recovery import OperatorRecoveryRequest
from gateway_backend.operations.state import TransitionDisposition
from gateway_backend.operations.store import RecordNotFound

if TYPE_CHECKING:
    from gateway_backend.http.auth import InternalBearerPort, SessionPort


class _FailClosedInternalBearerPort:
    def verify(self, request: Request) -> None:
        del request
        raise ApiError(
            code="AUTHENTICATION_REQUIRED",
            message="authentication required",
            status_code=401,
        )


def _default_internal_bearer_port() -> InternalBearerPort:
    return _FailClosedInternalBearerPort()


@runtime_checkable
class OperationReaderPort(Protocol):
    def get_operation(self, operation_id: str) -> OperationRecord:
        """Return an operation or raise RecordNotFound."""

    def get_step(self, step_id: str) -> StepRecord:
        """Return a step or raise RecordNotFound."""


@runtime_checkable
class SubmissionReaderPort(Protocol):
    def get_submit_attempt(self, submit_attempt_id: str) -> SubmitAttempt | None:
        """Load one SubmitAttempt."""

    def get_submission(self, submission_id: str) -> Submission | None:
        """Load one Submission."""


@runtime_checkable
class OperatorRecoveryApplicationPort(Protocol):
    def execute_recovery(self, request: OperatorRecoveryRequest) -> TransitionDisposition:
        """Apply or replay one authorized operator recovery command."""


@runtime_checkable
class AdmissionGatePort(Protocol):
    def allows_new_work(self) -> bool:
        """Return False when gateway admission is closed for new commands."""

    def try_acquire(self) -> bool:
        """Reserve one in-flight creation slot, or return False when closed or full."""

    def release(self) -> None:
        """Release one previously acquired creation slot."""


@runtime_checkable
class ArtifactRefLookupPort(Protocol):
    def lookup_ref(self, artifact_id: str) -> ArtifactRef | None:
        """Return durable artifact metadata when the store can resolve one id."""


class FailClosedArtifactRefLookup:
    def lookup_ref(self, artifact_id: str) -> ArtifactRef | None:
        del artifact_id
        return None


@runtime_checkable
class BundleReaderPort(Protocol):
    def read_bundle(self, artifact_id: str) -> tuple[str, Iterator[bytes]]:
        """Return logical bundle name and bounded byte stream."""


class OpenAdmissionGate:
    def allows_new_work(self) -> bool:
        return True

    def try_acquire(self) -> bool:
        return True

    def release(self) -> None:
        return None


class ClosableAdmissionGate:
    """Process-local gate that bounds in-flight creation and closes before HTTP drain."""

    def __init__(self, *, limit: int = 32) -> None:
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        self._limit = limit
        self._in_flight = 0
        self._open = True
        self._lock = Lock()

    def allows_new_work(self) -> bool:
        with self._lock:
            return self._open

    def try_acquire(self) -> bool:
        with self._lock:
            if not self._open or self._in_flight >= self._limit:
                return False
            self._in_flight += 1
            return True

    def release(self) -> None:
        with self._lock:
            if self._in_flight > 0:
                self._in_flight -= 1

    def close(self) -> None:
        with self._lock:
            self._open = False


@contextmanager
def acquire_new_work(gate: AdmissionGatePort) -> Iterator[None]:
    """Admit one creation request or raise 429 without leaking the slot."""

    if not gate.try_acquire():
        from gateway_backend.http.errors import ApiError

        closed = not gate.allows_new_work()
        raise ApiError(
            code="ADMISSION_LIMIT_REACHED",
            message=(
                "gateway admission is closed for new work"
                if closed
                else "gateway admission limit reached"
            ),
            status_code=429,
        )
    try:
        yield
    finally:
        gate.release()


class FailClosedBaselineCanonicalDigestPort:
    def get_baseline_canonical_digest(
        self,
        *,
        repository_id: str,
        baseline_head: BaselineHead,
        input_completeness: InputCompleteness,
        ruleset_version: str,
    ) -> str:
        del repository_id, baseline_head, input_completeness, ruleset_version
        from gateway_backend.http.errors import ApiError

        raise ApiError(
            code="SERVICE_NOT_READY",
            message="baseline canonical digest port is unavailable",
            status_code=503,
        )


class FailClosedRepositoryMainResolvePort:
    def resolve_main_expected_commit(self, *, repository_id: str) -> str:
        del repository_id
        from gateway_backend.http.errors import ApiError

        raise ApiError(
            code="DEPENDENCY_UNAVAILABLE",
            message="repository main resolve is unavailable",
            status_code=503,
        )


class FailClosedOperatorRecoveryPort:
    def execute_recovery(self, request: OperatorRecoveryRequest) -> TransitionDisposition:
        del request
        from gateway_backend.http.errors import ApiError

        raise ApiError(
            code="SERVICE_NOT_READY",
            message="operator recovery composition is unavailable",
            status_code=503,
        )


class FailClosedSubmissionReader:
    def get_submit_attempt(self, submit_attempt_id: str) -> SubmitAttempt | None:
        del submit_attempt_id
        return None

    def get_submission(self, submission_id: str) -> Submission | None:
        del submission_id
        return None


@dataclass(frozen=True, slots=True)
class WorkspaceHttpDependencies:
    session_port: SessionPort
    scope_resolution: ScopeResolutionPort
    baseline_head_read: BaselineHeadReadPort
    workspace_repository: WorkspaceRepository
    unit_of_work_factory: WorkspaceControlUnitOfWorkFactory
    artifact_store: BoundedArtifactStorePort
    job_registry: JobDefinitionRegistry
    bundle_reader: BundleReaderPort
    admission_gate: AdmissionGatePort
    operation_reader: OperationReaderPort
    now: Callable[[], datetime]
    submission_reader: SubmissionReaderPort = field(default_factory=FailClosedSubmissionReader)
    artifact_ref_lookup: ArtifactRefLookupPort = field(default_factory=FailClosedArtifactRefLookup)
    internal_bearer_port: InternalBearerPort = field(
        default_factory=_default_internal_bearer_port
    )
    baseline_canonical_digest: BaselineCanonicalDigestPort = field(
        default_factory=FailClosedBaselineCanonicalDigestPort
    )
    main_resolve: RepositoryMainResolvePort = field(
        default_factory=FailClosedRepositoryMainResolvePort
    )
    operator_recovery_port: OperatorRecoveryApplicationPort = field(
        default_factory=FailClosedOperatorRecoveryPort
    )

    @classmethod
    def default_now(cls) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class HistoryHttpDependencies:
    unit_of_work_factory: HistoryControlUnitOfWorkFactory
    snapshot_loader: HistorySnapshotLoaderPort
    scope_resolution: ScopeResolutionPort
    job_registry: JobDefinitionRegistry
    admission_gate: AdmissionGatePort
    operation_reader: OperationReaderPort
    artifact_store: BoundedArtifactStorePort
    bundle_reader: BundleReaderPort
    table_ruleset_version: str
    now: Callable[[], datetime]


def get_history_http(request: Request) -> HistoryHttpDependencies:
    deps = getattr(request.app.state, "history_http", None)
    if deps is None:
        from gateway_backend.http.errors import ApiError

        raise ApiError(
            code="SERVICE_NOT_READY",
            message="history HTTP dependencies are unavailable",
            status_code=503,
        )
    if not isinstance(deps, HistoryHttpDependencies):
        raise TypeError("history_http state must be HistoryHttpDependencies")
    return deps


def get_workspace_http(request: Request) -> WorkspaceHttpDependencies:
    deps = getattr(request.app.state, "workspace_http", None)
    if deps is None:
        from gateway_backend.http.errors import ApiError

        raise ApiError(
            code="SERVICE_NOT_READY",
            message="workspace HTTP dependencies are unavailable",
            status_code=503,
        )
    if not isinstance(deps, WorkspaceHttpDependencies):
        raise TypeError("workspace_http state must be WorkspaceHttpDependencies")
    return deps


class ReadOnlyOperationStore:
    """Read-only operation access for HTTP GET without opening a write transaction."""

    def __init__(self, unit_of_work_factory: ControlDbUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def get_operation(self, operation_id: str) -> OperationRecord:
        with self._unit_of_work_factory() as unit_of_work:
            try:
                return unit_of_work.operations.get_operation(operation_id)
            except RecordNotFound:
                from gateway_backend.http.errors import ApiError

                raise ApiError(
                    code="RESOURCE_NOT_FOUND",
                    message="resource not found",
                    status_code=404,
                ) from None

    def get_step(self, step_id: str) -> StepRecord:
        with self._unit_of_work_factory() as unit_of_work:
            try:
                return unit_of_work.operations.get_step(step_id)
            except RecordNotFound:
                from gateway_backend.http.errors import ApiError

                raise ApiError(
                    code="RECOVERY_TARGET_NOT_FOUND",
                    message="recovery target not found",
                    status_code=404,
                ) from None


class ReadOnlySubmissionStore:
    """Read-only submission access for HTTP GET without opening a write transaction."""

    def __init__(self, unit_of_work_factory: ControlDbUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def get_submit_attempt(self, submit_attempt_id: str) -> SubmitAttempt | None:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.submission.get_submit_attempt(submit_attempt_id)

    def get_submission(self, submission_id: str) -> Submission | None:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.submission.get_submission(submission_id)


def reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    seen: set[str] = set()
    for key, _ in pairs:
        if key in seen:
            raise ValueError("duplicate JSON keys are not allowed")
        seen.add(key)
    return dict(pairs)


BODY_LIMIT_POST_PATHS = frozenset(
    {
        "/v1/archive-plan-preview",
        "/v1/archive-confirmations",
        "/v1/archive-anomaly-resolutions",
        "/v1/archives",
        "/v1/history-compares",
    }
)


class ArchiveRequestBodyLimitMiddleware:
    """Reject Archive POST bodies above the Design §3.3 byte budget before parsing."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path", ""))
        if path not in BODY_LIMIT_POST_PATHS:
            await self.app(scope, receive, send)
            return

        import json

        from gateway_backend.application.archive.contracts import ARCHIVE_MAX_REQUEST_BYTES
        from gateway_backend.http.errors import error_response

        body = b""
        more_body = True
        while more_body:
            message: Message = await receive()
            if message["type"] != "http.request":
                return
            chunk = message.get("body", b"")
            if not isinstance(chunk, (bytes, bytearray)):
                chunk = b""
            body += bytes(chunk)
            more_body = bool(message.get("more_body", False))
            if len(body) > ARCHIVE_MAX_REQUEST_BYTES:
                response = error_response(
                    code="REQUEST_TOO_LARGE",
                    message="request body exceeds size limit",
                    status_code=413,
                )
                await response(scope, receive, send)
                return

        if body:
            try:
                json.loads(
                    body.decode("utf-8"),
                    object_pairs_hook=reject_duplicate_json_keys,
                )
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError, RecursionError):
                response = error_response(
                    code="REQUEST_VALIDATION_FAILED",
                    message="request validation failed",
                    status_code=422,
                )
                await response(scope, receive, send)
                return

        sent = False

        async def replay_receive() -> Message:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)


def require_identity(request: Request) -> IdentityContext:
    return get_workspace_http(request).session_port.resolve(request)


def require_internal_bearer(request: Request) -> None:
    get_workspace_http(request).internal_bearer_port.verify(request)
