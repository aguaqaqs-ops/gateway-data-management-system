"""Whole-host budgets and isolation have one pure owner, with bounded host observations."""
from __future__ import annotations

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


def test_group_renderer_sets_exact_project_ports_images_and_parent_mounts(deployment: tuple[Any, Any]) -> None:
    helper, groups = deployment
    configs = helper.load_configs(groups)
    sys.path.insert(0, str(VNEXT / "scripts"))
    try:
        render = runpy.run_path(str(VNEXT / "scripts/render-runtime-config.py"))["render_group"]
    finally:
        sys.path.pop(0)
    group = groups.groups[0]
    config = configs[group.group_id]
    rendered = render(config, Path(group.storage_config), Path(group.resource_config), groups, group.group_id,
        Path("/etc/gateway/groups.json"), Path("/etc/gateway/device-directory.json"))
    assert rendered["name"] == group.project
    backend = rendered["services"]["backend"]
    assert backend["ports"] == [dict(target=8000, published=str(group.backend_port), host_ip="127.0.0.1", protocol="tcp")]
    assert backend["image"] == group.images.backend
    mounts = {item["target"]: item for item in backend["volumes"]}
    assert mounts["/run/gateway/session"]["source"] == group.session_directory
    assert mounts["/run/gateway/groups"]["source"] == "/etc/gateway"
    assert mounts["/run/gateway/session"]["read_only"] is True
    assert rendered["secrets"]["repository-bearer-token"]["file"] == group.repository_token_file
    assert rendered["services"]["worker"]["image"] == group.images.worker
