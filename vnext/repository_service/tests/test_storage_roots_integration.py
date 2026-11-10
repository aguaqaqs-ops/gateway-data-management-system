"""Real-filesystem RS publication, import, recovery and stopped-service administration."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from gateway_repository_contracts import OperationStatus
from gateway_repository_service.app import create_app
from gateway_repository_service.capacity import assert_import_layout_admission, CapacityAdmissionError
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.storage_roots import RepositoryRoots
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.faults import ImportWorkerFaultPoint
from support.http_harness import import_headers
from support.import_recovery_harness import (
    assert_crash_exit, crash_import_subprocess, seed_queued_dolt_import,
)
from support.storage_layout import write_storage_layout
from support.upload_harness import upload_headers
from test_import_package import build_package_bytes
from test_snapshot_admin import _poll_succeeded


@pytest.fixture(params=[False, True], ids=["same-filesystem", "split-filesystem"])
def roots(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[RepositoryRoots]:
    with tempfile.TemporaryDirectory(prefix="gateway-rs-roots-", dir="/dev/shm") as temp:
        secondary = Path(temp)
        if request.param:
            assert tmp_path.stat().st_dev != secondary.stat().st_dev
            yield RepositoryRoots(secondary / "repository", secondary / "artifacts",
                tmp_path / "metadata", tmp_path / "scratch")
        else:
            yield RepositoryRoots.under(tmp_path)


def _settings(roots: RepositoryRoots) -> RepositoryServiceSettings:
    return RepositoryServiceSettings(profile="test", bearer_token="test-bearer-token", roots=roots,
        min_free_disk_bytes=1, min_free_disk_fraction=0.000001, max_import_workers=1)


def _check(layout_file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "gateway_repository_service.snapshot_admin",
        "check", "--storage-layout-file", str(layout_file)],
        check=False, capture_output=True, text=True, timeout=30)


@pytest.mark.integration
@pytest.mark.serial
def test_create_upload_import_restart_and_admin_use_the_owned_roots(roots: RepositoryRoots) -> None:
    settings = _settings(roots)
    with TestClient(create_app(settings)) as client:
        runtime = cast(ServiceRuntime, cast(FastAPI, client.app).state.runtime)
        created = client.post("/v1/repositories", headers={
            "Authorization": "Bearer test-bearer-token", "Idempotency-Key": "roots-create"})
        assert created.status_code == 201, created.text
        repository_id = UUID(created.json()["repository_id"])
        initial = created.json()["initial_commit_id"]
        layout = runtime.layout
        assert layout.published_repository(repository_id.hex).is_relative_to(roots.repository)
        assert not list(layout.staging_versioned.iterdir())
        assert runtime.control_store.path == settings.control_db_path
        assert settings.control_db_path.is_relative_to(roots.metadata)
        assert runtime.dolt_runner.server_root == roots.metadata
        assert runtime.dolt_runner.home.is_relative_to(roots.metadata)
        assert runtime.dolt_runner.tmpdir.is_relative_to(roots.scratch)
        config = json.loads((runtime.dolt_runner.home / ".dolt/config_global.json").read_text())
        assert config["versioncheck.disabled"] == "true"
        payload = build_package_bytes(manifest={"package_version": 1,
            "canonicalization_manifest_digest": "manifest-digest-1",
            "tables": [{"name": "records", "schema": {"columns": [
                {"name": "id", "sql_type": "BIGINT", "nullable": False}], "primary_key": ["id"]},
                "row_count": 1}]}, replay_sql=b"CREATE TABLE records (id BIGINT NOT NULL PRIMARY KEY);\nINSERT INTO records VALUES (1);\n")
        uploaded = client.post(f"/v1/repositories/{repository_id}/artifacts",
            headers=upload_headers(idempotency_key="roots-upload", payload=payload), content=payload)
        assert uploaded.status_code == 201, uploaded.text
        artifact_id = UUID(uploaded.json()["artifact_ref"]["artifact_id"])
        ready = artifact_ready_path(layout, repository_id, artifact_id)
        assert ready.is_relative_to(roots.artifacts)
        assert ready.read_bytes() == payload
        submitted = client.post(f"/v1/repositories/{repository_id}/versioned/imports",
            headers=import_headers(idempotency_key="roots-import"), json={
                "repository_id": str(repository_id), "artifact_ref": uploaded.json()["artifact_ref"],
                "target_ref": "main", "expected_commit_id": initial,
                "verification_policy": "STRUCTURAL", "unknown_type_policy": "REJECT"})
        assert submitted.status_code == 202, submitted.text
        succeeded = _poll_succeeded(client, repository_id, submitted.json()["operation_id"])
        commit_id = succeeded["result"]["commit_id"]
        deadline = time.monotonic() + 5
        while ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not ready.exists()
        lifecycle = runtime.mutation_store.get_artifact_lifecycle(artifact_id)
        assert lifecycle is not None and lifecycle.bytes_deleted_at is not None
        assert not list(layout.staging_artifacts.glob("import-*"))
        ref = client.get(f"/v1/repositories/{repository_id}/versioned/refs/main",
            headers={"Authorization": "Bearer test-bearer-token"})
        assert ref.status_code == 200 and ref.json()["commit_id"] == commit_id
    layout_file = write_storage_layout(roots)
    checked = _check(layout_file)
    assert checked.returncode == 0, checked.stderr
    assert json.loads(checked.stdout)["repository_count"] == 1
    with TestClient(create_app(settings)) as client:
        assert client.get("/readyz").status_code == 200
        replay = client.post("/v1/repositories", headers={
            "Authorization": "Bearer test-bearer-token", "Idempotency-Key": "roots-create"})
        assert replay.status_code == 201 and replay.json() == created.json()


@pytest.mark.integration
@pytest.mark.serial
def test_effect_recovery_rebuilds_scratch_and_preserves_published_commit(roots: RepositoryRoots) -> None:
    settings, repository_id, artifact_id, operation_id, expected = seed_queued_dolt_import(
        roots.metadata.parent / "seed", key="roots-recovery", roots=roots)
    crashed = crash_import_subprocess(settings, repository_id=repository_id,
        operation_id=operation_id, fault_point=ImportWorkerFaultPoint.AFTER_MAIN_PUBLISH_BEFORE_SUCCEEDED.value)
    assert_crash_exit(crashed)
    layout = DurableLayout.bind_existing(roots)
    ready = artifact_ready_path(layout, repository_id, artifact_id)
    assert ready.is_file()
    shutil.rmtree(roots.scratch)
    # All of this root is derived. Runtime recreates only its known namespaces;
    # authoritative commit/package/control state comes from the other roots.
    runtime = ServiceRuntime.start(settings)
    try:
        operation = runtime.import_store.get_operation(repository_id, operation_id)
        assert operation is not None and operation.status is OperationStatus.SUCCEEDED
        assert operation.result is not None and operation.result.expected_commit_id == expected
        assert not ready.exists()
        assert roots.scratch.is_dir()
    finally:
        runtime.shutdown()
    checked = _check(write_storage_layout(roots))
    assert checked.returncode == 0, checked.stderr


def test_import_capacity_rejects_the_extraction_filesystem(roots: RepositoryRoots, monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    from types import SimpleNamespace
    from gateway_repository_service import capacity

    layout = DurableLayout.create_service(roots)
    settings = _settings(roots)
    native = os.statvfs
    observed: list[Path] = []

    def measured(path: Path) -> os.statvfs_result:
        observed.append(path)
        device = path.stat().st_dev
        if device == roots.scratch.stat().st_dev:
            values = native(path)
            return cast(os.statvfs_result, SimpleNamespace(f_frsize=1, f_bavail=1,
                f_blocks=values.f_blocks, f_files=1000, f_favail=1000))
        return native(path)

    monkeypatch.setattr(capacity.os, "statvfs", measured)
    with pytest.raises(CapacityAdmissionError, match="below import"):
        assert_import_layout_admission(layout, settings)
    assert len(observed) == len({path.stat().st_dev for path in roots.paths()})
