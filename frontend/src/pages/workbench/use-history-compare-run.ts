import { useEffect, useState } from "react";
import type { GatewayApi } from "../../features/api/client";
import { reportConnectionStatus } from "../../features/api/connection-status";
import { PollingConnectionLostError, pollHistoryCompare } from "../../features/api/journeys";
import {
  ensureLocalBundle,
  OpfsBundleStore,
  type InstalledBundle,
} from "../../features/bundle/local-bundle";
import { describeHistoryReadError } from "../../features/workbench/history-compare-errors";
import {
  summarizeHistoryPair,
  type HistoryPairSummary,
} from "../../features/workbench/history-summary";
import { historyBundleErrorMessage, type Schemas } from "./workbench-helpers";

export function useHistoryCompareRun(gatewayApi: GatewayApi) {
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

  const operationId = new URLSearchParams(window.location.search).get("operationId");
  const operationKind = new URLSearchParams(window.location.search).get("operationKind");
  const historyCompareOperationId = operationKind === "history-compare" ? operationId : null;
  const compareReplayed =
    Boolean(historyCompareOperationId) &&
    new URLSearchParams(window.location.search).get("replayed") === "1";

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

  const retryQuery = () => setRefreshCompare((value) => value + 1);
  const retryDownload = () => {
    setCompareError(null);
    setDownloadRevision((value) => value + 1);
  };
  const toggleDrawerCollapsed = () => setHistoryDrawerCollapsed((value) => !value);

  return {
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
  };
}
