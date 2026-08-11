"""Tests for CommitId path transport encoding."""

from __future__ import annotations

import pytest

from gateway_repository_contracts.path_transport import (
    decode_commit_id_path_segment,
    encode_commit_id_path_segment,
)

_COMMIT_ID_MATRIX = (
    ".",
    "..",
    "/",
    "%",
    "?",
    "#",
    "a b",
    "中文",
    "abc/def",
    "commit-c1",
)


@pytest.mark.parametrize("commit_id", _COMMIT_ID_MATRIX)
def test_commit_id_path_transport_roundtrip(commit_id: str) -> None:
    encoded = encode_commit_id_path_segment(commit_id)
    assert "/" not in encoded
    assert encoded not in {".", ".."}
    assert decode_commit_id_path_segment(encoded) == commit_id


def test_decode_rejects_empty_segment() -> None:
    with pytest.raises(ValueError, match="invalid"):
        decode_commit_id_path_segment("")


def test_decode_rejects_invalid_base64url() -> None:
    with pytest.raises(ValueError, match="base64url|invalid"):
        decode_commit_id_path_segment("!!!")
