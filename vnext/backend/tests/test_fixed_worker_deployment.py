"""Host inspection enforces the fixed deployment against actual Docker state."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import runpy
import sys
from typing import Any

import pytest

from gateway_backend.deployment_config import DeploymentConfig, ResourceProfile, StorageLayoutConfig

pytestmark = pytest.mark.unit
VNEXT = Path(__file__).resolve().parents[2]


def test_actual_fixed_workers_reject_scaling_missing_identity_image_and_resource_drift() -> None:
    sys.path.insert(0, str(VNEXT / "scripts"))
    try:
        validate = runpy.run_path(str(VNEXT / "scripts/worker_deployment.py"))["validate_workers"]
    finally:
        sys.path.pop(0)
    fixture = VNEXT / "fixtures/runtime-config/v1"
    resources = json.loads((fixture / "resource-profile.json").read_bytes())
    resources["worker"].update(count=2, active_limit=2, memory_envelope_bytes=16 * 1024**3,
                               kernel_memory_bytes=8 * 1024**3)
    resources["host_budget"].update(memory_bytes=46 * 1024**3, cpu_count=9)
    config = DeploymentConfig(StorageLayoutConfig.from_bytes((fixture / "storage-layout.json").read_bytes()),
                              ResourceProfile.from_bytes(json.dumps(resources).encode()))
    def container(index: int) -> dict[str, Any]:
        return {"Id": str(index), "Image": "sha256:one-worker-build", "State": {"Status": "running"},
            "Config": {"Labels": {"com.docker.compose.project": "ours",
                "com.docker.compose.service": "worker" if index == 1 else "worker-2",
                "com.docker.compose.container-number": "1", "com.docker.compose.oneoff": "False"},
                "Env": [f"GATEWAY_BACKEND_OPERATION_WORKER_INSTANCE_INDEX={index}"]},
            "HostConfig": {"Memory": 16 * 1024**3, "MemorySwap": 16 * 1024**3,
                "NanoCpus": 2_000_000_000, "RestartPolicy": {"Name": "no"}}}
    original = [container(1), container(2)]
    assert set(validate(config, "ours", original)) == {"worker", "worker-2"}
    faults = [original[:1], [*original, container(2)]]
    for path, value in ((["Config", "Env"], ["GATEWAY_BACKEND_OPERATION_WORKER_INSTANCE_INDEX=1"]),
                        (["Config", "Labels", "com.docker.compose.project"], "theirs"),
                        (["Config", "Labels", "com.docker.compose.container-number"], "2"),
                        (["State", "Status"], "exited"), (["Image"], "sha256:different"),
                        (["HostConfig", "Memory"], 1), (["HostConfig", "MemorySwap"], -1),
                        (["HostConfig", "NanoCpus"], 1),
                        (["HostConfig", "RestartPolicy", "Name"], "unless-stopped")):
        changed = deepcopy(original)
        current = changed[1]
        for key in path[:-1]:
            current = current[key]
        current[path[-1]] = value
        faults.append(changed)
    for fault in faults:
        with pytest.raises(ValueError):
            validate(config, "ours", fault)
