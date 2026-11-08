import { previewBaseUrl, type JourneyIdentity } from "./env";

/**
 * Direct backend calls used for setup and for verifying state that the UI does
 * not expose (pointers, review versions, operation results). Everything goes
 * to the real backend through the preview proxy (`http://127.0.0.1:4173`), the
 * same origin the browser uses, so no mock module is involved.
 */

export interface WorkspaceBody {
  workspace_id: string;
  gateway_device_external_key: string;
  business_project_id: string;
  state: string;
  generation: number;
  current_upload_revision_id: string | null;
  current_preview_result_id: string | null;
  active_submit_attempt_id: string | null;
  active_submission_id: string | null;
  optimistic_version: number;
  created_at: string;
  updated_at: string;
}

export interface PreviewResultBody {
  preview_result_id: string;
  workspace_id: string;
  upload_revision_id: string;
  generation: number;
  operation_id: string;
  business_baseline_node_id: string;
  business_baseline_commit_id: string;
  derived_stale: boolean;
  bundle_digest: string;
  identity_assessment_set_digest: string;
  identity_pairs: Array<{
    pair_id: string;
    applicability: string;
    status: string;
    mode: string;
    assessment_ref: string | null;
    assessment_digest: string | null;
  }>;
  created_at: string;
}

export interface OperationBody {
  operation_id: string;
  workspace_id: string;
  upload_revision_id: string | null;
  generation: number;
  job_kind: string;
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
  diagnostic: string | null;
}

export interface SubmitAttemptBody {
  submit_attempt_id: string;
  workspace_id: string;
  state: "PREPARED" | "EFFECT_PENDING" | "FINALIZED" | "ABORTED";
  operation_id: string | null;
  submission_id: string | null;
  abort_code: string | null;
}

export interface SubmissionBody {
  submission_id: string;
  submit_attempt_id: string;
  workspace_id: string;
  upload_revision_id: string;
  preview_result_id: string;
  generation: number;
  repository_id: string;
  based_on_baseline_node_id: string;
  created_by: string;
  created_at: string;
}

export type ReviewStatus = "PENDING" | "APPROVED" | "REJECTED" | "WITHDRAWN";

export interface ReviewFactsBody {
  submission_id: string;
  status: ReviewStatus;
  review_version: number;
  updated_by: string;
  updated_at: string;
  submission_disposition: string | null;
  identity_exception: string | null;
  identity_confirmations: unknown[];
}

export interface WorkspaceNode {
  node_id: string;
  node_kind: string;
  version: number | null;
  parent_node_id: string | null;
  review_status: ReviewStatus | null;
  submission_disposition: string | null;
  review_version: number | null;
  submission_id: string | null;
  created_at: string;
}

export interface HistoryBody {
  nodes: WorkspaceNode[];
  next_cursor: string | null;
}

export interface TarResponse {
  status: number;
  contentType: string | null;
  contentLength: string | null;
  etag: string | null;
  contentDisposition: string | null;
  body: Buffer;
}

export class ApiCallError extends Error {
  constructor(
    readonly status: number,
    readonly code: string | null,
    message: string,
    readonly body: unknown,
  ) {
    super(`${status} ${code ?? "?"}: ${message}`);
  }
}

export interface ApiEnvelope<T> {
  status: number;
  body: T;
}

function headersFor(identity: JourneyIdentity, extra?: Record<string, string>): Record<string, string> {
  return { Authorization: `Bearer ${identity.token}`, ...extra };
}

export async function apiRequest<T>(
  identity: JourneyIdentity,
  method: string,
  path: string,
  options: { body?: unknown; headers?: Record<string, string> } = {},
): Promise<ApiEnvelope<T>> {
  const init: RequestInit = {
    method,
    headers: headersFor(identity, {
      ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
      ...options.headers,
    }),
  };
  if (options.body !== undefined) init.body = JSON.stringify(options.body);
  const response = await fetch(`${previewBaseUrl()}${path}`, init);
  const text = await response.text();
  const body = text ? (JSON.parse(text) as T) : (undefined as T);
  if (!response.ok) {
    const payload = body as { code?: string; message?: string } | undefined;
    throw new ApiCallError(response.status, payload?.code ?? null, payload?.message ?? text, body);
  }
  return { status: response.status, body };
}

export async function tryApi<T>(
  identity: JourneyIdentity,
  method: string,
  path: string,
  options: { body?: unknown; headers?: Record<string, string> } = {},
): Promise<{ ok: true; status: number; body: T } | { ok: false; status: number; code: string | null; message: string }> {
  try {
    const result = await apiRequest<T>(identity, method, path, options);
    return { ok: true, status: result.status, body: result.body };
  } catch (error) {
    if (error instanceof ApiCallError) return { ok: false, status: error.status, code: error.code, message: error.message };
    throw error;
  }
}

export function createWorkspace(identity: JourneyIdentity): Promise<ApiEnvelope<WorkspaceBody>> {
  return apiRequest<WorkspaceBody>(identity, "POST", "/v1/workspaces", {
    body: {
      gateway_device_external_key: identity.gatewayDeviceExternalKey,
      business_project_id: identity.businessProjectId,
    },
  });
}

export async function currentWorkspace(identity: JourneyIdentity): Promise<WorkspaceBody> {
  const { body } = await createWorkspace(identity);
  return body;
}

export function listHistory(identity: JourneyIdentity): Promise<ApiEnvelope<HistoryBody>> {
  return apiRequest<HistoryBody>(identity, "GET", "/v1/history?limit=100");
}

export function getPreviewResult(
  identity: JourneyIdentity,
  workspaceId: string,
  previewResultId: string,
): Promise<ApiEnvelope<PreviewResultBody>> {
  return apiRequest<PreviewResultBody>(identity, "GET", `/v1/workspaces/${workspaceId}/preview-results/${previewResultId}`);
}

export function getOperation(identity: JourneyIdentity, operationId: string): Promise<ApiEnvelope<OperationBody>> {
  return apiRequest<OperationBody>(identity, "GET", `/v1/operations/${operationId}`);
}

export function getSubmitAttempt(
  identity: JourneyIdentity,
  workspaceId: string,
  attemptId: string,
): Promise<ApiEnvelope<SubmitAttemptBody>> {
  return apiRequest<SubmitAttemptBody>(identity, "GET", `/v1/workspaces/${workspaceId}/submit-attempts/${attemptId}`);
}

export function getSubmission(
  identity: JourneyIdentity,
  workspaceId: string,
  submissionId: string,
): Promise<ApiEnvelope<SubmissionBody>> {
  return apiRequest<SubmissionBody>(identity, "GET", `/v1/workspaces/${workspaceId}/submissions/${submissionId}`);
}

export function getReviewFacts(identity: JourneyIdentity, submissionId: string): Promise<ApiEnvelope<ReviewFactsBody>> {
  return apiRequest<ReviewFactsBody>(identity, "GET", `/v1/submissions/${submissionId}/review`);
}

export function applyReview(
  identity: JourneyIdentity,
  submissionId: string,
  body: { expected_review_version: number; action: "APPROVE" | "REJECT" | "WITHDRAW"; reason?: string },
  idempotencyKey: string = crypto.randomUUID(),
): Promise<ApiEnvelope<{ submission_id: string; status: ReviewStatus; review_version: number }>> {
  return apiRequest(identity, "POST", `/v1/submissions/${submissionId}/review-events`, {
    body,
    headers: { "Idempotency-Key": idempotencyKey },
  });
}

export async function fetchTar(identity: JourneyIdentity, path: string): Promise<TarResponse> {
  const response = await fetch(`${previewBaseUrl()}${path}`, {
    headers: headersFor(identity, { Accept: "application/x-tar" }),
  });
  return {
    status: response.status,
    contentType: response.headers.get("content-type"),
    contentLength: response.headers.get("content-length"),
    etag: response.headers.get("etag"),
    contentDisposition: response.headers.get("content-disposition"),
    body: Buffer.from(await response.arrayBuffer()),
  };
}

export async function waitForOperation(
  identity: JourneyIdentity,
  operationId: string,
  timeoutMs = 240_000,
): Promise<OperationBody> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const { body } = await getOperation(identity, operationId);
    if (body.status === "SUCCEEDED" || body.status === "FAILED" || body.status === "CANCELLED") return body;
    if (Date.now() > deadline) throw new Error(`operation ${operationId} did not settle within ${timeoutMs}ms (last ${body.status})`);
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

export async function submissionFromWorkspace(identity: JourneyIdentity, workspace: WorkspaceBody): Promise<SubmissionBody> {
  if (!workspace.active_submission_id) throw new Error("workspace has no active_submission_id");
  const submission = await getSubmission(identity, workspace.workspace_id, workspace.active_submission_id);
  return submission.body;
}

export async function waitForPendingSubmission(
  identity: JourneyIdentity,
  workspaceId: string,
  timeoutMs = 240_000,
): Promise<{ workspace: WorkspaceBody; submission: SubmissionBody }> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const workspace = await currentWorkspace(identity);
    if (workspace.workspace_id !== workspaceId) throw new Error(`workspace changed: ${workspace.workspace_id} !== ${workspaceId}`);
    if (workspace.active_submission_id && !workspace.active_submit_attempt_id) {
      const submission = await getSubmission(identity, workspaceId, workspace.active_submission_id);
      return { workspace, submission: submission.body };
    }
    if (Date.now() > deadline) throw new Error(`workspace ${workspaceId} has no settled submission within ${timeoutMs}ms`);
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}
