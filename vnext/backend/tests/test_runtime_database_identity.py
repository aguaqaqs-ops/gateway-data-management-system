"""Database identity observations preserve SQLite's real process-owned locks."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any

import pytest

from gateway_backend import runtime_preflight
from gateway_backend.bootstrap import storage_admin


# Keep any deliberately exposed pre-fix lock loss in an isolated process. It
# must not run more SQLite code or destruct a connection after losing its locks.
_LOCK_WITNESS = r'''
import json, os, sqlite3, subprocess, sys
from pathlib import Path
from gateway_backend.runtime_preflight import check_database_files
from gateway_backend.bootstrap.storage_admin import _database_file_identity
root = Path(sys.argv[1])
database = root / "control.sqlite3"
connection = sqlite3.connect(database, timeout=0, isolation_level=None)
assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
connection.execute("CREATE TABLE witness(id INTEGER PRIMARY KEY)")
connection.execute("BEGIN IMMEDIATE")
connection.execute("INSERT INTO witness VALUES(1)")
competitor = r"""
import errno, fcntl, json, os, sqlite3, sys
from pathlib import Path
path = Path(sys.argv[1])
result = {}
if sys.argv[2] == "observe":
    for name in ("control.sqlite3", "control.sqlite3-shm"):
        descriptor = os.open(path.parent / name, os.O_RDWR)
        try:
            try:
                fcntl.lockf(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                result[name] = "locked"
            else:
                result[name] = "acquired"
                fcntl.lockf(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
con = sqlite3.connect(path, timeout=0, isolation_level=None)
try:
    try:
        con.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc):
            raise
        result["writer"] = "locked"
    else:
        result["writer"] = "acquired"
        if sys.argv[2] == "released":
            con.execute("INSERT INTO witness VALUES(2)")
            con.execute("COMMIT")
            result["rows"] = con.execute("SELECT count(*) FROM witness").fetchone()[0]
        else:
            con.execute("ROLLBACK")
finally:
    con.close()
print(json.dumps(result))
"""
def observe(mode):
    return json.loads(subprocess.check_output([sys.executable, "-B", "-c", competitor, str(database), mode], text=True, timeout=15))
def identities():
    return {name: (p.stat().st_dev, p.stat().st_ino) for name in
        ("control.sqlite3", "control.sqlite3-wal", "control.sqlite3-shm") if (p := root / name).exists()}
before = observe("observe")
original = identities()
if sys.argv[2] == "runtime":
    check_database_files(root)
else:
    _database_file_identity(database, root)
after = observe("observe")
result = {"before": before, "after": after, "same_files": identities() == original,
    "active_transaction": connection.in_transaction, "sqlite_version": sqlite3.sqlite_version}
expected = {"control.sqlite3": "locked", "control.sqlite3-shm": "locked", "writer": "locked"}
if before != expected or after != expected or not result["same_files"] or not result["active_transaction"]:
    print(json.dumps(result), flush=True)
    os._exit(1)
connection.execute("COMMIT")
connection.close()
result["released"] = observe("released")
print(json.dumps(result), flush=True)
'''


@pytest.mark.integration
@pytest.mark.serial
@pytest.mark.parametrize("owner", ["runtime", "maintenance"])
def test_identity_observation_preserves_live_sqlite_database_and_shm_locks(
    tmp_path: Path, owner: str,
) -> None:
    completed = subprocess.run([sys.executable, "-B", "-c", _LOCK_WITNESS, str(tmp_path), owner],
                               text=True, capture_output=True, timeout=45, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["before"] == result["after"] == {
        "control.sqlite3": "locked", "control.sqlite3-shm": "locked", "writer": "locked"}
    assert result["active_transaction"] and result["same_files"]
    assert result["released"] == {"writer": "acquired", "rows": 2}


def _check(owner: str, metadata: Path) -> None:
    if owner == "runtime":
        runtime_preflight.check_database_files(metadata)
    else:
        storage_admin._database_file_identity(metadata / "control.sqlite3", metadata)


IDENTITY_FILE_FAULTS = (
    *(('runtime', name, fault) for name in ('control.sqlite3', 'control.sqlite3-wal',
        'control.sqlite3-shm', 'control.sqlite3-journal') for fault in ('symlink', 'directory', 'fifo')),
    *(('maintenance', 'control.sqlite3', fault) for fault in ('symlink', 'directory', 'fifo')),
)


@pytest.mark.unit
@pytest.mark.parametrize("owner,name,fault", IDENTITY_FILE_FAULTS)
def test_database_identity_rejects_nonordinary_files_without_touching_targets(
    tmp_path: Path, owner: str, name: str, fault: str,
) -> None:
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    (metadata / "control.sqlite3").write_bytes(b"db")
    target = tmp_path / "outside"
    target.write_bytes(b"unchanged")
    file = metadata / name
    file.unlink(missing_ok=True)
    if fault == "symlink":
        file.symlink_to(target)
    elif fault == "directory":
        file.mkdir()
    else:
        os.mkfifo(file)
    with pytest.raises((OSError, ValueError)):
        _check(owner, metadata)
    assert target.read_bytes() == b"unchanged"


@pytest.mark.unit
@pytest.mark.parametrize("owner", ["runtime", "maintenance"])
def test_database_identity_fstat_rejects_symlink_replaced_at_open(
    tmp_path: Path, owner: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "control.sqlite3"
    database.write_bytes(b"db")
    target = tmp_path / "other"
    target.write_bytes(b"other")
    original_open = os.open
    def replace(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if Path(path) == database:
            database.unlink()
            database.symlink_to(target)
        return original_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", replace)
    with pytest.raises((OSError, ValueError)):
        _check(owner, tmp_path)
    assert target.read_bytes() == b"other"


@pytest.mark.unit
@pytest.mark.parametrize("owner", ["runtime", "maintenance"])
def test_database_identity_keeps_effective_read_permission_check(
    tmp_path: Path, owner: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "control.sqlite3").write_bytes(b"db")
    original_access = os.access
    checks: list[bool] = []
    def deny_file(path: Any, mode: int, **kwargs: Any) -> bool:
        if str(path).startswith("/proc/self/fd/"):
            checks.append(mode == os.R_OK and kwargs.get("effective_ids") is True)
            return False
        return original_access(path, mode, **kwargs)
    monkeypatch.setattr(os, "access", deny_file)
    with pytest.raises(ValueError):
        _check(owner, tmp_path)
    assert checks == [True]


@pytest.mark.unit
@pytest.mark.parametrize("owner", ["runtime", "maintenance"])
def test_database_identity_rejects_different_descriptor_mount(
    tmp_path: Path, owner: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "control.sqlite3").write_bytes(b"db")
    if owner == "runtime":
        def mount(path: Path, _limit: int) -> str:
            mode = os.fstat(int(path.name)).st_mode
            return "mnt_id: file" if stat.S_ISREG(mode) else "mnt_id: directory"
        monkeypatch.setattr(runtime_preflight, "_bounded", mount)
    else:
        monkeypatch.setattr(storage_admin, "descriptor_mount_id", lambda _: "other-mount")
    with pytest.raises(ValueError):
        _check(owner, tmp_path)


@pytest.mark.unit
@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_runtime_database_journal_without_database_remains_rejected(tmp_path: Path, suffix: str) -> None:
    (tmp_path / ("control.sqlite3" + suffix)).write_bytes(b"orphan")
    with pytest.raises(ValueError, match="no owning database"):
        runtime_preflight.check_database_files(tmp_path)
