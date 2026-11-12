"""One multi-worker deployment journey; business matrices retain their own owners."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
import json
from pathlib import Path
from queue import Queue
import subprocess
import sys
from threading import Event
from typing import Any, cast

import pytest

from tests.support import compose_gate_harness as harness
from tests.support.container_input_files import write_container_readable_text
from tests.support.processing_groups_harness import EXECUTOR_BARRIER, wait_for
from tests.test_submit_compose_e2e import ACTOR2_TOKEN, _compose_env

pytestmark = [pytest.mark.integration, pytest.mark.serial]


def _finalize_worker_probe(preserve_failure: Callable[[], None], barriers: list[Path],
        resume_polling: Event, cleanup: Callable[[], None] | None = None) -> None:
    """Attempt every release, retaining the test failure over observation errors."""
    primary = sys.exception()
    failures: list[tuple[str, BaseException]] = []
    def attempt(phase: str, action: Callable[[], object]) -> None:
        try:
            action()
        except BaseException as error:
            failures.append((phase, error))
    try:
        attempt("diagnostics", preserve_failure)
    finally:
        try:
            for barrier in barriers:
                attempt("executor release", lambda: write_container_readable_text(
                    barrier.with_suffix(".release"), "release executor"))
        finally:
            try:
                attempt("polling resume", resume_polling.set)
            finally:
                if cleanup is not None:
                    attempt("project cleanup", cleanup)
    if primary is not None:
        for phase, error in failures:
            primary.add_note(f"fixed-worker {phase} failed: {type(error).__name__}: {error}")
    elif failures:
        first = failures[0][1]
        for phase, error in failures[1:]:
            first.add_note(f"fixed-worker {phase} failed: {type(error).__name__}: {error}")
        raise first


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


def _manage_group(env: dict[str, str], command: str) -> str:
    rendered = json.loads(Path(env["GATEWAY_RUNTIME_COMPOSE_OVERRIDE"]).read_bytes())
    mounts = {item["target"]: item["source"] for item in rendered["services"]["worker"]["volumes"]}
    result = subprocess.run([sys.executable, str(harness.VNEXT_ROOT / "scripts/manage-worker-group.py"), command,
        "--project", env["COMPOSE_PROJECT_NAME"],
        "--groups-file", str(Path(env["GATEWAY_PROCESSING_GROUPS_DIRECTORY"]) / "groups.json"),
        "--compose-file", str(harness.COMPOSE_FILE),
        "--compose-file", env["GATEWAY_RUNTIME_COMPOSE_OVERRIDE"],
        "--storage-layout", mounts["/run/gateway/storage-layout.json"],
        "--resource-profile", mounts["/run/gateway/resource-profile.json"],
        "--internal-bearer-token-file", env["GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE"]],
        env=env, check=False, capture_output=True, text=True, timeout=900)
    assert result.returncode == 0, result.stdout + result.stderr
    print("fixed_group_maintenance=" + result.stdout.strip(), flush=True)
    return result.stdout


def _queued_preview_snapshot(env: dict[str, str], operation_ids: list[str]) -> dict[str, Any]:
    # Read one consistent view of the accepted facts, not telemetry or queue counts.
    probe = f'''
import json, sqlite3
operation_ids = json.loads({json.dumps(json.dumps(operation_ids))})
connection = sqlite3.connect('file:/var/lib/gateway/be-metadata/control.sqlite3?mode=ro', uri=True, timeout=1)
connection.row_factory = sqlite3.Row
connection.execute('BEGIN')
snapshot = {{}}
for operation_id in operation_ids:
    operation = dict(connection.execute("SELECT operation_id, status, job_contract_version, "
        "job_payload, optimistic_version, created_at_us, updated_at_us FROM operation_records "
        "WHERE operation_id = ?", (operation_id,)).fetchone())
    operation['job_payload'] = json.loads(operation['job_payload'])
    assert operation['status'] == 'QUEUED'
    step = dict(connection.execute("SELECT status, contract_version, optimistic_version, attempt_count, "
        "eligible_at_us, retry_not_before_us, created_at_us, updated_at_us FROM step_records "
        "WHERE operation_id = ?", (operation_id,)).fetchone())
    assert step['status'] == 'PENDING' and step['attempt_count'] == 0
    workspace = dict(connection.execute("SELECT workspace_id, generation, optimistic_version, "
        "current_upload_revision_id, state, created_at_us, updated_at_us FROM workspace_records "
        "WHERE workspace_id = ?", (operation['job_payload']['workspace_id'],)).fetchone())
    protections = [dict(row) for row in connection.execute("SELECT artifact_id, intent, recorded_at_us, "
        "expires_at_us FROM artifact_protection_intents WHERE owner_kind = 'preview-operation' "
        "AND owner_id = ? ORDER BY artifact_id", (operation_id,))]
    assert protections and all(row['intent'] == 'active-operation' for row in protections)
    snapshot[operation_id] = {{'operation': operation, 'step': step,
        'workspace': workspace, 'protections': protections}}
connection.close()
print(json.dumps(snapshot, sort_keys=True))
'''
    result = harness.run_compose(env, "exec", "-T", "backend", "python", "-c", probe)
    assert result.returncode == 0, result.stdout + result.stderr
    return cast(dict[str, Any], json.loads(result.stdout))


def test_fixed_two_workers_share_image_and_roots_with_actual_limits_and_clean_exit(tmp_path: Path) -> None:
    harness.require_docker()
    env = _compose_env(tmp_path)
    revision = subprocess.run(["git", "-C", str(harness.REPO_ROOT), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, timeout=10).stdout.strip()
    assert not subprocess.run(["git", "-C", str(harness.REPO_ROOT), "status", "--porcelain"],
        check=True, capture_output=True, text=True, timeout=10).stdout.strip()
    env.update(GATEWAY_BACKEND_CANDIDATE_SHA=revision,
        GATEWAY_BACKEND_IMAGE=env["COMPOSE_PROJECT_NAME"] + "-backend:fixed",
        GATEWAY_WORKER_IMAGE=env["COMPOSE_PROJECT_NAME"] + "-worker:fixed")
    harness.ensure_repository_service_image(candidate_revision=revision)
    harness.prepare_runtime_config(env, workers=2)
    rendered_path = Path(env["GATEWAY_RUNTIME_COMPOSE_OVERRIDE"])
    rendered_config = json.loads(rendered_path.read_bytes())
    roots = {item["target"]: item["source"] for item in rendered_config["services"]["worker"]["volumes"]}
    scratch = Path(roots["/var/lib/gateway/be-scratch"])
    barriers = [scratch / f"fixed-worker-{index}-barrier" for index in (1, 2)]
    for index, service in enumerate(("worker", "worker-2"), 1):
        rendered_config["services"][service]["command"] = ["python", "-c",
            EXECUTOR_BARRIER.replace("processing-group-barrier", f"fixed-worker-{index}-barrier")]
    rendered_path.write_text(json.dumps(rendered_config))
    resume_polling = Event()
    accepted: Queue[str] = Queue()
    diagnostics_attempted = False
    def preserve_failure() -> None:
        nonlocal diagnostics_attempted
        if sys.exc_info()[0] is not None and not diagnostics_attempted:
            diagnostics_attempted = True
            harness.capture_container_diagnostics(env, tmp_path / "worker-diagnostics")
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
                queued = _queued_preview_snapshot(env, operation_ids)
                assert "not quiescent" in _manage_group(env, "drain")
                assert _queued_preview_snapshot(env, operation_ids) == queued
                # These schemas have no operation/Workspace absolute deadline.
                # Preserve their real time anchors and protection expiry instead.
                print("queued_previews_preserved_across_drain=" + json.dumps(operation_ids), flush=True)
                # Keep the authenticated startup dependency available. Each test-only
                # executor barrier blocks after claim while the supervisor renews leases.
                for barrier in barriers:
                    write_container_readable_text(barrier.with_suffix(".arm"), "hold executor")
                started = subprocess.run(["docker", "start", *ids], check=False,
                    capture_output=True, text=True, timeout=30)
                assert started.returncode == 0, started.stderr
                for barrier in barriers:
                    wait_for(barrier.with_suffix(".reached").exists, timeout=30)
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
                _finalize_worker_probe(preserve_failure, barriers, resume_polling)
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
        assert "not quiescent" in _manage_group(env, "drain")
        # Recovery explicitly starts the same fixed containers under closed admission.
        assert "not quiescent" in _manage_group(env, "start-recovery")
        harness.worker_ready(env)
        restarted = harness.capture_worker_container_state(env)
        assert {state.split()[0] for state in restarted.values()} == set(ids)
        assert "group processes stopped" in _manage_group(env, "stop-group")
    finally:
        _finalize_worker_probe(preserve_failure, barriers, resume_polling,
            lambda: harness.cleanup_compose_project_artifacts(env))
