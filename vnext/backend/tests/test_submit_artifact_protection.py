"""Prepare-import artifact pin protection tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway_backend.application.submission.import_builder import pin_prepare_import_artifacts
from gateway_backend.domain.submission.models import BackendArtifactRef
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, initialize_control_db
from tests.test_submit_transactions import seed_submit_ready_workspace

pytestmark = pytest.mark.unit

_SHA_PACKAGE = "sha256:" + "05" * 32
_SHA_MANIFEST = "sha256:" + "06" * 32


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "control.db"
    initialize_control_db(path)
    return path


def test_pin_prepare_import_artifacts_extends_attempt_protection(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    manifest_ref = BackendArtifactRef(
        artifact_id="manifest-1",
        media_type="application/vnd.gateway.canonicalization-manifest+json",
        size_bytes=12,
        raw_sha256=_SHA_MANIFEST,
    )
    package_ref = BackendArtifactRef(
        artifact_id="backend-pkg-1",
        media_type="application/vnd.gateway.repository-import.v1+tar+zstd",
        size_bytes=10,
        raw_sha256=_SHA_PACKAGE,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        pin_prepare_import_artifacts(
            unit_of_work,
            submit_attempt_id="sa-1",
            manifest_ref=manifest_ref,
            package_ref=package_ref,
            existing_snapshot_refs=seed.protected_refs,
        )
        held = unit_of_work.list_artifact_protection_for_owner(
            owner_kind="submit-attempt",
            owner_id="sa-1",
        )
        assert held == frozenset(
            {ref.artifact_id for ref in seed.protected_refs} | {"manifest-1", "backend-pkg-1"}
        )
