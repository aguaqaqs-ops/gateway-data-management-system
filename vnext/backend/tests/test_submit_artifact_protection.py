"""Preview-to-attempt transfer and terminal artifact pin release tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from gateway_backend.application.submission.accept_transaction import accept_submit_transaction
from gateway_backend.application.submission.import_builder import (
    clear_attempt_artifact_protection,
    promote_finalize_artifact_protection,
    transfer_preview_protection_to_attempt,
)
from gateway_backend.domain.submission.models import (
    BackendArtifactRef,
    SubmitAttemptState,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, initialize_control_db
from tests.support.workspace_fixtures import FixedScopeResolutionPort
from tests.test_submit_transactions import (
    BASELINE_HEAD,
    TS1,
    _accept_command,
    _preflight,
    _submit_job_registry,
    _uow_factory,
    FakeBaselineCanonicalDigestPort,
    RecordingMainResolvePort,
    seed_submit_ready_workspace,
)

pytestmark = pytest.mark.unit

_SHA_INITIAL = "sha256:" + "01" * 32
_SHA_MODIFIED = "sha256:" + "02" * 32
_SHA_CLOSURE = "sha256:" + "03" * 32
_SHA_SNAP = "sha256:" + "04" * 32
_SHA_PACKAGE = "sha256:" + "05" * 32
_SHA_MANIFEST = "sha256:" + "06" * 32


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "control.db"
    initialize_control_db(path)
    return path


def test_transfer_preview_protection_to_attempt_moves_exact_refs(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    protected = seed.protected_refs
    attempt_refs = tuple(
        ref for ref in protected if ref.artifact_id in {"initial-1", "modified-1", "closure-1", "snap-1"}
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        transfer_preview_protection_to_attempt(
            unit_of_work,
            workspace_id=seed.workspace.workspace_id,
            preview_operation_id=seed.preview_operation_id,
            submit_attempt_id="sa-1",
            expected_refs=protected,
            attempt_refs=attempt_refs,
        )
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="submit-attempt",
            owner_id="sa-1",
        ) == frozenset(ref.artifact_id for ref in attempt_refs)
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="current-preview",
            owner_id=seed.workspace.workspace_id,
        ) == frozenset()
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="preview-operation",
            owner_id=seed.preview_operation_id,
        ) == frozenset()


def test_accept_transaction_transfers_preview_pins_to_attempt(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    result = accept_submit_transaction(
        command=_accept_command(seed, idempotency_key="accept-key-1"),
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        baseline_digest=FakeBaselineCanonicalDigestPort(),
        main_resolve=RecordingMainResolvePort(),
        preflight=_preflight(seed),
        now=TS1,
    )
    with ControlDbUnitOfWork(seed.db_path, read_only=True) as unit_of_work:
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="submit-attempt",
            owner_id=result.submit_attempt_id,
        ) == frozenset(
            {
                "initial-1",
                "modified-1",
                "closure-1",
                "snap-1",
            }
        )
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="current-preview",
            owner_id=seed.workspace.workspace_id,
        ) == frozenset()


def test_finalize_promotes_source_and_manifest_pins(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    accepted = accept_submit_transaction(
        command=_accept_command(seed, idempotency_key="accept-key-1"),
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        baseline_digest=FakeBaselineCanonicalDigestPort(),
        main_resolve=RecordingMainResolvePort(),
        preflight=_preflight(seed),
        now=TS1,
    )
    backend_ref = BackendArtifactRef(
        artifact_id="backend-pkg-1",
        media_type="application/vnd.gateway.repository-import.v1+tar+zstd",
        size_bytes=10,
        raw_sha256=_SHA_PACKAGE,
    )
    with ControlDbUnitOfWork(seed.db_path) as unit_of_work:
        attempt = unit_of_work.submission.get_submit_attempt(accepted.submit_attempt_id)
        assert attempt is not None
        updated = replace(
            attempt,
            state=SubmitAttemptState.EFFECT_PENDING,
            canonicalization_manifest_ref="manifest-1",
            canonicalization_manifest_digest=_SHA_MANIFEST,
            repository_import_artifact_ref=backend_ref,
            optimistic_version=1,
            effect_pending_at=TS1,
        )
        unit_of_work.submission.cas_update_attempt(updated, expected_version=0)
        promote_finalize_artifact_protection(unit_of_work, attempt=updated)
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="submit-attempt",
            owner_id=accepted.submit_attempt_id,
        ) == frozenset()
        assert "initial-1" in unit_of_work.list_artifact_protection_for_owner(
            owner_kind="source-package",
            owner_id=accepted.submit_attempt_id,
        )
        assert "manifest-1" in unit_of_work.list_artifact_protection_for_owner(
            owner_kind="canonicalization-manifest",
            owner_id=accepted.submit_attempt_id,
        )


def test_abort_clears_attempt_pins_without_promotion(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    accepted = accept_submit_transaction(
        command=_accept_command(seed, idempotency_key="accept-key-1"),
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        baseline_digest=FakeBaselineCanonicalDigestPort(),
        main_resolve=RecordingMainResolvePort(),
        preflight=_preflight(seed),
        now=TS1,
    )
    with ControlDbUnitOfWork(seed.db_path) as unit_of_work:
        clear_attempt_artifact_protection(
            unit_of_work,
            submit_attempt_id=accepted.submit_attempt_id,
        )
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="submit-attempt",
            owner_id=accepted.submit_attempt_id,
        ) == frozenset()
        assert unit_of_work.list_artifact_protection_for_owner(
            owner_kind="source-package",
            owner_id=accepted.submit_attempt_id,
        ) == frozenset()
