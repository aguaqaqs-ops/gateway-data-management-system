import type { components, paths } from "./generated/openapi";
import { createAuthenticatedFetch, type AccessTokenProvider, type FetchLike } from "./authenticated-fetch";
import { Sha256 } from "../bundle/sha256";

type Schemas = components["schemas"];
type KnownPath = keyof paths;

export type ReviewAction = "APPROVE" | "REJECT" | "WITHDRAW";
export type ReviewStatus = "PENDING" | "APPROVED" | "REJECTED" | "WITHDRAWN";
export type SafeReviewEvent = Omit<Schemas["ReviewEventResponse"], "event_kind" | "from_status" | "to_status"> & {
  event_kind: "SUBMISSION_FINALIZED" | "APPROVED" | "REJECTED" | "WITHDRAWN";
  from_status: ReviewStatus | null;
  to_status: ReviewStatus;
};
export type SafeReviewFacts = Omit<Schemas["ReviewFactsResponse"], "status" | "events"> & {
  status: ReviewStatus;
  events: SafeReviewEvent[];
};
export type SafeHistoryList = Omit<Schemas["HistoryListResponse"], "nodes"> & {
  nodes: Array<Omit<Schemas["HistoryNodeResponse"], "review_status"> & { review_status: ReviewStatus | null }>;
};
export type SafeReviewApplied = Omit<Schemas["ReviewAppliedResponse"], "status" | "event"> & {
  status: ReviewStatus;
  event: SafeReviewEvent;
};

export interface UploadArtifact {
  partName: string;
  mediaType: string;
  file: File;
}

export interface UploadRevisionInput {
  expectedWorkspaceVersion: number;
  inputCompleteness: "FULL" | "MODIFIED_ONLY";
  initial?: UploadArtifact;
  modified: UploadArtifact;
  idempotencyKey?: string;
}

export interface GatewayApiOptions {
  baseUrl: string;
  token: AccessTokenProvider;
  fetcher?: FetchLike;
}

export interface GatewayApi {
  createWorkspace(body: Schemas["CreateWorkspaceRequest"]): Promise<Schemas["WorkspaceResponse"]>;
  uploadRevision(workspaceId: string, input: UploadRevisionInput): Promise<Schemas["UploadRevisionResponse"]>;
  startPreview(workspaceId: string, body: Schemas["StartPreviewRequest"], idempotencyKey?: string): Promise<Schemas["OperationAcceptedResponse"]>;
  getOperation(operationId: string, signal?: AbortSignal): Promise<Schemas["OperationResponse"]>;
  getPreviewResult(workspaceId: string, previewResultId: string): Promise<Schemas["PreviewResultResponse"]>;
  getPreviewBundle(workspaceId: string, previewResultId: string, signal?: AbortSignal): Promise<Response>;
  acceptSubmit(workspaceId: string, body: Schemas["AcceptSubmitRequest"], idempotencyKey?: string): Promise<Schemas["SubmitAcceptedResponse"]>;
  getSubmitAttempt(workspaceId: string, attemptId: string): Promise<Schemas["SubmitAttemptResponse"]>;
  getSubmission(workspaceId: string, submissionId: string): Promise<Schemas["SubmissionResponse"]>;
  getReviewFacts(submissionId: string): Promise<SafeReviewFacts>;
  applyReview(submissionId: string, body: { expected_review_version: number; action: ReviewAction; reason?: string | null }, idempotencyKey?: string): Promise<SafeReviewApplied>;
  listHistory(): Promise<SafeHistoryList>;
  startHistoryCompare(body: Schemas["HistoryCompareAcceptRequest"], idempotencyKey?: string): Promise<Schemas["HistoryCompareAcceptResponse"]>;
  getHistoryCompare(operationId: string, signal?: AbortSignal): Promise<Schemas["HistoryCompareResultResponse"]>;
  getHistoryBundle(operationId: string, signal?: AbortSignal): Promise<Response>;
  listArchiveCandidates(): Promise<Schemas["ArchiveCandidatesResponse"]>;
  listArchiveEvents(afterSequence?: number): Promise<Schemas["ArchiveAuditEventsResponse"]>;
  previewArchive(body: Schemas["PreviewArchivePlanRequest"]): Promise<Schemas["PreviewArchivePlanResponse"]>;
  appendArchiveConfirmation(body: Schemas["AppendArchiveConfirmationRequest"], idempotencyKey?: string): Promise<Schemas["ArchiveAuditAppendResponse"]>;
  appendArchiveAnomalyResolution(body: Schemas["AppendArchiveAnomalyResolutionRequest"], idempotencyKey?: string): Promise<Schemas["ArchiveAuditAppendResponse"]>;
  startArchive(body: Schemas["StartArchiveRequest"], idempotencyKey?: string): Promise<Schemas["ArchiveStartedResponse"]>;
  getArchiveResult(archiveResultId: string): Promise<Schemas["ArchiveResultResponse"]>;
}

async function json<T>(response: Response): Promise<T> {
  return response.json() as Promise<T>;
}

async function sha256(file: File): Promise<string> {
  const digest = new Sha256();
  const reader = file.stream().getReader();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      digest.update(value);
    }
  } finally {
    reader.releaseLock();
  }
  return digest.digest();
}

function safeReviewStatus(value: string): ReviewStatus {
  if (value === "PENDING" || value === "APPROVED" || value === "REJECTED" || value === "WITHDRAWN") return value;
  if (value === "RETURNED_FOR_REVISION") return "REJECTED";
  throw new Error(`未知审核状态：${value}`);
}

function safeReviewEvent(event: Schemas["ReviewEventResponse"]): SafeReviewEvent {
  const kind = event.event_kind === "RETURNED_FOR_REVISION" ? "REJECTED" : event.event_kind;
  if (kind !== "SUBMISSION_FINALIZED" && kind !== "APPROVED" && kind !== "REJECTED" && kind !== "WITHDRAWN") {
    throw new Error(`未知审核事件：${event.event_kind}`);
  }
  return {
    ...event,
    event_kind: kind,
    from_status: event.from_status == null ? null : safeReviewStatus(event.from_status),
    to_status: safeReviewStatus(event.to_status),
  };
}

export function createGatewayApi(options: GatewayApiOptions): GatewayApi {
  const request = createAuthenticatedFetch(options);
  const route = <T extends KnownPath>(path: T): T => path;
  const sendJson = async <T>(path: string, body: unknown, key?: string): Promise<T> => {
    const headers = new Headers({ "Content-Type": "application/json" });
    if (key) headers.set("Idempotency-Key", key);
    return json<T>(await request(path, { method: "POST", headers, body: JSON.stringify(body) }));
  };

  return {
    createWorkspace: (body) => sendJson<Schemas["WorkspaceResponse"]>(route("/v1/workspaces"), body),
    async uploadRevision(workspaceId, input) {
      if (input.inputCompleteness === "FULL" && !input.initial) throw new Error("完整上传必须包含原始组态");
      if (input.inputCompleteness === "MODIFIED_ONLY" && input.initial) throw new Error("仅修改上传不能包含原始组态");
      const artifacts: { INITIAL?: { part_name: string; media_type: string; size_bytes: number; raw_sha256: string }; MODIFIED: { part_name: string; media_type: string; size_bytes: number; raw_sha256: string } } = {
        MODIFIED: { part_name: input.modified.partName, media_type: input.modified.mediaType, size_bytes: input.modified.file.size, raw_sha256: await sha256(input.modified.file) },
      };
      if (input.initial) artifacts.INITIAL = { part_name: input.initial.partName, media_type: input.initial.mediaType, size_bytes: input.initial.file.size, raw_sha256: await sha256(input.initial.file) };
      const form = new FormData();
      form.append("manifest", JSON.stringify({ expected_workspace_version: input.expectedWorkspaceVersion, input_completeness: input.inputCompleteness, artifacts }));
      if (input.initial) form.append(input.initial.partName, input.initial.file, input.initial.file.name);
      form.append(input.modified.partName, input.modified.file, input.modified.file.name);
      const headers = new Headers();
      if (input.idempotencyKey) headers.set("Idempotency-Key", input.idempotencyKey);
      const response = await request(route("/v1/workspaces/{workspace_id}/upload-revisions").replace("{workspace_id}", encodeURIComponent(workspaceId)), { method: "POST", headers, body: form });
      return json<Schemas["UploadRevisionResponse"]>(response);
    },
    startPreview: (workspaceId, body, key) => sendJson<Schemas["OperationAcceptedResponse"]>(route("/v1/workspaces/{workspace_id}/preview-operations").replace("{workspace_id}", encodeURIComponent(workspaceId)), body, key),
    getOperation: async (operationId, signal) => json<Schemas["OperationResponse"]>(await request(route("/v1/operations/{operation_id}").replace("{operation_id}", encodeURIComponent(operationId)), { signal })),
    getPreviewResult: async (workspaceId, previewResultId) => json<Schemas["PreviewResultResponse"]>(await request(route("/v1/workspaces/{workspace_id}/preview-results/{preview_result_id}").replace("{workspace_id}", encodeURIComponent(workspaceId)).replace("{preview_result_id}", encodeURIComponent(previewResultId)))),
    getPreviewBundle: (workspaceId, previewResultId, signal) => request(route("/v1/workspaces/{workspace_id}/preview-results/{preview_result_id}/bundle").replace("{workspace_id}", encodeURIComponent(workspaceId)).replace("{preview_result_id}", encodeURIComponent(previewResultId)), { signal, headers: { Accept: "application/x-tar" } }),
    acceptSubmit: (workspaceId, body, key) => sendJson<Schemas["SubmitAcceptedResponse"]>(route("/v1/workspaces/{workspace_id}/submit-attempts").replace("{workspace_id}", encodeURIComponent(workspaceId)), body, key),
    getSubmitAttempt: async (workspaceId, attemptId) => json<Schemas["SubmitAttemptResponse"]>(await request(route("/v1/workspaces/{workspace_id}/submit-attempts/{submit_attempt_id}").replace("{workspace_id}", encodeURIComponent(workspaceId)).replace("{submit_attempt_id}", encodeURIComponent(attemptId)))),
    getSubmission: async (workspaceId, submissionId) => json<Schemas["SubmissionResponse"]>(await request(route("/v1/workspaces/{workspace_id}/submissions/{submission_id}").replace("{workspace_id}", encodeURIComponent(workspaceId)).replace("{submission_id}", encodeURIComponent(submissionId)))),
    async getReviewFacts(submissionId) {
      const result = await json<Schemas["ReviewFactsResponse"]>(await request(route("/v1/submissions/{submission_id}/review").replace("{submission_id}", encodeURIComponent(submissionId))));
      return { ...result, status: safeReviewStatus(result.status), events: (result.events ?? []).map(safeReviewEvent) };
    },
    async applyReview(submissionId, body, key) {
      const result = await sendJson<Schemas["ReviewAppliedResponse"]>(route("/v1/submissions/{submission_id}/review-events").replace("{submission_id}", encodeURIComponent(submissionId)), body, key);
      return { ...result, status: safeReviewStatus(result.status), event: safeReviewEvent(result.event) };
    },
    async listHistory() {
      const nodes: SafeHistoryList["nodes"] = [];
      const seenCursors = new Set<string>();
      let cursor: string | undefined;
      let firstPage: Schemas["HistoryListResponse"] | undefined;
      for (;;) {
        const query = new URLSearchParams({ limit: "100" });
        if (cursor !== undefined) query.set("cursor", cursor);
        const path = `${route("/v1/history")}?${query.toString()}`;
        const page = await json<Schemas["HistoryListResponse"]>(await request(path));
        firstPage ??= page;
        nodes.push(...page.nodes.map((node) => ({ ...node, review_status: node.review_status == null ? null : safeReviewStatus(node.review_status) })));
        const next = page.next_cursor ?? null;
        if (next === null) return { ...firstPage, nodes, next_cursor: null };
        if (!next || seenCursors.has(next)) throw new Error("History 分页游标无效或重复");
        seenCursors.add(next);
        cursor = next;
      }
    },
    startHistoryCompare: (body, key) => sendJson<Schemas["HistoryCompareAcceptResponse"]>(route("/v1/history-compares"), body, key),
    getHistoryCompare: async (operationId, signal) => json<Schemas["HistoryCompareResultResponse"]>(await request(route("/v1/history-compares/{operation_id}").replace("{operation_id}", encodeURIComponent(operationId)), { signal })),
    getHistoryBundle: (operationId, signal) => request(route("/v1/history-compares/{operation_id}/bundle").replace("{operation_id}", encodeURIComponent(operationId)), { signal, headers: { Accept: "application/x-tar" } }),
    listArchiveCandidates: async () => json<Schemas["ArchiveCandidatesResponse"]>(await request(route("/v1/archive-candidates"))),
    listArchiveEvents: async (afterSequence) => json<Schemas["ArchiveAuditEventsResponse"]>(await request(`/v1/archive-audit-events${afterSequence === undefined ? "" : `?after_sequence=${encodeURIComponent(String(afterSequence))}`}`)),
    previewArchive: (body) => sendJson<Schemas["PreviewArchivePlanResponse"]>(route("/v1/archive-plan-preview"), body),
    appendArchiveConfirmation: (body, key) => sendJson<Schemas["ArchiveAuditAppendResponse"]>(route("/v1/archive-confirmations"), body, key),
    appendArchiveAnomalyResolution: (body, key) => sendJson<Schemas["ArchiveAuditAppendResponse"]>(route("/v1/archive-anomaly-resolutions"), body, key),
    startArchive: (body, key) => sendJson<Schemas["ArchiveStartedResponse"]>(route("/v1/archives"), body, key),
    getArchiveResult: async (archiveResultId) => json<Schemas["ArchiveResultResponse"]>(await request(route("/v1/archives/{archive_result_id}").replace("{archive_result_id}", encodeURIComponent(archiveResultId)))),
  };
}
