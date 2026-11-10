"""Deployment authority: role-local roots, actual limits and fail-closed identity."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gateway_backend.deployment_config import DeploymentConfig
from gateway_backend import runtime_preflight as preflight
from tests.support.artifact_layout import write_deployment_files

pytestmark = pytest.mark.unit


@pytest.fixture
def deployment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DeploymentConfig:
    storage, resources = write_deployment_files(tmp_path / "roots")
    document = json.loads(storage.read_bytes())
    document["filesystems"]["local"]["min_free_bytes"] = 1
    document["filesystems"]["local"]["min_free_fraction"] = 0.000001
    storage.write_text(json.dumps(document))
    config = DeploymentConfig.load(storage, resources)
    for slot, root in config.storage.roots.items():
        (Path(root.path) / preflight.MARKER).write_text(json.dumps(preflight.marker_document(config.storage, slot)))
    monkeypatch.setattr(preflight, "check_resources", lambda *_: None)
    monkeypatch.setattr(preflight, "mounts", lambda: tuple(preflight.Mount(index, "1:1", root.source,
        root.path, "/dev/mapper/gateway-data", True) for index, root in enumerate(config.storage.roots.values())))
    return config


@pytest.mark.parametrize("role,prefix,count", (("backend", "be-", 6), ("worker", "be-", 6), ("repository_service", "rs-", 4)))
def test_role_checks_only_its_authorized_roots(deployment: DeploymentConfig, role: str, prefix: str, count: int) -> None:
    for slot, root in deployment.storage.roots.items():
        if not slot.startswith(prefix):
            (Path(root.path) / preflight.MARKER).unlink()
            Path(root.path).rmdir()
    guard = preflight.RuntimePreflight(deployment, role)
    observed = guard.observations()
    assert len(observed["slots"]) == count  # type: ignore[arg-type]
    assert observed["storage_digest"] == deployment.storage.digest
    assert observed["resource_digest"] == deployment.resources.digest
    assert observed["hard_envelope"] is True


@pytest.mark.parametrize("fault", ("missing", "marker", "schema-bool", "symlink", "readonly", "wrong-source", "unmounted"))
def test_invalid_root_refuses_start_without_replacement(deployment: DeploymentConfig, monkeypatch: pytest.MonkeyPatch, fault: str) -> None:
    root = Path(deployment.storage.roots["be-durable"].path)
    marker = root / preflight.MARKER
    if fault in {"missing", "symlink"}:
        marker.unlink()
        root.rmdir()
        if fault == "symlink":
            root.symlink_to(root.parent / "canonical", target_is_directory=True)
    elif fault == "marker":
        marker.write_text("{}")
    elif fault == "schema-bool":
        document = json.loads(marker.read_bytes())
        document["schema_version"] = True
        marker.write_text(json.dumps(document))
    else:
        observed = preflight.mounts()
        modified = []
        for entry in observed:
            if entry.target != str(root):
                modified.append(entry)
            elif fault != "unmounted":
                modified.append(preflight.Mount(entry.mount_id, entry.device, entry.root, entry.target,
                    "wrong" if fault == "wrong-source" else entry.source, fault != "readonly"))
        monkeypatch.setattr(preflight, "mounts", lambda: tuple(modified))
    with pytest.raises((ValueError, OSError)):
        preflight.RuntimePreflight(deployment, "backend")
    if fault == "missing":
        assert not root.exists()


def test_runtime_identity_loss_remains_latched_until_restart(deployment: DeploymentConfig) -> None:
    guard = preflight.RuntimePreflight(deployment, "worker")
    root = Path(deployment.storage.roots["be-metadata"].path)
    moved = root.with_name("old-metadata")
    root.rename(moved)
    root.mkdir()
    (root / preflight.MARKER).write_bytes((moved / preflight.MARKER).read_bytes())
    with pytest.raises(ValueError, match="identity changed"):
        guard.check()
    root.rmdir() if not list(root.iterdir()) else (root / preflight.MARKER).unlink()
    root.rmdir()
    moved.rename(root)
    with pytest.raises(ValueError, match="restart"):
        guard.check()


@pytest.mark.parametrize("fault", ("memory", "swap", "cpu", "ancestor", "cpuset"))
def test_actual_role_limits_and_ancestors_must_cover_profile(
    deployment: DeploymentConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str,
) -> None:
    own, parent = tmp_path / "own", tmp_path / "parent"
    worker = deployment.resources.worker
    for group in (own, parent):
        group.mkdir()
        (group / "memory.max").write_text(str(worker.memory_envelope_bytes))
        (group / "memory.swap.max").write_text("0")
        (group / "cpu.max").write_text("200000 100000")
        (group / "cpuset.cpus.effective").write_text("0-3")
    if fault == "memory":
        (own / "memory.max").write_text("max")
    elif fault == "swap":
        (own / "memory.swap.max").write_text("max")
    elif fault == "cpu":
        (own / "cpu.max").write_text("max 100000")
    elif fault == "ancestor":
        (parent / "memory.max").write_text("1")
    else:
        (parent / "cpuset.cpus.effective").write_text("0")
    monkeypatch.setattr(preflight, "_cgroup_chain", lambda: (own, parent))
    # Restore the production check replaced by the role-root fixture.
    from importlib import reload
    real_check = reload(preflight).check_resources
    monkeypatch.setattr(preflight, "_cgroup_chain", lambda: (own, parent))
    monkeypatch.setattr(preflight.os, "sched_getaffinity", lambda _: {0, 1, 2, 3})
    with pytest.raises(ValueError):
        real_check(deployment, "worker")
