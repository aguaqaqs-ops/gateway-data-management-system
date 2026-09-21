"""Archive application contracts: digests, validators and command shapes."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from gateway_shared_kernel.jcs import canonicalize_jcs, canonicalize_json_value

from gateway_backend.domain.archive.models import (
    ArchiveAnomalyResolutionAction,
    ArchiveConfirmationAction,
)
from gateway_backend.domain.submission.review import ReviewStatus

ARCHIVE_DIGEST_PREFIX = "gateway-vnext:archive:"
ARCHIVE_DIGEST_VERSION = "v1"
ARCHIVE_MAX_CANDIDATES = 200
ARCHIVE_MAX_AUDIT_REFS = 200
ARCHIVE_MAX_REQUEST_BYTES = 256 * 1024
ARCHIVE_ID_MIN_BYTES = 1
ARCHIVE_ID_MAX_BYTES = 255
ARCHIVE_REASON_MIN_BYTES = 1
ARCHIVE_REASON_MAX_BYTES = 4096
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ArchiveCandidateRef:
    submission_id: str
    expected_candidate_digest: str


@dataclass(frozen=True, slots=True)
class ArchiveSelectedRef:
    submission_id: str
    expected_candidate_digest: str


@dataclass(frozen=True, slots=True)
class ArchiveAuditReferenceInput:
    subject_digest: str
    sequence: int


def validate_utf8_id(value: str, *, field_name: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{field_name} must be a string")
    encoded = value.encode("utf-8")
    if len(encoded) < ARCHIVE_ID_MIN_BYTES or len(encoded) > ARCHIVE_ID_MAX_BYTES:
        raise ValueError(f"{field_name} must be between 1 and 255 UTF-8 bytes")
    return value


def validate_utf8_reason(value: str, *, field_name: str = "reason") -> str:
    if type(value) is not str:
        raise ValueError(f"{field_name} must be a string")
    encoded = value.encode("utf-8")
    if len(encoded) < ARCHIVE_REASON_MIN_BYTES or len(encoded) > ARCHIVE_REASON_MAX_BYTES:
        raise ValueError(f"{field_name} must be between 1 and 4096 UTF-8 bytes")
    return value


def validate_archive_digest(value: str, *, field_name: str) -> str:
    if type(value) is not str or not _DIGEST_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a sha256 digest")
    return value


def validate_non_negative_int(value: int, *, field_name: str) -> int:
    if type(value) is not int or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def compute_archive_digest(kind: str, payload: Mapping[str, Any]) -> str:
    if type(kind) is not str or not kind:
        raise ValueError("kind must be a non-empty string")
    preimage = (
        f"{ARCHIVE_DIGEST_PREFIX}{kind}:{ARCHIVE_DIGEST_VERSION}".encode("utf-8")
        + b"\x00"
        + canonicalize_jcs(canonicalize_json_value(dict(payload)))
    )
    return f"sha256:{hashlib.sha256(preimage).hexdigest()}"


def _sorted_unique_ids(values: Sequence[str]) -> tuple[str, ...]:
    if len(set(values)) != len(values):
        raise ValueError("duplicate ids are not allowed")
    return tuple(sorted(values, key=lambda item: item.encode("utf-8")))


def compute_candidate_digest(
    *,
    repository_id: str,
    gateway_device_external_key: str,
    business_project_id: str,
    workspace_id: str,
    workspace_generation: int,
    submission_id: str,
    submit_attempt_id: str,
    upload_revision_id: str,
    preview_result_id: str,
    based_on_baseline_node_id: str,
    business_baseline_commit_id: str,
    repository_commit_id: str,
    canonical_business_digest: str,
    canonicalization_manifest_ref: str,
    canonicalization_manifest_digest: str,
    source_artifact_refs: Sequence[str],
    requested_verification_policy: str,
    completed_verification_policy: str,
    review_status: str,
    review_sequence: int,
) -> str:
    payload = {
        "based_on_baseline_node_id": based_on_baseline_node_id,
        "business_baseline_commit_id": business_baseline_commit_id,
        "business_project_id": business_project_id,
        "canonical_business_digest": canonical_business_digest,
        "canonicalization_manifest_digest": canonicalization_manifest_digest,
        "canonicalization_manifest_ref": canonicalization_manifest_ref,
        "completed_verification_policy": completed_verification_policy,
        "gateway_device_external_key": gateway_device_external_key,
        "preview_result_id": preview_result_id,
        "repository_commit_id": repository_commit_id,
        "repository_id": repository_id,
        "requested_verification_policy": requested_verification_policy,
        "review_sequence": review_sequence,
        "review_status": review_status,
        "source_artifact_refs": _sorted_unique_ids(tuple(source_artifact_refs)),
        "submission_id": submission_id,
        "submit_attempt_id": submit_attempt_id,
        "upload_revision_id": upload_revision_id,
        "workspace_generation": workspace_generation,
        "workspace_id": workspace_id,
    }
    return compute_archive_digest("candidate", payload)


def compute_candidate_set_digest(
    *,
    repository_id: str,
    gateway_device_external_key: str,
    business_project_id: str,
    baseline_node_id: str,
    baseline_commit_id: str,
    baseline_head_version: int,
    candidates: Sequence[ArchiveCandidateRef],
) -> str:
    if len(candidates) > ARCHIVE_MAX_CANDIDATES:
        raise ValueError("candidate set exceeds supported limit")
    candidate_payloads = tuple(
        {
            "candidate_digest": validate_archive_digest(
                candidate.expected_candidate_digest,
                field_name="expected_candidate_digest",
            ),
            "submission_id": validate_utf8_id(candidate.submission_id, field_name="submission_id"),
        }
        for candidate in sorted(candidates, key=lambda item: item.submission_id.encode("utf-8"))
    )
    submission_ids = tuple(item["submission_id"] for item in candidate_payloads)
    if len(set(submission_ids)) != len(submission_ids):
        raise ValueError("duplicate submission ids are not allowed")
    payload = {
        "baseline_commit_id": baseline_commit_id,
        "baseline_head_version": baseline_head_version,
        "baseline_node_id": baseline_node_id,
        "business_project_id": business_project_id,
        "candidates": candidate_payloads,
        "gateway_device_external_key": gateway_device_external_key,
        "repository_id": repository_id,
    }
    return compute_archive_digest("candidate-set", payload)


def compute_selection_subject_digest(
    *,
    candidate_set_digest: str,
    selected_submission_id: str,
    expected_candidate_digest: str,
) -> str:
    payload = {
        "candidate_set_digest": validate_archive_digest(candidate_set_digest, field_name="candidate_set_digest"),
        "expected_candidate_digest": validate_archive_digest(
            expected_candidate_digest,
            field_name="expected_candidate_digest",
        ),
        "selected_submission_id": validate_utf8_id(
            selected_submission_id,
            field_name="selected_submission_id",
        ),
    }
    return compute_archive_digest("selection", payload)


def compute_anomaly_subject_digest(
    *,
    selection_subject_digest: str,
    issue_code: str,
    sibling_submission_id: str,
    sibling_candidate_digest: str,
) -> str:
    payload = {
        "issue_code": issue_code,
        "selection_subject_digest": validate_archive_digest(
            selection_subject_digest,
            field_name="selection_subject_digest",
        ),
        "sibling_candidate_digest": validate_archive_digest(
            sibling_candidate_digest,
            field_name="sibling_candidate_digest",
        ),
        "sibling_submission_id": validate_utf8_id(
            sibling_submission_id,
            field_name="sibling_submission_id",
        ),
    }
    return compute_archive_digest("anomaly", payload)


def compute_confirmation_request_fingerprint(
    *,
    repository_id: str,
    gateway_device_external_key: str,
    business_project_id: str,
    expected_baseline_node_id: str,
    expected_baseline_head_version: int,
    selected_submission_id: str,
    expected_candidate_digest: str,
    candidate_set_digest: str,
    subject_digest: str,
    expected_sequence: int,
    action: ArchiveConfirmationAction,
    reason: str,
    actor_id: str,
) -> str:
    payload = {
        "action": action.value,
        "actor_id": validate_utf8_id(actor_id, field_name="actor_id"),
        "business_project_id": business_project_id,
        "candidate_set_digest": validate_archive_digest(candidate_set_digest, field_name="candidate_set_digest"),
        "command_kind": "CONFIRMATION",
        "expected_baseline_head_version": expected_baseline_head_version,
        "expected_baseline_node_id": expected_baseline_node_id,
        "expected_candidate_digest": validate_archive_digest(
            expected_candidate_digest,
            field_name="expected_candidate_digest",
        ),
        "expected_sequence": expected_sequence,
        "gateway_device_external_key": gateway_device_external_key,
        "reason": validate_utf8_reason(reason),
        "repository_id": repository_id,
        "selected_submission_id": validate_utf8_id(selected_submission_id, field_name="selected_submission_id"),
        "subject_digest": validate_archive_digest(subject_digest, field_name="subject_digest"),
    }
    return compute_archive_digest("confirmation-request", payload)


def compute_resolution_request_fingerprint(
    *,
    repository_id: str,
    gateway_device_external_key: str,
    business_project_id: str,
    expected_baseline_node_id: str,
    expected_baseline_head_version: int,
    selected_submission_id: str,
    expected_candidate_digest: str,
    candidate_set_digest: str,
    subject_digest: str,
    expected_sequence: int,
    action: ArchiveAnomalyResolutionAction,
    reason: str,
    actor_id: str,
    issue_code: str,
    sibling_submission_id: str,
    sibling_candidate_digest: str,
) -> str:
    payload = {
        "action": action.value,
        "actor_id": validate_utf8_id(actor_id, field_name="actor_id"),
        "business_project_id": business_project_id,
        "candidate_set_digest": validate_archive_digest(candidate_set_digest, field_name="candidate_set_digest"),
        "command_kind": "RESOLUTION",
        "expected_baseline_head_version": expected_baseline_head_version,
        "expected_baseline_node_id": expected_baseline_node_id,
        "expected_candidate_digest": validate_archive_digest(
            expected_candidate_digest,
            field_name="expected_candidate_digest",
        ),
        "expected_sequence": expected_sequence,
        "gateway_device_external_key": gateway_device_external_key,
        "issue_code": issue_code,
        "reason": validate_utf8_reason(reason),
        "repository_id": repository_id,
        "selected_submission_id": validate_utf8_id(selected_submission_id, field_name="selected_submission_id"),
        "sibling_candidate_digest": validate_archive_digest(
            sibling_candidate_digest,
            field_name="sibling_candidate_digest",
        ),
        "sibling_submission_id": validate_utf8_id(
            sibling_submission_id,
            field_name="sibling_submission_id",
        ),
        "subject_digest": validate_archive_digest(subject_digest, field_name="subject_digest"),
    }
    return compute_archive_digest("resolution-request", payload)


def compute_start_request_fingerprint(
    *,
    repository_id: str,
    gateway_device_external_key: str,
    business_project_id: str,
    expected_baseline_node_id: str,
    expected_baseline_head_version: int,
    candidate_set_digest: str,
    selected_submission_id: str,
    expected_candidate_digest: str,
    confirmation_refs: Sequence[ArchiveAuditReferenceInput],
    anomaly_resolution_refs: Sequence[ArchiveAuditReferenceInput],
) -> str:
    if len(confirmation_refs) > ARCHIVE_MAX_AUDIT_REFS:
        raise ValueError("confirmation refs exceed supported limit")
    if len(anomaly_resolution_refs) > ARCHIVE_MAX_AUDIT_REFS:
        raise ValueError("anomaly resolution refs exceed supported limit")
    confirmation_payload = tuple(
        {
            "sequence": validate_non_negative_int(ref.sequence, field_name="sequence"),
            "subject_digest": validate_archive_digest(ref.subject_digest, field_name="subject_digest"),
        }
        for ref in sorted(confirmation_refs, key=lambda item: item.subject_digest)
    )
    resolution_payload = tuple(
        {
            "sequence": validate_non_negative_int(ref.sequence, field_name="sequence"),
            "subject_digest": validate_archive_digest(ref.subject_digest, field_name="subject_digest"),
        }
        for ref in sorted(anomaly_resolution_refs, key=lambda item: item.subject_digest)
    )
    payload = {
        "anomaly_resolution_refs": resolution_payload,
        "business_project_id": business_project_id,
        "candidate_set_digest": validate_archive_digest(candidate_set_digest, field_name="candidate_set_digest"),
        "command_kind": "START",
        "confirmation_refs": confirmation_payload,
        "expected_baseline_head_version": expected_baseline_head_version,
        "expected_baseline_node_id": expected_baseline_node_id,
        "expected_candidate_digest": validate_archive_digest(
            expected_candidate_digest,
            field_name="expected_candidate_digest",
        ),
        "gateway_device_external_key": gateway_device_external_key,
        "repository_id": repository_id,
        "selected_submission_id": validate_utf8_id(selected_submission_id, field_name="selected_submission_id"),
    }
    return compute_archive_digest("start-request", payload)


def review_status_to_archive_value(status: ReviewStatus) -> str:
    return status.value
