import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { gatewayApi } from "../api/application-api";
import { currentGatewaySession } from "../api/session";
import { deriveUploadModeGates, type Problem, type UploadModeAttempt, type UploadModeGates, type UploadModeOperation, type UploadModeWorkspace } from "./upload-header";
import type { SafeReviewFacts } from "../api/client";

function problemFrom(cause: unknown): Problem {
  if (cause && typeof cause === "object" && "status" in cause) {
    const status = (cause as { status?: unknown }).status;
    const code = (cause as { code?: unknown }).code;
    return {
      status: typeof status === "number" ? status : null,
      code: typeof code === "string" ? code : null,
    };
  }
  return { status: null, code: cause instanceof Error ? cause.name : null };
}

export type ResumeOutcome =
  | { kind: "submitted"; submissionId: string }
  | { kind: "aborted"; abortCode: string | null }
  | { kind: "unfinished"; operationId: string }
  | { kind: "empty" }
  | { kind: "unknown" };

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
  /** Re-runs the full workspace → review/attempt → operation read sequence. */
  refresh: () => Promise<{ workspace: UploadModeWorkspace | null; attempt: UploadModeAttempt | null }>;
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
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
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

  const inflight = useRef<Promise<{ workspace: UploadModeWorkspace | null; attempt: UploadModeAttempt | null }> | null>(null);
  const attemptIdRef = useRef<string | null>(null);
  const workspaceRef = useRef<UploadModeWorkspace | null>(null);
  workspaceRef.current = workspace;
  const rereadConsumed = useRef<string | null>(null);

  const readReview = useCallback(async (submissionId: string) => {
    setReviewLoading(true);
    setReviewProblem(null);
    try {
      const facts = await gatewayApi.getReviewFacts(submissionId);
      setReview(facts);
      setReviewProblem(null);
    } catch (cause) {
      setReview(null);
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
          setOperation(null);
          setOperationProblem(problemFrom(cause));
        }
      } else {
        setOperation(null);
        setOperationProblem(null);
      }
      return loadedAttempt;
    } catch (cause) {
      setAttempt(null);
      setAttemptProblem(problemFrom(cause));
      setOperation(null);
      setOperationProblem(null);
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
          return { workspace: loaded, attempt: loadedAttempt };
        }
        clearAttemptChain();
        return { workspace: loaded, attempt: null };
      } catch (cause) {
        setWorkspace(null);
        setWorkspaceProblem(problemFrom(cause));
        return { workspace: null, attempt: null };
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
        setWorkspace(null);
        setWorkspaceProblem(problemFrom(cause));
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
        return { kind: "empty" };
      }
      const loadedAttempt = await readAttemptChain(loaded.workspace_id, attemptId);
      setReview(null);
      setReviewProblem(null);
      setReviewLoading(false);
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

  return {
    workspace,
    workspaceLoading,
    workspaceProblem,
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
