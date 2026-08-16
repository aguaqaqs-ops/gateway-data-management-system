"""Focused negative Compose probes for S7 expected-failure cleanup.

These are harness probes, not S7 PASS nodeids. Docker absence fails the test.
"""

from __future__ import annotations

import shutil
from contextlib import AbstractContextManager
from pathlib import Path

import pytest

from support.compose_build_harness import (
    expected_build_metadata,
    ensure_repository_service_image,
)
from support.compose_lifecycle_harness import (
    FIXTURE_ROOT,
    INSIDE_SERVICE_ENDPOINT,
    ComposeResourceNames,
    allocate_compose_resources,
    assert_named_volume_empty,
    classify_completed_client,
    classify_readiness,
    create_scoped_volume,
    discover_started_service_network,
    ensure_client_image,
    inspect_health_command,
    list_host_client_pids,
    p2r2_compose_env,
    p2r2_project_session,
    run_command,
    run_gate_host_consumer_unchecked,
    run_inside_network_consumer_unchecked,
    seed_volume_marker_command,
    start_p2r2_service,
    write_token_file,
)
from support.snapshot_admin_harness import (
    RestoreProcedureError,
    list_dolt_pids,
    snapshot_check_temp_homes,
)

_TOKEN = "compose-e2e-bearer-token"
_WRONG_TOKEN = "compose-e2e-wrong-token"


def _require_docker() -> None:
    if shutil.which("docker") is None:
        pytest.fail("docker is required for compose negative probes")


def _session(
    names: ComposeResourceNames,
    env: dict[str, str],
    *,
    host_paths: tuple[str, ...],
    service_image: str,
    work_root: Path,
) -> AbstractContextManager[None]:
    return p2r2_project_session(
        names,
        env,
        secrets=(_TOKEN, _WRONG_TOKEN),
        host_paths=host_paths,
        service_image=service_image,
        work_root=work_root,
        dolt_baseline=frozenset(list_dolt_pids()),
        check_temp_baseline=frozenset(str(path) for path in snapshot_check_temp_homes()),
        client_pid_baseline=list_host_client_pids(),
    )


@pytest.mark.integration
@pytest.mark.serial
def test_compose_missing_readiness_cleans_up(tmp_path: Path) -> None:
    _require_docker()
    names = allocate_compose_resources("readiness")
    token_file = write_token_file(tmp_path / names.token_filename, _TOKEN)
    host_paths = (str(tmp_path), str(token_file), str(FIXTURE_ROOT))
    service_image = ensure_repository_service_image()
    env = p2r2_compose_env(token_file=token_file, service_image=service_image)
    with _session(names, env, host_paths=host_paths, service_image=service_image, work_root=tmp_path):
        started = start_p2r2_service(
            names,
            token_file=token_file,
            token=_TOKEN,
            service_image=service_image,
            host_paths=host_paths,
            env=env,
            wait=False,
        )
        health = run_command(
            inspect_health_command(started.container_id),
            secrets=(_TOKEN,),
            host_paths=host_paths,
        ).stdout
        assert classify_readiness(health) == "not_ready"


@pytest.mark.integration
@pytest.mark.serial
def test_compose_wrong_token_cleans_up(tmp_path: Path) -> None:
    _require_docker()
    names = allocate_compose_resources("wrongtoken")
    token_file = write_token_file(tmp_path / names.token_filename, _TOKEN)
    host_paths = (str(tmp_path), str(token_file), str(FIXTURE_ROOT))
    service_image = ensure_repository_service_image()
    env = p2r2_compose_env(token_file=token_file, service_image=service_image)
    with _session(names, env, host_paths=host_paths, service_image=service_image, work_root=tmp_path):
        started = start_p2r2_service(
            names,
            token_file=token_file,
            token=_TOKEN,
            service_image=service_image,
            host_paths=host_paths,
            env=env,
        )
        discovery = discover_started_service_network(started)
        completed = run_gate_host_consumer_unchecked(
            base_url=discovery.gate_host_endpoint,
            token=_WRONG_TOKEN,
            secrets=(_TOKEN, _WRONG_TOKEN),
            host_paths=host_paths,
        )
        assert classify_completed_client(completed) == "unauthorized"


@pytest.mark.integration
@pytest.mark.serial
def test_compose_wrong_network_cleans_up(tmp_path: Path) -> None:
    _require_docker()
    names = allocate_compose_resources("wrongnet")
    token_file = write_token_file(tmp_path / names.token_filename, _TOKEN)
    host_paths = (str(tmp_path), str(token_file), str(FIXTURE_ROOT))
    service_image = ensure_repository_service_image()
    client_image = ensure_client_image(candidate_sha=expected_build_metadata().candidate_sha)
    env = p2r2_compose_env(token_file=token_file, service_image=service_image)
    with _session(names, env, host_paths=host_paths, service_image=service_image, work_root=tmp_path):
        start_p2r2_service(
            names,
            token_file=token_file,
            token=_TOKEN,
            service_image=service_image,
            host_paths=host_paths,
            env=env,
        )
        completed = run_inside_network_consumer_unchecked(
            client_image=client_image,
            network=None,
            base_url=INSIDE_SERVICE_ENDPOINT,
            token=_TOKEN,
            env_file=tmp_path / "client.env",
            secrets=(_TOKEN,),
            host_paths=host_paths,
        )
        assert classify_completed_client(completed) == "failed"


@pytest.mark.integration
@pytest.mark.serial
def test_compose_non_empty_restore_target_cleans_up(tmp_path: Path) -> None:
    _require_docker()
    names = allocate_compose_resources("restoreprobe")
    token_file = write_token_file(tmp_path / names.token_filename, _TOKEN)
    host_paths = (str(tmp_path), str(token_file))
    service_image = ensure_repository_service_image()
    env = p2r2_compose_env(token_file=token_file, service_image=service_image)
    with _session(names, env, host_paths=host_paths, service_image=service_image, work_root=tmp_path):
        create_scoped_volume(names.restore_volume, allowed=names.allowed_names)
        run_command(
            seed_volume_marker_command(image=service_image, volume=names.restore_volume),
            secrets=(_TOKEN,),
            host_paths=host_paths,
        )
        with pytest.raises(RestoreProcedureError, match="not empty"):
            assert_named_volume_empty(
                image=service_image,
                volume=names.restore_volume,
                allowed=names.allowed_names,
            )
