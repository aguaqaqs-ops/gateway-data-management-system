"""One real two-group deployment owner, also used by the fresh real-input driver.

All generated files and barriers live outside the checkout. The executor barrier
is a test-only command wrapper: its supervisor continues ordinary lease renewal.
No production endpoint, environment switch or executor hook is introduced.
"""
from __future__ import annotations

from dataclasses import replace
import importlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any, cast
from uuid import uuid4

import httpx

from tests.support import compose_gate_harness as harness
from tests.support.container_input_files import write_container_readable_text

SCRIPTS = harness.VNEXT_ROOT / "scripts"
GIB = 1024**3
PERMISSIONS = ["workspace_read", "upload_submit_workspace", "preview_workspace",
               "review_submission", "archive_submission", "statistics_read_group"]
# Wrap only worker-1's executor callable. The ordinary worker supervisor keeps
# running; reaching this file means the old claimed operation occupies that
# executor, rather than merely waiting for its polling client.
EXECUTOR_BARRIER = '''
import time
from pathlib import Path
from gateway_backend.bootstrap import operation_worker
root = Path('/var/lib/gateway/be-scratch')
original = operation_worker._KernelWorkerRegistry.resolve
def resolve(self, key):
    executor = original(self, key)
    if executor is None:
        return None
    def execute(*args, **kwargs):
        arm = root / 'processing-group-barrier.arm'
        if arm.exists():
            arm.unlink()
            (root / 'processing-group-barrier.reached').write_text('executor occupied')
            deadline = time.monotonic() + 240
            while not (root / 'processing-group-barrier.release').exists():
                if time.monotonic() >= deadline:
                    raise RuntimeError('processing-group test barrier timed out')
                time.sleep(0.02)
        return executor(*args, **kwargs)
    return execute
operation_worker._KernelWorkerRegistry.resolve = resolve
raise SystemExit(operation_worker.main())
'''



def port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def run(*args: str, env: dict[str, str] | None = None, timeout: float = 120) -> str:
    result = subprocess.run(list(args), env=env, capture_output=True, text=True,
                            check=False, timeout=timeout)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def wait_for(check: Any, *, timeout: float = 60) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("processing group observation did not reach its barrier")


def session(device: str, project: str, token: str, *, actor: str = "submitter",
            permissions: list[str] | None = None) -> dict[str, Any]:
    return dict(token=token, actor_id=actor, gateway_device_external_key=device,
                business_project_id=project, permissions=permissions or PERMISSIONS)


class ProcessingGroupsStack:
    def __init__(self, root: Path, *, a_workers: int) -> None:
        assert a_workers in (1, 2)
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        root.chmod(0o755)
        self.public = root / "public"
        self.entry_directory = root / "entry"
        self.public.mkdir(mode=0o755)
        self.entry_directory.mkdir(mode=0o755)
        self.owner = "processing-groups-" + uuid4().hex
        self.entry_project = self.owner + "-entry"
        self.envs: dict[str, dict[str, str]] = {}
        self.runtime_roots: dict[str, Path] = {}
        self.configs: dict[str, dict[str, Any]] = {}
        self.a_workers = a_workers
        self.revision = run("git", "-C", str(harness.REPO_ROOT), "rev-parse", "HEAD").strip()
        assert not run("git", "-C", str(harness.REPO_ROOT), "status", "--porcelain").strip()
        self.groups_path = self.public / "groups.json"
        self.directory_path = self.public / "device-directory.json"
        manifest = json.loads((harness.VNEXT_ROOT / "fixtures/processing-groups/v1/groups.json").read_bytes())
        manifest["environment_id"] = "development"
        manifest["entry"].update(listen_address="127.0.0.1", listen_port=port(), management_port=port(),
                                 image=os.environ.get("GATEWAY_ENTRY_IMAGE", "nginx:1.28.0"))
        manifest["groups"] = []
        self.url = "http://127.0.0.1:" + str(manifest["entry"]["listen_port"])
        for group_id, workers in (("group-a", a_workers), ("group-b", 1)):
            directory = root / group_id
            run(sys.executable, str(SCRIPTS / "tests/runtime_config_fixture.py"), str(directory),
                "--owner", self.owner, "--workers", str(workers), "--group-id", group_id,
                "--processing-groups-small-input")
            self.runtime_roots[group_id] = directory
            self.configs[group_id] = json.loads((directory / "storage-layout.json").read_bytes())
            sessions = directory / "session"
            sessions.mkdir(mode=0o755)
            write_container_readable_text(sessions / "session.json", '{"sessions":[]}')
            internal, repository = directory / "internal.token", directory / "repository.token"
            write_container_readable_text(internal, group_id + "-internal")
            write_container_readable_text(repository, harness.BEARER_TOKEN if group_id == "group-a" else "group-b-repository")
            seed = directory / "seed.json"
            write_container_readable_text(seed, '{"mappings":[]}')
            project = self.owner + "-" + group_id
            images = dict(backend="gateway-processing-groups-backend:" + self.revision[:12],
                          worker="gateway-processing-groups-worker:" + self.revision[:12],
                          repository_service=harness.repository_service_image(), revision=self.revision)
            group = dict(group_id=group_id, project=project, backend_port=port(),
                         storage_config=str(directory / "storage-layout.json"),
                         resource_config=str(directory / "resource-profile.json"),
                         session_directory=str(sessions), internal_token_file=str(internal),
                         repository_token_file=str(repository), images=images)
            manifest["groups"].append(group)
            env = os.environ.copy()
            env.update(COMPOSE_PROJECT_NAME=project, GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE=str(seed),
                       GATEWAY_BACKEND_SESSION_DIRECTORY=str(sessions),
                       GATEWAY_PROCESSING_GROUPS_DIRECTORY=str(self.public),
                       GATEWAY_P2R2_BEARER_TOKEN_FILE=str(repository),
                       GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE=str(internal),
                       GATEWAY_BACKEND_CANDIDATE_SHA=self.revision,
                       GATEWAY_BACKEND_IMAGE=images["backend"], GATEWAY_WORKER_IMAGE=images["worker"],
                       GATEWAY_RUNTIME_COMPOSE_OVERRIDE=str(directory / "compose-runtime.json"))
            self.envs[group_id] = env
        write_container_readable_text(self.groups_path, json.dumps(manifest))
        write_container_readable_text(self.directory_path, json.dumps(dict(schema_version=1,
            environment_id="development", devices=[])))
        self.manifest = manifest
        sys.path.insert(0, str(SCRIPTS))
        self.entry_module = importlib.import_module("processing_group_entry")
        self.groups = importlib.import_module("processing_group_config").ProcessingGroupsConfig.load(self.groups_path)
        self.entry = self.entry_module.EntryRuntime(self.groups, self.entry_directory, self.entry_project)

    def compose(self, group: str, *args: str, timeout: float = 600) -> str:
        result = harness.run_compose(self.envs[group], *args, timeout=timeout)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    def start(self) -> None:
        harness.acquire_compose_gate_lock()
        assert not harness.compose_gate_prebuilt(), "two-group gate requires clean local image build"
        harness.ensure_repository_service_image()
        for group_id, env in self.envs.items():
            group = next(row for row in self.manifest["groups"] if row["group_id"] == group_id)
            override = Path(env["GATEWAY_RUNTIME_COMPOSE_OVERRIDE"])
            override.unlink()
            run(sys.executable, str(SCRIPTS / "render-runtime-config.py"), "render",
                "--storage-layout", group["storage_config"], "--resource-profile", group["resource_config"],
                "--groups-file", str(self.groups_path), "--directory-file", str(self.directory_path),
                "--group", group_id, "--build-from-source", "--output", str(override))
            rendered = json.loads(override.read_bytes())
            if group_id == "group-a":
                rendered["services"]["worker"]["command"] = ["python", "-c", EXECUTOR_BARRIER]
            override.write_text(json.dumps(rendered))
        self.compose("group-a", "build", "backend", "worker", timeout=1800)
        for group_id in self.envs:
            self.compose(group_id, "up", "-d", "--no-build", "--pull", "never",
                         "backend", "worker", *(["worker-2"] if group_id == "group-a" and self.a_workers == 2 else []))
            harness.wait_http_ok(self.group_url(group_id) + "/readyz")
            harness.worker_ready(self.envs[group_id])
        self.cli("render-entry")
        up = self.entry.compose("up", "-d", "--no-build", "--pull", "never", "entry")
        assert up.returncode == 0, up.stderr
        harness.wait_http_ok(self.url + "/healthz")
        self.inspect()

    def group_url(self, group: str) -> str:
        return str(next(item.backend_endpoint for item in self.groups.groups if item.group_id == group))

    def cli(self, command: str, *extra: str) -> dict[str, Any]:
        output = run(sys.executable, str(SCRIPTS / "manage-processing-groups.py"), command,
                     "--groups-file", str(self.groups_path), "--directory-file", str(self.directory_path),
                     "--entry-directory", str(self.entry_directory), "--entry-project", self.entry_project,
                     *extra, timeout=180)
        result: dict[str, Any] = json.loads(output)
        return result

    def add(self, group: str, device: str, *, project: str = "compose-project") -> dict[str, Any]:
        incoming = self.root / (uuid4().hex + ".sessions.json")
        write_container_readable_text(incoming, json.dumps({"sessions": [
            session(device, project, device + "-token"),
            session(device, project, device + "-reviewer", actor="reviewer")]}))
        result = self.cli("add-device", "--group", group, "--device", device, "--project", project,
                          "--session-document", str(incoming))
        assert result["state"] == "available", result
        assert self.cli("status-device", "--device", device)["state"] == "available"
        return self.registration(group, device)

    def registration(self, group: str, device: str) -> dict[str, Any]:
        response = httpx.get(self.group_url(group) + "/internal/v1/devices/registration", params={"device": device},
                             headers={"Authorization": "Bearer " + group + "-internal"})
        assert response.status_code == 200, response.text
        result: dict[str, Any] = response.json()
        return result

    def client(self, device: str, *, reviewer: bool = False) -> httpx.Client:
        return httpx.Client(base_url=self.url, headers=harness.compose_auth_headers(device_key=device,
            token=device + ("-reviewer" if reviewer else "-token")), timeout=60)

    def snapshot(self) -> dict[str, str]:
        snapshots = {}
        for group_id in self.envs:
            ids = self.compose(group_id, "ps", "-aq").split()
            snapshots[group_id] = run("docker", "inspect", "--format",
                "{{.Id}} {{.State.Pid}} {{.State.StartedAt}} {{.RestartCount}}", *ids)
        snapshots["entry"] = run("docker", "inspect", "--format",
            "{{.Id}} {{.State.Pid}} {{.State.StartedAt}} {{.RestartCount}}", self.entry.container_id())
        return snapshots

    def inspect(self) -> dict[str, Any]:
        result = self.cli("check-groups", "--inspect")
        print("processing_group_deployment=" + json.dumps(result, sort_keys=True), flush=True)
        return result

    def reject_foreign_root_and_image(self) -> None:
        """Real Docker bindings/selected images, without changing a live group."""
        deployment = importlib.import_module("processing_group_deployment")
        host = importlib.import_module("host_runtime_config")
        group = next(item for item in self.groups.groups if item.group_id == "group-a")
        config = host.DeploymentConfig.load(Path(group.storage_config), Path(group.resource_config))
        wrong_image = replace(group, images=replace(group.images, backend=group.images.repository_service))
        try:
            deployment.inspect_group(config, wrong_image)
        except ValueError as error:
            assert "actual group image/resources differ" in str(error), error
        else:
            raise AssertionError("actual container accepted a different selected image")
        # Same source image and A configuration, but one actual bind points at
        # B's existing root. Preflight must reject before any startup write probe.
        command = ["docker", "run", "--rm", "--pull", "never", "--network", "none", "--cgroupns", "host",
            "--name", self.owner + "-foreign-root", "--label", "com.docker.compose.project=" + group.project,
            "--label", "com.docker.compose.service=boundary-probe",
            "--memory", str(2 * GIB), "--memory-swap", str(2 * GIB), "--cpus", "1"]
        for slot, root in config.storage.role_roots("backend").items():
            source = self.configs["group-b"]["roots"][slot]["source"] if slot == "be-durable" else root.source
            command.extend(("--mount", "type=bind,source=" + source + ",target=" + root.path))
        for source, target in ((group.storage_config, "/run/gateway/storage-layout.json"),
                               (group.resource_config, "/run/gateway/resource-profile.json")):
            command.extend(("--mount", "type=bind,readonly,source=" + source + ",target=" + target))
        probe = """from pathlib import Path
from gateway_backend.deployment_config import DeploymentConfig
from gateway_backend.runtime_preflight import DeploymentIdentityChanged, RuntimePreflight
config=DeploymentConfig.load(Path('/run/gateway/storage-layout.json'),Path('/run/gateway/resource-profile.json'))
try:
    RuntimePreflight(config,'backend')
except DeploymentIdentityChanged as error:
    assert 'actual bind mount does not match configuration' in str(error), str(error)
    print('foreign_root_rejected_before_startup_writes=true')
else:
    raise AssertionError('foreign group root was accepted')
"""
        assert "foreign_root_rejected_before_startup_writes=true" in run(*command,
            "--entrypoint", "python", group.images.backend, "-c", probe, timeout=30)
        print("actual_foreign_root_and_selected_image_rejected=true", flush=True)
        self.inspect()

    def barrier_path(self, state: str) -> Path:
        return Path(self.configs["group-a"]["roots"]["be-scratch"]["source"]) / ("processing-group-barrier." + state)

    def arm(self) -> None:
        write_container_readable_text(self.barrier_path("arm"), "hold first executor")

    def release(self) -> None:
        write_container_readable_text(self.barrier_path("release"), "release first executor")

    def operation(self, group: str, operation_id: str) -> dict[str, Any]:
        probe = """import sqlite3,json,sys
c=sqlite3.connect('file:/var/lib/gateway/be-metadata/control.sqlite3?mode=ro',uri=True)
c.row_factory=sqlite3.Row
r=c.execute('SELECT o.status,s.status AS step_status,s.worker_id,s.attempt_count FROM operation_records o JOIN step_records s USING(operation_id) WHERE operation_id=?',(sys.argv[1],)).fetchone()
print(json.dumps(dict(r) if r else {}))
"""
        return cast(dict[str, Any], json.loads(self.compose(group, "exec", "-T", "backend", "python", "-c", probe, operation_id)))

    def journey(self, group: str, device: str, registration: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return harness.run_accept_to_submission_read_journey(self.envs[group],
            initial_commit_id=registration["initial_commit_id"], base_url=self.url, device_key=device,
            project_id=registration["business_project_id"], expected_baseline_node_id=registration["initial_node_id"],
            token=device + "-token", journey_key_prefix=device, **kwargs)

    def maintenance(self, group: str, command: str) -> str:
        row = next(item for item in self.manifest["groups"] if item["group_id"] == group)
        return run(sys.executable, str(SCRIPTS / "manage-worker-group.py"), command,
            "--project", row["project"], "--compose-file", str(harness.COMPOSE_FILE),
            "--compose-file", self.envs[group]["GATEWAY_RUNTIME_COMPOSE_OVERRIDE"],
            "--storage-layout", row["storage_config"], "--resource-profile", row["resource_config"],
            "--groups-file", str(self.groups_path), "--backend-url", self.group_url(group),
            "--internal-bearer-token-file", row["internal_token_file"], env=self.envs[group], timeout=300)

    def close(self) -> None:
        errors: list[Exception] = []
        retain = sys.exc_info()[0] is not None
        try:
            self.release()
        except Exception as error:
            errors.append(error)
        # Each project is attempted even if logs, TERM/down or an earlier
        # project's cleanup failed. The exact owner labels bound every action.
        for group_id in self.envs:
            try:
                logs = harness.run_compose(self.envs[group_id], "logs", "--no-color", timeout=30)
                print("processing_group_logs=" + group_id + "\n" + logs.stdout + logs.stderr, flush=True)
            except Exception as error:
                errors.append(error)
            try:
                down = harness.run_compose(self.envs[group_id], "down", "--remove-orphans", "--volumes", timeout=240)
                if down.returncode:
                    raise RuntimeError("owned group cleanup failed: " + group_id + " " + down.stderr)
            except Exception as error:
                errors.append(error)
        try:
            down = self.entry.compose("down", "--remove-orphans")
            if down.returncode:
                raise RuntimeError("owned entry cleanup failed: " + down.stderr)
        except Exception as error:
            errors.append(error)
        released = True
        for project in (self.entry_project, *(env["COMPOSE_PROJECT_NAME"] for env in self.envs.values())):
            try:
                if run("docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + project).strip():
                    released = False
                    errors.append(RuntimeError("owned containers remain: " + project))
            except Exception as error:
                released = False
                errors.append(error)
        if released:
            for directory in self.runtime_roots.values():
                try:
                    print(run(sys.executable, str(SCRIPTS / "tests/runtime_config_fixture.py"), str(directory),
                        "--owner", self.owner, "--cleanup", *(["--retain"] if retain or errors else [])), end="", flush=True)
                except Exception as error:
                    errors.append(error)
            harness.release_compose_gate_lock()
        else:
            print("processing_groups_cleanup_requires_node_protection=true", flush=True)
        if errors:
            raise ExceptionGroup("processing group cleanup failed; preserve node protection if resources remain", errors)

    def archive(self, device: str, submission_id: str, *, reason: str) -> dict[str, Any]:
        """Use the existing Review/Archive protocol, preserving explicit anomalies."""
        with self.client(device, reviewer=True) as client:
            response = client.post(f"/v1/submissions/{submission_id}/review-events",
                headers={"Idempotency-Key": device + "-approve"},
                json={"expected_review_version": 0, "action": "APPROVE"})
            assert response.status_code == 201, response.text
            candidates = client.get("/v1/archive-candidates")
            assert candidates.status_code == 200, candidates.text
            candidate = next(item for item in candidates.json()["candidates"] if item["submission_id"] == submission_id)
            selected = {key: candidate[key] for key in ("submission_id", "expected_candidate_digest")}
            preview = client.post("/v1/archive-plan-preview", json={"selected": selected})
            assert preview.status_code == 200, preview.text
            plan = preview.json()
            confirm = client.post("/v1/archive-confirmations", headers={"Idempotency-Key": device + "-confirm"},
                json=dict(expected_baseline_node_id=plan["head"]["business_baseline_node_id"],
                          expected_baseline_head_version=plan["head"]["baseline_head_version"], selected=selected,
                          candidate_set_digest=plan["candidate_set_digest"], subject_digest=plan["selection_subject_digest"],
                          expected_sequence=0, action="CONFIRM", reason=reason))
            assert confirm.status_code == 201, confirm.text
            refs = harness.resolve_archive_preview_anomalies(client, preview_body=plan, selected=selected,
                token=device + "-reviewer", device_key=device,
                idempotency_key_prefix=device + "-resolve", reason=reason)
            ready = client.post("/v1/archive-plan-preview", json={"selected": selected})
            assert ready.status_code == 200, ready.text
            assert ready.json()["can_start"] is True, ready.text
            response = client.post("/v1/archives", headers={"Idempotency-Key": device + "-archive"},
                json=dict(expected_baseline_node_id=plan["head"]["business_baseline_node_id"],
                          expected_baseline_head_version=plan["head"]["baseline_head_version"], selected=selected,
                          candidate_set_digest=plan["candidate_set_digest"],
                          confirmation_refs=[dict(subject_digest=plan["selection_subject_digest"], sequence=confirm.json()["sequence"])],
                          anomaly_resolution_refs=refs))
            assert response.status_code == 201, response.text
            result: dict[str, Any] = response.json()
            current = client.get("/v1/archive-candidates")
            assert current.status_code == 200, current.text
            assert current.json()["head"]["business_baseline_node_id"] == result["baseline_node_id"]
            assert current.json()["head"]["baseline_head_version"] == plan["head"]["baseline_head_version"] + 1
            result["observed_anomalies"] = [dict(subject_kind=item["subject_kind"], issue_code=item["issue_code"])
                                            for item in plan["anomalies"]]
            return result
