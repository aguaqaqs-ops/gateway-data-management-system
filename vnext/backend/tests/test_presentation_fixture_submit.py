"""The real comment-only producer still reaches Submit's canonical no-op boundary."""
from __future__ import annotations

import json
from pathlib import Path
import runpy

import pytest


@pytest.mark.unit
def test_comment_only_fixture_reaches_canonical_noop_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    vnext = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(vnext / "scripts"))
    generator = runpy.run_path(str(vnext / "scripts/generate-presentation-fixtures.py"))
    inputs_root = vnext / "fixtures/presentation-inputs"
    manifest = json.loads((inputs_root / "manifest.json").read_bytes())
    scenario = next(item for item in manifest["scenarios"] if item["id"] == "comment-only")
    inputs = {item["path"]: (inputs_root / item["path"]).read_bytes() for item in manifest["files"]}
    with generator["fixed_fixture_inputs"]():
        record = generator["generate_bundle"](tmp_path / "generated", scenario, inputs)
    assert record["operation_result"] == "READY"
    assert record["assertions_result"] == "PASS"
    submit = record["submit_result"]
    assert submit["code"] == "NO_CANONICAL_CHANGE"
    assert submit["write_transactions"] == submit["repository_main_calls"] == 0
    assert submit["baseline_canonical_state_digest"] == submit["modified_canonical_state_digest"]
