"""One multi-worker deployment journey; business matrices retain their own owners."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
from threading import Barrier
from typing import Any

import pytest

from tests.support import compose_gate_harness as harness
from tests.test_submit_compose_e2e import _compose_env

pytestmark = [pytest.mark.integration, pytest.mark.serial]


def test_fixed_two_workers_share_image_and_roots_with_actual_limits_and_clean_exit(tmp_path: Path) -> None:
    harness.require_docker()
    env = _compose_env(tmp_path)
    try:
        _repository_id, initial_commit = harness.start_three_container_stack(env, tmp_path, workers=2)
        rendered = harness.run_compose(env, "config", "--format", "json")
        assert rendered.returncode == 0, rendered.stdout + rendered.stderr
        services = json.loads(rendered.stdout)["services"]
        first, second = services["worker"], services["worker-2"]
        for service in (first, second):
            assert service["deploy"]["replicas"] == 1
            assert service["restart"] == "no"
        assert first["image"] == second["image"]
        assert first["volumes"] == second["volumes"]
        assert first["secrets"] == second["secrets"]
        assert {key: value for key, value in first["environment"].items() if not key.endswith("INSTANCE_INDEX")} == {
            key: value for key, value in second["environment"].items() if not key.endswith("INSTANCE_INDEX")}
        observed = harness.check_fixed_worker_deployment(env)
        assert {entry["instance_index"] for entry in observed.values()} == {1, 2}
        # The duplicate exits before starting a kernel or executor; running peers remain intact.
        baseline = harness.capture_worker_container_state(env)
        duplicate = harness.run_compose(env, "run", "--rm", "--no-deps", "--pull", "never", "worker", timeout=60)
        assert duplicate.returncode != 0
        assert "worker instance is already running" in duplicate.stdout + duplicate.stderr
        harness.assert_worker_container_unchanged(env, baseline)
        rendezvous = Barrier(2)
        def preview(index: int) -> dict[str, Any]:
            rendezvous.wait(timeout=30)
            return harness.run_accept_to_submission_read_journey(env, initial_commit_id=initial_commit,
                journey_key_prefix=f"fixed-workers-{index}", preview_only=True)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(preview, (1, 2)))
        assert results[0]["workspace_id"] != results[1]["workspace_id"]
        assert results[0]["preview_summaries"] == results[1]["preview_summaries"]
        harness.check_fixed_worker_deployment(env)
        # Runtime preflight checks the actual cgroup hierarchy inside each live container.
        probe = ("from pathlib import Path; from gateway_backend.deployment_config import DeploymentConfig; "
            "from gateway_backend.runtime_preflight import RuntimePreflight; "
            "guard=RuntimePreflight(DeploymentConfig.load(Path('/run/gateway/storage-layout.json'),"
            "Path('/run/gateway/resource-profile.json')),'worker'); "
            "import json; print(json.dumps(guard.observations(),sort_keys=True))")
        for service in observed:
            result = harness.run_compose(env, "exec", "-T", service, "python", "-c", probe)
            assert result.returncode == 0, result.stdout + result.stderr
            print(f"{service}_cgroup_preflight={result.stdout}", flush=True)
        harness.persist_compose_gate_provenance(env, harness.capture_running_container_provenance(env))
        ids = [str(entry["container_id"]) for entry in observed.values()]
        signalled = subprocess.run(["docker", "kill", "--signal", "TERM", *ids],
            check=False, capture_output=True, text=True, timeout=30)
        assert signalled.returncode == 0, signalled.stderr
        exited = subprocess.run(["docker", "wait", *ids], check=False,
            capture_output=True, text=True, timeout=210)
        assert exited.returncode == 0, exited.stderr
        assert exited.stdout.split() == ["0", "0"]
        state = subprocess.run(["docker", "inspect", *ids], check=False,
            capture_output=True, text=True, timeout=30)
        assert state.returncode == 0, state.stderr
        assert all(item["State"]["Pid"] == 0 and not item["State"]["Running"]
                   for item in json.loads(state.stdout))
    finally:
        harness.cleanup_compose_project_artifacts(env)
