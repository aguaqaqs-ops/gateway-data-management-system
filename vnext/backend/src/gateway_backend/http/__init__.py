"""P5-5A HTTP interface: routes, DTOs, session authorization and orchestration."""

from gateway_backend.http.dependencies import WorkspaceHttpDependencies
from gateway_backend.http.wiring import register_workspace_http

__all__ = ["WorkspaceHttpDependencies", "register_workspace_http"]
