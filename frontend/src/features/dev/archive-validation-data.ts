import type { components } from "../api/generated/openapi";

type Schemas = components["schemas"];
type Anomaly = Schemas["ArchivePreviewAnomalyResponse"];
type Preview = Schemas["PreviewArchivePlanResponse"];
type Candidates = Schemas["ArchiveCandidatesResponse"];

/**
 * FE3c archive-validation fixtures (kickoff §16.8–§16.9).
 *
 * Reachability sources are noted on each builder. Every candidate carries a
 * required `review_version` that equals the same submission's Review GET
 * version in the scenario (both come from the review projection), stays
 * distinct across candidates, and never collides with workspace or baseline
 * versions (§5.3).
 */

export const V_SUBMISSIONS = ["v-s1", "v-s2", "v-s3"] as const;

export const V_REVIEW_VERSIONS: Record<string, number> = {
  "v-s1": 11,
  "v-s2": 12,
  "v-s3": 13,
};

export function vCandidate(submissionId: string): Schemas["ArchiveCandidateResponse"] {
  const reviewVersion = V_REVIEW_VERSIONS[submissionId];
  if (reviewVersion === undefined) throw new Error(`unknown V-scenario submission: ${submissionId}`);
  return {
    submission_id: submissionId,
    expected_candidate_digest: `sha256:v-candidate-${submissionId}`,
    review_version: reviewVersion,
  };
}

export const V_CANDIDATES: Candidates = {
  head: { business_baseline_node_id: "v-baseline-7", business_baseline_commit_id: "commit-v-7", baseline_head_version: 7 },
  candidates: [vCandidate("v-s1"), vCandidate("v-s2"), vCandidate("v-s3")],
  candidate_set_digest: "sha256:v-candidates",
  blockers: [],
  pending_submission_ids: [],
  pending_submission_count: 0,
} satisfies Candidates;

const EMPTY_VALIDATION: Schemas["ArchiveBusinessValidationResponse"] = {
  rule_id: "gateway-vnext/archive-business-validation/v1",
  baseline_facts_digest: null,
  issues: [],
  source_diagnostics: [],
  time_comparisons: [],
};

function vPlan(overrides: Partial<Preview>): Preview {
  return {
    head: V_CANDIDATES.head,
    selected: { submission_id: "v-s1", expected_candidate_digest: "sha256:v-candidate-v-s1" },
    selection_subject_digest: "sha256:v-selection-subject",
    candidate_set_digest: "sha256:v-candidates",
    confirmation_requirements: ["sha256:v-selection-subject"],
    anomalies: [],
    audit_validity: false,
    can_start: false,
    dispositions: [],
    workspace_releases: [],
    blockers: [],
    pending_submission_ids: [],
    pending_submission_count: 0,
    business_validation: EMPTY_VALIDATION,
    ...overrides,
  } satisfies Preview;
}

export function vAnomaly(overrides: Partial<Anomaly> & { issue_code: Anomaly["issue_code"]; subject_kind: Anomaly["subject_kind"] }): Anomaly {
  return {
    target_submission_id: "v-s1",
    target_candidate_digest: "sha256:v-candidate-v-s1",
    subject_digest: "sha256:v-anomaly",
    accepted_at: null,
    accepted_by: null,
    affected_submission_ids: ["v-s1"],
    details: {},
    detected_status: "DETECTED",
    latest_sequence: 0,
    reason: null,
    relations: [],
    resolution_status: "UNRESOLVED",
    side: "MODIFIED",
    ...overrides,
  } satisfies Anomaly;
}

function vGeneratedTime(status: Schemas["ArchiveGeneratedTimeResponse"]["status"]): Schemas["ArchiveGeneratedTimeResponse"] {
  return {
    empty_count: 0,
    invalid_count: status === "NO_VALID_VALUE" ? 2 : 0,
    last_not_max: false,
    last_valid_source_row: status === "VALID" || status === "NO_VALID_VALUE" ? null : 4,
    max_valid_source_row: null,
    max_valid_time_utc: null,
    rule_id: "gateway-vnext/configuration-generated-time/v1",
    selected_time_utc: status === "VALID" ? "2026-11-07T12:00:00Z" : null,
    status,
    valid_count: status === "VALID" ? 4 : 0,
  };
}

function vContentDigest(tag: string): Schemas["ArchiveContentIdentityResponse"] {
  return {
    canonical_state_digest: `sha256:v-content-${tag}`,
    scalar_encoding_version: 1,
    storage_projection_ruleset_digest: "sha256:v-ruleset",
    storage_projection_version: "v1",
  };
}

/** V1: one card per known code (7 business + sibling + identity), all UNRESOLVED. */
export function vAllKindsAnomalies(): Anomaly[] {
  return [
    vAnomaly({
      issue_code: "INITIAL_SOURCE_UNEXPLAINED", subject_kind: "CONFIGURATION_SOURCE",
      subject_digest: "sha256:v-source", detected_status: "UNEXPLAINED", side: "INITIAL",
      affected_submission_ids: ["v-s1"],
      details: {
        detected_status: "UNEXPLAINED",
        edges: [{ submission_id: "v-s1", candidate_digest: "sha256:v-candidate-v-s1", configuration_facts_digest: "sha256:v-facts-s1", initial: vContentDigest("s1-initial"), modified: vContentDigest("s1-modified") }],
        states: [vContentDigest("state-1"), vContentDigest("state-2")],
      },
    }),
    vAnomaly({
      issue_code: "GENERATION_TIME_MISSING", subject_kind: "CONFIGURATION_TIME_QUALITY",
      subject_digest: "sha256:v-time-missing-modified", side: "MODIFIED",
      details: { generated_time: vGeneratedTime("COLUMN_ABSENT") },
    }),
    vAnomaly({
      issue_code: "GENERATION_TIME_INVALID_VALUES", subject_kind: "CONFIGURATION_TIME_QUALITY",
      subject_digest: "sha256:v-time-invalid", side: "MODIFIED",
      details: { generated_time: { ...vGeneratedTime("VALID"), invalid_count: 2, selected_time_utc: "2026-11-07T12:00:00Z", last_valid_source_row: 5 } },
    }),
    vAnomaly({
      issue_code: "GENERATION_TIME_LAST_NOT_MAX", subject_kind: "CONFIGURATION_TIME_QUALITY",
      subject_digest: "sha256:v-time-last-not-max", side: "MODIFIED",
      details: { generated_time: { ...vGeneratedTime("VALID"), last_not_max: true, selected_time_utc: "2026-11-07T11:00:00Z", last_valid_source_row: 3, max_valid_time_utc: "2026-11-07T12:00:00Z", max_valid_source_row: 1 } },
    }),
    vAnomaly({
      issue_code: "TIME_ABNORMAL_MODIFIED", subject_kind: "CONFIGURATION_TIME_ORDER",
      subject_digest: "sha256:v-time-regression", side: "MODIFIED",
      relations: ["MODIFIED_BEFORE_BASELINE"],
      details: { comparisons: [{ detected_status: "BACKWARD", relation: "MODIFIED_BEFORE_BASELINE", submission_id: "v-s1", left_time_utc: "2026-11-06T12:00:00Z", right_time_utc: "2026-11-07T12:00:00Z" }] },
    }),
    vAnomaly({
      issue_code: "TIME_ABNORMAL_INITIAL", subject_kind: "CONFIGURATION_TIME_ORDER",
      subject_digest: "sha256:v-time-initial", side: "INITIAL",
      relations: ["INITIAL_BEFORE_BASELINE"],
      details: { comparisons: [{ detected_status: "BACKWARD", relation: "INITIAL_BEFORE_BASELINE", submission_id: "v-s1", left_time_utc: "2026-11-05T12:00:00Z", right_time_utc: "2026-11-07T12:00:00Z" }] },
    }),
    vAnomaly({
      issue_code: "BASELINE_TIME_UNAVAILABLE", subject_kind: "CONFIGURATION_TIME_QUALITY",
      subject_digest: "sha256:v-baseline-time", side: "BASELINE",
      affected_submission_ids: ["v-s1", "v-s2", "v-s3"],
      details: { comparison_status: "NOT_COMPARABLE", generated_time: null },
    }),
    vAnomaly({
      issue_code: "APPROVED_SIBLING_EXCLUDED", subject_kind: "APPROVED_SIBLING_EXCLUDED",
      subject_digest: "sha256:v-sibling-s2", target_submission_id: "v-s2", target_candidate_digest: "sha256:v-candidate-v-s2",
      side: null, affected_submission_ids: ["v-s2"], details: {},
    }),
    vAnomaly({
      issue_code: "PROJECT_IDENTITY_EXCEPTION", subject_kind: "PROJECT_IDENTITY_EXCEPTION",
      subject_digest: "sha256:v-identity", side: null, details: {},
    }),
  ];
}

export function vValidationFor(): Schemas["ArchiveBusinessValidationResponse"] {
  return {
    rule_id: "gateway-vnext/archive-business-validation/v1",
    baseline_facts_digest: "sha256:v-baseline-facts",
    issues: [],
    source_diagnostics: [{
      baseline_identity: vContentDigest("baseline"),
      detected_status: "UNEXPLAINED",
      initial_identity: vContentDigest("v-s1-initial"),
      initial_origin: "UPLOADED",
      matching_sources: [],
      rules_identity_differs_from_baseline: false,
      submission_id: "v-s1",
    }],
    time_comparisons: [{
      detected_status: "NOT_COMPARABLE",
      left_time_utc: null,
      relation: "MODIFIED_BEFORE_BASELINE",
      right_time_utc: null,
      submission_id: "v-s1",
    }],
  };
}

/** V1: every known kind renders its own card with its details type. */
export function vPreviewAllKinds(): Preview {
  const anomalies = vAllKindsAnomalies();
  return vPlan({ anomalies, business_validation: vValidationFor() });
}

/** V2: same code and target on INITIAL and MODIFIED are two independent items. */
export function vPreviewTwoSided(): Preview {
  const initial = vAnomaly({
    issue_code: "GENERATION_TIME_MISSING", subject_kind: "CONFIGURATION_TIME_QUALITY",
    subject_digest: "sha256:v-twoside-initial", side: "INITIAL",
    details: { generated_time: vGeneratedTime("COLUMN_ABSENT") },
  });
  const modified = vAnomaly({
    issue_code: "GENERATION_TIME_MISSING", subject_kind: "CONFIGURATION_TIME_QUALITY",
    subject_digest: "sha256:v-twoside-modified", side: "MODIFIED",
    details: { generated_time: vGeneratedTime("COLUMN_ABSENT") },
  });
  const anomalies = [initial, modified];
  return vPlan({ anomalies, business_validation: vValidationFor() });
}

/** V13: both sides accepted, so the dialog allows start (the stub rejects it). */
export function vPreviewTwoSidedAccepted(): Preview {
  const base = vPreviewTwoSided();
  return {
    ...base,
    anomalies: base.anomalies.map((anomaly) => ({
      ...anomaly,
      resolution_status: "ACCEPTED" as const,
      latest_sequence: 2,
      accepted_by: "archiver-1",
      accepted_at: "2026-11-07T15:20:00Z",
      reason: "两侧已核对",
    })),
    audit_validity: true,
    can_start: true,
  };
}

/** V3/V4: an accepted source item keeps "来源未解释" next to "已接受". */
export function vPreviewAcceptedSource(): Preview {
  const accepted = vAnomaly({
    issue_code: "INITIAL_SOURCE_UNEXPLAINED", subject_kind: "CONFIGURATION_SOURCE",
    subject_digest: "sha256:v-source", detected_status: "UNEXPLAINED", side: "INITIAL",
    resolution_status: "ACCEPTED", latest_sequence: 3,
    accepted_by: "archiver-1", accepted_at: "2026-11-07T15:20:00Z", reason: "已核对纸质流转单",
    affected_submission_ids: ["v-s1"],
    details: {
      detected_status: "UNEXPLAINED",
      edges: [{ submission_id: "v-s1", candidate_digest: "sha256:v-candidate-v-s1", configuration_facts_digest: "sha256:v-facts-s1", initial: vContentDigest("s1-initial"), modified: vContentDigest("s1-modified") }],
      states: [vContentDigest("state-1")],
    },
  });
  const pending = vAnomaly({
    issue_code: "GENERATION_TIME_MISSING", subject_kind: "CONFIGURATION_TIME_QUALITY",
    subject_digest: "sha256:v-time-missing-modified", side: "MODIFIED",
    details: { generated_time: vGeneratedTime("COLUMN_ABSENT") },
  });
  const anomalies = [accepted, pending];
  return vPlan({ anomalies, business_validation: vValidationFor() });
}

/** V1 unknown-code probe: no accept entry, start stays disabled. */
export function vPreviewUnknownCode(): Preview {
  return vPlan({
    anomalies: [vAnomaly({
      issue_code: "FUTURE_CODE", subject_kind: "CONFIGURATION_TIME_QUALITY",
      subject_digest: "sha256:v-future", side: "MODIFIED",
      details: { generated_time: vGeneratedTime("COLUMN_ABSENT") },
    })],
    business_validation: EMPTY_VALIDATION,
  });
}

/**
 * V6: 200 FULL candidates on an empty INITIAL baseline. Each side has an
 * effective generation time on ① and a missing one on ② (NOT_COMPARABLE, so
 * no regression items); the selected candidate has one MODIFIED-side
 * GENERATION_TIME_MISSING and the other 199 each contribute one sibling
 * exclusion: 199 + 200 = 399 anomaly refs plus 1 confirmation ref.
 * Reachability: archive design §7.1 (N=200, empty INITIAL, no identity exception).
 */
export function vCandidates200(): Candidates {
  const candidates = Array.from({ length: 200 }, (_, index) => {
    const submissionId = `v-many-${index}`;
    return {
      submission_id: submissionId,
      expected_candidate_digest: `sha256:v-many-candidate-${index}`,
      review_version: 101 + index,
    };
  });
  return {
    head: { business_baseline_node_id: "v-baseline-empty", business_baseline_commit_id: "commit-v-0", baseline_head_version: 0 },
    candidates,
    candidate_set_digest: "sha256:v-many-candidates",
    blockers: [],
    pending_submission_ids: [],
    pending_submission_count: 0,
  } satisfies Candidates;
}

export function vPreview399(): Preview {
  const selected = "v-many-0";
  const anomalies: Anomaly[] = [];
  for (let index = 1; index < 200; index += 1) {
    anomalies.push(vAnomaly({
      issue_code: "APPROVED_SIBLING_EXCLUDED", subject_kind: "APPROVED_SIBLING_EXCLUDED",
      subject_digest: `sha256:v-many-sibling-${index}`,
      target_submission_id: `v-many-${index}`, target_candidate_digest: `sha256:v-many-candidate-${index}`,
      side: null, affected_submission_ids: [`v-many-${index}`], details: {},
    }));
  }
  for (let index = 0; index < 200; index += 1) {
    anomalies.push(vAnomaly({
      issue_code: "GENERATION_TIME_MISSING", subject_kind: "CONFIGURATION_TIME_QUALITY",
      subject_digest: `sha256:v-many-time-${index}`,
      target_submission_id: `v-many-${index}`, target_candidate_digest: `sha256:v-many-candidate-${index}`,
      side: "MODIFIED", affected_submission_ids: [`v-many-${index}`],
      details: { generated_time: vGeneratedTime("COLUMN_ABSENT") },
    }));
  }
  return vPlan({
    head: { business_baseline_node_id: "v-baseline-empty", business_baseline_commit_id: "commit-v-0", baseline_head_version: 0 },
    selected: { submission_id: selected, expected_candidate_digest: "sha256:v-many-candidate-0" },
    candidate_set_digest: "sha256:v-many-candidates",
    confirmation_requirements: ["sha256:v-many-selection-subject"],
    selection_subject_digest: "sha256:v-many-selection-subject",
    anomalies,
    audit_validity: false,
    can_start: false,
    business_validation: EMPTY_VALIDATION,
  });
}

/** V6 accepted twin: every item ACCEPTED, so start refs cover all 399. */
export function vPreview399Accepted(): Preview {
  const base = vPreview399();
  return {
    ...base,
    anomalies: base.anomalies.map((anomaly, index) => ({
      ...anomaly,
      resolution_status: "ACCEPTED" as const,
      latest_sequence: index + 1,
      accepted_by: "archiver-1",
      accepted_at: "2026-11-07T15:20:00Z",
      reason: "v6 批量核对",
    })),
    audit_validity: true,
    can_start: true,
  };
}

/** V7: integrity/attempt blockers carry text and a re-preview affordance only. */
export function vPreviewBlocked(blocker: "ARCHIVE_INTEGRITY_FAILURE" | "ACTIVE_SUBMIT_ATTEMPT"): Preview {
  return vPlan({
    anomalies: [],
    blockers: [blocker],
    audit_validity: false,
    can_start: false,
    business_validation: EMPTY_VALIDATION,
  });
}

/** V8: pending-review blocker lists every pending submission without truncation. */
export const V_PENDING_CANDIDATES: Candidates = {
  head: V_CANDIDATES.head,
  candidates: [vCandidate("v-s1"), vCandidate("v-s2")],
  candidate_set_digest: "sha256:v-pending-candidates",
  blockers: ["ARCHIVE_PENDING_REVIEW"],
  pending_submission_ids: ["v-s2", "v-s3"],
  pending_submission_count: 2,
} satisfies Candidates;

export function vPreviewPending(): Preview {
  return vPlan({
    candidate_set_digest: "sha256:v-pending-candidates",
    anomalies: vPreviewTwoSided().anomalies,
    business_validation: EMPTY_VALIDATION,
    blockers: ["ARCHIVE_PENDING_REVIEW"],
    audit_validity: false,
    can_start: false,
  });
}

/** V10: after closing v-s2, the bridge source is gone: v-s1 INITIAL is unexplained again. */
export function vPreviewAfterClose(): Preview {
  const source = vAnomaly({
    issue_code: "INITIAL_SOURCE_UNEXPLAINED", subject_kind: "CONFIGURATION_SOURCE",
    subject_digest: "sha256:v-source-after-close", detected_status: "UNEXPLAINED", side: "INITIAL",
    affected_submission_ids: ["v-s1"],
    details: {
      detected_status: "UNEXPLAINED",
      edges: [{ submission_id: "v-s1", candidate_digest: "sha256:v-candidate-v-s1", configuration_facts_digest: "sha256:v-facts-s1", initial: vContentDigest("s1-initial"), modified: vContentDigest("s1-modified") }],
      states: [vContentDigest("state-1")],
    },
  });
  const anomalies = [source, ...vPreviewTwoSided().anomalies.map((anomaly) => ({
    ...anomaly,
    subject_digest: `${anomaly.subject_digest}-after-close`,
  }))];
  return vPlan({
    candidate_set_digest: "sha256:v-candidates-after-close",
    anomalies,
    business_validation: vValidationFor(),
  });
}

/** V9/V10 review facts: candidate review_version equals the review version. */
export function vReviewFacts(submissionId: string): Schemas["ReviewFactsResponse"] {
  return {
    submission_id: submissionId,
    status: "APPROVED",
    review_version: V_REVIEW_VERSIONS[submissionId] ?? 11,
    updated_by: "reviewer",
    updated_at: "2026-11-07T09:00:00Z",
    identity_exception: false,
    events: [],
    submission_disposition: null,
  };
}

/** V6 history: the empty baseline plus three many-candidates as tree rows. */
export function vManyHistoryPage(): Schemas["HistoryListResponse"] {
  return {
    head: { node_id: "v-baseline-empty", commit_id: "commit-v-0", version: 0 },
    nodes: [
      {
        ref_kind: "baseline_node", ref_id: "v-baseline-empty", node_kind: "BASELINE_NODE", baseline_kind: "INITIAL",
        commit_id: "commit-v-0", created_at: "2026-11-07T08:00:00Z", parent: null,
        identity_exception: false,
      },
      ...[0, 1, 2].map((index) => ({
        ref_kind: "submission" as const, ref_id: `v-many-${index}`, node_kind: "SUBMISSION" as const,
        commit_id: `commit-v-many-${index}`, created_at: `2026-11-07T09:0${index}:00Z`,
        parent: { ref_kind: "baseline_node" as const, ref_id: "v-baseline-empty" },
        identity_exception: false, review_status: "APPROVED" as const,
      })),
    ],
    next_cursor: null,
  } satisfies Schemas["HistoryListResponse"];
}

/** Minimal workbench history: one archived baseline plus the V submissions. */
export function vHistoryPage(): Schemas["HistoryListResponse"] {
  return {
    head: { node_id: "v-baseline-7", commit_id: "commit-v-7", version: 7 },
    nodes: [
      {
        ref_kind: "baseline_node", ref_id: "v-baseline-7", node_kind: "BASELINE_NODE", baseline_kind: "ARCHIVED_SUBMISSION",
        commit_id: "commit-v-7", created_at: "2026-11-07T09:00:00Z", parent: { ref_kind: "baseline_node", ref_id: "v-baseline-0" },
        identity_exception: false,
      },
      ...V_SUBMISSIONS.map((submissionId, index) => ({
        ref_kind: "submission" as const, ref_id: submissionId, node_kind: "SUBMISSION" as const,
        commit_id: `commit-${submissionId}`, created_at: `2026-11-07T09:0${index}:00Z`,
        parent: { ref_kind: "baseline_node" as const, ref_id: "v-baseline-7" },
        identity_exception: false, review_status: "APPROVED" as const,
      })),
    ],
    next_cursor: null,
  } satisfies Schemas["HistoryListResponse"];
}
