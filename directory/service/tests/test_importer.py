import sqlite3

import pytest

from gdds_directory import db, importer

HEADER = b"region1,region2,project_name,station_code,pinyin_initials,pinyin_full\n"
ROW = "江苏,苏州,名称,SZ-0142,mc,ming cheng\n".encode()


@pytest.mark.parametrize(("station", "device"), [
    ("SZ-0142", "dev-fbe8accb4da11574"),
    (" sz-0142 ", "dev-fbe8accb4da11574"),
    ("WX-0207", "dev-0a5e7c9870eaba0b"),
])
def test_keys(station: str, device: str) -> None:
    assert importer.keys(importer.normalize_station(station))[0] == device


@pytest.mark.parametrize(("row", "code"), [
    (",苏州,名称,SZ-0142,mc,ming cheng", "FIELD_EMPTY"),
    ("江苏,苏/州,名称,SZ-0142,mc,ming cheng", "FIELD_INVALID_CHAR"),
    ("江苏,苏州,名称,SZ 0142,mc,ming cheng", "FIELD_INVALID_CHAR"),
    ("江苏,苏州,名称,SZ-0142,m-c,ming cheng", "PINYIN_INVALID"),
    ("江苏,苏州,名称,SZ-0142,mc,ming  cheng", "PINYIN_INVALID"),
])
def test_invalid(row: str, code: str) -> None:
    _, errors = importer.parse(HEADER + (row + "\n").encode())
    assert any(code in e for e in errors)


def test_replace_restore_and_dry_run() -> None:
    conn = sqlite3.connect(":memory:")
    conn.executescript(db.SCHEMA)
    projects, errors = importer.parse(HEADER + ROW)
    assert not errors
    assert importer.apply(conn, projects, HEADER + ROW, dry_run=True)["added"] == 1
    assert conn.execute("SELECT count(*) FROM projects").fetchone() == (0,)
    importer.apply(conn, projects, HEADER + ROW)
    conn.execute("INSERT INTO provisioning (device_key, environment_id, group_id, repository_id) VALUES (?, 'env', 'group', 'repo')", (projects[0].device_key,))
    conn.commit()
    other, _ = importer.parse(HEADER + "浙江,宁波,另一个,NB-1,ly,\n".encode())
    importer.apply(conn, other, b"other")
    changed, _ = importer.parse(HEADER + "浙江,宁波,改名,SZ-0142,gm,\n".encode())
    assert importer.apply(conn, changed, b"changed")["restored"] == 1
    assert conn.execute("SELECT repository_id FROM provisioning").fetchone() == ("repo",)
    assert conn.execute("SELECT device_key FROM projects WHERE station_code='SZ-0142'").fetchone() == (projects[0].device_key,)


def test_import_transaction_rolls_back() -> None:
    conn = sqlite3.connect(":memory:")
    conn.executescript(db.SCHEMA)
    projects, _ = importer.parse(HEADER + ROW)
    importer.apply(conn, projects, b"first")
    conn.execute("CREATE TRIGGER reject_insert BEFORE INSERT ON projects BEGIN SELECT RAISE(ABORT, 'reject'); END")
    conn.commit()
    other, _ = importer.parse(HEADER + "浙江,宁波,另一个,NB-1,ly,\n".encode())
    with pytest.raises(sqlite3.IntegrityError):
        importer.apply(conn, other, b"second")
    assert conn.execute("SELECT removed FROM projects WHERE station_code='SZ-0142'").fetchone() == (0,)
    assert conn.execute("SELECT import_sha256 FROM metadata").fetchone() == (__import__("hashlib").sha256(b"first").hexdigest(),)


def test_collision_with_removed_entry_reports_source_lines() -> None:
    conn = sqlite3.connect(":memory:")
    conn.executescript(db.SCHEMA)
    projects, _ = importer.parse(HEADER + ROW)
    importer.apply(conn, projects, b"first")
    conn.execute("UPDATE projects SET station_code='OTHER', removed=1")
    conn.commit()
    with pytest.raises(ValueError, match="第 2 行 station_code：KEY_COLLISION"):
        importer.apply(conn, projects, b"second")
