"""One Preview/accept barrier: hidden business change still saves canonical data."""
from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from gateway_backend.application import preview_jobs
from gateway_backend.application.pair_pipeline import run_preview_pair_pipeline
from gateway_backend.application.checkpoints import load_ready_closure
from gateway_backend.application.comparison_audit import ComparisonStructureAudit
from gateway_backend.application.submission.accept_transaction import accept_submit_transaction
from gateway_backend.application.submission.contracts import AcceptSubmitCommand
from gateway_backend.application.submit_registry import submit_job_registry
from gateway_backend.application.workspace.preview import build_preview_job_payload
from gateway_backend.artifacts.bounded_store import BoundedArtifactStorePort
from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
from gateway_backend.domain.workspace.models import InputCompleteness
from gateway_backend.http.dependencies import ArtifactRefLookupPort
from gateway_backend.http.orchestration.submit_acceptance import load_accept_submit_preflight
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from tests.support.baseline_fixtures import seed_provisioned_mapping_with_head
from tests.support.preview_job_harness import (
    BASELINE_HEAD, IDEMPOTENCY_KEY, REPOSITORY_ID, build_preview_harness,
    build_upload_revision, store_source_package,
)
from tests.support.table_rules import _runtime_comparison_ruleset_digest
from tests.support.workspace_fixtures import FixedScopeResolutionPort, make_identity
from tests.test_preview_job_assemble import (
    _HarnessArtifactRefLookup, _HarnessBoundedArtifactStore, _run_through_publish,
)
from tests.test_submit_transactions import RecordingMainResolvePort

pytestmark = [pytest.mark.unit, pytest.mark.integration]


def test_hidden_schema_preview_preserves_ready_audit_and_accepts_canonical_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = build_preview_harness(tmp_path, input_completeness=InputCompleteness.MODIFIED_ONLY, include_identity_table=True)
    modified = store_source_package(harness.artifact_store,
        b"CREATE TABLE t(id INT NOT NULL PRIMARY KEY,note TEXT); INSERT INTO t VALUES(1,'new');"
        b"CREATE TABLE version_manager (`project_id` VARCHAR(32)); INSERT INTO version_manager VALUES ('project-a');",
        artifact_id=build_artifact_id(ArtifactLocation.DURABLE, "test-structure-input", "modified"))
    harness.upload_revision = build_upload_revision(input_completeness=InputCompleteness.MODIFIED_ONLY,
        initial_binding=None, modified_binding=modified, generation=harness.upload_revision.generation)
    harness.job_payload = build_preview_job_payload(workspace_id=harness.upload_revision.workspace_id,
        upload_revision=harness.upload_revision, repository_id=REPOSITORY_ID,
        business_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        business_baseline_commit_id=BASELINE_HEAD.business_baseline_commit_id,
        baseline_head_version=BASELINE_HEAD.baseline_head_version, idempotency_key=IDEMPOTENCY_KEY,
        comparison_ruleset_digest=_runtime_comparison_ruleset_digest())
    seed_provisioned_mapping_with_head(harness.db_path, repository_id=REPOSITORY_ID, baseline_head=BASELINE_HEAD)
    pairs = []
    original = run_preview_pair_pipeline
    def capture(**kwargs: Any) -> Any:
        pair = original(**kwargs)
        pairs.append(pair)
        return pair
    monkeypatch.setattr(preview_jobs, "run_preview_pair_pipeline", capture)
    _run_through_publish(harness, "op-hidden-schema")
    assert len(pairs) == 1 and pairs[0].structure_audit_ref is not None
    surface = pairs[0].surface_result.surface
    assert surface is not None and surface.summary.changed_table_count == 0
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as uow:
        workspace = uow.workspace.get_workspace(harness.upload_revision.workspace_id)
        assert workspace is not None and workspace.current_preview_result_id is not None
        preview = uow.workspace.get_preview_result(workspace.current_preview_result_id)
        assert preview is not None and preview.canonical is not None
        assert preview.canonical.baseline_canonical_state_digest != preview.canonical.modified_canonical_state_digest
    ready = load_ready_closure(harness.artifact_store, harness.artifact_store.get_ref(preview.ready_closure_artifact_id))
    assert pairs[0].structure_audit_ref in ready.artifact_refs()
    audit = ComparisonStructureAudit.model_validate_json(harness.artifact_store.locate(pairs[0].structure_audit_ref))
    assert audit.pair_id == pairs[0].pair_id
    command = AcceptSubmitCommand(context=make_identity(actor_id=workspace.owner_actor_id,
        device_key=workspace.gateway_device_external_key, project_id=workspace.business_project_id,
        permissions=frozenset({"upload_submit_workspace", "workspace_read"})), workspace_id=workspace.workspace_id,
        expected_workspace_version=workspace.optimistic_version, upload_revision_id=harness.upload_revision.upload_revision_id,
        preview_result_id=preview.preview_result_id, generation=preview.generation,
        expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        expected_baseline_head_version=BASELINE_HEAD.baseline_head_version, idempotency_key="hidden-schema-submit", options={})
    def uow_factory(*, read_only: bool = False) -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(harness.db_path, read_only=read_only)
    preflight = load_accept_submit_preflight(command=command, unit_of_work_factory=uow_factory,
        preview_result=preview, upload_revision=harness.upload_revision,
        artifact_ref_lookup=cast(ArtifactRefLookupPort, _HarnessArtifactRefLookup(harness.artifact_store)),
        artifact_store=cast(BoundedArtifactStorePort, _HarnessBoundedArtifactStore(harness.artifact_store)),
        current_storage_projection_ruleset_digest=_runtime_comparison_ruleset_digest())
    accepted = accept_submit_transaction(command=command,
        scope_resolution=FixedScopeResolutionPort(repository_id=REPOSITORY_ID, baseline_head=BASELINE_HEAD),
        unit_of_work_factory=uow_factory, job_registry=submit_job_registry(), main_resolve=RecordingMainResolvePort(),
        preflight=preflight, now=harness.upload_revision.created_at)
    assert not accepted.replay
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM submit_attempt_records").fetchone()[0] == 1
