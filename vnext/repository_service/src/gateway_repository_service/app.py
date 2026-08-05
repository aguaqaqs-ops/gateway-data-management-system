"""FastAPI composition root for Repository Service."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from fastapi import FastAPI
from starlette.middleware.errors import ServerErrorMiddleware

from gateway_repository_service.http.errors import register_exception_handlers, server_exception_handler
from gateway_repository_service.http.middleware import RequestIdMiddleware
from gateway_repository_service.http.readiness import DefaultReadiness, LifecycleReadiness, ReadinessPort
from gateway_repository_service.http.routes.probes import register_probe_routes
from gateway_repository_service.http.routes.repositories import register_repository_routes
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.settings import RepositoryServiceSettings


@asynccontextmanager
async def _default_lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: RepositoryServiceSettings = app.state.settings
    runtime = ServiceRuntime.start(settings)
    app.state.runtime = runtime
    app.state.auth_state = runtime.auth_state
    app.state.readiness = LifecycleReadiness(runtime)
    try:
        yield
    finally:
        runtime.shutdown()


def create_app(
    settings: RepositoryServiceSettings | None = None,
    *,
    readiness: ReadinessPort | None = None,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[Any]] | None = None,
    enable_lifecycle: bool = True,
) -> FastAPI:
    configured = settings or RepositoryServiceSettings()
    use_lifecycle = enable_lifecycle and readiness is None
    app = FastAPI(
        title="Gateway Repository Service",
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json",
        lifespan=lifespan or (_default_lifespan if use_lifecycle else None),
    )
    app.state.settings = configured
    if readiness is not None:
        app.state.readiness = readiness
    elif not use_lifecycle:
        app.state.readiness = DefaultReadiness()

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(ServerErrorMiddleware, handler=server_exception_handler, debug=False)
    register_exception_handlers(app)
    register_probe_routes(app)
    register_repository_routes(app)

    return app
