"""Minimal package and import smoke tests for gateway-repository-client."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import gateway_repository_client
import gateway_repository_contracts


SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "gateway_repository_client"


def test_package_importable() -> None:
    assert gateway_repository_client.__name__ == "gateway_repository_client"


def test_contracts_dependency_importable() -> None:
    assert gateway_repository_contracts.__name__ == "gateway_repository_contracts"


def test_lock_file_exists() -> None:
    lock_path = Path(__file__).resolve().parents[1] / "uv.lock"
    assert lock_path.is_file()


def test_public_exports() -> None:
    module = importlib.import_module("gateway_repository_client")
    expected = {
        "ArrowIpcByteStream",
        "RepositoryClient",
        "RepositoryClientError",
        "RepositoryClientTimeoutError",
        "RepositoryProtocolError",
        "RepositoryStreamError",
        "NonRewindableUploadSourceError",
        "UploadBodySource",
        "retry_idempotent_request",
    }
    assert module.__all__
    assert expected <= set(module.__all__)
    for name in expected:
        assert getattr(module, name) is not None


def test_production_sources_do_not_import_service_or_pyarrow() -> None:
    banned = ("gateway_repository_service", "pyarrow")
    offenders: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in banned:
                        offenders.append(f"{path.name}:{alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                if node.module.split(".")[0] in banned:
                    offenders.append(f"{path.name}:{node.module}")
    assert offenders == []
