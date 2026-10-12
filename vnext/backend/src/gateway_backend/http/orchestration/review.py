"""Review orchestration for HTTP apply and read routes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from gateway_backend.application.submission.review import get_review_facts
from gateway_backend.application.submission.review_contracts import ApplyReviewCommand
from gateway_backend.application.submission.review_transaction import apply_review_transaction
from gateway_backend.application.submission.ports import ReviewApplyControlUnitOfWorkFactory
from gateway_backend.domain.submission.errors import InvalidReviewIdempotencyKey
from gateway_backend.domain.submission.review import ReviewAction, validate_review_idempotency_key
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.domain.workspace.ports import ScopeResolutionPort
from gateway_backend.http.errors import ApiError
from gateway_backend.http.schemas.review import (
    ApplyReviewRequest,
    ReviewAppliedResponse,
    ReviewFactsResponse,
    apply_review_result_to_response,
    review_facts_to_response,
)


@dataclass(frozen=True, slots=True)
class ApplyReviewOperationResult:
    response: ReviewAppliedResponse
    replay: bool


def parse_review_idempotency_key(raw_header: str | None) -> str:
    if raw_header is None:
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="Idempotency-Key header is required",
            status_code=422,
        )
    try:
        return validate_review_idempotency_key(raw_header)
    except InvalidReviewIdempotencyKey:
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="request validation failed",
            status_code=422,
        ) from None


def build_apply_review_command(
    *,
    context: IdentityContext,
    submission_id: str,
    body: ApplyReviewRequest,
    idempotency_key: str,
) -> ApplyReviewCommand:
    return ApplyReviewCommand(
        context=context,
        submission_id=submission_id,
        expected_review_version=body.expected_review_version,
        action=ReviewAction(body.action),
        reason=body.reason,
        idempotency_key=idempotency_key,
    )


def apply_review_operation(
    *,
    command: ApplyReviewCommand,
    scope_resolution: ScopeResolutionPort,
    unit_of_work_factory: ReviewApplyControlUnitOfWorkFactory,
    now: datetime,
) -> ApplyReviewOperationResult:
    result = apply_review_transaction(
        command=command,
        scope_resolution=scope_resolution,
        unit_of_work_factory=unit_of_work_factory,
        now=now,
    )
    return ApplyReviewOperationResult(
        response=apply_review_result_to_response(result),
        replay=result.replay,
    )


def get_review_facts_operation(
    *,
    context: IdentityContext,
    submission_id: str,
    scope_resolution: ScopeResolutionPort,
    unit_of_work_factory: ReviewApplyControlUnitOfWorkFactory,
) -> ReviewFactsResponse:
    facts = get_review_facts(
        context=context,
        submission_id=submission_id,
        scope_resolution=scope_resolution,
        unit_of_work_factory=unit_of_work_factory,
    )
    return review_facts_to_response(facts)
