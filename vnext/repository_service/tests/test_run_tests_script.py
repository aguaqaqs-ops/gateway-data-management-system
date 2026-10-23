"""Unit tests for package selection and exit-code propagation in run-tests.sh."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

VNEXT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = VNEXT_ROOT.parent
RUN_TESTS_SCRIPT = VNEXT_ROOT / "scripts" / "run-tests.sh"
CLOSURE_SCRIPT = VNEXT_ROOT / "scripts" / "test_input_closure.py"
LOCK_PACKAGES = (
    "backend",
    "repository_service",
    "repository_client",
    "repository_contracts",
    "shared_kernel",
)


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _seed_repo_file(repo_root: Path, relative: str, content: str = "fixture\n") -> None:
    path = repo_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _runner_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    repo_root = tmp_path / "runner-repo"
    vnext_root = repo_root / "vnext"
    vnext_root.mkdir(parents=True)
    shutil.copy2(VNEXT_ROOT / ".dockerignore", vnext_root / ".dockerignore")
    for package in LOCK_PACKAGES:
        _seed_repo_file(vnext_root, f"{package}/pyproject.toml")
        _seed_repo_file(vnext_root, f"{package}/uv.lock")
    for relative in (
        "repository-workspace.toml",
        "fixtures/.keep",
        "deploy/compose.yaml",
        "backend/Dockerfile",
        "repository_service/Dockerfile",
        "repository_client/tests/Dockerfile",
        "repository_client/tests/Dockerfile.dependency-base",
        "rust/Cargo.toml",
        "rust/Cargo.lock",
        "rust/rust-toolchain.toml",
        "rust/gateway-compute-python/Cargo.toml",
        "rust/gateway-compute-python-impl/Cargo.toml",
        "rust/gateway-compute-core/Cargo.toml",
        "rust/gateway-shared-kernel/Cargo.toml",
        "rust/gateway-architecture-check/Cargo.toml",
    ):
        _seed_repo_file(vnext_root, relative)

    scripts = vnext_root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RUN_TESTS_SCRIPT, scripts / "run-tests.sh")
    shutil.copy2(CLOSURE_SCRIPT, scripts / "test_input_closure.py")
    (scripts / "lib").mkdir()
    shutil.copy2(
        VNEXT_ROOT / "scripts" / "lib" / "gateway-index-env.sh",
        scripts / "lib" / "gateway-index-env.sh",
    )
    _seed_repo_file(vnext_root, "scripts/uv-consume.sh")
    _seed_repo_file(repo_root, "legacy/table-rules.json", "{}\n")
    _seed_repo_file(repo_root, ".gitignore", "**/.venv/\n**/.hypothesis/\n")
    _seed_repo_file(
        repo_root,
        "docs/backend-vnext/refactoring/formal/plans/p2-r1-runtime-provider-feasibility.md",
        "Measurement methodology version: `fixture`\n",
    )
    for package in LOCK_PACKAGES:
        environment = vnext_root / package / ".venv"
        site_packages = environment / "lib" / "python3.14" / "site-packages"
        site_packages.mkdir(parents=True, exist_ok=True)
        (environment / "pyvenv.cfg").write_text("fixture environment\n", encoding="utf-8")
        (site_packages / "fixture_dependency.py").write_text(
            f"PACKAGE = {package!r}\n", encoding="utf-8"
        )

    git_env = os.environ.copy()
    subprocess.run(["git", "init", "-q", str(repo_root)], check=True)
    subprocess.run(
        ["git", "-C", str(repo_root), "config", "user.name", "Test"],
        check=True,
        env=git_env,
    )
    subprocess.run(
        ["git", "-C", str(repo_root), "config", "user.email", "test@example.invalid"],
        check=True,
        env=git_env,
    )
    subprocess.run(["git", "-C", str(repo_root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repo_root), "commit", "-qm", "runner fixture"],
        check=True,
        env=git_env,
    )

    fake_bin = tmp_path / "fake-bin"
    tmpdir = tmp_path / "test-tmp"
    tmpdir.mkdir()
    manifest_log = tmp_path / "manifest-invocations.log"
    _write_executable(fake_bin / "dolt", "#!/usr/bin/env bash\nprintf 'dolt version 2.1.11\\n'\n")
    _write_executable(
        fake_bin / "uv",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            if [[ "$1" == "--no-config" && "$2" == "python" && "$3" == "find" ]]; then
              printf '%s\\n' {shlex.quote(sys.executable)}
            else
              printf 'uv 0.12.5\\n'
            fi
            """
        ),
    )
    _write_executable(fake_bin / "rustc", "#!/usr/bin/env bash\nprintf 'rustc 1.97.0 (fixture)\\n'\n")
    _write_executable(
        fake_bin / "docker",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            if [[ "$*" == "--version" ]]; then
              printf 'Docker version 26.1.5 (fixture)\\n'
            elif [[ "$*" == "version --format {{.Server.Version}}" ]]; then
              printf '26.1.5\\n'
            elif [[ "$*" == "compose version" ]]; then
              printf 'Docker Compose version v2.26.1 (fixture)\\n'
            elif [[ "$*" == "context show" ]]; then
              printf 'default\\n'
            elif [[ "$1" == "context" && "$2" == "inspect" ]]; then
              printf '{"Name":"default","Endpoints":{"docker":{"Host":"unix:///fixture.sock"}}}\\n'
            elif [[ "$1" == "info" && "$2" == "--format" ]]; then
              printf 'linux/amd64 overlay2\\n'
            elif [[ "$1" == "image" && "$2" == "ls" ]]; then
              exit 0
            elif [[ "$1" == "image" && "$2" == "inspect" ]]; then
              printf 'sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\\n'
            else
              echo "unexpected docker invocation: $*" >&2
              exit 99
            fi
            """
        ),
    )
    _write_executable(
        fake_bin / "python3",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            if [[ "$*" == *"test_input_closure.py manifest --package"* ]]; then
              args=("$@")
              package=""
              for ((index = 0; index < ${#args[@]}; index++)); do
                if [[ "${args[index]}" == "--package" ]]; then
                  package="${args[index + 1]}"
                  break
                fi
              done
              storage="${HYPOTHESIS_STORAGE_DIRECTORY:-}"
              if [[ -e "${storage}" || -L "${storage}" ]]; then
                storage_state=present
              else
                storage_state=absent
              fi
              printf '%s\\t%s\\t%s\\n' "${package}" "${storage}" "${storage_state}" \\
                >>"${RUNNER_MANIFEST_LOG}"
            fi
            exec "${REAL_PYTHON}" "$@"
            """
        ),
    )
    calls_log = tmp_path / "pytest-invocations.log"
    sync_log = tmp_path / "environment-syncs.log"
    fake_uv_consume = tmp_path / "uv-consume-fake.sh"
    _write_executable(
        fake_uv_consume,
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            if [[ "$*" == "-C . sync" ]]; then
              printf '%s\n' "$(basename "$PWD")" >>"${RUNNER_SYNC_LOG}"
              exit 0
            fi
            if [[ "$*" == *"python -VV"* ]]; then
              printf 'Python 3.14.6 (fixture)\\n'
              exit 0
            fi
            if [[ "$*" != *"pytest"* ]]; then
              echo "unexpected uv-consume invocation: $*" >&2
              exit 99
            fi
            storage="${HYPOTHESIS_STORAGE_DIRECTORY:-}"
            if [[ -z "${storage}" ]]; then
              echo "runner did not set HYPOTHESIS_STORAGE_DIRECTORY" >&2
              exit 98
            fi
            printf '%s\\t%s\\t%s\\n' "$PWD" "$*" "${storage}" >>"${RUNNER_CALLS_LOG}"
            mkdir -p "${storage}"
            printf 'generated by fake pytest\\n' >"${storage}/fake-example"
            for arg in "$@"; do
              if [[ "${arg}" == --ignore=* ]]; then
                exit "${RUNNER_IGNORE_STATUS:-0}"
              fi
            done
            exit "${RUNNER_PYTEST_STATUS:-0}"
            """
        ),
    )

    env = os.environ.copy()
    for name in tuple(env):
        if name.startswith(
            (
                "DOCKER_",
                "GATEWAY_BACKEND_UV_BOOTSTRAP_",
                "GATEWAY_COMPOSE_GATE_",
                "GATEWAY_DOCKER_BUILD_NETWORK",
                "GATEWAY_P2R1_",
                "GATEWAY_REPOSITORY_",
                "GATEWAY_VNEXT_LOCK_ROOT",
            )
        ) or name in {"HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy"}:
            env.pop(name, None)
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["GATEWAY_UV_CONSUME"] = str(fake_uv_consume)
    env["RUNNER_CALLS_LOG"] = str(calls_log)
    env["RUNNER_SYNC_LOG"] = str(sync_log)
    env["RUNNER_MANIFEST_LOG"] = str(manifest_log)
    env["RUNNER_HYPOTHESIS_ROOT"] = str(tmpdir / "gateway-runner-hypothesis")
    env["REAL_PYTHON"] = sys.executable
    env["TMPDIR"] = str(tmpdir)
    env["GATEWAY_TEST_WORKERS"] = "1"
    env.pop("GATEWAY_TEST_PACKAGES", None)
    return repo_root, calls_log, env


def _run_runner(
    repo_root: Path,
    env: dict[str, str],
    *,
    packages: str | None = None,
) -> subprocess.CompletedProcess[str]:
    run_env = env.copy()
    if packages is None:
        run_env.pop("GATEWAY_TEST_PACKAGES", None)
    else:
        run_env["GATEWAY_TEST_PACKAGES"] = packages
    return subprocess.run(
        ["bash", str(repo_root / "vnext" / "scripts" / "run-tests.sh")],
        check=False,
        capture_output=True,
        text=True,
        env=run_env,
        cwd=repo_root,
    )


@pytest.mark.unit
def test_run_tests_serial_batches_keep_first_batch_failure(tmp_path: Path) -> None:
    repo_root, _calls_log, env = _runner_fixture(tmp_path)
    env["GATEWAY_TEST_BASETEMP"] = str(tmp_path / "pytest-tmp")
    env["RUNNER_IGNORE_STATUS"] = "42"
    completed = _run_runner(repo_root, env)
    assert completed.returncode == 1, completed.stderr
    assert "backend status=failed" in completed.stdout
    assert "repository_service status=failed" in completed.stdout


@pytest.mark.unit
@pytest.mark.parametrize(
    ("selection", "expected_packages"),
    [
        ("shared_kernel", ["shared_kernel"]),
        (
            "repository_service,backend",
            ["backend", "backend", "repository_service", "repository_service"],
        ),
    ],
)
def test_run_tests_runs_selected_packages_in_authoritative_order(
    tmp_path: Path,
    selection: str,
    expected_packages: list[str],
) -> None:
    repo_root, calls_log, env = _runner_fixture(tmp_path)
    completed = _run_runner(repo_root, env, packages=selection)
    assert completed.returncode == 0, completed.stderr
    actual_packages = [Path(line.split("\t", 1)[0]).name for line in calls_log.read_text().splitlines()]
    assert actual_packages == expected_packages
    actual_syncs = Path(env["RUNNER_SYNC_LOG"]).read_text().splitlines()
    assert actual_syncs == sorted(
        {"backend", "repository_service"} if "," in selection else {"shared_kernel"},
        key=(
            "shared_kernel",
            "repository_contracts",
            "repository_client",
            "backend",
            "repository_service",
        ).index,
    )
    manifests = [line for line in completed.stdout.splitlines() if line.startswith("==> test input manifest")]
    assert [line.split("package=", 1)[1].split(" ", 1)[0] for line in manifests] == sorted(
        {"backend", "repository_service"} if "," in selection else {"shared_kernel"},
        key=("shared_kernel", "repository_contracts", "repository_client", "backend", "repository_service").index,
    )
    for package in set(expected_packages):
        assert f"==> {package} status=passed" in completed.stdout
    if selection == "shared_kernel":
        assert '"package": "shared_kernel"' in completed.stdout
        assert '"package": "backend"' not in completed.stdout


@pytest.mark.unit
def test_run_tests_without_package_selection_keeps_all_packages_and_two_passes(
    tmp_path: Path,
) -> None:
    repo_root, calls_log, env = _runner_fixture(tmp_path)
    completed = _run_runner(repo_root, env)
    assert completed.returncode == 0, completed.stderr
    assert "==> umask=" in completed.stdout
    actual_packages = [Path(line.split("\t", 1)[0]).name for line in calls_log.read_text().splitlines()]
    assert all(
        "\t-C . run pytest -p no:cacheprovider " in line
        for line in calls_log.read_text().splitlines()
    )
    assert actual_packages == [
        "shared_kernel",
        "repository_contracts",
        "repository_client",
        "backend",
        "backend",
        "repository_service",
        "repository_service",
    ]
    assert Path(env["RUNNER_SYNC_LOG"]).read_text().splitlines() == [
        "shared_kernel",
        "repository_contracts",
        "repository_client",
        "backend",
        "repository_service",
    ]
    assert "==> backend (parallel)" in completed.stdout
    assert "==> backend (serial)" in completed.stdout
    assert "==> repository_service (parallel)" in completed.stdout
    assert "==> repository_service (serial)" in completed.stdout
    assert "==> repository_service status=passed" in completed.stdout


@pytest.mark.unit
@pytest.mark.parametrize(
    "selection",
    ["unknown", "backend,backend", "backend,,shared_kernel", ""],
)
def test_run_tests_rejects_unknown_duplicate_or_malformed_packages(
    tmp_path: Path,
    selection: str,
) -> None:
    repo_root, calls_log, env = _runner_fixture(tmp_path)
    completed = _run_runner(repo_root, env, packages=selection)
    assert completed.returncode == 2
    assert "GATEWAY_TEST_PACKAGES" in completed.stderr
    assert not calls_log.exists()
    assert not Path(env["RUNNER_SYNC_LOG"]).exists()


@pytest.mark.parametrize(
    ("selection", "selected_packages", "retained_package", "pytest_packages"),
    [
        ("shared_kernel", ("shared_kernel",), "repository_client", ("shared_kernel",)),
        (
            "repository_service,backend",
            ("backend", "repository_service"),
            "shared_kernel",
            ("backend", "backend", "repository_service", "repository_service"),
        ),
    ],
)
@pytest.mark.parametrize(("pytest_status", "expected_exit"), [(0, 0), (37, 1)])
def test_run_tests_isolates_and_cleans_selected_hypothesis_storage(
    tmp_path: Path,
    selection: str,
    selected_packages: tuple[str, ...],
    retained_package: str,
    pytest_packages: tuple[str, ...],
    pytest_status: int,
    expected_exit: int,
) -> None:
    repo_root, calls_log, env = _runner_fixture(tmp_path)
    storage_root = Path(env["RUNNER_HYPOTHESIS_ROOT"])
    for package in selected_packages:
        package_storage = storage_root / package
        package_storage.mkdir(parents=True)
        (package_storage / "stale-example").write_text("left by an earlier run\n", encoding="utf-8")

    retained_storage = storage_root / retained_package
    retained_storage.mkdir(parents=True)
    retained_marker = retained_storage / "keep.txt"
    retained_marker.write_text("unselected path\n", encoding="utf-8")

    local_storage = repo_root / "vnext" / "shared_kernel" / ".hypothesis"
    local_storage.mkdir()
    local_marker = local_storage / "developer-cache.txt"
    local_marker.write_text("focused-run cache\n", encoding="utf-8")

    caller_storage = tmp_path / "caller-selected-hypothesis"
    caller_storage.mkdir()
    caller_marker = caller_storage / "keep.txt"
    caller_marker.write_text("external caller value\n", encoding="utf-8")
    env["HYPOTHESIS_STORAGE_DIRECTORY"] = str(caller_storage)
    env["RUNNER_PYTEST_STATUS"] = str(pytest_status)

    completed = _run_runner(repo_root, env, packages=selection)
    assert completed.returncode == expected_exit, completed.stderr

    manifest_lines = Path(env["RUNNER_MANIFEST_LOG"]).read_text().splitlines()
    manifest_events = [line.split("\t") for line in manifest_lines]
    assert manifest_events == [
        [package, str(storage_root / package), "absent"]
        for package in selected_packages
    ]

    pytest_events = [line.split("\t", 2) for line in calls_log.read_text().splitlines()]
    assert [Path(event[0]).name for event in pytest_events] == list(pytest_packages)
    assert [event[2] for event in pytest_events] == [
        str(storage_root / package) for package in pytest_packages
    ]

    for package in selected_packages:
        package_storage = storage_root / package
        assert not package_storage.exists()
        assert (
            f"==> test input manifest package={package} hypothesis_storage={package_storage}"
            in completed.stdout
        )
        assert (
            f"==> cleanup Hypothesis storage package={package} path={package_storage}"
            in completed.stdout
        )
    assert retained_marker.read_text(encoding="utf-8") == "unselected path\n"
    assert local_marker.read_text(encoding="utf-8") == "focused-run cache\n"
    assert caller_marker.read_text(encoding="utf-8") == "external caller value\n"


@pytest.mark.parametrize(
    ("selection", "selected_packages"),
    [
        ("shared_kernel", ("shared_kernel",)),
        ("repository_service,backend", ("backend", "repository_service")),
    ],
)
def test_run_tests_cleans_selected_hypothesis_storage_on_early_exit(
    tmp_path: Path,
    selection: str,
    selected_packages: tuple[str, ...],
) -> None:
    repo_root, calls_log, env = _runner_fixture(tmp_path)
    storage_root = Path(env["RUNNER_HYPOTHESIS_ROOT"])
    for package in selected_packages:
        package_storage = storage_root / package
        package_storage.mkdir(parents=True)
        (package_storage / "stale-example").write_text("left by an earlier run\n", encoding="utf-8")

    env["GATEWAY_TEST_WORKERS"] = "not-a-worker-count"
    completed = _run_runner(repo_root, env, packages=selection)
    assert completed.returncode == 2
    assert "GATEWAY_TEST_WORKERS" in completed.stderr
    assert not calls_log.exists()
    assert not Path(env["RUNNER_SYNC_LOG"]).exists()
    assert not Path(env["RUNNER_MANIFEST_LOG"]).exists()
    for package in selected_packages:
        assert not (storage_root / package).exists()
