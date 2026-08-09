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
