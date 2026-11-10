"""Deployment authority: role-local roots, actual limits and fail-closed identity."""
from __future__ import annotations

import json
import os
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
        root.path, config.storage.filesystems["local"].expected_source, True) for index, root in enumerate(config.storage.roots.values())))
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
    (root / preflight.MARKER).unlink()
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
    monkeypatch.setattr(os, "sched_getaffinity", lambda _: {0, 1, 2, 3})
    with pytest.raises(ValueError):
        real_check(deployment, "worker")


def test_host_initialization_validates_all_roots_before_writing_and_is_idempotent(
    deployment: DeploymentConfig, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(preflight, "mounts", lambda: (preflight.Mount(1, "1:1", "/", "/", deployment.storage.filesystems["local"].expected_source, True),))
    monkeypatch.setattr(preflight, "check_host_budget", lambda _: None)
    for root in deployment.storage.roots.values():
        (Path(root.path) / preflight.MARKER).unlink()
    unknown = Path(deployment.storage.roots["rs-scratch"].source) / "unknown"
    unknown.write_bytes(b"preserve")
    with pytest.raises(ValueError, match="empty"):
        preflight.initialize_host(deployment)
    assert all(not (Path(root.path) / preflight.MARKER).exists() for root in deployment.storage.roots.values())
    assert unknown.read_bytes() == b"preserve"
    unknown.unlink()
    preflight.initialize_host(deployment)
    preflight.check_host(deployment)
    preflight.initialize_host(deployment)


def test_renderer_runs_without_site_packages_and_owns_every_role_limit_and_bind(tmp_path: Path) -> None:
    import subprocess
    import sys
    fixtures = Path(__file__).resolve().parents[2] / "fixtures/runtime-config/v1"
    output = tmp_path / "compose-runtime.json"
    result = subprocess.run([sys.executable, "-S", str(fixtures.parents[2] / "scripts/render-runtime-config.py"),
        "--storage-layout", str(fixtures / "storage-layout.json"), "--resource-profile", str(fixtures / "resource-profile.json"),
        "render", "--output", str(output)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    services = json.loads(output.read_bytes())["services"]
    assert set(services) == {"backend", "worker", "repository-service"}
    assert services["worker"]["mem_limit"] == 32 * 1024**3
    assert services["worker"]["memswap_limit"] == 32 * 1024**3
    for role, service in services.items():
        mounts = service["volumes"]
        assert all(item["bind"]["create_host_path"] is False for item in mounts)
        assert service["deploy"]["replicas"] == 1
        own = "rs-" if role == "repository-service" else "be-"
        assert all(own in item["target"] for item in mounts[:-2])
        assert all(item["read_only"] for item in mounts[-2:])


def test_mountinfo_identifies_cgroup2_by_filesystem_type_not_source_name(tmp_path: Path) -> None:
    path = tmp_path / "mountinfo"
    path.write_text("47 30 0:29 / /sys/fs/cgroup ro,nosuid,nodev,noexec,relatime - cgroup2 none rw\n")
    entry, = preflight.mounts(path)
    assert entry.filesystem_type == "cgroup2"
    assert entry.source == "none"


def test_disabled_cpuset_controller_uses_actual_process_affinity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, deployment: DeploymentConfig) -> None:
    group = tmp_path / "delegated"
    group.mkdir()
    worker = deployment.resources.worker
    (group / "memory.max").write_text(str(worker.memory_envelope_bytes))
    (group / "memory.swap.max").write_text("0")
    (group / "cpu.max").write_text("200000 100000")
    from importlib import reload
    real_check = reload(preflight).check_resources
    monkeypatch.setattr(preflight, "_cgroup_chain", lambda: (group,))
    monkeypatch.setattr(os, "sched_getaffinity", lambda _: {0, 1})
    real_check(deployment, "worker")
    monkeypatch.setattr(os, "sched_getaffinity", lambda _: {0})
    with pytest.raises(ValueError, match="CPU/cpuset"):
        real_check(deployment, "worker")


def test_low_capacity_does_not_latch_identity_or_disable_cleanup(deployment: DeploymentConfig, monkeypatch: pytest.MonkeyPatch) -> None:
    guard = preflight.RuntimePreflight(deployment, "backend")
    original = preflight.check_capacity
    def low(*_args: object) -> tuple[int, int]:
        raise preflight.CapacityUnavailable("low capacity")
    monkeypatch.setattr(preflight, "check_capacity", low)
    with pytest.raises(preflight.CapacityUnavailable):
        guard.check()
    guard.check(capacity=False)
    cleanup_guard = preflight.RuntimePreflight(deployment, "repository_service", startup_capacity=False)
    cleanup_guard.check(capacity=False)
    monkeypatch.setattr(preflight, "check_capacity", original)
    guard.check()
    cleanup_guard.check()


@pytest.mark.parametrize("failure", ("write", "fsync"))
def test_startup_write_probe_failure_cleans_its_own_file(deployment: DeploymentConfig, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    def fail(*_args: object) -> None:
        raise OSError(5, "injected probe failure")
    with monkeypatch.context() as injected:
        injected.setattr(os, failure, fail)
        with pytest.raises(ValueError, match="probe failed"):
            preflight.RuntimePreflight(deployment, "backend")
    assert all(not list(Path(root.path).glob(".gateway-preflight-*")) for root in deployment.storage.role_roots("backend").values())


@pytest.mark.parametrize("fault", (None, "missing-leaf", "missing-ancestor", "tight-ancestor"))
def test_true_cgroup_hierarchy_root_has_no_local_limits_but_other_layers_must(deployment: DeploymentConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str | None) -> None:
    from importlib import reload
    real_check = reload(preflight).check_resources
    base, parent, leaf = tmp_path / "cgroup", tmp_path / "cgroup/parent", tmp_path / "cgroup/parent/leaf"
    leaf.mkdir(parents=True)
    (base / "cgroup.controllers").write_text("cpu memory cpuset")
    (base / "cgroup.procs").write_text("")
    worker = deployment.resources.worker
    for group in (parent, leaf):
        (group / "cgroup.type").write_text("domain")
        (group / "memory.max").write_text(str(worker.memory_envelope_bytes))
        (group / "memory.swap.max").write_text("0")
        (group / "cpu.max").write_text("200000 100000")
    if fault == "missing-leaf":
        (leaf / "memory.max").unlink()
    elif fault == "missing-ancestor":
        (parent / "cpu.max").unlink()
    elif fault == "tight-ancestor":
        (parent / "memory.max").write_text("1")
    monkeypatch.setattr(preflight, "mounts", lambda: (preflight.Mount(1, "0:1", "/", str(base), "none", True, "cgroup2"),))
    monkeypatch.setattr(preflight, "_cgroup_chain", lambda: (leaf, parent, base))
    monkeypatch.setattr(os, "sched_getaffinity", lambda _: {0, 1, 2, 3})
    if fault is None:
        real_check(deployment, "worker")
    else:
        with pytest.raises((OSError, ValueError)):
            real_check(deployment, "worker")


@pytest.fixture
def writer_deployment(tmp_path: Path) -> DeploymentConfig:
    return DeploymentConfig.load(*write_deployment_files(tmp_path / "writer-roots"))


@pytest.mark.parametrize("producer", ("artifact", "scratch"))
@pytest.mark.parametrize("allow", (False, True))
def test_production_writers_require_known_headroom_before_bytes(
    writer_deployment: DeploymentConfig, monkeypatch: pytest.MonkeyPatch, producer: str, allow: bool,
) -> None:
    from types import SimpleNamespace
    from gateway_shared_kernel import raw_blob_digest
    from gateway_backend.artifacts import ArtifactRef
    from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
    from gateway_backend.artifacts.store import StorageCapacityUnavailable
    from gateway_backend.bootstrap.storage_layout import local_store_from_config, scratch_space_from_config

    payload = b"known-write"
    ref = ArtifactRef(build_artifact_id(ArtifactLocation.EXPORT, "headroom-owner", producer),
                      "application/octet-stream", len(payload), raw_blob_digest(payload))
    store = local_store_from_config(writer_deployment)
    scratch = scratch_space_from_config(writer_deployment)
    minimum = 100
    # The config's actual policy is kept; choose its effective fractional floor.
    total = minimum * 1_000_000
    available = minimum + (len(payload) + 4096 + 65536 if allow else 1)
    monkeypatch.setattr(os, "statvfs", lambda _path: SimpleNamespace(
        f_bavail=available, f_frsize=1, f_blocks=total, f_flag=0, f_favail=100))
    if producer == "artifact":
        if allow:
            store.put(payload, ref)
            assert store.locate(ref) == payload
        else:
            with pytest.raises(StorageCapacityUnavailable):
                store.put(payload, ref)
            assert not store.object_directory(ref.artifact_id).exists()
    else:
        with scratch.session(owner="operation:headroom") as session, session.file(byte_limit=100) as (source, output):
            if allow:
                output.write(payload)
                with source.open_read() as stream:
                    assert stream.read() == payload  # buffered data is visible before close
            else:
                with pytest.raises(StorageCapacityUnavailable):
                    output.write(payload)
                with source.open_read() as stream:
                    assert stream.read() == b""


@pytest.mark.parametrize("split", (False, True))
def test_write_demands_merge_only_when_actual_filesystem_matches(
    writer_deployment: DeploymentConfig, monkeypatch: pytest.MonkeyPatch, split: bool,
) -> None:
    from types import SimpleNamespace
    observed: list[int] = []
    actual_stat = Path.stat
    scratch = Path(writer_deployment.storage.roots["be-scratch"].path)
    def device(path: Path, *args: object, **kwargs: object) -> os.stat_result:
        info = actual_stat(path, *args, **kwargs)  # type: ignore[arg-type]
        if split and path == scratch:
            values = list(info)
            values[2] += 1
            return os.stat_result(values)
        return info
    monkeypatch.setattr(Path, "stat", device)
    monkeypatch.setattr(preflight, "check_configured_root", lambda *_: None)
    def free_space(path: Path) -> SimpleNamespace:
        observed.append(Path(path).stat().st_dev)
        return SimpleNamespace(f_bavail=100000, f_frsize=1, f_blocks=1000000, f_flag=0, f_favail=100)
    monkeypatch.setattr(os, "statvfs", free_space)
    if split:
        preflight.check_write_capacity(writer_deployment.storage, {"be-export": 60000, "be-scratch": 60000})
        assert len(observed) == 2
    else:
        with pytest.raises(preflight.CapacityUnavailable):
            preflight.check_write_capacity(writer_deployment.storage, {"be-export": 60000, "be-scratch": 60000})
        assert len(observed) == 1


def test_scratch_source_already_allocated_is_not_charged_again_for_target(
    writer_deployment: DeploymentConfig, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_shared_kernel import raw_blob_digest
    from gateway_backend.artifacts import ArtifactRef
    from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
    from gateway_backend.bootstrap.storage_layout import local_store_from_config, scratch_space_from_config
    payload = b"source-bytes"
    demands: list[int] = []
    def free_capacity(_path: Path, _minimum: int, _fraction: float, *, headroom: int = 0) -> tuple[int, int]:
        demands.append(headroom)
        return 1000000, 100
    monkeypatch.setattr(preflight, "check_capacity", free_capacity)
    store = local_store_from_config(writer_deployment)
    with scratch_space_from_config(writer_deployment).session(owner="operation:copy") as session:
        with session.file(byte_limit=100) as (source, output):
            output.write(payload)
            ref = ArtifactRef(build_artifact_id(ArtifactLocation.EXPORT, "headroom-copy", "one"),
                              "application/octet-stream", len(payload), raw_blob_digest(payload))
            store.put_from_path(source, ref, checkpoint=lambda: None, byte_limit=100)
            assert store.locate(ref) == payload
    assert demands == [len(payload) + 65536, len(payload) + 4096 + 65536]
