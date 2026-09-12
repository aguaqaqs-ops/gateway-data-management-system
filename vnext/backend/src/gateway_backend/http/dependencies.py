"""HTTP dependency container and admission gate."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Protocol, runtime_checkable

from fastapi import Request

from gateway_backend.application.job_definitions import JobDefinitionRegistry
from gateway_backend.artifacts.bounded_store import BoundedArtifactStorePort
from gateway_backend.domain.workspace.ports import (
    BaselineHeadReadPort,
    ScopeResolutionPort,
    WorkspaceRepository,
)
from gateway_backend.http.auth import SessionPort
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.operations.contracts import OperationRecord
from gateway_backend.operations.store import RecordNotFound


@runtime_checkable
class OperationReaderPort(Protocol):
    def get_operation(self, operation_id: str) -> OperationRecord:
        """Return an operation or raise RecordNotFound."""


@runtime_checkable
class AdmissionGatePort(Protocol):
    def allows_new_work(self) -> bool:
        """Return False when gateway admission is closed for new commands."""


@runtime_checkable
class BundleReaderPort(Protocol):
    def read_bundle(self, artifact_id: str) -> tuple[str, Iterator[bytes]]:
        """Return logical bundle name and bounded byte stream."""


class OpenAdmissionGate:
    def allows_new_work(self) -> bool:
        return True


class ClosableAdmissionGate:
    """Process-local gate that closes creation admission before HTTP drain."""

    def __init__(self) -> None:
        self._open = True
        self._lock = Lock()

    def allows_new_work(self) -> bool:
        with self._lock:
            return self._open

    def close(self) -> None:
        with self._lock:
            self._open = False


@dataclass(frozen=True, slots=True)
class WorkspaceHttpDependencies:
    session_port: SessionPort
    scope_resolution: ScopeResolutionPort
    baseline_head_read: BaselineHeadReadPort
    workspace_repository: WorkspaceRepository
    unit_of_work_factory: Callable[[], ControlDbUnitOfWork]
    artifact_store: BoundedArtifactStorePort
    job_registry: JobDefinitionRegistry
    bundle_reader: BundleReaderPort
    admission_gate: AdmissionGatePort
    operation_reader: OperationReaderPort
    now: Callable[[], datetime]

    @classmethod
    def default_now(cls) -> datetime:
        return datetime.now(UTC)


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

    def __init__(self, unit_of_work_factory: Callable[[], ControlDbUnitOfWork]) -> None:
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
