import { describe, expect, it } from "vitest";
import {
  SIMULATED_STRING_VALUES,
  V_CANDIDATES,
  V_PENDING_CANDIDATES,
  V_REVIEW_VERSIONS,
  vAllKindsAnomalies,
  vCandidates200,
  vPreview399,
  vPreview399Accepted,
  vPreviewAcceptedSourceRevoked,
  vPreviewAfterClose,
  vPreviewAllKinds,
  vPreviewBlocked,
  vPreviewModifiedOnly,
  vPreviewPending,
  vPreviewTwoSided,
  vPreviewTwoSidedBothAccepted,
  vPreviewTwoSidedBothRevoked,
  vPreviewTwoSidedInitialRevoked,
  vPreviewUnknownCode,
  vReviewFacts,
} from "./simulated-api";

/**
 * FE3c archive-validation fixtures (kickoff §16.8–§16.9).
 * Every rule below quotes the backend source that makes the combination reachable.
 */
describe("archive validation fixtures", () => {
  it("gives every candidate a required review_version matching its review facts", () => {
    for (const candidate of V_CANDIDATES.candidates) {
      expect(candidate.review_version, candidate.submission_id).toBeGreaterThan(1);
      expect(candidate.review_version, candidate.submission_id).toBe(V_REVIEW_VERSIONS[candidate.submission_id]);
      expect(vReviewFacts(candidate.submission_id).review_version, candidate.submission_id).toBe(candidate.review_version);
    }
    const versions = V_CANDIDATES.candidates.map((candidate) => candidate.review_version);
    expect(new Set(versions).size).toBe(versions.length);
  });

  it("covers every known issue code exactly once in the V1 set", () => {
    const codes = vAllKindsAnomalies().map((anomaly) => anomaly.issue_code);
    expect([...codes].sort()).toEqual([...SIMULATED_STRING_VALUES["ArchiveAuditEventResponse.issue_code"].values].filter((code) => code !== null).sort());
  });

  it("keeps V1 items UNRESOLVED with zero sequences and empty audit facts", () => {
    for (const anomaly of vAllKindsAnomalies()) {
      expect(anomaly.resolution_status).toBe("UNRESOLVED");
      expect(anomaly.latest_sequence).toBe(0);
      expect(anomaly.accepted_by).toBeNull();
      expect(anomaly.accepted_at).toBeNull();
      expect(anomaly.reason).toBeNull();
    }
  });

  it("models source items as UNEXPLAINED and the rest as DETECTED (queries.py:424)", () => {
    for (const anomaly of vAllKindsAnomalies()) {
      expect(anomaly.detected_status).toBe(anomaly.subject_kind === "CONFIGURATION_SOURCE" ? "UNEXPLAINED" : "DETECTED");
    }
  });

  it("binds the baseline-time item to BASELINE with the full candidate set", () => {
    const baseline = vAllKindsAnomalies().find((anomaly) => anomaly.issue_code === "BASELINE_TIME_UNAVAILABLE");
    expect(baseline?.side).toBe("BASELINE");
    expect(baseline?.affected_submission_ids).toEqual(["v-s1", "v-s2", "v-s3"]);
  });

  it("keeps the two same-code same-target sides on distinct subjects (V2)", () => {
    const anomalies = vPreviewTwoSided().anomalies;
    expect(anomalies).toHaveLength(2);
    expect(anomalies[0]?.subject_digest).not.toBe(anomalies[1]?.subject_digest);
    expect(new Set(anomalies.map((anomaly) => anomaly.side)).size).toBe(2);
  });

  it("marks the unknown-code item with its raw code for the no-entry probe", () => {
    const preview = vPreviewUnknownCode();
    expect(preview.anomalies).toHaveLength(1);
    expect(preview.anomalies[0]?.issue_code).toBe("FUTURE_CODE");
  });

  it("builds exactly 399 items for 200 FULL candidates on an empty baseline (V6)", () => {
    const candidates = vCandidates200();
    expect(candidates.candidates).toHaveLength(200);
    const preview = vPreview399();
    expect(preview.anomalies).toHaveLength(399);
    expect(preview.anomalies.filter((anomaly) => anomaly.issue_code === "APPROVED_SIBLING_EXCLUDED")).toHaveLength(199);
    expect(preview.anomalies.filter((anomaly) => anomaly.issue_code === "GENERATION_TIME_MISSING")).toHaveLength(200);
    const accepted = vPreview399Accepted();
    expect(accepted.anomalies.every((anomaly) => anomaly.resolution_status === "ACCEPTED")).toBe(true);
    expect(accepted.can_start).toBe(true);
  });

  it("keeps blocked previews free of accept entries (V7)", () => {
    for (const blocker of ["ARCHIVE_INTEGRITY_FAILURE", "ACTIVE_SUBMIT_ATTEMPT"] as const) {
      const preview = vPreviewBlocked(blocker);
      expect(preview.blockers).toEqual([blocker]);
      expect(preview.anomalies).toEqual([]);
      expect(preview.can_start).toBe(false);
    }
  });

  it("lists every pending submission for the pending-review blocker (V8)", () => {
    expect(V_PENDING_CANDIDATES.blockers).toEqual(["ARCHIVE_PENDING_REVIEW"]);
    expect(V_PENDING_CANDIDATES.pending_submission_ids).toEqual(["v-s2", "v-s3"]);
    expect(V_PENDING_CANDIDATES.pending_submission_count).toBe(2);
    const preview = vPreviewPending();
    expect(preview.blockers).toEqual(["ARCHIVE_PENDING_REVIEW"]);
    expect(preview.can_start).toBe(false);
  });

  it("re-derives every subject after the close changed the candidate set (V10)", () => {
    const preview = vPreviewAfterClose();
    expect(preview.candidate_set_digest).not.toBe(V_CANDIDATES.candidate_set_digest);
    expect(preview.anomalies.every((anomaly) => anomaly.resolution_status === "UNRESOLVED")).toBe(true);
    expect(preview.anomalies.some((anomaly) => anomaly.issue_code === "INITIAL_SOURCE_UNEXPLAINED")).toBe(true);
  });

  it("keeps all V previews and candidates within the backend start rules", () => {
    for (const plan of [vPreviewAllKinds(), vPreviewTwoSided(), vPreviewPending(), vPreviewAfterClose(), vPreviewUnknownCode(), vPreview399(), vPreviewBlocked("ARCHIVE_INTEGRITY_FAILURE")]) {
      expect(plan.audit_validity, "audit_validity").toBe(false);
      expect(plan.can_start, "can_start").toBe(false);
      if (plan.selection_subject_digest) expect(plan.confirmation_requirements).toContain(plan.selection_subject_digest);
    }
  });
  it("only emits REVOKED/ACCEPTED with the §16.8 field combinations", () => {
    for (const anomaly of vPreviewTwoSidedBothAccepted().anomalies) {
      expect(anomaly.resolution_status).toBe("ACCEPTED");
      expect(anomaly.latest_sequence).toBeGreaterThan(0);
      expect(anomaly.accepted_by).toBeTruthy();
      expect(anomaly.accepted_at).toBeTruthy();
      expect(anomaly.reason).toBeTruthy();
    }
    const revoked = [
      ...vPreviewTwoSidedInitialRevoked().anomalies,
      ...vPreviewTwoSidedBothRevoked().anomalies,
      ...vPreviewAcceptedSourceRevoked().anomalies,
    ].filter((anomaly) => anomaly.resolution_status === "REVOKED");
    expect(revoked.length).toBeGreaterThanOrEqual(3);
    for (const anomaly of revoked) {
      expect(anomaly.latest_sequence).toBeGreaterThanOrEqual(2);
      expect(anomaly.accepted_by).toBeNull();
      expect(anomaly.accepted_at).toBeNull();
      expect(anomaly.reason).toBeTruthy();
    }
  });

  it("checks only the MODIFIED side for MODIFIED_ONLY uploads (§16.8)", () => {
    const preview = vPreviewModifiedOnly();
    expect(preview.anomalies).toHaveLength(1);
    expect(preview.anomalies.every((anomaly) => anomaly.side === "MODIFIED")).toBe(true);
    expect(preview.anomalies.some((anomaly) => anomaly.side === "INITIAL")).toBe(false);
  });

  it("keeps every reachable preview within the 8N+1 item bound (§16.8)", () => {
    for (const [plan, candidateCount] of [
      [vPreviewAllKinds(), 3],
      [vPreviewTwoSided(), 3],
      [vPreviewModifiedOnly(), 3],
      [vPreviewAfterClose(), 3],
      [vPreviewPending(), 2],
      [vPreview399(), 200],
    ] as const) {
      expect(plan.anomalies.length, plan.candidate_set_digest).toBeLessThanOrEqual(8 * candidateCount + 1);
    }
  });
});
