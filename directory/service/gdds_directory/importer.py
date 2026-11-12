"""Validate and atomically replace a directory import."""

import csv
import hashlib
import io
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime

HEADER = ("region1", "region2", "project_name", "station_code", "pinyin_initials", "pinyin_full")
INITIALS = re.compile(r"[a-z0-9]+(?:\|[a-z0-9]+)*\Z")
FULL = re.compile(r"[a-z0-9]+(?: [a-z0-9]+)*(?:\|[a-z0-9]+(?: [a-z0-9]+)*)*\Z")


@dataclass(frozen=True)
class Project:
    station_code: str
    device_key: str
    project_id: str
    name: str
    region1: str
    region2: str
    pinyin_initials: str
    pinyin_full: str
    line: int = 0


def normalize_station(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().upper()


def keys(station: str) -> tuple[str, str]:
    digest = hashlib.sha256(b"gdds-directory/station/v1\0" + station.encode()).hexdigest()[:16]
    return "dev-" + digest, "prj-" + digest


def parse(data: bytes) -> tuple[list[Project], list[str]]:
    errors: list[str] = []
    projects: list[Project] = []
    stations: set[str] = set()
    devices: set[str] = set()
    try:
        reader = csv.reader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True)
        if tuple(next(reader, [])) != HEADER:
            return [], ["第 1 行 header：HEADER_MISMATCH"]
        for row in reader:
            line = reader.line_num
            if len(row) != len(HEADER):
                errors.append(f"第 {line} 行 header：HEADER_MISMATCH")
                continue
            region1, region2, name = (x.strip() for x in row[:3])
            station = normalize_station(row[3])
            initials, full = (x.strip().lower() for x in row[4:])
            before = len(errors)
            def error(column: str, code: str) -> None:
                errors.append(f"第 {line} 行 {column}：{code}")
            for col, val, limit in (("region1", region1, 50), ("region2", region2, 50), ("project_name", name, 100), ("station_code", station, 64)):
                if not val:
                    error(col, "FIELD_EMPTY")
                elif len(val) > limit:
                    error(col, "FIELD_TOO_LONG")
                elif any(unicodedata.category(c) == "Cc" or (col == "station_code" and c.isspace()) or (col in ("region1", "region2") and c == "/") for c in val):
                    error(col, "FIELD_INVALID_CHAR")
            if not initials:
                error("pinyin_initials", "FIELD_EMPTY")
            elif not INITIALS.fullmatch(initials):
                error("pinyin_initials", "PINYIN_INVALID")
            if full and not FULL.fullmatch(full):
                error("pinyin_full", "PINYIN_INVALID")
            device, project = keys(station)
            if station in stations:
                error("station_code", "STATION_DUPLICATE")
            elif device in devices:
                error("station_code", "KEY_COLLISION")
            stations.add(station)
            devices.add(device)
            if len(errors) == before:
                projects.append(Project(station, device, project, name, region1, region2, json.dumps(initials.split("|")), json.dumps(full.split("|") if full else []), line))
        if not stations:
            errors.append("第 2 行 station_code：FIELD_EMPTY")
    except (UnicodeDecodeError, csv.Error):
        errors.append("第 1 行 header：HEADER_MISMATCH")
    return projects, errors


def apply(conn: sqlite3.Connection, projects: list[Project], data: bytes, *, dry_run: bool = False) -> dict[str, int]:
    existing = {row[0]: row for row in conn.execute("SELECT station_code, device_key, project_id, name, region1, region2, pinyin_initials, pinyin_full, removed FROM projects")}
    by_key = {row[1]: row[0] for row in existing.values()}
    summary = dict.fromkeys(("added", "updated", "removed", "restored", "unchanged"), 0)
    incoming = {p.station_code for p in projects}
    collisions = [f"第 {p.line} 行 station_code：KEY_COLLISION" for p in projects if p.device_key in by_key and by_key[p.device_key] != p.station_code]
    if collisions:
        raise ValueError("\n".join(collisions))
    for p in projects:
        old = existing.get(p.station_code)
        values = (p.station_code, p.device_key, p.project_id, p.name, p.region1, p.region2, p.pinyin_initials, p.pinyin_full)
        category = "added" if old is None else "restored" if old[8] else "unchanged" if old[:8] == values else "updated"
        summary[category] += 1
    summary["removed"] = sum(1 for station, row in existing.items() if station not in incoming and not row[8])
    if dry_run:
        return summary
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    version = "c-" + now.strftime("%Y%m%dT%H%M%SZ-") + hashlib.sha256(data + now.isoformat().encode()).hexdigest()[:8]
    with conn:
        conn.execute("UPDATE projects SET removed=1 WHERE removed=0")
        conn.executemany("""INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(station_code) DO UPDATE SET name=excluded.name, region1=excluded.region1,
            region2=excluded.region2, pinyin_initials=excluded.pinyin_initials,
            pinyin_full=excluded.pinyin_full, removed=0""", [(p.station_code, p.device_key, p.project_id, p.name, p.region1, p.region2, p.pinyin_initials, p.pinyin_full) for p in projects])
        conn.execute("INSERT OR REPLACE INTO metadata VALUES (1, ?, ?, ?)", (version, timestamp, hashlib.sha256(data).hexdigest()))
    return summary
