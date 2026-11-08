import { describe, expect, it } from "vitest";
import { UPLOAD_COPY, WITHDRAW_COPY, deriveUploadModeGates, type UploadModeAttempt, type UploadModeInput, type UploadModeOperation, type UploadModeWorkspace } from "./upload-header";
import type { SafeReviewFacts } from "../api/client";

function workspace(overrides: Partial<UploadModeWorkspace> = {}): UploadModeWorkspace {
  return { workspace_id: "workspace-1", active_submission_id: null, active_submit_attempt_id: null, ...overrides } as unknown as UploadModeWorkspace;
}

function review(overrides: Partial<SafeReviewFacts> = {}): SafeReviewFacts {
  return { submission_id: "submission-1", status: "PENDING", review_version: 1, submission_disposition: null, ...overrides } as unknown as SafeReviewFacts;
}

function attempt(overrides: Partial<UploadModeAttempt> = {}): UploadModeAttempt {
  return { submit_attempt_id: "attempt-1", operation_id: "operation-1", state: "EFFECT_PENDING", ...overrides } as unknown as UploadModeAttempt;
}

function operation(overrides: Partial<UploadModeOperation> = {}): UploadModeOperation {
  return { operation_id: "operation-1", status: "QUEUED", job_kind: "backend-vnext/submit", ...overrides } as unknown as UploadModeOperation;
}

function input(overrides: Partial<UploadModeInput> = {}): UploadModeInput {
  return {
    workspace: workspace(),
    workspaceError: null,
    attempt: null,
    attemptLoading: false,
    attemptError: null,
    operation: null,
    operationLoading: false,
    operationError: null,
    review: null,
    reviewLoading: false,
    reviewError: null,
    ...overrides,
  };
}

describe("deriveUploadModeGates", () => {
  it("blocks everything with the unknown reason when the workspace is unreadable", () => {
    const gates = deriveUploadModeGates(input({ workspace: null, workspaceError: { status: 500 } }));
    expect(gates.withdraw).toMatchObject({ enabled: false, reason: WITHDRAW_COPY.unknown, retry: true });
    expect(gates.submit).toMatchObject({ enabled: false, reason: UPLOAD_COPY.unknown, retry: true });
    expect(gates.upload).toMatchObject({ enabled: false, reason: UPLOAD_COPY.unknown, retry: true });
  });

  it("enables submit and upload but disables withdraw when no pointer is set", () => {
    const gates = deriveUploadModeGates(input());
    expect(gates.submit.enabled).toBe(true);
    expect(gates.upload.enabled).toBe(true);
    expect(gates.withdraw).toMatchObject({ enabled: false, reason: WITHDRAW_COPY.none });
  });

  it("enables withdraw and blocks submit/upload while a pending submission is active", () => {
    const gates = deriveUploadModeGates(input({
      workspace: workspace({ active_submission_id: "submission-1" }),
      review: review({ status: "PENDING" }),
    }));
    expect(gates.withdraw.enabled).toBe(true);
    expect(gates.submit).toMatchObject({ enabled: false, reason: UPLOAD_COPY.pending });
    expect(gates.upload).toMatchObject({ enabled: false, reason: UPLOAD_COPY.pending });
  });

  it("keeps withdraw disabled with the approval reason when the submission is approved", () => {
    const gates = deriveUploadModeGates(input({
      workspace: workspace({ active_submission_id: "submission-1" }),
      review: review({ status: "APPROVED" }),
    }));
    expect(gates.withdraw).toMatchObject({ enabled: false, reason: WITHDRAW_COPY.approved });
    expect(gates.upload).toMatchObject({ enabled: false, reason: UPLOAD_COPY.approved });
  });

  it("blocks withdraw, submit and upload while the submit operation runs", () => {
    const gates = deriveUploadModeGates(input({
      workspace: workspace({ active_submit_attempt_id: "attempt-1" }),
      attempt: attempt(),
      operation: operation({ status: "RUNNING" }),
    }));
    expect(gates.withdraw).toMatchObject({ enabled: false, reason: WITHDRAW_COPY.executing });
    expect(gates.submit).toMatchObject({ enabled: false, reason: UPLOAD_COPY.executing });
    expect(gates.upload).toMatchObject({ enabled: false, reason: UPLOAD_COPY.executing });
  });

  it("requires an administrator when the operation ended but the attempt is unfinished", () => {
    const gates = deriveUploadModeGates(input({
      workspace: workspace({ active_submit_attempt_id: "attempt-1" }),
      attempt: attempt({ state: "EFFECT_PENDING" }),
      operation: operation({ status: "SUCCEEDED" }),
    }));
    expect(gates.withdraw).toMatchObject({ enabled: false, reason: WITHDRAW_COPY.recovery });
    expect(gates.upload.enabled).toBe(false);
  });

  it("offers a retry when the attempt or operation cannot be read", () => {
    const gates = deriveUploadModeGates(input({
      workspace: workspace({ active_submit_attempt_id: "attempt-1" }),
      attemptError: { status: 500 },
    }));
    expect(gates.withdraw).toMatchObject({ enabled: false, reason: WITHDRAW_COPY.unknown, retry: true });
    expect(gates.submit).toMatchObject({ enabled: false, reason: UPLOAD_COPY.unknown, retry: true });
  });

  it("shows the permission reason for withdraw and the in-review reason for upload on 403", () => {
    const gates = deriveUploadModeGates(input({
      workspace: workspace({ active_submission_id: "submission-1" }),
      reviewError: { status: 403, code: "SCOPE_FORBIDDEN" },
    }));
    expect(gates.withdraw).toMatchObject({ enabled: false, reason: WITHDRAW_COPY.forbidden });
    expect(gates.upload).toMatchObject({ enabled: false, reason: UPLOAD_COPY.inReview });
  });

  it("prioritizes the archived disposition and asks for a re-read", () => {
    const gates = deriveUploadModeGates(input({
      workspace: workspace({ active_submission_id: "submission-1" }),
      review: review({ status: "APPROVED", submission_disposition: { disposition: "ARCHIVED_BASELINE", source_kind: "ARCHIVE", submission_id: "submission-1", result_id: "result-1", closure: null } }),
    }));
    expect(gates.withdraw).toMatchObject({ enabled: false, reason: WITHDRAW_COPY.archived, reread: true });
    expect(gates.submit).toMatchObject({ enabled: false, reason: WITHDRAW_COPY.archived, reread: true });
  });

  it("uses the closed-without-archive copy for manual closes", () => {
    const gates = deriveUploadModeGates(input({
      workspace: workspace({ active_submission_id: "submission-1" }),
      review: review({ status: "APPROVED", submission_disposition: { disposition: "CLOSED_NOT_ARCHIVED", source_kind: "MANUAL_CLOSE", submission_id: "submission-1", result_id: null, closure: { closed_by: "actor-1", closed_at: "2026-11-08T00:00:00Z", reason: "不再需要" } } }),
    }));
    expect(gates.withdraw).toMatchObject({ enabled: false, reason: WITHDRAW_COPY.closed, reread: true });
    expect(gates.upload).toMatchObject({ enabled: false, reason: WITHDRAW_COPY.closed, reread: true });
  });

  it("asks for a re-read when review facts report a terminal status", () => {
    const gates = deriveUploadModeGates(input({
      workspace: workspace({ active_submission_id: "submission-1" }),
      review: review({ status: "WITHDRAWN" }),
    }));
    expect(gates.withdraw).toMatchObject({ enabled: false, reason: WITHDRAW_COPY.withdrawn, reread: true });
  });
});
