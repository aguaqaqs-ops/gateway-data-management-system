"""FastAPI composition root for Repository Service."""

from __future__ import annotations

from fastapi import FastAPI

from gateway_repository_service.http.errors import register_exception_handlers
from gateway_repository_service.http.middleware import RequestIdMiddleware
from gateway_repository_service.http.readiness import DefaultReadiness, ReadinessPort
from gateway_repository_service.http.routes.probes import register_probe_routes
from gateway_repository_service.settings import RepositoryServiceSettings


def create_app(
    settings: RepositoryServiceSettings | None = None,
    *,
    readiness: ReadinessPort | None = None,
) -> FastAPI:
    configured = settings or RepositoryServiceSettings()
    readiness_port: ReadinessPort = readiness if readiness is not None else DefaultReadiness()

    app = FastAPI(
        title="Gateway Repository Service",
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json",
    )
    app.state.settings = configured
    app.state.readiness = readiness_port

    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    register_probe_routes(app)

    return app
