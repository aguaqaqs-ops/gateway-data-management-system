"""URL path helpers for Repository Client requests."""

from __future__ import annotations

from urllib.parse import quote

from gateway_repository_contracts import encode_commit_id_path_segment


def encode_path_segment(value: str) -> str:
    """Percent-encode a single opaque path segment without changing its semantics."""

    return quote(value, safe="")


def encode_commit_id_path(commit_id: str) -> str:
    """Encode a CommitId for use as a single HTTP path segment."""

    return encode_commit_id_path_segment(commit_id)
