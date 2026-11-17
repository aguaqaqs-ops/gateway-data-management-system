"""The accepted Preview v3 binding preimage is a committed static vector."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_backend.application.preview_binding import derive_preview_ready_closure_digest
from gateway_backend.infrastructure.control_db.sqlite_workspace import preview_result_from_row

pytestmark = pytest.mark.unit


def test_preview_binding_v3_matches_static_preimage_and_independent_raw_sha() -> None:
    vector_path = (
        Path(__file__).resolve().parents[2] / "fixtures/golden/preview-ready-binding/v3.json"
    )
    vector = json.loads(vector_path.read_text())
    expected = (
        "v3:sha256:" + hashlib.sha256(canonicalize_json_value(vector["preimage"])).hexdigest()
    )
    assert expected == vector["binding_digest"]
    row = {
        **vector["preview_row"],
        "binding": canonicalize_json_value(vector["preview_row"]["binding"]),
    }
    assert derive_preview_ready_closure_digest(preview_result_from_row(row)) == expected


def test_preview_binding_changes_when_frozen_rule_equivalence_changes() -> None:
    vector_path = (
        Path(__file__).resolve().parents[2] / "fixtures/golden/preview-ready-binding/v3.json"
    )
    vector = json.loads(vector_path.read_text())
    row = {
        **vector["preview_row"],
        "binding": canonicalize_json_value(vector["preview_row"]["binding"]),
    }
    preview = preview_result_from_row(row)
    changed = replace(preview, canonical=replace(preview.canonical, rules_semantically_equal=False))
    assert derive_preview_ready_closure_digest(changed) != derive_preview_ready_closure_digest(
        preview
    )
