from fastapi import FastAPI

from gateway_backend.settings import BackendSettings


def create_app(settings: BackendSettings | None = None) -> FastAPI:
    configured = settings or BackendSettings()
    app = FastAPI(title="Gateway Backend vNext")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "artifact_root": str(configured.artifact_root)}

    return app
