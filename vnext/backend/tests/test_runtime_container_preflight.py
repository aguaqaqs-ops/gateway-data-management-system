"""Minimal real-container deployment proofs; complete business gates belong to G."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.serial]
VNEXT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("role,fault", (("backend", None), ("worker", None),
    ("repository_service", None), ("backend", "readonly"), ("backend", "marker"), ("backend", "unmounted"),
    ("worker", "memory"), ("repository_service", "permissions")))
def test_real_bind_and_cgroup_preflight_refuses_invalid_deployments(tmp_path: Path, role: str, fault: str | None) -> None:
    image = os.environ.get("GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE")
    if not image:
        pytest.fail("verified preloaded dependency image is required")
    subprocess.run([sys.executable, str(VNEXT / "scripts/tests/runtime_config_fixture.py"), str(tmp_path)],
        capture_output=True, text=True, check=True, timeout=30)
    storage = json.loads((tmp_path / "storage-layout.json").read_bytes())
    profile = json.loads((tmp_path / "resource-profile.json").read_bytes())
    prefix = "rs-" if role == "repository_service" else "be-"
    selected = {slot: root for slot, root in storage["roots"].items() if slot.startswith(prefix)}
    first = next(iter(selected.values()))
    if fault == "marker":
        marker = Path(first["source"]) / ".gateway-storage.json"
        marker.chmod(0o644)
        marker.write_text("{}")
    if fault == "permissions":
        Path(first["source"]).chmod(0o000)
    resources = profile["worker"] if role == "worker" else profile[role]
    memory = resources["memory_envelope_bytes"] if role == "worker" else resources["memory_limit_bytes"]
    name = "gateway-f-preflight-" + uuid4().hex
    command = ["docker", "run", "--rm", "--name", name, "--label", "gateway.test-task=p7-s1a-f",
        "--pull=never", "--network=none", "--cgroupns=host", "--memory=" + str(memory - 1 if fault == "memory" else memory),
        "--memory-swap=" + str(memory), "--cpus=" + str(resources["cpu_limit"]),
        "--user=" + ("65534:65534" if fault == "permissions" else "0:0"),
        "--env", "PYTHONDONTWRITEBYTECODE=1",
        "--env", "PYTHONPATH=/workspace/vnext/backend/src:/workspace/vnext/shared_kernel/src:/workspace/vnext/repository_service/src",
        "--mount", f"type=bind,src={VNEXT},dst=/workspace/vnext,readonly"]
    for index, item in enumerate(selected.values()):
        if index == 0 and fault == "unmounted":
            continue
        command += ["--mount", f"type=bind,src={item['source']},dst={item['path']}" + (",readonly" if index == 0 and fault == "readonly" else "")]
    command += ["--mount", f"type=bind,src={tmp_path},dst=/configuration,readonly", "--entrypoint", "python", image, "-c"]
    package = "gateway_repository_service" if role == "repository_service" else "gateway_backend"
    script = f"from pathlib import Path; from {package}.deployment_config import DeploymentConfig; from {package}.runtime_preflight import RuntimePreflight; RuntimePreflight(DeploymentConfig.load(Path('/configuration/storage-layout.json'), Path('/configuration/resource-profile.json')), {role!r}); print('PREFLIGHT_OK')"
    try:
        completed = subprocess.run([*command, script], capture_output=True, text=True, check=False, timeout=30)
        if fault is None:
            assert completed.returncode == 0, completed.stdout + completed.stderr
            assert "PREFLIGHT_OK" in completed.stdout
        else:
            assert completed.returncode != 0, completed.stdout + completed.stderr
            assert "PREFLIGHT_OK" not in completed.stdout
            assert "ValueError" in completed.stderr
        # No DB or service directories have been initialized by a preflight.
        for item in selected.values():
            path = Path(item["source"])
            path.chmod(0o755)
            assert {child.name for child in path.iterdir()} == {".gateway-storage.json"}
    finally:
        subprocess.run(["docker", "rm", "--force", name], capture_output=True, check=False, timeout=15)
