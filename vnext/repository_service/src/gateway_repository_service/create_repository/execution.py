"""One nonblocking CREATE owner per runtime/store, including actual child exit."""
from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
from threading import Lock

from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.settings import RepositoryServiceSettings


class CreateExecutionOwner:
    def __init__(self) -> None:
        self._gate = Lock()
        self._state = Lock()
        self._unresolved = False
        self._closed = False
        self.runner: DoltRunner | None = None

    def configure(self, settings: RepositoryServiceSettings, layout: DurableLayout) -> DoltRunner:
        if self.runner is None:
            self.runner = DoltRunner.for_layout(settings, layout)
        return self.runner

    @property
    def in_use(self) -> bool:
        return self._gate.locked()

    def close(self) -> None:
        with self._state:
            self._closed = True

    @contextmanager
    def admit(self) -> Iterator[None]:
        with self._state:
            if self._closed:
                raise ServiceError(code="SERVICE_NOT_READY", message="service is stopping", status_code=503)
            if self._unresolved:
                raise unresolved()
            if not self._gate.acquire(blocking=False):
                raise ServiceError(code="CREATE_REPOSITORY_BUSY", message="repository creation is busy", status_code=503)
        try:
            yield
        finally:
            if self.runner is not None and self.runner.has_active_children():
                # Retain the gate: another request must never overlap a child whose exit is unknown.
                with self._state:
                    self._unresolved = True
                raise unresolved()
            else:
                self._gate.release()


def unresolved() -> ServiceError:
    return ServiceError(code="CREATE_REPOSITORY_UNRESOLVED", message="repository creation evidence is unresolved", status_code=503)
