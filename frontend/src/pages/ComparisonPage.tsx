import { DataEditor, GridCellKind, type DataEditorRef, type GridCell, type GridColumn, type Theme } from "@glideapps/glide-data-grid";
import "@glideapps/glide-data-grid/dist/index.css";
import { AlertTriangle, ArrowDown, ArrowUp, ChevronDown, ChevronLeft, ChevronRight, Code2, Copy, FileCode2, Search, Table2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ComponentProps, type CSSProperties } from "react";
import { createAuthenticatedFetch } from "../features/api/authenticated-fetch";
import { ensureLocalBundle, OpfsBundleStore, type InstalledBundle } from "../features/bundle/local-bundle";
import { loadComparisonPresentation, readLocalChangeRecords, readLocalRiskAnnotations, readLocalTable, type LocalComparisonPresentation } from "../features/bundle/presentation";
import { deriveChangeLocations, deriveFormulaDisplays, normalizeRowIdentity, type DerivedNavigationGroup, type DerivedTable, type RiskAnnotation, type RiskLevel, type RowDiffRecord, type SurfaceTable } from "../features/view-model/model";
import { buildBrowseRows, normalizeDisplayScalar, snapshotRowIdentity, type BrowseRow } from "../features/view-model/table-rows";
import { formatNavigationDiagnostic, formatSurfaceDiagnostic } from "../features/view-model/diagnostics";
import { describeRiskReason } from "../features/view-model/risk-copy";
import { BrowseCommandRuntime, decodeBrowseState, type BrowseState } from "../features/view-model/commands";
import { createTableTheme } from "../design-system/theme";
import { ChangeBadge, ErrorState, LoadingSkeleton, RiskBadge, formatBytes } from "../design-system/components";

type PairSummary = { pair_id: string };
type PairPresentation = { pair: PairSummary; presentation: LocalComparisonPresentation };
type Settings = { sidebarWidth: number; sidebarCollapsed: boolean; collapsedGroups: string[] };
const API = createAuthenticatedFetch({ baseUrl: window.location.origin, token: () => null });
const SETTINGS_KEY = "gateway-comparison-sidebar-v1";
const DEFAULT_SETTINGS: Settings = { sidebarWidth: 288, sidebarCollapsed: false, collapsedGroups: [] };

function readSettings(): Settings {
  try {
    const value = JSON.parse(window.localStorage.getItem(SETTINGS_KEY) ?? "null") as Partial<Settings> | null;
    return { sidebarWidth: typeof value?.sidebarWidth === "number" ? Math.max(224, Math.min(420, value.sidebarWidth)) : DEFAULT_SETTINGS.sidebarWidth,
      sidebarCollapsed: typeof value?.sidebarCollapsed === "boolean" ? value.sidebarCollapsed : window.innerWidth <= 1440,
      collapsedGroups: Array.isArray(value?.collapsedGroups) ? value.collapsedGroups.filter((item): item is string => typeof item === "string") : [] };
  } catch { return DEFAULT_SETTINGS; }
}

function getViewId(presentation: LocalComparisonPresentation): string {
  const view = presentation.surface.view;
  if (view && typeof view === "object" && typeof (view as Record<string, unknown>).view_id === "string") {
    return String((view as Record<string, unknown>).view_id);
  }
  throw new Error("bundle surface 缺少后端视图 ID");
}

function viewLabel(pair: PairPresentation, index: number, total: number, mode: BrowseState["mode"]): string {
  if (mode === "REVIEW") return "基线 → 待审提交";
  if (mode === "HISTORY") return "节点 " + (index + 1) + " → 节点 " + (index + 2);
  if (total === 1) return "当前基线 → 本次归档组态";
  const id = pair.pair.pair_id.toLowerCase();
  if (id.includes("baseline_to_initial")) return "原始组态视图";
  if (id.includes("initial_to_modified")) return "本次组态视图";
  return "比较视图 " + (index + 1);
}

function viewTitle(pair: PairPresentation, index: number, total: number, mode: BrowseState["mode"]): string {
  if (mode === "REVIEW") return "审核比较：基线节点 → 待审提交";
  if (mode === "HISTORY") return "节点 " + (index + 1) + " → 节点 " + (index + 2);
  if (total === 1) return "当前基线 → 本次归档组态";
  if (pair.pair.pair_id.toLowerCase().includes("baseline_to_initial")) return "已归档数据 → 原始组态备份";
  if (pair.pair.pair_id.toLowerCase().includes("initial_to_modified")) return "原始组态备份 → 本次归档组态";
  return getViewId(pair.presentation);
}

function statusText(table: DerivedTable): string {
  const copy: Record<string, string> = { UNCHANGED: "未变化", BUSINESS_EQUIVALENT: "业务等价", ADDED: "新增表", DELETED: "删除表", UPDATED: "有修改", MODIFIED: "有修改", SCHEMA_CHANGED: "结构变化", DEGRADED: "降级比较", FAILED: "比较失败", REPLACED: "数据集替换" };
  return copy[table.changeKind] ?? "比较过程有提示";
}

function badgeKind(kind: string): "ADDED" | "DELETED" | "UPDATED" | "UNCHANGED" {
  if (kind === "ADDED" || kind === "ADDED_TABLE") return "ADDED";
  if (kind === "DELETED" || kind === "DELETED_TABLE") return "DELETED";
  if (["UPDATED", "MODIFIED", "SCHEMA_CHANGED", "DEGRADED", "REPLACED"].includes(kind)) return "UPDATED";
  return "UNCHANGED";
}

function riskTokens(level: RiskLevel): { bg: string; rail: string; text: string; cell: string } {
  const style = getComputedStyle(document.documentElement);
  const name = "risk-" + level.toLowerCase().replace("_", "-");
  return { bg: style.getPropertyValue("--" + name + "-bg").trim(), rail: style.getPropertyValue("--" + name + "-rail").trim(),
    text: style.getPropertyValue("--" + name + "-text").trim(), cell: style.getPropertyValue("--" + name + "-cell").trim() };
}

function rowLabel(row: BrowseRow): string {
  if (row.kind === "collapsed") return "… " + (row.collapsedCount ?? 0) + " 行未变更";
  if (row.recordKind === "BLANK_DELETE_INTERVAL" || row.recordKind === "BLANK_INSERT_INTERVAL") {
    const interval = row.values.interval && typeof row.values.interval === "object" ? row.values.interval as Record<string, unknown> : {};
    const start = Number(interval.before_start ?? interval.current_start ?? row.beforePosition ?? row.currentPosition ?? 0);
    const end = Number(interval.before_end ?? interval.current_end ?? start);
    const insert = row.recordKind === "BLANK_INSERT_INTERVAL";
    return "第 " + start + "–" + end + " 行：" + (insert ? "插入" : "删除") + " " + Math.max(0, end - start + 1) + " 个空行";
  }
  if (row.kind === "added") return "+ 新增";
  if (row.kind === "deleted") return "− 删除";
  if (row.kind === "modified-before" || row.kind === "modified-after") return "↔ 修改";
  if (row.kind === "ordered") return "↕ 移动 · " + (row.beforePosition ?? "—") + " → " + (row.currentPosition ?? "—");
  if (row.kind === "blank") return "空行区间";
  return "";
}

function columnWidth(name: string, values: unknown[]): number {
  const longest = values.reduce<number>((length, value) => Math.max(length, Array.from(normalizeDisplayScalar(value)).length), Array.from(name).length);
  return Math.min(360, Math.max(112, longest * 8 + 38));
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

function tabHasSignal(tab: DerivedNavigationGroup["items"][number]["tabs"][number]): boolean {
  if (tab.rowFilter === null) return Boolean(tab.table && (tab.table.changeKind !== "UNCHANGED" || tab.table.riskLevel));
  return Boolean((tab.facts?.change_kind && tab.facts.change_kind !== "UNCHANGED") || tab.facts?.risk_level);
}

function requestForMode(mode: BrowseState["mode"], state: BrowseState): string | undefined {
  return state.modeRequests?.[mode] ?? state.requestPath;
}

function identityStatusText(value: unknown): string {
  if (value === "DIFFERENT_PROJECT") return "不同项目";
  if (value === "SAME_PROJECT") return "同一项目";
  if (value === "UNVERIFIABLE") return "项目身份无法验证";
  return "项目身份评估不可用";
}

export function ComparisonPage() {
  const runtime = useMemo(() => new BrowseCommandRuntime(decodeBrowseState(window.location.search)), []);
  const [browse, setBrowse] = useState<BrowseState>(runtime.snapshot.state);
  const [bundle, setBundle] = useState<InstalledBundle | null>(null);
  const [pairs, setPairs] = useState<PairPresentation[]>([]);
  const [loading, setLoading] = useState({ phase: "准备比较结果", received: 0, total: 0 });
  const [error, setError] = useState<{ code: string; details: string } | null>(null);
  const [settings, setSettings] = useState<Settings>(readSettings);
  const collapsed = settings.sidebarCollapsed;
  const [overflow, setOverflow] = useState(false);
  const [formulaOpen, setFormulaOpen] = useState(false);
  const [formulas, setFormulas] = useState<ReturnType<typeof deriveFormulaDisplays>>([]);
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
  const workspaceRef = useRef<HTMLDivElement>(null);
  const selectedNavRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const unsubscribe = runtime.subscribe(({ state }) => { setBrowse(state); setSearch(state.search); setOnlyInteresting(state.onlyInteresting); setDebug(state.debug); });
    const restore = () => runtime.restoreFromUrl();
    window.addEventListener("popstate", restore);
    return () => { unsubscribe(); window.removeEventListener("popstate", restore); };
  }, [runtime]);
  useEffect(() => { try { window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings)); } catch { /* defaults remain in memory */ } }, [settings]);

  const loadBundle = useCallback(async () => {
    const params = new URLSearchParams(window.location.search);
    const requestPath = browse.requestPath ?? requestForMode(browse.mode, browse) ?? params.get("request") ?? "";
    if (!requestPath.startsWith("/v1/")) {
      setError({ code: "BUNDLE_REQUEST_INVALID", details: "比较结果地址无效。" }); return;
    }
    const requestKey = (browse.bundleDigest ?? "new") + "|" + requestPath;
    if (loadingKey.current === requestKey) return;
    loadingKey.current = requestKey;
    setError(null); setBundle(null); setPairs([]);
    setLoading({ phase: "下载并校验比较结果", received: 0, total: 0 });
    try {
      const loaded = await ensureLocalBundle({ store: new OpfsBundleStore(), expectedBundleDigest: browse.bundleDigest ?? undefined,
        fetchBundle: () => API(requestPath, { headers: { Accept: "application/x-tar" } }),
        onProgress: ({ receivedBytes, contentLength }) => setLoading({ phase: "下载并校验比较结果", received: receivedBytes, total: contentLength }) });
      const pairSummaries = loaded.manifest.pairs.filter((value): value is PairSummary => Boolean(value && typeof value === "object" && typeof (value as PairSummary).pair_id === "string"));
      const loadedPairs = await Promise.all(pairSummaries.map(async (pair) => ({ pair, presentation: await loadComparisonPresentation(loaded, pair.pair_id) })));
      setBundle(loaded); setPairs(loadedPairs); setLoading({ phase: "比较结果已就绪", received: 0, total: 0 });
      const currentState = runtime.snapshot.state;
      if (currentState.bundleDigest !== loaded.manifest.bundle_digest || currentState.requestPath !== requestPath) runtime.execute({ name: "set-bundle", mode: currentState.mode, bundleDigest: loaded.manifest.bundle_digest, requestPath }, "external");
      const selected = loadedPairs.find(({ pair, presentation }) => pair.pair_id === currentState.pairId || getViewId(presentation) === currentState.viewId) ?? loadedPairs[0];
      if (selected && (currentState.pairId !== selected.pair.pair_id || currentState.viewId !== getViewId(selected.presentation))) {
        runtime.execute({ name: "select-pair", pairId: selected.pair.pair_id }, "external");
        runtime.execute({ name: "set-view", viewId: getViewId(selected.presentation) }, "external");
      }
    } catch (cause) {
      const details = cause instanceof Error ? cause.message : String(cause);
      setError({ code: /摘要|完整性|校验|截断/.test(details) ? "BUNDLE_INTEGRITY_MISMATCH" : "BUNDLE_LOAD_FAILED", details });
    } finally {
      if (loadingKey.current === requestKey) loadingKey.current = null;
    }
  }, [browse.bundleDigest, browse.mode, browse.modeRequests, browse.requestPath, runtime]);
  useEffect(() => { void loadBundle(); }, [loadBundle]);

  const activePair = pairs.find(({ pair }) => pair.pair_id === browse.pairId) ?? pairs.find(({ presentation }) => getViewId(presentation) === browse.viewId) ?? pairs[0];
  const presentation = activePair?.presentation ?? null;
  const groups = useMemo(() => presentation?.view.groups ?? [], [presentation]);
  const visibleGroups = useMemo(() => groups.filter((group) => {
    if (!matchesGroup(group, browse.search)) return false;
    return !browse.onlyInteresting || group.items.some((item) => item.changeKinds.some((kind) => kind !== "UNCHANGED") || item.riskLevels.length > 0)
      || presentation?.navigationDiagnostics.some((diagnostic) => diagnostic.target.group_key === group.groupKey) === true;
  }), [browse.onlyInteresting, browse.search, groups, presentation?.navigationDiagnostics]);
  const navigationEntries = useMemo(() => groups.flatMap((group) => group.items.flatMap((item) => item.tabs.map((tab) => ({ group, item, tab })))), [groups]);
  const wholeTableName = browse.tabKey?.startsWith("__whole__:") ? browse.tabKey.slice("__whole__:".length) : null;
  const wholeTable = wholeTableName ? presentation?.view.tables.find((item) => item.tableName === wholeTableName) : null;
  const selectedEntry = useMemo(() => navigationEntries.find(({ item, tab }) => item.itemKey === browse.nodeKey && tab.tabKey === browse.tabKey)
    ?? navigationEntries.find(({ tab }) => tab.tabKey === browse.tabKey)
    ?? navigationEntries[0]
    ?? null, [browse.nodeKey, browse.tabKey, navigationEntries]);
  const selectedTab = useMemo(() => wholeTable && wholeTableName
    ? { tabKey: "__whole__:" + wholeTableName, label: wholeTable.label, tableName: wholeTableName, rowFilter: null, facts: null, table: wholeTable }
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

  const loadTable = useCallback(async () => {
    if (!bundle || !presentation || !selectedTab || !surfaceTable) { setRows([]); return; }
    setTableLoading(true);
    try {
      const paths = presentation.tableArtifacts.get(selectedTab.tableName);
      const beforePromise = paths?.before ? readLocalTable(bundle, presentation, selectedTab.tableName, "before") : Promise.resolve([]);
      const currentPromise = paths?.current ? readLocalTable(bundle, presentation, selectedTab.tableName, "current") : Promise.resolve([]);
      if (replacement) {
        const [before, current] = await Promise.all([beforePromise, currentPromise]);
        setBeforeRows(before as Record<string, unknown>[]); setCurrentRows(current as Record<string, unknown>[]); setRows([]); setRecords([]); setAnnotations([]); return;
      }
      const [before, current, rowRecords, risks] = await Promise.all([beforePromise, currentPromise, readLocalChangeRecords(bundle, presentation, selectedTab.tableName), readLocalRiskAnnotations(bundle, presentation, selectedTab.tableName)]);
      const filterRows = (source: Record<string, unknown>[]) => selectedTab.rowFilter ? source.filter((row) => String(row[selectedTab.rowFilter?.column ?? ""] ?? "") === String(selectedTab.rowFilter?.value ?? "")) : source;
      const beforeFiltered = filterRows(before as Record<string, unknown>[]); const currentFiltered = filterRows(current as Record<string, unknown>[]);
      const recordsFiltered = filterRows(rowRecords as RowDiffRecord[]);
      setBeforeRows(beforeFiltered); setCurrentRows(currentFiltered); setRecords(recordsFiltered); setAnnotations(risks);
      setRows(buildBrowseRows({ table: surfaceTable, beforeRows: beforeFiltered, currentRows: currentFiltered, records: recordsFiltered, annotations: risks, onlyInteresting: browse.onlyInteresting, search: browse.search, expandedRuns }));
    } catch (cause) {
      setError({ code: "TABLE_READ_FAILED", details: cause instanceof Error ? cause.message : String(cause) });
    } finally { setTableLoading(false); }
  }, [browse.onlyInteresting, browse.search, bundle, expandedRuns, presentation, replacement, selectedTab, surfaceTable]);
  useEffect(() => { void loadTable(); }, [loadTable]);

  const locations = useMemo(() => deriveChangeLocations(records, annotations), [annotations, records]);
  const riskMap = useMemo(() => new Map(annotations.filter((annotation) => annotation.target.target_type === "ROW")
    .flatMap((annotation) => [annotation.target.row_identity, annotation.target.before_row_identity, annotation.target.current_row_identity]
      .map((identity) => normalizeRowIdentity(identity ?? undefined))
      .filter((identity): identity is string => Boolean(identity))
      .map((identity) => [identity, annotation.risk_level] as const))), [annotations]);
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
  const selectedGlobalIndex = navigationEntries.findIndex(({ item, tab }) => item.itemKey === browse.nodeKey && tab.tabKey === selectedTab?.tabKey && tab.tableName === selectedTab?.tableName);
  const visibleTabs = selectedGlobalIndex > 5 ? [...navigationEntries.slice(0, 5), navigationEntries[selectedGlobalIndex]].filter((entry): entry is NonNullable<typeof entry> => Boolean(entry)) : navigationEntries.slice(0, 6);
  const visibleTabKeys = new Set(visibleTabs.map(({ item, tab }) => item.itemKey + "|" + tab.tabKey + "|" + tab.tableName));
  const overflowTabs = navigationEntries.filter(({ item, tab }) => !visibleTabKeys.has(item.itemKey + "|" + tab.tabKey + "|" + tab.tableName));

  const switchMode = (mode: BrowseState["mode"]) => {
    const target = requestForMode(mode, browse);
    if (target && target !== browse.requestPath) runtime.execute({ name: "set-bundle", mode, bundleDigest: "", requestPath: target });
    else runtime.execute({ name: "set-mode", mode });
  };

  const chooseTab = (tableName: string, tabKey: string, itemKey = tableName) => {
    runtime.execute({ name: "select-node", nodeKey: itemKey }); runtime.execute({ name: "select-tab", tabKey }); setOverflow(false);
  };
  const choosePair = (pair: PairPresentation) => {
    runtime.execute({ name: "select-pair", pairId: pair.pair.pair_id }); runtime.execute({ name: "set-view", viewId: getViewId(pair.presentation) });
    runtime.execute({ name: "select-node", nodeKey: "" }); runtime.execute({ name: "select-tab", tabKey: "" });
  };
  const openWholeTable = (tableName: string, itemKey?: string | null) => {
    const owner = groups.flatMap((group) => group.items).find((item) => item.itemKey === itemKey || item.tabs.some((tab) => tab.tableName === tableName));
    runtime.execute({ name: "select-node", nodeKey: itemKey ?? owner?.itemKey ?? selectedNodeKey });
    runtime.execute({ name: "select-tab", tabKey: "__whole__:" + tableName });
  };
  const updateSidebarWidth = (clientX: number) => {
    const left = workspaceRef.current?.getBoundingClientRect().left ?? 0;
    setSettings((state) => ({ ...state, sidebarWidth: Math.max(224, Math.min(420, clientX - left)) }));
  };
  const openFormula = useCallback(async () => {
    if (!bundle || !presentation) return;
    const composite = presentation.surface.tables.find((item) => item.table_name === "composite_signal_point");
    if (!composite) return;
    const [before, current, beforeDevices, currentDevices] = await Promise.all([
      presentation.tableArtifacts.get(composite.table_name)?.before ? readLocalTable(bundle, presentation, composite.table_name, "before") : Promise.resolve([]),
      presentation.tableArtifacts.get(composite.table_name)?.current ? readLocalTable(bundle, presentation, composite.table_name, "current") : Promise.resolve([]),
      presentation.tableArtifacts.get("device")?.before ? readLocalTable(bundle, presentation, "device", "before") : Promise.resolve([]),
      presentation.tableArtifacts.get("device")?.current ? readLocalTable(bundle, presentation, "device", "current") : Promise.resolve([]),
    ]);
    const beforeRows = before as Record<string, unknown>[];
    const currentRows = current as Record<string, unknown>[];
    const records = await readLocalChangeRecords(bundle, presentation, composite.table_name);
    const changedPointKeys = new Set<string>();
    const deletedPointKeys = new Set<string>();
    for (const record of records) {
      const recordKind = String(record.record_kind ?? "");
      const identity = normalizeRowIdentity(record.row_identity);
      if (!identity) continue;
      const matchingRow = [...currentRows, ...beforeRows].find((row) => snapshotRowIdentity(row, composite) === identity);
      if (!matchingRow || typeof matchingRow.source_table !== "string" || matchingRow.point_gid === undefined) continue;
      const pointKey = `${matchingRow.source_table}:${String(matchingRow.point_gid)}`;
      if (recordKind === "ROW_MODIFIED" && (record.changed_columns ?? []).some((column) => column === "formula_digest" || column === "formula_ast_json")) changedPointKeys.add(pointKey);
      if (recordKind === "ROW_DELETED") deletedPointKeys.add(pointKey);
    }
    setFormulas(deriveFormulaDisplays({ mode: browse.mode === "PREVIEW" ? "PREVIEW" : "HISTORY", before: beforeRows, current: currentRows,
      beforeDevices: beforeDevices as Record<string, unknown>[], currentDevices: currentDevices as Record<string, unknown>[], changedPointKeys, deletedPointKeys }));
    setFormulaOpen(true);
  }, [browse.mode, bundle, presentation]);

  return <main className="comparison-page">
    <header className="compare-header">
      <div className="compare-header__top"><div className="compare-brand"><button className="back-link" aria-label="返回工作台">‹</button><div><div className="breadcrumb">工作台 <span>/</span> 差异浏览</div><h1>差异浏览</h1></div></div><div className="compare-header__mode" aria-label="模式操作区" /><div className="compare-status"><span className="compare-status__dot" />已连接 <span className="compare-status__divider" />{bundle ? "比较结果已就绪" : "读取比较结果"}</div></div>
      <div className="compare-header__bottom"><div className="mode-tabs" role="group" aria-label="浏览模式"><button className={browse.mode === "PREVIEW" ? "is-active" : ""} onClick={() => switchMode("PREVIEW")}>上传预览</button><button className={browse.mode === "REVIEW" ? "is-active" : ""} onClick={() => switchMode("REVIEW")}>审核</button><button className={browse.mode === "HISTORY" ? "is-active" : ""} onClick={() => switchMode("HISTORY")}>历史比较</button></div>
        <div className="view-tabs" role="tablist" aria-label="比较视图">{(browse.mode === "REVIEW" ? (activePair ? [activePair] : []) : pairs).map((pair) => { const index = pairs.findIndex(({ pair: item }) => item.pair_id === pair.pair.pair_id); return <button role="tab" aria-selected={activePair?.pair.pair_id === pair.pair.pair_id} className={activePair?.pair.pair_id === pair.pair.pair_id ? "is-active" : ""} key={pair.pair.pair_id} onClick={() => choosePair(pair)} title={viewTitle(pair, index, pairs.length, browse.mode)}>{viewLabel(pair, index, pairs.length, browse.mode)}</button>; })}</div>
        <div className="header-tools"><button className={onlyInteresting ? "toggle-chip is-active" : "toggle-chip"} onClick={() => runtime.execute({ name: "set-only-interesting", enabled: !onlyInteresting })}>只看变化 / 风险</button>{import.meta.env.DEV && <button className={debug ? "toggle-chip is-active" : "toggle-chip"} onClick={() => runtime.execute({ name: "set-debug", enabled: !debug })}><Code2 size={14} /> Debug</button>}</div>
      </div>
    </header>
    {!bundle && !error && <section className="compare-loading"><LoadingSkeleton label={loading.phase} /><div className="loading-progress"><span>{loading.phase}</span><span>{loading.total ? formatBytes(loading.received) + " / " + formatBytes(loading.total) : "正在准备"}</span></div></section>}
    {error && <section className="compare-error"><ErrorState code={error.code} details={error.details} onRetry={() => void loadBundle()} /></section>}
    {bundle && presentation && <div ref={workspaceRef} className={"compare-workspace" + (collapsed ? " sidebar-is-collapsed" : "")} style={{ "--sidebar-width": settings.sidebarWidth + "px" } as CSSProperties}>
      <aside className="navigation-sidebar" aria-label="比较导航"><div className="sidebar-heading"><div><span>比较内容</span><strong>{presentation.view.tables.length} 张表</strong></div><button className="icon-button" aria-label="收起导航" onClick={() => setSettings((state) => ({ ...state, sidebarCollapsed: true }))}><ChevronLeft size={18} /></button></div>
        <div className="sidebar-search"><Search size={15} /><input ref={searchInputRef} aria-label="搜索组、节点或页签" value={search} onChange={(event) => runtime.execute({ name: "set-search", search: event.currentTarget.value })} placeholder="搜索组、节点或页签" /></div><div className="sidebar-toolbar"><span>{visibleGroups.length} 个分组</span><button onClick={() => runtime.execute({ name: "set-only-interesting", enabled: !onlyInteresting })}>{onlyInteresting ? "显示全部" : "只看变化 / 风险"}</button></div>
        {globalNavigationDiagnostics.map((diagnostic, index) => <NavigationDiagnosticNote key={diagnostic.code + index} diagnostic={diagnostic} tables={presentation.surface.tables} debug={debugMode} onOpenWholeTable={openWholeTable} />)}
        <div className="sidebar-scroll">{presentation.navigation ? visibleGroups.map((group) => {
          const groupMatches = group.label.toLocaleLowerCase().includes(browse.search.trim().toLocaleLowerCase());
          const items = group.items.filter((item) => (groupMatches || matchesItem(item, browse.search)) && (!browse.onlyInteresting
            || item.changeKinds.some((kind) => kind !== "UNCHANGED")
            || item.riskLevels.length > 0
            || presentation.navigationDiagnostics.some((diagnostic) => diagnostic.target.item_key === item.itemKey)));
          const groupDiagnostics = presentation.navigationDiagnostics.filter((diagnostic) => diagnostic.target.group_key === group.groupKey);
          return <section className="nav-group" key={group.groupKey}><button className="nav-group__heading" aria-expanded={!settings.collapsedGroups.includes(group.groupKey)} onClick={() => { runtime.execute({ name: "toggle-group", groupKey: group.groupKey }); setSettings((state) => ({ ...state, collapsedGroups: state.collapsedGroups.includes(group.groupKey) ? state.collapsedGroups.filter((key) => key !== group.groupKey) : [...state.collapsedGroups, group.groupKey] })); }}><ChevronDown className={settings.collapsedGroups.includes(group.groupKey) ? "is-closed" : ""} size={14} /><span>{group.label}</span><small>{items.length}</small>{groupDiagnostics.length > 0 && <small className="nav-group__diagnostic-count">{groupDiagnostics.length} 条提示</small>}</button>
          {presentation.navigationDiagnostics.filter((diagnostic) => diagnostic.target.group_key === group.groupKey && !diagnostic.target.item_key && !diagnostic.target.tab_key).map((diagnostic, index) => <NavigationDiagnosticNote key={diagnostic.code + index} diagnostic={diagnostic} tables={presentation.surface.tables} debug={debugMode} onOpenWholeTable={openWholeTable} />)}
          {!settings.collapsedGroups.includes(group.groupKey) && items.map((item) => { const itemTabs = item.tabs.filter((tab) => (groupMatches || matchesItem(item, browse.search)) && (!browse.onlyInteresting || tab.table?.changeKind !== "UNCHANGED" || item.riskLevels.length > 0 || tab.facts?.change_kind && tab.facts.change_kind !== "UNCHANGED" || tab.facts?.risk_level || presentation.navigationDiagnostics.some((diagnostic) => diagnostic.target.item_key === item.itemKey && diagnostic.target.tab_key === tab.tabKey))); if (!itemTabs.length) return null; const active = item.itemKey === browse.nodeKey; const tabDiagnostics = (tabKey: string) => presentation.navigationDiagnostics.filter((diagnostic) => diagnostic.target.tab_key === tabKey && diagnostic.target.item_key === item.itemKey).map((diagnostic, index) => <NavigationDiagnosticNote key={diagnostic.code + index} diagnostic={diagnostic} tables={presentation.surface.tables} debug={debugMode} onOpenWholeTable={openWholeTable} />); const itemState = item.changeKinds.map((kind) => kind === "ADDED" ? "新增" : kind === "DELETED" ? "删除" : kind === "UNCHANGED" ? "未变化" : "有修改").join("、") || "未变化"; const itemTitle = `${item.label} · ${itemState}${item.riskLevels[0] ? " · " + item.riskLevels[0] : ""}`; return <div className={active ? "nav-item is-active" : "nav-item"} key={item.itemKey} ref={active ? selectedNavRef : undefined}><button className="nav-item__button" onClick={() => { const tab = itemTabs[0]; if (tab) chooseTab(tab.tableName, tab.tabKey, item.itemKey); }} title={itemTitle}><span className={"nav-icon nav-icon--" + item.itemKind.toLowerCase()}><Table2 size={15} /></span><span className={item.changeKinds.includes("DELETED") ? "nav-item__label is-deleted" : "nav-item__label"}>{item.label}</span>{item.riskLevels[0] ? <RiskBadge level={item.riskLevels[0]} /> : <span className="nav-change">{item.changeKinds.some((kind) => kind !== "UNCHANGED") ? "更新" : ""}</span>}</button>
            {presentation.navigationDiagnostics.filter((diagnostic) => diagnostic.target.item_key === item.itemKey && !diagnostic.target.tab_key).map((diagnostic, index) => <NavigationDiagnosticNote key={diagnostic.code + index} diagnostic={diagnostic} tables={presentation.surface.tables} debug={debugMode} onOpenWholeTable={openWholeTable} />)}
            {item.showTabs ? <div className="nav-item__tabs">{itemTabs.map((tab) => <div className="nav-tab" key={tab.tabKey}><button className={browse.nodeKey === item.itemKey && browse.tabKey === tab.tabKey ? "is-active" : ""} onClick={() => chooseTab(tab.tableName, tab.tabKey, item.itemKey)}>{tab.label}</button>{tabDiagnostics(tab.tabKey)}</div>)}</div> : itemTabs.flatMap((tab) => tabDiagnostics(tab.tabKey))}</div>; })}</section>; }) :
          <section className="nav-group"><div className="nav-group__heading"><span>全部表</span><small>占位导航</small></div>{visibleGroups.flatMap((group) => group.items).map((item) => { const tab = item.tabs[0]; return tab ? <button key={item.itemKey} className={browse.tabKey === tab.tabKey ? "nav-item__button is-active" : "nav-item__button"} onClick={() => chooseTab(tab.tableName, tab.tabKey, item.itemKey)}><Table2 size={15} /><span className="nav-item__label">{item.label}</span></button> : null; })}</section>}</div>
        <div className="sidebar-footer"><span>本地 bundle · 浏览期间不请求后端</span><small>{bundle.manifest.bundle_digest.slice(0, 19)}…</small></div>
      </aside>
      {!collapsed && <div className="sidebar-resize" role="separator" aria-label="调整侧栏宽度" aria-orientation="vertical" aria-valuemin={224} aria-valuemax={420} aria-valuenow={settings.sidebarWidth} tabIndex={0} onPointerDown={(event) => event.currentTarget.setPointerCapture(event.pointerId)} onPointerMove={(event) => { if (event.buttons) updateSidebarWidth(event.clientX); }} onPointerUp={(event) => event.currentTarget.releasePointerCapture(event.pointerId)} onKeyDown={(event) => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); setSettings((state) => ({ ...state, sidebarWidth: Math.max(224, Math.min(420, state.sidebarWidth + (event.key === "ArrowRight" ? 16 : -16))) })); } }} />}
      <button className="sidebar-expand" aria-label="展开导航" onClick={() => { setSettings((state) => ({ ...state, sidebarCollapsed: false })); window.requestAnimationFrame(() => searchInputRef.current?.focus()); }}><ChevronRight size={16} /><Search size={15} /><span>{selectedTab?.label ?? "当前位置"}</span></button>
      <section className="comparison-content" aria-label="比较内容">
        {navigationEntries.length > 0 && <div className="overflow-tabs" role="tablist" aria-label="表格页签"><div className="overflow-tabs__visible">{visibleTabs.map(({ item, tab }) => { const active = browse.nodeKey === item.itemKey && selectedTab?.tabKey === tab.tabKey && selectedTab.tableName === tab.tableName; return <button role="tab" aria-selected={active} key={item.itemKey + "|" + tab.tabKey + "|" + tab.tableName} className={active ? "is-active" : ""} onClick={() => chooseTab(tab.tableName, tab.tabKey, item.itemKey)}><span>{tab.label}</span>{tabHasSignal(tab) && <i className="overflow-tab-dot" aria-label="有变化或风险" />}</button>; })}</div>{overflowTabs.length > 0 && <div className="overflow-tabs__menu"><button aria-expanded={overflow} onClick={() => setOverflow(!overflow)}>更多 {overflowTabs.length}<ChevronDown size={14} /></button>{overflow && <div className="overflow-menu">{overflowTabs.map(({ item, tab }) => <button key={item.itemKey + "|" + tab.tabKey + "|" + tab.tableName} onClick={() => chooseTab(tab.tableName, tab.tabKey, item.itemKey)}><span>{tab.label}</span>{tabHasSignal(tab) && <i className="overflow-tab-dot" aria-label="有变化或风险" />}</button>)}</div>}</div>}</div>}
        {selectedTab && table && surfaceTable ? <><div className="table-heading"><div><div className="table-heading__title"><h2>{selectedTab.label || table.label}</h2>{table.riskLevel && <span title={`${statusText(table)} · ${table.riskLevel}`}><RiskBadge level={table.riskLevel} /></span>}</div><div className="table-heading__meta">{table.changeKind === "FAILED" ? <span className="table-state-badge table-state-badge--failed">失败</span> : <ChangeBadge kind={badgeKind(table.changeKind)} />}<span title={`${table.changeKind === "BUSINESS_EQUIVALENT" ? "内容写法不同，业务含义相同 · " : ""}change_kind=${table.changeKind}`}>{statusText(table)}</span><span>·</span><span>{table.rowCounts.before ?? "—"} → {table.rowCounts.current ?? "—"} 行</span>{table.annotationCount > 0 && <span>· {table.annotationCount} 条风险标注</span>}{selectedTab.tabKey.startsWith("__whole__:") && <span>· 整表视图</span>}</div></div><div className="table-heading__actions"><button className="icon-button" aria-label="查看公式" onClick={() => void openFormula()} disabled={!presentation.surface.tables.some((item) => item.table_name === "composite_signal_point")}><FileCode2 size={18} /></button></div></div>
          {debugMode && <DebugInfoBar table={surfaceTable} reasonDetails={riskReasonDetails} />}
          {table.changeKind === "SCHEMA_CHANGED" && <div className="table-state-note">{formatSchemaSummary(surfaceTable.schema_summary)}</div>}
          {[...(presentation.surfaceDiagnostics ?? []), ...(surfaceTable.diagnostics?.diagnostics_summary ?? [])].map((diagnostic, index) => { const formatted = formatSurfaceDiagnostic(diagnostic); return <div className="diagnostic-note" key={diagnostic + index}><AlertTriangle size={15} /><span>{formatted.message}</span>{debugMode && <code>{formatted.raw}</code>}</div>; })}
          {presentation.navigationDiagnostics.filter((item) => !item.target.group_key && !item.target.item_key && !item.target.tab_key && item.target.table_id === selectedTab.tableName).map((item, index) => <div className="diagnostic-note" key={item.code + index}><AlertTriangle size={15} /><span>{formatNavigationDiagnostic(item, presentation.surface.tables)}</span>{debugMode && <code>{item.code}</code>}</div>)}
          {replacement ? <ReplacementBrowser before={beforeRows} current={currentRows} table={surfaceTable} assessment={presentation.projectIdentityAssessment} /> : table.changeKind === "FAILED" ? <div className="table-failed" role="alert"><AlertTriangle size={20} /><strong>比较失败</strong><span>该表没有可显示的比较结果。</span></div> : <>
            <div className="risk-legend"><div><strong>行级风险</strong><span>风险来自比较结果中的风险标注</span></div>{riskReasonDetails.length > 0 && <div className="risk-legend__reasons">{riskReasonDetails.map((detail) => <span key={detail.reasonCode + detail.ruleId} title={`reason_code=${detail.reasonCode}${detail.ruleId ? ` · rule_id=${detail.ruleId}` : ""}`}>{detail.copy}{debugMode && <code>{detail.reasonCode}{detail.ruleId ? " · " + detail.ruleId : ""}</code>}</span>)}</div>}<div className="risk-legend__items">{[...riskMap.entries()].reduce((levels, [, level]) => { const match = levels.find((item) => item.level === level); if (match) match.count += 1; else levels.push({ level, count: 1 }); return levels; }, [] as Array<{ level: RiskLevel; count: number }>).map(({ level, count }) => <span key={level}><RiskBadge level={level} /> {count}</span>)}</div><span className="risk-legend__source">数据来源：差异结果</span></div>
            <ChangeNavigator locations={locations} riskRows={rows.filter((row) => row.kind === "unchanged" && row.riskLevel !== null)} rowCount={Math.max(table.rowCounts.before ?? 0, table.rowCounts.current ?? 0)} visibleRows={visibleRows} currentIndex={currentIndex} onJump={(index) => runtime.execute({ name: "jump-to-change", index })} onFormula={() => void openFormula()} hasFormula={presentation.surface.tables.some((item) => item.table_name === "composite_signal_point")} />
            {tableLoading ? <LoadingSkeleton label="正在读取本地表格" /> : <GridTable rows={rows} table={surfaceTable} annotations={annotations} debug={debugMode} highlightedIdentity={locations[currentIndex]?.rowIdentity ?? null} onVisibleRows={setVisibleRows} onExpand={(row) => setExpandedRuns((old) => new Set([...old, row.key]))} />}
          </>}</> : <div className="empty-table">请选择一个导航页签。</div>}
      </section>
    </div>}
    {formulaOpen && <div className="formula-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setFormulaOpen(false); }}><aside className="formula-drawer" role="dialog" aria-modal="true" aria-labelledby="formula-title"><header><div><span className="section-kicker">复合信号公式</span><h2 id="formula-title">公式查看</h2></div><button className="icon-button" aria-label="关闭公式" onClick={() => setFormulaOpen(false)}><X size={18} /></button></header><div className="formula-drawer__body">{browse.mode === "PREVIEW" && <p className="formula-note">改前公式在 BE-b 实现后提供。</p>}{formulas.map((formula) => <section className="formula-card" key={formula.pointKey}><div><strong>{formula.currentDeviceName ?? formula.beforeDeviceName ?? "未知装置"} · {formula.pointKey}</strong>{(formula.label || (formula.changed && browse.mode !== "PREVIEW")) && <span className="formula-changed">公式已改</span>}</div><div className={browse.mode === "PREVIEW" ? "formula-sides formula-sides--single" : "formula-sides"}>{browse.mode !== "PREVIEW" && <FormulaSide title="改前公式" formula={formula.beforeFormula} compare={formula.currentFormula} highlight={formula.changed} deviceName={formula.beforeDeviceName} />}<FormulaSide title={browse.mode === "PREVIEW" ? "上传侧公式" : "改后公式"} formula={formula.currentFormula} compare={browse.mode === "PREVIEW" ? undefined : formula.beforeFormula} highlight={browse.mode !== "PREVIEW" && formula.changed} deviceName={formula.currentDeviceName} /></div></section>)}</div></aside></div>}
  </main>;
}

function ChangeNavigator({ locations, riskRows, rowCount, visibleRows, currentIndex, onJump, onFormula, hasFormula }: {
  locations: ReturnType<typeof deriveChangeLocations>;
  riskRows: BrowseRow[];
  rowCount: number;
  visibleRows: { start: number; end: number };
  currentIndex: number;
  onJump: (index: number) => void;
  onFormula: () => void;
  hasFormula: boolean;
}) {
  if (!locations.length && !riskRows.length) return <div className="change-navigator"><span>没有行级变化</span>{hasFormula && <button onClick={onFormula}>查看公式</button>}</div>;
  const index = Math.min(currentIndex, Math.max(0, locations.length - 1));
  const range = Math.max(rowCount, 1);
  const toPercent = (position: number) => Math.max(0, Math.min(100, (position - .5) / range * 100));
  const selectedPosition = locations[index]?.position ?? index + 1;
  const visibleStart = Math.max(1, visibleRows.start);
  const visibleEnd = Math.max(visibleStart, visibleRows.end);
  const visibleLeft = toPercent(visibleStart);
  const visibleRight = Math.min(100, (visibleEnd / range) * 100);
  return <div className="change-navigator"><div className="change-navigator__controls">{locations.length ? <><span>变更 <strong>{index + 1}</strong> / {locations.length}</span><button aria-label="上一个变更" onClick={() => onJump(Math.max(0, index - 1))} disabled={index === 0}><ArrowUp size={15} /></button><button aria-label="下一个变更" onClick={() => onJump(Math.min(locations.length - 1, index + 1))} disabled={index === locations.length - 1}><ArrowDown size={15} /></button></> : <span>没有行级变化</span>}{hasFormula && <button className="formula-entry" onClick={onFormula}>查看公式</button>}</div><div className="distribution-strip" role="group" aria-label={locations.length + " 个变更的位置分布"}>
    <span className="distribution-visible-range" aria-hidden="true" style={{ left: visibleLeft + "%", width: Math.max(1, visibleRight - visibleLeft) + "%" }} />
    {riskRows.map((row) => <span key={"risk:" + row.key} aria-label={"第 " + row.rowNumber + " 行风险"} className={"distribution-mark distribution-mark--risk-only distribution-mark--" + (row.riskLevel ?? "UNKNOWN").toLowerCase().replace("_", "-")} style={{ left: toPercent(row.rowNumber) + "%" }} />)}
    {locations.map((location, itemIndex) => { const position = location.position ?? itemIndex + 1; return <button key={String(location.rowIdentity) + itemIndex} aria-label={"定位第 " + (itemIndex + 1) + " 个变更"} className={"distribution-mark" + (location.riskLevel ? " distribution-mark--" + location.riskLevel.toLowerCase().replace("_", "-") : "") + (itemIndex === index ? " is-current" : "")} style={{ left: toPercent(position) + "%" }} onClick={() => onJump(itemIndex)} />; })}
    {locations.length > 0 && <span className="distribution-current-position" aria-hidden="true" style={{ left: toPercent(selectedPosition) + "%" }} />}
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

function GridTable({ rows, table, annotations, debug, highlightedIdentity, onVisibleRows, onExpand }: { rows: BrowseRow[]; table: SurfaceTable; annotations: RiskAnnotation[]; debug: boolean; highlightedIdentity: string | null; onVisibleRows: (range: { start: number; end: number }) => void; onExpand: (row: BrowseRow) => void }) {
  const gridRef = useRef<DataEditorRef>(null);
  const [hoveredCell, setHoveredCell] = useState<readonly [number, number] | null>(null);
  const columns = useMemo<GridColumn[]>(() => {
    const meta: GridColumn[] = [{ id: "__number", title: "#", width: 54 }, { id: "__diff", title: "变更", width: 180 }];
    if (debug) meta.push({ id: "__kind", title: "Diff Kind", width: 210 }, { id: "__role", title: "Row Role", width: 84 }, { id: "__semantic", title: "Ordered Semantic / Position", width: 260 });
    const sample = rows.slice(0, 200);
    return [...meta, ...(table.columns ?? []).map((column) => ({ id: column.name, title: column.name, width: columnWidth(column.name, sample.map((row) => row.values[column.name])) }))];
  }, [debug, rows, table.columns]);
  const theme = useMemo(() => createTableTheme(), []);
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
    let value: unknown;
    if (columnId === "__number") value = row.rowNumber;
    else if (columnId === "__diff") value = row.kind === "collapsed" ? rowLabel(row) : rowLabel(row) + (detached ? " ↔" : "");
    else if (columnId === "__kind") value = row.recordKind ?? "—";
    else if (columnId === "__role") value = row.kind === "modified-before" ? "前" : row.kind === "modified-after" ? "后" : "—";
    else if (columnId === "__semantic") value = row.semanticKind ? row.semanticKind + " · " + (row.beforePosition ?? "—") + " → " + (row.currentPosition ?? "—") : "—";
    else value = row.values[columnId];
    const risk = row.riskLevel ? riskTokens(row.riskLevel) : null;
    const changed = row.changedColumns.includes(columnId);
    const boldStyle = row.kind === "modified-after" && changed ? `600 ${theme.baseFontStyle}` : undefined;
    const cellTheme = risk
      ? { bgCell: changed ? risk.cell : risk.bg, textDark: row.kind === "modified-before" || row.kind === "deleted" ? "#535D69" : risk.text, ...(boldStyle ? { baseFontStyle: boldStyle } : {}) }
      : changed ? { bgCell: "#E6E9ED", textDark: "#1B2229", ...(boldStyle ? { baseFontStyle: boldStyle } : {}) } : undefined;
    return { kind: GridCellKind.Text, data: normalizeDisplayScalar(value), displayData: normalizeDisplayScalar(value), allowOverlay: row.kind === "collapsed",
      style: row.kind === "modified-before" || row.kind === "deleted" ? "faded" : "normal",
      themeOverride: columnId === "__number" ? undefined : cellTheme };
  }, [columns, pairRows, rows]);
  const getRowThemeOverride = useCallback((row: number): Partial<Theme> | undefined => { const value = rows[row]; if (!value?.riskLevel) return undefined; const risk = riskTokens(value.riskLevel); return { bgCell: risk.bg, textDark: risk.text }; }, [rows]);
  const drawCell = useCallback((args: Parameters<NonNullable<ComponentProps<typeof DataEditor>["drawCell"]>>[0], drawContent: () => void) => {
    drawContent(); const row = rows[args.row]; if (!row) return;
    if (args.col === 0 && row.riskLevel) { args.ctx.fillStyle = riskTokens(row.riskLevel).rail; args.ctx.fillRect(args.rect.x, args.rect.y, 4, args.rect.height); }
    if (args.col === 1 && row.pairKey) { const pair = pairRows.get(row.pairKey) ?? []; const at = pair.indexOf(args.row); if (pair.length === 2 && Math.abs((pair[0] ?? 0) - (pair[1] ?? 0)) === 1) { args.ctx.strokeStyle = "#68798A"; args.ctx.lineWidth = 1.5; args.ctx.beginPath(); const x = args.rect.x + 14; const center = args.rect.y + args.rect.height / 2; args.ctx.moveTo(x, at === 0 ? center : args.rect.y); args.ctx.lineTo(x, at === 0 ? args.rect.y + args.rect.height : center); args.ctx.stroke(); } }
    if (row.kind === "deleted") { args.ctx.strokeStyle = "#535D69"; args.ctx.lineWidth = 1; args.ctx.beginPath(); const y = args.rect.y + args.rect.height / 2; args.ctx.moveTo(args.rect.x + 8, y); args.ctx.lineTo(args.rect.x + args.rect.width - 8, y); args.ctx.stroke(); }
    if (highlightedIdentity && row.rowIdentity === highlightedIdentity) { args.ctx.strokeStyle = "#1F5FBF"; args.ctx.lineWidth = 1; args.ctx.beginPath(); args.ctx.moveTo(args.rect.x, args.rect.y + .5); args.ctx.lineTo(args.rect.x + args.rect.width, args.rect.y + .5); args.ctx.moveTo(args.rect.x, args.rect.y + args.rect.height - .5); args.ctx.lineTo(args.rect.x + args.rect.width, args.rect.y + args.rect.height - .5); if (args.col === 0) { args.ctx.moveTo(args.rect.x + .5, args.rect.y); args.ctx.lineTo(args.rect.x + .5, args.rect.y + args.rect.height); } if (args.col === columns.length - 1) { args.ctx.moveTo(args.rect.x + args.rect.width - .5, args.rect.y); args.ctx.lineTo(args.rect.x + args.rect.width - .5, args.rect.y + args.rect.height); } args.ctx.stroke(); }
  }, [columns.length, highlightedIdentity, pairRows, rows]);
  const activate = useCallback(([column, row]: readonly [number, number]) => { if (columns[column]?.id === "__diff" && rows[row]?.kind === "collapsed") onExpand(rows[row] as BrowseRow); }, [columns, onExpand, rows]);
  const onMouseMove = useCallback((event: Parameters<NonNullable<ComponentProps<typeof DataEditor>["onMouseMove"]>>[0]) => {
    const next = event.kind === "cell" ? event.location : null;
    setHoveredCell((previous) => previous?.[0] === next?.[0] && previous?.[1] === next?.[1] ? previous : next);
  }, []);
  const onVisibleRegionChanged = useCallback((range: { y: number; height: number }) => {
    const first = rows[Math.max(0, Math.min(rows.length - 1, range.y))];
    const last = rows[Math.max(0, Math.min(rows.length - 1, range.y + range.height - 1))];
    if (!first || !last) return;
    const end = last.collapsedRows?.at(-1)?.rowNumber ?? last.rowNumber;
    onVisibleRows({ start: first.rowNumber, end });
  }, [onVisibleRows, rows]);
  const hoverRow = hoveredCell ? rows[hoveredCell[1]] : undefined;
  const hoverColumn = hoveredCell ? columns[hoveredCell[0]] : undefined;
  const hoverPair = hoverRow?.pairKey ? pairRows.get(hoverRow.pairKey) : undefined;
  const hoverBefore = hoverPair?.length === 2 ? rows[hoverPair.find((index) => rows[index]?.kind === "modified-before") ?? -1] : undefined;
  const hoverAfter = hoverPair?.length === 2 ? rows[hoverPair.find((index) => rows[index]?.kind === "modified-after") ?? -1] : undefined;
  const hoverColumnId = typeof hoverColumn?.id === "string" ? hoverColumn.id : null;
  const hoverChanged = Boolean(hoverRow && hoverColumnId && hoverRow.changedColumns.includes(hoverColumnId));
  const hoverAnnotation = hoverRow?.rowIdentity ? annotations.find((annotation) => annotation.target.target_type === "ROW" && [annotation.target.row_identity, annotation.target.before_row_identity, annotation.target.current_row_identity].some((identity) => identity !== null && normalizeRowIdentity(identity) === hoverRow.rowIdentity)) : undefined;
  const showHoverDetail = Boolean(hoverRow && (hoverChanged || hoverRow.riskLevel));
  const fieldTitle = table.columns?.find((column) => column.name === hoverColumn?.id)?.display_name ?? hoverColumn?.id ?? "";
  return <div className="grid-frame" aria-label="比较表格"><DataEditor ref={gridRef} columns={columns} rows={rows.length} getCellContent={getCellContent} getRowThemeOverride={getRowThemeOverride} drawCell={drawCell} onCellActivated={activate} onMouseMove={onMouseMove} onVisibleRegionChanged={onVisibleRegionChanged} headerHeight={38} rowHeight={38} theme={theme} width="100%" height={Math.max(300, Math.min(600, rows.length * 38 + 40))} smoothScrollX smoothScrollY verticalBorder={false} />
    {showHoverDetail && hoverRow && <div className="grid-hover-detail" role="tooltip">
      {hoverChanged && hoverColumnId && hoverBefore && hoverAfter && <section><strong>字段变更</strong><div><span>{fieldTitle}</span><code>{normalizeDisplayScalar(hoverBefore.values[hoverColumnId])}</code><span aria-hidden="true">→</span><code className="grid-hover-detail__new">{normalizeDisplayScalar(hoverAfter.values[hoverColumnId])}</code></div></section>}
      {hoverRow.riskLevel && <section className="grid-hover-detail__risk"><strong>风险信息 <RiskBadge level={hoverRow.riskLevel} /></strong>{hoverAnnotation?.reasons.map((reason) => <span key={reason.reason_code + reason.rule_id} title={debug ? `reason_code=${reason.reason_code} · rule_id=${reason.rule_id}` : undefined}>{describeRiskReason(reason.reason_code)}{debug && <code>{reason.reason_code} · {reason.rule_id}</code>}</span>)}<small>原始规则编码在 Debug 模式中查看</small></section>}
    </div>}
  </div>;
}

function ReplacementBrowser({ before, current, table, assessment }: { before: Record<string, unknown>[]; current: Record<string, unknown>[]; table: SurfaceTable; assessment?: Record<string, unknown> }) {
  const summary = table.replacement_summary && typeof table.replacement_summary === "object" ? table.replacement_summary : {};
  const identityStatus = assessment?.status ?? "DIFFERENT_PROJECT";
  const beforeSide = summary.before && typeof summary.before === "object" ? summary.before as Record<string, unknown> : {};
  const currentSide = summary.current && typeof summary.current === "object" ? summary.current as Record<string, unknown> : {};
  const beforeColumns = Array.isArray(beforeSide.columns) ? beforeSide.columns as NonNullable<SurfaceTable["columns"]> : table.columns ?? [];
  const currentColumns = Array.isArray(currentSide.columns) ? currentSide.columns as NonNullable<SurfaceTable["columns"]> : table.columns ?? [];
  return <section className="replacement-browser"><div className="replacement-summary"><strong>数据集替换 · 双侧浏览</strong><span className="replacement-status">身份结论：{identityStatusText(identityStatus)}</span><div className="identity-pair-summary"><span>匹配条目：{String(assessment?.matched_entry_count ?? "—")}</span><span>替换前：{String(assessment?.before_distinct_entry_count ?? "—")} 个身份条目</span><span>替换后：{String(assessment?.current_distinct_entry_count ?? "—")} 个身份条目</span></div><small>替换前：{before.length} 行 · {beforeColumns.length} 列</small><small>替换后：{current.length} 行 · {currentColumns.length} 列</small></div><div className="replacement-sides"><ReplacementSide title="替换前" rows={before} columns={beforeColumns} /><ReplacementSide title="替换后" rows={current} columns={currentColumns} /></div></section>;
}

function ReplacementSide({ title, rows, columns }: { title: string; rows: Record<string, unknown>[]; columns: NonNullable<SurfaceTable["columns"]> }) {
  const gridColumns = useMemo<GridColumn[]>(() => columns.map((column) => ({ id: column.name, title: column.name, width: columnWidth(column.name, rows.slice(0, 200).map((row) => row[column.name])) })), [columns, rows]);
  const getCellContent = useCallback(([column, row]: readonly [number, number]): GridCell => {
    const key = gridColumns[column]?.id; const item = rows[row]; if (!key || !item) return { kind: GridCellKind.Loading, allowOverlay: false };
    const value = normalizeDisplayScalar(item[key]); return { kind: GridCellKind.Text, data: value, displayData: value, allowOverlay: false };
  }, [gridColumns, rows]);
  return <section className="replacement-side"><h3>{title} <small>{rows.length} 行</small></h3><div className="grid-frame"><DataEditor columns={gridColumns} rows={rows.length} getCellContent={getCellContent} rowMarkers={{ kind: "number", width: 44 }} headerHeight={38} rowHeight={36} theme={createTableTheme()} width="100%" height={420} verticalBorder={false} /></div></section>;
}

function parseFormula(value: unknown): unknown {
  if (typeof value !== "string") return value;
  try { return JSON.parse(value) as unknown; } catch { return value; }
}

function FormulaTree({ value, other, highlight }: { value: unknown; other?: unknown; highlight: boolean }) {
  if (Array.isArray(value)) {
    const compared = Array.isArray(other) ? other : [];
    return <div className="formula-tree__collection">[ {value.map((item, index) => <div className="formula-tree__entry" key={index}><span className="formula-tree__key">{index}:</span><FormulaTree value={item} other={compared[index]} highlight={highlight} /></div>)} ]</div>;
  }
  if (value && typeof value === "object") {
    const compared = other && typeof other === "object" && !Array.isArray(other) ? other as Record<string, unknown> : {};
    return <div className="formula-tree__collection">&#123;{Object.entries(value as Record<string, unknown>).map(([key, item]) => <div className="formula-tree__entry" key={key}><span className="formula-tree__key">{key}:</span><FormulaTree value={item} other={compared[key]} highlight={highlight} /></div>)}&#125;</div>;
  }
  const different = highlight && JSON.stringify(value) !== JSON.stringify(other);
  return <span className={different ? "formula-tree__value is-changed" : "formula-tree__value"}>{value === undefined ? "∅" : JSON.stringify(value) ?? String(value)}</span>;
}

function FormulaSide({ title, formula, compare, highlight, deviceName }: { title: string; formula: unknown; compare?: unknown; highlight: boolean; deviceName: string | null }) {
  const parsed = parseFormula(formula);
  const compared = compare === undefined ? undefined : parseFormula(compare);
  return <section className="formula-side"><div><strong>{title}</strong><span>{deviceName ?? "未知装置"}</span></div><div className="formula-tree">{parsed == null ? "暂无公式" : <FormulaTree value={parsed} other={compared} highlight={highlight} />}</div></section>;
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
