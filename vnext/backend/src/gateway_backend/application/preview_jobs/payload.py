"""Preview job payload, dependency contracts, and JobDefinition metadata."""

from __future__ import annotations

import json

from collections.abc import (
    Callable,
    Mapping,
)
from dataclasses import dataclass
from gateway_backend.application.job_definitions import (
    JobDefinition,
    NormalPublicationCapability,
)
from gateway_backend.application.job_steps import (
    require_non_empty_str,
    successor_step_id,
)
from gateway_backend.application.payloads import (
    PayloadDecodeError,
    load_job_payload_bytes,
)
from gateway_backend.application.preview_job_identity import (
    PREVIEW_JOB_CONTRACT_VERSION,
    PREVIEW_JOB_KIND,
    PREVIEW_STEP_MATERIALIZE,
)
from gateway_backend.application.recovery import RecoveryCapability
from gateway_backend.application.workspace.ports import (
    WorkspaceControlTransaction as PreviewControlTransaction,
)
from gateway_backend.artifacts.computation_cache import ComputationCachePort
from gateway_backend.artifacts.snapshot_table_export_cache import SnapshotTableExportCachePort
from gateway_backend.artifacts.store import ArtifactStorePort
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    RepositoryTableAccessProvider,
)
from gateway_backend.domain.workspace.models import (
    InputCompleteness,
    SourceArtifactBinding,
    SourceArtifactRole,
)
from gateway_backend.domain.workspace.ports import BaselineHeadReadPort
from gateway_backend.operations.contracts import (
    JobStepKey,
    OperationDiagnosticDetail,
    OperationRecord,
)
from gateway_shared_kernel import DigestRef
from typing import (
    ContextManager,
    cast,
)

PREVIEW_STEP_ASSEMBLE = "assemble_preview"

PREVIEW_STEP_PUBLISH = "publish_preview"

PREVIEW_MATERIALIZE_DECODER = "backend-vnext/preview/materialize/decoder/v1"

PREVIEW_ASSEMBLE_DECODER = "backend-vnext/preview/assemble/decoder/v1"

PREVIEW_PUBLISH_DECODER = "backend-vnext/preview/publish/decoder/v1"

PREVIEW_MATERIALIZE_HANDLER = "backend-vnext/preview/materialize/handler/v1"

PREVIEW_ASSEMBLE_HANDLER = "backend-vnext/preview/assemble/handler/v1"

PREVIEW_PUBLISH_HANDLER = "backend-vnext/preview/publish/handler/v1"

_JCS_MEDIA_TYPE = "application/jcs"

_SIDE_BASELINE = "BASELINE"

_SIDE_INITIAL = "INITIAL"

_SIDE_MODIFIED = "MODIFIED"

_PAIR_BASELINE_TO_INITIAL = "baseline_to_initial"

_PAIR_INITIAL_TO_MODIFIED = "initial_to_modified"

class PreviewJobError(ValueError):
    """Bounded preview job failure surfaced to the operation runtime."""

    def __init__(
        self,
        message: str,
        *,
        diagnostic_code: str | None = None,
        diagnostic_details: tuple[OperationDiagnosticDetail, ...] | None = None,
        diagnostic_omitted_count: int = 0,
    ) -> None:
        super().__init__(message)
        self.diagnostic_code = diagnostic_code
        if diagnostic_details is None:
            if diagnostic_omitted_count != 0:
                raise ValueError("diagnostic_omitted_count requires diagnostic_details")
            self.diagnostic_details = None
            self.diagnostic_omitted_count = 0
            return
        ordered_details = tuple(
            sorted(diagnostic_details, key=_operation_diagnostic_detail_sort_key)
        )
        self.diagnostic_details = ordered_details[:100]
        self.diagnostic_omitted_count = diagnostic_omitted_count + max(
            0,
            len(ordered_details) - 100,
        )

def _operation_diagnostic_detail_sort_key(
    detail: OperationDiagnosticDetail,
) -> tuple[str, str, str, str]:
    return (
        detail.side.value,
        "" if detail.table_name is None else detail.table_name,
        "" if detail.column_name is None else detail.column_name,
        detail.code,
    )

@dataclass(frozen=True, slots=True)
class PreviewIdempotencyIdentity:
    workspace_id: str
    idempotency_key: str

@dataclass(frozen=True, slots=True)
class PreviewJobPayload:
    workspace_id: str
    upload_revision_id: str
    generation: int
    repository_id: str
    business_baseline_node_id: str
    business_baseline_commit_id: str
    baseline_head_version: int
    input_completeness: InputCompleteness
    source_artifacts: Mapping[SourceArtifactRole, SourceArtifactBinding]
    source_digests: Mapping[str, str]
    input_digest: str
    ruleset_version: str
    comparison_ruleset_digest: str
    capability_contract_versions: Mapping[str, object]
    provider_versions: Mapping[str, str]
    ready_closure_contract_version: str
    idempotency_identity: PreviewIdempotencyIdentity
    options: Mapping[str, object]

PreviewControlTransactionFactory = Callable[[], ContextManager[PreviewControlTransaction]]

RepositoryProviderFactory = Callable[[str, str], RepositoryTableAccessProvider]

@dataclass(frozen=True, slots=True)
class PreviewRuntimeDependencies:
    artifact_store: ArtifactStorePort
    repository_provider_factory: RepositoryProviderFactory
    baseline_head_read: BaselineHeadReadPort
    control_transaction_factory: PreviewControlTransactionFactory
    snapshot_export_cache: SnapshotTableExportCachePort | None = None
    computation_cache: ComputationCachePort | None = None

def preview_materialize_job_definition() -> JobDefinition:
    return JobDefinition(
        key=JobStepKey(job_kind=PREVIEW_JOB_KIND, step_name=PREVIEW_STEP_MATERIALIZE),
        supported_payload_versions=frozenset({PREVIEW_JOB_CONTRACT_VERSION}),
        decoder_identity=PREVIEW_MATERIALIZE_DECODER,
        handler_identity=PREVIEW_MATERIALIZE_HANDLER,
        publication_capability=NormalPublicationCapability.SINGLE_SUCCESSOR,
        recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
    )

def preview_assemble_job_definition() -> JobDefinition:
    return JobDefinition(
        key=JobStepKey(job_kind=PREVIEW_JOB_KIND, step_name=PREVIEW_STEP_ASSEMBLE),
        supported_payload_versions=frozenset({PREVIEW_JOB_CONTRACT_VERSION}),
        decoder_identity=PREVIEW_ASSEMBLE_DECODER,
        handler_identity=PREVIEW_ASSEMBLE_HANDLER,
        publication_capability=NormalPublicationCapability.SINGLE_SUCCESSOR,
        recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
    )

def preview_publish_job_definition() -> JobDefinition:
    return JobDefinition(
        key=JobStepKey(job_kind=PREVIEW_JOB_KIND, step_name=PREVIEW_STEP_PUBLISH),
        supported_payload_versions=frozenset({PREVIEW_JOB_CONTRACT_VERSION}),
        decoder_identity=PREVIEW_PUBLISH_DECODER,
        handler_identity=PREVIEW_PUBLISH_HANDLER,
        publication_capability=NormalPublicationCapability.TERMINAL,
        recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
    )

def decode_preview_payload(payload_object: dict[str, object]) -> PreviewJobPayload:
    _reject_unknown_top_level_keys(payload_object)
    workspace_id = require_non_empty_str(payload_object, "workspace_id")
    upload_revision_id = require_non_empty_str(payload_object, "upload_revision_id")
    generation = _require_non_negative_int(payload_object, "generation")
    repository_id = require_non_empty_str(payload_object, "repository_id")
    business_baseline_node_id = require_non_empty_str(payload_object, "business_baseline_node_id")
    business_baseline_commit_id = require_non_empty_str(
        payload_object, "business_baseline_commit_id"
    )
    baseline_head_version = _require_non_negative_int(payload_object, "baseline_head_version")
    input_completeness = _decode_input_completeness(payload_object.get("input_completeness"))
    source_artifacts = _decode_source_artifacts(payload_object.get("source_artifacts"))
    source_digests = _decode_string_map(
        payload_object.get("source_digests"), label="source_digests"
    )
    input_digest = require_non_empty_str(payload_object, "input_digest")
    ruleset_version = require_non_empty_str(payload_object, "ruleset_version")
    comparison_ruleset_digest = require_non_empty_str(payload_object, "comparison_ruleset_digest")
    capability_contract_versions = _decode_object_map(
        payload_object.get("capability_contract_versions"),
        label="capability_contract_versions",
    )
    from gateway_backend.application.preview_semantics import current_preview_capabilities

    if capability_contract_versions != current_preview_capabilities():
        raise PayloadDecodeError(
            "preview capability versions do not match current semantics",
            code="PAYLOAD_SHAPE_INVALID",
        )
    provider_versions = _decode_string_map(
        payload_object.get("provider_versions"), label="provider_versions"
    )
    ready_closure_contract_version = require_non_empty_str(
        payload_object,
        "ready_closure_contract_version",
    )
    idempotency_identity = _decode_idempotency_identity(payload_object.get("idempotency_identity"))
    options = _decode_object_map(payload_object.get("options"), label="options")
    _validate_role_closure(input_completeness, source_artifacts)
    return PreviewJobPayload(
        workspace_id=workspace_id,
        upload_revision_id=upload_revision_id,
        generation=generation,
        repository_id=repository_id,
        business_baseline_node_id=business_baseline_node_id,
        business_baseline_commit_id=business_baseline_commit_id,
        baseline_head_version=baseline_head_version,
        input_completeness=input_completeness,
        source_artifacts=source_artifacts,
        source_digests=source_digests,
        input_digest=input_digest,
        ruleset_version=ruleset_version,
        comparison_ruleset_digest=comparison_ruleset_digest,
        capability_contract_versions=capability_contract_versions,
        provider_versions=dict(provider_versions),
        ready_closure_contract_version=ready_closure_contract_version,
        idempotency_identity=idempotency_identity,
        options=options,
    )

def _load_preview_payload(
    operation: OperationRecord, store: ArtifactStorePort
) -> PreviewJobPayload:
    payload_bytes = load_job_payload_bytes(operation, store)
    try:
        payload_object = json.loads(payload_bytes)
    except (TypeError, UnicodeDecodeError, ValueError) as exc:
        raise PayloadDecodeError(
            "job_payload must be canonical JSON bytes",
            code="PAYLOAD_SHAPE_INVALID",
        ) from exc
    if type(payload_object) is not dict:
        raise PayloadDecodeError("job_payload must be a JSON object", code="PAYLOAD_SHAPE_INVALID")
    return decode_preview_payload(cast(dict[str, object], payload_object))

def _artifact_ref_from_binding(binding: SourceArtifactBinding) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=binding.artifact_id,
        media_type=binding.media_type,
        size_bytes=binding.size_bytes,
        raw_sha256=DigestRef(binding.raw_sha256),
    )

_PREVIEW_STEP_SUFFIX: dict[str, str] = {
    PREVIEW_STEP_MATERIALIZE: "1",
    PREVIEW_STEP_ASSEMBLE: "2",
    PREVIEW_STEP_PUBLISH: "3",
}

def _successor_step_id(operation_id: str, step_name: str) -> str:
    return successor_step_id(operation_id, step_name, _PREVIEW_STEP_SUFFIX)

_ALLOWED_PAYLOAD_KEYS = frozenset(
    {
        "workspace_id",
        "upload_revision_id",
        "generation",
        "repository_id",
        "business_baseline_node_id",
        "business_baseline_commit_id",
        "baseline_head_version",
        "input_completeness",
        "source_artifacts",
        "source_digests",
        "input_digest",
        "ruleset_version",
        "comparison_ruleset_digest",
        "capability_contract_versions",
        "provider_versions",
        "ready_closure_contract_version",
        "idempotency_identity",
        "options",
    }
)

def _reject_unknown_top_level_keys(payload_object: dict[str, object]) -> None:
    unknown = sorted(set(payload_object) - _ALLOWED_PAYLOAD_KEYS)
    if unknown:
        raise PayloadDecodeError(
            f"unknown preview payload keys: {', '.join(unknown)}",
            code="PAYLOAD_SHAPE_INVALID",
        )

def _require_non_negative_int(payload_object: dict[str, object], key: str) -> int:
    value = payload_object.get(key)
    if type(value) is not int or isinstance(value, bool) or value < 0:
        raise PayloadDecodeError(f"{key} must be a non-negative int", code="PAYLOAD_SHAPE_INVALID")
    return value

def _decode_input_completeness(value: object) -> InputCompleteness:
    if type(value) is not str:
        raise PayloadDecodeError(
            "input_completeness must be a string", code="PAYLOAD_SHAPE_INVALID"
        )
    try:
        return InputCompleteness(value)
    except ValueError as exc:
        raise PayloadDecodeError(
            "input_completeness is invalid", code="PAYLOAD_SHAPE_INVALID"
        ) from exc

def _decode_source_artifacts(value: object) -> dict[SourceArtifactRole, SourceArtifactBinding]:
    if type(value) is not dict:
        raise PayloadDecodeError("source_artifacts must be an object", code="PAYLOAD_SHAPE_INVALID")
    decoded: dict[SourceArtifactRole, SourceArtifactBinding] = {}
    for role_name, binding_payload in value.items():
        if type(role_name) is not str:
            raise PayloadDecodeError(
                "source_artifacts role must be a string", code="PAYLOAD_SHAPE_INVALID"
            )
        if type(binding_payload) is not dict:
            raise PayloadDecodeError(
                "source artifact binding must be an object", code="PAYLOAD_SHAPE_INVALID"
            )
        decoded[SourceArtifactRole(role_name)] = SourceArtifactBinding(
            artifact_id=str(binding_payload["artifact_id"]),
            media_type=str(binding_payload["media_type"]),
            size_bytes=int(binding_payload["size_bytes"]),
            raw_sha256=str(binding_payload["raw_sha256"]),
        )
    return decoded

def _decode_string_map(value: object, *, label: str) -> dict[str, str]:
    if type(value) is not dict:
        raise PayloadDecodeError(f"{label} must be an object", code="PAYLOAD_SHAPE_INVALID")
    decoded: dict[str, str] = {}
    for key, item in value.items():
        if type(key) is not str or type(item) is not str:
            raise PayloadDecodeError(f"{label} must be a string map", code="PAYLOAD_SHAPE_INVALID")
        decoded[key] = item
    return decoded

def _decode_object_map(value: object, *, label: str) -> dict[str, object]:
    if type(value) is not dict:
        raise PayloadDecodeError(f"{label} must be an object", code="PAYLOAD_SHAPE_INVALID")
    return dict(value)

def _decode_idempotency_identity(value: object) -> PreviewIdempotencyIdentity:
    if type(value) is not dict:
        raise PayloadDecodeError(
            "idempotency_identity must be an object", code="PAYLOAD_SHAPE_INVALID"
        )
    return PreviewIdempotencyIdentity(
        workspace_id=require_non_empty_str(value, "workspace_id"),
        idempotency_key=require_non_empty_str(value, "idempotency_key"),
    )

def _validate_role_closure(
    input_completeness: InputCompleteness,
    source_artifacts: Mapping[SourceArtifactRole, SourceArtifactBinding],
) -> None:
    if input_completeness is InputCompleteness.FULL:
        if (
            SourceArtifactRole.INITIAL not in source_artifacts
            or SourceArtifactRole.MODIFIED not in source_artifacts
        ):
            raise PayloadDecodeError(
                "FULL preview requires INITIAL and MODIFIED source artifacts",
                code="PAYLOAD_SHAPE_INVALID",
            )
    elif input_completeness is InputCompleteness.MODIFIED_ONLY:
        if SourceArtifactRole.INITIAL in source_artifacts:
            raise PayloadDecodeError(
                "MODIFIED_ONLY preview forbids INITIAL source artifact",
                code="PAYLOAD_SHAPE_INVALID",
            )
        if SourceArtifactRole.MODIFIED not in source_artifacts:
            raise PayloadDecodeError(
                "MODIFIED_ONLY preview requires MODIFIED source artifact",
                code="PAYLOAD_SHAPE_INVALID",
            )


__all__ = [
    "PREVIEW_STEP_ASSEMBLE",
    "PREVIEW_STEP_PUBLISH",
    "PREVIEW_MATERIALIZE_DECODER",
    "PREVIEW_ASSEMBLE_DECODER",
    "PREVIEW_PUBLISH_DECODER",
    "PREVIEW_MATERIALIZE_HANDLER",
    "PREVIEW_ASSEMBLE_HANDLER",
    "PREVIEW_PUBLISH_HANDLER",
    "PreviewJobError",
    "PreviewIdempotencyIdentity",
    "PreviewJobPayload",
    "PreviewControlTransactionFactory",
    "RepositoryProviderFactory",
    "PreviewRuntimeDependencies",
    "preview_materialize_job_definition",
    "preview_assemble_job_definition",
    "preview_publish_job_definition",
    "decode_preview_payload",
]
