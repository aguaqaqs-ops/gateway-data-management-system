"""Fail-closed layout checks for repository artifact ancestor paths."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gateway_repository_service.artifact_layout import prepare_artifact_layout
from gateway_repository_service.artifact_root import ArtifactRootError
from gateway_repository_service.layout import DurableLayout, LayoutError, repository_key
from gateway_repository_service.mutation_reconciliation import (
    SynchronousMutationReconciler,
    upload_staging_files_for_artifact,
)
from support.artifact_cleanup_contract import ARTIFACT_ID, REPOSITORY_ID


def _plant_escaped_repository(tmp_path: Path) -> tuple[DurableLayout, Path, Path]:
    layout = DurableLayout.create_for_probe(tmp_path / "data-root")
    outside = tmp_path / "outside"
    (outside / "staging").mkdir(parents=True)
    (outside / "ready").mkdir()
    staging_sentinel = outside / "staging" / f"{ARTIFACT_ID.hex}.aaaaaaaaaaaa"
    ready_sentinel = outside / "ready" / "keep-me"
    staging_sentinel.write_bytes(b"staging-sentinel")
    ready_sentinel.write_bytes(b"ready-sentinel")
    repo = layout.artifacts / repository_key(REPOSITORY_ID)
    repo.symlink_to(outside)
    return layout, staging_sentinel, ready_sentinel


def _assert_sentinels_intact(staging_sentinel: Path, ready_sentinel: Path) -> None:
    assert staging_sentinel.is_file()
    assert staging_sentinel.read_bytes() == b"staging-sentinel"
    assert ready_sentinel.is_file()
    assert ready_sentinel.read_bytes() == b"ready-sentinel"


def test_repository_symlink_does_not_escape_artifacts_root(tmp_path: Path) -> None:
    layout, staging_sentinel, ready_sentinel = _plant_escaped_repository(tmp_path)
    key = repository_key(REPOSITORY_ID)

    with pytest.raises(LayoutError, match="symlink or non-directory"):
        layout.repository_artifact_directories(key)
    _assert_sentinels_intact(staging_sentinel, ready_sentinel)

    with pytest.raises(LayoutError, match="symlink or non-directory"):
        upload_staging_files_for_artifact(layout, REPOSITORY_ID, ARTIFACT_ID)
    _assert_sentinels_intact(staging_sentinel, ready_sentinel)

    reconciler = SynchronousMutationReconciler(
        settings=MagicMock(),
        layout=layout,
        mutation_store=MagicMock(),
        import_store=MagicMock(),
    )
    with pytest.raises(LayoutError, match="symlink or non-directory"):
        reconciler._cleanup_upload_staging(REPOSITORY_ID, ARTIFACT_ID)  # noqa: SLF001
    _assert_sentinels_intact(staging_sentinel, ready_sentinel)

    with pytest.raises(ArtifactRootError, match="symlink"):
        prepare_artifact_layout(
            data_root=layout.root,
            artifacts=layout.artifacts,
            gateway_uid=os.getuid(),
            gateway_gid=os.getgid(),
        )
    _assert_sentinels_intact(staging_sentinel, ready_sentinel)


def test_staging_symlink_is_rejected_without_touching_outside(tmp_path: Path) -> None:
    layout = DurableLayout.create_for_probe(tmp_path / "data-root")
    outside = tmp_path / "outside-staging"
    outside.mkdir()
    sentinel = outside / f"{ARTIFACT_ID.hex}.aaaaaaaaaaaa"
    sentinel.write_bytes(b"staging-sentinel")
    key = repository_key(REPOSITORY_ID)
    repo = layout.artifacts / key
    repo.mkdir()
    (repo / "ready").mkdir()
    (repo / "staging").symlink_to(outside)

    with pytest.raises(LayoutError, match="staging is a symlink or non-directory"):
        layout.repository_artifact_directories(key)
    assert sentinel.is_file()
    assert sentinel.read_bytes() == b"staging-sentinel"

    with pytest.raises(ArtifactRootError, match="symlink"):
        prepare_artifact_layout(
            data_root=layout.root,
            artifacts=layout.artifacts,
            gateway_uid=os.getuid(),
            gateway_gid=os.getgid(),
        )
    assert sentinel.is_file()
    assert sentinel.read_bytes() == b"staging-sentinel"
