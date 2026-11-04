import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { ArrowDown, ArrowUp, Check, ChevronDown, ChevronLeft, ChevronRight, Copy, Folder, GitBranch, GitCommitHorizontal, Layers, Plus, RefreshCw, Search, Trash2, X } from "lucide-react";
import type { components } from "../features/api/generated/openapi";
import { gatewayApi } from "../features/api/application-api";
import { readHistoryCompareIntent, requestWithTimeout, resolveHistoryCompareIntent, type IdempotentIntent } from "../features/api/idempotency";
import { ApiError } from "../features/api/authenticated-fetch";
import { reportConnectionStatus } from "../features/api/connection-status";
import { PollingConnectionLostError, pollHistoryCompare } from "../features/api/journeys";
import { currentGatewaySession, historyCompareRequestTimeoutMs } from "../features/api/session";
import { ensureLocalBundle, OpfsBundleStore, type InstalledBundle } from "../features/bundle/local-bundle";
import { ConnectionStatusIndicator } from "../design-system/ConnectionStatusIndicator";
import { ErrorState, LoadingSkeleton } from "../design-system/components";
import { OperationStatusPanel } from "../features/workbench/OperationStatusPanel";
import { UploadStepCard, type UploadStepCardHandle } from "../features/workbench/UploadStepCard";
import { ArchiveMainlineDialog } from "../features/workbench/ArchiveMainlineDialog";
import { formatWaitDuration } from "../features/workbench/wait-duration";
import { summarizeHistoryPair, type HistoryPairSummary } from "../features/workbench/history-summary";
import { buildWorkspaceTree, deriveWorkbenchActions, sortWorkspaceTreeRows, type WorkbenchActionId, type WorkspaceTreeRow } from "../features/view-model/workspace";
import { WORKSPACE_STATE_COPY } from "../features/view-model/workspace-state-copy";

type Schemas = components["schemas"];
type SortColumn = "label" | "createdAt" | "submitAt" | "reviewAt";
const DEFAULT_COLUMN_WIDTHS = [520, 240, 210, 190];

function refKey(ref: Schemas["HistoryCompareNodeRequest"]): string {
  return `${ref.ref_kind}:${ref.ref_id}`;
}

function historyRef(row: WorkspaceTreeRow): Schemas["HistoryCompareNodeRequest"] | null {
  return row.refId && row.refKind ? { ref_kind: row.refKind, ref_id: row.refId } : null;
}

function pageUrl(page: "workspace" | "compare", extra: Record<string, string | null | undefined> = {}, compareNodes: Schemas["HistoryCompareNodeRequest"][] = []): string {
  const params = new URLSearchParams({ page });
  for (const [key, value] of Object.entries(extra)) if (value) params.set(key, value);
  for (const node of compareNodes) params.append("compare", refKey(node));
  return `/?${params.toString()}`;
}

function isTemporaryError(cause: unknown): boolean {
  return cause instanceof TypeError || cause instanceof DOMException && cause.name === "TimeoutError"
    || cause instanceof ApiError && (cause.status === 429 || cause.status >= 500);
}

function messageFrom(cause: unknown): { code: string; message: string } {
  if (cause instanceof ApiError) return { code: cause.code ?? `HTTP_${cause.status}`, message: cause.message };
  return { code: cause instanceof Error ? cause.name : "REQUEST_FAILED", message: cause instanceof Error ? cause.message : String(cause) };
}

function statusClass(tone: WorkspaceTreeRow["statusTone"]): string { return `tree-status tree-status--${tone}`; }

function showOperationForCompare(operationId: string | null, state: Schemas["HistoryCompareResultResponse"] | null): boolean {
  return Boolean(operationId && (!state || state.status === "QUEUED" || state.status === "RUNNING"));
}

export function WorkbenchPage({ identityControl }: { identityControl?: ReactNode }) {
  const [data, setData] = useState<{ workspace: Schemas["WorkspaceResponse"]; history: Schemas["HistoryListResponse"] } | null>(null);
  const [loadError, setLoadError] = useState<{ code: string; message: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [currentBaselineOnly, setCurrentBaselineOnly] = useState(false);
  const [selectedKey, setSelectedKey] = useState("");
  const [detailExpanded, setDetailExpanded] = useState(() => window.innerWidth > 1440);
  const [compareRefs, setCompareRefs] = useState<Schemas["HistoryCompareNodeRequest"][]>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.getAll("compare").flatMap((raw) => {
      const split = raw.indexOf(":");
      if (split < 0) return [];
      const kind = raw.slice(0, split);
      return kind === "baseline_node" || kind === "submission" ? [{ ref_kind: kind, ref_id: raw.slice(split + 1) }] : [];
    });
  });
  const [columnWidths, setColumnWidths] = useState(DEFAULT_COLUMN_WIDTHS);
  const [sort, setSort] = useState<{ column: SortColumn; direction: 1 | -1 } | null>(null);
  const [collapsedNodes, setCollapsedNodes] = useState<Set<string>>(() => new Set());
  const [compareIntent, setCompareIntent] = useState<IdempotentIntent<Schemas["HistoryCompareAcceptRequest"]> | null>(() => {
    try { return readHistoryCompareIntent(window.sessionStorage.getItem("gateway-history-compare-pending-intent")); }
    catch { return null; }
  });
  const [compareStartError, setCompareStartError] = useState<{ code: string; message: string } | null>(() => compareIntent
    ? { code: "REQUEST_UNCONFIRMED", message: "上次请求结果尚未确认，可使用同一请求重试。" }
    : null);
  const [comparePending, setComparePending] = useState(false);
  const [compareState, setCompareState] = useState<Schemas["HistoryCompareResultResponse"] | null>(null);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [compareConnectionLost, setCompareConnectionLost] = useState(false);
  const [refreshCompare, setRefreshCompare] = useState(0);
  const [compareElapsed, setCompareElapsed] = useState(0);
  const [bundleStatus, setBundleStatus] = useState<"idle" | "downloading" | "ready" | "failed">("idle");
  const [downloadRevision, setDownloadRevision] = useState(0);
  const [historyBundle, setHistoryBundle] = useState<InstalledBundle | null>(null);
  const [pairSummaries, setPairSummaries] = useState<Record<string, HistoryPairSummary>>({});
  const [pairSummaryError, setPairSummaryError] = useState<string | null>(null);
  const uploadRef = useRef<UploadStepCardHandle>(null);
  const [pendingUploadAction, setPendingUploadAction] = useState<"initial" | "modified" | "start" | null>(null);
  const [resumePreviewOperation] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get("operationId");
    return Boolean(id && params.get("operationKind") !== "history-compare" && sessionStorage.getItem("gateway-preview-operation") === id);
  });
  const resumePending = useRef(resumePreviewOperation);
  const [uploadLocked, setUploadLocked] = useState(resumePreviewOperation);
  const [uploadReady, setUploadReady] = useState(false);
  const [uploadBlockedReason, setUploadBlockedReason] = useState<string | null>(null);
  const [archiveSubmissionId, setArchiveSubmissionId] = useState<string | null>(null);
  const operationId = new URLSearchParams(window.location.search).get("operationId");
  const operationKind = new URLSearchParams(window.location.search).get("operationKind");
  const historyCompareOperationId = operationKind === "history-compare" ? operationId : null;
  const pendingIntentKey = "gateway-history-compare-pending-intent";
  const searchRef = useRef<HTMLInputElement>(null);

  const resumePreviewFromOperation = useCallback(async (finishedOperationId: string) => {
    if (sessionStorage.getItem("gateway-preview-operation") !== finishedOperationId) return;
    const session = currentGatewaySession();
    try {
      const workspace = await gatewayApi.createWorkspace({ business_project_id: session.businessProjectId, gateway_device_external_key: session.gatewayDeviceExternalKey });
      const previewResultId = workspace.current_preview_result_id;
      if (!previewResultId) { setUploadLocked(false); return; }
      const preview = await gatewayApi.getPreviewResult(workspace.workspace_id, previewResultId);
      await ensureLocalBundle({ store: new OpfsBundleStore(), expectedBundleDigest: preview.bundle_digest, fetchBundle: () => gatewayApi.getPreviewBundle(workspace.workspace_id, previewResultId) });
      resumePending.current = false;
      sessionStorage.removeItem("gateway-preview-operation");
      window.location.assign(pageUrl("compare", { mode: "PREVIEW", workspaceId: workspace.workspace_id, previewResultId, workbenchNode: selectedKey }, compareRefs));
    } catch {
      resumePending.current = false;
      sessionStorage.removeItem("gateway-preview-operation");
      setUploadLocked(false);
    }
  }, [compareRefs, selectedKey]);

  const load = useCallback(async () => {
    const session = currentGatewaySession();
    if (!session.businessProjectId || !session.gatewayDeviceExternalKey) {
      setLoadError({ code: "SESSION_REQUIRED", message: "当前会话没有业务项目与网关设备身份" });
      setData(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setLoadError(null);
    try {
      const [workspace, history] = await Promise.all([
        gatewayApi.createWorkspace({ business_project_id: session.businessProjectId, gateway_device_external_key: session.gatewayDeviceExternalKey }),
        gatewayApi.listHistory(),
      ]);
      setData({ workspace, history });
      setLoadError(null);
    } catch (cause) {
      const message = messageFrom(cause);
      if (isTemporaryError(cause)) reportConnectionStatus("interrupted");
      setLoadError(message);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const onSessionChange = () => { void load(); };
    window.addEventListener("gateway-session-change", onSessionChange);
    return () => window.removeEventListener("gateway-session-change", onSessionChange);
  }, [load]);

  const rows = useMemo(() => data ? buildWorkspaceTree(data.workspace, data.history, compareRefs) : [], [data, compareRefs]);
  useEffect(() => {
    if (!rows.length) return;
    const queryNode = new URLSearchParams(window.location.search).get("workbenchNode");
    const found = queryNode && rows.some((row) => row.key === queryNode) ? queryNode : rows.find((row) => row.kind === "workspace")?.key ?? rows[0]?.key;
    setSelectedKey((current) => current && rows.some((row) => row.key === current) ? current : found ?? "");
  }, [rows]);
  useEffect(() => {
    if (!selectedKey || !rows.some((row) => row.key === selectedKey)) return;
    const url = new URL(window.location.href);
    if (url.searchParams.get("workbenchNode") === selectedKey) return;
    url.searchParams.set("workbenchNode", selectedKey);
    window.history.replaceState(null, "", url);
  }, [rows, selectedKey]);
  const rowByKey = useMemo(() => new Map(rows.map((row) => [row.key, row])), [rows]);
  const selected = rowByKey.get(selectedKey) ?? null;
  const comparedKeys = useMemo(() => new Set(compareRefs.map(refKey)), [compareRefs]);
  const comparisonLocked = comparePending || showOperationForCompare(historyCompareOperationId, compareState)
    || Boolean(historyCompareOperationId && compareState?.status === "SUCCEEDED" && bundleStatus === "downloading");
  const actions = useMemo(() => deriveWorkbenchActions(selected, compareRefs.length, selected ? comparedKeys.has(selected.key) : false, comparisonLocked), [selected, compareRefs.length, comparedKeys, comparisonLocked]);

  const visibleRows = useMemo(() => {
    const query = filter.trim().toLocaleLowerCase();
    const rowMap = new Map(rows.map((row) => [row.key, row]));
    const matches = new Set(rows.filter((row) => (!currentBaselineOnly || row.isHead || row.kind === "workspace")
      && (!query || `${row.label} ${row.status} ${row.refId ?? ""}`.toLocaleLowerCase().includes(query))).map((row) => row.key));
    if (query) for (const key of [...matches]) {
      let parent = rowMap.get(key)?.parentKey ?? null;
      while (parent) { matches.add(parent); parent = rowMap.get(parent)?.parentKey ?? null; }
    }
    const filtered = rows.filter((row) => matches.has(row.key));
    return sortWorkspaceTreeRows(filtered, sort).filter((row) => {
      let parent = row.parentKey;
      while (parent) {
        if (collapsedNodes.has(parent)) return false;
        parent = rowMap.get(parent)?.parentKey ?? null;
      }
      return true;
    });
  }, [rows, filter, currentBaselineOnly, sort, collapsedNodes]);

  const setCompareSelection = (next: Schemas["HistoryCompareNodeRequest"][]) => {
    if (comparisonLocked) return;
    setCompareRefs(next.slice(0, 3));
    setCompareIntent(null);
    setCompareStartError(null);
    try { window.sessionStorage.removeItem(pendingIntentKey); } catch { /* storage is optional */ }
    const url = new URL(window.location.href);
    url.searchParams.delete("compare");
    for (const node of next.slice(0, 3)) url.searchParams.append("compare", refKey(node));
    window.history.replaceState(null, "", url);
  };

  const toggleCompare = (row: WorkspaceTreeRow) => {
    const ref = historyRef(row);
    if (!ref) return;
    const current = [...compareRefs];
    const existingIndex = current.findIndex((item) => refKey(item) === refKey(ref));
    if (existingIndex >= 0) current.splice(existingIndex, 1);
    else if (current.length < 3) current.push(ref);
    setCompareSelection(current);
  };

  const openPreview = (pair?: string) => {
    if (!data?.workspace.current_preview_result_id) return;
    window.location.assign(pageUrl("compare", {
      mode: "PREVIEW", workspaceId: data.workspace.workspace_id,
      previewResultId: data.workspace.current_preview_result_id, workbenchNode: selectedKey, pair,
    }, compareRefs));
  };

  const openReview = (row: WorkspaceTreeRow) => {
    if (!row.refId) return;
    window.location.assign(pageUrl("compare", { mode: "REVIEW", submissionId: row.refId, workbenchNode: selectedKey }, compareRefs));
  };

  const sendHistoryCompare = async (intent: IdempotentIntent<Schemas["HistoryCompareAcceptRequest"]>) => {
    setComparePending(true);
    setCompareStartError(null);
    try {
      const accepted = await requestWithTimeout(gatewayApi.startHistoryCompare(intent.request, intent.key), historyCompareRequestTimeoutMs());
      setCompareIntent(null);
      try { window.sessionStorage.removeItem(pendingIntentKey); } catch { /* storage is optional */ }
      const compareParams: Record<string, string> = {
        page: "workspace", operationId: accepted.operation_id, operationKind: "history-compare", workbenchNode: selectedKey,
      };
      window.location.assign(pageUrl("workspace", compareParams, intent.request.nodes));
    } catch (cause) {
      if (isTemporaryError(cause)) reportConnectionStatus("interrupted");
      const info = messageFrom(cause);
      setCompareStartError(cause instanceof ApiError && (cause.status === 403 || cause.code === "SCOPE_FORBIDDEN")
        ? { code: "SCOPE_FORBIDDEN", message: "当前身份没有该操作的权限" }
        : cause instanceof DOMException && cause.name === "TimeoutError"
          ? { code: "TimeoutError", message: "请求超时；历史比较可能已经受理。使用同一请求重试会复用幂等结果。" }
          : { code: info.code, message: info.message });
    } finally {
      setComparePending(false);
    }
  };

  const startOrRetryCompare = (request: Schemas["HistoryCompareAcceptRequest"] = { nodes: compareRefs }) => {
    if (comparePending) return;
    let intent = compareIntent;
    if (!intent) {
      try {
        const saved = window.sessionStorage.getItem(pendingIntentKey);
        if (saved) intent = readHistoryCompareIntent(saved);
      } catch { /* create a new intent when storage is unavailable or invalid */ }
    }
    intent = resolveHistoryCompareIntent(intent, request);
    try { window.sessionStorage.setItem(pendingIntentKey, JSON.stringify(intent)); } catch { /* in-memory retry still reuses the key */ }
    setCompareRefs(intent.request.nodes);
    const url = new URL(window.location.href);
    url.searchParams.delete("compare");
    for (const node of intent.request.nodes) url.searchParams.append("compare", refKey(node));
    window.history.replaceState(null, "", url);
    setCompareIntent(intent);
    void sendHistoryCompare(intent);
  };

  useEffect(() => {
    if (!historyCompareOperationId) return;
    const controller = new AbortController();
    const startedAt = Date.now();
    setCompareState({ operation_id: historyCompareOperationId, status: "QUEUED", diagnostic: null });
    setBundleStatus("idle");
    setCompareError(null);
    setCompareConnectionLost(false);
    setCompareElapsed(0);
    const ticker = window.setInterval(() => setCompareElapsed(Math.floor((Date.now() - startedAt) / 1_000)), 1_000);
    void pollHistoryCompare(gatewayApi, historyCompareOperationId, {
      signal: controller.signal,
      onUpdate: (value) => { setCompareState(value); setCompareConnectionLost(false); },
      onConnectionStatus: (status) => setCompareConnectionLost(status === "interrupted"),
    }).then(async (result) => {
      if (result.status !== "SUCCEEDED" || !result.result) {
        setCompareError(result.diagnostic?.message ?? "历史比较未能完成");
        setBundleStatus("idle");
        return;
      }
      setBundleStatus("downloading");
      try {
        const installed = await ensureLocalBundle({
          store: new OpfsBundleStore(), expectedBundleDigest: result.result.bundle_digest,
          fetchBundle: () => gatewayApi.getHistoryBundle(historyCompareOperationId, controller.signal),
        });
        setHistoryBundle(installed);
        setCompareError(null);
        setBundleStatus("ready");
      } catch (cause) {
        if (controller.signal.aborted) return;
        setCompareError(cause instanceof Error ? cause.message : String(cause));
        setBundleStatus("failed");
      }
    }).catch((cause: unknown) => {
      if (controller.signal.aborted) return;
      if (cause instanceof PollingConnectionLostError) {
        setCompareConnectionLost(true);
        reportConnectionStatus("interrupted");
      } else {
        setCompareError(cause instanceof Error ? cause.message : String(cause));
      }
    });
    return () => { controller.abort(new DOMException("比较状态查询已停止", "AbortError")); window.clearInterval(ticker); };
  }, [historyCompareOperationId, refreshCompare, downloadRevision]);

  const resizeColumn = (index: number, event: ReactPointerEvent<HTMLButtonElement>) => {
    const startX = event.clientX;
    const initialWidth = columnWidths[index] ?? DEFAULT_COLUMN_WIDTHS[index] ?? 180;
    const move = (pointer: PointerEvent) => setColumnWidths((values) => values.map((value, current) => current === index ? Math.max(120, initialWidth + pointer.clientX - startX) : value));
    const finish = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", finish); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", finish, { once: true });
  };

  const sortBy = (column: SortColumn) => setSort((state) => state?.column === column ? { column, direction: state.direction === 1 ? -1 : 1 } : { column, direction: 1 });
  const sortIcon = (column: SortColumn) => sort?.column === column ? sort.direction === 1 ? <ArrowUp size={12} /> : <ArrowDown size={12} /> : null;

  const runAction = (id: WorkbenchActionId) => {
    if (!selected || comparisonLocked && (id === "join-compare" || id === "remove-compare" || id === "view-diff")) return;
    if (id === "join-compare" || id === "remove-compare") toggleCompare(selected);
    else if (id === "view-diff") {
      if (selected.kind === "submission" && selected.reviewStatus === "PENDING") openReview(selected);
      else {
        const currentRef = historyRef(selected);
        if (currentRef && selected.parentRef) {
          startOrRetryCompare({ nodes: [{ ref_kind: selected.parentRef.ref_kind, ref_id: selected.parentRef.ref_id }, currentRef] });
        }
      }
    } else if (id === "archive-mainline" && selected?.kind === "submission" && selected.refId) {
      setArchiveSubmissionId(selected.refId);
    } else if (id === "original-backup" || id === "current-archive" || id === "upload") {
      setDetailExpanded(true);
      setPendingUploadAction(id === "original-backup" ? "initial" : id === "current-archive" ? "modified" : "start");
    }
  };

  useEffect(() => {
    if (!pendingUploadAction) return;
    if (selected?.kind !== "workspace") {
      const workspaceRow = rows.find((row) => row.kind === "workspace");
      if (workspaceRow) setSelectedKey(workspaceRow.key);
      return;
    }
    setDetailExpanded(true);
    const frame = window.requestAnimationFrame(() => {
      const handle = uploadRef.current;
      if (!handle) return;
      if (pendingUploadAction === "initial") handle.chooseInitial();
      else if (pendingUploadAction === "modified") handle.chooseModified();
      else handle.start();
      setPendingUploadAction(null);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [pendingUploadAction, selected?.kind, rows]);

  useEffect(() => {
    if (!historyBundle || compareState?.status !== "SUCCEEDED" || !compareState.result) {
      setPairSummaries({});
      return;
    }
    let cancelled = false;
    setPairSummaryError(null);
    void Promise.all(compareState.result.pairs.map(async (pair) => [pair.pair_id, await summarizeHistoryPair(historyBundle, pair.pair_id)] as const))
      .then((entries) => { if (!cancelled) setPairSummaries(Object.fromEntries(entries)); })
      .catch((cause: unknown) => { if (!cancelled) setPairSummaryError(cause instanceof Error ? cause.message : String(cause)); });
    return () => { cancelled = true; };
  }, [historyBundle, compareState]);

  const effectiveActions = actions.map((action) => action.id === "upload"
    ? { ...action, enabled: action.enabled && uploadReady, reason: uploadBlockedReason ?? action.reason }
    : action);

  const showHistoryDrawer = Boolean(historyCompareOperationId);
  const showOperationStatus = operationId !== null && (operationKind === null || operationKind === "operation");

  if (loading) return <main className="workspace-page"><LoadingSkeleton label="加载工作区与 History" /></main>;
  if (loadError || !data) return <main className="workspace-page workspace-page--error"><ErrorState code={loadError?.code ?? "WORKSPACE_LOAD_FAILED"} title={loadError?.code === "SCOPE_FORBIDDEN" ? "当前身份没有该操作的权限" : undefined} details={loadError?.message ?? "工作区加载失败"} onRetry={() => void load()} /><ConnectionStatusIndicator hideConnected />{identityControl}</main>;

  const compareLabels = compareRefs.map((ref) => rows.find((row) => row.key === refKey(ref))?.label ?? ref.ref_id);
  const selectedReviewFacts = selected?.kind === "submission" && compareState?.status === "SUCCEEDED" ? "审核信息按只读模式加载" : null;
  return <main className={`workspace-page${detailExpanded ? " details-open" : " details-collapsed"}${uploadLocked ? " workspace-page--uploading" : ""}`}>
    {uploadLocked && <div className="page-lock-overlay" role="presentation" {...{ inert: true } as object}><p>上传与预览执行中，页面其余操作已锁定</p></div>}
    <header className="workspace-topbar">
      <div className="workspace-brand"><strong>网关数据工作台</strong><span>{data.workspace.gateway_device_external_key}</span></div>
      <div className="workspace-topbar__right">{(showHistoryDrawer || showOperationStatus) && <span className="task-indicator"><RefreshCw size={13} />{showHistoryDrawer ? "历史比较" : "操作状态"}</span>}<ConnectionStatusIndicator />{identityControl}</div>
    </header>
    <div className="workspace-layout">
      <section className="workspace-main" aria-label="组态树工作台">
        <div className="workspace-tree-heading"><h1>组态树</h1><label className="workspace-search"><Search size={15} /><input ref={searchRef} aria-label="搜索工作区与 History 节点" placeholder="搜索节点" value={filter} onChange={(event) => setFilter(event.currentTarget.value)} /></label><span className="workspace-tree-heading__spacer" />
          <label className="workspace-checkbox"><input type="checkbox" checked={currentBaselineOnly} onChange={(event) => setCurrentBaselineOnly(event.currentTarget.checked)} />只显示当前基线</label>
        </div>
        {showOperationStatus && <OperationStatusPanel operationId={operationId} onSucceeded={resumePreviewOperation ? (id) => void resumePreviewFromOperation(id) : undefined} onFailed={resumePreviewOperation ? () => { resumePending.current = false; sessionStorage.removeItem("gateway-preview-operation"); setUploadLocked(false); } : undefined} />}
        <div className="workspace-context-bar" aria-label="上下文工具栏">
          <div className="workspace-context-bar__selection"><span className="node-type-icon">{selected?.kind === "workspace" ? <Folder size={16} /> : selected?.kind === "baseline" ? <Layers size={16} /> : <GitCommitHorizontal size={16} />}</span><strong>{selected?.label ?? "未选择节点"}</strong>{selected?.status && <span className={statusClass(selected.statusTone)}><i aria-hidden="true" />{selected.status}</span>}{selected?.eligibilityNote && <span className="status-tag status-tag--warning">基线已更新</span>}{selected?.identityException && <span className="status-tag status-tag--neutral">项目身份例外</span>}</div>
          <div className="workspace-actions">{effectiveActions.map((action) => <div className="workspace-action" key={action.id}>
            <button className={`button ${action.id === "archive-mainline" ? "button--primary" : "button--secondary"}`} disabled={!action.enabled} title={action.reason ?? undefined} onClick={() => runAction(action.id)}>
              {action.id === "join-compare" ? <Plus size={14} /> : action.id === "remove-compare" ? <X size={14} /> : null}{action.label}
            </button>
            {!action.enabled && <span className="disabled-reason" title={action.reason ?? undefined}>{action.reason}</span>}
          </div>)}</div>
        </div>
        <div className="workspace-table-scroll">
          <table className="workspace-table" aria-label="History 组态树">
            <colgroup>{columnWidths.map((width, index) => <col key={index} style={{ width }} />)}</colgroup>
            <thead><tr>
              {([["label", "节点 / 描述"], ["createdAt", "组态生成时间"], ["submitAt", "提交时间"], ["reviewAt", "审核时间"]] as Array<[SortColumn, string]>).map(([column, label], index) => <th key={column} scope="col"><button onClick={() => sortBy(column)}>{label}{sortIcon(column)}</button><button className="column-resize" aria-label={`调整${label}列宽`} onPointerDown={(event) => resizeColumn(index, event)} /></th>)}
            </tr></thead>
            <tbody>{visibleRows.map((row) => <tr key={row.key} className={selectedKey === row.key ? "is-selected" : ""} aria-selected={selectedKey === row.key} onClick={() => setSelectedKey(row.key)}>
              <td><div className="workspace-tree-cell" style={{ paddingLeft: 14 + row.depth * 26 }}>
                {row.hasChildren ? <button className="workspace-tree-toggle" aria-label={`${collapsedNodes.has(row.key) ? "展开" : "折叠"}${row.label}`} aria-expanded={!collapsedNodes.has(row.key)} onClick={(event) => { event.stopPropagation(); setCollapsedNodes((current) => { const next = new Set(current); if (next.has(row.key)) next.delete(row.key); else next.add(row.key); return next; }); }}>{collapsedNodes.has(row.key) ? <ChevronRight size={14} /> : <ChevronDown size={14} />}</button> : <span className="workspace-tree-toggle-placeholder" />}
                {row.kind === "baseline" ? <Layers size={16} /> : row.kind === "workspace" ? <Folder size={16} /> : row.kind === "migration" ? <GitBranch size={16} /> : <GitCommitHorizontal size={16} />}
                <button className="workspace-node-label" onClick={() => setSelectedKey(row.key)}>{row.label}</button>
                {row.status && <span className={statusClass(row.statusTone)}><i aria-hidden="true" />{row.status}</span>}
                {row.compareOrder && <span className="compare-order" title={`比较节点 ${row.compareOrder}`}>比较 {row.compareOrder}</span>}
                {row.eligibilityNote && <span className="status-tag status-tag--warning" title="该提交所基于的基线已不是当前基线，不能归档">基线已更新</span>}
                {row.identityException && <span className="status-tag status-tag--neutral" title="项目身份例外">项目身份例外</span>}
              </div></td>
              <td>{row.createdAt ? new Date(row.createdAt).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }) : "—"}</td>
              <td>{row.submitAt ? new Date(row.submitAt).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }) : "—"}</td>
              <td>{row.reviewAt ? new Date(row.reviewAt).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }) : "—"}</td>
            </tr>)}</tbody>
          </table>
        </div>
        <div className="compare-tray" aria-label="比较托盘">
          <div className="compare-tray__label"><GitBranch size={17} /><strong>比较托盘</strong>{compareRefs.length > 0 && <span>{compareRefs.length} / 3</span>}{compareLabels.length === 0 && <small>选择 2–3 个基线或提交节点</small>}</div>
          <div className="compare-tray__items">{compareRefs.map((node, index) => <div className="compare-chip" key={refKey(node)}><span>{index + 1}</span>{compareLabels[index]}<button aria-label={`移除${compareLabels[index]}`} disabled={comparisonLocked} onClick={() => setCompareSelection(compareRefs.filter((item) => refKey(item) !== refKey(node)))}><X size={13} /></button></div>)}</div>
          <div className="compare-tray__actions"><button className="button button--ghost" disabled={!compareRefs.length || comparisonLocked} onClick={() => setCompareSelection([])}><Trash2 size={14} />清空比较</button>
            {compareStartError && <span role="alert" className="compare-tray__error" title={compareStartError.code}>{compareStartError.message}（{compareStartError.code}）<button className="icon-button" aria-label="复制比较错误详情" onClick={() => void navigator.clipboard?.writeText(`${compareStartError.code}\n${compareStartError.message}`)}><Copy size={13} /></button></span>}
            {compareIntent && compareStartError ? <button className="button button--primary" disabled={comparePending || comparisonLocked} onClick={() => startOrRetryCompare(compareIntent.request)}><RefreshCw size={14} />重试发起比较</button> : <button className="button button--primary" disabled={compareRefs.length < 2 || comparisonLocked} onClick={() => startOrRetryCompare()}>{comparisonLocked ? <RefreshCw size={14} /> : null}{comparisonLocked ? "比较中" : "历史比较"}</button>}
            {compareRefs.length < 2 && <small>至少选择 2 个节点</small>}
          </div>
        </div>
        {showHistoryDrawer && <section className="history-result-drawer" aria-label="历史比较结果抽屉">
          <div className="history-result-drawer__heading"><div><GitBranch size={16} /><strong>历史比较</strong><span className={`status-tag status-tag--${compareState?.status === "SUCCEEDED" ? "success" : compareState?.status === "FAILED" ? "warning" : "info"}`}>{compareConnectionLost ? "连接中断" : compareState?.status === "QUEUED" ? "排队中" : compareState?.status === "RUNNING" ? "执行中" : compareState?.status === "SUCCEEDED" ? "已完成" : compareState?.status === "FAILED" ? "失败" : compareState?.status === "CANCELLED" ? "已取消" : "查询中"}</span><small>已等待 {formatWaitDuration(compareElapsed)}</small></div>
            <div className="history-result-drawer__buttons">{compareConnectionLost && <button className="button button--secondary" onClick={() => setRefreshCompare((value) => value + 1)}><RefreshCw size={14} />重试查询</button>}
              {bundleStatus === "failed" && <button className="button button--secondary" onClick={() => { setCompareError(null); setDownloadRevision((value) => value + 1); }}><RefreshCw size={14} />重试下载</button>}
              {bundleStatus === "ready" && <button className="button button--primary" onClick={() => window.location.assign(pageUrl("compare", { mode: "HISTORY", operationId: historyCompareOperationId, operationKind: "history-compare", workbenchNode: selectedKey }, compareRefs))}>打开差异工作台</button>}
              <button className="icon-button" aria-label="收起历史比较结果" onClick={() => { const url = new URL(window.location.href); url.searchParams.delete("operationId"); url.searchParams.delete("operationKind"); window.history.replaceState(null, "", url); window.location.reload(); }}><ChevronDown size={17} /></button>
            </div>
          </div>
          {compareError && <p role="alert" className="history-result-drawer__error">{compareError}</p>}
          {compareState?.status === "SUCCEEDED" && <div className="history-result-drawer__body">
            <div className="history-result-drawer__nodes">{compareRefs.map((node, index) => <article key={refKey(node)}><span>{index + 1}</span><div><strong>{rows.find((row) => row.key === refKey(node))?.label ?? node.ref_id}</strong><small>{node.ref_kind === "baseline_node" ? "基线" : "提交"}</small></div><Check size={15} /></article>)}</div>
            <div className="history-result-drawer__pairs">{compareState.result?.pairs.map((pair, index) => {
              const summary = pairSummaries[pair.pair_id];
              return <div key={pair.pair_id} className="history-pair-summary"><span>比较对 {index + 1}</span><strong title={pair.pair_id}>节点 {index + 1} → 节点 {index + 2}</strong><small>{pair.record_count} 条差异记录</small>
                {summary && <div className="history-pair-summary__counts">
                  <span>表 {summary.tableCount}</span><span>变更 {summary.changedTableCount}</span><span className={summary.degradedTableCount > 0 ? "is-warning" : ""}>降级 {summary.degradedTableCount}</span>
                </div>}
                {summary && summary.tables.length > 0 && <details className="history-pair-summary__tables"><summary>每张表的新增 / 删除 / 修改行数</summary><table><thead><tr><th>表</th><th>新增</th><th>删除</th><th>修改</th></tr></thead><tbody>{summary.tables.map((table) => <tr key={table.tableName}><td title={table.tableName}>{table.displayName}</td><td>+{table.added}</td><td>−{table.deleted}</td><td>~{table.modified}</td></tr>)}</tbody></table></details>}
                {!summary && bundleStatus === "ready" && <small>正在读取本地 bundle 中的比较事实…</small>}
              </div>;
            })}</div>
            {pairSummaryError && <p role="alert" className="history-result-drawer__error">无法读取本地比较事实：{pairSummaryError}</p>}
            <p>{bundleStatus === "downloading" || bundleStatus === "idle" ? "下载中：正在校验 bundle。" : bundleStatus === "ready" ? "已就绪：bundle 已下载并校验。" : "下载失败，可重试。"}</p>
          </div>}
        </section>}
      </section>
      <aside className="workspace-details" aria-label="详情面板">
        <button className="workspace-details__toggle" aria-label={detailExpanded ? "折叠详情面板" : "展开详情面板"} onClick={() => setDetailExpanded((value) => !value)}>{detailExpanded ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}</button>
        {detailExpanded ? <div className="workspace-details__content">
          <p className="eyebrow">{selected?.kind === "workspace" ? "工作区详情" : selected?.kind === "submission" ? "提交详情" : "历史节点详情"}</p>
          <h2>{selected?.label ?? "未选择节点"}</h2><p className={selected ? statusClass(selected.statusTone) : "tree-status tree-status--neutral"}><i aria-hidden="true" />{selected?.status || "—"}</p>
          {selected?.kind === "workspace" && <>
            <dl className="details-list"><div><dt>网关设备</dt><dd>{data.workspace.gateway_device_external_key}</dd></div><div><dt>业务项目</dt><dd>{data.workspace.business_project_id}</dd></div><div><dt>工作区状态</dt><dd>{WORKSPACE_STATE_COPY[data.workspace.state as keyof typeof WORKSPACE_STATE_COPY] ?? "状态未知"}</dd></div><div><dt>组态代次</dt><dd>{data.workspace.generation}</dd></div><div><dt>当前 Preview</dt><dd>{data.workspace.current_preview_result_id ?? "—"}</dd></div></dl>
            <button className="button button--secondary workspace-details__action" disabled={!data.workspace.current_preview_result_id} title={data.workspace.current_preview_result_id ? undefined : "当前工作区还没有 Preview 结果"} onClick={() => openPreview("initial_to_modified")}>查看本次组态差异</button>
            {!data.workspace.current_preview_result_id && <p className="disabled-reason">当前工作区还没有 Preview 结果</p>}
            <UploadStepCard ref={uploadRef} head={data.history.head} emptyBaseline={data.history.nodes.some((node) => node.ref_id === data.history.head.node_id && node.parent === null)} onUploadStateChange={(active) => { if (active) resumePending.current = false; if (active || !resumePending.current) setUploadLocked(active); }} onReadyChange={(ready, reason) => { setUploadReady(ready); setUploadBlockedReason(reason); }}
              onComplete={(workspaceId, previewResultId) => window.location.assign(pageUrl("compare", { mode: "PREVIEW", workspaceId, previewResultId, workbenchNode: selectedKey }, compareRefs))} />
          </>}
          {selected?.kind !== "workspace" && selected && <dl className="details-list"><div><dt>节点类型</dt><dd>{selected.kind === "baseline" ? selected.baselineKind === "INITIAL" ? "初始基线" : "归档基线" : selected.kind === "submission" ? "提交" : "规则迁移"}</dd></div><div><dt>状态</dt><dd>{selected.status || "—"}</dd></div><div><dt>节点 ID</dt><dd>{selected.refId}</dd></div><div><dt>组态生成时间</dt><dd>{selected.createdAt ?? "—"}</dd></div>{selected.submitAt && <div><dt>提交时间</dt><dd>{selected.submitAt}</dd></div>}{selected.eligibilityNote && <div className="details-list__long"><dt>归档原因</dt><dd><details><summary>展开原因</summary>该提交所基于的基线已不是当前基线，不能归档</details></dd></div>}{selected.identityException && <div><dt>身份说明</dt><dd>项目身份例外</dd></div>}</dl>}
          {selectedReviewFacts && <p className="subtle-copy">{selectedReviewFacts}</p>}
        </div> : <div className="workspace-details__collapsed"><span>详情</span></div>}
      </aside>
    </div>
    <ArchiveMainlineDialog open={archiveSubmissionId !== null} submissionId={archiveSubmissionId} onClose={() => setArchiveSubmissionId(null)} onArchived={() => window.location.assign(pageUrl("workspace", {}, compareRefs))} />
  </main>;
}
