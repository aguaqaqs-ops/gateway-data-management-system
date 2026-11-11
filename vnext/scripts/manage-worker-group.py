#!/usr/bin/env python3
"""One-shot TERM-only maintenance of one fixed Compose worker group, on its host."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
import sqlite3
import subprocess
import time
from typing import Any
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, ProxyHandler

from host_runtime_config import DeploymentConfig
from worker_deployment import _docker, inspect_project, validate_workers, worker_services

WAIT_SECONDS = 180


def read_token(path: Path) -> str:
    try:
        token = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        raise ValueError("unreadable credential file") from None
    if not token or "\n" in token or "\r" in token:
        raise ValueError("invalid credential file")
    return token


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        # Never forward the deployment credential to a redirect destination.
        return None


def drain_request(url: str, token: str, *, close: bool = False) -> dict[str, Any]:
    request = Request(url.rstrip("/") + "/internal/v1/maintenance/drain",
                      headers={"Authorization": "Bearer " + token},
                      method="POST" if close else "GET")
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=10) as response:
            payload = json.loads(response.read(4096))
    except (URLError, OSError, ValueError):
        raise ValueError("authenticated backend drain request failed") from None
    if (type(payload) is not dict or type(payload.get("accepting_new_work")) is not bool
            or type(payload.get("in_flight")) is not int or payload["in_flight"] < 0):
        raise ValueError("backend returned an invalid drain snapshot")
    return payload


def close_admission(url: str, token: str) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    snapshot = drain_request(url, token, close=True)
    while True:
        if snapshot["accepting_new_work"]:
            raise ValueError("backend admission did not remain closed")
        if snapshot["in_flight"] == 0:
            return
        if time.monotonic() >= deadline:
            raise ValueError("admission drain timed out; gate remains closed")
        time.sleep(1)
        snapshot = drain_request(url, token)


def _service(container: dict[str, Any]) -> str:
    return str(container["Config"]["Labels"]["com.docker.compose.service"])


def validate_group(config: DeploymentConfig, project: str,
                   containers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    validate_workers(config, project, containers, allowed_states=("running", "exited", "created"))
    expected = {"backend", "repository-service", *worker_services(config.resources.worker.count)}
    group: dict[str, dict[str, Any]] = {}
    for item in containers:
        service = _service(item)
        labels = item["Config"]["Labels"]
        if (service not in expected or service in group
                or labels.get("com.docker.compose.container-number") != "1"
                or labels.get("com.docker.compose.oneoff", "False").lower() != "false"):
            raise ValueError("unexpected or duplicate group service: " + service)
        if item["State"]["Status"] not in {"running", "exited", "created"}:
            raise ValueError("unstable group service: " + service)
        mounts = {entry["Destination"]: entry for entry in item["Mounts"]}
        for target, original in (("/run/gateway/storage-layout.json", config.storage._source_document),
                                 ("/run/gateway/resource-profile.json", config.resources._source_document)):
            mount = mounts.get(target)
            if mount is None or mount["Type"] != "bind" or mount.get("RW", True):
                raise ValueError("group configuration mount is not a read-only bind: " + service)
            # Parse both documents as canonical JSON; whitespace is not deployment identity.
            mounted = json.dumps(json.loads(Path(mount["Source"]).read_bytes()), sort_keys=True, separators=(",", ":")).encode()
            canonical = json.dumps(json.loads(original), sort_keys=True, separators=(",", ":")).encode()
            if mounted != canonical:
                raise ValueError("actual group configuration differs: " + service)
        group[service] = item
    if set(group) != expected:
        raise ValueError("missing fixed group services")
    return group


def _cgroup(container: dict[str, Any]) -> Path:
    pid = container["State"]["Pid"]
    if pid:
        lines = Path(f"/proc/{pid}/cgroup").read_text().splitlines()
        names = [line[3:] for line in lines if line.startswith("0::")]
        if len(names) != 1:
            raise ValueError("unified container cgroup cannot be inspected")
        relative = names[0].lstrip("/")
    else:
        # Standard Docker cgroup-v2 layout, including stopped original containers.
        driver = _docker("info", "--format", "{{.CgroupDriver}}").strip()
        parent = container["HostConfig"].get("CgroupParent", "")
        if driver == "systemd":
            parent = parent or "system.slice"
            if "/" in parent or not parent.endswith(".slice"):
                raise ValueError("unsupported systemd cgroup parent")
            parts = parent[:-6].split("-")
            prefix = "/".join("-".join(parts[:index]) + ".slice" for index in range(1, len(parts) + 1))
            relative = prefix + "/docker-" + container["Id"] + ".scope"
        elif driver == "cgroupfs":
            relative = (parent or "/docker").strip("/") + "/" + container["Id"]
        else:
            raise ValueError("unsupported Docker cgroup driver")
    root = Path("/sys/fs/cgroup")
    path = (root / relative).resolve()
    if root not in path.parents:
        raise ValueError("container cgroup is outside the local unified hierarchy")
    if pid and not (path / "cgroup.events").is_file():
        raise ValueError("live container cgroup is not visible on this host")
    return path


def _empty(cgroup: Path) -> bool:
    try:
        events = dict(line.split() for line in (cgroup / "cgroup.events").read_text().splitlines())
    except FileNotFoundError:
        return not cgroup.exists()
    return events.get("populated") == "0"


def _rs_shutdown_completed(original: dict[str, Any], current: dict[str, Any]) -> bool:
    started = original["State"].get("StartedAt")
    if not started or current["State"].get("StartedAt") != started:
        return False
    # Uvicorn re-raises TERM after shutdown, even when lifespan shutdown failed.
    # Inspect its existing generation-local completion log, including stderr,
    # without copying application log contents into maintenance diagnostics.
    result = subprocess.run(["docker", "logs", "--since", started, "--tail", "200", original["Id"]],
                            capture_output=True, text=True, check=False, timeout=30)
    if result.returncode:
        return False
    lines = (result.stdout + "\n" + result.stderr).splitlines()
    return (any("Application shutdown complete." in line for line in lines)
            and not any("Application shutdown failed." in line for line in lines))


def stop_services(containers: list[dict[str, Any]]) -> None:
    groups = {item["Id"]: _cgroup(item) for item in containers}
    originals = {item["Id"]: item for item in containers}
    running = [item["Id"] for item in containers if item["State"]["Status"] == "running"]
    if running:
        _docker("kill", "--signal", "TERM", *running)
    deadline = time.monotonic() + WAIT_SECONDS
    while True:
        current = json.loads(_docker("inspect", *(item["Id"] for item in containers)))
        pending = [item for item in current if item["State"]["Running"] or item["State"]["Pid"]
                   or not _empty(groups[item["Id"]])]
        if not pending:
            failed = []
            for item in current:
                state = item["State"]
                # Direct Uvicorn execution re-raises TERM after lifespan shutdown.
                # Signal status alone cannot distinguish a failed shutdown.
                controlled_rs_term = (item["Id"] in running and _service(item) == "repository-service"
                    and state["Status"] == "exited" and state.get("ExitCode") == 128 + signal.SIGTERM
                    and _rs_shutdown_completed(originals[item["Id"]], item))
                if (state.get("OOMKilled") or state.get("Error")
                        or (state.get("ExitCode") != 0 and not controlled_rs_term)):
                    failed.append(_service(item))
            if failed:
                raise ValueError("abnormal exit; preserve group for diagnosis: " + ",".join(failed))
            return
        if time.monotonic() >= deadline:
            raise ValueError("TERM timeout; still active, no KILL sent: " + ",".join(_service(item) for item in pending))
        time.sleep(1)


def assert_business_settled(config: DeploymentConfig) -> None:
    """Read only: never repair leases, clear occupancy, or mutate UNKNOWN facts."""
    database = Path(config.storage.roots["be-metadata"].source) / "control.sqlite3"
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=1) as connection:
        running = connection.execute("SELECT count(*) FROM step_records WHERE status = 'RUNNING'").fetchone()[0]
        effects = connection.execute("SELECT count(*) FROM submit_attempt_records WHERE state = 'EFFECT_PENDING'").fetchone()[0]
    if running or effects:
        raise ValueError("unsettled RUNNING/external effects; reconcile original requests under old configuration before stop-group")


def manage(command: str, config: DeploymentConfig, project: str, url: str, token: str) -> str:
    group = validate_group(config, project, inspect_project(project))
    origin = urlsplit(url)
    published = group["backend"]["HostConfig"].get("PortBindings", {}).get("8000/tcp") or []
    if (origin.scheme != "http" or origin.hostname not in {"127.0.0.1", "::1", "localhost"}
            or not any(str(binding["HostPort"]) == str(origin.port or 80) for binding in published)):
        raise ValueError("backend URL must use the selected local container's published HTTP port")
    workers = [group[service] for service in worker_services(config.resources.worker.count)]
    if command == "start-recovery":
        snapshot = drain_request(url, token)
        if snapshot["accepting_new_work"] or snapshot["in_flight"]:
            raise ValueError("recovery start requires a closed, drained backend")
        if (group["backend"]["State"]["Status"] != "running"
                or group["repository-service"]["State"].get("Health", {}).get("Status") != "healthy"):
            raise ValueError("recovery start requires readable healthy backend storage/config and ready RS")
        for worker in workers:
            if worker["State"]["Status"] == "running" or worker["State"]["Pid"] or not _empty(_cgroup(worker)):
                raise ValueError("original workers must be fully stopped before recovery start")
        _docker("start", *(item["Id"] for item in workers))
        return "recovery workers started; queued work may execute; group is not quiescent"
    if group["backend"]["State"]["Status"] == "running":
        close_admission(url, token)
    stop_services(workers)
    if command == "drain":
        return "workers stopped; backend/RS remain available; group is not quiescent"
    assert_business_settled(config)
    stop_services([group["backend"]])
    stop_services([group["repository-service"]])
    return "group processes stopped; retain configuration, queues and all business facts"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("drain", "stop-group", "start-recovery"))
    parser.add_argument("--storage-layout", type=Path, required=True)
    parser.add_argument("--resource-profile", type=Path, required=True)
    parser.add_argument("--compose-file", type=Path, action="append", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000")
    parser.add_argument("--internal-bearer-token-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        parsed = urlsplit(args.backend_url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username
                or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
            raise ValueError("backend URL must be an HTTP origin without credentials")
        config = DeploymentConfig.load(args.storage_layout.absolute(), args.resource_profile.absolute())
        token = read_token(args.internal_bearer_token_file)
        compose = ["docker", "compose", "-p", args.project]
        for path in args.compose_file:
            compose.extend(("-f", str(path.absolute())))
        rendered = subprocess.run([*compose, "config", "--format", "json"], capture_output=True, text=True, timeout=30)
        if rendered.returncode:
            raise ValueError("Compose configuration validation failed")
        services = json.loads(rendered.stdout)["services"]
        expected = set(worker_services(config.resources.worker.count))
        if {name for name in services if name == "worker" or name.startswith("worker-")} != expected:
            raise ValueError("Compose fixed worker service list differs from profile")
        print(manage(args.command, config, args.project, args.backend_url, token))
        return 0
    except ValueError as exc:
        import sys
        print(f"maintenance failed: {exc}; gate is not reopened; preserve original group", file=sys.stderr)
        return 2
    except (OSError, KeyError, sqlite3.Error, subprocess.SubprocessError):
        # Exception messages can contain URLs, file content or Compose environment.
        # The helpers use fixed diagnostic text; unexpected failures stay redacted.
        import sys
        print("maintenance failed; admission is never reopened automatically; preserve original group and inspect service diagnostics", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
