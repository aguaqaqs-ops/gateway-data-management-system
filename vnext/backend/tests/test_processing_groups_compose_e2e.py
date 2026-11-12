"""Owning two-group hot-add, bridge, lifecycle and actual deployment journey."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from queue import Queue
from threading import Event

import httpx
import pytest

from tests.support import compose_gate_harness as harness
from tests.support.processing_groups_harness import ProcessingGroupsStack, session, wait_for

pytestmark = [pytest.mark.integration, pytest.mark.serial]


def _internal_statistics(stack: ProcessingGroupsStack) -> None:
    # First prove a genuinely empty session file has no injected identity.
    endpoint = stack.group_url("group-b") + "/internal/v1/statistics/group"
    assert httpx.get(endpoint).status_code == 401
    group = next(row for row in stack.manifest["groups"] if row["group_id"] == "group-b")
    path = Path(group["session_directory"]) / "session.json"
    stack.entry_module.atomic_write(path, json.dumps({"sessions": [
        session("unmapped-statistics-device", "unmapped-project", "unmapped-statistics", permissions=["statistics_read_group"]),
        session("unmapped-statistics-device", "unmapped-project", "unprivileged-statistics", permissions=["workspace_read"]),
    ]}).encode())
    for suffix in ("", "/resources"):
        for token, status in (("unmapped-statistics", 200), ("unprivileged-statistics", 403), ("absent", 401)):
            response = httpx.get(endpoint + suffix, headers={"Authorization": "Bearer " + token})
            assert response.status_code == status, response.text
        # An actual ordinary group peer cannot manufacture host-gateway trust.
        script = '''import urllib.request,urllib.error,sys
request=urllib.request.Request('http://backend:8000/internal/v1/statistics/group'+sys.argv[1],headers={
'Authorization':'Bearer unmapped-statistics','Host':'127.0.0.1','X-Forwarded-For':'127.0.0.1','Forwarded':'for=127.0.0.1'})
try:
    response=urllib.request.urlopen(request,timeout=10)
    print(response.status)
except urllib.error.HTTPError as error:
    print(error.code)
'''
        assert stack.compose("group-b", "exec", "-T", "worker", "python", "-c", script, suffix).strip() == "404"
        assert httpx.get(stack.url + "/internal/v1/statistics/group" + suffix,
                         headers={"Authorization": "Bearer unmapped-statistics"}).status_code == 404
    stack.inspect()


def _repository_boundaries(stack: ProcessingGroupsStack) -> None:
    # Exercise the exact startup consumer against the real authenticated RS.
    # No readiness response is substituted for its identity response.
    probe = """from pathlib import Path
from types import SimpleNamespace
from gateway_backend.bootstrap.repository_identity import assert_repository_identity
from gateway_backend.deployment_config import DeploymentConfig
config=DeploymentConfig.load(Path('/run/gateway/storage-layout.json'),Path('/run/gateway/resource-profile.json'))
token=Path('/run/secrets/repository-bearer-token').read_text().strip()
assert_repository_identity('http://repository-service:8000',token,config,timeout_seconds=2)
for endpoint,credential,expected in [
    ('http://backend:8000',token,config),
    ('http://repository-service:8000','wrong-repository-credential',config),
    ('http://repository-service:8000',token,SimpleNamespace(storage=SimpleNamespace(environment_id=config.storage.environment_id,group_id='group-b',digest=config.storage.digest))),
    ('http://repository-service:8000',token,SimpleNamespace(storage=SimpleNamespace(environment_id=config.storage.environment_id,group_id=config.storage.group_id,digest='sha256:'+'0'*64))),
]:
    try:
        assert_repository_identity(endpoint,credential,expected,timeout_seconds=2)
    except ValueError:
        continue
    raise AssertionError('foreign endpoint/credential/group/storage was accepted')
print('real_repository_boundaries=4 rejected')
"""
    assert "4 rejected" in stack.compose("group-a", "exec", "-T", "backend", "python", "-c", probe)


def _rejected_identity(stack: ProcessingGroupsStack) -> None:
    # Wrong receiving group, a valid bearer for the wrong key and foreign object
    # IDs all remain local authorization failures; no fallback lookup is added.
    with stack.client("synthetic-b1") as b:
        headers = dict(b.headers)
        wrong = httpx.get(stack.group_url("group-a") + "/v1/device-context", headers=headers)
        assert wrong.status_code == 401, wrong.text
        wrong = b.get("/v1/device-context", headers={"X-Gateway-Device-Key": "0" * 64})
        assert wrong.status_code == 404, wrong.text
    with stack.client("compose-device") as a:
        wrong = httpx.get(stack.group_url("group-a") + "/v1/device-context",
            headers={**dict(a.headers), "X-Gateway-Device-Key": harness.compose_auth_headers(device_key="synthetic-b1")["X-Gateway-Device-Key"]})
        assert wrong.status_code == 404, wrong.text
        wrong = a.post("/v1/workspaces", json=dict(gateway_device_external_key="synthetic-b1", business_project_id="compose-project"))
        assert wrong.status_code == 404, wrong.text
    for token, status in (("group-b-internal", 401), ("group-a-internal", 409)):
        response = httpx.post(stack.group_url("group-a") + "/internal/v1/devices/register",
            headers={"Authorization": "Bearer " + token}, json=dict(environment_id="development", group_id="group-b",
                gateway_device_external_key="synthetic-b1", business_project_id="compose-project"))
        assert response.status_code == status, response.text


@pytest.mark.parametrize("a_workers", [1, 2], ids=["w1-admission-before-release", "w2-completion-before-release"])
def test_two_groups_hot_add_keeps_old_executor_and_other_group_running(tmp_path: Path, a_workers: int) -> None:
    harness.require_docker()
    stack = ProcessingGroupsStack(tmp_path / "deployment", a_workers=a_workers)
    accepted: Queue[str] = Queue()
    try:
        stack.start()
        _internal_statistics(stack)
        _repository_boundaries(stack)
        a1 = stack.add("group-a", "compose-device")
        b1 = stack.add("group-b", "synthetic-b1")
        _rejected_identity(stack)
        # Ensure the armed first executor owns the old claim. Start the same W2
        # second container only after that observable barrier, before hot-add.
        if a_workers == 2:
            stack.compose("group-a", "stop", "worker-2")
        stack.arm()
        b_stop = Event()
        b_seen: Queue[None] = Queue()
        def continue_b() -> int:
            count = 0
            with stack.client("synthetic-b1") as client:
                while not b_stop.is_set():
                    response = client.get("/v1/device-context", timeout=5)
                    assert response.status_code == 200, response.text
                    count += 1
                    b_seen.put(None)
                    b_stop.wait(0.1)
            return count
        with ThreadPoolExecutor(max_workers=3) as executor:
            continuity = executor.submit(continue_b)
            old = executor.submit(stack.journey, "group-a", "compose-device", a1,
                                  preview_only=True, on_preview_accepted=accepted.put)
            try:
                old_id = accepted.get(timeout=60)
                wait_for(stack.barrier_path("reached").exists)
                old_fact = stack.operation("group-a", old_id)
                assert old_fact["status"] == old_fact["step_status"] == "RUNNING", old_fact
                assert old_fact["attempt_count"] == 1
                if a_workers == 2:
                    stack.compose("group-a", "start", "worker-2")
                    harness.worker_ready(stack.envs["group-a"])
                b_seen.get(timeout=10)
                before = stack.snapshot()
                with stack.client("synthetic-b1") as b:
                    assert b.get("/v1/device-context").status_code == 200
                inode = (stack.runtime_roots["group-a"] / "session/session.json").stat().st_ino
                b_before_add = b_seen.qsize()
                a2 = stack.add("group-a", "synthetic-a2")
                assert (stack.runtime_roots["group-a"] / "session/session.json").stat().st_ino != inode
                assert stack.snapshot() == before
                assert stack.operation("group-a", old_id) == old_fact
                new_accepted: Queue[str] = Queue()
                newer = executor.submit(stack.journey, "group-a", "synthetic-a2", a2,
                                        on_preview_accepted=new_accepted.put)
                new_id = new_accepted.get(timeout=60)  # Upload and preview were accepted via the public entry.
                if a_workers == 1:
                    assert stack.operation("group-a", new_id)["status"] == "QUEUED"
                    assert not newer.done()
                    assert stack.operation("group-a", old_id) == old_fact
                    stack.release()
                new_result = newer.result(timeout=180)
                archived = stack.archive("synthetic-a2", new_result["submission_id"], reason="Synthetic boundary fixture explicitly reviewed")
                if a_workers == 2:
                    assert stack.operation("group-a", old_id) == old_fact
                    assert not old.done()
                    assert not stack.barrier_path("release").exists()
                    print("strict_hot_add_overlap=" + json.dumps(dict(old_operation=old_id,
                        new_operation=new_id, new_archive=archived["baseline_node_id"], old_fact=old_fact)), flush=True)
                assert stack.snapshot() == before
                assert b_seen.qsize() > b_before_add
                with stack.client("synthetic-b1") as b:
                    assert b.get("/v1/device-context").status_code == 200
                    assert b.get("/v1/operations/" + new_id).status_code == 404
            finally:
                stack.release()
                b_stop.set()
            print("other_group_continuity_requests=" + str(continuity.result(timeout=10)), flush=True)
            assert old.result(timeout=180)["workspace_id"] != new_result["workspace_id"]
        # Exact replay after Head advancement retains INITIAL; no seed rewind.
        assert stack.add("group-a", "synthetic-a2") == a2
        before_maintenance = stack.snapshot()
        assert "group processes stopped" in stack.maintenance("group-a", "stop-group")
        assert stack.snapshot()["group-b"] == before_maintenance["group-b"]
        assert stack.entry.container_id() == before_maintenance["entry"]
        # A's stopped state must not block B's management or complete business.
        b2 = stack.add("group-b", "synthetic-b2")
        result = stack.journey("group-b", "synthetic-b2", b2)
        stack.archive("synthetic-b2", result["submission_id"], reason="Synthetic independent group fixture explicitly reviewed")
        assert b1["repository_id"] != a1["repository_id"] != a2["repository_id"]
        stack.compose("group-a", "up", "-d", "--no-build", "--pull", "never", "backend", "worker",
                      *(["worker-2"] if a_workers == 2 else []))
        harness.wait_http_ok(stack.group_url("group-a") + "/readyz")
        harness.worker_ready(stack.envs["group-a"])
        assert stack.registration("group-a", "synthetic-a2") == a2
        stack.inspect()
        for group in stack.envs:
            harness.persist_compose_gate_provenance(stack.envs[group], harness.capture_running_container_provenance(stack.envs[group]))
    finally:
        stack.close()
