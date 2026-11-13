import type { useBoundGatewayApi } from "../../api/application-api";
import { ApiError } from "../../api/authenticated-fetch";
import { buildArchiveSelectedRef } from "../../api/journeys";
import {
  anomalyAction,
  formatReasonLimitError,
  resolutionError,
  utf8Length,
} from "../../view-model/archive-dialog";
import type { Anomaly, Candidates, Plan } from "./archive-types";
import type { useReasonedAction } from "./use-reasoned-action";

type GatewayApi = ReturnType<typeof useBoundGatewayApi>;
type AcceptAction = ReturnType<typeof useReasonedAction<Anomaly>>;
type RevokeAction = ReturnType<typeof useReasonedAction<Anomaly>>;

interface UseAnomalyResolutionOptions {
  gatewayApi: GatewayApi;
  plan: Plan | null;
  candidates: Candidates | null;
  submissionId: string | null;
  selectedDigest: string | null;
  accept: AcceptAction;
  revoke: RevokeAction;
  reportConflict: (notice: string) => void;
  refresh: () => void;
}

/** Shared submission path for accepting and revoking an anomaly resolution. */
export function useAnomalyResolution({
  gatewayApi,
  plan,
  candidates,
  submissionId,
  selectedDigest,
  accept,
  revoke,
  reportConflict,
  refresh,
}: UseAnomalyResolutionOptions) {
  async function submitResolution(kind: "accept" | "revoke") {
    const target = kind === "accept" ? accept.target : revoke.target;
    const reason = kind === "accept" ? accept.reason : revoke.reason;
    const key = kind === "accept" ? accept.key : revoke.key;
    if (!plan || !candidates || !target || !submissionId || !selectedDigest || !key) return;
    if (formatReasonLimitError(kind, reason.trim(), utf8Length(reason)) !== undefined) return;
    const setBusy = kind === "accept" ? accept.setBusy : revoke.setBusy;
    const setError = kind === "accept" ? accept.setError : revoke.setError;
    setBusy(true);
    setError(null);
    try {
      await gatewayApi.appendArchiveAnomalyResolution(
        {
          expected_baseline_node_id: plan.head.business_baseline_node_id,
          expected_baseline_head_version: plan.head.baseline_head_version,
          candidate_set_digest: plan.candidate_set_digest,
          selected: buildArchiveSelectedRef({
            submission_id: submissionId,
            expected_candidate_digest: selectedDigest,
          }),
          subject_digest: target.subject_digest,
          subject_kind: target.subject_kind,
          issue_code: target.issue_code,
          target_submission_id: target.target_submission_id,
          target_candidate_digest: target.target_candidate_digest,
          expected_sequence: target.latest_sequence,
          action: kind === "accept" ? anomalyAction(target) : "REVOKE",
          reason,
        },
        key,
      );
      if (kind === "accept") accept.setTarget(null);
      else revoke.setTarget(null);
      refresh();
    } catch (cause) {
      if (
        cause instanceof ApiError &&
        (cause.code === "BASELINE_VERSION_CONFLICT" ||
          cause.code === "CANDIDATE_SET_CONFLICT" ||
          cause.code === "CANDIDATE_BINDING_CONFLICT" ||
          cause.code === "ARCHIVE_AUDIT_VERSION_CONFLICT")
      ) {
        if (kind === "accept") accept.setTarget(null);
        else revoke.setTarget(null);
        reportConflict("归档候选或核验结果已变化，已重新预检");
        return;
      }
      setError(resolutionError(cause));
    } finally {
      setBusy(false);
    }
  }

  return { submitResolution };
}
