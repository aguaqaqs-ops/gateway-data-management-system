"""Compose gate provenance helpers."""

from __future__ import annotations

import subprocess

import pytest

from tests.support.compose_gate_harness import (
    REPO_ROOT,
    SOURCE_TREE_SHA_DIRTY_COMMAND,
    SOURCE_TREE_SHA_EXCLUDES,
    source_tree_sha_for_provenance,
)

pytestmark = pytest.mark.unit


def _git_head_tree_sha() -> str:
    completed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD^{tree}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    if completed.returncode != 0:
        pytest.fail(f"git rev-parse HEAD^{{tree}} failed: {completed.stderr}")
    return completed.stdout.strip()


def test_source_tree_sha_dirty_worktree_is_reproducible_and_differs_from_head_tree() -> None:
    tree_sha, worktree_clean, command = source_tree_sha_for_provenance()
    if worktree_clean:
        pytest.skip("worktree is clean; dirty-tree provenance assertions do not apply")
    assert command == SOURCE_TREE_SHA_DIRTY_COMMAND
    assert "GIT_INDEX_FILE" in command
    assert "add -A" in command
    assert tree_sha != _git_head_tree_sha()
    repeat_sha, repeat_clean, repeat_command = source_tree_sha_for_provenance()
    assert repeat_clean is False
    assert repeat_command == command
    assert repeat_sha == tree_sha
    assert SOURCE_TREE_SHA_EXCLUDES.startswith("full repo tree via temporary index")
