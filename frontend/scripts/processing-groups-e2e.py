#!/usr/bin/env python3
"""Own two isolated real groups for the browser suite; all registration uses add-device.

The shell runner owns the node marker. This process owns the Compose flock and
all generated group resources, and closes them before reporting stopped.
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vnext/backend"))
from tests.support.processing_groups_harness import ProcessingGroupsStack


def write(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--sessions", required=True, type=Path)
    parser.add_argument("--scopes", type=Path)
    parser.add_argument("--control", required=True, type=Path)
    args = parser.parse_args()
    stopping = False

    def stop(_signal: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stop)
    stack = ProcessingGroupsStack(args.root, a_workers=1)
    registrations: dict[str, dict[str, object]] = {}
    try:
        stack.start()
        def register(group: str, rows: list[dict[str, object]]) -> dict[str, object]:
            device = str(rows[0]["gateway_device_external_key"])
            project = str(rows[0]["business_project_id"])
            incoming = args.root / ("incoming-" + str(len(registrations)) + ".json")
            write(incoming, {"sessions": rows})
            incoming.chmod(0o600)
            # Formal hot-add path: reservation, group registration, sessions,
            # publication and actual public device-context confirmation.
            result = stack.cli("add-device", "--group", group, "--device", device,
                "--project", project, "--session-document", str(incoming))
            if result["state"] != "available":
                raise RuntimeError("browser scope registration did not become available")
            registration = stack.registration(group, device)
            registrations[device] = registration
            return registration
        by_device: dict[str, list[dict[str, object]]] = {}
        for row in json.loads(args.sessions.read_text())["sessions"]:
            by_device.setdefault(row["gateway_device_external_key"], []).append(row)
        for rows in by_device.values():
            register("group-a", rows)
        synthetic = dict(name="synthetic-group-b", role="submitter", scope="synthetic-group-b",
            token="synthetic-group-b-token", actorId="synthetic-group-b",
            businessProjectId="synthetic-project-b", gatewayDeviceExternalKey="synthetic-device-b")
        def session(identity: dict[str, str]) -> dict[str, object]:
            return dict(token=identity["token"], actor_id=identity["actorId"],
                business_project_id=identity["businessProjectId"], gateway_device_external_key=identity["gatewayDeviceExternalKey"],
                permissions=["workspace_read", "read_project_history", "upload_submit_workspace", "preview_workspace"])
        register("group-b", [session(synthetic)])
        hot = dict(name="synthetic-hot-b", role="submitter", scope="synthetic-hot-b",
            token="synthetic-hot-b-token", actorId="synthetic-hot-b",
            businessProjectId="synthetic-hot-project", gatewayDeviceExternalKey="synthetic-hot-device")
        if args.scopes:
            scopes = json.loads(args.scopes.read_text())
            for scope in scopes["scopes"]:
                reg = registrations["fe3b-device-" + scope["slug"]]
                scope.update(repository_id=reg["repository_id"], initial_commit_id=reg["initial_commit_id"],
                    business_baseline_node_id=reg["initial_node_id"])
            write(args.scopes, scopes)
        write(args.control / "groups-ready.json", dict(entry_url=stack.url,
            backend_url=stack.group_url("group-a"), synthetic=synthetic, hot=hot,
            deployment=stack.inspect(), registrations=registrations))
        while not stopping and not (args.control / "groups-stop").exists():
            if (args.control / "hot-add-request").exists() and not (args.control / "hot-add-result.json").exists():
                before = stack.snapshot()
                register("group-b", [session(hot)])
                if stack.snapshot() != before:
                    raise RuntimeError("hot add restarted an existing group container")
                write(args.control / "hot-add-result.json", {"state": "available", "containers_unchanged": True})
            time.sleep(0.1)
    finally:
        stack.close()
        write(args.control / "groups-stopped.json", {"state": "stopped"})


if __name__ == "__main__":
    main()
