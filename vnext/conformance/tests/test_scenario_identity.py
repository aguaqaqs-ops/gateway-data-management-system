"""Scenario identity and ordering tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.paths import VNEXT_ROOT
from gateway_conformance.scenario.closure import load_scenario_closure
from gateway_conformance.scenario.identity import (
    scenario_id_from_relative_path,
    scenario_path_from_id,
)
from gateway_conformance.scenario.validate import validate_scenario
from support import (
    base_manifest,
    build_valid_data_scenario,
    structured_input_asset,
    write_scenario_tree,
)


FORMAL_MIXED_SCALARS = (
    VNEXT_ROOT / "fixtures" / "scenarios" / "data" / "canonical-row-hashes" / "mixed-scalars"
)


def test_scenario_id_path_reversibility() -> None:
    scenario_id = "data.test-capability.mixed-scalars"
    path = scenario_path_from_id(scenario_id)
    assert path.as_posix() == "data/test-capability/mixed-scalars"
    assert scenario_id_from_relative_path(path) == scenario_id


def test_unsorted_contract_bindings_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "minimal"
    build_valid_data_scenario(root)
    text = (root / "scenario.yaml").read_text(encoding="utf-8")
    text = text.replace(
        "contract_bindings:\n  - binding_id: subject",
        "contract_bindings:\n  - binding_id: zebra\n    owner: test-capability\n"
        "    contract_id: gateway-vnext.test-contract\n"
        "    semantic_version: 1.0.0\n  - binding_id: subject",
    )
    (root / "scenario.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(ConformanceValidationError, match="sorted"):
        validate_scenario(root)


def test_mismatched_scenario_id_and_path_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "minimal"
    build_valid_data_scenario(root)
    text = (
        (root / "scenario.yaml")
        .read_text(encoding="utf-8")
        .replace(
            "scenario_id: data.test-capability.minimal",
            "scenario_id: data.test-capability.other-name",
        )
    )
    (root / "scenario.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(ConformanceValidationError, match="reversibly"):
        validate_scenario(root)


def test_stimulus_asset_ref_undeclared_logical_name_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "asset-ref-stimulus"
    manifest, golden = base_manifest(scenario_suffix="asset-ref-stimulus")
    manifest["stimulus"] = {
        "contract_binding_id": "subject",
        "payload": {"storage": "asset-ref", "logical_name": "missing-asset"},
    }
    write_scenario_tree(root, manifest, golden_bytes=golden)
    with pytest.raises(
        ConformanceValidationError,
        match="stimulus asset-ref logical_name is not declared",
    ):
        validate_scenario(root)


def test_scenario_id_dot_collision_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "a-b"
    build_valid_data_scenario(root)
    text = (
        (root / "scenario.yaml")
        .read_text(encoding="utf-8")
        .replace(
            "scenario_id: data.test-capability.minimal",
            "scenario_id: data.test-capability.a.b",
        )
    )
    (root / "scenario.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(ConformanceValidationError, match="does not match"):
        validate_scenario(root)


def test_duplicate_declared_path_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "dup-path"
    manifest, golden = base_manifest(scenario_suffix="dup-path")
    payload, asset = structured_input_asset()
    manifest["input_assets"] = [
        asset,
        {
            **asset,
            "logical_name": "table-copy",
        },
    ]
    root.mkdir(parents=True)
    (root / "input").mkdir()
    (root / asset["path"]).write_bytes(payload)
    with pytest.raises(ConformanceValidationError, match="duplicate declared closure path"):
        write_scenario_tree(root, manifest, golden_bytes=golden)


def test_duplicate_semantic_binding_tuple_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "dup-binding"
    manifest, golden = base_manifest(scenario_suffix="dup-binding")
    manifest["contract_bindings"] = [
        {
            "binding_id": "alpha",
            "owner": "test-capability",
            "contract_id": "gateway-vnext.test-contract",
            "semantic_version": "1.0.0",
        },
        {
            "binding_id": "subject",
            "owner": "test-capability",
            "contract_id": "gateway-vnext.test-contract",
            "semantic_version": "1.0.0",
        },
    ]
    write_scenario_tree(root, manifest, golden_bytes=golden)
    with pytest.raises(ConformanceValidationError, match="duplicate semantic binding"):
        validate_scenario(root)


def test_formal_owner_closure_unsorted_rejected(tmp_path: Path) -> None:
    import copy
    import shutil

    from gateway_conformance.scenario.identity import assert_manifest_ordering

    dest = tmp_path / "data" / "canonical-row-hashes" / "mixed-scalars"
    shutil.copytree(FORMAL_MIXED_SCALARS, dest)
    closure = load_scenario_closure(dest)
    manifest = copy.deepcopy(closure.manifest)
    manifest["owner_closure_assets"].append(
        {
            "logical_name": "aaa-anchor",
            "path": "input/aaa-anchor.json",
            "media_type": "application/json",
            "size_bytes": 1,
            "raw_sha256": "sha256:" + "0" * 64,
        }
    )
    with pytest.raises(ConformanceValidationError, match="owner_closure_assets must be sorted"):
        assert_manifest_ordering(manifest)


def test_formal_owner_closure_duplicate_logical_name_rejected(tmp_path: Path) -> None:
    import copy
    import shutil

    from gateway_conformance.scenario.identity import assert_manifest_ordering

    dest = tmp_path / "data" / "canonical-row-hashes" / "mixed-scalars"
    shutil.copytree(FORMAL_MIXED_SCALARS, dest)
    closure = load_scenario_closure(dest)
    manifest = copy.deepcopy(closure.manifest)
    manifest["owner_closure_assets"].append(copy.deepcopy(manifest["owner_closure_assets"][0]))
    with pytest.raises(
        ConformanceValidationError, match="owner_closure_assets contains duplicates"
    ):
        assert_manifest_ordering(manifest)


def test_formal_input_and_owner_logical_name_collision_rejected(tmp_path: Path) -> None:
    import copy
    import shutil

    from gateway_conformance.scenario.identity import assert_manifest_ordering

    dest = tmp_path / "data" / "canonical-row-hashes" / "mixed-scalars"
    shutil.copytree(FORMAL_MIXED_SCALARS, dest)
    closure = load_scenario_closure(dest)
    manifest = copy.deepcopy(closure.manifest)
    manifest["owner_closure_assets"][0]["logical_name"] = "table-stream"
    with pytest.raises(ConformanceValidationError, match="share logical_name"):
        assert_manifest_ordering(manifest)
