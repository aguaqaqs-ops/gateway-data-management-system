"""Count-only checks for the Phase 6 S1b synthetic load helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.p6_s1b_synthetic_load import _json_depth, _parse_input

pytestmark = pytest.mark.unit


def test_json_depth_counts_nested_values_across_multiple_create_statements(
    tmp_path: Path,
) -> None:
    source = tmp_path / "synthetic.sql"
    source.write_text(
        "CREATE TABLE `json_values` (`payload` JSON);\n"
        "CREATE TABLE `other_values` (`payload` VARCHAR(32));\n"
        "INSERT INTO `json_values` (`payload`) VALUES ('{}'), ('{\"x\":[1]}');\n",
        encoding="utf-8",
    )

    summary = _json_depth(source)

    assert summary == {
        "json_value_count": 2,
        "maximum_nesting_depth": 2,
        "depth_counts": {"1": 1, "2": 1},
    }


def test_synthetic_parser_tracks_rows_when_tables_have_different_widths(tmp_path: Path) -> None:
    source = tmp_path / "different-widths.sql"
    source.write_text(
        "CREATE TABLE `records` ("
        "`id` INT NOT NULL, `value` VARCHAR(20) NOT NULL, `optional` VARCHAR(20), "
        "PRIMARY KEY (`id`));\n"
        "CREATE TABLE `other` (`id` INT NOT NULL, PRIMARY KEY (`id`));\n"
        "INSERT INTO `records` VALUES (1, 'a', 'x');\n"
        "INSERT INTO `other` VALUES (2);\n",
        encoding="utf-8",
    )

    parsed = _parse_input(source.read_bytes())
    assert len(parsed.rows_by_table["records"]) == 1
    assert len(parsed.rows_by_table["other"]) == 1
    assert len(parsed.rows_by_table["records"][0].cells) == 3
    assert len(parsed.rows_by_table["other"][0].cells) == 1
