from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from .formal_app import VNextFormalAppSettings, create_app


DEFAULT_STATE_ROOT = Path.home() / "test-dir" / "backend-vnext-formal-state"


def _split_csv(value: str | None, *, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return fallback
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    return items or fallback


def get_settings() -> VNextFormalAppSettings:
    state_root = os.getenv("BACKEND_VNEXT_FORMAL_STATE_ROOT")
    return VNextFormalAppSettings(
        state_root=Path(state_root).expanduser() if state_root else DEFAULT_STATE_ROOT,
        frontend_origins=_split_csv(
            os.getenv("BACKEND_VNEXT_FORMAL_FRONTEND_ORIGINS"),
            fallback=VNextFormalAppSettings.frontend_origins,
        ),
        control_plane_base_url=os.getenv(
            "BACKEND_VNEXT_FORMAL_CONTROL_PLANE_BASE_URL",
            VNextFormalAppSettings.control_plane_base_url,
        ),
        control_plane_internal_auth_token=os.getenv(
            "BACKEND_VNEXT_FORMAL_CONTROL_PLANE_INTERNAL_AUTH_TOKEN",
            VNextFormalAppSettings.control_plane_internal_auth_token,
        ),
        control_plane_timeout_seconds=float(
            os.getenv(
                "BACKEND_VNEXT_FORMAL_CONTROL_PLANE_TIMEOUT_SECONDS",
                str(VNextFormalAppSettings.control_plane_timeout_seconds),
            )
        ),
        internal_bearer_token=os.getenv(
            "BACKEND_VNEXT_FORMAL_INTERNAL_BEARER_TOKEN",
            VNextFormalAppSettings.internal_bearer_token,
        ),
        sso_ticket_secret=os.getenv(
            "BACKEND_VNEXT_FORMAL_SSO_TICKET_SECRET",
            VNextFormalAppSettings.sso_ticket_secret,
        ),
        workspace_session_secret=os.getenv(
            "BACKEND_VNEXT_FORMAL_WORKSPACE_SESSION_SECRET",
            VNextFormalAppSettings.workspace_session_secret,
        ),
        workspace_session_cookie_name=os.getenv(
            "BACKEND_VNEXT_FORMAL_WORKSPACE_SESSION_COOKIE_NAME",
            VNextFormalAppSettings.workspace_session_cookie_name,
        ),
        workspace_session_ttl_seconds=int(
            os.getenv(
                "BACKEND_VNEXT_FORMAL_WORKSPACE_SESSION_TTL_SECONDS",
                str(VNextFormalAppSettings.workspace_session_ttl_seconds),
            )
        ),
    )


app = create_app(settings=get_settings())

__all__ = ("app", "create_app", "get_settings")


if __name__ == "__main__":
    uvicorn.run(
        "backend_vnext.api.formal_main:app",
        host=os.getenv("BACKEND_VNEXT_FORMAL_HOST", "127.0.0.1"),
        port=int(os.getenv("BACKEND_VNEXT_FORMAL_PORT", "8001")),
        reload=False,
    )
