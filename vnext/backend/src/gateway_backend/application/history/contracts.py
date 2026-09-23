"""History read-model contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from gateway_backend.domain.archive.models import ArchiveDispositionKind
from gateway_backend.domain.baseline.models import BaselineNode, BaselineNodeKind
from gateway_backend.domain.submission.models import Submission
from gateway_backend.domain.submission.review import ReviewStatus
from gateway_backend.domain.workspace.models import BaselineHead

PERMISSION_READ_PROJECT_HISTORY = "read_project_history"
DEFAULT_HISTORY_PAGE_LIMIT = 100
MAX_HISTORY_PAGE_LIMIT = 500
MAX_HISTORY_CURSOR_BYTES = 1024


class HistoryNodeRefKind(StrEnum):
    BASELINE_NODE = "baseline_node"
    SUBMISSION = "submission"


class HistoryNodeKind(StrEnum):
    BASELINE_NODE = "BASELINE_NODE"
    SUBMISSION = "SUBMISSION"
    SYSTEM_MIGRATION = "SYSTEM_MIGRATION"


class HistoryEligibilityNote(StrEnum):
    NOT_CANDIDATE_BASE_ADVANCED = "NOT_CANDIDATE_BASE_ADVANCED"


@dataclass(frozen=True, slots=True)
class HistoryNodeRef:
    ref_kind: HistoryNodeRefKind
    ref_id: str

    def __post_init__(self) -> None:
        if type(self.ref_kind) is not HistoryNodeRefKind:
            raise ValueError("ref_kind must be HistoryNodeRefKind")
        if type(self.ref_id) is not str or not self.ref_id:
            raise ValueError("ref_id must be a non-empty string")


@dataclass(frozen=True, slots=True)
class HistoryNode:
    ref_kind: HistoryNodeRefKind
    ref_id: str
    node_kind: HistoryNodeKind
    commit_id: str
    created_at: datetime
    parent: HistoryNodeRef | None
    baseline_kind: BaselineNodeKind | None = None
    review_status: ReviewStatus | None = None
    archive_disposition: ArchiveDispositionKind | None = None
    promoted_baseline_node_id: str | None = None
    eligibility_note: HistoryEligibilityNote | None = None

    def __post_init__(self) -> None:
        if type(self.ref_kind) is not HistoryNodeRefKind:
            raise ValueError("ref_kind must be HistoryNodeRefKind")
        if type(self.ref_id) is not str or not self.ref_id:
            raise ValueError("ref_id must be a non-empty string")
        if type(self.node_kind) is not HistoryNodeKind:
            raise ValueError("node_kind must be HistoryNodeKind")
        if type(self.commit_id) is not str or not self.commit_id:
            raise ValueError("commit_id must be a non-empty string")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be an aware datetime")
        if self.parent is not None and type(self.parent) is not HistoryNodeRef:
            raise ValueError("parent must be HistoryNodeRef or None")
        if self.baseline_kind is not None and type(self.baseline_kind) is not BaselineNodeKind:
            raise ValueError("baseline_kind must be BaselineNodeKind or None")
        if self.review_status is not None and type(self.review_status) is not ReviewStatus:
            raise ValueError("review_status must be ReviewStatus or None")
        if self.archive_disposition is not None and type(self.archive_disposition) is not ArchiveDispositionKind:
            raise ValueError("archive_disposition must be ArchiveDispositionKind or None")
        if self.promoted_baseline_node_id is not None and (
            type(self.promoted_baseline_node_id) is not str or not self.promoted_baseline_node_id
        ):
            raise ValueError("promoted_baseline_node_id must be a non-empty string or None")
        if self.eligibility_note is not None and type(self.eligibility_note) is not HistoryEligibilityNote:
            raise ValueError("eligibility_note must be HistoryEligibilityNote or None")
        if self.node_kind is HistoryNodeKind.BASELINE_NODE:
            if self.baseline_kind is None:
                raise ValueError("baseline nodes require baseline_kind")
            if self.review_status is not None or self.archive_disposition is not None:
                raise ValueError("baseline nodes must not carry submission-only fields")
        elif self.node_kind is HistoryNodeKind.SUBMISSION:
            if self.baseline_kind is not None:
                raise ValueError("submission nodes must not carry baseline_kind")
            if self.review_status is None:
                raise ValueError("submission nodes require review_status")


@dataclass(frozen=True, slots=True)
class HistoryHead:
    node_id: str
    commit_id: str
    version: int

    def __post_init__(self) -> None:
        if type(self.node_id) is not str or not self.node_id:
            raise ValueError("node_id must be a non-empty string")
        if type(self.commit_id) is not str or not self.commit_id:
            raise ValueError("commit_id must be a non-empty string")
        if type(self.version) is not int or self.version < 0:
            raise ValueError("version must be a non-negative integer")

    @classmethod
    def from_baseline_head(cls, baseline_head: BaselineHead) -> HistoryHead:
        return cls(
            node_id=baseline_head.business_baseline_node_id,
            commit_id=baseline_head.business_baseline_commit_id,
            version=baseline_head.baseline_head_version,
        )


@dataclass(frozen=True, slots=True)
class HistorySubmissionFact:
    submission: Submission
    review_status: ReviewStatus
    disposition: ArchiveDispositionKind | None


@dataclass(frozen=True, slots=True)
class HistoryFacts:
    repository_id: str
    baseline_nodes: tuple[BaselineNode, ...]
    submissions: tuple[HistorySubmissionFact, ...]
    head: BaselineHead


@dataclass(frozen=True, slots=True)
class HistoryTreeProjection:
    head: HistoryHead
    nodes: tuple[HistoryNode, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class HistoryPageEntry:
    ref_kind: HistoryNodeRefKind
    ref_id: str
    node_kind: HistoryNodeKind
    commit_id: str
    created_at: datetime
    baseline_kind: BaselineNodeKind | None = None
    parent_node_id: str | None = None
    based_on_baseline_node_id: str | None = None
    review_status: ReviewStatus | None = None
    archive_disposition: ArchiveDispositionKind | None = None


@dataclass(frozen=True, slots=True)
class HistoryPageSnapshot:
    head: BaselineHead
    entries: tuple[HistoryPageEntry, ...]
    promoted_by_submission: dict[str, str]
    has_next_page: bool
