import { useCallback, useRef, useState } from "react";
import { ApiError } from "../../features/api/authenticated-fetch";
import type { GatewayApi } from "../../features/api/client";
import type { UploadModeSnapshot } from "../../features/workbench/use-upload-mode";

export function usePreviewWithdraw(
  gatewayApi: GatewayApi,
  uploadMode: UploadModeSnapshot,
  refreshUploadMode: () => Promise<void>,
) {
  const { workspace, review, refresh: refreshUploadSnapshot } = uploadMode;
  const [withdrawOpen, setWithdrawOpen] = useState(false);
  const [withdrawBusy, setWithdrawBusy] = useState(false);
  const [withdrawUnderstood, setWithdrawUnderstood] = useState(false);
  const [withdrawError, setWithdrawError] = useState<{ title: string; code: string } | null>(null);
  const withdrawKey = useRef<string | null>(null);

  const openWithdraw = () => {
    setWithdrawUnderstood(false);
    setWithdrawError(null);
    withdrawKey.current = crypto.randomUUID();
    setWithdrawOpen(true);
  };

  const confirmWithdraw = useCallback(async () => {
    if (!workspace?.active_submission_id || !review) return;
    setWithdrawBusy(true);
    setWithdrawError(null);
    const key = withdrawKey.current ?? crypto.randomUUID();
    withdrawKey.current = key;
    try {
      await gatewayApi.applyReview(
        workspace.active_submission_id,
        { expected_review_version: review.review_version, action: "WITHDRAW" },
        key,
      );
      const { workspace: loaded, workspaceError: refreshError } = await refreshUploadSnapshot();
      if (refreshError) {
        setWithdrawError({ title: "撤回未完成", code: refreshError.code ?? "REQUEST_FAILED" });
        return;
      }
      if (
        !loaded?.active_submission_id &&
        !loaded?.active_submit_attempt_id &&
        !loaded?.current_upload_revision_id &&
        !loaded?.current_preview_result_id
      ) {
        setWithdrawOpen(false);
        window.location.assign("/?page=workspace&notice=withdrawn");
        return;
      }
      await refreshUploadMode();
    } catch (cause) {
      if (cause instanceof ApiError) {
        const conflict = [
          "REVIEW_VERSION_CONFLICT",
          "REVIEW_TRANSITION_CONFLICT",
          "WORKSPACE_OCCUPANCY_CONFLICT",
          "ARCHIVE_CLOSED",
        ].includes(cause.code ?? "");
        if (conflict) {
          setWithdrawError({
            title: "审核状态已变化，已重新读取",
            code: cause.code ?? "REVIEW_STATE_CHANGED",
          });
          await refreshUploadMode();
        } else if (cause.status === 403) {
          setWithdrawError({
            title: "当前身份没有撤回权限",
            code: cause.code ?? "SCOPE_FORBIDDEN",
          });
        } else if (cause.status === 404) {
          setWithdrawError({
            title: "未找到该提交，请刷新后重试",
            code: cause.code ?? "RESOURCE_NOT_FOUND",
          });
        } else {
          setWithdrawError({ title: "撤回未完成", code: cause.code ?? `HTTP_${cause.status}` });
        }
        if (cause.status < 500 && cause.status !== 429) withdrawKey.current = null;
      } else {
        setWithdrawError({ title: "撤回未完成", code: "REQUEST_FAILED" });
        withdrawKey.current = null;
      }
    } finally {
      setWithdrawBusy(false);
    }
  }, [workspace, review, refreshUploadMode, refreshUploadSnapshot]);

  return {
    withdrawOpen,
    setWithdrawOpen,
    withdrawBusy,
    withdrawUnderstood,
    setWithdrawUnderstood,
    withdrawError,
    openWithdraw,
    confirmWithdraw,
  };
}
