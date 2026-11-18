import { useState } from "react";
import type { GatewayApi } from "../../features/api/client";
import { reportConnectionStatus } from "../../features/api/connection-status";
import {
  readHistoryCompareIntent,
  requestWithTimeout,
  resolveHistoryCompareIntent,
  type IdempotentIntent,
} from "../../features/api/idempotency";
import { scopedStorage } from "../../features/api/scoped-storage";
import { historyCompareRequestTimeoutMs } from "../../features/api/session";
import type { WorkspaceTreeRow } from "../../features/view-model/workspace";
import {
  describeHistoryStartError,
  type HistoryCompareFailure,
} from "../../features/workbench/history-compare-errors";
import {
  historyRef,
  isTemporaryError,
  pageUrl,
  refKey,
  showOperationForCompare,
  type Schemas,
} from "./workbench-helpers";

const PENDING_INTENT_KEY = "gateway-history-compare-pending-intent";

export function useCompareTray(
  gatewayApi: GatewayApi,
  options: {
    selectedKey: string;
    historyCompareOperationId: string | null;
    compareState: Schemas["HistoryCompareResultResponse"] | null;
    bundleStatus: "idle" | "downloading" | "ready" | "failed";
  },
) {
  const { selectedKey, historyCompareOperationId, compareState, bundleStatus } = options;
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
  const [compareIntent, setCompareIntent] = useState<IdempotentIntent<
    Schemas["HistoryCompareAcceptRequest"]
  > | null>(() => {
    try {
      return readHistoryCompareIntent(scopedStorage.getItem(PENDING_INTENT_KEY));
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

  const comparisonLocked =
    comparePending ||
    showOperationForCompare(historyCompareOperationId, compareState) ||
    Boolean(
      historyCompareOperationId &&
      compareState?.status === "SUCCEEDED" &&
      bundleStatus === "downloading",
    );

  const setCompareSelection = (next: Schemas["HistoryCompareNodeRequest"][]) => {
    if (comparisonLocked) return;
    setCompareRefs(next.slice(0, 3));
    setCompareIntent(null);
    setCompareStartError(null);
    try {
      scopedStorage.removeItem(PENDING_INTENT_KEY);
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
        scopedStorage.removeItem(PENDING_INTENT_KEY);
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
          scopedStorage.removeItem(PENDING_INTENT_KEY);
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
        const saved = scopedStorage.getItem(PENDING_INTENT_KEY);
        if (saved) intent = readHistoryCompareIntent(saved);
      } catch {
        /* create a new intent when storage is unavailable or invalid */
      }
    }
    intent = resolveHistoryCompareIntent(intent, request);
    try {
      scopedStorage.setItem(PENDING_INTENT_KEY, JSON.stringify(intent));
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

  return {
    compareRefs,
    compareIntent,
    compareStartError,
    comparePending,
    comparisonLocked,
    setCompareSelection,
    toggleCompare,
    sendHistoryCompare,
    startOrRetryCompare,
    openCompareOperation,
    jumpToCompare,
  };
}
