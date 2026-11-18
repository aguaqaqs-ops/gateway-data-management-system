import { useCallback, useEffect, useState } from "react";
import type { GatewayApi } from "../../features/api/client";
import type { BrowseCommandRuntime, BrowseState } from "../../features/view-model/commands";
import {
  getUrlOperationJobKind,
  type UploadModeSnapshot,
} from "../../features/workbench/use-upload-mode";

export function usePreviewSubmitResume(
  gatewayApi: GatewayApi,
  uploadMode: UploadModeSnapshot,
  runtime: BrowseCommandRuntime,
  mode: BrowseState["mode"],
) {
  const [submitOpen, setSubmitOpen] = useState(false);
  const [resumeOperationId, setResumeOperationId] = useState<string | null>(null);
  const {
    refresh: refreshUploadSnapshot,
    resumeAfterOperation,
    retryResume,
    clearResumeNotice,
  } = uploadMode;

  const refreshUploadMode = useCallback(async () => {
    const {
      workspace: loaded,
      attempt: loadedAttempt,
      workspaceError,
    } = await refreshUploadSnapshot();
    if (workspaceError) return;
    if (loaded?.active_submit_attempt_id && loadedAttempt?.operation_id) {
      const urlOperationId = new URL(window.location.href).searchParams.get("operationId");
      if (!urlOperationId) {
        runtime.execute(
          {
            name: "set-operation",
            operationId: loadedAttempt.operation_id,
            operationKind: "operation",
          },
          "external",
        );
      } else if (urlOperationId !== loadedAttempt.operation_id) {
        // §6.2: a submit operation in the URL that disagrees with the
        // server-side pointer loses to the pointer; a preview operation in
        // the URL belongs to the preview flow and is left alone (job_kind).
        // The runtime state is updated (not just the URL) so later browse
        // commands do not restore the stale operation id.
        if ((await getUrlOperationJobKind(gatewayApi, urlOperationId)) === "backend-vnext/submit") {
          runtime.execute(
            {
              name: "set-operation",
              operationId: loadedAttempt.operation_id,
              operationKind: "operation",
            },
            "external",
          );
        }
      }
    } else {
      setResumeOperationId(null);
    }
  }, [refreshUploadSnapshot, runtime]);

  // The resume card mounts as soon as the attempt is known, without waiting
  // for the (possibly long-polling) operation read inside the same refresh.
  const resumeAttemptOperationId = uploadMode.attempt?.operation_id ?? null;
  useEffect(() => {
    if (resumeAttemptOperationId) setResumeOperationId(resumeAttemptOperationId);
  }, [resumeAttemptOperationId]);
  useEffect(() => {
    if (mode !== "PREVIEW") return;
    void refreshUploadMode();
  }, [mode, refreshUploadMode]);

  // F1: the resume notice comes from the hook snapshot (uploadMode.resumeNotice);
  // the page only clears the operation card for terminal outcomes that leave
  // no pointer behind. Retry re-runs the read sequence and re-derives the notice.
  const finishSubmitResume = useCallback(
    async (finishedOperationId: string) => {
      const outcome = await resumeAfterOperation(finishedOperationId);
      if (outcome.kind === "submitted") {
        const params = new URLSearchParams({
          page: "compare",
          mode: "REVIEW",
          submissionId: outcome.submissionId,
        });
        window.location.assign(`/?${params.toString()}`);
        return;
      }
      if (outcome.kind === "aborted" || outcome.kind === "empty") {
        setResumeOperationId(null);
      }
    },
    [resumeAfterOperation],
  );
  // G1 (§6.2 step 2): the notice retry re-runs the resume sequence from step
  // 1 via the hook entry, so both pages share one implementation and empty
  // pointers still re-read the known attempt ID.
  const retryResumeNotice = useCallback(async () => {
    const outcome = await retryResume();
    if (outcome.kind === "submitted") {
      const params = new URLSearchParams({
        page: "compare",
        mode: "REVIEW",
        submissionId: outcome.submissionId,
      });
      window.location.assign(`/?${params.toString()}`);
      return;
    }
    if (outcome.kind === "aborted" || outcome.kind === "empty") {
      setResumeOperationId(null);
    }
  }, [retryResume]);

  const openSubmit = () => {
    clearResumeNotice();
    setSubmitOpen(true);
  };

  return {
    submitOpen,
    setSubmitOpen,
    openSubmit,
    resumeOperationId,
    resumeNotice: uploadMode.resumeNotice,
    refreshUploadMode,
    finishSubmitResume,
    retryResumeNotice,
  };
}
