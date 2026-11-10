"""Small current-source Compose owner proof; the full product gate runs in G."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from support import compose_lifecycle_harness as harness

pytestmark = [pytest.mark.integration, pytest.mark.serial]


@pytest.mark.parametrize("retain", (False, True))
def test_actual_rs_harness_starts_with_rendered_roots_and_cleans_only_owned_resources(
    tmp_path: Path, retain: bool,
) -> None:
    image = os.environ["GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE"]
    names = harness.allocate_compose_resources("f-owner")
    token = "isolated-owner-proof"
    token_file = harness.write_token_file(tmp_path / names.token_filename, token)
    env = harness.p2r2_compose_env(token_file=token_file, service_image=image)
    directory = harness._prepare_runtime_volume(names.data_volume, names.project)
    owner = harness._runtime_fixture_owners[names.data_volume][1]
    override = directory / "compose-runtime.json"
    document = json.loads(override.read_bytes())
    document["services"]["repository-service"].update({
        "entrypoint": ["/workspace/vnext/repository_service/docker-entrypoint.sh"],
        "command": ["python", "-m", "uvicorn", "gateway_repository_service.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"],
        "environment": {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "/workspace/vnext/repository_service/src:/workspace/vnext/repository_contracts/src"},
    })
    document["services"]["repository-service"]["volumes"].append({
        "type": "bind", "source": str(harness.VNEXT_ROOT), "target": "/workspace/vnext", "read_only": True,
        "bind": {"create_host_path": False},
    })
    override.write_text(json.dumps(document))
    source_metadata = Path(json.loads((directory / "storage-layout.json").read_bytes())["roots"]["rs-metadata"]["source"])
    original_identity: tuple[int, int, int] | None = None
    try:
        started = harness.start_p2r2_service(names, token_file=token_file, token=token,
            service_image=image, host_paths=(str(tmp_path), str(directory)), env=env)
        actual = harness.run_command(["docker", "exec", "--user", "gateway", started.container_id, "python", "-c",
            "import json,os,urllib.request; from pathlib import Path; "
            "from gateway_repository_service.runtime_preflight import mounts,_cgroup_chain; "
            "from dataclasses import asdict; "
            "print(json.dumps({'role_euid':os.geteuid(),'cgroup':{key:(_cgroup_chain()[0]/key).read_text().strip() for key in ('memory.max','memory.swap.max','cpu.max')},'roots':[asdict(entry) for entry in mounts() if entry.target.startswith('/var/lib/gateway/rs-')]}))"]).stdout
        info = source_metadata.stat()
        original_identity = (info.st_uid, info.st_gid, info.st_mode)
        print("ACTUAL_RS_COMPOSE_OWNER " + actual, flush=True)
        # Foreign ownership cannot authorize even an empty-directory cleanup.
        rejected = subprocess.run(["python3", "-I", str(harness.VNEXT_ROOT / "scripts/tests/runtime_config_fixture.py"),
            str(directory), "--owner", owner + "-foreign", "--cleanup"], capture_output=True, text=True, check=False)
        assert rejected.returncode != 0 and directory.is_dir()
    finally:
        harness.cleanup_compose_project(names, env, service_image=image, retain_runtime=retain)
    assert harness.project_inventory(names.project).is_empty()
    assert subprocess.run(["docker", "volume", "inspect", names.data_volume], capture_output=True).returncode != 0
    assert directory.exists() is retain
    if retain:
        restored_metadata = directory / ("failure-" + names.data_volume) / "rs-metadata"
        info = restored_metadata.stat()
        assert (info.st_uid, info.st_gid, info.st_mode) == original_identity
        print("FAILED_RUNTIME_ORIGINAL_RETAINED=" + str(directory), flush=True)
