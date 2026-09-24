"""History HTTP DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from gateway_backend.application.history.contracts import (
    HistoryHead,
    HistoryNode,
    HistoryTreeProjection,
)
from gateway_backend.http.schemas.constraints import (
    BoundedOpaqueId,
    NonNegativeIJsonInt,
    Sha256Digest,
)
from gateway_repository_contracts.types import CommitIdString

HistoryNodeRefKindLiteral = Literal["baseline_node", "submission"]
HistoryNodeKindLiteral = Literal["BASELINE_NODE", "SUBMISSION", "SYSTEM_MIGRATION"]
HistoryBaselineKindLiteral = Literal["INITIAL", "ARCHIVED_SUBMISSION"]
HistoryReviewStatusLiteral = Literal[
    "PENDING",
    "APPROVED",
    "REJECTED",
    "RETURNED_FOR_REVISION",
    "WITHDRAWN",
]
HistoryArchiveDispositionLiteral = Literal["ARCHIVED_BASELINE", "CLOSED_NOT_ARCHIVED"]
HistoryEligibilityNoteLiteral = Literal["NOT_CANDIDATE_BASE_ADVANCED"]


class HistoryNodeRefResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref_kind: HistoryNodeRefKindLiteral
    ref_id: BoundedOpaqueId


class HistoryHeadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: BoundedOpaqueId
    commit_id: CommitIdString
    version: NonNegativeIJsonInt


class HistoryNodeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref_kind: HistoryNodeRefKindLiteral
    ref_id: BoundedOpaqueId
    node_kind: HistoryNodeKindLiteral
    commit_id: CommitIdString
    created_at: datetime
    parent: HistoryNodeRefResponse | None = None
    baseline_kind: HistoryBaselineKindLiteral | None = None
    review_status: HistoryReviewStatusLiteral | None = None
    archive_disposition: HistoryArchiveDispositionLiteral | None = None
    promoted_baseline_node_id: BoundedOpaqueId | None = None
    eligibility_note: HistoryEligibilityNoteLiteral | None = None


class HistoryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    head: HistoryHeadResponse
    nodes: list[HistoryNodeResponse]
    next_cursor: str | None = Field(default=None, max_length=1024)


def history_head_to_response(head: HistoryHead) -> HistoryHeadResponse:
    return HistoryHeadResponse(
        node_id=head.node_id,
        commit_id=head.commit_id,
        version=head.version,
    )


def history_node_to_response(node: HistoryNode) -> HistoryNodeResponse:
    parent = None
    if node.parent is not None:
        parent = HistoryNodeRefResponse(
            ref_kind=node.parent.ref_kind.value,
            ref_id=node.parent.ref_id,
        )
    return HistoryNodeResponse(
        ref_kind=node.ref_kind.value,
        ref_id=node.ref_id,
        node_kind=node.node_kind.value,
        commit_id=node.commit_id,
        created_at=node.created_at,
        parent=parent,
        baseline_kind=None if node.baseline_kind is None else node.baseline_kind.value,
        review_status=None if node.review_status is None else node.review_status.value,
        archive_disposition=None if node.archive_disposition is None else node.archive_disposition.value,
        promoted_baseline_node_id=node.promoted_baseline_node_id,
        eligibility_note=(
            None
            if node.eligibility_note is None
            else cast(Literal["NOT_CANDIDATE_BASE_ADVANCED"], node.eligibility_note.value)
        ),
    )


def history_projection_to_response(projection: HistoryTreeProjection) -> HistoryListResponse:
    return HistoryListResponse(
        head=history_head_to_response(projection.head),
        nodes=[history_node_to_response(node) for node in projection.nodes],
        next_cursor=projection.next_cursor,
    )


class HistoryCompareNodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref_kind: HistoryNodeRefKindLiteral
    ref_id: BoundedOpaqueId


class HistoryCompareAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[HistoryCompareNodeRequest] = Field(min_length=2, max_length=3)


class HistoryCompareAcceptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    status: Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]
    replayed: bool


class HistoryCompareDiagnosticResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class HistoryComparePairResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pair_id: str
    before_ref: HistoryNodeRefResponse
    before_commit: CommitIdString
    current_ref: HistoryNodeRefResponse
    current_commit: CommitIdString
    comparison_digest: Sha256Digest
    risk_digest: Sha256Digest
    surface_digest: Sha256Digest
    record_count: NonNegativeIJsonInt


class HistoryCompareResultInputResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: dict[str, object]
    pairs: list[HistoryComparePairResultResponse]
    bundle_digest: Sha256Digest
    completed_at: datetime | None = None


class IntegrityIncidentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str
    operation_id: str
    repository_id: str
    commit_refs: list[dict[str, str]]
    failure_class: str
    expected_digest: Sha256Digest
    observed_digest: Sha256Digest
    affected_tables: list[str]
    recommended_action: str
    first_seen_at: datetime
    last_seen_at: datetime
    acknowledgement_status: Literal["PENDING", "ACKNOWLEDGED"]
    resolution_reference: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: object) -> IntegrityIncidentResponse:
        from gateway_backend.application.history.contracts import HistoryCompareIntegrityRecord

        if type(record) is not HistoryCompareIntegrityRecord:
            raise TypeError("record must be HistoryCompareIntegrityRecord")
        return cls(
            incident_id=record.incident_id,
            operation_id=record.operation_id,
            repository_id=record.repository_id,
            commit_refs=[dict(item) for item in record.commit_refs],
            failure_class=record.failure_class,
            expected_digest=record.expected_digest,
            observed_digest=record.observed_digest,
            affected_tables=list(record.affected_tables),
            recommended_action=record.recommended_action,
            first_seen_at=record.first_seen_at,
            last_seen_at=record.last_seen_at,
            acknowledgement_status=record.acknowledgement_status.value,
            resolution_reference=record.resolution_reference,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class HistoryCompareResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    status: Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]
    diagnostic: HistoryCompareDiagnosticResponse | None = None
    integrity_incident: IntegrityIncidentResponse | None = None
    result: HistoryCompareResultInputResponse | None = None


class IntegrityAcknowledgementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acknowledgement_status: Literal["ACKNOWLEDGED"]
    resolution_reference: BoundedOpaqueId


class IntegrityAcknowledgementResponse(IntegrityIncidentResponse):
    pass
