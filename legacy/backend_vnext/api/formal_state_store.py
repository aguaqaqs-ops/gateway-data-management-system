from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import json
import tempfile
from threading import RLock


@dataclass
class GatewayDeviceRecord:
    gateway_device_id: str
    gateway_device_external_key: str
    display_name: str
    status: str
    business_project_id: str
    repo_key: str
    artifact_root_key: str
    updated_by_actor_id: str
    reason: str
    created_at: str
    updated_at: str


@dataclass
class BaselineBatchRecord:
    batch_id: str
    gateway_device_external_key: str
    batch_no: int
    base_main_hash: str
    baseline_kind: str
    status: str
    archive_gate_status: str
    opened_at: str
    current_main_hash: str | None = None
    closed_at: str | None = None
    invalidated_at: str | None = None
    idempotency_key: str | None = None
    workspace_confirmation_set_hash: str | None = None
    candidate_set_hash: str | None = None
    selected_modified_candidate_id: str | None = None
    selected_initial_candidate_ids: list[str] = field(default_factory=list)
    pending_review_submission_count: int = 0
    in_review_submission_count: int = 0
    approved_not_archived_submission_count: int = 0
    special_workspace_count: int = 0
    rejected_or_withdrawn_pending_confirmation_count: int = 0
    preview_pending_confirmation_count: int = 0
    initial_only_pending_confirmation_count: int = 0
    last_activity_at: str | None = None


@dataclass
class WorkspaceRecord:
    workspace_id: str
    gateway_device_external_key: str
    owner_actor_id: str
    business_project_id: str
    batch_id: str | None
    status: str
    upload_mode: str | None = None
    base_main_hash: str | None = None
    draft_commit_hash: str | None = None
    initial_commit_hash: str | None = None
    initial_configuration_generated_at: str | None = None
    initial_source_artifact_ref: dict[str, object] | None = None
    initial_source_package: dict[str, object] | None = None
    latest_preview: dict[str, object] | None = None
    latest_upload_semantics: str | None = None
    latest_baseline_source: dict[str, object] | None = None
    submitted_submission_id: str | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class PreviewBundleRecord:
    preview_bundle_id: str
    workspace_id: str
    owner_actor_id: str
    gateway_device_external_key: str
    tar_path: str
    bundle_root: str
    size_bytes: int
    sha256: str
    package_format: str
    created_at: str
    preview_refs: dict[str, object] = field(default_factory=dict)
    preview_input_binding: dict[str, object] = field(default_factory=dict)
    preview_source_package: dict[str, object] | None = None


@dataclass
class SubmitOperationRecord:
    submit_operation_id: str
    workspace_id: str
    submission_id: str
    preview_token: str
    preview_revision_id: str
    preview_strategy_manifest_ref: str
    preview_strategy_manifest_digest: str
    preview_bundle_digest: str
    source_artifact_ref: str | None
    source_artifact_payload_sha256: str | None
    final_modified_commit_hash: str | None
    status: str
    error_code: str | None
    created_at: str
    updated_at: str
    operation_payload: dict[str, object] = field(default_factory=dict)


@dataclass
class SubmissionRecord:
    submission_id: str
    workspace_id: str
    batch_id: str
    sequence_no: int
    submitter_actor_id: str
    preview_token: str
    baseline_kind: str
    base_main_hash: str
    initial_commit_hash: str | None
    modified_commit_hash: str
    preview_revision_id: str
    preview_strategy_manifest_ref: str
    preview_strategy_manifest_digest: str
    preview_bundle_digest: str
    preview_bundle_id: str
    baseline_alignment: str | None
    preview_manifest_ref: str
    preview_index_ref: str
    preview_bundle_root_ref: str
    status: str
    archive_status: str
    transfer_status: str | None
    submitted_at: str
    reviewed_at: str | None = None
    reviewed_by_actor_id: str | None = None
    withdrawn_at: str | None = None
    withdrawn_by_actor_id: str | None = None
    initial_configuration_generated_at: str | None = None
    configuration_generated_at: str | None = None
    initial_source_package: dict[str, object] = field(default_factory=dict)
    submit_source_package: dict[str, object] = field(default_factory=dict)
    snapshot_rows_artifact_ref: dict[str, object] | None = None
    snapshot_rows_artifact_stats: dict[str, object] = field(default_factory=dict)
    preview_input_binding: dict[str, object] = field(default_factory=dict)
    submit_operation: SubmitOperationRecord | None = None
    repository_id: str | None = None
    repository_target_ref: str | None = None
    repository_commit_hash: str | None = None


@dataclass
class ArchiveCandidateRecord:
    candidate_id: str
    batch_id: str
    workspace_id: str
    source_kind: str
    role: str
    source_submission_id: str
    base_main_hash: str
    initial_commit_hash: str | None
    modified_commit_hash: str
    preview_revision_id: str | None
    preview_strategy_manifest_digest: str | None
    preview_bundle_digest: str | None
    preview_bundle_id: str | None
    status: str
    created_by_actor_id: str
    created_at: str
    override_reason: str | None = None
    configuration_generated_at: str | None = None
    abnormal_kind: str | None = None
    time_abnormal_reason: str | None = None


@dataclass
class WorkspaceArchiveConfirmationRecord:
    confirmation_id: str
    batch_id: str
    workspace_id: str
    status: str
    archive_candidate_id: str | None
    confirmed_by_actor_id: str
    confirmed_at: str
    reason: str | None = None


@dataclass
class ArchiveExecutionRecord:
    execution_id: str
    batch_id: str
    command_idempotency_key: str
    requested_by_actor_id: str
    selected_modified_candidate_id: str
    selected_initial_candidate_ids: tuple[str, ...]
    old_main_hash: str
    new_main_hash: str | None
    status: str
    transfer_status: str
    failure_reason: str | None
    created_at: str


@dataclass
class BaselineArchiveNodeRecord:
    node_id: str
    batch_id: str
    role: str
    commit_hash: str
    immutable_ref: str
    summary_ref: str
    source_submission_id: str
    source_workspace_id: str
    source_candidate_id: str
    archive_execution_id: str
    created_by_actor_id: str
    created_at: str
    associated_mainline_node_id: str | None = None
    anomaly_resolution_id: str | None = None
    configuration_generated_at: str | None = None
    abnormal_kind: str | None = None
    time_abnormal_reason: str | None = None
    snapshot_rows_artifact_ref: dict[str, object] | None = None
    snapshot_rows_artifact_stats: dict[str, object] = field(default_factory=dict)


@dataclass
class AnomalyResolutionRecord:
    resolution_id: str
    batch_id: str
    workspace_id: str
    submission_id: str
    resolution_type: str
    reason: str
    accepted_by_actor_id: str
    accepted_at: str
    affected_submission_ids: tuple[str, ...] = ()
    abnormal_kind: str | None = None
    time_abnormal_reason: str | None = None
    covered_reason_codes: tuple[str, ...] = ()


@dataclass
class HistoryComparisonRecord:
    operation_id: str
    gateway_device_external_key: str
    business_project_id: str
    actor_id: str
    status: str
    input_nodes: list[dict[str, object]]
    pair_plan: list[dict[str, object]]
    bundle: dict[str, object] | None
    comparison_bundle_download: dict[str, object] | None
    comparison_bundle_tar_path: str | None
    diagnostics: list[dict[str, object]]
    submitted_at: str
    updated_at: str


@dataclass
class _State:
    gateways: dict[str, GatewayDeviceRecord] = field(default_factory=dict)
    batches_by_gateway: dict[str, list[BaselineBatchRecord]] = field(default_factory=dict)
    workspaces: dict[str, WorkspaceRecord] = field(default_factory=dict)
    preview_bundles: dict[str, PreviewBundleRecord] = field(default_factory=dict)
    submissions: dict[str, SubmissionRecord] = field(default_factory=dict)
    archive_candidates: dict[str, ArchiveCandidateRecord] = field(default_factory=dict)
    archive_confirmations: dict[str, WorkspaceArchiveConfirmationRecord] = field(default_factory=dict)
    anomaly_resolutions: dict[str, AnomalyResolutionRecord] = field(default_factory=dict)
    archive_executions: dict[str, ArchiveExecutionRecord] = field(default_factory=dict)
    baseline_archive_nodes: dict[str, BaselineArchiveNodeRecord] = field(default_factory=dict)
    archive_selections: dict[str, dict[str, object]] = field(default_factory=dict)
    history_comparisons: dict[str, HistoryComparisonRecord] = field(default_factory=dict)
    next_submission_sequence: int = 1


class VNextFormalStateStore:
    """Minimal vNext-owned state for the formal API."""

    def __init__(self, *, root: Path | None = None) -> None:
        resolved_root = (
            Path(tempfile.mkdtemp(prefix="backend-vnext-formal-"))
            if root is None
            else Path(root).expanduser().resolve()
        )
        self._root = resolved_root
        self._path = resolved_root / "formal-state.json" if root is not None else None
        self._lock = RLock()
        self._state = _State()
        if self._path is not None:
            self._load()

    @property
    def root(self) -> Path:
        return self._root

    def upsert_gateway_device(
        self,
        *,
        gateway_device_external_key: str,
        display_name: str,
        status: str,
        business_project_id: str,
        repo_key: str,
        artifact_root_key: str,
        updated_by_actor_id: str,
        reason: str,
    ) -> dict[str, object]:
        with self._lock:
            now = _now()
            existing = self._state.gateways.get(gateway_device_external_key)
            created = existing is None
            record = GatewayDeviceRecord(
                gateway_device_id=(
                    existing.gateway_device_id
                    if existing is not None
                    else f"gateway-device:{gateway_device_external_key}"
                ),
                gateway_device_external_key=gateway_device_external_key,
                display_name=display_name,
                status=status,
                business_project_id=business_project_id,
                repo_key=repo_key,
                artifact_root_key=artifact_root_key,
                updated_by_actor_id=updated_by_actor_id,
                reason=reason,
                created_at=existing.created_at if existing is not None else now,
                updated_at=now,
            )
            self._state.gateways[gateway_device_external_key] = record
            current = self._current_open_batch(gateway_device_external_key)
            if current is None:
                current = self._append_batch(
                    gateway_device_external_key=gateway_device_external_key,
                    base_main_hash=f"vnext-empty-main:{gateway_device_external_key}",
                    baseline_kind="EXPLICIT_EMPTY",
                    idempotency_key=f"initial-open:{gateway_device_external_key}",
                )
            self._save()
            return {
                "gateway_device_id": record.gateway_device_id,
                "gateway_device_external_key": record.gateway_device_external_key,
                "display_name": record.display_name,
                "status": record.status,
                "repo_key": record.repo_key,
                "artifact_root_key": record.artifact_root_key,
                "created": created,
                "current_main_hash": current.current_main_hash,
                "current_batch": _batch_payload(current),
            }

    def disable_gateway_device(
        self,
        *,
        gateway_device_external_key: str,
        updated_by_actor_id: str,
        reason: str,
    ) -> dict[str, object]:
        with self._lock:
            existing = self._state.gateways.get(gateway_device_external_key)
            if existing is None:
                existing = GatewayDeviceRecord(
                    gateway_device_id=f"gateway-device:{gateway_device_external_key}",
                    gateway_device_external_key=gateway_device_external_key,
                    display_name=gateway_device_external_key,
                    status="DISABLED",
                    business_project_id="unknown",
                    repo_key=gateway_device_external_key,
                    artifact_root_key=gateway_device_external_key,
                    updated_by_actor_id=updated_by_actor_id,
                    reason=reason,
                    created_at=_now(),
                    updated_at=_now(),
                )
            existing.status = "DISABLED"
            existing.updated_by_actor_id = updated_by_actor_id
            existing.reason = reason
            existing.updated_at = _now()
            self._state.gateways[gateway_device_external_key] = existing
            self._save()
            return {
                "gateway_device_id": existing.gateway_device_id,
                "gateway_device_external_key": gateway_device_external_key,
                "status": "DISABLED",
            }

    def get_current_baseline_batch(self, gateway_device_external_key: str) -> dict[str, object] | None:
        with self._lock:
            batch = self._current_open_batch(gateway_device_external_key)
            return _batch_payload(batch) if batch is not None else None

    def get_latest_baseline_batch(self, gateway_device_external_key: str) -> dict[str, object] | None:
        with self._lock:
            batches = self._state.batches_by_gateway.get(gateway_device_external_key, [])
            if not batches:
                return None
            return _batch_payload(batches[-1])

    def get_gateway_device(self, gateway_device_external_key: str) -> dict[str, object] | None:
        with self._lock:
            record = self._state.gateways.get(gateway_device_external_key)
            if record is None:
                return None
            return {
                "gateway_device_id": record.gateway_device_id,
                "gateway_device_external_key": record.gateway_device_external_key,
                "display_name": record.display_name,
                "status": record.status,
                "business_project_id": record.business_project_id,
                "repo_key": record.repo_key,
                "artifact_root_key": record.artifact_root_key,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            }

    def open_baseline_batch(
        self,
        *,
        gateway_device_external_key: str,
        base_main_hash: str,
        baseline_kind: str,
        opened_by_actor_id: str,
        reason: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        del opened_by_actor_id, reason
        with self._lock:
            for batch in self._state.batches_by_gateway.get(gateway_device_external_key, []):
                if batch.idempotency_key == idempotency_key:
                    return _batch_payload(batch)
            batch = self._append_batch(
                gateway_device_external_key=gateway_device_external_key,
                base_main_hash=base_main_hash,
                baseline_kind=baseline_kind,
                idempotency_key=idempotency_key,
            )
            self._save()
            return _batch_payload(batch)

    def get_open_batch_workbench_summary(self, gateway_device_external_key: str) -> dict[str, object]:
        with self._lock:
            batch = self._current_open_batch(gateway_device_external_key)
            if batch is None:
                raise KeyError(gateway_device_external_key)
            return {
                "gateway_device_external_key": gateway_device_external_key,
                "batch_id": batch.batch_id,
                "batch_no": batch.batch_no,
                "archive_gate_status": batch.archive_gate_status,
                "pending_review_submission_count": batch.pending_review_submission_count,
                "in_review_submission_count": batch.in_review_submission_count,
                "approved_not_archived_submission_count": batch.approved_not_archived_submission_count,
                "special_workspace_count": batch.special_workspace_count,
                "rejected_or_withdrawn_pending_confirmation_count": (
                    batch.rejected_or_withdrawn_pending_confirmation_count
                ),
                "preview_pending_confirmation_count": batch.preview_pending_confirmation_count,
                "initial_only_pending_confirmation_count": batch.initial_only_pending_confirmation_count,
                "ready_for_archive": batch.archive_gate_status == "READY_FOR_ARCHIVE",
                "archive_frozen": batch.archive_gate_status == "ARCHIVE_FROZEN",
                "current_main_hash": batch.current_main_hash,
                "last_activity_at": batch.last_activity_at or batch.opened_at,
            }

    def create_or_get_workspace(
        self,
        *,
        gateway_device_external_key: str,
        owner_actor_id: str,
        business_project_id: str,
    ) -> tuple[dict[str, object], bool]:
        with self._lock:
            current_batch = self._current_open_batch(gateway_device_external_key)
            existing = self._select_actor_workspace(
                actor_id=owner_actor_id,
                current_batch_id=current_batch.batch_id if current_batch is not None else None,
                workspaces=[
                    workspace
                    for workspace in self._state.workspaces.values()
                    if workspace.gateway_device_external_key == gateway_device_external_key
                ],
            )
            if (
                existing is not None
                and current_batch is not None
                and existing.batch_id == current_batch.batch_id
            ):
                return _workspace_payload(existing), False
            if existing is not None and current_batch is None and existing.batch_id is None:
                return _workspace_payload(existing), False
            base_workspace_id = f"workspace:{gateway_device_external_key}:{owner_actor_id}"
            workspace_id = base_workspace_id
            if workspace_id in self._state.workspaces:
                workspace_id = (
                    f"{base_workspace_id}:batch-"
                    f"{current_batch.batch_no if current_batch is not None else len(self._state.workspaces) + 1}"
                )
            now = _now()
            record = WorkspaceRecord(
                workspace_id=workspace_id,
                gateway_device_external_key=gateway_device_external_key,
                owner_actor_id=owner_actor_id,
                business_project_id=business_project_id,
                batch_id=current_batch.batch_id if current_batch is not None else None,
                status="EMPTY",
                upload_mode="FULL",
                base_main_hash=current_batch.base_main_hash if current_batch is not None else None,
                created_at=now,
                updated_at=now,
            )
            self._state.workspaces[workspace_id] = record
            self._save()
            return _workspace_payload(record), True

    def get_workspace(self, workspace_id: str) -> dict[str, object] | None:
        with self._lock:
            record = self._state.workspaces.get(workspace_id)
            return None if record is None else _workspace_payload(record)

    def get_workspace_initial_source_artifact_ref(self, workspace_id: str) -> dict[str, object] | None:
        with self._lock:
            record = self._state.workspaces.get(workspace_id)
            if record is None or record.initial_source_artifact_ref is None:
                return None
            return dict(record.initial_source_artifact_ref)

    def resolve_modified_only_baseline_source(self, workspace_id: str) -> dict[str, object]:
        with self._lock:
            record = self._state.workspaces.get(workspace_id)
            if record is None:
                raise KeyError(workspace_id)
            batch = self._find_batch(record.gateway_device_external_key, record.batch_id)
            if batch is None:
                return {
                    "status": "UNRESOLVED",
                    "upload_semantics": "MODIFIED_ONLY",
                    "error_code": "formal.baseline_batch_unresolved",
                    "message": "Workspace baseline batch is not available.",
                }
            if (
                _is_explicit_empty_first_batch(batch)
                and record.status in {"EMPTY", "INITIAL_READY", "PREVIEW_READY"}
            ):
                return {
                    "status": "READY",
                    "upload_semantics": "INITIALIZE_BASELINE",
                    "baseline_source_kind": "EXPLICIT_EMPTY",
                    "batch_id": batch.batch_id,
                    "batch_no": batch.batch_no,
                    "base_main_hash": batch.base_main_hash,
                    "source_submission_id": None,
                    "archive_node_id": None,
                    "artifact_ref": None,
                }

            baseline_commit = batch.current_main_hash or batch.base_main_hash
            archive_node = self._find_mainline_archive_node_by_commit(
                gateway_device_external_key=record.gateway_device_external_key,
                commit_hash=baseline_commit,
            )
            if archive_node is None:
                return {
                    "status": "UNRESOLVED",
                    "upload_semantics": "MODIFIED_ONLY",
                    "error_code": "formal.baseline_source_unresolved",
                    "message": "Current baseline is not backed by an archived submission artifact.",
                    "batch_id": batch.batch_id,
                    "batch_no": batch.batch_no,
                    "base_main_hash": batch.base_main_hash,
                    "current_main_hash": batch.current_main_hash,
                }
            submission = self._state.submissions.get(archive_node.source_submission_id)
            artifact_ref = (
                submission.submit_source_package.get("artifact_ref")
                if submission is not None
                else None
            )
            snapshot_rows_artifact_ref = (
                archive_node.snapshot_rows_artifact_ref
                if archive_node.snapshot_rows_artifact_ref is not None
                else (
                    submission.snapshot_rows_artifact_ref
                    if submission is not None
                    else None
                )
            )
            if not isinstance(artifact_ref, dict):
                return {
                    "status": "UNRESOLVED",
                    "upload_semantics": "MODIFIED_ONLY",
                    "error_code": "formal.baseline_source_unresolved",
                    "message": "Archived baseline source submission artifact is missing.",
                    "batch_id": batch.batch_id,
                    "batch_no": batch.batch_no,
                    "source_submission_id": archive_node.source_submission_id,
                    "archive_node_id": archive_node.node_id,
                }
            return {
                "status": "READY",
                "upload_semantics": "MODIFIED_ONLY",
                "baseline_source_kind": "ARCHIVED_MAINLINE",
                "batch_id": batch.batch_id,
                "batch_no": batch.batch_no,
                "base_main_hash": batch.base_main_hash,
                "current_main_hash": batch.current_main_hash,
                "source_submission_id": archive_node.source_submission_id,
                "archive_node_id": archive_node.node_id,
                "artifact_ref": dict(artifact_ref),
                "snapshot_rows_artifact_ref": (
                    None
                    if snapshot_rows_artifact_ref is None
                    else dict(snapshot_rows_artifact_ref)
                ),
            }

    def mark_workspace_initial_ready(
        self,
        *,
        workspace_id: str,
        initial_commit_hash: str,
        source_artifact_ref: dict[str, object],
        source_package: dict[str, object],
        initial_configuration_generated_at: str | None = None,
    ) -> dict[str, object]:
        with self._lock:
            record = self._state.workspaces.get(workspace_id)
            if record is None:
                raise KeyError(workspace_id)
            record.status = "INITIAL_READY"
            record.initial_commit_hash = initial_commit_hash
            record.initial_configuration_generated_at = initial_configuration_generated_at
            record.initial_source_artifact_ref = dict(source_artifact_ref)
            record.initial_source_package = dict(source_package)
            record.latest_preview = None
            record.updated_at = _now()
            self._save()
            return _workspace_payload(record)

    def mark_workspace_preview_ready(
        self,
        *,
        workspace_id: str,
        preview_refs: dict[str, object],
        preview_input_binding: dict[str, object],
        preview_source_package: dict[str, object],
        preview_bundle_record: dict[str, object],
        upload_semantics: str | None = None,
        baseline_source: dict[str, object] | None = None,
    ) -> dict[str, object]:
        with self._lock:
            record = self._state.workspaces.get(workspace_id)
            if record is None:
                raise KeyError(workspace_id)
            bundle_record = PreviewBundleRecord(
                preview_bundle_id=str(preview_bundle_record["preview_bundle_id"]),
                workspace_id=workspace_id,
                owner_actor_id=record.owner_actor_id,
                gateway_device_external_key=record.gateway_device_external_key,
                tar_path=str(preview_bundle_record["tar_path"]),
                bundle_root=str(preview_bundle_record["bundle_root"]),
                size_bytes=int(preview_bundle_record["size_bytes"]),
                sha256=str(preview_bundle_record["sha256"]),
                package_format=str(preview_bundle_record["package_format"]),
                created_at=_now(),
                preview_refs=dict(preview_refs),
                preview_input_binding=dict(preview_input_binding),
                preview_source_package=dict(preview_source_package),
            )
            self._state.preview_bundles[bundle_record.preview_bundle_id] = bundle_record
            record.status = "PREVIEW_READY"
            record.latest_preview = dict(preview_refs)
            record.latest_upload_semantics = upload_semantics
            record.latest_baseline_source = (
                None if baseline_source is None else dict(baseline_source)
            )
            record.draft_commit_hash = str(preview_refs.get("preview_revision_id"))
            record.updated_at = _now()
            self._save()
            return _workspace_payload(record)

    def get_preview_bundle(self, preview_bundle_id: str) -> dict[str, object] | None:
        with self._lock:
            record = self._state.preview_bundles.get(preview_bundle_id)
            if record is None:
                return None
            return {
                "preview_bundle_id": record.preview_bundle_id,
                "workspace_id": record.workspace_id,
                "owner_actor_id": record.owner_actor_id,
                "gateway_device_external_key": record.gateway_device_external_key,
                "tar_path": record.tar_path,
                "bundle_root": record.bundle_root,
                "size_bytes": record.size_bytes,
                "sha256": record.sha256,
                "package_format": record.package_format,
                "preview_refs": dict(record.preview_refs),
                "preview_input_binding": dict(record.preview_input_binding),
                "preview_source_package": (
                    None
                    if record.preview_source_package is None
                    else dict(record.preview_source_package)
                ),
                "created_at": record.created_at,
            }

    def next_submission_id(self) -> str:
        with self._lock:
            sequence = self._state.next_submission_sequence
            self._state.next_submission_sequence += 1
            self._save()
            return f"submission-{sequence:03d}"

    def create_submission(
        self,
        *,
        workspace_id: str,
        submitter_actor_id: str,
        preview_refs: dict[str, object],
        preview_input_binding: dict[str, object],
        submit_source_package: dict[str, object],
        accepted_payload: dict[str, object],
        operation_payload: dict[str, object],
        source_artifact_ref: str | None,
        source_artifact_payload_sha256: str | None,
        operation_status: str = "ACCEPTED",
        final_modified_commit_hash: str | None = None,
        repository_id: str | None = None,
        repository_target_ref: str | None = None,
        repository_commit_hash: str | None = None,
        configuration_generated_at: str | None = None,
        snapshot_rows_artifact_ref: dict[str, object] | None = None,
        snapshot_rows_artifact_stats: dict[str, object] | None = None,
    ) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        with self._lock:
            workspace = self._state.workspaces.get(workspace_id)
            if workspace is None:
                raise KeyError(workspace_id)
            if workspace.submitted_submission_id is not None or workspace.status == "SUBMITTED":
                raise ValueError("workspace already submitted")
            batch = self._find_batch(workspace.gateway_device_external_key, workspace.batch_id)
            if batch is None:
                raise KeyError("workspace baseline batch not found")

            submission_id = str(accepted_payload["submission_id"])
            if submission_id in self._state.submissions:
                raise ValueError("submission already exists")

            now = str(accepted_payload.get("accepted_at") or _now())
            sequence_no = self._state.next_submission_sequence - 1
            operation = SubmitOperationRecord(
                submit_operation_id=str(accepted_payload["operation_id"]),
                workspace_id=workspace_id,
                submission_id=submission_id,
                preview_token=str(preview_refs["preview_token"]),
                preview_revision_id=str(preview_refs["preview_revision_id"]),
                preview_strategy_manifest_ref=str(preview_refs["preview_strategy_manifest_ref"]),
                preview_strategy_manifest_digest=str(preview_refs["preview_strategy_manifest_digest"]),
                preview_bundle_digest=str(preview_refs["preview_bundle_digest"]),
                source_artifact_ref=source_artifact_ref,
                source_artifact_payload_sha256=source_artifact_payload_sha256,
                final_modified_commit_hash=final_modified_commit_hash,
                status=operation_status,
                error_code=None,
                created_at=str(operation_payload.get("created_at") or now),
                updated_at=str(operation_payload.get("updated_at") or now),
                operation_payload=dict(operation_payload),
            )
            submission = SubmissionRecord(
                submission_id=submission_id,
                workspace_id=workspace_id,
                batch_id=batch.batch_id,
                sequence_no=sequence_no,
                submitter_actor_id=submitter_actor_id,
                preview_token=str(preview_refs["preview_token"]),
                baseline_kind=batch.baseline_kind,
                base_main_hash=str(workspace.base_main_hash or batch.base_main_hash),
                initial_commit_hash=workspace.initial_commit_hash,
                modified_commit_hash=_string_digest_payload(
                    preview_input_binding.get("current_snapshot_digest")
                ),
                preview_revision_id=str(preview_refs["preview_revision_id"]),
                preview_strategy_manifest_ref=str(preview_refs["preview_strategy_manifest_ref"]),
                preview_strategy_manifest_digest=str(preview_refs["preview_strategy_manifest_digest"]),
                preview_bundle_digest=str(preview_refs["preview_bundle_digest"]),
                preview_bundle_id=str(preview_refs["preview_bundle_id"]),
                baseline_alignment="NORMAL",
                preview_manifest_ref=str(preview_refs["preview_manifest_ref"]),
                preview_index_ref=str(preview_refs["preview_index_ref"]),
                preview_bundle_root_ref=str(preview_refs["preview_bundle_root_ref"]),
                status="PENDING_REVIEW",
                archive_status="NOT_ARCHIVED",
                transfer_status=None,
                submitted_at=now,
                initial_configuration_generated_at=workspace.initial_configuration_generated_at,
                configuration_generated_at=configuration_generated_at,
                initial_source_package=(
                    {}
                    if workspace.initial_source_package is None
                    else dict(workspace.initial_source_package)
                ),
                submit_source_package=dict(submit_source_package),
                snapshot_rows_artifact_ref=(
                    None if snapshot_rows_artifact_ref is None else dict(snapshot_rows_artifact_ref)
                ),
                snapshot_rows_artifact_stats=(
                    {} if snapshot_rows_artifact_stats is None else dict(snapshot_rows_artifact_stats)
                ),
                preview_input_binding=dict(preview_input_binding),
                submit_operation=operation,
                repository_id=repository_id,
                repository_target_ref=repository_target_ref,
                repository_commit_hash=repository_commit_hash,
            )
            self._state.submissions[submission_id] = submission
            workspace.status = "SUBMITTED"
            workspace.submitted_submission_id = submission_id
            workspace.updated_at = _now()
            batch.pending_review_submission_count += 1
            batch.last_activity_at = workspace.updated_at
            self._save()
            return (
                _submission_payload(submission),
                _submit_operation_payload(operation),
                _workspace_payload(workspace),
            )

    def get_submission(self, submission_id: str) -> dict[str, object] | None:
        with self._lock:
            record = self._state.submissions.get(submission_id)
            return None if record is None else _submission_payload(record)

    def review_submission(
        self,
        *,
        submission_id: str,
        actor_id: str,
        action: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        with self._lock:
            submission = self._state.submissions.get(submission_id)
            if submission is None:
                raise KeyError(submission_id)
            workspace = self._state.workspaces.get(submission.workspace_id)
            if workspace is None:
                raise KeyError(submission.workspace_id)
            batch = self._find_batch(workspace.gateway_device_external_key, workspace.batch_id)
            if batch is None:
                raise KeyError("workspace baseline batch not found")

            now = _now()
            normalized = action.replace("-", "_")
            if normalized == "start_review":
                if submission.status != "PENDING_REVIEW":
                    raise ValueError("start_review requires PENDING_REVIEW submission")
                submission.status = "IN_REVIEW"
                submission.reviewed_by_actor_id = actor_id
                submission.reviewed_at = now
                batch.pending_review_submission_count = max(0, batch.pending_review_submission_count - 1)
                batch.in_review_submission_count += 1
            elif normalized == "approve":
                if submission.status != "IN_REVIEW":
                    raise ValueError("approve requires IN_REVIEW submission")
                submission.status = "APPROVED"
                submission.reviewed_by_actor_id = actor_id
                submission.reviewed_at = now
                batch.in_review_submission_count = max(0, batch.in_review_submission_count - 1)
                batch.approved_not_archived_submission_count += 1
            elif normalized == "reject":
                if submission.status != "IN_REVIEW":
                    raise ValueError("reject requires IN_REVIEW submission")
                submission.status = "REJECTED"
                submission.reviewed_by_actor_id = actor_id
                submission.reviewed_at = now
                batch.in_review_submission_count = max(0, batch.in_review_submission_count - 1)
                batch.rejected_or_withdrawn_pending_confirmation_count += 1
                _reopen_workspace_after_terminal_submission(workspace, now=now)
            elif normalized == "withdraw":
                if submission.status != "PENDING_REVIEW":
                    raise ValueError("withdraw requires PENDING_REVIEW submission")
                submission.status = "WITHDRAWN"
                submission.withdrawn_by_actor_id = actor_id
                submission.withdrawn_at = now
                batch.pending_review_submission_count = max(0, batch.pending_review_submission_count - 1)
                batch.rejected_or_withdrawn_pending_confirmation_count += 1
                _reopen_workspace_after_terminal_submission(workspace, now=now)
            else:
                raise ValueError(f"unsupported submission review action: {action}")

            workspace.updated_at = now
            batch.last_activity_at = now
            if batch.pending_review_submission_count == 0 and batch.in_review_submission_count == 0:
                if batch.approved_not_archived_submission_count > 0:
                    batch.archive_gate_status = "READY_FOR_ARCHIVE"
                else:
                    batch.archive_gate_status = "COLLECTING_CONFIRMATIONS"
            self._save()
            return _submission_payload(submission), _workspace_payload(workspace)

    def get_baseline_batch_by_id(self, batch_id: str) -> dict[str, object] | None:
        with self._lock:
            batch = self._find_batch_by_id(batch_id)
            return None if batch is None else _batch_payload(batch)

    def get_archive_snapshot(self, batch_id: str) -> dict[str, object]:
        with self._lock:
            batch = self._require_batch(batch_id)
            return self._archive_snapshot_payload(batch)

    def upsert_archive_candidate(
        self,
        *,
        batch_id: str,
        workspace_id: str,
        candidate_id: str,
        actor_id: str,
        source_kind: str,
        role: str,
        source_submission_id: str | None,
        override_reason: str | None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        with self._lock:
            batch = self._require_batch(batch_id)
            workspace = self._require_workspace_for_batch(workspace_id=workspace_id, batch_id=batch_id)
            if source_kind != "APPROVED_SUBMISSION":
                raise ValueError("formal archive currently supports APPROVED_SUBMISSION candidates only")
            if role not in {"MAINLINE_MODIFIED", "BASELINE_INITIAL_HISTORY"}:
                raise ValueError("unsupported archive candidate role")
            if source_submission_id is None:
                raise ValueError("source_submission_id is required")
            submission = self._state.submissions.get(source_submission_id)
            if submission is None:
                raise KeyError(source_submission_id)
            if submission.workspace_id != workspace_id or submission.batch_id != batch_id:
                raise ValueError("source submission does not match archive workspace/batch")
            if submission.status != "APPROVED":
                raise ValueError("archive candidate requires APPROVED submission")
            if submission.repository_commit_hash is None:
                raise ValueError("archive candidate requires finalized repository commit hash")
            if submission.configuration_generated_at is None:
                raise ValueError("archive candidate requires FINAL configuration_generated_at")
            graph = self._batch_graph_payload(batch)
            unresolved_roots = set(graph.get("unresolved_submission_ids", []))
            initial_time_abnormal_roots = {
                str(item.get("submission_id"))
                for item in graph.get("diagnostics", [])
                if isinstance(item, dict)
                and item.get("code") == "TIME_ABNORMAL_INITIAL"
                and item.get("submission_id") is not None
            }
            peer_chain_downstream_ids = {
                str(item.get("submission_id"))
                for item in graph.get("diagnostics", [])
                if isinstance(item, dict)
                and item.get("code") == "PEER_CHAIN_MATCH"
                and item.get("submission_id") is not None
            }
            if role == "BASELINE_INITIAL_HISTORY":
                if submission.submission_id in peer_chain_downstream_ids:
                    raise ValueError("baseline initial history candidate requires root abnormal initial submission")
                if submission.submission_id not in unresolved_roots and submission.submission_id not in initial_time_abnormal_roots:
                    raise ValueError("baseline initial history candidate requires root abnormal initial submission")
                if not self._resolution_covers(batch_id, submission.submission_id, "UNRESOLVED_INITIAL_STATE") and not self._resolution_covers(
                    batch_id, submission.submission_id, "TIME_ABNORMAL_INITIAL"
                ):
                    raise ValueError("baseline initial history candidate requires anomaly resolution")
            graph_time_codes = {
                item.get("code")
                for item in graph.get("diagnostics", [])
                if isinstance(item, dict) and item.get("submission_id") == submission.submission_id
            }
            abnormal_kind = None
            time_abnormal_reason = None
            if "TIME_ABNORMAL_MODIFIED" in graph_time_codes:
                abnormal_kind = "modified"
                time_abnormal_reason = "TIME_ABNORMAL_MODIFIED"
            elif "TIME_ABNORMAL_INITIAL" in graph_time_codes:
                abnormal_kind = "initial"
                time_abnormal_reason = "TIME_ABNORMAL_INITIAL"

            now = _now()
            record = ArchiveCandidateRecord(
                candidate_id=candidate_id,
                batch_id=batch_id,
                workspace_id=workspace_id,
                source_kind=source_kind,
                role=role,
                source_submission_id=source_submission_id,
                base_main_hash=batch.base_main_hash,
                initial_commit_hash=submission.initial_commit_hash,
                modified_commit_hash=(
                    submission.initial_commit_hash
                    if role == "BASELINE_INITIAL_HISTORY" and submission.initial_commit_hash is not None
                    else submission.repository_commit_hash
                ),
                preview_revision_id=submission.preview_revision_id,
                preview_strategy_manifest_digest=submission.preview_strategy_manifest_digest,
                preview_bundle_digest=submission.preview_bundle_digest,
                preview_bundle_id=submission.preview_bundle_id,
                status=submission.archive_status,
                created_by_actor_id=actor_id,
                created_at=self._state.archive_candidates.get(candidate_id, None).created_at
                if candidate_id in self._state.archive_candidates
                else now,
                override_reason=override_reason,
                configuration_generated_at=submission.configuration_generated_at,
                abnormal_kind=abnormal_kind,
                time_abnormal_reason=time_abnormal_reason,
            )
            self._state.archive_candidates[candidate_id] = record
            batch.last_activity_at = now
            self._save()
            return _workspace_payload(workspace), _archive_candidate_payload(record)

    def confirm_workspace_archive(
        self,
        *,
        batch_id: str,
        workspace_id: str,
        actor_id: str,
        confirmation_status: str,
        archive_candidate_id: str | None,
        reason: str | None,
    ) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        with self._lock:
            batch = self._require_batch(batch_id)
            workspace = self._require_workspace_for_batch(workspace_id=workspace_id, batch_id=batch_id)
            if confirmation_status not in {"CONFIRMED_WITH_CANDIDATE", "CONFIRMED_DISCARDED"}:
                raise ValueError("unsupported archive confirmation status")
            if confirmation_status == "CONFIRMED_WITH_CANDIDATE":
                if archive_candidate_id is None:
                    raise ValueError("archive_candidate_id is required for CONFIRMED_WITH_CANDIDATE")
                candidate = self._state.archive_candidates.get(archive_candidate_id)
                if candidate is None:
                    raise KeyError(archive_candidate_id)
                if candidate.batch_id != batch_id or candidate.workspace_id != workspace_id:
                    raise ValueError("archive candidate does not match workspace/batch")

            now = _now()
            confirmation_id = f"archive-confirmation:{batch_id}:{workspace_id}"
            record = WorkspaceArchiveConfirmationRecord(
                confirmation_id=confirmation_id,
                batch_id=batch_id,
                workspace_id=workspace_id,
                status=confirmation_status,
                archive_candidate_id=archive_candidate_id,
                confirmed_by_actor_id=actor_id,
                confirmed_at=now,
                reason=reason,
            )
            self._state.archive_confirmations[confirmation_id] = record
            batch.last_activity_at = now
            self._save()
            return _workspace_payload(workspace), _archive_confirmation_payload(record), _batch_payload(batch)

    def accept_anomaly_resolution(
        self,
        *,
        batch_id: str,
        workspace_id: str,
        submission_id: str,
        actor_id: str,
        resolution_type: str,
        reason: str,
        affected_submission_ids: tuple[str, ...] = (),
    ) -> dict[str, object]:
        with self._lock:
            batch = self._require_batch(batch_id)
            workspace = self._require_workspace_for_batch(workspace_id=workspace_id, batch_id=batch_id)
            submission = self._state.submissions.get(submission_id)
            if submission is None:
                raise KeyError(submission_id)
            if submission.workspace_id != workspace_id or submission.batch_id != batch_id:
                raise ValueError("resolution submission does not match workspace/batch")
            normalized_type = resolution_type.strip().upper()
            normalized_reason = reason.strip()
            if not normalized_reason:
                raise ValueError("anomaly resolution reason is required")
            graph = self._batch_graph_payload(batch, apply_resolutions=False)
            target_codes = {
                str(item.get("code"))
                for item in graph.get("diagnostics", [])
                if isinstance(item, dict) and item.get("submission_id") == submission_id
            }
            requested_affected = tuple(dict.fromkeys((submission_id, *affected_submission_ids)))
            if normalized_type == "MANUAL_ACCEPT_EXTERNAL_CHANGE":
                allowed_codes = {"UNRESOLVED_INITIAL_STATE", "TIME_ABNORMAL_INITIAL"}
                abnormal_kind = "initial"
            elif normalized_type == "MANUAL_ACCEPT_INCOMPLETE_SUMMARY":
                allowed_codes = {"SUMMARY_FACT_MISSING"}
                abnormal_kind = "initial"
            elif normalized_type == "MANUAL_ACCEPT_ABNORMAL_MODIFIED":
                allowed_codes = {"TIME_ABNORMAL_MODIFIED"}
                abnormal_kind = "modified"
            else:
                raise ValueError(f"unsupported anomaly resolution type: {resolution_type}")
            covered_codes = tuple(sorted(target_codes & allowed_codes))
            if not covered_codes:
                raise ValueError("anomaly resolution does not cover any current graph blocking reason")
            reachable_for_root = set(_peer_chain_downstream_submission_ids(graph, submission_id))
            for affected_id in requested_affected:
                if affected_id not in reachable_for_root:
                    raise ValueError("anomaly resolution affected submissions must belong to the same root chain")
            now = _now()
            resolution = AnomalyResolutionRecord(
                resolution_id=f"anomaly-resolution:{batch_id}:{len(self._anomaly_resolutions_for_batch(batch_id)) + 1:03d}",
                batch_id=batch_id,
                workspace_id=workspace.workspace_id,
                submission_id=submission_id,
                resolution_type=normalized_type,
                reason=normalized_reason,
                accepted_by_actor_id=actor_id,
                accepted_at=now,
                affected_submission_ids=requested_affected,
                abnormal_kind=abnormal_kind,
                time_abnormal_reason=(
                    "TIME_ABNORMAL_MODIFIED"
                    if "TIME_ABNORMAL_MODIFIED" in covered_codes
                    else ("TIME_ABNORMAL_INITIAL" if "TIME_ABNORMAL_INITIAL" in covered_codes else None)
                ),
                covered_reason_codes=covered_codes,
            )
            self._state.anomaly_resolutions[resolution.resolution_id] = resolution
            batch.last_activity_at = now
            self._save()
            return _anomaly_resolution_payload(resolution)

    def select_archive_candidates(
        self,
        *,
        batch_id: str,
        actor_id: str,
        selected_modified_candidate_id: str,
        selected_initial_candidate_ids: tuple[str, ...],
        candidate_set_hash: str | None,
        override_reason: str | None,
    ) -> tuple[dict[str, object], str, tuple[str, ...]]:
        del actor_id, override_reason
        with self._lock:
            batch = self._require_batch(batch_id)
            candidate = self._state.archive_candidates.get(selected_modified_candidate_id)
            if candidate is None:
                raise KeyError(selected_modified_candidate_id)
            if candidate.batch_id != batch_id or candidate.role != "MAINLINE_MODIFIED":
                raise ValueError("selected modified candidate does not match batch/role")
            snapshot = self._archive_snapshot_payload(batch)
            if candidate_set_hash is not None and candidate_set_hash != snapshot["candidate_set_hash"]:
                raise ValueError("candidate_set_hash mismatch")
            if candidate.time_abnormal_reason == "TIME_ABNORMAL_MODIFIED" and not self._resolution_covers(
                batch_id,
                candidate.source_submission_id,
                "TIME_ABNORMAL_MODIFIED",
            ):
                raise ValueError("selected modified candidate requires abnormal modified resolution")
            for initial_candidate_id in selected_initial_candidate_ids:
                initial_candidate = self._state.archive_candidates.get(initial_candidate_id)
                if initial_candidate is None:
                    raise KeyError(initial_candidate_id)
                if initial_candidate.batch_id != batch_id or initial_candidate.role != "BASELINE_INITIAL_HISTORY":
                    raise ValueError("selected initial candidate does not match batch/role")
                graph = snapshot.get("batch_graph", {})
                graph_diagnostics = graph.get("diagnostics", []) if isinstance(graph, dict) else []
                if any(
                    isinstance(item, dict)
                    and item.get("code") == "PEER_CHAIN_MATCH"
                    and item.get("submission_id") == initial_candidate.source_submission_id
                    for item in graph_diagnostics
                ):
                    raise ValueError("selected initial candidate must be a root abnormal initial submission")
                if not self._resolution_covers(
                    batch_id,
                    initial_candidate.source_submission_id,
                    "UNRESOLVED_INITIAL_STATE",
                ) and not self._resolution_covers(
                    batch_id,
                    initial_candidate.source_submission_id,
                    "TIME_ABNORMAL_INITIAL",
                ):
                    raise ValueError("selected initial candidate requires anomaly resolution")
            self._state.archive_selections[batch_id] = {
                "selected_modified_candidate_id": selected_modified_candidate_id,
                "selected_initial_candidate_ids": list(selected_initial_candidate_ids),
            }
            batch.selected_modified_candidate_id = selected_modified_candidate_id
            batch.selected_initial_candidate_ids = list(selected_initial_candidate_ids)
            batch.candidate_set_hash = str(snapshot["candidate_set_hash"])
            batch.last_activity_at = _now()
            self._save()
            return _batch_payload(batch), selected_modified_candidate_id, selected_initial_candidate_ids

    def dry_run_archive_mainline(self, batch_id: str) -> dict[str, object]:
        with self._lock:
            batch = self._require_batch(batch_id)
            snapshot = self._archive_snapshot_payload(batch)
            failure_reasons = self._archive_failure_reasons(batch, snapshot)
            return {
                "snapshot": snapshot,
                "eligible_for_execute": not failure_reasons,
                "failure_reasons": failure_reasons,
                "plan": {},
            }

    def validate_archive_mainline_execute(
        self,
        *,
        batch_id: str,
        requested_by_actor_id: str,
        idempotency_key: str,
        expected_base_main_hash: str,
        selected_modified_candidate_id: str,
        selected_initial_candidate_ids: tuple[str, ...],
        workspace_confirmation_set_hash: str,
        candidate_set_hash: str,
        override_reason: str | None,
    ) -> dict[str, object]:
        del requested_by_actor_id, override_reason
        with self._lock:
            for execution in self._state.archive_executions.values():
                if execution.command_idempotency_key == idempotency_key and execution.batch_id == batch_id:
                    workspace_ids = [
                        self._state.archive_candidates[execution.selected_modified_candidate_id].workspace_id
                    ]
                    for candidate_id in execution.selected_initial_candidate_ids:
                        candidate = self._state.archive_candidates.get(candidate_id)
                        if candidate is not None:
                            workspace_ids.append(candidate.workspace_id)
                    return {
                        "batch_id": batch_id,
                        "idempotent_replay": True,
                        "workspace_ids": sorted(set(workspace_ids)),
                    }

            batch = self._require_batch(batch_id)
            if batch.status != "OPEN" or batch.archive_gate_status != "READY_FOR_ARCHIVE":
                raise ValueError("archive execute requires OPEN batch with READY_FOR_ARCHIVE gate")
            if expected_base_main_hash != batch.base_main_hash:
                raise ValueError("expected_base_main_hash mismatch")
            snapshot = self._archive_snapshot_payload(batch)
            if workspace_confirmation_set_hash != snapshot["workspace_confirmation_set_hash"]:
                raise ValueError("workspace_confirmation_set_hash mismatch")
            if candidate_set_hash != snapshot["candidate_set_hash"]:
                raise ValueError("candidate_set_hash mismatch")
            failure_reasons = self._archive_failure_reasons(batch, snapshot)
            if failure_reasons:
                raise ValueError("archive execute blocked: " + "; ".join(failure_reasons))
            selection = self._state.archive_selections.get(batch_id)
            if selection is None or selection.get("selected_modified_candidate_id") != selected_modified_candidate_id:
                raise ValueError("selected modified candidate was not frozen")
            frozen_initial_candidate_ids = tuple(selection.get("selected_initial_candidate_ids", []))
            if tuple(selected_initial_candidate_ids) != frozen_initial_candidate_ids:
                raise ValueError("selected initial candidates were not frozen")

            candidate = self._state.archive_candidates[selected_modified_candidate_id]
            submission = self._state.submissions[candidate.source_submission_id]
            workspace_ids = [candidate.workspace_id]
            if submission.repository_commit_hash is None:
                raise ValueError("selected submission is missing repository commit hash")
            artifact_ref = submission.submit_source_package.get("artifact_ref")
            if not submission.submit_source_package or not isinstance(artifact_ref, dict):
                raise ValueError("selected submission is missing submit source package artifact")
            for initial_candidate_id in selected_initial_candidate_ids:
                initial_candidate = self._state.archive_candidates.get(initial_candidate_id)
                if initial_candidate is None:
                    raise KeyError(initial_candidate_id)
                if initial_candidate.batch_id != batch_id or initial_candidate.role != "BASELINE_INITIAL_HISTORY":
                    raise ValueError("selected initial candidate does not match batch/role")
                initial_submission = self._state.submissions.get(initial_candidate.source_submission_id)
                if initial_submission is None:
                    raise KeyError(initial_candidate.source_submission_id)
                if not initial_submission.initial_source_package:
                    raise ValueError("selected initial history candidate is missing initial source package")
                initial_resolution_id = self._resolution_id_covering(
                    batch_id,
                    initial_submission.submission_id,
                    "UNRESOLVED_INITIAL_STATE",
                ) or self._resolution_id_covering(
                    batch_id,
                    initial_submission.submission_id,
                    "TIME_ABNORMAL_INITIAL",
                )
                if initial_resolution_id is None:
                    raise ValueError("selected initial history candidate requires anomaly resolution")
                workspace_ids.append(initial_candidate.workspace_id)
            return {
                "batch_id": batch_id,
                "idempotent_replay": False,
                "workspace_ids": sorted(set(workspace_ids)),
                "preparation_source": {
                    "batch_id": batch_id,
                    "workspace_id": candidate.workspace_id,
                    "source_submission_id": submission.submission_id,
                    "source_package_id": submission.submit_source_package.get("source_package_id"),
                    "source_package_digest": submission.submit_source_package.get("source_package_digest"),
                    "artifact_ref": dict(artifact_ref),
                },
            }

    def execute_archive_mainline(
        self,
        *,
        batch_id: str,
        requested_by_actor_id: str,
        idempotency_key: str,
        expected_base_main_hash: str,
        selected_modified_candidate_id: str,
        selected_initial_candidate_ids: tuple[str, ...],
        workspace_confirmation_set_hash: str,
        candidate_set_hash: str,
        override_reason: str | None,
    ) -> dict[str, object]:
        del override_reason
        with self._lock:
            for execution in self._state.archive_executions.values():
                if execution.command_idempotency_key == idempotency_key:
                    batch = self._require_batch(batch_id)
                    return self._archive_execute_payload(batch=batch, execution=execution, idempotent_replay=True)

            batch = self._require_batch(batch_id)
            if batch.status != "OPEN" or batch.archive_gate_status != "READY_FOR_ARCHIVE":
                raise ValueError("archive execute requires OPEN batch with READY_FOR_ARCHIVE gate")
            if expected_base_main_hash != batch.base_main_hash:
                raise ValueError("expected_base_main_hash mismatch")
            snapshot = self._archive_snapshot_payload(batch)
            if workspace_confirmation_set_hash != snapshot["workspace_confirmation_set_hash"]:
                raise ValueError("workspace_confirmation_set_hash mismatch")
            if candidate_set_hash != snapshot["candidate_set_hash"]:
                raise ValueError("candidate_set_hash mismatch")
            failure_reasons = self._archive_failure_reasons(batch, snapshot)
            if failure_reasons:
                raise ValueError("archive execute blocked: " + "; ".join(failure_reasons))
            selection = self._state.archive_selections.get(batch_id)
            if selection is None or selection.get("selected_modified_candidate_id") != selected_modified_candidate_id:
                raise ValueError("selected modified candidate was not frozen")
            frozen_initial_candidate_ids = tuple(selection.get("selected_initial_candidate_ids", []))
            if tuple(selected_initial_candidate_ids) != frozen_initial_candidate_ids:
                raise ValueError("selected initial candidates were not frozen")

            candidate = self._state.archive_candidates[selected_modified_candidate_id]
            submission = self._state.submissions[candidate.source_submission_id]
            workspace = self._state.workspaces[candidate.workspace_id]
            now = _now()
            new_main_hash = submission.repository_commit_hash
            if new_main_hash is None:
                raise ValueError("selected submission is missing repository commit hash")
            mainline_resolution_id = (
                self._resolution_id_covering(batch_id, submission.submission_id, "TIME_ABNORMAL_MODIFIED")
                if candidate.time_abnormal_reason == "TIME_ABNORMAL_MODIFIED"
                else None
            )
            initial_history_inputs: list[tuple[ArchiveCandidateRecord, SubmissionRecord, WorkspaceRecord, str | None]] = []
            for initial_candidate_id in selected_initial_candidate_ids:
                initial_candidate = self._state.archive_candidates.get(initial_candidate_id)
                if initial_candidate is None:
                    raise KeyError(initial_candidate_id)
                if initial_candidate.batch_id != batch_id or initial_candidate.role != "BASELINE_INITIAL_HISTORY":
                    raise ValueError("selected initial candidate does not match batch/role")
                initial_submission = self._state.submissions.get(initial_candidate.source_submission_id)
                if initial_submission is None:
                    raise KeyError(initial_candidate.source_submission_id)
                initial_workspace = self._state.workspaces.get(initial_candidate.workspace_id)
                if initial_workspace is None:
                    raise KeyError(initial_candidate.workspace_id)
                if not initial_submission.initial_source_package:
                    raise ValueError("selected initial history candidate is missing initial source package")
                initial_resolution_id = self._resolution_id_covering(
                    batch_id,
                    initial_submission.submission_id,
                    "UNRESOLVED_INITIAL_STATE",
                ) or self._resolution_id_covering(
                    batch_id,
                    initial_submission.submission_id,
                    "TIME_ABNORMAL_INITIAL",
                )
                if initial_resolution_id is None:
                    raise ValueError("selected initial history candidate requires anomaly resolution")
                initial_history_inputs.append(
                    (initial_candidate, initial_submission, initial_workspace, initial_resolution_id)
                )

            execution = ArchiveExecutionRecord(
                execution_id=f"archive-execution:{len(self._state.archive_executions) + 1:03d}",
                batch_id=batch_id,
                command_idempotency_key=idempotency_key,
                requested_by_actor_id=requested_by_actor_id,
                selected_modified_candidate_id=selected_modified_candidate_id,
                selected_initial_candidate_ids=tuple(selected_initial_candidate_ids),
                old_main_hash=batch.base_main_hash,
                new_main_hash=new_main_hash,
                status="SUCCEEDED",
                transfer_status="TRANSFERRED",
                failure_reason=None,
                created_at=now,
            )
            next_node_number = len(self._state.baseline_archive_nodes) + 1
            mainline_node = BaselineArchiveNodeRecord(
                node_id=f"baseline-archive-node:{len(self._state.baseline_archive_nodes) + 1:03d}",
                batch_id=batch_id,
                role="MAINLINE_MODIFIED",
                commit_hash=new_main_hash,
                immutable_ref=f"refs/tags/formal/{batch_id}/mainline",
                summary_ref=f"archive_summaries/{execution.execution_id}/mainline.json",
                source_submission_id=submission.submission_id,
                source_workspace_id=workspace.workspace_id,
                source_candidate_id=candidate.candidate_id,
                archive_execution_id=execution.execution_id,
                created_by_actor_id=requested_by_actor_id,
                created_at=now,
                anomaly_resolution_id=mainline_resolution_id,
                configuration_generated_at=submission.configuration_generated_at,
                abnormal_kind=candidate.abnormal_kind,
                time_abnormal_reason=candidate.time_abnormal_reason,
                snapshot_rows_artifact_ref=(
                    None
                    if submission.snapshot_rows_artifact_ref is None
                    else dict(submission.snapshot_rows_artifact_ref)
                ),
                snapshot_rows_artifact_stats=dict(submission.snapshot_rows_artifact_stats),
            )
            next_node_number += 1
            history_nodes: list[BaselineArchiveNodeRecord] = []
            for initial_candidate, initial_submission, initial_workspace, resolution_id in initial_history_inputs:
                history_node = BaselineArchiveNodeRecord(
                    node_id=f"baseline-archive-node:{next_node_number:03d}",
                    batch_id=batch_id,
                    role="BASELINE_INITIAL_HISTORY",
                    commit_hash=initial_candidate.modified_commit_hash,
                    immutable_ref=f"refs/tags/formal/{batch_id}/initial-history/{initial_candidate.candidate_id}",
                    summary_ref=f"archive_summaries/{execution.execution_id}/{initial_candidate.candidate_id}/initial.json",
                    source_submission_id=initial_submission.submission_id,
                    source_workspace_id=initial_workspace.workspace_id,
                    source_candidate_id=initial_candidate.candidate_id,
                    archive_execution_id=execution.execution_id,
                    created_by_actor_id=requested_by_actor_id,
                    created_at=now,
                    associated_mainline_node_id=mainline_node.node_id,
                    anomaly_resolution_id=resolution_id,
                    configuration_generated_at=initial_submission.initial_configuration_generated_at,
                    abnormal_kind="initial",
                    time_abnormal_reason=initial_candidate.time_abnormal_reason,
                    snapshot_rows_artifact_ref=(
                        None
                        if initial_submission.snapshot_rows_artifact_ref is None
                        else dict(initial_submission.snapshot_rows_artifact_ref)
                    ),
                    snapshot_rows_artifact_stats=dict(
                        initial_submission.snapshot_rows_artifact_stats
                    ),
                )
                history_nodes.append(history_node)
                next_node_number += 1

            self._state.archive_executions[execution.execution_id] = execution
            self._state.baseline_archive_nodes[mainline_node.node_id] = mainline_node
            for history_node in history_nodes:
                self._state.baseline_archive_nodes[history_node.node_id] = history_node
            candidate.status = "ARCHIVED_AS_MAINLINE"
            for initial_candidate, _initial_submission, _initial_workspace, _resolution_id in initial_history_inputs:
                initial_candidate.status = "ARCHIVED_AS_INITIAL_HISTORY"
            submission.archive_status = "ARCHIVED_AS_MAINLINE"
            submission.transfer_status = "TRANSFERRED"
            workspace.status = "CLOSED"
            workspace.latest_preview = None
            workspace.submitted_submission_id = submission.submission_id
            workspace.updated_at = now
            batch.status = "CLOSED"
            batch.archive_gate_status = "ARCHIVED"
            batch.current_main_hash = new_main_hash
            batch.closed_at = now
            batch.approved_not_archived_submission_count = max(0, batch.approved_not_archived_submission_count - 1)
            batch.last_activity_at = now
            if self._current_open_batch(batch.gateway_device_external_key) is None:
                self._append_batch(
                    gateway_device_external_key=batch.gateway_device_external_key,
                    base_main_hash=new_main_hash,
                    baseline_kind="DOLT_COMMIT",
                    idempotency_key=f"formal-archive:{execution.execution_id}",
                )
            self._save()
            return self._archive_execute_payload(batch=batch, execution=execution, idempotent_replay=False)

    def list_archive_executions(self, batch_id: str) -> dict[str, object]:
        with self._lock:
            batch = self._require_batch(batch_id)
            return {
                "baseline_batch": _batch_payload(batch),
                "execution_records": [
                    _archive_execution_payload(record)
                    for record in self._archive_executions_for_batch(batch_id)
                ],
            }

    def resolve_history_comparison_node(
        self,
        *,
        actor_id: str,
        gateway_device_external_key: str,
        business_project_id: str,
        kind: str,
        node_id: str,
        index: int,
    ) -> dict[str, object]:
        with self._lock:
            gateway = self._state.gateways.get(gateway_device_external_key)
            if gateway is None:
                raise KeyError(gateway_device_external_key)
            if gateway.business_project_id != business_project_id:
                raise PermissionError("gateway project does not match session")
            if kind == "SUBMISSION_MODIFIED":
                return self._resolve_submission_modified_history_node(
                    actor_id=actor_id,
                    gateway_device_external_key=gateway_device_external_key,
                    business_project_id=business_project_id,
                    submission_id=node_id,
                    index=index,
                )
            if kind == "BASELINE_MAINLINE":
                return self._resolve_baseline_mainline_history_node(
                    gateway_device_external_key=gateway_device_external_key,
                    business_project_id=business_project_id,
                    batch_id=node_id,
                    index=index,
                )
            if kind == "BASELINE_INITIAL_HISTORY":
                return self._resolve_baseline_initial_history_node(
                    gateway_device_external_key=gateway_device_external_key,
                    business_project_id=business_project_id,
                    node_id=node_id,
                    index=index,
                )
            return _unresolved_history_input(
                index=index,
                kind=kind,
                node_id=node_id,
                code="formal.unsupported_history_node_kind",
                message=f"Unsupported history comparison node kind: {kind}",
            )

    def save_history_comparison(
        self,
        *,
        operation_id: str,
        actor_id: str,
        gateway_device_external_key: str,
        business_project_id: str,
        status: str,
        input_nodes: list[dict[str, object]],
        pair_plan: list[dict[str, object]],
        bundle: dict[str, object] | None,
        comparison_bundle_download: dict[str, object] | None = None,
        comparison_bundle_tar_path: str | None = None,
        diagnostics: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        with self._lock:
            now = _now()
            record = HistoryComparisonRecord(
                operation_id=operation_id,
                gateway_device_external_key=gateway_device_external_key,
                business_project_id=business_project_id,
                actor_id=actor_id,
                status=status,
                input_nodes=list(input_nodes),
                pair_plan=list(pair_plan),
                bundle=None if bundle is None else dict(bundle),
                comparison_bundle_download=(
                    None
                    if comparison_bundle_download is None
                    else dict(comparison_bundle_download)
                ),
                comparison_bundle_tar_path=comparison_bundle_tar_path,
                diagnostics=list(diagnostics or []),
                submitted_at=self._state.history_comparisons.get(operation_id, None).submitted_at
                if operation_id in self._state.history_comparisons
                else now,
                updated_at=now,
            )
            self._state.history_comparisons[operation_id] = record
            self._save()
            return _history_comparison_payload(record)

    def get_history_comparison(
        self,
        *,
        operation_id: str,
        actor_id: str,
        gateway_device_external_key: str,
        business_project_id: str,
    ) -> dict[str, object] | None:
        with self._lock:
            record = self._state.history_comparisons.get(operation_id)
            if record is None:
                return None
            if record.gateway_device_external_key != gateway_device_external_key:
                raise PermissionError("history comparison gateway does not match session")
            if record.business_project_id != business_project_id:
                raise PermissionError("history comparison project does not match session")
            if record.actor_id != actor_id:
                raise PermissionError("history comparison actor does not match session")
            return _history_comparison_payload(record)

    def get_history_comparison_bundle_artifact_path(
        self,
        *,
        operation_id: str,
        actor_id: str,
        gateway_device_external_key: str,
        business_project_id: str,
    ) -> str | None:
        with self._lock:
            record = self._state.history_comparisons.get(operation_id)
            if record is None:
                return None
            if record.gateway_device_external_key != gateway_device_external_key:
                raise PermissionError("history comparison gateway does not match session")
            if record.business_project_id != business_project_id:
                raise PermissionError("history comparison project does not match session")
            if record.actor_id != actor_id:
                raise PermissionError("history comparison actor does not match session")
            return record.comparison_bundle_tar_path

    def get_workspace_tree(
        self,
        *,
        actor_id: str,
        gateway_device_external_key: str,
        business_project_id: str,
        permissions: tuple[str, ...],
    ) -> dict[str, object]:
        with self._lock:
            gateway = self._state.gateways.get(gateway_device_external_key)
            if gateway is None:
                raise KeyError(gateway_device_external_key)
            if gateway.business_project_id != business_project_id:
                raise PermissionError("gateway project does not match session")

            permission_set = set(permissions)
            batches = list(self._state.batches_by_gateway.get(gateway_device_external_key, []))
            current_batch = self._current_open_batch(gateway_device_external_key)
            current_effective_batch = current_batch or (batches[-1] if batches else None)
            scoped_workspaces = [
                workspace
                for workspace in self._state.workspaces.values()
                if workspace.gateway_device_external_key == gateway_device_external_key
                and workspace.business_project_id == business_project_id
            ]
            scoped_workspace_ids = {workspace.workspace_id for workspace in scoped_workspaces}
            submissions_by_workspace: dict[str, list[SubmissionRecord]] = {}
            for submission in self._state.submissions.values():
                if submission.workspace_id not in scoped_workspace_ids:
                    continue
                submissions_by_workspace.setdefault(submission.workspace_id, []).append(submission)
            for submissions in submissions_by_workspace.values():
                submissions.sort(key=lambda item: (item.submitted_at, item.sequence_no, item.submission_id))

            actor_workspace = self._select_actor_workspace(
                actor_id=actor_id,
                current_batch_id=current_batch.batch_id if current_batch is not None else None,
                workspaces=scoped_workspaces,
            )
            archive_nodes_by_submission = {
                node.source_submission_id: node
                for node in self._state.baseline_archive_nodes.values()
                if node.batch_id in {batch.batch_id for batch in batches}
                and node.role == "MAINLINE_MODIFIED"
            }
            baselines = []
            tree_nodes = []
            all_submissions: list[dict[str, object]] = []
            for batch in sorted(batches, key=lambda item: (item.batch_no, item.batch_id)):
                batch_workspaces = sorted(
                    (workspace for workspace in scoped_workspaces if workspace.batch_id == batch.batch_id),
                    key=lambda item: (item.created_at, item.workspace_id),
                )
                tree_nodes.append(
                    {
                        "node_id": f"baseline:{batch.batch_id}",
                        "parent_id": None,
                        "kind": "baseline",
                        "label": f"Baseline {batch.batch_no}",
                        "depth": 0,
                        "path": None,
                        "table_name": None,
                        "owner_id": None,
                        "status": batch.status,
                        "commit_hash": batch.current_main_hash or batch.base_main_hash,
                        "current_actor_owned": False,
                    }
                )
                workspace_items = []
                for workspace in batch_workspaces:
                    workspace_payload = _workspace_payload(workspace)
                    workspace_submissions = [
                        _submission_payload(submission)
                        for submission in submissions_by_workspace.get(workspace.workspace_id, [])
                    ]
                    all_submissions.extend(workspace_submissions)
                    workspace_items.append(
                        {
                            "workspace": workspace_payload,
                            "submissions": workspace_submissions,
                        }
                    )
                    tree_nodes.append(
                        {
                            "node_id": f"workspace:{workspace.workspace_id}",
                            "parent_id": f"baseline:{batch.batch_id}",
                            "kind": "workspace",
                            "label": f"Workspace {workspace.owner_actor_id}",
                            "depth": 1,
                            "path": None,
                            "table_name": None,
                            "owner_id": workspace.owner_actor_id,
                            "status": workspace.status,
                            "commit_hash": workspace.draft_commit_hash
                            or workspace.initial_commit_hash
                            or workspace.base_main_hash,
                            "current_actor_owned": workspace.owner_actor_id == actor_id,
                        }
                    )
                    for submission in submissions_by_workspace.get(workspace.workspace_id, []):
                        tree_nodes.append(
                            _submission_tree_node_payload(
                                submission=submission,
                                workspace=workspace,
                                archive_node=archive_nodes_by_submission.get(submission.submission_id),
                                actor_id=actor_id,
                                depth=2,
                            )
                        )
                for history_node in sorted(
                    (
                        node
                        for node in self._state.baseline_archive_nodes.values()
                        if node.batch_id == batch.batch_id
                        and node.role == "BASELINE_INITIAL_HISTORY"
                    ),
                    key=lambda item: (item.created_at, item.node_id),
                ):
                    source_submission = self._state.submissions.get(history_node.source_submission_id)
                    source_workspace = self._state.workspaces.get(history_node.source_workspace_id)
                    tree_nodes.append(
                        _baseline_initial_history_tree_node_payload(
                            node=history_node,
                            source_submission=source_submission,
                            source_workspace=source_workspace,
                            depth=1,
                        )
                    )
                baselines.append(
                    {
                        "baseline": _batch_payload(batch),
                        "workspaces": workspace_items,
                    }
                )

            actor_workspace_payload = None if actor_workspace is None else _workspace_payload(actor_workspace)
            generated_at = _now()
            stable_payload = {
                "gateway": _gateway_tree_payload(gateway, current_effective_batch),
                "current_batch": _batch_payload(current_batch) if current_batch is not None else None,
                "current_effective_baseline_id": (
                    current_effective_batch.batch_id if current_effective_batch is not None else None
                ),
                "baselines": baselines,
                "actor_workspace": actor_workspace_payload,
                "submissions": all_submissions,
                "tree_nodes": tree_nodes,
                "allowed_actions": _workspace_tree_allowed_actions(
                    permissions=permission_set,
                    actor_workspace=actor_workspace,
                    current_batch=current_batch,
                    submissions=tuple(self._state.submissions.values()),
                    scoped_workspace_ids=scoped_workspace_ids,
                ),
            }
            return {
                **stable_payload,
                "tree_commit_hash": _payload_hash(stable_payload),
                "generated_at": generated_at,
            }

    def _select_actor_workspace(
        self,
        *,
        actor_id: str,
        current_batch_id: str | None,
        workspaces: list[WorkspaceRecord],
    ) -> WorkspaceRecord | None:
        actor_workspaces = [
            workspace
            for workspace in workspaces
            if workspace.owner_actor_id == actor_id
        ]
        if not actor_workspaces:
            return None
        if current_batch_id is not None:
            for workspace in sorted(actor_workspaces, key=lambda item: (item.created_at, item.workspace_id)):
                if workspace.batch_id == current_batch_id:
                    return workspace
            return None
        return sorted(actor_workspaces, key=lambda item: (item.updated_at, item.workspace_id))[-1]

    def _resolve_submission_modified_history_node(
        self,
        *,
        actor_id: str,
        gateway_device_external_key: str,
        business_project_id: str,
        submission_id: str,
        index: int,
    ) -> dict[str, object]:
        submission = self._state.submissions.get(submission_id)
        if submission is None:
            return _unresolved_history_input(
                index=index,
                kind="SUBMISSION_MODIFIED",
                node_id=submission_id,
                code="formal.submission_not_found",
                message="Submission was not found.",
            )
        workspace = self._state.workspaces.get(submission.workspace_id)
        if workspace is None:
            return _unresolved_history_input(
                index=index,
                kind="SUBMISSION_MODIFIED",
                node_id=submission_id,
                code="formal.workspace_not_found",
                message="Submission workspace was not found.",
            )
        if workspace.gateway_device_external_key != gateway_device_external_key:
            raise PermissionError("history submission gateway does not match session")
        if workspace.business_project_id != business_project_id:
            raise PermissionError("history submission project does not match session")
        del actor_id
        if not submission.submit_source_package:
            return _unresolved_history_input(
                index=index,
                kind="SUBMISSION_MODIFIED",
                node_id=submission_id,
                code="formal.submit_source_package_missing",
                message="Submission source package artifact is missing.",
            )
        return _ready_history_input(
            index=index,
            kind="SUBMISSION_MODIFIED",
            node_id=submission_id,
            display_name=f"Submission {submission.sequence_no}",
            display_metadata={
                "submission_id": submission.submission_id,
                "workspace_id": submission.workspace_id,
                "batch_id": submission.batch_id,
                "status": submission.status,
                "archive_status": submission.archive_status,
                "commit_hash": submission.repository_commit_hash or submission.modified_commit_hash,
            },
            source_package=dict(submission.submit_source_package),
        )

    def _resolve_baseline_mainline_history_node(
        self,
        *,
        gateway_device_external_key: str,
        business_project_id: str,
        batch_id: str,
        index: int,
    ) -> dict[str, object]:
        batch = self._find_batch_by_id(batch_id)
        if batch is None:
            return _unresolved_history_input(
                index=index,
                kind="BASELINE_MAINLINE",
                node_id=batch_id,
                code="formal.baseline_batch_not_found",
                message="Baseline batch was not found.",
            )
        if batch.gateway_device_external_key != gateway_device_external_key:
            raise PermissionError("history baseline gateway does not match session")
        gateway = self._state.gateways.get(gateway_device_external_key)
        if gateway is None or gateway.business_project_id != business_project_id:
            raise PermissionError("history baseline project does not match session")
        archive_node = self._find_mainline_archive_node_by_commit(
            gateway_device_external_key=gateway_device_external_key,
            commit_hash=batch.current_main_hash or batch.base_main_hash,
        )
        if archive_node is None:
            return _unresolved_history_input(
                index=index,
                kind="BASELINE_MAINLINE",
                node_id=batch_id,
                code="formal.baseline_mainline_unresolved",
                message="Baseline mainline is not backed by an archived submission artifact.",
            )
        submission = self._state.submissions.get(archive_node.source_submission_id)
        if submission is None or not submission.submit_source_package:
            return _unresolved_history_input(
                index=index,
                kind="BASELINE_MAINLINE",
                node_id=batch_id,
                code="formal.baseline_source_submission_unresolved",
                message="Archived baseline source submission artifact is missing.",
            )
        return _ready_history_input(
            index=index,
            kind="BASELINE_MAINLINE",
            node_id=batch_id,
            display_name=f"Baseline {batch.batch_no} mainline",
            display_metadata={
                "batch_id": batch.batch_id,
                "batch_no": str(batch.batch_no),
                "commit_hash": batch.current_main_hash or "",
                "source_submission_id": archive_node.source_submission_id,
                "archive_node_id": archive_node.node_id,
            },
            source_package=dict(submission.submit_source_package),
        )

    def _resolve_baseline_initial_history_node(
        self,
        *,
        gateway_device_external_key: str,
        business_project_id: str,
        node_id: str,
        index: int,
    ) -> dict[str, object]:
        normalized_node_id = node_id.removeprefix("baseline-initial-history:")
        archive_node = self._state.baseline_archive_nodes.get(normalized_node_id)
        if archive_node is None or archive_node.role != "BASELINE_INITIAL_HISTORY":
            return _unresolved_history_input(
                index=index,
                kind="BASELINE_INITIAL_HISTORY",
                node_id=node_id,
                code="formal.baseline_initial_history_unresolved",
                message="Baseline initial history node was not found.",
            )
        batch = self._find_batch_by_id(archive_node.batch_id)
        if batch is None or batch.gateway_device_external_key != gateway_device_external_key:
            raise PermissionError("history baseline initial gateway does not match session")
        gateway = self._state.gateways.get(gateway_device_external_key)
        if gateway is None or gateway.business_project_id != business_project_id:
            raise PermissionError("history baseline initial project does not match session")
        submission = self._state.submissions.get(archive_node.source_submission_id)
        if submission is None or not submission.initial_source_package:
            return _unresolved_history_input(
                index=index,
                kind="BASELINE_INITIAL_HISTORY",
                node_id=node_id,
                code="formal.baseline_initial_source_unresolved",
                message="Archived baseline initial source package is missing.",
            )
        return _ready_history_input(
            index=index,
            kind="BASELINE_INITIAL_HISTORY",
            node_id=node_id,
            display_name=f"Baseline {batch.batch_no} initial history",
            display_metadata={
                "batch_id": batch.batch_id,
                "batch_no": str(batch.batch_no),
                "commit_hash": archive_node.commit_hash,
                "source_submission_id": archive_node.source_submission_id,
                "archive_node_id": archive_node.node_id,
                "associated_mainline_node_id": archive_node.associated_mainline_node_id,
                "configuration_generated_at": archive_node.configuration_generated_at,
                "abnormal_kind": archive_node.abnormal_kind,
                "time_abnormal_reason": archive_node.time_abnormal_reason,
            },
            source_package=dict(submission.initial_source_package),
        )

    def _append_batch(
        self,
        *,
        gateway_device_external_key: str,
        base_main_hash: str,
        baseline_kind: str,
        idempotency_key: str,
    ) -> BaselineBatchRecord:
        batches = self._state.batches_by_gateway.setdefault(gateway_device_external_key, [])
        batch_no = len(batches) + 1
        now = _now()
        batch = BaselineBatchRecord(
            batch_id=f"batch:{gateway_device_external_key}:{batch_no}",
            gateway_device_external_key=gateway_device_external_key,
            batch_no=batch_no,
            base_main_hash=base_main_hash,
            baseline_kind=baseline_kind,
            status="OPEN",
            archive_gate_status="COLLECTING_CONFIRMATIONS",
            opened_at=now,
            current_main_hash=base_main_hash,
            idempotency_key=idempotency_key,
            last_activity_at=now,
        )
        batches.append(batch)
        return batch

    def _current_open_batch(self, gateway_device_external_key: str) -> BaselineBatchRecord | None:
        for batch in reversed(self._state.batches_by_gateway.get(gateway_device_external_key, [])):
            if batch.status == "OPEN":
                return batch
        return None

    def _find_batch(self, gateway_device_external_key: str, batch_id: str | None) -> BaselineBatchRecord | None:
        if batch_id is None:
            return None
        for batch in self._state.batches_by_gateway.get(gateway_device_external_key, []):
            if batch.batch_id == batch_id:
                return batch
        return None

    def _find_batch_by_id(self, batch_id: str) -> BaselineBatchRecord | None:
        for batches in self._state.batches_by_gateway.values():
            for batch in batches:
                if batch.batch_id == batch_id:
                    return batch
        return None

    def _find_mainline_archive_node_by_commit(
        self,
        *,
        gateway_device_external_key: str,
        commit_hash: str | None,
    ) -> BaselineArchiveNodeRecord | None:
        if commit_hash is None:
            return None
        candidates: list[BaselineArchiveNodeRecord] = []
        for node in self._state.baseline_archive_nodes.values():
            if node.role != "MAINLINE_MODIFIED" or node.commit_hash != commit_hash:
                continue
            node_batch = self._find_batch_by_id(node.batch_id)
            if node_batch is None or node_batch.gateway_device_external_key != gateway_device_external_key:
                continue
            candidates.append(node)
        return sorted(candidates, key=lambda item: (item.created_at, item.node_id))[-1] if candidates else None

    def _require_batch(self, batch_id: str) -> BaselineBatchRecord:
        batch = self._find_batch_by_id(batch_id)
        if batch is None:
            raise KeyError(batch_id)
        return batch

    def _require_workspace_for_batch(self, *, workspace_id: str, batch_id: str) -> WorkspaceRecord:
        workspace = self._state.workspaces.get(workspace_id)
        if workspace is None:
            raise KeyError(workspace_id)
        if workspace.batch_id != batch_id:
            raise ValueError("workspace does not belong to archive batch")
        return workspace

    def _archive_candidates_for_batch(self, batch_id: str) -> list[ArchiveCandidateRecord]:
        return sorted(
            (
                candidate
                for candidate in self._state.archive_candidates.values()
                if candidate.batch_id == batch_id
            ),
            key=lambda item: (item.created_at, item.candidate_id),
        )

    def _archive_confirmations_for_batch(self, batch_id: str) -> list[WorkspaceArchiveConfirmationRecord]:
        return sorted(
            (
                confirmation
                for confirmation in self._state.archive_confirmations.values()
                if confirmation.batch_id == batch_id
            ),
            key=lambda item: (item.confirmed_at, item.confirmation_id),
        )

    def _archive_executions_for_batch(self, batch_id: str) -> list[ArchiveExecutionRecord]:
        return sorted(
            (
                execution
                for execution in self._state.archive_executions.values()
                if execution.batch_id == batch_id
            ),
            key=lambda item: (item.created_at, item.execution_id),
        )

    def _baseline_archive_nodes_for_batch(self, batch_id: str) -> list[BaselineArchiveNodeRecord]:
        return sorted(
            (
                node
                for node in self._state.baseline_archive_nodes.values()
                if node.batch_id == batch_id
            ),
            key=lambda item: (item.created_at, item.node_id),
        )

    def _anomaly_resolutions_for_batch(self, batch_id: str) -> list[AnomalyResolutionRecord]:
        return sorted(
            (
                resolution
                for resolution in self._state.anomaly_resolutions.values()
                if resolution.batch_id == batch_id
            ),
            key=lambda item: (item.accepted_at, item.resolution_id),
        )

    def _resolution_covers(self, batch_id: str, submission_id: str, code: str) -> bool:
        return self._resolution_id_covering(batch_id, submission_id, code) is not None

    def _resolution_id_covering(self, batch_id: str, submission_id: str, code: str) -> str | None:
        for resolution in self._anomaly_resolutions_for_batch(batch_id):
            if code not in set(resolution.covered_reason_codes):
                continue
            affected_ids = set(resolution.affected_submission_ids)
            affected_ids.add(resolution.submission_id)
            if submission_id in affected_ids:
                return resolution.resolution_id
        return None

    def _batch_graph_payload(self, batch: BaselineBatchRecord, *, apply_resolutions: bool = True) -> dict[str, object]:
        baseline_state = batch.current_main_hash or batch.base_main_hash
        baseline_archive_node = self._find_mainline_archive_node_by_commit(
            gateway_device_external_key=batch.gateway_device_external_key,
            commit_hash=baseline_state,
        )
        baseline_configuration_generated_at = (
            None if baseline_archive_node is None else baseline_archive_node.configuration_generated_at
        )
        explicit_empty_first_batch = _is_explicit_empty_first_batch(batch)
        submissions = sorted(
            (
                submission
                for submission in self._state.submissions.values()
                if submission.batch_id == batch.batch_id
            ),
            key=lambda item: (item.submitted_at, item.sequence_no, item.submission_id),
        )
        approved_submissions = [
            submission
            for submission in submissions
            if submission.status == "APPROVED" and submission.archive_status == "NOT_ARCHIVED"
        ]
        pending_submission_ids = [
            submission.submission_id
            for submission in submissions
            if submission.status in {"PENDING_REVIEW", "IN_REVIEW"}
        ]
        reachable_states: set[str] = {baseline_state}
        peer_modified_states: set[str] = set()
        peer_modified_state_roots: dict[str, str] = {}
        reachable_submission_ids: list[str] = []
        unresolved_submission_ids: list[str] = []
        time_abnormal_submission_ids: list[str] = []
        blocking_reason_codes: set[str] = set()
        nodes: list[dict[str, object]] = [
            {
                "node_id": f"baseline:{batch.batch_id}",
                "node_kind": "BATCH_BASELINE",
                "state_digest": baseline_state,
                "configuration_generated_at": baseline_configuration_generated_at,
            }
        ]
        edges: list[dict[str, object]] = []
        diagnostics: list[dict[str, object]] = []

        for submission in approved_submissions:
            initial_state = submission.initial_commit_hash or submission.base_main_hash
            modified_state = submission.repository_commit_hash or submission.modified_commit_hash
            initial_time = submission.initial_configuration_generated_at
            if initial_time is None and initial_state == baseline_state:
                initial_time = baseline_configuration_generated_at
            modified_time = submission.configuration_generated_at

            nodes.extend(
                [
                    {
                        "node_id": f"submission:{submission.submission_id}:initial",
                        "node_kind": "SUBMISSION_INITIAL",
                        "submission_id": submission.submission_id,
                        "state_digest": initial_state,
                        "configuration_generated_at": initial_time,
                    },
                    {
                        "node_id": f"submission:{submission.submission_id}:modified",
                        "node_kind": "SUBMISSION_MODIFIED",
                        "submission_id": submission.submission_id,
                        "state_digest": modified_state,
                        "configuration_generated_at": modified_time,
                    },
                ]
            )
            edges.append(
                {
                    "from_node_id": f"submission:{submission.submission_id}:initial",
                    "to_node_id": f"submission:{submission.submission_id}:modified",
                    "edge_kind": "SUBMISSION_INITIAL_TO_MODIFIED",
                }
            )

            if modified_time is None:
                blocking_reason_codes.add("SUMMARY_FACT_MISSING")
                diagnostics.append(
                    {
                        "code": "SUMMARY_FACT_MISSING",
                        "submission_id": submission.submission_id,
                        "field": "configuration_generated_at",
                        "message": "Approved submission is missing FINAL modified configuration_generated_at.",
                    }
                )
            if not explicit_empty_first_batch and initial_time is None:
                blocking_reason_codes.add("SUMMARY_FACT_MISSING")
                diagnostics.append(
                    {
                        "code": "SUMMARY_FACT_MISSING",
                        "submission_id": submission.submission_id,
                        "field": "initial_configuration_generated_at",
                        "message": "Approved submission is missing FINAL initial configuration_generated_at.",
                    }
                )

            initial_dt = _parse_datetime(initial_time)
            modified_dt = _parse_datetime(modified_time)
            baseline_dt = _parse_datetime(baseline_configuration_generated_at)
            submission_time_abnormal = False
            if initial_dt is not None and modified_dt is not None and modified_dt < initial_dt:
                submission_time_abnormal = True
                blocking_reason_codes.add("TIME_ABNORMAL_MODIFIED")
                diagnostics.append(
                    {
                        "code": "TIME_ABNORMAL_MODIFIED",
                        "submission_id": submission.submission_id,
                        "message": "Modified configuration_generated_at is earlier than initial.",
                    }
                )
            if (
                not explicit_empty_first_batch
                and initial_dt is not None
                and baseline_dt is not None
                and initial_dt < baseline_dt
            ):
                submission_time_abnormal = True
                blocking_reason_codes.add("TIME_ABNORMAL_INITIAL")
                diagnostics.append(
                    {
                        "code": "TIME_ABNORMAL_INITIAL",
                        "submission_id": submission.submission_id,
                        "message": "Initial configuration_generated_at is earlier than baseline.",
                    }
                )
            if modified_dt is not None and baseline_dt is not None and modified_dt < baseline_dt:
                submission_time_abnormal = True
                blocking_reason_codes.add("TIME_ABNORMAL_MODIFIED")
                diagnostics.append(
                    {
                        "code": "TIME_ABNORMAL_MODIFIED",
                        "submission_id": submission.submission_id,
                        "message": "Modified configuration_generated_at is earlier than baseline.",
                    }
                )
            if submission_time_abnormal:
                time_abnormal_submission_ids.append(submission.submission_id)

            if explicit_empty_first_batch or initial_state in reachable_states:
                reachable_submission_ids.append(submission.submission_id)
                reachable_states.add(modified_state)
                peer_modified_states.add(modified_state)
            elif initial_state in peer_modified_states:
                root_submission_id = peer_modified_state_roots.get(initial_state)
                reachable_submission_ids.append(submission.submission_id)
                peer_modified_states.add(modified_state)
                if root_submission_id is not None:
                    peer_modified_state_roots[modified_state] = root_submission_id
                diagnostics.append(
                    {
                        "code": "PEER_CHAIN_MATCH",
                        "submission_id": submission.submission_id,
                        "root_submission_id": root_submission_id,
                        "message": "Submission initial state is explained by a peer modified state.",
                    }
                )
            else:
                unresolved_submission_ids.append(submission.submission_id)
                blocking_reason_codes.add("UNRESOLVED_INITIAL_STATE")
                diagnostics.append(
                    {
                        "code": "UNRESOLVED_INITIAL_STATE",
                        "submission_id": submission.submission_id,
                        "message": "Submission initial state is not reachable from baseline or peer chain.",
                    }
                )
                peer_modified_states.add(modified_state)
                peer_modified_state_roots[modified_state] = submission.submission_id

        raw_blocking_reason_codes = sorted(blocking_reason_codes)
        resolved_reason_codes = (
            _resolved_reason_codes_for_batch(
                self._anomaly_resolutions_for_batch(batch.batch_id),
                diagnostics,
            )
            if apply_resolutions
            else []
        )
        effective_blocking_reason_codes = [
            code for code in raw_blocking_reason_codes if code not in set(resolved_reason_codes)
        ]
        overall_status = "PASS" if not effective_blocking_reason_codes else "BLOCKED"
        if pending_submission_ids and not effective_blocking_reason_codes:
            overall_status = "PENDING_REVIEW"
        return {
            "schema_version": "batch-graph/v1",
            "overall_status": overall_status,
            "blocking_reason_codes": effective_blocking_reason_codes,
            "raw_blocking_reason_codes": raw_blocking_reason_codes,
            "resolved_reason_codes": resolved_reason_codes,
            "reachable_submission_ids": reachable_submission_ids,
            "pending_submission_ids": pending_submission_ids,
            "unresolved_submission_ids": unresolved_submission_ids,
            "time_abnormal_submission_ids": time_abnormal_submission_ids,
            "nodes": nodes,
            "edges": edges,
            "diagnostics": diagnostics,
        }

    def _archive_snapshot_payload(self, batch: BaselineBatchRecord) -> dict[str, object]:
        confirmations = [
            _archive_confirmation_payload(record)
            for record in self._archive_confirmations_for_batch(batch.batch_id)
        ]
        candidates = [
            _archive_candidate_payload(record)
            for record in self._archive_candidates_for_batch(batch.batch_id)
        ]
        executions = [
            _archive_execution_payload(record)
            for record in self._archive_executions_for_batch(batch.batch_id)
        ]
        nodes = [
            _baseline_archive_node_payload(record)
            for record in self._baseline_archive_nodes_for_batch(batch.batch_id)
        ]
        anomaly_resolutions = [
            _anomaly_resolution_payload(record)
            for record in self._anomaly_resolutions_for_batch(batch.batch_id)
        ]
        selection = self._state.archive_selections.get(batch.batch_id, {})
        batch_graph = self._batch_graph_payload(batch)
        workspace_confirmation_set_hash = _payload_hash(
            {
                "batch_id": batch.batch_id,
                "confirmations": confirmations,
            }
        )
        candidate_set_hash = _payload_hash(
            {
                "batch_id": batch.batch_id,
                "candidates": candidates,
                "selection": selection,
            }
        )
        failure_reasons = self._archive_failure_reasons(
            batch,
            {
                "confirmations": confirmations,
                "candidates": candidates,
                "selected_modified_candidate_id": selection.get("selected_modified_candidate_id"),
                "workspace_confirmation_set_hash": workspace_confirmation_set_hash,
                "candidate_set_hash": candidate_set_hash,
                "batch_graph": batch_graph,
            },
        )
        return {
            "baseline_batch": _batch_payload(batch),
            "confirmations": confirmations,
            "candidates": candidates,
            "execution_records": executions,
            "anomaly_resolutions": anomaly_resolutions,
            "baseline_archive_nodes": nodes,
            "selected_modified_candidate_id": selection.get("selected_modified_candidate_id"),
            "selected_initial_candidate_ids": list(selection.get("selected_initial_candidate_ids", [])),
            "workspace_confirmation_set_hash": workspace_confirmation_set_hash,
            "candidate_set_hash": candidate_set_hash,
            "eligible_for_execute": not failure_reasons,
            "failure_reasons": failure_reasons,
            "batch_graph": batch_graph,
        }

    def _archive_failure_reasons(
        self,
        batch: BaselineBatchRecord,
        snapshot: dict[str, object],
    ) -> list[str]:
        reasons: list[str] = []
        if batch.status != "OPEN":
            reasons.append("batch is not open")
        if batch.archive_gate_status != "READY_FOR_ARCHIVE":
            reasons.append("archive gate is not ready")
        graph = snapshot.get("batch_graph")
        if isinstance(graph, dict):
            for code in graph.get("blocking_reason_codes", []):
                if isinstance(code, str):
                    reasons.append(f"batch graph blocked: {code}")
        selected = snapshot.get("selected_modified_candidate_id")
        if not isinstance(selected, str) or not selected:
            reasons.append("selected modified candidate is missing")
            return reasons
        candidate = self._state.archive_candidates.get(selected)
        if candidate is None:
            reasons.append("selected modified candidate was not found")
            return reasons
        confirmation = self._state.archive_confirmations.get(
            f"archive-confirmation:{batch.batch_id}:{candidate.workspace_id}"
        )
        if confirmation is None or confirmation.archive_candidate_id != candidate.candidate_id:
            reasons.append("selected modified candidate is not confirmed")
        submission = self._state.submissions.get(candidate.source_submission_id)
        if submission is None or submission.repository_commit_hash is None:
            reasons.append("selected submission is missing repository commit hash")
        return reasons

    def _archive_execute_payload(
        self,
        *,
        batch: BaselineBatchRecord,
        execution: ArchiveExecutionRecord,
        idempotent_replay: bool,
    ) -> dict[str, object]:
        snapshot = self._archive_snapshot_payload(batch)
        return {
            "eligibility": {
                "baseline_batch": _batch_payload(batch),
                "repo_probe": {
                    "repo_mode": "formal",
                    "current_main_hash": batch.current_main_hash,
                },
                "eligible_for_execute": True,
                "eligible_for_dry_run": True,
                "failure_reasons": [],
                "unconfirmed_workspace_ids": [],
                "selected_modified_candidate_id": execution.selected_modified_candidate_id,
                "selected_initial_candidate_ids": list(execution.selected_initial_candidate_ids),
                "confirmation_summary": _count_by(snapshot["confirmations"], "status"),
                "candidate_summary": _count_by(snapshot["candidates"], "status"),
            },
            "baseline_batch": _batch_payload(batch),
            "execution_record": _archive_execution_payload(execution),
            "baseline_archive_nodes": [
                _baseline_archive_node_payload(record)
                for record in self._baseline_archive_nodes_for_batch(batch.batch_id)
            ],
            "idempotent_replay": idempotent_replay,
        }

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        gateways = {
            key: GatewayDeviceRecord(**value)
            for key, value in raw.get("gateways", {}).items()
        }
        batches_by_gateway = {
            key: [BaselineBatchRecord(**item) for item in value]
            for key, value in raw.get("batches_by_gateway", {}).items()
        }
        workspaces = {
            key: WorkspaceRecord(**value)
            for key, value in raw.get("workspaces", {}).items()
        }
        preview_bundles = {
            key: PreviewBundleRecord(**value)
            for key, value in raw.get("preview_bundles", {}).items()
        }
        submissions = {
            key: SubmissionRecord(
                **{
                    **value,
                    "submit_operation": (
                        None
                        if value.get("submit_operation") is None
                        else SubmitOperationRecord(**value["submit_operation"])
                    ),
                }
            )
            for key, value in raw.get("submissions", {}).items()
        }
        archive_candidates = {
            key: ArchiveCandidateRecord(**value)
            for key, value in raw.get("archive_candidates", {}).items()
        }
        archive_confirmations = {
            key: WorkspaceArchiveConfirmationRecord(**value)
            for key, value in raw.get("archive_confirmations", {}).items()
        }
        anomaly_resolutions = {
            key: AnomalyResolutionRecord(
                **{
                    **value,
                    "affected_submission_ids": tuple(value.get("affected_submission_ids", [])),
                    "covered_reason_codes": tuple(value.get("covered_reason_codes", [])),
                }
            )
            for key, value in raw.get("anomaly_resolutions", {}).items()
        }
        archive_executions = {
            key: ArchiveExecutionRecord(
                **{
                    **value,
                    "selected_initial_candidate_ids": tuple(
                        value.get("selected_initial_candidate_ids", [])
                    ),
                }
            )
            for key, value in raw.get("archive_executions", {}).items()
        }
        baseline_archive_nodes = {
            key: BaselineArchiveNodeRecord(**value)
            for key, value in raw.get("baseline_archive_nodes", {}).items()
        }
        history_comparisons = {
            key: HistoryComparisonRecord(**value)
            for key, value in raw.get("history_comparisons", {}).items()
        }
        self._state = _State(
            gateways=gateways,
            batches_by_gateway=batches_by_gateway,
            workspaces=workspaces,
            preview_bundles=preview_bundles,
            submissions=submissions,
            archive_candidates=archive_candidates,
            archive_confirmations=archive_confirmations,
            anomaly_resolutions=anomaly_resolutions,
            archive_executions=archive_executions,
            baseline_archive_nodes=baseline_archive_nodes,
            archive_selections={
                key: dict(value)
                for key, value in raw.get("archive_selections", {}).items()
            },
            history_comparisons=history_comparisons,
            next_submission_sequence=int(raw.get("next_submission_sequence", len(submissions) + 1)),
        )

    def _save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "gateways": {
                key: asdict(value)
                for key, value in sorted(self._state.gateways.items())
            },
            "batches_by_gateway": {
                key: [asdict(item) for item in value]
                for key, value in sorted(self._state.batches_by_gateway.items())
            },
            "workspaces": {
                key: asdict(value)
                for key, value in sorted(self._state.workspaces.items())
            },
            "preview_bundles": {
                key: asdict(value)
                for key, value in sorted(self._state.preview_bundles.items())
            },
            "submissions": {
                key: asdict(value)
                for key, value in sorted(self._state.submissions.items())
            },
            "archive_candidates": {
                key: asdict(value)
                for key, value in sorted(self._state.archive_candidates.items())
            },
            "archive_confirmations": {
                key: asdict(value)
                for key, value in sorted(self._state.archive_confirmations.items())
            },
            "anomaly_resolutions": {
                key: asdict(value)
                for key, value in sorted(self._state.anomaly_resolutions.items())
            },
            "archive_executions": {
                key: asdict(value)
                for key, value in sorted(self._state.archive_executions.items())
            },
            "baseline_archive_nodes": {
                key: asdict(value)
                for key, value in sorted(self._state.baseline_archive_nodes.items())
            },
            "archive_selections": {
                key: dict(value)
                for key, value in sorted(self._state.archive_selections.items())
            },
            "history_comparisons": {
                key: asdict(value)
                for key, value in sorted(self._state.history_comparisons.items())
            },
            "next_submission_sequence": self._state.next_submission_sequence,
        }
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def _batch_payload(batch: BaselineBatchRecord) -> dict[str, object]:
    return {
        "batch_id": batch.batch_id,
        "gateway_device_external_key": batch.gateway_device_external_key,
        "batch_no": batch.batch_no,
        "base_main_hash": batch.base_main_hash,
        "baseline_kind": batch.baseline_kind,
        "status": batch.status,
        "archive_gate_status": batch.archive_gate_status,
        "opened_at": batch.opened_at,
        "current_main_hash": batch.current_main_hash,
        "closed_at": batch.closed_at,
        "invalidated_at": batch.invalidated_at,
        "workspace_confirmation_set_hash": batch.workspace_confirmation_set_hash,
        "candidate_set_hash": batch.candidate_set_hash,
        "selected_modified_candidate_id": batch.selected_modified_candidate_id,
        "selected_initial_candidate_ids": list(batch.selected_initial_candidate_ids),
    }


def _is_explicit_empty_first_batch(batch: BaselineBatchRecord) -> bool:
    return batch.batch_no == 1 and batch.baseline_kind == "EXPLICIT_EMPTY"


def _gateway_tree_payload(
    gateway: GatewayDeviceRecord,
    current_effective_batch: BaselineBatchRecord | None,
) -> dict[str, object]:
    return {
        "gateway_device_id": gateway.gateway_device_id,
        "gateway_device_external_key": gateway.gateway_device_external_key,
        "display_name": gateway.display_name,
        "status": gateway.status,
        "business_project_id": gateway.business_project_id,
        "repo_key": gateway.repo_key,
        "artifact_root_key": gateway.artifact_root_key,
        "current_main_hash": (
            current_effective_batch.current_main_hash
            if current_effective_batch is not None
            else None
        ),
    }


def _workspace_payload(record: WorkspaceRecord) -> dict[str, object]:
    return {
        "id": record.workspace_id,
        "baseline_batch_id": record.batch_id,
        "owner_actor_id": record.owner_actor_id,
        "gateway_device_external_key": record.gateway_device_external_key,
        "business_project_id": record.business_project_id,
        "status": record.status,
        "upload_mode": record.upload_mode,
        "base_main_hash": record.base_main_hash,
        "draft_commit_hash": record.draft_commit_hash,
        "initial_commit_hash": record.initial_commit_hash,
        "initial_configuration_generated_at": record.initial_configuration_generated_at,
        "submitted_submission_id": record.submitted_submission_id,
        "locked_reason": None,
        "latest_preview": record.latest_preview,
        "latest_upload_semantics": record.latest_upload_semantics,
        "latest_baseline_source": record.latest_baseline_source,
    }


def _submission_tree_node_payload(
    *,
    submission: SubmissionRecord,
    workspace: WorkspaceRecord,
    archive_node: BaselineArchiveNodeRecord | None,
    actor_id: str,
    depth: int,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "node_id": f"submission:{submission.submission_id}",
        "parent_id": f"workspace:{workspace.workspace_id}",
        "kind": "submission",
        "label": f"Submission {submission.sequence_no}",
        "depth": depth,
        "path": None,
        "table_name": None,
        "owner_id": submission.submitter_actor_id,
        "status": submission.status,
        "commit_hash": submission.repository_commit_hash or submission.modified_commit_hash,
        "current_actor_owned": submission.submitter_actor_id == actor_id,
        "source_submission_id": submission.submission_id,
        "source_workspace_id": workspace.workspace_id,
        "source_submitter_actor_id": submission.submitter_actor_id,
        "source_submitted_at": submission.submitted_at,
        "source_reviewer_actor_id": submission.reviewed_by_actor_id,
        "source_reviewed_at": submission.reviewed_at,
    }
    if archive_node is not None:
        payload.update(
            {
                "archive_node_id": archive_node.node_id,
                "archive_node_role": archive_node.role,
                "retained_by_actor_id": archive_node.created_by_actor_id,
                "retained_at": archive_node.created_at,
                "retention_reason": "Archived as mainline.",
                "associated_mainline_node_id": archive_node.associated_mainline_node_id,
                "configuration_generated_at": archive_node.configuration_generated_at,
                "abnormal_kind": archive_node.abnormal_kind,
                "time_abnormal_reason": archive_node.time_abnormal_reason,
            }
        )
    else:
        payload.update(
            {
                "archive_node_id": None,
                "archive_node_role": None,
                "retained_by_actor_id": None,
                "retained_at": None,
                "retention_reason": None,
                "associated_mainline_node_id": None,
                "configuration_generated_at": submission.configuration_generated_at,
                "abnormal_kind": None,
                "time_abnormal_reason": None,
            }
        )
    return payload


def _baseline_initial_history_tree_node_payload(
    *,
    node: BaselineArchiveNodeRecord,
    source_submission: SubmissionRecord | None,
    source_workspace: WorkspaceRecord | None,
    depth: int,
) -> dict[str, object]:
    return {
        "node_id": f"baseline-initial-history:{node.node_id}",
        "parent_id": f"baseline:{node.batch_id}",
        "kind": "baseline_initial_history",
        "label": "Baseline Initial History",
        "depth": depth,
        "path": None,
        "table_name": None,
        "owner_id": None if source_submission is None else source_submission.submitter_actor_id,
        "status": "ARCHIVED",
        "commit_hash": node.commit_hash,
        "current_actor_owned": False,
        "archive_node_id": node.node_id,
        "archive_node_role": node.role,
        "source_submission_id": node.source_submission_id,
        "source_workspace_id": node.source_workspace_id,
        "source_submitter_actor_id": None if source_submission is None else source_submission.submitter_actor_id,
        "source_submitted_at": None if source_submission is None else source_submission.submitted_at,
        "source_reviewer_actor_id": None if source_submission is None else source_submission.reviewed_by_actor_id,
        "source_reviewed_at": None if source_submission is None else source_submission.reviewed_at,
        "source_workspace_owner_actor_id": None if source_workspace is None else source_workspace.owner_actor_id,
        "retained_by_actor_id": node.created_by_actor_id,
        "retained_at": node.created_at,
        "retention_reason": "Archived as baseline initial history.",
        "associated_mainline_node_id": node.associated_mainline_node_id,
        "configuration_generated_at": node.configuration_generated_at,
        "abnormal_kind": node.abnormal_kind,
        "time_abnormal_reason": node.time_abnormal_reason,
    }


def _workspace_tree_allowed_actions(
    *,
    permissions: set[str],
    actor_workspace: WorkspaceRecord | None,
    current_batch: BaselineBatchRecord | None,
    submissions: tuple[SubmissionRecord, ...],
    scoped_workspace_ids: set[str],
) -> list[dict[str, object]]:
    can_upload = "upload_submit_workspace" in permissions
    can_review = "review_submission" in permissions
    can_archive = "archive_mainline" in permissions
    approved_not_archived = any(
        submission.workspace_id in scoped_workspace_ids
        and submission.status == "APPROVED"
        and submission.archive_status == "NOT_ARCHIVED"
        for submission in submissions
    )
    actor_has_mutable_workspace = (
        actor_workspace is not None
        and actor_workspace.status not in {"SUBMITTED", "CLOSED"}
    )
    explicit_empty_first_batch = (
        current_batch is not None and _is_explicit_empty_first_batch(current_batch)
    )
    actor_has_preview = (
        actor_workspace is not None
        and actor_workspace.latest_preview is not None
        and actor_workspace.status not in {"SUBMITTED", "CLOSED"}
    )
    return [
        _action_state(
            "create_or_get_workspace",
            allowed=can_upload and current_batch is not None,
            denied_reason=(
                "upload_submit_workspace permission is required"
                if not can_upload
                else "no open baseline batch"
            ),
        ),
        _action_state(
            "upload_initial_snapshot",
            allowed=can_upload and actor_has_mutable_workspace and not explicit_empty_first_batch,
            denied_reason=(
                "upload_submit_workspace permission is required"
                if not can_upload
                else (
                    "initial snapshot is disabled for explicit empty first baseline"
                    if explicit_empty_first_batch
                    else "actor workspace is not ready for initial upload"
                )
            ),
        ),
        _action_state(
            "upload_modified_snapshot",
            allowed=can_upload and actor_has_mutable_workspace,
            denied_reason=(
                "upload_submit_workspace permission is required"
                if not can_upload
                else "actor workspace is not ready for upload"
            ),
        ),
        _action_state(
            "submit_workspace",
            allowed=can_upload and actor_has_preview,
            denied_reason=(
                "upload_submit_workspace permission is required"
                if not can_upload
                else "actor workspace has no ready preview"
            ),
        ),
        _action_state(
            "review_submission",
            allowed=can_review,
            denied_reason="review_submission permission is required",
        ),
        _action_state(
            "archive_mainline",
            allowed=can_archive and approved_not_archived,
            denied_reason=(
                "archive_mainline permission is required"
                if not can_archive
                else "no approved submission is ready for archive"
            ),
        ),
    ]


def _action_state(action: str, *, allowed: bool, denied_reason: str) -> dict[str, object]:
    return {
        "action": action,
        "allowed": allowed,
        "reason": None if allowed else denied_reason,
    }


def _reopen_workspace_after_terminal_submission(record: WorkspaceRecord, *, now: str) -> None:
    record.status = "INITIAL_READY"
    record.submitted_submission_id = None
    record.latest_preview = None
    record.draft_commit_hash = None
    record.updated_at = now


def _submit_operation_payload(record: SubmitOperationRecord) -> dict[str, object]:
    return {
        "submit_operation_id": record.submit_operation_id,
        "workspace_id": record.workspace_id,
        "submission_id": record.submission_id,
        "preview_token": record.preview_token,
        "preview_revision_id": record.preview_revision_id,
        "preview_strategy_manifest_ref": record.preview_strategy_manifest_ref,
        "preview_strategy_manifest_digest": record.preview_strategy_manifest_digest,
        "preview_bundle_digest": record.preview_bundle_digest,
        "source_artifact_ref": record.source_artifact_ref,
        "source_artifact_payload_sha256": record.source_artifact_payload_sha256,
        "final_modified_commit_hash": record.final_modified_commit_hash,
        "status": record.status,
        "error_code": record.error_code,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _submission_payload(record: SubmissionRecord) -> dict[str, object]:
    return {
        "id": record.submission_id,
        "workspace_id": record.workspace_id,
        "batch_id": record.batch_id,
        "sequence_no": record.sequence_no,
        "submitter_actor_id": record.submitter_actor_id,
        "preview_token": record.preview_token,
        "baseline_kind": record.baseline_kind,
        "base_main_hash": record.base_main_hash,
        "initial_commit_hash": record.initial_commit_hash,
        "modified_commit_hash": record.modified_commit_hash,
        "preview_revision_id": record.preview_revision_id,
        "preview_strategy_manifest_ref": record.preview_strategy_manifest_ref,
        "preview_strategy_manifest_digest": record.preview_strategy_manifest_digest,
        "preview_bundle_digest": record.preview_bundle_digest,
        "preview_bundle_id": record.preview_bundle_id,
        "baseline_alignment": record.baseline_alignment,
        "preview_manifest_ref": record.preview_manifest_ref,
        "preview_index_ref": record.preview_index_ref,
        "preview_bundle_root_ref": record.preview_bundle_root_ref,
        "status": record.status,
        "archive_status": record.archive_status,
        "transfer_status": record.transfer_status,
        "submitted_at": record.submitted_at,
        "reviewed_at": record.reviewed_at,
        "reviewed_by_actor_id": record.reviewed_by_actor_id,
        "withdrawn_at": record.withdrawn_at,
        "withdrawn_by_actor_id": record.withdrawn_by_actor_id,
        "initial_configuration_generated_at": record.initial_configuration_generated_at,
        "configuration_generated_at": record.configuration_generated_at,
        "repository_id": record.repository_id,
        "repository_target_ref": record.repository_target_ref,
        "repository_commit_hash": record.repository_commit_hash,
        "snapshot_rows_artifact_ref": (
            None
            if record.snapshot_rows_artifact_ref is None
            else dict(record.snapshot_rows_artifact_ref)
        ),
        "snapshot_rows_artifact_stats": dict(record.snapshot_rows_artifact_stats),
    }


def _archive_candidate_payload(record: ArchiveCandidateRecord) -> dict[str, object]:
    return {
        "id": record.candidate_id,
        "batch_id": record.batch_id,
        "workspace_id": record.workspace_id,
        "source_submission_id": record.source_submission_id,
        "source_kind": record.source_kind,
        "role": record.role,
        "base_main_hash": record.base_main_hash,
        "initial_commit_hash": record.initial_commit_hash,
        "modified_commit_hash": record.modified_commit_hash,
        "preview_revision_id": record.preview_revision_id,
        "preview_strategy_manifest_digest": record.preview_strategy_manifest_digest,
        "preview_bundle_digest": record.preview_bundle_digest,
        "preview_bundle_id": record.preview_bundle_id,
        "status": record.status,
        "override_reason": record.override_reason,
        "configuration_generated_at": record.configuration_generated_at,
        "abnormal_kind": record.abnormal_kind,
        "time_abnormal_reason": record.time_abnormal_reason,
    }


def _archive_confirmation_payload(record: WorkspaceArchiveConfirmationRecord) -> dict[str, object]:
    return {
        "id": record.confirmation_id,
        "batch_id": record.batch_id,
        "workspace_id": record.workspace_id,
        "status": record.status,
        "archive_candidate_id": record.archive_candidate_id,
        "confirmed_by_actor_id": record.confirmed_by_actor_id,
        "confirmed_at": record.confirmed_at,
        "reason": record.reason,
    }


def _archive_execution_payload(record: ArchiveExecutionRecord) -> dict[str, object]:
    return {
        "id": record.execution_id,
        "batch_id": record.batch_id,
        "command_idempotency_key": record.command_idempotency_key,
        "requested_by_actor_id": record.requested_by_actor_id,
        "selected_modified_candidate_id": record.selected_modified_candidate_id,
        "selected_initial_candidate_ids": list(record.selected_initial_candidate_ids),
        "old_main_hash": record.old_main_hash,
        "new_main_hash": record.new_main_hash,
        "status": record.status,
        "transfer_status": record.transfer_status,
        "failure_reason": record.failure_reason,
        "created_at": record.created_at,
    }


def _baseline_archive_node_payload(record: BaselineArchiveNodeRecord) -> dict[str, object]:
    return {
        "id": record.node_id,
        "batch_id": record.batch_id,
        "role": record.role,
        "commit_hash": record.commit_hash,
        "immutable_ref": record.immutable_ref,
        "summary_ref": record.summary_ref,
        "source_submission_id": record.source_submission_id,
        "source_workspace_id": record.source_workspace_id,
        "source_candidate_id": record.source_candidate_id,
        "archive_execution_id": record.archive_execution_id,
        "created_by_actor_id": record.created_by_actor_id,
        "created_at": record.created_at,
        "associated_mainline_node_id": record.associated_mainline_node_id,
        "anomaly_resolution_id": record.anomaly_resolution_id,
        "configuration_generated_at": record.configuration_generated_at,
        "abnormal_kind": record.abnormal_kind,
        "time_abnormal_reason": record.time_abnormal_reason,
        "snapshot_rows_artifact_ref": (
            None
            if record.snapshot_rows_artifact_ref is None
            else dict(record.snapshot_rows_artifact_ref)
        ),
        "snapshot_rows_artifact_stats": dict(record.snapshot_rows_artifact_stats),
    }


def _anomaly_resolution_payload(record: AnomalyResolutionRecord) -> dict[str, object]:
    return {
        "id": record.resolution_id,
        "resolution_id": record.resolution_id,
        "batch_id": record.batch_id,
        "workspace_id": record.workspace_id,
        "submission_id": record.submission_id,
        "resolution_type": record.resolution_type,
        "reason": record.reason,
        "accepted_by_actor_id": record.accepted_by_actor_id,
        "accepted_at": record.accepted_at,
        "affected_submission_ids": list(record.affected_submission_ids),
        "abnormal_kind": record.abnormal_kind,
        "time_abnormal_reason": record.time_abnormal_reason,
        "covered_reason_codes": list(record.covered_reason_codes),
    }


def _resolved_reason_codes_for_batch(
    resolutions: list[AnomalyResolutionRecord],
    diagnostics: list[dict[str, object]],
) -> list[str]:
    blocking_diagnostics_by_code: dict[str, list[dict[str, object]]] = {}
    for diagnostic in diagnostics:
        code = diagnostic.get("code")
        submission_id = diagnostic.get("submission_id")
        if not isinstance(code, str) or not isinstance(submission_id, str):
            continue
        if code == "PEER_CHAIN_MATCH":
            continue
        blocking_diagnostics_by_code.setdefault(code, []).append(diagnostic)

    resolved_codes: list[str] = []
    for code, code_diagnostics in sorted(blocking_diagnostics_by_code.items()):
        if code_diagnostics and all(
            _diagnostic_is_covered_by_resolution(diagnostic, code, resolutions)
            for diagnostic in code_diagnostics
        ):
            resolved_codes.append(code)
    return resolved_codes


def _diagnostic_is_covered_by_resolution(
    diagnostic: dict[str, object],
    code: str,
    resolutions: list[AnomalyResolutionRecord],
) -> bool:
    submission_id = diagnostic.get("submission_id")
    if not isinstance(submission_id, str):
        return False
    for resolution in resolutions:
        if code not in set(resolution.covered_reason_codes):
            continue
        affected_ids = set(resolution.affected_submission_ids)
        affected_ids.add(resolution.submission_id)
        if submission_id in affected_ids:
            return True
    return False


def _peer_chain_downstream_submission_ids(
    graph: dict[str, object],
    root_submission_id: str,
) -> tuple[str, ...]:
    affected_ids = [root_submission_id]
    for diagnostic in graph.get("diagnostics", []):
        if not isinstance(diagnostic, dict):
            continue
        if diagnostic.get("code") != "PEER_CHAIN_MATCH":
            continue
        if diagnostic.get("root_submission_id") != root_submission_id:
            continue
        submission_id = diagnostic.get("submission_id")
        if isinstance(submission_id, str):
            affected_ids.append(submission_id)
    return tuple(dict.fromkeys(affected_ids))


def _history_comparison_payload(record: HistoryComparisonRecord) -> dict[str, object]:
    return {
        "schema_version": "history-comparison-response/v1",
        "operation": {
            "operation_id": record.operation_id,
            "status": record.status,
            "input_nodes": list(record.input_nodes),
            "pair_plan": list(record.pair_plan),
            "bundle_contract_version": "history-comparison-bundle/v1",
            "comparison_surface_contract_version": "comparison-surface/v1",
            "submitted_at": record.submitted_at,
            "updated_at": record.updated_at,
            "retryable": False,
            "message": None,
            "diagnostics": list(record.diagnostics),
        },
        "bundle": None if record.bundle is None else dict(record.bundle),
        "comparison_bundle_download": (
            None
            if record.comparison_bundle_download is None
            else dict(record.comparison_bundle_download)
        ),
    }


def _ready_history_input(
    *,
    index: int,
    kind: str,
    node_id: str,
    display_name: str,
    display_metadata: dict[str, object],
    source_package: dict[str, object],
) -> dict[str, object]:
    return {
        "index": index,
        "kind": kind,
        "id": node_id,
        "comparable_status": "READY",
        "summary_status": "READY",
        "display_name": display_name,
        "display_metadata": {key: str(value) for key, value in display_metadata.items()},
        "diagnostics": [],
        "source_package": dict(source_package),
    }


def _unresolved_history_input(
    *,
    index: int,
    kind: str,
    node_id: str,
    code: str,
    message: str,
) -> dict[str, object]:
    return {
        "index": index,
        "kind": kind,
        "id": node_id,
        "comparable_status": "UNRESOLVED",
        "summary_status": "UNRESOLVED",
        "display_name": None,
        "display_metadata": {},
        "diagnostics": [
            {
                "code": code,
                "message": message,
                "severity": "warning",
                "input_indexes": [index],
            }
        ],
    }


def _payload_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _count_by(items: object, key: str) -> dict[str, int]:
    if not isinstance(items, list):
        return {}
    counts: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        value = item.get(key)
        if isinstance(value, str) and value:
            counts[value] = counts.get(value, 0) + 1
    return counts


def _string_digest_payload(value: object) -> str:
    if isinstance(value, str) and value:
        return value
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        payload = to_payload()
        if isinstance(payload, str) and payload:
            return payload
    raise ValueError("digest payload must be a non-empty string")


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
