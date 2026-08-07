from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]
import pytest

from gateway_repository_service.arrow_mapping import (
    ColumnCatalog,
    SqlValueConversionError,
    TableCatalog,
    TemporalSqlTypeKind,
    UnknownSqlTypeError,
    UnknownTypePolicy,
    arrow_type,
    classify_temporal_sql_type,
    is_known_sql_type,
    normalize_sql_type,
    parse_temporal_sql_type,
    record_batch,
)
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.locking import DurableRootLock
from gateway_repository_service.publication import FaultPoint, atomic_publish
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.settings import RepositoryServiceSettings


def test_component_first_layout_has_one_device_and_no_current_or_sqlite(tmp_path: Path) -> None:
    layout = DurableLayout.create(tmp_path / "root")
    layout.assert_same_filesystem()
    assert layout.layout_marker.is_file()
    assert layout.service_lock.parent.name == "control"
    assert not (layout.root / "current").exists()
    assert not (layout.root / "repository-service.sqlite3").exists()
    assert not (layout.service_state / "repository-service.sqlite3").exists()


def test_root_lock_is_exclusive_and_reacquirable(tmp_path: Path) -> None:
    layout = DurableLayout.create(tmp_path / "root")
    lock = DurableRootLock(layout.service_lock).acquire()
    script = """
import sys
from pathlib import Path
from gateway_repository_service.locking import DurableRootLock, RootLockBusy
try:
    DurableRootLock(Path(sys.argv[1])).acquire()
except RootLockBusy:
    raise SystemExit(2)
raise SystemExit(0)
"""
    blocked = subprocess.run([sys.executable, "-c", script, str(layout.service_lock)], check=False)
    assert blocked.returncode == 2
    lock.release()
    available = subprocess.run(
        [sys.executable, "-c", script, str(layout.service_lock)], check=False
    )
    assert available.returncode == 0


def test_atomic_publication_fault_points_are_fail_closed(tmp_path: Path) -> None:
    layout = DurableLayout.create(tmp_path / "root")
    before = layout.staging_repository("a" * 32, "before")
    (before / "payload").write_text("payload", encoding="utf-8")
    target_before = layout.published_repository("a" * 32)
    try:
        atomic_publish(before, target_before, fault=FaultPoint.BEFORE_RENAME)
    except RuntimeError:
        pass
    else:
        raise AssertionError("before-rename fault did not fail")
    assert not target_before.exists()

    after = layout.staging_repository("b" * 32, "after")
    (after / "payload").write_text("payload", encoding="utf-8")
    target_after = layout.published_repository("b" * 32)
    try:
        atomic_publish(after, target_after, fault=FaultPoint.AFTER_RENAME)
    except RuntimeError:
        pass
    else:
        raise AssertionError("after-rename fault did not surface")
    assert target_after.is_dir()
    assert (target_after / "payload").read_text(encoding="utf-8") == "payload"


def test_atomic_publication_no_replace_preserves_existing_target(tmp_path: Path) -> None:
    layout = DurableLayout.create(tmp_path / "root")
    staging = layout.staging_repository("c" * 32, "source")
    (staging / "payload").write_text("new", encoding="utf-8")
    target = layout.published_repository("c" * 32)
    target.mkdir(parents=True)
    (target / "payload").write_text("old", encoding="utf-8")
    try:
        atomic_publish(staging, target)
    except FileExistsError:
        pass
    else:
        raise AssertionError("no-replace publication did not fail")
    assert (target / "payload").read_text(encoding="utf-8") == "old"
    assert (staging / "payload").read_text(encoding="utf-8") == "new"


@pytest.mark.integration
def test_runner_validates_exact_dolt_version(tmp_path: Path) -> None:
    layout = DurableLayout.create(tmp_path / "root")
    runner = DoltRunner(RepositoryServiceSettings(), layout.root)
    assert runner.settings.dolt_version == "2.1.11"


@pytest.mark.integration
def test_runner_home_disables_dolt_version_check(tmp_path: Path) -> None:
    layout = DurableLayout.create(tmp_path / "root")
    runner = DoltRunner(RepositoryServiceSettings(), layout.root)
    config = json.loads(
        (runner.home / ".dolt" / "config_global.json").read_text(encoding="utf-8")
    )
    assert config["versioncheck.disabled"] == "true"
    assert config["metrics.disabled"] == "true"


@pytest.mark.integration
def test_runner_preserves_existing_private_dolt_config(tmp_path: Path) -> None:
    layout = DurableLayout.create(tmp_path / "root")
    config_path = layout.root / "provider" / "runner-home" / ".dolt" / "config_global.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"user.name": "operator"}), encoding="utf-8")
    DoltRunner(RepositoryServiceSettings(), layout.root)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["user.name"] == "operator"
    assert config["versioncheck.disabled"] == "true"
    assert config["metrics.disabled"] == "true"


def test_known_and_unknown_arrow_mapping() -> None:
    assert arrow_type("BOOLEAN", UnknownTypePolicy.REJECT)[0] == pa.bool_()
    assert arrow_type("BIGINT UNSIGNED", UnknownTypePolicy.REJECT)[0] == pa.uint64()
    assert arrow_type("DECIMAL(40,2)", UnknownTypePolicy.REJECT)[0] == pa.decimal256(40, 2)
    assert arrow_type("TIME(6)", UnknownTypePolicy.REJECT)[0] == pa.duration("us")
    assert arrow_type("TIMESTAMP", UnknownTypePolicy.REJECT)[0] == pa.timestamp("us", tz="UTC")
    with pytest.raises(UnknownSqlTypeError):
        arrow_type("TIMESTAMP(999)", UnknownTypePolicy.REJECT)
    assert parse_temporal_sql_type("TIMESTAMP(6)") == ("TIMESTAMP", 6)
    assert parse_temporal_sql_type("TIMESTAMP_FOO") is None
    assert classify_temporal_sql_type("TIMESTAMP(-1)")[0] == TemporalSqlTypeKind.MALFORMED
    assert classify_temporal_sql_type("TIMESTAMP()")[0] == TemporalSqlTypeKind.MALFORMED
    assert classify_temporal_sql_type("TIMESTAMP(7)")[0] == TemporalSqlTypeKind.MALFORMED
    assert classify_temporal_sql_type(" TIMESTAMP(6)")[0] == TemporalSqlTypeKind.NOT_TEMPORAL
    assert classify_temporal_sql_type("TIMESTAMP (6)")[0] == TemporalSqlTypeKind.MALFORMED
    assert normalize_sql_type("TIMESTAMP", "TIMESTAMP(00)") == "TIMESTAMP"
    assert normalize_sql_type("ENUM", "enum('a','b')") == "ENUM('a','b')"
    assert normalize_sql_type("ENUM", "enum('A','B')") == "ENUM('A','B')"
    assert normalize_sql_type("SET", "set('x','X')") != normalize_sql_type("SET", "set('X','x')")
    unknown, metadata = arrow_type("ENUM('a','b')", UnknownTypePolicy.STRINGIFY)
    assert unknown == pa.large_string()
    assert metadata[b"gateway.sql_type"] == b"ENUM('a','b')"
    assert metadata[b"gateway.lossy"] == b"true"
    try:
        arrow_type("ENUM('a','b')", UnknownTypePolicy.REJECT)
    except UnknownSqlTypeError:
        pass
    else:
        raise AssertionError("unknown type did not reject")
    assert not is_known_sql_type("ENUM('a','b')")
    assert is_known_sql_type("INT")


def test_stringify_does_not_degrade_known_types() -> None:
    spellings = (
        "INT",
        "DECIMAL(10,2)",
        "DATE",
        "TIME(6)",
        "TIMESTAMP(6)",
        "BINARY(4)",
        "JSON",
    )
    for spelling in spellings:
        reject = arrow_type(spelling, UnknownTypePolicy.REJECT)
        stringify = arrow_type(spelling, UnknownTypePolicy.STRINGIFY)
        assert reject == stringify


def test_stringify_known_type_conversion_failure_raises_sql_value_conversion_error() -> None:
    catalog = TableCatalog(
        "records",
        (ColumnCatalog("event_date", "DATE", True, None),),
        1,
    )
    with pytest.raises(SqlValueConversionError) as exc_info:
        record_batch(catalog, [("not-a-date",)], UnknownTypePolicy.STRINGIFY)
    message = str(exc_info.value)
    assert "not-a-date" not in message
    assert exc_info.value.column == "event_date"
    assert exc_info.value.sql_type == "DATE"


@pytest.mark.parametrize(
    "bad_value",
    [
        pytest.param([1, 2], id="list"),
        pytest.param({"a": 1}, id="dict"),
    ],
)
def test_int_column_non_scalar_raises_sql_value_conversion_error(bad_value: object) -> None:
    catalog = TableCatalog(
        "records",
        (ColumnCatalog("value", "INT", True, None),),
        1,
    )
    with pytest.raises(SqlValueConversionError) as exc_info:
        record_batch(catalog, [(bad_value,)], UnknownTypePolicy.STRINGIFY)
    assert exc_info.value.column == "value"
    assert exc_info.value.sql_type == "INT"


def test_out_of_bounds_spelling_classified_as_unknown() -> None:
    for spelling in ("BIT(65)", "DECIMAL(99,2)", "DECIMAL(10,20)"):
        assert is_known_sql_type(spelling) is False
        arrow, metadata = arrow_type(spelling, UnknownTypePolicy.STRINGIFY)
        assert arrow == pa.large_string()
        assert metadata[b"gateway.lossy"] == b"true"


def test_malformed_temporal_remains_hard_error() -> None:
    with pytest.raises(UnknownSqlTypeError, match="invalid temporal"):
        arrow_type("TIME(9)", UnknownTypePolicy.STRINGIFY)
    assert is_known_sql_type("TIME(9)") is False


def test_unknown_sql_spelling_preserves_quoted_literals() -> None:
    double_space = normalize_sql_type("ENUM", "enum('a  b')")
    single_space = normalize_sql_type("ENUM", "enum('a b')")
    assert double_space == "ENUM('a  b')"
    assert single_space == "ENUM('a b')"
    assert double_space != single_space
    assert normalize_sql_type("ENUM", "enum('a collate b')") == "ENUM('a collate b')"
    assert normalize_sql_type("INT", "int(11) unsigned zerofill") == "INT UNSIGNED"
    assert normalize_sql_type("INTEGER", "integer(11)") == "INT"


OUT_OF_BOUNDS_STRINGIFY_FIDELITY = (
    ("BIT(65)", "0x01"),
    ("BIT(65)", "1"),
    ("BIT(65)", "0xff"),
    ("BIT(0)", "1"),
    ("BIT(100)", "0xdeadbeef"),
    ("DECIMAL(99,2)", "123.45"),
)


@pytest.mark.parametrize(("sql_type", "raw_value"), OUT_OF_BOUNDS_STRINGIFY_FIDELITY)
def test_stringify_out_of_bounds_preserves_provider_text(
    sql_type: str,
    raw_value: str,
) -> None:
    catalog = TableCatalog(
        "records",
        (ColumnCatalog("value", sql_type, True, None),),
        1,
    )
    batch = record_batch(catalog, [(raw_value,)], UnknownTypePolicy.STRINGIFY)
    assert batch.column(0).to_pylist() == [raw_value]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", False),
        ("1", True),
        ("2", True),
        ("200", True),
        ("255", True),
    ],
)
def test_tinyint_one_boolean_conversion(value: str, expected: bool) -> None:
    catalog = TableCatalog(
        "records",
        (ColumnCatalog("flag", "BOOLEAN", True, None),),
        1,
    )
    batch = record_batch(catalog, [(value,)], UnknownTypePolicy.STRINGIFY)
    assert batch.column(0).to_pylist() == [expected]
