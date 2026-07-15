from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class RefKind(StrEnum):
    BRANCH = "BRANCH"
    TAG = "TAG"


class RefPurpose(StrEnum):
    MAINLINE = "MAINLINE"
    WORKSPACE_DRAFT = "WORKSPACE_DRAFT"
    WORKSPACE_INITIAL = "WORKSPACE_INITIAL"
    SUBMISSION_PREVIEW = "SUBMISSION_PREVIEW"
    ARCHIVE_CANDIDATE = "ARCHIVE_CANDIDATE"
    BASELINE_BATCH = "BASELINE_BATCH"
    BASELINE_ARCHIVE_NODE = "BASELINE_ARCHIVE_NODE"
    HISTORY_COMPARISON = "HISTORY_COMPARISON"


class RefRetentionOwnerKind(StrEnum):
    WORKSPACE = "WORKSPACE"
    SUBMISSION = "SUBMISSION"
    ARCHIVE_CANDIDATE = "ARCHIVE_CANDIDATE"
    BASELINE_BATCH = "BASELINE_BATCH"
    BASELINE_ARCHIVE_NODE = "BASELINE_ARCHIVE_NODE"
    HISTORY_COMPARISON = "HISTORY_COMPARISON"
    SYSTEM = "SYSTEM"


@dataclass(frozen=True, slots=True)
class RepositoryRef:
    repository_id: str
    ref: str
    kind: RefKind
    purpose: RefPurpose
    owner_kind: RefRetentionOwnerKind
    owner_id: str
    commit_hash: str | None = None
    protected: bool = False


@dataclass(frozen=True, slots=True)
class RepositoryRefSnapshot:
    repository_id: str
    ref: str
    kind: RefKind
    purpose: RefPurpose
    owner_kind: RefRetentionOwnerKind
    owner_id: str
    commit_hash: str
    created_by_operation_id: str
    created_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.repository_id, "repository_id")
        _require_text(self.ref, "ref")
        _require_text(self.owner_id, "owner_id")
        _require_text(self.commit_hash, "commit_hash")
        _require_text(self.created_by_operation_id, "created_by_operation_id")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be an aware datetime")
        object.__setattr__(self, "kind", RefKind(self.kind))
        object.__setattr__(self, "purpose", RefPurpose(self.purpose))
        object.__setattr__(self, "owner_kind", RefRetentionOwnerKind(self.owner_kind))


@dataclass(frozen=True, slots=True)
class RefReleaseRequest:
    repository_id: str
    ref: str
    purpose: RefPurpose
    expected_commit_hash: str
    owner_kind: RefRetentionOwnerKind
    owner_id: str
    reason: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class MutableRefReleaseConflict(Exception):
    ref: str
    expected_commit_hash: str
    actual_commit_hash: str
    retryable: bool = False
    final: bool = True

    def __str__(self) -> str:
        return f"mutable ref points at a different commit: ref={self.ref}"


@dataclass(frozen=True, slots=True)
class MutableRefReleaseRejected(Exception):
    ref: str
    reason: str
    retryable: bool = False
    final: bool = True

    def __str__(self) -> str:
        return f"ref is not a releasable mutable branch: ref={self.ref}"


@dataclass(frozen=True, slots=True)
class PromoteMainlineInitialHistoryCandidate:
    candidate_id: str
    ref_snapshot: RepositoryRefSnapshot
    history_commit_hash: str

    def __post_init__(self) -> None:
        _require_text(self.candidate_id, "candidate_id")
        _require_text(self.history_commit_hash, "history_commit_hash")
        if self.ref_snapshot.commit_hash != self.history_commit_hash:
            raise ValueError("initial history ref snapshot must match history_commit_hash")


@dataclass(frozen=True, slots=True)
class PromoteMainlineRequest:
    repository_id: str
    batch_id: str
    expected_base_main_hash: str
    selected_modified_candidate_id: str
    selected_modified_ref_snapshot: RepositoryRefSnapshot
    selected_modified_commit_hash: str
    selected_initial_history_candidates: tuple[PromoteMainlineInitialHistoryCandidate, ...]
    idempotency_key: str
    request_hash: str

    def __post_init__(self) -> None:
        _require_text(self.repository_id, "repository_id")
        _require_text(self.batch_id, "batch_id")
        _require_text(self.expected_base_main_hash, "expected_base_main_hash")
        _require_text(self.selected_modified_candidate_id, "selected_modified_candidate_id")
        _require_text(self.selected_modified_commit_hash, "selected_modified_commit_hash")
        _require_text(self.idempotency_key, "idempotency_key")
        _require_text(self.request_hash, "request_hash")
        if self.selected_modified_ref_snapshot.commit_hash != self.selected_modified_commit_hash:
            raise ValueError("selected modified ref snapshot must match selected_modified_commit_hash")


@dataclass(frozen=True, slots=True)
class PromoteMainlineResult:
    repository_id: str
    batch_id: str
    old_main_hash: str
    new_main_hash: str
    selected_modified_candidate_id: str
    selected_initial_history_candidate_ids: tuple[str, ...]
    repository_operation_id: str
    request_hash: str
    idempotent_replay: bool
    operation_record: "RepositoryOperationRecord"


@dataclass(frozen=True, slots=True)
class MainlinePromotionConflict(Exception):
    repository_id: str
    expected_base_main_hash: str
    actual_main_hash: str | None
    target_main_hash: str
    retryable: bool = False
    final: bool = True

    def __str__(self) -> str:
        return "current main does not match expected base main hash"


class RepositoryOperationType(StrEnum):
    CREATE_REPOSITORY = "CreateRepository"
    OPEN_REPOSITORY = "OpenRepository"
    IMPORT_ARCHIVE = "ImportArchive"
    IMPORT_SQL_DUMP = "ImportSqlDump"
    CREATE_REF = "CreateRef"
    RESOLVE_REF = "ResolveRef"
    CREATE_IMMUTABLE_REF = "CreateImmutableRef"
    RELEASE_MUTABLE_REF = "ReleaseMutableRef"
    CREATE_COMMIT = "CreateCommit"
    GET_COMMIT = "GetCommit"
    MATERIALIZE_TABLE_SNAPSHOT = "MaterializeTableSnapshot"
    READ_TABLE_ROWS = "ReadTableRows"
    COMPARE_REFS = "CompareRefs"
    PROMOTE_MAINLINE = "PromoteMainline"
    BUILD_PREVIEW_ARTIFACTS = "BuildPreviewArtifacts"
    BUILD_HISTORY_COMPARISON = "BuildHistoryComparison"
    CLEANUP_REPOSITORY_CACHE = "CleanupRepositoryCache"
    PLAN_DOLT_GARBAGE_COLLECTION = "PlanDoltGarbageCollection"
    EXECUTE_DOLT_GARBAGE_COLLECTION = "ExecuteDoltGarbageCollection"
    SCAN_REPOSITORY_STORAGE = "ScanRepositoryStorage"


class OperationStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"
    CANCELLED = "CANCELLED"
    RECOVERED = "RECOVERED"


@dataclass(frozen=True, slots=True)
class RepositoryOperationContext:
    operation_id: str
    caller_service: str
    actor_id: str


@dataclass(frozen=True, slots=True)
class RepositoryOperationRecord:
    operation_id: str
    idempotency_key: str
    request_hash: str
    repository_id: str
    operation_type: RepositoryOperationType
    status: OperationStatus
    started_at: datetime
    finished_at: datetime | None = None
    input_digest: str | None = None
    before_ref: str | None = None
    before_commit: str | None = None
    after_ref: str | None = None
    after_commit: str | None = None
    error_code: str | None = None
    message_summary: str | None = None
    retryable: bool = False
    log_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_type", RepositoryOperationType(self.operation_type))
        object.__setattr__(self, "status", OperationStatus(self.status))


class RepositoryRefPort(Protocol):
    def release_mutable_ref(
        self,
        request: RefReleaseRequest,
        *,
        context: RepositoryOperationContext,
    ) -> RepositoryRef: ...


class RepositoryServicePort(RepositoryRefPort, Protocol):
    def promote_mainline(
        self,
        request: PromoteMainlineRequest,
        *,
        context: RepositoryOperationContext,
    ) -> PromoteMainlineResult: ...


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
