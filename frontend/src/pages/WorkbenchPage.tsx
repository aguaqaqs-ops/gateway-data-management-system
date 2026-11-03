import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { ArrowDown, ArrowUp, Check, ChevronDown, ChevronLeft, ChevronRight, Folder, GitBranch, GitCommitHorizontal, Layers, Plus, RefreshCw, Search, Trash2, X } from "lucide-react";
import type { components } from "../features/api/generated/openapi";
import { gatewayApi } from "../features/api/application-api";
import { createIdempotentIntent, type IdempotentIntent } from "../features/api/idempotency";
import { ApiError } from "../features/api/authenticated-fetch";
import { reportConnectionStatus } from "../features/api/connection-status";
import { PollingConnectionLostError, pollHistoryCompare } from "../features/api/journeys";
import { currentGatewaySession } from "../features/api/session";
import { ensureLocalBundle, OpfsBundleStore } from "../features/bundle/local-bundle";
import { ConnectionStatusIndicator } from "../design-system/ConnectionStatusIndicator";
import { ErrorState, LoadingSkeleton } from "../design-system/components";
import { OperationStatusPanel } from "../features/workbench/OperationStatusPanel";
import { buildWorkspaceTree, deriveWorkbenchActions, type WorkbenchActionId, type WorkspaceTreeRow } from "../features/view-model/workspace";
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

function requestWithTimeout<T>(request: Promise<T>, timeoutMs: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new DOMException("历史比较请求仍在处理", "TimeoutError")), timeoutMs);
    request.then((value) => { window.clearTimeout(timer); resolve(value); }, (cause: unknown) => { window.clearTimeout(timer); reject(cause); });
  });
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

function statusForNode(row: WorkspaceTreeRow): string {
  if (row.eligibilityNote) return "基线已更新";
  if (row.identityException) return "项目身份例外";
  return row.status;
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
  const [compareIntent, setCompareIntent] = useState<IdempotentIntent<Schemas["HistoryCompareAcceptRequest"]> | null>(null);
  const [compareStartError, setCompareStartError] = useState<string | null>(null);
  const [comparePending, setComparePending] = useState(false);
  const [compareState, setCompareState] = useState<Schemas["HistoryCompareResultResponse"] | null>(null);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [compareConnectionLost, setCompareConnectionLost] = useState(false);
  const [refreshCompare, setRefreshCompare] = useState(0);
  const [compareElapsed, setCompareElapsed] = useState(0);
  const operationId = new URLSearchParams(window.location.search).get("operationId");
  const operationKind = new URLSearchParams(window.location.search).get("operationKind");
  const historyCompareOperationId = operationKind === "history-compare" ? operationId : null;
  const pendingIntentKey = "gateway-history-compare-pending-intent";
  const searchRef = useRef<HTMLInputElement>(null);

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

  const rows = useMemo(() => data ? buildWorkspaceTree(data.workspace, data.history) : [], [data]);
  useEffect(() => {
    if (!rows.length) return;
    const queryNode = new URLSearchParams(window.location.search).get("node");
    const found = queryNode && rows.some((row) => row.key === queryNode) ? queryNode : rows.find((row) => row.kind === "workspace")?.key ?? rows[0]?.key;
    setSelectedKey((current) => current && rows.some((row) => row.key === current) ? current : found ?? "");
  }, [rows]);
  const rowByKey = useMemo(() => new Map(rows.map((row) => [row.key, row])), [rows]);
  const selected = rowByKey.get(selectedKey) ?? null;
  const comparedKeys = useMemo(() => new Set(compareRefs.map(refKey)), [compareRefs]);
  const actions = useMemo(() => deriveWorkbenchActions(selected, compareRefs.length, selected ? comparedKeys.has(selected.key) : false), [selected, compareRefs.length, comparedKeys]);

  const visibleRows = useMemo(() => {
    const query = filter.trim().toLocaleLowerCase();
    const result = rows.filter((row) => {
      if (currentBaselineOnly && !row.isHead && row.kind !== "workspace") return false;
      return !query || `${row.label} ${statusForNode(row)} ${row.refId ?? ""}`.toLocaleLowerCase().includes(query);
    });
    if (sort) result.sort((left, right) => {
      const leftValue = left[sort.column] ?? "";
      const rightValue = right[sort.column] ?? "";
      return String(leftValue).localeCompare(String(rightValue), "zh-CN") * sort.direction;
    });
    return result;
  }, [rows, filter, currentBaselineOnly, sort]);

  const setCompareSelection = (next: Schemas["HistoryCompareNodeRequest"][]) => {
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
      previewResultId: data.workspace.current_preview_result_id, node: selectedKey, pair,
    }, compareRefs));
  };

  const openReview = (row: WorkspaceTreeRow) => {
    if (!row.refId) return;
    window.location.assign(pageUrl("compare", { mode: "REVIEW", submissionId: row.refId, node: row.key }, compareRefs));
  };

  const sendHistoryCompare = async (intent: IdempotentIntent<Schemas["HistoryCompareAcceptRequest"]>) => {
    setComparePending(true);
    setCompareStartError(null);
    try {
      const timeoutMs = import.meta.env.DEV ? 700 : 30_000;
      const accepted = await requestWithTimeout(gatewayApi.startHistoryCompare(intent.request, intent.key), timeoutMs);
      setCompareIntent(null);
      try { window.sessionStorage.removeItem(pendingIntentKey); } catch { /* storage is optional */ }
      const compareParams: Record<string, string> = {
        page: "workspace", operationId: accepted.operation_id, operationKind: "history-compare",
      };
      window.location.assign(pageUrl("workspace", compareParams, intent.request.nodes));
    } catch (cause) {
      if (isTemporaryError(cause)) reportConnectionStatus("interrupted");
      const info = messageFrom(cause);
      setCompareStartError(cause instanceof DOMException && cause.name === "TimeoutError"
        ? "请求超时；历史比较可能已经受理。使用同一请求重试会复用幂等结果。"
        : `${info.message}（${info.code}）`);
    } finally {
      setComparePending(false);
    }
  };

  const startOrRetryCompare = () => {
    if (comparePending) return;
    let intent = compareIntent;
    if (!intent) {
      try {
        const saved = window.sessionStorage.getItem(pendingIntentKey);
        if (saved) intent = JSON.parse(saved) as IdempotentIntent<Schemas["HistoryCompareAcceptRequest"]>;
      } catch { /* create a new intent when storage is unavailable or invalid */ }
    }
    intent ??= createIdempotentIntent({ nodes: compareRefs });
    try { window.sessionStorage.setItem(pendingIntentKey, JSON.stringify(intent)); } catch { /* in-memory retry still reuses the key */ }
    setCompareIntent(intent);
    void sendHistoryCompare(intent);
  };

  useEffect(() => {
    if (!historyCompareOperationId) return;
    const controller = new AbortController();
    const startedAt = Date.now();
    setCompareState({ operation_id: historyCompareOperationId, status: "QUEUED", diagnostic: null });
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
        return;
      }
      await ensureLocalBundle({
        store: new OpfsBundleStore(), expectedBundleDigest: result.result.bundle_digest,
        fetchBundle: () => gatewayApi.getHistoryBundle(historyCompareOperationId, controller.signal),
      });
      setCompareError(null);
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
  }, [historyCompareOperationId, refreshCompare]);

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
    if (!selected) return;
    if (id === "original-backup") openPreview("baseline_to_initial");
    else if (id === "current-archive") openPreview("initial_to_modified");
    else if (id === "join-compare" || id === "remove-compare") toggleCompare(selected);
    else if (id === "view-diff") {
      if (selected.kind === "submission" && selected.reviewStatus === "PENDING") openReview(selected);
      else {
        const currentRef = historyRef(selected);
        if (currentRef && selected.parentRef) {
          const intent = createIdempotentIntent({ nodes: [{ ref_kind: selected.parentRef.ref_kind, ref_id: selected.parentRef.ref_id }, currentRef] });
          void sendHistoryCompare(intent);
        }
      }
    }
  };

  const showHistoryDrawer = Boolean(historyCompareOperationId);
  const showOperationStatus = operationId && operationKind === "operation";

  if (loading) return <main className="workspace-page"><LoadingSkeleton label="加载工作区与 History" /></main>;
  if (loadError || !data) return <main className="workspace-page workspace-page--error"><ErrorState code={loadError?.code ?? "WORKSPACE_LOAD_FAILED"} details={loadError?.message ?? "工作区加载失败"} onRetry={() => void load()} /><ConnectionStatusIndicator hideConnected />{identityControl}</main>;

  const compareLabels = compareRefs.map((ref) => rows.find((row) => row.key === refKey(ref))?.label ?? ref.ref_id);
  const selectedReviewFacts = selected?.kind === "submission" && compareState?.status === "SUCCEEDED" ? "审核信息按只读模式加载" : null;
  return <main className={`workspace-page${detailExpanded ? " details-open" : " details-collapsed"}`}>
    <header className="workspace-topbar">
      <div className="workspace-brand"><strong>网关数据工作台</strong><span>{data.workspace.gateway_device_external_key}</span></div>
      <div className="workspace-topbar__right"><span className="task-indicator"><RefreshCw size={13} />{showHistoryDrawer ? "历史比较" : "工作区就绪"}</span><ConnectionStatusIndicator />{identityControl}</div>
    </header>
    <div className="workspace-layout">
      <section className="workspace-main" aria-label="组态树工作台">
        <div className="workspace-tree-heading"><h1>组态树</h1><label className="workspace-search"><Search size={15} /><input ref={searchRef} aria-label="搜索工作区与 History 节点" placeholder="搜索节点" value={filter} onChange={(event) => setFilter(event.currentTarget.value)} /></label><span className="workspace-tree-heading__spacer" />
          <label className="workspace-checkbox"><input type="checkbox" checked={currentBaselineOnly} onChange={(event) => setCurrentBaselineOnly(event.currentTarget.checked)} />只显示当前基线</label>
          <button className="button button--secondary" onClick={() => setFilter("")}>展开全部</button>
        </div>
        {showOperationStatus && <OperationStatusPanel operationId={operationId} />}
        <div className="workspace-context-bar" aria-label="上下文工具栏">
          <div className="workspace-context-bar__selection"><span className="node-type-icon">{selected?.kind === "workspace" ? <Folder size={16} /> : selected?.kind === "baseline" ? <Layers size={16} /> : <GitCommitHorizontal size={16} />}</span><strong>{selected?.label ?? "未选择节点"}</strong>{selected && <span className="status-tag">{statusForNode(selected)}</span>}{selected?.eligibilityNote && <details className="inline-reason"><summary>说明</summary><span>该提交所基于的基线已不是当前基线，不能归档</span></details>}</div>
          <div className="workspace-actions">{actions.map((action) => <div className="workspace-action" key={action.id}>
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
            <tbody>{visibleRows.map((row) => <tr key={row.key} className={selectedKey === row.key ? "is-selected" : ""} onClick={() => setSelectedKey(row.key)}>
              <td><div className="workspace-tree-cell" style={{ paddingLeft: 18 + row.depth * 26 }}>
                {row.kind === "baseline" ? <Layers size={16} /> : row.kind === "workspace" ? <Folder size={16} /> : row.kind === "migration" ? <GitBranch size={16} /> : <GitCommitHorizontal size={16} />}
                <button className="workspace-node-label" onClick={() => setSelectedKey(row.key)}>{row.label}</button>
                <span className={`status-tag status-tag--${row.isHead ? "head" : row.kind}`}>{row.isHead ? "当前基线" : row.status}</span>
                {row.eligibilityNote && <span className="status-tag status-tag--warning" title="该提交所基于的基线已不是当前基线，不能归档">基线已更新</span>}
                {row.identityException && <span className="status-tag status-tag--neutral" title="项目身份例外">身份例外</span>}
              </div></td>
              <td>{row.createdAt ? new Date(row.createdAt).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }) : "—"}</td>
              <td>{row.submitAt ? new Date(row.submitAt).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }) : "—"}</td>
              <td>{row.reviewAt ? new Date(row.reviewAt).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }) : "—"}</td>
            </tr>)}</tbody>
          </table>
        </div>
        <div className="compare-tray" aria-label="比较托盘">
          <div className="compare-tray__label"><GitBranch size={17} /><strong>比较托盘</strong>{compareRefs.length > 0 && <span>{compareRefs.length} / 3</span>}{compareLabels.length === 0 && <small>选择 2–3 个基线或提交节点</small>}</div>
          <div className="compare-tray__items">{compareRefs.map((node, index) => <div className="compare-chip" key={refKey(node)}><span>{index + 1}</span>{compareLabels[index]}<button aria-label={`移除${compareLabels[index]}`} onClick={() => setCompareSelection(compareRefs.filter((item) => refKey(item) !== refKey(node)))}><X size={13} /></button></div>)}</div>
          <div className="compare-tray__actions"><button className="button button--ghost" disabled={!compareRefs.length || comparePending} onClick={() => setCompareSelection([])}><Trash2 size={14} />清空比较</button>
            {compareStartError && <span role="alert" className="compare-tray__error">{compareStartError}</span>}
            {compareIntent && compareStartError ? <button className="button button--primary" disabled={comparePending} onClick={startOrRetryCompare}><RefreshCw size={14} />重试发起比较</button> : <button className="button button--primary" disabled={compareRefs.length < 2 || comparePending} onClick={startOrRetryCompare}>{comparePending ? <RefreshCw size={14} /> : null}历史比较</button>}
            {compareRefs.length < 2 && <small>至少选择 2 个节点</small>}
          </div>
        </div>
        {showHistoryDrawer && <section className="history-result-drawer" aria-label="历史比较结果抽屉">
          <div className="history-result-drawer__heading"><div><GitBranch size={16} /><strong>历史比较</strong><span className={`status-tag status-tag--${compareState?.status === "SUCCEEDED" ? "success" : "info"}`}>{compareConnectionLost ? "连接中断" : compareState?.status === "SUCCEEDED" ? "已完成" : compareState?.status === "FAILED" ? "失败" : compareState?.status === "CANCELLED" ? "已取消" : "仍在运行"}</span><small>已等待 {compareElapsed} 秒</small></div>
            <div className="history-result-drawer__buttons">{compareConnectionLost && <button className="button button--secondary" onClick={() => setRefreshCompare((value) => value + 1)}><RefreshCw size={14} />重试查询</button>}
              {compareState?.status === "SUCCEEDED" && <button className="button button--primary" onClick={() => window.location.assign(pageUrl("compare", { mode: "HISTORY", operationId: historyCompareOperationId, operationKind: "history-compare" }, compareRefs))}>打开差异工作台</button>}
              <button className="icon-button" aria-label="收起历史比较结果" onClick={() => { const url = new URL(window.location.href); url.searchParams.delete("operationId"); url.searchParams.delete("operationKind"); window.history.replaceState(null, "", url); window.location.reload(); }}><ChevronDown size={17} /></button>
            </div>
          </div>
          {compareError && <p role="alert" className="history-result-drawer__error">{compareError}</p>}
          {compareState?.status === "SUCCEEDED" && <div className="history-result-drawer__body">
            <div className="history-result-drawer__nodes">{compareRefs.map((node, index) => <article key={refKey(node)}><span>{index + 1}</span><div><strong>{rows.find((row) => row.key === refKey(node))?.label ?? node.ref_id}</strong><small>{node.ref_kind === "baseline_node" ? "基线" : "提交"}</small></div><Check size={15} /></article>)}</div>
            <div className="history-result-drawer__pairs">{compareState.result?.pairs.map((pair, index) => <div key={pair.pair_id}><span>比较对 {index + 1}</span><strong>{pair.pair_id}</strong><small>{pair.record_count} 条差异记录</small></div>)}</div>
            <p>bundle 已下载并校验，可打开 History 差异浏览。</p>
          </div>}
        </section>}
      </section>
      <aside className="workspace-details" aria-label="详情面板">
        <button className="workspace-details__toggle" aria-label={detailExpanded ? "折叠详情面板" : "展开详情面板"} onClick={() => setDetailExpanded((value) => !value)}>{detailExpanded ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}</button>
        {detailExpanded ? <div className="workspace-details__content">
          <p className="eyebrow">{selected?.kind === "workspace" ? "工作区详情" : selected?.kind === "submission" ? "提交详情" : "历史节点详情"}</p>
          <h2>{selected?.label ?? "未选择节点"}</h2><p className="workspace-details__status"><span className="status-dot" />{selected ? statusForNode(selected) : "—"}</p>
          {selected?.kind === "workspace" && <>
            <dl className="details-list"><div><dt>网关设备</dt><dd>{data.workspace.gateway_device_external_key}</dd></div><div><dt>业务项目</dt><dd>{data.workspace.business_project_id}</dd></div><div><dt>工作区状态</dt><dd>{WORKSPACE_STATE_COPY[data.workspace.state as keyof typeof WORKSPACE_STATE_COPY] ?? "状态未知"}</dd></div><div><dt>组态代次</dt><dd>{data.workspace.generation}</dd></div><div><dt>当前 Preview</dt><dd>{data.workspace.current_preview_result_id ?? "—"}</dd></div></dl>
            <button className="button button--secondary workspace-details__action" disabled={!data.workspace.current_preview_result_id} title={data.workspace.current_preview_result_id ? undefined : "当前工作区还没有 Preview 结果"} onClick={() => openPreview("initial_to_modified")}>查看本次组态差异</button>
            {!data.workspace.current_preview_result_id && <p className="disabled-reason">当前工作区还没有 Preview 结果</p>}
            <p className="subtle-copy">写操作会在 FE2c 接入。</p>
          </>}
          {selected?.kind !== "workspace" && selected && <dl className="details-list"><div><dt>节点类型</dt><dd>{selected.kind === "baseline" ? selected.baselineKind === "INITIAL" ? "初始基线" : "归档基线" : selected.kind === "submission" ? "提交" : "规则迁移"}</dd></div><div><dt>状态</dt><dd>{statusForNode(selected)}</dd></div><div><dt>节点 ID</dt><dd>{selected.refId}</dd></div><div><dt>组态生成时间</dt><dd>{selected.createdAt ?? "—"}</dd></div>{selected.submitAt && <div><dt>提交时间</dt><dd>{selected.submitAt}</dd></div>}{selected.eligibilityNote && <div className="details-list__long"><dt>归档原因</dt><dd><details><summary>展开原因</summary>该提交所基于的基线已不是当前基线，不能归档</details></dd></div>}{selected.identityException && <div><dt>身份说明</dt><dd>项目身份例外</dd></div>}</dl>}
          {selectedReviewFacts && <p className="subtle-copy">{selectedReviewFacts}</p>}
        </div> : <div className="workspace-details__collapsed"><span>详情</span></div>}
      </aside>
    </div>
  </main>;
}
