from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from gateway_backend.http.dependencies import WorkspaceHttpDependencies
from gateway_backend.http.shutdown import begin_http_pre_drain
from gateway_backend.settings import BackendSettings


def create_app(
    settings: BackendSettings | None = None,
    *,
    workspace_http: WorkspaceHttpDependencies | None = None,
) -> FastAPI:
    if workspace_http is not None:
        from gateway_backend.http.dependencies import ArchiveRequestBodyLimitMiddleware
        from gateway_backend.http.wiring import register_workspace_http

        app = FastAPI(title="Gateway Backend vNext")
        app.add_middleware(ArchiveRequestBodyLimitMiddleware)
        _register_health_routes(app, ready=True)
        register_workspace_http(app, workspace_http)
        return app

    configured = settings if settings is not None else BackendSettings()  # type: ignore[call-arg]

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        from gateway_backend.http.runtime import prepare_backend_runtime
        from gateway_backend.http.wiring import register_workspace_http

        runtime = prepare_backend_runtime(configured)
        register_workspace_http(app, runtime.workspace_http)
        app.state.admission_gate = runtime.admission_gate
        app.state.ready = True
        try:
            yield
        finally:
            begin_http_pre_drain(app)

    from gateway_backend.http.dependencies import ArchiveRequestBodyLimitMiddleware
    from gateway_backend.http.errors import register_exception_handlers

    app = FastAPI(title="Gateway Backend vNext", lifespan=lifespan)
    app.add_middleware(ArchiveRequestBodyLimitMiddleware)
    register_exception_handlers(app)
    app.state.ready = False
    _register_health_routes(app, ready=None)
    return app


def _register_health_routes(app: FastAPI, *, ready: bool | None) -> None:
    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", response_model=None)
    def readyz() -> JSONResponse:
        is_ready = ready if ready is not None else bool(getattr(app.state, "ready", False))
        if not is_ready:
            return JSONResponse({"status": "not_ready"}, status_code=503)
        return JSONResponse({"status": "ok"})
