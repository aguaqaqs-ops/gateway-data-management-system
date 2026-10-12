"""Submit import builder and artifact protection helpers."""

from __future__ import annotations

import json
from collections.abc import Callable

from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.submission.contracts import (
    PrepareImportBuildInput,
    PrepareImportCheckpoint,
    PrepareImportPublicationResult,
    SnapshotTableBinding,
    SubmitImportPublicationPort,
)
from gateway_backend.application.submission.ports import SubmitControlTransaction
from gateway_backend.artifacts.store import ArtifactStorePort
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.artifacts.serialize import artifact_ref_from_dict
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.snapshot_materialization import manifest_from_bytes
from gateway_backend.capabilities.storage_projection import (
    CanonicalizationManifest,
    MAX_MANIFEST_JSON_BYTES,
    canonicalization_manifest_from_bytes,
)
from gateway_backend.domain.submission.models import (
    BackendArtifactRef,
    BuilderMutationPolicy,
)


class SubmitImportBuilderError(ValueError):
    """Raised when submit import builder input or reuse is invalid."""


def resolve_canonical_snapshot_bindings(
    *,
    operation_artifact_refs: tuple[ArtifactRef, ...],
    canonical_table_set_closure_ref: str,
    canonical_table_set_closure_digest: str,
    canonicalization_manifest_ref: str,
    canonicalization_manifest_digest: str,
    read_artifact: Callable[[ArtifactRef], bytes],
) -> tuple[tuple[SnapshotTableBinding, ...], tuple[ArtifactRef, ...]]:
    """Resolve prepare inputs from Preview's frozen canonical closure and manifest."""
    refs_by_id = {ref.artifact_id: ref for ref in operation_artifact_refs}
    if len(refs_by_id) != len(operation_artifact_refs):
        raise SubmitImportBuilderError("operation has duplicate artifact references")
    closure_ref = _required_exact_ref(refs_by_id, canonical_table_set_closure_ref)
    manifest_ref = _required_exact_ref(refs_by_id, canonicalization_manifest_ref)
    closure_bytes = _read_bounded_artifact(read_artifact, closure_ref)
    if raw_blob_digest(closure_bytes).value != canonical_table_set_closure_digest:
        raise SubmitImportBuilderError("canonical table closure raw SHA does not match attempt")
    closure = _parse_canonical_table_closure(closure_bytes)
    manifest = _read_canonicalization_manifest(read_artifact, manifest_ref)
    if manifest.manifest_digest is None or manifest.manifest_digest.value != canonicalization_manifest_digest:
        raise SubmitImportBuilderError("canonicalization manifest digest does not match attempt")

    expected_tables = {table.name for table in manifest.tables}
    closure_tables = {name for name, _ref in closure}
    if expected_tables != closure_tables:
        raise SubmitImportBuilderError("canonical table closure does not match canonical manifest")

    bindings: list[SnapshotTableBinding] = []
    all_refs: dict[str, ArtifactRef] = {
        closure_ref.artifact_id: closure_ref,
        manifest_ref.artifact_id: manifest_ref,
    }
    for table_name, embedded_ref in closure:
        table_manifest_ref = _require_embedded_ref(refs_by_id, embedded_ref)
        table_manifest_bytes = _read_bounded_artifact(read_artifact, table_manifest_ref)
        try:
            table_manifest = manifest_from_bytes(table_manifest_bytes)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise SubmitImportBuilderError(
                f"canonical table manifest for {table_name!r} is corrupt"
            ) from exc
        if table_manifest.table_name != table_name:
            raise SubmitImportBuilderError("canonical table manifest name does not match closure")
        bindings.append(
            SnapshotTableBinding(
                artifact_id=table_manifest_ref.artifact_id,
                media_type=table_manifest_ref.media_type,
                size_bytes=table_manifest_ref.size_bytes,
                raw_sha256=table_manifest_ref.raw_sha256.value,
            )
        )
        all_refs[table_manifest_ref.artifact_id] = table_manifest_ref
        for row_ref in table_manifest.row_file_refs:
            exact_row_ref = _require_embedded_ref(refs_by_id, row_ref)
            all_refs[exact_row_ref.artifact_id] = exact_row_ref

    return tuple(bindings), tuple(all_refs[key] for key in sorted(all_refs))


def _required_exact_ref(refs_by_id: dict[str, ArtifactRef], artifact_id: str) -> ArtifactRef:
    ref = refs_by_id.get(artifact_id)
    if ref is None:
        raise SubmitImportBuilderError(f"operation artifact refs do not include {artifact_id!r}")
    return ref


def _require_embedded_ref(
    refs_by_id: dict[str, ArtifactRef],
    embedded_ref: ArtifactRef,
) -> ArtifactRef:
    current = _required_exact_ref(refs_by_id, embedded_ref.artifact_id)
    if current != embedded_ref:
        raise SubmitImportBuilderError(
            f"operation artifact ref {embedded_ref.artifact_id!r} does not match frozen closure"
        )
    return current


def _read_bounded_artifact(read_artifact: Callable[[ArtifactRef], bytes], ref: ArtifactRef) -> bytes:
    if ref.size_bytes > MAX_MANIFEST_JSON_BYTES:
        raise SubmitImportBuilderError("canonical artifact manifest exceeds size limit")
    try:
        payload = read_artifact(ref)
    except (ManifestVerificationError, OSError) as exc:
        raise SubmitImportBuilderError("canonical artifact is unavailable") from exc
    if type(payload) is not bytes or len(payload) != ref.size_bytes:
        raise SubmitImportBuilderError("canonical artifact size does not match artifact ref")
    if raw_blob_digest(payload).value != ref.raw_sha256.value:
        raise SubmitImportBuilderError("canonical artifact raw SHA does not match artifact ref")
    return payload


def _parse_canonical_table_closure(payload: bytes) -> tuple[tuple[str, ArtifactRef], ...]:
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SubmitImportBuilderError("canonical table closure is invalid JSON") from exc
    if type(document) is not dict or set(document) != {"contract_version", "tables"}:
        raise SubmitImportBuilderError("canonical table closure has an invalid shape")
    if document["contract_version"] != "backend-vnext/preview/canonical-table-set-closure/v1":
        raise SubmitImportBuilderError("canonical table closure contract is unsupported")
    if canonicalize_json_value(document) != payload:
        raise SubmitImportBuilderError("canonical table closure is not canonical JSON")
    tables = document["tables"]
    if type(tables) is not list:
        raise SubmitImportBuilderError("canonical table closure tables must be an array")
    result: list[tuple[str, ArtifactRef]] = []
    seen: set[str] = set()
    prior_name: bytes | None = None
    for item in tables:
        if type(item) is not dict or set(item) != {"table_name", "manifest_ref"}:
            raise SubmitImportBuilderError("canonical table closure entry has an invalid shape")
        table_name = item["table_name"]
        if type(table_name) is not str or not table_name or table_name in seen:
            raise SubmitImportBuilderError("canonical table closure names must be unique")
        encoded_name = table_name.encode("utf-8")
        if prior_name is not None and encoded_name <= prior_name:
            raise SubmitImportBuilderError("canonical table closure names must be sorted")
        prior_name = encoded_name
        seen.add(table_name)
        manifest_ref_payload = item["manifest_ref"]
        if type(manifest_ref_payload) is not dict:
            raise SubmitImportBuilderError("canonical table manifest ref must be an object")
        try:
            manifest_ref = artifact_ref_from_dict(manifest_ref_payload)
        except (ValueError, TypeError, KeyError) as exc:
            raise SubmitImportBuilderError("canonical table manifest ref is invalid") from exc
        result.append((table_name, manifest_ref))
    return tuple(result)


def _read_canonicalization_manifest(
    read_artifact: Callable[[ArtifactRef], bytes],
    ref: ArtifactRef,
) -> CanonicalizationManifest:
    payload = _read_bounded_artifact(read_artifact, ref)
    try:
        return canonicalization_manifest_from_bytes(payload)
    except ValueError as exc:
        raise SubmitImportBuilderError("canonicalization manifest is corrupt") from exc


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
