from pathlib import Path

import pytest

from tests.support.http_workspace_harness import create_workspace_http_environment

pytestmark = pytest.mark.unit


def test_healthz_returns_ok_without_host_path(tmp_path: Path) -> None:
    client = create_workspace_http_environment(tmp_path).client

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert str(tmp_path) not in response.text
    assert "artifact" not in response.text


def test_readyz_is_ok_when_workspace_http_is_injected(tmp_path: Path) -> None:
    client = create_workspace_http_environment(tmp_path).client

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert str(tmp_path) not in response.text
