import { useRef, useState } from "react";
import { ApiError } from "../api/authenticated-fetch";
import { applyReviewAction } from "../api/journeys";
import { gatewayApi } from "../api/application-api";
import type { SafeReviewFacts } from "../api/client";
import { Button, Dialog } from "../../design-system/components";

type DialogKind = "approve" | "reject" | "withdraw";

const STATUS_REASON: Record<string, string> = {
  APPROVED: "该提交已通过审核",
  REJECTED: "该提交已退回",
  WITHDRAWN: "该提交已撤回",
};

function actionError(cause: unknown): { title: string; code: string } {
  if (cause instanceof ApiError) {
    if (cause.code === "SCOPE_FORBIDDEN") return { title: "当前身份没有该操作的权限", code: "SCOPE_FORBIDDEN" };
    if (cause.code === "REVIEW_VERSION_CONFLICT") return { title: "数据已被更新，请刷新审核信息后重试", code: cause.code };
    if (cause.code === "IDEMPOTENCY_CONFLICT") return { title: "本次审核与服务器记录不一致，请刷新后重试", code: cause.code };
    return { title: cause.message || "审核操作失败", code: cause.code ?? "REVIEW_FAILED" };
  }
  return { title: cause instanceof Error ? cause.message : "审核操作失败", code: "REVIEW_FAILED" };
}

interface ReviewActionsProps {
  submissionId: string;
  facts: SafeReviewFacts;
  bundleReady: boolean;
  onFactsChanged: (facts: SafeReviewFacts) => void;
}

export function ReviewActions({ submissionId, facts, bundleReady, onFactsChanged }: ReviewActionsProps) {
  const [dialog, setDialog] = useState<DialogKind | null>(null);
  const [reason, setReason] = useState("");
  const [understood, setUnderstood] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ title: string; code: string } | null>(null);
  const dialogKey = useRef<string | null>(null);
  const pending = facts.status === "PENDING";
  const blockedReason = !bundleReady ? "请等待历史比较 bundle 下载完成" : pending ? undefined : STATUS_REASON[facts.status] ?? "当前提交不可审核";

  function open(next: DialogKind) {
    setDialog(next);
    setReason("");
    setUnderstood(false);
    setError(null);
    dialogKey.current = crypto.randomUUID();
  }

  async function confirm() {
    if (!dialog) return;
    if (dialog === "reject" && !reason.trim()) return;
    if (dialog === "withdraw" && !understood) return;
    setBusy(true);
    setError(null);
    if (!dialogKey.current) dialogKey.current = crypto.randomUUID();
    const key = dialogKey.current;
    try {
      const action = dialog === "approve" ? "APPROVE" : dialog === "reject" ? "REJECT" : "WITHDRAW";
      await applyReviewAction(gatewayApi, submissionId, facts.review_version, action, dialog === "reject" ? reason.trim() : undefined, key);
      onFactsChanged(await gatewayApi.getReviewFacts(submissionId));
      setDialog(null);
    } catch (cause) {
      if (cause instanceof ApiError && (cause.status < 500 && cause.status !== 429)) dialogKey.current = null;
      setError(actionError(cause));
    } finally {
      setBusy(false);
    }
  }

  const confirmDisabled = busy || (dialog === "reject" && !reason.trim()) || (dialog === "withdraw" && !understood);

  return <div className="review-actions">
    <Button variant="danger" onClick={() => open("withdraw")} disabled={!pending || !bundleReady} disabledReason={blockedReason}>撤回</Button>
    <Button variant="danger" onClick={() => open("reject")} disabled={!pending || !bundleReady} disabledReason={blockedReason}>退回</Button>
    <Button variant="primary" onClick={() => open("approve")} disabled={!pending || !bundleReady} disabledReason={blockedReason}>审核通过</Button>

    <Dialog open={dialog === "approve"} title="确认审核通过" onClose={() => { if (!busy) setDialog(null); }} actions={<>
      <Button variant="secondary" onClick={() => setDialog(null)} disabled={busy}>取消</Button>
      <Button variant="primary" onClick={() => void confirm()} disabled={confirmDisabled}>确认通过</Button>
    </>}>
      <p className="confirm-impact">通过后该提交成为已通过提交，可以归档为新的业务基线；审核记录会保留。</p>
      {error && <p role="alert" className="form-error" title={`错误代码：${error.code}`}>{error.title}<code> {error.code}</code></p>}
    </Dialog>

    <Dialog open={dialog === "reject"} title="退回提交" onClose={() => { if (!busy) setDialog(null); }} actions={<>
      <Button variant="secondary" onClick={() => setDialog(null)} disabled={busy}>取消</Button>
      <Button variant="danger" onClick={() => void confirm()} disabled={confirmDisabled} disabledReason={!reason.trim() ? "退回时必须填写理由" : undefined}>{busy ? "提交中…" : "确认退回"}</Button>
    </>}>
      <p className="confirm-impact">退回后该提交不会成为归档候选，提交人需要重新上传并提交；退回理由会保留在审核记录中。</p>
      <label className="confirm-reason">退回理由<textarea aria-label="退回理由" value={reason} onChange={(event) => setReason(event.currentTarget.value)} placeholder="说明退回原因（必填）" /></label>
      {error && <p role="alert" className="form-error" title={`错误代码：${error.code}`}>{error.title}<code> {error.code}</code></p>}
    </Dialog>

    <Dialog open={dialog === "withdraw"} title="撤回提交" onClose={() => { if (!busy) setDialog(null); }} actions={<>
      <Button variant="secondary" onClick={() => setDialog(null)} disabled={busy}>取消</Button>
      <Button variant="danger" onClick={() => void confirm()} disabled={confirmDisabled} disabledReason={!understood ? "请先确认已了解撤回影响" : undefined}>{busy ? "提交中…" : "确认撤回"}</Button>
    </>}>
      <p className="confirm-impact">撤回后该提交不再进入归档候选，也无法继续审核；提交人需要重新上传并提交。此操作不可撤销。</p>
      <label className="confirm-checkbox"><input type="checkbox" checked={understood} onChange={(event) => setUnderstood(event.currentTarget.checked)} />我已了解撤回后需要重新提交，并确认继续</label>
      {error && <p role="alert" className="form-error" title={`错误代码：${error.code}`}>{error.title}<code> {error.code}</code></p>}
    </Dialog>
  </div>;
}
