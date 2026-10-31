"""Unit tests for build-repository-service-image.sh identity args and fail-closed exits."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from support.compose_build_harness import BUILD_SCRIPT, UV_LOCK_PATH, VNEXT_ROOT

INDEX_LIB = VNEXT_ROOT / "scripts" / "lib" / "gateway-index-env.sh"
_LOCK_PACKAGES = (
    "shared_kernel",
    "repository_contracts",
    "repository_client",
    "backend",
    "repository_service",
)

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_STUB_CANDIDATE = "a" * 40
_STUB_BUILD_INPUT = "b" * 40
_EQUAL_SHA = "a" * 40
_STUB_TREE = "sha256:" + "c" * 64
_EQUAL_TREE = _STUB_TREE
_IDENTITY_ENV_KEYS = (
    "GATEWAY_P2R1_CANDIDATE_SHA",
    "GATEWAY_P2R1_BUILD_INPUT_REVISION",
    "GATEWAY_P2R1_SOURCE_TREE_SHA256",
    "GATEWAY_P2R1_BUILD_REVISION",
)


def _uv_lock_sha256() -> str:
    return hashlib.sha256(UV_LOCK_PATH.read_bytes()).hexdigest()


def _isolated_vnext_root(tmp_path: Path) -> Path:
    isolated = tmp_path / "vnext"
    for package in _LOCK_PACKAGES:
        dest = isolated / package
        dest.mkdir(parents=True)
        shutil.copy(VNEXT_ROOT / package / "uv.lock", dest / "uv.lock")
    return isolated


def _snapshot_all_locks() -> str:
    completed = subprocess.run(
        ["bash", "-c", f'source "{INDEX_LIB}" && gateway_snapshot_lockfile_sha256 "{VNEXT_ROOT}"'],
        check=True,
        capture_output=True,
        text=True,
        cwd=VNEXT_ROOT,
    )
    return completed.stdout


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _assert_no_secret_leak(completed: subprocess.CompletedProcess[str]) -> None:
    text = f"{completed.stdout}\n{completed.stderr}".lower()
    assert "token" not in text
    assert "http_proxy" not in text
    assert "https_proxy" not in text
    assert "bearer" not in text
    assert "provenance pass" not in text


def _fake_docker_script(
    *,
    build_exit_code: int | None,
    argv_file: Path | None,
    lock_sha: str | None = None,
) -> str:
    digest = lock_sha if lock_sha is not None else _uv_lock_sha256()
    build_handler = "exit 1" if build_exit_code is None else f"exit {build_exit_code}"
    record = ""
    if argv_file is not None:
        record = f'printf "%s\\n" "$@" > "{argv_file}"\n'
    return f"""#!/usr/bin/env bash
set -euo pipefail
LOCK_SHA="{digest}"
if [[ "$1" == "image" && "$2" == "inspect" ]]; then
  for arg in "$@"; do
    if [[ "$arg" == "--format" ]]; then
      echo "${{LOCK_SHA}}"
      exit 0
    fi
  done
  exit 0
fi
if [[ "$1" == "build" ]]; then
  {record}{build_handler}
fi
echo "unexpected docker invocation: $*" >&2
exit 1
"""


def _stub_identity_json(
    *,
    candidate_sha: str = _STUB_CANDIDATE,
    build_input_revision: str = _STUB_BUILD_INPUT,
    source_tree_sha256: str = _STUB_TREE,
) -> str:
    return json.dumps(
        {
            "schema": "gateway.p2r1.build-identity",
            "schema_version": 1,
            "candidate_sha": candidate_sha,
            "build_input_revision": build_input_revision,
            "source_tree_sha256": source_tree_sha256,
        }
    )


def _python3_identity_override(json_payload: str) -> str:
    real = shutil.which("python3")
    assert real is not None
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ "${1:-}" == *build_context_digest.py && "${2:-}" == "identity" ]]; then\n'
        "  printf '%s\\n' '" + json_payload + "'\n"
        "  exit 0\n"
        "fi\n"
        f'exec "{real}" "$@"\n'
    )


def _python3_identity_failure() -> str:
    real = shutil.which("python3")
    assert real is not None
    return f"""#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == *identity* ]]; then
  echo "error: worktree is dirty" >&2
  exit 1
fi
exec "{real}" "$@"
"""


def _base_env(bin_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in _IDENTITY_ENV_KEYS:
        env.pop(key, None)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["GATEWAY_P2R1_UV_LOCK_SHA256"] = _uv_lock_sha256()
    env["GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE"] = f"gateway-p2r1-repository:lock-{_uv_lock_sha256()[:12]}"
    env["GATEWAY_REPOSITORY_SERVICE_IMAGE"] = "gateway-repository-service:test-exit-code"
    env["HTTP_PROXY"] = "http://proxy.invalid:8080"
    env["HTTPS_PROXY"] = "http://proxy.invalid:8080"
    return env


def _fake_uv_consume_script(*, lock_check_exit: int = 0) -> str:
    return textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        if [[ "$1" == "-C" ]]; then
          shift 2
        fi
        if [[ "$1" == "lock-check" ]]; then
          exit {lock_check_exit}
        fi
        exit 0
        """
    )


def _run_build_script(
    tmp_path: Path,
    *,
    timeout_script: str,
    docker_build_exit_code: int | None,
    extra_env: dict[str, str] | None = None,
    python3_script: str | None = None,
    docker_lock_sha: str | None = None,
    docker_script: str | None = None,
    uv_consume_script: str | None = None,
    lock_root: Path | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    argv_file = tmp_path / "docker-build.argv"
    _write_executable(bin_dir / "timeout", timeout_script)
    if docker_script is None:
        docker_script = _fake_docker_script(
            build_exit_code=docker_build_exit_code,
            argv_file=argv_file,
            lock_sha=docker_lock_sha,
        )
    _write_executable(bin_dir / "docker", docker_script)
    _write_executable(bin_dir / "curl", "#!/usr/bin/env bash\nexit 1\n")
    if python3_script is None:
        python3_script = _python3_identity_override(_stub_identity_json())
    _write_executable(bin_dir / "python3", python3_script)
    if uv_consume_script is None:
        uv_consume_script = _fake_uv_consume_script(lock_check_exit=0)
    _write_executable(bin_dir / "uv-consume.sh", uv_consume_script)
    env = _base_env(bin_dir)
    isolated_tmp = tmp_path / "isolated-tmp"
    isolated_tmp.mkdir()
    env["TMPDIR"] = str(isolated_tmp)
    env["GATEWAY_UV_CONSUME"] = str(bin_dir / "uv-consume.sh")
    if lock_root is not None:
        env["GATEWAY_VNEXT_LOCK_ROOT"] = str(lock_root)
    if extra_env:
        env.update(extra_env)
    completed = subprocess.run(
        ["bash", str(BUILD_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=VNEXT_ROOT,
    )
    assert list(isolated_tmp.iterdir()) == [], "lock snapshot leaked from build script"
    return completed, argv_file


def _build_arg_map(argv_file: Path) -> dict[str, str]:
    args = argv_file.read_text(encoding="utf-8").splitlines()
    values: dict[str, str] = {}
    for index, arg in enumerate(args):
        if arg == "--build-arg" and index + 1 < len(args):
            name, _, value = args[index + 1].partition("=")
            values[name] = value
    return values


def _docker_network(argv_file: Path) -> str | None:
    for arg in argv_file.read_text(encoding="utf-8").splitlines():
        if arg.startswith("--network="):
            return arg.partition("=")[2]
    return None


@pytest.mark.unit
def test_build_script_snapshots_five_lockfiles_before_and_after_build(tmp_path: Path) -> None:
    script = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert "gateway_snapshot_lockfile_sha256" in script
    assert "gateway_assert_lockfiles_unchanged" in script
    assert "lock-check" in script


@pytest.mark.unit
def test_build_script_lock_check_failure_skips_docker(tmp_path: Path) -> None:
    completed, argv_file = _run_build_script(
        tmp_path,
        timeout_script='#!/usr/bin/env bash\nshift\nexec "$@"\n',
        docker_build_exit_code=0,
        uv_consume_script=_fake_uv_consume_script(lock_check_exit=1),
    )
    assert completed.returncode == 1
    assert not argv_file.is_file()


@pytest.mark.unit
def test_build_script_preserves_build_exit_when_locks_drift(tmp_path: Path) -> None:
    isolated = _isolated_vnext_root(tmp_path)
    lock_path = isolated / "shared_kernel" / "uv.lock"
    drift_docker = _fake_docker_script(
        build_exit_code=42,
        argv_file=tmp_path / "docker-build.argv",
    ).replace(
        "exit 42",
        f'printf "\\n" >> "{lock_path}"\n  exit 42',
    )
    completed, argv_file = _run_build_script(
        tmp_path,
        timeout_script='#!/usr/bin/env bash\nshift\nexec "$@"\n',
        docker_build_exit_code=42,
        docker_script=drift_docker,
        lock_root=isolated,
    )
    assert completed.returncode == 42, completed.stderr
    argv = argv_file.read_text(encoding="utf-8").splitlines()
    dockerfile = str(VNEXT_ROOT / "repository_service" / "Dockerfile")
    file_index = argv.index("--file")
    assert argv[file_index + 1] == dockerfile
    assert str(VNEXT_ROOT) in argv


@pytest.mark.unit
def test_build_script_preserves_lockfiles_on_success(tmp_path: Path) -> None:
    before = _snapshot_all_locks()
    completed, _ = _run_build_script(
        tmp_path,
        timeout_script='#!/usr/bin/env bash\nshift\nexec "$@"\n',
        docker_build_exit_code=0,
    )
    assert completed.returncode == 0, completed.stderr
    assert _snapshot_all_locks() == before


@pytest.mark.unit
def test_build_script_preserves_lockfiles_on_docker_failure(tmp_path: Path) -> None:
    before = _snapshot_all_locks()
    completed, _ = _run_build_script(
        tmp_path,
        timeout_script='#!/usr/bin/env bash\nshift\nexec "$@"\n',
        docker_build_exit_code=42,
    )
    assert completed.returncode == 42
    assert _snapshot_all_locks() == before


@pytest.mark.unit
def test_build_script_honors_docker_build_network_override(tmp_path: Path) -> None:
    completed, argv_file = _run_build_script(
        tmp_path,
        timeout_script='#!/usr/bin/env bash\nshift\nexec "$@"\n',
        docker_build_exit_code=0,
        extra_env={"GATEWAY_DOCKER_BUILD_NETWORK": "default"},
    )
    assert completed.returncode == 0, completed.stderr
    assert _docker_network(argv_file) == "default"
    _assert_no_secret_leak(completed)


@pytest.mark.unit
def test_build_script_defaults_docker_build_network_to_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GATEWAY_DOCKER_BUILD_NETWORK", raising=False)
    completed, argv_file = _run_build_script(
        tmp_path,
        timeout_script='#!/usr/bin/env bash\nshift\nexec "$@"\n',
        docker_build_exit_code=0,
    )
    assert completed.returncode == 0, completed.stderr
    assert _docker_network(argv_file) == "host"
    _assert_no_secret_leak(completed)


@pytest.mark.unit
def test_build_script_propagates_docker_failure(tmp_path: Path) -> None:
    completed, argv_file = _run_build_script(
        tmp_path,
        timeout_script='#!/usr/bin/env bash\nshift\nexec "$@"\n',
        docker_build_exit_code=42,
    )
    assert completed.returncode == 42
    assert "==> built" not in completed.stdout
    assert argv_file.is_file()
    _assert_no_secret_leak(completed)


@pytest.mark.unit
def test_build_script_propagates_timeout_exit(tmp_path: Path) -> None:
    completed, argv_file = _run_build_script(
        tmp_path,
        timeout_script="#!/usr/bin/env bash\nexit 124\n",
        docker_build_exit_code=None,
    )
    assert completed.returncode == 124
    assert "timed out after 1800s" in completed.stderr
    assert "==> built" not in completed.stdout
    assert not argv_file.is_file()
    _assert_no_secret_leak(completed)


@pytest.mark.unit
def test_build_script_passes_three_independent_identity_args(tmp_path: Path) -> None:
    completed, argv_file = _run_build_script(
        tmp_path,
        timeout_script='#!/usr/bin/env bash\nshift\nexec "$@"\n',
        docker_build_exit_code=0,
    )
    assert completed.returncode == 0, completed.stderr
    values = _build_arg_map(argv_file)
    assert values["CANDIDATE_SHA"] == _STUB_CANDIDATE
    assert values["BUILD_INPUT_REVISION"] == _STUB_BUILD_INPUT
    assert values["SOURCE_TREE_SHA256"] == _STUB_TREE
    assert _SHA40.fullmatch(values["CANDIDATE_SHA"])
    assert _SHA40.fullmatch(values["BUILD_INPUT_REVISION"])
    assert _DIGEST.fullmatch(values["SOURCE_TREE_SHA256"])
    argv = argv_file.read_text(encoding="utf-8")
    assert argv.count("CANDIDATE_SHA=") == 1
    assert argv.count("BUILD_INPUT_REVISION=") == 1
    assert argv.count("SOURCE_TREE_SHA256=") == 1
    assert "BUILD_REVISION=" not in argv
    _assert_no_secret_leak(completed)


@pytest.mark.unit
def test_build_script_keeps_equal_candidate_and_build_input_independent(tmp_path: Path) -> None:
    payload = _stub_identity_json(
        candidate_sha=_EQUAL_SHA,
        build_input_revision=_EQUAL_SHA,
        source_tree_sha256=_EQUAL_TREE,
    )
    completed, argv_file = _run_build_script(
        tmp_path,
        timeout_script='#!/usr/bin/env bash\nshift\nexec "$@"\n',
        docker_build_exit_code=0,
        python3_script=_python3_identity_override(payload),
    )
    assert completed.returncode == 0, completed.stderr
    values = _build_arg_map(argv_file)
    assert values["CANDIDATE_SHA"] == _EQUAL_SHA
    assert values["BUILD_INPUT_REVISION"] == _EQUAL_SHA
    assert values["SOURCE_TREE_SHA256"] == _EQUAL_TREE
    argv_text = argv_file.read_text(encoding="utf-8")
    assert argv_text.count("CANDIDATE_SHA=") == 1
    assert argv_text.count("BUILD_INPUT_REVISION=") == 1
    _assert_no_secret_leak(completed)


@pytest.mark.unit
def test_build_script_rejects_dirty_tree_before_docker(tmp_path: Path) -> None:
    completed, argv_file = _run_build_script(
        tmp_path,
        timeout_script='#!/usr/bin/env bash\nshift\nexec "$@"\n',
        docker_build_exit_code=0,
        python3_script=_python3_identity_failure(),
    )
    assert completed.returncode != 0
    assert not argv_file.is_file()
    assert "unable to compute repository image identity" in completed.stderr
    assert "==> built" not in completed.stdout
    _assert_no_secret_leak(completed)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "value"),
    [("schema", "gateway.p2r1.build-identity-v0"), ("schema_version", True)],
    ids=["schema-name", "boolean-schema-version"],
)
def test_build_script_rejects_unsupported_identity_schema_before_docker(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    identity = json.loads(_stub_identity_json())
    identity[field] = value
    payload = json.dumps(identity)
    completed, argv_file = _run_build_script(
        tmp_path,
        timeout_script='#!/usr/bin/env bash\nshift\nexec "$@"\n',
        docker_build_exit_code=0,
        python3_script=_python3_identity_override(payload),
    )
    assert completed.returncode != 0
    assert not argv_file.is_file()
    assert "unable to parse canonical repository image identity" in completed.stderr
    _assert_no_secret_leak(completed)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("env_key", "env_value"),
    [
        ("GATEWAY_P2R1_CANDIDATE_SHA", "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"),
        ("GATEWAY_P2R1_BUILD_INPUT_REVISION", "unknown"),
        ("GATEWAY_P2R1_SOURCE_TREE_SHA256", "sha256:" + "0" * 64),
        ("GATEWAY_P2R1_CANDIDATE_SHA", "abc"),
    ],
    ids=["candidate-mismatch", "build-input-unknown", "source-tree-stale", "candidate-short"],
)
def test_build_script_rejects_caller_override_before_docker(
    tmp_path: Path,
    env_key: str,
    env_value: str,
) -> None:
    completed, argv_file = _run_build_script(
        tmp_path,
        timeout_script='#!/usr/bin/env bash\nshift\nexec "$@"\n',
        docker_build_exit_code=0,
        extra_env={env_key: env_value},
    )
    assert completed.returncode != 0
    assert not argv_file.is_file()
    assert "does not match helper" in completed.stderr
    _assert_no_secret_leak(completed)


@pytest.mark.unit
def test_build_script_rejects_lock_mismatch_before_docker(tmp_path: Path) -> None:
    completed, argv_file = _run_build_script(
        tmp_path,
        timeout_script='#!/usr/bin/env bash\nshift\nexec "$@"\n',
        docker_build_exit_code=0,
        extra_env={"GATEWAY_P2R1_UV_LOCK_SHA256": "0" * 64},
    )
    assert completed.returncode != 0
    assert not argv_file.is_file()
    assert "does not match repository_service/uv.lock" in completed.stderr
    _assert_no_secret_leak(completed)


@pytest.mark.unit
def test_build_script_rejects_dependency_base_lock_mismatch(tmp_path: Path) -> None:
    completed, argv_file = _run_build_script(
        tmp_path,
        timeout_script='#!/usr/bin/env bash\nshift\nexec "$@"\n',
        docker_build_exit_code=0,
        docker_lock_sha="0" * 64,
    )
    assert completed.returncode != 0
    assert not argv_file.is_file()
    assert "no retained dependency-base image" in completed.stderr
    _assert_no_secret_leak(completed)
