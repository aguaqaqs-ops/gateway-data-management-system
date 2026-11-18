import { useCallback, useEffect, useRef, useState } from "react";
import type { useBoundGatewayApi } from "../../api/application-api";
import { ApiError } from "../../api/authenticated-fetch";
import {
  buildArchiveSelectedRef,
  createArchiveJourneyProgress,
  runArchiveJourney,
} from "../../api/journeys";
import {
  archiveError,
  KNOWN_ISSUE_CODES,
  startDisabledReason as computeStartDisabledReason,
} from "../../view-model/archive-dialog";
import type { Anomaly, Candidates, Plan, Result } from "./archive-types";

type GatewayApi = ReturnType<typeof useBoundGatewayApi>;

interface UseArchivePlanOptions {
  gatewayApi: GatewayApi;
  open: boolean;
  submissionId: string | null;
}

/** One archive plan and its execution: candidates, plan, selection, load/reset/start. */
export function useArchivePlan({ gatewayApi, open, submissionId }: UseArchivePlanOptions) {
  const [candidates, setCandidates] = useState<Candidates | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [selectedDigest, setSelectedDigest] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<{ message: string; code: string | null } | null>(null);
  const [confirmSelection, setConfirmSelection] = useState(false);
  const [collectionNotice, setCollectionNotice] = useState<string | null>(null);
  // C8: the 409 conflict notice renders separately from the candidate-set
  // change notice; the pending stash is consumed by every completed load.
  const [conflictNotice, setConflictNotice] = useState<string | null>(null);
  const previousDigest = useRef<string | null>(null);
  const pendingNotice = useRef<string | null>(null);
  const [running, setRunning] = useState(false);
  const [failure, setFailure] = useState<{ title: string; code: string; refresh: boolean } | null>(
    null,
  );
  const [result, setResult] = useState<Result | null>(null);
  const progress = useRef(createArchiveJourneyProgress());

  const load = useCallback(async (target: string) => {
    progress.current = createArchiveJourneyProgress();
    setLoading(true);
    setLoadError(null);
    setFailure(null);
    let stage: "candidates" | "preview" = "candidates";
    try {
      let listed = await gatewayApi.listArchiveCandidates();
      let candidate = listed.candidates.find((item) => item.submission_id === target);
      if (!candidate) {
        setLoadError({ message: "所选提交不在当前归档候选集合中，请刷新归档候选。", code: null });
        setPlan(null);
        return;
      }
      stage = "preview";
      let selected = buildArchiveSelectedRef(candidate);
      let loaded = await gatewayApi.previewArchive({ selected });
      if (loaded.selected && loaded.selected.submission_id !== target) {
        setLoadError({ message: "归档预检返回了其他提交，请刷新后重试。", code: null });
        setPlan(null);
        return;
      }
      if (loaded.candidate_set_digest !== listed.candidate_set_digest) {
        // §16.2 “一次加载”: the candidate read and the preview must agree. Redo
        // both once, rebuilding selected from the second candidate read.
        stage = "candidates";
        const reloadedList = await gatewayApi.listArchiveCandidates();
        stage = "preview";
        const reloadedCandidate = reloadedList.candidates.find(
          (item) => item.submission_id === target,
        );
        if (!reloadedCandidate) {
          setLoadError({ message: "所选提交不在当前归档候选集合中，请刷新归档候选。", code: null });
          setPlan(null);
          return;
        }
        listed = reloadedList;
        candidate = reloadedCandidate;
        selected = buildArchiveSelectedRef(candidate);
        const reloaded = await gatewayApi.previewArchive({ selected });
        if (reloaded.selected && reloaded.selected.submission_id !== target) {
          setLoadError({ message: "归档预检返回了其他提交，请刷新后重试。", code: null });
          setPlan(null);
          return;
        }
        if (reloaded.candidate_set_digest !== listed.candidate_set_digest) {
          setLoadError({ message: "归档候选集合已变化，请重新预检。", code: null });
          setPlan(null);
          return;
        }
        loaded = reloaded;
      }
      if (
        previousDigest.current !== null &&
        previousDigest.current !== loaded.candidate_set_digest
      ) {
        // The set-change banner always uses the generic text; the specific
        // 409 text lives in the separate conflict banner below.
        setCollectionNotice("候选集合已变化，之前的接受不再适用，请重新核对");
      } else {
        // A later load whose candidate set did not change invalidates the old
        // set-change banner.
        setCollectionNotice(null);
      }
      if (pendingNotice.current === null) {
        // An ordinary load clears a stale 409 conflict notice; a load that
        // follows a 409 (pending set) keeps it so both notices can appear.
        setConflictNotice(null);
      }
      pendingNotice.current = null;
      previousDigest.current = loaded.candidate_set_digest;
      setCandidates(listed);
      setSelectedDigest(candidate.expected_candidate_digest);
      setPlan(loaded);
    } catch (cause) {
      // A failed load does not confirm the pending 409 notice; drop it so the
      // next successful load starts from a clean slate.
      pendingNotice.current = null;
      const message =
        cause instanceof ApiError && cause.code === "SCOPE_FORBIDDEN"
          ? stage === "preview"
            ? "当前身份没有预检归档方案的权限"
            : "当前身份没有该操作的权限"
          : cause instanceof Error
            ? cause.message
            : String(cause);
      setLoadError({
        message,
        code: cause instanceof ApiError ? (cause.code ?? `HTTP_${cause.status}`) : null,
      });
      setPlan(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open || !submissionId) return;
    setPlan(null);
    setCandidates(null);
    setResult(null);
    setFailure(null);
    setCollectionNotice(null);
    setConflictNotice(null);
    pendingNotice.current = null;
    setConfirmSelection(false);
    previousDigest.current = null;
    progress.current = createArchiveJourneyProgress();
    void load(submissionId);
  }, [open, submissionId, load]);

  function refresh() {
    progress.current = createArchiveJourneyProgress();
    setResult(null);
    if (submissionId) void load(submissionId);
  }

  const anomalies = plan?.anomalies ?? [];
  const unprocessedCount = anomalies.filter(
    (anomaly) => anomaly.resolution_status !== "ACCEPTED",
  ).length;
  const unknownCount = anomalies.filter(
    (anomaly: Anomaly) => !KNOWN_ISSUE_CODES.has(anomaly.issue_code),
  ).length;
  const blocked = Boolean(plan && plan.blockers.length > 0);
  const canStart = Boolean(
    plan &&
    candidates &&
    selectedDigest &&
    submissionId &&
    !blocked &&
    unknownCount === 0 &&
    unprocessedCount === 0 &&
    confirmSelection &&
    !loading &&
    !running,
  );

  async function start() {
    if (!plan || !candidates || !submissionId || !selectedDigest || !canStart) return;
    setRunning(true);
    setFailure(null);
    try {
      const required = plan.confirmation_requirements ?? [];
      const outcome = await runArchiveJourney(
        gatewayApi,
        {
          selected: buildArchiveSelectedRef({
            submission_id: submissionId,
            expected_candidate_digest: selectedDigest,
          }),
          confirmations: required.map((subjectDigest) => ({
            subjectDigest,
            action: "CONFIRM" as const,
          })),
        },
        progress.current,
      );
      setResult(outcome.result);
    } catch (cause) {
      setFailure(archiveError(cause));
    } finally {
      setRunning(false);
    }
  }

  function startDisabledReason(): string | undefined {
    return computeStartDisabledReason({
      loading,
      loadError,
      plan,
      blockerCount: plan?.blockers.length ?? 0,
      unknownCount,
      unprocessedCount,
      confirmSelection,
      running,
    });
  }

  function reportConflict(notice: string) {
    pendingNotice.current = notice;
    setConflictNotice(notice);
    refresh();
  }

  async function clearPlanAndLoad(target: string) {
    setCandidates(null);
    setPlan(null);
    await load(target);
  }

  return {
    candidates,
    plan,
    selectedDigest,
    loading,
    loadError,
    confirmSelection,
    setConfirmSelection,
    collectionNotice,
    conflictNotice,
    running,
    failure,
    result,
    load,
    refresh,
    start,
    canStart,
    startDisabledReason,
    unprocessedCount,
    unknownCount,
    reportConflict,
    clearPlanAndLoad,
  };
}
