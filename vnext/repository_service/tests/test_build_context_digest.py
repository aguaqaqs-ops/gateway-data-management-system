"""Unit tests for repository-service Docker build context digests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from support.build_context_digest import (
    compute_build_input_revision,
    compute_build_revision,
    compute_head_sha,
    compute_source_tree_sha256,
)


def _seed_vnext_layout(vnext_root: Path) -> None:
    service_file = vnext_root / "repository_service" / "src" / "example.py"
    contracts_file = vnext_root / "repository_contracts" / "src" / "example.py"
    service_file.parent.mkdir(parents=True, exist_ok=True)
    contracts_file.parent.mkdir(parents=True, exist_ok=True)
    service_file.write_text("service\n", encoding="utf-8")
    contracts_file.write_text("contracts\n", encoding="utf-8")


@pytest.mark.unit
def test_content_digest_is_deterministic_for_same_tree(tmp_path: Path) -> None:
    vnext_root = tmp_path / "vnext"
    _seed_vnext_layout(vnext_root)
    first = compute_source_tree_sha256(vnext_root=vnext_root)
    second = compute_source_tree_sha256(vnext_root=vnext_root)
    assert first == second


@pytest.mark.unit
def test_content_digest_ignores_cache_artifacts(tmp_path: Path) -> None:
    vnext_root = tmp_path / "vnext"
    _seed_vnext_layout(vnext_root)

    baseline = compute_source_tree_sha256(vnext_root=vnext_root)

    cache_file = vnext_root / "repository_service" / ".pytest_cache" / "v" / "cache" / "nodeids"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text("ignored\n", encoding="utf-8")

    assert compute_source_tree_sha256(vnext_root=vnext_root) == baseline


@pytest.mark.unit
def test_build_input_revision_uses_last_commit_touching_build_paths(tmp_path: Path) -> None:
    vnext_root = tmp_path / "vnext"
    _seed_vnext_layout(vnext_root)
    build_input = "abc123def456"
    head = "fff000eee111"

    def _fake_run(command: list[str], **kwargs: object) -> object:
        if "log" in command and "--format=%H" in command:
            return type("Completed", (), {"stdout": f"{build_input}\n"})()
        if command[-2:] == ["rev-parse", "HEAD"]:
            return type("Completed", (), {"stdout": f"{head}\n"})()
        raise AssertionError(f"unexpected command: {command}")

    with patch("support.build_context_digest.subprocess.run", side_effect=_fake_run):
        assert compute_build_input_revision(vnext_root=vnext_root) == build_input
        assert compute_build_revision(vnext_root=vnext_root) == build_input
        assert compute_head_sha(vnext_root=vnext_root) == head
