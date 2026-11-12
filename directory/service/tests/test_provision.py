"""Provisioning boundaries with a host substitute and a real local database."""
import json
import hashlib
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from gdds_directory import db, provision


def database(path: Path) -> sqlite3.Connection:
    path.parent.chmod(0o700)
    conn = db.connect(path)
    conn.execute("INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,0)", ("S1", "dev-1", "prj-1", "Project", "R1", "R2", '["p"]', '[]'))
    conn.execute("INSERT INTO metadata VALUES (1,'version','2026-01-01T00:00:00Z','digest')")
    conn.commit()
    return conn


class RecordingLog:
    def write(self, text: str) -> None:
        pass

    def flush(self) -> None:
        pass

    def fileno(self) -> int:
        return 1


class StubAdd:
    def __init__(self) -> None:
        self.groups = SimpleNamespace(environment_id="env")
        self.group = SimpleNamespace(group_id="group")
        self.config = SimpleNamespace(ttl_days=180)
        self.candidates: list[str] = []
        self.fail_receipt = True

    def preflight(self, targets: Any, pending: Any) -> None:
        pass

    def add(self, device: str, project: str, candidate: dict[str, Any], private_dir: Path) -> int:
        self.candidates.append(candidate["token"])
        return 0

    def registration(self, device: str, project: str) -> dict[str, Any]:
        if self.fail_receipt:
            raise provision.Incomplete("unconfirmed")
        return {"repository_id": "repo", "initial_node_id": "initial", "initial_commit_id": "commit"}

    def probe(self, session: Any, repository: str) -> None:
        pass


def test_add_recovery_reuses_pending_and_only_activates_after_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conn = database(tmp_path / "db")
    adapter = StubAdd()
    monkeypatch.setattr(provision, "_log", lambda *args, **kwargs: None)
    with pytest.raises(provision.Incomplete):
        provision._add_batch(conn, adapter, provision._targets(conn, None), False, RecordingLog(), tmp_path)  # type: ignore[arg-type]
    assert conn.execute("SELECT current_session FROM provisioning").fetchone()[0] is None
    adapter.fail_receipt = False
    assert provision._add_batch(conn, adapter, provision._targets(conn, None), False, RecordingLog(), tmp_path) == 0  # type: ignore[arg-type]
    assert hashlib.sha256(adapter.candidates[0].encode()).digest() == hashlib.sha256(adapter.candidates[1].encode()).digest()
    assert conn.execute("SELECT current_session IS NOT NULL, pending_session IS NULL, repository_id FROM provisioning").fetchone() == (1, 1, "repo")
    conn.close()


class SessionManagement:
    @staticmethod
    def session_document(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text())  # type: ignore[no-any-return]

    @staticmethod
    def require_unique_session_tokens(groups: Any, group: str, document: Any) -> None:
        pass


def test_replace_preserves_other_session_and_recovers_same_candidate(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    old = provision._session("dev-1", "prj-1", 180)
    candidate = provision._session("dev-1", "prj-1", 180)
    third = provision._session("other", "project", 180)
    path.write_bytes(provision._encode([old, third]))
    path.chmod(0o640)
    adapter = object.__new__(provision.GatewayHostAdapter)
    adapter.session_path = path
    adapter.management = SessionManagement()
    adapter.groups = object()
    adapter.group = SimpleNamespace(group_id="group")
    adapter.replace_sessions([(old, candidate)])
    assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(provision._encode([candidate, third])).digest()
    assert path.stat().st_mode & 0o777 == 0o640
    # Simulate an independent legal session appended after a crash.
    another = provision._session("other2", "project2", 180)
    path.write_bytes(provision._encode([candidate, third, another]))
    adapter.replace_sessions([(old, candidate)])
    assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(provision._encode([candidate, third, another])).digest()
    altered = dict(candidate, actor_id="changed")
    path.write_bytes(provision._encode([altered, third]))
    with pytest.raises(provision.Rejected):
        adapter.replace_sessions([(old, candidate)])
    assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(provision._encode([altered, third])).digest()


@pytest.mark.parametrize("code", [1, 2, 3])
def test_management_failure_never_activates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    conn = database(tmp_path / "db")
    adapter = StubAdd()
    monkeypatch.setattr(provision, "_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(adapter, "add", lambda *args: code)
    assert provision._add_batch(conn, adapter, provision._targets(conn, None), False, RecordingLog(), tmp_path) == code  # type: ignore[arg-type]
    assert conn.execute("SELECT current_session IS NULL, pending_session IS NOT NULL FROM provisioning").fetchone() == (1, 1)
    conn.close()


def test_gateway_helper_validator_and_lock_protocol(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    _, locks, _, management = provision._load_helpers(root)
    path = tmp_path / "session.json"
    row = provision._session("dev-1", "prj-1", 180)
    path.write_bytes(provision._encode([row]))
    doc = management.session_document(path)
    assert len(doc["sessions"]) == 1
    path.write_text('{"sessions":[],"sessions":[]}')
    with pytest.raises(ValueError):
        management.session_document(path)
    with locks.publication_lock(tmp_path), locks.group_management_lock(tmp_path, "group"):
        with pytest.raises(BlockingIOError):
            with locks.publication_lock(tmp_path):
                pass


@pytest.mark.parametrize("bad", ["wrong_environment", "wrong_group", "wrong_project", "wrong_repository", "unknown_field"])
def test_scope_response_rejects_mismatches(bad: str) -> None:
    response = {"environment_id": "env", "group_id": "group", "gateway_device_external_key": "dev-1", "business_project_id": "prj-1", "repository_id": "repo"}
    key = {"wrong_environment": "environment_id", "wrong_group": "group_id", "wrong_project": "business_project_id", "wrong_repository": "repository_id", "unknown_field": "unexpected"}[bad]
    response[key] = "wrong"
    with pytest.raises(provision.Incomplete):
        provision._scope(response, "env", "group", "dev-1", "prj-1", "repo")


@pytest.mark.parametrize("in_entry", [False, True])
def test_rejects_db_and_private_temp_under_gateway_public_directories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, in_entry: bool) -> None:
    tmp_path.chmod(0o700)
    public = tmp_path / "public"
    entry = tmp_path / "entry"
    public.mkdir(mode=0o700)
    entry.mkdir(mode=0o700)
    config = provision.Config(tmp_path, public / "groups.json", public / "directory.json", "group", entry, "entry", tmp_path, 180)
    monkeypatch.setattr(provision.Config, "from_environment", lambda: config)
    path = (entry if in_entry else public) / "database.sqlite"
    assert provision.run(path, all_devices=True, dry_run=True) == 2
    assert not path.exists()
