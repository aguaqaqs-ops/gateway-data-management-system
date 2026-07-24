"""Scenario digest sensitivity and ordering tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.scenario.digest import (
    compute_fixture_content_digest,
    compute_input_digest,
)
from gateway_shared_kernel import raw_blob_digest

from gateway_conformance.scenario.closure import ResolvedAsset, load_scenario_closure
from gateway_conformance.scenario.validate import validate_scenario
from support import build_valid_data_scenario, write_scenario_tree


def test_stale_input_digest_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "minimal"
    build_valid_data_scenario(root)
    text = (root / "scenario.yaml").read_text(encoding="utf-8")
    lines = []
    for line in text.splitlines():
        if line.startswith("input_digest:"):
            lines.append("input_digest: sha256:" + "d" * 64)
        else:
            lines.append(line)
    (root / "scenario.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ConformanceValidationError, match="input_digest"):
        validate_scenario(root)


def test_stale_fixture_digest_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "minimal"
    build_valid_data_scenario(root)
    text = (root / "scenario.yaml").read_text(encoding="utf-8")
    lines = []
    for line in text.splitlines():
        if line.startswith("fixture_content_digest:"):
            lines.append("fixture_content_digest: sha256:" + "e" * 64)
        else:
            lines.append(line)
    (root / "scenario.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ConformanceValidationError, match="fixture_content_digest"):
        validate_scenario(root)


def test_input_change_changes_fixture_digest_but_fixture_projection_excludes_self(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data" / "test-capability" / "minimal"
    build_valid_data_scenario(root)
    closure = load_scenario_closure(root)
    before_fixture = compute_fixture_content_digest(closure)
    before_input = compute_input_digest(closure.manifest, closure.assets)

    text = (
        (root / "scenario.yaml")
        .read_text(encoding="utf-8")
        .replace(
            '{"action":"run"}',
            '{"action":"changed"}',
        )
    )
    (root / "scenario.yaml").write_text(text, encoding="utf-8")
    closure2 = load_scenario_closure(root)
    after_input = compute_input_digest(closure2.manifest, closure2.assets)
    after_fixture = compute_fixture_content_digest(closure2)

    assert before_input != after_input
    assert before_fixture != after_fixture


def test_directory_enumeration_order_does_not_affect_fixture_digest(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "minimal"
    build_valid_data_scenario(root)
    closure = load_scenario_closure(root)
    digest_a = compute_fixture_content_digest(closure)
    digest_b = compute_fixture_content_digest(closure)
    assert digest_a == digest_b


def test_schema_binding_change_changes_input_digest() -> None:
    from copy import deepcopy

    from support import base_manifest, structured_input_asset

    manifest, _ = base_manifest(scenario_suffix="structured-input")
    payload, asset = structured_input_asset()
    manifest["input_assets"] = [asset]
    resolved = ResolvedAsset(
        logical_name="table",
        relative_path=asset["path"],
        raw=payload,
        media_type="application/json",
        structured=True,
        content_digest=asset["content_digest"],
    )
    before = compute_input_digest(manifest, {"table": resolved})
    mutated = deepcopy(manifest)
    mutated["input_assets"][0]["content_binding"]["schema_id"] = "gateway-vnext.test-result.v1"
    after = compute_input_digest(mutated, {"table": resolved})
    assert before != after


def test_golden_pretty_format_does_not_change_fixture_digest(tmp_path: Path) -> None:
    import json

    root = tmp_path / "data" / "test-capability" / "minimal"
    manifest = build_valid_data_scenario(root)
    before = manifest["fixture_content_digest"]
    golden_path = root / "expected" / "result.golden.json"
    pretty_bytes = (
        json.dumps(json.loads(golden_path.read_text(encoding="utf-8")), indent=2) + "\n"
    ).encode("utf-8")
    manifest["expected"][0]["size_bytes"] = len(pretty_bytes)
    manifest["expected"][0]["raw_sha256"] = raw_blob_digest(pretty_bytes).value
    write_scenario_tree(root, manifest, golden_bytes=pretty_bytes)
    closure = load_scenario_closure(root)
    assert compute_fixture_content_digest(closure) == before
