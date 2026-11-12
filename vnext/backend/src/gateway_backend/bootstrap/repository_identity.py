"""One bounded authenticated check of the Repository Service deployment owner."""
from __future__ import annotations

from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from typing import Any

from gateway_repository_contracts import DeploymentIdentityResponse
from gateway_backend.deployment_config import DeploymentConfig


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def assert_repository_identity(base_url: str, token: str, deployment: DeploymentConfig, *, timeout_seconds: float) -> None:
    """Never accept /readyz alone, redirect credentials, scan roots, or change state."""
    request = Request(base_url.rstrip("/") + "/internal/v1/deployment-identity",
        headers={"Authorization": "Bearer " + token})
    try:
        with build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=timeout_seconds) as response:
            raw = response.read(4097)
            if response.status != 200 or len(raw) > 4096:
                raise ValueError("invalid deployment response")
            identity = DeploymentIdentityResponse.model_validate_json(raw)
        storage = deployment.storage
        if (identity.environment_id, identity.group_id, identity.storage_digest) != (
                storage.environment_id, storage.group_id, storage.digest):
            raise ValueError("deployment identity differs")
    except (URLError, OSError, TimeoutError, ValueError):
        raise ValueError("repository service deployment identity unavailable or inconsistent") from None
