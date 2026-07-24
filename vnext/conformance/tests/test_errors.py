"""Error sanitization tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.sanitize import sanitize_message
from gateway_conformance.scenario.validate import validate_scenario
from support import build_valid_data_scenario


def test_oversized_manifest_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "minimal"
    build_valid_data_scenario(root)
    huge = b"x" * (1_048_576 + 1)
    (root / "scenario.yaml").write_bytes(huge)
    with pytest.raises(ConformanceValidationError):
        validate_scenario(root)


def test_error_message_does_not_leak_absolute_path(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "minimal"
    build_valid_data_scenario(root)
    (root / "expected" / "result.golden.json").unlink()
    try:
        validate_scenario(root)
    except ConformanceValidationError as exc:
        assert str(root) not in str(exc)
        assert sanitize_message(str(exc)) == str(exc)
