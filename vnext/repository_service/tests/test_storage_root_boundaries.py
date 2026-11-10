"""Configured-root absence, nested mounts and metadata file ownership boundaries."""
from __future__ import annotations

import os
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from gateway_repository_service.control_db import ControlStore
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.runtime import ServiceRuntime, ServiceStartupError
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.storage_roots import RepositoryRoots
from support.lifecycle_harness import prepare_test_roots
from support.storage_layout import write_storage_layout


@pytest.mark.parametrize("missing", ["repository", "artifacts", "metadata", "scratch"])
def test_host_probe_missing_root_fails_before_database_open_and_creates_no_replacement(
    tmp_path: Path, missing: str,
) -> None:
    roots = prepare_test_roots(RepositoryRoots.under(tmp_path / "roots"))
    target = getattr(roots, missing)
    target.rmdir()
    token = tmp_path / "token"
    token.write_text("test-token")
    settings = RepositoryServiceSettings(profile="test", bearer_token_file=token, roots=roots)
    with patch.object(ControlStore, "open") as opened:
        with pytest.raises(ServiceStartupError, match="configured RS root is unavailable"):
            ServiceRuntime.start(settings)
        opened.assert_not_called()
    assert not target.exists()
    assert all(not list(root.iterdir()) for root in roots.paths() if root != target)
    assert not settings.control_db_path.exists()


@pytest.mark.parametrize("suffix", ["", "-wal", "-shm"])
def test_control_database_or_journal_symlink_is_rejected_before_open(
    tmp_path: Path, suffix: str,
) -> None:
    layout = DurableLayout.create_for_probe(tmp_path / "roots")
    settings = RepositoryServiceSettings(profile="test", bearer_token="token", roots=layout.roots)
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"outside-metadata")
    target = Path(f"{settings.control_db_path}{suffix}")
    target.symlink_to(sentinel)
    with patch.object(ControlStore, "open") as opened:
        with pytest.raises(ServiceStartupError, match="control database metadata path"):
            ServiceRuntime.start(settings)
        opened.assert_not_called()
    assert sentinel.read_bytes() == b"outside-metadata"
    assert target.is_symlink()
    assert not settings.control_db_path.exists() if suffix else settings.control_db_path.is_symlink()


def _container_command(tmp_path: Path, *, nested_mount: bool = False) -> list[str]:
    image = os.environ.get("GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE")
    if not image:
        pytest.fail("preloaded RS dependency image is required for the storage boundary proof")
    if not nested_mount:
        repository = Path(__file__).resolve().parents[2]
        prepared = subprocess.run([sys.executable, str(repository / "scripts/tests/runtime_config_fixture.py"), str(tmp_path)],
                       check=False, capture_output=True, text=True, timeout=30)
        assert prepared.returncode == 0, prepared.stdout + prepared.stderr
        document = json.loads((tmp_path / "storage-layout.json").read_bytes())
        command = ["docker", "run", "--rm", "--name", f"gateway-rs-proof-{uuid4().hex}",
            "--label", "gateway.test-task=p7-s1a-f", "--pull=never", "--network=none", "--user=0",
            "--memory=4294967296", "--memory-swap=4294967296", "--cpus=2", "--cgroupns=host",
            "--env", "PYTHONPATH=/workspace/vnext/repository_service/src:/workspace/vnext/repository_contracts/src",
            "--env", "PYTHONDONTWRITEBYTECODE=1",
            "--mount", f"type=bind,source={repository},target=/workspace/vnext,readonly"]
        for slot, item in document["roots"].items():
            if slot.startswith("rs-"):
                command += ["--mount", f"type=bind,source={item['source']},target={item['path']}"]
        for name in ("storage-layout", "resource-profile"):
            command += ["--mount", f"type=bind,source={tmp_path / (name + '.json')},target=/run/gateway/{name}.json,readonly"]
        command += ["--env", "GATEWAY_STORAGE_LAYOUT_FILE=/run/gateway/storage-layout.json",
                    "--env", "GATEWAY_RESOURCE_PROFILE_FILE=/run/gateway/resource-profile.json"]
        return command + ["--entrypoint", "sh", image]
    tmp_path.chmod(0o755)
    roots = prepare_test_roots(RepositoryRoots.under(tmp_path / "roots"))
    roots.repository.parent.chmod(0o755)
    layout_file = write_storage_layout(roots)
    document = json.loads(layout_file.read_text())
    for slot in document["roots"].values():
        slot["path"] = "/proof/" + Path(slot["path"]).relative_to(tmp_path).as_posix()
    layout_file.write_text(json.dumps(document))
    repository = Path(__file__).resolve().parents[3]
    command = ["docker", "run", "--rm", "--name", f"gateway-rs-proof-{uuid4().hex}",
        "--label", "gateway.test-task=p7-s1a-e", "--pull=never", "--network=none", "--user=0",
        "--env", "PYTHONPATH=/workspace/vnext/repository_service/src:/workspace/vnext/repository_contracts/src",
        "--env", "PYTHONDONTWRITEBYTECODE=1",
        "--env", "GATEWAY_STORAGE_LAYOUT_FILE=/proof/roots-storage-layout.json",
        "--mount", f"type=bind,source={repository},target=/workspace,readonly",
        "--mount", f"type=bind,source={tmp_path},target=/proof"]
    if nested_mount:
        (roots.repository / ".staging").mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "keep").write_bytes(b"unchanged")
        command += ["--mount", f"type=bind,source={outside},target=/proof/roots/repository/.staging"]
    return command + ["--entrypoint", "sh", image]


def _run_container(command: list[str], args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    name = command[command.index("--name") + 1]
    try:
        return subprocess.run([*command, *args], check=False, capture_output=True,
            text=True, timeout=timeout)
    finally:
        existing = subprocess.run(["docker", "container", "inspect", name],
            check=False, capture_output=True)
        if existing.returncode == 0:
            subprocess.run(["docker", "rm", "--force", name], check=True, capture_output=True)


@pytest.mark.integration
@pytest.mark.serial
def test_nested_mount_is_rejected_before_creation_or_permission_changes(tmp_path: Path) -> None:
    command = _container_command(tmp_path, nested_mount=True)
    script = r"""
import os, pwd
from pathlib import Path
from unittest.mock import patch
from gateway_repository_service import artifact_layout
from gateway_repository_service.deployment_config import StorageLayoutConfig
from gateway_repository_service.storage_roots import RepositoryRoots
from gateway_repository_service.layout import DurableLayout, LayoutError
roots = RepositoryRoots.from_config(StorageLayoutConfig.load(Path('/proof/roots-storage-layout.json')))
outside = Path('/proof/outside')
before = outside.stat()
with patch('os.mkdir', side_effect=AssertionError('creation before validation')) as mkdir, patch.object(artifact_layout, '_fchown_chmod', side_effect=AssertionError('permissions before validation')) as permissions:
    try:
        DurableLayout.create_service(roots)
    except LayoutError:
        pass
    else:
        raise AssertionError('nested mount was accepted')
    assert artifact_layout.main(['--storage-layout-file', '/proof/roots-storage-layout.json', '--gateway-user', pwd.getpwuid(os.getuid()).pw_name]) == 1
    mkdir.assert_not_called()
    permissions.assert_not_called()
assert [path.name for path in outside.iterdir()] == ['keep']
assert (outside / 'keep').read_bytes() == b'unchanged'
after = outside.stat()
assert (after.st_uid, after.st_gid, after.st_mode) == (before.st_uid, before.st_gid, before.st_mode)
print('NESTED_MOUNT_REJECTED_BEFORE_MUTATION')
"""
    result = _run_container(command, ["-c", 'exec python -c "$1"', "proof", script], timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "NESTED_MOUNT_REJECTED_BEFORE_MUTATION" in result.stdout


@pytest.mark.integration
@pytest.mark.serial
def test_entrypoint_prepares_known_parent_and_runs_real_create_as_gateway(tmp_path: Path) -> None:
    command = _container_command(tmp_path)
    script = r"""
import os, pwd
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.create_repository.command import CreateRepositoryCommand
assert os.geteuid() == pwd.getpwnam('gateway').pw_uid != 0
settings = RepositoryServiceSettings(profile='test', bearer_token='proof', max_import_workers=1)
runtime = ServiceRuntime.start(settings)
try:
    assert runtime.is_ready()
    parent = runtime.layout.repository_root / '.staging'
    assert parent.stat().st_uid == os.geteuid()
    response = CreateRepositoryCommand(settings=settings, layout=runtime.layout, mutation_store=runtime.mutation_store).execute('uid-proof')
    assert runtime.layout.published_repository(response.repository_id.hex).is_dir()
finally:
    runtime.shutdown()
import json
from dataclasses import asdict
from pathlib import Path
from gateway_repository_service.runtime_preflight import mounts, _cgroup_chain
chain = _cgroup_chain()
print('ACTUAL_RS_ROLE ' + json.dumps({'euid': os.geteuid(), 'cgroup': {name: (chain[0] / name).read_text().strip() for name in ('memory.max','memory.swap.max','cpu.max')}, 'mounts': [asdict(entry) for entry in mounts() if entry.target in {str(path) for path in settings.storage_roots.paths()}]}, sort_keys=True))
print('GATEWAY_ENTRYPOINT_START_AND_CREATE_OK euid=' + str(os.geteuid()))
"""
    result = _run_container(command, ["/workspace/vnext/repository_service/docker-entrypoint.sh",
        "python", "-c", script], timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "GATEWAY_ENTRYPOINT_START_AND_CREATE_OK euid=" in result.stdout
    print(result.stdout, flush=True)
