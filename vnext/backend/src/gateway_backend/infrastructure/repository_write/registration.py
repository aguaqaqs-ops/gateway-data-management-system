"""Narrow Repository client adapter for device provisioning."""
from gateway_repository_client import RepositoryClient
from gateway_backend.application.provisioning.contracts import CreatedRepository, RepositoryIdentity


class RegistrationRepositoryAdapter:
    def __init__(self, client: RepositoryClient) -> None:
        self.client = client

    async def get_deployment_identity(self) -> RepositoryIdentity:
        result = await self.client.get_deployment_identity()
        return RepositoryIdentity(result.environment_id, result.group_id, result.storage_digest)

    async def create_repository(self, *, idempotency_key: str) -> CreatedRepository:
        result = await self.client.create_repository(idempotency_key=idempotency_key)
        return CreatedRepository(str(result.repository_id), str(result.initial_commit_id))
