"""Minimal package and import smoke tests for gateway-repository-client."""

from __future__ import annotations

import importlib
from pathlib import Path

import gateway_repository_client
import gateway_repository_contracts


def test_package_importable() -> None:
    assert gateway_repository_client.__name__ == "gateway_repository_client"


def test_contracts_dependency_importable() -> None:
    assert gateway_repository_contracts.__name__ == "gateway_repository_contracts"


def test_lock_file_exists() -> None:
    lock_path = Path(__file__).resolve().parents[1] / "uv.lock"
    assert lock_path.is_file()


def test_no_public_exports() -> None:
    module = importlib.import_module("gateway_repository_client")
    assert not hasattr(module, "__all__") or module.__all__ == ()
