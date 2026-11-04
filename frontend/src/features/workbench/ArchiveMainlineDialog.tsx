import { useCallback, useEffect, useRef, useState } from "react";
import type { components } from "../api/generated/openapi";
import { ApiError } from "../api/authenticated-fetch";
import { gatewayApi } from "../api/application-api";
import { ApiError } from "../api/authenticated-fetch";
import { createArchiveJourneyProgress, runArchiveJourney } from "../api/journeys";
import { Button, Dialog } from "../../design-system/components";

type Schemas = components["schemas"];
type Plan = Schemas["PreviewArchivePlanResponse"];
type Result = Schemas["ArchiveResultResponse"];
type Anomaly = Plan["anomalies"][number];

const ISSUE_COPY: Record<string, string> = {
  APPROVED_SIBLING_EXCLUDED: "存在未包含的已通过提交",
  PROJECT_IDENTITY_EXCEPTION: "存在项目身份例外",
  ACTIVE_SUBMIT_ATTEMPT: "已有提交正在处理",
  ARCHIVE_INTEGRITY_FAILURE: "归档数据完整性校验未通过",
};

const DISPOSITION_COPY: Record<string, string> = {
  ARCHIVED_BASELINE: "归档为新基线",
  CLOSED_NOT_ARCHIVED: "关闭且不归档",
};

function archiveError(cause: unknown): { title: string; code: string; refresh: boolean } {
  if (cause instanceof ApiError) {
    if (cause.code === "SCOPE_FORBIDDEN") return { title: "当前身份没有该操作的权限", code: "SCOPE_FORBIDDEN", refresh: false };
    if (cause.code === "BASELINE_VERSION_CONFLICT" || cause.code === "ARCHIVE_AUDIT_VERSION_CONFLICT") return { title: "数据已被更新，请刷新预检后重试", code: cause.code, refresh: true };
    if (cause.code === "CANDIDATE_BINDING_CONFLICT" || cause.code === "IDEMPOTENCY_CONFLICT") return { title: "归档候选或确认记录已变化，请刷新预检后重试", code: cause.code, refresh: true };
    return { title: cause.message || "归档失败", code: cause.code ?? "ARCHIVE_FAILED", refresh: false };
  }
  return { title: cause instanceof Error ? cause.message : "归档失败", code: "ARCHIVE_FAILED", refresh: false };
}

function anomalyAction(anomaly: Anomaly): "ACKNOWLEDGE_EXCLUSION" | "ACKNOWLEDGE_IDENTITY_EXCEPTION" {
  return anomaly.subject_kind === "PROJECT_IDENTITY_EXCEPTION" ? "ACKNOWLEDGE_IDENTITY_EXCEPTION" : "ACKNOWLEDGE_EXCLUSION";
}

interface ArchiveMainlineDialogProps {
  open: boolean;
  submissionId: string | null;
  onClose: () => void;
  onArchived: () => void;
}

export function ArchiveMainlineDialog({ open, submissionId, onClose, onArchived }: ArchiveMainlineDialogProps) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [selectedDigest, setSelectedDigest] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [confirmations, setConfirmations] = useState<Record<string, boolean>>({});
  const [anomalyResolutions, setAnomalyResolutions] = useState<Record<string, { acknowledged: boolean; reason: string }>>({});
  const [running, setRunning] = useState(false);
  const [failure, setFailure] = useState<{ title: string; code: string; refresh: boolean } | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const progress = useRef(createArchiveJourneyProgress());

  const load = useCallback(async (target: string) => {
    progress.current = createArchiveJourneyProgress();
    setLoading(true);
    setLoadError(null);
    setFailure(null);
    try {
      const candidates = await gatewayApi.listArchiveCandidates();
      const candidate = candidates.candidates.find((item) => item.submission_id === target);
      if (!candidate) {
        setLoadError("所选提交不在当前归档候选集合中，请刷新归档候选。");
        setPlan(null);
        return;
      }
      const loaded = await gatewayApi.previewArchive({ selected: candidate });
      if (loaded.selected && loaded.selected.submission_id !== target) {
        setLoadError("归档预检返回了其他提交，请刷新后重试。");
        setPlan(null);
        return;
      }
      setSelectedDigest(candidate.expected_candidate_digest);
      setPlan(loaded);
      setConfirmations({});
      setAnomalyResolutions({});
    } catch (cause) {
      setLoadError(cause instanceof ApiError ? `${cause.message}（${cause.code ?? `HTTP_${cause.status}`}）` : cause instanceof Error ? cause.message : String(cause));
      setPlan(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open || !submissionId) return;
    setPlan(null);
    setResult(null);
    setFailure(null);
    progress.current = createArchiveJourneyProgress();
    void load(submissionId);
  }, [open, submissionId, load]);

  const requiredConfirmations = plan?.confirmation_requirements ?? [];
  const missingConfirmation = requiredConfirmations.some((digest) => !confirmations[digest]);
  const missingAnomaly = (plan?.anomalies ?? []).some((anomaly) => {
    const value = anomalyResolutions[anomaly.subject_digest];
    return !value?.acknowledged || !value.reason.trim();
  });
  const blocked = Boolean(plan && plan.blockers.length > 0);
  const needsConfirmation = Boolean(plan && !plan.can_start && plan.blockers.length === 0);
  const canStart = Boolean(plan && selectedDigest && !blocked && !missingConfirmation && !missingAnomaly && !loading && !running);

  async function start() {
    if (!plan || !selectedDigest || !submissionId || !canStart) return;
    setRunning(true);
    setFailure(null);
    try {
      const outcome = await runArchiveJourney(gatewayApi, {
        selected: { submission_id: submissionId, expected_candidate_digest: selectedDigest },
        confirmations: requiredConfirmations.map((subjectDigest) => ({ subjectDigest, action: "CONFIRM" as const })),
        anomalyResolutions: (plan.anomalies ?? []).map((anomaly) => ({
          subjectDigest: anomaly.subject_digest,
          action: anomalyAction(anomaly),
          reason: anomalyResolutions[anomaly.subject_digest]?.reason.trim() ?? "",
        })),
      }, progress.current);
      setResult(outcome.result);
    } catch (cause) {
      setFailure(archiveError(cause));
    } finally {
      setRunning(false);
    }
  }

  function resetUnsentAnomalyKey(subjectDigest: string) {
    const entry = progress.current.anomalyResolutions.get(subjectDigest);
    if (entry && entry.sequence === undefined) progress.current.anomalyResolutions.delete(subjectDigest);
  }

  function refresh() {
    progress.current = createArchiveJourneyProgress();
    setResult(null);
    void load(submissionId);
  }

  const archivedCount = result?.dispositions.filter((item) => item.disposition === "ARCHIVED_BASELINE").length ?? 0;
  const closedCount = result?.dispositions.filter((item) => item.disposition === "CLOSED_NOT_ARCHIVED").length ?? 0;

  return <Dialog open={open} title="归档主基线" description="确认候选、异常处理与归档后的影响，完成后生成新的业务基线。" onClose={() => { if (!running) onClose(); }} actions={result ? <>
    <Button variant="primary" onClick={onArchived}>完成</Button>
  </> : <>
    <Button variant="secondary" onClick={refresh} disabled={loading || running}>重新预检</Button>
    <Button variant="primary" onClick={() => void start()} disabled={!canStart} disabledReason={blocked ? "当前预检存在阻断项" : missingConfirmation ? "请确认归档选择" : missingAnomaly ? "请处理全部异常项" : !plan ? "正在预检" : undefined}>{running ? "归档中…" : "确认归档"}</Button>
  </>}>
    {loading && <p className="subtle-copy">正在读取归档候选并预检…</p>}
    {loadError && <p role="alert" className="form-error">{loadError}</p>}
    {!loading && !result && plan && <>
      <section className="archive-step" aria-label="预检状态">
        <h3>预检状态</h3>
        <dl className="confirm-summary">
          <div><dt>当前基线版本</dt><dd>{plan.head.baseline_head_version}</dd></div>
          <div><dt>候选提交</dt><dd>{plan.selected?.submission_id ?? submissionId ?? "—"}</dd></div>
          <div><dt>候选集合摘要</dt><dd><code>{plan.candidate_set_digest.slice(0, 20)}…</code></dd></div>
        </dl>
        {blocked && <div role="alert" className="archive-blockers"><strong>归档被阻止</strong><ul>{plan.blockers.map((code) => <li key={code}>{ISSUE_COPY[code] ?? code}<code>{code}</code></li>)}</ul></div>}
        {needsConfirmation && <p className="subtle-copy">首次预检待确认：完成下方确认与异常处理后，重新预检再归档。</p>}
      </section>

      {requiredConfirmations.length > 0 && <section className="archive-step" aria-label="需逐一确认项">
        <h3>需逐一确认项</h3>
        {requiredConfirmations.map((digest) => <label className="confirm-checkbox" key={digest}><input type="checkbox" checked={Boolean(confirmations[digest])} onChange={(event) => { const checked = event.currentTarget.checked; setConfirmations((current) => ({ ...current, [digest]: checked })); }} />确认归档选择 <code title={digest}>{digest.slice(0, 24)}…</code></label>)}
      </section>}

      {(plan.anomalies ?? []).length > 0 && <section className="archive-step" aria-label="异常处理">
        <h3>异常处理</h3>
        {plan.anomalies.map((anomaly) => {
          const value = anomalyResolutions[anomaly.subject_digest] ?? { acknowledged: false, reason: "" };
          return <div className="archive-anomaly" key={anomaly.subject_digest}>
            <strong>{ISSUE_COPY[anomaly.issue_code] ?? anomaly.issue_code}<code title={anomaly.issue_code}>{anomaly.issue_code}</code></strong>
            <p>目标提交 {anomaly.target_submission_id}，需要说明处理原因。</p>
            <label className="confirm-checkbox"><input type="checkbox" checked={value.acknowledged} onChange={(event) => { const acknowledged = event.currentTarget.checked; resetUnsentAnomalyKey(anomaly.subject_digest); setAnomalyResolutions((current) => ({ ...current, [anomaly.subject_digest]: { ...value, acknowledged } })); }} />我已核对该异常并确认继续归档</label>
            <label className="confirm-reason">处理原因<textarea aria-label={`${anomaly.issue_code} 的处理原因`} value={value.reason} onChange={(event) => { const reason = event.currentTarget.value; resetUnsentAnomalyKey(anomaly.subject_digest); setAnomalyResolutions((current) => ({ ...current, [anomaly.subject_digest]: { ...value, reason } })); }} placeholder="说明为什么可以忽略或继续归档" /></label>
          </div>;
        })}
      </section>}

      <section className="archive-step" aria-label="确认后的影响">
        <h3>确认后的影响</h3>
        <p>归档成功后，所选提交会成为新的业务基线；其他候选会按预检结果归档或关闭。该操作不可撤销。</p>
        {plan.dispositions && plan.dispositions.length > 0 && <ul className="archive-impact">{plan.dispositions.map((item) => <li key={item.submission_id}><span>{item.submission_id}</span>{DISPOSITION_COPY[item.disposition] ?? item.disposition}</li>)}</ul>}
        {(plan.workspace_releases ?? []).length > 0 && <p className="subtle-copy">将释放 {plan.workspace_releases.length} 个工作区：{plan.workspace_releases.map((item) => item.workspace_id).join("、")}</p>}
      </section>

      {running && <p role="status" className="submit-progress">归档执行中，请勿关闭页面。</p>}
      {failure && <div role="alert" className="form-error"> {failure.title}<code> {failure.code}</code><button className="link-button" onClick={() => void navigator.clipboard?.writeText(failure.code)}>复制错误代码</button>{failure.refresh && <Button variant="secondary" onClick={refresh}>刷新预检</Button>}</div>}
    </>}
    {result && <section className="archive-step" aria-label="归档结果">
      <h2>归档完成</h2>
      <dl className="confirm-summary">
        <div><dt>新基线</dt><dd>{result.baseline_node_id}</dd></div>
        <div><dt>基线版本</dt><dd>{result.baseline_head_version}</dd></div>
        <div><dt>归档提交</dt><dd>{result.selected_submission_id}</dd></div>
        <div><dt>处理结果</dt><dd>归档 {archivedCount} 项，关闭 {closedCount} 项</dd></div>
      </dl>
      <p className="confirm-impact">新的业务基线已生成，工作台将刷新以显示最新 History。</p>
    </section>}
  </Dialog>;
}
