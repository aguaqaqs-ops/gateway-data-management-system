"""Unit tests for the S7 Compose lifecycle harness."""

from __future__ import annotations

import ast
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest

from support.compose_build_harness import CANDIDATE_LABEL
from support.snapshot_admin_harness import RestoreProcedureError
from support.versioned_fixture_consumer_harness import parse_consumer_summary
from support import compose_lifecycle_harness as harness

pytestmark = pytest.mark.unit

_SHA = "a" * 40
_LOCK = "b" * 64
_IMAGE_ID = "sha256:" + "c" * 64
_TOKEN = "compose-e2e-bearer-token"
_HOST_PATH = "/var/lib/gateway/repository"
_VALID_SUMMARY = (
    '{"c0":"commit-c0","c1":"commit-c1","c2":"commit-c2",'
    '"main_commit":"commit-c2","repository_id":"018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11",'
    '"status":"ok"}'
)

COMPOSE_BOUNDARY_FAULTS: tuple[tuple[str, dict[str, object], str], ...] = (
    (
        "published-string-port",
        {
            "services": {
                "repository-service": {"ports": ["8000:8000"]},
            }
        },
        "must not publish host ports",
    ),
    (
        "published-mapping-port",
        {
            "services": {
                "repository-service": {"ports": [{"target": 8000, "published": 8000}]},
            }
        },
        "must not publish host ports",
    ),
    (
        "docker-socket-string",
        {
            "services": {
                "repository-service": {"volumes": ["/var/run/docker.sock:/var/run/docker.sock"]},
            }
        },
        "must not mount the Docker socket",
    ),
    (
        "docker-socket-mapping",
        {
            "services": {
                "repository-service": {
                    "volumes": [{"source": "/var/run/docker.sock", "target": "/var/run/docker.sock"}]
                },
            }
        },
        "must not mount the Docker socket",
    ),
    (
        "host-root-mount",
        {
            "services": {
                "repository-service": {"volumes": [{"source": "/", "target": "/host"}]},
            }
        },
        "must not mount the host root",
    ),
    (
        "resident-client",
        {
            "services": {
                "repository-service": {},
                "repository-client": {"image": "gateway-repository-client-e2e:local"},
            }
        },
        "resident client or snapshot service",
    ),
    (
        "resident-snapshot",
        {
            "services": {
                "repository-service": {},
                "snapshot-operator": {"image": "gateway-repository-service:local"},
            }
        },
        "resident client or snapshot service",
    ),
)

READINESS_CASES: tuple[tuple[str, str], ...] = (
    ("healthy", "ready"),
    ("healthy\n", "ready"),
    ("starting", "not_ready"),
    ("unhealthy", "not_ready"),
    ("", "not_ready"),
)

WRONG_NETWORK_ENDPOINTS: tuple[str, ...] = (
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://0.0.0.0:8000",
    "https://[::1]/",
)

SUMMARY_FAULTS: tuple[tuple[str, str], ...] = (
    ("multiline", _VALID_SUMMARY + "\n"),
    ("extra-key", _VALID_SUMMARY[:-1] + ',"path":"/tmp"}'),
    ("missing-status", '{"repository_id":"018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11","c0":"c0","c1":"c1","c2":"c2","main_commit":"c2"}'),
    ("timeout-shape", '{"status":"timeout"}'),
    ("empty", ""),
)

NON_EMPTY_RESTORE_LISTINGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("layout-component", ("control",)),
    ("ordinary-file", ("root.tar",)),
    ("nested-keep-and-extra", ("lost+found", "service-state")),
)


def _valid_service_config() -> dict[str, object]:
    return {
        "services": {
            "repository-service": {
                "image": "gateway-repository-service:local",
                "volumes": ["repository-service-data:/var/lib/gateway/repository"],
            }
        }
    }


def test_allocate_compose_resources_uses_stable_prefix_and_unique_suffix() -> None:
    first = harness.allocate_compose_resources("inside")
    second = harness.allocate_compose_resources("inside")
    assert first.project.startswith("gateway-p2r6-s7-inside-")
    assert first.project != second.project
    assert first.data_volume == f"{first.project}_repository-service-data"
    assert first.restore_volume == f"{first.project}_restore"
    assert first.token_filename == f"{first.project}.token"
    assert first.network_name == f"{first.project}_default"
    assert first.restore_volume in first.allowed_names


@pytest.mark.parametrize("role", ["", "Inside", "has_underscore", "a" * 40])
def test_allocate_compose_resources_rejects_invalid_role(role: str) -> None:
    with pytest.raises(ValueError, match="role"):
        harness.allocate_compose_resources(role)


def test_allocate_compose_resources_rejects_invalid_suffix() -> None:
    with pytest.raises(ValueError, match="suffix"):
        harness.allocate_compose_resources("import", suffix="short")


def test_write_token_file_is_owner_read_only(tmp_path: Path) -> None:
    path = harness.write_token_file(tmp_path / "token", _TOKEN)
    assert path.read_text(encoding="utf-8") == _TOKEN
    assert path.stat().st_mode & 0o777 == 0o400


def test_parse_rendered_compose_config_accepts_p2r2_service_without_ports() -> None:
    config = harness.parse_rendered_compose_config(_valid_service_config())
    harness.assert_p2r2_compose_boundary(config)
    assert config.repository_service.published_ports == ()
    assert config.resident_client_services == ()


def test_parse_rendered_compose_config_accepts_json_string() -> None:
    config = harness.parse_rendered_compose_config(json.dumps(_valid_service_config()))
    harness.assert_p2r2_compose_boundary(config)


@pytest.mark.parametrize(
    ("payload", "match"),
    [(payload, match) for _name, payload, match in COMPOSE_BOUNDARY_FAULTS],
    ids=[name for name, _payload, _match in COMPOSE_BOUNDARY_FAULTS],
)
def test_assert_p2r2_compose_boundary_rejects_faults(
    payload: dict[str, object],
    match: str,
) -> None:
    config = harness.parse_rendered_compose_config(payload)
    with pytest.raises(AssertionError, match=match):
        harness.assert_p2r2_compose_boundary(config)


def test_force_recreate_service_command_does_not_use_compose_restart() -> None:
    command = harness.force_recreate_service_command(project="gateway-p2r6-s7-import-abcdefabcdef")
    assert "restart" not in command
    assert command[-5:] == ["up", "-d", "--no-build", "--force-recreate", "repository-service"]


def test_parse_service_network_discovery_records_distinct_endpoints() -> None:
    discovery = harness.parse_service_network_discovery(
        {
            "gateway-p2r6-s7-inside-aaaaaaaaaaaa_default": {
                "NetworkID": "nid-1",
                "Gateway": "172.18.0.1",
                "IPAddress": "172.18.0.6",
            }
        },
        project="gateway-p2r6-s7-inside-aaaaaaaaaaaa",
    )
    assert discovery.inside_endpoint == "http://repository-service:8000"
    assert discovery.gate_host_endpoint == "http://172.18.0.6:8000"
    assert discovery.inside_endpoint != discovery.gate_host_endpoint
    assert discovery.gateway_ipv4 == "172.18.0.1"
    assert discovery.network_id == "nid-1"


def test_parse_service_network_discovery_rejects_loopback_service_ip() -> None:
    with pytest.raises(ValueError, match="host-port loopback"):
        harness.parse_service_network_discovery(
            {
                "demo_default": {
                    "NetworkID": "nid-1",
                    "Gateway": "172.18.0.1",
                    "IPAddress": "127.0.0.1",
                }
            },
            project="demo",
        )


@pytest.mark.parametrize("endpoint", WRONG_NETWORK_ENDPOINTS)
def test_assert_not_host_port_endpoint_rejects_published_forms(endpoint: str) -> None:
    with pytest.raises(ValueError, match="host-port"):
        harness.assert_not_host_port_endpoint(endpoint)


@pytest.mark.parametrize(("status", "expected"), READINESS_CASES)
def test_classify_readiness(status: str, expected: str) -> None:
    assert harness.classify_readiness(status) == expected


def test_classify_client_auth_failure_for_wrong_token() -> None:
    assert (
        harness.classify_client_auth_failure(returncode=1, summary=None, http_status=401)
        == "unauthorized"
    )
    assert harness.classify_client_auth_failure(returncode=1, summary=None) == "failed"
    parsed = harness.parse_client_summary(_VALID_SUMMARY)
    assert harness.classify_client_auth_failure(returncode=0, summary=parsed) == "ok"


@pytest.mark.parametrize(
    "names",
    [listing for _label, listing in NON_EMPTY_RESTORE_LISTINGS],
    ids=[label for label, _listing in NON_EMPTY_RESTORE_LISTINGS],
)
def test_assert_restore_volume_listing_empty_rejects_non_empty(names: tuple[str, ...]) -> None:
    with pytest.raises(RestoreProcedureError, match="not empty"):
        harness.assert_restore_volume_listing_empty(names)


def test_assert_restore_volume_listing_empty_allows_lost_and_found() -> None:
    harness.assert_restore_volume_listing_empty(())
    harness.assert_restore_volume_listing_empty(("lost+found",))


def test_parse_client_summary_matches_consumer_harness() -> None:
    assert harness.parse_client_summary(_VALID_SUMMARY) == parse_consumer_summary(_VALID_SUMMARY)
    summary = harness.assert_client_stdout_safe(_VALID_SUMMARY)
    assert UUID(summary["repository_id"])


@pytest.mark.parametrize(
    "stdout",
    [stdout for _name, stdout in SUMMARY_FAULTS],
    ids=[name for name, _stdout in SUMMARY_FAULTS],
)
def test_parse_client_summary_rejects_faults(stdout: str) -> None:
    assert harness.parse_client_summary(stdout) is None
    with pytest.raises(AssertionError, match="typed consumer summary"):
        harness.assert_client_stdout_safe(stdout)


def test_assert_client_stdout_safe_rejects_secret_and_path_leak() -> None:
    leaked = (
        '{"status":"ok","repository_id":"018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11",'
        f'"c0":"{_TOKEN}","c1":"c1","c2":"c2","main_commit":"{_HOST_PATH}"}}'
    )
    with pytest.raises(AssertionError, match="secret"):
        harness.assert_client_stdout_safe(leaked, secrets=(_TOKEN,), host_paths=(_HOST_PATH,))


def test_redact_evidence_text_removes_token_and_host_path() -> None:
    text = f"token={_TOKEN} root={_HOST_PATH}"
    redacted = harness.redact_evidence_text(text, secrets=(_TOKEN,), host_paths=(_HOST_PATH,))
    assert _TOKEN not in redacted
    assert _HOST_PATH not in redacted
    assert "<redacted>" in redacted
    assert "<redacted-path>" in redacted


def test_run_command_redacts_secrets_on_failure() -> None:
    completed = subprocess.CompletedProcess(
        args=["docker"],
        returncode=1,
        stdout="",
        stderr=f"auth {_TOKEN} path {_HOST_PATH}",
    )
    with (
        patch("support.compose_lifecycle_harness.subprocess.run", return_value=completed),
        pytest.raises(RuntimeError) as exc_info,
    ):
        harness.run_command(
            ["docker", "compose", "up"],
            secrets=(_TOKEN,),
            host_paths=(_HOST_PATH,),
        )
    rendered = str(exc_info.value)
    assert _TOKEN not in rendered
    assert _HOST_PATH not in rendered


def test_ephemeral_client_env_does_not_include_socket_or_data_root() -> None:
    env = harness.ephemeral_client_env(
        base_url="http://repository-service:8000",
        bearer_token=_TOKEN,
        fixture_root=harness.FIXTURE_ROOT,
    )
    assert set(env) == {
        "GATEWAY_REPOSITORY_BASE_URL",
        "GATEWAY_REPOSITORY_BEARER_TOKEN",
        "GATEWAY_VERSIONED_FIXTURE_ROOT",
    }
    assert "DOCKER_HOST" not in env
    assert str(harness.FIXTURE_ROOT) == env["GATEWAY_VERSIONED_FIXTURE_ROOT"]


def test_ephemeral_client_docker_command_uses_readonly_fixture_mount_and_env_file(
    tmp_path: Path,
) -> None:
    env_file = harness.write_client_env_file(
        tmp_path / "client.env",
        base_url="http://repository-service:8000",
        bearer_token=_TOKEN,
    )
    command = harness.ephemeral_client_docker_command(
        image=harness.DEFAULT_CLIENT_IMAGE,
        fixture_root=harness.FIXTURE_ROOT,
        env_file=env_file,
        network="gateway-p2r6-s7-inside-aaaaaaaaaaaa_default",
    )
    joined = " ".join(command)
    assert "--rm" in command
    assert "readonly" in joined
    assert "/fixtures" in joined
    assert "--env-file" in command
    assert _TOKEN not in joined
    assert "/var/run/docker.sock" not in joined
    assert "--network" in command
    env_file_text = env_file.read_text(encoding="utf-8")
    assert "GATEWAY_REPOSITORY_BEARER_TOKEN=" + _TOKEN in env_file_text
    assert env_file.stat().st_mode & 0o777 == 0o600


def test_host_runner_command_uses_locked_offline_client_project() -> None:
    command = harness.host_runner_command()
    assert command[:5] == ["uv", "run", "--project", str(harness.CLIENT_PROJECT), "--locked"]
    assert "--offline" in command
    assert str(harness.CONSUMER_SCRIPT) in command


def test_client_identity_rejects_free_text_and_formats_host_runner() -> None:
    image = harness.client_image_identity(
        candidate_sha=_SHA,
        client_uv_lock_sha256=_LOCK,
        image_id=_IMAGE_ID,
    )
    assert image.evidence_id() == _IMAGE_ID
    host = harness.host_runner_identity(candidate_sha=_SHA, client_uv_lock_sha256=_LOCK)
    assert host.evidence_id() == (
        f"host-runner:candidate={_SHA};client_uv_lock_sha256={_LOCK}"
    )
    with pytest.raises(ValueError, match="sha256"):
        harness.client_image_identity(
            candidate_sha=_SHA,
            client_uv_lock_sha256=_LOCK,
            image_id="gateway-repository-client-e2e:local",
        )


def test_client_image_matches_requires_candidate_and_client_lock() -> None:
    with patch(
        "support.compose_lifecycle_harness.inspect_image",
        return_value=(_IMAGE_ID, {CANDIDATE_LABEL: _SHA, harness.CLIENT_UV_LOCK_LABEL: _LOCK}),
    ):
        assert harness.client_image_matches(
            harness.DEFAULT_CLIENT_IMAGE,
            candidate_sha=_SHA,
            client_uv_lock_sha256=_LOCK,
        )
    with patch(
        "support.compose_lifecycle_harness.inspect_image",
        return_value=(_IMAGE_ID, {CANDIDATE_LABEL: _SHA, harness.CLIENT_UV_LOCK_LABEL: "0" * 64}),
    ):
        assert not harness.client_image_matches(
            harness.DEFAULT_CLIENT_IMAGE,
            candidate_sha=_SHA,
            client_uv_lock_sha256=_LOCK,
        )


def test_ensure_client_image_skips_rebuild_when_labels_match() -> None:
    with (
        patch.object(harness, "current_client_uv_lock_sha256", return_value=_LOCK),
        patch.object(harness, "client_image_matches", return_value=True),
        patch.object(harness, "_run_client_build") as build,
    ):
        assert harness.ensure_client_image(candidate_sha=_SHA) == harness.DEFAULT_CLIENT_IMAGE
        build.assert_not_called()


def test_ensure_client_image_rebuilds_when_labels_stale() -> None:
    with (
        patch.object(harness, "current_client_uv_lock_sha256", return_value=_LOCK),
        patch.object(harness, "client_image_matches", side_effect=[False, True]),
        patch.object(harness, "_run_client_build") as build,
    ):
        assert harness.ensure_client_image(candidate_sha=_SHA) == harness.DEFAULT_CLIENT_IMAGE
        build.assert_called_once()


def test_run_client_build_timeout_does_not_leak_secrets() -> None:
    with (
        patch.object(harness, "CLIENT_DOCKERFILE", harness.CLIENT_DOCKERFILE),
        patch(
            "support.compose_lifecycle_harness.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["docker"], timeout=1800),
        ),
        pytest.raises(RuntimeError, match="timed out after 1800s") as exc_info,
    ):
        harness._run_client_build(
            harness.DEFAULT_CLIENT_IMAGE,
            candidate_sha=_SHA,
            client_uv_lock_sha256=_LOCK,
        )
    assert _TOKEN not in str(exc_info.value)


def test_refuse_unscoped_deletion_never_deletes_foreign_objects() -> None:
    names = harness.allocate_compose_resources("lifecycle", suffix="aaaaaaaaaaaa")
    kept = harness.refuse_unscoped_deletion((names.restore_volume,), names.allowed_names)
    assert kept == (names.restore_volume,)
    with pytest.raises(RuntimeError, match="outside the generated"):
        harness.refuse_unscoped_deletion(("unrelated-volume",), names.allowed_names)


def _empty_project_docker(
    command: list[str],
    *,
    restore_exists: bool = False,
) -> subprocess.CompletedProcess[str]:
    if command[:3] == ["docker", "compose", "-p"]:
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
    if command[:2] == ["docker", "inspect"]:
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="No such container")
    if command[:3] in (
        ["docker", "container", "ls"],
        ["docker", "network", "ls"],
        ["docker", "volume", "ls"],
    ):
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
    if command[:3] == ["docker", "volume", "inspect"]:
        if restore_exists:
            return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="not found")
    if command[:3] == ["docker", "volume", "rm"]:
        if restore_exists:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        raise AssertionError("must not remove a volume that is not in the generated set")
    raise AssertionError(f"unexpected command: {command}")


def test_cleanup_compose_project_asserts_zero_inventory_and_scoped_restore_remove() -> None:
    names = harness.allocate_compose_resources("import", suffix="bbbbbbbbbbbb")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return _empty_project_docker(command, restore_exists=True)

    with patch("support.compose_lifecycle_harness.subprocess.run", side_effect=fake_run):
        harness.cleanup_compose_project(names, env={})
    volume_rm = [command for command in calls if command[:3] == ["docker", "volume", "rm"]]
    assert volume_rm == [["docker", "volume", "rm", names.restore_volume]]
    hold_inspect = [
        command
        for command in calls
        if command[:2] == ["docker", "inspect"] and command[-1] == f"{names.project}-hold"
    ]
    assert hold_inspect


def test_cleanup_compose_project_skips_missing_restore_volume() -> None:
    names = harness.allocate_compose_resources("import", suffix="cccccccccccc")

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return _empty_project_docker(command, restore_exists=False)

    with patch("support.compose_lifecycle_harness.subprocess.run", side_effect=fake_run):
        harness.cleanup_compose_project(names, env={})


@pytest.mark.serial
def test_wait_healthy_times_out_when_readiness_missing() -> None:
    completed = subprocess.CompletedProcess(
        args=["docker"],
        returncode=0,
        stdout="starting",
        stderr="",
    )
    with (
        patch("support.compose_lifecycle_harness.subprocess.run", return_value=completed),
        patch("support.compose_lifecycle_harness.time.sleep"),
        patch("support.compose_lifecycle_harness.time.monotonic", side_effect=[0.0, 0.0, 10.0]),
        pytest.raises(TimeoutError, match="did not become healthy"),
    ):
        harness.wait_healthy("abc", timeout=5.0, poll_interval=0.0)


def test_client_dockerfile_is_test_only_and_pins_lock() -> None:
    dockerfile = harness.CLIENT_DOCKERFILE.read_text(encoding="utf-8")
    assert f"ARG UV_LOCK_SHA256={harness.current_client_uv_lock_sha256()}" in dockerfile
    assert "org.opencontainers.image.revision" in dockerfile
    assert harness.CLIENT_UV_LOCK_LABEL in dockerfile
    assert "docker.sock" not in dockerfile
    assert "versioned_v1" not in dockerfile
    assert "fixtures/versioned_v1" not in dockerfile
    assert "privileged" not in dockerfile
    assert "USER nobody" in dockerfile
    assert "versioned_fixture_consumer.py" in dockerfile
    compose = harness.COMPOSE_FILE.read_text(encoding="utf-8")
    assert "repository_client/tests/Dockerfile" not in compose
    assert "gateway-repository-client-e2e" not in compose


def test_inspect_networks_command_and_parser() -> None:
    command = harness.inspect_networks_command("abc123")
    assert command[:3] == ["docker", "inspect", "-f"]
    discovery = harness.parse_inspect_networks(
        json.dumps(
            {
                "gateway-p2r6-s7-inside-aaaaaaaaaaaa_default": {
                    "NetworkID": "nid-1",
                    "Gateway": "172.18.0.1",
                    "IPAddress": "172.18.0.6",
                }
            }
        ),
        project="gateway-p2r6-s7-inside-aaaaaaaaaaaa",
    )
    assert discovery.inside_endpoint != discovery.gate_host_endpoint


def test_snapshot_hold_and_volume_commands_use_service_image_not_alpine() -> None:
    image = "gateway-repository-service:local"
    project = "gateway-p2r6-s7-lifecycle-aaaaaaaaaaaa"
    hold = harness.snapshot_hold_command(
        image=image,
        volume="proj_repository-service-data",
        project=project,
    )
    assert "alpine" not in " ".join(hold)
    assert hold[hold.index("--user") + 1] == "gateway"
    assert f"{harness.HOLD_PROJECT_LABEL}={project}" in hold
    assert f"{harness.HOLD_ROLE_LABEL}={harness.HOLD_ROLE_VALUE}" in hold
    assert "gateway_repository_service.snapshot_admin" in hold
    assert hold[-1] == "hold"
    listing = harness.volume_listing_command(image=image, volume="restore-vol")
    assert listing[-6] == "/data"
    copy = harness.copy_volume_command(
        image=image,
        source_volume="src-vol",
        dest_volume="dst-vol",
    )
    assert "alpine" not in " ".join(copy)
    assert image in copy
    check = harness.snapshot_check_command(image=image, volume="restore-vol")
    assert check[check.index("--user") + 1] == "gateway"
    assert "check" in check


def test_parse_hold_ready_and_check_json() -> None:
    ready = harness.parse_hold_ready_json(
        '{"action":"hold","status":"ready","schema_version":1}\n'
    )
    assert ready["status"] == "ready"
    with pytest.raises(ValueError, match="complete ready"):
        harness.parse_hold_ready_json('{"action":"hold","status":"busy"}')
    passed = harness.parse_check_passed_json(
        '{"action":"check","status":"passed","repository_count":1}'
    )
    assert passed["status"] == "passed"
    with pytest.raises(ValueError, match="one JSON line"):
        harness.parse_check_passed_json("{}\n{}")


def test_parse_volume_listing_strips_data_root_and_lost_and_found() -> None:
    names = harness.parse_volume_listing("/data\n/data/lost+found\n/data/control\n")
    assert names == ("control",)
    with pytest.raises(RestoreProcedureError, match="not empty"):
        harness.assert_restore_volume_listing_empty(names)


def test_assert_pinned_consumer_summary_requires_distinct_commits_and_main_c2() -> None:
    summary = harness.parse_client_summary(_VALID_SUMMARY)
    assert summary is not None
    harness.assert_pinned_consumer_summary(summary)
    broken = dict(summary)
    broken["main_commit"] = broken["c1"]
    with pytest.raises(AssertionError, match="main must resolve to c2"):
        harness.assert_pinned_consumer_summary(broken)


def test_hold_container_name_is_project_scoped() -> None:
    project = "gateway-p2r6-s7-lifecycle-aaaaaaaaaaaa"
    assert harness.hold_container_name(project) == f"{project}-hold"
    with pytest.raises(RuntimeError, match="outside the generated"):
        harness.stop_hold_container("foreign-hold", project=project)


def test_create_scoped_volume_refuses_foreign_names() -> None:
    names = harness.allocate_compose_resources("restored", suffix="aaaaaaaaaaaa")
    with pytest.raises(RuntimeError, match="outside the generated"):
        harness.create_scoped_volume("unrelated", allowed=names.allowed_names)


def test_host_runner_env_does_not_keep_venv_overrides() -> None:
    with patch.dict(
        os.environ,
        {"PYTHONPATH": "/tmp/leak", "VIRTUAL_ENV": "/tmp/venv", "PYTHONHOME": "/tmp/home"},
        clear=False,
    ):
        env = harness.host_runner_env(
            base_url="http://172.18.0.6:8000",
            bearer_token=_TOKEN,
        )
    assert "PYTHONPATH" not in env
    assert "VIRTUAL_ENV" not in env
    assert env["GATEWAY_REPOSITORY_BASE_URL"] == "http://172.18.0.6:8000"


def test_host_runner_env_drops_docker_control_variables() -> None:
    leaked = {
        "DOCKER_HOST": "unix:///var/run/docker.sock",
        "DOCKER_CONTEXT": "desktop-linux",
        "DOCKER_CERT_PATH": "/tmp/certs",
        "DOCKER_TLS_VERIFY": "1",
        "DOCKER_CONFIG": "/tmp/docker",
        "DOCKER_API_VERSION": "1.45",
        "PATH": "/usr/bin",
        "HOME": "/home/user",
    }
    with patch.dict(os.environ, leaked, clear=False):
        env = harness.host_runner_env(
            base_url="http://172.18.0.6:8000",
            bearer_token=_TOKEN,
        )
    for key in harness._DOCKER_CONTROL_ENV:
        assert key not in env
    assert "DOCKER_HOST" not in env
    assert env["PATH"] == "/usr/bin"
    assert env["GATEWAY_REPOSITORY_BASE_URL"] == "http://172.18.0.6:8000"


def test_p2r2_project_session_cleans_up_when_start_raises() -> None:
    names = harness.allocate_compose_resources("inside", suffix="dddddddddddd")
    env = {"GATEWAY_REPOSITORY_SERVICE_IMAGE": "img"}
    with patch.object(harness, "cleanup_compose_project") as cleanup:
        with pytest.raises(TimeoutError, match="did not become healthy"):
            with harness.p2r2_project_session(names, env):
                raise TimeoutError("container abc did not become healthy")
    cleanup.assert_called_once()
    assert cleanup.call_args.args[0] is names
    assert cleanup.call_args.args[1] == env


def test_project_inventory_includes_hold_container() -> None:
    with (
        patch.object(harness, "inspect_hold_container", return_value="holdid"),
        patch.object(harness, "docker_objects", return_value=[]),
    ):
        inventory = harness.project_inventory("gateway-p2r6-s7-lifecycle-aaaaaaaaaaaa")
    assert inventory.hold_containers == ("holdid",)
    assert not inventory.is_empty()


def test_remove_hold_container_absent_is_success() -> None:
    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="No such container")
        if command[:3] == ["docker", "rm", "-f"]:
            raise AssertionError("must not rm a missing hold")
        raise AssertionError(f"unexpected command: {command}")

    with patch("support.compose_lifecycle_harness.subprocess.run", side_effect=fake_run):
        harness.remove_hold_container("gateway-p2r6-s7-lifecycle-aaaaaaaaaaaa")


def test_remove_hold_container_propagates_rm_failure() -> None:
    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(command, 0, stdout="abc123\n", stderr="")
        if command[:3] == ["docker", "rm", "-f"]:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="busy")
        raise AssertionError(f"unexpected command: {command}")

    with (
        patch("support.compose_lifecycle_harness.subprocess.run", side_effect=fake_run),
        pytest.raises(RuntimeError, match="failed to remove hold"),
    ):
        harness.remove_hold_container("gateway-p2r6-s7-lifecycle-aaaaaaaaaaaa")


def test_remove_hold_container_asserts_absent_after_rm() -> None:
    inspects = iter(
        [
            subprocess.CompletedProcess(["docker"], 0, stdout="abc123\n", stderr=""),
            subprocess.CompletedProcess(["docker"], 0, stdout="abc123\n", stderr=""),
        ]
    )

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["docker", "inspect"]:
            return next(inspects)
        if command[:3] == ["docker", "rm", "-f"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    with (
        patch("support.compose_lifecycle_harness.subprocess.run", side_effect=fake_run),
        pytest.raises(AssertionError, match="still exists"),
    ):
        harness.remove_hold_container("gateway-p2r6-s7-lifecycle-aaaaaaaaaaaa")


def test_classify_completed_client_uses_http_status_from_stderr() -> None:
    failed = subprocess.CompletedProcess(
        ["uv"],
        1,
        stdout="",
        stderr="RepositoryClientError(status_code=401, error=...)\n",
    )
    assert harness.classify_completed_client(failed) == "unauthorized"
    unreachable = subprocess.CompletedProcess(["uv"], 1, stdout="", stderr="connection refused")
    assert harness.classify_completed_client(unreachable) == "failed"


def test_assert_node_residuals_cleared_rejects_dolt_delta() -> None:
    names = harness.allocate_compose_resources("inside", suffix="eeeeeeeeeeee")
    with (
        patch.object(
            harness,
            "project_inventory",
            return_value=harness.DockerObjectInventory((), (), (), ()),
        ),
        patch.object(harness, "list_dolt_pids", return_value={99}),
        pytest.raises(AssertionError, match="dolt children remain"),
    ):
        harness.assert_node_residuals_cleared(names, dolt_baseline=frozenset())


S7_COMPOSE_NODEIDS: tuple[tuple[str, str], ...] = (
    (
        "test_import_compose_e2e.py",
        "test_compose_repository_service_import_restart_replay",
    ),
    (
        "test_versioned_read_compose_e2e.py",
        "test_compose_remote_client_commit_pinned_read_inside_network",
    ),
    (
        "test_versioned_read_compose_e2e.py",
        "test_compose_remote_client_commit_pinned_read_from_gate_host",
    ),
    (
        "test_versioned_read_compose_e2e.py",
        "test_compose_repository_service_fresh_restart_restored_lifecycle",
    ),
)


S7_NEGATIVE_PROBES: tuple[tuple[str, str], ...] = (
    (
        "test_compose_lifecycle_negative_probes.py",
        "test_compose_missing_readiness_cleans_up",
    ),
    (
        "test_compose_lifecycle_negative_probes.py",
        "test_compose_wrong_token_cleans_up",
    ),
    (
        "test_compose_lifecycle_negative_probes.py",
        "test_compose_wrong_network_cleans_up",
    ),
    (
        "test_compose_lifecycle_negative_probes.py",
        "test_compose_non_empty_restore_target_cleans_up",
    ),
)


def _function_decorator_names(function: ast.FunctionDef) -> list[str]:
    decorator_names: list[str] = []
    for decorator in function.decorator_list:
        parts: list[str] = []
        current: ast.AST = decorator
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
            decorator_names.append(".".join(reversed(parts)))
    return decorator_names


def test_s7_exact_compose_nodeids_collect() -> None:
    tests_root = Path(__file__).resolve().parent
    required_markers = {
        "test_compose_remote_client_commit_pinned_read_inside_network",
        "test_compose_remote_client_commit_pinned_read_from_gate_host",
        "test_compose_repository_service_fresh_restart_restored_lifecycle",
    }
    found: set[str] = set()
    for filename, nodeid in S7_COMPOSE_NODEIDS:
        source = ast.parse((tests_root / filename).read_text(encoding="utf-8"))
        functions = {
            node.name: node for node in source.body if isinstance(node, ast.FunctionDef)
        }
        assert nodeid in functions, f"missing {filename}::{nodeid}"
        found.add(nodeid)
        if nodeid in required_markers:
            decorator_names = _function_decorator_names(functions[nodeid])
            assert "pytest.mark.integration" in decorator_names, nodeid
            assert "pytest.mark.serial" in decorator_names, nodeid
    assert found == {nodeid for _filename, nodeid in S7_COMPOSE_NODEIDS}


def test_s7_negative_probes_collect() -> None:
    tests_root = Path(__file__).resolve().parent
    found: set[str] = set()
    for filename, nodeid in S7_NEGATIVE_PROBES:
        source = ast.parse((tests_root / filename).read_text(encoding="utf-8"))
        functions = {
            node.name: node for node in source.body if isinstance(node, ast.FunctionDef)
        }
        assert nodeid in functions, f"missing {filename}::{nodeid}"
        found.add(nodeid)
        decorator_names = _function_decorator_names(functions[nodeid])
        assert "pytest.mark.integration" in decorator_names, nodeid
        assert "pytest.mark.serial" in decorator_names, nodeid
    assert found == {nodeid for _filename, nodeid in S7_NEGATIVE_PROBES}
