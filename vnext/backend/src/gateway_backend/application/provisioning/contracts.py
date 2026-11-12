"""Registration facts and minimal owner ports, independent of storage and HTTP."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class RegistrationConflict(ValueError):
    pass


class RegistrationDependencyUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Registration:
    environment_id: str
    group_id: str
    gateway_device_external_key: str
    business_project_id: str
    repository_id: str
    initial_node_id: str
    initial_commit_id: str


@dataclass(frozen=True)
class CreatedRepository:
    repository_id: str
    initial_commit_id: str


@dataclass(frozen=True)
class RepositoryIdentity:
    environment_id: str
    group_id: str
    storage_digest: str


class RegistrationRepositoryPort(Protocol):
    async def get_deployment_identity(self) -> RepositoryIdentity: ...
    async def create_repository(self, *, idempotency_key: str) -> CreatedRepository: ...


class RegistrationStorePort(Protocol):
    def lookup(self, device: str, project: str | None = None) -> Registration | None: ...
    def insert_or_exact(self, registration: Registration) -> Registration: ...


class ReservationPort(Protocol):
    def require_reservation(self, device: str, group: str) -> object: ...
