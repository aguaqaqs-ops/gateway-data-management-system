"""Minimal real-container deployment proofs; complete business gates belong to G."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
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
    prepared = subprocess.run([sys.executable, str(VNEXT / "scripts/tests/runtime_config_fixture.py"), str(tmp_path)],
        capture_output=True, text=True, check=False, timeout=30)
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr
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
    script = f"import sys; sys.path.insert(0, '/workspace/vnext/scripts'); from pathlib import Path; from host_runtime_config import DeploymentConfig, RuntimePreflight; RuntimePreflight(DeploymentConfig.load(Path('/configuration/storage-layout.json'), Path('/configuration/resource-profile.json')), {role!r}); print('PREFLIGHT_OK')"
    try:
        completed = subprocess.run([*command, script], capture_output=True, text=True, check=False, timeout=30)
        if fault is None:
            assert completed.returncode == 0, completed.stdout + completed.stderr
            assert "PREFLIGHT_OK" in completed.stdout
        else:
            assert completed.returncode != 0, completed.stdout + completed.stderr
            assert "PREFLIGHT_OK" not in completed.stdout
            expected = "DeploymentIdentityChanged" if fault in {"marker", "unmounted"} else "ValueError"
            assert expected in completed.stderr
        # No DB or service directories have been initialized by a preflight.
        for item in selected.values():
            path = Path(item["source"])
            path.chmod(0o755)
            assert {child.name for child in path.iterdir()} == {".gateway-storage.json"}
    finally:
        subprocess.run(["docker", "rm", "--force", name], capture_output=True, check=False, timeout=15)


@pytest.mark.parametrize("role,split", (("backend", False), ("worker", False),
                                       ("repository_service", True), ("backend", True)))
def test_production_renderer_applies_actual_compose_limits_and_role_mounts(tmp_path: Path, role: str, split: bool) -> None:
    image = os.environ.get("GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE")
    if not image:
        pytest.fail("verified dependency image required")
    with tempfile.TemporaryDirectory(prefix="gateway-f-split-", dir="/dev/shm") as temporary:
        prepared = subprocess.run([sys.executable, str(VNEXT / "scripts/tests/runtime_config_fixture.py"), str(tmp_path),
            *(["--split-root", temporary] if split else [])], capture_output=True, text=True, check=False, timeout=30)
        assert prepared.returncode == 0, prepared.stdout + prepared.stderr
        storage = json.loads((tmp_path / "storage-layout.json").read_bytes())
        if split:
            assert Path(storage["roots"]["be-export"]["source"]).stat().st_dev != Path(storage["roots"]["be-metadata"]["source"]).stat().st_dev
            assert Path(storage["roots"]["rs-scratch"]["source"]).stat().st_dev != Path(storage["roots"]["rs-metadata"]["source"]).stat().st_dev
        script = ("import sys,json; sys.path.insert(0,'/workspace/vnext/scripts'); "
            "from pathlib import Path; from host_runtime_config import DeploymentConfig,RuntimePreflight; "
            f"guard=RuntimePreflight(DeploymentConfig.load(Path('/run/gateway/storage-layout.json'),Path('/run/gateway/resource-profile.json')),{role!r}); "
            "print('COMPOSE_PREFLIGHT_OK ' + json.dumps(guard.observations(),sort_keys=True))")
        service = "repository-service" if role == "repository_service" else role
        override = tmp_path / "source-proof.json"
        override.write_text(json.dumps({"services": {service: {"image": image, "user": "0:0",
            "entrypoint": ["python", "-c", script], "command": [],
            "environment": {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "/workspace/vnext/shared_kernel/src"},
            "volumes": [{"type": "bind", "source": str(VNEXT), "target": "/workspace/vnext", "read_only": True,
                         "bind": {"create_host_path": False}}]}}}))
        secret = tmp_path / "token"
        secret.write_text("fixture-only")
        mapping = tmp_path / "mapping.json"
        mapping.write_text('{"mappings":[]}')
        environment = {**os.environ, "GATEWAY_P2R2_BEARER_TOKEN_FILE": str(secret),
            "GATEWAY_BACKEND_SESSION_FILE": str(secret), "GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE": str(secret),
            "GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE": str(mapping)}
        project = "gateway-f-render-" + uuid4().hex[:12]
        command = ["docker", "compose", "-p", project, "-f", str(VNEXT / "deploy/compose.yaml"),
                   "-f", str(tmp_path / "compose-runtime.json"), "-f", str(override)]
        try:
            rendered = subprocess.run([*command, "config", "--format", "json"], env=environment,
                capture_output=True, text=True, check=False, timeout=30)
            assert rendered.returncode == 0, rendered.stdout + rendered.stderr
            effective = json.loads(rendered.stdout)["services"][service]
            assert effective["deploy"]["replicas"] == 1
            configured_roots = [item for item in effective["volumes"] if item["target"].startswith("/var/lib/gateway/")]
            assert len(configured_roots) == (4 if role == "repository_service" else 6)
            assert all(("rs-" if role == "repository_service" else "be-") in item["target"] for item in configured_roots)
            result = subprocess.run([*command, "run", "--rm", "--no-deps", "--pull", "never", service],
                env=environment, capture_output=True, text=True, check=False, timeout=45)
            assert result.returncode == 0, result.stdout + result.stderr
            assert "COMPOSE_PREFLIGHT_OK " in result.stdout
            print(result.stdout, flush=True)
        finally:
            subprocess.run([*command, "down", "--volumes", "--remove-orphans"], env=environment,
                capture_output=True, check=False, timeout=30)


@pytest.mark.parametrize("retain", (False, True))
def test_backend_harness_removes_successful_owned_binds_and_retains_failed_state(tmp_path: Path, retain: bool) -> None:
    from tests.support import compose_gate_harness as harness

    image = os.environ["GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE"]
    secret = tmp_path / "token"
    secret.write_text("fixture-only")
    env = {**os.environ, "COMPOSE_PROJECT_NAME": "gateway-f-be-owner-" + uuid4().hex[:12],
        "GATEWAY_P2R2_BEARER_TOKEN_FILE": str(secret), "GATEWAY_BACKEND_SESSION_FILE": str(secret),
        "GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE": str(secret), "GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE": str(secret)}
    harness.prepare_runtime_config(env)
    directory, _owner = harness._runtime_fixtures[env["COMPOSE_PROJECT_NAME"]]
    override = Path(env["GATEWAY_RUNTIME_COMPOSE_OVERRIDE"])
    document = json.loads(override.read_bytes())
    document["services"]["backend"].update({"image": image, "user": "0:0", "entrypoint": ["python", "-c",
        "from pathlib import Path; Path('/var/lib/gateway/be-durable/owned-proof').write_bytes(b'preserved')"], "command": []})
    override.write_text(json.dumps(document))
    try:
        try:
            completed = harness.run_compose(env, "run", "--rm", "--no-deps", "--pull", "never", "backend")
            assert completed.returncode == 0, completed.stdout + completed.stderr
            if retain:
                raise RuntimeError("injected owner failure after actual Compose run")
        finally:
            harness.cleanup_compose_project_artifacts(env)
    except RuntimeError as exc:
        assert retain and str(exc) == "injected owner failure after actual Compose run"
    assert directory.exists() is retain
    if retain:
        assert (directory / "roots/be-durable/owned-proof").read_bytes() == b"preserved"
        print("FAILED_BACKEND_RUNTIME_RETAINED=" + str(directory), flush=True)
    assert "GATEWAY_RUNTIME_COMPOSE_OVERRIDE" not in env
