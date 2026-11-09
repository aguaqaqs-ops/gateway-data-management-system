"""Exact HTTP target attribution for the real-dump evidence windows."""

from __future__ import annotations

import pytest

from benchmarks.real_dump_log_window import repository_access_counts

pytestmark = pytest.mark.unit

REPOSITORY = "00000000-0000-0000-0000-000000000001"
LOGICAL_COMMIT = "commit-c1"
PATH_PREFIX = f"/v1/repositories/{REPOSITORY}/versioned/commits/Y29tbWl0LWMx"
INVALID_REQUESTS = (
    ('"GET /v1/repositories/00000000-0000-0000-0000-000000000002/versioned/commits/Y29tbWl0LWMx/catalog HTTP/1.1" 200 OK\n', "exact repository/commit"),
    (f'"GET /v1/repositories/{REPOSITORY}/versioned/commits/Y29tbWl0LWMy/rows?table_name=t HTTP/1.1" 200 OK\n', "exact repository/commit"),
    (f'"GET {PATH_PREFIX}/rows?table_name=t HTTP/1.1" 503 Service Unavailable\n', "HTTP successful"),
)


def test_log_window_counts_canonical_commit_path() -> None:
    log = (f'"GET {PATH_PREFIX}/catalog HTTP/1.1" 200 OK\n'
           f'"GET {PATH_PREFIX}/rows?table_name=t HTTP/1.1" 200 OK\n'
           '"GET /readyz HTTP/1.1" 200 OK\n')
    assert repository_access_counts(log, REPOSITORY, LOGICAL_COMMIT) == (1, 1)


def test_log_window_keeps_zero_data_reads_separate_from_healthchecks() -> None:
    assert repository_access_counts('"GET /readyz HTTP/1.1" 200 OK\n', REPOSITORY, LOGICAL_COMMIT) == (0, 0)


@pytest.mark.parametrize(("request_line", "message"), INVALID_REQUESTS)
def test_log_window_rejects_other_targets_and_unsuccessful_data_reads(
    request_line: str, message: str,
) -> None:
    with pytest.raises(RuntimeError, match=message):
        repository_access_counts(request_line, REPOSITORY, LOGICAL_COMMIT)
