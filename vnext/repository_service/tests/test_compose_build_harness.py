"""Unit tests for compose build provenance helpers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from support import compose_build_harness as harness


@pytest.mark.unit
def test_image_matches_build_context_requires_matching_labels() -> None:
    with (
        patch.object(harness, "expected_build_metadata", return_value=("sha256:abc", "rev-1")),
        patch.object(
            harness,
            "image_labels",
            return_value={
                harness.SOURCE_TREE_LABEL: "sha256:abc",
                harness.REVISION_LABEL: "rev-1",
            },
        ),
    ):
        assert harness.image_matches_build_context("gateway-repository-service:local")


@pytest.mark.unit
def test_image_matches_build_context_rejects_stale_labels() -> None:
    with (
        patch.object(harness, "expected_build_metadata", return_value=("sha256:new", "rev-dirty")),
        patch.object(
            harness,
            "image_labels",
            return_value={
                harness.SOURCE_TREE_LABEL: "sha256:old",
                harness.REVISION_LABEL: "rev-old",
            },
        ),
    ):
        assert not harness.image_matches_build_context("gateway-repository-service:local")


@pytest.mark.unit
def test_ensure_repository_service_image_rebuilds_when_labels_stale() -> None:
    with (
        patch.object(harness, "image_matches_build_context", side_effect=[False, True]),
        patch.object(harness, "_run_build") as run_build,
    ):
        image = harness.ensure_repository_service_image()
        assert image == harness.DEFAULT_IMAGE
        run_build.assert_called_once_with(harness.DEFAULT_IMAGE)


@pytest.mark.unit
def test_ensure_repository_service_image_skips_rebuild_when_labels_match() -> None:
    with (
        patch.object(harness, "image_matches_build_context", return_value=True),
        patch.object(harness, "_run_build") as run_build,
    ):
        image = harness.ensure_repository_service_image()
        assert image == harness.DEFAULT_IMAGE
        run_build.assert_not_called()


@pytest.mark.unit
def test_dependency_base_matches_lock_requires_matching_label() -> None:
    lock_sha = "9129e908087b7168fec966ea8339fcd3200a3402357fa5eb7ef75f060a9e41fe"
    with patch.object(
        harness,
        "image_labels",
        return_value={harness.UV_LOCK_LABEL: lock_sha},
    ):
        assert harness.dependency_base_matches_lock("gateway-p2r1-repository:lock-9129e908087b", lock_sha)


@pytest.mark.unit
def test_dependency_base_matches_lock_rejects_stale_label() -> None:
    current = harness.current_uv_lock_sha256()
    with patch.object(
        harness,
        "image_labels",
        return_value={harness.UV_LOCK_LABEL: "fce9185b59b654729670c618c352f9f7a458fb2de40bbd2e088158e81a771e65"},
    ):
        assert not harness.dependency_base_matches_lock("gateway-p2r1-repository:lock-fce9185b59b6", current)
