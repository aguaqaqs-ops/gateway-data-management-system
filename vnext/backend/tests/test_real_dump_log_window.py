"""Exact HTTP target attribution for the real-dump evidence windows."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

pytestmark = pytest.mark.unit

REPOSITORY = "00000000-0000-0000-0000-000000000001"
LOGICAL_COMMIT = "commit-c1"
PATH_PREFIX = f"/v1/repositories/{REPOSITORY}/versioned/commits/Y29tbWl0LWMx"
INVALID_REQUESTS = (
    (f'"GET /v1/repositories/00000000-0000-0000-0000-000000000002/versioned/commits/Y29tbWl0LWMx/catalog HTTP/1.1" 200 OK\n', "exact repository/commit"),
    (f'"GET /v1/repositories/{REPOSITORY}/versioned/commits/Y29tbWl0LWMy/rows?table_name=t HTTP/1.1" 200 OK\n', "exact repository/commit"),
    (f'"GET {PATH_PREFIX}/rows?table_name=t HTTP/1.1" 503 Service Unavailable\n', "HTTP successful"),
)


def _load_access_counts() -> Callable[[str, str, str], tuple[int, int]]:
    path = (Path(__file__).resolve().parents[3] / "docs/backend-vnext/refactoring/formal/"
            "plans/p6-s6-assets/t4-evidence.py")
    spec = importlib.util.spec_from_file_location("s6_t4_evidence", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    original_path = sys.path[:]
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = original_path
    return cast(Callable[[str, str, str], tuple[int, int]], module.repository_access_counts)


ACCESS_COUNTS = _load_access_counts()


def test_log_window_counts_canonical_commit_path() -> None:
    log = (f'"GET {PATH_PREFIX}/catalog HTTP/1.1" 200 OK\n'
           f'"GET {PATH_PREFIX}/rows?table_name=t HTTP/1.1" 200 OK\n'
           '"GET /readyz HTTP/1.1" 200 OK\n')
    assert ACCESS_COUNTS(log, REPOSITORY, LOGICAL_COMMIT) == (1, 1)


def test_log_window_keeps_zero_data_reads_separate_from_healthchecks() -> None:
    assert ACCESS_COUNTS('"GET /readyz HTTP/1.1" 200 OK\n', REPOSITORY, LOGICAL_COMMIT) == (0, 0)


@pytest.mark.parametrize(("request_line", "message"), INVALID_REQUESTS)
def test_log_window_rejects_other_targets_and_unsuccessful_data_reads(
    request_line: str, message: str,
) -> None:
    with pytest.raises(RuntimeError, match=message):
        ACCESS_COUNTS(request_line, REPOSITORY, LOGICAL_COMMIT)
