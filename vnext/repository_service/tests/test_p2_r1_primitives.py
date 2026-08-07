from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]
import pytest

from gateway_repository_service.arrow_mapping import (
    TemporalSqlTypeKind,
    UnknownSqlTypeError,
    UnknownTypePolicy,
    arrow_type,
    classify_temporal_sql_type,
    normalize_sql_type,
    parse_temporal_sql_type,
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


def test_runner_validates_exact_dolt_version(tmp_path: Path) -> None:
    layout = DurableLayout.create(tmp_path / "root")
    runner = DoltRunner(RepositoryServiceSettings(), layout.root)
    assert runner.settings.dolt_version == "2.1.11"


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
    unknown, metadata = arrow_type("ENUM('A','B')", UnknownTypePolicy.STRINGIFY)
    assert unknown == pa.large_string()
    assert metadata[b"gateway.lossy"] == b"true"
    try:
        arrow_type("ENUM('A','B')", UnknownTypePolicy.REJECT)
    except UnknownSqlTypeError:
        pass
    else:
        raise AssertionError("unknown type did not reject")
