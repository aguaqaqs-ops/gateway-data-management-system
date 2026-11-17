"""T1 AcceptSubmit SQLite transaction orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime

from gateway_shared_kernel import DigestRef

from gateway_backend.application.job_definitions import (
    JobDefinitionLookupError,
    JobDefinitionRegistry,
)
from gateway_backend.application.preview_binding import derive_preview_ready_closure_digest
from gateway_backend.application.submission.accept import (
    PERMISSION_UPLOAD_SUBMIT,
    AcceptPreflightLoadedFacts,
    assert_no_canonical_change,
    evaluate_new_accept_preflight_local_guards,
    load_new_accept_preflight_facts,
    try_accept_submit_replay,
    validate_accept_submit_with_frozen,
)
from gateway_backend.application.submission.contracts import (
    SUBMIT_JOB_CONTRACT_VERSION,
    AcceptSubmitCommand,
    AcceptSubmitResult,
    AcceptSubmitValidationResult,
    derive_repository_import_idempotency_key,
    derive_repository_upload_idempotency_key,
    deterministic_submit_attempt_id as deterministic_submit_attempt_id,
    deterministic_submit_operation_id as deterministic_submit_operation_id,
)
from gateway_backend.application.submission.errors import (
    PreviewBindingConflict,
    SubmitAcceptanceUnavailable,
    SubmitArtifactUnavailable,
    SubmitJobNotRegistered,
)
from gateway_backend.application.submission.import_builder import (
    SubmitImportBuilderError,
    resolve_canonical_snapshot_bindings,
)
from gateway_backend.application.submission.job_payload import (
    SUBMIT_JOB_KIND,
    SUBMIT_STEP_AWAIT,
    SUBMIT_STEP_PREPARE,
    SUBMIT_STEP_SUBMIT,
    build_submit_job_payload,
)
from gateway_backend.application.submission.ports import (
    ArtifactRefLookupPort,
    RepositoryMainResolvePort,
    SubmitControlTransaction,
    SubmitControlUnitOfWorkFactory,
)
from gateway_backend.application.submission.review_result import load_preview_review_closure
from gateway_backend.artifacts.bounded_store import BoundedArtifactStorePort
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.submission.models import (
    BuilderMutationPolicy,
    RepositorySubmitOccupancy,
    SubmitAcceptanceRecord,
    SubmitAttempt,
    SubmitAttemptState,
    SubmitIdentityConfirmation,
    SubmitTargetRef,
    SubmitUnknownTypePolicy,
    SubmitVerificationPolicy,
)
from gateway_backend.domain.workspace.errors import ScopeForbidden
from gateway_backend.domain.workspace.models import (
    BaselineHead,
    PreviewResult,
    UploadRevision,
)
from gateway_backend.domain.workspace.policies import assert_permission
from gateway_backend.domain.workspace.ports import ScopeResolutionPort, WorkspaceRepository
from gateway_backend.operations.store import RecordNotFound
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
    preview_ready_closure_digest: str
    preview_operation_id: str
    protected_artifact_refs: tuple[ArtifactRef, ...]
    current_storage_projection_ruleset_digest: str
    resolved_repository_id: str | None = None
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
        raise SubmitJobNotRegistered() from exc


def build_replay_preflight_from_attempt(attempt: SubmitAttempt) -> AcceptSubmitPreflight:
    return AcceptSubmitPreflight(
        preview_ready_closure_digest=attempt.preview_ready_closure_digest,
        preview_operation_id="",
        protected_artifact_refs=(),
        current_storage_projection_ruleset_digest="",
    )


def load_accept_submit_preflight(
    *,
    command: AcceptSubmitCommand,
    unit_of_work_factory: SubmitControlUnitOfWorkFactory,
    preview_result: PreviewResult,
    upload_revision: UploadRevision,
    artifact_ref_lookup: ArtifactRefLookupPort,
    artifact_store: BoundedArtifactStorePort,
    current_storage_projection_ruleset_digest: str,
) -> AcceptSubmitPreflight:
    preview_operation_id = preview_result.operation_id
    with unit_of_work_factory(read_only=True) as unit_of_work:
        preview_refs = unit_of_work.list_artifact_protection_for_owner(
            owner_kind="current-preview",
            owner_id=command.workspace_id,
        )
        operation_refs = unit_of_work.list_artifact_protection_for_owner(
            owner_kind="preview-operation",
            owner_id=preview_operation_id,
        )
        held_ids = preview_refs | operation_refs

    try:
        _table_bindings, canonical_refs = resolve_canonical_snapshot_bindings(
            operation_artifact_refs=tuple(
                ref
                for artifact_id in held_ids
                if (ref := artifact_ref_lookup.lookup_ref(artifact_id)) is not None
            ),
            canonical_table_set_closure_ref=(
                preview_result.canonical.canonical_table_set_closure_ref.artifact_id
            ),
            canonical_table_set_closure_digest=(
                preview_result.canonical.canonical_table_set_closure_digest.value
            ),
            canonicalization_manifest_ref=(
                preview_result.canonical.canonicalization_manifest_ref.artifact_id
            ),
            canonicalization_manifest_digest=(
                preview_result.canonical.canonicalization_manifest_digest.value
            ),
            read_artifact=lambda ref: b"".join(artifact_store.read_exact(ref)),
        )
    except SubmitImportBuilderError as exc:
        raise PreviewBindingConflict(str(exc)) from exc
    try:
        review_refs = load_preview_review_closure(
            preview_result, lookup=artifact_ref_lookup, store=artifact_store
        )
    except ManifestVerificationError as exc:
        raise SubmitArtifactUnavailable("required review artifact is not readable") from exc
    except (ValueError, TypeError, KeyError) as exc:
        raise PreviewBindingConflict("preview review closure is invalid") from exc
    refs_by_id = {ref.artifact_id: ref for ref in (*canonical_refs, *review_refs)}
    for _role, binding in upload_revision.source_artifacts.items():
        refs_by_id[binding.artifact_id] = ArtifactRef(
            artifact_id=binding.artifact_id,
            media_type=binding.media_type,
            size_bytes=binding.size_bytes,
            raw_sha256=DigestRef(binding.raw_sha256),
        )
    ready_ref = artifact_ref_lookup.lookup_ref(preview_result.ready_closure_artifact_id)
    if ready_ref is None:
        raise PreviewBindingConflict("preview ready closure artifact metadata is missing")
    refs_by_id[ready_ref.artifact_id] = ready_ref
    protected_artifact_refs = tuple(refs_by_id[key] for key in sorted(refs_by_id))
    expected_preview_ids = frozenset(refs_by_id) - frozenset(
        binding.artifact_id for binding in upload_revision.source_artifacts.values()
    )
    if not expected_preview_ids.issubset(held_ids):
        raise PreviewBindingConflict("preview protection does not cover canonical bindings")
    return AcceptSubmitPreflight(
        preview_ready_closure_digest=derive_preview_ready_closure_digest(preview_result),
        preview_operation_id=preview_operation_id,
        protected_artifact_refs=protected_artifact_refs,
        current_storage_projection_ruleset_digest=current_storage_projection_ruleset_digest,
    )


def accept_submit_operation(
    *,
    command: AcceptSubmitCommand,
    scope_resolution: ScopeResolutionPort,
    workspace_repository: WorkspaceRepository,
    unit_of_work_factory: SubmitControlUnitOfWorkFactory,
    job_registry: JobDefinitionRegistry,
    artifact_store: BoundedArtifactStorePort,
    artifact_ref_lookup: ArtifactRefLookupPort,
    main_resolve: RepositoryMainResolvePort,
    current_storage_projection_ruleset_digest: str,
    now: datetime,
    operation_queue_limit: int = 32,
) -> AcceptSubmitResult:
    assert_submit_job_registered(job_registry)
    assert_permission(command.context, PERMISSION_UPLOAD_SUBMIT)

    is_replay = False
    preflight: AcceptSubmitPreflight
    new_key_loaded: AcceptPreflightLoadedFacts | None = None

    with unit_of_work_factory(read_only=True) as unit_of_work:
        resolved = scope_resolution.resolve(command.context)
        replay_result = try_accept_submit_replay(
            command=command,
            workspace_repository=unit_of_work.workspace,
            submission_repository=unit_of_work.submission,
            resolved_repository_id=resolved.repository_id,
            baseline_head=resolved.baseline_head,
        )
        if replay_result is not None:
            is_replay = True
            prior_attempt = replay_result.prior_attempt
            if prior_attempt is None:
                raise PreviewBindingConflict("submit replay validation failed")
            preflight = build_replay_preflight_from_attempt(prior_attempt)
        else:
            loaded_upload = workspace_repository.get_upload_revision(command.upload_revision_id)
            loaded_preview = workspace_repository.get_preview_result(
                command.preview_result_id,
                workspace_id=command.workspace_id,
                repository_id=resolved.repository_id,
            )
            if loaded_upload is None or loaded_preview is None:
                raise ScopeForbidden
            preview_ready_closure_digest = derive_preview_ready_closure_digest(loaded_preview)
            new_key_loaded = load_new_accept_preflight_facts(
                command=command,
                workspace_repository=unit_of_work.workspace,
                occupancy=unit_of_work.submission,
                resolved_repository_id=resolved.repository_id,
                baseline_head=resolved.baseline_head,
                preview_ready_closure_digest=preview_ready_closure_digest,
                current_storage_projection_ruleset_digest=current_storage_projection_ruleset_digest,
            )
            evaluate_new_accept_preflight_local_guards(command=command, loaded=new_key_loaded)

    if not is_replay:
        if new_key_loaded is None:
            raise PreviewBindingConflict("accept preflight is missing loaded facts")
        assert_no_canonical_change(loaded=new_key_loaded)
        upload_revision = new_key_loaded.upload_revision
        preview_result = new_key_loaded.preview_result
        if new_key_loaded.workspace_occupancy_held or new_key_loaded.repository_occupancy_held:
            preflight = AcceptSubmitPreflight(
                preview_ready_closure_digest=derive_preview_ready_closure_digest(preview_result),
                preview_operation_id=preview_result.operation_id,
                protected_artifact_refs=(),
                current_storage_projection_ruleset_digest=(
                    current_storage_projection_ruleset_digest
                ),
            )
        else:
            preflight = load_accept_submit_preflight(
                command=command,
                unit_of_work_factory=unit_of_work_factory,
                preview_result=preview_result,
                upload_revision=upload_revision,
                artifact_ref_lookup=artifact_ref_lookup,
                artifact_store=artifact_store,
                current_storage_projection_ruleset_digest=current_storage_projection_ruleset_digest,
            )
            for ref in preflight.protected_artifact_refs:
                verified = artifact_store.verify_readable(
                    ref,
                    expected_size=ref.size_bytes,
                    expected_raw_sha256=ref.raw_sha256,
                )
                if not verified.verified:
                    raise SubmitArtifactUnavailable("required artifact is not readable")

    transaction_result = accept_submit_transaction(
        command=command,
        scope_resolution=scope_resolution,
        unit_of_work_factory=unit_of_work_factory,
        job_registry=job_registry,
        main_resolve=main_resolve,
        preflight=preflight,
        now=now,
        operation_queue_limit=operation_queue_limit,
    )

    with unit_of_work_factory(read_only=True) as unit_of_work:
        attempt = unit_of_work.submission.get_submit_attempt(transaction_result.submit_attempt_id)
    if attempt is None:
        raise SubmitAcceptanceUnavailable("submit attempt is unavailable after acceptance")

    return AcceptSubmitResult(
        submit_attempt_id=transaction_result.submit_attempt_id,
        operation_id=transaction_result.operation_id,
        workspace_id=command.workspace_id,
        preview_result_id=command.preview_result_id,
        generation=command.generation,
        state=attempt.state,
        replay=transaction_result.replay,
    )


def accept_submit_transaction(
    *,
    command: AcceptSubmitCommand,
    scope_resolution: ScopeResolutionPort,
    unit_of_work_factory: SubmitControlUnitOfWorkFactory,
    job_registry: JobDefinitionRegistry,
    main_resolve: RepositoryMainResolvePort,
    preflight: AcceptSubmitPreflight,
    now: datetime,
    operation_queue_limit: int = 32,
) -> AcceptSubmitTransactionResult:
    assert_submit_job_registered(job_registry)
    assert_permission(command.context, PERMISSION_UPLOAD_SUBMIT)
    resolved = scope_resolution.resolve(command.context)

    with unit_of_work_factory(read_only=True) as unit_of_work:
        prior_record = unit_of_work.submission.find_submit_idempotency(
            command.workspace_id,
            command.idempotency_key,
        )
        is_replay = prior_record is not None
        if is_replay:
            frozen = preflight
        else:
            loaded = load_new_accept_preflight_facts(
                command=command,
                workspace_repository=unit_of_work.workspace,
                occupancy=unit_of_work.submission,
                resolved_repository_id=resolved.repository_id,
                baseline_head=resolved.baseline_head,
                preview_ready_closure_digest=preflight.preview_ready_closure_digest,
                current_storage_projection_ruleset_digest=(
                    preflight.current_storage_projection_ruleset_digest
                ),
            )
            repository_id = loaded.workspace.repository_id

    if not is_replay:
        evaluate_new_accept_preflight_local_guards(command=command, loaded=loaded)

        assert_no_canonical_change(loaded=loaded)

        frozen = replace(
            preflight,
            resolved_repository_id=resolved.repository_id,
            repository_expected_commit_id=main_resolve.resolve_main_expected_commit(
                repository_id=repository_id
            ),
        )

    with unit_of_work_factory(read_only=False) as unit_of_work:
        return _accept_submit_in_transaction(
            command=command,
            unit_of_work=unit_of_work,
            preflight_baseline_head=resolved.baseline_head,
            preflight=frozen,
            now=now,
            operation_queue_limit=operation_queue_limit,
        )


def _assert_current_preview_semantics(
    unit_of_work: SubmitControlTransaction, preview: PreviewResult
) -> None:
    """Check only new T1 accepts; replay and frozen readers retain original identity."""
    # Preview job initialization imports workspace, whose public API imports this module.
    from gateway_backend.application.preview_job_identity import (
        PREVIEW_JOB_CONTRACT_VERSION,
        PREVIEW_JOB_KIND,
    )
    from gateway_backend.application.preview_jobs.payload import decode_preview_payload

    message = "preview semantics changed; use a new key to create a new preview"
    try:
        operation = unit_of_work.operations.get_operation(preview.operation_id)
    except RecordNotFound as exc:
        raise PreviewBindingConflict(message) from exc
    if (
        operation.job_kind != PREVIEW_JOB_KIND
        or operation.job_contract_version != PREVIEW_JOB_CONTRACT_VERSION
        or preview.contract_version != operation.job_contract_version
        or operation.job_payload is None
        or BusinessReference(kind="workspace", value=preview.workspace_id)
        not in operation.business_refs
        or BusinessReference(kind="upload_revision", value=preview.upload_revision_id)
        not in operation.business_refs
    ):
        raise PreviewBindingConflict(message)
    try:
        document = json.loads(operation.job_payload)
        if not isinstance(document, dict):
            raise ValueError("preview payload is not an object")
        payload = decode_preview_payload(document)
    except (ValueError, UnicodeDecodeError) as exc:
        raise PreviewBindingConflict(message) from exc
    if (
        payload.workspace_id != preview.workspace_id
        or payload.upload_revision_id != preview.upload_revision_id
        or payload.generation != preview.generation
        or payload.repository_id != preview.repository_id
        or payload.business_baseline_node_id != preview.business_baseline_node_id
        or payload.business_baseline_commit_id != preview.business_baseline_commit_id
        or payload.baseline_head_version != preview.baseline_head_version
    ):
        raise PreviewBindingConflict(message)


def _accept_submit_in_transaction(
    *,
    command: AcceptSubmitCommand,
    unit_of_work: SubmitControlTransaction,
    preflight_baseline_head: BaselineHead,
    preflight: AcceptSubmitPreflight,
    now: datetime,
    operation_queue_limit: int,
) -> AcceptSubmitTransactionResult:
    prior_record = unit_of_work.submission.find_submit_idempotency(
        command.workspace_id,
        command.idempotency_key,
    )
    is_replay = prior_record is not None
    if not is_replay and (
        preflight.resolved_repository_id is None or preflight.repository_expected_commit_id is None
    ):
        raise PreviewBindingConflict("accept preflight is missing frozen repository facts")
    validation = validate_accept_submit_with_frozen(
        command=command,
        unit_of_work=unit_of_work,
        preflight_baseline_head=preflight_baseline_head,
        repository_expected_commit_id=preflight.repository_expected_commit_id or "",
        current_storage_projection_ruleset_digest=(
            preflight.current_storage_projection_ruleset_digest
        ),
        preview_ready_closure_digest=preflight.preview_ready_closure_digest,
    )
    if validation.replay and validation.prior_attempt is not None:
        return AcceptSubmitTransactionResult(
            submit_attempt_id=validation.prior_attempt.submit_attempt_id,
            operation_id=validation.prior_attempt.operation_id,
            replay=True,
        )

    _assert_current_preview_semantics(unit_of_work, validation.preview_result)

    if preflight.preview_ready_closure_digest != derive_preview_ready_closure_digest(
        validation.preview_result
    ):
        raise PreviewBindingConflict("accepted Preview binding changed after preflight")

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
    if unit_of_work.count_queued_operations() >= operation_queue_limit:
        from gateway_backend.operations.store import OperationQueueFull

        raise OperationQueueFull
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
            preflight.protected_artifact_refs,
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
    if not expected_ids.issubset(held_refs):
        raise PreviewBindingConflict("preview artifact protection does not cover preflight refs")


def _artifact_refs_for_attempt(
    attempt: SubmitAttempt,
    protected_refs: tuple[ArtifactRef, ...],
) -> tuple[ArtifactRef, ...]:
    required_ids = tuple(
        dict.fromkeys(
            (
                *attempt.source_artifact_refs,
                attempt.preview_ready_closure_ref,
                attempt.canonical_table_set_closure_ref,
                attempt.canonicalization_manifest_ref,
            )
        )
    )
    selected_ids = {ref.artifact_id for ref in protected_refs}
    if not set(required_ids).issubset(selected_ids):
        raise PreviewBindingConflict("protected artifact refs do not cover attempt bindings")
    refs_by_id = {ref.artifact_id: ref for ref in protected_refs}
    return tuple(refs_by_id[artifact_id] for artifact_id in required_ids)


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
        for _role, binding in sorted(
            upload.source_artifacts.items(), key=lambda item: item[0].value
        )
    )
    return SubmitAttempt(
        configuration_facts=preview.canonical.configuration_facts,
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
        preview_ready_closure_ref=preview.ready_closure_artifact_id,
        preview_ready_closure_digest=preflight.preview_ready_closure_digest,
        canonical_table_set_closure_ref=(
            preview.canonical.canonical_table_set_closure_ref.artifact_id
        ),
        canonical_table_set_closure_digest=(
            preview.canonical.canonical_table_set_closure_digest.value
        ),
        canonicalization_manifest_ref=(preview.canonical.canonicalization_manifest_ref.artifact_id),
        canonicalization_manifest_digest=(preview.canonical.canonicalization_manifest_digest.value),
        repository_import_artifact_ref=None,
        repository_artifact_ref=None,
        repository_operation_id=None,
        repository_operation_evidence=None,
        requested_target_ref=SubmitTargetRef.MAIN,
        requested_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        requested_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        builder_mutation_policy=BuilderMutationPolicy.ADAPTIVE_PATCH,
        accept_idempotency_key=command.idempotency_key,
        accept_request_fingerprint=validation.accept_request_fingerprint,
        repository_upload_idempotency_key=derive_repository_upload_idempotency_key(
            submit_attempt_id
        ),
        repository_import_idempotency_key=derive_repository_import_idempotency_key(
            submit_attempt_id
        ),
        operation_id=operation_id,
        state=SubmitAttemptState.PREPARED,
        submission_id=None,
        optimistic_version=0,
        created_by=command.context.actor_id,
        created_at=now,
        identity_confirmations=tuple(
            SubmitIdentityConfirmation(
                action=item.action,
                assessment_set_digest=item.assessment_set_digest,
                reason=item.reason,
                actor_id=command.context.actor_id,
                confirmed_at=now,
            )
            for item in command.identity_confirmations
        ),
    )
