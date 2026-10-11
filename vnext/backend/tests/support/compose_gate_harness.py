"""Shared helpers for backend compose integration gates."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from collections.abc import Callable
from typing import Any, TextIO, cast

import httpx
import pytest

from tests.support.history_zero_write_tables import HISTORY_ZERO_WRITE_TABLES
from tests.support.source_package_fixtures import pack_tar_gz
from tests.support.submit_job_harness import _repository_service_build_package_bytes
from tests.support.upload_http_packages import _SQL, upload_files

VNEXT_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_ROOT = VNEXT_ROOT / "deploy"
COMPOSE_FILE = DEPLOY_ROOT / "compose.yaml"
BUILD_REPOSITORY_SCRIPT = VNEXT_ROOT / "scripts" / "build-repository-service-image.sh"
BACKEND_URL = "http://127.0.0.1:8000"
GATE_PROJECT_ENV = "GATEWAY_COMPOSE_GATE_PROJECT_NAME"
GATE_SESSION_ENV = "GATEWAY_COMPOSE_GATE_SESSION"
PREBUILT_ENV = "GATEWAY_COMPOSE_GATE_PREBUILT"
COMPOSE_GATE_LOCK_PATH = Path("/tmp/gateway-compose-gate.lock")
COMPOSE_GATE_LOCK_TIMEOUT_SECONDS = 1800.0
COMPOSE_GATE_LOCK_POLL_SECONDS = 2.0
_gate_lock_file: TextIO | None = None
COMPOSE_GATE_PROVENANCE_PATH = (
    Path(__file__).resolve().parent / ".last_compose_gate_provenance.json"
)
REPO_ROOT = Path(__file__).resolve().parents[4]
SOURCE_TREE_SHA_DIRTY_COMMAND = (
    'GIT_INDEX_FILE=$(mktemp) && git -C "$REPO_ROOT" read-tree HEAD && '
    'git -C "$REPO_ROOT" add -A && git -C "$REPO_ROOT" write-tree'
)
SOURCE_TREE_SHA_EXCLUDES = (
    "full repo tree via temporary index (includes unstaged and untracked); "
    "not a HEAD^{tree} snapshot"
)
_LOGGER = logging.getLogger(__name__)
ORDERED_SYX_TABLE = "b1_n1_iec104_syx_list"
ORDERED_SYX_VOCABULARY_DDL = (
    "CREATE TABLE `b1_n1_iec104_syx_list` ("
    "`gid` INT NOT NULL, "
    "`no` INT NOT NULL, "
    "PRIMARY KEY (`gid`)"
    ");\n"
)
ORDERED_SYX_SIZED_DDL = (
    "CREATE TABLE `b1_n1_iec104_syx_list` ("
    "`gid` BIGINT NOT NULL, "
    "`no` INT NOT NULL, "
    "`value` VARCHAR(8) NULL, "
    "PRIMARY KEY (`gid`)"
    ");\n"
)


def require_docker(*, compose_project_name: str | None = None) -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker is required for compose e2e gate")
    if compose_project_name is not None:
        # Port 8000 is checked after compose gate flock in start_three_container_stack.
        return
    _assert_port_8000_available_for_gate(None)


def _assert_port_8000_available_for_gate(compose_project_name: str | None) -> None:
    port_users = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            "publish=8000",
            "--format",
            "{{.ID}}\t{{.Names}}\t{{.Label \"com.docker.compose.project\"}}",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    if port_users.returncode != 0:
        pytest.fail(f"failed to inspect port 8000 usage: {port_users.stderr}\n{port_users.stdout}")
    conflicts: list[str] = []
    for line in port_users.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        container_id = parts[0]
        name = parts[1] if len(parts) > 1 else container_id
        project = parts[2] if len(parts) > 2 else ""
        if compose_project_name and project == compose_project_name:
            _LOGGER.info(
                "compose gate reusing project container on port 8000: %s (%s)",
                name,
                container_id,
            )
            continue
        conflicts.append(f"{name} ({container_id}, project={project or 'unknown'})")
    if conflicts:
        pytest.fail(
            "port 8000 is already published by non-gate containers: "
            + "; ".join(conflicts)
        )


def compose_project_name(tmp_path: Path, *, default_prefix: str) -> str:
    fixed = os.environ.get(GATE_PROJECT_ENV, "").strip()
    if fixed:
        return fixed
    session = os.environ.get(GATE_SESSION_ENV, "").strip() or str(os.getpid())
    return f"{default_prefix}-{session}-{tmp_path.name}"


def acquire_compose_gate_lock() -> None:
    global _gate_lock_file
    if _gate_lock_file is not None:
        return
    COMPOSE_GATE_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_file = COMPOSE_GATE_LOCK_PATH.open("a+", encoding="utf-8")
    deadline = time.monotonic() + COMPOSE_GATE_LOCK_TIMEOUT_SECONDS
    while True:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            _gate_lock_file = lock_file
            return
        except BlockingIOError:
            if time.monotonic() >= deadline:
                lock_file.close()
                pytest.fail(
                    "timed out waiting for compose gate lock "
                    f"at {COMPOSE_GATE_LOCK_PATH} after "
                    f"{COMPOSE_GATE_LOCK_TIMEOUT_SECONDS:.0f}s; "
                    "another session may be running compose gates on port 8000"
                )
            time.sleep(COMPOSE_GATE_LOCK_POLL_SECONDS)


def release_compose_gate_lock() -> None:
    global _gate_lock_file
    if _gate_lock_file is None:
        return
    try:
        fcntl.flock(_gate_lock_file.fileno(), fcntl.LOCK_UN)
    finally:
        _gate_lock_file.close()
        _gate_lock_file = None


def repository_service_image() -> str:
    return os.environ.get("GATEWAY_REPOSITORY_SERVICE_IMAGE", "gateway-repository-service:local")


def compose_gate_prebuilt() -> bool:
    return os.environ.get(PREBUILT_ENV, "").strip() in {"1", "true", "yes"}


def run_compose(env: dict[str, str], *args: str, timeout: float = 600.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), *args],
        cwd=DEPLOY_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


REPOSITORY_SERVICE_EXEC_USER = "gateway"


def run_repository_service_exec(
    env: dict[str, str],
    *args: str,
    timeout: float = 600.0,
) -> subprocess.CompletedProcess[str]:
    return run_compose(
        env,
        "exec",
        "-T",
        "-u",
        REPOSITORY_SERVICE_EXEC_USER,
        "repository-service",
        *args,
        timeout=timeout,
    )


def ensure_repository_service_image() -> None:
    image = repository_service_image()
    inspect = subprocess.run(
        ["docker", "image", "inspect", image],
        check=False,
        capture_output=True,
        text=True,
        timeout=60.0,
    )
    if inspect.returncode == 0:
        return
    if not BUILD_REPOSITORY_SCRIPT.is_file():
        pytest.fail(f"missing repository-service build script: {BUILD_REPOSITORY_SCRIPT}")
    completed = subprocess.run(
        [str(BUILD_REPOSITORY_SCRIPT)],
        cwd=VNEXT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=1800.0,
    )
    if completed.returncode != 0:
        pytest.fail(
            "repository-service image build failed; "
            f"stdout={completed.stdout[-500:]} stderr={completed.stderr[-500:]}"
        )


def build_compose_stack_images(env: dict[str, str]) -> None:
    ensure_repository_service_image()
    if compose_gate_prebuilt():
        return
    build = run_compose(env, "build", "backend", "worker")
    if build.returncode != 0:
        pytest.fail(f"compose backend/worker build failed: {build.stderr}\n{build.stdout}")


def build_backend_image(env: dict[str, str]) -> None:
    ensure_repository_service_image()
    if compose_gate_prebuilt():
        return
    build = run_compose(env, "build", "backend")
    if build.returncode != 0:
        pytest.fail(f"backend image build failed: {build.stderr}\n{build.stdout}")


def _inspect_image(image_ref: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["docker", "image", "inspect", image_ref],
        check=False,
        capture_output=True,
        text=True,
        timeout=60.0,
    )
    if completed.returncode != 0:
        return {"image_ref": image_ref, "missing": True}
    payload = json.loads(completed.stdout)
    image = payload[0]
    return {
        "image_ref": image_ref,
        "id": image.get("Id"),
        "labels": image.get("Config", {}).get("Labels", {}),
    }


def compose_image_ids(env: dict[str, str]) -> dict[str, dict[str, Any]]:
    project = env["COMPOSE_PROJECT_NAME"]
    repo_image = repository_service_image()
    return {
        "repository_service": _inspect_image(repo_image),
        "backend": _inspect_image(f"{project}-backend"),
        "worker": _inspect_image(f"{project}-worker"),
    }


def wait_http_ok(url: str, *, timeout_seconds: float = 180.0) -> None:
    import time
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5.0) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, ConnectionResetError):
            time.sleep(2.0)
    raise RuntimeError(f"endpoint did not become ready: {url}")


def resolve_main_commit_id(
    env: dict[str, str],
    repository_id: str,
    *,
    bearer_token: str,
) -> str:
    script = f"""
import json, time, urllib.error, urllib.request
req = urllib.request.Request(
    "http://127.0.0.1:8000/v1/repositories/{repository_id}/versioned/refs/main",
    headers={{"Authorization": "Bearer {bearer_token}"}},
)
for attempt in range(15):
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            print(json.loads(response.read().decode())["commit_id"])
            break
    except urllib.error.HTTPError as exc:
        if exc.code == 503 and attempt < 14:
            time.sleep(2.0)
            continue
        raise
else:
    raise RuntimeError("repository main resolve timed out")
"""
    result = run_compose(env, "exec", "-T", "repository-service", "python", "-c", script)
    if result.returncode != 0:
        pytest.fail(f"failed to resolve repository main ref: {result.stderr}\n{result.stdout}")
    commit_id = result.stdout.strip()
    if not commit_id:
        pytest.fail("repository main resolve returned empty commit_id")
    return commit_id


def list_repository_commit_ids(
    env: dict[str, str],
    repository_id: str,
    *,
    bearer_token: str,
) -> set[str]:
    script = f"""
import json, os, re, subprocess, uuid
repo_hex = uuid.UUID("{repository_id}").hex
repo_path = f"/var/lib/gateway/repository/versioned/{{repo_hex}}"
pager_env = {{
    **os.environ,
    "PAGER": "",
    "GIT_PAGER": "",
    "NO_COLOR": "1",
    "DOLT_CLI_NO_COLOR": "1",
}}
log = subprocess.run(
    ["dolt", "log", "-n", "200", "--oneline", "--decorate=no"],
    cwd=repo_path,
    check=False,
    capture_output=True,
    text=True,
    env=pager_env,
)
if log.returncode != 0:
    raise RuntimeError(log.stderr or log.stdout)
ansi = re.compile(r"\\x1b\\[[0-9;]*m")
commits = [
    ansi.sub("", line.split()[0])
    for line in log.stdout.splitlines()
    if line.strip()
]
print(json.dumps(sorted(commits)))
"""
    result = run_repository_service_exec(env, "python", "-c", script)
    if result.returncode != 0:
        pytest.fail(f"failed to list repository commits: {result.stderr}\n{result.stdout}")
    payload = json.loads(result.stdout.strip() or "[]")
    return set(str(item) for item in payload)


def _worker_container_name(env: dict[str, str]) -> str:
    return f"{env['COMPOSE_PROJECT_NAME']}-worker-1"


def capture_worker_container_state(env: dict[str, str]) -> dict[str, str]:
    container = _worker_container_name(env)
    restart = subprocess.run(
        ["docker", "inspect", "--format", "{{.RestartCount}}", container],
        check=False,
        capture_output=True,
        text=True,
        timeout=60.0,
    )
    if restart.returncode != 0:
        pytest.fail(
            f"docker inspect RestartCount failed for {container}: "
            f"{restart.stderr}\n{restart.stdout}"
        )
    started = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.StartedAt}}", container],
        check=False,
        capture_output=True,
        text=True,
        timeout=60.0,
    )
    if started.returncode != 0:
        pytest.fail(
            f"docker inspect StartedAt failed for {container}: "
            f"{started.stderr}\n{started.stdout}"
        )
    return {
        "restart_count": restart.stdout.strip(),
        "started_at": started.stdout.strip(),
    }


def assert_worker_container_unchanged(
    env: dict[str, str],
    baseline: dict[str, str],
) -> None:
    current = capture_worker_container_state(env)
    if current["restart_count"] != baseline["restart_count"]:
        pytest.fail(
            "worker container restart count changed after submit failure: "
            f"baseline={baseline['restart_count']} current={current['restart_count']} "
            f"(container={_worker_container_name(env)})"
        )
    if current["started_at"] != baseline["started_at"]:
        pytest.fail(
            "worker container StartedAt changed after submit failure: "
            f"baseline={baseline['started_at']} current={current['started_at']} "
            f"(container={_worker_container_name(env)})"
        )


def assert_submit_occupancy_cleared_in_compose(
    env: dict[str, str],
    *,
    workspace_id: str,
    submit_attempt_id: str,
) -> None:
    workspace_literal = json.dumps(workspace_id)
    attempt_literal = json.dumps(submit_attempt_id)
    script = f"""
import sqlite3
conn = sqlite3.connect('/var/lib/gateway/control/control.sqlite3')
workspace_id = {workspace_literal}
submit_attempt_id = {attempt_literal}
workspace_count = conn.execute(
    "SELECT COUNT(*) FROM workspace_submit_occupancy_records WHERE workspace_id = ?",
    (workspace_id,),
).fetchone()[0]
repository_count = conn.execute(
    "SELECT COUNT(*) FROM repository_submit_occupancy_records "
    "WHERE workspace_id = ? AND submit_attempt_id = ?",
    (workspace_id, submit_attempt_id),
).fetchone()[0]
print(f"{{workspace_count}},{{repository_count}}")
"""
    result = run_compose(env, "exec", "-T", "backend", "python", "-c", script)
    if result.returncode != 0:
        pytest.fail(
            "failed to read submit occupancy from control DB: "
            f"{result.stderr}\n{result.stdout}"
        )
    parts = result.stdout.strip().split(",")
    if len(parts) != 2:
        pytest.fail(f"unexpected occupancy probe output: {result.stdout!r}")
    workspace_count, repository_count = int(parts[0]), int(parts[1])
    if workspace_count != 0:
        pytest.fail(
            "workspace submit occupancy was not cleared after prepare failure: "
            f"workspace_id={workspace_id} count={workspace_count}"
        )
    if repository_count != 0:
        pytest.fail(
            "repository submit occupancy was not cleared after prepare failure: "
            f"workspace_id={workspace_id} submit_attempt_id={submit_attempt_id} "
            f"count={repository_count}"
        )


def count_backend_operations(env: dict[str, str]) -> int:
    script = (
        "import sqlite3; "
        "conn = sqlite3.connect('/var/lib/gateway/control/control.sqlite3'); "
        "print(conn.execute('SELECT COUNT(*) FROM operation_records').fetchone()[0])"
    )
    result = run_compose(env, "exec", "-T", "backend", "python", "-c", script)
    if result.returncode != 0:
        pytest.fail(f"failed to count operations: {result.stderr}\n{result.stdout}")
    return int(result.stdout.strip())


def _inspect_container_image_id(container_id: str) -> str:
    completed = subprocess.run(
        ["docker", "inspect", "--format", "{{.Image}}", container_id],
        check=False,
        capture_output=True,
        text=True,
        timeout=60.0,
    )
    if completed.returncode != 0:
        pytest.fail(
            f"docker inspect failed for {container_id}: "
            f"{completed.stderr}\n{completed.stdout}"
        )
    image_id = completed.stdout.strip()
    if not image_id.startswith("sha256:"):
        pytest.fail(f"expected immutable image id for {container_id}, got {image_id!r}")
    return image_id


def normalize_running_images(
    captured: dict[str, dict[str, str]],
    compose_project_name: str,
) -> dict[str, dict[str, str]]:
    """Map compose ps container names to canonical service keys."""

    service_suffixes = {
        "backend": f"{compose_project_name}-backend-1",
        "worker": f"{compose_project_name}-worker-1",
        "repository_service": f"{compose_project_name}-repository-service-1",
    }
    normalized: dict[str, dict[str, str]] = {}
    for service, container_name in service_suffixes.items():
        entry = captured.get(container_name)
        if entry is None:
            pytest.fail(f"missing running container for {service}: {container_name}")
        normalized[service] = {
            "container_id": entry["container_id"],
            "image": entry["image"],
        }
    return normalized


def capture_running_container_provenance(env: dict[str, str]) -> dict[str, dict[str, str]]:
    result = run_compose(
        env,
        "ps",
        "--format",
        "{{.Name}}\t{{.ID}}",
    )
    if result.returncode != 0:
        pytest.fail(f"compose ps failed: {result.stderr}\n{result.stdout}")
    captured: dict[str, dict[str, str]] = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        name, container_id = line.split("\t", 1)
        captured[name] = {
            "container_id": container_id,
            "image": _inspect_container_image_id(container_id),
        }
    return captured


def persist_compose_gate_provenance(
    env: dict[str, str],
    provenance: dict[str, dict[str, str]],
) -> Path:
    payload = {
        "compose_project_name": env["COMPOSE_PROJECT_NAME"],
        "containers": provenance,
    }
    COMPOSE_GATE_PROVENANCE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return COMPOSE_GATE_PROVENANCE_PATH


def assert_running_backend_worker_images_match_build(env: dict[str, str]) -> None:
    built = compose_image_ids(env)
    running = capture_running_container_provenance(env)
    project = env["COMPOSE_PROJECT_NAME"]
    for service in ("backend", "worker"):
        running_key = f"{project}-{service}-1"
        running_image = running.get(running_key, {}).get("image")
        built_image = built[service].get("id")
        if running_image is None or built_image is None:
            pytest.fail(f"missing running or built image for {service}")
        if running_image != built_image:
            pytest.fail(
                f"running image for {service} does not match fresh build: "
                f"{running_image} != {built_image}"
            )


SESSION_TOKEN = "compose-session-token"
BEARER_TOKEN = "compose-submit-bearer"
BASELINE_NODE_ID = "compose-node"
BASELINE_MANIFEST_DIGEST = "sha256:" + "a" * 64
BASELINE_REPLAY_SQL = b"CREATE TABLE t (id INT NOT NULL PRIMARY KEY);\n"
DEVICE_KEY = "compose-device"
PROJECT_ID = "compose-project"


def compose_auth_headers(
    *,
    token: str = SESSION_TOKEN,
    idempotency_key: str | None = None,
) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def wait_repository_service_ready(env: dict[str, str], *, timeout_seconds: float = 180.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    probe = (
        "import urllib.request; "
        "urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=5.0)"
    )
    while time.monotonic() < deadline:
        result = run_compose(
            env,
            "exec",
            "-T",
            "repository-service",
            "python",
            "-c",
            probe,
        )
        if result.returncode == 0:
            return
        time.sleep(2.0)
    raise RuntimeError("repository-service did not become ready")


def worker_ready(env: dict[str, str], *, timeout_seconds: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        logs = run_compose(env, "logs", "worker", "--no-color")
        if "code=worker_ready" in logs.stdout:
            return
        time.sleep(2.0)
    raise RuntimeError("worker did not emit worker_ready")


def _git_head_tree_sha(repo_root: Path = REPO_ROOT) -> str:
    tree = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD^{tree}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    if tree.returncode != 0:
        pytest.fail(f"git rev-parse HEAD^{{tree}} failed: {tree.stderr}")
    return tree.stdout.strip()


def _git_dirty_worktree_tree_sha(repo_root: Path = REPO_ROOT) -> str:
    index_fd, index_path = tempfile.mkstemp(prefix="gateway-provenance-index-")
    os.close(index_fd)
    git_env = {**os.environ, "GIT_INDEX_FILE": index_path}
    try:
        read_tree = subprocess.run(
            ["git", "-C", str(repo_root), "read-tree", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30.0,
            env=git_env,
        )
        if read_tree.returncode != 0:
            pytest.fail(f"git read-tree HEAD failed: {read_tree.stderr}")
        add_all = subprocess.run(
            ["git", "-C", str(repo_root), "add", "-A"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30.0,
            env=git_env,
        )
        if add_all.returncode != 0:
            pytest.fail(f"git add -A failed: {add_all.stderr}")
        write_tree = subprocess.run(
            ["git", "-C", str(repo_root), "write-tree"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30.0,
            env=git_env,
        )
        if write_tree.returncode != 0:
            pytest.fail(f"git write-tree failed: {write_tree.stderr}")
        tree_sha = write_tree.stdout.strip()
        head_tree = _git_head_tree_sha(repo_root)
        if tree_sha == head_tree:
            pytest.fail(
                "dirty worktree tree digest matches HEAD^{tree}; "
                "temporary index did not capture worktree changes"
            )
        return tree_sha
    finally:
        try:
            os.remove(index_path)
        except OSError:
            pass


def source_tree_sha_for_provenance(repo_root: Path = REPO_ROOT) -> tuple[str, bool, str]:
    status = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    if status.returncode != 0:
        pytest.fail(f"git status failed: {status.stderr}")
    worktree_clean = not status.stdout.strip()
    if worktree_clean:
        command = f"git -C {repo_root} rev-parse 'HEAD^{{tree}}'"
        return _git_head_tree_sha(repo_root), True, command
    return _git_dirty_worktree_tree_sha(repo_root), False, SOURCE_TREE_SHA_DIRTY_COMMAND


def _teardown_compose_project_resources(env: dict[str, str]) -> None:
    project = env["COMPOSE_PROJECT_NAME"]
    down = run_compose(env, "down", "-v", "--remove-orphans")
    if down.returncode != 0:
        _LOGGER.warning(
            "compose down returned %s: %s",
            down.returncode,
            down.stderr or down.stdout,
        )
    volumes = subprocess.run(
        [
            "docker",
            "volume",
            "ls",
            "-q",
            "--filter",
            f"label=com.docker.compose.project={project}",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60.0,
    )
    if volumes.returncode != 0:
        pytest.fail(f"docker volume ls failed: {volumes.stderr}\n{volumes.stdout}")
    volume_ids = [item for item in volumes.stdout.splitlines() if item.strip()]
    if volume_ids:
        removed = subprocess.run(
            ["docker", "volume", "rm", *volume_ids],
            check=False,
            capture_output=True,
            text=True,
            timeout=60.0,
        )
        if removed.returncode != 0:
            pytest.fail(f"docker volume rm failed: {removed.stderr}\n{removed.stdout}")
    networks = subprocess.run(
        [
            "docker",
            "network",
            "ls",
            "-q",
            "--filter",
            f"label=com.docker.compose.project={project}",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60.0,
    )
    if networks.returncode != 0:
        pytest.fail(f"docker network ls failed: {networks.stderr}\n{networks.stdout}")
    network_ids = [item for item in networks.stdout.splitlines() if item.strip()]
    if network_ids:
        pruned = subprocess.run(
            ["docker", "network", "rm", *network_ids],
            check=False,
            capture_output=True,
            text=True,
            timeout=60.0,
        )
        if pruned.returncode != 0:
            pytest.fail(f"docker network rm failed: {pruned.stderr}\n{pruned.stdout}")


def cleanup_compose_project_artifacts(env: dict[str, str]) -> None:
    _teardown_compose_project_resources(env)
    release_compose_gate_lock()


def capture_r4_manifest_artifact_ids(env: dict[str, str]) -> frozenset[str]:
    script = """
import json
from pathlib import Path
root = Path("/var/lib/gateway/artifacts")
manifest_ids = set()
for sidecar in root.rglob("*.ref.jcs"):
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        continue
    artifact_id = payload.get("artifact_id")
    if isinstance(artifact_id, str) and artifact_id.startswith("r4-manifest-"):
        manifest_ids.add(artifact_id)
print(json.dumps(sorted(manifest_ids)))
"""
    result = run_compose(env, "exec", "-T", "backend", "python", "-c", script)
    if result.returncode != 0:
        pytest.fail(f"failed to list r4-manifest artifacts: {result.stderr}\n{result.stdout}")
    payload = json.loads(result.stdout.strip() or "[]")
    return frozenset(str(item) for item in payload)


def read_history_compare_materialize_job_state(
    env: dict[str, str],
    operation_id: str,
) -> dict[str, object]:
    materialize_step_id = f"{operation_id}-step-1"
    script = f"""
import json, sqlite3, sys
from pathlib import Path
from gateway_backend.application.checkpoints import load_checkpoint_envelope
from gateway_backend.artifacts.serialize import artifact_ref_from_dict
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore

step_id = "{materialize_step_id}"
conn = sqlite3.connect("/var/lib/gateway/control/control.sqlite3")
row = conn.execute(
    "SELECT checkpoint_ref FROM step_records WHERE step_id = ?",
    (step_id,),
).fetchone()
if row is None or row[0] is None:
    raise RuntimeError(f"missing checkpoint for {{step_id}}")
checkpoint = json.loads(row[0].decode("utf-8") if isinstance(row[0], bytes) else row[0])
store = LocalArtifactStore(Path("/var/lib/gateway/artifacts"))
ref = artifact_ref_from_dict(checkpoint)
envelope = load_checkpoint_envelope(store, ref)
print(json.dumps(envelope.job_state))
"""
    result = run_compose(env, "exec", "-T", "backend", "python", "-c", script)
    if result.returncode != 0:
        pytest.fail(
            f"failed to read history compare materialize checkpoint: "
            f"{result.stderr}\n{result.stdout}"
        )
    return cast(dict[str, object], json.loads(result.stdout.strip()))


def oracle_history_compare_digest_from_materialize_checkpoint(
    env: dict[str, str],
    operation_id: str,
    *,
    before_commit: str,
    current_commit: str,
) -> str:
    materialize_step_id = f"{operation_id}-step-1"
    script = f"""
import json, sqlite3
from pathlib import Path
from gateway_backend.application.checkpoints import load_checkpoint_envelope
from gateway_backend.application.history.compare_jobs import (
    _run_pair_pipeline,
    _sides_from_materialize_checkpoint,
)
from gateway_backend.artifacts.serialize import artifact_ref_from_dict
from gateway_backend.capabilities.table_rules import comparison_rule_set, migrated_table_ruleset_snapshot
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore
from gateway_backend.operations.worker import ExecutionControl

step_id = "{materialize_step_id}"
before_commit = "{before_commit}"
current_commit = "{current_commit}"
conn = sqlite3.connect("/var/lib/gateway/control/control.sqlite3")
row = conn.execute(
    "SELECT checkpoint_ref FROM step_records WHERE step_id = ?",
    (step_id,),
).fetchone()
if row is None or row[0] is None:
    raise RuntimeError(f"missing checkpoint for {{step_id}}")
checkpoint = json.loads(row[0].decode("utf-8") if isinstance(row[0], bytes) else row[0])
store = LocalArtifactStore(Path("/var/lib/gateway/artifacts"))
ref = artifact_ref_from_dict(checkpoint)
envelope = load_checkpoint_envelope(store, ref)
job_state = envelope.job_state
sides = _sides_from_materialize_checkpoint(job_state, store)
result = _run_pair_pipeline(
    pair_id="pair-0",
    before=sides[before_commit],
    current=sides[current_commit],
    rule_set=comparison_rule_set(migrated_table_ruleset_snapshot()),
    store=store,
    control=ExecutionControl(),
)
print(result.comparison_digest)
"""
    result = run_compose(env, "exec", "-T", "backend", "python", "-c", script)
    if result.returncode != 0:
        pytest.fail(
            f"failed to compute history compare oracle digest: "
            f"{result.stderr}\n{result.stdout}"
        )
    return result.stdout.strip()


def ordered_compare_facts_from_materialize_checkpoint(
    env: dict[str, str],
    operation_id: str,
    *,
    before_commit: str,
    current_commit: str,
) -> dict[str, object]:
    materialize_step_id = f"{operation_id}-step-1"
    script = f"""
import json, sqlite3
from pathlib import Path
from gateway_backend.application.checkpoints import load_checkpoint_envelope
from gateway_backend.application.history.compare_jobs import (
    _sides_from_materialize_checkpoint,
)
from gateway_backend.artifacts.serialize import artifact_ref_from_dict
from gateway_backend.capabilities.comparison import (
    ComparisonPlan,
    ComparisonRequest,
    DetailedFactsResult,
    compare_plan,
)
from gateway_backend.capabilities.comparison import plan_comparison
from gateway_backend.capabilities.table_rules import comparison_rule_set, migrated_table_ruleset_snapshot
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore

step_id = "{materialize_step_id}"
before_commit = "{before_commit}"
current_commit = "{current_commit}"
conn = sqlite3.connect("/var/lib/gateway/control/control.sqlite3")
row = conn.execute(
    "SELECT checkpoint_ref FROM step_records WHERE step_id = ?",
    (step_id,),
).fetchone()
if row is None or row[0] is None:
    raise RuntimeError(f"missing checkpoint for {{step_id}}")
checkpoint = json.loads(row[0].decode("utf-8") if isinstance(row[0], bytes) else row[0])
store = LocalArtifactStore(Path("/var/lib/gateway/artifacts"))
ref = artifact_ref_from_dict(checkpoint)
envelope = load_checkpoint_envelope(store, ref)
job_state = envelope.job_state
sides = _sides_from_materialize_checkpoint(job_state, store)
request = ComparisonRequest(
    pair_id="pair-0",
    before=sides[before_commit],
    current=sides[current_commit],
    rule_set=comparison_rule_set(migrated_table_ruleset_snapshot()),
)
plan = plan_comparison(request)
if not isinstance(plan, ComparisonPlan):
    raise RuntimeError("pair planning failed")
compared = compare_plan(plan)
if not isinstance(compared, DetailedFactsResult) or compared.facts is None:
    raise RuntimeError("pair comparison did not produce facts")
facts = compared.facts

def _gid_from_record(record):
    for label, value in record.before_values + record.current_values:
        if label == "gid":
            return value
    return None

tables = []
for table in facts.tables:
    ordered_records = []
    if table.ordered_extension is not None:
        for record in table.ordered_extension.records:
            ordered_records.append(
                {{
                    "record_kind": record.record_kind.value,
                    "gid": _gid_from_record(record),
                    "row_identity": (
                        record.row_identity.value if record.row_identity is not None else None
                    ),
                }}
            )
    tables.append(
        {{
            "table_name": table.table_name,
            "status": table.status.value,
            "ordered_records": ordered_records,
        }}
    )
    print(json.dumps({{"tables": tables}}))
"""
    result = run_compose(env, "exec", "-T", "backend", "python", "-c", script)
    if result.returncode != 0:
        pytest.fail(
            f"failed to compute ordered compare facts: {result.stderr}\n{result.stdout}"
        )
    payload_line = result.stdout.strip().splitlines()[-1]
    return cast(dict[str, object], json.loads(payload_line))


def read_repository_table_rows(
    env: dict[str, str],
    repository_id: str,
    commit_id: str,
    table_name: str,
) -> tuple[tuple[object, ...], ...]:
    script = f"""
import json, os, subprocess, uuid
repo_hex = uuid.UUID("{repository_id}").hex
repo_path = f"/var/lib/gateway/repository/versioned/{{repo_hex}}"
commit = "{commit_id}"
table = "{table_name}"
query = subprocess.run(
    ["dolt", "sql", "-q", f"SELECT * FROM `{{table}}` AS OF '{{commit}}'", "-r", "json"],
    cwd=repo_path,
    check=False,
    capture_output=True,
    text=True,
    env={{**os.environ, "PAGER": "", "GIT_PAGER": "", "NO_COLOR": "1", "DOLT_CLI_NO_COLOR": "1"}},
)
if query.returncode != 0:
    print("[]")
else:
    payload = json.loads(query.stdout or "{{}}")
    rows = payload.get("rows", [])
    print(json.dumps([tuple(row.values()) for row in rows]))
"""
    result = run_repository_service_exec(env, "python", "-c", script)
    if result.returncode != 0:
        pytest.fail(f"failed to read repository rows: {result.stderr}\n{result.stdout}")
    payload = json.loads(result.stdout.strip() or "[]")
    return tuple(tuple(row) for row in payload)


def build_baseline_import_package() -> bytes:
    manifest: dict[str, object] = {
        "package_version": 1,
        "canonicalization_manifest_digest": BASELINE_MANIFEST_DIGEST,
        "tables": [
            {
                "name": "t",
                "schema": {
                    "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                    "primary_key": ["id"],
                },
                "row_count": 0,
            }
        ],
    }
    return _repository_service_build_package_bytes(manifest=manifest, replay_sql=BASELINE_REPLAY_SQL)


def _import_package_into_repository(
    env: dict[str, str],
    tmp_path: Path,
    *,
    repository_id: str,
    expected_commit_id: str,
    package_bytes: bytes,
    artifact_idempotency_key: str,
    import_idempotency_key: str,
    package_filename: str,
) -> str:
    package_path = tmp_path / package_filename
    package_path.write_bytes(package_bytes)
    container_id = run_compose(
        env,
        "ps",
        "repository-service",
        "--format",
        "{{.ID}}",
    ).stdout.strip()
    if not container_id:
        pytest.fail("repository-service container is not running for baseline import")
    container_package_path = f"/tmp/{package_filename}"
    copy = subprocess.run(
        ["docker", "cp", str(package_path), f"{container_id}:{container_package_path}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60.0,
    )
    if copy.returncode != 0:
        pytest.fail(f"failed to copy baseline import package: {copy.stderr}\n{copy.stdout}")
    script = f"""
import json, time, urllib.request, hashlib
base = "http://127.0.0.1:8000"
repo_id = "{repository_id}"
expected_commit = "{expected_commit_id}"
token = "{BEARER_TOKEN}"
payload = open("{container_package_path}", "rb").read()
digest = hashlib.sha256(payload).hexdigest()
upload_req = urllib.request.Request(
    f"{{base}}/v1/repositories/{{repo_id}}/artifacts",
    data=payload,
    method="POST",
    headers={{
        "Authorization": f"Bearer {{token}}",
        "Idempotency-Key": "{artifact_idempotency_key}",
        "Content-Type": "application/vnd.gateway.repository-import.v1+tar+zstd",
        "Content-Length": str(len(payload)),
        "X-Artifact-SHA256": digest,
    }},
)
with urllib.request.urlopen(upload_req, timeout=60) as response:
    uploaded = json.loads(response.read().decode())
artifact = uploaded["artifact_ref"]
import_body = json.dumps({{
    "repository_id": repo_id,
    "artifact_ref": {{
        "artifact_id": artifact["artifact_id"],
        "media_type": artifact["media_type"],
        "size_bytes": artifact["size_bytes"],
        "raw_sha256": artifact["raw_sha256"],
    }},
    "target_ref": "main",
    "expected_commit_id": expected_commit,
    "verification_policy": "STRUCTURAL",
    "unknown_type_policy": "REJECT",
}}).encode()
import_req = urllib.request.Request(
    f"{{base}}/v1/repositories/{{repo_id}}/versioned/imports",
    data=import_body,
    method="POST",
    headers={{
        "Authorization": f"Bearer {{token}}",
        "Idempotency-Key": "{import_idempotency_key}",
        "Content-Type": "application/json",
    }},
)
with urllib.request.urlopen(import_req, timeout=60) as response:
    operation = json.loads(response.read().decode())
operation_id = operation["operation_id"]
deadline = time.monotonic() + 120.0
while time.monotonic() < deadline:
    poll_req = urllib.request.Request(
        f"{{base}}/v1/repositories/{{repo_id}}/operations/{{operation_id}}",
        headers={{"Authorization": f"Bearer {{token}}"}},
    )
    with urllib.request.urlopen(poll_req, timeout=30) as response:
        body = json.loads(response.read().decode())
    operation = body["operation"]
    if operation["status"] in {{"SUCCEEDED", "FAILED", "CANCELLED"}}:
        if operation["status"] != "SUCCEEDED":
            raise RuntimeError(operation)
        break
    time.sleep(1.0)
else:
    raise RuntimeError("baseline import timed out")
resolve_req = urllib.request.Request(
    f"{{base}}/v1/repositories/{{repo_id}}/versioned/refs/main",
    headers={{"Authorization": f"Bearer {{token}}"}},
)
with urllib.request.urlopen(resolve_req, timeout=30) as response:
    resolved = json.loads(response.read().decode())
print(resolved["commit_id"])
"""
    result = run_compose(env, "exec", "-T", "repository-service", "python", "-c", script)
    if result.returncode != 0:
        pytest.fail(f"baseline import failed: {result.stderr}\n{result.stdout}")
    commit_id = result.stdout.strip()
    if not commit_id:
        pytest.fail("repository import did not return commit_id")
    return commit_id


def import_baseline_into_repository(
    env: dict[str, str],
    tmp_path: Path,
    *,
    repository_id: str,
    expected_commit_id: str,
) -> str:
    return _import_package_into_repository(
        env,
        tmp_path,
        repository_id=repository_id,
        expected_commit_id=expected_commit_id,
        package_bytes=build_baseline_import_package(),
        artifact_idempotency_key="compose-baseline-artifact",
        import_idempotency_key="compose-baseline-import",
        package_filename="baseline-import.tar.zst",
    )


def seed_repository_and_mapping(
    env: dict[str, str],
    tmp_path: Path,
    *,
    import_baseline: bool = True,
) -> tuple[str, str]:
    script = (
        "import json, urllib.request; "
        "req = urllib.request.Request("
        "'http://127.0.0.1:8000/v1/repositories', "
        "method='POST', "
        f"headers={{'Authorization': 'Bearer {BEARER_TOKEN}', 'Idempotency-Key': 'compose-seed-repo'}}); "
        "print(urllib.request.urlopen(req, timeout=30.0).read().decode())"
    )
    result = run_compose(env, "exec", "-T", "repository-service", "python", "-c", script)
    if result.returncode != 0:
        pytest.fail(f"repository seed failed: {result.stderr}\n{result.stdout}")
    payload = json.loads(result.stdout.strip())
    repository_id = str(payload["repository_id"])
    initial_commit_id = str(payload["initial_commit_id"])
    if import_baseline:
        baseline_commit_id = import_baseline_into_repository(
            env,
            tmp_path,
            repository_id=repository_id,
            expected_commit_id=initial_commit_id,
        )
    else:
        baseline_commit_id = initial_commit_id
    mapping_path = Path(env["GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE"])
    mapping_path.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "gateway_device_external_key": DEVICE_KEY,
                        "business_project_id": PROJECT_ID,
                        "repository_id": repository_id,
                        "business_baseline_node_id": BASELINE_NODE_ID,
                        "business_baseline_commit_id": baseline_commit_id,
                        "baseline_head_version": 0,
                        "enabled": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return repository_id, baseline_commit_id


def start_three_container_stack(
    env: dict[str, str],
    tmp_path: Path,
    *,
    import_baseline: bool = True,
) -> tuple[str, str]:
    acquire_compose_gate_lock()
    _assert_port_8000_available_for_gate(env["COMPOSE_PROJECT_NAME"])
    build_compose_stack_images(env)
    _teardown_compose_project_resources(env)
    up_repo = run_compose(env, "up", "-d", "--no-build", "repository-service")
    if up_repo.returncode != 0:
        pytest.fail(f"compose up repository-service failed: {up_repo.stderr}\n{up_repo.stdout}")
    wait_repository_service_ready(env)
    repository_id, initial_commit_id = seed_repository_and_mapping(
        env,
        tmp_path,
        import_baseline=import_baseline,
    )
    up_stack = run_compose(env, "up", "-d", "--no-build", "backend", "worker")
    if up_stack.returncode != 0:
        pytest.fail(f"compose up backend/worker failed: {up_stack.stderr}\n{up_stack.stdout}")
    wait_http_ok(f"{BACKEND_URL}/readyz")
    worker_ready(env)
    return repository_id, initial_commit_id


def poll_operation(
    client: httpx.Client,
    operation_id: str,
    *,
    timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_status = "unavailable"
    last_diagnostic_code: str | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/v1/operations/{operation_id}")
        if response.status_code != 200:
            time.sleep(2.0)
            continue
        body = response.json()
        status = body.get("status")
        last_status = status if type(status) is str else "invalid"
        diagnostic = body.get("diagnostic")
        diagnostic_code = diagnostic.get("code") if isinstance(diagnostic, dict) else None
        last_diagnostic_code = diagnostic_code if type(diagnostic_code) is str else None
        if body["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return cast(dict[str, Any], body)
        time.sleep(2.0)
    raise RuntimeError(
        "operation did not reach terminal status: "
        f"{operation_id} (last_status={last_status}, diagnostic_code={last_diagnostic_code})"
    )


def read_workspace_row(env: dict[str, str], workspace_id: str) -> dict[str, Any]:
    script = (
        "import json, sqlite3, sys; "
        "conn = sqlite3.connect('/var/lib/gateway/control/control.sqlite3'); "
        "row = conn.execute("
        "'SELECT optimistic_version, generation, current_preview_result_id "
        "FROM workspace_records WHERE workspace_id = ?', "
        f"('{workspace_id}',)"
        ").fetchone(); "
        "sys.stdout.write(json.dumps("
        "{'optimistic_version': row[0], 'generation': row[1], 'current_preview_result_id': row[2]} "
        "if row else {})"
        ")"
    )
    result = run_compose(env, "exec", "-T", "backend", "python", "-c", script)
    if result.returncode != 0:
        pytest.fail(f"failed to read workspace row: {result.stderr}\n{result.stdout}")
    payload = json.loads(result.stdout.strip() or "{}")
    if not payload.get("current_preview_result_id"):
        pytest.fail("workspace current_preview_result_id is empty after preview")
    return cast(dict[str, Any], payload)


def capture_business_table_state_in_compose(env: dict[str, str]) -> dict[str, tuple[int, str]]:
    tables_repr = repr(tuple(HISTORY_ZERO_WRITE_TABLES))
    script = f"""
import hashlib, json, sqlite3
tables = {tables_repr}
conn = sqlite3.connect('/var/lib/gateway/control/control.sqlite3')
state = {{}}
for table in tables:
    count = conn.execute(f'SELECT COUNT(*) FROM {{table}}').fetchone()[0]
    rows = conn.execute(f'SELECT * FROM {{table}} ORDER BY rowid').fetchall()
    payload = tuple(tuple(row) for row in rows)
    digest = hashlib.sha256(repr(payload).encode('utf-8')).hexdigest()
    state[table] = [count, digest]
print(json.dumps(state))
"""
    result = run_compose(env, "exec", "-T", "backend", "python", "-c", script)
    if result.returncode != 0:
        pytest.fail(f"failed to capture business table state: {result.stderr}\n{result.stdout}")
    payload = json.loads(result.stdout.strip() or "{}")
    return {
        table: (int(values[0]), str(values[1]))
        for table, values in payload.items()
    }


def poll_history_compare_result(
    client: httpx.Client,
    operation_id: str,
    *,
    timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = client.get(f"/v1/history-compares/{operation_id}")
        if response.status_code != 200:
            time.sleep(2.0)
            continue
        body = response.json()
        if body["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return cast(dict[str, Any], body)
        time.sleep(2.0)
    raise RuntimeError(f"history compare did not reach terminal status: {operation_id}")


def accept_history_compare(
    client: httpx.Client,
    *,
    nodes: list[dict[str, str]],
    idempotency_key: str,
    token: str,
    timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    response = client.post(
        "/v1/history-compares",
        headers=compose_auth_headers(token=token, idempotency_key=idempotency_key),
        json={"nodes": nodes},
    )
    assert response.status_code in {200, 202}, response.text
    body = cast(dict[str, Any], response.json())
    operation_id = str(body["operation_id"])
    terminal = poll_history_compare_result(
        client,
        operation_id,
        timeout_seconds=timeout_seconds,
    )
    assert terminal["status"] == "SUCCEEDED", terminal
    return terminal


def _dbcfg_sql(
    *,
    t_rows: tuple[int, ...],
    ordered_rows: tuple[tuple[int | None, int], ...] = (),
    include_ordered_table: bool = False,
    include_ordered_ddl: bool = True,
    ordered_ddl: str = ORDERED_SYX_VOCABULARY_DDL,
) -> bytes:
    lines = ["CREATE TABLE t (id INT NOT NULL PRIMARY KEY);"]
    for value in t_rows:
        lines.append(f"INSERT INTO t VALUES ({value});")
    if include_ordered_table:
        if include_ordered_ddl:
            lines.append(ordered_ddl.rstrip())
        for gid, number in ordered_rows:
            gid_sql = "NULL" if gid is None else str(gid)
            lines.append(f"INSERT INTO `{ORDERED_SYX_TABLE}` VALUES ({gid_sql}, {number});")
    return ("\n".join(lines) + "\n").encode("utf-8")


def modified_table_upload_files(
    *,
    insert_value: int,
    expected_version: int = 0,
) -> dict[str, tuple[str, bytes, str]]:
    modified_sql = _SQL.decode().replace("VALUES (1)", f"VALUES ({insert_value})").encode("utf-8")
    return upload_files(
        expected_version=expected_version,
        modified_bytes=pack_tar_gz({"sql/dbcfg.sql": modified_sql}),
    )


def _dbcfg_sql_sized_ordered(
    *,
    t_rows: tuple[int, ...],
    ordered_rows: tuple[tuple[int | None, int, str], ...] = (),
    include_ordered_table: bool = False,
    include_ordered_ddl: bool = True,
) -> bytes:
    lines = ["CREATE TABLE t (id INT NOT NULL PRIMARY KEY);"]
    for value in t_rows:
        lines.append(f"INSERT INTO t VALUES ({value});")
    if include_ordered_table:
        if include_ordered_ddl:
            lines.append(ORDERED_SYX_SIZED_DDL.rstrip())
        for gid, number, row_value in ordered_rows:
            gid_sql = "NULL" if gid is None else str(gid)
            lines.append(
                f"INSERT INTO `{ORDERED_SYX_TABLE}` VALUES ({gid_sql}, {number}, '{row_value}');"
            )
    return ("\n".join(lines) + "\n").encode("utf-8")


def ordered_syx_sized_upload_files(
    *,
    t_rows: tuple[int, ...],
    before_ordered_rows: tuple[tuple[int | None, int, str], ...],
    after_ordered_rows: tuple[tuple[int | None, int, str], ...],
    expected_version: int = 0,
) -> dict[str, tuple[str, bytes, str]]:
    initial_sql = _dbcfg_sql_sized_ordered(
        t_rows=t_rows,
        ordered_rows=before_ordered_rows,
        include_ordered_table=True,
        include_ordered_ddl=True,
    )
    modified_sql = _dbcfg_sql_sized_ordered(
        t_rows=t_rows,
        ordered_rows=after_ordered_rows,
        include_ordered_table=True,
        include_ordered_ddl=True,
    )
    return upload_files(
        expected_version=expected_version,
        initial_bytes=pack_tar_gz({"sql/dbcfg.sql": initial_sql}),
        modified_bytes=pack_tar_gz({"sql/dbcfg.sql": modified_sql}),
    )


def ordered_syx_vocabulary_upload_files(
    *,
    t_rows: tuple[int, ...],
    before_ordered_rows: tuple[tuple[int | None, int], ...],
    after_ordered_rows: tuple[tuple[int | None, int], ...],
    expected_version: int = 0,
) -> dict[str, tuple[str, bytes, str]]:
    initial_sql = _dbcfg_sql(
        t_rows=t_rows,
        ordered_rows=before_ordered_rows,
        include_ordered_table=True,
        include_ordered_ddl=True,
        ordered_ddl=ORDERED_SYX_VOCABULARY_DDL,
    )
    modified_sql = _dbcfg_sql(
        t_rows=t_rows,
        ordered_rows=after_ordered_rows,
        include_ordered_table=True,
        include_ordered_ddl=True,
        ordered_ddl=ORDERED_SYX_VOCABULARY_DDL,
    )
    return upload_files(
        expected_version=expected_version,
        initial_bytes=pack_tar_gz({"sql/dbcfg.sql": initial_sql}),
        modified_bytes=pack_tar_gz({"sql/dbcfg.sql": modified_sql}),
    )


def poll_submit_attempt(
    client: httpx.Client,
    workspace_id: str,
    submit_attempt_id: str,
    *,
    timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = client.get(
            f"/v1/workspaces/{workspace_id}/submit-attempts/{submit_attempt_id}",
        )
        if response.status_code != 200:
            time.sleep(2.0)
            continue
        body = response.json()
        if body["state"] in {"FINALIZED", "ABORTED"}:
            return cast(dict[str, Any], body)
        time.sleep(2.0)
    raise RuntimeError(f"submit attempt did not reach terminal state: {submit_attempt_id}")


def run_accept_to_submission_read_journey(
    env: dict[str, str],
    *,
    initial_commit_id: str,
    journey_key_prefix: str = "compose",
    token: str = SESSION_TOKEN,
    expected_baseline_node_id: str = BASELINE_NODE_ID,
    expected_baseline_head_version: int = 0,
    upload_files_factory: Callable[[int], dict[str, tuple[str, bytes, str]]] | None = None,
) -> dict[str, Any]:
    with httpx.Client(
        base_url=BACKEND_URL,
        headers=compose_auth_headers(token=token),
        timeout=60.0,
    ) as client:
        workspace = client.post(
            "/v1/workspaces",
            json={
                "gateway_device_external_key": DEVICE_KEY,
                "business_project_id": PROJECT_ID,
            },
        )
        assert workspace.status_code in {200, 201}, workspace.text
        workspace_body = workspace.json()
        workspace_id = workspace_body["workspace_id"]

        upload_builder = upload_files_factory or (
            lambda expected_version: upload_files(expected_version=expected_version)
        )
        upload_payload = upload_builder(workspace_body["optimistic_version"])
        upload = client.post(
            f"/v1/workspaces/{workspace_id}/upload-revisions",
            headers=compose_auth_headers(token=token, idempotency_key=f"{journey_key_prefix}-upload"),
            files=upload_payload,
        )
        assert upload.status_code == 201, upload.text
        upload_body = upload.json()

        preview = client.post(
            f"/v1/workspaces/{workspace_id}/preview-operations",
            headers=compose_auth_headers(token=token, idempotency_key=f"{journey_key_prefix}-preview"),
            json={
                "expected_workspace_version": upload_body["optimistic_version"],
                "upload_revision_id": upload_body["upload_revision_id"],
                "generation": upload_body["generation"],
                "expected_baseline_node_id": expected_baseline_node_id,
                "expected_baseline_head_version": expected_baseline_head_version,
                "options": {},
            },
        )
        assert preview.status_code == 202, preview.text
        preview_operation = preview.json()
        preview_terminal = poll_operation(client, preview_operation["operation_id"])
        assert preview_terminal["status"] == "SUCCEEDED", preview_terminal

        workspace_row = read_workspace_row(env, workspace_id)
        preview_result_id = str(workspace_row["current_preview_result_id"])
        preview_read = client.get(
            f"/v1/workspaces/{workspace_id}/preview-results/{preview_result_id}",
        )
        assert preview_read.status_code == 200, preview_read.text
        assert preview_read.json()["business_baseline_commit_id"] == initial_commit_id

        accepted = client.post(
            f"/v1/workspaces/{workspace_id}/submit-attempts",
            headers=compose_auth_headers(token=token, idempotency_key=f"{journey_key_prefix}-submit"),
            json={
                "expected_workspace_version": workspace_row["optimistic_version"],
                "upload_revision_id": upload_body["upload_revision_id"],
                "preview_result_id": preview_result_id,
                "generation": workspace_row["generation"],
                "expected_baseline_node_id": expected_baseline_node_id,
                "expected_baseline_head_version": expected_baseline_head_version,
                "options": {},
            },
        )
        assert accepted.status_code == 202, accepted.text
        accepted_body = accepted.json()
        submit_operation = poll_operation(client, accepted_body["operation_id"])
        assert submit_operation["status"] == "SUCCEEDED", submit_operation

        attempt = poll_submit_attempt(
            client,
            workspace_id,
            accepted_body["submit_attempt_id"],
        )
        assert attempt["state"] == "FINALIZED", attempt
        assert attempt.get("submission_id")

        submission = client.get(
            f"/v1/workspaces/{workspace_id}/submissions/{attempt['submission_id']}",
        )
        assert submission.status_code == 200, submission.text
        submission_body = submission.json()
        assert submission_body["submit_attempt_id"] == accepted_body["submit_attempt_id"]
        assert BEARER_TOKEN not in submission.text
        assert SESSION_TOKEN not in submission.text
        return {
            "workspace_id": workspace_id,
            "submit_attempt_id": accepted_body["submit_attempt_id"],
            "submission_id": attempt["submission_id"],
            "preview_result_id": preview_result_id,
        }
