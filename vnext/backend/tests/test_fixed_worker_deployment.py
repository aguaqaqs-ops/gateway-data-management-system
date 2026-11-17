"""Host inspection enforces the fixed deployment against actual Docker state."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import runpy
import sys
import subprocess
import time
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
    resources["worker"].update(
        count=2, active_limit=2, memory_envelope_bytes=16 * 1024**3, kernel_memory_bytes=8 * 1024**3
    )
    resources["host_budget"].update(memory_bytes=46 * 1024**3, cpu_count=9)
    config = DeploymentConfig(
        StorageLayoutConfig.from_bytes((fixture / "storage-layout.json").read_bytes()),
        ResourceProfile.from_bytes(json.dumps(resources).encode()),
    )

    def container(index: int) -> dict[str, Any]:
        return {
            "Id": str(index),
            "Image": "sha256:one-worker-build",
            "State": {"Status": "running"},
            "Config": {
                "Labels": {
                    "com.docker.compose.project": "ours",
                    "com.docker.compose.service": "worker" if index == 1 else "worker-2",
                    "com.docker.compose.container-number": "1",
                    "com.docker.compose.oneoff": "False",
                },
                "Env": [f"GATEWAY_BACKEND_OPERATION_WORKER_INSTANCE_INDEX={index}"],
            },
            "HostConfig": {
                "Memory": 16 * 1024**3,
                "MemorySwap": 16 * 1024**3,
                "NanoCpus": 2_000_000_000,
                "RestartPolicy": {"Name": "no"},
            },
        }

    original = [container(1), container(2)]
    assert set(validate(config, "ours", original)) == {"worker", "worker-2"}
    faults = [original[:1], [*original, container(2)]]
    for path, value in (
        (["Config", "Env"], ["GATEWAY_BACKEND_OPERATION_WORKER_INSTANCE_INDEX=1"]),
        (["Config", "Labels", "com.docker.compose.project"], "theirs"),
        (["Config", "Labels", "com.docker.compose.container-number"], "2"),
        (["State", "Status"], "exited"),
        (["Image"], "sha256:different"),
        (["HostConfig", "Memory"], 1),
        (["HostConfig", "MemorySwap"], -1),
        (["HostConfig", "NanoCpus"], 1),
        (["HostConfig", "RestartPolicy", "Name"], "unless-stopped"),
    ):
        changed = deepcopy(original)
        current = changed[1]
        for key in path[:-1]:
            current = current[key]
        current[path[-1]] = value
        faults.append(changed)
    for fault in faults:
        with pytest.raises(ValueError):
            validate(config, "ours", fault)


def test_worker_readiness_requires_current_generation_logs_and_running_fixed_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support import compose_gate_harness as harness

    generation = {
        "worker": "first 0 2026-11-11T16:00:00Z",
        "worker-2": "second 0 2026-11-11T16:00:01Z",
    }
    calls: list[tuple[str, ...]] = []
    verified: list[str] = []
    monkeypatch.setattr(harness, "configured_worker_services", lambda env: tuple(generation))
    monkeypatch.setattr(harness, "capture_worker_container_state", lambda env: generation)

    def logs(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        service = args[-1]
        since = generation[service].rsplit(" ", 1)[1]
        assert args == ("logs", "--no-color", "--since", since, service)
        count = sum(call[-1] == service for call in calls)
        # The first poll has only old-generation ready logs (excluded by --since).
        return subprocess.CompletedProcess(
            args, 0, stdout="" if count == 1 else "code=worker_ready", stderr=""
        )

    monkeypatch.setattr(harness, "run_compose", logs)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        harness,
        "check_fixed_worker_deployment",
        lambda env: verified.append("running-fixed-identity"),
    )
    monkeypatch.setattr(
        harness,
        "assert_running_backend_worker_images_match_build",
        lambda env: verified.append("image"),
    )
    harness.worker_ready({})
    assert len(calls) == 4
    assert verified == ["running-fixed-identity", "image"]


def test_worker_readiness_rejects_generation_change_during_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support import compose_gate_harness as harness

    generations = iter(
        ({"worker": "first 0 2026-11-11T16:00:00Z"}, {"worker": "first 1 2026-11-11T16:00:01Z"})
    )
    monkeypatch.setattr(harness, "configured_worker_services", lambda env: ("worker",))
    monkeypatch.setattr(harness, "capture_worker_container_state", lambda env: next(generations))
    monkeypatch.setattr(
        harness,
        "run_compose",
        lambda env, *args: subprocess.CompletedProcess(
            args, 0, stdout="code=worker_ready", stderr=""
        ),
    )
    with pytest.raises(AssertionError, match="fixed worker containers changed"):
        harness.worker_ready({})


@pytest.mark.parametrize("kernel_threads", (None, 1, 2))
def test_prepare_runtime_config_forwards_optional_kernel_threads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kernel_threads: int | None,
) -> None:
    from tests.support import compose_gate_harness as harness

    commands: list[list[str]] = []
    session = tmp_path / "session.json"
    session.write_text('{"sessions":[]}', encoding="utf-8")
    token = tmp_path / "token"
    token.write_text("fixture-only", encoding="utf-8")
    mapping = tmp_path / "mapping.json"
    mapping.write_text('{"mappings":[]}', encoding="utf-8")
    env: dict[str, str] = {
        "COMPOSE_PROJECT_NAME": "unit-kernel-threads",
        "GATEWAY_BACKEND_SESSION_FILE": str(session),
        "GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE": str(token),
        "GATEWAY_P2R2_BEARER_TOKEN_FILE": str(token),
        "GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE": str(mapping),
    }

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        target = Path(command[command.index("--owner") - 1])
        (target / "storage-layout.json").write_text(
            json.dumps({"environment_id": "development", "group_id": "group-1", "roots": {}}),
            encoding="utf-8",
        )
        (target / "resource-profile.json").write_text(
            json.dumps(
                {
                    "host_budget": {
                        "memory_bytes": 51539607552,
                        "cpu_count": 8,
                        "shared_memory_reserve_bytes": 8589934592,
                        "shared_cpu_reserve": 2,
                    }
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        harness,
        "write_container_readable_text",
        lambda path, text: path.write_text(text),
    )
    try:
        harness.prepare_runtime_config(env, kernel_threads=kernel_threads)
    finally:
        harness._runtime_fixtures.pop(env["COMPOSE_PROJECT_NAME"], None)

    assert len(commands) == 1
    command = commands[0]
    if kernel_threads is None:
        assert "--kernel-threads" not in command
    else:
        idx = command.index("--kernel-threads")
        assert command[idx + 1] == str(kernel_threads)


@pytest.mark.parametrize("bad_threads", (0, -1, True))
def test_prepare_runtime_config_rejects_invalid_kernel_threads(bad_threads: object) -> None:
    from tests.support import compose_gate_harness as harness

    with pytest.raises(ValueError, match="kernel_threads must be a positive integer"):
        harness.prepare_runtime_config(
            {"COMPOSE_PROJECT_NAME": "bad-threads"},
            kernel_threads=bad_threads,  # type: ignore[arg-type]
        )


def test_prepare_runtime_config_rejects_mismatched_existing_override(tmp_path: Path) -> None:
    from tests.support import compose_gate_harness as harness

    override = tmp_path / "compose-runtime.json"
    override.write_text("{}", encoding="utf-8")
    (tmp_path / "resource-profile.json").write_text(
        json.dumps({"worker": {"kernel_threads": 1}}),
        encoding="utf-8",
    )
    env = {"GATEWAY_RUNTIME_COMPOSE_OVERRIDE": str(override)}
    harness.prepare_runtime_config(env, kernel_threads=1)
    with pytest.raises(
        ValueError, match="existing runtime fixture has kernel_threads=1, expected 2"
    ):
        harness.prepare_runtime_config(env, kernel_threads=2)


def test_start_three_container_stack_forwards_kernel_threads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from tests.support import compose_gate_harness as harness

    recorded: list[tuple[str, int, int | None]] = []
    monkeypatch.setattr(harness, "acquire_compose_gate_lock", lambda: None)
    monkeypatch.setattr(
        harness,
        "prepare_runtime_config",
        lambda _env, *, workers=1, kernel_threads=None: recorded.append(
            ("prepare", workers, kernel_threads)
        ),
    )
    monkeypatch.setattr(harness, "_assert_port_8000_available_for_gate", lambda _project: None)
    monkeypatch.setattr(
        harness,
        "build_compose_stack_images",
        lambda _env, *, workers=1, kernel_threads=None: recorded.append(
            ("build", workers, kernel_threads)
        ),
    )
    monkeypatch.setattr(harness, "_teardown_compose_project_resources", lambda _env: None)
    monkeypatch.setattr(
        harness,
        "run_compose",
        lambda _env, *args: subprocess.CompletedProcess(args, 0, stdout="", stderr=""),
    )
    monkeypatch.setattr(harness, "wait_repository_service_ready", lambda _env: None)
    monkeypatch.setattr(harness, "seed_repository_and_mapping", lambda _env: ("repo-1", "commit-1"))
    monkeypatch.setattr(harness, "configured_worker_services", lambda _env: ("worker",))
    monkeypatch.setattr(harness, "wait_http_ok", lambda _url: None)
    monkeypatch.setattr(harness, "worker_ready", lambda _env: None)

    env = {"COMPOSE_PROJECT_NAME": "unit-stack-threads"}
    assert harness.start_three_container_stack(env, tmp_path, kernel_threads=2) == (
        "repo-1",
        "commit-1",
    )
    assert recorded == [("prepare", 1, 2), ("build", 1, 2)]
