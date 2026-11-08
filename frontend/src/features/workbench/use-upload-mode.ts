import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { gatewayApi } from "../api/application-api";
import { ApiError } from "../api/authenticated-fetch";
import { currentGatewaySession } from "../api/session";
import { deriveUploadModeGates, type Problem, type UploadModeAttempt, type UploadModeGates, type UploadModeOperation, type UploadModeWorkspace } from "./upload-header";
import type { SafeReviewFacts } from "../api/client";

function problemFrom(cause: unknown): Problem {
  if (cause instanceof ApiError) {
    return { status: cause.status, code: cause.code ?? null };
  }
  return { status: null, code: cause instanceof Error ? cause.name : null };
}

export interface RefreshResult {
  workspace: UploadModeWorkspace | null;
  attempt: UploadModeAttempt | null;
  /** Set when the workspace read itself failed (never thrown). */
  workspaceError: { code: string; message: string } | null;
}

function errorFrom(cause: unknown): { code: string; message: string } {
  if (cause instanceof ApiError) {
    return { code: cause.code ?? `HTTP_${cause.status}`, message: cause.message };
  }
  return {
    code: cause instanceof Error ? cause.name : "REQUEST_FAILED",
    message: cause instanceof Error ? cause.message : String(cause),
  };
}

export type ResumeOutcome =
  | { kind: "submitted"; submissionId: string }
  | { kind: "aborted"; abortCode: string | null }
  | { kind: "unfinished"; operationId: string }
  | { kind: "empty" }
  | { kind: "unknown" };

/**
 * F1: the resume notice derives from the same snapshot as the gates (§6.2
 * steps 1-3). The pages render it without keeping their own copy, so the
 * prompt and the submit/upload disabled reasons can never disagree.
 */
export interface ResumeNotice {
  title: string;
  code: string | null;
  /** How to label the code: the submit operation ID or the backend abort code. */
  codeLabel: "操作ID" | "原始代码" | null;
}

export interface UploadModeSnapshot {
  workspace: UploadModeWorkspace | null;
  workspaceLoading: boolean;
  workspaceProblem: Problem | null;
  review: SafeReviewFacts | null;
  reviewLoading: boolean;
  reviewProblem: Problem | null;
  attempt: UploadModeAttempt | null;
  attemptLoading: boolean;
  attemptProblem: Problem | null;
  operation: UploadModeOperation | null;
  operationLoading: boolean;
  operationProblem: Problem | null;
  gates: UploadModeGates;
  /** F1 resume notice derived from the same snapshot as the gates; null before any resume. */
  resumeNotice: ResumeNotice | null;
  /** Re-runs the full workspace → review/attempt → operation read sequence. */
  refresh: () => Promise<RefreshResult>;
  /**
   * B3: after a submit operation reaches a terminal state, re-reads the
   * workspace and — using the known attempt ID — the attempt (for abort_code)
   * and its operation, updating every held state and read error together so
   * the gates and the resume notice derive from the same snapshot.
   */
  resumeAfterOperation: (finishedOperationId: string) => Promise<ResumeOutcome>;
}

/**
 * Reads the workspace, the review facts, the submit attempt and its operation
 * for the upload-mode gates (kickoff §6.1/§6.2). Both the Preview page and the
 * workbench consume this hook so the occupancy rules cannot drift apart.
 *
 * B2: when the gates ask for a re-read (stale disposition or terminal review
 * status), the hook re-reads the workspace exactly once per stale snapshot
 * before reporting the terminal reason.
 */
export function useUploadModeState(options: { enabled: boolean }): UploadModeSnapshot {
  const { enabled } = options;
  const [workspace, setWorkspace] = useState<UploadModeWorkspace | null>(null);
  // N1: start loading so the first frame reports "reading" instead of flashing
  // "unknown" before the mount read runs. A disabled hook never renders gates.
  const [workspaceLoading, setWorkspaceLoading] = useState(true);
  const [workspaceProblem, setWorkspaceProblem] = useState<Problem | null>(null);
  const [review, setReview] = useState<SafeReviewFacts | null>(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewProblem, setReviewProblem] = useState<Problem | null>(null);
  const [attempt, setAttempt] = useState<UploadModeAttempt | null>(null);
  const [attemptLoading, setAttemptLoading] = useState(false);
  const [attemptProblem, setAttemptProblem] = useState<Problem | null>(null);
  const [operation, setOperation] = useState<UploadModeOperation | null>(null);
  const [operationLoading, setOperationLoading] = useState(false);
  const [operationProblem, setOperationProblem] = useState<Problem | null>(null);

  // F1: counts completed resumes; the notice below only appears after a resume.
  const [resumeSeq, setResumeSeq] = useState(0);
  const inflight = useRef<Promise<RefreshResult> | null>(null);
  const attemptIdRef = useRef<string | null>(null);
  const workspaceRef = useRef<UploadModeWorkspace | null>(null);
  workspaceRef.current = workspace;
  const rereadConsumed = useRef<string | null>(null);

  // A failed re-read keeps the last known snapshot and only records the
  // problem: the gates already report "unknown" from the problem, and the
  // pages must not flash to an error page (or unmount the resume card)
  // while stale data is still on screen.
  const readReview = useCallback(async (submissionId: string) => {
    setReviewLoading(true);
    setReviewProblem(null);
    try {
      const facts = await gatewayApi.getReviewFacts(submissionId);
      setReview(facts);
      setReviewProblem(null);
    } catch (cause) {
      setReviewProblem(problemFrom(cause));
    } finally {
      setReviewLoading(false);
    }
  }, []);

  const readAttemptChain = useCallback(async (workspaceId: string, attemptId: string) => {
    setAttemptLoading(true);
    setOperationLoading(true);
    setAttemptProblem(null);
    setOperationProblem(null);
    try {
      const loadedAttempt = await gatewayApi.getSubmitAttempt(workspaceId, attemptId);
      setAttempt(loadedAttempt);
      setAttemptProblem(null);
      attemptIdRef.current = loadedAttempt.submit_attempt_id;
      if (loadedAttempt.operation_id) {
        try {
          const loadedOperation = await gatewayApi.getOperation(loadedAttempt.operation_id);
          setOperation(loadedOperation);
          setOperationProblem(null);
        } catch (cause) {
          setOperationProblem(problemFrom(cause));
        }
      } else {
        setOperation(null);
        setOperationProblem(null);
      }
      return loadedAttempt;
    } catch (cause) {
      setAttemptProblem(problemFrom(cause));
      return null;
    } finally {
      setAttemptLoading(false);
      setOperationLoading(false);
    }
  }, []);

  const clearAttemptChain = useCallback(() => {
    setAttempt(null);
    setAttemptProblem(null);
    setAttemptLoading(false);
    setOperation(null);
    setOperationProblem(null);
    setOperationLoading(false);
    attemptIdRef.current = null;
  }, []);

  const refresh = useCallback(async () => {
    if (inflight.current) return inflight.current;
    const run = (async () => {
      setWorkspaceLoading(true);
      setWorkspaceProblem(null);
      try {
        const session = currentGatewaySession();
        const loaded = await gatewayApi.createWorkspace({
          business_project_id: session.businessProjectId,
          gateway_device_external_key: session.gatewayDeviceExternalKey,
        });
        setWorkspace(loaded);
        setWorkspaceProblem(null);
        if (loaded.active_submission_id) {
          await readReview(loaded.active_submission_id);
        } else {
          setReview(null);
          setReviewProblem(null);
          setReviewLoading(false);
        }
        if (loaded.active_submit_attempt_id) {
          attemptIdRef.current = loaded.active_submit_attempt_id;
          const loadedAttempt = await readAttemptChain(loaded.workspace_id, loaded.active_submit_attempt_id);
          return { workspace: loaded, attempt: loadedAttempt, workspaceError: null };
        }
        clearAttemptChain();
        return { workspace: loaded, attempt: null, workspaceError: null };
      } catch (cause) {
        // Keep the last known workspace; only the problem is new. Callers
        // that need a hard failure (page-level load, reload-head) check
        // the returned workspaceError.
        setWorkspaceProblem(problemFrom(cause));
        return { workspace: workspaceRef.current, attempt: null, workspaceError: errorFrom(cause) };
      } finally {
        setWorkspaceLoading(false);
        inflight.current = null;
      }
    })();
    inflight.current = run;
    return run;
  }, [clearAttemptChain, readAttemptChain, readReview]);

  useEffect(() => {
    if (!enabled) return;
    // Like the old page-level loads, the mount read waits for an identity:
    // the simulated identity arrives lazily and publishes a session-change
    // event, which the pages use to trigger their load. Fetching without a
    // session would send an unauthenticated first request.
    const session = currentGatewaySession();
    if (!session.businessProjectId || !session.gatewayDeviceExternalKey) return;
    void refresh();
  }, [enabled, refresh]);

  const gates = useMemo(() => deriveUploadModeGates({
    workspace,
    workspaceLoading,
    workspaceError: workspaceProblem,
    attempt,
    attemptLoading,
    attemptError: attemptProblem,
    operation,
    operationLoading,
    operationError: operationProblem,
    review,
    reviewLoading,
    reviewError: reviewProblem,
  }), [workspace, workspaceLoading, workspaceProblem, attempt, attemptLoading, attemptProblem,
    operation, operationLoading, operationProblem, review, reviewLoading, reviewProblem]);

  // B2: one re-read per stale snapshot, never a loop. The key pins the exact
  // stale content; a refresh that leaves the same content behind is consumed.
  const rereadKey = gates.withdraw.reread || gates.submit.reread || gates.upload.reread
    ? [
      workspace?.workspace_id ?? "",
      workspace?.active_submission_id ?? "",
      workspace?.active_submit_attempt_id ?? "",
      review?.status ?? "",
      review?.submission_disposition?.disposition ?? "",
      attempt?.state ?? "",
    ].join("|")
    : null;
  useEffect(() => {
    if (!enabled || !rereadKey) return;
    if (rereadConsumed.current === rereadKey) return;
    rereadConsumed.current = rereadKey;
    void refresh();
  }, [enabled, rereadKey, refresh]);

  const resumeAfterOperation = useCallback(async (finishedOperationId: string): Promise<ResumeOutcome> => {
    void finishedOperationId;
    setWorkspaceLoading(true);
    setAttemptLoading(true);
    setOperationLoading(true);
    try {
      const session = currentGatewaySession();
      let loaded: UploadModeWorkspace;
      try {
        loaded = await gatewayApi.createWorkspace({
          business_project_id: session.businessProjectId,
          gateway_device_external_key: session.gatewayDeviceExternalKey,
        });
        setWorkspace(loaded);
        setWorkspaceProblem(null);
      } catch (cause) {
        setWorkspaceProblem(problemFrom(cause));
        setResumeSeq((seq) => seq + 1);
        return { kind: "unknown" };
      }
      // The known attempt ID survives the pointer being cleared (ABORTED), so
      // prefer the previously seen ID over the fresh pointers.
      const attemptId = loaded.active_submit_attempt_id ?? attemptIdRef.current;
      if (loaded.active_submission_id) {
        await readReview(loaded.active_submission_id);
        clearAttemptChain();
        return { kind: "submitted", submissionId: loaded.active_submission_id };
      }
      if (!attemptId) {
        setReview(null);
        setReviewProblem(null);
        setReviewLoading(false);
        clearAttemptChain();
        setResumeSeq((seq) => seq + 1);
        return { kind: "empty" };
      }
      const loadedAttempt = await readAttemptChain(loaded.workspace_id, attemptId);
      setReview(null);
      setReviewProblem(null);
      setReviewLoading(false);
      setResumeSeq((seq) => seq + 1);
      if (!loadedAttempt) return { kind: "unknown" };
      if (loadedAttempt.state === "ABORTED") {
        return { kind: "aborted", abortCode: loadedAttempt.abort_code ?? null };
      }
      return { kind: "unfinished", operationId: loadedAttempt.operation_id ?? "" };
    } finally {
      setWorkspaceLoading(false);
      setAttemptLoading(false);
      setOperationLoading(false);
    }
  }, [clearAttemptChain, readAttemptChain, readReview]);

  // F1: the resume notice and the gates come from this same snapshot (§6.2).
  // ABORTED (pointers cleared, attempt readable) keeps the unfinished-submit
  // copy with the backend abort code. Cleared pointers with an unreadable
  // attempt keep the buttons available with the unreadable-result copy.
  // A readable attempt pointer follows the §6.1 gate reason. Anything else
  // unreadable reports the unknown copy; retry restarts from step 1.
  const resumeNotice = useMemo<ResumeNotice | null>(() => {
    if (resumeSeq === 0) return null;
    if (!workspace || workspaceProblem) {
      return { title: "无法确认提交状态", code: null, codeLabel: null };
    }
    if (workspace.active_submit_attempt_id) {
      if (!attempt || attemptProblem || operationProblem) {
        return { title: "无法确认提交状态", code: null, codeLabel: null };
      }
      if (attempt.state === "ABORTED") {
        return { title: "提交未完成，请检查上传与 Preview 后重试", code: attempt.abort_code ?? null, codeLabel: "原始代码" };
      }
      return { title: gates.submit.reason ?? "无法确认提交状态", code: attempt.operation_id ?? null, codeLabel: "操作ID" };
    }
    if (workspace.active_submission_id) {
      return { title: gates.submit.reason ?? "无法确认提交状态", code: null, codeLabel: null };
    }
    if (attempt && attempt.state === "ABORTED") {
      return { title: "提交未完成，请检查上传与 Preview 后重试", code: attempt.abort_code ?? null, codeLabel: "原始代码" };
    }
    if (attemptProblem) {
      return { title: "无法读取提交结果，请刷新后重试", code: null, codeLabel: null };
    }
    return { title: "提交未完成，请检查上传与 Preview 后重试", code: null, codeLabel: null };
  }, [resumeSeq, workspace, workspaceProblem, attempt, attemptProblem, operationProblem, gates.submit.reason]);

  return {
    workspace,
    workspaceLoading,
    workspaceProblem,
    resumeNotice,
    review,
    reviewLoading,
    reviewProblem,
    attempt,
    attemptLoading,
    attemptProblem,
    operation,
    operationLoading,
    operationProblem,
    gates,
    refresh,
    resumeAfterOperation,
  };
}

/**
 * B8/job_kind: resolves the job_kind of the operation referenced by the URL so
 * the pages can tell a submit operation from a preview operation (§6.2).
 * Returns null when the operation cannot be read.
 */
export async function getUrlOperationJobKind(operationId: string): Promise<string | null> {
  try {
    const loaded = await gatewayApi.getOperation(operationId);
    return loaded.job_kind ?? null;
  } catch {
    return null;
  }
}
