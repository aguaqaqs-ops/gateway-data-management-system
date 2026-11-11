"""Non-null presentation artifacts survive recovery and obey READY protection."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import gateway_backend.application.preview_jobs as preview
from gateway_backend.application.bundle_download import prepare_bundle_download
from gateway_backend.application.checkpoints import load_checkpoint_envelope, load_ready_closure
from gateway_backend.application.recovery import RecoveryOutcomeDisposition
from gateway_backend.artifacts import ArtifactRef, artifact_ref_from_dict
from gateway_backend.artifacts.bounded_store import CleanupClassification, DeleteDisposition
from gateway_backend.artifacts.bundle_download import BundleIntegrityError
from gateway_backend.artifacts.location import ArtifactLocation, parse_artifact_id
from gateway_backend.infrastructure.artifact_store import BoundedArtifactStore
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.operations import OperationStatus
from tests.support.artifact_layout import open_test_store
from tests.support.preview_job_harness import (
    build_preview_harness, claim_next_step, insert_preview_operation, run_claimed_handler,
)
from tests.test_bundle_download import assert_complete_tar


@pytest.mark.parametrize("cancel", (False, True))
def test_actual_presentation_refs_recover_from_disk_transfer_or_release_protection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cancel: bool,
) -> None:
    harness = build_preview_harness(tmp_path / "job")
    harness.seed_workspace()
    local = open_test_store(tmp_path / "objects")
    store = BoundedArtifactStore(local, protection_uow=lambda: ControlDbUnitOfWork(harness.db_path),
        unpinned_ttl=timedelta(0))
    for ref, raw in harness.artifact_store._artifacts.values():
        store.put(raw, ref)
    deps = replace(harness.deps, artifact_store=store)
    _, handlers, _ = preview.preview_composition_bundle(deps)
    harness.handlers = dict(handlers)
    operation_refs: set[ArtifactRef] = set()
    original_pair = preview._run_pair_pipeline
    def capture(*args: Any, **kwargs: Any) -> Any:
        result = original_pair(*args, **kwargs)
        surface = result.surface_result.surface
        assert surface is not None
        operation_refs.update(p.projection_ref for p in surface.projections)
        operation_refs.update(t.row_locator_ref for t in surface.tables if t.row_locator_ref is not None)
        return result
    monkeypatch.setattr(preview, "_run_pair_pipeline", capture)
    operation_id = "presentation-lifecycle"
    insert_preview_operation(harness, operation_id)
    for handler in (preview.PREVIEW_MATERIALIZE_HANDLER, preview.PREVIEW_ASSEMBLE_HANDLER):
        session, control, operation, step = claim_next_step(harness)
        run_claimed_handler(harness, handler, session, control, operation, step)
    assert len(operation_refs) >= 2
    assert all(parse_artifact_id(ref.artifact_id) is ArtifactLocation.COMPARISON for ref in operation_refs)
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as uow:
        assembled_step = uow.operations.get_step(operation_id + "-step-2")
    assert assembled_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(store, assembled_step.checkpoint_ref)
    ready_ref = artifact_ref_from_dict(envelope.job_state["ready_closure_ref"])
    ready = load_ready_closure(store, ready_ref)
    manifest_ref = local.get_ref(str(envelope.job_state["bundle_artifact_id"]))
    manifest = json.loads(store.locate(manifest_ref))
    entries = [e for e in manifest["closure_entries"] if e["kind"] in {"PROJECTION", "ROW_LOCATOR"}]
    assert {e["kind"] for e in entries} == {"PROJECTION", "ROW_LOCATOR"}
    bundle_refs = {artifact_ref_from_dict(e["artifact_ref"]) for e in entries}
    assert all(parse_artifact_id(ref.artifact_id) is ArtifactLocation.EXPORT for ref in bundle_refs)
    refs = operation_refs | bundle_refs
    assert refs <= set(ready.artifact_refs())
    after_ttl = datetime.now(UTC) + timedelta(days=2)
    for ref in refs:
        assert store.classify_cleanup(ref, after_ttl).classification is CleanupClassification.PROTECTED
        assert store.delete_eligible(ref, expected_classification=CleanupClassification.ELIGIBLE_AFTER,
            now=after_ttl) is DeleteDisposition.RETRYABLE_FAILURE

    # A new store/composition can publish entirely from the persisted READY
    # closure. Native comparison and navigation are forbidden during recovery.
    reopened_local = open_test_store(tmp_path / "objects")
    reopened = BoundedArtifactStore(reopened_local, protection_uow=lambda: ControlDbUnitOfWork(harness.db_path),
        unpinned_ttl=timedelta(0))
    def forbid_recompute(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("publish recovery must consume the closed presentation artifacts")
    monkeypatch.setattr(preview, "_run_pair_pipeline", forbid_recompute)
    recovery = preview.build_preview_recovery_port(replace(deps, artifact_store=reopened))
    session, control, operation, step = claim_next_step(harness)
    if cancel:
        control.request_cancel()
    outcome = recovery.recover(operation, step, control, session)
    assert outcome.disposition is RecoveryOutcomeDisposition.PUBLISHED
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as uow:
        persisted = uow.operations.get_operation(operation_id)
        assert persisted.status is (OperationStatus.CANCELLED if cancel else OperationStatus.SUCCEEDED)
        if not cancel:
            for ref in refs:
                owners = uow.connection.execute("SELECT owner_kind FROM artifact_protection_intents WHERE artifact_id=?",
                    (ref.artifact_id,)).fetchall()
                assert "current-preview" in {row[0] for row in owners}
                assert "preview-checkpoint" not in {row[0] for row in owners}
    if cancel:
        for ref in refs:
            assert reopened.classify_cleanup(ref, after_ttl).classification is CleanupClassification.ELIGIBLE_AFTER
            assert reopened.delete_eligible(ref, expected_classification=CleanupClassification.ELIGIBLE_AFTER,
                now=after_ttl) is DeleteDisposition.DELETED
        return
    prepared = prepare_bundle_download(reopened, manifest_ref.artifact_id)
    try:
        tar_bytes = b"".join(prepared.stream)
    finally:
        prepared.close()
    downloaded = assert_complete_tar(tar_bytes)
    assert downloaded["bundle_digest"] == manifest["bundle_digest"]
    for ref in refs:
        assert reopened.classify_cleanup(ref, after_ttl).classification is CleanupClassification.PROTECTED
    for kind in ("PROJECTION", "ROW_LOCATOR"):
        ref = artifact_ref_from_dict(next(e["artifact_ref"] for e in entries if e["kind"] == kind))
        path = reopened_local.payload_path(ref.artifact_id)
        original = path.read_bytes()
        path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
        try:
            with pytest.raises(BundleIntegrityError):
                prepare_bundle_download(reopened, manifest_ref.artifact_id)
        finally:
            path.write_bytes(original)
