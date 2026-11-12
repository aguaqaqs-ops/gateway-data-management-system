"""Host-only provisioning and recoverable session rotation.

No credentials are emitted by this module. The host adapter delegates reservation,
registration and publication to the deployed gateway's management tool.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import re
import secrets
import selectors
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from . import db, importer

PERMISSIONS = ["workspace_read", "upload_submit_workspace", "preview_workspace", "review_submission", "withdraw_own_submission", "archive_submission", "read_project_history"]
MAX_SESSION = 1048576
MAX_MANAGEMENT_OUTPUT = 65536


def _safe_diagnostic(raw: bytes, code: int) -> tuple[str, str]:
    """Map only known tool messages; never return remote-controlled text."""
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return "unknown", "unknown"
    if not isinstance(value, dict):
        return "unknown", "unknown"
    expected = {0: "available", 1: "incomplete", 2: "invalid", 3: "busy"}
    state = expected.get(code, "unknown")
    if value.get("state") != state:
        return "unknown", "unknown"
    reasons = {
        "configuration or request rejected": "configuration or request rejected",
        "device provisioning or publication not completed; retry the same identity": "provisioning or publication unconfirmed",
    }
    reason = value.get("reason")
    return state, reasons.get(reason, "unknown") if isinstance(reason, str) else "unknown"


def _management_command(args: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    """Drain both streams under one byte and time bound; preserve no raw output."""
    process: subprocess.Popen[bytes] | None = None
    completed = False
    try:
        process = subprocess.Popen(args, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        assert process.stdout is not None
        deadline = time.monotonic() + 180
        captured = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise Incomplete("management command unconfirmed")
                for key, _ in selector.select(remaining):
                    chunk = os.read(key.fd, 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    captured.extend(chunk)
                    if len(captured) > MAX_MANAGEMENT_OUTPUT:
                        raise Incomplete("management output exceeded limit")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Incomplete("management command unconfirmed")
        code = process.wait(timeout=remaining)
        state, reason = _safe_diagnostic(bytes(captured), code)
        completed = True
        return code if code in (0, 1, 2, 3) else 1, state, reason
    except (OSError, subprocess.TimeoutExpired):
        raise Incomplete("management command unconfirmed") from None
    finally:
        if process is not None:
            if not completed:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process.poll() is None:
                process.wait()
            if process.stdout is not None:
                process.stdout.close()


class Rejected(Exception):
    """Safe configuration or preflight rejection."""


class Incomplete(Exception):
    """A remote operation may have taken effect; retry the same operation."""


@dataclass(frozen=True)
class Config:
    root: Path
    groups_file: Path
    directory_file: Path
    group_id: str
    entry_directory: Path
    entry_project: str
    log_directory: Path
    ttl_days: int

    @classmethod
    def from_environment(cls) -> Config:
        names = ("GDDS_DIRECTORY_GATEWAY_ROOT", "GDDS_DIRECTORY_GROUPS_FILE", "GDDS_DIRECTORY_GATEWAY_DIRECTORY_FILE", "GDDS_DIRECTORY_ENTRY_DIRECTORY", "GDDS_DIRECTORY_LOG_DIR")
        values: dict[str, Path] = {}
        for name in names:
            raw = os.environ.get(name, "")
            if not raw or not Path(raw).is_absolute() or ".." in Path(raw).parts:
                raise Rejected(name + ": absolute path required")
            values[name] = Path(raw)
        group = os.environ.get("GDDS_DIRECTORY_GROUP_ID", "")
        entry_project = os.environ.get("GDDS_DIRECTORY_ENTRY_PROJECT", "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", group):
            raise Rejected("GDDS_DIRECTORY_GROUP_ID: invalid")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", entry_project):
            raise Rejected("GDDS_DIRECTORY_ENTRY_PROJECT: invalid")
        try:
            ttl = int(os.environ.get("GDDS_DIRECTORY_SESSION_TTL_DAYS", "180"))
            if not 1 <= ttl <= 36500:
                raise ValueError
        except ValueError:
            raise Rejected("GDDS_DIRECTORY_SESSION_TTL_DAYS: invalid") from None
        config = cls(values[names[0]], values[names[1]], values[names[2]], group, values[names[3]], entry_project, values[names[4]], ttl)
        if config.groups_file.parent != config.directory_file.parent:
            raise Rejected("GDDS_DIRECTORY_GATEWAY_DIRECTORY_FILE: parent differs from groups file")
        if not (config.root / "vnext/scripts/manage-processing-groups.py").is_file():
            raise Rejected("GDDS_DIRECTORY_GATEWAY_ROOT: management tool unavailable")
        if not config.entry_directory.is_dir() or not config.log_directory.is_dir():
            raise Rejected("GDDS_DIRECTORY_ENTRY_DIRECTORY or GDDS_DIRECTORY_LOG_DIR: directory unavailable")
        if config.log_directory.resolve().is_relative_to(Path(__file__).resolve().parents[3]):
            raise Rejected("GDDS_DIRECTORY_LOG_DIR: must be outside worktree")
        return config


def _load_helpers(root: Path) -> tuple[ModuleType, ModuleType, ModuleType, ModuleType]:
    scripts = str(root / "vnext/scripts")
    # Host helpers import each other as top-level modules. Avoid accepting an
    # already loaded module from a different deployed gateway root.
    for name in ("processing_group_config", "processing_group_locks", "processing_group_entry", "host_runtime_config"):
        loaded = sys.modules.get(name)
        if loaded is not None and not str(getattr(loaded, "__file__", "")).startswith(scripts + "/"):
            raise Rejected("gateway helper identity differs")
    sys.path.insert(0, scripts)
    try:
        config = importlib.import_module("processing_group_config")
        locks = importlib.import_module("processing_group_locks")
        entry = importlib.import_module("processing_group_entry")
        spec = importlib.util.spec_from_file_location("_directory_gateway_management", root / "vnext/scripts/manage-processing-groups.py")
        if spec is None or spec.loader is None:
            raise Rejected("gateway management helper unavailable")
        management = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(management)
        return config, locks, entry, management
    finally:
        sys.path.remove(scripts)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _request(url: str, token: str, device: str | None = None, *, unauthorized: bool = False, missing_ok: bool = False) -> dict[str, Any] | None:
    headers = {"Accept": "application/json", "Connection": "close", "Authorization": "Bearer " + token}
    if device is not None:
        headers["X-Gateway-Device-Key"] = hashlib.sha256(device.encode("utf-8")).hexdigest()
    try:
        with build_opener(ProxyHandler({}), _NoRedirect()).open(Request(url, headers=headers), timeout=5) as response:
            raw = response.read(65537)
            if len(raw) > 65536 or unauthorized:
                raise Incomplete("probe not confirmed")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise Incomplete("probe not confirmed")
            return value
    except HTTPError as exc:
        code = exc.code
        exc.close()
        if unauthorized and code == 401:
            return None
        if missing_ok and code == 404:
            return None
        raise Incomplete("probe not confirmed") from None
    except (OSError, ValueError):
        raise Incomplete("probe not confirmed") from None


def _scope(value: dict[str, Any] | None, env: str, group: str, device: str, project: str, repository: str | None = None, *, registration: bool = False) -> str:
    fields = {"environment_id", "group_id", "gateway_device_external_key", "business_project_id", "repository_id"}
    if registration:
        fields |= {"initial_node_id", "initial_commit_id"}
    if value is None or set(value) != fields or any(not isinstance(value[x], str) or not value[x] for x in fields):
        raise Incomplete("scope response invalid")
    if (value["environment_id"], value["group_id"], value["gateway_device_external_key"], value["business_project_id"]) != (env, group, device, project):
        raise Incomplete("scope response differs")
    result = str(value["repository_id"])
    if repository is not None and result != repository:
        raise Incomplete("repository response differs")
    return result


def _session(device: str, project: str, ttl: int) -> dict[str, Any]:
    return {"token": "dir-" + secrets.token_urlsafe(32), "actor_id": "test1", "gateway_device_external_key": device, "business_project_id": project, "permissions": PERMISSIONS.copy(), "expires_at": (datetime.now(UTC) + timedelta(days=ttl)).strftime("%Y-%m-%dT%H:%M:%SZ")}


def _unexpired(session: dict[str, Any]) -> bool:
    try:
        expiry = datetime.fromisoformat(str(session["expires_at"]).replace("Z", "+00:00"))
        return expiry.tzinfo is not None and expiry > datetime.now(UTC)
    except (ValueError, KeyError, TypeError):
        return False


def _encode(rows: list[dict[str, Any]]) -> bytes:
    raw = (json.dumps({"sessions": rows}, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    if len(raw) > MAX_SESSION:
        raise Rejected("session capacity exceeded")
    return raw


class GatewayHostAdapter:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.diagnostic = ("unknown", "unknown")
        self.host, self.locks, self.entry, self.management = _load_helpers(config.root)
        self.reload()

    def reload(self) -> None:
        self.groups = self.host.ProcessingGroupsConfig.load(self.config.groups_file)
        self.directory = self.host.DeviceDirectory.load(self.config.directory_file, known_groups=self.groups.group_ids)
        self.groups.require_directory(self.directory)
        selected = [row for row in self.groups.groups if row.group_id == self.config.group_id]
        if len(selected) != 1:
            raise Rejected("target group unavailable")
        self.group = selected[0]
        if self.config.entry_project in {row.project for row in self.groups.groups}:
            raise Rejected("entry project conflicts with group")
        self.session_path = Path(self.group.session_directory) / "session.json"
        self.public_url = "http://" + ("[::1]" if ":" in self.groups.entry.listen_address else "127.0.0.1") + ":" + str(self.groups.entry.listen_port) + "/v1/device-context"

    def preflight(self, targets: list[tuple[str, str]], pending: dict[str, dict[str, Any]]) -> None:
        existing = {item.gateway_device_external_key: item for item in self.directory.devices}
        added = []
        for device, project in targets:
            row = existing.get(device)
            if row is not None and row.group_id != self.group.group_id:
                raise Rejected("device reserved by another group")
            if row is not None:
                token = Path(self.group.internal_token_file).read_text(encoding="utf-8").strip()
                if not token:
                    raise Rejected("management credential unavailable")
                registration = _request(self.group.backend_endpoint + "/internal/v1/devices/registration?device=" + quote(device, safe=""), token, missing_ok=True)
                if registration is not None:
                    _scope(registration, self.groups.environment_id, self.group.group_id, device, project, registration=True)
            if row is None:
                added.append(self.host.DeviceDirectoryEntry(device, self.group.group_id, False))
        proposed = replace(self.directory, devices=(*self.directory.devices, *added))
        self.host.DeviceDirectory.from_bytes(proposed.to_bytes(), known_groups=self.groups.group_ids)
        documents = [self.management.session_document(Path(g.session_directory) / "session.json") for g in self.groups.groups]
        seen: set[str] = set()
        owners: dict[str, str] = {}
        target_rows: list[dict[str, Any]] = []
        for group, document in zip(self.groups.groups, documents, strict=True):
            for row in document["sessions"]:
                if row["token"] in seen:
                    raise Rejected("duplicate group token")
                seen.add(row["token"])
                owners[row["token"]] = group.group_id
            if group.group_id == self.group.group_id:
                target_rows = list(document["sessions"])
        # Fixed-size placeholders establish an upper bound without issuing tokens.
        for device, project in targets:
            candidate = pending.get(device)
            if candidate is not None and not _unexpired(candidate):
                raise Rejected("pending credential expired")
            if candidate is not None and owners.get(candidate["token"], self.group.group_id) != self.group.group_id:
                raise Rejected("credential belongs to another group")
            proposed_row = candidate or {"token": "dir-" + "x" * 43, "actor_id": "test1", "gateway_device_external_key": device, "business_project_id": project, "permissions": PERMISSIONS, "expires_at": "2099-12-31T23:59:59Z"}
            matches = [row for row in target_rows if candidate is not None and row["token"] == proposed_row["token"]]
            if matches and matches[0] != proposed_row:
                raise Rejected("credential conflicts with existing session")
            if not matches:
                target_rows.append(proposed_row)
        _encode(target_rows)

    def add(self, device: str, project: str, candidate: dict[str, Any], private_dir: Path) -> int:
        fd, name = tempfile.mkstemp(prefix=".gdds-session-", dir=private_dir)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(_encode([candidate]))
                stream.flush()
                os.fsync(stream.fileno())
            self.management.session_document(Path(name))
            args = [sys.executable, str(self.config.root / "vnext/scripts/manage-processing-groups.py"), "add-device", "--groups-file", str(self.config.groups_file), "--directory-file", str(self.config.directory_file), "--entry-directory", str(self.config.entry_directory), "--entry-project", self.config.entry_project, "--group", self.group.group_id, "--device", device, "--project", project, "--session-document", name]
            env = {key: os.environ[key] for key in ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONFIG", "XDG_RUNTIME_DIR") if key in os.environ}
            code, state, reason = _management_command(args, env)
            self.diagnostic = (state, reason)
            return code
        finally:
            os.unlink(name)

    def registration(self, device: str, project: str) -> dict[str, Any]:
        token = Path(self.group.internal_token_file).read_text(encoding="utf-8").strip()
        if not token:
            raise Incomplete("management credential unavailable")
        response = _request(self.group.backend_endpoint + "/internal/v1/devices/registration?device=" + quote(device, safe=""), token)
        _scope(response, self.groups.environment_id, self.group.group_id, device, project, registration=True)
        assert response is not None
        return response

    def probe(self, session: dict[str, Any], repository: str, *, revoked: bool = False) -> None:
        device = session["gateway_device_external_key"]
        value = _request(self.public_url, session["token"], device, unauthorized=revoked)
        if not revoked:
            _scope(value, self.groups.environment_id, self.group.group_id, device, session["business_project_id"], repository)

    def replace_sessions(self, changes: list[tuple[dict[str, Any], dict[str, Any]]]) -> tuple[str, str]:
        document = self.management.session_document(self.session_path)
        rows: list[dict[str, Any]] = list(document["sessions"])
        before = hashlib.sha256(self.session_path.read_bytes()).hexdigest()
        for old, candidate in changes:
            if not _unexpired(candidate):
                raise Rejected("pending credential expired")
            old_matches = [i for i, row in enumerate(rows) if row.get("token") == old["token"]]
            new_matches = [i for i, row in enumerate(rows) if row.get("token") == candidate["token"]]
            if len(old_matches) == 1 and not new_matches and rows[old_matches[0]] == old:
                rows[old_matches[0]] = candidate
            elif not old_matches and len(new_matches) == 1 and rows[new_matches[0]] == candidate:
                pass
            else:
                raise Rejected("owned session conflict")
        raw = _encode(rows)
        info = self.session_path.stat()
        fd, name = tempfile.mkstemp(prefix=".gdds-renew-", dir=self.session_path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                os.fchown(stream.fileno(), info.st_uid, info.st_gid)
                os.fchmod(stream.fileno(), info.st_mode & 0o7777)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            proposed = self.management.session_document(Path(name))
            self.management.require_unique_session_tokens(self.groups, self.group.group_id, proposed)
            os.replace(name, self.session_path)
            parent = os.open(self.session_path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return before, hashlib.sha256(raw).hexdigest()


def _load_session(raw: str, device: str, project: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
        if not isinstance(value, dict) or set(value) != {"token", "actor_id", "gateway_device_external_key", "business_project_id", "permissions", "expires_at"}:
            raise ValueError
        if value["actor_id"] != "test1" or value["gateway_device_external_key"] != device or value["business_project_id"] != project or value["permissions"] != PERMISSIONS:
            raise ValueError
        if not isinstance(value["token"], str) or re.fullmatch(r"dir-[A-Za-z0-9_-]{43}", value["token"]) is None:
            raise ValueError
        if not isinstance(value["expires_at"], str):
            raise ValueError
        return value
    except (ValueError, TypeError, KeyError):
        raise Rejected("stored credential invalid") from None


def _catalog_changed(conn: sqlite3.Connection) -> None:
    now = datetime.now(UTC)
    version = "c-" + now.strftime("%Y%m%dT%H%M%SZ-") + secrets.token_hex(4)
    conn.execute("UPDATE metadata SET catalog_version=? WHERE id=1", (version,))


def _targets(conn: sqlite3.Connection, stations: list[str] | None) -> list[tuple[str, str, str, str | None, str | None, str | None, str | None, str | None]]:
    rows = conn.execute("""SELECT p.station_code,p.device_key,p.project_id,r.environment_id,r.group_id,r.current_session,r.pending_session,r.repository_id
        FROM projects p LEFT JOIN provisioning r USING(device_key) WHERE p.removed=0 ORDER BY p.station_code""").fetchall()
    if stations is None:
        return [row for row in rows if row[5] is None]
    wanted = [importer.normalize_station(value) for value in stations]
    if not wanted or any(not value for value in wanted) or len(set(wanted)) != len(wanted):
        raise Rejected("invalid station list")
    by_station = {row[0]: row for row in rows}
    if any(value not in by_station for value in wanted):
        raise Rejected("station unavailable or removed")
    return [by_station[value] for value in wanted]


def _check_binding(row: tuple[Any, ...], adapter: GatewayHostAdapter) -> None:
    if row[3] is not None and (row[3], row[4]) != (adapter.groups.environment_id, adapter.group.group_id):
        raise Rejected("stored target binding differs")


def _log_path(config: Config) -> Path:
    name = "provision-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S-") + secrets.token_hex(6) + ".jsonl"
    return config.log_directory / name


def _log(stream: Any, event: str, **fields: object) -> None:
    stream.write(json.dumps({"time": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "event": event, **fields}, ensure_ascii=True, separators=(",", ":")) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def _add_batch(conn: sqlite3.Connection, adapter: GatewayHostAdapter, rows: list[tuple[Any, ...]], dry_run: bool, stream: Any | None, private_dir: Path) -> int:
    candidates: dict[str, dict[str, Any]] = {}
    pending_rows = []
    if conn.execute("SELECT 1 FROM provisioning WHERE current_session IS NOT NULL AND pending_session IS NOT NULL LIMIT 1").fetchone():
        raise Rejected("session renewal is unfinished")
    for row in rows:
        station, device, project, _, _, current, pending, _ = row
        _check_binding(row, adapter)
        if current is not None:
            if pending is not None:
                raise Rejected("session renewal is unfinished")
            continue
        if pending is not None:
            candidates[device] = _load_session(pending, device, project)
        pending_rows.append((station, device, project))
    try:
        adapter.preflight([(device, project) for _, device, project in pending_rows], candidates)
    except ValueError:
        raise Rejected("gateway preflight rejected") from None
    if dry_run:
        print(json.dumps({"group": adapter.group.group_id, "devices": [device for _, device, _ in pending_rows]}, ensure_ascii=True))
        return 0
    assert stream is not None
    completed: list[str] = []
    for _, device, project in pending_rows:
        candidate = candidates.get(device)
        if candidate is None:
            candidate = _session(device, project, adapter.config.ttl_days)
            with conn:
                conn.execute("INSERT INTO provisioning (device_key, environment_id, group_id, pending_session) VALUES (?, ?, ?, ?) ON CONFLICT(device_key) DO UPDATE SET pending_session=excluded.pending_session", (device, adapter.groups.environment_id, adapter.group.group_id, json.dumps(candidate, separators=(",", ":"))))
        _log(stream, "candidate-saved", device=device, completed=completed)
        try:
            code = adapter.add(device, project, candidate, private_dir)
        except Incomplete:
            _log(stream, "management-unconfirmed", device=device, completed=completed, gateway_step="unknown")
            print(json.dumps({"device": device, "pending": True, "completed": completed, "step": "management", "gateway_step": "unknown"}))
            raise
        state, reason = getattr(adapter, "diagnostic", ("unknown", "unknown"))
        _log(stream, "management-exit", device=device, exit_code=code, state=state, reason=reason, completed=completed)
        if code != 0:
            print(json.dumps({"device": device, "pending": True, "completed": completed, "step": "management", "state": state, "reason": reason, "gateway_step": "unknown"}))
            return code
        try:
            receipt = adapter.registration(device, project)
            adapter.probe(candidate, receipt["repository_id"])
        except Incomplete:
            _log(stream, "confirmation-unfinished", device=device, completed=completed, gateway_step="unknown")
            print(json.dumps({"device": device, "pending": True, "completed": completed, "step": "confirmation", "gateway_step": "unknown"}))
            raise
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        with conn:
            conn.execute("UPDATE provisioning SET current_session=pending_session,pending_session=NULL,repository_id=?,initial_node_id=?,initial_commit_id=?,provisioned_at=? WHERE device_key=?", (receipt["repository_id"], receipt["initial_node_id"], receipt["initial_commit_id"], now, device))
            _catalog_changed(conn)
        completed.append(device)
        _log(stream, "activated", device=device, repository_id=receipt["repository_id"], initial_node_id=receipt["initial_node_id"], initial_commit_id=receipt["initial_commit_id"], probe="confirmed", completed=completed)
    print(json.dumps({"completed": completed}))
    return 0


def _renew(conn: sqlite3.Connection, adapter: GatewayHostAdapter, stream: Any) -> int:
    rows = conn.execute("""SELECT p.device_key,p.project_id,r.environment_id,r.group_id,r.current_session,r.pending_session,r.repository_id
        FROM projects p JOIN provisioning r USING(device_key) WHERE r.current_session IS NOT NULL ORDER BY p.device_key""").fetchall()
    if not rows:
        return 0
    if any((row[2], row[3]) != (adapter.groups.environment_id, adapter.group.group_id) or not row[6] for row in rows):
        raise Rejected("stored target binding or receipt differs")
    old = [_load_session(row[4], row[0], row[1]) for row in rows]
    pending_count = sum(row[5] is not None for row in rows)
    if pending_count not in (0, len(rows)):
        raise Rejected("partial pending renewal conflicts")
    recovered = pending_count > 0
    with adapter.locks.publication_lock(adapter.config.groups_file.parent), adapter.locks.group_management_lock(adapter.config.groups_file.parent, adapter.group.group_id):
        adapter.reload()
        if any((row[2], row[3]) != (adapter.groups.environment_id, adapter.group.group_id) for row in rows):
            raise Rejected("target changed during renewal")
        # Validate all group session documents and check full global token uniqueness
        # before any candidate is written.
        doc = adapter.management.session_document(adapter.session_path)
        adapter.management.require_unique_session_tokens(adapter.groups, adapter.group.group_id, doc)
        current_rows = doc["sessions"]
        candidates = [_load_session(row[5], row[0], row[1]) for row in rows] if recovered else []
        for index, session in enumerate(old):
            candidate = candidates[index] if recovered else None
            matches = [item for item in current_rows if item.get("token") == session["token"]]
            candidate_matches = [item for item in current_rows if candidate is not None and item.get("token") == candidate["token"]]
            if candidate is not None and not _unexpired(candidate):
                raise Rejected("pending credential expired")
            if not ((len(matches) == 1 and matches[0] == session and not candidate_matches) or (candidate is not None and not matches and len(candidate_matches) == 1 and candidate_matches[0] == candidate)):
                raise Rejected("owned session conflict")
        if not recovered:
            candidates = [_session(row[0], row[1], adapter.config.ttl_days) for row in rows]
            # Capacity check happens before persisting candidates.
            replaced = list(current_rows)
            for prior, candidate in zip(old, candidates, strict=True):
                replaced[replaced.index(prior)] = candidate
            _encode(replaced)
            with conn:
                conn.executemany("UPDATE provisioning SET pending_session=? WHERE device_key=?", [(json.dumps(candidate, separators=(",", ":")), row[0]) for row, candidate in zip(rows, candidates, strict=True)])
            _log(stream, "renewal-candidates-saved", devices=[row[0] for row in rows])
        before, after = adapter.replace_sessions(list(zip(old, candidates, strict=True)))
        _log(stream, "sessions-replaced", before_sha256=before, after_sha256=after, recovered=recovered)
        for row, previous, candidate in zip(rows, old, candidates, strict=True):
            try:
                adapter.probe(candidate, row[6])
                adapter.probe(previous, row[6], revoked=True)
            except Incomplete:
                _log(stream, "renewal-probe-unfinished", device=row[0])
                print(json.dumps({"device": row[0], "pending": True, "step": "renewal-probe", "gateway_step": "unknown"}))
                raise
            _log(stream, "renewal-probe", device=row[0], new_scope="confirmed", old_token="unauthorized")
        with conn:
            conn.executemany("UPDATE provisioning SET current_session=pending_session,pending_session=NULL WHERE device_key=?", [(row[0],) for row in rows])
        _log(stream, "renewal-activated", devices=[row[0] for row in rows])
    return 0


def run(path: Path, *, stations: list[str] | None = None, all_devices: bool = False, renew: bool = False, dry_run: bool = False) -> int:
    """Execute one CLI operation; exceptions are deliberately redacted.

    The caller must select exactly one of stations, all_devices, or renew. Exit
    codes follow I8. `stations` contains the decoded file's lines.
    """
    if sum((stations is not None, all_devices, renew)) != 1 or (renew and dry_run):
        print("invalid provision selection", file=sys.stderr)
        return 2
    try:
        config = Config.from_environment()
        db.validate_path(path)
        if any(path.resolve().is_relative_to(root.resolve()) for root in (config.groups_file.parent, config.entry_directory)):
            raise Rejected("GDDS_DIRECTORY_DB: cannot be in gateway public configuration directory")
        if not path.exists():
            raise Rejected("directory database unavailable")
        try:
            adapter = GatewayHostAdapter(config)
        except (ValueError, OSError, ImportError):
            raise Rejected("gateway configuration invalid or unavailable") from None
        if dry_run:
            conn = db.connect(path, create=False, readonly=True)
            try:
                conn.execute("BEGIN")
                return _add_batch(conn, adapter, _targets(conn, None if all_devices else stations), True, None, path.parent)
            finally:
                conn.close()
        with db.management_lock(path):
            conn = db.connect(path, create=False)
            try:
                adapter.reload()
                log_path = _log_path(config)
                fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    _log(stream, "start", hostname=os.uname().nodename, environment=adapter.groups.environment_id, group=adapter.group.group_id)
                    try:
                        result = _renew(conn, adapter, stream) if renew else _add_batch(conn, adapter, _targets(conn, None if all_devices else stations), False, stream, path.parent)
                    except (Rejected, Incomplete, BlockingIOError, OSError, ValueError, sqlite3.Error):
                        _log(stream, "unfinished", gateway_step="unknown")
                        raise
                    finally:
                        _log(stream, "end")
                return result
            finally:
                conn.close()
    except BlockingIOError:
        print("directory or gateway management lock busy", file=sys.stderr)
        return 3
    except Rejected as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (Incomplete, OSError, ValueError, sqlite3.Error, ImportError):
        print("provision unfinished; gateway step unknown; retry the same operation", file=sys.stderr)
        return 1
