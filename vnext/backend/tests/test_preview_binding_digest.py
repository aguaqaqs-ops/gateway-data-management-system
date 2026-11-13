"""The accepted Preview v2 binding preimage is a committed static vector."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_backend.application.preview_binding import derive_preview_ready_closure_digest
from tests.test_submit_transactions import _preview_result

pytestmark = pytest.mark.unit


def test_preview_binding_v2_matches_static_preimage_and_independent_raw_sha() -> None:
    vector_path = Path(__file__).resolve().parents[2] / "fixtures/golden/preview-ready-binding/v2.json"
    vector = json.loads(vector_path.read_text())
    expected = "v2:sha256:" + hashlib.sha256(canonicalize_json_value(vector["preimage"])).hexdigest()
    assert expected == vector["binding_digest"]
    assert derive_preview_ready_closure_digest(_preview_result(vector["fixture_workspace_id"])) == expected
