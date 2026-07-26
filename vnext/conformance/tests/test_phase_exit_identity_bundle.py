"""Tests for phase-exit identity bundle (image-side direct_url, atomic persist)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
IDENTITY_BUNDLE = REPO_ROOT / "vnext/scripts/phase_exit_identity_bundle.py"

_spec = importlib.util.spec_from_file_location("phase_exit_identity_bundle", IDENTITY_BUNDLE)
assert _spec and _spec.loader
_bundle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bundle)

build_identity_document = _bundle.build_identity_document
atomic_persist = _bundle.atomic_persist
canonical_json_bytes = _bundle.canonical_json_bytes
HOST_RUST_DIRECT_URL = {
    "url": "file:///root/gateway-data-management-system/vnext/rust/gateway-compute-python",
    "dir_info": {},
}
IMAGE_NATIVE_PATH = "/app/backend/.venv/lib/python3.14/site-packages/gateway_compute/gateway_compute.cpython-314-x86_64-linux-gnu.so"


def _inspect_payload() -> str:
    return json.dumps(
        [
            {
                "Id": "sha256:deadbeef",
                "Architecture": "amd64",
                "Os": "linux",
                "RepoDigests": [],
            }
        ]
    )


def _probe_payload(
    *,
    direct_url: object,
    native_module_path: str = IMAGE_NATIVE_PATH,
) -> str:
    return json.dumps(
        {"native_module_path": native_module_path, "direct_url": direct_url},
        separators=(",", ":"),
    )


def _mock_subprocess_for_probe(probe_stdout: str) -> object:
    def _run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if cmd[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(cmd, 0, _inspect_payload(), "")
        if cmd[:3] == ["docker", "run", "--rm"]:
            return subprocess.CompletedProcess(cmd, 0, probe_stdout + "\n", "")
        raise AssertionError(f"unexpected subprocess: {cmd}")

    return _run


def test_build_identity_document_uses_image_direct_url_not_host(tmp_path: Path) -> None:
    wheel_url = {
        "url": "file:///opt/gateway/wheels/gateway_compute_python-0.1.0-cp314-cp314-manylinux_2_34_x86_64.whl",
        "dir_info": {},
    }
    lock_file = tmp_path / "locks.sha"
    lock_file.write_text("ab" * 32 + " vnext/backend/uv.lock\n", encoding="utf-8")

    with patch.object(
        _bundle.subprocess,
        "run",
        side_effect=_mock_subprocess_for_probe(_probe_payload(direct_url=wheel_url)),
    ):
        with patch.dict(
            os.environ,
            {"PHASE_EXIT_HOST_PIP_VERSION": "pip 25.3 from /tmp/venv (python 3.14)"},
            clear=False,
        ):
            doc = build_identity_document(lock_after_path=lock_file, image_tag="gateway-test:tag")

    assert doc["direct_url"] == wheel_url
    assert doc["native_module_path"] == IMAGE_NATIVE_PATH
    assert doc["host_pip_version"] == "pip 25.3 from /tmp/venv (python 3.14)"
    assert "direct_url_note" not in doc
    serialized = json.dumps(doc)
    assert "/rust/gateway-compute-python" not in serialized


def test_build_identity_document_null_direct_url_has_note(tmp_path: Path) -> None:
    lock_file = tmp_path / "locks.sha"
    lock_file.write_text("cd" * 32 + " vnext/rust/Cargo.lock\n", encoding="utf-8")
    with patch.object(
        _bundle.subprocess,
        "run",
        side_effect=_mock_subprocess_for_probe(_probe_payload(direct_url=None)),
    ):
        doc = build_identity_document(lock_after_path=lock_file, image_tag="gateway-test:tag")
    assert doc["direct_url"] is None
    assert doc["direct_url_note"] == "wheel install without direct_url.json"


def test_build_identity_document_rejects_rust_tree_url_in_image(tmp_path: Path) -> None:
    lock_file = tmp_path / "locks.sha"
    lock_file.write_text("ef" * 32 + " vnext/backend/uv.lock\n", encoding="utf-8")
    bad = _probe_payload(direct_url=HOST_RUST_DIRECT_URL)
    with patch.object(_bundle.subprocess, "run", side_effect=_mock_subprocess_for_probe(bad)):
        with pytest.raises(ValueError, match="source tree"):
            build_identity_document(lock_after_path=lock_file, image_tag="gateway-test:tag")


def test_host_rust_path_never_in_native_module_path(tmp_path: Path) -> None:
    lock_file = tmp_path / "locks.sha"
    lock_file.write_text("00" * 32 + " vnext/backend/uv.lock\n", encoding="utf-8")
    host_path = f"{REPO_ROOT}/vnext/backend/.venv/lib/python3.14/site-packages/gateway_compute/gateway_compute.so"
    wheel = {
        "url": "file:///opt/gateway/wheels/gateway_compute_python-0.1.0-cp314-cp314-manylinux_2_34_x86_64.whl"
    }
    with patch.object(
        _bundle.subprocess,
        "run",
        side_effect=_mock_subprocess_for_probe(_probe_payload(direct_url=wheel)),
    ):
        doc = build_identity_document(lock_after_path=lock_file, image_tag="gateway-test:tag")
    assert host_path not in json.dumps(doc)
    assert doc["native_module_path"] == IMAGE_NATIVE_PATH


def test_atomic_persist_fsync_and_content(tmp_path: Path) -> None:
    import hashlib

    draft = tmp_path / "draft.json"
    artifact_dir = tmp_path / "artifacts"
    doc = {"gate_status": "passed", "direct_url": None}
    payload = canonical_json_bytes(doc)
    digest = hashlib.sha256(payload).hexdigest()
    draft.write_bytes(payload)

    with patch.object(_bundle.os, "fsync") as fsync_mock:
        final = atomic_persist(draft, artifact_dir, digest)
    assert final.is_file()
    assert final.read_bytes() == payload
    assert fsync_mock.call_count >= 1


def test_atomic_persist_removes_final_on_post_replace_failure(tmp_path: Path) -> None:
    import hashlib

    draft = tmp_path / "draft.json"
    artifact_dir = tmp_path / "artifacts"
    doc = {"gate_status": "passed"}
    payload = canonical_json_bytes(doc)
    digest = hashlib.sha256(payload).hexdigest()
    draft.write_bytes(payload)
    final_path = artifact_dir / f"phase-exit-container-identity-{digest}.json"

    def _fail_fsync_dir(path: Path) -> None:
        raise OSError("injected fsync failure")

    with patch.object(_bundle, "_fsync_directory", side_effect=_fail_fsync_dir):
        with pytest.raises(OSError, match="injected fsync"):
            atomic_persist(draft, artifact_dir, digest)
    assert not final_path.exists()


def test_identity_bundle_source_uses_image_probe() -> None:
    text = IDENTITY_BUNDLE.read_text(encoding="utf-8")
    assert "_read_image_probe" in text
    assert "PHASE_EXIT_NATIVE_MODULE_PATH" not in text
    assert "def _read_direct_url()" not in text
