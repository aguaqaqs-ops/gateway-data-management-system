import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import type { components } from "../api/generated/openapi";
import { ApiError } from "../api/authenticated-fetch";
import { gatewayApi } from "../api/application-api";
import { buildArchiveSelectedRef, createArchiveJourneyProgress, runArchiveJourney } from "../api/journeys";
import { Button, Dialog } from "../../design-system/components";
import {
  anomalyAction,
  anomalyDetailText,
  anomalyGroupKey,
  archiveError,
  blockerCopy,
  closeError,
  detectedStatusCopy,
  formatReasonLimitError,
  formatServerTimeUtc,
  GROUP_DEFS,
  ISSUE_COPY,
  KNOWN_ISSUE_CODES,
  RELATION_COPY,
  COMPARISON_STATUS_COPY,
  resolutionError,
  resolutionStatusCopy,
  resolutionStatusTone,
  SIDE_COPY,
  startDisabledReason as computeStartDisabledReason,
  statusTagClass,
  utf8Length,
} from "../view-model/archive-dialog";

type Schemas = components["schemas"];

type Candidates = Schemas["ArchiveCandidatesResponse"];
type Candidate = Candidates["candidates"][number];
type Plan = Schemas["PreviewArchivePlanResponse"];
type Anomaly = Plan["anomalies"][number];
type Result = Schemas["ArchiveResultResponse"];
type CloseResult = Schemas["CloseSubmissionResponse"];

interface ArchiveMainlineDialogProps {
  open: boolean;
  submissionId: string | null;
  onClose: () => void;
  onArchived: () => void;
  /** Display name for a submission id ("提交 n"); falls back to the raw id. */
  resolveName?: (submissionId: string) => string | null;
  /** Baseline label for a head node id ("归档基线 n"); falls back to the node id. */
  resolveBaselineLabel?: (nodeId: string) => string | null;
  /** Select a submission in the workspace tree (used by pending-review links). */
  onSelectSubmission?: (submissionId: string) => void;
  /** Reload the workspace tree after a manual close changed dispositions. */
  onDispositionChanged?: () => void;
}

export function ArchiveMainlineDialog({ open, submissionId, onClose, onArchived, resolveName, resolveBaselineLabel, onSelectSubmission, onDispositionChanged }: ArchiveMainlineDialogProps) {
  const [candidates, setCandidates] = useState<Candidates | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [selectedDigest, setSelectedDigest] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<{ message: string; code: string | null } | null>(null);
  const [confirmSelection, setConfirmSelection] = useState(false);
  const [collectionNotice, setCollectionNotice] = useState<string | null>(null);
  const previousDigest = useRef<string | null>(null);
  const [acceptTarget, setAcceptTarget] = useState<Anomaly | null>(null);
  const [acceptReason, setAcceptReason] = useState("");
  const [acceptKey, setAcceptKey] = useState<string | null>(null);
  const [acceptBusy, setAcceptBusy] = useState(false);
  const [acceptError, setAcceptError] = useState<{ title: string; code: string } | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<Anomaly | null>(null);
  const [revokeReason, setRevokeReason] = useState("");
  const [revokeKey, setRevokeKey] = useState<string | null>(null);
  const [revokeBusy, setRevokeBusy] = useState(false);
  const [revokeError, setRevokeError] = useState<{ title: string; code: string } | null>(null);
  const [closeTarget, setCloseTarget] = useState<Candidate | null>(null);
  const [closeReason, setCloseReason] = useState("");
  const [closeUnderstood, setCloseUnderstood] = useState(false);
  const [closeKey, setCloseKey] = useState<string | null>(null);
  const [closeBusy, setCloseBusy] = useState(false);
  const [closeErrorState, setCloseErrorState] = useState<{ title: string; code: string } | null>(null);
  const [closeResult, setCloseResult] = useState<CloseResult | null>(null);
  const [closeSnapshot, setCloseSnapshot] = useState<{ candidate: Candidate; head: Plan["head"]; candidateSetDigest: string } | null>(null);
  const [closeRetry, setCloseRetry] = useState<{ body: Schemas["CloseSubmissionRequest"] } | null>(null);
  const [running, setRunning] = useState(false);
  const [failure, setFailure] = useState<{ title: string; code: string; refresh: boolean } | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const progress = useRef(createArchiveJourneyProgress());

  const displayName = useCallback((id: string) => resolveName?.(id) ?? id, [resolveName]);

  const load = useCallback(async (target: string) => {
    progress.current = createArchiveJourneyProgress();
    setLoading(true);
    setLoadError(null);
    setFailure(null);
    let stage: "candidates" | "preview" = "candidates";
    try {
      let listed = await gatewayApi.listArchiveCandidates();
      let candidate = listed.candidates.find((item) => item.submission_id === target);
      if (!candidate) {
        setLoadError({ message: "所选提交不在当前归档候选集合中，请刷新归档候选。", code: null });
        setPlan(null);
        return;
      }
      stage = "preview";
      let selected = buildArchiveSelectedRef(candidate);
      let loaded = await gatewayApi.previewArchive({ selected });
      if (loaded.selected && loaded.selected.submission_id !== target) {
        setLoadError({ message: "归档预检返回了其他提交，请刷新后重试。", code: null });
        setPlan(null);
        return;
      }
      if (loaded.candidate_set_digest !== listed.candidate_set_digest) {
        // §16.2 “一次加载”: the candidate read and the preview must agree. Redo
        // both once, rebuilding selected from the second candidate read.
        stage = "candidates";
        const reloadedList = await gatewayApi.listArchiveCandidates();
        stage = "preview";
        const reloadedCandidate = reloadedList.candidates.find((item) => item.submission_id === target);
        if (!reloadedCandidate) {
          setLoadError({ message: "所选提交不在当前归档候选集合中，请刷新归档候选。", code: null });
          setPlan(null);
          return;
        }
        listed = reloadedList;
        candidate = reloadedCandidate;
        selected = buildArchiveSelectedRef(candidate);
        const reloaded = await gatewayApi.previewArchive({ selected });
        if (reloaded.selected && reloaded.selected.submission_id !== target) {
          setLoadError({ message: "归档预检返回了其他提交，请刷新后重试。", code: null });
          setPlan(null);
          return;
        }
        if (reloaded.candidate_set_digest !== listed.candidate_set_digest) {
          setLoadError({ message: "归档候选集合已变化，请重新预检。", code: null });
          setPlan(null);
          return;
        }
        loaded = reloaded;
      }
      if (previousDigest.current !== null && previousDigest.current !== loaded.candidate_set_digest) {
        setCollectionNotice("候选集合已变化，之前的接受不再适用，请重新核对");
      }
      previousDigest.current = loaded.candidate_set_digest;
      setCandidates(listed);
      setSelectedDigest(candidate.expected_candidate_digest);
      setPlan(loaded);
    } catch (cause) {
      const message = cause instanceof ApiError && cause.code === "SCOPE_FORBIDDEN"
        ? (stage === "preview" ? "当前身份没有预检归档方案的权限" : "当前身份没有该操作的权限")
        : cause instanceof Error ? cause.message : String(cause);
      setLoadError({ message, code: cause instanceof ApiError ? (cause.code ?? `HTTP_${cause.status}`) : null });
      setPlan(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open || !submissionId) return;
    setPlan(null);
    setCandidates(null);
    setResult(null);
    setFailure(null);
    setCollectionNotice(null);
    setConfirmSelection(false);
    previousDigest.current = null;
    progress.current = createArchiveJourneyProgress();
    void load(submissionId);
  }, [open, submissionId, load]);

  function refresh() {
    progress.current = createArchiveJourneyProgress();
    setResult(null);
    if (submissionId) void load(submissionId);
  }

  function openAccept(anomaly: Anomaly) {
    setAcceptTarget(anomaly);
    setAcceptReason("");
    setAcceptError(null);
    setAcceptKey(crypto.randomUUID());
  }

  function openRevoke(anomaly: Anomaly) {
    setRevokeTarget(anomaly);
    setRevokeReason("");
    setRevokeError(null);
    setRevokeKey(crypto.randomUUID());
  }

  async function submitResolution(kind: "accept" | "revoke") {
    const target = kind === "accept" ? acceptTarget : revokeTarget;
    const reason = kind === "accept" ? acceptReason : revokeReason;
    const key = kind === "accept" ? acceptKey : revokeKey;
    if (!plan || !candidates || !target || !submissionId || !selectedDigest || !key) return;
    if (formatReasonLimitError(kind, reason.trim(), utf8Length(reason)) !== undefined) return;
    const setBusy = kind === "accept" ? setAcceptBusy : setRevokeBusy;
    const setError = kind === "accept" ? setAcceptError : setRevokeError;
    setBusy(true);
    setError(null);
    try {
      await gatewayApi.appendArchiveAnomalyResolution({
        expected_baseline_node_id: plan.head.business_baseline_node_id,
        expected_baseline_head_version: plan.head.baseline_head_version,
        candidate_set_digest: plan.candidate_set_digest,
        selected: buildArchiveSelectedRef({ submission_id: submissionId, expected_candidate_digest: selectedDigest }),
        subject_digest: target.subject_digest,
        subject_kind: target.subject_kind,
        issue_code: target.issue_code,
        target_submission_id: target.target_submission_id,
        target_candidate_digest: target.target_candidate_digest,
        expected_sequence: target.latest_sequence,
        action: kind === "accept" ? anomalyAction(target) : "REVOKE",
        reason,
      }, key);
      if (kind === "accept") setAcceptTarget(null); else setRevokeTarget(null);
      refresh();
    } catch (cause) {
      if (cause instanceof ApiError && (cause.code === "BASELINE_VERSION_CONFLICT" || cause.code === "CANDIDATE_SET_CONFLICT" || cause.code === "CANDIDATE_BINDING_CONFLICT" || cause.code === "ARCHIVE_AUDIT_VERSION_CONFLICT")) {
        if (kind === "accept") setAcceptTarget(null); else setRevokeTarget(null);
        setCollectionNotice("归档候选或核验结果已变化，已重新预检");
        refresh();
        return;
      }
      setError(resolutionError(cause));
    } finally {
      setBusy(false);
    }
  }

  function openClose(candidate: Candidate) {
    if (!plan || !candidates) return;
    setCloseTarget(candidate);
    setCloseSnapshot({ candidate, head: plan.head, candidateSetDigest: candidates.candidate_set_digest });
    setCloseReason("");
    setCloseUnderstood(false);
    setCloseErrorState(null);
    setCloseResult(null);
    setCloseRetry(null);
    setCloseKey(crypto.randomUUID());
  }

  async function submitClose() {
    if (!closeTarget || !closeSnapshot || !closeKey) return;
    if (formatReasonLimitError("close", closeReason.trim(), utf8Length(closeReason)) !== undefined || !closeUnderstood) return;
    const body: Schemas["CloseSubmissionRequest"] = {
      expected_baseline_node_id: closeSnapshot.head.business_baseline_node_id,
      expected_baseline_head_version: closeSnapshot.head.baseline_head_version,
      expected_review_version: closeSnapshot.candidate.review_version,
      reason: closeReason,
    };
    setCloseBusy(true);
    setCloseErrorState(null);
    setCloseRetry(null);
    try {
      const response = await gatewayApi.closeSubmission(closeSnapshot.candidate.submission_id, body, closeKey);
      setCloseResult(response);
      setCloseRetry(null);
      setCandidates(null);
      setPlan(null);
      await load(closeTarget.submission_id === submissionId ? closeTarget.submission_id : (submissionId ?? closeTarget.submission_id));
      onDispositionChanged?.();
    } catch (cause) {
      if (cause instanceof ApiError && (cause.code === "BASELINE_VERSION_CONFLICT" || cause.code === "REVIEW_VERSION_CONFLICT" || cause.code === "REVIEW_TRANSITION_CONFLICT" || cause.code === "WORKSPACE_OCCUPANCY_CONFLICT" || cause.code === "ARCHIVE_CLOSED")) {
        setCloseTarget(null);
        setCollectionNotice(cause.code === "ARCHIVE_CLOSED" ? "该提交已归档或关闭" : "提交或基线已变化，已重新预检");
        refresh();
        return;
      }
      if (cause instanceof ApiError) {
        setCloseErrorState(closeError(cause));
        return;
      }
      setCloseRetry({ body });
      setCloseErrorState({ title: "关闭请求未能送达，可以重试", code: "CLOSE_NOT_SENT" });
    } finally {
      setCloseBusy(false);
    }
  }

  async function retryClose() {
    if (!closeTarget || !closeSnapshot || !closeKey || !closeRetry) return;
    setCloseBusy(true);
    setCloseErrorState(null);
    try {
      const response = await gatewayApi.closeSubmission(closeSnapshot.candidate.submission_id, closeRetry.body, closeKey);
      setCloseResult(response);
      setCloseRetry(null);
      refresh();
      onDispositionChanged?.();
    } catch (cause) {
      if (cause instanceof ApiError && (cause.code === "BASELINE_VERSION_CONFLICT" || cause.code === "REVIEW_VERSION_CONFLICT" || cause.code === "REVIEW_TRANSITION_CONFLICT" || cause.code === "WORKSPACE_OCCUPANCY_CONFLICT" || cause.code === "ARCHIVE_CLOSED")) {
        setCloseTarget(null);
        setCollectionNotice(cause.code === "ARCHIVE_CLOSED" ? "该提交已归档或关闭" : "提交或基线已变化，已重新预检");
        refresh();
        return;
      }
      if (cause instanceof ApiError) {
        setCloseErrorState(closeError(cause));
        setCloseRetry(null);
        return;
      }
      setCloseErrorState({ title: "关闭请求未能送达，可以重试", code: "CLOSE_NOT_SENT" });
    } finally {
      setCloseBusy(false);
    }
  }

  const anomalies = plan?.anomalies ?? [];
  const unprocessedCount = anomalies.filter((anomaly) => anomaly.resolution_status !== "ACCEPTED").length;
  const unknownCount = anomalies.filter((anomaly) => !KNOWN_ISSUE_CODES.has(anomaly.issue_code)).length;
  const blocked = Boolean(plan && plan.blockers.length > 0);
  const canStart = Boolean(plan && candidates && selectedDigest && submissionId && !blocked && unknownCount === 0 && unprocessedCount === 0 && confirmSelection && !loading && !running);

  async function start() {
    if (!plan || !candidates || !submissionId || !selectedDigest || !canStart) return;
    setRunning(true);
    setFailure(null);
    try {
      const required = plan.confirmation_requirements ?? [];
      const outcome = await runArchiveJourney(gatewayApi, {
        selected: buildArchiveSelectedRef({ submission_id: submissionId, expected_candidate_digest: selectedDigest }),
        confirmations: required.map((subjectDigest) => ({ subjectDigest, action: "CONFIRM" as const })),
      }, progress.current);
      setResult(outcome.result);
    } catch (cause) {
      setFailure(archiveError(cause));
    } finally {
      setRunning(false);
    }
  }

  function startDisabledReason(): string | undefined {
    return computeStartDisabledReason({
      loading,
      loadError,
      plan,
      blockerCount: plan?.blockers.length ?? 0,
      unknownCount,
      unprocessedCount,
      confirmSelection,
      running,
    });
  }

  const archivedCount = result?.dispositions.filter((item) => item.disposition === "ARCHIVED_BASELINE").length ?? 0;
  const closedCount = result?.dispositions.filter((item) => item.disposition === "CLOSED_NOT_ARCHIVED").length ?? 0;
  const headNodeId = candidates?.head.business_baseline_node_id ?? plan?.head.business_baseline_node_id ?? "";
  const headLabel = (headNodeId && resolveBaselineLabel?.(headNodeId)) || headNodeId;
  const headVersion = candidates?.head.baseline_head_version ?? plan?.head.baseline_head_version;
  const pendingIds = candidates?.pending_submission_ids ?? [];
  const pendingCount = candidates?.pending_submission_count ?? 0;
  const hasPendingBlocker = Boolean(plan?.blockers.includes("ARCHIVE_PENDING_REVIEW"));
  const validation = plan?.business_validation;


  function renderAnomalyCard(anomaly: Anomaly) {
    const known = KNOWN_ISSUE_CODES.has(anomaly.issue_code);
    const side = anomaly.side ? SIDE_COPY[anomaly.side] ?? anomaly.side : null;
    return <div className="archive-anomaly" key={anomaly.subject_digest}>
      <strong>{displayName(anomaly.target_submission_id)}{side ? ` · ${side}` : ""}：{ISSUE_COPY[anomaly.issue_code] ?? anomaly.issue_code}</strong>
      <p>
        <span className="status-tag status-tag--warning">原始诊断：{detectedStatusCopy(anomaly)}</span>
        <span className={statusTagClass(resolutionStatusTone(anomaly.resolution_status))}>处理：{resolutionStatusCopy(anomaly.resolution_status)}</span>
      </p>
      <p>{anomalyDetailText(anomaly, displayName)}</p>
      <p>受影响提交：{anomaly.affected_submission_ids.map(displayName).join("、") || "—"}</p>
      {anomaly.resolution_status === "ACCEPTED" && <p>已由 {anomaly.accepted_by} 于 {anomaly.accepted_at ? formatServerTimeUtc(anomaly.accepted_at) : "—"} 接受：{anomaly.reason}</p>}
      {anomaly.resolution_status === "REVOKED" && <p>已撤销，原因：{anomaly.reason}</p>}
      {known && anomaly.resolution_status !== "ACCEPTED" && <Button variant="secondary" onClick={() => openAccept(anomaly)}>接受</Button>}
      {known && anomaly.resolution_status === "ACCEPTED" && <Button variant="secondary" onClick={() => openRevoke(anomaly)}>撤销接受</Button>}
      {!known && <p className="subtle-copy">当前版本不能处理该项，请刷新或联系管理员</p>}
    </div>;
  }

  function renderGroup(groupKey: string, title: string) {
    const items = anomalies
      .filter((anomaly) => anomalyGroupKey(anomaly) === groupKey)
      .sort((left, right) => displayName(left.target_submission_id).localeCompare(displayName(right.target_submission_id), "zh-CN") || (left.side ?? "").localeCompare(right.side ?? ""));
    if (items.length === 0) return null;
    const unprocessed = items.filter((anomaly) => anomaly.resolution_status !== "ACCEPTED").length;
    return <details className="archive-group" key={groupKey} open={unprocessed > 0}>
      <summary>{title}（未处理 {unprocessed} ／ 共 {items.length}）</summary>
      {items.map(renderAnomalyCard)}
    </details>;
  }

  function renderReasonField(kind: "accept" | "revoke" | "close", value: string, onChange: (next: string) => void, label: string) {
    const bytes = utf8Length(value);
    const error = formatReasonLimitError(kind, value.trim(), bytes);
    return <>
      <label className="confirm-reason">{label}<textarea aria-label={label} value={value} onChange={(event) => onChange(event.currentTarget.value)} placeholder="说明原因（必填）" /></label>
      {bytes > 3500 && <p className="subtle-copy">已输入 {bytes} 字节（上限 4096 字节）</p>}
      {error && <p role="alert" className="form-error"><span>{error}</span></p>}
    </>;
  }

  const acceptLimitError = formatReasonLimitError("accept", acceptReason.trim(), utf8Length(acceptReason));
  const revokeLimitError = formatReasonLimitError("revoke", revokeReason.trim(), utf8Length(revokeReason));
  const closeLimitError = formatReasonLimitError("close", closeReason.trim(), utf8Length(closeReason));

  return <>
    <Dialog open={open && !acceptTarget && !revokeTarget && !closeTarget} title="归档主基线" description="确认候选、异常处理与归档后的影响，完成后生成新的业务基线。" onClose={() => { if (!running) onClose(); }} alert={failure ? <div role="alert" className="form-error"><span>{failure.title}</span><span>错误代码：<code>{failure.code}</code></span><span className="form-error__actions"><button className="link-button" onClick={() => void navigator.clipboard?.writeText(failure.code)}>复制错误代码</button>{failure.refresh && <Button variant="secondary" onClick={refresh}>重新预检</Button>}</span></div> : null} actions={result ? <>
      <Button variant="primary" onClick={onArchived}>完成</Button>
    </> : <>
      <Button variant="secondary" onClick={refresh} disabled={loading || running}>重新预检</Button>
      <Button variant="primary" onClick={() => void start()} disabled={!canStart} disabledReason={startDisabledReason()}>{running ? "归档中…" : "确认归档"}</Button>
    </>}>
      {loading && <p className="subtle-copy">正在读取归档候选并预检…</p>}
      {loadError && <div role="alert" className="form-error"><span>{loadError.message}</span>{loadError.code && <><span>错误代码：<code>{loadError.code}</code></span><span className="form-error__actions"><button className="link-button" onClick={() => void navigator.clipboard?.writeText(loadError.code ?? "")}>复制错误代码</button></span></>}</div>}
      {collectionNotice && <div role="alert" className="form-error"><span>{collectionNotice}</span></div>}
      {!loading && !result && plan && candidates && <>
        <section className="archive-step" aria-label="预检状态">
          <h3>预检状态</h3>
          <dl className="confirm-summary">
            <div><dt>当前基线</dt><dd>{headLabel}{headVersion !== undefined ? `（版本 ${headVersion}）` : ""}</dd></div>
            <div><dt>选中</dt><dd>{submissionId ? displayName(submissionId) : "—"}</dd></div>
          </dl>
          {plan.blockers.length > 0 && <div role="alert" className="archive-blockers"><strong>归档被阻止</strong><ul>{plan.blockers.map((code) => { const copy = blockerCopy(code); return <li key={code}><span>{copy.text}</span><span className="subtle-copy">错误代码：<code title={code}>{code}</code></span></li>; })}</ul></div>}
          {hasPendingBlocker && <>
            <p>有 {pendingCount} 个待审核的提交，审核通过、退回或撤回后才能归档：{pendingIds.map((id) => onSelectSubmission
              ? <button key={id} className="link-button" onClick={() => { onClose(); onSelectSubmission(id); }}>{displayName(id)}</button>
              : <span key={id}>{displayName(id)}</span>).reduce<ReactNode[]>((nodes, node, index) => index === 0 ? [node] : [...nodes, "、", node], [])}</p>
            <p className="subtle-copy">只有上传或预览、尚未提交的工作区不影响归档。</p>
          </>}
          <Button variant="secondary" onClick={refresh} disabled={loading || running}>重新预检</Button>
        </section>

        <section className="archive-step" aria-label="归档选择确认">
          <h3>归档选择确认</h3>
          <label className="confirm-checkbox"><input type="checkbox" checked={confirmSelection} onChange={(event) => setConfirmSelection(event.currentTarget.checked)} />确认把“{submissionId ? displayName(submissionId) : "—"}”归档为新的业务基线</label>
        </section>

        <section className="archive-step" aria-label="业务核验">
          <h3>业务核验</h3>
          {validation && <>
            <table className="archive-overview">
              <thead><tr><th>提交</th><th>原始组态来源</th><th>生成时间比较</th></tr></thead>
              <tbody>{validation.source_diagnostics.map((diagnostic) => {
                const comparisons = validation.time_comparisons.filter((comparison) => comparison.submission_id === diagnostic.submission_id);
                const origin = diagnostic.detected_status === "EXPLAINED"
                  ? `已解释${diagnostic.matching_sources.map((source) => source.source_kind === "BASELINE" ? "（当前基线）" : `（${displayName(source.submission_id ?? "")} 的 ${source.side === "INITIAL" ? "①" : "②"}）`).join("、")}${diagnostic.initial_origin === "BASELINE_REUSED" ? "，沿用当前基线（只上传了本次归档组态）" : ""}${diagnostic.rules_identity_differs_from_baseline ? "，规则版本与当前基线不同" : ""}`
                  : diagnostic.detected_status === "NOT_APPLICABLE" ? "不适用（首次归档）" : "未解释";
                return <tr key={diagnostic.submission_id}>
                  <td>{displayName(diagnostic.submission_id)}{plan.selected?.submission_id === diagnostic.submission_id ? "（选中）" : ""}</td>
                  <td>{origin}</td>
                  <td>{comparisons.length === 0 ? "—" : comparisons.map((comparison, index) => <span key={index}>{RELATION_COPY[comparison.relation] ?? comparison.relation}：{COMPARISON_STATUS_COPY[comparison.detected_status] ?? comparison.detected_status}{comparison.left_time_utc || comparison.right_time_utc ? `（${comparison.left_time_utc ? formatServerTimeUtc(comparison.left_time_utc) : "—"} ／ ${comparison.right_time_utc ? formatServerTimeUtc(comparison.right_time_utc) : "—"}）` : ""}{index < comparisons.length - 1 ? "；" : ""}</span>)}</td>
                </tr>;
              })}</tbody>
            </table>
          </>}
          <p className="subtle-copy">待处理项 未处理 {unprocessedCount} ／ 共 {anomalies.length}</p>
          {GROUP_DEFS.map((group) => renderGroup(group.key, group.title))}
        </section>

        <section className="archive-step" aria-label="候选提交">
          <h3>候选提交</h3>
          <ul>{candidates.candidates.map((candidate) => <li key={candidate.submission_id}>
            <span>{displayName(candidate.submission_id)}{candidate.submission_id === submissionId ? "（选中）" : ""} 已通过</span>
            <Button variant="secondary" onClick={() => openClose(candidate)}>关闭（不归档）</Button>
          </li>)}</ul>
        </section>

        <section className="archive-step" aria-label="确认后的影响">
          <h3>确认后的影响</h3>
          <p>归档成功后，所选提交会成为新的业务基线；其他候选会按预检结果归档或关闭。该操作不可撤销。</p>
          {plan.dispositions && plan.dispositions.length > 0 && <ul className="archive-impact">{plan.dispositions.map((item) => <li key={item.submission_id}><span>{displayName(item.submission_id)}</span>{item.disposition === "ARCHIVED_BASELINE" ? "归档为新基线" : "关闭且不归档"}</li>)}</ul>}
          {(plan.workspace_releases ?? []).length > 0 && <p className="subtle-copy">将释放 {plan.workspace_releases.length} 个工作区：{plan.workspace_releases.map((item) => item.workspace_id).join("、")}</p>}
        </section>

        {running && <p role="status" className="submit-progress">归档执行中，请勿关闭页面。</p>}
      </>}
      {result && <section className="archive-step" aria-label="归档结果">
        <h2>归档完成</h2>
        <dl className="confirm-summary">
          <div><dt>新基线</dt><dd>{result.baseline_node_id}</dd></div>
          <div><dt>基线版本</dt><dd>{result.baseline_head_version}</dd></div>
          <div><dt>归档提交</dt><dd>{displayName(result.selected_submission_id)}</dd></div>
          <div><dt>处理结果</dt><dd>归档 {archivedCount} 项，关闭 {closedCount} 项</dd></div>
        </dl>
        <p className="confirm-impact">新的业务基线已生成，工作台将刷新以显示最新 History。</p>
      </section>}
    </Dialog>

    <Dialog open={open && acceptTarget !== null} title="接受异常" description="接受表示你已核对该问题并说明理由。" onClose={() => { if (!acceptBusy) setAcceptTarget(null); }} actions={<>
      <Button variant="secondary" onClick={() => setAcceptTarget(null)} disabled={acceptBusy}>取消</Button>
      <Button variant="primary" onClick={() => void submitResolution("accept")} disabled={acceptBusy || acceptLimitError !== undefined} disabledReason={acceptLimitError}>{acceptBusy ? "提交中…" : "确认接受"}</Button>
    </>}>
      {acceptTarget && <>
        <p><strong>{displayName(acceptTarget.target_submission_id)}{acceptTarget.side ? ` · ${SIDE_COPY[acceptTarget.side] ?? acceptTarget.side}` : ""}：{ISSUE_COPY[acceptTarget.issue_code] ?? acceptTarget.issue_code}</strong></p>
        <p>受影响提交：{acceptTarget.affected_submission_ids.map(displayName).join("、") || "—"}</p>
        <p className="confirm-impact">接受表示你已核对该问题并说明理由。原始诊断不会改为通过，接受记录会写入归档审计，可以撤销。</p>
        {renderReasonField("accept", acceptReason, setAcceptReason, "接受理由")}
        {acceptError && <div role="alert" className="form-error"><span>{acceptError.title}</span><span>错误代码：<code>{acceptError.code}</code></span></div>}
      </>}
    </Dialog>

    <Dialog open={open && revokeTarget !== null} title="撤销接受" description="撤销后该项回到需要处理的状态。" onClose={() => { if (!revokeBusy) setRevokeTarget(null); }} actions={<>
      <Button variant="secondary" onClick={() => setRevokeTarget(null)} disabled={revokeBusy}>取消</Button>
      <Button variant="danger" onClick={() => void submitResolution("revoke")} disabled={revokeBusy || revokeLimitError !== undefined} disabledReason={revokeLimitError}>{revokeBusy ? "提交中…" : "确认撤销"}</Button>
    </>}>
      {revokeTarget && <>
        <p><strong>{displayName(revokeTarget.target_submission_id)}{revokeTarget.side ? ` · ${SIDE_COPY[revokeTarget.side] ?? revokeTarget.side}` : ""}：{ISSUE_COPY[revokeTarget.issue_code] ?? revokeTarget.issue_code}</strong></p>
        <p className="confirm-impact">撤销后该项回到需要处理的状态，归档前需要重新接受。</p>
        {renderReasonField("revoke", revokeReason, setRevokeReason, "撤销理由")}
        {revokeError && <div role="alert" className="form-error"><span>{revokeError.title}</span><span>错误代码：<code>{revokeError.code}</code></span></div>}
      </>}
    </Dialog>

    <Dialog open={open && closeTarget !== null} title="关闭提交（不归档）" description="关闭后该提交保留已通过记录，不会成为基线。" onClose={() => { if (!closeBusy) { setCloseTarget(null); } }} actions={<>
      <Button variant="secondary" onClick={() => setCloseTarget(null)} disabled={closeBusy}>取消</Button>
      <Button variant="danger" onClick={() => void submitClose()} disabled={closeBusy || !closeUnderstood || closeLimitError !== undefined || closeResult !== null} disabledReason={closeResult ? undefined : !closeUnderstood ? "请确认已了解关闭不可撤销" : closeLimitError}>{closeBusy ? "提交中…" : "确认关闭"}</Button>
    </>}>
      {closeTarget && <>
        <p>关闭提交{displayName(closeTarget.submission_id)}（不归档）。</p>
        <ul className="confirm-impact">
          <li>该提交保留“已通过”的审核记录，标记为“已关闭（未归档）”，不会成为基线；</li>
          <li>提交人的工作区被释放，当前上传与预览被清空，需要重新上传、预览并提交；</li>
          <li>当前基线不变；</li>
          <li>关闭后其余候选的核验结果可能变化，需要重新处理；</li>
          <li>关闭不可撤销。</li>
        </ul>
        {renderReasonField("close", closeReason, setCloseReason, "关闭理由")}
        <label className="confirm-checkbox"><input type="checkbox" checked={closeUnderstood} onChange={(event) => setCloseUnderstood(event.currentTarget.checked)} />我已了解关闭不可撤销</label>
        {closeErrorState && <div role="alert" className="form-error"><span>{closeErrorState.title}</span><span>错误代码：<code>{closeErrorState.code}</code></span><span className="form-error__actions">{closeRetry && <Button variant="secondary" onClick={() => void retryClose()} disabled={closeBusy}>重试</Button>}</span></div>}
        {closeResult && <div role="status" aria-label="关闭结果" className="confirm-impact"><p>已关闭。</p>
          <p>关闭人：{closeResult.closed_by}；关闭时间：{formatServerTimeUtc(closeResult.closed_at)}；理由：{closeResult.reason}</p>
        </div>}
      </>}
    </Dialog>
  </>;
}
