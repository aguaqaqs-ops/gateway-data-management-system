"""Count-only checks for the Phase 6 S1b synthetic load helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.p6_s1b_synthetic_load import _json_depth, _parse_input, make_2x

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


def test_synthetic_copy_preserves_rows_with_a_partial_column_list(tmp_path: Path) -> None:
    source = tmp_path / "partial-insert.sql"
    output = tmp_path / "two-copies.sql"
    source.write_text(
        "CREATE TABLE `records` ("
        "`id` INT NOT NULL, `value` VARCHAR(20) NOT NULL, "
        "`optional` VARCHAR(20) DEFAULT 'x', PRIMARY KEY (`id`));\n"
        "INSERT INTO `records` (`id`, `value`) VALUES (1, 'a'), (2, 'b');\n",
        encoding="utf-8",
    )

    parsed = _parse_input(source.read_bytes())
    assert len(parsed.rows_by_table["records"]) == 2
    assert all(row.cells[2] is None for row in parsed.rows_by_table["records"])

    summary = make_2x(source, output, "_copy")

    assert summary["table_count"] == 1
    assert summary["output_table_count"] == 2
    assert summary["output_row_count"] == 4
