"""Helpers for P2-R4 Compose end-to-end tests with retained build cache."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from support.build_context_digest import (
    ImageIdentity,
    compute_image_identity,
)

VNEXT_ROOT = Path(__file__).resolve().parents[3]
BUILD_SCRIPT = VNEXT_ROOT / "scripts" / "build-repository-service-image.sh"
DEFAULT_IMAGE = "gateway-repository-service:local"
UV_LOCK_PATH = VNEXT_ROOT / "repository_service" / "uv.lock"
CANDIDATE_LABEL = "org.opencontainers.image.revision"
BUILD_INPUT_LABEL = "gateway.p2r1.build-input-revision"
SOURCE_TREE_LABEL = "gateway.p2r1.source-tree-sha256"
UV_LOCK_LABEL = "gateway.p2r1.uv-lock-sha256"
BUILD_TIMEOUT_SECONDS = 1800
_IMAGE_ID_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def current_uv_lock_sha256() -> str:
    return hashlib.sha256(UV_LOCK_PATH.read_bytes()).hexdigest()


def dependency_base_image_for_lock(lock_sha256: str | None = None) -> str:
    digest = lock_sha256 if lock_sha256 is not None else current_uv_lock_sha256()
    return f"gateway-p2r1-repository:lock-{digest[:12]}"


def dependency_base_matches_lock(image: str, lock_sha256: str | None = None) -> bool:
    labels = image_labels(image)
    if not labels:
        return False
    expected = lock_sha256 if lock_sha256 is not None else current_uv_lock_sha256()
    return labels.get(UV_LOCK_LABEL) == expected


def resolve_service_image() -> str:
    return os.environ.get("GATEWAY_REPOSITORY_SERVICE_IMAGE", DEFAULT_IMAGE)


def image_id(image: str) -> str:
    completed = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def expected_build_metadata() -> ImageIdentity:
    return compute_image_identity(vnext_root=VNEXT_ROOT)


def image_labels(image: str) -> dict[str, str]:
    completed = subprocess.run(
        ["docker", "image", "inspect", image],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        return {}
    payload: list[dict[str, Any]] = json.loads(completed.stdout)
    if not payload:
        return {}
    config = payload[0].get("Config", {})
    labels = config.get("Labels", {})
    if not isinstance(labels, dict):
        return {}
    return {str(key): str(value) for key, value in labels.items()}


def image_matches_build_context(image: str) -> bool:
    current_id = image_id(image)
    if not _IMAGE_ID_DIGEST.fullmatch(current_id):
        return False
    labels = image_labels(image)
    if not labels:
        return False
    expected = expected_build_metadata()
    expected_lock = current_uv_lock_sha256()
    return (
        labels.get(CANDIDATE_LABEL) == expected.candidate_sha
        and labels.get(BUILD_INPUT_LABEL) == expected.build_input_revision
        and labels.get(SOURCE_TREE_LABEL) == expected.source_tree_sha256
        and labels.get(UV_LOCK_LABEL) == expected_lock
    )


def verify_transferred_image(expected_image_id: str, local_ref: str) -> bool:
    """Accept a loaded image only when immutable ID and labels match.

    Tag or name equality is not transfer proof.
    """

    if not _IMAGE_ID_DIGEST.fullmatch(expected_image_id):
        return False
    current_id = image_id(local_ref)
    if current_id != expected_image_id:
        return False
    return image_matches_build_context(local_ref)


def _run_build(image: str) -> None:
    if not BUILD_SCRIPT.is_file():
        raise RuntimeError(f"missing build script: {BUILD_SCRIPT}")
    expected = expected_build_metadata()
    env = os.environ.copy()
    env.setdefault("GATEWAY_REPOSITORY_SERVICE_IMAGE", image)
    env["GATEWAY_P2R1_CANDIDATE_SHA"] = expected.candidate_sha
    env["GATEWAY_P2R1_BUILD_INPUT_REVISION"] = expected.build_input_revision
    env["GATEWAY_P2R1_SOURCE_TREE_SHA256"] = expected.source_tree_sha256
    env["GATEWAY_P2R1_UV_LOCK_SHA256"] = current_uv_lock_sha256()
    try:
        completed = subprocess.run(
            ["bash", str(BUILD_SCRIPT)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            cwd=VNEXT_ROOT,
            timeout=BUILD_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"repository-service image build timed out after {BUILD_TIMEOUT_SECONDS}s"
        ) from exc
    if completed.returncode != 0:
        raise RuntimeError(
            "repository-service image build failed; use retained cache on remote host\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )


def ensure_repository_service_image(*, force_rebuild: bool = False) -> str:
    image = resolve_service_image()
    if not force_rebuild and image_matches_build_context(image):
        return image
    _run_build(image)
    if not image_matches_build_context(image):
        labels = image_labels(image)
        expected = expected_build_metadata()
        raise RuntimeError(
            "repository-service image provenance does not match current build context\n"
            f"image_id={image_id(image)}\n"
            f"expected candidate_sha={expected.candidate_sha}\n"
            f"actual candidate_sha={labels.get(CANDIDATE_LABEL)}\n"
            f"expected build_input_revision={expected.build_input_revision}\n"
            f"actual build_input_revision={labels.get(BUILD_INPUT_LABEL)}\n"
            f"expected source_tree_sha256={expected.source_tree_sha256}\n"
            f"actual source_tree_sha256={labels.get(SOURCE_TREE_LABEL)}\n"
            f"expected uv_lock_sha256={current_uv_lock_sha256()}\n"
            f"actual uv_lock_sha256={labels.get(UV_LOCK_LABEL)}\n"
            f"candidate_sha={expected.candidate_sha}"
        )
    return image
