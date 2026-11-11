import { useEffect, useId, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { ApiError } from "../api/authenticated-fetch";
import { applyReviewAction } from "../api/journeys";
import { gatewayApi } from "../api/application-api";
import type { SafeReviewFacts } from "../api/client";
import { Button, Dialog } from "../../design-system/components";
type DialogKind = "approve" | "reject" | "withdraw";

const STALE_ON_FACTS_REFRESH = new Set(["REVIEW_VERSION_CONFLICT", "IDEMPOTENCY_CONFLICT"]);

const STATUS_REASON: Record<string, string> = {
  APPROVED: "该提交已通过审核",
  REJECTED: "该提交已退回",
  WITHDRAWN: "该提交已撤回",
};

function actionError(cause: unknown, dialog: DialogKind | null): { title: string; code: string; expiredApprove: boolean; closed: boolean } {
  const base = { expiredApprove: false, closed: false };
  if (cause instanceof ApiError) {
    if (cause.code === "ARCHIVE_CLOSED") {
      return { title: "该提交已归档或关闭，已重新读取", code: "ARCHIVE_CLOSED", expiredApprove: false, closed: true };
    }
    if (cause.code === "BASELINE_VERSION_CONFLICT" && dialog === "approve") {
      return { title: "该提交所基于的基线已更新，不能通过。可以退回，或由提交人撤回后基于当前基线重新提交。", code: "BASELINE_VERSION_CONFLICT", expiredApprove: true, closed: false };
    }
    if (cause.code === "SCOPE_FORBIDDEN") return { title: "当前身份没有该操作的权限", code: "SCOPE_FORBIDDEN", ...base };
    if (cause.code === "REVIEW_VERSION_CONFLICT") return { title: "数据已被更新，请刷新审核信息后重试", code: cause.code, ...base };
    if (cause.code === "IDEMPOTENCY_CONFLICT") return { title: "本次审核与服务器记录不一致，请刷新后重试", code: cause.code, ...base };
    return { title: cause.message || "审核操作失败", code: cause.code ?? "REVIEW_FAILED", ...base };
  }
  return { title: cause instanceof Error ? cause.message : "审核操作失败", code: "REVIEW_FAILED", ...base };
}

interface ReviewActionsProps {
  submissionId: string;
  facts: SafeReviewFacts;
  bundleReady: boolean;
  onFactsChanged: (facts: SafeReviewFacts) => void;
  /**
   * C5: invoked after the facts refresh that follows a terminal action or a
   * 409 conflict, so the page re-reads the review and the History together
   * instead of the review alone.
   */
  onReviewSettled?: () => void;
  /**
   * C12 rule 1: the top-bar error notice lives below the header main row, not
   * inside the button row, so it cannot widen the row or move the buttons.
   */
  errorNoticeHost?: RefObject<HTMLElement | null>;
}

export function ReviewActions({ submissionId, facts, bundleReady, onFactsChanged, onReviewSettled, errorNoticeHost }: ReviewActionsProps) {
  const generatedId = useId();
  const [dialog, setDialog] = useState<DialogKind | null>(null);
  const [reason, setReason] = useState("");
  const [understood, setUnderstood] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ title: string; code: string } | null>(null);
  const [expiredApprove, setExpiredApprove] = useState(false);
  const dialogKey = useRef<string | null>(null);
  // C12 rule 5: a refresh that advances the Review state must not silently
  // drop the ARCHIVE_CLOSED notice ("已重新读取"); only switching submissions
  // clears it. Ordinary conflicts still refresh through refreshFacts().
  useEffect(() => {
    setExpiredApprove(false);
    setError(null);
  }, [submissionId]);
  useEffect(() => {
    setExpiredApprove(false);
  }, [facts.review_version, facts.status]);
  // N17: a REVIEW reload from another path (for example the bundle or table
  // reload) can make a previously reported conflict stale. Only the conflict
  // notices are superseded by fresher facts; terminal and closed notices
  // ("已重新读取") stay until the submission itself changes.
  useEffect(() => {
    setError((current) => (current && STALE_ON_FACTS_REFRESH.has(current.code) ? null : current));
  }, [facts.review_version, facts.status, facts.submission_disposition]);
  const disposition = facts.submission_disposition;
  const dispositionReason = disposition
    ? disposition.disposition === "ARCHIVED_BASELINE" ? "该提交已归档" : "该提交已关闭（未归档）"
    : undefined;
  const approveDisabled = Boolean(dispositionReason) || !bundleReady || facts.status !== "PENDING" || expiredApprove;
  const otherDisabled = Boolean(dispositionReason) || !bundleReady || facts.status !== "PENDING";
  const blockedReason = dispositionReason
    ?? (!bundleReady ? "请等待历史比较 bundle 下载完成" : facts.status === "PENDING" ? undefined : STATUS_REASON[facts.status] ?? "当前提交不可审核");
  const approveReason = expiredApprove ? "该提交所基于的基线已更新，不能通过" : blockedReason;
  // Rule 3: withdraw/reject always share blockedReason; approve joins them when
  // its reason is identical. The shared reason is rendered once below the group.
  const groupReason = blockedReason;
  const approveUsesGroup = Boolean(blockedReason) && approveReason === blockedReason;
  const groupReasonId = `${generatedId}-review-disabled-reason`;

  function open(next: DialogKind) {
    setDialog(next);
    setReason("");
    setUnderstood(false);
    setError(null);
    dialogKey.current = crypto.randomUUID();
  }

  async function refreshFacts() {
    setBusy(true);
    try {
      onFactsChanged(await gatewayApi.getReviewFacts(submissionId));
      setError(null);
      dialogKey.current = null;
    } catch (cause) {
      const failure = actionError(cause, null);
      setError({ title: failure.title, code: failure.code });
    } finally {
      setBusy(false);
    }
  }

  function renderError() {
    if (!error) return null;
    return <div role="alert" className="form-error" title={`错误代码：${error.code}`}>
      <span>{error.title}</span>
      <span>错误代码：<code>{error.code}</code></span>
      <span className="form-error__actions">
        <button className="link-button" onClick={() => void navigator.clipboard?.writeText(error.code)}>复制错误代码</button>
        {error.code === "REVIEW_VERSION_CONFLICT" && <button className="link-button" onClick={() => void refreshFacts()}>刷新审核信息</button>}
      </span>
    </div>;
  }

  async function confirm() {
    if (!dialog) return;
    if (dialog === "reject" && !reason.trim()) return;
    if (dialog === "withdraw" && !understood) return;
    setBusy(true);
    setError(null);
    if (!dialogKey.current) dialogKey.current = crypto.randomUUID();
    const key = dialogKey.current;
    const failedDialog = dialog;
    try {
      const action = dialog === "approve" ? "APPROVE" : dialog === "reject" ? "REJECT" : "WITHDRAW";
      await applyReviewAction(gatewayApi, submissionId, facts.review_version, action, dialog === "reject" ? reason.trim() : undefined, key);
      onFactsChanged(await gatewayApi.getReviewFacts(submissionId));
      onReviewSettled?.();
      setExpiredApprove(false);
      setDialog(null);
    } catch (cause) {
      if (cause instanceof ApiError && (cause.status < 500 && cause.status !== 429)) dialogKey.current = null;
      const failure = actionError(cause, failedDialog);
      if (failure.expiredApprove || failure.closed) {
        // Expired approvals and closed submissions refresh the facts behind
        // the notice (§16.7); ordinary version conflicts keep the dialog open
        // until the user refreshes (FE2c R6 behavior).
        if (failure.expiredApprove) setExpiredApprove(true);
        setDialog(null);
        setError({ title: failure.title, code: failure.code });
        try {
          onFactsChanged(await gatewayApi.getReviewFacts(submissionId));
          onReviewSettled?.();
        } catch {
          // Keep the failure notice when the refresh itself fails.
        }
      } else {
        setError({ title: failure.title, code: failure.code });
      }
    } finally {
      setBusy(false);
    }
  }

  const confirmDisabled = busy || (dialog === "reject" && !reason.trim()) || (dialog === "withdraw" && !understood);

  const errorNotice = dialog === null && error ? renderError() : null;
  const errorHost = errorNoticeHost?.current ?? null;

  return <>
    <div className="review-actions">
      <div className="review-actions__buttons">
        <Button variant="danger" onClick={() => open("withdraw")} disabled={otherDisabled} disabledReason={groupReason ? undefined : blockedReason} aria-describedby={groupReason ? groupReasonId : undefined}>撤回</Button>
        <Button variant="danger" onClick={() => open("reject")} disabled={otherDisabled} disabledReason={groupReason ? undefined : blockedReason} aria-describedby={groupReason ? groupReasonId : undefined}>退回</Button>
        <Button variant="primary" onClick={() => open("approve")} disabled={approveDisabled} disabledReason={approveUsesGroup ? undefined : approveReason} aria-describedby={approveUsesGroup ? groupReasonId : undefined}>审核通过</Button>
      </div>
      {groupReason && <span className="review-actions__reason" id={groupReasonId}>{groupReason}</span>}

    <Dialog open={dialog === "approve"} title="确认审核通过" onClose={() => { if (!busy) setDialog(null); }} actions={<>
      <Button variant="secondary" onClick={() => setDialog(null)} disabled={busy}>取消</Button>
      <Button variant="primary" onClick={() => void confirm()} disabled={confirmDisabled}>确认通过</Button>
    </>}>
      <p className="confirm-impact">通过后该提交成为已通过提交，可以归档为新的业务基线；审核记录会保留。</p>
      {renderError()}
    </Dialog>

    <Dialog open={dialog === "reject"} title="退回提交" onClose={() => { if (!busy) setDialog(null); }} actions={<>
      <Button variant="secondary" onClick={() => setDialog(null)} disabled={busy}>取消</Button>
      <Button variant="danger" onClick={() => void confirm()} disabled={confirmDisabled} disabledReason={!reason.trim() ? "退回时必须填写理由" : undefined}>{busy ? "提交中…" : "确认退回"}</Button>
    </>}>
      <p className="confirm-impact">退回后该提交不会成为归档候选，提交人需要重新上传并提交；退回理由会保留在审核记录中。</p>
      <label className="confirm-reason">退回理由<textarea aria-label="退回理由" value={reason} onChange={(event) => setReason(event.currentTarget.value)} placeholder="说明退回原因（必填）" /></label>
      {renderError()}
    </Dialog>

    <Dialog open={dialog === "withdraw"} title="撤回提交" onClose={() => { if (!busy) setDialog(null); }} actions={<>
      <Button variant="secondary" onClick={() => setDialog(null)} disabled={busy}>取消</Button>
      <Button variant="danger" onClick={() => void confirm()} disabled={confirmDisabled} disabledReason={!understood ? "请先确认已了解撤回影响" : undefined}>{busy ? "提交中…" : "确认撤回"}</Button>
    </>}>
      <p className="confirm-impact">撤回后该提交不再进入归档候选，也无法继续审核；提交人需要重新上传并提交。此操作不可撤销。</p>
      <label className="confirm-checkbox"><input type="checkbox" checked={understood} onChange={(event) => setUnderstood(event.currentTarget.checked)} />我已了解撤回后需要重新提交，并确认继续</label>
      {renderError()}
    </Dialog>
    </div>
    {errorNotice && errorHost && createPortal(errorNotice, errorHost)}
    {errorNotice && !errorHost && errorNotice}
  </>;
}
