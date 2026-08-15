"""Unit tests for compose build provenance helpers."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from support.build_context_digest import ImageIdentity
from support import compose_build_harness as harness

_SHA_A = "a" * 40
_SHA_B = "b" * 40
_TREE = "sha256:" + "c" * 64
_LOCK = "d" * 64
_IMAGE_ID = "sha256:" + "e" * 64
_OTHER_IMAGE_ID = "sha256:" + "f" * 64
_IDENTITY = ImageIdentity(
    candidate_sha=_SHA_A,
    build_input_revision=_SHA_B,
    source_tree_sha256=_TREE,
)


def _valid_labels() -> dict[str, str]:
    return {
        harness.CANDIDATE_LABEL: _SHA_A,
        harness.BUILD_INPUT_LABEL: _SHA_B,
        harness.SOURCE_TREE_LABEL: _TREE,
        harness.UV_LOCK_LABEL: _LOCK,
    }


IMAGE_MATCH_FAULTS: tuple[tuple[str, dict[str, str], str], ...] = (
    (
        "missing-candidate",
        {key: value for key, value in _valid_labels().items() if key != harness.CANDIDATE_LABEL},
        _IMAGE_ID,
    ),
    ("stale-candidate", {**_valid_labels(), harness.CANDIDATE_LABEL: "0" * 40}, _IMAGE_ID),
    ("malformed-candidate", {**_valid_labels(), harness.CANDIDATE_LABEL: "not-a-sha"}, _IMAGE_ID),
    (
        "missing-build-input",
        {key: value for key, value in _valid_labels().items() if key != harness.BUILD_INPUT_LABEL},
        _IMAGE_ID,
    ),
    ("stale-build-input", {**_valid_labels(), harness.BUILD_INPUT_LABEL: "0" * 40}, _IMAGE_ID),
    ("malformed-build-input", {**_valid_labels(), harness.BUILD_INPUT_LABEL: "short"}, _IMAGE_ID),
    (
        "missing-source-tree",
        {key: value for key, value in _valid_labels().items() if key != harness.SOURCE_TREE_LABEL},
        _IMAGE_ID,
    ),
    ("stale-source-tree", {**_valid_labels(), harness.SOURCE_TREE_LABEL: "sha256:" + "0" * 64}, _IMAGE_ID),
    ("malformed-source-tree", {**_valid_labels(), harness.SOURCE_TREE_LABEL: "sha256:abcd"}, _IMAGE_ID),
    (
        "missing-lock",
        {key: value for key, value in _valid_labels().items() if key != harness.UV_LOCK_LABEL},
        _IMAGE_ID,
    ),
    ("stale-lock", {**_valid_labels(), harness.UV_LOCK_LABEL: "0" * 64}, _IMAGE_ID),
    ("malformed-lock", {**_valid_labels(), harness.UV_LOCK_LABEL: "lock"}, _IMAGE_ID),
    ("empty-image-id", _valid_labels(), ""),
    ("tag-image-id", _valid_labels(), "gateway-repository-service:local"),
    ("short-image-id", _valid_labels(), "sha256:abcd"),
)


def _assert_no_secret_leak(text: str) -> None:
    lowered = text.lower()
    assert "token" not in lowered
    assert "http_proxy" not in lowered
    assert "https_proxy" not in lowered
    assert "bearer" not in lowered
    assert "provenance pass" not in lowered


@pytest.mark.unit
def test_run_build_timeout_raises_runtime_error() -> None:
    with (
        patch.object(harness, "BUILD_SCRIPT", harness.BUILD_SCRIPT),
        patch.object(harness, "expected_build_metadata", return_value=_IDENTITY),
        patch.object(harness, "current_uv_lock_sha256", return_value=_LOCK),
        patch(
            "support.compose_build_harness.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["bash"], timeout=1800),
        ),
    ):
        with pytest.raises(RuntimeError, match="timed out after 1800s") as exc_info:
            harness._run_build(harness.DEFAULT_IMAGE)
    _assert_no_secret_leak(str(exc_info.value))


@pytest.mark.unit
def test_run_build_sets_helper_identity_env_not_legacy_revision() -> None:
    captured: dict[str, str] = {}

    def fake_run(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        env = kwargs["env"]
        assert isinstance(env, dict)
        captured.update({str(key): str(value) for key, value in env.items()})
        return subprocess.CompletedProcess(args=["bash"], returncode=0, stdout="", stderr="")

    with (
        patch.object(harness, "expected_build_metadata", return_value=_IDENTITY),
        patch.object(harness, "current_uv_lock_sha256", return_value=_LOCK),
        patch("support.compose_build_harness.subprocess.run", side_effect=fake_run),
    ):
        harness._run_build(harness.DEFAULT_IMAGE)

    assert captured["GATEWAY_P2R1_CANDIDATE_SHA"] == _SHA_A
    assert captured["GATEWAY_P2R1_BUILD_INPUT_REVISION"] == _SHA_B
    assert captured["GATEWAY_P2R1_SOURCE_TREE_SHA256"] == _TREE
    assert captured["GATEWAY_P2R1_UV_LOCK_SHA256"] == _LOCK


@pytest.mark.unit
def test_image_matches_build_context_requires_all_fields() -> None:
    with (
        patch.object(harness, "expected_build_metadata", return_value=_IDENTITY),
        patch.object(harness, "current_uv_lock_sha256", return_value=_LOCK),
        patch.object(harness, "image_id", return_value=_IMAGE_ID),
        patch.object(harness, "image_labels", return_value=_valid_labels()),
    ):
        assert harness.image_matches_build_context("gateway-repository-service:local")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("labels", "image_digest"),
    [(labels, image_digest) for _name, labels, image_digest in IMAGE_MATCH_FAULTS],
    ids=[name for name, _labels, _image_digest in IMAGE_MATCH_FAULTS],
)
def test_image_matches_build_context_rejects_faults(
    labels: dict[str, str],
    image_digest: str,
) -> None:
    with (
        patch.object(harness, "expected_build_metadata", return_value=_IDENTITY),
        patch.object(harness, "current_uv_lock_sha256", return_value=_LOCK),
        patch.object(harness, "image_id", return_value=image_digest),
        patch.object(harness, "image_labels", return_value=labels),
    ):
        assert not harness.image_matches_build_context("gateway-repository-service:local")


@pytest.mark.unit
def test_image_id_distinguishes_immutable_digests() -> None:
    def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        image = args[-1]
        digest = _IMAGE_ID if image.endswith(":current") else _OTHER_IMAGE_ID
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=f"{digest}\n", stderr="")

    with patch("support.compose_build_harness.subprocess.run", side_effect=fake_run):
        assert harness.image_id("gateway-repository-service:current") == _IMAGE_ID
        assert harness.image_id("gateway-repository-service:stale") == _OTHER_IMAGE_ID
        assert harness.image_id("gateway-repository-service:current") != harness.image_id(
            "gateway-repository-service:stale"
        )


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
