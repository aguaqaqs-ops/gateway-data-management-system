"""One multi-worker deployment journey; business matrices retain their own owners."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from queue import Queue
import subprocess
from threading import Event
from typing import Any

import pytest

from tests.support import compose_gate_harness as harness
from tests.test_submit_compose_e2e import ACTOR2_TOKEN, _compose_env

pytestmark = [pytest.mark.integration, pytest.mark.serial]


def _stop_workers(ids: list[str]) -> None:
    signalled = subprocess.run(["docker", "kill", "--signal", "TERM", *ids],
        check=False, capture_output=True, text=True, timeout=30)
    assert signalled.returncode == 0, signalled.stderr
    exited = subprocess.run(["docker", "wait", *ids], check=False,
        capture_output=True, text=True, timeout=210)
    assert exited.returncode == 0, exited.stderr
    assert exited.stdout.split() == ["0"] * len(ids)
    state = subprocess.run(["docker", "inspect", *ids], check=False,
        capture_output=True, text=True, timeout=30)
    assert state.returncode == 0, state.stderr
    assert all(item["State"]["Pid"] == 0 and not item["State"]["Running"]
               for item in json.loads(state.stdout))


def test_fixed_two_workers_share_image_and_roots_with_actual_limits_and_clean_exit(tmp_path: Path) -> None:
    harness.require_docker()
    env = _compose_env(tmp_path)
    resume_polling = Event()
    accepted: Queue[str] = Queue()
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
        baseline = harness.capture_worker_container_state(env)
        duplicate = harness.run_compose(env, "run", "--rm", "--no-deps", "--pull", "never", "worker", timeout=60)
        assert duplicate.returncode != 0
        assert "operation_worker_failed category=worker_instance_conflict" in duplicate.stdout + duplicate.stderr
        assert "code=worker_ready" not in duplicate.stdout + duplicate.stderr
        harness.assert_worker_container_unchanged(env, baseline)
        ids = [str(entry["container_id"]) for entry in observed.values()]
        _stop_workers(ids)

        def on_accepted(operation_id: str) -> None:
            accepted.put(operation_id)
            assert resume_polling.wait(timeout=120), "worker overlap probe did not release polling"

        def preview(index: int) -> dict[str, Any]:
            return harness.run_accept_to_submission_read_journey(env, initial_commit_id=initial_commit,
                journey_key_prefix=f"fixed-workers-{index}", preview_only=True,
                token=harness.SESSION_TOKEN if index == 1 else ACTOR2_TOKEN,
                on_preview_accepted=on_accepted)

        # Fresh isolated roots: neither operation can hit a prewarmed baseline export cache.
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(preview, index) for index in (1, 2)]
            try:
                operation_ids = [accepted.get(timeout=60) for _ in range(2)]
                assert len(set(operation_ids)) == 2
                paused = harness.run_compose(env, "pause", "repository-service")
                assert paused.returncode == 0, paused.stderr
                # Restart the exact original containers without waiting on the paused RS healthcheck.
                started = subprocess.run(["docker", "start", *ids], check=False,
                    capture_output=True, text=True, timeout=30)
                assert started.returncode == 0, started.stderr
                probe = f'''
import json, sqlite3, time
from pathlib import Path
from gateway_backend.bootstrap.worker_instance import worker_id_for
from gateway_backend.deployment_config import DeploymentConfig
config = DeploymentConfig.load(Path('/run/gateway/storage-layout.json'), Path('/run/gateway/resource-profile.json'))
expected = {{worker_id_for(config, index) for index in (1, 2)}}
operation_ids = json.loads({json.dumps(json.dumps(operation_ids))})
connection = sqlite3.connect('/var/lib/gateway/be-metadata/control.sqlite3', timeout=1)
deadline = time.monotonic() + 20
while time.monotonic() < deadline:
    rows = connection.execute("SELECT operation_id, worker_id FROM step_records "
        "WHERE operation_id IN (?, ?) AND status = 'RUNNING'", operation_ids).fetchall()
    if len(rows) == 2 and {{row[0] for row in rows}} == set(operation_ids) and {{row[1] for row in rows}} == expected:
        print('concurrent_fixed_worker_claims=' + json.dumps(rows), flush=True)
        break
    time.sleep(0.05)
else:
    raise RuntimeError('both fixed workers did not execute the two accepted operations concurrently')
'''
                overlap = harness.run_compose(env, "exec", "-T", "backend", "python", "-c", probe, timeout=25)
                assert overlap.returncode == 0, overlap.stdout + overlap.stderr
                print(overlap.stdout, flush=True)
            finally:
                harness.run_compose(env, "unpause", "repository-service")
                resume_polling.set()
            results = [future.result(timeout=300) for future in futures]
        assert results[0]["workspace_id"] != results[1]["workspace_id"]
        assert results[0]["preview_summaries"] == results[1]["preview_summaries"]
        harness.worker_ready(env)
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
        _stop_workers(ids)
    finally:
        harness.run_compose(env, "unpause", "repository-service")
        resume_polling.set()
        harness.cleanup_compose_project_artifacts(env)
