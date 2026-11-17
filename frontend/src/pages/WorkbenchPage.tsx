import { scopedStorage } from "../features/api/scoped-storage";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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
import type { components } from "../features/api/generated/openapi";
import { useBoundGatewayApi } from "../features/api/application-api";
import {
  readHistoryCompareIntent,
  requestWithTimeout,
  resolveHistoryCompareIntent,
  type IdempotentIntent,
} from "../features/api/idempotency";
import { ApiError, DEVICE_UNAVAILABLE_MESSAGE } from "../features/api/authenticated-fetch";
import { bundleErrorTitle } from "../features/bundle/local-bundle";
import { reportConnectionStatus } from "../features/api/connection-status";
import { PollingConnectionLostError, pollHistoryCompare } from "../features/api/journeys";
import {
  currentGatewaySession,
  SessionChangedError,
  historyCompareRequestTimeoutMs,
} from "../features/api/session";
import { getUrlOperationJobKind, useUploadModeState } from "../features/workbench/use-upload-mode";
import { ClosureReason, formatDispositionTime } from "../features/workbench/disposition-display";
import {
  ensureLocalBundle,
  OpfsBundleStore,
  type InstalledBundle,
} from "../features/bundle/local-bundle";
import { ConnectionStatusIndicator } from "../features/workbench/ConnectionStatusIndicator";
import { ErrorState, LoadingSkeleton } from "../design-system/components";
import { OperationStatusPanel } from "../features/workbench/OperationStatusPanel";
import { UploadStepCard } from "../features/workbench/UploadStepCard";
import { ArchiveMainlineDialog } from "../features/workbench/ArchiveMainlineDialog";
import { formatWaitDuration } from "../features/workbench/wait-duration";
import {
  summarizeHistoryPair,
  type HistoryPairSummary,
} from "../features/workbench/history-summary";
import {
  describeHistoryReadError,
  describeHistoryStartError,
  type HistoryCompareFailure,
} from "../features/workbench/history-compare-errors";
import {
  HistoryCompareTasks,
  type HistoryCompareTask,
} from "../features/workbench/HistoryCompareTasks";
import { baselineDisplayLabelFor } from "../features/view-model/baseline-labels";
import {
  buildWorkspaceTree,
  compareToggle,
  deriveWorkbenchActions,
  hasOnlyInitialBaseline,
  sortWorkspaceTreeRows,
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

type Schemas = components["schemas"];
type SortColumn = "label" | "time";

function shortTime(iso: string | null): string {
  return iso
    ? new Date(iso).toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      })
    : "—";
}

function timeTitle(row: WorkspaceTreeRow): string {
  return row.kind === "workspace"
    ? "工作区最近更新时间"
    : row.kind === "submission"
      ? "提交时间"
      : "创建时间";
}

function refKey(ref: Schemas["HistoryCompareNodeRequest"]): string {
  return `${ref.ref_kind}:${ref.ref_id}`;
}

function historyRef(row: WorkspaceTreeRow): Schemas["HistoryCompareNodeRequest"] | null {
  return row.refId && row.refKind ? { ref_kind: row.refKind, ref_id: row.refId } : null;
}

function pageUrl(
  page: "workspace" | "compare",
  extra: Record<string, string | null | undefined> = {},
  compareNodes: Schemas["HistoryCompareNodeRequest"][] = [],
): string {
  const params = new URLSearchParams({ page });
  for (const [key, value] of Object.entries(extra)) if (value) params.set(key, value);
  for (const node of compareNodes) params.append("compare", refKey(node));
  return `/?${params.toString()}`;
}

function isTemporaryError(cause: unknown): boolean {
  return (
    cause instanceof TypeError ||
    (cause instanceof DOMException && cause.name === "TimeoutError") ||
    (cause instanceof ApiError && (cause.status === 429 || cause.status >= 500))
  );
}

function messageFrom(cause: unknown): { code: string; message: string } {
  if (cause instanceof ApiError)
    return { code: cause.code ?? `HTTP_${cause.status}`, message: cause.message };
  return {
    code: cause instanceof Error ? cause.name : "REQUEST_FAILED",
    message: cause instanceof Error ? cause.message : String(cause),
  };
}

function statusClass(tone: WorkspaceTreeRow["statusTone"]): string {
  return `tree-status tree-status--${tone}`;
}

function showOperationForCompare(
  operationId: string | null,
  state: Schemas["HistoryCompareResultResponse"] | null,
): boolean {
  return Boolean(
    operationId && (!state || state.status === "QUEUED" || state.status === "RUNNING"),
  );
}

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
  const [history, setHistory] = useState<Schemas["HistoryListResponse"] | null>(null);
  const [loadError, setLoadError] = useState<{ code: string; message: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [currentBaselineOnly, setCurrentBaselineOnly] = useState(false);
  const [selectedKey, setSelectedKey] = useState("");
  // The panel carries the node actions, so it starts open on normal widths.
  const [detailExpanded, setDetailExpanded] = useState(() => window.innerWidth > 1100);
  const [compareRefs, setCompareRefs] = useState<Schemas["HistoryCompareNodeRequest"][]>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.getAll("compare").flatMap((raw) => {
      const split = raw.indexOf(":");
      if (split < 0) return [];
      const kind = raw.slice(0, split);
      return kind === "baseline_node" || kind === "submission"
        ? [{ ref_kind: kind, ref_id: raw.slice(split + 1) }]
        : [];
    });
  });
  const [sort, setSort] = useState<{ column: SortColumn; direction: 1 | -1 } | null>(null);
  const [collapsedNodes, setCollapsedNodes] = useState<Set<string>>(() => new Set());
  const [compareIntent, setCompareIntent] = useState<IdempotentIntent<
    Schemas["HistoryCompareAcceptRequest"]
  > | null>(() => {
    try {
      return readHistoryCompareIntent(
        scopedStorage.getItem("gateway-history-compare-pending-intent"),
      );
    } catch {
      return null;
    }
  });
  const [compareStartError, setCompareStartError] = useState<HistoryCompareFailure | null>(() =>
    compareIntent
      ? {
          code: "REQUEST_UNCONFIRMED",
          message: "上次请求结果尚未确认，可使用同一请求重试。",
          retry: "same",
          operationIds: [],
        }
      : null,
  );
  const [comparePending, setComparePending] = useState(false);
  const [compareState, setCompareState] = useState<Schemas["HistoryCompareResultResponse"] | null>(
    null,
  );
  const [compareError, setCompareError] = useState<string | null>(null);
  // Set when only a new request (new idempotency key) can produce a usable result.
  const [compareNeedsRerun, setCompareNeedsRerun] = useState(false);
  const [compareConnectionLost, setCompareConnectionLost] = useState(false);
  const [refreshCompare, setRefreshCompare] = useState(0);
  const [historyDrawerCollapsed, setHistoryDrawerCollapsed] = useState(false);
  // Bumped after the URL changes in place, so the URL-derived operation ID is read again.
  const [, setUrlRevision] = useState(0);
  const [compareElapsed, setCompareElapsed] = useState(0);
  const [bundleStatus, setBundleStatus] = useState<"idle" | "downloading" | "ready" | "failed">(
    "idle",
  );
  const [downloadRevision, setDownloadRevision] = useState(0);
  const [historyBundle, setHistoryBundle] = useState<InstalledBundle | null>(null);
  const [pairSummaries, setPairSummaries] = useState<Record<string, HistoryPairSummary>>({});
  const [pairSummaryError, setPairSummaryError] = useState<string | null>(null);
  const [resumePreviewOperation] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get("operationId");
    return Boolean(
      id &&
      params.get("operationKind") !== "history-compare" &&
      scopedStorage.getItem("gateway-preview-operation") === id,
    );
  });
  const [resumeSubmitOperationId, setResumeSubmitOperationId] = useState<string | null>(null);
  // F1: rendered from the hook snapshot; the page keeps no resume copy.
  const submitResumeNotice = uploadMode.resumeNotice;
  const [notice, setNotice] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).get("notice"),
  );
  const resumePending = useRef(resumePreviewOperation);
  const [uploadLocked, setUploadLocked] = useState(resumePreviewOperation);
  const [archiveSubmissionId, setArchiveSubmissionId] = useState<string | null>(null);
  const operationId = new URLSearchParams(window.location.search).get("operationId");
  const operationKind = new URLSearchParams(window.location.search).get("operationKind");
  const historyCompareOperationId = operationKind === "history-compare" ? operationId : null;
  const compareReplayed =
    Boolean(historyCompareOperationId) &&
    new URLSearchParams(window.location.search).get("replayed") === "1";
  const pendingIntentKey = "gateway-history-compare-pending-intent";
  const searchRef = useRef<HTMLInputElement>(null);

  const resumePreviewFromOperation = useCallback(
    async (finishedOperationId: string) => {
      if (scopedStorage.getItem("gateway-preview-operation") !== finishedOperationId) return;
      const session = currentGatewaySession();
      try {
        const workspace = await gatewayApi.createWorkspace({
          business_project_id: session.businessProjectId,
          gateway_device_external_key: session.gatewayDeviceExternalKey,
        });
        const previewResultId = workspace.current_preview_result_id;
        if (!previewResultId) {
          setUploadLocked(false);
          return;
        }
        const preview = await gatewayApi.getPreviewResult(workspace.workspace_id, previewResultId);
        await ensureLocalBundle({
          store: new OpfsBundleStore(),
          expectedBundleDigest: preview.bundle_digest,
          fetchBundle: () => gatewayApi.getPreviewBundle(workspace.workspace_id, previewResultId),
        });
        gatewayApi.assertSession?.();
        resumePending.current = false;
        scopedStorage.removeItem("gateway-preview-operation");
        window.location.assign(
          pageUrl(
            "compare",
            {
              mode: "PREVIEW",
              workspaceId: workspace.workspace_id,
              previewResultId,
              workbenchNode: selectedKey,
            },
            compareRefs,
          ),
        );
      } catch (cause) {
        if (cause instanceof SessionChangedError) return;
        try {
          gatewayApi.assertSession?.();
        } catch {
          return;
        }
        resumePending.current = false;
        scopedStorage.removeItem("gateway-preview-operation");
        setUploadLocked(false);
      }
    },
    [compareRefs, selectedKey],
  );

  const reloadHistory = useCallback(async (): Promise<Schemas["HistoryListResponse"] | null> => {
    try {
      const loaded = await gatewayApi.listHistory();
      setHistory(loaded);
      return loaded;
    } catch {
      return null;
    }
  }, []);

  const load = useCallback(async () => {
    const session = currentGatewaySession();
    if (!session.businessProjectId || !session.gatewayDeviceExternalKey) {
      setLoadError({ code: "SESSION_REQUIRED", message: "当前会话没有业务项目与网关设备身份" });
      setHistory(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setLoadError(null);
    try {
      const snapshot = await uploadMode.refresh();
      if (!snapshot.workspace || snapshot.workspaceError) {
        // The shared refresh keeps stale state on failure; the page-level
        // load still reports it as a load error (as before B4).
        setLoadError(
          snapshot.workspaceError ?? { code: "WORKSPACE_LOAD_FAILED", message: "工作区加载失败" },
        );
        setHistory(null);
        return;
      }
      const loadedHistory = await gatewayApi.listHistory();
      setHistory(loadedHistory);
      const loadedAttempt = snapshot.attempt;
      if (snapshot.workspace.active_submit_attempt_id && loadedAttempt?.operation_id) {
        const url = new URL(window.location.href);
        const urlOperationId = url.searchParams.get("operationId");
        if (urlOperationId !== loadedAttempt.operation_id) {
          // §6.2: only a submit operation in the URL loses to the pointer;
          // a preview operation belongs to the preview flow (job_kind).
          const jobKind = urlOperationId
            ? await getUrlOperationJobKind(gatewayApi, urlOperationId)
            : null;
          if (!urlOperationId || jobKind === "backend-vnext/submit") {
            url.searchParams.set("operationId", loadedAttempt.operation_id);
            url.searchParams.set("operationKind", "operation");
            window.history.replaceState(null, "", url);
          }
        }
      } else {
        setResumeSubmitOperationId(null);
      }
      setLoadError(null);
    } catch (cause) {
      const message = messageFrom(cause);
      if (isTemporaryError(cause)) reportConnectionStatus("interrupted");
      setLoadError(message);
      setHistory(null);
    } finally {
      setLoading(false);
    }
  }, [uploadMode.refresh]);

  const reloadHead = useCallback(async (): Promise<
    Schemas["HistoryListResponse"]["head"] | null
  > => {
    const session = currentGatewaySession();
    if (!session.businessProjectId || !session.gatewayDeviceExternalKey) return null;
    try {
      const snapshot = await uploadMode.refresh();
      if (!snapshot.workspace || snapshot.workspaceError) return null;
      const loadedHistory = await gatewayApi.listHistory();
      setHistory(loadedHistory);
      return loadedHistory.head;
    } catch {
      return null;
    }
  }, [uploadMode.refresh]);

  // The resume card mounts as soon as the attempt is known, without waiting
  // for the (possibly long-polling) operation read inside the same refresh.
  const resumeAttemptOperationId = uploadMode.attempt?.operation_id ?? null;
  useEffect(() => {
    if (resumeAttemptOperationId) setResumeSubmitOperationId(resumeAttemptOperationId);
  }, [resumeAttemptOperationId]);

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

  useEffect(() => {
    void load();
    const onSessionChange = () => {
      void load();
    };
    window.addEventListener("gateway-session-change", onSessionChange);
    return () => window.removeEventListener("gateway-session-change", onSessionChange);
  }, [load]);

  const rows = useMemo(
    () => (workspace && history ? buildWorkspaceTree(workspace, history, compareRefs) : []),
    [workspace, history, compareRefs],
  );
  useEffect(() => {
    if (!rows.length) return;
    const queryNode = new URLSearchParams(window.location.search).get("workbenchNode");
    const found =
      queryNode && rows.some((row) => row.key === queryNode)
        ? queryNode
        : (rows.find((row) => row.kind === "workspace")?.key ?? rows[0]?.key);
    setSelectedKey((current) =>
      current && rows.some((row) => row.key === current) ? current : (found ?? ""),
    );
  }, [rows]);
  useEffect(() => {
    if (!selectedKey || !rows.some((row) => row.key === selectedKey)) return;
    const url = new URL(window.location.href);
    if (url.searchParams.get("workbenchNode") === selectedKey) return;
    url.searchParams.set("workbenchNode", selectedKey);
    window.history.replaceState(null, "", url);
  }, [rows, selectedKey]);
  const rowByKey = useMemo(() => new Map(rows.map((row) => [row.key, row])), [rows]);
  const nodeLabel = (ref: Schemas["HistoryCompareNodeRequest"]) =>
    rowByKey.get(refKey(ref))?.label ?? ref.ref_id;
  const selected = rowByKey.get(selectedKey) ?? null;
  const comparedKeys = useMemo(() => new Set(compareRefs.map(refKey)), [compareRefs]);
  const comparisonLocked =
    comparePending ||
    showOperationForCompare(historyCompareOperationId, compareState) ||
    Boolean(
      historyCompareOperationId &&
      compareState?.status === "SUCCEEDED" &&
      bundleStatus === "downloading",
    );
  const actions = useMemo(
    () => deriveWorkbenchActions(selected, comparisonLocked),
    [selected, comparisonLocked],
  );

  const visibleRows = useMemo(() => {
    const query = filter.trim().toLocaleLowerCase();
    const rowMap = new Map(rows.map((row) => [row.key, row]));
    // "Current baseline only" keeps the head baseline's whole branch (its
    // workspace and submissions), not just the head row.
    const underHead = (row: WorkspaceTreeRow): boolean => {
      for (
        let current: WorkspaceTreeRow | undefined = row;
        current;
        current = current.parentKey ? rowMap.get(current.parentKey) : undefined
      ) {
        if (current.isHead) return true;
      }
      return false;
    };
    const matches = new Set(
      rows
        .filter(
          (row) =>
            (!currentBaselineOnly || underHead(row) || row.kind === "workspace") &&
            (!query ||
              `${row.label} ${row.status} ${row.refId ?? ""}`.toLocaleLowerCase().includes(query)),
        )
        .map((row) => row.key),
    );
    if (query)
      for (const key of [...matches]) {
        let parent = rowMap.get(key)?.parentKey ?? null;
        while (parent) {
          matches.add(parent);
          parent = rowMap.get(parent)?.parentKey ?? null;
        }
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
    try {
      scopedStorage.removeItem(pendingIntentKey);
    } catch {
      /* storage is optional */
    }
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

  const openCompareOperation = (
    operationId: string,
    nodes: Schemas["HistoryCompareNodeRequest"][],
  ) => {
    window.location.assign(
      pageUrl(
        "workspace",
        { operationId, operationKind: "history-compare", workbenchNode: selectedKey },
        nodes,
      ),
    );
  };

  // A limit error names existing compares by ID only; their nodes come from the server list.
  const jumpToCompare = async (operationId: string) => {
    let nodes: Schemas["HistoryCompareNodeRequest"][] = [];
    try {
      const page = await gatewayApi.listHistoryCompares({ limit: 100 });
      nodes = page.items.find((item) => item.operation_id === operationId)?.nodes ?? [];
    } catch {
      /* open without node labels */
    }
    openCompareOperation(operationId, nodes);
  };

  const sendHistoryCompare = async (
    intent: IdempotentIntent<Schemas["HistoryCompareAcceptRequest"]>,
  ) => {
    setComparePending(true);
    setCompareStartError(null);
    try {
      const accepted = await requestWithTimeout(
        gatewayApi.startHistoryCompare(intent.request, intent.key),
        historyCompareRequestTimeoutMs(),
      );
      setCompareIntent(null);
      try {
        scopedStorage.removeItem(pendingIntentKey);
      } catch {
        /* storage is optional */
      }
      // 200/replayed: an existing operation (same request) is reattached by its original ID.
      const compareParams: Record<string, string | null> = {
        page: "workspace",
        operationId: accepted.operation_id,
        operationKind: "history-compare",
        workbenchNode: selectedKey,
        replayed: accepted.replayed ? "1" : null,
      };
      window.location.assign(pageUrl("workspace", compareParams, intent.request.nodes));
    } catch (cause) {
      if (isTemporaryError(cause)) reportConnectionStatus("interrupted");
      const failure = describeHistoryStartError(cause);
      if (failure.retry !== "same") {
        // The key can no longer give a usable answer; the next attempt gets a new one.
        setCompareIntent(null);
        try {
          scopedStorage.removeItem(pendingIntentKey);
        } catch {
          /* storage is optional */
        }
      }
      setCompareStartError(failure);
    } finally {
      setComparePending(false);
    }
  };

  /** `fresh` forces a new idempotency key (expired, failed or unreadable earlier result). */
  const startOrRetryCompare = (
    request: Schemas["HistoryCompareAcceptRequest"] = { nodes: compareRefs },
    fresh = false,
  ) => {
    if (comparePending) return;
    let intent = fresh ? null : compareIntent;
    if (!intent && !fresh) {
      try {
        const saved = scopedStorage.getItem(pendingIntentKey);
        if (saved) intent = readHistoryCompareIntent(saved);
      } catch {
        /* create a new intent when storage is unavailable or invalid */
      }
    }
    intent = resolveHistoryCompareIntent(intent, request);
    try {
      scopedStorage.setItem(pendingIntentKey, JSON.stringify(intent));
    } catch {
      /* in-memory retry still reuses the key */
    }
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
    // Unknown until the first read: returning from the diff view re-reads a
    // finished compare, which must not show as queued again.
    setCompareState(null);
    setBundleStatus("idle");
    setCompareError(null);
    setCompareNeedsRerun(false);
    setCompareConnectionLost(false);
    setCompareElapsed(0);
    const ticker = window.setInterval(
      () => setCompareElapsed(Math.floor((Date.now() - startedAt) / 1_000)),
      1_000,
    );
    void pollHistoryCompare(gatewayApi, historyCompareOperationId, {
      signal: controller.signal,
      onUpdate: (value) => {
        setCompareState(value);
        setCompareConnectionLost(false);
      },
      onConnectionStatus: (status) => setCompareConnectionLost(status === "interrupted"),
    })
      .then(async (result) => {
        if (result.status !== "SUCCEEDED" || !result.result) {
          setCompareError(result.diagnostic?.message ?? "历史比较未能完成");
          // The same key keeps returning this terminal state; a retry needs a new request.
          setCompareNeedsRerun(true);
          setBundleStatus("idle");
          return;
        }
        setBundleStatus("downloading");
        try {
          const installed = await ensureLocalBundle({
            store: new OpfsBundleStore(),
            expectedBundleDigest: result.result.bundle_digest,
            fetchBundle: () =>
              gatewayApi.getHistoryBundle(historyCompareOperationId, controller.signal),
          });
          gatewayApi.assertSession?.();
          setHistoryBundle(installed);
          setCompareError(null);
          setBundleStatus("ready");
        } catch (cause) {
          if (controller.signal.aborted) return;
          // B5: the server's bundle error code is carried into the message so
          // it stays visible; the title copy comes from bundleErrorTitle.
          setCompareError(historyBundleErrorMessage(cause));
          setCompareNeedsRerun(describeHistoryReadError(cause).retry === "new");
          setBundleStatus("failed");
        }
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        if (cause instanceof PollingConnectionLostError) {
          setCompareConnectionLost(true);
          reportConnectionStatus("interrupted");
        } else {
          const failure = describeHistoryReadError(cause);
          setCompareError(`${failure.message}（${failure.code}）`);
          setCompareNeedsRerun(failure.retry === "new");
        }
      });
    return () => {
      controller.abort(new DOMException("比较状态查询已停止", "AbortError"));
      window.clearInterval(ticker);
    };
  }, [historyCompareOperationId, refreshCompare, downloadRevision]);

  const sortBy = (column: SortColumn) =>
    setSort((state) =>
      state?.column === column
        ? { column, direction: state.direction === 1 ? -1 : 1 }
        : { column, direction: 1 },
    );
  const sortIcon = (column: SortColumn) =>
    sort?.column === column ? (
      sort.direction === 1 ? (
        <ArrowUp size={12} />
      ) : (
        <ArrowDown size={12} />
      )
    ) : null;

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

  useEffect(() => {
    if (!historyBundle || compareState?.status !== "SUCCEEDED" || !compareState.result) {
      setPairSummaries({});
      return;
    }
    let cancelled = false;
    setPairSummaryError(null);
    void Promise.all(
      compareState.result.pairs.map(
        async (pair) =>
          [pair.pair_id, await summarizeHistoryPair(historyBundle, pair.pair_id)] as const,
      ),
    )
      .then((entries) => {
        if (!cancelled) setPairSummaries(Object.fromEntries(entries));
      })
      .catch((cause: unknown) => {
        if (!cancelled) setPairSummaryError(cause instanceof Error ? cause.message : String(cause));
      });
    return () => {
      cancelled = true;
    };
  }, [historyBundle, compareState]);

  // B1/B4: the toolbar upload action and the UploadStepCard share the same
  // occupancy gate from the hook; the page no longer keeps its own rule.
  const occupancyReason = uploadMode.gates.upload.enabled
    ? null
    : (uploadMode.gates.upload.reason ?? null);

  const showHistoryDrawer = Boolean(historyCompareOperationId);
  // Closing only forgets the operation in this page; the backend has no cancel
  // for History compare, so it is offered once the compare has finished.
  const closeHistoryDrawer = () => {
    const url = new URL(window.location.href);
    url.searchParams.delete("operationId");
    url.searchParams.delete("operationKind");
    url.searchParams.delete("replayed");
    window.history.replaceState(null, "", url);
    setHistoryDrawerCollapsed(false);
    setUrlRevision((value) => value + 1);
  };
  const showOperationStatus =
    operationId !== null && (operationKind === null || operationKind === "operation");
  // The server names the newest active Preview of the current upload revision
  // (possibly started in another tab or terminal); it is a reattach hint, not
  // proof that it is the only one.
  const activePreviewOperationId =
    !operationId && !uploadLocked ? (workspace?.active_preview_operation_id ?? null) : null;
  const resumeActivePreview = (id: string) => {
    try {
      scopedStorage.setItem("gateway-preview-operation", id);
    } catch {
      /* the status panel still shows without auto-open */
    }
    window.location.assign(
      pageUrl(
        "workspace",
        { operationId: id, operationKind: "operation", workbenchNode: selectedKey },
        compareRefs,
      ),
    );
  };

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
      onUploadStateChange={(active) => {
        if (active) {
          resumePending.current = false;
          uploadMode.clearResumeNotice();
        }
        if (active || !resumePending.current) setUploadLocked(active);
      }}
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
          {showOperationStatus && !(uploadLocked && !resumePreviewOperation) && (
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
                  ? () => {
                      resumePending.current = false;
                      scopedStorage.removeItem("gateway-preview-operation");
                      setUploadLocked(false);
                    }
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
                                setCollapsedNodes((current) => {
                                  const next = new Set(current);
                                  if (next.has(row.key)) next.delete(row.key);
                                  else next.add(row.key);
                                  return next;
                                });
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
                    <button
                      className="button button--secondary"
                      onClick={() => setRefreshCompare((value) => value + 1)}
                    >
                      <RefreshCw size={14} />
                      重试查询
                    </button>
                  )}
                  {bundleStatus === "failed" && !compareNeedsRerun && (
                    <button
                      className="button button--secondary"
                      onClick={() => {
                        setCompareError(null);
                        setDownloadRevision((value) => value + 1);
                      }}
                    >
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
                    onClick={() => setHistoryDrawerCollapsed((value) => !value)}
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

function historyBundleErrorMessage(cause: unknown): string {
  if (cause instanceof ApiError) {
    const title = cause.code ? bundleErrorTitle(cause.code) : undefined;
    const head = cause.code ? `${cause.code}：` : "";
    return `${title ? `${title}。` : ""}${head}${cause.message}`;
  }
  return cause instanceof Error ? cause.message : String(cause);
}

function fullTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString("zh-CN", { hour12: false }) : "—";
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
