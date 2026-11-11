"""Inspect the fixed worker services of one explicit Compose project."""
from __future__ import annotations

import json
import subprocess
from typing import Any

from host_runtime_config import DeploymentConfig

INSTANCE_ENV = "GATEWAY_BACKEND_OPERATION_WORKER_INSTANCE_INDEX"


def worker_services(count: int) -> tuple[str, ...]:
    return ("worker", *(f"worker-{index}" for index in range(2, count + 1)))


def _docker(*args: str) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True,
                            check=False, timeout=30)
    if result.returncode:
        raise ValueError("worker deployment inspection failed: " + result.stderr[-1000:])
    return result.stdout


def validate_workers(config: DeploymentConfig, project: str,
                     containers: list[dict[str, Any]], *,
                     allowed_states: tuple[str, ...] = ("running",)) -> dict[str, dict[str, Any]]:
    """Reject missing, scaled, stopped or differently configured worker processes."""
    expected = worker_services(config.resources.worker.count)
    found: dict[str, dict[str, Any]] = {}
    profile = config.resources.worker
    for container in containers:
        labels = container["Config"].get("Labels") or {}
        if labels.get("com.docker.compose.project") != project:
            raise ValueError("container does not belong to the selected Compose project")
        service = labels.get("com.docker.compose.service", "")
        if service != "worker" and not service.startswith("worker-"):
            continue
        if (service not in expected or service in found
                or labels.get("com.docker.compose.container-number") != "1"
                or labels.get("com.docker.compose.oneoff", "False").lower() != "false"):
            raise ValueError("unexpected or duplicate fixed worker service: " + service)
        index = expected.index(service) + 1
        environment = dict(item.split("=", 1) for item in container["Config"]["Env"])
        host = container["HostConfig"]
        if (environment.get(INSTANCE_ENV) != str(index)
                or container["State"].get("Status") not in allowed_states
                or host["Memory"] != profile.memory_envelope_bytes
                or host["MemorySwap"] != profile.memory_envelope_bytes + profile.swap_limit_bytes
                or host["NanoCpus"] != round(profile.cpu_limit * 1_000_000_000)
                or host["RestartPolicy"]["Name"] != "no"):
            raise ValueError("fixed worker identity/state/resources differ: " + service)
        found[service] = {"container_id": container["Id"], "image": container["Image"],
                          "instance_index": index, "memory_bytes": host["Memory"],
                          "memory_swap_bytes": host["MemorySwap"], "nano_cpus": host["NanoCpus"]}
    if set(found) != set(expected):
        raise ValueError("missing fixed worker services: " + ",".join(set(expected) - set(found)))
    if len({entry["image"] for entry in found.values()}) != 1:
        raise ValueError("fixed workers must use the same immutable image")
    return found


def check_workers(config: DeploymentConfig, project: str) -> dict[str, dict[str, Any]]:
    return validate_workers(config, project, inspect_project(project))


def inspect_project(project: str) -> list[dict[str, Any]]:
    """Select only containers carrying the exact explicit Compose project label."""
    if not project or project.startswith("-"):
        raise ValueError("an explicit Compose project is required")
    ids = _docker("ps", "-aq", "--filter", "label=com.docker.compose.project=" + project).split()
    containers = json.loads(_docker("inspect", *ids)) if ids else []
    return containers
