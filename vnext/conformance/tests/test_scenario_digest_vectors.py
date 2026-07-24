"""Normative scenario digest vector conformance."""

from __future__ import annotations

import base64
import json
from typing import Any, cast
from pathlib import Path

import pytest

from gateway_shared_kernel import DigestKind, semantic_digest

from gateway_conformance.paths import SCENARIO_DIGEST_VECTOR_ROOT
from gateway_conformance.scenario import closure as closure_mod
from gateway_conformance.scenario.closure import load_scenario_closure
from gateway_conformance.scenario.digest import (
    compute_fixture_content_digest,
    compute_input_digest,
)
from support import (
    build_valid_data_scenario,
    build_valid_owner_closure_v2_scenario,
    build_valid_shared_structured_input_scenario,
    build_valid_structured_input_scenario,
)


def _load_jsonl(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        rows[str(item["case_id"])] = item
    return rows


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _build_shared_structured(
    root: Path, *, shared_root: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    monkeypatch.setattr(closure_mod, "SHARED_ROOT", shared_root)
    return cast(
        dict[str, Any],
        build_valid_shared_structured_input_scenario(root, shared_root=shared_root),
    )


@pytest.mark.parametrize(
    ("builder_name", "case_id"),
    [
        ("data", "minimal-data"),
        ("structured", "structured-input"),
        ("shared-structured", "shared-structured-input"),
        ("owner-closure-v2", "owner-closure-v2"),
    ],
)
def test_normative_input_and_fixture_digests_match_vectors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    builder_name: str,
    case_id: str,
) -> None:
    vector_set = json.loads(
        (SCENARIO_DIGEST_VECTOR_ROOT / "vector-set.json").read_text(encoding="utf-8")
    )
    input_rows = _load_jsonl(SCENARIO_DIGEST_VECTOR_ROOT / "input-digest.jsonl")
    fixture_rows = _load_jsonl(SCENARIO_DIGEST_VECTOR_ROOT / "fixture-digest.jsonl")
    assert any(item["case_id"] == case_id for item in vector_set["cases"])

    root = tmp_path / "data" / "test-capability" / case_id
    if builder_name == "data":
        build_valid_data_scenario(root)
    elif builder_name == "structured":
        build_valid_structured_input_scenario(root)
    elif builder_name == "owner-closure-v2":
        build_valid_owner_closure_v2_scenario(root)
    else:
        shared_root = tmp_path / "fixtures" / "shared"
        _build_shared_structured(root, shared_root=shared_root, monkeypatch=monkeypatch)

    closure = load_scenario_closure(root)
    assert (
        compute_input_digest(closure.manifest, closure.assets)
        == input_rows[case_id]["input_digest"]
    )
    assert (
        compute_fixture_content_digest(closure) == fixture_rows[case_id]["fixture_content_digest"]
    )


@pytest.mark.parametrize(
    "case_id",
    ["minimal-data", "structured-input", "shared-structured-input", "owner-closure-v2"],
)
def test_independent_oracle_digest_from_fixed_preimage(case_id: str) -> None:
    """Oracle uses only shared-kernel digest API + fixed vector frame bytes."""
    input_rows = _load_jsonl(SCENARIO_DIGEST_VECTOR_ROOT / "input-digest.jsonl")
    fixture_rows = _load_jsonl(SCENARIO_DIGEST_VECTOR_ROOT / "fixture-digest.jsonl")
    input_frame = _b64url_decode(input_rows[case_id]["collection_frame_base64url"])
    fixture_frame = _b64url_decode(fixture_rows[case_id]["collection_frame_base64url"])
    assert (
        semantic_digest(DigestKind.SCENARIO_INPUT, input_frame).digest_ref.value
        == input_rows[case_id]["input_digest"]
    )
    assert (
        semantic_digest(DigestKind.SCENARIO_FIXTURE, fixture_frame).digest_ref.value
        == fixture_rows[case_id]["fixture_content_digest"]
    )


def test_shared_structured_closure_child_uses_owner_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gateway_conformance.scenario.digest import _closure_entries, _digest_ref_to_raw

    root = tmp_path / "data" / "test-capability" / "shared-structured-input"
    shared_root = tmp_path / "fixtures" / "shared"
    _build_shared_structured(root, shared_root=shared_root, monkeypatch=monkeypatch)
    closure = load_scenario_closure(root)
    asset = next(iter(closure.assets.values()))
    assert asset.structured and asset.content_digest is not None
    entries = dict(_closure_entries(closure))
    assert entries[asset.relative_path.encode("utf-8")] == _digest_ref_to_raw(asset.content_digest)


def test_owner_closure_v2_fixture_frame_ignores_owner_transport_metadata(
    tmp_path: Path,
) -> None:
    import copy
    from dataclasses import replace

    from gateway_conformance.scenario.digest import fixture_collection_frame_bytes

    root = tmp_path / "data" / "test-capability" / "owner-closure-v2"
    build_valid_owner_closure_v2_scenario(root)
    closure = load_scenario_closure(root)
    before = fixture_collection_frame_bytes(closure)
    manifest = copy.deepcopy(closure.manifest)
    owner = manifest["owner_closure_assets"][0]
    owner["size_bytes"] = 999
    owner["raw_sha256"] = "sha256:" + "f" * 64
    tampered = replace(closure, manifest=manifest)
    assert fixture_collection_frame_bytes(tampered) == before
