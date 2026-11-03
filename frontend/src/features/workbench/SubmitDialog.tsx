import { useEffect, useRef, useState } from "react";
import type { components } from "../api/generated/openapi";
import { gatewayApi } from "../api/application-api";
import { ApiError } from "../api/authenticated-fetch";
import { runSubmitJourney, SubmitAbortedError } from "../api/journeys";
import { currentGatewaySession } from "../api/session";
import { Button, Dialog } from "../../design-system/components";
import { formatWaitDuration } from "./wait-duration";

type Schemas = components["schemas"];
type Preview = Schemas["PreviewResultResponse"];
type IdentityPair = Preview["identity_pairs"][number];
type RequiredPair = IdentityPair & { status: "DIFFERENT_PROJECT" | "UNVERIFIABLE" };

const CONFIRMATION_ACTION: Record<RequiredPair["status"], "ACCEPT_DATASET_REPLACEMENT" | "ACCEPT_UNVERIFIABLE_DETAILED_RESULT"> = {
  DIFFERENT_PROJECT: "ACCEPT_DATASET_REPLACEMENT",
  UNVERIFIABLE: "ACCEPT_UNVERIFIABLE_DETAILED_RESULT",
};

function confirmationCopy(pair: RequiredPair): { title: string; body: string; checkbox: string } {
  if (pair.status === "DIFFERENT_PROJECT") {
    return {
      title: "业务项目不同，需要确认数据集替换",
      body: "Preview 中的业务项目与当前基线的业务项目不同。提交会按数据集替换处理，请确认这是预期操作。",
      checkbox: "我确认这是数据集替换，并按替换后的数据提交",
    };
  }
  return {
    title: "项目身份无法验证",
    body: "Preview 无法确认业务项目身份。请核对差异结果后再提交，否则可能把其他项目的数据写入当前基线。",
    checkbox: "我已核对差异结果，确认按无法验证身份的结果提交",
  };
}

function describeSubmitError(cause: unknown): { title: string; code: string; retryable: boolean } {
  if (cause instanceof SubmitAbortedError) {
    return { title: "提交未完成，请检查上传与 Preview 后重试", code: cause.abortCode, retryable: false };
  }
  if (cause instanceof ApiError) {
    const map: Record<string, string> = {
      SCOPE_FORBIDDEN: "当前身份没有该操作的权限",
      WORKSPACE_VERSION_CONFLICT: "数据已被更新，请刷新后重试",
      BASELINE_VERSION_CONFLICT: "数据已被更新，请刷新后重试",
      PREVIEW_DERIVED_STALE: "Preview 结果已过期，请重新上传并预览",
      PREVIEW_BINDING_CONFLICT: "Preview 结果与当前工作区不一致，请刷新后重试",
      SUBMIT_OCCUPANCY_CONFLICT: "已有提交正在处理，请稍后重试",
      NO_CANONICAL_CHANGE: "本次组态与基线一致，没有可提交的变更",
      PROJECT_IDENTITY_CONFIRMATION_REQUIRED: "需要确认项目身份差异后才能提交",
      PROJECT_IDENTITY_CONFIRMATION_MISMATCH: "项目身份确认已变化，请刷新后重新确认",
      IDEMPOTENCY_CONFLICT: "本次提交与服务器记录不一致，请关闭后重新提交",
      ADMISSION_LIMIT_REACHED: "系统繁忙，请稍后重试",
    };
    return { title: (cause.code ? map[cause.code] : undefined) ?? "提交失败", code: cause.code ?? "SUBMIT_FAILED", retryable: true };
  }
  return { title: cause instanceof Error ? cause.message : "提交失败", code: "SUBMIT_FAILED", retryable: true };
}

interface SubmitDialogProps {
  open: boolean;
  workspaceId: string;
  previewResultId: string;
  onClose: () => void;
  onSubmitted: (submissionId: string) => void;
}

export function SubmitDialog({ open, workspaceId, previewResultId, onClose, onSubmitted }: SubmitDialogProps) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [workspaceVersion, setWorkspaceVersion] = useState<number | null>(null);
  const [head, setHead] = useState<Schemas["HistoryListResponse"]["head"] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [confirmations, setConfirmations] = useState<Record<string, { confirmed: boolean; reason: string }>>({});
  const [submitting, setSubmitting] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [failure, setFailure] = useState<{ title: string; code: string; retryable: boolean } | null>(null);
  const [aborted, setAborted] = useState<string | null>(null);
  const idempotencyKey = useRef<string | null>(null);
  const startedAt = useRef<number | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    setFailure(null);
    setAborted(null);
    setConfirmations({});
    setPreview(null);
    setWorkspaceVersion(null);
    setHead(null);
    idempotencyKey.current = crypto.randomUUID();
    const session = currentGatewaySession();
    void Promise.all([
      gatewayApi.getPreviewResult(workspaceId, previewResultId),
      gatewayApi.createWorkspace({ business_project_id: session.businessProjectId, gateway_device_external_key: session.gatewayDeviceExternalKey }),
      gatewayApi.listHistory(),
    ]).then(([loadedPreview, workspace, history]) => {
      if (cancelled) return;
      setPreview(loadedPreview);
      setWorkspaceVersion(workspace.optimistic_version);
      setHead(history.head);
    }).catch((cause: unknown) => {
      if (!cancelled) setLoadError(cause instanceof Error ? cause.message : String(cause));
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, workspaceId, previewResultId]);

  useEffect(() => {
    if (!submitting) return;
    const ticker = window.setInterval(() => setElapsed(startedAt.current ? Math.floor((Date.now() - startedAt.current) / 1_000) : 0), 1_000);
    return () => window.clearInterval(ticker);
  }, [submitting]);

  const requiredPairs = (preview?.identity_pairs ?? []).filter((pair): pair is RequiredPair => pair.status === "DIFFERENT_PROJECT" || pair.status === "UNVERIFIABLE");
  const missing = requiredPairs.some((pair) => !confirmations[pair.pair_id]?.confirmed || !confirmations[pair.pair_id]?.reason.trim());
  const stale = Boolean(preview?.derived_stale);
  const canSubmit = Boolean(preview && workspaceVersion !== null && head && !stale && !missing && !loading && !submitting);

  async function submit() {
    if (!preview || workspaceVersion === null || !head || !canSubmit) return;
    setSubmitting(true);
    setFailure(null);
    setAborted(null);
    setElapsed(0);
    startedAt.current = Date.now();
    try {
      const result = await runSubmitJourney(gatewayApi, {
        workspaceId,
        previewResultId,
        uploadRevisionId: preview.upload_revision_id,
        generation: preview.generation,
        expectedWorkspaceVersion: workspaceVersion,
        baselineNodeId: preview.business_baseline_node_id,
        baselineHeadVersion: head.version,
        idempotencyKey: idempotencyKey.current ?? undefined,
        identityConfirmations: requiredPairs.map((pair) => ({
          action: CONFIRMATION_ACTION[pair.status],
          assessmentSetDigest: preview.identity_assessment_set_digest,
          reason: confirmations[pair.pair_id]?.reason.trim() ?? "",
        })),
      });
      onSubmitted(result.submission.submission_id);
    } catch (cause) {
      if (cause instanceof SubmitAbortedError) {
        setAborted(cause.abortCode);
        setFailure({ title: "提交未完成", code: cause.abortCode, retryable: true });
      } else {
        setFailure(describeSubmitError(cause));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return <Dialog open={open} title="提交本次组态" onClose={() => { if (!submitting) onClose(); }} actions={<><Button variant="secondary" onClick={onClose} disabled={submitting}>取消</Button><Button variant="primary" onClick={() => void submit()} disabled={!canSubmit} disabledReason={stale ? "Preview 结果已过期" : missing ? "请确认全部项目身份差异并填写原因" : undefined}>{submitting ? "提交中…" : "确认提交"}</Button></>}>
    {loading && <p className="subtle-copy">正在加载 Preview 信息…</p>}
    {loadError && <p role="alert" className="form-error">无法加载 Preview：{loadError}</p>}
    {!loading && !loadError && preview && <>
      <dl className="confirm-summary">
        <div><dt>工作区</dt><dd>{preview.workspace_id}</dd></div>
        <div><dt>Preview</dt><dd>{preview.preview_result_id}</dd></div>
        <div><dt>业务基线</dt><dd>{preview.business_baseline_node_id}</dd></div>
        <div><dt>代次</dt><dd>{preview.generation}</dd></div>
      </dl>
      <p className="confirm-impact">提交后将生成待审核提交，审核通过后才能归档为新的基线。提交前请确认差异结果与项目身份。</p>
      {stale && <p className="form-warning">Preview 结果已基于旧基线，请返回工作区重新上传并生成 Preview。</p>}
      {requiredPairs.map((pair) => {
        const copy = confirmationCopy(pair);
        const value = confirmations[pair.pair_id] ?? { confirmed: false, reason: "" };
        return <section className="confirm-requirement" key={pair.pair_id} aria-label={copy.title}>
          <h3>{copy.title}</h3>
          <p>{copy.body}</p>
          <label className="confirm-checkbox"><input type="checkbox" checked={value.confirmed} onChange={(event) => { const confirmed = event.currentTarget.checked; setConfirmations((current) => ({ ...current, [pair.pair_id]: { ...value, confirmed } })); }} />{copy.checkbox}</label>
          <label className="confirm-reason">确认原因<textarea aria-label={`${copy.title}的原因`} value={value.reason} onChange={(event) => { const reason = event.currentTarget.value; setConfirmations((current) => ({ ...current, [pair.pair_id]: { ...value, reason } })); }} placeholder="说明为什么可以继续提交" /></label>
        </section>;
      })}
      {requiredPairs.length === 0 && <p className="subtle-copy">项目身份均已确认一致，无需额外确认。</p>}
      {submitting && <p role="status" className="submit-progress">提交执行中 · 已等待 {formatWaitDuration(elapsed)}，请勿关闭页面。</p>}
      {aborted && <p role="alert" className="form-error" title={`原始错误代码：${aborted}`}>提交未完成，请检查上传与 Preview 后重试。{import.meta.env.DEV && <code> {aborted}</code>}</p>}
      {failure && !aborted && <p role="alert" className="form-error" title={`错误代码：${failure.code}`}>{failure.title}{import.meta.env.DEV && <code> {failure.code}</code>}</p>}
    </>}
  </Dialog>;
}
