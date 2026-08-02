"""Deterministic SQL fixtures for the P2-R1 provider matrix."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from gateway_repository_service.arrow_mapping import ColumnCatalog, TableCatalog


class Workload(StrEnum):
    W0 = "W0"
    W1 = "W1"
    W2 = "W2"
    W3_1 = "W3-1pct"
    W3_10 = "W3-10pct"


class ScaleWorkload(StrEnum):
    """Same-shape scaling series; deliberately excluded from the legacy matrix."""

    S10 = "S10"
    S40 = "S40"
    S100 = "S100"


@dataclass(frozen=True)
class Fixture:
    workload: StrEnum
    replay_sql: Path
    expected_tables: tuple[TableCatalog, ...]
    rows: int
    package_bytes: int
    dataset_id: str
    synthetic: bool = True


def generate_fixture(root: Path, workload: Workload) -> Fixture:
    root.mkdir(parents=True, exist_ok=True)
    replay = root / f"{workload.value}.replay.sql"
    if workload == Workload.W0:
        tables = _write_w0(replay)
    elif workload == Workload.W1:
        tables = _write_representative(replay, 40_000, 170)
    elif workload == Workload.W2:
        tables = _write_representative(replay, 100_000, 1_800)
    else:
        base = root / "W1.replay.sql"
        if not base.exists():
            _write_representative(base, 40_000, 170)
        tables = _write_delta(replay, int(40_000 * (0.01 if workload == Workload.W3_1 else 0.10)))
    digest = hashlib.sha256(replay.read_bytes()).hexdigest()
    return Fixture(
        workload=workload,
        replay_sql=replay,
        expected_tables=tables,
        rows=sum(table.row_count for table in tables),
        package_bytes=replay.stat().st_size,
        dataset_id=f"synthetic-{workload.value}-{digest[:16]}",
    )


def generate_scale_fixture(root: Path, workload: ScaleWorkload) -> Fixture:
    rows = {ScaleWorkload.S10: 10_000, ScaleWorkload.S40: 40_000, ScaleWorkload.S100: 100_000}[workload]
    root.mkdir(parents=True, exist_ok=True)
    replay = root / f"{workload.value}.replay.sql"
    tables = _write_representative(replay, rows, 170)
    digest = hashlib.sha256(replay.read_bytes()).hexdigest()
    return Fixture(
        workload=workload,
        replay_sql=replay,
        expected_tables=tables,
        rows=rows,
        package_bytes=replay.stat().st_size,
        dataset_id=f"synthetic-{workload.value}-{digest[:16]}",
    )


def _write_w0(path: Path) -> tuple[TableCatalog, ...]:
    with path.open("w", encoding="utf-8") as handle:
        handle.write(
            """CREATE TABLE known_types (
  id INT NOT NULL PRIMARY KEY,
  bool_value BOOLEAN NULL,
  bit_value BIT(8) NOT NULL,
  tiny_signed TINYINT NOT NULL,
  tiny_unsigned TINYINT UNSIGNED NOT NULL,
  small_signed SMALLINT NOT NULL,
  small_unsigned SMALLINT UNSIGNED NOT NULL,
  medium_signed MEDIUMINT NOT NULL,
  medium_unsigned MEDIUMINT UNSIGNED NOT NULL,
  int_signed INT NOT NULL,
  int_unsigned INT UNSIGNED NOT NULL,
  big_signed BIGINT NOT NULL,
  big_unsigned BIGINT UNSIGNED NOT NULL,
  decimal_small DECIMAL(10,2) NOT NULL,
  decimal_large DECIMAL(40,2) NOT NULL,
  float_value FLOAT NOT NULL,
  double_value DOUBLE NOT NULL,
  date_value DATE NOT NULL,
  time_value TIME(6) NOT NULL,
  datetime_value DATETIME(6) NOT NULL,
  timestamp_value TIMESTAMP(6) NOT NULL,
  char_value CHAR(4) NOT NULL,
  varchar_value VARCHAR(32) NOT NULL,
  text_value TEXT NOT NULL,
  binary_value BINARY(2) NOT NULL,
  varbinary_value VARBINARY(8) NOT NULL,
  blob_value BLOB NOT NULL,
  json_value JSON NOT NULL
);
INSERT INTO known_types VALUES (1, TRUE, b'10101010', -3, 250, -300, 60000, -70000, 70000, -800000, 4000000000, -9000000000, 18000000000, 12.34, 12345678901234567890.12, 1.25, 2.5, '2026-01-02', '03:04:05.123456', '2026-01-02 03:04:05.123456', '2026-01-02 03:04:05.123456', 'utf8', 'hello', '世界', X'00FF', X'0102', X'000102', '{"kind": "known"}');
INSERT INTO known_types VALUES (2, NULL, b'00000001', 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 0.01, 0.02, 3.5, 4.5, '2026-02-03', '00:00:00', '2026-02-03 00:00:00', '2026-02-03 00:00:00', 'null', 'nullable', 'text', X'0000', X'00', X'', '{}');
CREATE TABLE unknown_types (id INT NOT NULL PRIMARY KEY, unknown_value ENUM('a','b') NULL);
INSERT INTO unknown_types VALUES (1, 'a');
INSERT INTO unknown_types VALUES (2, NULL);
CREATE TABLE composite_keys (left_id INT NOT NULL, right_id INT NOT NULL, value_text VARCHAR(16) NULL, PRIMARY KEY (left_id, right_id));
INSERT INTO composite_keys VALUES (1, 1, 'one');
INSERT INTO composite_keys VALUES (1, 2, NULL);
"""
        )
    return (
        _table(
            "composite_keys",
            (
                ColumnCatalog("left_id", "INT", False, 1),
                ColumnCatalog("right_id", "INT", False, 2),
                ColumnCatalog("value_text", "VARCHAR(16)", True, None),
            ),
            2,
        ),
        _table("known_types", _known_columns(), 2),
        _table(
            "unknown_types",
            (
                ColumnCatalog("id", "INT", False, 1),
                ColumnCatalog("unknown_value", "ENUM('A','B')", True, None),
            ),
            2,
        ),
    )


def _write_representative(path: Path, rows: int, payload_width: int) -> tuple[TableCatalog, ...]:
    payload_type = "VARCHAR(2048)"
    with path.open("w", encoding="utf-8") as handle:
        handle.write(
            f"CREATE TABLE records (id BIGINT NOT NULL PRIMARY KEY, tenant_id INT NOT NULL, payload {payload_type} NOT NULL, duplicate_key VARCHAR(32) NOT NULL, amount DECIMAL(12,2) NOT NULL, happened DATETIME(6) NOT NULL, flag BOOLEAN NULL, raw_value BLOB NULL);\n"
        )
        for index in range(rows):
            payload = f"payload-{index % 1000:04d}-" + ("x" * payload_width)
            duplicate = f"group-{index % 128:03d}"
            raw = (index % 256).to_bytes(2, "big").hex()
            flag = "NULL" if index % 17 == 0 else "TRUE" if index % 2 else "FALSE"
            handle.write(
                "INSERT INTO records VALUES "
                f"({index + 1}, {(index % 64) + 1}, '{payload}', '{duplicate}', "
                f"{index % 1000000 / 100:.2f}, '2026-01-01 00:00:00.{index % 1000000:06d}', "
                f"{flag}, X'{raw}');\n"
            )
    return (
        _table(
            "records",
            (
                ColumnCatalog("id", "BIGINT", False, 1),
                ColumnCatalog("tenant_id", "INT", False, None),
                ColumnCatalog("payload", payload_type, False, None),
                ColumnCatalog("duplicate_key", "VARCHAR(32)", False, None),
                ColumnCatalog("amount", "DECIMAL(12,2)", False, None),
                ColumnCatalog("happened", "DATETIME(6)", False, None),
                ColumnCatalog("flag", "BOOLEAN", True, None),
                ColumnCatalog("raw_value", "BLOB", True, None),
            ),
            rows,
        ),
    )


def _write_delta(path: Path, rows: int) -> tuple[TableCatalog, ...]:
    with path.open("w", encoding="utf-8") as handle:
        for index in range(rows):
            handle.write(
                f"UPDATE records SET payload = 'changed-{index:08d}', amount = {index % 1000}.50 WHERE id = {index + 1};\n"
            )
    return (
        _table(
            "records",
            (
                ColumnCatalog("id", "BIGINT", False, 1),
                ColumnCatalog("tenant_id", "INT", False, None),
                ColumnCatalog("payload", "VARCHAR(2048)", False, None),
                ColumnCatalog("duplicate_key", "VARCHAR(32)", False, None),
                ColumnCatalog("amount", "DECIMAL(12,2)", False, None),
                ColumnCatalog("happened", "DATETIME(6)", False, None),
                ColumnCatalog("flag", "BOOLEAN", True, None),
                ColumnCatalog("raw_value", "BLOB", True, None),
            ),
            40_000,
        ),
    )


def _known_columns() -> tuple[ColumnCatalog, ...]:
    names = (
        ("id", "INT", False, 1),
        ("bool_value", "BOOLEAN", True, None),
        ("bit_value", "BIT(8)", False, None),
        ("tiny_signed", "TINYINT", False, None),
        ("tiny_unsigned", "TINYINT UNSIGNED", False, None),
        ("small_signed", "SMALLINT", False, None),
        ("small_unsigned", "SMALLINT UNSIGNED", False, None),
        ("medium_signed", "MEDIUMINT", False, None),
        ("medium_unsigned", "MEDIUMINT UNSIGNED", False, None),
        ("int_signed", "INT", False, None),
        ("int_unsigned", "INT UNSIGNED", False, None),
        ("big_signed", "BIGINT", False, None),
        ("big_unsigned", "BIGINT UNSIGNED", False, None),
        ("decimal_small", "DECIMAL(10,2)", False, None),
        ("decimal_large", "DECIMAL(40,2)", False, None),
        ("float_value", "FLOAT", False, None),
        ("double_value", "DOUBLE", False, None),
        ("date_value", "DATE", False, None),
        ("time_value", "TIME(6)", False, None),
        ("datetime_value", "DATETIME(6)", False, None),
        ("timestamp_value", "TIMESTAMP(6)", False, None),
        ("char_value", "CHAR(4)", False, None),
        ("varchar_value", "VARCHAR(32)", False, None),
        ("text_value", "TEXT", False, None),
        ("binary_value", "BINARY(2)", False, None),
        ("varbinary_value", "VARBINARY(8)", False, None),
        ("blob_value", "BLOB", False, None),
        ("json_value", "JSON", False, None),
    )
    return tuple(ColumnCatalog(*item) for item in names)


def _table(name: str, columns: tuple[ColumnCatalog, ...], row_count: int) -> TableCatalog:
    return TableCatalog(name, columns, row_count)
