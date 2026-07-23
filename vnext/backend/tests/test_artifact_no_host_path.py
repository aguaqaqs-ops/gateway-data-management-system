"""Location independence and path-confusion rejection tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gateway_backend.artifacts import (
    artifact_ref_from_dict,
    assert_no_host_path_identity,
    build_logical_ref,
)

VECTOR_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "vectors" / "artifacts" / "v1"


@pytest.mark.parametrize(
    "payload",
    [
        {"host_path": "/tmp/x"},
        {"artifact_root": "/workspace/artifacts"},
        {"logical_ref": "/tmp/artifact.arrow"},
        {"logical_ref": "C:\\temp\\artifact.arrow"},
        {"logical_ref": "\\\\server\\share\\artifact.arrow"},
        {"logical_ref": "file:///tmp/artifact.arrow"},
        {"logical_ref": "../artifact.arrow"},
        {"logical_ref": "safe/../artifact.arrow"},
        {"logical_ref": "safe%2f..%2fartifact.arrow"},
        {"logical_ref": "safe\x00artifact"},
    ],
)
def test_identity_rejects_host_path_or_encoding_confusion(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        assert_no_host_path_identity(payload)


@pytest.mark.parametrize(
    ("namespace", "artifact_id"),
    [
        ("", "item"),
        ("canonical-row-hash", ""),
        ("..", "item"),
        ("canonical-row-hash", ".."),
        ("canonical-row-hash", "a/b"),
        ("canonical-row-hash", "a\\b"),
        ("canonical-row-hash", "%2e%2e"),
        ("Canonical", "item"),
        ("canonical", "item_1"),
    ],
)
def test_logical_ref_builder_rejects_invalid_segments(namespace: str, artifact_id: str) -> None:
    with pytest.raises(ValueError):
        build_logical_ref(namespace, artifact_id)


def test_host_path_fixture_rejected_before_schema_or_dto_construction() -> None:
    payload = json.loads((VECTOR_ROOT / "invalid" / "ref-with-host-path.json").read_text())
    with pytest.raises(ValueError, match="forbidden key 'host_path'"):
        artifact_ref_from_dict(payload)


def test_logical_ref_is_not_a_host_or_file_uri() -> None:
    logical_ref = build_logical_ref("canonical-row-hash", "example-0001")
    assert logical_ref == ("gateway-vnext.artifacts/v1/ref/canonical-row-hash/example-0001")
    assert not logical_ref.startswith(("/", "file:", "\\\\"))
    assert "\\" not in logical_ref
    assert "%" not in logical_ref
