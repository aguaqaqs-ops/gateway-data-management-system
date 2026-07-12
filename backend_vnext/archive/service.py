from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from ..archive.closeout import open_ref_closeout
from ..contracts.repository import (
    PromoteMainlineRequest,
    RepositoryOperationContext,
    RepositoryRefSnapshot,
    RepositoryServicePort,
)
from ..archive.digests import (
    compute_candidate_set_hash,
    compute_command_payload_hash,
    compute_workspace_confirmation_set_hash,
    normalize_candidate_ids,
)
from ..archive.execution import (
    build_promote_mainline_request,
    build_repository_ref_snapshot,
    mark_archive_statuses,
)
from ..archive.policy import (
    candidate_source_kind_from_submission,
    initial_history_resolution_failure,
    require_batch_open,
    validate_mainline_candidate,
)
from ..archive.selection import ArchiveBatchSnapshot, build_batch_snapshot, ensure_snapshot_matches_command
from ..capabilities.snapshot_materialization import SnapshotMaterializationResult
from ..repository_server import (
    RepositoryRefTimeoutPolicy,
    RepositoryTableAccessProvider,
)
from ..submissions.models import SubmissionStatus
from ..submissions.store import SubmissionStore
from ..workspaces.models import WorkspaceRecord, WorkspaceStatus
from ..workspaces.store import WorkspaceStore
from .models import (
    AnomalyResolutionType,
    ArchiveAnomalyResolutionRecord,
    ArchiveBatchRecord,
    ArchiveCandidateRecord,
    ArchiveCandidateRole,
    ArchiveCandidateSourceKind,
    ArchiveCandidateStatus,
    ArchiveExecutionRecord,
    ArchiveExecutionStatus,
    ArchiveExecutionTransferStatus,
    WorkspaceArchiveConfirmationRecord,
    WorkspaceArchiveConfirmationStatus,
    BaselineBatchArchiveGateStatus,
    BaselineBatchStatus,
)
from .store import ArchiveStore


@dataclass(frozen=True, slots=True)
class ArchiveOpenBatchCommand:
    batch_id: str
    repository_id: str
    base_main_hash: str
    opened_by_actor_id: str
    open_reason: str
    workspace_ids: tuple[str, ...] = ()
    opened_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in ("batch_id", "repository_id", "base_main_hash", "opened_by_actor_id", "open_reason"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.opened_at is not None and (not isinstance(self.opened_at, datetime) or self.opened_at.tzinfo is None):
            raise ValueError("opened_at must be a timezone-aware datetime or None")
        for workspace_id in self.workspace_ids:
            if not isinstance(workspace_id, str) or not workspace_id:
                raise ValueError("workspace_ids must contain non-empty strings")


@dataclass(frozen=True, slots=True)
class ArchiveOpenBatchResult:
    batch: ArchiveBatchRecord
    workspaces: tuple[WorkspaceRecord, ...]


@dataclass(frozen=True, slots=True)
class ArchiveConfirmWorkspaceCommand:
    batch_id: str
    workspace_id: str
    actor_id: str
    archive_candidate_id: str | None = None
    reason: str | None = None
    confirmed_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in ("batch_id", "workspace_id", "actor_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.archive_candidate_id is not None and (not isinstance(self.archive_candidate_id, str) or not self.archive_candidate_id):
            raise ValueError("archive_candidate_id must be a non-empty string or None")
        if self.reason is not None and (not isinstance(self.reason, str) or not self.reason):
            raise ValueError("reason must be a non-empty string or None")
        if self.confirmed_at is not None and (not isinstance(self.confirmed_at, datetime) or self.confirmed_at.tzinfo is None):
            raise ValueError("confirmed_at must be a timezone-aware datetime or None")


@dataclass(frozen=True, slots=True)
class ArchiveConfirmWorkspaceResult:
    batch: ArchiveBatchRecord
    confirmation: WorkspaceArchiveConfirmationRecord


@dataclass(frozen=True, slots=True)
class ArchiveCandidateUpsertCommand:
    batch_id: str
    workspace_id: str
    source_kind: ArchiveCandidateSourceKind | str
    role: ArchiveCandidateRole | str
    source_submission_id: str | None = None
    candidate_id: str | None = None
    override_reason: str | None = None
    selected_for_archive: bool = False
    anomaly_resolution_required: bool = False
    configuration_generated_at: datetime | None = None
    abnormal_kind: str | None = None
    time_abnormal_reason: str | None = None
    created_by_actor_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("batch_id", "workspace_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.candidate_id is not None and (not isinstance(self.candidate_id, str) or not self.candidate_id):
            raise ValueError("candidate_id must be a non-empty string or None")
        if self.source_submission_id is not None and (not isinstance(self.source_submission_id, str) or not self.source_submission_id):
            raise ValueError("source_submission_id must be a non-empty string or None")
        if self.override_reason is not None and (not isinstance(self.override_reason, str) or not self.override_reason):
            raise ValueError("override_reason must be a non-empty string or None")
        if not isinstance(self.selected_for_archive, bool):
            raise TypeError("selected_for_archive must be a boolean")
        if not isinstance(self.anomaly_resolution_required, bool):
            raise TypeError("anomaly_resolution_required must be a boolean")
        if self.configuration_generated_at is not None and self.configuration_generated_at.tzinfo is None:
            raise ValueError("configuration_generated_at must be timezone-aware")
        for field_name in ("abnormal_kind", "time_abnormal_reason", "created_by_actor_id"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{field_name} must be a non-empty string or None")


@dataclass(frozen=True, slots=True)
class ArchiveCandidateUpsertResult:
    batch: ArchiveBatchRecord
    candidate: ArchiveCandidateRecord


@dataclass(frozen=True, slots=True)
class ArchiveAnomalyResolutionCommand:
    batch_id: str
    candidate_id: str
    actor_id: str
    resolution_type: AnomalyResolutionType | str
    reason: str
    resolution_id: str | None = None
    resolved_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in ("batch_id", "candidate_id", "actor_id", "reason"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.resolution_id is not None and (not isinstance(self.resolution_id, str) or not self.resolution_id):
            raise ValueError("resolution_id must be a non-empty string or None")
        if self.resolved_at is not None and (not isinstance(self.resolved_at, datetime) or self.resolved_at.tzinfo is None):
            raise ValueError("resolved_at must be a timezone-aware datetime or None")


@dataclass(frozen=True, slots=True)
class ArchiveAnomalyResolutionResult:
    batch: ArchiveBatchRecord
    resolution: ArchiveAnomalyResolutionRecord


@dataclass(frozen=True, slots=True)
class ArchiveSelectCandidatesCommand:
    batch_id: str
    selected_modified_candidate_id: str
    selected_initial_candidate_ids: tuple[str, ...] = ()
    actor_id: str = "system"
    override_reason: str | None = None
    candidate_set_hash: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("batch_id", "selected_modified_candidate_id", "actor_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.override_reason is not None and (not isinstance(self.override_reason, str) or not self.override_reason):
            raise ValueError("override_reason must be a non-empty string or None")
        if self.candidate_set_hash is not None and (not isinstance(self.candidate_set_hash, str) or not self.candidate_set_hash):
            raise ValueError("candidate_set_hash must be a non-empty string or None")
        for candidate_id in self.selected_initial_candidate_ids:
            if not isinstance(candidate_id, str) or not candidate_id:
                raise ValueError("selected_initial_candidate_ids must contain non-empty strings")
        object.__setattr__(
            self,
            "selected_initial_candidate_ids",
            _normalize_candidate_ids(self.selected_initial_candidate_ids),
        )


@dataclass(frozen=True, slots=True)
class ArchiveSelectCandidatesResult:
    batch: ArchiveBatchRecord
    selected_modified_candidate_id: str
    selected_initial_candidate_ids: tuple[str, ...]
    candidate_set_hash: str


@dataclass(frozen=True, slots=True)
class ArchiveDryRunCommand:
    batch_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.batch_id, str) or not self.batch_id:
            raise ValueError("batch_id must be a non-empty string")


@dataclass(frozen=True, slots=True)
class ArchiveDryRunResult:
    snapshot: ArchiveBatchSnapshot


@dataclass(frozen=True, slots=True)
class ArchiveExecuteCommand:
    batch_id: str
    expected_base_main_hash: str
    selected_modified_candidate_id: str
    selected_initial_candidate_ids: tuple[str, ...]
    requested_by_actor_id: str
    idempotency_key: str
    workspace_confirmation_set_hash: str
    candidate_set_hash: str
    override_reason: str | None = None
    open_ref_requested_tables: tuple[str, ...] = ()
    open_ref_timeout_policy: RepositoryRefTimeoutPolicy | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "batch_id",
            "expected_base_main_hash",
            "selected_modified_candidate_id",
            "requested_by_actor_id",
            "idempotency_key",
            "workspace_confirmation_set_hash",
            "candidate_set_hash",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.override_reason is not None and (not isinstance(self.override_reason, str) or not self.override_reason):
            raise ValueError("override_reason must be a non-empty string or None")
        for candidate_id in self.selected_initial_candidate_ids:
            if not isinstance(candidate_id, str) or not candidate_id:
                raise ValueError("selected_initial_candidate_ids must contain non-empty strings")
        for table_name in self.open_ref_requested_tables:
            if not isinstance(table_name, str) or not table_name:
                raise ValueError("open_ref_requested_tables must contain non-empty strings")
        if self.open_ref_timeout_policy is not None and not isinstance(self.open_ref_timeout_policy, RepositoryRefTimeoutPolicy):
            raise TypeError("open_ref_timeout_policy must be a RepositoryRefTimeoutPolicy or None")
        object.__setattr__(
            self,
            "selected_initial_candidate_ids",
            _normalize_candidate_ids(self.selected_initial_candidate_ids),
        )


@dataclass(frozen=True, slots=True)
class ArchiveExecuteResult:
    batch: ArchiveBatchRecord
    execution_record: ArchiveExecutionRecord
    idempotent_replay: bool
    open_ref_result: SnapshotMaterializationResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.batch, ArchiveBatchRecord):
            raise TypeError("batch must be an ArchiveBatchRecord")
        if not isinstance(self.execution_record, ArchiveExecutionRecord):
            raise TypeError("execution_record must be an ArchiveExecutionRecord")
        if not isinstance(self.idempotent_replay, bool):
            raise TypeError("idempotent_replay must be a boolean")
        if self.open_ref_result is not None and not isinstance(self.open_ref_result, SnapshotMaterializationResult):
            raise TypeError("open_ref_result must be a SnapshotMaterializationResult or None")


class ArchiveService:
    def __init__(
        self,
        *,
        archive_store: ArchiveStore,
        submission_store: SubmissionStore,
        workspace_store: WorkspaceStore,
        repository_service: RepositoryServicePort,
        repository_table_access_provider: RepositoryTableAccessProvider | None = None,
    ) -> None:
        self.archive_store = archive_store
        self.submission_store = submission_store
        self.workspace_store = workspace_store
        self.repository_service = repository_service
        self.repository_table_access_provider = repository_table_access_provider
        if not hasattr(self.archive_store, "create_batch") or not hasattr(self.archive_store, "get_batch") or not hasattr(self.archive_store, "save_batch"):
            raise TypeError("archive_store must implement ArchiveStore")
        if not hasattr(self.submission_store, "create") or not hasattr(self.submission_store, "get") or not hasattr(self.submission_store, "save") or not hasattr(self.submission_store, "delete"):
            raise TypeError("submission_store must implement SubmissionStore")
        if not hasattr(self.workspace_store, "create") or not hasattr(self.workspace_store, "get") or not hasattr(self.workspace_store, "save") or not hasattr(self.workspace_store, "delete") or not hasattr(self.workspace_store, "list_by_batch"):
            raise TypeError("workspace_store must implement the WorkspaceStore protocol")
        if not hasattr(self.repository_service, "promote_mainline"):
            raise TypeError("repository_service must implement promote_mainline()")
        if self.repository_table_access_provider is not None and not hasattr(self.repository_table_access_provider, "open_ref"):
            raise TypeError("repository_table_access_provider must implement open_ref() or be None")

    def open_batch(self, command: ArchiveOpenBatchCommand) -> ArchiveOpenBatchResult:
        if not isinstance(command, ArchiveOpenBatchCommand):
            raise TypeError("command must be an ArchiveOpenBatchCommand")
        existing = self.archive_store.get_batch(command.batch_id)
        if existing is not None:
            if (
                existing.repository_id != command.repository_id
                or existing.base_main_hash != command.base_main_hash
            ):
                raise ValueError("archive batch already exists with a conflicting payload")
            return ArchiveOpenBatchResult(
                batch=existing,
                workspaces=tuple(
                    self._bind_workspace_to_batch(workspace_id=workspace_id, batch_id=existing.batch_id)
                    for workspace_id in command.workspace_ids
                ),
            )

        opened_at = command.opened_at or datetime.now(timezone.utc)
        batch = ArchiveBatchRecord(
            batch_id=command.batch_id,
            repository_id=command.repository_id,
            base_main_hash=command.base_main_hash,
            opened_by_actor_id=command.opened_by_actor_id,
            open_reason=command.open_reason,
            opened_at=opened_at,
        )
        batch = self.archive_store.create_batch(batch)
        workspaces = tuple(
            self._bind_workspace_to_batch(workspace_id=workspace_id, batch_id=batch.batch_id)
            for workspace_id in command.workspace_ids
        )
        return ArchiveOpenBatchResult(batch=batch, workspaces=workspaces)

    def confirm_workspace_archive(self, command: ArchiveConfirmWorkspaceCommand) -> ArchiveConfirmWorkspaceResult:
        if not isinstance(command, ArchiveConfirmWorkspaceCommand):
            raise TypeError("command must be an ArchiveConfirmWorkspaceCommand")
        batch = self._require_batch(command.batch_id)
        workspace = self._require_workspace(command.workspace_id)
        self._require_workspace_batch(workspace, command.batch_id)
        candidate = None
        if command.archive_candidate_id is not None:
            candidate = self._require_candidate(command.archive_candidate_id)
            self._require_candidate_batch(candidate, command.batch_id)

        existing = next(
            (
                item
                for item in self.archive_store.list_confirmations_by_batch(command.batch_id)
                if item.workspace_id == command.workspace_id
            ),
            None,
        )
        if existing is None:
            confirmation = WorkspaceArchiveConfirmationRecord(
                confirmation_id=self.archive_store.next_confirmation_identity(),
                batch_id=command.batch_id,
                workspace_id=command.workspace_id,
            )
            self.archive_store.create_confirmation(confirmation)
        else:
            confirmation = existing
        if candidate is None:
            updated = confirmation.confirm_discarded(
                actor_id=command.actor_id,
                reason=command.reason,
                confirmed_at=command.confirmed_at,
            )
        else:
            updated = confirmation.confirm_with_candidate(
                actor_id=command.actor_id,
                archive_candidate_id=candidate.candidate_id,
                reason=command.reason,
                confirmed_at=command.confirmed_at,
            )
        self.archive_store.save_confirmation(updated, expected_version=confirmation.version)
        batch = self._refresh_archive_gate(batch)
        return ArchiveConfirmWorkspaceResult(batch=batch, confirmation=updated)

    def upsert_archive_candidate(self, command: ArchiveCandidateUpsertCommand) -> ArchiveCandidateUpsertResult:
        if not isinstance(command, ArchiveCandidateUpsertCommand):
            raise TypeError("command must be an ArchiveCandidateUpsertCommand")
        batch = self._require_batch(command.batch_id)
        workspace = self._require_workspace(command.workspace_id)
        self._require_workspace_batch(workspace, command.batch_id)
        submission = None
        if command.source_submission_id is not None:
            submission = self.submission_store.get(command.source_submission_id)
            if submission is None:
                raise KeyError(f"submission not found: {command.source_submission_id}")
            if submission.batch_id != command.batch_id:
                raise ValueError("source submission batch does not match archive batch")
        candidate_id = command.candidate_id or self.archive_store.next_candidate_identity()
        existing = self.archive_store.get_candidate(candidate_id)
        source_kind = ArchiveCandidateSourceKind(command.source_kind)
        if submission is not None:
            source_kind = self._candidate_source_kind_from_submission(submission.status)
        candidate = existing or ArchiveCandidateRecord(
            candidate_id=candidate_id,
            batch_id=command.batch_id,
            workspace_id=command.workspace_id,
            source_kind=source_kind,
            role=command.role,
            source_submission_id=command.source_submission_id,
            override_reason=command.override_reason,
            selected_for_archive=command.selected_for_archive,
            anomaly_resolution_required=command.anomaly_resolution_required,
            configuration_generated_at=command.configuration_generated_at,
            abnormal_kind=command.abnormal_kind,
            time_abnormal_reason=command.time_abnormal_reason,
            created_by_actor_id=command.created_by_actor_id,
        )
        if existing is not None:
            candidate = existing.select_for_archive(
                role=ArchiveCandidateRole(command.role),
                selected_for_archive=command.selected_for_archive,
                override_reason=command.override_reason,
                configuration_generated_at=command.configuration_generated_at,
            )
            candidate = candidate.with_confirmation_metadata(
                anomaly_resolution_required=command.anomaly_resolution_required,
                abnormal_kind=command.abnormal_kind,
                time_abnormal_reason=command.time_abnormal_reason,
                source_submission_id=command.source_submission_id,
            )
        if candidate.role == ArchiveCandidateRole.MAINLINE_MODIFIED and candidate.selected_for_archive:
            candidate.ensure_selectable_as_mainline()
        if existing is None:
            self.archive_store.create_candidate(candidate)
        else:
            self.archive_store.save_candidate(candidate, expected_version=existing.version)
        batch = self._refresh_archive_gate(batch)
        return ArchiveCandidateUpsertResult(batch=batch, candidate=candidate)

    def record_anomaly_resolution(self, command: ArchiveAnomalyResolutionCommand) -> ArchiveAnomalyResolutionResult:
        if not isinstance(command, ArchiveAnomalyResolutionCommand):
            raise TypeError("command must be an ArchiveAnomalyResolutionCommand")
        batch = self._require_batch(command.batch_id)
        candidate = self._require_candidate(command.candidate_id)
        self._require_candidate_batch(candidate, command.batch_id)
        resolution = ArchiveAnomalyResolutionRecord(
            resolution_id=command.resolution_id or self.archive_store.next_anomaly_resolution_identity(),
            batch_id=command.batch_id,
            candidate_id=command.candidate_id,
            resolution_type=command.resolution_type,
            reason=command.reason,
            resolved_by_actor_id=command.actor_id,
            resolved_at=command.resolved_at or datetime.now(timezone.utc),
        )
        existing = self.archive_store.get_anomaly_resolution(resolution.resolution_id)
        if existing is None:
            self.archive_store.create_anomaly_resolution(resolution)
        else:
            self.archive_store.save_anomaly_resolution(resolution, expected_version=existing.version)
        batch = self._refresh_archive_gate(batch)
        return ArchiveAnomalyResolutionResult(batch=batch, resolution=resolution)

    def select_archive_candidates(self, command: ArchiveSelectCandidatesCommand) -> ArchiveSelectCandidatesResult:
        if not isinstance(command, ArchiveSelectCandidatesCommand):
            raise TypeError("command must be an ArchiveSelectCandidatesCommand")
        batch = self._require_batch(command.batch_id)
        self._require_batch_open(batch, action="select_archive_candidates")
        candidates = self.archive_store.list_candidates_by_batch(command.batch_id)
        current_candidate_set_hash = self._compute_candidate_set_hash(candidates)
        if command.candidate_set_hash is not None and command.candidate_set_hash != current_candidate_set_hash:
            raise ValueError("candidate set hash is stale")
        candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
        selected_modified = candidate_by_id.get(command.selected_modified_candidate_id)
        if selected_modified is None:
            raise KeyError(f"archive candidate not found: {command.selected_modified_candidate_id}")
        selected_initial_ids = _normalize_candidate_ids(command.selected_initial_candidate_ids)
        if command.selected_modified_candidate_id in selected_initial_ids:
            raise ValueError("selected modified candidate cannot also be an initial history candidate")
        selected_modified = selected_modified.select_for_archive(
            role=ArchiveCandidateRole.MAINLINE_MODIFIED,
            selected_for_archive=True,
            override_reason=command.override_reason,
        )
        self._validate_mainline_candidate(selected_modified)
        updated_candidates: list[ArchiveCandidateRecord] = []
        for candidate in candidate_by_id.values():
            if candidate.candidate_id == selected_modified.candidate_id:
                updated_candidates.append(selected_modified)
                continue
            if candidate.candidate_id in selected_initial_ids:
                updated = candidate.select_for_archive(
                    role=ArchiveCandidateRole.BASELINE_INITIAL_HISTORY,
                    selected_for_archive=True,
                )
                if updated.status != ArchiveCandidateStatus.NOT_ARCHIVED:
                    raise ValueError("selected initial history candidate is not selectable")
                updated_candidates.append(updated)
            else:
                updated_candidates.append(
                    candidate.select_for_archive(
                        role=candidate.role,
                        selected_for_archive=False,
                    )
                )
        original_batch_version = batch.version
        for candidate in updated_candidates:
            self.archive_store.save_candidate(candidate, expected_version=candidate.version - 1)
        batch = batch.with_selection(
            selected_modified_candidate_id=selected_modified.candidate_id,
            selected_initial_candidate_ids=selected_initial_ids,
        )
        batch = batch.with_candidate_set_hash(self._compute_candidate_set_hash(updated_candidates))
        batch = self.archive_store.save_batch(batch, expected_version=original_batch_version)
        batch = self._refresh_archive_gate(batch)
        return ArchiveSelectCandidatesResult(
            batch=batch,
            selected_modified_candidate_id=selected_modified.candidate_id,
            selected_initial_candidate_ids=selected_initial_ids,
            candidate_set_hash=batch.candidate_set_hash or self._compute_candidate_set_hash(updated_candidates),
        )

    def dry_run_archive_mainline(self, command: ArchiveDryRunCommand) -> ArchiveDryRunResult:
        if not isinstance(command, ArchiveDryRunCommand):
            raise TypeError("command must be an ArchiveDryRunCommand")
        snapshot = self._build_snapshot(batch=self._require_batch(command.batch_id))
        return ArchiveDryRunResult(snapshot=snapshot)

    def execute_archive_mainline(self, command: ArchiveExecuteCommand) -> ArchiveExecuteResult:
        if not isinstance(command, ArchiveExecuteCommand):
            raise TypeError("command must be an ArchiveExecuteCommand")
        batch = self._require_batch(command.batch_id)
        existing = self.archive_store.get_execution_by_idempotency_key(command.idempotency_key)
        payload_hash = self._compute_command_payload_hash(command)
        if existing is not None:
            if existing.command_payload_hash != payload_hash:
                raise ValueError("idempotency key was already used with a different payload")
            return ArchiveExecuteResult(
                batch=batch,
                execution_record=existing,
                idempotent_replay=True,
                open_ref_result=None,
            )
        self._require_batch_open(batch, action="execute_archive_mainline")
        if command.expected_base_main_hash != batch.base_main_hash:
            raise ValueError("expected base main hash does not match the batch baseline")
        snapshot = self._build_snapshot(batch=batch)
        self._ensure_snapshot_matches_command(snapshot, command)
        if not snapshot.eligible_for_execute:
            raise ValueError(f"archive batch is not eligible for execution: {snapshot.failure_reasons}")
        selected_modified = self._require_candidate(command.selected_modified_candidate_id)
        self._require_candidate_batch(selected_modified, command.batch_id)
        selected_initial_candidates = [
            self._require_candidate(candidate_id) for candidate_id in command.selected_initial_candidate_ids
        ]
        batch = batch.start_archive()
        self.archive_store.save_batch(batch, expected_version=batch.version - 1)
        execution = ArchiveExecutionRecord(
            execution_id=self.archive_store.next_execution_identity(),
            batch_id=batch.batch_id,
            command_idempotency_key=command.idempotency_key,
            command_payload_hash=payload_hash,
            requested_by_actor_id=command.requested_by_actor_id,
            selected_modified_candidate_id=selected_modified.candidate_id,
            selected_initial_candidate_ids=tuple(command.selected_initial_candidate_ids),
            old_main_hash=batch.base_main_hash,
        )
        execution = execution.mark_executing()
        self.archive_store.create_execution(execution)

        try:
            promotion = self.repository_service.promote_mainline(
                request=self._build_promote_mainline_request(
                    batch=batch,
                    selected_modified=selected_modified,
                    selected_initial_candidates=selected_initial_candidates,
                    idempotency_key=command.idempotency_key,
                    request_hash=payload_hash,
                    override_reason=command.override_reason,
                ),
                context=RepositoryOperationContext(
                    operation_id=f"archive-promote-{batch.batch_id}-{execution.execution_id}",
                    caller_service="backend_vnext.archive.service",
                    actor_id=command.requested_by_actor_id,
                ),
            )
        except Exception as exc:  # pragma: no cover - repository promotion failure path
            execution = execution.mark_failed_frozen(reason=str(exc))
            self.archive_store.save_execution(execution, expected_version=2)
            batch = batch.freeze_archive_gate(reason=str(exc))
            self.archive_store.save_batch(batch, expected_version=batch.version - 1)
            return ArchiveExecuteResult(
                batch=batch,
                execution_record=execution,
                idempotent_replay=False,
                open_ref_result=None,
            )

        batch = self._mark_archive_statuses(
            batch=batch,
            selected_modified_candidate=selected_modified,
            selected_initial_candidates=selected_initial_candidates,
        )

        open_ref_result: SnapshotMaterializationResult | None = None
        open_ref_error: Exception | None = None
        try:
            open_ref_result = self._open_ref_closeout(
                batch=batch,
                selected_modified=selected_modified,
                requested_tables=command.open_ref_requested_tables,
                timeout_policy=command.open_ref_timeout_policy,
            )
        except Exception as exc:  # pragma: no cover - open ref closeout failure path
            open_ref_error = exc

        if open_ref_result is None:
            execution = execution.mark_succeeded(
                new_main_hash=promotion.new_main_hash,
                transfer_status=ArchiveExecutionTransferStatus.TRANSFER_FAILED,
                failure_reason=str(open_ref_error or "open ref closeout failed"),
            )
        else:
            selected_modified_submission = self._require_submission(selected_modified.source_submission_id)
            repository_ref = selected_modified_submission.repository_target_ref
            if repository_ref is None:
                raise ValueError("selected modified submission is missing repository_target_ref")
            execution = execution.mark_open_ref_completed(
                open_ref_repository_ref=repository_ref,
                open_ref_snapshot_id=open_ref_result.snapshot.snapshot_id,
                open_ref_snapshot_digest=open_ref_result.snapshot.snapshot_digest.hex_digest,
            )
            execution = execution.mark_succeeded(
                new_main_hash=promotion.new_main_hash,
                transfer_status=ArchiveExecutionTransferStatus.TRANSFERRED,
            )
        batch = batch.complete_archive(closed_at=datetime.now(timezone.utc))
        self.archive_store.save_batch(batch, expected_version=batch.version - 1)
        self.archive_store.save_execution(execution, expected_version=2)
        return ArchiveExecuteResult(
            batch=batch,
            execution_record=execution,
            idempotent_replay=False,
            open_ref_result=open_ref_result,
        )

    def _bind_workspace_to_batch(self, *, workspace_id: str, batch_id: str) -> WorkspaceRecord:
        workspace = self._require_workspace(workspace_id)
        if workspace.batch_id == batch_id:
            return workspace
        updated = workspace.with_batch_id(batch_id)
        self.workspace_store.save(updated, expected_version=workspace.version)
        return updated

    def _refresh_archive_gate(self, batch: ArchiveBatchRecord) -> ArchiveBatchRecord:
        active_workspace_ids = {
            workspace.workspace_id
            for workspace in self.workspace_store.list_by_batch(batch.batch_id)
            if workspace.status != WorkspaceStatus.CLOSED
        }
        confirmed_workspace_ids = {
            confirmation.workspace_id
            for confirmation in self.archive_store.list_confirmations_by_batch(batch.batch_id)
            if confirmation.workspace_id in active_workspace_ids
        }
        if active_workspace_ids and active_workspace_ids <= confirmed_workspace_ids:
            updated = batch.mark_archive_gate_ready()
        else:
            updated = batch.mark_archive_gate_collecting()
        return self.archive_store.save_batch(updated, expected_version=batch.version)

    def _build_snapshot(self, *, batch: ArchiveBatchRecord) -> ArchiveBatchSnapshot:
        confirmations = self.archive_store.list_confirmations_by_batch(batch.batch_id)
        candidates = self.archive_store.list_candidates_by_batch(batch.batch_id)
        anomaly_resolutions = self.archive_store.list_anomaly_resolutions_by_batch(batch.batch_id)
        active_workspace_ids = {
            workspace.workspace_id
            for workspace in self.workspace_store.list_by_batch(batch.batch_id)
            if workspace.status != WorkspaceStatus.CLOSED
        }
        return build_batch_snapshot(
            batch=batch,
            confirmations=confirmations,
            candidates=candidates,
            anomaly_resolutions=anomaly_resolutions,
            active_workspace_ids=active_workspace_ids,
            require_submission=self._require_submission,
        )

    def _ensure_snapshot_matches_command(self, snapshot: ArchiveBatchSnapshot, command: ArchiveExecuteCommand) -> None:
        ensure_snapshot_matches_command(snapshot, command)

    def _compute_workspace_confirmation_set_hash(
        self,
        confirmations: tuple[WorkspaceArchiveConfirmationRecord, ...],
    ) -> str:
        return compute_workspace_confirmation_set_hash(confirmations)

    def _compute_candidate_set_hash(
        self,
        candidates: Sequence[ArchiveCandidateRecord],
    ) -> str:
        return compute_candidate_set_hash(candidates)

    def _compute_command_payload_hash(self, command: ArchiveExecuteCommand) -> str:
        return compute_command_payload_hash(command)

    def _require_batch(self, batch_id: str) -> ArchiveBatchRecord:
        batch = self.archive_store.get_batch(batch_id)
        if batch is None:
            raise KeyError(f"archive batch not found: {batch_id}")
        return batch

    def _require_workspace(self, workspace_id: str) -> WorkspaceRecord:
        workspace = self.workspace_store.get(workspace_id)
        if workspace is None:
            raise KeyError(f"workspace not found: {workspace_id}")
        return workspace

    def _require_candidate(self, candidate_id: str) -> ArchiveCandidateRecord:
        candidate = self.archive_store.get_candidate(candidate_id)
        if candidate is None:
            raise KeyError(f"archive candidate not found: {candidate_id}")
        return candidate

    def _require_workspace_batch(self, workspace: WorkspaceRecord, batch_id: str) -> None:
        if workspace.batch_id != batch_id:
            raise ValueError("workspace does not belong to the archive batch")

    def _require_candidate_batch(self, candidate: ArchiveCandidateRecord, batch_id: str) -> None:
        if candidate.batch_id != batch_id:
            raise ValueError("archive candidate does not belong to the archive batch")

    def _require_batch_open(self, batch: ArchiveBatchRecord, *, action: str) -> None:
        require_batch_open(batch, action=action)

    def _validate_mainline_candidate(self, candidate: ArchiveCandidateRecord) -> None:
        validate_mainline_candidate(candidate)

    def _candidate_source_kind_from_submission(self, status: SubmissionStatus) -> ArchiveCandidateSourceKind:
        return candidate_source_kind_from_submission(status)

    def _initial_history_resolution_failure(
        self,
        *,
        candidates: tuple[ArchiveCandidateRecord, ...],
        anomaly_resolutions: tuple[ArchiveAnomalyResolutionRecord, ...],
    ) -> str | None:
        return initial_history_resolution_failure(
            candidates=candidates,
            anomaly_resolutions=anomaly_resolutions,
        )

    def _mark_archive_statuses(
        self,
        *,
        batch: ArchiveBatchRecord,
        selected_modified_candidate: ArchiveCandidateRecord,
        selected_initial_candidates: list[ArchiveCandidateRecord],
    ) -> ArchiveBatchRecord:
        return mark_archive_statuses(
            batch=batch,
            selected_modified_candidate=selected_modified_candidate,
            selected_initial_candidates=selected_initial_candidates,
            archive_store=self.archive_store,
            submission_store=self.submission_store,
            workspace_store=self.workspace_store,
        )

    def _build_promote_mainline_request(
        self,
        *,
        batch: ArchiveBatchRecord,
        selected_modified: ArchiveCandidateRecord,
        selected_initial_candidates: list[ArchiveCandidateRecord],
        idempotency_key: str,
        request_hash: str,
        override_reason: str | None,
    ) -> PromoteMainlineRequest:
        return build_promote_mainline_request(
            batch=batch,
            selected_modified=selected_modified,
            selected_initial_candidates=selected_initial_candidates,
            require_submission=self._require_submission,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            override_reason=override_reason,
        )

    def _build_repository_ref_snapshot(
        self,
        *,
        batch: ArchiveBatchRecord,
        submission,
        candidate_id: str,
        operation_id: str,
    ) -> RepositoryRefSnapshot:
        return build_repository_ref_snapshot(
            batch=batch,
            submission=submission,
            candidate_id=candidate_id,
            operation_id=operation_id,
        )

    def _open_ref_closeout(
        self,
        *,
        batch: ArchiveBatchRecord,
        selected_modified: ArchiveCandidateRecord,
        requested_tables: tuple[str, ...],
        timeout_policy: RepositoryRefTimeoutPolicy | None,
    ) -> SnapshotMaterializationResult:
        return open_ref_closeout(
            batch=batch,
            selected_modified=selected_modified,
            repository_table_access_provider=self.repository_table_access_provider,
            require_submission=self._require_submission,
            requested_tables=requested_tables,
            timeout_policy=timeout_policy,
        )

    def _require_submission(self, submission_id: str | None):
        if submission_id is None:
            raise ValueError("source submission id is required")
        submission = self.submission_store.get(submission_id)
        if submission is None:
            raise KeyError(f"submission not found: {submission_id}")
        return submission


def _normalize_candidate_ids(candidate_ids: Sequence[str]) -> tuple[str, ...]:
    return normalize_candidate_ids(candidate_ids)
