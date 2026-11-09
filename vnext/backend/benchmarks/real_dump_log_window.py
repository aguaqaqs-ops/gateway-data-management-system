"""Exact Repository HTTP attribution for isolated real-dump log windows."""

from __future__ import annotations

import re

from gateway_repository_contracts import encode_commit_id_path_segment


def repository_access_counts(text: str, repository_id: str, commit_id: str) -> tuple[int, int]:
    prefix = (
        r'"GET /v1/repositories/' + re.escape(repository_id)
        + r'/versioned/commits/' + re.escape(encode_commit_id_path_segment(commit_id))
    )
    rows = re.findall(prefix + r'/rows\?[^\s"]* HTTP/[^\s"]+" (\d{3})', text)
    catalogs = re.findall(prefix + r'/catalog HTTP/[^\s"]+" (\d{3})', text)
    # Reject other targets even when the expected target has no matches.
    all_rows = re.findall(
        r'"GET /v1/repositories/[^\s"]+/versioned/commits/[^\s"]+/rows\?[^\s"]* HTTP/',
        text,
    )
    all_catalogs = re.findall(
        r'"GET /v1/repositories/[^\s"]+/versioned/commits/[^\s"]+/catalog HTTP/',
        text,
    )
    if len(rows) != len(all_rows) or len(catalogs) != len(all_catalogs):
        raise RuntimeError("all actual data HTTP scoped to exact repository/commit")
    if any(status != "200" for status in rows + catalogs):
        raise RuntimeError("actual RS data HTTP successful")
    return len(rows), len(catalogs)
