"""History read-model and compare contracts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from gateway_shared_kernel.jcs import canonicalize_jcs, canonicalize_json_value

from gateway_backend.domain.archive.models import ArchiveDispositionKind
from gateway_backend.domain.baseline.models import BaselineNode, BaselineNodeKind
from gateway_backend.domain.submission.models import Submission
from gateway_backend.domain.submission.review import ReviewStatus
from gateway_backend.domain.workspace.models import BaselineHead, IdentityContext

PERMISSION_READ_PROJECT_HISTORY = "read_project_history"
DEFAULT_HISTORY_PAGE_LIMIT = 100
MAX_HISTORY_PAGE_LIMIT = 500
MAX_HISTORY_CURSOR_BYTES = 1024

HISTORY_COMPARE_JOB_KIND = "backend-vnext/history-compare"
HISTORY_COMPARE_JOB_CONTRACT_VERSION = "backend-vnext/history-compare/v1"
HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION = "backend-vnext/comparison/v2"
HISTORY_COMPARE_MIN_NODES = 2
HISTORY_COMPARE_MAX_NODES = 3
HISTORY_COMPARE_VIEW_KIND = "HISTORY"
HISTORY_INTEGRITY_FAILURE_CLASS = "HISTORY_REPOSITORY_INTEGRITY"
HISTORY_INTEGRITY_RECOMMENDED_ACTION = "OPERATOR_REVIEW_REQUIRED"


class HistoryCompareDiagnosticCode(StrEnum):
    """Worker/job contract diagnostic codes for History compare."""

    HISTORY_COMMIT_UNAVAILABLE = "HISTORY_COMMIT_UNAVAILABLE"
    HISTORY_REPOSITORY_INTEGRITY = "HISTORY_REPOSITORY_INTEGRITY"
    HISTORY_RULESET_VERSION_MISMATCH = "HISTORY_RULESET_VERSION_MISMATCH"


class IntegrityAcknowledgementStatus(StrEnum):
    PENDING = "PENDING"
    ACKNOWLEDGED = "ACKNOWLEDGED"


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


@dataclass(frozen=True, slots=True)
class HistoryCompareNodeBinding:
    ref_kind: HistoryNodeRefKind
    ref_id: str
    commit_id: str

    def __post_init__(self) -> None:
        if type(self.ref_kind) is not HistoryNodeRefKind:
            raise ValueError("ref_kind must be HistoryNodeRefKind")
        if type(self.ref_id) is not str or not self.ref_id:
            raise ValueError("ref_id must be a non-empty string")
        if type(self.commit_id) is not str or not self.commit_id:
            raise ValueError("commit_id must be a non-empty string")


@dataclass(frozen=True, slots=True)
class HistoryCompareAcceptanceRecord:
    acceptance_id: str
    gateway_device_external_key: str
    business_project_id: str
    repository_id: str
    idempotency_key: str
    request_fingerprint: str
    comparison_ruleset_digest: str
    nodes: tuple[HistoryCompareNodeBinding, ...]
    operation_id: str
    created_at: datetime

    def __post_init__(self) -> None:
        for label in (
            "acceptance_id",
            "gateway_device_external_key",
            "business_project_id",
            "repository_id",
            "idempotency_key",
            "request_fingerprint",
            "comparison_ruleset_digest",
            "operation_id",
        ):
            value = getattr(self, label)
            if type(value) is not str or not value:
                raise ValueError(f"{label} must be a non-empty string")
        if type(self.nodes) is not tuple or not self.nodes:
            raise ValueError("nodes must be a non-empty tuple")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be an aware datetime")


@dataclass(frozen=True, slots=True)
class HistoryCompareIntegrityRecord:
    incident_id: str
    operation_id: str
    repository_id: str
    commit_refs: tuple[dict[str, str], ...]
    failure_class: str
    expected_digest: str
    observed_digest: str
    affected_tables: tuple[str, ...]
    recommended_action: str
    first_seen_at: datetime
    last_seen_at: datetime
    acknowledgement_status: IntegrityAcknowledgementStatus
    resolution_reference: str | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        for label in (
            "incident_id",
            "operation_id",
            "repository_id",
            "failure_class",
            "expected_digest",
            "observed_digest",
            "recommended_action",
        ):
            value = getattr(self, label)
            if type(value) is not str or not value:
                raise ValueError(f"{label} must be a non-empty string")
        if type(self.commit_refs) is not tuple:
            raise ValueError("commit_refs must be a tuple")
        if type(self.affected_tables) is not tuple:
            raise ValueError("affected_tables must be a tuple")
        if type(self.acknowledgement_status) is not IntegrityAcknowledgementStatus:
            raise ValueError("acknowledgement_status must be IntegrityAcknowledgementStatus")
        for label in ("first_seen_at", "last_seen_at", "created_at", "updated_at"):
            value = getattr(self, label)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{label} must be an aware datetime")
        if self.resolution_reference is not None and (
            type(self.resolution_reference) is not str or not self.resolution_reference
        ):
            raise ValueError("resolution_reference must be a non-empty string or None")


@dataclass(frozen=True, slots=True)
class HistoryCompareValidationResult:
    repository_id: str
    gateway_device_external_key: str
    business_project_id: str
    nodes: tuple[HistoryCompareNodeBinding, ...]
    request_fingerprint: str
    comparison_ruleset_digest: str
    replay: bool
    prior_acceptance: HistoryCompareAcceptanceRecord | None
    operation_id: str | None = None
    acceptance_id: str | None = None


@dataclass(frozen=True, slots=True)
class HistoryCompareAcceptCommand:
    context: IdentityContext
    idempotency_key: str
    node_refs: tuple[HistoryNodeRef, ...]

def parse_nodes_json(raw: str) -> tuple[HistoryCompareNodeBinding, ...]:
    import json

    decoded = json.loads(raw)
    if type(decoded) is not list:
        raise ValueError("nodes_json must decode to a list")
    nodes: list[HistoryCompareNodeBinding] = []
    for item in decoded:
        if type(item) is not dict:
            raise ValueError("nodes_json entry must be an object")
        nodes.append(
            HistoryCompareNodeBinding(
                ref_kind=HistoryNodeRefKind(str(item["ref_kind"])),
                ref_id=str(item["ref_id"]),
                commit_id=str(item["commit_id"]),
            )
        )
    return tuple(nodes)


def nodes_json_from_bindings(nodes: Sequence[HistoryCompareNodeBinding]) -> str:
    payload = [
        {
            "ref_kind": node.ref_kind.value,
            "ref_id": node.ref_id,
            "commit_id": node.commit_id,
        }
        for node in nodes
    ]
    return canonicalize_jcs(canonicalize_json_value(payload)).decode("utf-8")

