"""Session resolution for current-session authorization."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fastapi import Request

from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.errors import ApiError


@runtime_checkable
class SessionPort(Protocol):
    def resolve(self, request: Request) -> IdentityContext:
        """Resolve the current session to an IdentityContext."""


class BearerSessionPort:
    """Map bearer token to a configured IdentityContext."""

    def __init__(self, sessions: dict[str, IdentityContext]) -> None:
        if not sessions:
            raise ValueError("sessions must not be empty")
        self._sessions = dict(sessions)

    def resolve(self, request: Request) -> IdentityContext:
        authorization = request.headers.get("Authorization")
        if authorization is None or not authorization.startswith("Bearer "):
            raise ApiError(
                code="AUTHENTICATION_REQUIRED",
                message="authentication required",
                status_code=401,
            )
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            raise ApiError(
                code="AUTHENTICATION_REQUIRED",
                message="authentication required",
                status_code=401,
            )
        identity = self._sessions.get(token)
        if identity is None:
            raise ApiError(
                code="AUTHENTICATION_REQUIRED",
                message="authentication required",
                status_code=401,
            )
        return identity


def require_identity(request: Request) -> IdentityContext:
    from gateway_backend.http.dependencies import get_workspace_http

    return get_workspace_http(request).session_port.resolve(request)
