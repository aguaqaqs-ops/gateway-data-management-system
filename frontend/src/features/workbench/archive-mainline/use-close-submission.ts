import { useState } from "react";
import type { useBoundGatewayApi } from "../../api/application-api";
import { ApiError } from "../../api/authenticated-fetch";
import { closeError, formatReasonLimitError, utf8Length } from "../../view-model/archive-dialog";
import type { Candidate, Candidates, CloseResult, Plan, Schemas } from "./archive-types";
import type { useReasonedAction } from "./use-reasoned-action";

type GatewayApi = ReturnType<typeof useBoundGatewayApi>;
type CloseAction = ReturnType<typeof useReasonedAction<Candidate>>;

interface UseCloseSubmissionOptions {
  gatewayApi: GatewayApi;
  plan: Plan | null;
  candidates: Candidates | null;
  submissionId: string | null;
  close: CloseAction;
  reportConflict: (notice: string) => void;
  clearPlanAndLoad: (target: string) => Promise<void>;
  refresh: () => void;
  onDispositionChanged?: () => void;
}

/** Closing a candidate without archiving it: acknowledged flag, snapshot, result and retry. */
export function useCloseSubmission({
  gatewayApi,
  plan,
  candidates,
  submissionId,
  close,
  reportConflict,
  clearPlanAndLoad,
  refresh,
  onDispositionChanged,
}: UseCloseSubmissionOptions) {
  const [closeUnderstood, setCloseUnderstood] = useState(false);
  const [closeResult, setCloseResult] = useState<CloseResult | null>(null);
  const [closeSnapshot, setCloseSnapshot] = useState<{
    candidate: Candidate;
    head: Plan["head"];
    candidateSetDigest: string;
  } | null>(null);
  const [closeRetry, setCloseRetry] = useState<{ body: Schemas["CloseSubmissionRequest"] } | null>(
    null,
  );

  function openClose(candidate: Candidate) {
    if (!plan || !candidates) return;
    close.open(candidate);
    setCloseSnapshot({
      candidate,
      head: plan.head,
      candidateSetDigest: candidates.candidate_set_digest,
    });
    setCloseUnderstood(false);
    setCloseResult(null);
    setCloseRetry(null);
  }

  async function submitClose() {
    if (!close.target || !closeSnapshot || !close.key) return;
    if (
      formatReasonLimitError("close", close.reason.trim(), utf8Length(close.reason)) !==
        undefined ||
      !closeUnderstood
    )
      return;
    const body: Schemas["CloseSubmissionRequest"] = {
      expected_baseline_node_id: closeSnapshot.head.business_baseline_node_id,
      expected_baseline_head_version: closeSnapshot.head.baseline_head_version,
      expected_review_version: closeSnapshot.candidate.review_version,
      reason: close.reason,
    };
    close.setBusy(true);
    close.setError(null);
    setCloseRetry(null);
    try {
      const response = await gatewayApi.closeSubmission(
        closeSnapshot.candidate.submission_id,
        body,
        close.key,
      );
      setCloseResult(response);
      setCloseRetry(null);
      await clearPlanAndLoad(
        close.target.submission_id === submissionId
          ? close.target.submission_id
          : (submissionId ?? close.target.submission_id),
      );
      onDispositionChanged?.();
    } catch (cause) {
      if (
        cause instanceof ApiError &&
        (cause.code === "BASELINE_VERSION_CONFLICT" ||
          cause.code === "REVIEW_VERSION_CONFLICT" ||
          cause.code === "REVIEW_TRANSITION_CONFLICT" ||
          cause.code === "WORKSPACE_OCCUPANCY_CONFLICT" ||
          cause.code === "ARCHIVE_CLOSED")
      ) {
        close.setTarget(null);
        const notice =
          cause.code === "ARCHIVE_CLOSED" ? "该提交已归档或关闭" : "提交或基线已变化，已重新预检";
        reportConflict(notice);
        return;
      }
      if (cause instanceof ApiError) {
        close.setError(closeError(cause));
        return;
      }
      setCloseRetry({ body });
      close.setError({ title: "关闭请求未能送达，可以重试", code: "CLOSE_NOT_SENT" });
    } finally {
      close.setBusy(false);
    }
  }

  async function retryClose() {
    if (!close.target || !closeSnapshot || !close.key || !closeRetry) return;
    close.setBusy(true);
    close.setError(null);
    try {
      const response = await gatewayApi.closeSubmission(
        closeSnapshot.candidate.submission_id,
        closeRetry.body,
        close.key,
      );
      setCloseResult(response);
      setCloseRetry(null);
      refresh();
      onDispositionChanged?.();
    } catch (cause) {
      if (
        cause instanceof ApiError &&
        (cause.code === "BASELINE_VERSION_CONFLICT" ||
          cause.code === "REVIEW_VERSION_CONFLICT" ||
          cause.code === "REVIEW_TRANSITION_CONFLICT" ||
          cause.code === "WORKSPACE_OCCUPANCY_CONFLICT" ||
          cause.code === "ARCHIVE_CLOSED")
      ) {
        close.setTarget(null);
        const notice =
          cause.code === "ARCHIVE_CLOSED" ? "该提交已归档或关闭" : "提交或基线已变化，已重新预检";
        reportConflict(notice);
        return;
      }
      if (cause instanceof ApiError) {
        close.setError(closeError(cause));
        setCloseRetry(null);
        return;
      }
      close.setError({ title: "关闭请求未能送达，可以重试", code: "CLOSE_NOT_SENT" });
    } finally {
      close.setBusy(false);
    }
  }

  return {
    closeUnderstood,
    setCloseUnderstood,
    closeResult,
    closeRetry,
    openClose,
    submitClose,
    retryClose,
  };
}
