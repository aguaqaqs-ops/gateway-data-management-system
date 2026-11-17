import "@glideapps/glide-data-grid/dist/index.css";
import {
  AlertTriangle,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Code2,
  MoreHorizontal,
  Search,
  Table2,
  X,
} from "lucide-react";
import { useRef, type CSSProperties, type ReactNode } from "react";
import { useBoundGatewayApi } from "../features/api/application-api";
import { bundleErrorTitle } from "../features/bundle/local-bundle";
import { tabScope } from "../features/view-model/model";
import {
  formatSurfaceDiagnostic,
  groupNavigationDiagnostics,
} from "../features/view-model/diagnostics";
import { itemChangeMark } from "../features/view-model/scope-copy";
import {
  SurfaceChangeBadge,
  surfaceChangePresentation,
  tableStatusText,
  TableFailureNotice,
} from "../features/view-model/table-state";
import { presentViewStatus } from "../features/view-model/view-status";
import {
  Dialog,
  ErrorState,
  LoadingSkeleton,
  RiskBadge,
  formatBytes,
} from "../design-system/components";
import { Button } from "../design-system/components";
import { ConnectionStatusIndicator } from "../features/workbench/ConnectionStatusIndicator";
import { formatWaitDuration } from "../features/workbench/wait-duration";
import { useUploadModeState } from "../features/workbench/use-upload-mode";
import { SessionGate } from "../features/session/SessionComponents";
import {
  formatHandoffDisplay,
  isGatewaySessionBlocked,
  useGatewaySessionState,
} from "../features/session/handoff-session";
import { SubmitDialog } from "../features/workbench/SubmitDialog";
import { OperationStatusPanel } from "../features/workbench/OperationStatusPanel";
import { ReviewActions } from "../features/workbench/ReviewActions";
import { ReviewDispositionLine } from "../features/workbench/disposition-display";
import { ChangeNavigator } from "./comparison/ChangeNavigator";
import { DebugInfoBar } from "./comparison/DebugInfoBar";
import { FormulaCard } from "./comparison/FormulaCard";
import { GridTable } from "./comparison/GridTable";
import { NavigationDiagnosticNote } from "./comparison/NavigationDiagnosticNote";
import { PreviewHeaderActions } from "./comparison/PreviewHeaderActions";
import {
  ChangeMark,
  InfoPopover,
  PublicNoticesPanel,
  ScopeChangeBadge,
  ScrollStrip,
} from "./comparison/PublicNoticesPanel";
import { ReplacementBrowser } from "./comparison/ReplacementBrowser";
import { clampSidebar, SIDEBAR_MAX, SIDEBAR_MIN } from "./comparison/sidebar-settings";
import { useBrowseRuntime } from "./comparison/use-browse-runtime";
import { useCompareHeaderHeight } from "./comparison/use-compare-header-height";
import { useComparisonBundle } from "./comparison/use-comparison-bundle";
import { useComparisonNavigation } from "./comparison/use-comparison-navigation";
import { useFormulaPanel } from "./comparison/use-formula-panel";
import { usePreviewSubmitResume } from "./comparison/use-preview-submit-resume";
import { usePreviewWithdraw } from "./comparison/use-preview-withdraw";
import { useReviewFacts } from "./comparison/use-review-facts";
import { useTabStripScroll } from "./comparison/use-tab-strip-scroll";
import { useTableData } from "./comparison/use-table-data";
import { useTableExpansion } from "./comparison/use-table-expansion";
import { useUnassignedBrowse } from "./comparison/use-unassigned-browse";
import { useViewSettings } from "./comparison/use-view-settings";
import {
  formatSchemaSummary,
  itemBadgeKind,
  itemStatusTooltip,
  localRiskText,
  noticeLines,
  noticeReasonText,
  reviewStatusLabel,
  riskLevelText,
  scopeChangeText,
  tabTitle,
  viewLabel,
  viewTitle,
} from "./comparison/view-copy";
import { orderedMovedCount, pairDiagnosticDetails, viewRiskLevel } from "./comparison/view-helpers";

export function ComparisonPage({ identityControl }: { identityControl?: ReactNode }) {
  const gatewayApi = useBoundGatewayApi();
  const sessionState = useGatewaySessionState();
  const { runtime, browse, search, onlyInteresting, debug } = useBrowseRuntime();
  // Upload-mode occupancy (withdraw/submit/upload gates) is shared with the
  // workbench through useUploadModeState (B4): a single read sequence for the
  // workspace, review, attempt and operation, with a one-time re-read (B2) and
  // a post-terminal resume re-read (B3).
  const uploadMode = useUploadModeState({ enabled: browse.mode === "PREVIEW" });
  const uploadGates = uploadMode.gates;

  const {
    submitOpen,
    setSubmitOpen,
    openSubmit,
    resumeOperationId,
    resumeNotice,
    refreshUploadMode,
    finishSubmitResume,
    retryResumeNotice,
  } = usePreviewSubmitResume(gatewayApi, uploadMode, runtime, browse.mode);
  const {
    withdrawOpen,
    setWithdrawOpen,
    withdrawBusy,
    withdrawUnderstood,
    setWithdrawUnderstood,
    withdrawError,
    openWithdraw,
    confirmWithdraw,
  } = usePreviewWithdraw(gatewayApi, uploadMode, refreshUploadMode);
  const { pageRef, headerRef } = useCompareHeaderHeight(sessionState);
  const {
    settings,
    setSettings,
    columnWidths,
    setColumnWidths,
    workspaceRef,
    fitSidebarWidth,
    updateSidebarWidth,
  } = useViewSettings();
  const {
    reviewFacts,
    setReviewFacts,
    reviewResultChecking,
    setReviewResultChecking,
    reviewResultErrorCode,
    setReviewResultErrorCode,
    readReviewContext,
  } = useReviewFacts(gatewayApi, runtime);
  const {
    bundle,
    pairs,
    loading,
    error,
    setError,
    historyCompareStatus,
    historyCompareWaited,
    loadBundle,
    reloadReviewContext,
  } = useComparisonBundle(gatewayApi, runtime, browse, sessionState.kind, {
    readReviewContext,
    setReviewResultChecking,
    setReviewResultErrorCode,
  });
  const {
    activePair,
    presentation,
    showEmptyTabs,
    selectedNavRef,
    shownTabs,
    shownItems,
    visibleGroups,
    wholeTableName,
    wholeTable,
    selectedEntry,
    emptyTabCount,
    toggleEmptyTabs,
    selectedTab,
    selectedNodeKey,
    globalNavigationDiagnostics,
    table,
    surfaceTable,
    replacement,
    chooseTab,
    choosePair,
    openWholeTable,
    itemLabels,
    openItem,
    selectedItem,
    stripTabs,
    itemEmptyTabCount,
    stripVisible,
  } = useComparisonNavigation({ pairs, browse, runtime });
  const { expandedRuns, toggleRun } = useTableExpansion(
    selectedNodeKey,
    selectedTab?.tabKey,
    selectedTab?.tableName,
  );
  const { filterTabsForTable, canBrowseUnassigned, browseUnassigned, activeUnassigned } =
    useUnassignedBrowse({ presentation, wholeTableName, browse, runtime, openWholeTable });
  const {
    rows,
    beforeRows,
    currentRows,
    annotations,
    tableLoading,
    visibleRows,
    setVisibleRows,
    locations,
    rowRiskCounts,
    currentIndex,
    riskReasonDetails,
    unassignedView,
    widthTable,
    storedWidths,
    changeColumnWidth,
    resetColumnWidths,
  } = useTableData({
    bundle,
    presentation,
    selectedTab,
    surfaceTable,
    replacement,
    browse,
    expandedRuns,
    filterTabsForTable,
    activeUnassigned,
    wholeTableName,
    deletionLayout: settings.deletionLayout,
    columnWidths,
    setColumnWidths,
    setError,
  });
  useTabStripScroll(selectedNodeKey, browse.tabKey);
  const { formulaOpen, setFormulaOpen, formulas, formulaFocus, setFormulaFocus, openFormula } =
    useFormulaPanel({ bundle, presentation, browseMode: browse.mode });

  const searchInputRef = useRef<HTMLInputElement>(null);
  const reviewNoticeRef = useRef<HTMLDivElement | null>(null);
  const collapsed = settings.sidebarCollapsed;
  const debugMode = debug && import.meta.env.DEV;
  const activePairIndex = activePair
    ? pairs.findIndex(({ pair }) => pair.pair_id === activePair.pair.pair_id)
    : 0;
  const viewPairs = pairs;
  // The device path leads the breadcrumb (full path on hover); the view label is
  // left out when the view switcher is visible in the same row.
  const deviceDisplay = sessionState.kind === "handoff" ? sessionState.session.display : null;
  const breadcrumbItems = [
    activePair && viewPairs.length <= 1
      ? viewLabel(activePair, activePairIndex, browse.mode)
      : null,
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

  if (isGatewaySessionBlocked(sessionState))
    return <SessionGate state={sessionState} identityControl={identityControl} />;
  return (
    <main ref={pageRef} className="comparison-page">
      {resumeOperationId && (
        <div className="comparison-resume">
          <OperationStatusPanel
            operationId={resumeOperationId}
            onSucceeded={(id) => void finishSubmitResume(id)}
            onFailed={(id) => void finishSubmitResume(id)}
          />
        </div>
      )}
      {resumeNotice && (
        <div role="alert" className="form-error">
          <span>{resumeNotice.title}</span>
          {resumeNotice.code && (
            <span>
              {resumeNotice.codeLabel ?? "操作ID"}：<code>{resumeNotice.code}</code>
              <button
                className="link-button"
                onClick={() => void navigator.clipboard?.writeText(resumeNotice.code ?? "")}
              >
                复制
              </button>
            </span>
          )}
          <span className="form-error__actions">
            <button className="link-button" onClick={() => void retryResumeNotice()}>
              重试
            </button>
            <button className="link-button" onClick={() => window.location.reload()}>
              刷新页面
            </button>
          </span>
        </div>
      )}
      <header ref={headerRef} className="compare-header">
        <h1 className="sr-only">差异浏览</h1>
        <div className="compare-header__bar">
          <button
            className="icon-button compare-back"
            aria-label="返回工作台"
            title="返回工作台"
            onClick={returnToWorkbench}
          >
            <ChevronLeft size={17} />
          </button>
          <nav className="breadcrumb" aria-label="位置">
            {deviceDisplay && (
              <span className="breadcrumb__device" title={formatHandoffDisplay(deviceDisplay)}>
                {deviceDisplay.project_name}（{deviceDisplay.station_code}）
              </span>
            )}
            {breadcrumbItems.map((item, index) => (
              <span key={item + index}>
                {(index > 0 || deviceDisplay) && <span aria-hidden="true">›</span>}
                {item}
              </span>
            ))}
          </nav>
          {browse.mode === "REVIEW" && browse.readOnly ? (
            <span
              className="mode-tag"
              title="提交时冻结的预览比较结果，不是父节点到此提交的净变化；净变化请在工作台用历史比较。"
            >
              提交时差异 · 只读
            </span>
          ) : (
            <span className="mode-tag">
              {browse.mode === "PREVIEW"
                ? "上传"
                : browse.mode === "REVIEW"
                  ? "审核"
                  : "历史比较 · 只读"}
            </span>
          )}
          {viewPairs.length > 1 && (
            <div className="view-tabs" role="tablist" aria-label="比较视图">
              {viewPairs.map((pair) => {
                const index = pairs.findIndex(
                  ({ pair: item }) => item.pair_id === pair.pair.pair_id,
                );
                const diagnostics = pairDiagnosticDetails(pair);
                const status = presentViewStatus(
                  pair.presentation.surface.view,
                  diagnostics.tableCount,
                );
                const risk = viewRiskLevel(pair);
                const active = activePair?.pair.pair_id === pair.pair.pair_id;
                return (
                  <button
                    role="tab"
                    aria-selected={active}
                    className={active ? "is-active" : ""}
                    key={pair.pair.pair_id}
                    onClick={() => choosePair(pair)}
                    title={[
                      viewTitle(pair, index, browse.mode),
                      status.text,
                      risk ? riskLevelText(risk) : null,
                      ...status.tooltipItems,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  >
                    <span>{viewLabel(pair, index, browse.mode)}</span>
                    {risk && <RiskBadge level={risk} />}
                  </button>
                );
              })}
            </div>
          )}
          <div className="scope-toggle" role="group" aria-label="表格范围">
            <button
              className={!onlyInteresting ? "is-active" : ""}
              aria-pressed={!onlyInteresting}
              onClick={() => runtime.execute({ name: "set-only-interesting", enabled: false })}
            >
              全部
            </button>
            <button
              className={onlyInteresting ? "is-active" : ""}
              aria-pressed={onlyInteresting}
              onClick={() => runtime.execute({ name: "set-only-interesting", enabled: true })}
            >
              仅看差异
            </button>
          </div>
          <div className="compare-status">
            <ConnectionStatusIndicator compact hideConnected={Boolean(error)} />
            {historyCompareStatus && (
              <>
                <span className="compare-status__divider" />
                <span>
                  {historyCompareStatus === "QUEUED"
                    ? "排队中"
                    : historyCompareStatus === "RUNNING"
                      ? `执行中 · 已等待 ${formatWaitDuration(historyCompareWaited)}`
                      : historyCompareStatus === "SUCCEEDED"
                        ? "比较已完成"
                        : historyCompareStatus === "FAILED"
                          ? "比较失败"
                          : "已取消"}
                </span>
              </>
            )}
            {reviewFacts && (
              <span className="review-facts-status">
                审核：{reviewStatusLabel(reviewFacts.status)}
              </span>
            )}
            {reviewFacts?.submission_disposition && (
              <span
                className={`status-tag status-tag--${reviewFacts.submission_disposition.disposition === "ARCHIVED_BASELINE" ? "info" : "neutral"}`}
                title={
                  reviewFacts.submission_disposition.disposition === "CLOSED_NOT_ARCHIVED"
                    ? reviewFacts.submission_disposition.source_kind === "ARCHIVE"
                      ? "归档时选中了其他提交"
                      : `由 ${reviewFacts.submission_disposition.closure?.closed_by ?? "未知"} 关闭：${reviewFacts.submission_disposition.closure?.reason ?? ""}`
                    : undefined
                }
              >
                {reviewFacts.submission_disposition.disposition === "ARCHIVED_BASELINE"
                  ? "已归档"
                  : "已关闭（未归档）"}
              </span>
            )}
            {identityControl}
            {browse.mode === "PREVIEW" && (
              <PreviewHeaderActions
                withdrawEnabled={uploadGates.withdraw.enabled}
                withdrawReason={uploadGates.withdraw.reason}
                withdrawRetry={Boolean(uploadGates.withdraw.retry && !uploadGates.withdraw.enabled)}
                withdrawRetryLabel={uploadGates.withdraw.retryLabel ?? "重试读取"}
                submitEnabled={Boolean(bundle) && uploadGates.submit.enabled}
                submitReason={!bundle ? "请等待差异结果加载完成" : uploadGates.submit.reason}
                onWithdraw={openWithdraw}
                onRetry={() => void refreshUploadMode()}
                onSubmit={openSubmit}
              />
            )}
            {browse.mode === "REVIEW" && !browse.readOnly && reviewFacts && browse.submissionId && (
              <ReviewActions
                submissionId={browse.submissionId}
                facts={reviewFacts}
                bundleReady={Boolean(bundle) && !reviewResultChecking}
                resultErrorCode={reviewResultErrorCode}
                onFactsChanged={setReviewFacts}
                onReviewSettled={reloadReviewContext}
                errorNoticeHost={reviewNoticeRef}
              />
            )}
          </div>
          <details className="compare-more">
            <summary aria-label="更多" title="更多">
              <MoreHorizontal size={17} />
            </summary>
            <div className="compare-more__menu">
              <label className="compare-more__check">
                <input type="checkbox" checked={showEmptyTabs} onChange={toggleEmptyTabs} />
                显示空页签（没有行，共 {emptyTabCount} 个）
              </label>
              {import.meta.env.DEV && (
                <div className="display-mode">
                  <span>显示模式（开发环境）</span>
                  <div role="radiogroup" aria-label="显示模式">
                    <button
                      role="radio"
                      aria-checked={!debug}
                      className={!debug ? "is-active" : ""}
                      onClick={() => runtime.execute({ name: "set-debug", enabled: false })}
                    >
                      User
                    </button>
                    <button
                      role="radio"
                      aria-checked={debug}
                      className={debug ? "is-active" : ""}
                      onClick={() => runtime.execute({ name: "set-debug", enabled: true })}
                    >
                      <Code2 size={13} /> Debug
                    </button>
                  </div>
                </div>
              )}
              {widthTable && Object.keys(storedWidths).length > 0 && (
                <button className="link-button compare-more__action" onClick={resetColumnWidths}>
                  恢复本表默认列宽
                </button>
              )}
              {browse.mode === "REVIEW" &&
                pairs.map((pair, index) => (
                  <div
                    key={pair.pair.pair_id}
                    className="compare-more__bundle"
                    data-pair-summary={pair.pair.pair_id}
                  >
                    <strong>{viewLabel(pair, index, browse.mode)}</strong>
                    <span>
                      变化表 {pair.pair.summary?.changed_table_count ?? "—"}/
                      {pair.pair.summary?.table_count ?? "—"}
                    </span>
                    <span>
                      逐行 +{pair.pair.summary?.row_added_count ?? "—"} / ~
                      {pair.pair.summary?.row_modified_count ?? "—"} / −
                      {pair.pair.summary?.row_deleted_count ?? "—"}
                    </span>
                  </div>
                ))}
              {bundle && (
                <div className="compare-more__bundle">
                  <span>本地 bundle · 浏览期间不请求后端</span>
                  <code>{bundle.manifest.bundle_digest}</code>
                </div>
              )}
            </div>
          </details>
        </div>
        {browse.mode === "REVIEW" && reviewFacts?.submission_disposition && (
          <ReviewDispositionLine facts={reviewFacts} />
        )}
        {browse.mode === "REVIEW" && (
          <div className="compare-header__notice" ref={reviewNoticeRef} />
        )}
      </header>
      {activePair?.presentation.navigation.initial_baseline && (
        <div className="pair-diagnostic-strip" role="status">
          首次建立基线
        </div>
      )}
      {activePair && pairDiagnosticDetails(activePair).codes.length > 0 && (
        <div className="pair-diagnostic-strip" role="status">
          {pairDiagnosticDetails(activePair).codes.map((diagnostic) => {
            const formatted = formatSurfaceDiagnostic(diagnostic);
            return (
              <div key={diagnostic}>
                <AlertTriangle size={14} />
                <span>{formatted.message}</span>
                {debugMode && <code>{formatted.raw}</code>}
              </div>
            );
          })}
        </div>
      )}
      {!bundle && !error && (
        <section className="compare-loading">
          <LoadingSkeleton label={loading.phase} />
          <div className="loading-progress">
            <span>{loading.phase}</span>
            <span>
              {loading.total
                ? formatBytes(loading.received) + " / " + formatBytes(loading.total)
                : "正在准备"}
            </span>
          </div>
        </section>
      )}
      {error && (
        <section className="compare-error">
          <ErrorState
            code={error.code}
            details={error.details}
            title={
              error.code === "SCOPE_FORBIDDEN"
                ? "当前身份没有该操作的权限"
                : bundleErrorTitle(error.code)
            }
            onRetry={() => void loadBundle()}
          />
        </section>
      )}
      {bundle && presentation && (
        <div
          ref={workspaceRef}
          className={"compare-workspace" + (collapsed ? " sidebar-is-collapsed" : "")}
          style={{ "--sidebar-width": settings.sidebarWidth + "px" } as CSSProperties}
        >
          <aside className="navigation-sidebar" aria-label="比较导航">
            <div className="sidebar-heading">
              <div className="sidebar-search">
                <Search size={14} />
                <input
                  ref={searchInputRef}
                  aria-label="搜索组、节点或页签"
                  value={search}
                  onChange={(event) =>
                    runtime.execute({ name: "set-search", search: event.currentTarget.value })
                  }
                  placeholder={`搜索 · ${presentation.view.tables.length} 张表`}
                />
              </div>
              <button
                className="icon-button"
                aria-label="收起导航"
                title="收起导航"
                onClick={() => setSettings((state) => ({ ...state, sidebarCollapsed: true }))}
              >
                <ChevronLeft size={16} />
              </button>
            </div>
            {globalNavigationDiagnostics.map((diagnostic, index) => (
              <NavigationDiagnosticNote
                key={diagnostic.code + index}
                diagnostic={diagnostic}
                tables={presentation.surface.tables}
                debug={debugMode}
                onOpenWholeTable={openWholeTable}
                onBrowseUnassigned={browseUnassigned}
                canBrowseUnassigned={canBrowseUnassigned}
              />
            ))}
            <div className="sidebar-scroll">
              <PublicNoticesPanel
                notices={presentation.view.tableNotices}
                changes={presentation.view.deviceDefinitionChanges}
                tables={presentation.surface.tables}
                items={itemLabels}
                debug={debugMode}
                onOpenWholeTable={openWholeTable}
                onOpenItem={openItem}
              />
              {visibleGroups.map((group) => {
                const items = shownItems(group);
                const groupDiagnostics = presentation.navigationDiagnostics.filter(
                  (diagnostic) => diagnostic.target.group_key === group.groupKey,
                );
                if (items.length === 0 && groupDiagnostics.length === 0) return null;
                return (
                  <section className="nav-group" key={group.groupKey}>
                    <button
                      className="nav-group__heading"
                      aria-expanded={!settings.collapsedGroups.includes(group.groupKey)}
                      onClick={() => {
                        runtime.execute({ name: "toggle-group", groupKey: group.groupKey });
                        setSettings((state) => ({
                          ...state,
                          collapsedGroups: state.collapsedGroups.includes(group.groupKey)
                            ? state.collapsedGroups.filter((key) => key !== group.groupKey)
                            : [...state.collapsedGroups, group.groupKey],
                        }));
                      }}
                    >
                      <ChevronDown
                        className={
                          settings.collapsedGroups.includes(group.groupKey) ? "is-closed" : ""
                        }
                        size={14}
                      />
                      <span className="nav-group__label">{group.label}</span>
                      <small title="非空项">
                        {items.filter((item) => item.nonemptyTabCount > 0).length}
                      </small>
                      {groupDiagnostics.length > 0 && (
                        <small className="nav-group__diagnostic-count">
                          {groupDiagnostics.length} 条提示
                        </small>
                      )}
                    </button>
                    {groupNavigationDiagnostics(
                      presentation.navigationDiagnostics,
                      group.groupKey,
                      items.map((item) => item.itemKey),
                    ).map((diagnostic, index) => (
                      <NavigationDiagnosticNote
                        key={diagnostic.code + index}
                        diagnostic={diagnostic}
                        tables={presentation.surface.tables}
                        debug={debugMode}
                        onOpenWholeTable={openWholeTable}
                        onBrowseUnassigned={browseUnassigned}
                        canBrowseUnassigned={canBrowseUnassigned}
                      />
                    ))}
                    {!settings.collapsedGroups.includes(group.groupKey) &&
                      items.map((item) => {
                        const itemTabs = shownTabs(item);
                        const active = item.itemKey === selectedNodeKey;
                        const { changeKinds, riskLevels } = item;
                        const itemState =
                          changeKinds
                            .map((kind) => surfaceChangePresentation(kind).text)
                            .join("、") || "未变化";
                        const itemKind = itemBadgeKind(changeKinds);
                        const itemMark = itemChangeMark(
                          item,
                          item.tabs.filter((tab) => !tab.empty).map(tabScope),
                        );
                        const itemTitle = `${item.label} · ${itemMark?.kind === "marker" ? itemMark.title : itemState}${itemStatusTooltip(changeKinds) ? " · " + itemStatusTooltip(changeKinds) : ""}${riskLevels[0] ? " · " + riskLevelText(riskLevels[0]) : ""}`;
                        return (
                          <div
                            className={active ? "nav-item is-active" : "nav-item"}
                            key={item.itemKey}
                            data-item-key={item.itemKey}
                            ref={active ? selectedNavRef : undefined}
                          >
                            <button
                              className="nav-item__button"
                              onClick={() => {
                                const tab = itemTabs[0];
                                if (tab) chooseTab(tab.tableName, tab.tabKey, item.itemKey);
                              }}
                              title={itemTitle}
                            >
                              <span className={"nav-icon nav-icon--" + item.itemKind.toLowerCase()}>
                                <Table2 size={15} />
                              </span>
                              <span
                                className={
                                  !itemMark &&
                                  changeKinds.some(
                                    (kind) => surfaceChangePresentation(kind).deleted,
                                  )
                                    ? "nav-item__label is-deleted"
                                    : "nav-item__label"
                                }
                              >
                                {item.label}
                              </span>
                              {riskLevels[0] ? (
                                <RiskBadge level={riskLevels[0]} />
                              ) : itemMark ? (
                                <ChangeMark mark={itemMark} />
                              ) : (
                                <SurfaceChangeBadge kind={itemKind} />
                              )}
                              {!item.changeComplete && (
                                <span
                                  className="scope-marker scope-marker--unknown"
                                  title="部分页签的变化或归属无法完整确定"
                                >
                                  变化?
                                </span>
                              )}
                              {!item.riskComplete && (
                                <span
                                  className="scope-marker scope-marker--incomplete"
                                  title="风险信息不完整，未标注不代表没有风险"
                                >
                                  风险?
                                </span>
                              )}
                              {item.tabs.some(
                                (tab) => tab.notice !== null && tab.rowFilter !== null,
                              ) && (
                                <span
                                  className="scope-marker scope-marker--public"
                                  title="相关表有整表或待定位提示，不是本装置自己的风险"
                                >
                                  表提示
                                </span>
                              )}
                            </button>
                            {presentation.navigationDiagnostics
                              .filter(
                                (diagnostic) =>
                                  diagnostic.target.item_key === item.itemKey &&
                                  !diagnostic.target.tab_key,
                              )
                              .map((diagnostic, index) => (
                                <NavigationDiagnosticNote
                                  key={diagnostic.code + index}
                                  diagnostic={diagnostic}
                                  tables={presentation.surface.tables}
                                  debug={debugMode}
                                  onOpenWholeTable={openWholeTable}
                                  onBrowseUnassigned={browseUnassigned}
                                  canBrowseUnassigned={canBrowseUnassigned}
                                />
                              ))}
                          </div>
                        );
                      })}
                  </section>
                );
              })}
            </div>
          </aside>
          {!collapsed && (
            <div
              className="sidebar-resize"
              role="separator"
              aria-label="调整侧栏宽度（双击适应名称）"
              title="拖动调整宽度，双击适应名称"
              onDoubleClick={fitSidebarWidth}
              aria-orientation="vertical"
              aria-valuemin={SIDEBAR_MIN}
              aria-valuemax={SIDEBAR_MAX}
              aria-valuenow={settings.sidebarWidth}
              tabIndex={0}
              onPointerDown={(event) => event.currentTarget.setPointerCapture(event.pointerId)}
              onPointerMove={(event) => {
                if (event.buttons) updateSidebarWidth(event.clientX);
              }}
              onPointerUp={(event) => event.currentTarget.releasePointerCapture(event.pointerId)}
              onKeyDown={(event) => {
                if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
                  event.preventDefault();
                  setSettings((state) => ({
                    ...state,
                    sidebarWidth: clampSidebar(
                      state.sidebarWidth + (event.key === "ArrowRight" ? 16 : -16),
                    ),
                  }));
                }
              }}
            />
          )}
          <button
            className="sidebar-expand"
            aria-label="展开导航"
            onClick={() => {
              setSettings((state) => ({ ...state, sidebarCollapsed: false }));
              window.requestAnimationFrame(() => searchInputRef.current?.focus());
            }}
          >
            <ChevronRight size={16} />
            <Search size={15} />
            <span>{selectedTab?.label ?? "当前位置"}</span>
          </button>
          <section className="comparison-content" aria-label="比较内容">
            {selectedItem && stripVisible && (
              <div className="overflow-tabs" role="tablist" aria-label="表格页签">
                <ScrollStrip>
                  {stripTabs.map((tab) => {
                    const active =
                      !wholeTable &&
                      selectedTab?.tabKey === tab.tabKey &&
                      selectedTab.tableName === tab.tableName;
                    const scope = tabScope(tab);
                    const risk = scope.riskLevel;
                    const deleted =
                      scope.kind === "WHOLE_TABLE" &&
                      surfaceChangePresentation(scope.changeKind ?? "UNCHANGED").deleted;
                    const warned = presentation.navigationDiagnostics.some(
                      ({ target }) =>
                        target.item_key === selectedItem.itemKey && target.tab_key === tab.tabKey,
                    );
                    return (
                      <button
                        role="tab"
                        aria-selected={active}
                        key={tab.tabKey + "|" + tab.tableName}
                        data-tab-key={tab.tabKey}
                        className={active ? "is-active" : ""}
                        onClick={() => chooseTab(tab.tableName, tab.tabKey, selectedItem.itemKey)}
                        title={tabTitle(scope) + (warned ? " · 有提示" : "")}
                      >
                        {warned && (
                          <AlertTriangle
                            className="overflow-tabs__warn"
                            size={12}
                            aria-label="有提示"
                          />
                        )}
                        <span
                          className={deleted ? "nav-item__label is-deleted" : "nav-item__label"}
                        >
                          {tab.label}
                        </span>
                        <small>
                          {scope.beforeCount ?? "—"} → {scope.currentCount ?? "—"}
                        </small>
                        {risk ? <RiskBadge level={risk} /> : <ScopeChangeBadge scope={scope} />}
                        {!scope.riskComplete && (
                          <span
                            className="scope-marker scope-marker--incomplete"
                            title="风险信息不完整"
                          >
                            风险?
                          </span>
                        )}
                      </button>
                    );
                  })}
                  {wholeTable && (
                    <button
                      role="tab"
                      aria-selected
                      className="is-active"
                      data-tab-key={"__whole__:" + wholeTable.tableName}
                    >
                      <span className="nav-item__label">整表：{wholeTable.label}</span>
                    </button>
                  )}
                </ScrollStrip>
                {itemEmptyTabCount > 0 && (
                  <button
                    className="overflow-tabs__empty-toggle"
                    aria-pressed={showEmptyTabs}
                    title="没有行的页签"
                    onClick={toggleEmptyTabs}
                  >
                    {showEmptyTabs ? "隐藏空页签" : `+${itemEmptyTabCount} 个空页签`}
                  </button>
                )}
              </div>
            )}
            {selectedTab && table && surfaceTable ? (
              <>
                {(() => {
                  // One info line: what this scope changed and how many rows; reasons and notes open as popovers.
                  const tabNotes = selectedItem
                    ? presentation.navigationDiagnostics.filter(
                        ({ target }) =>
                          target.item_key === selectedItem.itemKey &&
                          target.tab_key === selectedTab.tabKey,
                      )
                    : [];
                  const tableNotes = presentation.navigationDiagnostics.filter(
                    (item) =>
                      !item.target.item_key &&
                      !item.target.tab_key &&
                      item.target.table_id === selectedTab.tableName,
                  );
                  const surfaceNotes = surfaceTable.diagnostics?.diagnostics_summary ?? [];
                  const scope = tabScope(selectedTab);
                  const filtered = scope.kind !== "WHOLE_TABLE";
                  const fallback = scope.kind === "LOCAL_FALLBACK";
                  const schemaChanged = table.changeKind === "SCHEMA_CHANGED";
                  const noteCount =
                    surfaceNotes.length +
                    tabNotes.length +
                    tableNotes.length +
                    (fallback ? 1 : 0) +
                    (schemaChanged ? 1 : 0);
                  const wholeTableChange =
                    table.changeKind === "ADDED" || table.changeKind === "DELETED";
                  const change = surfaceChangePresentation(table.changeKind);
                  const viewKey =
                    selectedNodeKey + "|" + selectedTab.tabKey + "|" + selectedTab.tableName;
                  const riskText = localRiskText(scope);
                  const local = scope.rowChanges;
                  const moved = orderedMovedCount(surfaceTable);
                  const wholeStats = wholeTableChange
                    ? null
                    : `+${surfaceTable.row_change_stats?.row_added_count ?? 0} / −${surfaceTable.row_change_stats?.row_deleted_count ?? 0} / ↔${surfaceTable.row_change_stats?.row_modified_count ?? 0}${moved ? " / ↕" + moved : ""}`;
                  return (
                    <div className="table-info" data-scope={scope.kind}>
                      <h2 className={stripVisible ? "sr-only" : "table-info__title"}>
                        {selectedTab.label || table.label}
                      </h2>
                      {filtered ? (
                        <>
                          <ScopeChangeBadge scope={scope} />
                          {scope.riskLevel && (
                            <span title={"本页已确认风险：" + riskLevelText(scope.riskLevel)}>
                              <RiskBadge level={scope.riskLevel} />
                            </span>
                          )}
                          <span className="table-info__muted" title="本页签自己的变化">
                            {scopeChangeText(scope)}
                          </span>
                          {riskText && (
                            <span
                              className={
                                scope.riskComplete
                                  ? "table-info__muted"
                                  : "scope-marker scope-marker--incomplete"
                              }
                            >
                              {riskText}
                            </span>
                          )}
                          <span className="table-info__counts" title="本页（本装置）的行数">
                            本页 {scope.beforeCount ?? "—"} → {scope.currentCount ?? "—"} 行
                          </span>
                          {local && (
                            <span
                              className="table-info__counts"
                              title="本页新增 / 删除 / 修改的行（修改含迁移行）"
                            >
                              +{local.added} / −{local.deleted} / ↔{local.modified}
                              {local.moved_in || local.moved_out
                                ? `（移入 ${local.moved_in} · 移出 ${local.moved_out}）`
                                : ""}
                            </span>
                          )}
                          <span
                            className="table-info__muted table-info__counts"
                            title={
                              "整表统计，不是本页签自己的结果" +
                              (wholeStats ? "：新增 / 删除 / 修改" + (moved ? " / 移动" : "") : "")
                            }
                          >
                            整表 {table.rowCounts.before ?? "—"} → {table.rowCounts.current ?? "—"}{" "}
                            行{wholeStats ? " · " + wholeStats : ""}
                          </span>
                        </>
                      ) : (
                        <>
                          <SurfaceChangeBadge kind={table.changeKind} />
                          {table.riskLevel && (
                            <span title={riskLevelText(table.riskLevel)}>
                              <RiskBadge level={table.riskLevel} />
                            </span>
                          )}
                          <span
                            className={
                              table.changeKind === "DEGRADED"
                                ? "table-info__warn"
                                : "table-info__muted"
                            }
                            title={[change.text, change.tooltip].filter(Boolean).join(" · ")}
                          >
                            {tableStatusText(table)}
                          </span>
                          <span className="table-info__counts">
                            {table.rowCounts.before ?? "—"} → {table.rowCounts.current ?? "—"} 行
                          </span>
                          {wholeStats && (
                            <span
                              className="table-info__muted table-info__counts"
                              title={
                                moved ? "新增 / 删除 / 修改 / 移动的行" : "新增 / 删除 / 修改的行"
                              }
                            >
                              {wholeStats}
                            </span>
                          )}
                          {table.annotationCount > 0 && (
                            <span className="table-info__muted">
                              {table.annotationCount} 条风险标注
                            </span>
                          )}
                          {selectedTab.tabKey.startsWith("__whole__:") && (
                            <span className="table-info__muted">整表视图</span>
                          )}
                        </>
                      )}
                      {rowRiskCounts.map(({ level, count }) => (
                        <span
                          className="table-info__risk-count"
                          key={level}
                          title={(filtered ? "本页" : "本表") + "带风险的变化数"}
                        >
                          <RiskBadge level={level} />
                          <span>{count}</span>
                        </span>
                      ))}
                      <span className="table-info__spacer" />
                      {scope.notice && (
                        <InfoPopover key={viewKey + "|public"} tone="warn" label="表公共提示">
                          <div className="info-popover__list">
                            {noticeLines(scope.notice).map((line) => (
                              <span key={line}>{line}</span>
                            ))}
                            {scope.notice.unlocated_row_risk?.reason_codes.map((code) => (
                              <span key={code}>
                                {noticeReasonText(code)}
                                {debugMode && <code>{code}</code>}
                              </span>
                            ))}
                            {filtered && <span>以上属于整张表，不是本装置自己的风险。</span>}
                          </div>
                          {filtered && (
                            <button
                              className="link-button"
                              onClick={() => openWholeTable(selectedTab.tableName)}
                            >
                              查看整表
                            </button>
                          )}
                        </InfoPopover>
                      )}
                      {riskReasonDetails.length > 0 && (
                        <InfoPopover
                          key={viewKey + "|risk"}
                          tone="risk"
                          label={`风险原因 ${riskReasonDetails.length}`}
                        >
                          <div className="info-popover__list">
                            {riskReasonDetails.map((detail) => (
                              <span
                                key={detail.reasonCode + detail.ruleId}
                                title={`reason_code=${detail.reasonCode}${detail.ruleId ? ` · rule_id=${detail.ruleId}` : ""}`}
                              >
                                {detail.copy}
                                {debugMode && (
                                  <code>
                                    {detail.reasonCode}
                                    {detail.ruleId ? " · " + detail.ruleId : ""}
                                  </code>
                                )}
                              </span>
                            ))}
                          </div>
                        </InfoPopover>
                      )}
                      {noteCount > 0 && (
                        <InfoPopover
                          key={viewKey + "|notes"}
                          tone="warn"
                          label={`提示 ${noteCount}`}
                        >
                          <div className="info-popover__list">
                            {surfaceNotes.map((diagnostic, index) => {
                              const formatted = formatSurfaceDiagnostic(diagnostic);
                              return (
                                <span key={diagnostic + index}>
                                  {formatted.message}
                                  {debugMode && <code>{formatted.raw}</code>}
                                </span>
                              );
                            })}
                            {fallback && (
                              <span>
                                本页签的逐行变化无法确定，显示为“变化未知”；整表结果不代表本装置。
                              </span>
                            )}
                            {schemaChanged && (
                              <span>{formatSchemaSummary(surfaceTable.schema_summary)}</span>
                            )}
                          </div>
                          {[...tableNotes, ...tabNotes].map((diagnostic, index) => (
                            <NavigationDiagnosticNote
                              key={diagnostic.code + index}
                              diagnostic={diagnostic}
                              tables={presentation.surface.tables}
                              debug={debugMode}
                              onOpenWholeTable={openWholeTable}
                              onBrowseUnassigned={browseUnassigned}
                              canBrowseUnassigned={canBrowseUnassigned}
                            />
                          ))}
                        </InfoPopover>
                      )}
                    </div>
                  );
                })()}
                {unassignedView && (
                  <div className="unassigned-banner" role="status">
                    <span>
                      未归属浏览 · {unassignedView.side === "BEFORE" ? "改前侧" : "改后侧"}：显示
                      {unassignedView.side === "BEFORE" ? "改前" : "改后"}
                      没有被任何装置筛选认领的行（共 {unassignedView.rowCount ?? "—"} 行未归属
                      {unassignedView.changedRowCount === null
                        ? "，其中变化行数未知"
                        : `，其中 ${unassignedView.changedRowCount} 行有变化`}
                      ；当前可浏览 {unassignedView.browsableCount} 行）。
                    </span>
                    {unassignedView.partial && (
                      <span>
                        本结果缺少改前快照：只列出有改前记录的行，不代表全部旧的未归属行。
                      </span>
                    )}
                    <button
                      className="link-button"
                      onClick={() => runtime.execute({ name: "set-unassigned", side: null })}
                    >
                      返回整表
                    </button>
                  </div>
                )}
                {debugMode && (
                  <DebugInfoBar table={surfaceTable} reasonDetails={riskReasonDetails} />
                )}
                {replacement ? (
                  <ReplacementBrowser
                    before={beforeRows}
                    current={currentRows}
                    table={surfaceTable}
                    assessment={presentation.projectIdentityAssessment}
                    side={browse.side}
                    debug={debugMode}
                    onSelectSide={(side) => runtime.execute({ name: "select-side", side })}
                  />
                ) : table.changeKind === "FAILED" ? (
                  <TableFailureNotice table={table} />
                ) : (
                  <>
                    {tableLoading ? (
                      <LoadingSkeleton label="正在读取本地表格" />
                    ) : (
                      <div
                        className={`table-grid-area${locations.length || rows.some((row) => row.kind === "unchanged" && row.riskLevel !== null) ? " has-distribution" : ""}`}
                      >
                        <GridTable
                          rows={rows}
                          table={surfaceTable}
                          tabKey={selectedTab.tabKey}
                          annotations={annotations}
                          debug={debugMode}
                          highlighted={locations[currentIndex] ?? null}
                          storedWidths={storedWidths}
                          onWidthChange={changeColumnWidth}
                          onVisibleRows={setVisibleRows}
                          onExpand={(row) => toggleRun(row.key)}
                          onOpenFormula={(pointKey) => void openFormula(pointKey)}
                        />
                        {(locations.length > 0 ||
                          rows.some(
                            (row) => row.kind === "unchanged" && row.riskLevel !== null,
                          )) && (
                          <ChangeNavigator
                            locations={locations}
                            riskRows={rows.filter(
                              (row) =>
                                row.kind === "unchanged" &&
                                row.riskLevel !== null &&
                                row.ruler !== undefined,
                            )}
                            rowCount={Math.max(
                              table.rowCounts.before ?? 0,
                              table.rowCounts.current ?? 0,
                            )}
                            visibleRows={visibleRows}
                            currentIndex={currentIndex}
                            onJump={(index) => runtime.execute({ name: "jump-to-change", index })}
                            deletionLayout={settings.deletionLayout}
                            onDeletionLayout={(deletionLayout) =>
                              setSettings((state) => ({ ...state, deletionLayout }))
                            }
                          />
                        )}
                      </div>
                    )}
                  </>
                )}
              </>
            ) : (
              <div className="empty-table">请选择一个导航页签。</div>
            )}
          </section>
        </div>
      )}
      {browse.mode === "PREVIEW" && browse.workspaceId && browse.previewResultId && (
        <SubmitDialog
          open={submitOpen}
          workspaceId={browse.workspaceId}
          previewResultId={browse.previewResultId}
          onClose={() => setSubmitOpen(false)}
          onSubmitted={(submissionId) => {
            const params = new URLSearchParams({ page: "compare", mode: "REVIEW", submissionId });
            if (browse.workbenchNodeKey) params.set("workbenchNode", browse.workbenchNodeKey);
            for (const ref of browse.comparisonNodeRefs) params.append("compare", ref);
            window.location.assign(`/?${params.toString()}`);
          }}
        />
      )}
      <Dialog
        open={withdrawOpen}
        title="撤回提交"
        onClose={() => {
          if (!withdrawBusy) setWithdrawOpen(false);
        }}
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() => setWithdrawOpen(false)}
              disabled={withdrawBusy}
            >
              取消
            </Button>
            <Button
              variant="danger"
              onClick={() => void confirmWithdraw()}
              disabled={withdrawBusy || !withdrawUnderstood}
              disabledReason={!withdrawUnderstood ? "请先确认已了解撤回影响" : undefined}
            >
              {withdrawBusy ? "撤回中…" : "确认撤回"}
            </Button>
          </>
        }
      >
        <p className="confirm-impact">
          撤回后该提交不再进入归档候选，也无法继续审核；提交人需要重新上传并提交。此操作不可撤销。
        </p>
        <label className="confirm-checkbox">
          <input
            type="checkbox"
            checked={withdrawUnderstood}
            onChange={(event) => setWithdrawUnderstood(event.currentTarget.checked)}
          />
          我已了解撤回后需要重新提交，并确认继续
        </label>
        {withdrawError && (
          <div role="alert" className="form-error">
            <span>{withdrawError.title}</span>
            <span>
              错误代码：<code>{withdrawError.code}</code>
            </span>
          </div>
        )}
      </Dialog>
      {formulaOpen && (
        <div
          className="formula-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setFormulaOpen(false);
          }}
        >
          <aside
            className="formula-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="formula-title"
          >
            <header>
              <div>
                <span className="section-kicker">复合信号公式</span>
                <h2 id="formula-title">公式查看</h2>
              </div>
              <button
                className="icon-button"
                aria-label="关闭公式"
                onClick={() => setFormulaOpen(false)}
              >
                <X size={18} />
              </button>
            </header>
            <div className="formula-drawer__body">
              {(() => {
                // The clicked row's formula; the full list is one click away.
                const focused = formulaFocus
                  ? formulas.filter((formula) => formula.pointKey === formulaFocus)
                  : [];
                const shown = focused.length > 0 ? focused : formulas;
                return (
                  <>
                    {formulaFocus && focused.length === 0 && (
                      <p className="formula-drawer__note">
                        没有找到该行的公式，下面列出全部 {formulas.length} 条。
                      </p>
                    )}
                    {focused.length > 0 && formulas.length > 1 && (
                      <button
                        className="link-button formula-drawer__all"
                        onClick={() => setFormulaFocus(null)}
                      >
                        显示全部 {formulas.length} 条公式
                      </button>
                    )}
                    {shown.map((formula) => (
                      <FormulaCard
                        key={formula.pointKey}
                        formula={formula}
                        preview={browse.mode !== "HISTORY"}
                      />
                    ))}
                  </>
                );
              })()}
            </div>
          </aside>
        </div>
      )}
    </main>
  );
}
