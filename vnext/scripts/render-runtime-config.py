#!/usr/bin/env python3
"""Render standard bind deployment; check/init run only on the deployment host."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Both adapters deliberately keep structural validation stdlib-only. The renderer
# does not compute or substitute a different configuration digest.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend/src"))
from gateway_backend.deployment_config import DeploymentConfig  # noqa: E402
from gateway_backend.runtime_preflight import check_host, initialize_host  # noqa: E402


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
            "cgroup": "host", "deploy": {"replicas": config.resources.worker.count if role == "worker" else 1},
            "environment": {"GATEWAY_STORAGE_LAYOUT_FILE": "/run/gateway/storage-layout.json",
                            "GATEWAY_RESOURCE_PROFILE_FILE": "/run/gateway/resource-profile.json"}}
    return {"services": services}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-layout", type=Path, required=True)
    parser.add_argument("--resource-profile", type=Path, required=True)
    parser.add_argument("command", choices=("render", "check-host", "init-layout", "check-layout"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        storage, resources = args.storage_layout.absolute(), args.resource_profile.absolute()
        config = DeploymentConfig.load(storage, resources)
        if args.command == "render":
            if args.output is None:
                raise ValueError("render requires --output outside the source worktree")
            worktree = Path(__file__).resolve().parents[2]
            destination = args.output.absolute()
            if worktree == destination or worktree in destination.parents:
                raise ValueError("rendered output must be outside the source worktree")
            payload = json.dumps(render(config, storage, resources), indent=2) + "\n"
            with destination.open("x", encoding="utf-8") as stream:
                stream.write(payload)
        elif args.command == "init-layout":
            initialize_host(config)
        else:
            check_host(config, markers=args.command == "check-layout")
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"deployment configuration refused: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
