#!/usr/bin/env python3
"""Own two isolated real groups for the browser suite; all registration uses add-device.

The shell runner owns the node marker. This process owns the Compose flock and
all generated group resources, and closes them before reporting stopped.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import stat
import sys
import time
from pathlib import Path

from tests.support.processing_groups_harness import SCRIPTS, ProcessingGroupsStack, run


def write(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(json.dumps(value), encoding="utf-8")
        temporary.replace(path)
    except Exception as publication_error:
        try:
            temporary.unlink(missing_ok=True)
        except Exception as cleanup_error:
            raise ExceptionGroup("control document publication and temporary cleanup failed",
                [publication_error, cleanup_error]) from None
        raise


def caller_succeeded(control: Path) -> bool:
    status = json.loads((control / "groups-run-status.json").read_text())
    if (not isinstance(status, dict) or type(status.get("main_exit_code")) is not int
            or type(status.get("cleanup_failed")) is not bool or type(status.get("interrupted")) is not bool):
        raise ValueError("missing or invalid browser runner exit status")
    return status["main_exit_code"] == 0 and not status["cleanup_failed"] and not status["interrupted"]


def sanitize_credentials(root: Path, control: Path, owner: str) -> list[Exception]:
    """Attempt each credential independently, without printing any document values."""
    errors: list[Exception] = []
    try:
        incoming_paths = list(root.glob("incoming-*.json*"))
    except Exception as error:
        errors.append(error)
        incoming_paths = []
    for path in incoming_paths:
        try:
            path.unlink(missing_ok=True)
        except Exception as error:
            errors.append(error)
    # Revoke runtime credentials in place: a failed down may leave active bind
    # mounts. Keep their inode and every diagnostic database/artifact intact.
    for group in ("group-a", "group-b"):
        directory = root / group
        try:
            if not directory.exists():
                continue
            run(sys.executable, str(SCRIPTS / "tests/runtime_config_fixture.py"), str(directory),
                "--owner", owner, "--cleanup", "--retain")
        except Exception as error:
            errors.append(error)
            continue
        for name, replacement in (("session/session.json", '{"sessions":[]}'), ("internal.token", ""), ("repository.token", "")):
            path = root / group / name
            try:
                if path.exists():
                    descriptor = os.open(path, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                            raise ValueError("runtime credential is not an ordinary owned file")
                        stream.truncate(0)
                        stream.write(replacement)
            except Exception as error:
                errors.append(error)
    ready = control / "groups-ready.json"
    try:
        if ready.exists():
            record = json.loads(ready.read_text())
            for identity in ("synthetic", "hot"):
                record[identity].pop("token", None)
            write(ready, record)
    except Exception as error:
        errors.append(error)
        # A malformed/unwritable ready document must not keep its plaintext tokens.
        try:
            ready.unlink(missing_ok=True)
        except Exception as unlink_error:
            errors.append(unlink_error)
    # First publication can fail before ready exists. This exact temporary is
    # independent of incoming files in GROUPS_ROOT and of the parent's RUN_ROOT.
    try:
        ready.with_suffix(ready.suffix + ".tmp").unlink(missing_ok=True)
    except Exception as error:
        errors.append(error)
    return errors


def finish_stack(stack: ProcessingGroupsStack, root: Path, control: Path, *, interrupted: bool = False,
                 primary_error: BaseException | None = None) -> None:
    errors: list[BaseException] = [primary_error] if primary_error is not None else []
    success = False
    try:
        success = caller_succeeded(control) and not interrupted
    except Exception as error:
        errors.append(error)
    try:
        # Defer destructive cleanup until the parent has checked all residuals and
        # removed RUN_ROOT secrets. Service shutdown/log collection still happens now.
        stack.close(retain=True)
    except Exception as error:
        errors.append(error)
    errors.extend(sanitize_credentials(root, control, stack.owner))
    if errors:
        raise BaseExceptionGroup("browser group shutdown or credential cleanup failed", errors)
    write(control / "groups-stopped.json", {"state": "stopped", "caller_succeeded": success,
        "owner": stack.owner, "root": str(root.absolute())})


def cleanup_retained(root: Path, control: Path) -> None:
    """Called only after the parent finished every service/secret residual check."""
    record = json.loads((control / "groups-stopped.json").read_text())
    if (not caller_succeeded(control) or record.get("state") != "stopped"
            or record.get("caller_succeeded") is not True or record.get("root") != str(root.absolute())
            or not isinstance(record.get("owner"), str) or not record["owner"]):
        raise ValueError("refusing destructive cleanup without confirmed successful shutdown")
    # Preflight both owners before deleting either root, using the existing inode
    # and owner checked fixture authority, not a directory name/prefix.
    for retain in (True, False):
        for group in ("group-a", "group-b"):
            print(run(sys.executable, str(SCRIPTS / "tests/runtime_config_fixture.py"), str(root / group),
                "--owner", record["owner"], "--cleanup", *(["--retain"] if retain else [])), end="", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--sessions", type=Path)
    parser.add_argument("--cleanup-retained", action="store_true")
    parser.add_argument("--scopes", type=Path)
    parser.add_argument("--control", required=True, type=Path)
    args = parser.parse_args()
    if args.cleanup_retained:
        cleanup_retained(args.root, args.control)
        return
    if args.sessions is None:
        parser.error("--sessions is required when starting groups")
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
            token=secrets.token_hex(24), actorId="synthetic-group-b",
            businessProjectId="synthetic-project-b", gatewayDeviceExternalKey="synthetic-device-b")
        def session(identity: dict[str, str]) -> dict[str, object]:
            return dict(token=identity["token"], actor_id=identity["actorId"],
                business_project_id=identity["businessProjectId"], gateway_device_external_key=identity["gatewayDeviceExternalKey"],
                permissions=["workspace_read", "read_project_history", "upload_submit_workspace", "preview_workspace"])
        register("group-b", [session(synthetic)])
        hot = dict(name="synthetic-hot-b", role="submitter", scope="synthetic-hot-b",
            token=secrets.token_hex(24), actorId="synthetic-hot-b",
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
        (args.control / "groups-ready.json").chmod(0o600)
        while not stopping and not (args.control / "groups-stop").exists():
            if (args.control / "hot-add-request").exists() and not (args.control / "hot-add-result.json").exists():
                before = stack.snapshot()
                register("group-b", [session(hot)])
                if stack.snapshot() != before:
                    raise RuntimeError("hot add restarted an existing group container")
                write(args.control / "hot-add-result.json", {"state": "available", "containers_unchanged": True})
            time.sleep(0.1)
    finally:
        finish_stack(stack, args.root, args.control, interrupted=stopping, primary_error=sys.exc_info()[1])



if __name__ == "__main__":
    main()
