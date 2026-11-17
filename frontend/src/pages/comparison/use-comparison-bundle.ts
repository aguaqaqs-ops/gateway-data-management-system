import { useCallback, useEffect, useRef, useState } from "react";
import { boundBundleFetch } from "../../features/api/application-api";
import { ApiError } from "../../features/api/authenticated-fetch";
import type { GatewayApi } from "../../features/api/client";
import type { components } from "../../features/api/generated/openapi";
import { assertSubmissionReviewBundle, pollHistoryCompare } from "../../features/api/journeys";
import {
  ensureLocalBundle,
  OpfsBundleStore,
  type InstalledBundle,
} from "../../features/bundle/local-bundle";
import { loadComparisonPresentation } from "../../features/bundle/presentation";
import type { GatewaySessionState } from "../../features/session/handoff-session";
import type { BrowseCommandRuntime, BrowseState } from "../../features/view-model/commands";
import {
  bundleErrorState,
  bundlePathForState,
  serverResultReleaseCode,
  type PairPresentation,
  type PairSummary,
} from "./view-helpers";

export function useComparisonBundle(
  gatewayApi: GatewayApi,
  runtime: BrowseCommandRuntime,
  browse: BrowseState,
  sessionKind: GatewaySessionState["kind"],
  options: {
    readReviewContext: (
      submissionId: string,
    ) => Promise<components["schemas"]["SubmissionResultResponse"]>;
    setReviewResultChecking: (checking: boolean) => void;
    setReviewResultErrorCode: (code: string | undefined) => void;
  },
) {
  const { readReviewContext, setReviewResultChecking, setReviewResultErrorCode } = options;
  const [fetchBundle] = useState(boundBundleFetch);
  const [bundle, setBundle] = useState<InstalledBundle | null>(null);
  const [pairs, setPairs] = useState<PairPresentation[]>([]);
  const [loading, setLoading] = useState({ phase: "准备比较结果", received: 0, total: 0 });
  const [error, setError] = useState<{ code: string; details: string } | null>(null);
  const [historyCompareStatus, setHistoryCompareStatus] = useState<
    components["schemas"]["HistoryCompareResultResponse"]["status"] | null
  >(null);
  const [historyCompareWaited, setHistoryCompareWaited] = useState(0);
  const loadingKey = useRef<string | null>(null);
  const loadedRequest = useRef<{
    requestPath: string;
    bundleDigest: string;
    bundle: InstalledBundle;
  } | null>(null);

  const loadBundle = useCallback(async () => {
    if (sessionKind !== "handoff" && sessionKind !== "preset") return;
    const current = runtime.snapshot.state;
    const requestPath = bundlePathForState(current);
    if (!requestPath) {
      setError({
        code: "BUNDLE_RESOURCE_MISSING",
        details: "工作区、Preview 结果或历史比较操作 ID 不完整。",
      });
      return;
    }
    if (
      current.mode !== "REVIEW" &&
      loadedRequest.current?.requestPath === requestPath &&
      (!current.bundleDigest || current.bundleDigest === loadedRequest.current.bundleDigest)
    )
      return;
    const requestKey = requestPath;
    if (loadingKey.current === requestKey) return;
    loadingKey.current = requestKey;
    setError(null);
    setReviewResultErrorCode(undefined);
    setHistoryCompareStatus(null);
    if (current.mode === "REVIEW") setReviewResultChecking(true);
    if (loadedRequest.current?.requestPath !== requestPath) {
      setBundle(null);
      setPairs([]);
    }
    setLoading({ phase: "下载并校验比较结果", received: 0, total: 0 });
    try {
      let expectedBundleDigest: string | undefined;
      let submissionResult: components["schemas"]["SubmissionResultResponse"] | undefined;
      if (current.mode === "PREVIEW" && current.workspaceId && current.previewResultId) {
        expectedBundleDigest = (
          await gatewayApi.getPreviewResult(current.workspaceId, current.previewResultId)
        ).bundle_digest;
      }
      if (current.mode === "REVIEW" && current.submissionId) {
        const result = await readReviewContext(current.submissionId);
        gatewayApi.assertSession?.();
        if (result.submission_id !== current.submissionId)
          throw new ApiError("提交结果身份不一致", 503, "SUBMISSION_RESULT_INTEGRITY_FAILURE");
        submissionResult = result;
        expectedBundleDigest = result.bundle_digest;
        if (
          loadedRequest.current?.requestPath === requestPath &&
          loadedRequest.current.bundleDigest === expectedBundleDigest
        ) {
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
            if (value.status === "QUEUED" || value.status === "RUNNING")
              setLoading({
                phase: "历史比较执行中",
                received: Math.floor((Date.now() - startedAt) / 1_000),
                total: 0,
              });
          },
          onWait: () => setHistoryCompareWaited(Math.floor((Date.now() - startedAt) / 1_000)),
        });
        if (compareResult.status !== "SUCCEEDED" || !compareResult.result)
          throw new Error(compareResult.diagnostic?.message ?? "历史比较未能完成");
        expectedBundleDigest = compareResult.result.bundle_digest;
      }
      setBundle(null);
      setPairs([]);
      const loaded = await ensureLocalBundle({
        store: new OpfsBundleStore(),
        expectedBundleDigest,
        fetchBundle: async () => {
          try {
            return await fetchBundle(requestPath, { headers: { Accept: "application/x-tar" } });
          } catch (cause) {
            if (
              current.mode === "REVIEW" &&
              runtime.snapshot.state.submissionId === current.submissionId
            ) {
              setReviewResultErrorCode(serverResultReleaseCode(cause));
            }
            throw cause;
          }
        },
        onProgress: ({ receivedBytes, contentLength }) =>
          setLoading({
            phase: "下载并校验比较结果",
            received: receivedBytes,
            total: contentLength,
          }),
      });
      gatewayApi.assertSession?.();
      loadedRequest.current = {
        requestPath,
        bundleDigest: loaded.manifest.bundle_digest,
        bundle: loaded,
      };
      const pairSummaries: PairSummary[] = loaded.manifest.pairs.filter(
        (value) => typeof value?.pair_id === "string",
      );
      const inputRoles = new Map<number, string>();
      for (const input of loaded.manifest.inputs) {
        if (typeof input.role === "string" && Number.isInteger(input.input_index)) {
          inputRoles.set(input.input_index, input.role);
        }
      }
      const roleAt = (index: number | null | undefined): string | null =>
        typeof index === "number" ? (inputRoles.get(index) ?? null) : null;
      if (submissionResult && current.submissionId)
        assertSubmissionReviewBundle(current.submissionId, submissionResult, loaded);
      const loadedPairs = await Promise.all(
        pairSummaries.map(async (pair) => ({
          pair,
          roles: {
            before: roleAt(pair.before_input_index),
            current: roleAt(pair.current_input_index),
          },
          presentation: await loadComparisonPresentation(loaded, pair.pair_id),
        })),
      );
      gatewayApi.assertSession?.();
      setBundle(loaded);
      setPairs(loadedPairs);
      setLoading({ phase: "比较结果已就绪", received: 0, total: 0 });
      const currentState = runtime.snapshot.state;
      const initialBundleLoad = currentState.bundleDigest === null;
      if (currentState.bundleDigest !== loaded.manifest.bundle_digest)
        runtime.execute(
          {
            name: "set-bundle",
            mode: currentState.mode,
            bundleDigest: loaded.manifest.bundle_digest,
          },
          "external",
        );
      const selected =
        loadedPairs.find(({ pair }) => pair.pair_id === currentState.pairId) ??
        loadedPairs.find(({ pair }) => pair.pair_id === submissionResult?.default_pair_id) ??
        loadedPairs[0];
      if (selected && runtime.snapshot.state.pairId !== selected.pair.pair_id)
        runtime.execute({ name: "select-pair", pairId: selected.pair.pair_id }, "external");
      if (
        initialBundleLoad &&
        currentState.nodeKey &&
        runtime.snapshot.state.nodeKey !== currentState.nodeKey
      )
        runtime.execute({ name: "select-node", nodeKey: currentState.nodeKey }, "external");
      if (
        initialBundleLoad &&
        currentState.tabKey &&
        runtime.snapshot.state.tabKey !== currentState.tabKey
      )
        runtime.execute({ name: "select-tab", tabKey: currentState.tabKey }, "external");
      if (
        initialBundleLoad &&
        currentState.unassignedSide &&
        runtime.snapshot.state.unassignedSide !== currentState.unassignedSide
      )
        runtime.execute({ name: "set-unassigned", side: currentState.unassignedSide }, "external");
    } catch (cause) {
      const details = cause instanceof Error ? cause.message : String(cause);
      loadedRequest.current = null;
      setBundle(null);
      setPairs([]);
      setError(bundleErrorState(cause, details));
    } finally {
      if (loadingKey.current === requestKey) {
        loadingKey.current = null;
        if (current.mode === "REVIEW") setReviewResultChecking(false);
      }
    }
  }, [
    browse.bundleDigest,
    browse.mode,
    browse.operationId,
    browse.previewResultId,
    browse.submissionId,
    browse.workspaceId,
    runtime,
    sessionKind,
    readReviewContext,
  ]);

  useEffect(() => {
    void loadBundle();
  }, [loadBundle]);

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
      setBundle(null);
      setPairs([]);
      setError(bundleErrorState(cause, cause instanceof Error ? cause.message : String(cause)));
      return false;
    }
  }, [runtime, readReviewContext]);

  return {
    bundle,
    pairs,
    loading,
    error,
    setError,
    historyCompareStatus,
    historyCompareWaited,
    loadBundle,
    reloadReviewContext,
  };
}
