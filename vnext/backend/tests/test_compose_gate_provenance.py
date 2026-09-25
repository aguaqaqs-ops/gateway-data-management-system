"""Compose gate provenance helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.support.compose_gate_harness import (
    SOURCE_TREE_SHA_DIRTY_COMMAND,
    SOURCE_TREE_SHA_EXCLUDES,
    source_tree_sha_for_provenance,
)

pytestmark = pytest.mark.unit


def _git_head_tree_sha(repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD^{tree}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    if completed.returncode != 0:
        pytest.fail(f"git rev-parse HEAD^{{tree}} failed: {completed.stderr}")
    return completed.stdout.strip()


@pytest.fixture
def dirty_git_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    tracked = repo_root / "tracked.txt"
    tracked.write_text("initial\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        env={"GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.com", "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.com"},
    )
    tracked.write_text("dirty\n", encoding="utf-8")
    return repo_root


def test_source_tree_sha_dirty_worktree_is_reproducible_and_differs_from_head_tree(
    dirty_git_repo: Path,
) -> None:
    tree_sha, worktree_clean, command = source_tree_sha_for_provenance(dirty_git_repo)
    assert worktree_clean is False
    assert command == SOURCE_TREE_SHA_DIRTY_COMMAND
    assert "GIT_INDEX_FILE" in command
    assert "add -A" in command
    assert tree_sha != _git_head_tree_sha(dirty_git_repo)
    repeat_sha, repeat_clean, repeat_command = source_tree_sha_for_provenance(dirty_git_repo)
    assert repeat_clean is False
    assert repeat_command == command
    assert repeat_sha == tree_sha
    assert SOURCE_TREE_SHA_EXCLUDES.startswith("full repo tree via temporary index")
