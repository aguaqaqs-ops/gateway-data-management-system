import type { components } from "./generated/openapi";
import type { GatewayApi, ReviewAction, UploadRevisionInput } from "./client";
import { ensureLocalBundle, type InstalledBundle, type ReadableBundleStore } from "../bundle/local-bundle";

type Schemas = components["schemas"];

export class OperationFailedError extends Error {
  constructor(readonly operationId: string, readonly diagnostic: Schemas["OperationResponse"]["diagnostic"]) {
    super(diagnostic?.message ?? `操作 ${operationId} 执行失败`);
    this.name = "OperationFailedError";
  }
}

export interface PollOptions {
  intervalMs?: number;
  timeoutMs?: number;
  signal?: AbortSignal;
  wait?: (milliseconds: number, signal?: AbortSignal) => Promise<void>;
  onUpdate?: (operation: Schemas["OperationResponse"]) => void;
}

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
  const timeoutMs = options.timeoutMs ?? 5 * 60_000;
  const wait = options.wait ?? abortableWait;
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    if (options.signal?.aborted) throw options.signal.reason ?? new DOMException("已取消", "AbortError");
    const operation = await api.getOperation(operationId, options.signal);
    options.onUpdate?.(operation);
    if (operation.status === "SUCCEEDED") return operation;
    if (operation.status === "FAILED" || operation.status === "CANCELLED") throw new OperationFailedError(operationId, operation.diagnostic);
    const remaining = deadline - Date.now();
    if (remaining <= 0) throw new Error(`操作 ${operationId} 等待超时`);
    await wait(Math.min(intervalMs, remaining), options.signal);
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
  const bundle = await ensureLocalBundle({
    store,
    expectedBundleDigest: preview.bundle_digest,
    fetchBundle: () => api.getPreviewBundle(workspace.workspace_id, preview.preview_result_id),
    onProgress: input.onDownloadProgress,
  });
  return { workspace: refreshedWorkspace, upload, operation, preview, bundle };
}

export interface SubmitJourneyInput {
  workspaceId: string;
  previewResultId: string;
  uploadRevisionId: string;
  generation: number;
  expectedWorkspaceVersion: number;
  baselineNodeId: string;
  baselineHeadVersion: number;
  poll?: PollOptions;
}

export interface SubmitJourneyResult {
  accepted: Schemas["SubmitAcceptedResponse"];
  operation: Schemas["OperationResponse"];
  attempt: Schemas["SubmitAttemptResponse"];
  submission: Schemas["SubmissionResponse"];
}

export async function runSubmitJourney(api: GatewayApi, input: SubmitJourneyInput): Promise<SubmitJourneyResult> {
  const accepted = await api.acceptSubmit(input.workspaceId, {
    expected_workspace_version: input.expectedWorkspaceVersion,
    preview_result_id: input.previewResultId,
    upload_revision_id: input.uploadRevisionId,
    generation: input.generation,
    expected_baseline_node_id: input.baselineNodeId,
    expected_baseline_head_version: input.baselineHeadVersion,
  });
  const operation = await pollOperation(api, accepted.operation_id, input.poll);
  const attempt = await api.getSubmitAttempt(input.workspaceId, accepted.submit_attempt_id);
  if (!attempt.submission_id) throw new Error("提交操作完成后没有生成 submission");
  const submission = await api.getSubmission(input.workspaceId, attempt.submission_id);
  return { accepted, operation, attempt, submission };
}

export interface ReviewHistoryJourneyResult {
  reviewFacts: Awaited<ReturnType<GatewayApi["getReviewFacts"]>>;
  accepted: Schemas["HistoryCompareAcceptResponse"];
  operation: Schemas["OperationResponse"];
  result: Schemas["HistoryCompareResultResponse"];
  bundle: InstalledBundle;
}

export interface HistoryComparisonJourneyResult {
  accepted: Schemas["HistoryCompareAcceptResponse"];
  operation: Schemas["OperationResponse"];
  result: Schemas["HistoryCompareResultResponse"];
  bundle: InstalledBundle;
}

export async function runHistoryComparison(api: GatewayApi, store: ReadableBundleStore, nodes: Schemas["HistoryCompareNodeRequest"][], options: PollOptions = {}): Promise<HistoryComparisonJourneyResult> {
  if (nodes.length < 2 || nodes.length > 3) throw new Error("历史比较需要两到三个节点");
  if (nodes.some((node) => node.ref_kind === "submission" && !node.ref_id)) throw new Error("历史提交节点缺少标识");
  const accepted = await api.startHistoryCompare({
    nodes,
  });
  const operation = await pollOperation(api, accepted.operation_id, options);
  const result = await api.getHistoryCompare(accepted.operation_id);
  if (result.status !== "SUCCEEDED" || !result.result) throw new Error(result.diagnostic?.message ?? "历史比较没有成功结果");
  const bundle = await ensureLocalBundle({
    store,
    expectedBundleDigest: result.result.bundle_digest,
    fetchBundle: () => api.getHistoryBundle(accepted.operation_id),
  });
  return { accepted, operation, result, bundle };
}

/** Review compares the baseline node to the submission and always downloads the History bundle. */
export async function runReviewHistoryJourney(api: GatewayApi, store: ReadableBundleStore, submissionId: string, options: PollOptions = {}): Promise<ReviewHistoryJourneyResult> {
  const [reviewFacts, history] = await Promise.all([api.getReviewFacts(submissionId), api.listHistory()]);
  const comparison = await runHistoryComparison(api, store, [
    { ref_kind: "baseline_node", ref_id: history.head.node_id },
    { ref_kind: "submission", ref_id: submissionId },
  ], options);
  return { reviewFacts, ...comparison };
}

export async function applyReviewAction(api: GatewayApi, submissionId: string, action: ReviewAction, reason?: string): Promise<Awaited<ReturnType<GatewayApi["applyReview"]>>> {
  if (action === "REJECT" && !reason?.trim()) throw new Error("退回时必须填写理由");
  const facts = await api.getReviewFacts(submissionId);
  return api.applyReview(submissionId, {
    expected_review_version: facts.review_version,
    action,
    ...(reason === undefined ? {} : { reason }),
  });
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
