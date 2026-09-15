"""Submit import builder and artifact protection helpers."""

from __future__ import annotations

from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.application.submission.contracts import (
    PrepareImportBuildInput,
    PrepareImportCheckpoint,
    PrepareImportPublicationResult,
    SubmitImportPublicationPort,
)
from gateway_backend.application.submission.errors import PreviewBindingConflict
from gateway_backend.application.submission.ports import SubmitControlTransaction
from gateway_backend.artifacts.store import ArtifactStorePort
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.submission.models import (
    BackendArtifactRef,
    BuilderMutationPolicy,
    SubmitAttempt,
)


class SubmitImportBuilderError(ValueError):
    """Raised when submit import builder input or reuse is invalid."""


def publish_prepare_import_package(
    *,
    build_input: PrepareImportBuildInput,
    publication: SubmitImportPublicationPort,
    store: ArtifactStorePort,
) -> PrepareImportPublicationResult:
    _assert_rebuild_policy(build_input)
    return publication.build_and_publish(build_input=build_input, store=store)


def reuse_prepare_import_checkpoint(
    *,
    build_input: PrepareImportBuildInput,
    checkpoint: PrepareImportCheckpoint,
    publication: SubmitImportPublicationPort,
    store: ArtifactStorePort,
) -> PrepareImportPublicationResult:
    _assert_rebuild_policy(build_input)
    _assert_checkpoint_matches_build_input(checkpoint=checkpoint, build_input=build_input)
    payload = publication.read_back_package(checkpoint=checkpoint, store=store)
    if raw_blob_digest(payload).value != checkpoint.package_raw_sha256:
        raise SubmitImportBuilderError("checkpoint package raw SHA does not match read-back")
    return PrepareImportPublicationResult(checkpoint=checkpoint, replay=True)


def transfer_preview_protection_to_attempt(
    unit_of_work: SubmitControlTransaction,
    *,
    workspace_id: str,
    preview_operation_id: str,
    submit_attempt_id: str,
    expected_refs: tuple[ArtifactRef, ...],
    attempt_refs: tuple[ArtifactRef, ...],
) -> None:
    _assert_preview_protection_matches(
        unit_of_work,
        workspace_id=workspace_id,
        preview_operation_id=preview_operation_id,
        expected_refs=expected_refs,
    )
    required_ids = frozenset(ref.artifact_id for ref in attempt_refs)
    selected = tuple(ref for ref in expected_refs if ref.artifact_id in required_ids)
    if frozenset(ref.artifact_id for ref in selected) != required_ids:
        raise PreviewBindingConflict("protected artifact refs do not cover attempt bindings")
    if selected:
        unit_of_work.set_artifact_protection(
            selected,
            owner_kind="submit-attempt",
            owner_id=submit_attempt_id,
            intent="submit-attempt",
        )
    unit_of_work.clear_artifact_protection(
        owner_kind="current-preview",
        owner_id=workspace_id,
    )
    unit_of_work.clear_artifact_protection(
        owner_kind="preview-operation",
        owner_id=preview_operation_id,
    )


def promote_finalize_artifact_protection(
    unit_of_work: SubmitControlTransaction,
    *,
    attempt: SubmitAttempt,
) -> None:
    unit_of_work.clear_artifact_protection(
        owner_kind="submit-attempt",
        owner_id=attempt.submit_attempt_id,
    )
    source_refs = tuple(
        ArtifactRef(
            artifact_id=artifact_id,
            media_type="application/octet-stream",
            size_bytes=0,
            raw_sha256=DigestRef(
                "sha256:0000000000000000000000000000000000000000000000000000000000000000"
            ),
        )
        for artifact_id in attempt.source_artifact_refs
    )
    if source_refs:
        unit_of_work.set_artifact_protection(
            source_refs,
            owner_kind="source-package",
            owner_id=attempt.submit_attempt_id,
            intent="source-package",
        )
    manifest_digest = attempt.canonicalization_manifest_digest
    if attempt.canonicalization_manifest_ref is not None and manifest_digest is not None:
        unit_of_work.set_artifact_protection(
            (
                ArtifactRef(
                    artifact_id=attempt.canonicalization_manifest_ref,
                    media_type="application/json",
                    size_bytes=0,
                    raw_sha256=DigestRef(manifest_digest),
                ),
            ),
            owner_kind="canonicalization-manifest",
            owner_id=attempt.submit_attempt_id,
            intent="canonicalization-manifest",
        )


def clear_attempt_artifact_protection(
    unit_of_work: SubmitControlTransaction,
    *,
    submit_attempt_id: str,
) -> None:
    unit_of_work.clear_artifact_protection(
        owner_kind="submit-attempt",
        owner_id=submit_attempt_id,
    )


def pin_prepare_import_artifacts(
    unit_of_work: SubmitControlTransaction,
    *,
    submit_attempt_id: str,
    manifest_ref: BackendArtifactRef,
    package_ref: BackendArtifactRef,
    existing_snapshot_refs: tuple[ArtifactRef, ...],
) -> None:
    refs = (
        *existing_snapshot_refs,
        ArtifactRef(
            artifact_id=manifest_ref.artifact_id,
            media_type=manifest_ref.media_type,
            size_bytes=manifest_ref.size_bytes,
            raw_sha256=DigestRef(manifest_ref.raw_sha256),
        ),
        ArtifactRef(
            artifact_id=package_ref.artifact_id,
            media_type=package_ref.media_type,
            size_bytes=package_ref.size_bytes,
            raw_sha256=DigestRef(package_ref.raw_sha256),
        ),
    )
    unit_of_work.set_artifact_protection(
        refs,
        owner_kind="submit-attempt",
        owner_id=submit_attempt_id,
        intent="submit-attempt",
    )


def _assert_rebuild_policy(build_input: PrepareImportBuildInput) -> None:
    if build_input.builder_mutation_policy is not BuilderMutationPolicy.REBUILD_ALWAYS:
        raise SubmitImportBuilderError("builder_mutation_policy must be REBUILD_ALWAYS")


def _assert_checkpoint_matches_build_input(
    *,
    checkpoint: PrepareImportCheckpoint,
    build_input: PrepareImportBuildInput,
) -> None:
    if checkpoint.attempt_id != build_input.submit_attempt_id:
        raise SubmitImportBuilderError("checkpoint attempt_id does not match build input")
    if checkpoint.input_closure_digest != build_input.input_closure_digest:
        raise SubmitImportBuilderError("checkpoint input closure digest does not match build input")
    if checkpoint.builder_mutation_policy is not build_input.builder_mutation_policy:
        raise SubmitImportBuilderError("checkpoint builder policy does not match build input")


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
