"""Configuration comparison is derived and only backend startup may publish."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gateway_backend.bootstrap.deployment_identity import CONFIGURATION_RECORD, compare_configuration, publish_configuration
from gateway_backend.deployment_config import DeploymentConfig
from tests.support.artifact_layout import write_deployment_files

pytestmark = pytest.mark.unit


def test_worker_missing_record_never_creates_it_and_backend_startup_publishes(tmp_path: Path) -> None:
    paths = write_deployment_files(tmp_path / "roots")
    config = DeploymentConfig.load(*paths)
    record = Path(config.storage.roots["be-metadata"].path) / CONFIGURATION_RECORD
    with pytest.raises(ValueError, match="unavailable or inconsistent"):
        compare_configuration(config)
    assert not record.exists()
    publish_configuration(config)
    compare_configuration(config)
    # Whitespace and number spelling changes do not create a new identity.
    resources = json.loads(paths[1].read_bytes())
    resources["worker"]["cpu_limit"] = 2.0
    paths[1].write_text(json.dumps(resources, indent=4))
    compare_configuration(DeploymentConfig.load(*paths))


@pytest.mark.parametrize("fault", ("missing", "malformed", "wrong-group", "digest"))
def test_runtime_comparison_refuses_changed_bytes_without_repair_and_stopped_startup_can_rebuild(tmp_path: Path, fault: str) -> None:
    paths = write_deployment_files(tmp_path / "roots")
    config = DeploymentConfig.load(*paths)
    record = Path(config.storage.roots["be-metadata"].path) / CONFIGURATION_RECORD
    publish_configuration(config)
    if fault == "missing":
        record.unlink()
    elif fault == "malformed":
        record.write_text("{")
    else:
        document = json.loads(record.read_bytes())
        document["group_id" if fault == "wrong-group" else "resource_digest"] = "other"
        record.write_text(json.dumps(document))
    before = record.read_bytes() if record.exists() else None
    with pytest.raises(ValueError, match="unavailable or inconsistent"):
        compare_configuration(config)
    assert (record.read_bytes() if record.exists() else None) == before
    publish_configuration(config)
    compare_configuration(config)


@pytest.mark.parametrize("kind", ("symlink", "directory"))
def test_backend_startup_does_not_replace_redirected_configuration_records(tmp_path: Path, kind: str) -> None:
    config = DeploymentConfig.load(*write_deployment_files(tmp_path / "roots"))
    record = Path(config.storage.roots["be-metadata"].path) / CONFIGURATION_RECORD
    outside = tmp_path / "outside"
    outside.write_bytes(b"preserve")
    record.symlink_to(outside) if kind == "symlink" else record.mkdir()
    with pytest.raises((OSError, ValueError)):
        publish_configuration(config)
    assert outside.read_bytes() == b"preserve"
