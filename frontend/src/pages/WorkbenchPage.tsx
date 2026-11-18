import { useCallback, useMemo, useRef, type ReactNode } from "react";
import {
  ArrowDown,
  ArrowUp,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Copy,
  Folder,
  GitBranch,
  GitCommitHorizontal,
  Info,
  Layers,
  RefreshCw,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { useBoundGatewayApi } from "../features/api/application-api";
import { DEVICE_UNAVAILABLE_MESSAGE } from "../features/api/authenticated-fetch";
import { useUploadModeState } from "../features/workbench/use-upload-mode";
import { ClosureReason, formatDispositionTime } from "../features/workbench/disposition-display";
import { ConnectionStatusIndicator } from "../features/workbench/ConnectionStatusIndicator";
import { ErrorState, LoadingSkeleton } from "../design-system/components";
import { OperationStatusPanel } from "../features/workbench/OperationStatusPanel";
import { UploadStepCard } from "../features/workbench/UploadStepCard";
import { ArchiveMainlineDialog } from "../features/workbench/ArchiveMainlineDialog";
import { formatWaitDuration } from "../features/workbench/wait-duration";
import {
  HistoryCompareTasks,
  type HistoryCompareTask,
} from "../features/workbench/HistoryCompareTasks";
import { baselineDisplayLabelFor } from "../features/view-model/baseline-labels";
import {
  compareToggle,
  deriveWorkbenchActions,
  hasOnlyInitialBaseline,
  type WorkbenchAction,
  type WorkbenchActionId,
  type WorkspaceTreeRow,
} from "../features/view-model/workspace";
import { WORKSPACE_STATE_COPY } from "../features/view-model/workspace-state-copy";
import {
  DevicePath,
  ReturnToDirectoryLink,
  SessionGate,
} from "../features/session/SessionComponents";
import {
  isGatewaySessionBlocked,
  useGatewaySessionState,
} from "../features/session/handoff-session";
import { useCompareTray } from "./workbench/use-compare-tray";
import { useHistoryCompareRun } from "./workbench/use-history-compare-run";
import { useHistoryTree } from "./workbench/use-history-tree";
import { useSubmitResume } from "./workbench/use-submit-resume";
import { useUploadGate } from "./workbench/use-upload-gate";
import { useWorkbenchData } from "./workbench/use-workbench-data";
import { useWorkbenchPanels } from "./workbench/use-workbench-panels";
import {
  fullTime,
  historyRef,
  pageUrl,
  refKey,
  shortTime,
  statusClass,
  timeTitle,
  type SortColumn,
} from "./workbench/workbench-helpers";

export function WorkbenchPage({
  identityControl,
  headerControl,
}: {
  identityControl?: ReactNode;
  headerControl?: ReactNode;
}) {
  const gatewayApi = useBoundGatewayApi();
  const sessionState = useGatewaySessionState();
  // Upload-mode occupancy (submit/upload gates, step-card reason) is shared
  // with the Preview page through useUploadModeState (B4): a single read
  // sequence for the workspace, review, attempt and operation.
  const uploadMode = useUploadModeState({ enabled: true });
  const workspace = uploadMode.workspace;
  // F1: rendered from the hook snapshot; the page keeps no resume copy.
  const submitResumeNotice = uploadMode.resumeNotice;

  const { resumeSubmitOperationId, setResumeSubmitOperationId } = useSubmitResume(uploadMode);
  const { history, loadError, loading, load, reloadHistory, reloadHead } = useWorkbenchData(
    gatewayApi,
    uploadMode,
    setResumeSubmitOperationId,
  );
  const {
    selectedKey,
    setSelectedKey,
    detailExpanded,
    setDetailExpanded,
    notice,
    setNotice,
    archiveSubmissionId,
    setArchiveSubmissionId,
  } = useWorkbenchPanels();
  const {
    compareState,
    compareError,
    compareNeedsRerun,
    compareConnectionLost,
    historyDrawerCollapsed,
    compareElapsed,
    bundleStatus,
    pairSummaries,
    pairSummaryError,
    operationId,
    historyCompareOperationId,
    compareReplayed,
    showHistoryDrawer,
    showOperationStatus,
    closeHistoryDrawer,
    toggleDrawerCollapsed,
    retryQuery,
    retryDownload,
  } = useHistoryCompareRun(gatewayApi);
  const {
    compareRefs,
    compareIntent,
    compareStartError,
    comparePending,
    comparisonLocked,
    setCompareSelection,
    toggleCompare,
    startOrRetryCompare,
    openCompareOperation,
    jumpToCompare,
  } = useCompareTray(gatewayApi, {
    selectedKey,
    historyCompareOperationId,
    compareState,
    bundleStatus,
  });
  const {
    filter,
    setFilter,
    currentBaselineOnly,
    setCurrentBaselineOnly,
    sort,
    collapsedNodes,
    rows,
    nodeLabel,
    selected,
    comparedKeys,
    visibleRows,
    sortBy,
    toggleCollapse,
  } = useHistoryTree({
    workspace,
    history,
    compareRefs,
    selectedKey,
    setSelectedKey,
  });
  const {
    resumePreviewOperation,
    uploadLocked,
    resumePreviewFromOperation,
    activePreviewOperationId,
    resumeActivePreview,
    handleUploadStateChange,
    handlePreviewResumeFailed,
  } = useUploadGate(gatewayApi, uploadMode, {
    operationId,
    compareRefs,
    selectedKey,
  });

  const searchRef = useRef<HTMLInputElement>(null);

  const resumeSubmitFromOperation = useCallback(
    async (finishedOperationId: string) => {
      const outcome = await uploadMode.resumeAfterOperation(finishedOperationId);
      if (outcome.kind === "submitted") {
        window.location.assign(
          pageUrl(
            "compare",
            { mode: "REVIEW", submissionId: outcome.submissionId, workbenchNode: selectedKey },
            compareRefs,
          ),
        );
        return;
      }
      if (outcome.kind === "aborted" || outcome.kind === "empty") {
        setResumeSubmitOperationId(null);
      }
      await reloadHistory();
    },
    [compareRefs, selectedKey, reloadHistory, uploadMode.resumeAfterOperation],
  );

  // G1 (§6.2 step 2): the notice retry shares the hook entry with the Preview
  // page, so empty pointers still re-read the known attempt ID.
  const retryResumeNotice = useCallback(async () => {
    const outcome = await uploadMode.retryResume();
    if (outcome.kind === "submitted") {
      window.location.assign(
        pageUrl(
          "compare",
          { mode: "REVIEW", submissionId: outcome.submissionId, workbenchNode: selectedKey },
          compareRefs,
        ),
      );
      return;
    }
    if (outcome.kind === "aborted" || outcome.kind === "empty") {
      setResumeSubmitOperationId(null);
    }
    await reloadHistory();
  }, [compareRefs, selectedKey, reloadHistory, uploadMode.retryResume]);

  const actions = useMemo(
    () => deriveWorkbenchActions(selected, comparisonLocked),
    [selected, comparisonLocked],
  );

  const sortIcon = (column: SortColumn) =>
    sort?.column === column ? (
      sort.direction === 1 ? (
        <ArrowUp size={12} />
      ) : (
        <ArrowDown size={12} />
      )
    ) : null;

  const openPreview = (pair?: string) => {
    if (!workspace?.current_preview_result_id) return;
    window.location.assign(
      pageUrl(
        "compare",
        {
          mode: "PREVIEW",
          workspaceId: workspace.workspace_id,
          previewResultId: workspace.current_preview_result_id,
          workbenchNode: selectedKey,
          pair,
        },
        compareRefs,
      ),
    );
  };

  const openReview = (row: WorkspaceTreeRow) => {
    if (!row.refId) return;
    window.location.assign(
      pageUrl(
        "compare",
        { mode: "REVIEW", submissionId: row.refId, workbenchNode: selectedKey },
        compareRefs,
      ),
    );
  };

  // The frozen submission-time Preview result, read through the Submission
  // result endpoints only; it never starts a History compare.
  const openSubmissionResult = (row: WorkspaceTreeRow) => {
    if (!row.refId) return;
    window.location.assign(
      pageUrl(
        "compare",
        { mode: "REVIEW", submissionId: row.refId, readonly: "1", workbenchNode: selectedKey },
        compareRefs,
      ),
    );
  };

  const activeSubmissionRow = workspace?.active_submission_id
    ? (rows.find(
        (row) => row.kind === "submission" && row.refId === workspace.active_submission_id,
      ) ?? null)
    : null;
  const actionLabel = (action: WorkbenchAction) =>
    action.id === "open-submission" && activeSubmissionRow
      ? `转到${activeSubmissionRow.label}`
      : action.label;

  const runAction = (row: WorkspaceTreeRow, id: WorkbenchActionId) => {
    if (comparisonLocked && id === "compare-parent") return;
    if (id === "continue-preview") openPreview("initial_to_modified");
    else if (id === "open-submission") {
      if (activeSubmissionRow) setSelectedKey(activeSubmissionRow.key);
    } else if (id === "view-submission-diff") {
      openSubmissionResult(row);
    } else if (id === "open-review") {
      openReview(row);
    } else if (id === "compare-parent") {
      const currentRef = historyRef(row);
      if (currentRef && row.parentRef) {
        startOrRetryCompare({
          nodes: [{ ref_kind: row.parentRef.ref_kind, ref_id: row.parentRef.ref_id }, currentRef],
        });
      }
    } else if (id === "archive-mainline" && row.kind === "submission" && row.refId) {
      setArchiveSubmissionId(row.refId);
    }
  };

  // B1/B4: the toolbar upload action and the UploadStepCard share the same
  // occupancy gate from the hook; the page no longer keeps its own rule.
  const occupancyReason = uploadMode.gates.upload.enabled
    ? null
    : (uploadMode.gates.upload.reason ?? null);

  if (isGatewaySessionBlocked(sessionState))
    return <SessionGate state={sessionState} identityControl={identityControl} />;
  if (loading)
    return (
      <main className="workspace-page">
        <LoadingSkeleton label="加载工作区与 History" />
      </main>
    );
  if (loadError || !workspace || !history)
    return (
      <main className="workspace-page workspace-page--error">
        <ErrorState
          description={
            loadError?.message === DEVICE_UNAVAILABLE_MESSAGE
              ? DEVICE_UNAVAILABLE_MESSAGE
              : undefined
          }
          code={loadError?.code ?? "WORKSPACE_LOAD_FAILED"}
          title={loadError?.code === "SCOPE_FORBIDDEN" ? "当前身份没有该操作的权限" : undefined}
          details={loadError?.message ?? "工作区加载失败"}
          onRetry={() => void load()}
        />
        <ConnectionStatusIndicator hideConnected />
        {identityControl}
      </main>
    );

  const compareLabels = compareRefs.map(nodeLabel);
  const selectedReviewFacts =
    selected?.kind === "submission" && compareState?.status === "SUCCEEDED"
      ? "审核信息按只读模式加载"
      : null;
  const uploadCard = (
    <UploadStepCard
      head={history.head}
      onReloadHead={reloadHead}
      onUploadStateChange={handleUploadStateChange}
      onReadyChange={() => undefined}
      occupancyReason={occupancyReason}
      onComplete={(workspaceId, previewResultId) =>
        window.location.assign(
          pageUrl(
            "compare",
            { mode: "PREVIEW", workspaceId, previewResultId, workbenchNode: selectedKey },
            compareRefs,
          ),
        )
      }
    />
  );
  return (
    <main
      className={`workspace-page${detailExpanded ? " details-open" : " details-collapsed"}${uploadLocked ? " workspace-page--uploading" : ""}`}
    >
      {activePreviewOperationId && (
        <div role="status" className="info-note workspace-notice">
          <Info size={16} aria-hidden="true" />
          <span>该工作区有进行中的预览（可能由其他标签页或终端发起）。</span>
          <button
            className="link-button"
            onClick={() => resumeActivePreview(activePreviewOperationId)}
          >
            查看进度并接回
          </button>
        </div>
      )}
      {notice === "withdrawn" && (
        <div role="status" className="form-success workspace-notice">
          <span>已撤回，可以重新上传</span>
          <button className="link-button" onClick={() => setNotice(null)}>
            关闭
          </button>
        </div>
      )}
      {submitResumeNotice && (
        <div role="alert" className="form-error workspace-notice">
          <span>{submitResumeNotice.title}</span>
          {submitResumeNotice.code && (
            <span>
              {submitResumeNotice.codeLabel ?? "操作ID"}：<code>{submitResumeNotice.code}</code>
              <button
                className="link-button"
                onClick={() => void navigator.clipboard?.writeText(submitResumeNotice.code ?? "")}
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
      {uploadLocked && (
        <div className="page-lock-overlay" role="presentation" {...({ inert: "" } as object)}>
          <p>上传与预览执行中，页面其余操作已锁定</p>
        </div>
      )}
      <header className="workspace-topbar" {...(uploadLocked ? ({ inert: "" } as object) : {})}>
        <div
          className={`workspace-brand${sessionState.kind === "handoff" ? " workspace-brand--device" : ""}`}
        >
          <strong>网关数据工作台</strong>
          {sessionState.kind === "handoff" ? (
            <DevicePath display={sessionState.session.display} />
          ) : (
            <span>{workspace.gateway_device_external_key}</span>
          )}
        </div>
        <div className="workspace-topbar__right">
          {(showHistoryDrawer || showOperationStatus) && (
            <span className="task-indicator">
              <RefreshCw size={13} />
              {showHistoryDrawer ? "历史比较" : "操作状态"}
            </span>
          )}
          <HistoryCompareTasks
            api={gatewayApi}
            currentOperationId={historyCompareOperationId}
            labelFor={nodeLabel}
            onOpen={(task: HistoryCompareTask) =>
              openCompareOperation(task.operation_id, task.nodes)
            }
          />
          {headerControl}
          <ConnectionStatusIndicator />
          {identityControl}
          {sessionState.kind === "handoff" && (
            <>
              <span className="topbar-divider" aria-hidden="true" />
              <ReturnToDirectoryLink href={sessionState.session.returnUrl} />
            </>
          )}
        </div>
      </header>
      <div className="workspace-layout" {...(uploadLocked ? ({ inert: "" } as object) : {})}>
        <section className="workspace-main" aria-label="组态树工作台">
          <div className="workspace-tree-heading">
            <h1>组态树</h1>
            <label className="workspace-search">
              <Search size={15} />
              <input
                ref={searchRef}
                aria-label="搜索工作区与 History 节点"
                placeholder="搜索节点"
                value={filter}
                onChange={(event) => setFilter(event.currentTarget.value)}
              />
            </label>
            <span className="workspace-tree-heading__spacer" />
            <label className="workspace-checkbox">
              <input
                type="checkbox"
                checked={currentBaselineOnly}
                onChange={(event) => setCurrentBaselineOnly(event.currentTarget.checked)}
              />
              只显示当前基线
            </label>
          </div>
          {showOperationStatus &&
            operationId !== null &&
            !(uploadLocked && !resumePreviewOperation) && (
              <OperationStatusPanel
                operationId={operationId}
                onSucceeded={
                  resumePreviewOperation
                    ? (id) => void resumePreviewFromOperation(id)
                    : resumeSubmitOperationId === operationId
                      ? (id) => void resumeSubmitFromOperation(id)
                      : undefined
                }
                onFailed={
                  resumePreviewOperation
                    ? handlePreviewResumeFailed
                    : resumeSubmitOperationId === operationId
                      ? (id) => void resumeSubmitFromOperation(id)
                      : undefined
                }
              />
            )}
          <div className="workspace-table-scroll">
            <table className="workspace-table" aria-label="History 组态树">
              <colgroup>
                <col className="workspace-table__compare-col" />
                <col />
                <col className="workspace-table__time-col" />
              </colgroup>
              <thead>
                <tr>
                  <th
                    scope="col"
                    className="workspace-table__compare"
                    title="勾选 2–3 个基线或提交节点，在下方比较托盘发起历史比较"
                  >
                    比较
                  </th>
                  <th scope="col">
                    <button onClick={() => sortBy("label")}>节点{sortIcon("label")}</button>
                  </th>
                  <th scope="col">
                    <button onClick={() => sortBy("time")}>时间{sortIcon("time")}</button>
                  </th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row) => {
                  const compared = comparedKeys.has(row.key);
                  const toggle = compareToggle(row, compareRefs.length, compared, comparisonLocked);
                  // With the panel collapsed, the selected or hovered row carries the node actions.
                  const rowActions = detailExpanded
                    ? []
                    : deriveWorkbenchActions(row, comparisonLocked);
                  return (
                    <tr
                      key={row.key}
                      className={selectedKey === row.key ? "is-selected" : ""}
                      aria-selected={selectedKey === row.key}
                      onClick={() => setSelectedKey(row.key)}
                    >
                      <td className="workspace-table__compare">
                        {toggle.available && (
                          <label
                            title={toggle.reason ?? (compared ? "移出比较" : "加入比较")}
                            onClick={(event) => event.stopPropagation()}
                          >
                            <input
                              type="checkbox"
                              aria-label={`${compared ? "移出比较" : "加入比较"}：${row.label}`}
                              checked={compared}
                              disabled={!toggle.enabled}
                              onChange={() => toggleCompare(row)}
                            />
                          </label>
                        )}
                      </td>
                      <td>
                        <div
                          className="workspace-tree-cell"
                          style={{ paddingLeft: 4 + row.depth * 24 }}
                        >
                          {row.hasChildren ? (
                            <button
                              className="workspace-tree-toggle"
                              aria-label={`${collapsedNodes.has(row.key) ? "展开" : "折叠"}${row.label}`}
                              aria-expanded={!collapsedNodes.has(row.key)}
                              onClick={(event) => {
                                event.stopPropagation();
                                toggleCollapse(row.key);
                              }}
                            >
                              {collapsedNodes.has(row.key) ? (
                                <ChevronRight size={14} />
                              ) : (
                                <ChevronDown size={14} />
                              )}
                            </button>
                          ) : (
                            <span className="workspace-tree-toggle-placeholder" />
                          )}
                          {row.kind === "baseline" ? (
                            <Layers size={16} />
                          ) : row.kind === "workspace" ? (
                            <Folder size={16} />
                          ) : row.kind === "migration" ? (
                            <GitBranch size={16} />
                          ) : (
                            <GitCommitHorizontal size={16} />
                          )}
                          <button
                            className="workspace-node-label"
                            onClick={() => setSelectedKey(row.key)}
                          >
                            {row.label}
                          </button>
                          {row.status && (
                            <span
                              className={statusClass(row.statusTone)}
                              title={
                                row.submissionDisposition === "CLOSED_NOT_ARCHIVED" &&
                                row.closure?.reason
                                  ? "有理由关闭，详情见右侧面板"
                                  : undefined
                              }
                            >
                              <i aria-hidden="true" />
                              {row.status}
                            </span>
                          )}
                          {row.compareOrder && (
                            <span className="compare-order" title={`比较节点 ${row.compareOrder}`}>
                              比较 {row.compareOrder}
                            </span>
                          )}
                          {row.eligibilityNote && !row.submissionDisposition && (
                            <span
                              className="status-tag status-tag--warning"
                              title="该提交所基于的基线已不是当前基线"
                            >
                              基线已更新
                            </span>
                          )}
                          {row.identityException && (
                            <span className="status-tag status-tag--neutral" title="项目身份例外">
                              项目身份例外
                            </span>
                          )}
                          {rowActions.length > 0 && (
                            <span className="workspace-row-actions">
                              {rowActions.map((action) => (
                                <button
                                  key={action.id}
                                  className="button button--secondary"
                                  disabled={!action.enabled}
                                  title={action.reason ?? undefined}
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    runAction(row, action.id);
                                  }}
                                >
                                  {actionLabel(action)}
                                </button>
                              ))}
                            </span>
                          )}
                        </div>
                      </td>
                      <td
                        className="workspace-table__time"
                        title={
                          row.time
                            ? `${timeTitle(row)}：${new Date(row.time).toLocaleString("zh-CN", { hour12: false })}`
                            : undefined
                        }
                      >
                        {shortTime(row.time)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {hasOnlyInitialBaseline(history) && (
              <div className="tree-empty-note">
                <div className="info-note" role="status">
                  <Info size={16} aria-hidden="true" />
                  <div>
                    <strong>尚无数据</strong>
                    <span>该设备只有初始基线。选择组态目录并上传后，即可提交第一次组态。</span>
                  </div>
                </div>
              </div>
            )}
          </div>
          <div className="compare-tray" aria-label="比较托盘">
            <div className="compare-tray__label">
              <GitBranch size={17} />
              <strong>比较托盘</strong>
              {compareRefs.length > 0 && <span>{compareRefs.length} / 3</span>}
              {compareLabels.length === 0 && <small>勾选 2–3 个基线或提交节点</small>}
            </div>
            <div className="compare-tray__items">
              {compareRefs.map((node, index) => (
                <div className="compare-chip" key={refKey(node)}>
                  <span>{index + 1}</span>
                  {compareLabels[index]}
                  <button
                    aria-label={`移除${compareLabels[index]}`}
                    disabled={comparisonLocked}
                    onClick={() =>
                      setCompareSelection(
                        compareRefs.filter((item) => refKey(item) !== refKey(node)),
                      )
                    }
                  >
                    <X size={13} />
                  </button>
                </div>
              ))}
            </div>
            <div className="compare-tray__actions">
              <button
                className="button button--ghost"
                disabled={!compareRefs.length || comparisonLocked}
                onClick={() => setCompareSelection([])}
              >
                <Trash2 size={14} />
                清空比较
              </button>
              {compareStartError && (
                <span role="alert" className="compare-tray__error" title={compareStartError.code}>
                  {compareStartError.message}（{compareStartError.code}）
                  <button
                    className="icon-button"
                    aria-label="复制比较错误详情"
                    onClick={() =>
                      void navigator.clipboard?.writeText(
                        `${compareStartError.code}\n${compareStartError.message}`,
                      )
                    }
                  >
                    <Copy size={13} />
                  </button>
                  {compareStartError.operationIds.length > 0 && (
                    <span className="compare-tray__jump">
                      {compareStartError.operationIds.map((id, index) => (
                        <button
                          key={id}
                          className="link-button"
                          title={id}
                          onClick={() => void jumpToCompare(id)}
                        >
                          查看已有比较
                          {compareStartError.operationIds.length > 1 ? ` ${index + 1}` : ""}
                        </button>
                      ))}
                    </span>
                  )}
                </span>
              )}
              {compareIntent && compareStartError?.retry === "same" ? (
                <button
                  className="button button--primary"
                  disabled={comparePending || comparisonLocked}
                  onClick={() => startOrRetryCompare(compareIntent.request)}
                >
                  <RefreshCw size={14} />
                  重试发起比较
                </button>
              ) : (
                <button
                  className="button button--primary"
                  disabled={compareRefs.length < 2 || comparisonLocked}
                  onClick={() => startOrRetryCompare(undefined, compareStartError?.retry === "new")}
                >
                  {comparisonLocked ? <RefreshCw size={14} /> : null}
                  {comparisonLocked
                    ? compareState === null || compareState.status === "SUCCEEDED"
                      ? "读取中"
                      : "比较中"
                    : compareStartError?.retry === "new"
                      ? "重新发起比较"
                      : "历史比较"}
                </button>
              )}
              {compareRefs.length < 2 && <small>至少选择 2 个节点</small>}
            </div>
          </div>
          {showHistoryDrawer && (
            <section className="history-result-drawer" aria-label="历史比较结果抽屉">
              <div className="history-result-drawer__heading">
                <div>
                  <GitBranch size={16} />
                  <strong>历史比较</strong>
                  <span
                    className={`status-tag status-tag--${compareState?.status === "SUCCEEDED" ? "success" : compareState?.status === "FAILED" ? "warning" : "info"}`}
                  >
                    {compareConnectionLost
                      ? "连接中断"
                      : compareState?.status === "QUEUED"
                        ? "排队中"
                        : compareState?.status === "RUNNING"
                          ? "执行中"
                          : compareState?.status === "SUCCEEDED"
                            ? "已完成"
                            : compareState?.status === "FAILED"
                              ? "失败"
                              : compareState?.status === "CANCELLED"
                                ? "已取消"
                                : "读取结果中"}
                  </span>
                  {(compareState?.status === "QUEUED" || compareState?.status === "RUNNING") && (
                    <small>已等待 {formatWaitDuration(compareElapsed)}</small>
                  )}
                  {compareReplayed && (
                    <small title="相同节点与规则的比较已存在，接回了原比较（同一结果与 bundle）">
                      已接回已有比较
                    </small>
                  )}
                </div>
                <div className="history-result-drawer__buttons">
                  {compareConnectionLost && (
                    <button className="button button--secondary" onClick={retryQuery}>
                      <RefreshCw size={14} />
                      重试查询
                    </button>
                  )}
                  {bundleStatus === "failed" && !compareNeedsRerun && (
                    <button className="button button--secondary" onClick={retryDownload}>
                      <RefreshCw size={14} />
                      重试下载
                    </button>
                  )}
                  {compareNeedsRerun && compareRefs.length >= 2 && (
                    <button
                      className="button button--secondary"
                      disabled={comparePending}
                      title="用新的请求重新比较这些节点（当前规则）"
                      onClick={() => startOrRetryCompare({ nodes: compareRefs }, true)}
                    >
                      <RefreshCw size={14} />
                      重新比较
                    </button>
                  )}
                  {bundleStatus === "ready" && (
                    <button
                      className="button button--primary"
                      onClick={() =>
                        window.location.assign(
                          pageUrl(
                            "compare",
                            {
                              mode: "HISTORY",
                              operationId: historyCompareOperationId,
                              operationKind: "history-compare",
                              workbenchNode: selectedKey,
                            },
                            compareRefs,
                          ),
                        )
                      }
                    >
                      打开差异工作台
                    </button>
                  )}
                  <button
                    className="icon-button"
                    aria-label={historyDrawerCollapsed ? "展开历史比较结果" : "收起历史比较结果"}
                    aria-expanded={!historyDrawerCollapsed}
                    title={historyDrawerCollapsed ? "展开" : "收起"}
                    onClick={toggleDrawerCollapsed}
                  >
                    {historyDrawerCollapsed ? <ChevronUp size={17} /> : <ChevronDown size={17} />}
                  </button>
                  {!comparisonLocked && (
                    <button
                      className="icon-button"
                      aria-label="关闭历史比较结果"
                      title="关闭"
                      onClick={closeHistoryDrawer}
                    >
                      <X size={17} />
                    </button>
                  )}
                </div>
              </div>
              {!historyDrawerCollapsed && compareError && (
                <p role="alert" className="history-result-drawer__error">
                  {compareError}
                </p>
              )}
              {!historyDrawerCollapsed && compareState?.status === "SUCCEEDED" && (
                <div className="history-result-drawer__body">
                  <div className="history-result-drawer__nodes">
                    {compareRefs.map((node, index) => (
                      <article key={refKey(node)}>
                        <span>{index + 1}</span>
                        <div>
                          <strong>
                            {rows.find((row) => row.key === refKey(node))?.label ?? node.ref_id}
                          </strong>
                          <small>{node.ref_kind === "baseline_node" ? "基线" : "提交"}</small>
                        </div>
                        <Check size={15} />
                      </article>
                    ))}
                  </div>
                  <div className="history-result-drawer__pairs">
                    {compareState.result?.pairs.map((pair, index) => {
                      const summary = pairSummaries[pair.pair_id];
                      return (
                        <div key={pair.pair_id} className="history-pair-summary">
                          <span>比较对 {index + 1}</span>
                          <strong title={pair.pair_id}>
                            节点 {index + 1} → 节点 {index + 2}
                          </strong>
                          <small>{pair.record_count} 条差异记录</small>
                          {summary && (
                            <div className="history-pair-summary__counts">
                              <span>表 {summary.tableCount}</span>
                              <span>变更 {summary.changedTableCount}</span>
                              <span className={summary.degradedTableCount > 0 ? "is-warning" : ""}>
                                降级 {summary.degradedTableCount}
                              </span>
                            </div>
                          )}
                          {summary && summary.tables.length > 0 && (
                            <details className="history-pair-summary__tables">
                              <summary>每张表的新增 / 删除 / 修改行数</summary>
                              <table>
                                <thead>
                                  <tr>
                                    <th>表</th>
                                    <th>新增</th>
                                    <th>删除</th>
                                    <th>修改</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {summary.tables.map((table) => (
                                    <tr key={table.tableName}>
                                      <td title={table.tableName}>{table.displayName}</td>
                                      <td>+{table.added}</td>
                                      <td>−{table.deleted}</td>
                                      <td>~{table.modified}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </details>
                          )}
                          {!summary && bundleStatus === "ready" && (
                            <small>正在读取本地 bundle 中的比较事实…</small>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  {pairSummaryError && (
                    <p role="alert" className="history-result-drawer__error">
                      无法读取本地比较事实：{pairSummaryError}
                    </p>
                  )}
                  <p>
                    {bundleStatus === "downloading" || bundleStatus === "idle"
                      ? "下载中：正在校验 bundle。"
                      : bundleStatus === "ready"
                        ? "已就绪：bundle 已下载并校验。"
                        : "下载失败，可重试。"}
                  </p>
                </div>
              )}
            </section>
          )}
        </section>
        <aside className="workspace-details" aria-label="详情面板">
          <button
            className="workspace-details__toggle"
            aria-label={detailExpanded ? "折叠详情面板" : "展开详情面板"}
            onClick={() => setDetailExpanded((value) => !value)}
          >
            {detailExpanded ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
          {detailExpanded ? (
            <div className="workspace-details__content">
              <div className="workspace-details__header">
                <p className="eyebrow">
                  {selected?.kind === "workspace"
                    ? "工作区详情"
                    : selected?.kind === "submission"
                      ? "提交详情"
                      : "历史节点详情"}
                </p>
                <h2>{selected?.label ?? "未选择节点"}</h2>
                <div className="workspace-details__tags">
                  <span
                    className={
                      selected
                        ? statusClass(selected.statusTone)
                        : "tree-status tree-status--neutral"
                    }
                  >
                    <i aria-hidden="true" />
                    {selected?.status || "—"}
                  </span>
                  {selected?.eligibilityNote && !selected?.submissionDisposition && (
                    <span className="status-tag status-tag--warning">基线已更新</span>
                  )}
                  {selected?.identityException && (
                    <span className="status-tag status-tag--neutral">项目身份例外</span>
                  )}
                </div>
                {actions.length > 0 && (
                  <div className="workspace-details__actions">
                    {actions.map((action) => (
                      <div className="workspace-details__action-item" key={action.id}>
                        <button
                          className={`button ${action.id === "archive-mainline" || action.id === "continue-preview" ? "button--primary" : "button--secondary"}`}
                          disabled={!action.enabled}
                          title={action.reason ?? undefined}
                          onClick={() => {
                            if (selected) runAction(selected, action.id);
                          }}
                        >
                          {actionLabel(action)}
                        </button>
                        {!action.enabled && action.reason && (
                          <small className="disabled-reason">{action.reason}</small>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              {selected?.kind === "workspace" && (
                <>
                  {workspace.state === "CLOSED" ? (
                    <p className="workspace-state-note">工作区已关闭，不能上传。</p>
                  ) : workspace.active_submission_id ? (
                    // The Preview now belongs to the submission: its diff is opened from that node.
                    <p className="workspace-state-note">
                      本次上传已提交为{activeSubmissionRow?.label ?? "提交"}。差异请在该提交上查看。
                      {occupancyReason && ` ${occupancyReason}。`}
                    </p>
                  ) : workspace.current_preview_result_id ? (
                    <>
                      <p className="workspace-state-note">
                        {workspace.active_submit_attempt_id
                          ? "提交正在处理，完成后会出现在组态树中。"
                          : "本次上传已生成预览，尚未提交。在预览中确认差异后提交。"}
                      </p>
                      <details className="workspace-reupload">
                        <summary>重新上传（替换当前预览）</summary>
                        {uploadCard}
                      </details>
                    </>
                  ) : (
                    uploadCard
                  )}
                  <details className="details-tech">
                    <summary>技术信息</summary>
                    <dl className="details-list">
                      <div>
                        <dt>网关设备</dt>
                        <dd>{workspace.gateway_device_external_key}</dd>
                      </div>
                      <div>
                        <dt>业务项目</dt>
                        <dd>{workspace.business_project_id}</dd>
                      </div>
                      <div>
                        <dt>工作区状态</dt>
                        <dd>
                          {WORKSPACE_STATE_COPY[
                            workspace.state as keyof typeof WORKSPACE_STATE_COPY
                          ] ?? "状态未知"}
                        </dd>
                      </div>
                      <div>
                        <dt>组态代次</dt>
                        <dd>{workspace.generation}</dd>
                      </div>
                      <div>
                        <dt>当前 Preview</dt>
                        <dd>{workspace.current_preview_result_id ?? "—"}</dd>
                      </div>
                      {workspace.active_submission_id && (
                        <div>
                          <dt>待审核提交</dt>
                          <dd>{workspace.active_submission_id}</dd>
                        </div>
                      )}
                    </dl>
                  </details>
                </>
              )}
              {selected?.kind !== "workspace" && selected && (
                <DispositionDetails selected={selected} />
              )}
              {selectedReviewFacts && <p className="subtle-copy">{selectedReviewFacts}</p>}
            </div>
          ) : (
            <div className="workspace-details__collapsed">
              <span>详情</span>
            </div>
          )}
        </aside>
      </div>
      <ArchiveMainlineDialog
        open={archiveSubmissionId !== null}
        submissionId={archiveSubmissionId}
        onClose={() => setArchiveSubmissionId(null)}
        onArchived={() => window.location.assign(pageUrl("workspace", {}, compareRefs))}
        resolveName={(id) =>
          rows.find((row) => row.kind === "submission" && row.refId === id)?.label ?? null
        }
        resolveBaselineLabel={(nodeId) =>
          history ? baselineDisplayLabelFor(history, nodeId) : null
        }
        onSelectSubmission={(id) => setSelectedKey(`submission:${id}`)}
        onDispositionChanged={() => void reloadHistory()}
      />
    </main>
  );
}

function DispositionDetails({ selected }: { selected: WorkspaceTreeRow }) {
  return (
    <dl className="details-list">
      <div>
        <dt>节点类型</dt>
        <dd>
          {selected.kind === "baseline"
            ? selected.baselineKind === "INITIAL"
              ? "初始基线"
              : "归档基线"
            : selected.kind === "submission"
              ? "提交"
              : "规则迁移"}
        </dd>
      </div>
      <div>
        <dt>审核状态</dt>
        <dd>{selected.submissionDisposition ? "已通过" : selected.status || "—"}</dd>
      </div>
      {selected.submissionDisposition && (
        <div className="details-list__long">
          <dt>终局处置</dt>
          <dd>
            {selected.submissionDisposition === "ARCHIVED_BASELINE"
              ? selected.dispositionBaselineLabel
                ? `已归档，成为${selected.dispositionBaselineLabel}`
                : "已归档"
              : "已关闭（未归档）"}
          </dd>
        </div>
      )}
      {selected.submissionDisposition === "CLOSED_NOT_ARCHIVED" &&
        selected.dispositionSourceKind === "ARCHIVE" && (
          <div className="details-list__long">
            <dt>原因</dt>
            <dd>归档时选中了其他提交</dd>
          </div>
        )}
      {selected.closure && (
        <>
          <div>
            <dt>关闭人</dt>
            <dd>{selected.closure.closed_by}</dd>
          </div>
          <div>
            <dt>关闭时间</dt>
            <dd title={selected.closure.closed_at}>
              {formatDispositionTime(selected.closure.closed_at)}
            </dd>
          </div>
          <div className="details-list__long">
            <dt>关闭理由</dt>
            <dd>
              <ClosureReason reason={selected.closure.reason} />
            </dd>
          </div>
        </>
      )}
      <div>
        <dt>节点 ID</dt>
        <dd>{selected.refId}</dd>
      </div>
      {selected.submitAt ? (
        <div>
          <dt>提交时间</dt>
          <dd title={selected.submitAt}>{fullTime(selected.submitAt)}</dd>
        </div>
      ) : (
        <div>
          <dt>创建时间</dt>
          <dd title={selected.createdAt ?? undefined}>{fullTime(selected.createdAt)}</dd>
        </div>
      )}
      {selected.eligibilityNote && !selected.submissionDisposition && (
        <div className="details-list__long">
          <dt>基线说明</dt>
          <dd>
            <details>
              <summary>展开说明</summary>该提交所基于的基线已不是当前基线
            </details>
          </dd>
        </div>
      )}
      {selected.identityException && (
        <div>
          <dt>身份说明</dt>
          <dd>项目身份例外</dd>
        </div>
      )}
    </dl>
  );
}
