"""Helpers for P2-R4 Compose end-to-end tests with retained build cache."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from support.build_context_digest import compute_build_revision, compute_source_tree_sha256

VNEXT_ROOT = Path(__file__).resolve().parents[3]
BUILD_SCRIPT = VNEXT_ROOT / "scripts" / "build-repository-service-image.sh"
DIGEST_SCRIPT = VNEXT_ROOT / "repository_service" / "tests" / "support" / "build_context_digest.py"
DEFAULT_IMAGE = "gateway-repository-service:local"
SOURCE_TREE_LABEL = "gateway.p2r1.source-tree-sha256"
REVISION_LABEL = "org.opencontainers.image.revision"


def resolve_service_image() -> str:
    return os.environ.get("GATEWAY_REPOSITORY_SERVICE_IMAGE", DEFAULT_IMAGE)


def expected_build_metadata() -> tuple[str, str]:
    return compute_source_tree_sha256(vnext_root=VNEXT_ROOT), compute_build_revision(vnext_root=VNEXT_ROOT)


def image_labels(image: str) -> dict[str, str]:
    completed = subprocess.run(
        ["docker", "image", "inspect", image],
        check=False,
        capture_output=True,
        text=True,
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
    labels = image_labels(image)
    if not labels:
        return False
    expected_tree, expected_revision = expected_build_metadata()
    return (
        labels.get(SOURCE_TREE_LABEL) == expected_tree
        and labels.get(REVISION_LABEL) == expected_revision
    )


def _run_build(image: str) -> None:
    if not BUILD_SCRIPT.is_file():
        raise RuntimeError(f"missing build script: {BUILD_SCRIPT}")
    expected_tree, expected_revision = expected_build_metadata()
    env = os.environ.copy()
    env.setdefault("GATEWAY_REPOSITORY_SERVICE_IMAGE", image)
    env["GATEWAY_P2R1_SOURCE_TREE_SHA256"] = expected_tree
    env["GATEWAY_P2R1_BUILD_REVISION"] = expected_revision
    completed = subprocess.run(
        ["bash", str(BUILD_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=VNEXT_ROOT,
    )
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
        expected_tree, expected_revision = expected_build_metadata()
        raise RuntimeError(
            "repository-service image provenance does not match current build context\n"
            f"expected source-tree-sha256={expected_tree}\n"
            f"actual source-tree-sha256={labels.get(SOURCE_TREE_LABEL)}\n"
            f"expected revision={expected_revision}\n"
            f"actual revision={labels.get(REVISION_LABEL)}"
        )
    return image
