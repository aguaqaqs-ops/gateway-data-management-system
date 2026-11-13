"""Read the immutable Preview owned by a Submission under current review scope."""
from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol
from dataclasses import dataclass

from gateway_backend.application.checkpoints import ReadyClosureDocument
from gateway_backend.application.submission.accept_transaction import deterministic_submit_operation_id
from gateway_backend.application.submission.job_payload import SUBMIT_JOB_KIND
from gateway_backend.operations import BusinessReference
from gateway_backend.operations.store import RecordNotFound
from gateway_backend.application.comparison_audit import ComparisonStructureAudit
from gateway_backend.application.submission.ports import ReviewApplyControlUnitOfWorkFactory
from gateway_backend.application.submission.review import (
    assert_fresh_scope_matches, assert_review_permission, load_review_scope_facts,
    resolve_fresh_provisioned_scope,
)
from gateway_backend.artifacts.bounded_store import BoundedArtifactStorePort
from gateway_backend.artifacts.bundle_download import BundleIntegrityError
from gateway_backend.artifacts.store import ArtifactUnavailableError
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.bundle_assembly import read_bundle_transport_metadata
from gateway_backend.capabilities.bundle_assembly.contracts import MAX_BUNDLE_MANIFEST_JSON_BYTES
from gateway_backend.domain.submission.models import Submission
from gateway_backend.domain.workspace.models import IdentityContext, PreviewResult
from gateway_backend.domain.workspace.ports import ScopeResolutionPort


class ArtifactLookup(Protocol):
    def lookup_ref(self, artifact_id: str) -> ArtifactRef | None: ...


def _read_metadata(store: BoundedArtifactStorePort, ref: ArtifactRef) -> bytes:
    if ref.size_bytes > MAX_BUNDLE_MANIFEST_JSON_BYTES:
        raise BundleIntegrityError("review metadata exceeds its JSON budget")
    return b"".join(_read_chunks(store, ref))


def _read_chunks(store: BoundedArtifactStorePort, ref: ArtifactRef) -> Iterator[bytes]:
    chunks = store.read_exact(ref)
    try:
        yield from chunks
    finally:
        close = getattr(chunks, "close", None)
        if close is not None:
            close()


def load_preview_review_closure(
    preview: PreviewResult, *, lookup: ArtifactLookup, store: BoundedArtifactStorePort,
) -> tuple[ArtifactRef, ...]:
    """Verify exact READY/bundle/pair/audit identities without current global rules."""
    expected_pair_ids = (("baseline_to_initial", "initial_to_modified")
        if preview.canonical.configuration_facts.initial_origin == "UPLOADED"
        else ("initial_to_modified",))
    if (tuple(pair.pair_id for pair in preview.comparison_pairs) != expected_pair_ids
            or tuple(pair.pair_id for pair in preview.identity_pairs) != expected_pair_ids):
        raise BundleIntegrityError("Preview pair count does not match its input mode")
    current_pair = preview.comparison_pairs[-1]
    if (current_pair.current_snapshot_digest != preview.digests.snapshot_digest
            or current_pair.comparison_digest != preview.digests.comparison_digest
            or (current_pair.risk_digest is not None and current_pair.risk_digest != preview.digests.risk_digest)
            or len({pair.ruleset_digest for pair in preview.comparison_pairs}) != 1):
        raise BundleIntegrityError("Preview comparison input binding mismatch")
    ready_ref = lookup.lookup_ref(preview.ready_closure_artifact_id)
    if ready_ref is None:
        raise ArtifactUnavailableError("preview READY closure is unavailable")
    ready = ReadyClosureDocument.from_canonical_bytes(_read_metadata(store, ready_ref))
    if ready.job_contract_version != preview.contract_version:
        raise BundleIntegrityError("Preview READY contract binding mismatch")
    refs = ready.artifact_refs()
    by_id = {ref.artifact_id: ref for ref in refs}
    manifest_ref = by_id.get(preview.bundle_artifact_id)
    if manifest_ref is None:
        raise BundleIntegrityError("Preview bundle is outside its READY closure")
    metadata = read_bundle_transport_metadata(_read_metadata(store, manifest_ref))
    if metadata.bundle_digest != preview.digests.bundle_digest:
        raise BundleIntegrityError("Preview bundle digest binding mismatch")
    expected_pairs = tuple((pair.pair_id, pair.surface_digest, pair.comparison_digest)
        for pair in preview.comparison_pairs)
    expected_risks = tuple((pair.pair_id, pair.risk_digest) for pair in preview.comparison_pairs)
    if metadata.pair_digests != expected_pairs or metadata.pair_risk_digests != expected_risks:
        raise BundleIntegrityError("Preview bundle pair binding mismatch")
    expected_refs = (metadata.closure_ref, *(entry.artifact_ref for entry in metadata.entries))
    if any(by_id.get(ref.artifact_id) != ref for ref in expected_refs):
        raise BundleIntegrityError("Preview READY closure does not cover its exact bundle closure")
    if _read_metadata(store, metadata.closure_ref) != metadata.expected_closure_bytes:
        raise BundleIntegrityError("Preview bundle closure binding mismatch")
    for pair in preview.comparison_pairs:
        if pair.structure_audit_artifact_id is None:
            continue
        audit_ref = by_id.get(pair.structure_audit_artifact_id)
        if audit_ref is None:
            raise BundleIntegrityError("Preview structure audit is outside its READY closure")
        audit = ComparisonStructureAudit.model_validate_json(_read_metadata(store, audit_ref))
        if (audit.pair_id, audit.comparison_digest, audit.before_snapshot_digest,
                audit.current_snapshot_digest, audit.ruleset_digest) != (
                pair.pair_id, pair.comparison_digest, pair.before_snapshot_digest,
                pair.current_snapshot_digest, pair.ruleset_digest) or not audit.tables:
            raise BundleIntegrityError("Preview structure audit binding mismatch")
    # Verify the complete backend closure, including canonical inputs and audits.
    # Payload files are consumed as bounded chunks, never joined into metadata.
    for ref in refs:
        for _chunk in _read_chunks(store, ref):
            pass
    return (ready_ref, *refs)


def assert_submission_preview_binding(submission: Submission, preview: PreviewResult) -> None:
    if (preview.preview_result_id != submission.preview_result_id
            or preview.workspace_id != submission.workspace_id
            or preview.repository_id != submission.repository_id
            or preview.upload_revision_id != submission.upload_revision_id
            or preview.generation != submission.workspace_generation
            or preview.business_baseline_node_id != submission.based_on_baseline_node_id
            or preview.business_baseline_commit_id != submission.business_baseline_commit_id
            or preview.canonical.configuration_facts != submission.configuration_facts
            or preview.canonical.modified_canonical_state_digest.value != submission.canonical_business_digest):
        raise BundleIntegrityError("Submission Preview binding mismatch")


@dataclass(frozen=True, slots=True)
class SubmissionPreviewRead:
    preview: PreviewResult
    ready_ref: ArtifactRef
    protected_artifact_ids: frozenset[str]


def read_submission_preview(
    *, context: IdentityContext, submission_id: str,
    scope_resolution: ScopeResolutionPort,
    unit_of_work_factory: ReviewApplyControlUnitOfWorkFactory,
) -> SubmissionPreviewRead:
    # Resolve/authorize the durable scalar target before decoding any result.
    assert_review_permission(context)
    resolved = scope_resolution.resolve(context)
    with unit_of_work_factory(read_only=True) as unit_of_work:
        fresh = resolve_fresh_provisioned_scope(unit_of_work, context)
        assert_fresh_scope_matches(fresh, resolved)
        facts = load_review_scope_facts(unit_of_work, context=context,
            submission_id=submission_id, resolved_scope=fresh)
        try:
            preview = unit_of_work.workspace.get_preview_result(facts.submission.preview_result_id,
                workspace_id=facts.submission.workspace_id, repository_id=fresh.repository_id)
        except (ValueError, TypeError, KeyError) as exc:
            raise BundleIntegrityError("Submission Preview facts are invalid") from exc
        if preview is None:
            raise ArtifactUnavailableError("Submission Preview is unavailable")
        assert_submission_preview_binding(facts.submission, preview)
        attempt = unit_of_work.submission.get_submit_attempt(facts.submission.submit_attempt_id,
            workspace_id=facts.submission.workspace_id, repository_id=fresh.repository_id)
        if (attempt is None or attempt.preview_result_id != preview.preview_result_id
                or attempt.submission_id != submission_id
                or attempt.preview_ready_closure_ref != preview.ready_closure_artifact_id
                or attempt.preview_ready_closure_digest != "v1:" + preview.ready_closure_artifact_id
                or attempt.configuration_facts != preview.canonical.configuration_facts
                or attempt.snapshot_digest != preview.digests.snapshot_digest):
            raise BundleIntegrityError("Submission accepted Preview binding mismatch")
        if attempt.operation_id != deterministic_submit_operation_id(
                workspace_id=attempt.workspace_id, idempotency_key=attempt.accept_idempotency_key):
            raise BundleIntegrityError("Submission operation binding mismatch")
        try:
            operation = unit_of_work.operations.get_operation(attempt.operation_id)
        except RecordNotFound as exc:
            raise ArtifactUnavailableError("Submission operation is unavailable") from exc
        if operation.job_kind != SUBMIT_JOB_KIND or operation.business_refs != (
                BusinessReference(kind="workspace", value=attempt.workspace_id),
                BusinessReference(kind="submit_attempt", value=attempt.submit_attempt_id)):
            raise BundleIntegrityError("Submission operation scope mismatch")
        refs = operation.artifact_refs
        held = unit_of_work.list_artifact_protection_for_owner(
            owner_kind="submission-review", owner_id=submission_id)
        ready_ref = next((ref for ref in refs if ref.artifact_id == preview.ready_closure_artifact_id), None)
        if ready_ref is None or ready_ref.artifact_id not in held:
            raise BundleIntegrityError("Submission review protection is incomplete")
        return SubmissionPreviewRead(preview, ready_ref, held)
