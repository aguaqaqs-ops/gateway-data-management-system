from pathlib import Path
import sqlite3

import pytest

from gdds_directory import db


def test_private_paths_and_readonly(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    path = tmp_path / "directory.sqlite"
    conn = db.connect(path)
    conn.close()
    assert path.stat().st_mode & 0o777 == 0o600
    conn = db.connect(path, create=False, readonly=True)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("DELETE FROM projects")
    conn.close()
    path.chmod(0o644)
    with pytest.raises(db.ConfigurationError):
        db.validate_path(path)


def test_reject_symlink_and_public_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tmp_path.chmod(0o700)
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(db.ConfigurationError):
        db.validate_path(link / "db")
    monkeypatch.setenv("GDDS_DIRECTORY_ENTRY_DIRECTORY", str(real))
    with pytest.raises(db.ConfigurationError):
        db.validate_path(real / "db")
