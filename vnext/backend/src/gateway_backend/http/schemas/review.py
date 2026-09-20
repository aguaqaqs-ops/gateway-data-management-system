"""Review HTTP DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gateway_backend.application.submission.review_contracts import ApplyReviewResult, ReviewFacts
from gateway_backend.domain.submission.review import ReviewEvent, ReviewProjection
from gateway_backend.http.schemas.constraints import BoundedDiagnosticReason, NonNegativeIJsonInt

ReviewActionLiteral = Literal["APPROVE", "REJECT", "RETURN_FOR_REVISION", "WITHDRAW"]
ReviewStatusLiteral = Literal[
    "PENDING",
    "APPROVED",
    "REJECTED",
    "RETURNED_FOR_REVISION",
    "WITHDRAWN",
]
ReviewEventKindLiteral = Literal[
    "SUBMISSION_FINALIZED",
    "APPROVED",
    "REJECTED",
    "RETURNED_FOR_REVISION",
    "WITHDRAWN",
]


class ApplyReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_review_version: NonNegativeIJsonInt
    action: ReviewActionLiteral
    reason: BoundedDiagnosticReason | None = None


class ReviewEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int
    event_kind: ReviewEventKindLiteral
    from_status: ReviewStatusLiteral | None = None
    to_status: ReviewStatusLiteral
    reason: str | None = None
    actor_id: str
    occurred_at: datetime


class ReviewAppliedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: str
    status: ReviewStatusLiteral
    review_version: int
    event: ReviewEventResponse


class ReviewFactsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: str
    status: ReviewStatusLiteral
    review_version: int
    updated_by: str
    updated_at: datetime
    events: list[ReviewEventResponse] = Field(default_factory=list)


def review_event_to_response(event: ReviewEvent) -> ReviewEventResponse:
    return ReviewEventResponse(
        sequence=event.sequence,
        event_kind=event.event_kind.value,
        from_status=event.from_status.value if event.from_status is not None else None,
        to_status=event.to_status.value,
        reason=event.reason,
        actor_id=event.actor_id,
        occurred_at=event.occurred_at,
    )


def review_projection_to_status(projection: ReviewProjection) -> ReviewStatusLiteral:
    return projection.status.value


def apply_review_result_to_response(result: ApplyReviewResult) -> ReviewAppliedResponse:
    return ReviewAppliedResponse(
        submission_id=result.event.submission_id,
        status=result.projection.status.value,
        review_version=result.projection.optimistic_version,
        event=review_event_to_response(result.event),
    )


def review_facts_to_response(facts: ReviewFacts) -> ReviewFactsResponse:
    projection = facts.projection
    return ReviewFactsResponse(
        submission_id=projection.submission_id,
        status=projection.status.value,
        review_version=projection.optimistic_version,
        updated_by=projection.updated_by,
        updated_at=projection.updated_at,
        events=[review_event_to_response(event) for event in facts.events],
    )
