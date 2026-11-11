#!/usr/bin/env python3
"""Render standard bind deployment; check/init run only on the deployment host."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from host_runtime_config import DeploymentConfig, check_host, initialize_host
from worker_deployment import check_workers


def render(config: DeploymentConfig, storage: Path, resources: Path) -> dict[str, object]:
    services: dict[str, object] = {}
    for role, service_name in (("backend", "backend"), ("worker", "worker"), ("repository_service", "repository-service")):
        profile = config.resources.worker if role == "worker" else getattr(config.resources, role)
        memory = profile.memory_envelope_bytes if role == "worker" else profile.memory_limit_bytes
        mounts = [{"type": "bind", "source": root.source, "target": root.path,
                   "bind": {"create_host_path": False}}
                  for root in config.storage.role_roots(role).values()]
        mounts.extend({"type": "bind", "source": str(source), "target": target,
                       "read_only": True, "bind": {"create_host_path": False}}
                      for source, target in ((storage, "/run/gateway/storage-layout.json"),
                                             (resources, "/run/gateway/resource-profile.json")))
        services[service_name] = {"volumes": mounts, "mem_limit": memory,
            "memswap_limit": memory + profile.swap_limit_bytes, "cpus": profile.cpu_limit,
            "cgroup": "host", "deploy": {"replicas": 1},
            "environment": {"GATEWAY_STORAGE_LAYOUT_FILE": "/run/gateway/storage-layout.json",
                            "GATEWAY_RESOURCE_PROFILE_FILE": "/run/gateway/resource-profile.json"}}
    worker = services["worker"]
    assert isinstance(worker, dict)
    worker["environment"]["GATEWAY_BACKEND_OPERATION_WORKER_INSTANCE_INDEX"] = "1"
    for index in range(2, config.resources.worker.count + 1):
        # Inherit the production worker definition, including its one image tag.
        # Only rendered mounts/resources and the fixed application index differ.
        services[f"worker-{index}"] = {
            **worker,
            "extends": {"file": str(Path(__file__).resolve().parents[1] / "deploy/compose.yaml"),
                        "service": "worker"},
            "environment": {**worker["environment"],
                            "GATEWAY_BACKEND_OPERATION_WORKER_INSTANCE_INDEX": str(index)},
        }
    return {"services": services}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-layout", type=Path, required=True)
    parser.add_argument("--resource-profile", type=Path, required=True)
    parser.add_argument("command", choices=("render", "check-host", "init-layout", "check-layout", "check-workers"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--project")
    args = parser.parse_args()
    try:
        storage, resources = args.storage_layout.absolute(), args.resource_profile.absolute()
        config = DeploymentConfig.load(storage, resources)
        if args.command == "render":
            if args.output is None:
                raise ValueError("render requires --output outside the source worktree")
            worktree = Path(__file__).resolve().parents[2]
            destination = args.output.resolve()
            if worktree == destination or worktree in destination.parents:
                raise ValueError("rendered output must be outside the source worktree")
            payload = json.dumps(render(config, storage, resources), indent=2) + "\n"
            with destination.open("x", encoding="utf-8") as stream:
                stream.write(payload)
        elif args.command == "check-workers":
            print(json.dumps(check_workers(config, args.project), sort_keys=True))
        elif args.command == "init-layout":
            initialize_host(config)
        else:
            check_host(config, markers=args.command == "check-layout")
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"deployment configuration refused: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
