"""Backend and worker reject an unavailable or different authenticated RS owner."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from typing import Any, Iterator
from urllib.error import URLError

import pytest

from gateway_backend.bootstrap.repository_identity import assert_repository_identity
from gateway_backend.bootstrap.composition import assert_repository_service_ready
from tests.support.runtime_settings import make_backend_settings, make_operation_worker_settings, prepare_backend_runtime_paths

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("fault", [None, "environment", "group", "storage", "auth", "malformed", "oversize", "unavailable"])
def test_authenticated_repository_identity_must_match_before_startup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str | None) -> None:
    settings = make_backend_settings(tmp_path)
    storage = settings.deployment_config.storage
    document = dict(environment_id=storage.environment_id, group_id=storage.group_id, storage_digest=storage.digest)
    if fault in {"environment", "group"}:
        document[fault + "_id"] = "other"
    if fault == "storage":
        document["storage_digest"] = "sha256:" + "0" * 64
    class Response:
        status = 401 if fault == "auth" else 200
        def read(self, bound: int) -> bytes:
            assert bound == 4097
            return b"x" * 4097 if fault == "oversize" else b"{}" if fault == "malformed" else json.dumps(document).encode()
    class Opener:
        @contextmanager
        def open(self, request: Any, *, timeout: float) -> Iterator[Response]:
            assert request.full_url == "http://repository.test/internal/v1/deployment-identity"
            assert request.get_header("Authorization") == "Bearer secret"
            assert timeout == 2
            if fault == "unavailable":
                raise URLError("not available")
            yield Response()
    monkeypatch.setattr("gateway_backend.bootstrap.repository_identity.build_opener", lambda *args: Opener())
    if fault is None:
        assert_repository_identity("http://repository.test", "secret", settings.deployment_config, timeout_seconds=2)
    else:
        with pytest.raises(ValueError, match="identity unavailable or inconsistent") as caught:
            assert_repository_identity("http://repository.test", "secret", settings.deployment_config, timeout_seconds=2)
        assert "secret" not in str(caught.value)


def test_readyz_alone_cannot_accept_a_different_repository_group(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_backend_settings(tmp_path)
    class Ready:
        status = 200
        def __enter__(self) -> Ready:
            return self
        def __exit__(self, *args: object) -> None:
            pass
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: Ready())
    def reject(*args: Any, **kwargs: Any) -> None:
        raise ValueError("wrong repository group")
    monkeypatch.setattr("gateway_backend.bootstrap.composition.assert_repository_identity", reject)
    with pytest.raises(ValueError, match="wrong repository group"):
        assert_repository_service_ready("http://repository.test", "token", timeout_seconds=2, deployment=settings.deployment_config)


def test_worker_checks_repository_identity_before_database_bootstrap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from gateway_backend.bootstrap.operation_worker import build_production_preview_dependencies
    prepare_backend_runtime_paths(tmp_path)
    settings = make_operation_worker_settings(tmp_path)
    def reject(*args: Any, **kwargs: Any) -> None:
        raise ValueError("wrong repository group")
    monkeypatch.setattr("gateway_backend.bootstrap.operation_worker.assert_repository_identity", reject)
    monkeypatch.setattr("gateway_backend.bootstrap.operation_worker.bootstrap_control_database",
        lambda *args: pytest.fail("wrong RS must not bootstrap the worker database"))
    with pytest.raises(ValueError, match="wrong repository group"):
        build_production_preview_dependencies(settings)
