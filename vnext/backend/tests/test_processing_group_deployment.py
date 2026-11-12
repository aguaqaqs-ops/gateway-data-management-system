"""Whole-host budgets and isolation have one pure owner, with bounded host observations."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import importlib
import json
from pathlib import Path
import runpy
import sys
from typing import Any

import pytest

pytestmark = pytest.mark.unit
VNEXT = Path(__file__).resolve().parents[2]


@pytest.fixture
def deployment(tmp_path: Path) -> tuple[Any, Any]:
    sys.path.insert(0, str(VNEXT / "scripts"))
    try:
        helper = importlib.import_module("processing_group_deployment")
        groups_model = importlib.import_module("processing_group_config").ProcessingGroupsConfig
    finally:
        sys.path.pop(0)
    document = json.loads((VNEXT / "fixtures/processing-groups/v1/groups.json").read_bytes())
    for index, group in enumerate(document["groups"]):
        directory = tmp_path / group["group_id"]
        directory.mkdir()
        (directory / "session").mkdir()
        (directory / "session/session.json").write_text('{"sessions":[]}')
        for name in ("internal", "repository"):
            (directory / (name + ".token")).write_text(f"{index}-{name}-credential")
            group[name + "_token_file"] = str(directory / (name + ".token"))
        group["session_directory"] = str(directory / "session")
        storage = json.loads((VNEXT / "fixtures/runtime-config/v1/storage-layout.json").read_bytes())
        resources = json.loads((VNEXT / "fixtures/runtime-config/v1/resource-profile.json").read_bytes())
        for value in (storage, resources):
            value.update(environment_id=document["environment_id"], group_id=group["group_id"])
        storage["filesystems"]["local"]["mountpoint"] = str(tmp_path)
        resources["host_budget"] = document["host"]
        resources["worker"].update(memory_envelope_bytes=12 * 1024**3, kernel_memory_bytes=4 * 1024**3)
        for slot, root in storage["roots"].items():
            root["source"] = str(directory / slot)
            (directory / slot).mkdir()
        for name, value in (("storage", storage), ("resource", resources)):
            filename = directory / (name + ".json")
            filename.write_text(json.dumps(value))
            group[name + "_config"] = str(filename)
    return helper, groups_model.from_bytes(json.dumps(document).encode())


def test_aggregate_budget_counts_entry_and_shared_reserve_once(deployment: tuple[Any, Any]) -> None:
    helper, groups = deployment
    configs = helper.load_configs(groups)
    assert set(configs) == {"group-a", "group-b"}
    # Two W1 groups fit 44.5 GiB including one 8 GiB shared reserve.
    host = replace(groups.host, memory_bytes=int(44.5 * 1024**3))
    for group in groups.groups:
        path = Path(group.resource_config)
        document = json.loads(path.read_bytes())
        document["host_budget"]["memory_bytes"] = host.memory_bytes
        path.write_text(json.dumps(document))
    helper.load_configs(replace(groups, host=host))
    too_small = replace(host, memory_bytes=host.memory_bytes - 1)
    for group in groups.groups:
        path = Path(group.resource_config)
        document = json.loads(path.read_bytes())
        document["host_budget"]["memory_bytes"] = too_small.memory_bytes
        path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="all groups"):
        helper.load_configs(replace(groups, host=too_small))


@pytest.mark.parametrize("fault", ["root-nesting", "token-content", "session-nesting", "host-mismatch", "group-mismatch"])
def test_cross_group_paths_credentials_and_identity_are_independent(deployment: tuple[Any, Any], fault: str) -> None:
    helper, groups = deployment
    first, second = groups.groups
    if fault == "token-content":
        Path(second.repository_token_file).write_bytes(Path(first.repository_token_file).read_bytes())
    elif fault == "session-nesting":
        nested = Path(first.session_directory) / "nested"
        nested.mkdir()
        (nested / "session.json").write_text('{"sessions":[]}')
        groups = replace(groups, groups=(first, replace(second, session_directory=str(nested))))
    else:
        filename = Path(second.storage_config if fault != "host-mismatch" else second.resource_config)
        document = json.loads(filename.read_bytes())
        if fault == "root-nesting":
            original = json.loads(Path(first.storage_config).read_bytes())["roots"]["be-metadata"]["source"]
            document["roots"]["be-metadata"]["source"] = original + "/nested"
        elif fault == "host-mismatch":
            document["host_budget"]["cpu_count"] -= 1
        else:
            document["group_id"] = "wrong-group"
        filename.write_text(json.dumps(document))
    with pytest.raises(ValueError):
        helper.load_configs(groups)


@pytest.mark.parametrize("workers", [1, 2])
def test_group_renderer_sets_exact_project_ports_images_and_parent_mounts(deployment: tuple[Any, Any], tmp_path: Path, workers: int) -> None:
    helper, groups = deployment
    path = Path(groups.groups[0].resource_config)
    resource = json.loads(path.read_bytes())
    resource["worker"].update(count=workers, active_limit=workers)
    path.write_text(json.dumps(resource))
    public = tmp_path / "public"
    public.mkdir()
    configs = helper.load_configs(groups)
    sys.path.insert(0, str(VNEXT / "scripts"))
    try:
        render = runpy.run_path(str(VNEXT / "scripts/render-runtime-config.py"))["render_group"]
    finally:
        sys.path.pop(0)
    group = groups.groups[0]
    config = configs[group.group_id]
    rendered = render(config, Path(group.storage_config), Path(group.resource_config), groups, group.group_id,
        public / "groups.json", public / "device-directory.json")
    assert rendered["name"] == group.project
    backend = rendered["services"]["backend"]
    assert backend["ports"] == [dict(target=8000, published=str(group.backend_port), host_ip="127.0.0.1", protocol="tcp")]
    assert backend["image"] == group.images.backend
    assert backend["build"]["args"]["CANDIDATE_SHA"] == "unknown"
    assert rendered["services"]["repository-service"]["build"]["args"]["CANDIDATE_SHA"] == "unknown"
    mounts = {item["target"]: item for item in backend["volumes"]}
    assert mounts["/run/gateway/session"]["source"] == group.session_directory
    assert mounts["/run/gateway/groups"]["source"] == str(public)
    assert mounts["/run/gateway/session"]["read_only"] is True
    assert rendered["secrets"]["repository-bearer-token"]["file"] == group.repository_token_file
    assert rendered["services"]["worker"]["image"] == group.images.worker
    for name in ("worker", "worker-2")[:workers]:
        targets = [item["target"] for item in rendered["services"][name]["volumes"]]
        assert len(set(targets)) == len(targets)


def test_same_physical_disk_is_reported_once_across_groups(deployment: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    helper, groups = deployment
    from types import SimpleNamespace
    monkeypatch.setattr(helper.host, "check_host", lambda *args, **kwargs: None)
    monkeypatch.setattr(helper.host, "mounts", lambda: (SimpleNamespace(target="/", root="/", device="8:1"),))
    result = helper.check_groups(groups)
    assert len(result["filesystems"]) == 1
    assert next(iter(result["filesystems"].values()))["available_bytes"] > 0


def test_actual_container_inspection_rejects_mount_port_image_and_project_drift(deployment: tuple[Any, Any], tmp_path: Path) -> None:
    helper, groups = deployment
    config = helper.load_configs(groups)["group-a"]
    group = groups.groups[0]
    public = tmp_path / "public"
    public.mkdir()
    (public / "groups.json").write_bytes(groups.to_bytes())
    (public / "device-directory.json").write_text(json.dumps(dict(schema_version=1, environment_id=groups.environment_id, devices=[])))
    containers = []
    for service, role in (("backend", "backend"), ("worker", "worker"), ("repository-service", "repository_service")):
        profile = getattr(config.resources, role)
        memory = profile.memory_envelope_bytes if role == "worker" else profile.memory_limit_bytes
        images = {"backend": group.images.backend, "worker": group.images.worker, "repository_service": group.images.repository_service}
        mounts = [dict(Type="bind", Source=root.source, Destination=root.path, RW=True)
            for root in config.storage.role_roots(role).values()]
        files = {"/run/gateway/storage-layout.json": group.storage_config,
            "/run/gateway/resource-profile.json": group.resource_config,
            "/run/secrets/repository-bearer-token": group.repository_token_file}
        environment = []
        if role != "repository_service":
            files.update({"/run/gateway/groups": str(public), "/run/gateway/provisioned-mapping.json": str(tmp_path / "seed.json")})
            prefix = "GATEWAY_BACKEND_" if role == "backend" else "GATEWAY_BACKEND_OPERATION_WORKER_"
            environment += [prefix + "REPOSITORY_BASE_URL=http://repository-service:8000",
                prefix + "REPOSITORY_BEARER_TOKEN_FILE=/run/secrets/repository-bearer-token",
                prefix + "PROCESSING_GROUPS_FILE=/run/gateway/groups/groups.json",
                prefix + "DEVICE_DIRECTORY_FILE=/run/gateway/groups/device-directory.json"]
        if role == "worker":
            environment += ["GATEWAY_BACKEND_OPERATION_WORKER_INSTANCE_INDEX=1"]
        if role == "backend":
            environment += ["GATEWAY_BACKEND_SESSION_FILE=/run/gateway/session/session.json"]
            files.update({"/run/gateway/session": group.session_directory,
                "/run/secrets/backend-internal-bearer": group.internal_token_file})
        mounts.extend(dict(Type="bind", Source=source, Destination=target, RW=False) for target, source in files.items())
        containers.append(dict(Id=service, Image="sha256:" + role, State=dict(Status="running"), Mounts=mounts,
            NetworkSettings=dict(Networks={group.project + "_default": {}}),
            Config=dict(Image=images[role], Env=environment, Labels={"com.docker.compose.project": group.project,
                "org.opencontainers.image.revision": group.images.revision,
                "com.docker.compose.service": service, "com.docker.compose.container-number": "1", "com.docker.compose.oneoff": "False"}),
            HostConfig=dict(Memory=memory, MemorySwap=memory + profile.swap_limit_bytes,
                NanoCpus=round(profile.cpu_limit * 1_000_000_000), RestartPolicy=dict(Name="no"),
                PortBindings={"8000/tcp": [dict(HostIp="127.0.0.1", HostPort=str(group.backend_port))]} if role == "backend" else {})))
    assert set(helper.validate_group_containers(config, group, containers)) == {"backend", "worker", "repository-service"}
    identities = {entry["Config"]["Image"]: dict(Id=entry["Image"], Config=dict(Labels={"org.opencontainers.image.revision": group.images.revision}))
        for entry in containers}
    assert helper.validate_group_containers(config, group, containers, image_identities=identities)
    identities[group.images.backend]["Id"] = "sha256:old-tag-target"
    with pytest.raises(ValueError, match="selected local image"):
        helper.validate_group_containers(config, group, containers, image_identities=identities)
    faults: list[tuple[list[Any], Any]] = [(["Config", "Image"], "other:revision"),
        (["Config", "Labels", "com.docker.compose.project"], "other"),
        (["Config", "Labels", "org.opencontainers.image.revision"], "0" * 40),
        (["NetworkSettings", "Networks"], {"other_default": {}}),
        (["HostConfig", "Memory"], 1),
        (["HostConfig", "PortBindings"], {"8000/tcp": [dict(HostIp="0.0.0.0", HostPort=str(group.backend_port))]}),
        (["Mounts", 0, "Source"], "/other-group/root"),
        (["Mounts", 0, "RW"], False)]
    for path, value in faults:
        changed = deepcopy(containers)
        target: Any = changed[0]
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        with pytest.raises(ValueError):
            helper.validate_group_containers(config, group, changed)


def test_public_parent_cannot_expose_group_private_paths(deployment: tuple[Any, Any], tmp_path: Path) -> None:
    helper, groups = deployment
    public = tmp_path / "public"
    public.mkdir()
    helper.check_public_directory(groups, public)
    # The tempting common configuration parent contains all private group files.
    with pytest.raises(ValueError, match="paths overlap"):
        helper.check_public_directory(groups, tmp_path)


def test_public_parent_alias_cannot_expose_private_group_root(deployment: tuple[Any, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace
    helper, groups = deployment
    public = tmp_path / "public"
    public.mkdir()
    private = Path(groups.groups[0].session_directory)
    monkeypatch.setattr(helper.host, "mounts", lambda: (SimpleNamespace(target="/", root="/"),
        SimpleNamespace(target=str(public), root=str(private))))
    with pytest.raises(ValueError, match="paths overlap"):
        helper.check_public_directory(groups, public)


def test_public_parent_rejects_any_nested_bind_mount(deployment: tuple[Any, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace
    helper, groups = deployment
    public = tmp_path / "public"
    public.mkdir()
    monkeypatch.setattr(helper.host, "mounts", lambda: (SimpleNamespace(target="/", root="/"),
        SimpleNamespace(target=str(public / "hidden"), root=str(Path(groups.groups[0].session_directory)))))
    with pytest.raises(ValueError, match="child mounts"):
        helper.check_public_directory(groups, public)


@pytest.mark.parametrize("fault", [None, "dirty", "revision"])
def test_source_build_uses_only_verified_selected_revision_and_repository_provenance(deployment: tuple[Any, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str | None) -> None:
    import subprocess
    helper, groups = deployment
    selected = replace(groups.groups[0], images=replace(groups.groups[0].images, revision="1" * 40))
    groups = replace(groups, groups=(selected, groups.groups[1]))
    public = tmp_path / "public"
    public.mkdir()
    config = helper.load_configs(groups)[selected.group_id]
    sys.path.insert(0, str(VNEXT / "scripts"))
    try:
        render = runpy.run_path(str(VNEXT / "scripts/render-runtime-config.py"))["render_group"]
    finally:
        sys.path.pop(0)
    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[-1] == "HEAD":
            output = "9" * 40 if fault == "revision" else selected.images.revision
        elif command[-1] == "--porcelain":
            output = " M source.py" if fault == "dirty" else ""
        else:
            assert command[-1] == "identity"
            output = json.dumps(dict(candidate_sha=selected.images.revision, build_input_revision="2" * 40,
                source_tree_sha256="sha256:" + "3" * 64))
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")
    monkeypatch.setattr(subprocess, "run", run)
    if fault is not None:
        with pytest.raises(ValueError, match="clean revision"):
            render(config, Path(selected.storage_config), Path(selected.resource_config), groups, selected.group_id,
                public / "groups.json", public / "device-directory.json", build_from_source=True)
        return
    rendered = render(config, Path(selected.storage_config), Path(selected.resource_config), groups, selected.group_id,
        public / "groups.json", public / "device-directory.json", build_from_source=True)
    for role in ("backend", "worker", "repository-service"):
        assert rendered["services"][role]["build"]["args"]["CANDIDATE_SHA"] == selected.images.revision
    arguments = rendered["services"]["repository-service"]["build"]["args"]
    assert arguments["BUILD_INPUT_REVISION"] == "2" * 40
    assert arguments["SOURCE_TREE_SHA256"] == "sha256:" + "3" * 64
