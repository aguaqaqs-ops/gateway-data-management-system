"""Session resolution for current-session authorization."""

from __future__ import annotations

from pathlib import Path
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


def load_session_file(session_file: Path) -> dict[str, IdentityContext]:
    """Load bearer token → IdentityContext mappings from a server-owned JSON file."""

    import json

    if not isinstance(session_file, Path) or not session_file.is_absolute():
        raise ValueError("session file must be absolute")
    try:
        payload = json.loads(session_file.read_text(encoding="utf-8"))
    except OSError:
        raise ValueError("session file is unreadable") from None
    except json.JSONDecodeError as exc:
        raise ValueError("session file is invalid JSON") from exc
    if type(payload) is not dict:
        raise ValueError("session file must be a JSON object")
    raw_sessions = payload.get("sessions")
    if type(raw_sessions) is not list or not raw_sessions:
        raise ValueError("session file must contain sessions")
    sessions: dict[str, IdentityContext] = {}
    for item in raw_sessions:
        if type(item) is not dict:
            raise ValueError("session entry must be an object")
        token = item.get("token")
        permissions = item.get("permissions")
        if type(token) is not str or not token:
            raise ValueError("session token must be a non-empty string")
        if token in sessions:
            raise ValueError("session file contains duplicate tokens")
        if type(permissions) is not list or not permissions:
            raise ValueError("session permissions must be a non-empty list")
        permission_set = frozenset(str(permission) for permission in permissions)
        sessions[token] = IdentityContext(
            actor_id=_require_session_string(item, "actor_id"),
            gateway_device_external_key=_require_session_string(item, "gateway_device_external_key"),
            business_project_id=_require_session_string(item, "business_project_id"),
            permissions=permission_set,
        )
    return sessions


def _require_session_string(item: dict[str, object], key: str) -> str:
    value = item.get(key)
    if type(value) is not str or not value:
        raise ValueError(f"session {key} must be a non-empty string")
    return value


def require_identity(request: Request) -> IdentityContext:
    from gateway_backend.http.dependencies import get_workspace_http

    return get_workspace_http(request).session_port.resolve(request)
