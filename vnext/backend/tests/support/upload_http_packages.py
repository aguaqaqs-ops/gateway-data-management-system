"""Shared valid SourcePackage bytes for HTTP upload tests."""

from __future__ import annotations

import json

from gateway_shared_kernel import raw_blob_digest

from tests.support.source_package_fixtures import load_bytes, pack_tar_gz

_SQL = load_bytes("package/valid/s1-minimal-tar-gz/sql/dbcfg.sql")
INITIAL_BYTES = pack_tar_gz({"sql/dbcfg.sql": _SQL})
MODIFIED_BYTES = pack_tar_gz({"sql/dbcfg.sql": _SQL + b"\n-- modified\n"})
INITIAL_DIGEST = raw_blob_digest(INITIAL_BYTES).value
MODIFIED_DIGEST = raw_blob_digest(MODIFIED_BYTES).value


def upload_manifest(
    expected_version: int = 0,
    *,
    completeness: str = "FULL",
    initial_bytes: bytes = INITIAL_BYTES,
    modified_bytes: bytes = MODIFIED_BYTES,
) -> dict[str, object]:
    artifacts: dict[str, object] = {
        "MODIFIED": {
            "part_name": "modified",
            "media_type": "application/gzip",
            "size_bytes": len(modified_bytes),
            "raw_sha256": raw_blob_digest(modified_bytes).value,
        }
    }
    if completeness == "FULL":
        artifacts["INITIAL"] = {
            "part_name": "initial",
            "media_type": "application/gzip",
            "size_bytes": len(initial_bytes),
            "raw_sha256": raw_blob_digest(initial_bytes).value,
        }
    return {
        "expected_workspace_version": expected_version,
        "input_completeness": completeness,
        "artifacts": artifacts,
    }


def upload_files(
    *,
    include_initial: bool = True,
    expected_version: int = 0,
    completeness: str = "FULL",
    initial_bytes: bytes = INITIAL_BYTES,
    modified_bytes: bytes = MODIFIED_BYTES,
    manifest: dict[str, object] | None = None,
) -> dict[str, tuple[str, bytes, str]]:
    payload = manifest or upload_manifest(
        expected_version,
        completeness=completeness,
        initial_bytes=initial_bytes,
        modified_bytes=modified_bytes,
    )
    files: dict[str, tuple[str, bytes, str]] = {
        "manifest": ("manifest", json.dumps(payload).encode("utf-8"), "application/json"),
        "modified": ("modified", modified_bytes, "application/gzip"),
    }
    if include_initial:
        files["initial"] = ("initial", initial_bytes, "application/gzip")
    return files
