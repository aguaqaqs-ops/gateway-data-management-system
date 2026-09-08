"""Workspace domain records and read-model helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class WorkspaceState(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class InputCompleteness(StrEnum):
    FULL = "FULL"
    MODIFIED_ONLY = "MODIFIED_ONLY"


class SourceArtifactRole(StrEnum):
    INITIAL = "INITIAL"
    MODIFIED = "MODIFIED"


class WorkspaceReadModelLabel(StrEnum):
    EMPTY = "EMPTY"
    INPUT_READY = "INPUT_READY"
    PREVIEW_READY = "PREVIEW_READY"


@dataclass(frozen=True, slots=True)
class IdentityContext:
    actor_id: str
    gateway_device_external_key: str
    business_project_id: str
    permissions: frozenset[str]

    def __post_init__(self) -> None:
        if type(self.actor_id) is not str or not self.actor_id:
            raise ValueError("actor_id must be a non-empty string")
        if type(self.gateway_device_external_key) is not str or not self.gateway_device_external_key:
            raise ValueError("gateway_device_external_key must be a non-empty string")
        if type(self.business_project_id) is not str or not self.business_project_id:
            raise ValueError("business_project_id must be a non-empty string")
        if type(self.permissions) is not frozenset:
            raise ValueError("permissions must be a frozenset")


@dataclass(frozen=True, slots=True)
class WorkspaceScope:
    owner_actor_id: str
    gateway_device_external_key: str
    business_project_id: str

    def __post_init__(self) -> None:
        if type(self.owner_actor_id) is not str or not self.owner_actor_id:
            raise ValueError("owner_actor_id must be a non-empty string")
        if type(self.gateway_device_external_key) is not str or not self.gateway_device_external_key:
            raise ValueError("gateway_device_external_key must be a non-empty string")
        if type(self.business_project_id) is not str or not self.business_project_id:
            raise ValueError("business_project_id must be a non-empty string")


@dataclass(frozen=True, slots=True)
class BaselineHead:
    business_baseline_node_id: str
    business_baseline_commit_id: str
    baseline_head_version: int

    def __post_init__(self) -> None:
        if type(self.business_baseline_node_id) is not str or not self.business_baseline_node_id:
            raise ValueError("business_baseline_node_id must be a non-empty string")
        if type(self.business_baseline_commit_id) is not str or not self.business_baseline_commit_id:
            raise ValueError("business_baseline_commit_id must be a non-empty string")
        if type(self.baseline_head_version) is not int or self.baseline_head_version < 0:
            raise ValueError("baseline_head_version must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class ResolvedScope:
    repository_id: str
    baseline_head: BaselineHead

    def __post_init__(self) -> None:
        if type(self.repository_id) is not str or not self.repository_id:
            raise ValueError("repository_id must be a non-empty string")
        if type(self.baseline_head) is not BaselineHead:
            raise ValueError("baseline_head must be BaselineHead")


@dataclass(frozen=True, slots=True)
class SourceArtifactBinding:
    artifact_id: str
    media_type: str
    size_bytes: int
    raw_sha256: str

    def __post_init__(self) -> None:
        if type(self.artifact_id) is not str or not self.artifact_id:
            raise ValueError("artifact_id must be a non-empty string")
        if type(self.media_type) is not str or not self.media_type:
            raise ValueError("media_type must be a non-empty string")
        if type(self.size_bytes) is not int or self.size_bytes < 0:
            raise ValueError("size_bytes must be a non-negative integer")
        if type(self.raw_sha256) is not str or not self.raw_sha256:
            raise ValueError("raw_sha256 must be a non-empty string")


@dataclass(frozen=True, slots=True)
class Workspace:
    workspace_id: str
    owner_actor_id: str
    gateway_device_external_key: str
    business_project_id: str
    repository_id: str
    state: WorkspaceState
    generation: int
    optimistic_version: int
    current_upload_revision_id: str | None
    current_preview_result_id: str | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None

    def __post_init__(self) -> None:
        if type(self.workspace_id) is not str or not self.workspace_id:
            raise ValueError("workspace_id must be a non-empty string")
        if type(self.owner_actor_id) is not str or not self.owner_actor_id:
            raise ValueError("owner_actor_id must be a non-empty string")
        if type(self.gateway_device_external_key) is not str or not self.gateway_device_external_key:
            raise ValueError("gateway_device_external_key must be a non-empty string")
        if type(self.business_project_id) is not str or not self.business_project_id:
            raise ValueError("business_project_id must be a non-empty string")
        if type(self.repository_id) is not str or not self.repository_id:
            raise ValueError("repository_id must be a non-empty string")
        if type(self.state) is not WorkspaceState:
            raise ValueError("state must be WorkspaceState")
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError("generation must be a non-negative integer")
        if type(self.optimistic_version) is not int or self.optimistic_version < 0:
            raise ValueError("optimistic_version must be a non-negative integer")
        if self.current_upload_revision_id is not None and (
            type(self.current_upload_revision_id) is not str or not self.current_upload_revision_id
        ):
            raise ValueError("current_upload_revision_id must be a non-empty string or None")
        if self.current_preview_result_id is not None and (
            type(self.current_preview_result_id) is not str or not self.current_preview_result_id
        ):
            raise ValueError("current_preview_result_id must be a non-empty string or None")
        if type(self.created_at) is not datetime:
            raise ValueError("created_at must be datetime")
        if type(self.updated_at) is not datetime:
            raise ValueError("updated_at must be datetime")
        if self.closed_at is not None and type(self.closed_at) is not datetime:
            raise ValueError("closed_at must be datetime or None")

    @property
    def scope(self) -> WorkspaceScope:
        return WorkspaceScope(
            owner_actor_id=self.owner_actor_id,
            gateway_device_external_key=self.gateway_device_external_key,
            business_project_id=self.business_project_id,
        )


@dataclass(frozen=True, slots=True)
class UploadRevision:
    upload_revision_id: str
    workspace_id: str
    generation: int
    input_completeness: InputCompleteness
    source_artifacts: Mapping[SourceArtifactRole, SourceArtifactBinding]
    idempotency_key: str
    request_fingerprint: str
    created_by: str
    created_at: datetime

    def __post_init__(self) -> None:
        if type(self.upload_revision_id) is not str or not self.upload_revision_id:
            raise ValueError("upload_revision_id must be a non-empty string")
        if type(self.workspace_id) is not str or not self.workspace_id:
            raise ValueError("workspace_id must be a non-empty string")
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError("generation must be a non-negative integer")
        if type(self.input_completeness) is not InputCompleteness:
            raise ValueError("input_completeness must be InputCompleteness")
        if type(self.source_artifacts) is not dict:
            raise ValueError("source_artifacts must be a mapping")
        if type(self.idempotency_key) is not str or not self.idempotency_key:
            raise ValueError("idempotency_key must be a non-empty string")
        if type(self.request_fingerprint) is not str or not self.request_fingerprint:
            raise ValueError("request_fingerprint must be a non-empty string")
        if type(self.created_by) is not str or not self.created_by:
            raise ValueError("created_by must be a non-empty string")
        if type(self.created_at) is not datetime:
            raise ValueError("created_at must be datetime")


@dataclass(frozen=True, slots=True)
class PreviewResultDigests:
    source_digest: str
    input_digest: str
    snapshot_digest: str
    comparison_digest: str
    risk_digest: str
    surface_digest: str
    bundle_digest: str

    def __post_init__(self) -> None:
        for field_name in (
            "source_digest",
            "input_digest",
            "snapshot_digest",
            "comparison_digest",
            "risk_digest",
            "surface_digest",
            "bundle_digest",
        ):
            value = getattr(self, field_name)
            if type(value) is not str or not value:
                raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True, slots=True)
class PreviewResult:
    preview_result_id: str
    workspace_id: str
    upload_revision_id: str
    generation: int
    repository_id: str
    business_baseline_node_id: str
    business_baseline_commit_id: str
    baseline_head_version: int
    ruleset_version: str
    contract_version: str
    provider_versions: Mapping[str, str]
    digests: PreviewResultDigests
    bundle_artifact_id: str
    ready_closure_artifact_id: str
    operation_id: str
    created_at: datetime

    def __post_init__(self) -> None:
        if type(self.preview_result_id) is not str or not self.preview_result_id:
            raise ValueError("preview_result_id must be a non-empty string")
        if type(self.workspace_id) is not str or not self.workspace_id:
            raise ValueError("workspace_id must be a non-empty string")
        if type(self.upload_revision_id) is not str or not self.upload_revision_id:
            raise ValueError("upload_revision_id must be a non-empty string")
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError("generation must be a non-negative integer")
        if type(self.repository_id) is not str or not self.repository_id:
            raise ValueError("repository_id must be a non-empty string")
        if type(self.business_baseline_node_id) is not str or not self.business_baseline_node_id:
            raise ValueError("business_baseline_node_id must be a non-empty string")
        if type(self.business_baseline_commit_id) is not str or not self.business_baseline_commit_id:
            raise ValueError("business_baseline_commit_id must be a non-empty string")
        if type(self.baseline_head_version) is not int or self.baseline_head_version < 0:
            raise ValueError("baseline_head_version must be a non-negative integer")
        if type(self.ruleset_version) is not str or not self.ruleset_version:
            raise ValueError("ruleset_version must be a non-empty string")
        if type(self.contract_version) is not str or not self.contract_version:
            raise ValueError("contract_version must be a non-empty string")
        if type(self.provider_versions) is not dict:
            raise ValueError("provider_versions must be a mapping")
        if type(self.digests) is not PreviewResultDigests:
            raise ValueError("digests must be PreviewResultDigests")
        if type(self.bundle_artifact_id) is not str or not self.bundle_artifact_id:
            raise ValueError("bundle_artifact_id must be a non-empty string")
        if type(self.ready_closure_artifact_id) is not str or not self.ready_closure_artifact_id:
            raise ValueError("ready_closure_artifact_id must be a non-empty string")
        if type(self.operation_id) is not str or not self.operation_id:
            raise ValueError("operation_id must be a non-empty string")
        if type(self.created_at) is not datetime:
            raise ValueError("created_at must be datetime")


def derive_read_model_label(workspace: Workspace) -> WorkspaceReadModelLabel:
    if workspace.current_preview_result_id is not None:
        return WorkspaceReadModelLabel.PREVIEW_READY
    if workspace.current_upload_revision_id is not None:
        return WorkspaceReadModelLabel.INPUT_READY
    return WorkspaceReadModelLabel.EMPTY
