"""Application command and result contracts for workspace use cases."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from gateway_backend.domain.workspace.models import (
    BaselineHead,
    IdentityContext,
    InputCompleteness,
    PreviewAcceptanceRecord,
    PreviewResult,
    SourceArtifactBinding,
    SourceArtifactRole,
    UploadRevision,
    Workspace,
)
from gateway_backend.capabilities.table_rules.contracts import RULESET_VERSION
from gateway_backend.settings import (
    FIXED_UPLOAD_MAX_COMPRESSED_BYTES,
    FIXED_UPLOAD_STREAM_TIMEOUT_SECONDS,
)
from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

# Frozen into preview job payload at accept time; must match table_rules RULESET_VERSION.
PREVIEW_FROZEN_RULESET_VERSION = RULESET_VERSION


@dataclass(frozen=True, slots=True)
class CreateOrGetWorkspaceResult:
    workspace: Workspace
    replay: bool


@dataclass(frozen=True, slots=True)
class AcceptUploadCommand:
    context: IdentityContext
    workspace_id: str
    expected_workspace_version: int
    idempotency_key: str
    input_completeness: InputCompleteness
    source_artifacts: Mapping[SourceArtifactRole, SourceArtifactBinding]
    now: datetime


@dataclass(frozen=True, slots=True)
class AcceptUploadResult:
    workspace: Workspace
    revision: UploadRevision
    replay: bool


@dataclass(frozen=True, slots=True)
class StartPreviewCommand:
    context: IdentityContext
    workspace_id: str
    expected_workspace_version: int
    upload_revision_id: str
    generation: int
    expected_baseline_node_id: str
    expected_baseline_head_version: int
    idempotency_key: str
    request_fingerprint: str


@dataclass(frozen=True, slots=True)
class StartPreviewValidationResult:
    workspace: Workspace
    upload_revision: UploadRevision
    baseline_head: BaselineHead
    replay: bool
    prior_acceptance: PreviewAcceptanceRecord | None


@dataclass(frozen=True, slots=True)
class PreviewReadState:
    result: PreviewResult
    derived_stale: bool
    submit_forbidden: bool


def compute_upload_request_fingerprint(
    *,
    scope_owner_actor_id: str,
    scope_gateway_device_external_key: str,
    scope_business_project_id: str,
    expected_workspace_version: int,
    input_completeness: InputCompleteness,
    source_artifacts: Mapping[SourceArtifactRole, SourceArtifactBinding],
) -> str:
    artifact_payload = {
        role.value: {
            "media_type": binding.media_type,
            "size_bytes": binding.size_bytes,
            "raw_sha256": binding.raw_sha256,
        }
        for role, binding in sorted(source_artifacts.items(), key=lambda item: item[0].value)
    }
    payload = {
        "owner_actor_id": scope_owner_actor_id,
        "gateway_device_external_key": scope_gateway_device_external_key,
        "business_project_id": scope_business_project_id,
        "expected_workspace_version": expected_workspace_version,
        "input_completeness": input_completeness.value,
        "source_artifacts": artifact_payload,
    }
    return raw_blob_digest(canonicalize_json_value(payload)).value


def compute_preview_request_fingerprint(
    *,
    workspace_id: str,
    expected_workspace_version: int,
    upload_revision_id: str,
    generation: int,
    expected_baseline_node_id: str,
    expected_baseline_head_version: int,
    request_fingerprint_seed: Mapping[str, object],
) -> str:
    payload = {
        "workspace_id": workspace_id,
        "expected_workspace_version": expected_workspace_version,
        "upload_revision_id": upload_revision_id,
        "generation": generation,
        "expected_baseline_node_id": expected_baseline_node_id,
        "expected_baseline_head_version": expected_baseline_head_version,
        "request_fingerprint_seed": dict(sorted(request_fingerprint_seed.items())),
    }
    return raw_blob_digest(canonicalize_json_value(payload)).value
