"""URL path helpers for Repository Client requests."""

from __future__ import annotations

from urllib.parse import quote


def encode_path_segment(value: str) -> str:
    """Percent-encode a single opaque path segment without changing its semantics."""

    return quote(value, safe="")
