"""Submit import builder and artifact protection helpers."""

from __future__ import annotations

from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.application.submission.contracts import (
    PrepareImportBuildInput,
    PrepareImportCheckpoint,
    PrepareImportPublicationResult,
    SubmitImportPublicationPort,
)
from gateway_backend.application.submission.ports import SubmitControlTransaction
from gateway_backend.artifacts.store import ArtifactStorePort
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.submission.models import (
    BackendArtifactRef,
    BuilderMutationPolicy,
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
    package_payload = publication.read_back_package(checkpoint=checkpoint, store=store)
    if raw_blob_digest(package_payload).value != checkpoint.package_raw_sha256:
        raise SubmitImportBuilderError("checkpoint package raw SHA does not match read-back")
    try:
        publication.verify_checkpoint_semantic_binding(checkpoint=checkpoint, store=store)
    except ValueError as exc:
        raise SubmitImportBuilderError(str(exc)) from exc
    return PrepareImportPublicationResult(checkpoint=checkpoint, replay=True)


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
