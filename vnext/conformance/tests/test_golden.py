"""Golden binding validation tests."""

from __future__ import annotations

from pathlib import Path

import json

import pytest

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.scenario.validate import validate_scenario
from support import build_valid_data_scenario


def test_golden_manifest_binding_mismatch_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "minimal"
    manifest = build_valid_data_scenario(root)
    text = (root / "scenario.yaml").read_text(encoding="utf-8")
    stale = manifest["expected"][0]["content_digest"]
    text = text.replace(stale, "sha256:" + "1" * 64, 1)
    (root / "scenario.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(ConformanceValidationError, match="content_digest"):
        validate_scenario(root)


def test_golden_kind_mismatch_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "minimal"
    build_valid_data_scenario(root)
    envelope = json.loads((root / "expected" / "result.golden.json").read_text(encoding="utf-8"))
    envelope["kind"] = "artifact"
    envelope["payload"] = {
        "storage": "closure",
        "value": {"content_digest": envelope["content_digest"], "manifest": {}},
    }
    envelope["payload_descriptor"]["comparison_mode"] = "artifact-closure"
    (root / "expected" / "result.golden.json").write_text(
        json.dumps(envelope, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(ConformanceValidationError):
        validate_scenario(root)
