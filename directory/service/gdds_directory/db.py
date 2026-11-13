"""Single baseline directory database."""

import fcntl
import os
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE projects (
 station_code TEXT NOT NULL PRIMARY KEY, device_key TEXT NOT NULL UNIQUE,
 project_id TEXT NOT NULL UNIQUE, name TEXT NOT NULL, region1 TEXT NOT NULL,
 region2 TEXT NOT NULL, pinyin_initials TEXT NOT NULL, pinyin_full TEXT NOT NULL,
 removed INTEGER NOT NULL CHECK (removed IN (0, 1))
);
CREATE TABLE provisioning (
 device_key TEXT NOT NULL PRIMARY KEY REFERENCES projects(device_key),
 environment_id TEXT NOT NULL, group_id TEXT NOT NULL,
 current_session TEXT, pending_session TEXT, repository_id TEXT,
 initial_node_id TEXT, initial_commit_id TEXT, provisioned_at TEXT
);
CREATE TABLE metadata (
 id INTEGER PRIMARY KEY CHECK (id = 1), catalog_version TEXT NOT NULL,
 imported_at TEXT NOT NULL, import_sha256 TEXT NOT NULL
);
"""


class ConfigurationError(ValueError):
    """Invalid private database configuration."""


def validate_path(path: Path) -> None:
    if not path.is_absolute() or ".." in path.parts:
        raise ConfigurationError("GDDS_DIRECTORY_DB: absolute normalized path required")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ConfigurationError("GDDS_DIRECTORY_DB: symlink forbidden")
    parent = path.parent.stat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid() or parent.st_mode & 0o077:
        raise ConfigurationError("GDDS_DIRECTORY_DB: private owned parent required")
    for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm"), Path(str(path) + ".lock")):
        if candidate.is_symlink():
            raise ConfigurationError("GDDS_DIRECTORY_DB: symlink forbidden")
        if candidate.exists():
            info = candidate.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise ConfigurationError("GDDS_DIRECTORY_DB: private owned file required")
    default_static = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    static = Path(os.environ.get("GDDS_DIRECTORY_STATIC_DIR", str(default_static)))
    public = os.environ.get("GDDS_DIRECTORY_ENTRY_DIRECTORY")
    for root in (static, Path(public) if public else None):
        if root is not None and path.resolve().is_relative_to(root.resolve()):
            raise ConfigurationError("GDDS_DIRECTORY_DB: cannot be inside static or public directory")


def connect(path: Path, *, create: bool = True, readonly: bool = False) -> sqlite3.Connection:
    validate_path(path)
    exists = path.exists()
    if not exists and not create:
        raise FileNotFoundError(path)
    if not exists:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) if readonly else sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    if not exists:
        conn.executescript(SCHEMA)
        conn.execute("PRAGMA user_version=1")
        conn.commit()
    else:
        # Compare the complete stored baseline against a freshly created schema.
        reference = sqlite3.connect(":memory:")
        try:
            reference.executescript(SCHEMA)
            query = "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
            if conn.execute("PRAGMA user_version").fetchone() != (1,) or conn.execute(query).fetchall() != reference.execute(query).fetchall():
                raise ValueError("directory database schema mismatch")
        except Exception:
            conn.close()
            raise
        finally:
            reference.close()
    return conn


@contextmanager
def management_lock(path: Path) -> Iterator[None]:
    validate_path(path)
    fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)
