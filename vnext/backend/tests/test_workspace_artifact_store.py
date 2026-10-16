"""Bounded artifact store publication, protection and cleanup tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from gateway_shared_kernel import raw_blob_digest

from gateway_backend.artifacts.bounded_store import CleanupClassification, DeleteDisposition
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.artifacts.types import validate_artifact_id
from gateway_backend.infrastructure.artifact_store import (
    BoundedArtifactStore,
    LocalArtifactStore,
    SQLiteArtifactProtectionStore,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, initialize_control_db

pytestmark = pytest.mark.unit

PAYLOAD = b"upload-package-bytes"
DIGEST = raw_blob_digest(PAYLOAD)
NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "control.db"
    initialize_control_db(path)
    return path


def test_put_stream_publishes_exact_ref_and_verifies_read_back(tmp_path: Path) -> None:
    store = BoundedArtifactStore(LocalArtifactStore(tmp_path / "artifacts"))
    ref = store.put_stream(
        "source-package",
        [PAYLOAD],
        declared_size=len(PAYLOAD),
        declared_raw_sha256=DIGEST,
        media_type="application/gzip",
    )
    verification = store.verify_readable(
        ref,
        expected_size=len(PAYLOAD),
        expected_raw_sha256=DIGEST,
    )
    assert verification.verified is True
    assert store.get_ref(ref.artifact_id) == ref
    assert b"".join(store.read_exact(ref)) == PAYLOAD


def test_ref_lookup_rejects_an_unknown_artifact_id(tmp_path: Path) -> None:
    store = BoundedArtifactStore(LocalArtifactStore(tmp_path / "artifacts"))

    with pytest.raises(ManifestVerificationError, match="unknown artifact_id"):
        store.get_ref("missing-artifact")


def test_put_stream_rejects_digest_mismatch(tmp_path: Path) -> None:
    store = BoundedArtifactStore(LocalArtifactStore(tmp_path / "artifacts"))
    with pytest.raises(ManifestVerificationError, match="declared_raw_sha256 mismatch"):
        store.put_stream(
            "source-package",
            [PAYLOAD],
            declared_size=len(PAYLOAD),
            declared_raw_sha256=raw_blob_digest(b"other"),
            media_type="application/gzip",
        )


def test_path_shaped_artifact_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="artifact_id"):
        validate_artifact_id("/etc/passwd")


def test_protected_artifact_refuses_delete(db_path: Path, tmp_path: Path) -> None:
    local = LocalArtifactStore(tmp_path / "artifacts")
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        protection = SQLiteArtifactProtectionStore(unit_of_work.connection)
        store = BoundedArtifactStore(local, protection_store=protection)
        ref = store.put_stream(
            "source-package",
            [PAYLOAD],
            declared_size=len(PAYLOAD),
            declared_raw_sha256=DIGEST,
            media_type="application/gzip",
        )
        store.set_protection(
            [ref],
            owner_kind="upload_revision",
            owner_id="ur-1",
            intent="pin",
            recorded_at=NOW,
        )
        assert store.classify_cleanup(ref, NOW).classification is CleanupClassification.PROTECTED

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        protection = SQLiteArtifactProtectionStore(unit_of_work.connection)
        store = BoundedArtifactStore(local, protection_store=protection)
        assert (
            store.delete_eligible(
                ref,
                expected_classification=CleanupClassification.ELIGIBLE_AFTER,
                now=NOW + timedelta(hours=48),
            )
            is DeleteDisposition.RETRYABLE_FAILURE
        )


PROTECTION_CLEANUP_CASES = (
    (timedelta(hours=1), CleanupClassification.MANUAL_REVIEW),
    (timedelta(hours=25), CleanupClassification.ELIGIBLE_AFTER),
)


@pytest.mark.parametrize(("age", "expected"), PROTECTION_CLEANUP_CASES)
def test_unpinned_artifact_becomes_eligible_after_ttl(
    tmp_path: Path,
    age: timedelta,
    expected: CleanupClassification,
) -> None:
    store = BoundedArtifactStore(
        LocalArtifactStore(tmp_path / "artifacts"),
        unpinned_ttl=timedelta(hours=24),
    )
    ref = store.put_stream(
        "source-package",
        [PAYLOAD],
        declared_size=len(PAYLOAD),
        declared_raw_sha256=DIGEST,
        media_type="application/gzip",
    )
    store._published_at_by_artifact_id[ref.artifact_id] = NOW  # noqa: SLF001
    decision = store.classify_cleanup(ref, NOW + age)
    assert decision.classification is expected


def test_delete_eligible_removes_unpinned_artifact_after_ttl(tmp_path: Path) -> None:
    store = BoundedArtifactStore(
        LocalArtifactStore(tmp_path / "artifacts"),
        unpinned_ttl=timedelta(hours=24),
    )
    ref = store.put_stream(
        "source-package",
        [PAYLOAD],
        declared_size=len(PAYLOAD),
        declared_raw_sha256=DIGEST,
        media_type="application/gzip",
    )
    store._published_at_by_artifact_id[ref.artifact_id] = NOW  # noqa: SLF001
    later = NOW + timedelta(hours=25)
    assert (
        store.delete_eligible(
            ref,
            expected_classification=CleanupClassification.ELIGIBLE_AFTER,
            now=later,
        )
        is DeleteDisposition.DELETED
    )
    with pytest.raises(ManifestVerificationError):
        store._local_store.locate(ref)  # noqa: SLF001


def test_clear_protection_releases_only_when_no_remaining_owner(
    db_path: Path,
    tmp_path: Path,
) -> None:
    local = LocalArtifactStore(tmp_path / "artifacts")
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        store = BoundedArtifactStore(local, protection_store=unit_of_work.protection)
        ref = store.put_stream(
            "source-package",
            [PAYLOAD],
            declared_size=len(PAYLOAD),
            declared_raw_sha256=DIGEST,
            media_type="application/gzip",
        )
        store.set_protection(
            [ref],
            owner_kind="preview-checkpoint",
            owner_id="step-1",
            intent="pin",
            recorded_at=NOW,
        )
        store.set_protection(
            [ref],
            owner_kind="current-preview",
            owner_id="ws-1",
            intent="pin",
            recorded_at=NOW,
        )
        assert store.classify_cleanup(ref, NOW).classification is CleanupClassification.PROTECTED
        unit_of_work.protection.clear_protection(
            owner_kind="preview-checkpoint",
            owner_id="step-1",
        )
        assert store.classify_cleanup(ref, NOW).classification is CleanupClassification.PROTECTED
        unit_of_work.protection.clear_protection(
            owner_kind="current-preview",
            owner_id="ws-1",
        )
        store._published_at_by_artifact_id[ref.artifact_id] = NOW  # noqa: SLF001
        later = NOW + timedelta(hours=25)
        assert store.classify_cleanup(ref, later).classification is CleanupClassification.ELIGIBLE_AFTER
