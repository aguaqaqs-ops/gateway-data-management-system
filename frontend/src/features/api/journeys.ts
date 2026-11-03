import type { components } from "./generated/openapi";
import type { GatewayApi, ReviewAction, UploadRevisionInput } from "./client";
import { ensureLocalBundle, type InstalledBundle, type ReadableBundleStore } from "../bundle/local-bundle";
import { reportConnectionStatus } from "./connection-status";

type Schemas = components["schemas"];

export class OperationFailedError extends Error {
  constructor(readonly operationId: string, readonly diagnostic: Schemas["OperationResponse"]["diagnostic"]) {
    super(diagnostic?.message ?? `操作 ${operationId} 执行失败`);
    this.name = "OperationFailedError";
  }
}

export class PollingConnectionLostError extends Error {
  constructor(readonly operationId: string, readonly attempts: number) {
    super(`操作 ${operationId} 暂时无法连接，请重试查询`);
    this.name = "PollingConnectionLostError";
  }
}

export interface PollOptions {
  intervalMs?: number;
  requestTimeoutMs?: number;
  maxTransientRetries?: number;
  signal?: AbortSignal;
  wait?: (milliseconds: number, signal?: AbortSignal) => Promise<void>;
  onWait?: (milliseconds: number) => void;
  onUpdate?: (operation: Schemas["OperationResponse"]) => void;
  onConnectionStatus?: (status: "connected" | "interrupted") => void;
}

export type HistoryComparePollOptions = Omit<PollOptions, "onUpdate"> & {
  onUpdate?: (result: Schemas["HistoryCompareResultResponse"]) => void;
};

function abortableWait(milliseconds: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason ?? new DOMException("已取消", "AbortError"));
    const timer = setTimeout(resolve, milliseconds);
    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(signal.reason ?? new DOMException("已取消", "AbortError"));
    }, { once: true });
  });
}

export async function pollOperation(api: GatewayApi, operationId: string, options: PollOptions = {}): Promise<Schemas["OperationResponse"]> {
  const intervalMs = options.intervalMs ?? 1_000;
  const requestTimeoutMs = options.requestTimeoutMs ?? 30_000;
  const maxTransientRetries = options.maxTransientRetries ?? 4;
  const wait = options.wait ?? abortableWait;
  let transientRetries = 0;
  let lastStatus: Schemas["OperationResponse"]["status"] | null = null;
  for (;;) {
    if (options.signal?.aborted) throw options.signal.reason ?? new DOMException("已取消", "AbortError");
    const request = new AbortController();
    const timeout = setTimeout(() => request.abort(new DOMException("状态请求超时", "TimeoutError")), requestTimeoutMs);
    const abortParent = () => request.abort(options.signal?.reason ?? new DOMException("查询已取消", "AbortError"));
    options.signal?.addEventListener("abort", abortParent, { once: true });
    try {
      const operation = await api.getOperation(operationId, request.signal);
      lastStatus = operation.status;
      transientRetries = 0;
      options.onConnectionStatus?.("connected");
      reportConnectionStatus("connected");
      options.onUpdate?.(operation);
      if (operation.status === "SUCCEEDED") return operation;
      if (operation.status === "FAILED" || operation.status === "CANCELLED" || operation.status === "SUPERSEDED") {
        throw new OperationFailedError(operationId, operation.diagnostic);
      }
    } catch (cause) {
      if (cause instanceof OperationFailedError) throw cause;
      if (options.signal?.aborted) throw options.signal.reason ?? cause;
      if (isRequestTimeout(cause, request.signal)) {
        // A slow status request says nothing about the operation's outcome.
      } else if (isTransientRequestError(cause)) {
        transientRetries += 1;
        if (transientRetries > maxTransientRetries) {
          options.onConnectionStatus?.("interrupted");
          reportConnectionStatus("interrupted");
          throw new PollingConnectionLostError(operationId, transientRetries);
        }
        const baseIntervalMs = lastStatus === "MANUAL_RECOVERY_REQUIRED" ? 30_000 : intervalMs;
        const delay = Math.min(baseIntervalMs * 2 ** (transientRetries - 1), 30_000);
        options.onWait?.(delay);
        await wait(delay, options.signal);
        continue;
      } else {
        throw cause;
      }
    } finally {
      clearTimeout(timeout);
      options.signal?.removeEventListener("abort", abortParent);
    }
    const delay = lastStatus === "MANUAL_RECOVERY_REQUIRED" ? 30_000 : intervalMs;
    options.onWait?.(delay);
    await wait(delay, options.signal);
  }
}

function isRequestTimeout(cause: unknown, signal: AbortSignal): boolean {
  return signal.aborted || (cause instanceof DOMException && (cause.name === "TimeoutError" || cause.name === "AbortError"));
}

function isTransientRequestError(cause: unknown): boolean {
  if (cause instanceof TypeError) return true;
  return typeof cause === "object" && cause !== null && "status" in cause
    && (Number((cause as { status: unknown }).status) >= 500 || Number((cause as { status: unknown }).status) === 429);
}

export async function pollHistoryCompare(
  api: GatewayApi,
  operationId: string,
  options: HistoryComparePollOptions = {},
): Promise<Schemas["HistoryCompareResultResponse"]> {
  const intervalMs = options.intervalMs ?? 1_000;
  const requestTimeoutMs = options.requestTimeoutMs ?? 30_000;
  const maxTransientRetries = options.maxTransientRetries ?? 4;
  const wait = options.wait ?? abortableWait;
  let transientRetries = 0;
  for (;;) {
    if (options.signal?.aborted) throw options.signal.reason ?? new DOMException("已取消", "AbortError");
    const request = new AbortController();
    const timeout = setTimeout(() => request.abort(new DOMException("状态请求超时", "TimeoutError")), requestTimeoutMs);
    const abortParent = () => request.abort(options.signal?.reason ?? new DOMException("查询已取消", "AbortError"));
    options.signal?.addEventListener("abort", abortParent, { once: true });
    try {
      const result = await api.getHistoryCompare(operationId, request.signal);
      transientRetries = 0;
      options.onConnectionStatus?.("connected");
      reportConnectionStatus("connected");
      options.onUpdate?.(result);
      if (result.status === "SUCCEEDED" || result.status === "FAILED" || result.status === "CANCELLED") return result;
    } catch (cause) {
      if (options.signal?.aborted) throw options.signal.reason ?? cause;
      if (isRequestTimeout(cause, request.signal)) {
        // Continue polling; an HTTP timeout is not a failed history comparison.
      } else if (isTransientRequestError(cause)) {
        transientRetries += 1;
        if (transientRetries > maxTransientRetries) {
          options.onConnectionStatus?.("interrupted");
          reportConnectionStatus("interrupted");
          throw new PollingConnectionLostError(operationId, transientRetries);
        }
        const delay = Math.min(intervalMs * 2 ** (transientRetries - 1), 30_000);
        options.onWait?.(delay);
        await wait(delay, options.signal);
        continue;
      } else {
        throw cause;
      }
    } finally {
      clearTimeout(timeout);
      options.signal?.removeEventListener("abort", abortParent);
    }
    options.onWait?.(intervalMs);
    await wait(intervalMs, options.signal);
  }
}

export interface BundleJourneyResult {
  workspace: Schemas["WorkspaceResponse"];
  upload: Schemas["UploadRevisionResponse"];
  operation: Schemas["OperationResponse"];
  preview: Schemas["PreviewResultResponse"];
  bundle: InstalledBundle;
}

export interface PreviewJourneyInput {
  workspaceRequest: Schemas["CreateWorkspaceRequest"];
  upload: Omit<UploadRevisionInput, "expectedWorkspaceVersion">;
  baselineNodeId: string;
  baselineHeadVersion: number;
  poll?: PollOptions;
  onDownloadProgress?: Parameters<typeof ensureLocalBundle>[0]["onProgress"];
}

export async function runPreviewJourney(api: GatewayApi, store: ReadableBundleStore, input: PreviewJourneyInput): Promise<BundleJourneyResult> {
  const workspace = await api.createWorkspace(input.workspaceRequest);
  const upload = await api.uploadRevision(workspace.workspace_id, { ...input.upload, expectedWorkspaceVersion: workspace.optimistic_version });
  const accepted = await api.startPreview(workspace.workspace_id, {
    expected_workspace_version: upload.optimistic_version,
    upload_revision_id: upload.upload_revision_id,
    generation: upload.generation,
    expected_baseline_node_id: input.baselineNodeId,
    expected_baseline_head_version: input.baselineHeadVersion,
  });
  const operation = await pollOperation(api, accepted.operation_id, input.poll);
  const refreshedWorkspace = await api.createWorkspace(input.workspaceRequest);
  const previewResultId = refreshedWorkspace.current_preview_result_id;
  if (!previewResultId) throw new Error("预览操作完成后工作区没有当前 Preview 结果");
  const preview = await api.getPreviewResult(workspace.workspace_id, previewResultId);
  if (preview.operation_id !== accepted.operation_id) throw new Error("Preview 结果不属于本次预览操作");
  if (preview.upload_revision_id !== upload.upload_revision_id) throw new Error("Preview 结果不属于本次上传版本");
  const bundle = await ensureLocalBundle({
    store,
    expectedBundleDigest: preview.bundle_digest,
    fetchBundle: () => api.getPreviewBundle(workspace.workspace_id, preview.preview_result_id),
    onProgress: input.onDownloadProgress,
  });
  return { workspace: refreshedWorkspace, upload, operation, preview, bundle };
}

export class SubmitAbortedError extends Error {
  constructor(readonly abortCode: string) {
    super("提交未完成");
    this.name = "SubmitAbortedError";
  }
}

export interface SubmitJourneyInput {
  workspaceId: string;
  previewResultId: string;
  uploadRevisionId: string;
  generation: number;
  expectedWorkspaceVersion: number;
  baselineNodeId: string;
  baselineHeadVersion: number;
  identityConfirmations?: Array<{
    action: "ACCEPT_DATASET_REPLACEMENT" | "ACCEPT_UNVERIFIABLE_DETAILED_RESULT";
    assessmentSetDigest: string;
    reason: string;
  }>;
  idempotencyKey?: string;
  poll?: PollOptions;
}

export interface SubmitJourneyResult {
  accepted: Schemas["SubmitAcceptedResponse"];
  operation: Schemas["OperationResponse"];
  attempt: Schemas["SubmitAttemptResponse"];
  submission: Schemas["SubmissionResponse"];
}

export async function runSubmitJourney(api: GatewayApi, input: SubmitJourneyInput): Promise<SubmitJourneyResult> {
  const body = {
    expected_workspace_version: input.expectedWorkspaceVersion,
    preview_result_id: input.previewResultId,
    upload_revision_id: input.uploadRevisionId,
    generation: input.generation,
    expected_baseline_node_id: input.baselineNodeId,
    expected_baseline_head_version: input.baselineHeadVersion,
    identity_confirmations: input.identityConfirmations?.map((confirmation) => ({
      action: confirmation.action,
      assessment_set_digest: confirmation.assessmentSetDigest,
      reason: confirmation.reason,
    })),
  };
  const accepted = input.idempotencyKey
    ? await api.acceptSubmit(input.workspaceId, body, input.idempotencyKey)
    : await api.acceptSubmit(input.workspaceId, body);
  const operation = await pollOperation(api, accepted.operation_id, input.poll);
  const attempt = await api.getSubmitAttempt(input.workspaceId, accepted.submit_attempt_id);
  if (attempt.state === "ABORTED") throw new SubmitAbortedError(attempt.abort_code ?? "ABORTED");
  if (!attempt.submission_id) throw new SubmitAbortedError(attempt.abort_code ?? "ABORTED");
  const submission = await api.getSubmission(input.workspaceId, attempt.submission_id);
  return { accepted, operation, attempt, submission };
}

export interface ReviewHistoryJourneyResult {
  reviewFacts: Awaited<ReturnType<GatewayApi["getReviewFacts"]>>;
  accepted: Schemas["HistoryCompareAcceptResponse"];
  result: Schemas["HistoryCompareResultResponse"];
  bundle: InstalledBundle;
}

export interface HistoryComparisonJourneyResult {
  accepted: Schemas["HistoryCompareAcceptResponse"];
  result: Schemas["HistoryCompareResultResponse"];
  bundle: InstalledBundle;
}

export async function runHistoryComparison(api: GatewayApi, store: ReadableBundleStore, nodes: Schemas["HistoryCompareNodeRequest"][], idempotencyKey: string, options: HistoryComparePollOptions = {}): Promise<HistoryComparisonJourneyResult> {
  if (nodes.length < 2 || nodes.length > 3) throw new Error("历史比较需要两到三个节点");
  if (nodes.some((node) => node.ref_kind === "submission" && !node.ref_id)) throw new Error("历史提交节点缺少标识");
  const accepted = await api.startHistoryCompare({
    nodes,
  }, idempotencyKey);
  const result = await pollHistoryCompare(api, accepted.operation_id, options);
  if (result.status !== "SUCCEEDED" || !result.result) throw new Error(result.diagnostic?.message ?? "历史比较没有成功结果");
  const bundle = await ensureLocalBundle({
    store,
    expectedBundleDigest: result.result.bundle_digest,
    fetchBundle: () => api.getHistoryBundle(accepted.operation_id),
  });
  return { accepted, result, bundle };
}

/** Review compares the baseline node to the submission and always downloads the History bundle. */
export async function runReviewHistoryJourney(api: GatewayApi, store: ReadableBundleStore, submissionId: string, idempotencyKey: string, options: HistoryComparePollOptions = {}): Promise<ReviewHistoryJourneyResult> {
  const [reviewFacts, history] = await Promise.all([api.getReviewFacts(submissionId), api.listHistory()]);
  const submissionNodes = history.nodes.filter((node) => node.ref_kind === "submission" && node.ref_id === submissionId);
  if (submissionNodes.length !== 1) throw new Error(`History 中找不到唯一提交节点：${submissionId}`);
  const parent = submissionNodes[0]?.parent;
  if (!parent) throw new Error(`History 提交节点没有基线 parent：${submissionId}`);
  const comparison = await runHistoryComparison(api, store, [
    { ref_kind: parent.ref_kind, ref_id: parent.ref_id },
    { ref_kind: "submission", ref_id: submissionId },
  ], idempotencyKey, options);
  return { reviewFacts, ...comparison };
}

export async function applyReviewAction(api: GatewayApi, submissionId: string, action: ReviewAction, reason?: string, idempotencyKey?: string): Promise<Awaited<ReturnType<GatewayApi["applyReview"]>>> {
  if (action === "REJECT" && !reason?.trim()) throw new Error("退回时必须填写理由");
  const facts = await api.getReviewFacts(submissionId);
  const body = {
    expected_review_version: facts.review_version,
    action,
    ...(reason === undefined ? {} : { reason }),
  };
  return idempotencyKey ? api.applyReview(submissionId, body, idempotencyKey) : api.applyReview(submissionId, body);
}

export interface ArchiveJourneyInput {
  selected: Schemas["ArchiveSelectedRefRequest"];
  confirmations?: Array<{ subjectDigest: string; action: "CONFIRM" | "REVOKE"; reason?: string | null }>;
  anomalyResolutions?: Array<{ subjectDigest: string; action: "ACKNOWLEDGE_EXCLUSION" | "ACKNOWLEDGE_IDENTITY_EXCEPTION" | "REVOKE"; reason: string }>;
  idempotencyKey?: string;
}

async function listAllArchiveEvents(api: GatewayApi): Promise<Schemas["ArchiveAuditEventResponse"][]> {
  const events: Schemas["ArchiveAuditEventResponse"][] = [];
  let afterSequence = 0;
  for (;;) {
    const page = await api.listArchiveEvents(afterSequence);
    events.push(...page.events);
    const next = page.next_after_sequence;
    if (next == null || next <= afterSequence) return events;
    afterSequence = next;
  }
}

export async function runArchiveJourney(api: GatewayApi, input: ArchiveJourneyInput): Promise<{ plan: Schemas["PreviewArchivePlanResponse"]; started: Schemas["ArchiveStartedResponse"]; result: Schemas["ArchiveResultResponse"] }> {
  const candidates = await api.listArchiveCandidates();
  let plan = await api.previewArchive({ selected: input.selected });
  if (candidates.candidate_set_digest !== plan.candidate_set_digest) throw new Error("归档候选列表已变化，请重新确认");
  const events = await listAllArchiveEvents(api);
  let expectedSequence = events.reduce((max, event) => Math.max(max, event.sequence), 0) + 1;
  const confirmationRefs: Schemas["ArchiveAuditReferenceRequest"][] = [];
  const anomalyResolutionRefs: Schemas["ArchiveAuditReferenceRequest"][] = [];
  for (const confirmation of input.confirmations ?? []) {
    const appended = await api.appendArchiveConfirmation({
      expected_baseline_node_id: plan.head.business_baseline_node_id,
      expected_baseline_head_version: plan.head.baseline_head_version,
      selected: input.selected,
      candidate_set_digest: plan.candidate_set_digest,
      subject_digest: confirmation.subjectDigest,
      expected_sequence: expectedSequence,
      action: confirmation.action,
      reason: confirmation.reason,
    });
    confirmationRefs.push({ subject_digest: confirmation.subjectDigest, sequence: appended.sequence });
    expectedSequence = appended.sequence + 1;
  }
  for (const resolution of input.anomalyResolutions ?? []) {
    const anomaly = plan.anomalies.find((item) => item.subject_digest === resolution.subjectDigest);
    if (!anomaly) throw new Error(`归档方案中没有对应的异常：${resolution.subjectDigest}`);
    const appended = await api.appendArchiveAnomalyResolution({
      expected_baseline_node_id: plan.head.business_baseline_node_id,
      expected_baseline_head_version: plan.head.baseline_head_version,
      selected: input.selected,
      candidate_set_digest: plan.candidate_set_digest,
      subject_digest: anomaly.subject_digest,
      expected_sequence: expectedSequence,
      action: resolution.action,
      reason: resolution.reason,
      subject_kind: anomaly.subject_kind,
      issue_code: anomaly.issue_code,
      target_submission_id: anomaly.target_submission_id,
      target_candidate_digest: anomaly.target_candidate_digest,
    });
    anomalyResolutionRefs.push({ subject_digest: anomaly.subject_digest, sequence: appended.sequence });
    expectedSequence = appended.sequence + 1;
  }
  if (confirmationRefs.length || anomalyResolutionRefs.length) plan = await api.previewArchive({ selected: input.selected });
  const latestCandidates = await api.listArchiveCandidates();
  if (latestCandidates.candidate_set_digest !== plan.candidate_set_digest) throw new Error("归档候选列表已变化，请重新确认");
  if (!plan.can_start) throw new Error(`归档被阻止：${plan.blockers.join("、")}`);
  const started = await api.startArchive({
    expected_baseline_node_id: plan.head.business_baseline_node_id,
    expected_baseline_head_version: plan.head.baseline_head_version,
    candidate_set_digest: plan.candidate_set_digest,
    selected: input.selected,
    confirmation_refs: confirmationRefs,
    anomaly_resolution_refs: anomalyResolutionRefs,
  }, input.idempotencyKey);
  const result = await api.getArchiveResult(started.archive_result_id);
  return { plan, started, result };
}

/** Dataset replacement uses the same local Preview bundle path with MODIFIED_ONLY upload input. */
export async function runDatasetReplacementPreview(
  api: GatewayApi,
  store: ReadableBundleStore,
  input: Omit<PreviewJourneyInput, "upload"> & { upload: Omit<UploadRevisionInput, "expectedWorkspaceVersion" | "initial" | "inputCompleteness"> & { inputCompleteness: "MODIFIED_ONLY"; initial?: never } },
): Promise<BundleJourneyResult> {
  return runPreviewJourney(api, store, input);
}
