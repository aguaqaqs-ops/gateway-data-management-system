"""Pure tests for private S5/DC32 measurement output and aggregation."""

from __future__ import annotations

import gzip
import io
import json
import stat
import tarfile
from pathlib import Path
from typing import Any

import pytest

from benchmarks.s5_dc32_capability_measurement import (
    MeasurementRecorder,
    _append_table_costs,
    _extract_required_sql,
    _measure_hashes,
    _private_json,
    _rate_mib,
)

pytestmark = pytest.mark.unit


def _package_with_sql(sql: bytes, *, member_name: str = "sql/dbcfg.sql") -> bytes:
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w:") as archive:
        member = tarfile.TarInfo(member_name)
        member.size = len(sql)
        archive.addfile(member, io.BytesIO(sql))
    return gzip.compress(tar_buffer.getvalue())


def test_dc32_extracts_only_the_required_sql_member() -> None:
    sql = b"CREATE TABLE sample (id BIGINT);\n"

    assert _extract_required_sql(_package_with_sql(sql)) == sql


def test_dc32_accepts_the_real_dump_rooted_archive_member_name() -> None:
    sql = b"CREATE TABLE sample (id BIGINT);\n"

    assert _extract_required_sql(_package_with_sql(sql, member_name="/sql/dbcfg.sql")) == sql


def test_dc32_hash_measurement_reports_existing_and_candidate_hashes() -> None:
    measured = _measure_hashes(b"package", b"sql")

    assert set(measured) == {
        "compressed_package:existing_raw_blob_digest",
        "compressed_package:sha256",
        "compressed_package:blake2b_256",
        "compressed_package:blake3_256",
        "uncompressed_sql:existing_raw_blob_digest",
        "uncompressed_sql:sha256",
        "uncompressed_sql:blake2b_256",
        "uncompressed_sql:blake3_256",
    }
    assert measured["compressed_package:blake3_256"]["bytes"] == 7


def test_dc32_private_json_uses_private_directory_and_file_modes(tmp_path: Path) -> None:
    output = tmp_path / "runs" / "measurement.json"

    _private_json(output, {"status": "PASS"})

    assert json.loads(output.read_text(encoding="utf-8")) == {"status": "PASS"}
    assert stat.S_IMODE(output.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_dc32_table_costs_include_unmeasured_stage_rows_and_business_facts() -> None:
    recorder = MeasurementRecorder("t4_v1_preview")
    recorder.measure(
        "comparison",
        lambda: "compared",
        table_name="customer",
    )
    table_facts: dict[str, Any] = {
        "customer": {
            "row_count": 12,
            "column_count": 4,
            "comparison_role": "KEYED",
            "ordered": False,
            "record_count": 3,
            "changed": True,
        }
    }
    result: list[dict[str, Any]] = []

    _append_table_costs(
        result,
        scenario="t4_v1_preview",
        recorder=recorder,
        table_facts=table_facts,
    )

    assert {item["stage"] for item in result} == {
        "comparison",
        "risk_evaluation",
        "surface_assembly",
        "artifact_write",
    }
    measured = next(item for item in result if item["stage"] == "comparison")
    assert measured["measured"] is True
    assert measured["comparison_role"] == "KEYED"
    assert measured["record_count"] == 3
    assert measured["changed"] is True
    unmeasured = next(item for item in result if item["stage"] == "risk_evaluation")
    assert unmeasured["measured"] is False
    assert unmeasured["wall_seconds"] == 0.0


def test_dc32_mib_rate_marks_zero_duration_as_unavailable() -> None:
    assert _rate_mib(1024 * 1024, 0.0) is None
    assert _rate_mib(1024 * 1024, 2.0) == 0.5
