import { DataEditor, GridCellKind, type DataEditorRef, type GridCell, type GridColumn, type Theme } from "@glideapps/glide-data-grid";
import "@glideapps/glide-data-grid/dist/index.css";
import { AlertTriangle, ArrowDown, ArrowUp, ChevronDown, ChevronLeft, ChevronRight, Code2, Copy, MoreHorizontal, Search, Table2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ComponentProps, type CSSProperties, type ReactNode } from "react";
import type { components } from "../features/api/generated/openapi";
import { useBoundGatewayApi, boundBundleFetch } from "../features/api/application-api";
import { assertSubmissionReviewBundle, pollHistoryCompare } from "../features/api/journeys";
import { bundleLoadErrorCode, ensureLocalBundle, OpfsBundleStore, type InstalledBundle } from "../features/bundle/local-bundle";
import { loadComparisonPresentation, readLocalChangeRecords, readLocalRiskAnnotations, readLocalTable, type LocalComparisonPresentation } from "../features/bundle/presentation";
import { deriveChangeLocations, deriveFormulaDisplays, navigationTabHasDifferences, normalizeRowIdentity, riskAnnotationRowIdentities, type DerivedNavigationGroup, type RiskAnnotation, type RiskLevel, type RowDiffRecord, type SurfaceTable } from "../features/view-model/model";
import { alignFormulaLines, renderFormulaLines } from "../features/view-model/formula-view";
import { readParquetMetadata, readParquetTable } from "../features/bundle/parquet-reader";
import { decodeSnapshotEncodings, type SnapshotColumnEncoding } from "../features/view-model/snapshot-encoding";
import { buildBrowseRows, canReuseUnrecordedIdentity, missingSideMarker, normalizeDisplayScalar, parseRowLocator, validateRowLocations, type BrowseRow } from "../features/view-model/table-rows";
import { formatNavigationDiagnostic, formatSurfaceDiagnostic, pairSurfaceDiagnosticCodes } from "../features/view-model/diagnostics";
import { describeRiskReason } from "../features/view-model/risk-copy";
import { identityStatusText } from "../features/view-model/identity-copy";
import { SurfaceChangeBadge, TableFailureNotice, surfaceChangePresentation, tableStatusText } from "../features/view-model/table-state";
import { presentViewStatus } from "../features/view-model/view-status";
import { BrowseCommandRuntime, decodeBrowseState, type BrowseState } from "../features/view-model/commands";
import { createTableTheme } from "../design-system/theme";
import { Dialog, ErrorState, LoadingSkeleton, RiskBadge, formatBytes } from "../design-system/components";
import { ConnectionStatusIndicator } from "../design-system/ConnectionStatusIndicator";
import { Button } from "../design-system/components";
import { formatWaitDuration } from "../features/workbench/wait-duration";
import { ApiError } from "../features/api/authenticated-fetch";
import { bundleErrorTitle } from "../features/bundle/local-bundle";
import { getUrlOperationJobKind, useUploadModeState } from "../features/workbench/use-upload-mode";
import { SessionGate } from "../features/session/SessionComponents";
import { formatHandoffDisplay, isGatewaySessionBlocked, useGatewaySessionState } from "../features/session/handoff-session";
import { SubmitDialog } from "../features/workbench/SubmitDialog";
import { OperationStatusPanel } from "../features/workbench/OperationStatusPanel";
import { ReviewActions } from "../features/workbench/ReviewActions";
import { ReviewDispositionLine } from "../features/workbench/disposition-display";
import type { SafeReviewFacts } from "../features/api/client";

function bundleErrorState(cause: unknown, details: string): { code: string; details: string } {
  // B5: the server's ApiError code is carried into the error state verbatim so
  // it stays visible and copyable; only non-HTTP failures use the generic
  // bundle-load codes. Never construct an empty bundle from an error response.
  if (cause instanceof ApiError) return { code: cause.code ?? `HTTP_${cause.status}`, details: cause.message || details };
  return { code: bundleLoadErrorCode(cause), details };
}

type PairSummary = { pair_id: string; summary?: Record<string, string> };
type PairPresentation = { pair: PairSummary; presentation: LocalComparisonPresentation };
type SizedGridColumn = GridColumn & { width: number };
type Settings = { sidebarWidth: number; sidebarCollapsed: boolean; collapsedGroups: string[] };
const SETTINGS_KEY = "gateway-comparison-sidebar-v2";
const SIDEBAR_MIN = 180;
const SIDEBAR_MAX = 520;
const DEFAULT_SETTINGS: Settings = { sidebarWidth: 220, sidebarCollapsed: false, collapsedGroups: [] };
const clampSidebar = (width: number) => Math.max(SIDEBAR_MIN, Math.min(SIDEBAR_MAX, width));

function reviewStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    PENDING: "待审核", APPROVED: "已通过", REJECTED: "已退回", WITHDRAWN: "已撤回",
  };
  return labels[status] ?? "状态未知";
}

function readSettings(): Settings {
  try {
    const value = JSON.parse(window.localStorage.getItem(SETTINGS_KEY) ?? "null") as Partial<Settings> | null;
    return { sidebarWidth: typeof value?.sidebarWidth === "number" ? clampSidebar(value.sidebarWidth) : DEFAULT_SETTINGS.sidebarWidth,
      sidebarCollapsed: typeof value?.sidebarCollapsed === "boolean" ? value.sidebarCollapsed : false,
      collapsedGroups: Array.isArray(value?.collapsedGroups) ? value.collapsedGroups.filter((item): item is string => typeof item === "string") : [] };
  } catch { return DEFAULT_SETTINGS; }
}

type ColumnWidths = Record<string, Record<string, number>>;
const COLUMN_WIDTHS_KEY = "gateway-comparison-column-widths-v1";

/** Column widths the viewer set, per table name; a convenience that may be absent. */
function readColumnWidths(): ColumnWidths {
  try {
    const value = JSON.parse(window.localStorage.getItem(COLUMN_WIDTHS_KEY) ?? "null") as unknown;
    if (!value || typeof value !== "object") return {};
    return Object.fromEntries(Object.entries(value as Record<string, unknown>).flatMap(([table, widths]) => {
      if (!widths || typeof widths !== "object") return [];
      const clean = Object.fromEntries(Object.entries(widths as Record<string, unknown>).filter((entry): entry is [string, number] => typeof entry[1] === "number" && Number.isFinite(entry[1])));
      return [[table, clean]];
    }));
  } catch { return {}; }
}

function viewLabel(pair: PairPresentation, index: number, total: number, mode: BrowseState["mode"]): string {
  if (mode === "REVIEW") return total === 1 ? "基线 → 修改" : pair.pair.pair_id === "baseline_to_initial" ? "基线 → 原始" : "原始 → 修改";
  if (mode === "HISTORY") return "节点 " + (index + 1) + " → 节点 " + (index + 2);
  if (total === 1) return "当前基线 → 本次归档组态";
  const id = pair.pair.pair_id.toLowerCase();
  if (id.includes("baseline_to_initial")) return "原始组态视图";
  if (id.includes("initial_to_modified")) return "本次组态视图";
  return "比较视图 " + (index + 1);
}

function viewTitle(pair: PairPresentation, index: number, total: number, mode: BrowseState["mode"]): string {
  if (mode === "REVIEW") return "提交绑定比较：" + viewLabel(pair, index, total, mode);
  if (mode === "HISTORY") return "节点 " + (index + 1) + " → 节点 " + (index + 2);
  if (total === 1) return "当前基线 → 本次归档组态";
  if (pair.pair.pair_id.toLowerCase().includes("baseline_to_initial")) return "已归档数据 → 原始组态备份";
  if (pair.pair.pair_id.toLowerCase().includes("initial_to_modified")) return "原始组态备份 → 本次归档组态";
  return "比较对 " + pair.pair.pair_id;
}

function viewRiskLevel(pair: PairPresentation): RiskLevel | null {
  const risk = pair.presentation.surface.view?.risk_level;
  return risk === "HIGH" || risk === "MEDIUM_HIGH" || risk === "MEDIUM_LOW" || risk === "LOW" || risk === "UNKNOWN" ? risk : null;
}

function pairDiagnosticDetails(pair: PairPresentation): { codes: string[]; tableCount: number } {
  const surface = pair.presentation.surface;
  const tableCount = surface.tables.filter((table) => (table.diagnostics?.diagnostics_summary?.length ?? 0) > 0).length;
  return { codes: pairSurfaceDiagnosticCodes(surface), tableCount };
}

function tabCount(tab: Pick<NavTab, "facts" | "table" | "rowFilter">, side: "before" | "current"): number | null {
  if (tab.rowFilter !== null) return (side === "before" ? tab.facts?.before_row_count : tab.facts?.current_row_count) ?? null;
  return tab.table?.rowCounts[side] ?? null;
}

function tabChangeKind(tab: { facts: { change_kind?: string | null } | null; table: { changeKind: string } | null }): string {
  return tab.table?.changeKind ?? tab.facts?.change_kind ?? "UNCHANGED";
}

function tabRiskLevel(tab: { facts: { risk_level?: RiskLevel | null } | null; table: { riskLevel: RiskLevel | null } | null }): RiskLevel | null {
  return tab.facts?.risk_level ?? tab.table?.riskLevel ?? null;
}

type NavItem = DerivedNavigationGroup["items"][number];
type NavTab = NavItem["tabs"][number];

function itemBadgeKind(kinds: readonly string[]): string {
  return kinds.find((kind) => surfaceChangePresentation(kind).badgeText !== null) ?? "UNCHANGED";
}

function itemStatusTooltip(kinds: readonly string[]): string {
  return [...new Set(kinds.map((kind) => surfaceChangePresentation(kind).tooltip).filter((tooltip): tooltip is string => Boolean(tooltip)))].join(" · ");
}

function riskLevelText(level: RiskLevel): string {
  return ({ HIGH: "高风险", MEDIUM_HIGH: "中高风险", MEDIUM_LOW: "中低风险", LOW: "低风险", UNKNOWN: "未知风险" })[level];
}

function tabTitle(changeKind: string, risk: RiskLevel | null, beforeCount: number | null, currentCount: number | null): string {
  const change = surfaceChangePresentation(changeKind);
  return [change.text, change.tooltip, risk ? riskLevelText(risk) : null, `${beforeCount ?? "—"} → ${currentCount ?? "—"} 行`]
    .filter((item): item is string => Boolean(item)).join(" · ");
}

function riskTokens(level: RiskLevel): { bg: string; rail: string; text: string; cell: string } {
  const style = getComputedStyle(document.documentElement);
  const name = "risk-" + level.toLowerCase().replace("_", "-");
  return { bg: style.getPropertyValue("--" + name + "-bg").trim(), rail: style.getPropertyValue("--" + name + "-rail").trim(),
    text: style.getPropertyValue("--" + name + "-text").trim(), cell: style.getPropertyValue("--" + name + "-cell").trim() };
}

function rowLabel(row: BrowseRow): string {
  if (row.kind === "collapsed") return row.expanded ? "▴ 收起 " + (row.collapsedCount ?? 0) + " 行未变更" : "▾ " + (row.collapsedCount ?? 0) + " 行未变更 · 展开";
  if (row.recordKind === "BLANK_DELETE_INTERVAL" || row.recordKind === "BLANK_INSERT_INTERVAL") {
    const interval = row.values.interval && typeof row.values.interval === "object" ? row.values.interval as Record<string, unknown> : {};
    const start = Number(interval.before_start ?? interval.current_start ?? row.beforePosition ?? row.currentPosition ?? 0);
    const end = Number(interval.before_end ?? interval.current_end ?? start);
    const insert = row.recordKind === "BLANK_INSERT_INTERVAL";
    return "第 " + start + "–" + end + " 行：" + (insert ? "插入" : "删除") + " " + Math.max(0, end - start + 1) + " 个空行";
  }
  if (row.kind === "added") return "+ 新增";
  if (row.kind === "deleted") return "− 删除";
  if (row.recordKind === "ORDERED_ROW_MOVED" || row.kind === "ordered") return "↕ 移动 · " + (row.beforePosition ?? "—") + " → " + (row.currentPosition ?? "—");
  if (row.kind === "modified-before" || row.kind === "modified-after") return "↔ 修改";
  if (row.kind === "blank") return "空行区间";
  return "";
}

function recordValues(value: unknown): Record<string, unknown> {
  if (!Array.isArray(value)) return {};
  return Object.fromEntries(value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const entry = item as { column_name?: unknown; value?: unknown };
    return typeof entry.column_name === "string" ? [[entry.column_name, entry.value]] : [];
  }));
}

type TextMeasure = (text: string) => number;

/** Measures text in the grid's own canvas font; falls back to a rough estimate. */
function createTextMeasure(font: string): TextMeasure {
  const context = typeof document === "undefined" ? null : document.createElement("canvas").getContext("2d");
  if (!context) return (text) => Array.from(text).length * 9;
  context.font = font;
  const cache = new Map<string, number>();
  return (text) => {
    let width = cache.get(text);
    if (width === undefined) { width = context.measureText(text).width; if (cache.size < 20_000) cache.set(text, width); }
    return width;
  };
}

/** Up to `limit` rows spread evenly over the table, so long tables size from more than their head. */
function sampleRows<T>(rows: readonly T[], limit: number): T[] {
  if (rows.length <= limit) return [...rows];
  const step = rows.length / limit;
  return Array.from({ length: limit }, (_, index) => rows[Math.floor(index * step)] as T);
}

const COLUMN_PADDING = 26;
const COLUMN_MIN = 56;
const COLUMN_AUTO_MAX = 420;
const COLUMN_FIT_MAX = 900;

/**
 * Width that fits the header and most values. Auto sizing uses the 95th
 * percentile so a few very long values do not widen the column; a double-click
 * fit uses the longest value.
 */
function fitWidth(headerWidth: number, valueWidths: number[], mode: "auto" | "fit"): number {
  const sorted = valueWidths.filter((width) => width > 0).sort((left, right) => left - right);
  const value = sorted.length === 0 ? 0 : mode === "fit" ? sorted[sorted.length - 1] ?? 0 : sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))] ?? 0;
  return Math.round(Math.min(mode === "fit" ? COLUMN_FIT_MAX : COLUMN_AUTO_MAX, Math.max(COLUMN_MIN, headerWidth, value) + COLUMN_PADDING));
}

function matchesGroup(group: DerivedNavigationGroup, query: string): boolean {
  const value = query.trim().toLocaleLowerCase();
  if (!value) return true;
  return [group.label, ...group.items.flatMap((item) => [item.label, ...item.tabs.map((tab) => tab.label)])]
    .some((item) => item.toLocaleLowerCase().includes(value));
}

function matchesItem(item: DerivedNavigationGroup["items"][number], query: string): boolean {
  const value = query.trim().toLocaleLowerCase();
  return !value || [item.label, ...item.tabs.map((tab) => tab.label)]
    .some((label) => label.toLocaleLowerCase().includes(value));
}

function bundlePathForState(state: BrowseState): string | null {
  if (state.mode === "PREVIEW" && state.workspaceId && state.previewResultId) {
    return `/v1/workspaces/${encodeURIComponent(state.workspaceId)}/preview-results/${encodeURIComponent(state.previewResultId)}/bundle`;
  }
  if (state.mode === "REVIEW" && state.submissionId) return `/v1/submissions/${encodeURIComponent(state.submissionId)}/result/bundle`;
  if (state.mode === "HISTORY" && state.operationId) {
    return `/v1/history-compares/${encodeURIComponent(state.operationId)}/bundle`;
  }
  return null;
}

export function ComparisonPage({ identityControl }: { identityControl?: ReactNode }) {
  const gatewayApi = useBoundGatewayApi();
  const [fetchBundle] = useState(boundBundleFetch);
  const sessionState = useGatewaySessionState();
  const runtime = useMemo(() => new BrowseCommandRuntime(decodeBrowseState(window.location.search)), []);
  const [browse, setBrowse] = useState<BrowseState>(runtime.snapshot.state);
  const [bundle, setBundle] = useState<InstalledBundle | null>(null);
  const [pairs, setPairs] = useState<PairPresentation[]>([]);
  const [loading, setLoading] = useState({ phase: "准备比较结果", received: 0, total: 0 });
  const [error, setError] = useState<{ code: string; details: string } | null>(null);
  const [historyCompareStatus, setHistoryCompareStatus] = useState<components["schemas"]["HistoryCompareResultResponse"]["status"] | null>(null);
  const [historyCompareWaited, setHistoryCompareWaited] = useState(0);
  const [reviewFacts, setReviewFacts] = useState<SafeReviewFacts | null>(null);
  const [submitOpen, setSubmitOpen] = useState(false);
  // Upload-mode occupancy (withdraw/submit/upload gates) is shared with the
  // workbench through useUploadModeState (B4): a single read sequence for the
  // workspace, review, attempt and operation, with a one-time re-read (B2) and
  // a post-terminal resume re-read (B3).
  const uploadMode = useUploadModeState({ enabled: browse.mode === "PREVIEW" });
  const { workspace, review, attempt } = uploadMode;
  const uploadGates = uploadMode.gates;
  const [resumeOperationId, setResumeOperationId] = useState<string | null>(null);
  const [withdrawOpen, setWithdrawOpen] = useState(false);
  const [withdrawBusy, setWithdrawBusy] = useState(false);
  const [withdrawUnderstood, setWithdrawUnderstood] = useState(false);
  const [withdrawError, setWithdrawError] = useState<{ title: string; code: string } | null>(null);
  const withdrawKey = useRef<string | null>(null);
  const { refresh: refreshUploadSnapshot } = uploadMode;
  const refreshUploadMode = useCallback(async () => {
    const { workspace: loaded, attempt: loadedAttempt, workspaceError } = await refreshUploadSnapshot();
    if (workspaceError) return;
    if (loaded?.active_submit_attempt_id && loadedAttempt?.operation_id) {
      const urlOperationId = new URL(window.location.href).searchParams.get("operationId");
      if (!urlOperationId) {
        runtime.execute({ name: "set-operation", operationId: loadedAttempt.operation_id, operationKind: "operation" }, "external");
      } else if (urlOperationId !== loadedAttempt.operation_id) {
        // §6.2: a submit operation in the URL that disagrees with the
        // server-side pointer loses to the pointer; a preview operation in
        // the URL belongs to the preview flow and is left alone (job_kind).
        // The runtime state is updated (not just the URL) so later browse
        // commands do not restore the stale operation id.
        if (await getUrlOperationJobKind(gatewayApi, urlOperationId) === "backend-vnext/submit") {
          runtime.execute({ name: "set-operation", operationId: loadedAttempt.operation_id, operationKind: "operation" }, "external");
        }
      }
    } else {
      setResumeOperationId(null);
    }
  }, [refreshUploadSnapshot, runtime]);

  // The resume card mounts as soon as the attempt is known, without waiting
  // for the (possibly long-polling) operation read inside the same refresh.
  const resumeAttemptOperationId = attempt?.operation_id ?? null;
  useEffect(() => {
    if (resumeAttemptOperationId) setResumeOperationId(resumeAttemptOperationId);
  }, [resumeAttemptOperationId]);
  useEffect(() => {
    if (browse.mode !== "PREVIEW") return;
    void refreshUploadMode();
  }, [browse.mode, refreshUploadMode]);
  const { resumeAfterOperation, retryResume, clearResumeNotice } = uploadMode;
  // F1: the resume notice comes from the hook snapshot (uploadMode.resumeNotice);
  // the page only clears the operation card for terminal outcomes that leave
  // no pointer behind. Retry re-runs the read sequence and re-derives the notice.
  const finishSubmitResume = useCallback(async (finishedOperationId: string) => {
    const outcome = await resumeAfterOperation(finishedOperationId);
    if (outcome.kind === "submitted") {
      const params = new URLSearchParams({ page: "compare", mode: "REVIEW", submissionId: outcome.submissionId });
      window.location.assign(`/?${params.toString()}`);
      return;
    }
    if (outcome.kind === "aborted" || outcome.kind === "empty") {
      setResumeOperationId(null);
    }
  }, [resumeAfterOperation]);
  // G1 (§6.2 step 2): the notice retry re-runs the resume sequence from step
  // 1 via the hook entry, so both pages share one implementation and empty
  // pointers still re-read the known attempt ID.
  const retryResumeNotice = useCallback(async () => {
    const outcome = await retryResume();
    if (outcome.kind === "submitted") {
      const params = new URLSearchParams({ page: "compare", mode: "REVIEW", submissionId: outcome.submissionId });
      window.location.assign(`/?${params.toString()}`);
      return;
    }
    if (outcome.kind === "aborted" || outcome.kind === "empty") {
      setResumeOperationId(null);
    }
  }, [retryResume]);
  const resumeNotice = uploadMode.resumeNotice;
  const confirmWithdraw = useCallback(async () => {
    if (!workspace?.active_submission_id || !review) return;
    setWithdrawBusy(true);
    setWithdrawError(null);
    const key = withdrawKey.current ?? crypto.randomUUID();
    withdrawKey.current = key;
    try {
      await gatewayApi.applyReview(workspace.active_submission_id, { expected_review_version: review.review_version, action: "WITHDRAW" }, key);
      const { workspace: loaded, workspaceError: refreshError } = await refreshUploadSnapshot();
      if (refreshError) {
        setWithdrawError({ title: "撤回未完成", code: refreshError.code ?? "REQUEST_FAILED" });
        return;
      }
      if (!loaded?.active_submission_id && !loaded?.active_submit_attempt_id && !loaded?.current_upload_revision_id && !loaded?.current_preview_result_id) {
        setWithdrawOpen(false);
        window.location.assign("/?page=workspace&notice=withdrawn");
        return;
      }
      await refreshUploadMode();
    } catch (cause) {
      if (cause instanceof ApiError) {
        const conflict = ["REVIEW_VERSION_CONFLICT", "REVIEW_TRANSITION_CONFLICT", "WORKSPACE_OCCUPANCY_CONFLICT", "ARCHIVE_CLOSED"].includes(cause.code ?? "");
        if (conflict) {
          setWithdrawError({ title: "审核状态已变化，已重新读取", code: cause.code ?? "REVIEW_STATE_CHANGED" });
          await refreshUploadMode();
        } else if (cause.status === 403) {
          setWithdrawError({ title: "当前身份没有撤回权限", code: cause.code ?? "SCOPE_FORBIDDEN" });
        } else if (cause.status === 404) {
          setWithdrawError({ title: "未找到该提交，请刷新后重试", code: cause.code ?? "RESOURCE_NOT_FOUND" });
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
  const [settings, setSettings] = useState<Settings>(readSettings);
  const collapsed = settings.sidebarCollapsed;
  const [formulaOpen, setFormulaOpen] = useState(false);
  const [formulas, setFormulas] = useState<ReturnType<typeof deriveFormulaDisplays>>([]);
  const [formulaFocus, setFormulaFocus] = useState<string | null>(null);
  const [rows, setRows] = useState<BrowseRow[]>([]);
  const [beforeRows, setBeforeRows] = useState<Record<string, unknown>[]>([]);
  const [currentRows, setCurrentRows] = useState<Record<string, unknown>[]>([]);
  const [records, setRecords] = useState<RowDiffRecord[]>([]);
  const [annotations, setAnnotations] = useState<Awaited<ReturnType<typeof readLocalRiskAnnotations>>>([]);
  const [expandedRuns, setExpandedRuns] = useState<Set<string>>(new Set());
  const [tableLoading, setTableLoading] = useState(false);
  const [visibleRows, setVisibleRows] = useState({ start: 1, end: 1 });
  const [search, setSearch] = useState(runtime.snapshot.state.search);
  const [onlyInteresting, setOnlyInteresting] = useState(runtime.snapshot.state.onlyInteresting);
  const [debug, setDebug] = useState(runtime.snapshot.state.debug);
  const loadingKey = useRef<string | null>(null);
  const loadedRequest = useRef<{ requestPath: string; bundleDigest: string; bundle: InstalledBundle } | null>(null);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const selectedNavRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const reviewNoticeRef = useRef<HTMLDivElement | null>(null);
  const pageRef = useRef<HTMLElement | null>(null);
  const headerRef = useRef<HTMLElement | null>(null);

  // R15: the sticky sidebar tracks the measured compare-header height so the
  // navigation title and search box are never covered by a taller top bar.
  // This effect stays above every early return: skipping it on some renders
  // would change the hook order and crash the page. It re-runs when the
  // session state settles because the header only mounts after the session
  // gate opens; otherwise the variable would stay unset on session-gated
  // first renders.
  useEffect(() => {
    const header = headerRef.current;
    const page = pageRef.current;
    if (!header || !page) return;
    const apply = () => {
      page.style.setProperty("--compare-header-height", `${Math.max(1, Math.round(header.getBoundingClientRect().height))}px`);
    };
    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(header);
    return () => observer.disconnect();
  }, [sessionState]);

  useEffect(() => {
    const unsubscribe = runtime.subscribe(({ state }) => { setBrowse(state); setSearch(state.search); setOnlyInteresting(state.onlyInteresting); setDebug(state.debug); });
    const restore = () => runtime.restoreFromUrl();
    window.addEventListener("popstate", restore);
    return () => { unsubscribe(); window.removeEventListener("popstate", restore); };
  }, [runtime]);
  useEffect(() => { try { window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings)); } catch { /* defaults remain in memory */ } }, [settings]);
  const [columnWidths, setColumnWidths] = useState<ColumnWidths>(readColumnWidths);
  useEffect(() => { try { window.localStorage.setItem(COLUMN_WIDTHS_KEY, JSON.stringify(columnWidths)); } catch { /* widths remain in memory */ } }, [columnWidths]);

  const loadBundle = useCallback(async () => {
    if (sessionState.kind !== "handoff" && sessionState.kind !== "preset") return;
    const current = runtime.snapshot.state;
    const requestPath = bundlePathForState(current);
    if (!requestPath) { setError({ code: "BUNDLE_RESOURCE_MISSING", details: "工作区、Preview 结果或历史比较操作 ID 不完整。" }); return; }
    if (current.mode !== "REVIEW" && loadedRequest.current?.requestPath === requestPath
      && (!current.bundleDigest || current.bundleDigest === loadedRequest.current.bundleDigest)) return;
    const requestKey = requestPath;
    if (loadingKey.current === requestKey) return;
    loadingKey.current = requestKey;
    setError(null); setHistoryCompareStatus(null);
    if (loadedRequest.current?.requestPath !== requestPath) { setBundle(null); setPairs([]); }
    setLoading({ phase: "下载并校验比较结果", received: 0, total: 0 });
    try {
      let expectedBundleDigest: string | undefined;
      let submissionResult: components["schemas"]["SubmissionResultResponse"] | undefined;
      if (current.mode === "PREVIEW" && current.workspaceId && current.previewResultId) {
        expectedBundleDigest = (await gatewayApi.getPreviewResult(current.workspaceId, current.previewResultId)).bundle_digest;
      }
      if (current.mode === "REVIEW" && current.submissionId) {
        const [facts, result] = await Promise.all([
          gatewayApi.getReviewFacts(current.submissionId), gatewayApi.getSubmissionResult(current.submissionId),
        ]);
        gatewayApi.assertSession?.();
        if (result.submission_id !== current.submissionId) throw new ApiError("提交结果身份不一致", 503, "SUBMISSION_RESULT_INTEGRITY_FAILURE");
        setReviewFacts(facts);
        submissionResult = result;
        expectedBundleDigest = result.bundle_digest;
        if (loadedRequest.current?.requestPath === requestPath
          && loadedRequest.current.bundleDigest === expectedBundleDigest) {
          assertSubmissionReviewBundle(current.submissionId, result, loadedRequest.current.bundle);
          setLoading({ phase: "比较结果已就绪", received: 0, total: 0 });
          return;
        }
      }
      if (current.mode === "HISTORY") {
        if (!current.operationId) throw new Error("历史比较操作 ID 缺失");
        const startedAt = Date.now();
        const compareResult = await pollHistoryCompare(gatewayApi, current.operationId, {
          onUpdate: (value) => {
            setHistoryCompareStatus(value.status);
            if (value.status === "QUEUED" || value.status === "RUNNING") setLoading({ phase: "历史比较执行中", received: Math.floor((Date.now() - startedAt) / 1_000), total: 0 });
          },
          onWait: () => setHistoryCompareWaited(Math.floor((Date.now() - startedAt) / 1_000)),
        });
        if (compareResult.status !== "SUCCEEDED" || !compareResult.result) throw new Error(compareResult.diagnostic?.message ?? "历史比较未能完成");
        expectedBundleDigest = compareResult.result.bundle_digest;
      }
      setBundle(null); setPairs([]);
      const loaded = await ensureLocalBundle({ store: new OpfsBundleStore(), expectedBundleDigest,
        fetchBundle: () => fetchBundle(requestPath, { headers: { Accept: "application/x-tar" } }),
        onProgress: ({ receivedBytes, contentLength }) => setLoading({ phase: "下载并校验比较结果", received: receivedBytes, total: contentLength }) });
      gatewayApi.assertSession?.();
      loadedRequest.current = { requestPath, bundleDigest: loaded.manifest.bundle_digest, bundle: loaded };
      const pairSummaries = loaded.manifest.pairs.filter((value): value is PairSummary => Boolean(value && typeof value === "object" && typeof (value as PairSummary).pair_id === "string"));
      if (submissionResult && current.submissionId) assertSubmissionReviewBundle(current.submissionId, submissionResult, loaded);
      const loadedPairs = await Promise.all(pairSummaries.map(async (pair) => ({ pair, presentation: await loadComparisonPresentation(loaded, pair.pair_id) })));
      gatewayApi.assertSession?.();
      setBundle(loaded); setPairs(loadedPairs); setLoading({ phase: "比较结果已就绪", received: 0, total: 0 });
      const currentState = runtime.snapshot.state;
      const initialBundleLoad = currentState.bundleDigest === null;
      if (currentState.bundleDigest !== loaded.manifest.bundle_digest) runtime.execute({ name: "set-bundle", mode: currentState.mode, bundleDigest: loaded.manifest.bundle_digest }, "external");
      const selected = loadedPairs.find(({ pair }) => pair.pair_id === currentState.pairId)
        ?? loadedPairs.find(({ pair }) => pair.pair_id === submissionResult?.default_pair_id) ?? loadedPairs[0];
      if (selected && runtime.snapshot.state.pairId !== selected.pair.pair_id) runtime.execute({ name: "select-pair", pairId: selected.pair.pair_id }, "external");
      if (initialBundleLoad && currentState.nodeKey && runtime.snapshot.state.nodeKey !== currentState.nodeKey) runtime.execute({ name: "select-node", nodeKey: currentState.nodeKey }, "external");
      if (initialBundleLoad && currentState.tabKey && runtime.snapshot.state.tabKey !== currentState.tabKey) runtime.execute({ name: "select-tab", tabKey: currentState.tabKey }, "external");
    } catch (cause) {
      const details = cause instanceof Error ? cause.message : String(cause);
      loadedRequest.current = null;
      setBundle(null); setPairs([]);
      setError(bundleErrorState(cause, details));
    } finally {
      if (loadingKey.current === requestKey) loadingKey.current = null;
    }
  }, [browse.bundleDigest, browse.mode, browse.operationId, browse.previewResultId, browse.submissionId, browse.workspaceId, runtime, sessionState.kind]);
  useEffect(() => { void loadBundle(); }, [loadBundle]);

  // Result authority is invalid while any review-context refresh is pending.
  const reloadReviewContext = useCallback(async (): Promise<boolean> => {
    const current = runtime.snapshot.state;
    if (current.mode !== "REVIEW" || !current.submissionId) return false;
    const cached = loadedRequest.current;
    setBundle(null);
    setError(null);
    setLoading({ phase: "重新读取提交绑定的比较结果", received: 0, total: 0 });
    try {
      const [facts, result] = await Promise.all([
        gatewayApi.getReviewFacts(current.submissionId), gatewayApi.getSubmissionResult(current.submissionId),
      ]);
      gatewayApi.assertSession?.();
      if (runtime.snapshot.state.submissionId !== current.submissionId) return false;
      if (!cached || cached.requestPath !== bundlePathForState(current)) {
        throw new ApiError("提交绑定的比较结果尚未就绪", 503, "SUBMISSION_RESULT_UNAVAILABLE");
      }
      assertSubmissionReviewBundle(current.submissionId, result, cached.bundle);
      setReviewFacts(facts);
      setBundle(cached.bundle);
      return true;
    } catch (cause) {
      if (runtime.snapshot.state.submissionId !== current.submissionId) return false;
      loadedRequest.current = null;
      setBundle(null); setPairs([]);
      setError(bundleErrorState(cause, cause instanceof Error ? cause.message : String(cause)));
      return false;
    }
  }, [runtime]);

  const activePair = pairs.find(({ pair }) => pair.pair_id === browse.pairId) ?? pairs[0];
  const presentation = activePair?.presentation ?? null;
  const groups = useMemo(() => presentation?.view.groups ?? [], [presentation]);
  const navigationDiagnostics = presentation?.navigationDiagnostics;
  // Tabs an item shows in the tab strip; the sidebar lists an item only when it has some.
  // Showing empty tabs lasts for this page only, so it cannot silently stick.
  const [showEmptyTabs, setShowEmptyTabs] = useState(false);
  const shownTabs = useCallback((item: NavItem): NavTab[] => item.tabs.filter((tab) => {
    if (!showEmptyTabs && tab.empty) return false;
    if (!browse.onlyInteresting) return true;
    return navigationTabHasDifferences(tab)
      || (navigationDiagnostics ?? []).some(({ target }) => target.item_key === item.itemKey && (!target.tab_key || target.tab_key === tab.tabKey));
  }), [browse.onlyInteresting, navigationDiagnostics, showEmptyTabs]);
  const visibleGroups = useMemo(() => groups.filter((group) => {
    if (!matchesGroup(group, browse.search)) return false;
    return group.items.some((item) => shownTabs(item).length > 0)
      || navigationDiagnostics?.some((diagnostic) => diagnostic.target.group_key === group.groupKey) === true;
  }), [browse.search, groups, navigationDiagnostics, shownTabs]);
  const navigationEntries = useMemo(() => groups.flatMap((group) => group.items.flatMap((item) => item.tabs.map((tab) => ({ group, item, tab })))), [groups]);
  const wholeTableName = browse.tabKey?.startsWith("__whole__:") ? browse.tabKey.slice("__whole__:".length) : null;
  const wholeTable = wholeTableName ? presentation?.view.tables.find((item) => item.tableName === wholeTableName) : null;
  // A saved location identifies both the item and its tab, including hidden empty tabs.
  const selectedEntry = useMemo(() => navigationEntries.find(({ item, tab }) => item.itemKey === browse.nodeKey && tab.tabKey === browse.tabKey)
    ?? navigationEntries.find(({ item, tab }) => item.itemKey === browse.nodeKey && shownTabs(item).includes(tab))
    ?? navigationEntries.find(({ item }) => item.itemKey === browse.nodeKey)
    ?? navigationEntries.find(({ item, tab }) => shownTabs(item).includes(tab))
    ?? navigationEntries.find(({ tab }) => !tab.empty)
    ?? navigationEntries[0]
    ?? null, [browse.nodeKey, browse.tabKey, navigationEntries, shownTabs]);
  const emptyTabCount = useMemo(() => navigationEntries.filter(({ tab }) => tab.empty).length, [navigationEntries]);
  const toggleEmptyTabs = () => {
    if (showEmptyTabs && selectedEntry?.tab.empty && !wholeTable) {
      const next = navigationEntries.find(({ group, item, tab }) => !tab.empty && shownTabs(item).includes(tab)
        && (matchesGroup(group, browse.search) || matchesItem(item, browse.search)))
        ?? navigationEntries.find(({ tab }) => !tab.empty);
      if (next) {
        runtime.execute({ name: "select-node", nodeKey: next.item.itemKey });
        runtime.execute({ name: "select-tab", tabKey: next.tab.tabKey });
      }
    }
    setShowEmptyTabs((value) => !value);
  };
  const selectedTab = useMemo(() => wholeTable && wholeTableName
    ? { tabKey: "__whole__:" + wholeTableName, label: wholeTable.label, tableName: wholeTableName, empty: false, rowFilter: null, facts: null, table: wholeTable }
    : selectedEntry?.tab ?? null, [selectedEntry, wholeTable, wholeTableName]);
  const selectedNodeKey = wholeTableName
    ? groups.flatMap((group) => group.items).find((item) => item.tabs.some((tab) => tab.tableName === wholeTableName))?.itemKey ?? browse.nodeKey ?? ""
    : selectedEntry?.item.itemKey ?? "";
  const globalNavigationDiagnostics = presentation?.navigationDiagnostics.filter(({ target }) =>
    !target.group_key && !target.item_key && !target.tab_key && !target.table_id) ?? [];
  const table = presentation?.view.tables.find((item) => item.tableName === selectedTab?.tableName) ?? null;
  const surfaceTable = presentation?.surface.tables.find((item) => item.table_name === selectedTab?.tableName) ?? null;
  const replacement = presentation?.surface.comparison_mode === "DATASET_REPLACEMENT" || table?.changeKind === "REPLACED";
  const debugMode = debug && import.meta.env.DEV;

  useEffect(() => {
    if (!presentation || !selectedTab) return;
    if (browse.tabKey !== selectedTab.tabKey) runtime.execute({ name: "select-tab", tabKey: selectedTab.tabKey }, "external");
    if (browse.nodeKey !== selectedNodeKey) runtime.execute({ name: "select-node", nodeKey: selectedNodeKey }, "external");
  }, [browse.nodeKey, browse.tabKey, presentation, runtime, selectedNodeKey, selectedTab]);
  useEffect(() => { selectedNavRef.current?.scrollIntoView({ block: "nearest" }); }, [browse.nodeKey, browse.tabKey]);
  // Opened unchanged runs belong to one tab; run keys repeat across tables.
  useEffect(() => { setExpandedRuns((old) => old.size ? new Set() : old); }, [selectedNodeKey, selectedTab?.tabKey, selectedTab?.tableName]);

  const filterTabsForTable = useCallback((tableName: string) => {
    if (!presentation) return [];
    const sides = presentation.view.replacementSides
      ? [...presentation.view.groups, ...presentation.view.replacementSides.before, ...presentation.view.replacementSides.current]
      : presentation.view.groups;
    return sides.flatMap((group) => group.items.flatMap((item) => item.tabs)).filter((tab) => tab.tableName === tableName && tab.rowFilter !== null);
  }, [presentation]);
  const loadTable = useCallback(async () => {
    if (!bundle || !presentation || !selectedTab || !surfaceTable) { setRows([]); return; }
    setTableLoading(true);
    try {
      const paths = presentation.tableArtifacts.get(selectedTab.tableName);
      const beforePromise = paths?.before ? readLocalTable(bundle, presentation, selectedTab.tableName, "before") : Promise.resolve([]);
      const currentPromise = paths?.current ? readLocalTable(bundle, presentation, selectedTab.tableName, "current") : Promise.resolve([]);
      const locatorPromise = paths?.rowLocator
        ? readParquetTable(bundle, paths.rowLocator, { columns: ["row_identity", "before_row_index", "current_row_index", "before_filter_context_json", "current_filter_context_json"] })
        : Promise.resolve([] as Record<string, unknown>[]);
      if (replacement) {
        const [before, current] = await Promise.all([beforePromise, currentPromise]);
        setBeforeRows(before as Record<string, unknown>[]); setCurrentRows(current as Record<string, unknown>[]); setRows([]); setRecords([]); setAnnotations([]); return;
      }
      const [before, current, rowRecords, risks, locatorRows] = await Promise.all([beforePromise, currentPromise, readLocalChangeRecords(bundle, presentation, selectedTab.tableName), readLocalRiskAnnotations(bundle, presentation, selectedTab.tableName), locatorPromise]);
      const beforeSnapshotRows = before as Record<string, unknown>[]; const currentSnapshotRows = current as Record<string, unknown>[];
      const tableRecords = rowRecords as RowDiffRecord[];
      const locator = parseRowLocator(locatorRows as Record<string, unknown>[]);
      const filterTabs = filterTabsForTable(surfaceTable.table_name);
      const exactTable = filterTabs.length > 0 && filterTabs.every((tab) => tab.facts?.basis === "EXACT");
      validateRowLocations({ table: surfaceTable, locator, records: tableRecords,
        beforeRowCount: beforeSnapshotRows.length, currentRowCount: currentSnapshotRows.length,
        hasBeforeSnapshot: Boolean(paths?.before), hasCurrentSnapshot: Boolean(paths?.current),
        publishesFilterTabs: filterTabs.length > 0, exactTable });
      const degraded = tableRecords.some((record) => record.record_kind === "TABLE_DEGRADED" || record.record_kind === "ORDERED_TABLE_DEGRADED");
      const needsEncodings = selectedTab.rowFilter !== null && !degraded;
      const [beforeMeta, currentMeta] = needsEncodings
        ? await Promise.all([
          paths?.before ? readParquetMetadata(bundle, paths.before) : Promise.resolve(null),
          paths?.current ? readParquetMetadata(bundle, paths.current) : Promise.resolve(null),
        ])
        : [null, null];
      const tableLabel = `表 ${surfaceTable.table_name}`;
      const beforeEncodings: Map<string, SnapshotColumnEncoding> = beforeMeta ? decodeSnapshotEncodings(beforeMeta.key_value_metadata, `${tableLabel}.改前`) : new Map();
      const currentEncodings: Map<string, SnapshotColumnEncoding> = currentMeta ? decodeSnapshotEncodings(currentMeta.key_value_metadata, `${tableLabel}.改后`) : new Map();
      setBeforeRows(beforeSnapshotRows); setCurrentRows(currentSnapshotRows); setRecords(tableRecords); setAnnotations(risks);
      const built = buildBrowseRows({ table: surfaceTable, beforeRows: beforeSnapshotRows, currentRows: currentSnapshotRows, records: tableRecords, annotations: risks, locator,
        hasBeforeSnapshot: Boolean(paths?.before), hasCurrentSnapshot: Boolean(paths?.current),
        rowFilter: selectedTab.rowFilter, beforeEncodings, currentEncodings, degraded,
        reuseUnrecordedBefore: canReuseUnrecordedIdentity(surfaceTable, filterTabs, Boolean(paths?.before), Boolean(paths?.current)),
        onlyInteresting: browse.onlyInteresting, search: browse.search, expandedRuns });
      setRows(built.rows);
    } catch (cause) {
      setError({ code: "TABLE_READ_FAILED", details: cause instanceof Error ? cause.message : String(cause) });
    } finally { setTableLoading(false); }
  }, [browse.onlyInteresting, browse.search, bundle, expandedRuns, filterTabsForTable, presentation, replacement, selectedTab, surfaceTable]);
  useEffect(() => { void loadTable(); }, [loadTable]);

  const locations = useMemo(() => deriveChangeLocations(records, annotations), [annotations, records]);
  const rowRiskCounts = useMemo(() => {
    const risks = new Map<string, RiskLevel>();
    for (const annotation of annotations) {
      for (const identity of riskAnnotationRowIdentities(annotation)) risks.set(identity, annotation.risk_level);
    }
    return [...risks.values()].reduce((levels, level) => {
      const match = levels.find((item) => item.level === level);
      if (match) match.count += 1;
      else levels.push({ level, count: 1 });
      return levels;
    }, [] as Array<{ level: RiskLevel; count: number }>);
  }, [annotations]);
  const currentIndex = Math.min(browse.changeIndex, Math.max(0, locations.length - 1));
  const riskReasonDetails = useMemo(() => {
    const result = new Map<string, { reasonCode: string; ruleId: string | null; copy: string }>();
    for (const annotation of annotations) for (const reason of annotation.reasons) {
      result.set(reason.reason_code + "|" + reason.rule_id, { reasonCode: reason.reason_code, ruleId: reason.rule_id, copy: describeRiskReason(reason.reason_code) });
    }
    for (const code of surfaceTable?.risk_refs?.reason_codes ?? []) {
      if (![...result.values()].some((detail) => detail.reasonCode === code)) result.set(code, { reasonCode: code, ruleId: null, copy: describeRiskReason(code) });
    }
    return [...result.values()];
  }, [annotations, surfaceTable]);
  // The tab strip belongs to the selected navigation item only; the selected
  // tab stays visible even when the scope filter would hide it.
  const selectedItem = useMemo(() => groups.flatMap((group) => group.items).find((item) => item.itemKey === selectedNodeKey) ?? null, [groups, selectedNodeKey]);
  const stripTabs = useMemo(() => {
    if (!selectedItem) return [];
    const shown = shownTabs(selectedItem);
    return selectedItem.tabs.filter((tab) => shown.includes(tab) || (!wholeTable && tab.tabKey === selectedTab?.tabKey && tab.tableName === selectedTab.tableName));
  }, [selectedItem, selectedTab, shownTabs, wholeTable]);
  const itemEmptyTabCount = selectedItem ? selectedItem.tabs.filter((tab) => tab.empty).length : 0;
  const stripVisible = Boolean(selectedItem && (stripTabs.length > 1 || wholeTable || itemEmptyTabCount > 0));
  useEffect(() => { document.querySelector(".overflow-tabs button.is-active")?.scrollIntoView({ block: "nearest", inline: "nearest" }); }, [selectedNodeKey, browse.tabKey]);

  const widthTable = surfaceTable?.table_name ?? null;
  const storedWidths = useMemo(() => (widthTable ? columnWidths[widthTable] : undefined) ?? {}, [columnWidths, widthTable]);
  const changeColumnWidth = useCallback((columnId: string, width: number) => {
    if (!widthTable) return;
    setColumnWidths((old) => ({ ...old, [widthTable]: { ...old[widthTable], [columnId]: width } }));
  }, [widthTable]);
  const resetColumnWidths = () => { if (widthTable) setColumnWidths((old) => { const next = { ...old }; delete next[widthTable]; return next; }); };

  const chooseTab = (tableName: string, tabKey: string, itemKey = tableName) => {
    runtime.execute({ name: "select-node", nodeKey: itemKey }); runtime.execute({ name: "select-tab", tabKey });
  };
  const choosePair = (pair: PairPresentation) => {
    runtime.execute({ name: "select-pair", pairId: pair.pair.pair_id });
    runtime.execute({ name: "select-node", nodeKey: "" }); runtime.execute({ name: "select-tab", tabKey: "" });
  };
  const openWholeTable = (tableName: string, itemKey?: string | null) => {
    const owner = groups.flatMap((group) => group.items).find((item) => item.itemKey === itemKey || item.tabs.some((tab) => tab.tableName === tableName));
    runtime.execute({ name: "select-node", nodeKey: itemKey ?? owner?.itemKey ?? selectedNodeKey });
    runtime.execute({ name: "select-tab", tabKey: "__whole__:" + tableName });
  };
  // Double-clicking the sidebar edge fits the longest visible name; doing it
  // again at that width goes back to the default.
  const fitSidebarWidth = () => {
    const sidebar = workspaceRef.current?.querySelector<HTMLElement>(".navigation-sidebar");
    if (!sidebar) return;
    let needed = 0;
    for (const button of sidebar.querySelectorAll<HTMLElement>(".nav-item__button, .nav-group__heading")) {
      const label = button.querySelector<HTMLElement>(".nav-item__label, .nav-group__label");
      if (!label) continue;
      needed = Math.max(needed, sidebar.clientWidth - label.clientWidth + label.scrollWidth);
    }
    const fitted = clampSidebar(Math.ceil(needed) + 4);
    setSettings((state) => ({ ...state, sidebarWidth: Math.abs(state.sidebarWidth - fitted) <= 2 ? DEFAULT_SETTINGS.sidebarWidth : fitted }));
  };
  const updateSidebarWidth = (clientX: number) => {
    const left = workspaceRef.current?.getBoundingClientRect().left ?? 0;
    setSettings((state) => ({ ...state, sidebarWidth: clampSidebar(clientX - left) }));
  };
  const openFormula = useCallback(async (pointKey: string | null) => {
    if (!bundle || !presentation) return;
    const composite = presentation.surface.tables.find((item) => item.table_name === "composite_signal_point");
    if (!composite) return;
    const compositeLocatorPath = presentation.tableArtifacts.get(composite.table_name)?.rowLocator ?? null;
    const locatorRows = compositeLocatorPath
      ? await readParquetTable(bundle, compositeLocatorPath, { columns: ["row_identity", "before_row_index", "current_row_index", "before_filter_context_json", "current_filter_context_json"] })
      : [];
    const compositeLocator = parseRowLocator(locatorRows as Record<string, unknown>[]);
    const [before, current, beforeDevices, currentDevices] = await Promise.all([
      presentation.tableArtifacts.get(composite.table_name)?.before ? readLocalTable(bundle, presentation, composite.table_name, "before") : Promise.resolve([]),
      presentation.tableArtifacts.get(composite.table_name)?.current ? readLocalTable(bundle, presentation, composite.table_name, "current") : Promise.resolve([]),
      presentation.tableArtifacts.get("device")?.before ? readLocalTable(bundle, presentation, "device", "before") : Promise.resolve([]),
      presentation.tableArtifacts.get("device")?.current ? readLocalTable(bundle, presentation, "device", "current") : Promise.resolve([]),
    ]);
    const beforeRows = [...before as Record<string, unknown>[]];
    const currentRows = current as Record<string, unknown>[];
    const records = await readLocalChangeRecords(bundle, presentation, composite.table_name);
    const hasBeforeSnapshot = Boolean(presentation.tableArtifacts.get(composite.table_name)?.before);
    const deletedPointKeys = new Set<string>();
    for (const record of records) {
      const recordKind = String(record.record_kind ?? "");
      const values = recordValues(record.before_values);
      if (recordKind === "ROW_DELETED") {
        if (typeof values.source_table !== "string" || values.point_gid === undefined) continue;
        beforeRows.push(values);
        deletedPointKeys.add(`${values.source_table}:${String(values.point_gid)}`);
        continue;
      }
      if (browse.mode === "HISTORY" || hasBeforeSnapshot || !["ROW_MODIFIED", "ORDERED_ROW_MODIFIED"].includes(recordKind)
        || !("formula_digest" in values)) continue;
      const recordIdentity = normalizeRowIdentity((record.current_row_identity ?? record.row_identity) as never);
      const locatedIndex = recordIdentity ? compositeLocator.get(recordIdentity)?.currentRowIndex ?? null : null;
      const currentRow = locatedIndex === null ? undefined : currentRows[locatedIndex];
      if (!currentRow) continue;
      beforeRows.push({ ...currentRow, ...values, formula_ast_json: null });
    }
    setFormulas(deriveFormulaDisplays({ mode: browse.mode === "HISTORY" ? "HISTORY" : "PREVIEW", before: beforeRows, current: currentRows,
      beforeDevices: beforeDevices as Record<string, unknown>[], currentDevices: currentDevices as Record<string, unknown>[], deletedPointKeys }));
    setFormulaFocus(pointKey);
    setFormulaOpen(true);
  }, [browse.mode, bundle, presentation]);

  const activePairIndex = activePair ? pairs.findIndex(({ pair }) => pair.pair_id === activePair.pair.pair_id) : 0;
  const viewPairs = pairs;
  // The device path leads the breadcrumb (full path on hover); the view label is
  // left out when the view switcher is visible in the same row.
  const deviceDisplay = sessionState.kind === "handoff" ? sessionState.session.display : null;
  const breadcrumbItems = [
    activePair && viewPairs.length <= 1 ? viewLabel(activePair, activePairIndex, pairs.length, browse.mode) : null,
    selectedEntry?.group.label ?? null,
    selectedEntry?.item.label ?? null,
    selectedTab && selectedTab.label !== selectedEntry?.item.label ? selectedTab.label : null,
  ].filter((item): item is string => Boolean(item));
  const returnToWorkbench = () => {
    const params = new URLSearchParams({ page: "workspace" });
    if (browse.operationId) params.set("operationId", browse.operationId);
    if (browse.operationKind) params.set("operationKind", browse.operationKind);
    if (browse.workbenchNodeKey) params.set("workbenchNode", browse.workbenchNodeKey);
    for (const ref of browse.comparisonNodeRefs) params.append("compare", ref);
    window.location.assign(`/?${params.toString()}`);
  };

  if (isGatewaySessionBlocked(sessionState)) return <SessionGate state={sessionState} identityControl={identityControl} />;
  return <main ref={pageRef} className="comparison-page">
    {resumeOperationId && <div className="comparison-resume"><OperationStatusPanel operationId={resumeOperationId} onSucceeded={(id) => void finishSubmitResume(id)} onFailed={(id) => void finishSubmitResume(id)} /></div>}
    {resumeNotice && <div role="alert" className="form-error"><span>{resumeNotice.title}</span>{resumeNotice.code && <span>{resumeNotice.codeLabel ?? "操作ID"}：<code>{resumeNotice.code}</code><button className="link-button" onClick={() => void navigator.clipboard?.writeText(resumeNotice.code ?? "")}>复制</button></span>}<span className="form-error__actions"><button className="link-button" onClick={() => void retryResumeNotice()}>重试</button><button className="link-button" onClick={() => window.location.reload()}>刷新页面</button></span></div>}
    <header ref={headerRef} className="compare-header">
      <h1 className="sr-only">差异浏览</h1>
      <div className="compare-header__bar">
        <button className="icon-button compare-back" aria-label="返回工作台" title="返回工作台" onClick={returnToWorkbench}><ChevronLeft size={17} /></button>
        <nav className="breadcrumb" aria-label="位置">{deviceDisplay && <span className="breadcrumb__device" title={formatHandoffDisplay(deviceDisplay)}>{deviceDisplay.project_name}（{deviceDisplay.station_code}）</span>}{breadcrumbItems.map((item, index) => <span key={item + index}>{(index > 0 || deviceDisplay) && <span aria-hidden="true">›</span>}{item}</span>)}</nav>
        <span className="mode-tag">{browse.mode === "PREVIEW" ? "上传" : browse.mode === "REVIEW" ? "审核" : "历史比较 · 只读"}</span>
        {viewPairs.length > 1 && <div className="view-tabs" role="tablist" aria-label="比较视图">{viewPairs.map((pair) => { const index = pairs.findIndex(({ pair: item }) => item.pair_id === pair.pair.pair_id); const diagnostics = pairDiagnosticDetails(pair); const status = presentViewStatus(pair.presentation.surface.view, diagnostics.tableCount); const risk = viewRiskLevel(pair); const active = activePair?.pair.pair_id === pair.pair.pair_id; return <button role="tab" aria-selected={active} className={active ? "is-active" : ""} key={pair.pair.pair_id} onClick={() => choosePair(pair)} title={[viewTitle(pair, index, pairs.length, browse.mode), status.text, risk ? riskLevelText(risk) : null, ...status.tooltipItems].filter(Boolean).join(" · ")}><span>{viewLabel(pair, index, pairs.length, browse.mode)}</span>{risk && <RiskBadge level={risk} />}</button>; })}</div>}
        <div className="scope-toggle" role="group" aria-label="表格范围"><button className={!onlyInteresting ? "is-active" : ""} aria-pressed={!onlyInteresting} onClick={() => runtime.execute({ name: "set-only-interesting", enabled: false })}>全部</button><button className={onlyInteresting ? "is-active" : ""} aria-pressed={onlyInteresting} onClick={() => runtime.execute({ name: "set-only-interesting", enabled: true })}>仅看差异</button></div>
        <div className="compare-status"><ConnectionStatusIndicator compact hideConnected={Boolean(error)} />{historyCompareStatus && <><span className="compare-status__divider" /><span>{historyCompareStatus === "QUEUED" ? "排队中" : historyCompareStatus === "RUNNING" ? `执行中 · 已等待 ${formatWaitDuration(historyCompareWaited)}` : historyCompareStatus === "SUCCEEDED" ? "比较已完成" : historyCompareStatus === "FAILED" ? "比较失败" : "已取消"}</span></>}{reviewFacts && <span className="review-facts-status">审核：{reviewStatusLabel(reviewFacts.status)}</span>}{reviewFacts?.submission_disposition && <span className={`status-tag status-tag--${reviewFacts.submission_disposition.disposition === "ARCHIVED_BASELINE" ? "info" : "neutral"}`} title={reviewFacts.submission_disposition.disposition === "CLOSED_NOT_ARCHIVED" ? (reviewFacts.submission_disposition.source_kind === "ARCHIVE" ? "归档时选中了其他提交" : `由 ${reviewFacts.submission_disposition.closure?.closed_by ?? "未知"} 关闭：${reviewFacts.submission_disposition.closure?.reason ?? ""}`) : undefined}>{reviewFacts.submission_disposition.disposition === "ARCHIVED_BASELINE" ? "已归档" : "已关闭（未归档）"}</span>}{identityControl}
          {browse.mode === "PREVIEW" && <PreviewHeaderActions
            withdrawEnabled={uploadGates.withdraw.enabled}
            withdrawReason={uploadGates.withdraw.reason}
            withdrawRetry={Boolean(uploadGates.withdraw.retry && !uploadGates.withdraw.enabled)}
            withdrawRetryLabel={uploadGates.withdraw.retryLabel ?? "重试读取"}
            submitEnabled={Boolean(bundle) && uploadGates.submit.enabled}
            submitReason={!bundle ? "请等待差异结果加载完成" : uploadGates.submit.reason}
            onWithdraw={() => { setWithdrawUnderstood(false); setWithdrawError(null); withdrawKey.current = crypto.randomUUID(); setWithdrawOpen(true); }}
            onRetry={() => void refreshUploadMode()}
            onSubmit={() => { clearResumeNotice(); setSubmitOpen(true); }}
          />}
          {browse.mode === "REVIEW" && reviewFacts && browse.submissionId && <ReviewActions submissionId={browse.submissionId} facts={reviewFacts} bundleReady={Boolean(bundle)} onFactsChanged={setReviewFacts} onReviewSettled={reloadReviewContext} errorNoticeHost={reviewNoticeRef} />}
        </div>
        <details className="compare-more">
          <summary aria-label="更多" title="更多"><MoreHorizontal size={17} /></summary>
          <div className="compare-more__menu">
            <label className="compare-more__check"><input type="checkbox" checked={showEmptyTabs} onChange={toggleEmptyTabs} />显示空页签（没有行，共 {emptyTabCount} 个）</label>
            {import.meta.env.DEV && <div className="display-mode"><span>显示模式（开发环境）</span><div role="radiogroup" aria-label="显示模式"><button role="radio" aria-checked={!debug} className={!debug ? "is-active" : ""} onClick={() => runtime.execute({ name: "set-debug", enabled: false })}>User</button><button role="radio" aria-checked={debug} className={debug ? "is-active" : ""} onClick={() => runtime.execute({ name: "set-debug", enabled: true })}><Code2 size={13} /> Debug</button></div></div>}
            {widthTable && Object.keys(storedWidths).length > 0 && <button className="link-button compare-more__action" onClick={resetColumnWidths}>恢复本表默认列宽</button>}
            {browse.mode === "REVIEW" && pairs.map((pair, index) => <div key={pair.pair.pair_id} className="compare-more__bundle" data-pair-summary={pair.pair.pair_id}><strong>{viewLabel(pair, index, pairs.length, browse.mode)}</strong><span>变化表 {pair.pair.summary?.changed_table_count ?? "—"}/{pair.pair.summary?.table_count ?? "—"}</span><span>逐行 +{pair.pair.summary?.row_added_count ?? "—"} / ~{pair.pair.summary?.row_modified_count ?? "—"} / −{pair.pair.summary?.row_deleted_count ?? "—"}</span></div>)}
            {bundle && <div className="compare-more__bundle"><span>本地 bundle · 浏览期间不请求后端</span><code>{bundle.manifest.bundle_digest}</code></div>}
          </div>
        </details>
      </div>
      {browse.mode === "REVIEW" && reviewFacts?.submission_disposition && <ReviewDispositionLine facts={reviewFacts} />}
      {browse.mode === "REVIEW" && <div className="compare-header__notice" ref={reviewNoticeRef} />}
    </header>
    {activePair && pairDiagnosticDetails(activePair).codes.length > 0 && <div className="pair-diagnostic-strip" role="status">{pairDiagnosticDetails(activePair).codes.map((diagnostic) => { const formatted = formatSurfaceDiagnostic(diagnostic); return <div key={diagnostic}><AlertTriangle size={14} /><span>{formatted.message}</span>{debugMode && <code>{formatted.raw}</code>}</div>; })}</div>}
    {!bundle && !error && <section className="compare-loading"><LoadingSkeleton label={loading.phase} /><div className="loading-progress"><span>{loading.phase}</span><span>{loading.total ? formatBytes(loading.received) + " / " + formatBytes(loading.total) : "正在准备"}</span></div></section>}
    {error && <section className="compare-error"><ErrorState code={error.code} details={error.details} title={error.code === "SCOPE_FORBIDDEN" ? "当前身份没有该操作的权限" : bundleErrorTitle(error.code)} onRetry={() => void loadBundle()} /></section>}
    {bundle && presentation && <div ref={workspaceRef} className={"compare-workspace" + (collapsed ? " sidebar-is-collapsed" : "")} style={{ "--sidebar-width": settings.sidebarWidth + "px" } as CSSProperties}>
      <aside className="navigation-sidebar" aria-label="比较导航"><div className="sidebar-heading"><div className="sidebar-search"><Search size={14} /><input ref={searchInputRef} aria-label="搜索组、节点或页签" value={search} onChange={(event) => runtime.execute({ name: "set-search", search: event.currentTarget.value })} placeholder={`搜索 · ${presentation.view.tables.length} 张表`} /></div><button className="icon-button" aria-label="收起导航" title="收起导航" onClick={() => setSettings((state) => ({ ...state, sidebarCollapsed: true }))}><ChevronLeft size={16} /></button></div>
        {globalNavigationDiagnostics.map((diagnostic, index) => <NavigationDiagnosticNote key={diagnostic.code + index} diagnostic={diagnostic} tables={presentation.surface.tables} debug={debugMode} onOpenWholeTable={openWholeTable} />)}
        <div className="sidebar-scroll">{visibleGroups.map((group) => {
          const groupMatches = group.label.toLocaleLowerCase().includes(browse.search.trim().toLocaleLowerCase());
          const items = group.items.filter((item) => (groupMatches || matchesItem(item, browse.search)) && shownTabs(item).length > 0);
          const groupDiagnostics = presentation.navigationDiagnostics.filter((diagnostic) => diagnostic.target.group_key === group.groupKey);
          if (items.length === 0 && groupDiagnostics.length === 0) return null;
          return <section className="nav-group" key={group.groupKey}><button className="nav-group__heading" aria-expanded={!settings.collapsedGroups.includes(group.groupKey)} onClick={() => { runtime.execute({ name: "toggle-group", groupKey: group.groupKey }); setSettings((state) => ({ ...state, collapsedGroups: state.collapsedGroups.includes(group.groupKey) ? state.collapsedGroups.filter((key) => key !== group.groupKey) : [...state.collapsedGroups, group.groupKey] })); }}><ChevronDown className={settings.collapsedGroups.includes(group.groupKey) ? "is-closed" : ""} size={14} /><span className="nav-group__label">{group.label}</span><small title="非空项">{items.filter((item) => item.nonemptyTabCount > 0).length}</small>{groupDiagnostics.length > 0 && <small className="nav-group__diagnostic-count">{groupDiagnostics.length} 条提示</small>}</button>
          {presentation.navigationDiagnostics.filter((diagnostic) => diagnostic.target.group_key === group.groupKey && !diagnostic.target.item_key && !diagnostic.target.tab_key).map((diagnostic, index) => <NavigationDiagnosticNote key={diagnostic.code + index} diagnostic={diagnostic} tables={presentation.surface.tables} debug={debugMode} onOpenWholeTable={openWholeTable} />)}
          {!settings.collapsedGroups.includes(group.groupKey) && items.map((item) => { const itemTabs = shownTabs(item); const active = item.itemKey === selectedNodeKey; const { changeKinds, riskLevels } = item; const itemState = changeKinds.map((kind) => surfaceChangePresentation(kind).text).join("、") || "未变化"; const itemKind = itemBadgeKind(changeKinds); const itemTitle = `${item.label} · ${itemState}${itemStatusTooltip(changeKinds) ? " · " + itemStatusTooltip(changeKinds) : ""}${riskLevels[0] ? " · " + riskLevelText(riskLevels[0]) : ""}`; return <div className={active ? "nav-item is-active" : "nav-item"} key={item.itemKey} data-item-key={item.itemKey} ref={active ? selectedNavRef : undefined}><button className="nav-item__button" onClick={() => { const tab = itemTabs[0]; if (tab) chooseTab(tab.tableName, tab.tabKey, item.itemKey); }} title={itemTitle}><span className={"nav-icon nav-icon--" + item.itemKind.toLowerCase()}><Table2 size={15} /></span><span className={changeKinds.some((kind) => surfaceChangePresentation(kind).deleted) ? "nav-item__label is-deleted" : "nav-item__label"}>{item.label}</span>{riskLevels[0] ? <RiskBadge level={riskLevels[0]} /> : <SurfaceChangeBadge kind={itemKind} />}</button>
            {presentation.navigationDiagnostics.filter((diagnostic) => diagnostic.target.item_key === item.itemKey && !diagnostic.target.tab_key).map((diagnostic, index) => <NavigationDiagnosticNote key={diagnostic.code + index} diagnostic={diagnostic} tables={presentation.surface.tables} debug={debugMode} onOpenWholeTable={openWholeTable} />)}
          </div>; })}</section>; })}</div>
      </aside>
      {!collapsed && <div className="sidebar-resize" role="separator" aria-label="调整侧栏宽度（双击适应名称）" title="拖动调整宽度，双击适应名称" onDoubleClick={fitSidebarWidth} aria-orientation="vertical" aria-valuemin={SIDEBAR_MIN} aria-valuemax={SIDEBAR_MAX} aria-valuenow={settings.sidebarWidth} tabIndex={0} onPointerDown={(event) => event.currentTarget.setPointerCapture(event.pointerId)} onPointerMove={(event) => { if (event.buttons) updateSidebarWidth(event.clientX); }} onPointerUp={(event) => event.currentTarget.releasePointerCapture(event.pointerId)} onKeyDown={(event) => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); setSettings((state) => ({ ...state, sidebarWidth: clampSidebar(state.sidebarWidth + (event.key === "ArrowRight" ? 16 : -16)) })); } }} />}
      <button className="sidebar-expand" aria-label="展开导航" onClick={() => { setSettings((state) => ({ ...state, sidebarCollapsed: false })); window.requestAnimationFrame(() => searchInputRef.current?.focus()); }}><ChevronRight size={16} /><Search size={15} /><span>{selectedTab?.label ?? "当前位置"}</span></button>
      <section className="comparison-content" aria-label="比较内容">
        {selectedItem && stripVisible && <div className="overflow-tabs" role="tablist" aria-label="表格页签"><ScrollStrip>{stripTabs.map((tab) => { const active = !wholeTable && selectedTab?.tabKey === tab.tabKey && selectedTab.tableName === tab.tableName; const risk = tabRiskLevel(tab); const kind = tabChangeKind(tab); const change = surfaceChangePresentation(kind); const beforeCount = tabCount(tab, "before"); const currentCount = tabCount(tab, "current"); const warned = presentation.navigationDiagnostics.some(({ target }) => target.item_key === selectedItem.itemKey && target.tab_key === tab.tabKey); return <button role="tab" aria-selected={active} key={tab.tabKey + "|" + tab.tableName} data-tab-key={tab.tabKey} className={active ? "is-active" : ""} onClick={() => chooseTab(tab.tableName, tab.tabKey, selectedItem.itemKey)} title={tabTitle(kind, risk, beforeCount, currentCount) + (warned ? " · 有提示" : "")}>{warned && <AlertTriangle className="overflow-tabs__warn" size={12} aria-label="有提示" />}<span className={change.deleted ? "nav-item__label is-deleted" : "nav-item__label"}>{tab.label}</span><small>{beforeCount ?? "—"} → {currentCount ?? "—"}</small>{risk ? <RiskBadge level={risk} /> : <SurfaceChangeBadge kind={kind} />}</button>; })}{wholeTable && <button role="tab" aria-selected className="is-active" data-tab-key={"__whole__:" + wholeTable.tableName}><span className="nav-item__label">整表：{wholeTable.label}</span></button>}</ScrollStrip>{itemEmptyTabCount > 0 && <button className="overflow-tabs__empty-toggle" aria-pressed={showEmptyTabs} title="没有行的页签" onClick={toggleEmptyTabs}>{showEmptyTabs ? "隐藏空页签" : `+${itemEmptyTabCount} 个空页签`}</button>}</div>}
          {selectedTab && table && surfaceTable ? <>
            {(() => {
              // One info line: what changed and how many rows; reasons and notes open as popovers.
              const tabNotes = selectedItem ? presentation.navigationDiagnostics.filter(({ target }) => target.item_key === selectedItem.itemKey && target.tab_key === selectedTab.tabKey) : [];
              const tableNotes = presentation.navigationDiagnostics.filter((item) => !item.target.group_key && !item.target.item_key && !item.target.tab_key && item.target.table_id === selectedTab.tableName);
              const surfaceNotes = surfaceTable.diagnostics?.diagnostics_summary ?? [];
              const fallback = selectedTab.facts?.basis === "TABLE_FALLBACK";
              const schemaChanged = table.changeKind === "SCHEMA_CHANGED";
              const noteCount = surfaceNotes.length + tabNotes.length + tableNotes.length + (fallback ? 1 : 0) + (schemaChanged ? 1 : 0);
              const filtered = selectedTab.rowFilter !== null;
              const wholeTableChange = table.changeKind === "ADDED" || table.changeKind === "DELETED";
              const scope = filtered ? selectedTab.facts?.table_scope ?? table.tableScope : table.tableScope;
              const change = surfaceChangePresentation(table.changeKind);
              const viewKey = selectedNodeKey + "|" + selectedTab.tabKey + "|" + selectedTab.tableName;
              return <div className="table-info">
                <h2 className={stripVisible ? "sr-only" : "table-info__title"}>{selectedTab.label || table.label}</h2>
                <SurfaceChangeBadge kind={table.changeKind} />
                {table.riskLevel && <span title={riskLevelText(table.riskLevel)}><RiskBadge level={table.riskLevel} /></span>}
                <span className={table.changeKind === "DEGRADED" ? "table-info__warn" : "table-info__muted"} title={[change.text, change.tooltip].filter(Boolean).join(" · ")}>{tableStatusText(table)}</span>
                {filtered && <span className="table-info__counts">本页 {tabCount(selectedTab, "before") ?? "—"} → {tabCount(selectedTab, "current") ?? "—"} 行</span>}
                <span className={filtered ? "table-info__muted table-info__counts" : "table-info__counts"}>{filtered ? "整表 " : ""}{table.rowCounts.before ?? "—"} → {table.rowCounts.current ?? "—"} 行</span>
                {!wholeTableChange && <span className="table-info__muted table-info__counts" title="新增 / 删除 / 修改的行">+{surfaceTable.row_change_stats?.row_added_count ?? 0} / −{surfaceTable.row_change_stats?.row_deleted_count ?? 0} / ↔{surfaceTable.row_change_stats?.row_modified_count ?? 0}</span>}
                {rowRiskCounts.map(({ level, count }) => <span className="table-info__risk-count" key={level}><RiskBadge level={level} /><span>{count}</span></span>)}
                {table.annotationCount > 0 && <span className="table-info__muted">{table.annotationCount} 条风险标注</span>}
                {selectedTab.tabKey.startsWith("__whole__:") && <span className="table-info__muted">整表视图</span>}
                {scope && <span className="table-scope-marker" title={scope.risk_level ? riskLevelText(scope.risk_level) : "整表范围"}>{scope.change ? "整表发生变化" : "整表未变化"}{scope.risk_level ? " · 整表风险" : ""}</span>}
                <span className="table-info__spacer" />
                {riskReasonDetails.length > 0 && <InfoPopover key={viewKey + "|risk"} tone="risk" label={`风险原因 ${riskReasonDetails.length}`}>
                  <div className="info-popover__list">{riskReasonDetails.map((detail) => <span key={detail.reasonCode + detail.ruleId} title={`reason_code=${detail.reasonCode}${detail.ruleId ? ` · rule_id=${detail.ruleId}` : ""}`}>{detail.copy}{debugMode && <code>{detail.reasonCode}{detail.ruleId ? " · " + detail.ruleId : ""}</code>}</span>)}</div>
                </InfoPopover>}
                {noteCount > 0 && <InfoPopover key={viewKey + "|notes"} tone="warn" label={`提示 ${noteCount}`}>
                  <div className="info-popover__list">
                    {surfaceNotes.map((diagnostic, index) => { const formatted = formatSurfaceDiagnostic(diagnostic); return <span key={diagnostic + index}>{formatted.message}{debugMode && <code>{formatted.raw}</code>}</span>; })}
                    {fallback && <span>此页签的变化和风险按整表提示，不是本页签自己的。</span>}
                    {schemaChanged && <span>{formatSchemaSummary(surfaceTable.schema_summary)}</span>}
                    {tableNotes.map((item, index) => <span key={item.code + index}>{formatNavigationDiagnostic(item, presentation.surface.tables)}{debugMode && <code>{item.code}</code>}</span>)}
                  </div>
                  {tabNotes.map((diagnostic, index) => <NavigationDiagnosticNote key={diagnostic.code + index} diagnostic={diagnostic} tables={presentation.surface.tables} debug={debugMode} onOpenWholeTable={openWholeTable} />)}
                </InfoPopover>}
              </div>;
            })()}
            {debugMode && <DebugInfoBar table={surfaceTable} reasonDetails={riskReasonDetails} />}
            {replacement ? <ReplacementBrowser before={beforeRows} current={currentRows} table={surfaceTable} assessment={presentation.projectIdentityAssessment} side={browse.side} onSelectSide={(side) => runtime.execute({ name: "select-side", side })} /> : table.changeKind === "FAILED" ? <TableFailureNotice table={table} /> : <>
              {tableLoading ? <LoadingSkeleton label="正在读取本地表格" /> : <div className={`table-grid-area${locations.length || rows.some((row) => row.kind === "unchanged" && row.riskLevel !== null) ? " has-distribution" : ""}`}>
                <GridTable rows={rows} table={surfaceTable} tabKey={selectedTab.tabKey} annotations={annotations} debug={debugMode} highlightedIdentity={locations[currentIndex]?.rowIdentity ?? null} storedWidths={storedWidths} onWidthChange={changeColumnWidth} onVisibleRows={setVisibleRows} onExpand={(row) => setExpandedRuns((old) => { const next = new Set(old); if (next.has(row.key)) next.delete(row.key); else next.add(row.key); return next; })} onOpenFormula={(pointKey) => void openFormula(pointKey)} />
                {(locations.length > 0 || rows.some((row) => row.kind === "unchanged" && row.riskLevel !== null)) && <ChangeNavigator locations={locations} riskRows={rows.filter((row) => row.kind === "unchanged" && row.riskLevel !== null && row.rowNumber !== null)} rowCount={Math.max(table.rowCounts.before ?? 0, table.rowCounts.current ?? 0)} visibleRows={visibleRows} currentIndex={currentIndex} onJump={(index) => runtime.execute({ name: "jump-to-change", index })} />}
              </div>}
            </>}</> : <div className="empty-table">请选择一个导航页签。</div>}
      </section>
    </div>}
    {browse.mode === "PREVIEW" && browse.workspaceId && browse.previewResultId && <SubmitDialog open={submitOpen} workspaceId={browse.workspaceId} previewResultId={browse.previewResultId} onClose={() => setSubmitOpen(false)} onSubmitted={(submissionId) => {
      const params = new URLSearchParams({ page: "compare", mode: "REVIEW", submissionId });
      if (browse.workbenchNodeKey) params.set("workbenchNode", browse.workbenchNodeKey);
      for (const ref of browse.comparisonNodeRefs) params.append("compare", ref);
      window.location.assign(`/?${params.toString()}`);
    }} />}
    <Dialog open={withdrawOpen} title="撤回提交" onClose={() => { if (!withdrawBusy) setWithdrawOpen(false); }} actions={<>
      <Button variant="secondary" onClick={() => setWithdrawOpen(false)} disabled={withdrawBusy}>取消</Button>
      <Button variant="danger" onClick={() => void confirmWithdraw()} disabled={withdrawBusy || !withdrawUnderstood} disabledReason={!withdrawUnderstood ? "请先确认已了解撤回影响" : undefined}>{withdrawBusy ? "撤回中…" : "确认撤回"}</Button>
    </>}>
      <p className="confirm-impact">撤回后该提交不再进入归档候选，也无法继续审核；提交人需要重新上传并提交。此操作不可撤销。</p>
      <label className="confirm-checkbox"><input type="checkbox" checked={withdrawUnderstood} onChange={(event) => setWithdrawUnderstood(event.currentTarget.checked)} />我已了解撤回后需要重新提交，并确认继续</label>
      {withdrawError && <div role="alert" className="form-error"><span>{withdrawError.title}</span><span>错误代码：<code>{withdrawError.code}</code></span></div>}
    </Dialog>
    {formulaOpen && <div className="formula-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setFormulaOpen(false); }}><aside className="formula-drawer" role="dialog" aria-modal="true" aria-labelledby="formula-title"><header><div><span className="section-kicker">复合信号公式</span><h2 id="formula-title">公式查看</h2></div><button className="icon-button" aria-label="关闭公式" onClick={() => setFormulaOpen(false)}><X size={18} /></button></header><div className="formula-drawer__body">{(() => {
      // The clicked row's formula; the full list is one click away.
      const focused = formulaFocus ? formulas.filter((formula) => formula.pointKey === formulaFocus) : [];
      const shown = focused.length > 0 ? focused : formulas;
      return <>
        {formulaFocus && focused.length === 0 && <p className="formula-drawer__note">没有找到该行的公式，下面列出全部 {formulas.length} 条。</p>}
        {focused.length > 0 && formulas.length > 1 && <button className="link-button formula-drawer__all" onClick={() => setFormulaFocus(null)}>显示全部 {formulas.length} 条公式</button>}
        {shown.map((formula) => <FormulaCard key={formula.pointKey} formula={formula} preview={browse.mode !== "HISTORY"} />)}
      </>;
    })()}</div></aside></div>}
  </main>;
}

/** A sideways strip without a scrollbar: the wheel scrolls it and arrows appear at hidden edges. */
function ScrollStrip({ children }: { children: ReactNode }) {
  const stripRef = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ left: false, right: false });
  useEffect(() => {
    const strip = stripRef.current;
    if (!strip) return;
    const update = () => setEdges((previous) => {
      const left = strip.scrollLeft > 1;
      const right = strip.scrollLeft + strip.clientWidth < strip.scrollWidth - 1;
      return previous.left === left && previous.right === right ? previous : { left, right };
    });
    const wheel = (event: WheelEvent) => {
      if (strip.scrollWidth <= strip.clientWidth || Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
      strip.scrollLeft += event.deltaY;
      event.preventDefault();
    };
    update();
    strip.addEventListener("scroll", update);
    strip.addEventListener("wheel", wheel, { passive: false });
    const resize = new ResizeObserver(update);
    resize.observe(strip);
    const content = new MutationObserver(update);
    content.observe(strip, { childList: true, subtree: true });
    return () => { strip.removeEventListener("scroll", update); strip.removeEventListener("wheel", wheel); resize.disconnect(); content.disconnect(); };
  }, []);
  const scroll = (direction: -1 | 1) => stripRef.current?.scrollBy({ left: direction * 280, behavior: "smooth" });
  return <>
    {edges.left && <button type="button" className="overflow-tabs__arrow" aria-label="向左查看页签" onClick={() => scroll(-1)}><ChevronLeft size={15} /></button>}
    <div ref={stripRef} className="overflow-tabs__visible">{children}</div>
    {edges.right && <button type="button" className="overflow-tabs__arrow" aria-label="向右查看页签" onClick={() => scroll(1)}><ChevronRight size={15} /></button>}
  </>;
}

/** A small button in the table info line that opens its details over the grid. */
function InfoPopover({ label, tone, children }: { label: string; tone: "risk" | "warn"; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (event: MouseEvent) => { if (!rootRef.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("mousedown", outside); document.removeEventListener("keydown", escape); };
  }, [open]);
  return <div ref={rootRef} className={`info-popover info-popover--${tone}`}>
    <button type="button" aria-expanded={open} onClick={() => setOpen((value) => !value)}><AlertTriangle size={13} aria-hidden="true" />{label}<ChevronDown size={13} aria-hidden="true" /></button>
    {open && <div className="info-popover__panel" role="dialog" aria-label={label}>{children}</div>}
  </div>;
}

function PreviewHeaderActions({ withdrawEnabled, withdrawReason, withdrawRetry, withdrawRetryLabel, submitEnabled, submitReason, onWithdraw, onRetry, onSubmit }: {
  withdrawEnabled: boolean;
  withdrawReason?: string;
  withdrawRetry: boolean;
  withdrawRetryLabel: "刷新" | "重试读取";
  submitEnabled: boolean;
  submitReason?: string;
  onWithdraw: () => void;
  onRetry: () => void;
  onSubmit: () => void;
}) {
  // C3: the withdraw and submit disabled reasons render in their own
  // button-wrapped spans (see Button), separated by an explicit divider so
  // the two reasons never read as one sentence.
  return <span className="compare-actions">
    <Button variant="danger" onClick={onWithdraw} disabled={!withdrawEnabled} disabledReason={withdrawReason}>撤回</Button>
    {withdrawRetry && <button className="link-button" onClick={onRetry}>{withdrawRetryLabel}</button>}
    {withdrawReason && submitReason && <span className="compare-actions__divider" aria-hidden="true" />}
    <Button variant="primary" onClick={onSubmit} disabled={!submitEnabled} disabledReason={submitReason}>提交</Button>
  </span>;
}

function ChangeNavigator({ locations, riskRows, rowCount, visibleRows, currentIndex, onJump }: {
  locations: ReturnType<typeof deriveChangeLocations>;
  riskRows: BrowseRow[];
  rowCount: number;
  visibleRows: { start: number; end: number };
  currentIndex: number;
  onJump: (index: number) => void;
}) {
  if (!locations.length && !riskRows.length) return <div className="change-navigator"><span>没有行级变化</span></div>;
  const index = Math.min(currentIndex, Math.max(0, locations.length - 1));
  const range = Math.max(rowCount, 1);
  const toPercent = (position: number) => Math.max(0, Math.min(100, (position - .5) / range * 100));
  const selectedPosition = locations[index]?.position ?? index + 1;
  const visibleStart = Math.max(1, visibleRows.start);
  const visibleEnd = Math.max(visibleStart, visibleRows.end);
  const visibleTop = toPercent(visibleStart);
  const visibleBottom = Math.min(100, (visibleEnd / range) * 100);
  return <div className="change-navigator"><div className="change-navigator__controls">{locations.length ? <><span>变更 <strong>{index + 1}</strong> / {locations.length}</span><button aria-label="上一个变更" onClick={() => onJump(Math.max(0, index - 1))} disabled={index === 0}><ArrowUp size={15} /></button><button aria-label="下一个变更" onClick={() => onJump(Math.min(locations.length - 1, index + 1))} disabled={index === locations.length - 1}><ArrowDown size={15} /></button></> : <span>没有行级变化</span>}</div><div className="distribution-strip" role="group" aria-label={locations.length + " 个变更的位置分布"}>
    <span className="distribution-visible-range" aria-hidden="true" style={{ top: visibleTop + "%", height: Math.max(1, visibleBottom - visibleTop) + "%" }} />
    {riskRows.map((row) => <span key={"risk:" + row.key} aria-label={"第 " + (row.rowNumber ?? "未知") + " 行风险"} className={"distribution-mark distribution-mark--risk-only distribution-mark--" + (row.riskLevel ?? "UNKNOWN").toLowerCase().replace("_", "-")} style={{ top: toPercent(row.rowNumber ?? 1) + "%" }} />)}
    {locations.map((location, itemIndex) => { const position = location.position ?? itemIndex + 1; return <button key={String(location.rowIdentity) + itemIndex} aria-label={"定位第 " + (itemIndex + 1) + " 个变更"} className={"distribution-mark" + (location.riskLevel ? " distribution-mark--" + location.riskLevel.toLowerCase().replace("_", "-") : "") + (itemIndex === index ? " is-current" : "")} style={{ top: toPercent(position) + "%" }} onClick={() => onJump(itemIndex)} />; })}
    {locations.length > 0 && <span className="distribution-current-position" aria-hidden="true" style={{ top: toPercent(selectedPosition) + "%" }} />}
  </div></div>;
}

function NavigationDiagnosticNote({ diagnostic, tables, debug, onOpenWholeTable }: {
  diagnostic: Parameters<typeof formatNavigationDiagnostic>[0];
  tables: readonly SurfaceTable[];
  debug: boolean;
  onOpenWholeTable: (tableName: string, itemKey?: string | null) => void;
}) {
  const message = formatNavigationDiagnostic(diagnostic, tables);
  const canOpenWholeTable = diagnostic.code === "DEVICE_ROWS_UNASSIGNED" && Boolean(diagnostic.target.table_id);
  return <div className="diagnostic-note diagnostic-note--navigation"><AlertTriangle size={14} /><span>{message}</span>{canOpenWholeTable && <button onClick={() => onOpenWholeTable(diagnostic.target.table_id as string, diagnostic.target.item_key)}>查看整表</button>}{debug && <code>{JSON.stringify({ code: diagnostic.code, target: diagnostic.target, side: diagnostic.side, params: diagnostic.params })}</code>}</div>;
}

type RiskReasonDetail = { reasonCode: string; ruleId: string | null; copy: string };

function DebugInfoBar({ table, reasonDetails }: { table: SurfaceTable; reasonDetails: RiskReasonDetail[] }) {
  const schema = table.compare?.projection_schema_digest;
  const content = table.compare?.projection_logical_digest;
  return <div className="debug-info-bar" aria-label="调试信息"><span className="debug-info-bar__tag">Debug</span>
    <CopyDebugValue label="Raw Table" value={table.table_name} />
    {schema && <CopyDebugValue label="Schema" value={schema} />}
    {content && <CopyDebugValue label="Content" value={content} />}
    <span className="debug-info-bar__status"><span>表状态</span><code>{table.table_status}</code></span>
    {reasonDetails.map((reason) => <span className="debug-info-bar__status" key={reason.reasonCode + reason.ruleId}><span>风险</span><code>{reason.reasonCode}{reason.ruleId ? " · " + reason.ruleId : ""}</code></span>)}
  </div>;
}

function CopyDebugValue({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1400);
    return () => window.clearTimeout(timer);
  }, [copied]);
  const display = value.startsWith("sha256:") && value.length > 19 ? value.slice(0, 19) + "…" : value;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  return <button className="debug-info-value" type="button" aria-label={`复制 ${label}`} title={`复制完整值：${value}`} onClick={() => void copy()}><span>{label}</span><code>{display}</code><Copy size={12} />{copied && <span className="sr-only" aria-live="polite">已复制</span>}</button>;
}

function GridTable({ rows, table, tabKey, annotations, debug, highlightedIdentity, storedWidths, onWidthChange, onVisibleRows, onExpand, onOpenFormula }: { rows: BrowseRow[]; table: SurfaceTable; tabKey: string; annotations: RiskAnnotation[]; debug: boolean; highlightedIdentity: string | null; storedWidths: Readonly<Record<string, number>>; onWidthChange: (columnId: string, width: number) => void; onVisibleRows: (range: { start: number; end: number }) => void; onExpand: (row: BrowseRow) => void; onOpenFormula: (pointKey: string | null) => void }) {
  const gridRef = useRef<DataEditorRef>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const [frameSize, setFrameSize] = useState({ width: 0, height: 0 });
  const [paintedToken, setPaintedToken] = useState<object | null>(null);
  const [hoveredCell, setHoveredCell] = useState<readonly [number, number] | null>(null);
  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    // The grid fills the frame, which takes the remaining height of the page.
    const measure = () => setFrameSize((previous) => previous.width === frame.clientWidth && previous.height === frame.clientHeight ? previous : { width: frame.clientWidth, height: frame.clientHeight });
    const observer = new ResizeObserver(measure);
    observer.observe(frame);
    measure();
    return () => observer.disconnect();
  }, []);
  const orderedColumns = useMemo(() => [...(table.columns ?? [])].sort((left, right) => left.display_order - right.display_order), [table.columns]);
  const pinnedColumnCount = useMemo(() => { let count = 0; for (const column of orderedColumns) { if (!column.pinned) break; count += 1; } return count; }, [orderedColumns]);
  const metaColumnCount = debug ? 5 : 2;
  const frozenColumnCount = metaColumnCount + pinnedColumnCount;
  const theme = useMemo(() => createTableTheme(), []);
  const measureCell = useMemo(() => createTextMeasure(`${theme.baseFontStyle} ${theme.fontFamily}`), [theme.baseFontStyle, theme.fontFamily]);
  const measureHeader = useMemo(() => createTextMeasure(`${theme.headerFontStyle} ${theme.fontFamily}`), [theme.headerFontStyle, theme.fontFamily]);
  // Text the grid shows for a sizable column (row labels for 变更, values otherwise).
  const columnText = useCallback((row: BrowseRow, columnId: string): string => columnId === "__diff" ? rowLabel(row) : row.kind === "collapsed" ? "" : normalizeDisplayScalar(row.values[columnId]), []);
  const fitColumn = useCallback((columnId: string, title: string, sourceRows: readonly BrowseRow[], mode: "auto" | "fit") =>
    fitWidth(measureHeader(title), sourceRows.map((row) => measureCell(columnText(row, columnId))), mode), [columnText, measureCell, measureHeader]);
  // Automatic widths are worked out once per table view (when its rows first
  // arrive), so expanding runs or toggling the scope does not shift columns.
  const autoWidthKey = `${table.table_name}|${tabKey}|${debug ? "debug" : "user"}|${rows.length > 0 ? "rows" : "empty"}`;
  const autoWidths = useMemo(() => {
    const sample = sampleRows(rows, 600);
    const widths = new Map<string, number>([["__diff", fitColumn("__diff", "变更", sample, "auto")]]);
    for (const column of orderedColumns) widths.set(column.name, fitColumn(column.name, column.display_name || column.name, sample, "auto"));
    return widths;
    // Keyed on the table view, not on rows: later row changes must not move columns.
  }, [autoWidthKey, fitColumn, orderedColumns]);
  const columns = useMemo<SizedGridColumn[]>(() => {
    const width = (id: string, fallback: number) => storedWidths[id] ?? autoWidths.get(id) ?? fallback;
    const meta: SizedGridColumn[] = [{ id: "__number", title: "#", width: 60 }, { id: "__diff", title: "变更", width: width("__diff", 150) }];
    if (debug) meta.push({ id: "__kind", title: "Diff Kind", width: width("__kind", 210) }, { id: "__role", title: "Row Role", width: width("__role", 84) }, { id: "__semantic", title: "Ordered Semantic / Position", width: width("__semantic", 260) });
    return [...meta, ...orderedColumns.map((column) => ({ id: column.name, title: column.display_name || column.name, width: width(column.name, 120) }))];
  }, [autoWidths, debug, orderedColumns, storedWidths]);
  const resizeColumn = useCallback((column: GridColumn, newSize: number) => {
    if (typeof column.id === "string" && column.id !== "__number") onWidthChange(column.id, Math.round(newSize));
  }, [onWidthChange]);
  // Double-clicking a header's right edge fits the column to its longest value.
  // Glide does not report clicks on header edges (its own fit needs a
  // selection reader we do not provide), so the edge under the pointer is
  // tracked from mouse moves and the frame's native double-click fits it.
  const edgeColumn = useRef<number | null>(null);
  const fitEdgeColumn = useCallback(() => {
    const column = edgeColumn.current === null ? undefined : columns[edgeColumn.current];
    if (!column || typeof column.id !== "string" || column.id === "__number") return;
    onWidthChange(column.id, fitColumn(column.id, String(column.title), sampleRows(rows, 5000), "fit"));
  }, [columns, fitColumn, onWidthChange, rows]);
  const paintToken = useMemo(() => ({}), [columns, rows]);
  const rendered = paintedToken === paintToken;
  const markPainted = useCallback(() => {
    setPaintedToken((previous) => previous === paintToken ? previous : paintToken);
  }, [paintToken]);
  useEffect(() => {
    if (rows.length !== 0) return;
    let secondFrame = 0;
    const firstFrame = requestAnimationFrame(() => { secondFrame = requestAnimationFrame(markPainted); });
    return () => { cancelAnimationFrame(firstFrame); if (secondFrame) cancelAnimationFrame(secondFrame); };
  }, [markPainted, rows.length]);
  const formulaColumnIndex = columns.findIndex((column) => column.id === "formula_ast_json");
  const formulaColumnOffset = formulaColumnIndex < 0 ? undefined : columns.slice(0, formulaColumnIndex).reduce((width, column) => width + column.width, 0);
  const formulaColumnWidth = formulaColumnIndex < 0 ? undefined : columns[formulaColumnIndex]?.width;
  // The row position is a ruler, not data: smaller, lighter, on the header tone.
  const numberTheme = useMemo<Partial<Theme>>(() => ({ textDark: "#8B95A1", bgCell: theme.bgHeader, baseFontStyle: "12px" }), [theme.bgHeader]);
  const pairRows = useMemo(() => { const result = new Map<string, number[]>(); rows.forEach((row, index) => { if (row.pairKey) result.set(row.pairKey, [...(result.get(row.pairKey) ?? []), index]); }); return result; }, [rows]);
  useEffect(() => {
    if (!highlightedIdentity) return;
    const row = rows.findIndex((item) => item.rowIdentity === highlightedIdentity);
    if (row >= 0) gridRef.current?.scrollTo(1, row, "vertical", 0, 0, { vAlign: "center" });
  }, [highlightedIdentity, rows]);
  const getCellContent = useCallback(([columnIndex, rowIndex]: readonly [number, number]): GridCell => {
    const row = rows[rowIndex]; const column = columns[columnIndex];
    if (!row || !column || typeof column.id !== "string") return { kind: GridCellKind.Loading, allowOverlay: false };
    const columnId = column.id;
    const pair = row.pairKey ? pairRows.get(row.pairKey) : undefined;
    const detached = pair && (pair.length !== 2 || Math.abs((pair[0] ?? 0) - (pair[1] ?? 0)) > 1);
    const beforePairRow = pair?.map((index) => rows[index]).find((candidate) => candidate?.kind === "modified-before");
    const formulaChanged = row.kind === "modified-after"
      && (beforePairRow ? beforePairRow.values.formula_digest !== row.values.formula_digest : row.formulaChanged === true);
    let value: unknown;
    if (columnId === "__number") value = row.rowNumber ?? "";
    else if (columnId === "__diff") value = row.kind === "collapsed" ? rowLabel(row) : rowLabel(row) + (detached ? " ↔" : "");
    else if (columnId === "__kind") value = row.recordKind ?? "—";
    else if (columnId === "__role") value = row.kind === "modified-before" ? "前" : row.kind === "modified-after" ? "后" : "—";
    else if (columnId === "__semantic") value = row.semanticKind ? row.semanticKind + " · " + (row.beforePosition ?? "—") + " → " + (row.currentPosition ?? "—") : "—";
    else if (columnId === "formula_ast_json" && table.table_name === "composite_signal_point") {
      value = "查看公式" + (formulaChanged ? " · 公式已改" : "");
    } else {
      const columnShape = orderedColumns.find((item) => item.name === columnId);
      value = missingSideMarker(row.side, columnShape?.present_in) ?? row.values[columnId];
    }
    const risk = row.riskLevel ? riskTokens(row.riskLevel) : null;
    const changed = row.changedColumns.includes(columnId);
    const boldStyle = row.kind === "modified-after" && changed ? `600 ${theme.baseFontStyle}` : undefined;
    const cellTheme = risk
      ? { bgCell: changed ? risk.cell : risk.bg, textDark: row.kind === "modified-before" || row.kind === "deleted" ? "#535D69" : risk.text, ...(boldStyle ? { baseFontStyle: boldStyle } : {}) }
      : changed ? { bgCell: "#E6E9ED", textDark: "#1B2229", ...(boldStyle ? { baseFontStyle: boldStyle } : {}) } : undefined;
    return { kind: GridCellKind.Text, data: normalizeDisplayScalar(value), displayData: normalizeDisplayScalar(value), allowOverlay: false,
      style: row.kind === "modified-before" || row.kind === "deleted" ? "faded" : "normal",
      ...(columnId === "__number" ? { contentAlign: "right" as const } : {}),
      themeOverride: columnId === "__number" ? numberTheme : cellTheme };
  }, [columns, numberTheme, orderedColumns, pairRows, rows, table.table_name, theme.baseFontStyle]);
  const getRowThemeOverride = useCallback((row: number): Partial<Theme> | undefined => { const value = rows[row]; if (!value?.riskLevel) return undefined; const risk = riskTokens(value.riskLevel); return { bgCell: risk.bg, textDark: risk.text }; }, [rows]);
  const drawCell = useCallback((args: Parameters<NonNullable<ComponentProps<typeof DataEditor>["drawCell"]>>[0], drawContent: () => void) => {
    drawContent();
    if (args.col === 0 && args.row === 0) markPainted();
    const row = rows[args.row]; if (!row) return;
    if (args.col === 0 && row.riskLevel) { args.ctx.fillStyle = riskTokens(row.riskLevel).rail; args.ctx.fillRect(args.rect.x, args.rect.y, 4, args.rect.height); }
    if (args.col === 1 && row.pairKey) { const pair = pairRows.get(row.pairKey) ?? []; const at = pair.indexOf(args.row); if (pair.length === 2 && Math.abs((pair[0] ?? 0) - (pair[1] ?? 0)) === 1) { args.ctx.strokeStyle = "#68798A"; args.ctx.lineWidth = 1.5; args.ctx.beginPath(); const x = args.rect.x + 14; const center = args.rect.y + args.rect.height / 2; args.ctx.moveTo(x, at === 0 ? center : args.rect.y); args.ctx.lineTo(x, at === 0 ? args.rect.y + args.rect.height : center); args.ctx.stroke(); } }
    if (row.kind === "deleted" && args.col >= (debug ? 5 : 2)) { args.ctx.strokeStyle = "#535D69"; args.ctx.lineWidth = 1; args.ctx.beginPath(); const y = args.rect.y + args.rect.height / 2; args.ctx.moveTo(args.rect.x + 8, y); args.ctx.lineTo(args.rect.x + args.rect.width - 8, y); args.ctx.stroke(); }
    if (highlightedIdentity && row.rowIdentity === highlightedIdentity) { args.ctx.strokeStyle = "#1F5FBF"; args.ctx.lineWidth = 1; args.ctx.beginPath(); args.ctx.moveTo(args.rect.x, args.rect.y + .5); args.ctx.lineTo(args.rect.x + args.rect.width, args.rect.y + .5); args.ctx.moveTo(args.rect.x, args.rect.y + args.rect.height - .5); args.ctx.lineTo(args.rect.x + args.rect.width, args.rect.y + args.rect.height - .5); if (args.col === 0) { args.ctx.moveTo(args.rect.x + .5, args.rect.y); args.ctx.lineTo(args.rect.x + .5, args.rect.y + args.rect.height); } if (args.col === columns.length - 1) { args.ctx.moveTo(args.rect.x + args.rect.width - .5, args.rect.y); args.ctx.lineTo(args.rect.x + args.rect.width - .5, args.rect.y + args.rect.height); } args.ctx.stroke(); }
  }, [columns.length, debug, highlightedIdentity, markPainted, pairRows, rows]);
  // A single click on an unchanged-run row toggles it; Enter/Space (activation)
  // toggles too, but the activation that follows a double click is ignored.
  const lastToggleClick = useRef(0);
  const click = useCallback(([column, row]: readonly [number, number]) => {
    const target = rows[row];
    if (target?.kind === "collapsed") { lastToggleClick.current = Date.now(); onExpand(target); return; }
    // Formulas are keyed by source_table:point_gid, the same pair the row carries.
    if (table.table_name === "composite_signal_point" && columns[column]?.id === "formula_ast_json") {
      const values = target?.values ?? {};
      onOpenFormula(values.source_table === undefined || values.point_gid === undefined ? null : `${String(values.source_table ?? "")}:${String(values.point_gid ?? "")}`);
    }
  }, [columns, onExpand, onOpenFormula, rows, table.table_name]);
  const activate = useCallback(([, row]: readonly [number, number]) => {
    const target = rows[row];
    if (target?.kind === "collapsed" && Date.now() - lastToggleClick.current > 600) onExpand(target);
  }, [onExpand, rows]);
  const onMouseMove = useCallback((event: Parameters<NonNullable<ComponentProps<typeof DataEditor>["onMouseMove"]>>[0]) => {
    const next = event.kind === "cell" ? event.location : null;
    setHoveredCell((previous) => previous?.[0] === next?.[0] && previous?.[1] === next?.[1] ? previous : next);
    edgeColumn.current = event.kind === "header" && event.isEdge ? event.location[0] : null;
  }, []);
  const onVisibleRegionChanged = useCallback((range: { y: number; height: number }) => {
    const first = rows[Math.max(0, Math.min(rows.length - 1, range.y))];
    const last = rows[Math.max(0, Math.min(rows.length - 1, range.y + range.height - 1))];
    if (!first || !last) return;
    const start = first.rowNumber ?? first.currentPosition ?? 1;
    const end = (last.expanded ? null : last.collapsedRows?.at(-1)?.rowNumber) ?? last.rowNumber ?? last.currentPosition ?? start;
    markPainted();
    onVisibleRows({ start, end });
  }, [markPainted, onVisibleRows, rows]);
  const hoverRow = hoveredCell ? rows[hoveredCell[1]] : undefined;
  const hoverColumn = hoveredCell ? columns[hoveredCell[0]] : undefined;
  const hoverPair = hoverRow?.pairKey ? pairRows.get(hoverRow.pairKey) : undefined;
  const hoverBefore = hoverPair?.length === 2 ? rows[hoverPair.find((index) => rows[index]?.kind === "modified-before") ?? -1] : undefined;
  const hoverAfter = hoverPair?.length === 2 ? rows[hoverPair.find((index) => rows[index]?.kind === "modified-after") ?? -1] : undefined;
  const hoverColumnId = typeof hoverColumn?.id === "string" ? hoverColumn.id : null;
  const hoverChanged = Boolean(hoverRow && hoverColumnId && hoverRow.changedColumns.includes(hoverColumnId));
  const hoverAnnotation = hoverRow?.rowIdentity ? annotations.find((annotation) => riskAnnotationRowIdentities(annotation).includes(hoverRow.rowIdentity as string)) : undefined;
  const missingSnapshotHint = hoverRow?.rowNumberTitle ?? (hoverRow?.kind === "modified-before" && hoverRow.rowNumber === null ? "改前值不在本 bundle 中" : null);
  const showHoverDetail = Boolean(hoverRow && (hoverChanged || hoverRow.riskLevel || missingSnapshotHint));
  const fieldTitle = table.columns?.find((column) => column.name === hoverColumn?.id)?.display_name ?? hoverColumn?.id ?? "";
  const firstColumn = table.columns?.[0];
  const firstCellContent = rows[0] && firstColumn ? normalizeDisplayScalar(rows[0].values[firstColumn.name]) : "空表";
  return <div ref={frameRef} className="grid-frame" aria-label="比较表格" onDoubleClick={fitEdgeColumn} data-tab-key={tabKey} data-rendered={rendered ? "true" : "false"} data-first-cell-content={firstCellContent} data-formula-column-offset={formulaColumnOffset} data-formula-column-width={formulaColumnWidth}><DataEditor ref={gridRef} columns={columns} rows={rows.length} getCellContent={getCellContent} getRowThemeOverride={getRowThemeOverride} drawCell={drawCell} onCellClicked={click} onCellActivated={activate} onColumnResize={resizeColumn} minColumnWidth={COLUMN_MIN} maxColumnWidth={COLUMN_FIT_MAX} onMouseMove={onMouseMove} onVisibleRegionChanged={onVisibleRegionChanged} headerHeight={34} rowHeight={34} theme={theme} width="100%" height={Math.max(240, frameSize.height)} smoothScrollX smoothScrollY verticalBorder={false} freezeColumns={frozenColumnCount} />
    {showHoverDetail && hoverRow && <div className="grid-hover-detail" role="tooltip">
      {missingSnapshotHint && <section><strong>行来源</strong><span>{missingSnapshotHint}</span></section>}
      {hoverChanged && hoverColumnId && hoverBefore && hoverAfter && <section><strong>字段变更</strong><div><span>{fieldTitle}</span><code>{normalizeDisplayScalar(hoverBefore.values[hoverColumnId])}</code><span aria-hidden="true">→</span><code className="grid-hover-detail__new">{normalizeDisplayScalar(hoverAfter.values[hoverColumnId])}</code></div></section>}
      {hoverRow.riskLevel && <section className="grid-hover-detail__risk"><strong>风险信息 <RiskBadge level={hoverRow.riskLevel} /></strong>{hoverAnnotation?.reasons.map((reason) => <span key={reason.reason_code + reason.rule_id} title={debug ? `reason_code=${reason.reason_code} · rule_id=${reason.rule_id}` : undefined}>{describeRiskReason(reason.reason_code)}{debug && <code>{reason.reason_code} · {reason.rule_id}</code>}</span>)}<small>原始规则编码在 Debug 模式中查看</small></section>}
    </div>}
  </div>;
}

function ReplacementBrowser({ before, current, table, assessment, side, onSelectSide }: { before: Record<string, unknown>[]; current: Record<string, unknown>[]; table: SurfaceTable; assessment?: Record<string, unknown>; side: "before" | "current" | null; onSelectSide: (side: "before" | "current") => void }) {
  const summary = table.replacement_summary && typeof table.replacement_summary === "object" ? table.replacement_summary : {};
  const identityStatus = assessment?.status;
  const beforeSide = summary.before && typeof summary.before === "object" ? summary.before as Record<string, unknown> : {};
  const currentSide = summary.current && typeof summary.current === "object" ? summary.current as Record<string, unknown> : {};
  const beforeColumns = Array.isArray(beforeSide.columns) ? beforeSide.columns as NonNullable<SurfaceTable["columns"]> : table.columns ?? [];
  const currentColumns = Array.isArray(currentSide.columns) ? currentSide.columns as NonNullable<SurfaceTable["columns"]> : table.columns ?? [];
  const beforeTitle = typeof beforeSide.display_name === "string" && beforeSide.display_name ? beforeSide.display_name : "替换前";
  const currentTitle = typeof currentSide.display_name === "string" && currentSide.display_name ? currentSide.display_name : "替换后";
  return <section className="replacement-browser"><div className="replacement-summary"><strong>数据集替换 · 双侧浏览</strong><span className="replacement-status">身份结论：{identityStatusText(identityStatus)}</span><div className="identity-pair-summary"><span>匹配条目：{String(assessment?.matched_entry_count ?? "—")}</span><span>替换前：{String(assessment?.before_distinct_entry_count ?? "—")} 个身份条目</span><span>替换后：{String(assessment?.current_distinct_entry_count ?? "—")} 个身份条目</span></div><div className="replacement-side-toggle" role="tablist" aria-label="替换侧"><button role="tab" aria-selected={side === "before"} className={side === "before" ? "is-active" : ""} onClick={() => onSelectSide("before")}>{beforeTitle}</button><button role="tab" aria-selected={side === "current"} className={side === "current" ? "is-active" : ""} onClick={() => onSelectSide("current")}>{currentTitle}</button></div><small>{beforeTitle}：{before.length} 行 · {beforeColumns.length} 列</small><small>{currentTitle}：{current.length} 行 · {currentColumns.length} 列</small></div><div className="replacement-sides"><ReplacementSide title={beforeTitle} rows={before} columns={beforeColumns} active={side === null || side === "before"} /><ReplacementSide title={currentTitle} rows={current} columns={currentColumns} active={side === null || side === "current"} /></div></section>;
}

function ReplacementSide({ title, rows, columns, active }: { title: string; rows: Record<string, unknown>[]; columns: NonNullable<SurfaceTable["columns"]>; active: boolean }) {
  const theme = useMemo(() => createTableTheme(), []);
  const gridColumns = useMemo<GridColumn[]>(() => {
    const measureCell = createTextMeasure(`${theme.baseFontStyle} ${theme.fontFamily}`);
    const measureHeader = createTextMeasure(`${theme.headerFontStyle} ${theme.fontFamily}`);
    const sample = sampleRows(rows, 600);
    return columns.map((column) => {
      const title = column.display_name || column.name;
      return { id: column.name, title, width: fitWidth(measureHeader(title), sample.map((row) => measureCell(normalizeDisplayScalar(row[column.name]))), "auto") };
    });
  }, [columns, rows, theme]);
  const getCellContent = useCallback(([column, row]: readonly [number, number]): GridCell => {
    const key = gridColumns[column]?.id; const item = rows[row]; if (!key || !item) return { kind: GridCellKind.Loading, allowOverlay: false };
    const value = normalizeDisplayScalar(item[key]); return { kind: GridCellKind.Text, data: value, displayData: value, allowOverlay: false };
  }, [gridColumns, rows]);
  return <section className={active ? "replacement-side" : "replacement-side is-inactive"}><h3>{title} <small>{rows.length} 行</small></h3><div className="grid-frame"><DataEditor columns={gridColumns} rows={rows.length} getCellContent={getCellContent} rowMarkers={{ kind: "number", width: 44 }} headerHeight={34} rowHeight={34} theme={theme} width="100%" height={420} verticalBorder={false} /></div></section>;
}

function FormulaCard({ formula, preview }: { formula: ReturnType<typeof deriveFormulaDisplays>[number]; preview: boolean }) {
  const title = formula.deleted && preview ? "删除记录中的基线公式" : preview ? "上传侧公式" : "改后公式";
  const currentDevices = formula.deleted && preview ? formula.beforeDevices : formula.currentDevices;
  const singleFormula = formula.currentFormula;
  const lines = renderFormulaLines(singleFormula, currentDevices);
  const beforeLines = renderFormulaLines(formula.beforeFormula, formula.beforeDevices);
  const currentLines = renderFormulaLines(formula.currentFormula, formula.currentDevices);
  const aligned = alignFormulaLines(beforeLines, currentLines);
  return <section className="formula-card"><div className="formula-card__heading"><strong>{formula.currentDeviceName ?? formula.beforeDeviceName ?? "未知装置"} · {formula.pointLabel}</strong>{(formula.label || (formula.changed && !preview)) && <span className="formula-changed">公式已改</span>}</div>
    {preview && !formula.beforeFormula ? <section className="formula-side formula-side--single"><strong>{title}</strong><FormulaLineList lines={lines} /></section>
      : <div className="formula-pair"><strong className="formula-pair__heading">改前公式</strong><strong className="formula-pair__heading">改后公式</strong>{aligned.length ? aligned.map((line, index) => <FormulaAlignedPair key={line.before?.key ?? line.current?.key ?? index} line={line} />) : <div className="formula-empty formula-empty--span">暂无公式</div>}</div>}
  </section>;
}

function FormulaAlignedPair({ line }: { line: ReturnType<typeof alignFormulaLines>[number] }) {
  const state = line.state === "same" ? "" : ` formula-line--${line.state}`;
  const beforeKind = line.before?.kind === "group" ? " formula-line--group" : "";
  const currentKind = line.current?.kind === "group" ? " formula-line--group" : "";
  return <><div className={`formula-line${beforeKind}${state}`} style={{ paddingLeft: 7 + (line.before?.depth ?? 0) * 14 }}>{line.before?.text ?? " "}</div><div className={`formula-line${currentKind}${state}`} style={{ paddingLeft: 7 + (line.current?.depth ?? 0) * 14 }}>{line.current?.text ?? " "}</div></>;
}

function FormulaLineList({ lines }: { lines: ReturnType<typeof renderFormulaLines> }) {
  if (!lines.length) return <div className="formula-empty">暂无公式</div>;
  return <div className="formula-lines">{lines.map((line) => <div key={line.key} className={line.kind === "group" ? "formula-line formula-line--group" : "formula-line"} style={{ paddingLeft: 7 + line.depth * 14 }}>{line.text}</div>)}</div>;
}

function formatSchemaSummary(value: Record<string, unknown> | null | undefined): string {
  if (!value) return "表结构发生变化，请检查新增或删除的列。";
  const addedValues = value.current_only_columns ?? value.added_columns;
  const removedValues = value.before_only_columns ?? value.removed_columns;
  const added = Array.isArray(addedValues) ? addedValues.map(String) : [];
  const removed = Array.isArray(removedValues) ? removedValues.map(String) : [];
  const details = [added.length ? "新增列：" + added.join("、") : "", removed.length ? "删除列：" + removed.join("、") : ""].filter(Boolean);
  return details.length ? "表结构发生变化。" + details.join("；") : "表结构发生变化，请检查新增或删除的列。";
}
