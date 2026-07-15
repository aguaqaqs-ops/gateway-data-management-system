from fastapi.testclient import TestClient
from pathlib import Path

from gateway_backend.app import create_app
from gateway_backend.settings import BackendSettings


def test_healthz_uses_injected_settings(tmp_path: Path) -> None:
    app = create_app(BackendSettings(artifact_root=tmp_path))

    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "artifact_root": str(tmp_path)}
