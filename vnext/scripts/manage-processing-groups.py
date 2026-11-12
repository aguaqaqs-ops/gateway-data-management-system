#!/usr/bin/env python3
"""Host-only processing-group entry and append-only online device provisioning."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import UTC, datetime
import importlib
import json
from pathlib import Path
import sys
from urllib.parse import quote

from processing_group_config import DeviceDirectory, DeviceDirectoryEntry, ProcessingGroupsConfig
from processing_group_entry import Busy, EntryRuntime, Incomplete, atomic_write, render_entry, request_json
from processing_group_locks import publication_lock, group_management_lock
import host_runtime_config

_identity = importlib.import_module(host_runtime_config.configuration.__package__ + ".device_identity")


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate session JSON key")
        result[key] = value
    return result


def session_document(path: Path) -> dict[str, object]:
    if not path.is_absolute():
        raise ValueError("session document must be absolute")
    with path.open("rb") as stream:
        raw = stream.read(1048577)
    if len(raw) > 1048576:
        raise ValueError("session document exceeds limit")
    value = json.loads(raw, object_pairs_hook=_object_pairs)
    if type(value) is not dict or set(value) != {"sessions"} or type(value["sessions"]) is not list:
        raise ValueError("invalid session document")
    tokens: set[str] = set()
    for row in value["sessions"]:
        if type(row) is not dict or not {"token", "actor_id", "gateway_device_external_key", "business_project_id", "permissions"} <= set(row) or set(row) - {"token", "actor_id", "gateway_device_external_key", "business_project_id", "permissions", "expires_at"}:
            raise ValueError("invalid session entry")
        token = row["token"]
        if type(token) is not str or not token or token in tokens or any(ord(char) <= 32 or ord(char) > 126 for char in token):
            raise ValueError("invalid or duplicate session token")
        tokens.add(token)
        if type(row["actor_id"]) is not str or not row["actor_id"]:
            raise ValueError("invalid session actor")
        for field in ("gateway_device_external_key", "business_project_id"):
            _identity.validate_scope_identity(row[field])
        permissions = row["permissions"]
        if type(permissions) is not list or not permissions or any(type(permission) is not str or not permission for permission in permissions):
            raise ValueError("invalid session permissions")
        _expires(row)
    return value


def _expires(row: dict[str, object]) -> datetime | None:
    value = row.get("expires_at")
    if value is None:
        return None
    if type(value) is not str:
        raise ValueError("invalid session expiry")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("session expiry requires timezone")
    return parsed


def merge_sessions(old: dict[str, object], incoming: dict[str, object], *, device: str, project: str,
                   now: datetime | None = None) -> tuple[bytes, str]:
    # Both documents have already been parsed by session_document. Keep old rows
    # exact, including expired credentials; same token cannot restore/rebind them.
    rows = list(old["sessions"])
    indexed = {row["token"]: row for row in rows}
    probe: str | None = None
    for row in incoming["sessions"]:
        if (row["gateway_device_external_key"], row["business_project_id"]) != (device, project):
            raise ValueError("session scope differs from target device")
        previous = indexed.get(row["token"])
        if previous is not None and previous != row:
            raise ValueError("existing session token differs")
        if previous is None:
            rows.append(row)
            indexed[row["token"]] = row
        expiry = _expires(row)
        if expiry is None or expiry > (now or datetime.now(UTC)):
            probe = row["token"]
    if probe is None:
        raise ValueError("session document needs an unexpired scope probe identity")
    raw = (json.dumps({"sessions": rows}, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if len(raw) > 1048576:
        raise ValueError("merged session document exceeds limit")
    return raw, probe


def require_unique_session_tokens(groups: ProcessingGroupsConfig, target: str,
                                  incoming: dict[str, object]) -> None:
    """Credentials cannot silently become a second group's identity."""
    owners: dict[str, str] = {}
    for group in groups.groups:
        document = session_document(Path(group.session_directory) / "session.json")
        for session in document["sessions"]:
            token = session["token"]
            if token in owners:
                raise ValueError("session token is shared across processing groups")
            owners[token] = group.group_id
    if any(owners.get(session["token"], target) != target for session in incoming["sessions"]):
        raise ValueError("session token belongs to another processing group")


def _identity_response(value: dict[str, object], groups: ProcessingGroupsConfig, group: object,
                       device: str, project: str | None = None) -> None:
    if (value.get("environment_id"), value.get("group_id"), value.get("gateway_device_external_key")) != (groups.environment_id, group.group_id, device):
        raise Incomplete("target identity differs")
    if project is not None and value.get("business_project_id") != project:
        raise Incomplete("target project differs")
    if type(value.get("repository_id")) is not str or not value["repository_id"]:
        raise Incomplete("target repository unavailable")


def status_device(groups: ProcessingGroupsConfig, directory: DeviceDirectory, runtime: EntryRuntime,
                  device: str) -> dict[str, object]:
    row = next((row for row in directory.devices if row.gateway_device_external_key == device), None)
    if row is None:
        return {"state": "unreserved"}
    group = next(group for group in groups.groups if group.group_id == row.group_id)
    token = Path(group.internal_token_file).read_text().strip()
    try:
        registration = request_json(group.backend_endpoint + "/internal/v1/devices/registration?device=" + quote(device, safe=""), token=token)
    except Incomplete:
        return {"state": "reserved", "group_id": group.group_id, "registration": "unconfirmed", "desired_enabled": row.enabled}
    _identity_response(registration, groups, group, device)
    actual = runtime.probe(row.route_key)
    expected_digest, _ = render_entry(groups, directory)
    result: dict[str, object] = {"state": "routing-pending", "group_id": row.group_id,
        "desired_enabled": row.enabled, "registration": "registered",
        "loaded_config_digest": actual.get("config_digest"), "selected_group": actual.get("group_id"),
        "config_pending": actual.get("config_digest") != expected_digest}
    if not row.enabled or actual.get("group_id") != row.group_id:
        return result
    sessions = session_document(Path(group.session_directory) / "session.json")
    project = registration.get("business_project_id")
    probe = next((session["token"] for session in sessions["sessions"]
        if (session["gateway_device_external_key"], session["business_project_id"]) == (device, project)
        and (_expires(session) is None or _expires(session) > datetime.now(UTC))), None)
    if probe is None:
        result["authorization"] = "unavailable"
        return result
    public_address = "[::1]" if ":" in groups.entry.listen_address else "127.0.0.1"
    try:
        request_json(group.backend_endpoint + "/readyz")
        public = request_json(f"http://{public_address}:{groups.entry.listen_port}/v1/device-context", token=probe, key=row.route_key)
        _identity_response(public, groups, group, device, str(project))
        if public["repository_id"] != registration["repository_id"]:
            raise Incomplete("public repository differs")
    except Incomplete:
        result["availability"] = "unconfirmed"
        return result
    result["state"] = "available"
    return result



def add_device(args: argparse.Namespace, groups: ProcessingGroupsConfig, runtime: EntryRuntime) -> dict[str, object]:
    device, project = _identity.validate_scope_identity(args.device), _identity.validate_scope_identity(args.project)
    group = next((group for group in groups.groups if group.group_id == args.group), None)
    if group is None:
        raise ValueError("unknown processing group")
    incoming = session_document(args.session_document)
    with publication_lock(args.groups_file.parent), group_management_lock(args.groups_file.parent, group.group_id):
        groups = ProcessingGroupsConfig.load(args.groups_file)
        runtime = EntryRuntime(groups, args.entry_directory, args.entry_project)
        group = next(item for item in groups.groups if item.group_id == args.group)
        directory = DeviceDirectory.load(args.directory_file, known_groups=groups.group_ids)
        groups.require_directory(directory)
        old = next((row for row in directory.devices if row.gateway_device_external_key == device), None)
        if old is not None and old.group_id != group.group_id:
            raise ValueError("device is already reserved by another group")
        session_path = Path(group.session_directory) / "session.json"
        require_unique_session_tokens(groups, group.group_id, incoming)
        merged, probe_token = merge_sessions(session_document(session_path), incoming, device=device, project=project)
        internal = Path(group.internal_token_file).read_text().strip()
        if not internal:
            raise ValueError("internal bearer unavailable")
        # Ready and prior-generation checks precede reserving a new identity.
        try:
            request_json(group.backend_endpoint + "/readyz")
            runtime.require_append_only(render_entry(groups, directory)[1])
        except Incomplete:
            raise ValueError("target group or entry precondition unavailable") from None
        if runtime.retiring_workers():
            raise Busy("previous entry generation is still serving requests")
        try:
            if old is None:
                reserved = replace(directory, devices=(*directory.devices, DeviceDirectoryEntry(device, group.group_id, False)))
                reserved.require_append_only(directory)
                # Re-parse to enforce count/size/collision limits after append.
                directory = DeviceDirectory.from_bytes(reserved.to_bytes(), known_groups=groups.group_ids)
                atomic_write(args.directory_file, directory.to_bytes())
            registration = request_json(group.backend_endpoint + "/internal/v1/devices/register", token=internal,
                body={"environment_id": groups.environment_id, "group_id": group.group_id,
                    "gateway_device_external_key": device, "business_project_id": project})
            _identity_response(registration, groups, group, device, project)
            atomic_write(session_path, merged)
            key = _identity.device_route_key(device)
            context = request_json(group.backend_endpoint + "/v1/device-context", token=probe_token, key=key)
            _identity_response(context, groups, group, device, project)
            if context["repository_id"] != registration["repository_id"]:
                raise Incomplete("registered repository differs from scope")
            request_json(group.backend_endpoint + "/readyz")
            enabled = replace(directory, devices=tuple(replace(row, enabled=True) if row.gateway_device_external_key == device else row for row in directory.devices))
            enabled.require_append_only(directory)
            atomic_write(args.directory_file, enabled.to_bytes())
            digest, raw = render_entry(groups, enabled)
            runtime.publish(digest, raw, key=key, group=group.group_id)
            public_address = "[::1]" if ":" in groups.entry.listen_address else "127.0.0.1"
            final = request_json(f"http://{public_address}:{groups.entry.listen_port}/v1/device-context", token=probe_token, key=key)
            _identity_response(final, groups, group, device, project)
            if final != context:
                raise Incomplete("public scope differs from registered scope")
            request_json(group.backend_endpoint + "/readyz")
            return {"state": "available", "group_id": group.group_id, "config_digest": digest}
        except (OSError, ValueError):
            raise Incomplete("device provisioning or publication not completed; retry the same identity") from None



def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "render-entry", "add-device", "status-device", "check-groups"))
    parser.add_argument("--groups-file", type=Path, required=True)
    parser.add_argument("--directory-file", type=Path, required=True)
    parser.add_argument("--entry-directory", type=Path, required=True)
    parser.add_argument("--entry-project", required=True)
    parser.add_argument("--group")
    parser.add_argument("--device")
    parser.add_argument("--project")
    parser.add_argument("--session-document", type=Path)
    args = parser.parse_args()
    try:
        if not args.groups_file.is_absolute() or not args.directory_file.is_absolute() or args.groups_file.parent != args.directory_file.parent:
            raise ValueError("groups and directory files need the same controlled absolute parent")
        groups = ProcessingGroupsConfig.load(args.groups_file)
        directory = DeviceDirectory.load(args.directory_file, known_groups=groups.group_ids)
        groups.require_directory(directory)
        runtime = EntryRuntime(groups, args.entry_directory, args.entry_project)
        if args.command == "add-device":
            if not all((args.group, args.device, args.project, args.session_document)):
                raise ValueError("add-device needs group, device, project and session document")
            result = add_device(args, groups, runtime)
        elif args.command == "status-device":
            if args.device is None:
                raise ValueError("status-device needs a device")
            _identity.validate_scope_identity(args.device)
            result = status_device(groups, directory, runtime, args.device)
        elif args.command == "check-groups":
            from processing_group_deployment import check_groups
            result = check_groups(groups)
        elif args.command == "render-entry":
            with publication_lock(args.groups_file.parent):
                digest, raw = render_entry(groups, directory)
                # Explicit bootstrap only. Running entry must be changed via
                # add-device's checked publication, never by render-entry.
                if (args.entry_directory / "nginx.conf").exists():
                    raise ValueError("entry is already initialized; use add-device")
                (args.entry_directory / "versions").mkdir(exist_ok=True)
                name = "versions/" + digest + ".conf"
                atomic_write(args.entry_directory / name, raw)
                runtime.validate(name)
                atomic_write(args.entry_directory / "nginx.conf", raw)
                result = {"config_digest": digest, "state": "rendered"}
        else:
            result = {"state": "valid"}
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 1 if args.command == "status-device" and result.get("state") != "available" else 0
    except (BlockingIOError, Busy):
        print('{"state":"busy"}', file=sys.stderr)
        return 3
    except Incomplete as exc:
        print(json.dumps({"state": "incomplete", "reason": str(exc)}), file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, StopIteration):
        print('{"state":"invalid","reason":"configuration or request rejected"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
