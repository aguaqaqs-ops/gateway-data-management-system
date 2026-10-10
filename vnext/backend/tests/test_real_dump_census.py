"""Pure parsing helpers for the host-side real dump census."""

from __future__ import annotations

import pytest

from benchmarks.real_dump_census import _storage_column_type_key

CENSUS_STORAGE_COLUMN_TYPE_SHAPES: tuple[tuple[str, str], ...] = (
    ("INT(11) UNSIGNED", "INT UNSIGNED"),
    ("TINYINT UNSIGNED", "TINYINT UNSIGNED"),
    ("SMALLINT(5) UNSIGNED", "SMALLINT UNSIGNED"),
    ("DECIMAL(10, 2) UNSIGNED", "DECIMAL UNSIGNED"),
    ("VARCHAR(128)", "VARCHAR"),
    ("ENUM('a', 'b')", "ENUM"),
)


@pytest.mark.parametrize(
    ("sql_type", "expected"),
    CENSUS_STORAGE_COLUMN_TYPE_SHAPES,
)
@pytest.mark.unit
def test_census_storage_column_type_key_preserves_unsigned(
    sql_type: str,
    expected: str,
) -> None:
    assert _storage_column_type_key(sql_type) == expected
