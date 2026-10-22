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


def test_dc32_table_costs_distinguish_measured_shared_and_inapplicable_stages() -> None:
    recorder = MeasurementRecorder("t4_v1_preview")
    recorder.measure(
        "comparison",
        lambda: "compared",
        table_name="customer",
    )
    recorder.measure("pair_artifact_write", lambda: None)
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
    assert measured["measurement_status"] == "measured"
    assert measured["wall_seconds"] is not None
    assert measured["comparison_role"] == "KEYED"
    assert measured["record_count"] == 3
    assert measured["changed"] is True
    unmeasured = next(item for item in result if item["stage"] == "risk_evaluation")
    assert unmeasured["measurement_status"] == "not_applicable"
    assert unmeasured["wall_seconds"] is None
    shared = next(item for item in result if item["stage"] == "artifact_write")
    assert shared["measurement_status"] == "shared_cost_per_package"
    assert shared["package_stage"] == "pair_artifact_write"
    assert shared["wall_seconds"] is None


def test_dc32_submit_table_costs_keep_planning_and_package_writes_shared() -> None:
    recorder = MeasurementRecorder("rd-t4-d-v1_submit_prepare")
    recorder.measure("submit_frozen_artifact_row_read", lambda: None, table_name="customer")
    recorder.measure("submit_schema_sql_rendering", lambda: None)
    recorder.measure("submit_artifact_write", lambda: None)
    recorder.measure("submit_plan_storage_mutation", lambda: None)
    recorder.measure("submit_render_change_set_replay", lambda: None)
    recorder.measure("submit_render_import_mutation_dml", lambda: None)
    table_facts: dict[str, Any] = {"customer": {"row_count": 12, "column_count": 4}}
    result: list[dict[str, Any]] = []

    _append_table_costs(
        result,
        scenario=recorder.scenario,
        recorder=recorder,
        table_facts=table_facts,
    )

    row_read = next(item for item in result if item["stage"] == "submit_frozen_artifact_row_read")
    assert row_read["measurement_status"] == "measured"
    assert row_read["measurement_scope"] == "per_table"
    parent = next(
        item for item in recorder.stages if item["stage"] == "submit_render_import_mutation_dml"
    )
    assert parent["measurement_status"] == "measured"
    assert parent["measurement_relation"] == "parent_inclusive"
    assert "submit_plan_storage_mutation" in parent["includes_stages"]
    child = next(
        item for item in recorder.stages if item["stage"] == "submit_plan_storage_mutation"
    )
    assert child["measurement_relation"] == "child"
    assert child["parent_stage"] == "submit_render_import_mutation_dml"
    for stage, package_stage in (
        ("submit_plan_storage_mutation", "submit_plan_storage_mutation"),
        ("submit_render_change_set_replay", "submit_render_change_set_replay"),
        ("submit_render_import_mutation_dml", "submit_render_import_mutation_dml"),
        ("schema_sql_rendering", "submit_schema_sql_rendering"),
        ("artifact_write", "submit_artifact_write"),
    ):
        item = next(record for record in result if record["stage"] == stage)
        assert item["measurement_status"] == "shared_cost_per_package"
        assert item["package_stage"] == package_stage
        assert item["wall_seconds"] is None
        assert item["thread_cpu_seconds"] is None
        if package_stage == "submit_render_import_mutation_dml":
            assert item["measurement_relation"] == "parent_inclusive"
            assert item["includes_stages"] == [
                "submit_plan_storage_mutation",
                "submit_render_change_set_replay",
            ]
        elif package_stage in {
            "submit_plan_storage_mutation",
            "submit_render_change_set_replay",
        }:
            assert item["measurement_relation"] == "child"
            assert item["parent_stage"] == "submit_render_import_mutation_dml"


def test_dc32_mib_rate_marks_zero_duration_as_unavailable() -> None:
    assert _rate_mib(1024 * 1024, 0.0) is None
    assert _rate_mib(1024 * 1024, 2.0) == 0.5
