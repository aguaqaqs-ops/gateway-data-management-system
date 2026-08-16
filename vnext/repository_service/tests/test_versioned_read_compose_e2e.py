"""Compose end-to-end tests for remote consumer and restored lifecycle nodeids."""

from __future__ import annotations

import shutil
from contextlib import AbstractContextManager
from pathlib import Path

import pytest

from support.compose_build_harness import (
    expected_build_metadata,
    ensure_repository_service_image,
    image_id,
    inspect_image,
)
from support.compose_lifecycle_harness import (
    CLIENT_UV_LOCK_LABEL,
    FIXTURE_ROOT,
    ComposeResourceNames,
    allocate_compose_resources,
    assert_named_volume_empty,
    assert_not_host_port_endpoint,
    check_named_volume,
    client_image_identity,
    compose_stop_command,
    copy_named_volume,
    create_repository_via_http,
    create_scoped_volume,
    current_client_uv_lock_sha256,
    discover_started_service_network,
    ensure_client_image,
    hold_container_name,
    host_runner_identity,
    list_host_client_pids,
    list_host_thread_idents,
    p2r2_compose_env,
    p2r2_project_session,
    recreate_started_service,
    remove_hold_container,
    run_command,
    run_gate_host_consumer,
    run_inside_network_consumer,
    snapshot_hold_command,
    start_p2r2_service,
    stop_hold_container,
    versioned_ref_status,
    wait_hold_container_ready,
    write_token_file,
)
from support.snapshot_admin_harness import list_dolt_pids, snapshot_check_temp_homes

_TOKEN = "compose-e2e-bearer-token"


def _require_docker() -> None:
    if shutil.which("docker") is None:
        pytest.fail("docker is required for compose e2e gate")


def _print_evidence(
    *,
    project: str,
    service_image: str,
    client_identity: str,
    endpoint: str,
    summary: dict[str, object],
) -> None:
    print(f"compose_project={project}", flush=True)
    print(f"service_image_id={image_id(service_image)}", flush=True)
    print(f"client_identity={client_identity}", flush=True)
    print(f"service_endpoint={endpoint}", flush=True)
    print(
        "consumer_summary="
        f"status={summary.get('status')} repository_id={summary.get('repository_id')} "
        f"c0={summary.get('c0')} c1={summary.get('c1')} c2={summary.get('c2')} "
        f"main={summary.get('main_commit')}",
        flush=True,
    )


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
        secrets=(_TOKEN,),
        host_paths=host_paths,
        service_image=service_image,
        work_root=work_root,
        dolt_baseline=frozenset(list_dolt_pids()),
        check_temp_baseline=frozenset(str(path) for path in snapshot_check_temp_homes()),
        client_pid_baseline=list_host_client_pids(),
        thread_baseline=list_host_thread_idents(),
    )


@pytest.mark.integration
@pytest.mark.serial
def test_compose_remote_client_commit_pinned_read_inside_network(tmp_path: Path) -> None:
    _require_docker()
    names = allocate_compose_resources("inside")
    token_file = write_token_file(tmp_path / names.token_filename, _TOKEN)
    host_paths = (str(tmp_path), str(token_file), str(FIXTURE_ROOT))
    service_image = ensure_repository_service_image()
    candidate_sha = expected_build_metadata().candidate_sha
    client_image = ensure_client_image(candidate_sha=candidate_sha)
    client_digest, client_labels = inspect_image(client_image)
    lock_sha = client_labels.get(CLIENT_UV_LOCK_LABEL, current_client_uv_lock_sha256())
    identity = client_image_identity(
        candidate_sha=candidate_sha,
        client_uv_lock_sha256=lock_sha,
        image_id=client_digest,
    )
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
        assert_not_host_port_endpoint(discovery.inside_endpoint)
        summary = run_inside_network_consumer(
            client_image=client_image,
            discovery=discovery,
            token=_TOKEN,
            env_file=tmp_path / "client.env",
            secrets=(_TOKEN,),
            host_paths=host_paths,
        )
        leftover_clients = run_command(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"ancestor={client_image}",
                "--filter",
                f"network={discovery.network_name}",
            ],
            secrets=(_TOKEN,),
            host_paths=host_paths,
        ).stdout.strip()
        assert leftover_clients == ""
        _print_evidence(
            project=names.project,
            service_image=service_image,
            client_identity=identity.evidence_id(),
            endpoint=discovery.inside_endpoint,
            summary=summary,
        )


@pytest.mark.integration
@pytest.mark.serial
def test_compose_remote_client_commit_pinned_read_from_gate_host(tmp_path: Path) -> None:
    _require_docker()
    names = allocate_compose_resources("gatehost")
    token_file = write_token_file(tmp_path / names.token_filename, _TOKEN)
    host_paths = (str(tmp_path), str(token_file), str(FIXTURE_ROOT))
    service_image = ensure_repository_service_image()
    identity = host_runner_identity(
        candidate_sha=expected_build_metadata().candidate_sha,
        client_uv_lock_sha256=current_client_uv_lock_sha256(),
    )
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
        assert discovery.gate_host_endpoint != discovery.inside_endpoint
        assert_not_host_port_endpoint(discovery.gate_host_endpoint)
        summary = run_gate_host_consumer(
            discovery=discovery,
            token=_TOKEN,
            secrets=(_TOKEN,),
            host_paths=host_paths,
        )
        _print_evidence(
            project=names.project,
            service_image=service_image,
            client_identity=identity.evidence_id(),
            endpoint=discovery.gate_host_endpoint,
            summary=summary,
        )


@pytest.mark.integration
@pytest.mark.serial
def test_compose_repository_service_fresh_restart_restored_lifecycle(tmp_path: Path) -> None:
    _require_docker()
    source = allocate_compose_resources("lifecycle")
    restored = allocate_compose_resources("restored")
    token_file = write_token_file(tmp_path / source.token_filename, _TOKEN)
    restore_token_file = write_token_file(tmp_path / restored.token_filename, _TOKEN)
    host_paths = (
        str(tmp_path),
        str(token_file),
        str(restore_token_file),
        str(FIXTURE_ROOT),
    )
    service_image = ensure_repository_service_image()
    identity = host_runner_identity(
        candidate_sha=expected_build_metadata().candidate_sha,
        client_uv_lock_sha256=current_client_uv_lock_sha256(),
    )
    source_env = p2r2_compose_env(token_file=token_file, service_image=service_image)
    restore_env = p2r2_compose_env(token_file=restore_token_file, service_image=service_image)
    with (
        _session(
            source,
            source_env,
            host_paths=host_paths,
            service_image=service_image,
            work_root=tmp_path,
        ),
        _session(
            restored,
            restore_env,
            host_paths=host_paths,
            service_image=service_image,
            work_root=tmp_path,
        ),
    ):
        started = start_p2r2_service(
            source,
            token_file=token_file,
            token=_TOKEN,
            service_image=service_image,
            host_paths=host_paths,
            env=source_env,
        )
        discovery = discover_started_service_network(started)
        fresh = run_gate_host_consumer(
            discovery=discovery,
            token=_TOKEN,
            secrets=(_TOKEN,),
            host_paths=host_paths,
        )
        started = recreate_started_service(started)
        discovery = discover_started_service_network(started)
        restarted = run_gate_host_consumer(
            discovery=discovery,
            token=_TOKEN,
            secrets=(_TOKEN,),
            host_paths=host_paths,
        )
        assert restarted == fresh

        run_command(
            compose_stop_command(project=source.project),
            env=started.env,
            secrets=(_TOKEN,),
            host_paths=host_paths,
        )
        hold_name = hold_container_name(source.project)
        remove_hold_container(source.project)
        run_command(
            snapshot_hold_command(
                image=service_image,
                volume=source.data_volume,
                project=source.project,
            ),
            secrets=(_TOKEN,),
            host_paths=host_paths,
        )
        wait_hold_container_ready(hold_name, secrets=(_TOKEN,), host_paths=host_paths)
        create_scoped_volume(restored.data_volume, allowed=restored.allowed_names)
        assert_named_volume_empty(
            image=service_image,
            volume=restored.data_volume,
            allowed=restored.allowed_names,
        )
        copy_named_volume(
            image=service_image,
            source_volume=source.data_volume,
            dest_volume=restored.data_volume,
            allowed=source.allowed_names | restored.allowed_names,
        )
        stop_hold_container(
            hold_name,
            project=source.project,
            secrets=(_TOKEN,),
            host_paths=host_paths,
        )
        remove_hold_container(source.project)
        check_named_volume(
            image=service_image,
            volume=restored.data_volume,
            allowed=restored.allowed_names,
        )

        started = start_p2r2_service(
            source,
            token_file=token_file,
            token=_TOKEN,
            service_image=service_image,
            host_paths=host_paths,
            env=source_env,
        )
        discovery = discover_started_service_network(started)
        mutation_id = create_repository_via_http(
            base_url=discovery.gate_host_endpoint,
            token=_TOKEN,
            idempotency_key="s7-post-snapshot-mutation",
        )
        assert mutation_id != fresh["repository_id"]

        restored_started = start_p2r2_service(
            restored,
            token_file=restore_token_file,
            token=_TOKEN,
            service_image=service_image,
            host_paths=host_paths,
            env=restore_env,
        )
        restore_discovery = discover_started_service_network(restored_started)
        restored_facts = run_gate_host_consumer(
            discovery=restore_discovery,
            token=_TOKEN,
            secrets=(_TOKEN,),
            host_paths=host_paths,
        )
        assert restored_facts == fresh
        assert (
            versioned_ref_status(
                base_url=restore_discovery.gate_host_endpoint,
                token=_TOKEN,
                repository_id=mutation_id,
            )
            == 404
        )
        _print_evidence(
            project=f"{source.project},{restored.project}",
            service_image=service_image,
            client_identity=identity.evidence_id(),
            endpoint=restore_discovery.gate_host_endpoint,
            summary=restored_facts,
        )
