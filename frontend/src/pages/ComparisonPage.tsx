import { DataEditor, GridCellKind, type DataEditorRef, type GridCell, type GridColumn, type Theme } from "@glideapps/glide-data-grid";
import "@glideapps/glide-data-grid/dist/index.css";
import { AlertTriangle, ArrowDown, ArrowUp, ChevronDown, ChevronLeft, ChevronRight, Code2, Copy, MoreHorizontal, Rows2, Rows4, Search, Table2, X } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ComponentProps, type CSSProperties, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";
import type { components } from "../features/api/generated/openapi";
import { useBoundGatewayApi, boundBundleFetch } from "../features/api/application-api";
import { assertSubmissionReviewBundle, pollHistoryCompare } from "../features/api/journeys";
import { bundleLoadErrorCode, ensureLocalBundle, OpfsBundleStore, type InstalledBundle } from "../features/bundle/local-bundle";
import { loadComparisonPresentation, readLocalChangeRecords, readLocalRiskAnnotations, readLocalTable, type LocalComparisonPresentation } from "../features/bundle/presentation";
import { deriveFormulaDisplays, navigationTabHasDifferences, normalizeRowIdentity, tabScope, type DerivedNavigationGroup, type DeviceDefinitionChange, type NavigationPredicate, type NavigationTableNotice, type RiskAnnotation, type RiskLevel, type RowDiffRecord, type SurfaceTable, type TabScope } from "../features/view-model/model";
import { alignFormulaLines, renderFormulaLines } from "../features/view-model/formula-view";
import { readParquetMetadata, readParquetTable } from "../features/bundle/parquet-reader";
import { decodeSnapshotEncodings, type SnapshotColumnEncoding } from "../features/view-model/snapshot-encoding";
import { blankIntervalLabel, buildBrowseRows, canReuseUnrecordedIdentity, columnHeaderTitle, deriveChangeLocations, missingSideMarker, normalizeDisplayScalar, parseRowLocator, rowMove, rowRiskAnnotation, validateRowLocations, type BrowseRow, type ChangeLocation, type DeletionLayout } from "../features/view-model/table-rows";
import { formatNavigationDiagnostic, formatSurfaceDiagnostic, groupNavigationDiagnostics, pairSurfaceDiagnosticCodes, type NavigationDiagnostic } from "../features/view-model/diagnostics";
import { describeRiskReason, isKnownRiskReason } from "../features/view-model/risk-copy";
import { itemChangeMark, scopeChangeMark, scopeChangeText as describeScopeChange, type ScopeChangeMark } from "../features/view-model/scope-copy";
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

function serverResultReleaseCode(cause: unknown): string | undefined {
  return cause instanceof ApiError && cause.status === 503
    && (cause.code === "SUBMISSION_RESULT_UNAVAILABLE" || cause.code === "SUBMISSION_RESULT_INTEGRITY_FAILURE")
    ? cause.code : undefined;
}

type PairSummary = { pair_id: string; summary?: Record<string, string> };
type PairPresentation = { pair: PairSummary; presentation: LocalComparisonPresentation };
type SizedGridColumn = GridColumn & { width: number };
type Settings = { sidebarWidth: number; sidebarCollapsed: boolean; collapsedGroups: string[]; deletionLayout: DeletionLayout };
const SETTINGS_KEY = "gateway-comparison-sidebar-v2";
const SIDEBAR_MIN = 180;
const SIDEBAR_MAX = 520;
const DEFAULT_SETTINGS: Settings = { sidebarWidth: 220, sidebarCollapsed: false, collapsedGroups: [], deletionLayout: "interleave" };
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
      collapsedGroups: Array.isArray(value?.collapsedGroups) ? value.collapsedGroups.filter((item): item is string => typeof item === "string") : [],
      deletionLayout: value?.deletionLayout === "group" ? "group" : "interleave" };
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
  if (mode === "REVIEW" && total === 1) return "基线 → 修改";
  if (mode === "HISTORY") return "节点 " + (index + 1) + " → 节点 " + (index + 2);
  if (total === 1) return "当前基线 → 本次归档组态";
  const id = pair.pair.pair_id.toLowerCase();
  if (id.includes("baseline_to_initial")) return "原始组态视图";
  if (id.includes("initial_to_modified")) return "本次组态视图";
  return "比较视图 " + (index + 1);
}

function viewTitle(pair: PairPresentation, index: number, total: number, mode: BrowseState["mode"]): string {
  if (mode === "REVIEW" && total === 1) return "提交绑定比较：基线 → 修改";
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

/** Reason codes in a public notice mix risk reasons and surface diagnostics; both have user copy. */
function noticeReasonText(code: string): string {
  return isKnownRiskReason(code) ? describeRiskReason(code) : formatSurfaceDiagnostic(code).message;
}

/** One line per public fact of a shared table; never phrased as a device's own result. */
function noticeLines(notice: NavigationTableNotice): string[] {
  const lines: string[] = [];
  if (notice.table_scope) {
    if (notice.initial_table_change) {
      if (notice.table_scope.risk_level) lines.push("整表风险：" + riskLevelText(notice.table_scope.risk_level));
    } else {
      lines.push((notice.table_scope.change ? "整表发生表级变化" : "整表无表级变化") + (notice.table_scope.risk_level ? " · 整表风险：" + riskLevelText(notice.table_scope.risk_level) : ""));
    }
  }
  const unlocated = notice.unlocated_row_risk;
  if (unlocated && (unlocated.risk_level !== null || unlocated.count !== null)) {
    lines.push("待定位风险" + (unlocated.risk_level ? "：" + riskLevelText(unlocated.risk_level) : "") + (unlocated.count !== null ? " · " + unlocated.count + " 项" : "") + "（不能归属到具体装置）");
  }
  if (!notice.risk_complete) lines.push("风险信息不完整：未生成标注不代表没有风险");
  return lines;
}

function definitionChangeText(change: DeviceDefinitionChange): string {
  const verb = change.change_kind === "ADDED" ? "新增" : change.change_kind === "DELETED" ? "删除" : "修改";
  const address = change.before_dev_addr !== null && change.current_dev_addr !== null && change.before_dev_addr !== change.current_dev_addr
    ? `地址 ${change.before_dev_addr} → ${change.current_dev_addr}`
    : `地址 ${change.current_dev_addr ?? change.before_dev_addr ?? "未知"}`;
  return `${verb}装置定义 · ${address}`;
}

/** Local risk status text for a filtered tab: confirmed, none generated, or incomplete. */
function localRiskText(scope: TabScope): string | null {
  if (scope.kind === "WHOLE_TABLE") return null;
  if (!scope.riskComplete) return scope.riskLevel ? "已确认风险之外，风险信息不完整" : "风险信息不完整";
  return scope.riskLevel ? null : "未生成风险标注";
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

const scopeChangeText = (scope: TabScope) => describeScopeChange(scope, (kind) => surfaceChangePresentation(kind).text);

function tabTitle(scope: TabScope): string {
  const change = scope.changeKind === null ? null : surfaceChangePresentation(scope.changeKind);
  return [scopeChangeText(scope), scope.kind === "WHOLE_TABLE" ? change?.tooltip : null, scope.riskLevel ? riskLevelText(scope.riskLevel) : null,
    !scope.membershipComplete && !scope.membershipInitialBaseline ? "归属变化未知" : null,
    localRiskText(scope), scope.notice ? "该表另有公共提示" : null, `${scope.beforeCount ?? "—"} → ${scope.currentCount ?? "—"} 行`]
    .filter((item): item is string => Boolean(item)).join(" · ");
}

/** Change badge or neutral marker of a scope; migration and registry-only changes never show add/delete. */
function ChangeMark({ mark }: { mark: ScopeChangeMark }) {
  if (mark.kind === "unknown") return <span className="scope-marker scope-marker--unknown" title="本页签的逐行变化无法确定">变化未知</span>;
  if (mark.kind === "marker") return <span className="scope-marker" title={mark.title}>{mark.text}</span>;
  return <SurfaceChangeBadge kind={mark.changeKind} />;
}

function ScopeChangeBadge({ scope }: { scope: TabScope }) {
  return <ChangeMark mark={scopeChangeMark(scope)} />;
}

function riskTokens(level: RiskLevel): { bg: string; rail: string; text: string; cell: string } {
  const style = getComputedStyle(document.documentElement);
  const name = "risk-" + level.toLowerCase().replace("_", "-");
  return { bg: style.getPropertyValue("--" + name + "-bg").trim(), rail: style.getPropertyValue("--" + name + "-rail").trim(),
    text: style.getPropertyValue("--" + name + "-text").trim(), cell: style.getPropertyValue("--" + name + "-cell").trim() };
}

/** Changed fields listed in the hover detail before the rest are summarised. */
const HOVER_FIELD_LIMIT = 8;

/** Rows an ordered table moved; row_change_stats does not count moves. */
function orderedMovedCount(table: SurfaceTable): number {
  const summary = table.ordered_extension?.ordered_summary;
  const moved = summary && typeof summary === "object" ? (summary as Record<string, unknown>).row_moved_count : null;
  return typeof moved === "number" && moved > 0 ? moved : 0;
}

function rowLabel(row: BrowseRow): string {
  if (row.kind === "collapsed") return row.expanded ? "▴ 收起 " + (row.collapsedCount ?? 0) + " 行未变更" : "▾ " + (row.collapsedCount ?? 0) + " 行未变更 · 展开";
  if (row.kind === "blank-interval" && row.interval) return blankIntervalLabel(row.interval);
  if (row.kind === "added") return "+ 新增";
  if (row.kind === "deleted") return "− 删除";
  if (row.recordKind === "ORDERED_ROW_MOVED" || row.kind === "ordered") return "↕ 移动 · " + (row.beforePosition ?? "—") + " → " + (row.currentPosition ?? "—");
  // Leading space keeps room for the line drawn between a modified pair.
  if (row.kind === "modified-before" || row.kind === "modified-after") { const move = rowMove(row); return "\u2002\u2002修改" + (move ? " · ↕ " + move.from + " → " + move.to : ""); }
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
  const [reviewResultChecking, setReviewResultChecking] = useState(false);
  const [reviewResultErrorCode, setReviewResultErrorCode] = useState<string>();
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
  const [scopedRows, setScopedRows] = useState<BrowseRow[]>([]);
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

  // Facts remain authoritative even when the separately authorized result is unreadable.
  // Only failures from server summary/download requests can enable reject/withdraw;
  // local bundle identity and download failures never supply this permission.
  const readReviewContext = useCallback(async (submissionId: string) => {
    const [review, result] = await Promise.allSettled([
      gatewayApi.getReviewFacts(submissionId).then((facts) => {
        gatewayApi.assertSession?.();
        if (runtime.snapshot.state.submissionId === submissionId) setReviewFacts(facts);
        return facts;
      }, (cause: unknown) => {
        if (runtime.snapshot.state.submissionId === submissionId) setReviewFacts(null);
        throw cause;
      }),
      gatewayApi.getSubmissionResult(submissionId),
    ]);
    gatewayApi.assertSession?.();
    if (review.status === "rejected") throw review.reason;
    if (result.status === "rejected") {
      const cause: unknown = result.reason;
      if (runtime.snapshot.state.submissionId === submissionId) setReviewResultErrorCode(serverResultReleaseCode(cause));
      throw cause;
    }
    return result.value;
  }, [gatewayApi, runtime]);

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
    setError(null); setReviewResultErrorCode(undefined); setHistoryCompareStatus(null);
    if (current.mode === "REVIEW") setReviewResultChecking(true);
    if (loadedRequest.current?.requestPath !== requestPath) { setBundle(null); setPairs([]); }
    setLoading({ phase: "下载并校验比较结果", received: 0, total: 0 });
    try {
      let expectedBundleDigest: string | undefined;
      let submissionResult: components["schemas"]["SubmissionResultResponse"] | undefined;
      if (current.mode === "PREVIEW" && current.workspaceId && current.previewResultId) {
        expectedBundleDigest = (await gatewayApi.getPreviewResult(current.workspaceId, current.previewResultId)).bundle_digest;
      }
      if (current.mode === "REVIEW" && current.submissionId) {
        const result = await readReviewContext(current.submissionId);
        gatewayApi.assertSession?.();
        if (result.submission_id !== current.submissionId) throw new ApiError("提交结果身份不一致", 503, "SUBMISSION_RESULT_INTEGRITY_FAILURE");
        submissionResult = result;
        expectedBundleDigest = result.bundle_digest;
        if (loadedRequest.current?.requestPath === requestPath
          && loadedRequest.current.bundleDigest === expectedBundleDigest) {
          assertSubmissionReviewBundle(current.submissionId, result, loadedRequest.current.bundle);
          setBundle(loadedRequest.current.bundle);
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
        fetchBundle: async () => {
          try { return await fetchBundle(requestPath, { headers: { Accept: "application/x-tar" } }); }
          catch (cause) {
            if (current.mode === "REVIEW" && runtime.snapshot.state.submissionId === current.submissionId) {
              setReviewResultErrorCode(serverResultReleaseCode(cause));
            }
            throw cause;
          }
        },
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
      if (initialBundleLoad && currentState.unassignedSide && runtime.snapshot.state.unassignedSide !== currentState.unassignedSide) runtime.execute({ name: "set-unassigned", side: currentState.unassignedSide }, "external");
    } catch (cause) {
      const details = cause instanceof Error ? cause.message : String(cause);
      loadedRequest.current = null;
      setBundle(null); setPairs([]);
      setError(bundleErrorState(cause, details));
    } finally {
      if (loadingKey.current === requestKey) {
        loadingKey.current = null;
        if (current.mode === "REVIEW") setReviewResultChecking(false);
      }
    }
  }, [browse.bundleDigest, browse.mode, browse.operationId, browse.previewResultId, browse.submissionId, browse.workspaceId, runtime, sessionState.kind, readReviewContext]);
  useEffect(() => { void loadBundle(); }, [loadBundle]);

  // Result authority is invalid while any review-context refresh is pending.
  const reloadReviewContext = useCallback(async (): Promise<boolean> => {
    const current = runtime.snapshot.state;
    if (current.mode !== "REVIEW" || !current.submissionId) return false;
    const cached = loadedRequest.current;
    setBundle(null);
    setError(null);
    setReviewResultErrorCode(undefined);
    setLoading({ phase: "重新读取提交绑定的比较结果", received: 0, total: 0 });
    try {
      const result = await readReviewContext(current.submissionId);
      gatewayApi.assertSession?.();
      if (runtime.snapshot.state.submissionId !== current.submissionId) return false;
      if (!cached || cached.requestPath !== bundlePathForState(current)) {
        throw new Error("提交绑定的比较结果尚未就绪，请重试下载");
      }
      assertSubmissionReviewBundle(current.submissionId, result, cached.bundle);
      setBundle(cached.bundle);
      return true;
    } catch (cause) {
      if (runtime.snapshot.state.submissionId !== current.submissionId) return false;
      loadedRequest.current = null;
      setBundle(null); setPairs([]);
      setError(bundleErrorState(cause, cause instanceof Error ? cause.message : String(cause)));
      return false;
    }
  }, [runtime, readReviewContext]);

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
  const shownItems = useCallback((group: DerivedNavigationGroup): NavItem[] => {
    const groupMatches = group.label.toLocaleLowerCase().includes(browse.search.trim().toLocaleLowerCase());
    return group.items.filter((item) => (groupMatches || matchesItem(item, browse.search)) && shownTabs(item).length > 0);
  }, [browse.search, shownTabs]);
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
      const next = visibleGroups.flatMap((group) => shownItems(group).flatMap((item) =>
        shownTabs(item).map((tab) => ({ item, tab })))).find(({ tab }) => !tab.empty)
        ?? navigationEntries.find(({ tab }) => !tab.empty);
      if (next) {
        runtime.execute({ name: "select-node", nodeKey: next.item.itemKey });
        runtime.execute({ name: "select-tab", tabKey: next.tab.tabKey });
      }
    }
    setShowEmptyTabs((value) => !value);
  };
  const selectedTab = useMemo(() => wholeTable && wholeTableName
    ? { tabKey: "__whole__:" + wholeTableName, label: wholeTable.label, tableName: wholeTableName, empty: false, rowFilter: null, facts: null, table: wholeTable,
      notice: presentation?.view.tableNotices.find((notice) => notice.table_id === wholeTableName) ?? null }
    : selectedEntry?.tab ?? null, [presentation, selectedEntry, wholeTable, wholeTableName]);
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
  /**
   * Predicates of every device filter on one side of a table, for orphan
   * browsing. Null when the side cannot be judged: replacement, no published
   * predicate, unsupported identity, or a missing current snapshot.
   */
  const unassignedPredicates = useCallback((tableName: string, side: "BEFORE" | "CURRENT"): NavigationPredicate[] | null => {
    if (!presentation || presentation.view.replacementSides) return null;
    const diagnostics = presentation.navigationDiagnostics.filter((diagnostic) => diagnostic.target.table_id === tableName && diagnostic.side === side);
    if (!diagnostics.some((diagnostic) => diagnostic.code === "DEVICE_ROWS_UNASSIGNED")) return null;
    if (diagnostics.some((diagnostic) => diagnostic.code === "DEVICE_FILTER_VALUE_UNSUPPORTED")) return null;
    if (side === "CURRENT" && !presentation.tableArtifacts.get(tableName)?.current) return null;
    const predicates = filterTabsForTable(tableName).flatMap((tab) => {
      const predicate = side === "BEFORE" ? tab.rowFilter?.before : tab.rowFilter?.current;
      return predicate ? [predicate] : [];
    });
    return predicates.length > 0 ? predicates : null;
  }, [filterTabsForTable, presentation]);
  const canBrowseUnassigned = useCallback((diagnostic: NavigationDiagnostic) => diagnostic.code === "DEVICE_ROWS_UNASSIGNED"
    && typeof diagnostic.target.table_id === "string" && diagnostic.side !== null
    && unassignedPredicates(diagnostic.target.table_id, diagnostic.side) !== null, [unassignedPredicates]);
  const browseUnassigned = (tableName: string, side: "BEFORE" | "CURRENT") => {
    openWholeTable(tableName);
    runtime.execute({ name: "set-unassigned", side });
  };
  const activeUnassigned = useMemo(() => wholeTableName && browse.unassignedSide ? unassignedPredicates(wholeTableName, browse.unassignedSide) : null,
    [browse.unassignedSide, unassignedPredicates, wholeTableName]);
  // An orphan state restored from the URL that this table cannot honour falls back to the plain whole table.
  useEffect(() => {
    if (presentation && browse.unassignedSide && !activeUnassigned) runtime.execute({ name: "set-unassigned", side: null }, "external");
  }, [activeUnassigned, browse.unassignedSide, presentation, runtime]);
  const loadTable = useCallback(async () => {
    if (!bundle || !presentation || !selectedTab || !surfaceTable) { setRows([]); setScopedRows([]); return; }
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
        setBeforeRows(before as Record<string, unknown>[]); setCurrentRows(current as Record<string, unknown>[]); setRows([]); setScopedRows([]); setAnnotations([]); return;
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
      const unassigned = activeUnassigned && browse.unassignedSide
        ? { side: browse.unassignedSide === "BEFORE" ? "before" as const : "current" as const, predicates: activeUnassigned } : null;
      const needsEncodings = (selectedTab.rowFilter !== null || unassigned !== null) && !degraded;
      const [beforeMeta, currentMeta] = needsEncodings
        ? await Promise.all([
          paths?.before ? readParquetMetadata(bundle, paths.before) : Promise.resolve(null),
          paths?.current ? readParquetMetadata(bundle, paths.current) : Promise.resolve(null),
        ])
        : [null, null];
      const tableLabel = `表 ${surfaceTable.table_name}`;
      const beforeEncodings: Map<string, SnapshotColumnEncoding> = beforeMeta ? decodeSnapshotEncodings(beforeMeta.key_value_metadata, `${tableLabel}.改前`) : new Map();
      const currentEncodings: Map<string, SnapshotColumnEncoding> = currentMeta ? decodeSnapshotEncodings(currentMeta.key_value_metadata, `${tableLabel}.改后`) : new Map();
      setBeforeRows(beforeSnapshotRows); setCurrentRows(currentSnapshotRows); setAnnotations(risks);
      const built = buildBrowseRows({ table: surfaceTable, beforeRows: beforeSnapshotRows, currentRows: currentSnapshotRows, records: tableRecords, annotations: risks, locator,
        hasBeforeSnapshot: Boolean(paths?.before), hasCurrentSnapshot: Boolean(paths?.current),
        rowFilter: selectedTab.rowFilter, beforeEncodings, currentEncodings, degraded,
        reuseUnrecordedBefore: canReuseUnrecordedIdentity(surfaceTable, filterTabs, Boolean(paths?.before), Boolean(paths?.current)),
        unassigned, onlyInteresting: browse.onlyInteresting, search: browse.search, expandedRuns, deletionLayout: settings.deletionLayout });
      setRows(built.rows); setScopedRows(built.scoped);
    } catch (cause) {
      setError({ code: "TABLE_READ_FAILED", details: cause instanceof Error ? cause.message : String(cause) });
    } finally { setTableLoading(false); }
  }, [activeUnassigned, browse.onlyInteresting, browse.search, browse.unassignedSide, bundle, expandedRuns, filterTabsForTable, presentation, replacement, selectedTab, settings.deletionLayout, surfaceTable]);
  useEffect(() => { void loadTable(); }, [loadTable]);

  // Locations, risk counts and reasons all follow the current scope: the device
  // filter or orphan view, never the whole table's records behind it.
  const locations = useMemo(() => deriveChangeLocations(scopedRows), [scopedRows]);
  const rowRiskCounts = useMemo(() => {
    const risks = new Map<string, RiskLevel>();
    for (const row of scopedRows) if (row.riskLevel) risks.set(row.pairKey ?? row.rowIdentity ?? row.key, row.riskLevel);
    return [...risks.values()].reduce((levels, level) => {
      const match = levels.find((item) => item.level === level);
      if (match) match.count += 1;
      else levels.push({ level, count: 1 });
      return levels;
    }, [] as Array<{ level: RiskLevel; count: number }>);
  }, [scopedRows]);
  const currentIndex = Math.min(browse.changeIndex, Math.max(0, locations.length - 1));
  const selectedScopeKind = selectedTab ? tabScope(selectedTab).kind : "WHOLE_TABLE";
  const riskReasonDetails = useMemo(() => {
    const result = new Map<string, { reasonCode: string; ruleId: string | null; copy: string }>();
    for (const row of scopedRows) {
      if (!row.riskLevel) continue;
      const annotation = rowRiskAnnotation(row, annotations);
      for (const reason of annotation?.reasons ?? []) {
        result.set(reason.reason_code + "|" + reason.rule_id, { reasonCode: reason.reason_code, ruleId: reason.rule_id, copy: describeRiskReason(reason.reason_code, reason.evidence) });
      }
    }
    // Table-level reasons belong to the whole-table view; a device tab lists them under the public notice.
    if (selectedScopeKind === "WHOLE_TABLE" && !browse.unassignedSide) {
      for (const code of surfaceTable?.risk_refs?.reason_codes ?? []) {
        if (![...result.values()].some((detail) => detail.reasonCode === code)) result.set(code, { reasonCode: code, ruleId: null, copy: describeRiskReason(code) });
      }
    }
    return [...result.values()];
  }, [annotations, browse.unassignedSide, scopedRows, selectedScopeKind, surfaceTable]);
  const unassignedView = useMemo(() => {
    if (!activeUnassigned || !browse.unassignedSide || !wholeTableName || !presentation) return null;
    const diagnostic = presentation.navigationDiagnostics.find((item) => item.code === "DEVICE_ROWS_UNASSIGNED" && item.target.table_id === wholeTableName && item.side === browse.unassignedSide);
    const side = browse.unassignedSide === "BEFORE" ? "before" : "current";
    return {
      side: browse.unassignedSide,
      rowCount: typeof diagnostic?.params.row_count === "number" ? diagnostic.params.row_count : null,
      changedRowCount: typeof diagnostic?.params.changed_row_count === "number" ? diagnostic.params.changed_row_count : null,
      browsableCount: new Set(scopedRows.filter((row) => row.side === side).map((row) => row.key)).size,
      partial: browse.unassignedSide === "BEFORE" && !presentation.tableArtifacts.get(wholeTableName)?.before,
    };
  }, [activeUnassigned, browse.unassignedSide, presentation, scopedRows, wholeTableName]);
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
    // "查看整表" means the whole table, even when the same table is open as an orphan subset.
    if (runtime.snapshot.state.unassignedSide) runtime.execute({ name: "set-unassigned", side: null });
  };
  const itemLabels = useMemo(() => new Map(groups.flatMap((group) => group.items.map((item) => [item.itemKey, item.label] as const))), [groups]);
  // A definition change may point at an item whose tabs are all empty; it still opens.
  const openItem = (itemKey: string) => {
    const item = groups.flatMap((group) => group.items).find((candidate) => candidate.itemKey === itemKey);
    const tab = item ? shownTabs(item)[0] ?? item.tabs[0] : undefined;
    if (item && tab) chooseTab(tab.tableName, tab.tabKey, item.itemKey);
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
        {browse.mode === "REVIEW" && browse.readOnly
          ? <span className="mode-tag" title="提交时冻结的预览比较结果，不是父节点到此提交的净变化；净变化请在工作台用历史比较。">提交时差异 · 只读</span>
          : <span className="mode-tag">{browse.mode === "PREVIEW" ? "上传" : browse.mode === "REVIEW" ? "审核" : "历史比较 · 只读"}</span>}
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
          {browse.mode === "REVIEW" && !browse.readOnly && reviewFacts && browse.submissionId && <ReviewActions submissionId={browse.submissionId} facts={reviewFacts} bundleReady={Boolean(bundle) && !reviewResultChecking} resultErrorCode={reviewResultErrorCode} onFactsChanged={setReviewFacts} onReviewSettled={reloadReviewContext} errorNoticeHost={reviewNoticeRef} />}
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
    {activePair?.presentation.navigation.initial_baseline && <div className="pair-diagnostic-strip" role="status">首次建立基线</div>}
    {activePair && pairDiagnosticDetails(activePair).codes.length > 0 && <div className="pair-diagnostic-strip" role="status">{pairDiagnosticDetails(activePair).codes.map((diagnostic) => { const formatted = formatSurfaceDiagnostic(diagnostic); return <div key={diagnostic}><AlertTriangle size={14} /><span>{formatted.message}</span>{debugMode && <code>{formatted.raw}</code>}</div>; })}</div>}
    {!bundle && !error && <section className="compare-loading"><LoadingSkeleton label={loading.phase} /><div className="loading-progress"><span>{loading.phase}</span><span>{loading.total ? formatBytes(loading.received) + " / " + formatBytes(loading.total) : "正在准备"}</span></div></section>}
    {error && <section className="compare-error"><ErrorState code={error.code} details={error.details} title={error.code === "SCOPE_FORBIDDEN" ? "当前身份没有该操作的权限" : bundleErrorTitle(error.code)} onRetry={() => void loadBundle()} /></section>}
    {bundle && presentation && <div ref={workspaceRef} className={"compare-workspace" + (collapsed ? " sidebar-is-collapsed" : "")} style={{ "--sidebar-width": settings.sidebarWidth + "px" } as CSSProperties}>
      <aside className="navigation-sidebar" aria-label="比较导航"><div className="sidebar-heading"><div className="sidebar-search"><Search size={14} /><input ref={searchInputRef} aria-label="搜索组、节点或页签" value={search} onChange={(event) => runtime.execute({ name: "set-search", search: event.currentTarget.value })} placeholder={`搜索 · ${presentation.view.tables.length} 张表`} /></div><button className="icon-button" aria-label="收起导航" title="收起导航" onClick={() => setSettings((state) => ({ ...state, sidebarCollapsed: true }))}><ChevronLeft size={16} /></button></div>
        {globalNavigationDiagnostics.map((diagnostic, index) => <NavigationDiagnosticNote key={diagnostic.code + index} diagnostic={diagnostic} tables={presentation.surface.tables} debug={debugMode} onOpenWholeTable={openWholeTable} onBrowseUnassigned={browseUnassigned} canBrowseUnassigned={canBrowseUnassigned} />)}
        <div className="sidebar-scroll"><PublicNoticesPanel notices={presentation.view.tableNotices} changes={presentation.view.deviceDefinitionChanges} tables={presentation.surface.tables} items={itemLabels} debug={debugMode} onOpenWholeTable={openWholeTable} onOpenItem={openItem} />{visibleGroups.map((group) => {
          const items = shownItems(group);
          const groupDiagnostics = presentation.navigationDiagnostics.filter((diagnostic) => diagnostic.target.group_key === group.groupKey);
          if (items.length === 0 && groupDiagnostics.length === 0) return null;
          return <section className="nav-group" key={group.groupKey}><button className="nav-group__heading" aria-expanded={!settings.collapsedGroups.includes(group.groupKey)} onClick={() => { runtime.execute({ name: "toggle-group", groupKey: group.groupKey }); setSettings((state) => ({ ...state, collapsedGroups: state.collapsedGroups.includes(group.groupKey) ? state.collapsedGroups.filter((key) => key !== group.groupKey) : [...state.collapsedGroups, group.groupKey] })); }}><ChevronDown className={settings.collapsedGroups.includes(group.groupKey) ? "is-closed" : ""} size={14} /><span className="nav-group__label">{group.label}</span><small title="非空项">{items.filter((item) => item.nonemptyTabCount > 0).length}</small>{groupDiagnostics.length > 0 && <small className="nav-group__diagnostic-count">{groupDiagnostics.length} 条提示</small>}</button>
          {groupNavigationDiagnostics(presentation.navigationDiagnostics, group.groupKey, items.map((item) => item.itemKey)).map((diagnostic, index) => <NavigationDiagnosticNote key={diagnostic.code + index} diagnostic={diagnostic} tables={presentation.surface.tables} debug={debugMode} onOpenWholeTable={openWholeTable} onBrowseUnassigned={browseUnassigned} canBrowseUnassigned={canBrowseUnassigned} />)}
          {!settings.collapsedGroups.includes(group.groupKey) && items.map((item) => { const itemTabs = shownTabs(item); const active = item.itemKey === selectedNodeKey; const { changeKinds, riskLevels } = item; const itemState = changeKinds.map((kind) => surfaceChangePresentation(kind).text).join("、") || "未变化"; const itemKind = itemBadgeKind(changeKinds); const itemMark = itemChangeMark(item, item.tabs.filter((tab) => !tab.empty).map(tabScope)); const itemTitle = `${item.label} · ${itemMark?.kind === "marker" ? itemMark.title : itemState}${itemStatusTooltip(changeKinds) ? " · " + itemStatusTooltip(changeKinds) : ""}${riskLevels[0] ? " · " + riskLevelText(riskLevels[0]) : ""}`; return <div className={active ? "nav-item is-active" : "nav-item"} key={item.itemKey} data-item-key={item.itemKey} ref={active ? selectedNavRef : undefined}><button className="nav-item__button" onClick={() => { const tab = itemTabs[0]; if (tab) chooseTab(tab.tableName, tab.tabKey, item.itemKey); }} title={itemTitle}><span className={"nav-icon nav-icon--" + item.itemKind.toLowerCase()}><Table2 size={15} /></span><span className={!itemMark && changeKinds.some((kind) => surfaceChangePresentation(kind).deleted) ? "nav-item__label is-deleted" : "nav-item__label"}>{item.label}</span>{riskLevels[0] ? <RiskBadge level={riskLevels[0]} /> : itemMark ? <ChangeMark mark={itemMark} /> : <SurfaceChangeBadge kind={itemKind} />}{!item.changeComplete && <span className="scope-marker scope-marker--unknown" title="部分页签的变化或归属无法完整确定">变化?</span>}{!item.riskComplete && <span className="scope-marker scope-marker--incomplete" title="风险信息不完整，未标注不代表没有风险">风险?</span>}{item.tabs.some((tab) => tab.notice !== null && tab.rowFilter !== null) && <span className="scope-marker scope-marker--public" title="相关表有整表或待定位提示，不是本装置自己的风险">表提示</span>}</button>
            {presentation.navigationDiagnostics.filter((diagnostic) => diagnostic.target.item_key === item.itemKey && !diagnostic.target.tab_key).map((diagnostic, index) => <NavigationDiagnosticNote key={diagnostic.code + index} diagnostic={diagnostic} tables={presentation.surface.tables} debug={debugMode} onOpenWholeTable={openWholeTable} onBrowseUnassigned={browseUnassigned} canBrowseUnassigned={canBrowseUnassigned} />)}
          </div>; })}</section>; })}</div>
      </aside>
      {!collapsed && <div className="sidebar-resize" role="separator" aria-label="调整侧栏宽度（双击适应名称）" title="拖动调整宽度，双击适应名称" onDoubleClick={fitSidebarWidth} aria-orientation="vertical" aria-valuemin={SIDEBAR_MIN} aria-valuemax={SIDEBAR_MAX} aria-valuenow={settings.sidebarWidth} tabIndex={0} onPointerDown={(event) => event.currentTarget.setPointerCapture(event.pointerId)} onPointerMove={(event) => { if (event.buttons) updateSidebarWidth(event.clientX); }} onPointerUp={(event) => event.currentTarget.releasePointerCapture(event.pointerId)} onKeyDown={(event) => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); setSettings((state) => ({ ...state, sidebarWidth: clampSidebar(state.sidebarWidth + (event.key === "ArrowRight" ? 16 : -16)) })); } }} />}
      <button className="sidebar-expand" aria-label="展开导航" onClick={() => { setSettings((state) => ({ ...state, sidebarCollapsed: false })); window.requestAnimationFrame(() => searchInputRef.current?.focus()); }}><ChevronRight size={16} /><Search size={15} /><span>{selectedTab?.label ?? "当前位置"}</span></button>
      <section className="comparison-content" aria-label="比较内容">
        {selectedItem && stripVisible && <div className="overflow-tabs" role="tablist" aria-label="表格页签"><ScrollStrip>{stripTabs.map((tab) => { const active = !wholeTable && selectedTab?.tabKey === tab.tabKey && selectedTab.tableName === tab.tableName; const scope = tabScope(tab); const risk = scope.riskLevel; const deleted = scope.kind === "WHOLE_TABLE" && surfaceChangePresentation(scope.changeKind ?? "UNCHANGED").deleted; const warned = presentation.navigationDiagnostics.some(({ target }) => target.item_key === selectedItem.itemKey && target.tab_key === tab.tabKey); return <button role="tab" aria-selected={active} key={tab.tabKey + "|" + tab.tableName} data-tab-key={tab.tabKey} className={active ? "is-active" : ""} onClick={() => chooseTab(tab.tableName, tab.tabKey, selectedItem.itemKey)} title={tabTitle(scope) + (warned ? " · 有提示" : "")}>{warned && <AlertTriangle className="overflow-tabs__warn" size={12} aria-label="有提示" />}<span className={deleted ? "nav-item__label is-deleted" : "nav-item__label"}>{tab.label}</span><small>{scope.beforeCount ?? "—"} → {scope.currentCount ?? "—"}</small>{risk ? <RiskBadge level={risk} /> : <ScopeChangeBadge scope={scope} />}{!scope.riskComplete && <span className="scope-marker scope-marker--incomplete" title="风险信息不完整">风险?</span>}</button>; })}{wholeTable && <button role="tab" aria-selected className="is-active" data-tab-key={"__whole__:" + wholeTable.tableName}><span className="nav-item__label">整表：{wholeTable.label}</span></button>}</ScrollStrip>{itemEmptyTabCount > 0 && <button className="overflow-tabs__empty-toggle" aria-pressed={showEmptyTabs} title="没有行的页签" onClick={toggleEmptyTabs}>{showEmptyTabs ? "隐藏空页签" : `+${itemEmptyTabCount} 个空页签`}</button>}</div>}
          {selectedTab && table && surfaceTable ? <>
            {(() => {
              // One info line: what this scope changed and how many rows; reasons and notes open as popovers.
              const tabNotes = selectedItem ? presentation.navigationDiagnostics.filter(({ target }) => target.item_key === selectedItem.itemKey && target.tab_key === selectedTab.tabKey) : [];
              const tableNotes = presentation.navigationDiagnostics.filter((item) => !item.target.item_key && !item.target.tab_key && item.target.table_id === selectedTab.tableName);
              const surfaceNotes = surfaceTable.diagnostics?.diagnostics_summary ?? [];
              const scope = tabScope(selectedTab);
              const filtered = scope.kind !== "WHOLE_TABLE";
              const fallback = scope.kind === "LOCAL_FALLBACK";
              const schemaChanged = table.changeKind === "SCHEMA_CHANGED";
              const noteCount = surfaceNotes.length + tabNotes.length + tableNotes.length + (fallback ? 1 : 0) + (schemaChanged ? 1 : 0);
              const wholeTableChange = table.changeKind === "ADDED" || table.changeKind === "DELETED";
              const change = surfaceChangePresentation(table.changeKind);
              const viewKey = selectedNodeKey + "|" + selectedTab.tabKey + "|" + selectedTab.tableName;
              const riskText = localRiskText(scope);
              const local = scope.rowChanges;
              const moved = orderedMovedCount(surfaceTable);
              const wholeStats = wholeTableChange ? null : `+${surfaceTable.row_change_stats?.row_added_count ?? 0} / −${surfaceTable.row_change_stats?.row_deleted_count ?? 0} / ↔${surfaceTable.row_change_stats?.row_modified_count ?? 0}${moved ? " / ↕" + moved : ""}`;
              return <div className="table-info" data-scope={scope.kind}>
                <h2 className={stripVisible ? "sr-only" : "table-info__title"}>{selectedTab.label || table.label}</h2>
                {filtered ? <>
                  <ScopeChangeBadge scope={scope} />
                  {scope.riskLevel && <span title={"本页已确认风险：" + riskLevelText(scope.riskLevel)}><RiskBadge level={scope.riskLevel} /></span>}
                  <span className="table-info__muted" title="本页签自己的变化">{scopeChangeText(scope)}</span>
                  {riskText && <span className={scope.riskComplete ? "table-info__muted" : "scope-marker scope-marker--incomplete"}>{riskText}</span>}
                  <span className="table-info__counts" title="本页（本装置）的行数">本页 {scope.beforeCount ?? "—"} → {scope.currentCount ?? "—"} 行</span>
                  {local && <span className="table-info__counts" title="本页新增 / 删除 / 修改的行（修改含迁移行）">+{local.added} / −{local.deleted} / ↔{local.modified}{local.moved_in || local.moved_out ? `（移入 ${local.moved_in} · 移出 ${local.moved_out}）` : ""}</span>}
                  <span className="table-info__muted table-info__counts" title={"整表统计，不是本页签自己的结果" + (wholeStats ? "：新增 / 删除 / 修改" + (moved ? " / 移动" : "") : "")}>整表 {table.rowCounts.before ?? "—"} → {table.rowCounts.current ?? "—"} 行{wholeStats ? " · " + wholeStats : ""}</span>
                </> : <>
                  <SurfaceChangeBadge kind={table.changeKind} />
                  {table.riskLevel && <span title={riskLevelText(table.riskLevel)}><RiskBadge level={table.riskLevel} /></span>}
                  <span className={table.changeKind === "DEGRADED" ? "table-info__warn" : "table-info__muted"} title={[change.text, change.tooltip].filter(Boolean).join(" · ")}>{tableStatusText(table)}</span>
                  <span className="table-info__counts">{table.rowCounts.before ?? "—"} → {table.rowCounts.current ?? "—"} 行</span>
                  {wholeStats && <span className="table-info__muted table-info__counts" title={moved ? "新增 / 删除 / 修改 / 移动的行" : "新增 / 删除 / 修改的行"}>{wholeStats}</span>}
                  {table.annotationCount > 0 && <span className="table-info__muted">{table.annotationCount} 条风险标注</span>}
                  {selectedTab.tabKey.startsWith("__whole__:") && <span className="table-info__muted">整表视图</span>}
                </>}
                {rowRiskCounts.map(({ level, count }) => <span className="table-info__risk-count" key={level} title={(filtered ? "本页" : "本表") + "带风险的变化数"}><RiskBadge level={level} /><span>{count}</span></span>)}
                <span className="table-info__spacer" />
                {scope.notice && <InfoPopover key={viewKey + "|public"} tone="warn" label="表公共提示">
                  <div className="info-popover__list">
                    {noticeLines(scope.notice).map((line) => <span key={line}>{line}</span>)}
                    {scope.notice.unlocated_row_risk?.reason_codes.map((code) => <span key={code}>{noticeReasonText(code)}{debugMode && <code>{code}</code>}</span>)}
                    {filtered && <span>以上属于整张表，不是本装置自己的风险。</span>}
                  </div>
                  {filtered && <button className="link-button" onClick={() => openWholeTable(selectedTab.tableName)}>查看整表</button>}
                </InfoPopover>}
                {riskReasonDetails.length > 0 && <InfoPopover key={viewKey + "|risk"} tone="risk" label={`风险原因 ${riskReasonDetails.length}`}>
                  <div className="info-popover__list">{riskReasonDetails.map((detail) => <span key={detail.reasonCode + detail.ruleId} title={`reason_code=${detail.reasonCode}${detail.ruleId ? ` · rule_id=${detail.ruleId}` : ""}`}>{detail.copy}{debugMode && <code>{detail.reasonCode}{detail.ruleId ? " · " + detail.ruleId : ""}</code>}</span>)}</div>
                </InfoPopover>}
                {noteCount > 0 && <InfoPopover key={viewKey + "|notes"} tone="warn" label={`提示 ${noteCount}`}>
                  <div className="info-popover__list">
                    {surfaceNotes.map((diagnostic, index) => { const formatted = formatSurfaceDiagnostic(diagnostic); return <span key={diagnostic + index}>{formatted.message}{debugMode && <code>{formatted.raw}</code>}</span>; })}
                    {fallback && <span>本页签的逐行变化无法确定，显示为“变化未知”；整表结果不代表本装置。</span>}
                    {schemaChanged && <span>{formatSchemaSummary(surfaceTable.schema_summary)}</span>}
                  </div>
                  {[...tableNotes, ...tabNotes].map((diagnostic, index) => <NavigationDiagnosticNote key={diagnostic.code + index} diagnostic={diagnostic} tables={presentation.surface.tables} debug={debugMode} onOpenWholeTable={openWholeTable} onBrowseUnassigned={browseUnassigned} canBrowseUnassigned={canBrowseUnassigned} />)}
                </InfoPopover>}
              </div>;
            })()}
            {unassignedView && <div className="unassigned-banner" role="status"><span>未归属浏览 · {unassignedView.side === "BEFORE" ? "改前侧" : "改后侧"}：显示{unassignedView.side === "BEFORE" ? "改前" : "改后"}没有被任何装置筛选认领的行（共 {unassignedView.rowCount ?? "—"} 行未归属{unassignedView.changedRowCount === null ? "，其中变化行数未知" : `，其中 ${unassignedView.changedRowCount} 行有变化`}；当前可浏览 {unassignedView.browsableCount} 行）。</span>{unassignedView.partial && <span>本结果缺少改前快照：只列出有改前记录的行，不代表全部旧的未归属行。</span>}<button className="link-button" onClick={() => runtime.execute({ name: "set-unassigned", side: null })}>返回整表</button></div>}
            {debugMode && <DebugInfoBar table={surfaceTable} reasonDetails={riskReasonDetails} />}
            {replacement ? <ReplacementBrowser before={beforeRows} current={currentRows} table={surfaceTable} assessment={presentation.projectIdentityAssessment} side={browse.side} debug={debugMode} onSelectSide={(side) => runtime.execute({ name: "select-side", side })} /> : table.changeKind === "FAILED" ? <TableFailureNotice table={table} /> : <>
              {tableLoading ? <LoadingSkeleton label="正在读取本地表格" /> : <div className={`table-grid-area${locations.length || rows.some((row) => row.kind === "unchanged" && row.riskLevel !== null) ? " has-distribution" : ""}`}>
                <GridTable rows={rows} table={surfaceTable} tabKey={selectedTab.tabKey} annotations={annotations} debug={debugMode} highlighted={locations[currentIndex] ?? null} storedWidths={storedWidths} onWidthChange={changeColumnWidth} onVisibleRows={setVisibleRows} onExpand={(row) => setExpandedRuns((old) => { const next = new Set(old); if (next.has(row.key)) next.delete(row.key); else next.add(row.key); return next; })} onOpenFormula={(pointKey) => void openFormula(pointKey)} />
                {(locations.length > 0 || rows.some((row) => row.kind === "unchanged" && row.riskLevel !== null)) && <ChangeNavigator locations={locations} riskRows={rows.filter((row) => row.kind === "unchanged" && row.riskLevel !== null && row.ruler !== undefined)} rowCount={Math.max(table.rowCounts.before ?? 0, table.rowCounts.current ?? 0)} visibleRows={visibleRows} currentIndex={currentIndex} onJump={(index) => runtime.execute({ name: "jump-to-change", index })}
                  deletionLayout={settings.deletionLayout} onDeletionLayout={(deletionLayout) => setSettings((state) => ({ ...state, deletionLayout }))} />}
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

function ChangeNavigator({ locations, riskRows, rowCount, visibleRows, currentIndex, onJump, deletionLayout, onDeletionLayout }: {
  locations: ReturnType<typeof deriveChangeLocations>;
  riskRows: BrowseRow[];
  rowCount: number;
  visibleRows: { start: number; end: number };
  currentIndex: number;
  onJump: (index: number) => void;
  deletionLayout: DeletionLayout;
  onDeletionLayout: (layout: DeletionLayout) => void;
}) {
  if (!locations.length && !riskRows.length) return <div className="change-navigator"><span title="没有行级变化">—</span></div>;
  const grouped = deletionLayout === "group";
  const layoutTitle = grouped ? "删除与新增：合并显示（点击改为逐行交替）" : "删除与新增：逐行交替（点击改为合并显示）";
  const index = Math.min(currentIndex, Math.max(0, locations.length - 1));
  const range = Math.max(rowCount, 1);
  const toPercent = (position: number) => Math.max(0, Math.min(100, (position - .5) / range * 100));
  const selectedPosition = locations[index]?.position ?? index + 1;
  const visibleStart = Math.max(1, visibleRows.start);
  const visibleEnd = Math.max(visibleStart, visibleRows.end);
  const visibleTop = toPercent(visibleStart);
  const visibleBottom = Math.min(100, (visibleEnd / range) * 100);
  return <div className="change-navigator"><div className="change-navigator__controls">{locations.length ? <><span className="change-navigator__count" title={"第 " + (index + 1) + " 个变更，共 " + locations.length + " 个"}><strong>{index + 1}</strong><span>/{locations.length}</span></span><button aria-label="上一个变更" onClick={() => onJump(Math.max(0, index - 1))} disabled={index === 0}><ArrowUp size={15} /></button><button aria-label="下一个变更" onClick={() => onJump(Math.min(locations.length - 1, index + 1))} disabled={index === locations.length - 1}><ArrowDown size={15} /></button></> : <span title="没有行级变化">—</span>}<button className="change-navigator__layout" aria-label={layoutTitle} title={layoutTitle} aria-pressed={grouped} onClick={() => onDeletionLayout(grouped ? "interleave" : "group")}>{grouped ? <Rows2 size={15} /> : <Rows4 size={15} />}</button></div><div className="distribution-strip" role="group" aria-label={locations.length + " 个变更的位置分布"}>
    <span className="distribution-visible-range" aria-hidden="true" style={{ top: visibleTop + "%", height: Math.max(1, visibleBottom - visibleTop) + "%" }} />
    {riskRows.map((row) => <span key={"risk:" + row.key} aria-label={"第 " + (row.rowNumber ?? "未知") + " 行风险"} className={"distribution-mark distribution-mark--risk-only distribution-mark--" + (row.riskLevel ?? "UNKNOWN").toLowerCase().replace("_", "-")} style={{ top: toPercent(row.ruler ?? 1) + "%" }} />)}
    {locations.map((location, itemIndex) => { const position = location.position ?? itemIndex + 1; return <button key={String(location.rowIdentity) + itemIndex} aria-label={"定位第 " + (itemIndex + 1) + " 个变更"} className={"distribution-mark" + (location.riskLevel ? " distribution-mark--" + location.riskLevel.toLowerCase().replace("_", "-") : "") + (itemIndex === index ? " is-current" : "")} style={{ top: toPercent(position) + "%" }} onClick={() => onJump(itemIndex)} />; })}
    {locations.length > 0 && <span className="distribution-current-position" aria-hidden="true" style={{ top: toPercent(selectedPosition) + "%" }} />}
  </div></div>;
}

function NavigationDiagnosticNote({ diagnostic, tables, debug, onOpenWholeTable, onBrowseUnassigned, canBrowseUnassigned }: {
  diagnostic: NavigationDiagnostic;
  tables: readonly SurfaceTable[];
  debug: boolean;
  onOpenWholeTable: (tableName: string, itemKey?: string | null) => void;
  onBrowseUnassigned: (tableName: string, side: "BEFORE" | "CURRENT") => void;
  canBrowseUnassigned: (diagnostic: NavigationDiagnostic) => boolean;
}) {
  const message = formatNavigationDiagnostic(diagnostic, tables);
  const orphan = diagnostic.code === "DEVICE_ROWS_UNASSIGNED" && Boolean(diagnostic.target.table_id);
  const browsable = orphan && canBrowseUnassigned(diagnostic);
  return <div className="diagnostic-note diagnostic-note--navigation"><AlertTriangle size={14} /><span>{message}{orphan && !browsable && <small className="diagnostic-note__hint">（无法按装置条件筛出未归属行，请查看整表）</small>}</span>
    {orphan && <button onClick={() => onOpenWholeTable(diagnostic.target.table_id as string, diagnostic.target.item_key)}>查看整表</button>}
    {browsable && diagnostic.side && <button onClick={() => onBrowseUnassigned(diagnostic.target.table_id as string, diagnostic.side as "BEFORE" | "CURRENT")}>浏览未归属行</button>}
    {debug && <code>{JSON.stringify({ code: diagnostic.code, target: diagnostic.target, side: diagnostic.side, params: diagnostic.params })}</code>}</div>;
}

/**
 * Public table facts and device-definition changes, listed independently of
 * device items so they stay reachable when empty tabs are hidden or only
 * differences are shown. Nothing here paints a device with personal risk.
 */
function PublicNoticesPanel({ notices, changes, tables, items, debug, onOpenWholeTable, onOpenItem }: {
  notices: readonly NavigationTableNotice[];
  changes: readonly DeviceDefinitionChange[];
  tables: readonly SurfaceTable[];
  items: ReadonlyMap<string, string>;
  debug: boolean;
  onOpenWholeTable: (tableName: string, itemKey?: string | null) => void;
  onOpenItem: (itemKey: string) => void;
}) {
  if (notices.length === 0 && changes.length === 0) return null;
  const tableLabel = (tableId: string) => tables.find((table) => table.table_name === tableId)?.display_name || tableId;
  return <section className="public-notices" aria-label="表公共提示与装置定义变化">
    {notices.length > 0 && <details className="public-notices__section" open>
      <summary>表公共提示 <small>{notices.length}</small></summary>
      {notices.map((notice) => <div className="public-notice" key={notice.table_id} data-table-id={notice.table_id}>
        <button className="public-notice__title" onClick={() => onOpenWholeTable(notice.table_id)} title="打开整表">{tableLabel(notice.table_id)}</button>
        {noticeLines(notice).map((line) => <span key={line}>{line}</span>)}
        {notice.unlocated_row_risk && notice.unlocated_row_risk.reason_codes.length > 0 && <span className="public-notice__reasons">{notice.unlocated_row_risk.reason_codes.map((code) => <span key={code}>{noticeReasonText(code)}{debug && <code>{code}</code>}</span>)}</span>}
      </div>)}
    </details>}
    {changes.length > 0 && <details className="public-notices__section" open>
      <summary>装置定义变化 <small>{changes.length}</small></summary>
      {changes.map((change) => <div className="public-notice" key={change.record_identity} data-record-identity={change.record_identity}>
        <button className="public-notice__title" onClick={() => onOpenWholeTable("device")} title="在装置总表中查看">{definitionChangeText(change)}</button>
        <span>{change.risk_level ? "风险：" + riskLevelText(change.risk_level) : change.risk_complete ? "未生成风险标注" : "风险信息不完整"}{change.risk_level && !change.risk_complete ? "（风险信息不完整）" : ""}</span>
        <span className="public-notice__links">{[change.before_item_key, change.current_item_key].filter((key, index, keys): key is string => key !== null && keys.indexOf(key) === index).map((key) => <button key={key} className="link-button" onClick={() => onOpenItem(key)}>{items.get(key) ?? key}</button>)}</span>
        {debug && <code>{change.record_identity}</code>}
      </div>)}
    </details>}
  </section>;
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

function GridTable({ rows, table, tabKey, annotations, debug, highlighted, storedWidths, onWidthChange, onVisibleRows, onExpand, onOpenFormula }: { rows: BrowseRow[]; table: SurfaceTable; tabKey: string; annotations: RiskAnnotation[]; debug: boolean; highlighted: ChangeLocation | null; storedWidths: Readonly<Record<string, number>>; onWidthChange: (columnId: string, width: number) => void; onVisibleRows: (range: { start: number; end: number }) => void; onExpand: (row: BrowseRow) => void; onOpenFormula: (pointKey: string | null) => void }) {
  const gridRef = useRef<DataEditorRef>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  // The hover detail follows the pointer and flips to stay inside the viewport.
  const hoverDetailRef = useRef<HTMLDivElement>(null);
  const pointer = useRef<{ x: number; y: number } | null>(null);
  const placeHoverDetail = useCallback(() => {
    const element = hoverDetailRef.current; const at = pointer.current;
    if (!element || !at) return;
    const gap = 14; const margin = 8;
    const width = element.offsetWidth; const height = element.offsetHeight;
    const left = at.x + gap + width > window.innerWidth - margin ? at.x - gap - width : at.x + gap;
    const top = at.y + gap + height > window.innerHeight - margin ? at.y - gap - height : at.y + gap;
    element.style.left = Math.max(margin, Math.min(left, window.innerWidth - margin - width)) + "px";
    element.style.top = Math.max(margin, Math.min(top, window.innerHeight - margin - height)) + "px";
  }, []);
  const trackPointer = useCallback((event: ReactMouseEvent) => { pointer.current = { x: event.clientX, y: event.clientY }; placeHoverDetail(); }, [placeHoverDetail]);
  useLayoutEffect(() => { placeHoverDetail(); });
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
  const columnText = useCallback((row: BrowseRow, columnId: string): string => columnId === "__diff" ? rowLabel(row) : row.kind === "collapsed" ? ""
    : normalizeDisplayScalar(row.values[columnId], orderedColumns.find((column) => column.name === columnId)), [orderedColumns]);
  const fitColumn = useCallback((columnId: string, title: string, sourceRows: readonly BrowseRow[], mode: "auto" | "fit") =>
    fitWidth(measureHeader(title), sourceRows.map((row) => measureCell(columnText(row, columnId))), mode), [columnText, measureCell, measureHeader]);
  // Automatic widths are worked out once per table view (when its rows first
  // arrive), so expanding runs or toggling the scope does not shift columns.
  const autoWidthKey = `${table.table_name}|${tabKey}|${debug ? "debug" : "user"}|${rows.length > 0 ? "rows" : "empty"}`;
  const autoWidths = useMemo(() => {
    const sample = sampleRows(rows, 600);
    const widths = new Map<string, number>([["__diff", fitColumn("__diff", "变更", sample, "auto")]]);
    for (const column of orderedColumns) widths.set(column.name, fitColumn(column.name, columnHeaderTitle(column, debug), sample, "auto"));
    return widths;
    // Keyed on the table view, not on rows: later row changes must not move columns.
  }, [autoWidthKey, fitColumn, orderedColumns]);
  const columns = useMemo<SizedGridColumn[]>(() => {
    const width = (id: string, fallback: number) => storedWidths[id] ?? autoWidths.get(id) ?? fallback;
    const meta: SizedGridColumn[] = [{ id: "__number", title: "#", width: 60 }, { id: "__diff", title: "变更", width: width("__diff", 150) }];
    if (debug) meta.push({ id: "__kind", title: "Diff Kind", width: width("__kind", 210) }, { id: "__role", title: "Row Role", width: width("__role", 84) }, { id: "__semantic", title: "Ordered Semantic / Position", width: width("__semantic", 260) });
    return [...meta, ...orderedColumns.map((column) => ({ id: column.name, title: columnHeaderTitle(column, debug), width: width(column.name, 120) }))];
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
  // A pair shares one identity: both halves highlight; a blank-interval summary is found by its row key.
  const isHighlighted = useCallback((row: BrowseRow) => highlighted !== null
    && (highlighted.rowIdentity !== null ? row.rowIdentity === highlighted.rowIdentity : row.key === highlighted.rowKey), [highlighted]);
  useEffect(() => {
    if (!highlighted) return;
    const row = rows.findIndex(isHighlighted);
    if (row >= 0) gridRef.current?.scrollTo(1, row, "vertical", 0, 0, { vAlign: "center" });
  }, [highlighted, isHighlighted, rows]);
  const getCellContent = useCallback(([columnIndex, rowIndex]: readonly [number, number]): GridCell => {
    const row = rows[rowIndex]; const column = columns[columnIndex];
    if (!row || !column || typeof column.id !== "string") return { kind: GridCellKind.Loading, allowOverlay: false };
    const columnId = column.id;
    const pair = row.pairKey ? pairRows.get(row.pairKey) : undefined;
    const detached = pair && (pair.length !== 2 || Math.abs((pair[0] ?? 0) - (pair[1] ?? 0)) > 1);
    const beforePairRow = pair?.map((index) => rows[index]).find((candidate) => candidate?.kind === "modified-before");
    const formulaChanged = row.kind === "modified-after"
      && (beforePairRow ? beforePairRow.values.formula_digest !== row.values.formula_digest : row.formulaChanged === true);
    const columnShape = orderedColumns.find((item) => item.name === columnId);
    let value: unknown;
    if (columnId === "__number") value = row.rowNumber ?? "";
    else if (columnId === "__diff") value = row.kind === "collapsed" ? rowLabel(row) : rowLabel(row) + (detached ? " ↔" : "");
    else if (columnId === "__kind") value = row.recordKind ?? "—";
    else if (columnId === "__role") value = row.kind === "modified-before" ? "前" : row.kind === "modified-after" ? "后" : "—";
    else if (columnId === "__semantic") value = row.semanticKind ? row.semanticKind + " · " + (row.beforePosition ?? "—") + " → " + (row.currentPosition ?? "—") : "—";
    else if (columnId === "formula_ast_json" && table.table_name === "composite_signal_point") {
      value = "查看公式" + (formulaChanged ? " · 公式已改" : "");
    } else {
      value = missingSideMarker(row.side, columnShape?.present_in)
        ?? (row.partialValues && !Object.hasOwn(row.values, columnId) ? "不可得" : row.values[columnId]);
    }
    const risk = row.riskLevel ? riskTokens(row.riskLevel) : null;
    const changed = row.changedColumns.includes(columnId);
    const boldStyle = row.kind === "modified-after" && changed ? `600 ${theme.baseFontStyle}` : undefined;
    const cellTheme = risk
      ? { bgCell: changed ? risk.cell : risk.bg, textDark: row.kind === "modified-before" || row.kind === "deleted" ? "#535D69" : risk.text, ...(boldStyle ? { baseFontStyle: boldStyle } : {}) }
      : changed ? { bgCell: "#E6E9ED", textDark: "#1B2229", ...(boldStyle ? { baseFontStyle: boldStyle } : {}) } : undefined;
    return { kind: GridCellKind.Text, data: normalizeDisplayScalar(value, columnShape), displayData: normalizeDisplayScalar(value, columnShape), allowOverlay: false,
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
    if (isHighlighted(row)) { args.ctx.strokeStyle = "#1F5FBF"; args.ctx.lineWidth = 1; args.ctx.beginPath(); args.ctx.moveTo(args.rect.x, args.rect.y + .5); args.ctx.lineTo(args.rect.x + args.rect.width, args.rect.y + .5); args.ctx.moveTo(args.rect.x, args.rect.y + args.rect.height - .5); args.ctx.lineTo(args.rect.x + args.rect.width, args.rect.y + args.rect.height - .5); if (args.col === 0) { args.ctx.moveTo(args.rect.x + .5, args.rect.y); args.ctx.lineTo(args.rect.x + .5, args.rect.y + args.rect.height); } if (args.col === columns.length - 1) { args.ctx.moveTo(args.rect.x + args.rect.width - .5, args.rect.y); args.ctx.lineTo(args.rect.x + args.rect.width - .5, args.rect.y + args.rect.height); } args.ctx.stroke(); }
  }, [columns.length, debug, isHighlighted, markPainted, pairRows, rows]);
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
    // The navigator and the grid share the physical ruler; business `no` may be sparse.
    const start = first.ruler ?? 1;
    const end = (last.expanded ? null : last.collapsedRows?.at(-1)?.ruler) ?? last.ruler ?? start;
    markPainted();
    onVisibleRows({ start, end });
  }, [markPainted, onVisibleRows, rows]);
  const hoverRow = hoveredCell ? rows[hoveredCell[1]] : undefined;
  const hoverColumn = hoveredCell ? columns[hoveredCell[0]] : undefined;
  const hoverPair = hoverRow?.pairKey ? pairRows.get(hoverRow.pairKey) : undefined;
  const hoverBefore = hoverPair?.length === 2 ? rows[hoverPair.find((index) => rows[index]?.kind === "modified-before") ?? -1] : undefined;
  const hoverAfter = hoverPair?.length === 2 ? rows[hoverPair.find((index) => rows[index]?.kind === "modified-after") ?? -1] : undefined;
  const hoverColumnId = typeof hoverColumn?.id === "string" ? hoverColumn.id : null;
  // Every changed field of the hovered modified row, the hovered column first.
  const hoverFields = useMemo(() => {
    if (!hoverRow || !hoverBefore || !hoverAfter || !hoverRow.changedColumns.length) return [];
    const order = new Map(orderedColumns.map((column, index) => [column.name, index]));
    return [...hoverRow.changedColumns]
      .sort((left, right) => Number(right === hoverColumnId) - Number(left === hoverColumnId)
        || (order.get(left) ?? Number.MAX_SAFE_INTEGER) - (order.get(right) ?? Number.MAX_SAFE_INTEGER))
      .map((name) => ({ name, shape: orderedColumns.find((column) => column.name === name) }));
  }, [hoverAfter, hoverBefore, hoverColumnId, hoverRow, orderedColumns]);
  const hoverChanged = hoverFields.length > 0;
  const hoverAnnotation = hoverRow ? rowRiskAnnotation(hoverRow, annotations) : undefined;
  const hoverMove = hoverRow && hoverRow.kind !== "collapsed" ? rowMove(hoverRow) : null;
  const showHoverDetail = Boolean(hoverRow && (hoverChanged || hoverRow.riskLevel || hoverMove));
  const firstColumn = table.columns?.[0];
  const firstCellContent = rows[0] && firstColumn ? normalizeDisplayScalar(rows[0].values[firstColumn.name]) : "空表";
  return <div ref={frameRef} className="grid-frame" aria-label="比较表格" onDoubleClick={fitEdgeColumn} onMouseMove={trackPointer} data-tab-key={tabKey} data-rendered={rendered ? "true" : "false"} data-first-cell-content={firstCellContent} data-formula-column-offset={formulaColumnOffset} data-formula-column-width={formulaColumnWidth}><DataEditor ref={gridRef} columns={columns} rows={rows.length} getCellContent={getCellContent} getRowThemeOverride={getRowThemeOverride} drawCell={drawCell} onCellClicked={click} onCellActivated={activate} onColumnResize={resizeColumn} minColumnWidth={COLUMN_MIN} maxColumnWidth={COLUMN_FIT_MAX} onMouseMove={onMouseMove} onVisibleRegionChanged={onVisibleRegionChanged} headerHeight={34} rowHeight={34} theme={theme} width="100%" height={Math.max(240, frameSize.height)} smoothScrollX smoothScrollY verticalBorder={false} freezeColumns={frozenColumnCount} />
    {showHoverDetail && hoverRow && <div ref={hoverDetailRef} className="grid-hover-detail" role="tooltip">
      {hoverChanged && hoverBefore && hoverAfter && <section><strong>字段变更{hoverFields.length > 1 ? " · " + hoverFields.length + " 列" : ""}</strong>
        {hoverFields.slice(0, HOVER_FIELD_LIMIT).map(({ name, shape }) => <div key={name} className={name === hoverColumnId ? "is-hovered" : undefined}><span>{shape?.display_name || name}</span><code>{normalizeDisplayScalar(hoverBefore.values[name], shape)}</code><span aria-hidden="true">→</span><code className="grid-hover-detail__new">{normalizeDisplayScalar(hoverAfter.values[name], shape)}</code></div>)}
        {hoverFields.length > HOVER_FIELD_LIMIT && <small>另有 {hoverFields.length - HOVER_FIELD_LIMIT} 列</small>}</section>}
      {hoverMove && <section><strong>位置</strong><span>第 {hoverMove.from} 行 → 第 {hoverMove.to} 行</span></section>}
      {hoverRow.riskLevel && <section className="grid-hover-detail__risk"><strong>风险信息 <RiskBadge level={hoverRow.riskLevel} /></strong>{hoverAnnotation?.reasons.map((reason) => <span key={reason.reason_code + reason.rule_id} title={debug ? `reason_code=${reason.reason_code} · rule_id=${reason.rule_id}` : undefined}>{describeRiskReason(reason.reason_code, reason.evidence)}{debug && <code>{reason.reason_code} · {reason.rule_id}</code>}</span>)}<small>原始规则编码在 Debug 模式中查看</small></section>}
    </div>}
  </div>;
}

function ReplacementBrowser({ before, current, table, assessment, side, debug, onSelectSide }: { before: Record<string, unknown>[]; current: Record<string, unknown>[]; table: SurfaceTable; assessment?: Record<string, unknown>; side: "before" | "current" | null; debug: boolean; onSelectSide: (side: "before" | "current") => void }) {
  const summary = table.replacement_summary && typeof table.replacement_summary === "object" ? table.replacement_summary : {};
  const identityStatus = assessment?.status;
  const beforeSide = summary.before && typeof summary.before === "object" ? summary.before as Record<string, unknown> : {};
  const currentSide = summary.current && typeof summary.current === "object" ? summary.current as Record<string, unknown> : {};
  const beforeColumns = Array.isArray(beforeSide.columns) ? beforeSide.columns as NonNullable<SurfaceTable["columns"]> : table.columns ?? [];
  const currentColumns = Array.isArray(currentSide.columns) ? currentSide.columns as NonNullable<SurfaceTable["columns"]> : table.columns ?? [];
  const beforeTitle = typeof beforeSide.display_name === "string" && beforeSide.display_name ? beforeSide.display_name : "替换前";
  const currentTitle = typeof currentSide.display_name === "string" && currentSide.display_name ? currentSide.display_name : "替换后";
  return <section className="replacement-browser"><div className="replacement-summary"><strong>数据集替换 · 双侧浏览</strong><span className="replacement-status">身份结论：{identityStatusText(identityStatus)}</span><div className="identity-pair-summary"><span>匹配条目：{String(assessment?.matched_entry_count ?? "—")}</span><span>替换前：{String(assessment?.before_distinct_entry_count ?? "—")} 个身份条目</span><span>替换后：{String(assessment?.current_distinct_entry_count ?? "—")} 个身份条目</span></div><div className="replacement-side-toggle" role="tablist" aria-label="替换侧"><button role="tab" aria-selected={side === "before"} className={side === "before" ? "is-active" : ""} onClick={() => onSelectSide("before")}>{beforeTitle}</button><button role="tab" aria-selected={side === "current"} className={side === "current" ? "is-active" : ""} onClick={() => onSelectSide("current")}>{currentTitle}</button></div><small>{beforeTitle}：{before.length} 行 · {beforeColumns.length} 列</small><small>{currentTitle}：{current.length} 行 · {currentColumns.length} 列</small></div><div className="replacement-sides"><ReplacementSide title={beforeTitle} rows={before} columns={beforeColumns} debug={debug} active={side === null || side === "before"} /><ReplacementSide title={currentTitle} rows={current} columns={currentColumns} debug={debug} active={side === null || side === "current"} /></div></section>;
}

function ReplacementSide({ title, rows, columns, debug, active }: { title: string; rows: Record<string, unknown>[]; columns: NonNullable<SurfaceTable["columns"]>; debug: boolean; active: boolean }) {
  const theme = useMemo(() => createTableTheme(), []);
  const gridColumns = useMemo<GridColumn[]>(() => {
    const measureCell = createTextMeasure(`${theme.baseFontStyle} ${theme.fontFamily}`);
    const measureHeader = createTextMeasure(`${theme.headerFontStyle} ${theme.fontFamily}`);
    const sample = sampleRows(rows, 600);
    return columns.map((column) => {
      const title = columnHeaderTitle(column, debug);
      return { id: column.name, title, width: fitWidth(measureHeader(title), sample.map((row) => measureCell(normalizeDisplayScalar(row[column.name], column))), "auto") };
    });
  }, [columns, debug, rows, theme]);
  const getCellContent = useCallback(([column, row]: readonly [number, number]): GridCell => {
    const key = gridColumns[column]?.id; const item = rows[row]; if (!key || !item) return { kind: GridCellKind.Loading, allowOverlay: false };
    const value = normalizeDisplayScalar(item[key], columns[column]); return { kind: GridCellKind.Text, data: value, displayData: value, allowOverlay: false };
  }, [columns, gridColumns, rows]);
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
