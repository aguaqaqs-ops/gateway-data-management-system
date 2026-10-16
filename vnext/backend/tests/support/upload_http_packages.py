"""Shared valid SourcePackage bytes for HTTP upload tests."""

from __future__ import annotations

import json

from gateway_shared_kernel import raw_blob_digest

from tests.support.source_package_fixtures import load_bytes, pack_tar_gz

_SQL = load_bytes("package/valid/s1-minimal-tar-gz/sql/dbcfg.sql")
KEYLESS_FALLBACK_TABLE = "dc29_keyless_fallback"
KEYLESS_FALLBACK_BASE_ROWS = ("duplicate", "duplicate", "stable")
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


def keyless_fallback_upload_files(
    expected_version: int,
    *,
    initial_rows: tuple[str, ...] = KEYLESS_FALLBACK_BASE_ROWS,
    modified_rows: tuple[str, ...] = KEYLESS_FALLBACK_BASE_ROWS,
) -> dict[str, tuple[str, bytes, str]]:
    initial_bytes = pack_tar_gz(
        {"sql/dbcfg.sql": _keyless_fallback_sql(initial_rows)}
    )
    modified_bytes = pack_tar_gz(
        {"sql/dbcfg.sql": _keyless_fallback_sql(modified_rows)}
    )
    return upload_files(
        expected_version=expected_version,
        initial_bytes=initial_bytes,
        modified_bytes=modified_bytes,
    )


def _keyless_fallback_sql(rows: tuple[str, ...]) -> bytes:
    if type(rows) is not tuple or any(type(row) is not str or row == "" for row in rows):
        raise ValueError("keyless fallback rows must be a tuple of non-empty strings")
    statements = [
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY);\n",
        "INSERT INTO t VALUES (1);\n",
        f"CREATE TABLE {KEYLESS_FALLBACK_TABLE} (value VARCHAR(64));\n",
    ]
    statements.extend(
        f"INSERT INTO {KEYLESS_FALLBACK_TABLE} VALUES ({_quote_sql_string(row)});\n" for row in rows
    )
    return "".join(statements).encode("utf-8")


def _quote_sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
