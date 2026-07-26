"""Build and atomically persist PHASE-EXIT-CONTAINER identity evidence."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_IMAGE_PROBE_SCRIPT = """
import importlib.metadata
import json
import sys
from pathlib import Path

import gateway_compute.gateway_compute as native

module_path = str(Path(native.__file__).resolve())
if "/rust/gateway-compute-python" in module_path:
    raise SystemExit(f"native module must not load from source tree: {module_path}")

direct_url = None
try:
    dist = importlib.metadata.distribution("gateway-compute-python")
except importlib.metadata.PackageNotFoundError:
    dist = None
if dist is not None:
    for path in dist.files or []:
        if path.name == "direct_url.json":
            direct_url = json.loads(dist.locate_file(path).read_text(encoding="utf-8"))
            break

print(json.dumps({"native_module_path": module_path, "direct_url": direct_url}, separators=(",", ":")))
""".strip()

_DIRECT_URL_NOTE_MISSING = "wheel install without direct_url.json"


def _assert_direct_url_allowed(direct_url: dict[str, Any]) -> None:
    url = direct_url.get("url", "")
    if "/rust/gateway-compute-python" in str(url):
        raise ValueError(f"direct_url must not reference source tree: {url}")


def _assert_native_module_path_allowed(native_module_path: str) -> None:
    if "/rust/gateway-compute-python" in native_module_path:
        raise ValueError(f"native_module_path must not reference source tree: {native_module_path}")
    if not native_module_path.startswith("/"):
        raise ValueError(f"native_module_path must be an absolute image path: {native_module_path}")


def _read_image_probe(image_tag: str) -> tuple[str, dict[str, Any] | None, str | None]:
    proc = subprocess.run(
        ["docker", "run", "--rm", image_tag, "python", "-c", _IMAGE_PROBE_SCRIPT],
        check=True,
        capture_output=True,
        text=True,
    )
    raw = proc.stdout.strip()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"unexpected image probe payload: {raw!r}")
    native_module_path = str(data.get("native_module_path", ""))
    _assert_native_module_path_allowed(native_module_path)
    direct_url = data.get("direct_url")
    direct_url_note: str | None = None
    if direct_url is None:
        direct_url_note = _DIRECT_URL_NOTE_MISSING
    else:
        if not isinstance(direct_url, dict):
            raise ValueError(f"unexpected direct_url from image: {direct_url!r}")
        _assert_direct_url_allowed(direct_url)
    return native_module_path, direct_url, direct_url_note


def _parse_lock_shas(lock_file: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for line in lock_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        sha, path = line.split(" ", 1)
        entries.append({"sha256": sha, "path": path})
    return entries


def _docker_image_fields(image_tag: str) -> dict[str, Any]:
    proc = subprocess.run(
        ["docker", "image", "inspect", image_tag],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(proc.stdout)[0]
    repo_digests = data.get("RepoDigests") or []
    repo_digest = repo_digests[0] if repo_digests else None
    return {
        "image_tag": image_tag,
        "image_id": data.get("Id"),
        "architecture": data.get("Architecture"),
        "os": data.get("Os"),
        "config_digest": data.get("Id"),
        "repo_digest": repo_digest,
        "repo_digest_note": None if repo_digest else "local tag build",
    }


def build_identity_document(
    *,
    lock_after_path: Path,
    image_tag: str,
) -> dict[str, Any]:
    native_module_path, direct_url, direct_url_note = _read_image_probe(image_tag)
    doc: dict[str, Any] = {
        "gate_status": "passed",
        "source_revision": os.environ.get("SOURCE_REVISION"),
        "expected_head": os.environ.get("EXPECTED_HEAD"),
        "wheel_sha256": os.environ.get("WHEEL_SHA256"),
        "extension_sha256": os.environ.get("EXTENSION_SHA256"),
        "python_runtime_image": os.environ.get("PHASE_EXIT_PYTHON_RUNTIME_IMAGE"),
        "network_deadline_sec": int(os.environ.get("PHASE_EXIT_NETWORK_DEADLINE_SEC", "0")),
        "host_uv_version": os.environ.get("PHASE_EXIT_HOST_UV_VERSION"),
        "host_pip_version": os.environ.get("PHASE_EXIT_HOST_PIP_VERSION"),
        "host_rustc_version": os.environ.get("PHASE_EXIT_HOST_RUSTC_VERSION"),
        "host_python_version": os.environ.get("PHASE_EXIT_HOST_PYTHON_VERSION"),
        "gateway_compute_python_version": os.environ.get("PHASE_EXIT_GATEWAY_COMPUTE_VERSION"),
        "native_module_path": native_module_path,
        "direct_url": direct_url,
        "lockfiles": _parse_lock_shas(lock_after_path),
    }
    if direct_url_note is not None:
        doc["direct_url_note"] = direct_url_note
    doc.update(_docker_image_fields(image_tag))
    return doc


def canonical_json_bytes(doc: dict[str, Any]) -> bytes:
    return (json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_draft(draft_path: Path, doc: dict[str, Any]) -> str:
    payload = canonical_json_bytes(doc)
    digest = hashlib.sha256(payload).hexdigest()
    draft_path.write_bytes(payload)
    return digest


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_persist(draft_path: Path, artifact_dir: Path, content_digest: str) -> Path:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    final_name = f"phase-exit-container-identity-{content_digest}.json"
    final_path = artifact_dir / final_name
    tmp_path = artifact_dir / f"{final_name}.tmp"
    payload = draft_path.read_bytes()
    with open(tmp_path, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, final_path)
    try:
        _fsync_directory(artifact_dir)
        latest = artifact_dir / "phase-exit-container-identity-latest.json"
        try:
            if latest.exists() or latest.is_symlink():
                latest.unlink()
            latest.symlink_to(final_path.name)
        except OSError:
            latest.write_bytes(payload)
    except OSError:
        if final_path.exists():
            final_path.unlink()
        raise
    return final_path


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: phase_exit_identity_bundle.py draft|persist")

    command = sys.argv[1]
    if command == "draft":
        draft_path = Path(os.environ["PHASE_EXIT_IDENTITY_DRAFT"])
        lock_after = Path(os.environ["PHASE_EXIT_LOCK_AFTER"])
        image_tag = os.environ["PHASE_EXIT_IMAGE_TAG"]
        doc = build_identity_document(lock_after_path=lock_after, image_tag=image_tag)
        digest = write_draft(draft_path, doc)
        print(digest)
        return

    if command == "persist":
        draft_path = Path(os.environ["PHASE_EXIT_IDENTITY_DRAFT"])
        artifact_dir = Path(os.environ["PHASE_EXIT_IDENTITY_ARTIFACT_DIR"])
        digest = os.environ["PHASE_EXIT_IDENTITY_CONTENT_DIGEST"]
        final_path = atomic_persist(draft_path, artifact_dir, digest)
        print(final_path)
        return

    raise SystemExit(f"unknown command: {command}")


if __name__ == "__main__":
    main()
