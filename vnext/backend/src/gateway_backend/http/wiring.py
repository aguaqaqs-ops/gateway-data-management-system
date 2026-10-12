"""Register 5A workspace HTTP routes and exception handlers."""

from __future__ import annotations

from fastapi import FastAPI

from gateway_backend.http.dependencies import HistoryHttpDependencies, WorkspaceHttpDependencies
from gateway_backend.http.errors import register_exception_handlers
from gateway_backend.http.routes.operations import router as operations_router
from gateway_backend.http.routes.operator_recovery import router as operator_recovery_router
from gateway_backend.http.routes.preview_operations import router as preview_operations_router
from gateway_backend.http.routes.preview_results import router as preview_results_router
from gateway_backend.http.routes.submit_attempts import router as submit_attempts_router
from gateway_backend.http.routes.archives import router as archives_router
from gateway_backend.http.routes.reviews import router as reviews_router
from gateway_backend.http.routes.submissions import router as submissions_router
from gateway_backend.http.routes.upload_revisions import router as upload_revisions_router
from gateway_backend.http.routes.workspaces import router as workspaces_router
from gateway_backend.http.routes.history import router as history_router

PRODUCTION_OPENAPI_PATHS = frozenset(
    {
        "/healthz",
        "/readyz",
        "/v1/history",
        "/v1/history-compares",
        "/v1/history-compares/{operation_id}",
        "/v1/history-compares/{operation_id}/bundle",
        "/v1/workspaces",
        "/v1/workspaces/{workspace_id}/upload-revisions",
        "/v1/workspaces/{workspace_id}/preview-operations",
        "/v1/operations/{operation_id}",
        "/v1/workspaces/{workspace_id}/preview-results/{preview_result_id}",
        "/v1/workspaces/{workspace_id}/preview-results/{preview_result_id}/bundle",
        "/v1/workspaces/{workspace_id}/submit-attempts",
        "/v1/workspaces/{workspace_id}/submit-attempts/{submit_attempt_id}",
        "/v1/workspaces/{workspace_id}/submissions/{submission_id}",
        "/v1/submissions/{submission_id}/review-events",
        "/v1/submissions/{submission_id}/review",
        "/v1/archive-candidates",
        "/v1/archive-plan-preview",
        "/v1/archive-confirmations",
        "/v1/archive-anomaly-resolutions",
        "/v1/archive-audit-events",
        "/v1/archives",
        "/v1/archives/{archive_result_id}",
        "/internal/v1/operations/{operation_id}/steps/{step_id}/recovery",
    }
)


def register_workspace_http(
    app: FastAPI,
    deps: WorkspaceHttpDependencies | None = None,
    history_deps: HistoryHttpDependencies | None = None,
) -> None:
    register_exception_handlers(app)
    if deps is not None:
        app.state.workspace_http = deps
    if history_deps is not None:
        app.state.history_http = history_deps
    app.include_router(workspaces_router)
    app.include_router(upload_revisions_router)
    app.include_router(preview_operations_router)
    app.include_router(operations_router)
    app.include_router(preview_results_router)
    app.include_router(submit_attempts_router)
    app.include_router(submissions_router)
    app.include_router(reviews_router)
    app.include_router(archives_router)
    app.include_router(history_router)
    app.include_router(operator_recovery_router)
