"""Service composition root and durable lifecycle orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from gateway_repository_service.capacity import (
    CapacityAdmissionError,
    DiskAdmission,
    assert_durable_root_writable,
    assert_free_disk_admission,
)
from gateway_repository_service.control_db import ControlDbError, ControlStore
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.locking import DurableRootLock, RootLockBusy
from gateway_repository_service.provider_lifecycle import OfflineCliCapabilityGate, ProviderUnavailableError
from gateway_repository_service.settings import RepositoryServiceSettings, SettingsError


class ServiceStartupError(RuntimeError):
    """Raised when durable lifecycle initialization fails before layout exists."""


@dataclass
class LifecycleState:
    layout_ok: bool = False
    lock_held: bool = False
    control_db_ok: bool = False
    provider_ok: bool = False
    writable_ok: bool = False
    disk_admission_ok: bool = False
    disk_admission: DiskAdmission | None = None
    startup_error: str | None = None

    @property
    def is_ready(self) -> bool:
        return (
            self.layout_ok
            and self.lock_held
            and self.control_db_ok
            and self.provider_ok
            and self.writable_ok
            and self.disk_admission_ok
            and self.startup_error is None
        )


class _ClosedControlStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def is_open(self) -> bool:
        return False

    def close(self) -> None:
        return None


@dataclass
class ServiceRuntime:
    settings: RepositoryServiceSettings
    layout: DurableLayout
    root_lock: DurableRootLock
    control_store: ControlStore | _ClosedControlStore
    provider_gate: OfflineCliCapabilityGate | None
    state: LifecycleState = field(default_factory=LifecycleState)

    @classmethod
    def start(cls, settings: RepositoryServiceSettings) -> "ServiceRuntime":
        state = LifecycleState()
        layout = DurableLayout.create(settings.data_root)
        root_lock = DurableRootLock(layout.service_lock)
        control_store: ControlStore | _ClosedControlStore = _ClosedControlStore(settings.control_db_path)
        provider_gate: OfflineCliCapabilityGate | None = None

        try:
            settings.resolve_bearer_token()
            state.layout_ok = True
            root_lock.acquire()
            state.lock_held = True
            opened = ControlStore.open(
                settings.control_db_path,
                expected_version=settings.control_db_user_version,
                busy_timeout_ms=settings.sqlite_busy_timeout_ms,
            )
            control_store = opened
            state.control_db_ok = True
            provider_gate = OfflineCliCapabilityGate.verify(settings, layout)
            state.provider_ok = True
            assert_durable_root_writable(layout.service_state)
            state.writable_ok = True
            state.disk_admission = assert_free_disk_admission(layout.root, settings)
            state.disk_admission_ok = True
        except (
            SettingsError,
            RootLockBusy,
            ControlDbError,
            ProviderUnavailableError,
            CapacityAdmissionError,
            RuntimeError,
        ) as exc:
            state.startup_error = str(exc)
            if isinstance(control_store, ControlStore):
                control_store.close()
                control_store = _ClosedControlStore(settings.control_db_path)
                state.control_db_ok = False
            if state.lock_held:
                root_lock.release()
                state.lock_held = False

        return cls(
            settings=settings,
            layout=layout,
            root_lock=root_lock,
            control_store=control_store,
            provider_gate=provider_gate,
            state=state,
        )

    def shutdown(self) -> None:
        if isinstance(self.control_store, ControlStore) and self.control_store.is_open():
            self.control_store.close()
        if self.state.lock_held:
            self.root_lock.release()
            self.state.lock_held = False

    def is_ready(self) -> bool:
        return self.state.is_ready

    def not_ready_message(self) -> str:
        if self.state.startup_error:
            return self.state.startup_error
        missing: list[str] = []
        if not self.state.layout_ok:
            missing.append("layout")
        if not self.state.lock_held:
            missing.append("root lock")
        if not self.state.control_db_ok:
            missing.append("control database")
        if not self.state.provider_ok:
            missing.append("provider")
        if not self.state.writable_ok:
            missing.append("durable root writable")
        if not self.state.disk_admission_ok:
            missing.append("free disk admission")
        if missing:
            return "durable lifecycle checks incomplete: " + ", ".join(missing)
        return "durable lifecycle is not initialized"
