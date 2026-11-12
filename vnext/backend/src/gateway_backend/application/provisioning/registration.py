"""One bounded registration around the existing repository and scope authorities."""
from __future__ import annotations

from collections.abc import Callable

from gateway_backend.device_identity import device_create_key, device_initial_node_id, validate_scope_identity
from gateway_backend.application.provisioning.contracts import (
    Registration, RegistrationConflict, RegistrationDependencyUnavailable,
    RegistrationRepositoryPort, RegistrationStorePort,
)


class DeviceRegistration:
    def __init__(self, *, store: RegistrationStorePort, environment: str, group: str, storage_digest: str,
                 reservation: Callable[[str], object], repository: RegistrationRepositoryPort) -> None:
        self.store = store
        self.environment = environment
        self.group = group
        self.storage_digest = storage_digest
        self.reservation = reservation
        self.repository = repository

    def query(self, device: str) -> Registration | None:
        validate_scope_identity(device)
        return self.store.lookup(device)

    async def register(self, *, environment: str, group: str, device: str, project: str) -> Registration:
        validate_scope_identity(device)
        validate_scope_identity(project)
        if environment != self.environment or group != self.group:
            raise RegistrationConflict("processing group differs")
        try:
            self.reservation(device)
        except (OSError, ValueError) as exc:
            raise RegistrationConflict("reservation unavailable or inconsistent") from exc
        try:
            identity = await self.repository.get_deployment_identity()
            if (identity.environment_id, identity.group_id, identity.storage_digest) != (environment, group, self.storage_digest):
                raise ValueError("repository service identity differs")
        except Exception as exc:
            raise RegistrationDependencyUnavailable("repository service identity unavailable or inconsistent") from exc
        existing = self.store.lookup(device, project)
        if existing is not None:
            return existing
        try:
            created = await self.repository.create_repository(idempotency_key=device_create_key(environment, group, device))
        except Exception as exc:
            raise RegistrationDependencyUnavailable("repository creation unavailable or unresolved") from exc
        expected = Registration(environment, group, device, project, created.repository_id,
            device_initial_node_id(environment, group, device), created.initial_commit_id)
        return self.store.insert_or_exact(expected)
