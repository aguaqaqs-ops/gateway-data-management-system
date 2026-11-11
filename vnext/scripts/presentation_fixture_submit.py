"""Fixture-only read ports for a real AcceptSubmit NO_CANONICAL_CHANGE call.

Only control/baseline reads are substituted. The production transaction, frozen
binding guards and no-op decision execute unchanged. Any attempt to open a write
transaction or resolve Repository main fails this fixture immediately.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterator

from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_backend.application.submission.accept_transaction import AcceptSubmitPreflight, accept_submit_transaction
from gateway_backend.application.submission.contracts import AcceptSubmitCommand
from gateway_backend.application.submission.errors import NoCanonicalChange
from gateway_backend.application.submit_registry import submit_job_registry
from gateway_backend.artifacts import artifact_ref_to_dict
from gateway_backend.capabilities.snapshot_materialization.contracts import canonical_state_digest_of
from gateway_backend.domain.configuration_facts import (
    CONFIGURATION_FACTS_SCHEMA, CONFIGURATION_TIME_RULE, CanonicalContentIdentity,
    ConfigurationFacts, ConfigurationGeneratedTime, ConfigurationSideFacts,
)
from gateway_backend.domain.workspace.models import (
    BaselineHead, IdentityContext, InputCompleteness, PreviewArtifactRef,
    PreviewCanonicalBindings, PreviewIdentityPair, PreviewResult, PreviewResultDigests,
    ProjectIdentityApplicability, ProjectIdentityMode, ProjectIdentityStatus, ResolvedScope,
    SourceArtifactBinding, SourceArtifactRole, UploadRevision, Workspace, WorkspaceState,
)


def run_comment_only_submit(*, before: Any, current: Any, store: Any,
    manifest_ref: Any, closure_ref: Any, surface: Any, bundle_digest: str,
    source_ref: Any, sql_source_digest: str, repository_id: str, rules_digest: Any,
) -> dict[str, Any]:
    before_digest = canonical_state_digest_of(before.bound.summary.tables)
    current_digest = canonical_state_digest_of(current.bound.summary.tables)
    if before_digest is None or before_digest != current_digest:
        raise ValueError("comment-only fixture changed canonical business identity")
    now = datetime(2026, 11, 11, tzinfo=UTC)
    head = BaselineHead("fixture-node", "fixture-commit", 1)
    workspace = Workspace("fixture-workspace", "fixture-actor", "fixture-device", "fixture-project",
        repository_id, WorkspaceState.OPEN, 1, 1, "fixture-upload", "fixture-preview", now, now)
    upload = UploadRevision("fixture-upload", workspace.workspace_id, 1, InputCompleteness.MODIFIED_ONLY,
        {SourceArtifactRole.MODIFIED: SourceArtifactBinding(**{**artifact_ref_to_dict(source_ref),
            "raw_sha256": source_ref.raw_sha256.value})}, "fixture-upload-key", "fixture-upload-fingerprint", "fixture-actor", now)
    identity = CanonicalContentIdentity(current_digest.value, rules_digest.value, "3", 1)
    absent_time = ConfigurationGeneratedTime(CONFIGURATION_TIME_RULE, "TABLE_ABSENT", None, None,
        0, 0, 0, None, None, False)
    side = ConfigurationSideFacts(identity, absent_time, source_ref.artifact_id, sql_source_digest)
    facts = ConfigurationFacts(CONFIGURATION_FACTS_SCHEMA, "fixture-preview-operation", workspace.workspace_id,
        upload.upload_revision_id, 1, repository_id, head.business_baseline_node_id,
        head.business_baseline_commit_id, 1, False, "fixture-baseline-submission", "BASELINE_REUSED", identity, side, side)
    pair = PreviewIdentityPair("initial_to_modified", ProjectIdentityApplicability.NOT_APPLICABLE,
        ProjectIdentityStatus.NOT_APPLICABLE, ProjectIdentityMode.DETAILED, None, None)
    identity_digest = raw_blob_digest(canonicalize_json_value({"schema": "project-identity-assessment-set/v1",
        "pairs": [["initial_to_modified", "NOT_APPLICABLE", "NOT_APPLICABLE", None]]}))
    def preview_ref(ref: Any) -> PreviewArtifactRef:
        return PreviewArtifactRef(**{**artifact_ref_to_dict(ref), "raw_sha256": ref.raw_sha256})
    preview = PreviewResult("fixture-preview", workspace.workspace_id, upload.upload_revision_id, 1,
        repository_id, head.business_baseline_node_id, head.business_baseline_commit_id, 1,
        "fixture-current-rules", "fixture-current-preview", {},
        PreviewResultDigests(sql_source_digest, sql_source_digest, current.bound.snapshot.snapshot_digest.value,
            surface.comparison_digest.value, surface.risk_evaluation_digest.value, surface.surface_digest.value, bundle_digest),
        PreviewCanonicalBindings(before_digest, facts, preview_ref(closure_ref), closure_ref.raw_sha256,
            preview_ref(manifest_ref), manifest_ref.raw_sha256, before_digest, current_digest, rules_digest),
        identity_digest, (pair,), manifest_ref.artifact_id, closure_ref.artifact_id, facts.operation_id, now)

    class ReadPorts:
        def get_workspace(self, key: str) -> Workspace:
            if key != workspace.workspace_id:
                raise ValueError("unexpected workspace")
            return workspace
        def get_upload_revision(self, key: str) -> UploadRevision:
            if key != upload.upload_revision_id:
                raise ValueError("unexpected upload")
            return upload
        def get_preview_result(self, key: str, **scope: Any) -> PreviewResult:
            if key != preview.preview_result_id or scope != {"workspace_id": workspace.workspace_id, "repository_id": repository_id}:
                raise ValueError("unexpected preview scope")
            return preview
        def find_submit_idempotency(self, *_: Any) -> None:
            return None
        def get_workspace_occupancy(self, *_: Any) -> None:
            return None
        def get_repository_occupancy(self, *_: Any) -> None:
            return None
        def resolve(self, _: Any) -> ResolvedScope:
            return ResolvedScope(repository_id, head)
        def resolve_main_expected_commit(self, **_: Any) -> str:
            raise AssertionError("NO_CANONICAL_CHANGE attempted Repository main I/O")

    reads = ReadPorts()
    class UnitOfWork:
        workspace = reads
        submission = reads
    read_transactions = 0
    @contextmanager
    def uow(*, read_only: bool = False) -> Iterator[UnitOfWork]:
        nonlocal read_transactions
        if not read_only:
            raise AssertionError("NO_CANONICAL_CHANGE opened a write transaction")
        read_transactions += 1
        yield UnitOfWork()
    command = AcceptSubmitCommand(IdentityContext("fixture-actor", "fixture-device", "fixture-project",
        frozenset({"upload_submit_workspace", "workspace_read"})), workspace.workspace_id, 1,
        upload.upload_revision_id, preview.preview_result_id, 1, head.business_baseline_node_id, 1,
        "fixture-submit-key", {})
    try:
        accept_submit_transaction(command=command, scope_resolution=reads, unit_of_work_factory=uow,
            job_registry=submit_job_registry(), main_resolve=reads,
            preflight=AcceptSubmitPreflight(closure_ref.raw_sha256.value, facts.operation_id, (), rules_digest.value), now=now)
    except NoCanonicalChange as exc:
        return {"code": exc.stable_code, "owner": "accept_submit_transaction",
            "read_transactions": read_transactions, "write_transactions": 0, "repository_main_calls": 0,
            "baseline_canonical_state_digest": before_digest.value,
            "modified_canonical_state_digest": current_digest.value,
            "fixture_only_ports": ["control-read-unit-of-work", "baseline-scope"],
            "source_ref": artifact_ref_to_dict(source_ref)}
    raise AssertionError("comment-only Submit did not return NO_CANONICAL_CHANGE")
