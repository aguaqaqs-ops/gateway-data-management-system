"""Positive schema-only scenario manifest samples."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gateway_conformance.scenario import validate as validate_mod
from gateway_conformance.scenario.closure import ScenarioClosure, load_scenario_closure
from gateway_conformance.scenario.validate import load_validated_scenario, validate_scenario
from support import (
    build_valid_command_scenario,
    build_valid_data_scenario,
    build_valid_recovery_scenario,
)


@pytest.mark.parametrize(
    ("builder", "track", "scenario_dir"),
    [
        (build_valid_data_scenario, "data", "minimal"),
        (build_valid_command_scenario, "command", "submit"),
        (build_valid_recovery_scenario, "recovery", "timeout-success"),
    ],
)
def test_valid_track_scenarios_pass_validation(
    tmp_path: Path,
    builder: object,
    track: str,
    scenario_dir: str,
) -> None:
    root = tmp_path / track / "test-capability" / scenario_dir
    manifest = builder(root)  # type: ignore[operator]
    assert manifest["track"] == track
    validate_scenario(root)


def test_load_validated_scenario_loads_closure_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "data" / "test-capability" / "minimal"
    build_valid_data_scenario(root)
    calls = {"count": 0}

    def counting_load(path: Path) -> ScenarioClosure:
        calls["count"] += 1
        return load_scenario_closure(path)

    monkeypatch.setattr(validate_mod, "load_scenario_closure", counting_load)
    manifest, closure = load_validated_scenario(root)
    assert calls["count"] == 1
    assert manifest is closure.manifest


def test_load_validated_scenario_does_not_mix_snapshots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "data" / "test-capability" / "minimal"
    build_valid_data_scenario(root)
    first = load_scenario_closure(root)
    second_manifest = dict(first.manifest)
    second_manifest["description"] = "second-snapshot"
    second = ScenarioClosure(
        root=first.root,
        manifest=second_manifest,
        declared_paths=first.declared_paths,
        assets=first.assets,
        golden_envelopes=first.golden_envelopes,
    )
    loads = iter([first, second])

    def fake_load(_path: Path) -> ScenarioClosure:
        return next(loads)

    monkeypatch.setattr(validate_mod, "load_scenario_closure", fake_load)
    validated = MagicMock(side_effect=lambda closure: closure.manifest)
    monkeypatch.setattr(validate_mod, "_validate_loaded_closure", validated)

    manifest, closure = load_validated_scenario(root)
    assert validated.call_count == 1
    assert validated.call_args.args[0] is first
    assert manifest is first.manifest
    assert closure is first
    assert manifest is not second.manifest
