"""Application command and result contracts for Review use cases."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.domain.submission.review import (
    ReviewAction,
    ReviewEvent,
    ReviewProjection,
    validate_review_idempotency_key,
    validate_review_reason,
)
from gateway_backend.domain.workspace.models import IdentityContext

REVIEW_APPLY_FINGERPRINT_CONTRACT_VERSION = "gateway-vnext.review-apply-fingerprint.v1"
REVIEW_APPLY_FINGERPRINT_GOLDEN = (
    "sha256:f97a6da6f2c568efdbbecdf64b6687593f5dc10b708cca81e602ba1a4e77b909"
)


@dataclass(frozen=True, slots=True)
class ApplyReviewCommand:
    """Inbound caller command; does not carry request_fingerprint."""

    context: IdentityContext
    submission_id: str
    expected_review_version: int
    action: ReviewAction
    reason: str | None
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ApplyReviewResult:
    event: ReviewEvent
    projection: ReviewProjection
    request_fingerprint: str
    replay: bool


@dataclass(frozen=True, slots=True)
class ReviewFacts:
    projection: ReviewProjection
    events: tuple[ReviewEvent, ...]


def compute_review_apply_request_fingerprint(
    *,
    action: ReviewAction,
    business_project_id: str,
    expected_review_version: int,
    gateway_device_external_key: str,
    reason: str | None,
    repository_id: str,
    submission_id: str,
    workspace_id: str,
) -> str:
    """Return the stable Review apply request fingerprint for one closed object."""

    validated_reason = validate_review_reason(action, reason)
    if type(action) is not ReviewAction:
        raise ValueError("action must be ReviewAction")
    if type(business_project_id) is not str or not business_project_id:
        raise ValueError("business_project_id must be a non-empty string")
    if type(expected_review_version) is not int or expected_review_version < 0:
        raise ValueError("expected_review_version must be a non-negative integer")
    if type(gateway_device_external_key) is not str or not gateway_device_external_key:
        raise ValueError("gateway_device_external_key must be a non-empty string")
    if type(repository_id) is not str or not repository_id:
        raise ValueError("repository_id must be a non-empty string")
    if type(submission_id) is not str or not submission_id:
        raise ValueError("submission_id must be a non-empty string")
    if type(workspace_id) is not str or not workspace_id:
        raise ValueError("workspace_id must be a non-empty string")

    payload = {
        "action": action.value,
        "business_project_id": business_project_id,
        "contract_version": REVIEW_APPLY_FINGERPRINT_CONTRACT_VERSION,
        "expected_review_version": expected_review_version,
        "gateway_device_external_key": gateway_device_external_key,
        "reason": validated_reason,
        "repository_id": repository_id,
        "submission_id": submission_id,
        "workspace_id": workspace_id,
    }
    digest = hashlib.sha256(canonicalize_json_value(payload)).hexdigest()
    return f"sha256:{digest}"


def build_apply_review_request_fingerprint_from_command(
    *,
    command: ApplyReviewCommand,
    workspace_id: str,
    repository_id: str,
) -> str:
    """Compute request fingerprint after scope closure using validated command facts."""

    validated_command = validate_apply_review_command(command)
    return compute_review_apply_request_fingerprint(
        action=validated_command.action,
        business_project_id=validated_command.context.business_project_id,
        expected_review_version=validated_command.expected_review_version,
        gateway_device_external_key=validated_command.context.gateway_device_external_key,
        reason=validated_command.reason,
        repository_id=repository_id,
        submission_id=validated_command.submission_id,
        workspace_id=workspace_id,
    )


def validate_apply_review_command(command: ApplyReviewCommand) -> ApplyReviewCommand:
    """Validate inbound command fields that must fail before persistence."""

    if type(command.context) is not IdentityContext:
        raise ValueError("context must be IdentityContext")
    if type(command.submission_id) is not str or not command.submission_id:
        raise ValueError("submission_id must be a non-empty string")
    if type(command.expected_review_version) is not int or command.expected_review_version < 0:
        raise ValueError("expected_review_version must be a non-negative integer")
    if type(command.action) is not ReviewAction:
        raise ValueError("action must be ReviewAction")
    validate_review_reason(command.action, command.reason)
    validate_review_idempotency_key(command.idempotency_key)
    return command
