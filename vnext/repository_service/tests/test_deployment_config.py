"""The same bounded deployment format vectors are owned by both role adapters."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from gateway_repository_service.deployment_config import DeploymentConfig, ResourceProfile, StorageLayoutConfig

pytestmark = pytest.mark.unit
_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures/runtime-config/v1"
_INVALID = json.loads((_FIXTURES / "invalid-configs.json").read_bytes())


def _documents() -> tuple[dict[str, Any], dict[str, Any]]:
    return (json.loads((_FIXTURES / "storage-layout.json").read_bytes()),
        json.loads((_FIXTURES / "resource-profile.json").read_bytes()))


def test_shared_configuration_roundtrip_and_role_scope() -> None:
    storage, resources = _documents()
    config = DeploymentConfig(StorageLayoutConfig.from_bytes(json.dumps(storage).encode()),
        ResourceProfile.from_bytes(json.dumps(resources).encode()))
    assert set(config.storage.role_roots("backend")) == {"be-" + item for item in
        ("durable", "canonical", "comparison", "export", "scratch", "metadata")}
    assert len(config.storage.role_roots("repository_service")) == 4
    assert config.storage.role_roots("worker") == config.storage.role_roots("backend")
    assert config.resources.worker.kernel_memory_bytes == 24 * 1024**3
    assert config.resources.worker.count == config.resources.worker.active_limit == 1
    assert config.storage.digest == StorageLayoutConfig.from_bytes(json.dumps(storage, sort_keys=True).encode()).digest
    assert config.resources.digest == ResourceProfile.from_bytes(json.dumps(resources, sort_keys=True).encode()).digest
    with pytest.raises(ValueError):
        config.storage.role_roots("other")


@pytest.mark.parametrize("case", _INVALID)
def test_shared_invalid_configuration_vectors(case: dict[str, Any]) -> None:
    storage, resources = _documents()
    document = deepcopy(storage if case["document"] == "storage" else resources)
    current = document
    for key in case["path"][:-1]:
        current = current[key]
    current[case["path"][-1]] = case["value"]
    parser = StorageLayoutConfig if case["document"] == "storage" else ResourceProfile
    with pytest.raises(ValueError):
        parser.from_bytes(json.dumps(document).encode())


@pytest.mark.parametrize("raw", [b'{"schema_version":1,"schema_version":1}',
    b'{"worker":{"cpu_limit":NaN}}', b'{"worker":{"cpu_limit":Infinity}}', b'[]', b' ' * (256 * 1024 + 1)])
@pytest.mark.parametrize("parser", [StorageLayoutConfig, ResourceProfile])
def test_configuration_rejects_duplicate_nonfinite_nonobject_and_oversize(raw: bytes, parser: Any) -> None:
    with pytest.raises(ValueError):
        parser.from_bytes(raw)


def test_configuration_pair_must_match_namespace() -> None:
    storage, resources = _documents()
    resources["group_id"] = "other"
    with pytest.raises(ValueError, match="must match"):
        DeploymentConfig(StorageLayoutConfig.from_bytes(json.dumps(storage).encode()),
            ResourceProfile.from_bytes(json.dumps(resources).encode()))


def test_storage_has_exact_roots_and_bounded_filesystems() -> None:
    storage, _ = _documents()
    del storage["roots"]["be-durable"]
    with pytest.raises(ValueError):
        StorageLayoutConfig.from_bytes(json.dumps(storage).encode())
    storage, _ = _documents()
    for index in range(11):
        storage["filesystems"][f"fs-{index}"] = deepcopy(storage["filesystems"]["local"])
    with pytest.raises(ValueError):
        StorageLayoutConfig.from_bytes(json.dumps(storage).encode())


def test_same_disk_and_split_disk_configuration_formats() -> None:
    storage, _ = _documents()
    same_disk = StorageLayoutConfig.from_bytes(json.dumps(storage).encode())
    storage["filesystems"] = {}
    for index, (slot, root) in enumerate(storage["roots"].items()):
        fs_id = f"disk-{index}"
        storage["filesystems"][fs_id] = {"mountpoint": f"/mnt/{fs_id}", "expected_source": f"/dev/{fs_id}",
            "min_free_bytes": 1, "min_free_fraction": 0.1}
        root["source"] = f"/mnt/{fs_id}/{slot}"
        root["filesystem_id"] = fs_id
    split_disk = StorageLayoutConfig.from_bytes(json.dumps(storage).encode())
    assert same_disk.digest != split_disk.digest
    assert len({root.filesystem_id for root in same_disk.roots.values()}) == 1
    assert len({root.filesystem_id for root in split_disk.roots.values()}) == 10
    assert set(same_disk.role_roots("backend")) == set(split_disk.role_roots("backend"))


def test_aliases_of_one_filesystem_reject_conflicting_capacity_policy() -> None:
    storage, _ = _documents()
    storage["filesystems"]["other"] = {**storage["filesystems"]["local"],
        "mountpoint": "/mnt/other", "min_free_bytes": 1}
    storage["roots"]["be-export"]["source"] = "/mnt/other/export"
    storage["roots"]["be-export"]["filesystem_id"] = "other"
    with pytest.raises(ValueError, match="one capacity policy"):
        StorageLayoutConfig.from_bytes(json.dumps(storage).encode())
