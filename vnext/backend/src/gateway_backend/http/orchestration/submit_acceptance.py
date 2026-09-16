"""Submit acceptance orchestration for HTTP AcceptSubmit."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from gateway_shared_kernel import DigestRef

from gateway_backend.application.job_definitions import JobDefinitionRegistry
from gateway_backend.application.submission.accept import (
    PERMISSION_UPLOAD_SUBMIT,
    AcceptPreflightLoadedFacts,
    assert_accept_preflight_post_noop_guards,
    assert_no_canonical_change_after_baseline,
    evaluate_new_accept_preflight_local_guards,
    load_new_accept_preflight_facts,
    try_accept_submit_replay,
)
from gateway_backend.application.submission.accept_transaction import (
    AcceptSubmitPreflight,
    accept_submit_transaction,
    assert_submit_job_registered,
)
from gateway_backend.application.submission.contracts import AcceptSubmitCommand
from gateway_backend.application.submission.errors import PreviewBindingConflict
from gateway_backend.application.submission.ports import (
    BaselineCanonicalDigestPort,
    RepositoryMainResolvePort,
    SubmitControlUnitOfWorkFactory,
)
from gateway_backend.artifacts.bounded_store import BoundedArtifactStorePort
from gateway_backend.http.dependencies import ArtifactRefLookupPort
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.submission.models import SubmitAttempt
from gateway_backend.domain.workspace.models import (
    BaselineHead,
    IdentityContext,
    PreviewResult,
    UploadRevision,
)
from gateway_backend.domain.workspace.policies import assert_permission
from gateway_backend.domain.workspace.ports import ScopeResolutionPort, WorkspaceRepository
from gateway_backend.http.errors import ApiError
from gateway_backend.http.schemas.submit import SubmitAcceptedResponse, SubmitAttemptStateLiteral
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork

PREVIEW_READY_CLOSURE_DIGEST_PREFIX = "v1:"


def _submit_uow_factory(
    unit_of_work_factory: Callable[[], ControlDbUnitOfWork],
) -> SubmitControlUnitOfWorkFactory:
    return cast(SubmitControlUnitOfWorkFactory, unit_of_work_factory)


@dataclass(frozen=True, slots=True)
class SubmitAcceptanceResult:
    response: SubmitAcceptedResponse
    replay: bool


def derive_preview_ready_closure_digest(preview: PreviewResult) -> str:
    return f"{PREVIEW_READY_CLOSURE_DIGEST_PREFIX}{preview.ready_closure_artifact_id}"


def derive_snapshot_table_set_digest(snapshot_table_artifact_refs: tuple[str, ...]) -> str:
    joined = ",".join(sorted(snapshot_table_artifact_refs))
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def build_replay_preflight_from_attempt(attempt: SubmitAttempt) -> AcceptSubmitPreflight:
    return AcceptSubmitPreflight(
        snapshot_table_artifact_refs=tuple(attempt.snapshot_table_artifact_refs),
        preview_ready_closure_digest=attempt.preview_ready_closure_digest,
        preview_operation_id="",
        protected_artifact_refs=(),
        snapshot_table_set_digest=attempt.snapshot_digest,
    )


def build_accept_submit_command(
    *,
    context: IdentityContext,
    workspace_id: str,
    expected_workspace_version: int,
    upload_revision_id: str,
    preview_result_id: str,
    generation: int,
    expected_baseline_node_id: str,
    expected_baseline_head_version: int,
    idempotency_key: str,
    options: Mapping[str, object],
) -> AcceptSubmitCommand:
    return AcceptSubmitCommand(
        context=context,
        workspace_id=workspace_id,
        expected_workspace_version=expected_workspace_version,
        upload_revision_id=upload_revision_id,
        preview_result_id=preview_result_id,
        generation=generation,
        expected_baseline_node_id=expected_baseline_node_id,
        expected_baseline_head_version=expected_baseline_head_version,
        idempotency_key=idempotency_key,
        options=dict(options),
    )


def load_accept_submit_preflight(
    *,
    command: AcceptSubmitCommand,
    unit_of_work_factory: Callable[[], ControlDbUnitOfWork],
    preview_result: PreviewResult,
    upload_revision: UploadRevision,
    artifact_ref_lookup: ArtifactRefLookupPort,
    baseline_canonical_digest: str | None = None,
) -> AcceptSubmitPreflight:
    preview_operation_id = preview_result.operation_id
    with _submit_uow_factory(unit_of_work_factory)(read_only=True) as unit_of_work:
        preview_refs = unit_of_work.list_artifact_protection_for_owner(
            owner_kind="current-preview",
            owner_id=command.workspace_id,
        )
        operation_refs = unit_of_work.list_artifact_protection_for_owner(
            owner_kind="preview-operation",
            owner_id=preview_operation_id,
        )
        held_ids = preview_refs | operation_refs

    source_ids = frozenset(
        binding.artifact_id
        for _role, binding in sorted(
            upload_revision.source_artifacts.items(),
            key=lambda item: item[0].value,
        )
    )
    closure_id = preview_result.ready_closure_artifact_id
    snapshot_table_artifact_refs = tuple(
        sorted(
            artifact_id
            for artifact_id in held_ids
            if artifact_id not in source_ids and artifact_id != closure_id
        )
    )
    protected_artifact_refs = _protected_artifact_refs(
        upload_revision=upload_revision,
        preview_result=preview_result,
        snapshot_table_artifact_refs=snapshot_table_artifact_refs,
        artifact_ref_lookup=artifact_ref_lookup,
    )
    return AcceptSubmitPreflight(
        snapshot_table_artifact_refs=snapshot_table_artifact_refs,
        preview_ready_closure_digest=derive_preview_ready_closure_digest(preview_result),
        preview_operation_id=preview_operation_id,
        protected_artifact_refs=protected_artifact_refs,
        snapshot_table_set_digest=derive_snapshot_table_set_digest(snapshot_table_artifact_refs),
        baseline_canonical_digest=baseline_canonical_digest,
    )


def accept_submit_operation(
    *,
    command: AcceptSubmitCommand,
    scope_resolution: ScopeResolutionPort,
    workspace_repository: WorkspaceRepository,
    unit_of_work_factory: Callable[[], ControlDbUnitOfWork],
    job_registry: JobDefinitionRegistry,
    artifact_store: BoundedArtifactStorePort,
    artifact_ref_lookup: ArtifactRefLookupPort,
    baseline_digest: BaselineCanonicalDigestPort,
    main_resolve: RepositoryMainResolvePort,
    now: datetime,
) -> SubmitAcceptanceResult:
    try:
        assert_submit_job_registered(job_registry)
    except PreviewBindingConflict as exc:
        if "not registered" in str(exc):
            raise ApiError(
                code="SERVICE_NOT_READY",
                message="submit job definition is not registered",
                status_code=503,
            ) from exc
        raise

    assert_permission(command.context, PERMISSION_UPLOAD_SUBMIT)

    is_replay = False
    preflight: AcceptSubmitPreflight
    new_key_loaded: AcceptPreflightLoadedFacts | None = None
    resolved_baseline_head: BaselineHead | None = None

    with _submit_uow_factory(unit_of_work_factory)(read_only=True) as unit_of_work:
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
            loaded_preview = workspace_repository.get_preview_result(command.preview_result_id)
            if loaded_upload is None or loaded_preview is None:
                raise ApiError(
                    code="RESOURCE_NOT_FOUND",
                    message="resource not found",
                    status_code=404,
                )
            upload_revision = loaded_upload
            preview_result = loaded_preview
            preview_ready_closure_digest = derive_preview_ready_closure_digest(preview_result)
            new_key_loaded = load_new_accept_preflight_facts(
                command=command,
                workspace_repository=unit_of_work.workspace,
                occupancy=unit_of_work.submission,
                resolved_repository_id=resolved.repository_id,
                baseline_head=resolved.baseline_head,
                preview_ready_closure_digest=preview_ready_closure_digest,
            )
            evaluate_new_accept_preflight_local_guards(command=command, loaded=new_key_loaded)
            assert_accept_preflight_post_noop_guards(loaded=new_key_loaded)
            resolved_baseline_head = resolved.baseline_head

    if is_replay:
        pass
    else:
        if new_key_loaded is None or resolved_baseline_head is None:
            raise PreviewBindingConflict("accept preflight is missing loaded facts")
        baseline_canonical_digest = baseline_digest.get_baseline_canonical_digest(
            repository_id=new_key_loaded.workspace.repository_id,
            baseline_head=resolved_baseline_head,
        )
        assert_no_canonical_change_after_baseline(
            loaded=new_key_loaded,
            baseline_canonical_digest=baseline_canonical_digest,
        )
        upload_revision = new_key_loaded.upload_revision
        preview_result = new_key_loaded.preview_result
        preflight = load_accept_submit_preflight(
            command=command,
            unit_of_work_factory=unit_of_work_factory,
            preview_result=preview_result,
            upload_revision=upload_revision,
            artifact_ref_lookup=artifact_ref_lookup,
            baseline_canonical_digest=baseline_canonical_digest,
        )
        for ref in preflight.protected_artifact_refs:
            verified = artifact_store.verify_readable(
                ref,
                expected_size=ref.size_bytes,
                expected_raw_sha256=ref.raw_sha256,
            )
            if not verified.verified:
                raise ApiError(
                    code="ARTIFACT_UNAVAILABLE",
                    message="required artifact is not readable",
                    status_code=503,
                )

    transaction_result = accept_submit_transaction(
        command=command,
        scope_resolution=scope_resolution,
        unit_of_work_factory=cast(SubmitControlUnitOfWorkFactory, unit_of_work_factory),
        job_registry=job_registry,
        baseline_digest=baseline_digest,
        main_resolve=main_resolve,
        preflight=preflight,
        now=now,
    )

    with _submit_uow_factory(unit_of_work_factory)(read_only=True) as unit_of_work:
        attempt = unit_of_work.submission.get_submit_attempt(transaction_result.submit_attempt_id)
    if attempt is None:
        raise ApiError(
            code="SERVICE_NOT_READY",
            message="submit attempt is unavailable after acceptance",
            status_code=503,
        )

    state: SubmitAttemptStateLiteral = attempt.state.value
    return SubmitAcceptanceResult(
        response=SubmitAcceptedResponse(
            submit_attempt_id=transaction_result.submit_attempt_id,
            operation_id=transaction_result.operation_id,
            workspace_id=command.workspace_id,
            preview_result_id=command.preview_result_id,
            generation=command.generation,
            state=state,
        ),
        replay=transaction_result.replay,
    )


def _protected_artifact_refs(
    *,
    upload_revision: UploadRevision,
    preview_result: PreviewResult,
    snapshot_table_artifact_refs: tuple[str, ...],
    artifact_ref_lookup: ArtifactRefLookupPort,
) -> tuple[ArtifactRef, ...]:
    refs_by_id: dict[str, ArtifactRef] = {}
    for _role, binding in sorted(upload_revision.source_artifacts.items(), key=lambda item: item[0].value):
        refs_by_id[binding.artifact_id] = ArtifactRef(
            artifact_id=binding.artifact_id,
            media_type=binding.media_type,
            size_bytes=binding.size_bytes,
            raw_sha256=DigestRef(binding.raw_sha256),
        )
    closure_id = preview_result.ready_closure_artifact_id
    for artifact_id in (closure_id, *snapshot_table_artifact_refs):
        if artifact_id in refs_by_id:
            continue
        resolved = artifact_ref_lookup.lookup_ref(artifact_id)
        if resolved is None:
            raise PreviewBindingConflict(f"artifact metadata is missing for {artifact_id!r}")
        refs_by_id[artifact_id] = resolved
    source_ids = frozenset(
        binding.artifact_id for _role, binding in upload_revision.source_artifacts.items()
    )
    required_ids = source_ids | {closure_id} | frozenset(snapshot_table_artifact_refs)
    selected = tuple(refs_by_id[artifact_id] for artifact_id in sorted(required_ids))
    if frozenset(ref.artifact_id for ref in selected) != required_ids:
        raise PreviewBindingConflict("preview artifact protection does not match required refs")
    return selected
