"""Bearer authentication dependency for protected routes."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.settings import RepositoryServiceSettings

_bearer_scheme = HTTPBearer(auto_error=False)


def _settings_from_request(request: Request) -> RepositoryServiceSettings:
    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, RepositoryServiceSettings):
        raise ServiceError(
            code="SERVICE_NOT_READY",
            message="service settings are unavailable",
            status_code=503,
        )
    return settings


def require_bearer_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> str:
    settings = _settings_from_request(request)
    expected = settings.resolve_bearer_token()
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ServiceError(
            code="UNAUTHENTICATED",
            message="missing or invalid bearer token",
            status_code=401,
        )
    if not hmac.compare_digest(credentials.credentials, expected):
        raise ServiceError(
            code="UNAUTHENTICATED",
            message="missing or invalid bearer token",
            status_code=401,
        )
    return credentials.credentials
