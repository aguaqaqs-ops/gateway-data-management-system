"""Closed response shapes for archive business diagnostics and frozen audit subjects."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from gateway_backend.http.schemas.constraints import NonNegativeIJsonInt

BusinessSubjectKind = Literal["CONFIGURATION_SOURCE", "CONFIGURATION_TIME_QUALITY", "CONFIGURATION_TIME_ORDER"]
TimeRelation = Literal["MODIFIED_BEFORE_INITIAL", "MODIFIED_BEFORE_BASELINE", "INITIAL_BEFORE_BASELINE"]
BusinessIssueCode = Literal["INITIAL_SOURCE_UNEXPLAINED", "GENERATION_TIME_MISSING", "GENERATION_TIME_INVALID_VALUES",
    "GENERATION_TIME_LAST_NOT_MAX", "TIME_ABNORMAL_MODIFIED", "TIME_ABNORMAL_INITIAL", "BASELINE_TIME_UNAVAILABLE"]


class ClosedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArchiveContentIdentityResponse(ClosedResponse):
    canonical_state_digest: str
    storage_projection_ruleset_digest: str
    storage_projection_version: str
    scalar_encoding_version: NonNegativeIJsonInt


class ArchiveGeneratedTimeResponse(ClosedResponse):
    rule_id: Literal["gateway-vnext/configuration-generated-time/v1"]
    status: Literal["VALID", "TABLE_ABSENT", "COLUMN_ABSENT", "NO_ROWS", "NO_VALUE", "NO_VALID_VALUE"]
    selected_time_utc: str | None
    max_valid_time_utc: str | None
    valid_count: NonNegativeIJsonInt
    empty_count: NonNegativeIJsonInt
    invalid_count: NonNegativeIJsonInt
    last_valid_source_row: NonNegativeIJsonInt | None
    max_valid_source_row: NonNegativeIJsonInt | None
    last_not_max: bool


class ArchiveSourceReferenceResponse(ClosedResponse):
    source_kind: Literal["BASELINE", "SUBMISSION"]
    side: Literal["INITIAL", "MODIFIED"]
    submission_id: str | None = None


class ArchiveSourceDiagnosticResponse(ClosedResponse):
    submission_id: str
    initial_origin: Literal["UPLOADED", "BASELINE_REUSED", "INITIAL_EMPTY"]
    detected_status: Literal["NOT_APPLICABLE", "UNEXPLAINED", "EXPLAINED"]
    initial_identity: ArchiveContentIdentityResponse
    baseline_identity: ArchiveContentIdentityResponse | None
    rules_identity_differs_from_baseline: bool
    matching_sources: list[ArchiveSourceReferenceResponse]


class ArchiveTimeComparisonResponse(ClosedResponse):
    submission_id: str
    relation: TimeRelation
    left_time_utc: str | None
    right_time_utc: str | None
    detected_status: Literal["NOT_APPLICABLE", "NOT_COMPARABLE", "BACKWARD", "NORMAL"]


class ArchiveSourceEdgeResponse(ClosedResponse):
    submission_id: str
    candidate_digest: str
    configuration_facts_digest: str
    initial: ArchiveContentIdentityResponse
    modified: ArchiveContentIdentityResponse


class ArchiveIssueDetailsResponse(ClosedResponse):
    generated_time: ArchiveGeneratedTimeResponse | None = None
    comparison_status: Literal["NOT_COMPARABLE"] | None = None
    states: list[ArchiveContentIdentityResponse] | None = None
    edges: list[ArchiveSourceEdgeResponse] | None = None
    detected_status: Literal["UNEXPLAINED"] | None = None
    comparisons: list[ArchiveTimeComparisonResponse] | None = None


class ArchiveBusinessIssueResponse(ClosedResponse):
    subject_kind: BusinessSubjectKind
    issue_code: BusinessIssueCode
    affected_submission_ids: list[str]
    side: Literal["INITIAL", "MODIFIED", "BASELINE"] | None
    relations: list[TimeRelation]
    details: ArchiveIssueDetailsResponse


class ArchiveBusinessValidationResponse(ClosedResponse):
    rule_id: Literal["gateway-vnext/archive-business-validation/v1"]
    baseline_facts_digest: str | None
    source_diagnostics: list[ArchiveSourceDiagnosticResponse]
    time_comparisons: list[ArchiveTimeComparisonResponse]
    issues: list[ArchiveBusinessIssueResponse]


class ArchiveAffectedCandidateResponse(ClosedResponse):
    submission_id: str
    candidate_digest: str
    configuration_facts_digest: str


class ArchiveBusinessSubjectResponse(ArchiveBusinessIssueResponse):
    selection_subject_digest: str
    rule_id: Literal["gateway-vnext/archive-business-validation/v1"]
    affected_candidates: list[ArchiveAffectedCandidateResponse]


class ArchiveSiblingSubjectResponse(ClosedResponse):
    selection_subject_digest: str
    issue_code: Literal["APPROVED_SIBLING_EXCLUDED"]
    target_submission_id: str
    target_candidate_digest: str


class ArchiveIdentitySubjectResponse(ClosedResponse):
    selection_subject_digest: str
    submission_id: str
    candidate_digest: str
    preview_bundle_digest: str
    assessment_set_digest: str


ArchiveAuditSubjectResponse = ArchiveBusinessSubjectResponse | ArchiveSiblingSubjectResponse | ArchiveIdentitySubjectResponse
