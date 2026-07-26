"""Negative tests for container native smoke identity checks."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pyarrow as pa
import pytest

from gateway_backend.container_native_smoke import (
    EXPECTED_RESULT_JCS_BYTES,
    EXPECTED_ROW_HASHES_HEX,
    EXPECTED_ROW_HASH_SCHEMA,
    assert_result_jcs_contract,
    assert_row_hash_column,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _run_smoke(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged = {
        "GATEWAY_SOURCE_REVISION": "abc123",
        "GATEWAY_EXPECTED_WHEEL_SHA256": "0" * 64,
        "GATEWAY_EXPECTED_EXTENSION_SHA256": "1" * 64,
        "GATEWAY_INSTALLED_WHEEL_PATH": "/nonexistent/wheel.whl",
    }
    merged.update(env)
    return subprocess.run(
        [sys.executable, "-m", "gateway_backend.container_native_smoke"],
        cwd=BACKEND_ROOT,
        env=merged,
        text=True,
        capture_output=True,
        check=False,
    )


def test_container_native_smoke_fails_on_missing_env() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "gateway_backend.container_native_smoke"],
        cwd=BACKEND_ROOT,
        env={},
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "GATEWAY_SOURCE_REVISION" in proc.stderr


def test_container_native_smoke_fails_on_missing_wheel_file(tmp_path: Path) -> None:
    proc = _run_smoke(
        {
            "GATEWAY_INSTALLED_WHEEL_PATH": str(tmp_path / "missing.whl"),
            "GATEWAY_EXPECTED_WHEEL_SHA256": "a" * 64,
            "GATEWAY_EXPECTED_EXTENSION_SHA256": "b" * 64,
        }
    )
    assert proc.returncode == 1
    assert "wheel file missing" in proc.stderr


def test_container_native_smoke_fails_on_wheel_sha_mismatch(tmp_path: Path) -> None:
    wheel = tmp_path / "gateway-compute-python.whl"
    wheel.write_bytes(b"wheel-bytes")
    proc = _run_smoke(
        {
            "GATEWAY_INSTALLED_WHEEL_PATH": str(wheel),
            "GATEWAY_EXPECTED_WHEEL_SHA256": "f" * 64,
            "GATEWAY_EXPECTED_EXTENSION_SHA256": "b" * 64,
        }
    )
    assert proc.returncode == 1
    assert "wheel sha256 mismatch" in proc.stderr


def test_assert_row_hash_column_rejects_wrong_hash() -> None:
    bad = pa.table(
        {"row_hash": [bytes.fromhex("00" * 32), bytes.fromhex(EXPECTED_ROW_HASHES_HEX[1])]},
        schema=EXPECTED_ROW_HASH_SCHEMA,
    )
    with pytest.raises(SystemExit):
        assert_row_hash_column(bad, EXPECTED_ROW_HASHES_HEX)


def test_assert_row_hash_column_rejects_extra_column() -> None:
    schema = pa.schema(
        [
            pa.field("row_hash", pa.binary(32), nullable=False),
            pa.field("extra", pa.int32(), nullable=False),
        ]
    )
    table = pa.table(
        {
            "row_hash": [bytes.fromhex(h) for h in EXPECTED_ROW_HASHES_HEX],
            "extra": [1, 2],
        },
        schema=schema,
    )
    with pytest.raises(SystemExit):
        assert_row_hash_column(table, EXPECTED_ROW_HASHES_HEX)


def test_assert_row_hash_column_rejects_non_32_byte_row() -> None:
    schema = pa.schema([pa.field("row_hash", pa.binary(), nullable=False)])
    table = pa.table({"row_hash": [b"x"] * 2}, schema=schema)
    with pytest.raises(SystemExit):
        assert_row_hash_column(table, EXPECTED_ROW_HASHES_HEX)


def test_assert_result_jcs_contract_rejects_invalid_json() -> None:
    with pytest.raises(SystemExit):
        assert_result_jcs_contract(b"not-json")


def test_assert_result_jcs_contract_rejects_non_canonical_bytes() -> None:
    pretty = json.dumps(json.loads(EXPECTED_RESULT_JCS_BYTES), indent=2).encode()
    with pytest.raises(SystemExit):
        assert_result_jcs_contract(pretty)


def test_assert_result_jcs_contract_accepts_oracle() -> None:
    assert_result_jcs_contract(EXPECTED_RESULT_JCS_BYTES)


def test_native_compute_smoke_oracle_matches_live_wheel() -> None:
    from gateway_backend.container_native_smoke import (
        SMOKE_REQUEST_JCS,
        assert_result_jcs_contract,
        assert_row_hash_column,
    )
    from gateway_backend.compute import canonical_row_hashes_v1

    table = pa.table({"flag": [True, False]})
    output, result_jcs = canonical_row_hashes_v1(SMOKE_REQUEST_JCS, table)
    assert_row_hash_column(output.read_all(), EXPECTED_ROW_HASHES_HEX)
    assert_result_jcs_contract(result_jcs)
