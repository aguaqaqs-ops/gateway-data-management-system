"""Service composition root and durable lifecycle orchestration."""

from __future__ import annotations

import os
from contextlib import ExitStack
from dataclasses import dataclass

from gateway_repository_service.auth_state import AuthState
from gateway_repository_service.capacity import (
    has_free_disk_admission,
    is_durable_root_writable,
)
from gateway_repository_service.control_db import ControlStore
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.locking import DurableRootLock
from gateway_repository_service.provider_lifecycle import OfflineCliCapabilityGate
from gateway_repository_service.settings import RepositoryServiceSettings


class ServiceStartupError(RuntimeError):
    """Raised when durable lifecycle initialization fails."""


@dataclass
class ServiceRuntime:
    settings: RepositoryServiceSettings
    layout: DurableLayout
    root_lock: DurableRootLock
    control_store: ControlStore
    provider_gate: OfflineCliCapabilityGate
    auth_state: AuthState

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
                expected_version=settings.control_db_user_version,
                busy_timeout_ms=settings.sqlite_busy_timeout_ms,
            )
            stack.callback(control_store.close)
            provider_gate = OfflineCliCapabilityGate.verify(settings, layout)
            if not is_durable_root_writable(layout.service_state):
                raise ServiceStartupError("durable root is not writable")
            if not has_free_disk_admission(layout.root, settings):
                raise ServiceStartupError("durable root free disk is below admission threshold")
            stack.pop_all()
            return cls(
                settings=settings,
                layout=layout,
                root_lock=root_lock,
                control_store=control_store,
                provider_gate=provider_gate,
                auth_state=AuthState(bearer_token=bearer_token),
            )
        except ServiceStartupError:
            raise
        except Exception as exc:
            raise ServiceStartupError(str(exc)) from exc
        finally:
            stack.close()

    def shutdown(self) -> None:
        if self.control_store.is_open():
            self.control_store.close()
        if self.root_lock.is_held():
            self.root_lock.release()

    def _readiness_failure(self) -> str | None:
        if not self.root_lock.is_held():
            return "root lock is not held"
        if not self._control_db_ready():
            return "control database is unavailable"
        if not self._provider_ready():
            return "provider is unavailable"
        if not is_durable_root_writable(self.layout.service_state):
            return "durable root is not writable"
        if not has_free_disk_admission(self.layout.root, self.settings):
            return "free disk admission failed"
        return None

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
