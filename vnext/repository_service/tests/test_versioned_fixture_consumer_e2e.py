"""External-process E2E for the public Versioned fixture consumer."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest

from support.versioned_fixture_consumer_harness import (
    FixtureConsumerEnvironment,
    run_fixture_consumer_subprocess,
    shutdown_fixture_consumer_environment,
    start_fixture_consumer_environment,
)

pytestmark = [pytest.mark.integration, pytest.mark.serial]


def test_public_versioned_fixture_consumer_c1_c2_immutable_reads(tmp_path: Path) -> None:
    bearer_token = secrets.token_urlsafe(24)
    env: FixtureConsumerEnvironment | None = None
    result = None
    try:
        env = start_fixture_consumer_environment(tmp_path, bearer_token=bearer_token)
        result = run_fixture_consumer_subprocess(env)
        assert result.timed_out is False
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.summary is not None, result.stdout + result.stderr
        summary = result.summary
        assert summary.get("status") == "ok"
        c0 = summary.get("c0")
        c1 = summary.get("c1")
        c2 = summary.get("c2")
        main_commit = summary.get("main_commit")
        assert isinstance(c0, str) and c0
        assert isinstance(c1, str) and c1
        assert isinstance(c2, str) and c2
        assert isinstance(main_commit, str) and main_commit
        assert len({c0, c1, c2}) == 3
        assert main_commit == c2
        assert bearer_token not in result.stdout
        assert bearer_token not in result.stderr
    finally:
        shutdown_fixture_consumer_environment(env)
