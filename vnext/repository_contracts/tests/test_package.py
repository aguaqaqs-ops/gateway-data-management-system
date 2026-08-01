"""Package and public export smoke tests."""

from __future__ import annotations

import importlib
from pathlib import Path

import gateway_repository_contracts


def test_package_importable() -> None:
    assert gateway_repository_contracts.__name__ == "gateway_repository_contracts"


def test_lock_file_exists() -> None:
    lock_path = Path(__file__).resolve().parents[1] / "uv.lock"
    assert lock_path.is_file()


def test_no_public_exports() -> None:
    module = importlib.import_module("gateway_repository_contracts")
    assert module.__all__


def test_thin_public_modules_importable() -> None:
    for module_name in (
        "gateway_repository_contracts.errors",
        "gateway_repository_contracts.types",
        "gateway_repository_contracts.versioned",
    ):
        importlib.import_module(module_name)
