from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from gateway_backend.http.dependencies import HistoryHttpDependencies, WorkspaceHttpDependencies
from gateway_backend.http.shutdown import begin_http_pre_drain
from gateway_backend.settings import BackendSettings


def create_app(
    settings: BackendSettings | None = None,
    *,
    workspace_http: WorkspaceHttpDependencies | None = None,
    history_http: HistoryHttpDependencies | None = None,
) -> FastAPI:
    if workspace_http is not None:
        from gateway_backend.http.dependencies import ArchiveRequestBodyLimitMiddleware
        from gateway_backend.http.wiring import register_workspace_http

        from gateway_backend.http.inflight_barrier import maybe_add_inflight_barrier_middleware

        app = FastAPI(title="Gateway Backend vNext")
        app.add_middleware(ArchiveRequestBodyLimitMiddleware)
        maybe_add_inflight_barrier_middleware(app)
        _register_health_routes(app, ready=True)
        register_workspace_http(app, workspace_http, history_deps=history_http)
        return app

    configured = settings if settings is not None else BackendSettings()  # type: ignore[call-arg]

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        from gateway_backend.bootstrap.composition import prepare_backend_runtime
        from gateway_backend.http.wiring import register_workspace_http

        runtime = prepare_backend_runtime(configured)
        register_workspace_http(
            app,
            runtime.workspace_http,
            history_deps=runtime.history_http,
        )
        app.state.storage_guard = runtime.storage_guard
        app.state.admission_gate = runtime.admission_gate
        app.state.ready = True
        try:
            yield
        finally:
            begin_http_pre_drain(app)

    from gateway_backend.http.dependencies import ArchiveRequestBodyLimitMiddleware
    from gateway_backend.http.errors import register_exception_handlers

    from gateway_backend.http.inflight_barrier import maybe_add_inflight_barrier_middleware

    app = FastAPI(title="Gateway Backend vNext", lifespan=lifespan)
    app.add_middleware(ArchiveRequestBodyLimitMiddleware)
    maybe_add_inflight_barrier_middleware(app)
    register_exception_handlers(app)
    @app.middleware("http")
    async def storage_admission(request, call_next):  # type: ignore[no-untyped-def]
        guard = getattr(app.state, "storage_guard", None)
        if guard is not None and request.url.path != "/healthz":
            try:
                guard.check()
            except (OSError, ValueError):
                from gateway_backend.http.errors import error_response
                return error_response(code="SERVICE_NOT_READY", message="deployment storage unavailable", status_code=503)
        return await call_next(request)

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
        guard = getattr(app.state, "storage_guard", None)
        if guard is not None:
            try:
                guard.check()
            except (OSError, ValueError):
                is_ready = False
        if not is_ready:
            return JSONResponse({"status": "not_ready"}, status_code=503)
        return JSONResponse({"status": "ok"})
