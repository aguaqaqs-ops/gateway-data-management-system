"""Authenticated identity from the runtime's existing cached deployment facts."""
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from gateway_repository_contracts import DeploymentIdentityResponse
from gateway_repository_service.http.auth import require_bearer_token
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.runtime import ServiceRuntime


def register_deployment_identity_routes(app: FastAPI) -> None:
    @app.get("/internal/v1/deployment-identity", response_model=DeploymentIdentityResponse)
    def deployment_identity(request: Request,
                            _authorized: Annotated[None, Depends(require_bearer_token)]) -> DeploymentIdentityResponse:
        runtime = getattr(request.app.state, "runtime", None)
        if not isinstance(runtime, ServiceRuntime) or runtime.settings.deployment_config is None:
            raise ServiceError(code="SERVICE_NOT_READY", message="deployment identity unavailable", status_code=503)
        storage = runtime.settings.deployment_config.storage
        return DeploymentIdentityResponse(environment_id=storage.environment_id,
            group_id=storage.group_id, storage_digest=storage.digest)
