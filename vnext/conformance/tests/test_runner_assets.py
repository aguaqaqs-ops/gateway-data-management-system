"""Verified asset resolver boundary tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.runner.runtime import VerifiedAssetResolver
from gateway_conformance.scenario.validate import load_validated_scenario
from tests.runner_support import build_structured_input_scenario


def test_declared_asset_readable(tmp_path: Path) -> None:
    root = build_structured_input_scenario(tmp_path)
    _manifest, closure = load_validated_scenario(root)
    resolver = VerifiedAssetResolver(closure.assets)
    payload = resolver.read_bytes("table")
    assert len(payload) > 0


def test_unknown_asset_rejected(tmp_path: Path) -> None:
    root = build_structured_input_scenario(tmp_path)
    _manifest, closure = load_validated_scenario(root)
    resolver = VerifiedAssetResolver(closure.assets)
    with pytest.raises(ConformanceValidationError, match="unknown verified asset"):
        resolver.read_bytes("missing")


def test_resolver_cannot_enumerate_host_directory(tmp_path: Path) -> None:
    root = build_structured_input_scenario(tmp_path)
    _manifest, closure = load_validated_scenario(root)
    resolver = VerifiedAssetResolver(closure.assets)
    assert not hasattr(resolver, "listdir")
    assert not hasattr(resolver, "__iter__")
