"""T1 AcceptSubmit SQLite transaction orchestration."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime

from gateway_backend.application.job_definitions import JobDefinitionLookupError, JobDefinitionRegistry
from gateway_backend.application.submission.accept import (
    PERMISSION_UPLOAD_SUBMIT,
    try_accept_submit_replay,
    validate_accept_submit_with_frozen,
)
from gateway_backend.application.submission.contracts import (
    SUBMIT_JOB_CONTRACT_VERSION,
    AcceptSubmitCommand,
    AcceptSubmitValidationResult,
    derive_repository_import_idempotency_key,
    derive_repository_upload_idempotency_key,
)
from gateway_backend.application.submission.errors import PreviewBindingConflict
from gateway_backend.application.submission.job_payload import (
    SUBMIT_JOB_KIND,
    SUBMIT_STEP_AWAIT,
    SUBMIT_STEP_PREPARE,
    SUBMIT_STEP_SUBMIT,
    build_submit_job_payload,
)
from gateway_backend.application.submission.ports import (
    BaselineCanonicalDigestPort,
    RepositoryMainResolvePort,
    SubmitControlTransaction,
    SubmitControlUnitOfWorkFactory,
)
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.submission.models import (
    BuilderMutationPolicy,
    RepositorySubmitOccupancy,
    SubmitAcceptanceRecord,
    SubmitAttempt,
    SubmitAttemptState,
    SubmitTargetRef,
    SubmitUnknownTypePolicy,
    SubmitVerificationPolicy,
)
from gateway_backend.domain.workspace.errors import ScopeForbidden
from gateway_backend.domain.workspace.models import BaselineHead
from gateway_backend.domain.workspace.policies import assert_permission
from gateway_backend.domain.workspace.ports import ScopeResolutionPort
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    BusinessReference,
    JobStepKey,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
)

_SUBMIT_JOB_STEPS = (SUBMIT_STEP_PREPARE, SUBMIT_STEP_SUBMIT, SUBMIT_STEP_AWAIT)


@dataclass(frozen=True, slots=True)
class AcceptSubmitPreflight:
    snapshot_table_artifact_refs: tuple[str, ...]
    preview_ready_closure_digest: str
    preview_operation_id: str
    protected_artifact_refs: tuple[ArtifactRef, ...]
    snapshot_table_set_digest: str
    resolved_repository_id: str | None = None
    baseline_canonical_digest: str | None = None
    repository_expected_commit_id: str | None = None


@dataclass(frozen=True, slots=True)
class AcceptSubmitTransactionResult:
    submit_attempt_id: str
    operation_id: str
    replay: bool


def assert_submit_job_registered(registry: JobDefinitionRegistry) -> None:
    try:
        for step_name in _SUBMIT_JOB_STEPS:
            registry.resolve_runnable(
                JobStepKey(job_kind=SUBMIT_JOB_KIND, step_name=step_name),
                SUBMIT_JOB_CONTRACT_VERSION,
            )
    except JobDefinitionLookupError as exc:
        raise PreviewBindingConflict("submit job definition is not registered") from exc


def deterministic_submit_attempt_id(*, workspace_id: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(f"submit:{workspace_id}:{idempotency_key}".encode("utf-8")).hexdigest()[:24]
    return f"sa-{digest}"


def deterministic_submit_operation_id(*, workspace_id: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(f"submit-op:{workspace_id}:{idempotency_key}".encode("utf-8")).hexdigest()[
        :24
    ]
    return f"op-{digest}"


def accept_submit_transaction(
    *,
    command: AcceptSubmitCommand,
    scope_resolution: ScopeResolutionPort,
    unit_of_work_factory: SubmitControlUnitOfWorkFactory,
    job_registry: JobDefinitionRegistry,
    baseline_digest: BaselineCanonicalDigestPort,
    main_resolve: RepositoryMainResolvePort,
    preflight: AcceptSubmitPreflight,
    now: datetime,
) -> AcceptSubmitTransactionResult:
    assert_submit_job_registered(job_registry)
    assert_permission(command.context, PERMISSION_UPLOAD_SUBMIT)
    resolved = scope_resolution.resolve(command.context)

    with unit_of_work_factory(read_only=True) as unit_of_work:
        replay = try_accept_submit_replay(
            command=command,
            workspace_repository=unit_of_work.workspace,
            submission_repository=unit_of_work.submission,
            resolved_repository_id=resolved.repository_id,
            baseline_head=resolved.baseline_head,
        )
        if replay is not None and replay.prior_attempt is not None:
            return AcceptSubmitTransactionResult(
                submit_attempt_id=replay.prior_attempt.submit_attempt_id,
                operation_id=replay.prior_attempt.operation_id,
                replay=True,
            )
        workspace = unit_of_work.workspace.get_workspace(command.workspace_id)
        if workspace is None:
            raise ScopeForbidden
        repository_id = workspace.repository_id

    frozen = replace(
        preflight,
        resolved_repository_id=resolved.repository_id,
        baseline_canonical_digest=baseline_digest.get_baseline_canonical_digest(
            repository_id=repository_id,
            baseline_head=resolved.baseline_head,
        ),
        repository_expected_commit_id=main_resolve.resolve_main_expected_commit(
            repository_id=repository_id
        ),
    )
    with unit_of_work_factory(read_only=False) as unit_of_work:
        return _accept_submit_in_transaction(
            command=command,
            unit_of_work=unit_of_work,
            baseline_head=resolved.baseline_head,
            preflight=frozen,
            now=now,
        )


def _accept_submit_in_transaction(
    *,
    command: AcceptSubmitCommand,
    unit_of_work: SubmitControlTransaction,
    baseline_head: BaselineHead,
    preflight: AcceptSubmitPreflight,
    now: datetime,
) -> AcceptSubmitTransactionResult:
    if (
        preflight.resolved_repository_id is None
        or preflight.baseline_canonical_digest is None
        or preflight.repository_expected_commit_id is None
    ):
        raise PreviewBindingConflict("accept preflight is missing frozen repository facts")
    validation = validate_accept_submit_with_frozen(
        command=command,
        workspace_repository=unit_of_work.workspace,
        submission_repository=unit_of_work.submission,
        occupancy=unit_of_work.submission,
        resolved_repository_id=preflight.resolved_repository_id,
        baseline_head=baseline_head,
        baseline_canonical_digest=preflight.baseline_canonical_digest,
        repository_expected_commit_id=preflight.repository_expected_commit_id,
        snapshot_table_artifact_refs=preflight.snapshot_table_artifact_refs,
        preview_ready_closure_digest=preflight.preview_ready_closure_digest,
    )
    if validation.replay and validation.prior_attempt is not None:
        return AcceptSubmitTransactionResult(
            submit_attempt_id=validation.prior_attempt.submit_attempt_id,
            operation_id=validation.prior_attempt.operation_id,
            replay=True,
        )

    _assert_preview_protection_matches(
        unit_of_work,
        workspace_id=command.workspace_id,
        preview_operation_id=preflight.preview_operation_id,
        expected_refs=preflight.protected_artifact_refs,
    )

    submit_attempt_id = deterministic_submit_attempt_id(
        workspace_id=command.workspace_id,
        idempotency_key=command.idempotency_key,
    )
    operation_id = deterministic_submit_operation_id(
        workspace_id=command.workspace_id,
        idempotency_key=command.idempotency_key,
    )
    attempt = _build_prepared_attempt(
        validation=validation,
        command=command,
        submit_attempt_id=submit_attempt_id,
        operation_id=operation_id,
        preflight=preflight,
        now=now,
    )
    step_id = f"{operation_id}-step-1"
    job_payload = build_submit_job_payload(
        attempt=attempt,
        snapshot_table_set_digest=preflight.snapshot_table_set_digest,
        options=command.options,
    )
    artifact_refs = _artifact_refs_for_attempt(attempt, preflight.protected_artifact_refs)
    operation = OperationRecord(
        contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
        operation_id=operation_id,
        job_kind=SUBMIT_JOB_KIND,
        job_contract_version=SUBMIT_JOB_CONTRACT_VERSION,
        job_payload=job_payload,
        job_payload_ref=None,
        business_refs=(
            BusinessReference(kind="workspace", value=command.workspace_id),
            BusinessReference(kind="submit_attempt", value=submit_attempt_id),
        ),
        artifact_refs=artifact_refs,
        repository_operation_id=None,
        checkpoint_ref=None,
        ready_closure_ref=None,
        status=OperationStatus.QUEUED,
        diagnostic=None,
        cancel_requested=False,
        created_at=now,
        updated_at=now,
        completed_at=None,
        optimistic_version=0,
    )
    step = StepRecord(
        contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
        step_id=step_id,
        operation_id=operation_id,
        step_name=SUBMIT_STEP_PREPARE,
        status=StepStatus.PENDING,
        attempt_count=0,
        diagnostic=None,
        cancel_requested=False,
        retry_not_before=None,
        worker_id=None,
        lease_token=None,
        lease_expires_at=None,
        checkpoint_ref=None,
        prior_output_refs=(),
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
        optimistic_version=0,
    )
    unit_of_work.operations.insert_operation_with_initial_step(operation, step)
    unit_of_work.submission.insert_attempt_prepared(attempt)
    unit_of_work.submission.insert_idempotency(
        SubmitAcceptanceRecord(
            workspace_id=command.workspace_id,
            idempotency_key=command.idempotency_key,
            request_fingerprint=validation.accept_request_fingerprint,
            submit_attempt_id=submit_attempt_id,
        )
    )
    updated_workspace = replace(
        validation.workspace,
        optimistic_version=validation.workspace.optimistic_version + 1,
        updated_at=now,
    )
    unit_of_work.workspace.save_workspace(
        updated_workspace,
        expected_version=command.expected_workspace_version,
    )
    unit_of_work.submission.insert_workspace_attempt_occupancy(
        workspace_id=command.workspace_id,
        submit_attempt_id=submit_attempt_id,
    )
    unit_of_work.submission.insert_repository_occupancy(
        RepositorySubmitOccupancy(
            repository_id=validation.workspace.repository_id,
            workspace_id=command.workspace_id,
            submit_attempt_id=submit_attempt_id,
            business_baseline_node_id=validation.baseline_head.business_baseline_node_id,
            baseline_head_version=validation.baseline_head.baseline_head_version,
            acquired_at=now,
        )
    )
    if artifact_refs:
        unit_of_work.set_artifact_protection(
            artifact_refs,
            owner_kind="submit-attempt",
            owner_id=submit_attempt_id,
            intent="submit-attempt",
        )
    unit_of_work.clear_artifact_protection(
        owner_kind="current-preview",
        owner_id=command.workspace_id,
    )
    unit_of_work.clear_artifact_protection(
        owner_kind="preview-operation",
        owner_id=preflight.preview_operation_id,
    )
    return AcceptSubmitTransactionResult(
        submit_attempt_id=submit_attempt_id,
        operation_id=operation_id,
        replay=False,
    )


def _assert_preview_protection_matches(
    unit_of_work: SubmitControlTransaction,
    *,
    workspace_id: str,
    preview_operation_id: str,
    expected_refs: tuple[ArtifactRef, ...],
) -> None:
    expected_ids = frozenset(ref.artifact_id for ref in expected_refs)
    preview_refs = unit_of_work.list_artifact_protection_for_owner(
        owner_kind="current-preview",
        owner_id=workspace_id,
    )
    operation_refs = unit_of_work.list_artifact_protection_for_owner(
        owner_kind="preview-operation",
        owner_id=preview_operation_id,
    )
    held_refs = preview_refs | operation_refs
    if held_refs != expected_ids:
        raise PreviewBindingConflict("preview artifact protection does not match preflight refs")


def _artifact_refs_for_attempt(
    attempt: SubmitAttempt,
    protected_refs: tuple[ArtifactRef, ...],
) -> tuple[ArtifactRef, ...]:
    required_ids = frozenset(
        (
            *attempt.source_artifact_refs,
            *attempt.snapshot_table_artifact_refs,
            attempt.preview_ready_closure_ref,
        )
    )
    selected = tuple(ref for ref in protected_refs if ref.artifact_id in required_ids)
    if frozenset(ref.artifact_id for ref in selected) != required_ids:
        raise PreviewBindingConflict("protected artifact refs do not cover attempt bindings")
    return selected


def _build_prepared_attempt(
    *,
    validation: AcceptSubmitValidationResult,
    command: AcceptSubmitCommand,
    submit_attempt_id: str,
    operation_id: str,
    preflight: AcceptSubmitPreflight,
    now: datetime,
) -> SubmitAttempt:
    preview = validation.preview_result
    upload = validation.upload_revision
    source_refs = tuple(
        binding.artifact_id
        for _role, binding in sorted(upload.source_artifacts.items(), key=lambda item: item[0].value)
    )
    return SubmitAttempt(
        submit_attempt_id=submit_attempt_id,
        workspace_id=command.workspace_id,
        workspace_generation=validation.workspace.generation,
        upload_revision_id=command.upload_revision_id,
        preview_result_id=command.preview_result_id,
        repository_id=validation.workspace.repository_id,
        business_baseline_node_id=validation.baseline_head.business_baseline_node_id,
        business_baseline_commit_id=validation.baseline_head.business_baseline_commit_id,
        baseline_head_version=validation.baseline_head.baseline_head_version,
        repository_expected_commit_id=validation.repository_expected_commit_id,
        canonical_business_digest=validation.canonical_business_digest,
        source_digest=preview.digests.source_digest,
        snapshot_digest=preview.digests.snapshot_digest,
        source_artifact_refs=source_refs,
        snapshot_table_artifact_refs=preflight.snapshot_table_artifact_refs,
        preview_ready_closure_ref=preview.ready_closure_artifact_id,
        preview_ready_closure_digest=preflight.preview_ready_closure_digest,
        canonicalization_manifest_ref=None,
        canonicalization_manifest_digest=None,
        repository_import_artifact_ref=None,
        repository_artifact_ref=None,
        repository_operation_id=None,
        repository_operation_evidence=None,
        requested_target_ref=SubmitTargetRef.MAIN,
        requested_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        requested_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        builder_mutation_policy=BuilderMutationPolicy.REBUILD_ALWAYS,
        accept_idempotency_key=command.idempotency_key,
        accept_request_fingerprint=validation.accept_request_fingerprint,
        repository_upload_idempotency_key=derive_repository_upload_idempotency_key(submit_attempt_id),
        repository_import_idempotency_key=derive_repository_import_idempotency_key(submit_attempt_id),
        operation_id=operation_id,
        state=SubmitAttemptState.PREPARED,
        submission_id=None,
        optimistic_version=0,
        created_by=command.context.actor_id,
        created_at=now,
    )
