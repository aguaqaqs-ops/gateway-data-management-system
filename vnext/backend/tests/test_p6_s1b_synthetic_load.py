"""Count-only checks for the Phase 6 S1b synthetic load helper."""

from __future__ import annotations

from pathlib import Path

from gateway_shared_kernel.types import SignedIntegerScalar, UnsignedIntegerScalar
import pytest

from benchmarks.p6_s1b_synthetic_load import _json_depth, _make_w4, _parse_input

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
        "INSERT INTO `records` VALUES (1, 'a', 'x'), (3, 'b', 'y');\n"
        "INSERT INTO `other` VALUES (2);\n",
        encoding="utf-8",
    )

    parsed = _parse_input(source.read_bytes())
    assert len(parsed.rows_by_table["records"]) == 2
    assert len(parsed.rows_by_table["other"]) == 1
    assert tuple(row.row_index for row in parsed.rows_by_table["records"]) == (0, 1)
    assert len(parsed.rows_by_table["records"][0].cells) == 3
    assert len(parsed.rows_by_table["other"][0].cells) == 1


@pytest.mark.parametrize(
    ("rate", "expected_inserted", "expected_deleted", "expected_updated"),
    ((0.1, 2, 2, 2), (1.0, 20, 20, 20)),
)
def test_w4_generates_unique_keys_and_counted_changes(
    tmp_path: Path,
    rate: float,
    expected_inserted: int,
    expected_deleted: int,
    expected_updated: int,
) -> None:
    source = tmp_path / "w4-source.sql"
    output = tmp_path / "w4-output.sql"
    source.write_text(
        "CREATE TABLE `records` (`id` INT NOT NULL PRIMARY KEY, `value` INT NOT NULL);\n"
        "INSERT INTO `records` VALUES "
        + ", ".join(f"({index}, {index * 10})" for index in range(1, 61))
        + ";\n"
        "CREATE TABLE `empty` (`id` INT NOT NULL PRIMARY KEY);\n",
        encoding="utf-8",
    )

    summary = _make_w4(source, output, rate)

    assert summary["table_count"] == 2
    assert summary["before_row_count"] == 60
    assert summary["after_row_count"] == 61
    tables = {item["table"]: item for item in summary["tables"]}
    assert tables["records"] == {
        "table": "records",
        "before": 3,
        "inserted": expected_inserted,
        "deleted": expected_deleted,
        "updated": expected_updated,
        "after": 60,
    }
    assert tables["empty"] == {
        "table": "empty",
        "before": 0,
        "inserted": 1,
        "deleted": 0,
        "updated": 0,
        "after": 1,
    }
    parsed = _parse_input(output.read_bytes())
    record_keys: list[str] = []
    for row in parsed.rows["records"]:
        key = row[0]
        assert isinstance(key, (SignedIntegerScalar, UnsignedIntegerScalar))
        record_keys.append(key.decimal)
    assert len(record_keys) == len(set(record_keys)) == 60
    assert len(parsed.rows["empty"]) == 1
    assert output.stat().st_mode & 0o777 == 0o600
