import type { components } from "../api/generated/openapi";
import type { SafeReviewFacts } from "../api/client";

type Schemas = components["schemas"];

export type UploadModeWorkspace = Schemas["WorkspaceResponse"];
export type UploadModeAttempt = Schemas["SubmitAttemptResponse"];
export type UploadModeOperation = Schemas["OperationResponse"];

export interface Problem {
  code?: string | null;
  status?: number | null;
}

export interface UploadModeInput {
  workspace: UploadModeWorkspace | null;
  /** True while the first workspace read for this snapshot has not completed. */
  workspaceLoading: boolean;
  workspaceError: Problem | null;
  attempt: UploadModeAttempt | null;
  attemptLoading: boolean;
  attemptError: Problem | null;
  operation: UploadModeOperation | null;
  operationLoading: boolean;
  operationError: Problem | null;
  review: SafeReviewFacts | null;
  reviewLoading: boolean;
  reviewError: Problem | null;
}

export interface Gate {
  enabled: boolean;
  reason?: string;
  /** The page should re-read the workspace once before acting. */
  reread?: boolean;
  /** The caller may offer a retry that restarts the read sequence. */
  retry?: boolean;
  /**
   * G2 (§6.1): the 404 row labels its retry affordance "刷新" while the other
   * retry rows keep "重试读取". The behavior is the same re-read sequence.
   */
  retryLabel?: "刷新" | "重试读取";
}

export interface UploadModeGates {
  withdraw: Gate;
  submit: Gate;
  upload: Gate;
}

export const WITHDRAW_COPY = {
  executing: "提交正在执行，完成后才能撤回",
  recovery: "提交结果待确认，需要管理员处理",
  unknown: "无法确认提交状态",
  loading: "正在读取提交状态",
  none: "当前没有待审核的提交",
  reading: "正在读取审核状态",
  forbidden: "当前身份没有撤回权限",
  notFound: "未找到该提交，请刷新后重试",
  failed: "无法读取审核状态",
  archived: "该提交已归档",
  closed: "该提交已关闭（未归档）",
  approved: "该提交已通过审核，不能撤回",
  rejected: "该提交已退回",
  withdrawn: "该提交已撤回",
} as const;

export const UPLOAD_COPY = {
  executing: "提交正在执行，完成后才能继续",
  recovery: "提交结果待确认，需要管理员处理",
  unknown: "无法确认提交状态",
  loading: "正在读取提交状态",
  pending: "已有待审核的提交，撤回后才能重新上传",
  approved: "该提交已通过审核，归档或关闭后才能重新上传",
  inReview: "已有提交在处理中，完成后才能重新上传",
  archived: "该提交已归档",
  closed: "该提交已关闭（未归档）",
  changed: "提交状态已变化",
} as const;

/** Backend OperationStatus terminal values (operations/contracts.py). ABORTED is an attempt state, not an operation state. */
const TERMINAL = new Set(["SUCCEEDED", "FAILED", "CANCELLED", "SUPERSEDED"]);
const ATTEMPT_CLOSED = new Set(["FINALIZED", "ABORTED"]);

type AttemptPhase = "none" | "executing" | "recovery" | "unknown" | "loading" | "stale";

function attemptPhase(input: UploadModeInput): AttemptPhase {
  if (!input.workspace?.active_submit_attempt_id) return "none";
  // A closed attempt behind a still-set attempt pointer means the workspace
  // snapshot is stale (F2): the submit finished after the workspace was read.
  // Never unlock on this snapshot; treat it like an unreadable snapshot with
  // a one-time re-read instead of judging by the submission pointer.
  if (input.attempt && ATTEMPT_CLOSED.has(input.attempt.state)) return "stale";
  if (input.attemptError || input.operationError) return "unknown";
  if (!input.attempt) return input.attemptLoading ? "loading" : "unknown";
  const status = input.operation?.status ?? null;
  if (status === null) {
    if (input.operationError) return "unknown";
    // The attempt is known but its operation is still being read: the submit
    // is still in flight, same as an explicit QUEUED/RUNNING status.
    return "executing";
  }
  if (status === "QUEUED" || status === "RUNNING") return "executing";
  if (status === "MANUAL_RECOVERY_REQUIRED") return "recovery";
  if (TERMINAL.has(status)) return "recovery";
  return "executing";
}

function loadingGate(copy: { loading: string }): Gate {
  return { enabled: false, reason: copy.loading };
}

function attemptGate(input: UploadModeInput, mode: "withdraw" | "upload"): Gate {
  const copy = mode === "withdraw" ? WITHDRAW_COPY : UPLOAD_COPY;
  switch (attemptPhase(input)) {
    case "loading":
      return loadingGate(copy);
    case "stale":
      return { enabled: false, reason: copy.unknown, retry: true, reread: true, retryLabel: "重试读取" };
    case "unknown":
      return { enabled: false, reason: copy.unknown, retry: true, retryLabel: "重试读取" };
    case "recovery":
      return { enabled: false, reason: copy.recovery };
    default:
      return { enabled: false, reason: copy.executing };
  }
}

function submissionGate(input: UploadModeInput, mode: "withdraw" | "upload"): Gate | null {
  if (!input.workspace?.active_submission_id) return null;
  if (input.reviewLoading) return { enabled: false, reason: WITHDRAW_COPY.reading };
  if (input.reviewError) {
    const status = input.reviewError.status ?? null;
    if (mode === "withdraw" && status === 403) return { enabled: false, reason: WITHDRAW_COPY.forbidden };
    if (mode === "withdraw" && status === 404) return { enabled: false, reason: WITHDRAW_COPY.notFound, retry: true, retryLabel: "刷新" };
    if (mode === "upload") return { enabled: false, reason: UPLOAD_COPY.inReview };
    return { enabled: false, reason: WITHDRAW_COPY.failed, retry: true, retryLabel: "重试读取" };
  }
  const disposition = input.review?.submission_disposition ?? null;
  if (disposition) {
    return {
      enabled: false,
      reason: disposition.disposition === "ARCHIVED_BASELINE" ? WITHDRAW_COPY.archived : WITHDRAW_COPY.closed,
      reread: true,
    };
  }
  switch (input.review?.status ?? null) {
    case "PENDING":
      return mode === "withdraw" ? { enabled: true } : { enabled: false, reason: UPLOAD_COPY.pending };
    case "APPROVED":
      return { enabled: false, reason: mode === "withdraw" ? WITHDRAW_COPY.approved : UPLOAD_COPY.approved };
    case "REJECTED":
      return { enabled: false, reason: WITHDRAW_COPY.rejected, reread: true };
    case "WITHDRAWN":
      return { enabled: false, reason: WITHDRAW_COPY.withdrawn, reread: true };
    default:
      return { enabled: false, reason: mode === "withdraw" ? WITHDRAW_COPY.failed : UPLOAD_COPY.inReview };
  }
}

/**
 * Derives the upload-mode header controls (withdraw, submit, upload) from the
 * workspace pointers, the submit attempt/operation and the review facts.
 * See kickoff §6.1: every pointer non-null blocks submit and upload; the
 * withdraw button is always visible but disabled with a reason.
 *
 * Loading and unreadable are distinct: while the first workspace read is in
 * flight the gates report "loading" without a retry affordance; only a
 * completed read that failed reports "unknown" with a retry.
 */
export function deriveUploadModeGates(input: UploadModeInput): UploadModeGates {
  if (input.workspaceLoading && !input.workspace && !input.workspaceError) {
    return {
      withdraw: loadingGate(WITHDRAW_COPY),
      submit: loadingGate(UPLOAD_COPY),
      upload: loadingGate(UPLOAD_COPY),
    };
  }
  if (!input.workspace || input.workspaceError) {
    return {
      withdraw: { enabled: false, reason: WITHDRAW_COPY.unknown, retry: true, retryLabel: "重试读取" },
      submit: { enabled: false, reason: UPLOAD_COPY.unknown, retry: true, retryLabel: "重试读取" },
      upload: { enabled: false, reason: UPLOAD_COPY.unknown, retry: true, retryLabel: "重试读取" },
    };
  }

  if (attemptPhase(input) !== "none") {
    return {
      withdraw: attemptGate(input, "withdraw"),
      submit: attemptGate(input, "upload"),
      upload: attemptGate(input, "upload"),
    };
  }

  const withdraw = submissionGate(input, "withdraw") ?? { enabled: false, reason: WITHDRAW_COPY.none };
  const upload = submissionGate(input, "upload") ?? { enabled: true };
  return {
    withdraw,
    submit: upload.enabled ? { enabled: true } : { ...upload },
    upload,
  };
}
