"""Unit tests for uv-consume.sh and controlled consumption behavior."""

from __future__ import annotations

import os
import signal
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

VNEXT_ROOT = Path(__file__).resolve().parents[2]
UV_CONSUME = VNEXT_ROOT / "scripts" / "uv-consume.sh"
INDEX_LIB = VNEXT_ROOT / "scripts" / "lib" / "gateway-index-env.sh"
BACKEND_LOCK = VNEXT_ROOT / "backend" / "uv.lock"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _snapshot_locks() -> str:
    completed = subprocess.run(
        ["bash", "-c", f'source "{INDEX_LIB}" && gateway_snapshot_lockfile_sha256 "{VNEXT_ROOT}"'],
        check=True,
        capture_output=True,
        text=True,
        cwd=VNEXT_ROOT,
    )
    return completed.stdout


def _fake_uv_script(log_file: Path, *, lock_check_exit: int = 0, run_exit: int = 0) -> str:
    return textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        printf '%s\\n' "$*" >> "{log_file}"
        if [[ "$1" == "--no-config" ]]; then
          shift
        fi
        case "$1" in
          lock)
            exit {lock_check_exit}
            ;;
          run|sync|pip)
            exit {run_exit}
            ;;
          *)
            echo "unexpected uv command: $1" >&2
            exit 99
            ;;
        esac
        """
    )


def _run_uv_consume(
    tmp_path: Path,
    *,
    args: list[str],
    env: dict[str, str] | None = None,
    log_file: Path,
    fake_uv: str,
    work_dir: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(bin_dir / "uv", fake_uv)
    merged = os.environ.copy()
    merged["PATH"] = f"{bin_dir}{os.pathsep}{merged.get('PATH', '')}"
    merged["GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT"] = "0"
    if env:
        merged.update(env)
    target_dir = work_dir or (VNEXT_ROOT / "shared_kernel")
    return subprocess.run(
        ["bash", str(UV_CONSUME), "-C", str(target_dir), *args],
        check=False,
        capture_output=True,
        text=True,
        env=merged,
        cwd=VNEXT_ROOT,
    )


@pytest.mark.unit
def test_uv_consume_rejects_short_index_override_without_leaking_credentials(tmp_path: Path) -> None:
    log_file = tmp_path / "uv.log"
    completed = _run_uv_consume(
        tmp_path,
        args=["sync", "-i=https://user:secret-pass@mirror.example/simple"],
        log_file=log_file,
        fake_uv=_fake_uv_script(log_file),
    )
    assert completed.returncode == 2
    assert "may not override package index (-i)" in completed.stderr
    assert "secret-pass" not in completed.stderr
    assert "user:secret" not in completed.stderr
    assert not log_file.exists()


@pytest.mark.unit
def test_uv_consume_rejects_index_override(tmp_path: Path) -> None:
    log_file = tmp_path / "uv.log"
    completed = _run_uv_consume(
        tmp_path,
        args=["sync", "--index-url", "http://user:secret-pass@mirror.example/simple"],
        log_file=log_file,
        fake_uv=_fake_uv_script(log_file),
    )
    assert completed.returncode == 2
    assert "may not override package index (--index-url)" in completed.stderr
    assert "secret-pass" not in completed.stderr
    assert "user:secret" not in completed.stderr
    assert not log_file.exists()


@pytest.mark.unit
def test_uv_consume_cleans_lock_snapshot_after_uv_failure(tmp_path: Path) -> None:
    log_file = tmp_path / "uv.log"
    lock_tmp = tmp_path / "lock-tmp"
    lock_tmp.mkdir()
    completed = _run_uv_consume(
        tmp_path,
        args=["run", "python", "-c", "pass"],
        env={"TMPDIR": str(lock_tmp)},
        log_file=log_file,
        fake_uv=_fake_uv_script(log_file, run_exit=23),
    )

    assert completed.returncode == 23
    assert list(lock_tmp.iterdir()) == []


@pytest.mark.unit
@pytest.mark.serial
def test_uv_consume_cleans_lock_snapshot_after_sigterm(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    lock_tmp = tmp_path / "lock-tmp"
    lock_tmp.mkdir()
    started = tmp_path / "uv-started"
    fake_uv = bin_dir / "uv"
    _write_executable(
        fake_uv,
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            touch "{started}"
            exec sleep 30
            """
        ),
    )
    environment = os.environ.copy()
    environment["PATH"] = f"{bin_dir}{os.pathsep}{environment.get('PATH', '')}"
    environment["TMPDIR"] = str(lock_tmp)
    environment["GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT"] = "0"
    process = subprocess.Popen(
        ["bash", str(UV_CONSUME), "-C", str(VNEXT_ROOT / "shared_kernel"), "run", "python"],
        cwd=VNEXT_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not started.exists() and time.monotonic() < deadline:
            if process.poll() is not None:
                break
            time.sleep(0.02)
        assert started.exists(), "fake uv did not start"
        assert list(lock_tmp.iterdir()), "lock snapshot was not created before uv started"
        os.killpg(process.pid, signal.SIGTERM)
        _stdout, _stderr = process.communicate(timeout=10)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()

    assert process.returncode in {143, -signal.SIGTERM}
    assert list(lock_tmp.iterdir()) == []


@pytest.mark.unit
def test_uv_consume_rejects_directory_switch_before_no_sync_check(tmp_path: Path) -> None:
    other_dir = tmp_path / "other-project"
    other_dir.mkdir()
    log_file = tmp_path / "uv.log"
    completed = _run_uv_consume(
        tmp_path,
        args=[
            "run",
            "--offline",
            "--no-sync",
            "--directory",
            str(other_dir),
            "python",
            "-c",
            "print(1)",
        ],
        log_file=log_file,
        fake_uv=_fake_uv_script(log_file),
    )
    assert completed.returncode == 2
    assert "may not switch project context (--directory)" in completed.stderr
    assert not log_file.exists()


@pytest.mark.unit
def test_uv_consume_rejects_cross_project_py_script_before_run(tmp_path: Path) -> None:
    other_dir = tmp_path / "other-project"
    other_dir.mkdir()
    probe = other_dir / "probe.py"
    probe.write_text('print("probe")\n', encoding="utf-8")
    log_file = tmp_path / "uv.log"
    completed = _run_uv_consume(
        tmp_path,
        args=["run", "--offline", "--no-sync", str(probe)],
        log_file=log_file,
        fake_uv=_fake_uv_script(log_file),
    )
    assert completed.returncode == 2
    assert "may not execute scripts outside project directory" in completed.stderr
    assert not log_file.exists()


@pytest.mark.unit
def test_uv_consume_rejects_python_cross_project_script(tmp_path: Path) -> None:
    other_dir = tmp_path / "other-project"
    other_dir.mkdir()
    probe = other_dir / "probe.py"
    probe.write_text('print("probe")\n', encoding="utf-8")
    log_file = tmp_path / "uv.log"
    completed = _run_uv_consume(
        tmp_path,
        args=["run", "--offline", "--no-sync", "python", str(probe)],
        log_file=log_file,
        fake_uv=_fake_uv_script(log_file),
    )
    assert completed.returncode == 2
    assert "may not execute scripts outside project directory" in completed.stderr
    assert not log_file.exists()


@pytest.mark.unit
def test_uv_consume_allows_pytest_external_test_path(tmp_path: Path) -> None:
    external = tmp_path / "external"
    external.mkdir()
    test_file = external / "test_v1.py"
    test_file.write_text("def test_ok() -> None:\n    assert True\n", encoding="utf-8")
    log_file = tmp_path / "uv.log"
    completed = _run_uv_consume(
        tmp_path,
        args=["run", "--offline", "--no-sync", "pytest", "-q", str(test_file)],
        log_file=log_file,
        fake_uv=_fake_uv_script(log_file),
    )
    assert completed.returncode == 0
    assert "outside project directory" not in completed.stderr
    assert len(log_file.read_text(encoding="utf-8").splitlines()) == 2


@pytest.mark.unit
def test_uv_consume_allows_component_pytest_invocation_pattern(tmp_path: Path) -> None:
    compute_test = VNEXT_ROOT / "rust" / "gateway-compute-python" / "tests" / "test_v1.py"
    assert compute_test.is_file()
    log_file = tmp_path / "uv.log"
    completed = _run_uv_consume(
        tmp_path,
        args=["run", "--offline", "--no-sync", "pytest", "-q", str(compute_test)],
        log_file=log_file,
        fake_uv=_fake_uv_script(log_file),
        work_dir=VNEXT_ROOT / "backend",
    )
    assert completed.returncode == 0
    assert "outside project directory" not in completed.stderr
    assert len(log_file.read_text(encoding="utf-8").splitlines()) == 2


@pytest.mark.unit
def test_uv_consume_rejects_project_switch_before_no_sync_check(tmp_path: Path) -> None:
    log_file = tmp_path / "uv.log"
    completed = _run_uv_consume(
        tmp_path,
        args=["run", "--offline", "--no-sync", "--project", "other", "python", "-c", "print(1)"],
        log_file=log_file,
        fake_uv=_fake_uv_script(log_file),
    )
    assert completed.returncode == 2
    assert "may not switch project context (--project)" in completed.stderr
    assert not log_file.exists()


@pytest.mark.unit
def test_uv_consume_strips_ambient_index_env(tmp_path: Path) -> None:
    log_file = tmp_path / "uv.log"
    probe = subprocess.run(
        [
            "bash",
            "-c",
            (
                f'source "{INDEX_LIB}" && '
                "export UV_INDEX=http://mirror.example/simple && "
                "export UV_DEFAULT_INDEX=http://mirror.example/simple && "
                "export UV_FROZEN=1 && "
                'gateway_invoke_uv 0 env | sort'
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=VNEXT_ROOT,
    )
    lines = probe.stdout.splitlines()
    assert not any(line.startswith("UV_INDEX=") for line in lines)
    assert not any(line.startswith("UV_DEFAULT_INDEX=") for line in lines)
    assert not any(line.startswith("UV_FROZEN=") for line in lines)

    completed = _run_uv_consume(
        tmp_path,
        args=["sync"],
        env={
            "UV_INDEX_URL": "http://mirror.example/simple",
            "UV_FROZEN": "1",
        },
        log_file=log_file,
        fake_uv=_fake_uv_script(log_file),
    )
    assert completed.returncode == 0
    assert log_file.read_text(encoding="utf-8").splitlines()[0] == "--no-config sync --locked"


@pytest.mark.unit
def test_uv_consume_no_sync_runs_lock_check_first(tmp_path: Path) -> None:
    log_file = tmp_path / "uv.log"
    work_dir = VNEXT_ROOT / "shared_kernel"
    completed = _run_uv_consume(
        tmp_path,
        args=["run", "--offline", "--no-sync", "python", "-c", "print(1)"],
        log_file=log_file,
        fake_uv=_fake_uv_script(log_file),
    )
    assert completed.returncode == 0
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert lines[0] == f"--no-config lock --check --offline --project {work_dir}"
    assert lines[1].startswith(
        f"--no-config run --locked --project {work_dir} --offline --no-sync"
    )


@pytest.mark.unit
def test_uv_consume_no_sync_fails_when_lock_check_fails(tmp_path: Path) -> None:
    log_file = tmp_path / "uv.log"
    work_dir = VNEXT_ROOT / "shared_kernel"
    completed = _run_uv_consume(
        tmp_path,
        args=["run", "--offline", "--no-sync", "python", "-c", "print(1)"],
        log_file=log_file,
        fake_uv=_fake_uv_script(log_file, lock_check_exit=1),
    )
    assert completed.returncode == 1
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert lines == [f"--no-config lock --check --offline --project {work_dir}"]
    before = _snapshot_locks()
    after = _snapshot_locks()
    assert before == after


@pytest.mark.unit
def test_gateway_assert_lockfiles_unchanged_detects_drift(tmp_path: Path) -> None:
    before = tmp_path / "before.sha"
    before.write_text(_snapshot_locks() + "drift\n", encoding="utf-8")
    completed = subprocess.run(
        [
            "bash",
            "-c",
            (
                f'source "{INDEX_LIB}" && '
                f'gateway_assert_lockfiles_unchanged "{VNEXT_ROOT}" "{before}"'
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=VNEXT_ROOT,
    )
    assert completed.returncode == 1
    assert "uv.lock files changed" in completed.stderr


@pytest.mark.unit
def test_uv_consume_pip_install_requires_offline(tmp_path: Path) -> None:
    log_file = tmp_path / "uv.log"
    completed = _run_uv_consume(
        tmp_path,
        args=["pip-install", "/tmp/demo.whl"],
        log_file=log_file,
        fake_uv=_fake_uv_script(log_file),
        work_dir=VNEXT_ROOT / "backend",
    )
    assert completed.returncode == 2
    assert "requires --offline" in completed.stderr


@pytest.mark.unit
@pytest.mark.serial
def test_real_uv_stale_lock_fails_on_controlled_run(tmp_path: Path) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        textwrap.dedent(
            """\
            [project]
            name = "demo"
            version = "0.0.1"
            requires-python = ">=3.12"
            dependencies = []
            """
        ),
        encoding="utf-8",
    )
    subprocess.run(["uv", "lock"], check=True, cwd=project)
    (project / "pyproject.toml").write_text(
        textwrap.dedent(
            """\
            [project]
            name = "demo"
            version = "0.0.1"
            requires-python = ">=3.12"
            dependencies = ["anyio"]
            """
        ),
        encoding="utf-8",
    )
    before = (project / "uv.lock").read_bytes()
    completed = subprocess.run(
        ["bash", str(UV_CONSUME), "-C", str(project), "run", "python", "-c", "print(1)"],
        check=False,
        capture_output=True,
        text=True,
        cwd=VNEXT_ROOT,
    )
    assert completed.returncode != 0
    assert (project / "uv.lock").read_bytes() == before


@pytest.mark.unit
@pytest.mark.serial
def test_real_uv_no_sync_cross_project_py_fails_before_run(tmp_path: Path) -> None:
    project_a = tmp_path / "project_a"
    project_b = tmp_path / "project_b"
    project_a.mkdir()
    project_b.mkdir()
    pyproject = textwrap.dedent(
        """\
        [project]
        name = "demo"
        version = "0.0.1"
        requires-python = ">=3.12"
        dependencies = []
        """
    )
    (project_a / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    (project_b / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    subprocess.run(["uv", "lock"], check=True, cwd=project_a)
    subprocess.run(["uv", "lock"], check=True, cwd=project_b)
    (project_b / "pyproject.toml").write_text(
        textwrap.dedent(
            """\
            [project]
            name = "demo"
            version = "0.0.1"
            requires-python = ">=3.12"
            dependencies = ["anyio"]
            """
        ),
        encoding="utf-8",
    )
    (project_b / "probe.py").write_text('print("probe")\n', encoding="utf-8")
    before_a = (project_a / "uv.lock").read_bytes()
    before_b = (project_b / "uv.lock").read_bytes()
    completed = subprocess.run(
        [
            "bash",
            str(UV_CONSUME),
            "-C",
            str(project_a),
            "run",
            "--offline",
            "--no-sync",
            str(project_b / "probe.py"),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=VNEXT_ROOT,
    )
    assert completed.returncode != 0
    assert (project_a / "uv.lock").read_bytes() == before_a
    assert (project_b / "uv.lock").read_bytes() == before_b


@pytest.mark.unit
@pytest.mark.serial
def test_real_uv_stale_lock_no_sync_controlled_fails_before_run(tmp_path: Path) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        textwrap.dedent(
            """\
            [project]
            name = "demo"
            version = "0.0.1"
            requires-python = ">=3.12"
            dependencies = []
            """
        ),
        encoding="utf-8",
    )
    subprocess.run(["uv", "lock"], check=True, cwd=project)
    (project / "pyproject.toml").write_text(
        textwrap.dedent(
            """\
            [project]
            name = "demo"
            version = "0.0.1"
            requires-python = ">=3.12"
            dependencies = ["anyio"]
            """
        ),
        encoding="utf-8",
    )
    before = (project / "uv.lock").read_bytes()
    completed = subprocess.run(
        [
            "bash",
            str(UV_CONSUME),
            "-C",
            str(project),
            "run",
            "--offline",
            "--no-sync",
            "python",
            "-c",
            "print(1)",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=VNEXT_ROOT,
    )
    assert completed.returncode != 0
    assert (project / "uv.lock").read_bytes() == before


@pytest.mark.unit
@pytest.mark.serial
def test_real_uv_native_no_sync_may_succeed_on_stale_lock_without_changing_lock(
    tmp_path: Path,
) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        textwrap.dedent(
            """\
            [project]
            name = "demo"
            version = "0.0.1"
            requires-python = ">=3.12"
            dependencies = []
            """
        ),
        encoding="utf-8",
    )
    subprocess.run(["uv", "lock"], check=True, cwd=project)
    (project / "pyproject.toml").write_text(
        textwrap.dedent(
            """\
            [project]
            name = "demo"
            version = "0.0.1"
            requires-python = ">=3.12"
            dependencies = ["anyio"]
            """
        ),
        encoding="utf-8",
    )
    before = (project / "uv.lock").read_bytes()
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--locked",
            "--offline",
            "--no-sync",
            "python",
            "-c",
            "print(1)",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=project,
        env={
            **os.environ,
            "UV_PROJECT_ENVIRONMENT": str(tmp_path / "venv"),
        },
    )
    assert completed.returncode == 0
    assert (project / "uv.lock").read_bytes() == before
