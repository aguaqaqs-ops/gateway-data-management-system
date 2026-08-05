"""Bearer authentication dependency for protected routes."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from gateway_repository_service.auth_state import AuthState
from gateway_repository_service.http.errors import ServiceError

_bearer_scheme = HTTPBearer(auto_error=False)


def _auth_state_from_request(request: Request) -> AuthState:
    auth_state = getattr(request.app.state, "auth_state", None)
    if not isinstance(auth_state, AuthState):
        raise ServiceError(
            code="SERVICE_NOT_READY",
            message="service authentication is unavailable",
            status_code=503,
        )
    return auth_state


def require_bearer_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> None:
    auth_state = _auth_state_from_request(request)
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ServiceError(
            code="UNAUTHENTICATED",
            message="missing or invalid bearer token",
            status_code=401,
        )
    if not hmac.compare_digest(credentials.credentials, auth_state.bearer_token):
        raise ServiceError(
            code="UNAUTHENTICATED",
            message="missing or invalid bearer token",
            status_code=401,
        )
