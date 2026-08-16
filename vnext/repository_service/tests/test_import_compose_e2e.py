"""Production Compose end-to-end tests for Versioned import delivery."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from support.compose_build_harness import ensure_repository_service_image
from support.compose_lifecycle_harness import (
    allocate_compose_resources,
    assert_p2r2_compose_boundary,
    compose_command,
    compose_config_command,
    compose_ps_command,
    force_recreate_service_command,
    list_host_client_pids,
    list_host_thread_idents,
    p2r2_compose_env,
    p2r2_project_session,
    parse_rendered_compose_config,
    run_command,
    wait_healthy,
    write_token_file,
)
from support.snapshot_admin_harness import list_dolt_pids, snapshot_check_temp_homes
from support.import_admission_crash_harness import build_import_package_bytes
from test_import_package import write_artifact

RUNNER = Path(__file__).resolve().parent / "support" / "import_compose_http_runner.py"
_CONTAINER_TOKEN_PATH = "/run/secrets/repository-bearer-token"


@pytest.mark.integration
@pytest.mark.serial
def test_compose_repository_service_import_restart_replay(tmp_path: Path) -> None:
    if shutil.which("docker") is None:
        pytest.fail("docker is required for compose e2e gate")

    names = allocate_compose_resources("import")
    token = "compose-e2e-bearer-token"
    token_file = write_token_file(tmp_path / names.token_filename, token)
    payload_path = tmp_path / "import-package.tar.zst"
    size_bytes, _ = write_artifact(payload_path, build_import_package_bytes())
    assert size_bytes > 0
    state_path = tmp_path / "compose-state.json"
    runner_in_container = "/tmp/import_compose_http_runner.py"
    payload_in_container = "/tmp/import-package.tar.zst"
    state_in_container = "/tmp/compose-state.json"
    host_paths = (str(tmp_path), str(token_file))

    service_image = ensure_repository_service_image()
    env = p2r2_compose_env(token_file=token_file, service_image=service_image)

    with p2r2_project_session(
        names,
        env,
        secrets=(token,),
        host_paths=host_paths,
        service_image=service_image,
        work_root=tmp_path,
        dolt_baseline=frozenset(list_dolt_pids()),
        check_temp_baseline=frozenset(str(path) for path in snapshot_check_temp_homes()),
        client_pid_baseline=list_host_client_pids(),
        thread_baseline=list_host_thread_idents(),
    ):
        rendered = run_command(
            compose_config_command(project=names.project),
            env=env,
            secrets=(token,),
            host_paths=host_paths,
        )
        assert_p2r2_compose_boundary(parse_rendered_compose_config(rendered.stdout))
        inspect = subprocess.run(
            ["docker", "image", "inspect", service_image],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if inspect.returncode != 0:
            raise RuntimeError(f"prebuilt image not present after cache build: {service_image}")
        gateway_uid = int(
            run_command(
                ["docker", "run", "--rm", "--entrypoint", "id", service_image, "-u", "gateway"],
                secrets=(token,),
                host_paths=host_paths,
            ).stdout.strip()
        )
        gateway_gid = int(
            run_command(
                ["docker", "run", "--rm", "--entrypoint", "id", service_image, "-g", "gateway"],
                secrets=(token,),
                host_paths=host_paths,
            ).stdout.strip()
        )
        os.chown(token_file, gateway_uid, gateway_gid)

        run_command(
            compose_command("up", "-d", "--no-build", "repository-service", project=names.project),
            env=env,
            secrets=(token,),
            host_paths=host_paths,
        )
        container_id = run_command(
            compose_ps_command(project=names.project),
            env=env,
            secrets=(token,),
            host_paths=host_paths,
        ).stdout.strip()
        assert container_id
        wait_healthy(container_id)
        mkdir_probe = subprocess.run(
            [
                "docker",
                "exec",
                "-u",
                "gateway",
                container_id,
                "mkdir",
                "/var/lib/gateway/repository/artifacts/.gateway-write-probe",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert mkdir_probe.returncode == 0
        run_command(
            [
                "docker",
                "exec",
                "-u",
                "gateway",
                container_id,
                "rmdir",
                "/var/lib/gateway/repository/artifacts/.gateway-write-probe",
            ],
            secrets=(token,),
            host_paths=host_paths,
        )

        run_command(
            ["docker", "cp", str(RUNNER), f"{container_id}:{runner_in_container}"],
            secrets=(token,),
            host_paths=host_paths,
        )
        run_command(
            ["docker", "cp", str(payload_path), f"{container_id}:{payload_in_container}"],
            secrets=(token,),
            host_paths=host_paths,
        )

        flow = run_command(
            [
                "docker",
                "exec",
                container_id,
                "python",
                runner_in_container,
                "flow",
                "--token-file",
                _CONTAINER_TOKEN_PATH,
                "--payload-path",
                payload_in_container,
                "--idempotency-prefix",
                names.project,
            ],
            secrets=(token,),
            host_paths=host_paths,
        )
        state_path.write_text(flow.stdout.strip(), encoding="utf-8")

        run_command(
            force_recreate_service_command(project=names.project),
            env=env,
            secrets=(token,),
            host_paths=host_paths,
        )
        container_id = run_command(
            compose_ps_command(project=names.project),
            env=env,
            secrets=(token,),
            host_paths=host_paths,
        ).stdout.strip()
        assert container_id
        wait_healthy(container_id)
        run_command(
            ["docker", "cp", str(RUNNER), f"{container_id}:{runner_in_container}"],
            secrets=(token,),
            host_paths=host_paths,
        )
        run_command(
            ["docker", "cp", str(state_path), f"{container_id}:{state_in_container}"],
            secrets=(token,),
            host_paths=host_paths,
        )

        verify = run_command(
            [
                "docker",
                "exec",
                container_id,
                "python",
                runner_in_container,
                "verify",
                "--token-file",
                _CONTAINER_TOKEN_PATH,
                "--state-path",
                state_in_container,
                "--idempotency-prefix",
                names.project,
            ],
            secrets=(token,),
            host_paths=host_paths,
        )
        verify_body = json.loads(verify.stdout.strip())
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        assert verify_body["operation_id"] == saved["operation_id"]
        assert verify_body["status"] == "SUCCEEDED"
        tombs = run_command(
            [
                "docker",
                "exec",
                container_id,
                "sh",
                "-c",
                "find /var/lib/gateway/repository/artifacts -name '.deleting-*' "
                "-o -name '.detach-*' -o -name '.unlink-verify-*' "
                "-o -name '.unlink-stage-*' | wc -l",
            ],
            secrets=(token,),
            host_paths=host_paths,
        )
        assert tombs.stdout.strip() == "0"
        print(f"compose_project={names.project}", flush=True)
