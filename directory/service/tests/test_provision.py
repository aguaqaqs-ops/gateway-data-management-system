"""Provisioning boundaries with a host substitute and a real local database."""
import json
import hashlib
import sqlite3
import sys
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


def test_replace_preserves_other_session_and_recovers_same_candidate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "session.json"
    old = provision._session("dev-1", "prj-1", 180)
    candidate = provision._session("dev-1", "prj-1", 180)
    third = provision._session("other", "project", 180)
    path.write_bytes(provision._encode([old, third]))
    path.chmod(0o640)
    adapter = object.__new__(provision.GatewayHostAdapter)
    adapter.session_path = path
    monkeypatch.setattr(adapter, "management", SessionManagement(), raising=False)
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
    with pytest.raises(provision.Incomplete) as caught:
        provision._scope(response, "env", "group", "dev-1", "prj-1", "repo")
    assert caught.value.status is None  # Scope validation does not retain the HTTP status.


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


@pytest.mark.parametrize("failed_device,failed_revoked", [("dev-1", False), ("dev-2", True)])
def test_renew_recovers_same_candidates_after_replace_before_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed_device: str, failed_revoked: bool
) -> None:
    conn = database(tmp_path / "db")
    conn.execute("INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,0)", ("S2", "dev-2", "prj-2", "Second", "R1", "R2", '["s"]', '[]'))
    original = [provision._session("dev-1", "prj-1", 180), provision._session("dev-2", "prj-2", 180)]
    third = provision._session("third", "project-third", 180)
    added = provision._session("new-third", "project-new", 180)
    conn.executemany("INSERT INTO provisioning (device_key,environment_id,group_id,current_session,repository_id) VALUES (?,?,?,?,?)", [(row["gateway_device_external_key"], "env", "group", json.dumps(row), "repo") for row in original])
    conn.commit()
    path = tmp_path / "session.json"
    path.write_bytes(provision._encode([*original, third]))
    path.chmod(0o600)
    _, locks, _, _ = provision._load_helpers(Path(__file__).resolve().parents[3])
    adapter = object.__new__(provision.GatewayHostAdapter)
    adapter.session_path = path
    monkeypatch.setattr(adapter, "management", SessionManagement(), raising=False)
    adapter.groups = SimpleNamespace(environment_id="env")
    adapter.group = SimpleNamespace(group_id="group")
    monkeypatch.setattr(adapter, "config", SimpleNamespace(groups_file=tmp_path / "groups.json", ttl_days=180), raising=False)
    adapter.locks = locks
    monkeypatch.setattr(adapter, "reload", lambda: None)
    monkeypatch.setattr(provision, "_log", lambda *args, **kwargs: None)
    generated: list[str] = []
    original_session = provision._session
    def issue(device: str, project: str, ttl: int) -> dict[str, Any]:
        value = original_session(device, project, ttl)
        generated.append(device)
        return value
    monkeypatch.setattr(provision, "_session", issue)
    failing = True
    probes: list[tuple[str, bool]] = []
    def probe(session: dict[str, Any], repository: str, *, revoked: bool = False) -> None:
        nonlocal failing
        # No target is activated until every device has passed both probes.
        assert conn.execute("SELECT count(*) FROM provisioning WHERE pending_session IS NOT NULL").fetchone()[0] == 2
        probes.append((session["gateway_device_external_key"], revoked))
        if failing and (session["gateway_device_external_key"], revoked) == (failed_device, failed_revoked):
            raise provision.Incomplete("probe not confirmed")
    monkeypatch.setattr(adapter, "probe", probe)
    with pytest.raises(provision.Incomplete):
        provision._renew(conn, adapter, RecordingLog())
    stored = conn.execute("SELECT current_session,pending_session FROM provisioning ORDER BY device_key").fetchall()
    assert all(row[1] is not None for row in stored)
    assert hashlib.sha256(stored[0][0].encode()).digest() == hashlib.sha256(json.dumps(original[0]).encode()).digest()
    assert hashlib.sha256(stored[1][0].encode()).digest() == hashlib.sha256(json.dumps(original[1]).encode()).digest()
    pending = [json.loads(row[1]) for row in stored]
    assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(provision._encode([*pending, third])).digest()
    path.write_bytes(provision._encode([*pending, third, added]))
    failing = False
    probes.clear()
    assert provision._renew(conn, adapter, RecordingLog()) == 0
    assert generated == ["dev-1", "dev-2"]
    assert probes == [("dev-1", False), ("dev-1", True), ("dev-2", False), ("dev-2", True)]
    result = conn.execute("SELECT current_session,pending_session FROM provisioning ORDER BY device_key").fetchall()
    assert all(row[1] is None for row in result)
    assert [hashlib.sha256(row[0].encode()).digest() for row in result] == [hashlib.sha256(row[1].encode()).digest() for row in stored]
    assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(provision._encode([*pending, third, added])).digest()
    conn.close()


@pytest.mark.parametrize("raw,code,expected", [
    (b'{"state":"busy"}', 3, ("busy", "unknown")),
    (b'{"state":"invalid","reason":"configuration or request rejected"}', 2, ("invalid", "configuration or request rejected")),
    (b'{"state":"invalid","reason":"secret"}', 2, ("invalid", "unknown")),
    (b'{"state":"busy","reason":"secret"}', 1, ("unknown", "unknown")),
    (b'not-json-secret', 1, ("unknown", "unknown")),
])
def test_management_diagnostics_only_expose_allowlisted_messages(raw: bytes, code: int, expected: tuple[str, str]) -> None:
    assert provision._safe_diagnostic(raw, code) == expected


def test_management_output_is_bounded_and_sanitized() -> None:
    code, state, reason = provision._management_command([sys.executable, "-c", "import sys; sys.stderr.write('{\"state\":\"busy\"}'); sys.exit(3)"], {})
    assert (code, state, reason) == (3, "busy", "unknown")
    with pytest.raises(provision.Incomplete, match="output exceeded limit"):
        provision._management_command([sys.executable, "-c", "import sys; sys.stdout.write('x' * 65537); sys.stdout.flush()"], {})


@pytest.mark.parametrize("role", ["registration", "public_scope"])
def test_confirmation_diagnostics_preserve_pending_and_exclude_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], role: str
) -> None:
    conn = database(tmp_path / "db")
    adapter = StubAdd()
    events: list[dict[str, object]] = []
    monkeypatch.setattr(provision, "_log", lambda _stream, event, **fields: events.append({"event": event, **fields}))
    error = provision.Incomplete("synthetic secret must not be logged", reason="http_status", status=404, entry_route_not_loaded=role == "public_scope")
    if role == "registration":
        def registration(_device: str, _project: str) -> dict[str, Any]:
            raise error
        monkeypatch.setattr(adapter, "registration", registration)
    else:
        adapter.fail_receipt = False
        def probe(_session: Any, _repository: str) -> None:
            raise error
        monkeypatch.setattr(adapter, "probe", probe)
    with pytest.raises(provision.Incomplete):
        provision._add_batch(conn, adapter, provision._targets(conn, None), False, RecordingLog(), tmp_path)  # type: ignore[arg-type]
    assert len(adapter.candidates) == 1
    assert conn.execute("SELECT current_session IS NULL,pending_session IS NOT NULL FROM provisioning").fetchone() == (1, 1)
    diagnostic = next(v for v in events if v["event"] == "confirmation-unfinished")
    assert diagnostic["role"] == role
    assert diagnostic["reason"] == "http_status"
    assert diagnostic["http_status"] == 404
    assert diagnostic["entry_route_not_loaded"] == (role == "public_scope")
    output = capsys.readouterr().out
    assert "synthetic secret" not in output
    assert adapter.candidates[0] not in output
    assert "synthetic secret" not in json.dumps(events)
    assert adapter.candidates[0] not in json.dumps(events)
    conn.close()


@pytest.mark.parametrize("entry_header,expected", [("route-not-loaded", True), ("another-rejection", False)])
def test_http_diagnostic_records_only_status_and_specific_entry_predicate(
    monkeypatch: pytest.MonkeyPatch, entry_header: str, expected: bool
) -> None:
    from email.message import Message
    from urllib.error import HTTPError

    headers = Message()
    headers["X-Gateway-Entry-Rejection"] = entry_header
    error = HTTPError("http://127.0.0.1/secret-url", 404, "secret error", headers, None)

    def open_request(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr(provision, "build_opener", lambda *_args: SimpleNamespace(open=open_request))
    with pytest.raises(provision.Incomplete) as caught:
        provision._request("http://127.0.0.1/secret-url", "synthetic-secret-token", "dev-1")
    assert provision._probe_diagnostic(caught.value, "public_scope") == {
        "role": "public_scope", "reason": "http_status", "http_status": 404,
        "entry_route_not_loaded": expected,
    }
    assert str(caught.value) == "probe not confirmed"
