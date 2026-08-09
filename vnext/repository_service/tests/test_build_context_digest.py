"""Unit tests for repository-service Docker build context digests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from support.build_context_digest import (
    compute_build_revision,
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
def test_build_revision_clean_vs_dirty(tmp_path: Path) -> None:
    vnext_root = tmp_path / "vnext"
    _seed_vnext_layout(vnext_root)
    head = "abc123def456"

    with (
        patch(
            "support.build_context_digest.is_build_context_clean",
            return_value=True,
        ),
        patch(
            "support.build_context_digest.subprocess.run",
            return_value=type("Completed", (), {"stdout": f"{head}\n"})(),
        ),
    ):
        assert compute_build_revision(vnext_root=vnext_root) == head

    with (
        patch(
            "support.build_context_digest.is_build_context_clean",
            return_value=False,
        ),
        patch(
            "support.build_context_digest.subprocess.run",
            return_value=type("Completed", (), {"stdout": f"{head}\n"})(),
        ),
    ):
        revision = compute_build_revision(vnext_root=vnext_root)

    expected_suffix = compute_source_tree_sha256(vnext_root=vnext_root).removeprefix("sha256:")[:12]
    assert revision == f"{head}-dirty-{expected_suffix}"
