import { expect, test, type Page, type Request as PlaywrightRequest, type Route } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import type { components } from "../src/features/api/generated/openapi";
import {
  HISTORY_PAGE_ONE, HISTORY_PAGE_TWO, HISTORY_COMPARE_RUNNING, MANUAL_RECOVERY_TO_SUCCESS,
  SIMULATED_ERROR_RESPONSES, TEST_REVIEW_FACTS, WORKSPACE_ALREADY_EXISTS, WORKSPACE_CREATED, HISTORY_COMPARE_ACCEPT_BODY,
  TEST_OPERATION_SUCCEEDED, testHistoryCompareSucceeded, TEST_SUBMIT_ACCEPTED,
  TEST_SUBMIT_ATTEMPT_FINALIZED, TEST_SUBMISSION, testPreviewResult, TEST_UPLOAD_FULL,
  TEST_ARCHIVE_CANDIDATES, TEST_ARCHIVE_STARTED, TEST_ARCHIVE_RESULT, TEST_ARCHIVE_CONFIRM_APPEND,
  TEST_ARCHIVE_RESOLUTION_APPEND, ARCHIVE_PLAN_READY, ARCHIVE_PLAN_NEEDS_CONFIRMATION, TEST_REVIEW_APPLIED, validateSimulatedRequest,
} from "../src/features/dev/simulated-api";

type Schemas = components["schemas"];

interface FixtureManifest {
  bundle_digest: string;
  pairs: Array<{ pair_id: string }>;
}

const fixtures = new Map<string, { tar: Buffer; manifest: FixtureManifest }>();
const outputDirectory = process.env.GATEWAY_FE_SCREENSHOT_DIR;

async function loadFixture(name: string) {
  const cached = fixtures.get(name);
  if (cached) return cached;
  const tar = await readFile("src/test/fixtures/generated/" + name + ".tar");
  const manifestSize = Number.parseInt(tar.subarray(124, 136).toString("ascii").replace(/\0.*$/, "").trim(), 8);
  const manifest = JSON.parse(tar.subarray(512, 512 + manifestSize).toString("utf8")) as FixtureManifest;
  const result = { tar, manifest };
  fixtures.set(name, result);
  return result;
}

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((r) => { resolve = r; });
  return { promise, resolve };
}

async function installFixtureRoutes(page: Page, options: {
  truncateFirst?: boolean;
  fail?: boolean;
  slowPreview?: Promise<void>;
  noPermission?: boolean;
  timeoutFirstCompare?: Promise<void>;
  historyCompareForbidden?: boolean;
  failHistoryBundleAttempts?: number;
  historyCompareErrors?: number;
  historyCompareStatus?: (operationId: string, index: number) => Schemas["HistoryCompareResultResponse"];
  operationStatus?: (operationId: string, index: number) => Schemas["OperationResponse"];
  operationHold?: { operationId: string; onHold?: () => void; release: Promise<void> };
  operationStatusForbidden?: boolean;
  uploadHoldPolls?: number;
  submitIdentity?: "confirm";
  submitForbidden?: boolean;
  submitConflict?: "WORKSPACE_VERSION_CONFLICT";
  submitAttemptReadFails?: boolean;
  submitAttemptState?: Schemas["SubmitAttemptResponse"]["state"];
  workspaceSubmitAttemptId?: string;
  clearWorkspacePointer?: boolean;
  /** F2: queued workspace snapshots; each POST /v1/workspaces consumes one. */
  workspaceSequence?: Schemas["WorkspaceResponse"][];
  /** C2: hold the next POST /v1/workspaces in flight until released. */
  workspacePostHold?: { onHold: () => void; release: Promise<void> };
  operationReadFails?: boolean;
  workspaceReadFails?: boolean;
  operationById?: Record<string, Schemas["OperationResponse"]>;
  clearWorkspacePointerOnTerminal?: boolean;
  submitAborted?: boolean;
  submitTimeoutFirst?: boolean;
  uploadConflict?: "WORKSPACE_VERSION_CONFLICT" | "IDEMPOTENCY_CONFLICT";
  uploadConflictOnce?: "WORKSPACE_VERSION_CONFLICT";
  previewConflict?: "WORKSPACE_VERSION_CONFLICT" | "IDEMPOTENCY_CONFLICT";
  previewForbidden?: boolean;
  reviewForbidden?: boolean;
  reviewConflict?: "REVIEW_VERSION_CONFLICT" | "IDEMPOTENCY_CONFLICT" | "BASELINE_VERSION_CONFLICT" | "ARCHIVE_CLOSED";
  reviewTimeoutFirst?: boolean;
  archiveForbidden?: boolean;
  archiveConflict?: "BASELINE_VERSION_CONFLICT" | "ARCHIVE_AUDIT_VERSION_CONFLICT" | "IDEMPOTENCY_CONFLICT";
  archiveBlocked?: boolean;
  approvedSubmission?: boolean;
  submissionOne?: boolean;
} = {}) {
  const requests = new Map<string, number>();
  const apiRequests: Array<{ method: string; path: string; token: string | null; idempotencyKey: string | null; body: string }> = [];
  const apiResponses: Array<{ method: string; path: string; status: number; body: string }> = [];
  const rejectInvalidRequest = async (route: Route, request: PlaywrightRequest): Promise<boolean> => {
    const invalid = validateSimulatedRequest({ method: request.method(), url: new URL(request.url()), headers: request.headers(), body: request.postData() ?? "" });
    if (!invalid) return false;
    apiResponses.push({ method: request.method(), path: new URL(request.url()).pathname, status: 422, body: JSON.stringify(invalid) });
    await route.fulfill({ status: 422, contentType: "application/json", body: JSON.stringify(invalid) });
    return true;
  };
  const historyCompareCounts = new Map<string, number>();
  let historyBundleCalls = 0;
  const operationCounts = new Map<string, number>();
  const idempotentResponses = new Map<string, { response: Schemas["HistoryCompareAcceptResponse"]; ready: Promise<void>; finish: () => void; requestBody: string }>();
  let workspaceCallCount = 0;
  let workspacePointerCleared = false;
  let submitAttemptPointer: string | null = null;
  let workspaceSubmitSucceeded = false;
  let uploadConflictConsumed = false;

  await page.route("**/v1/workspaces", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const request = route.request();
    const path = new URL(request.url()).pathname;
    apiRequests.push({ method: request.method(), path, token: request.headers()["authorization"] ?? null, idempotencyKey: request.headers()["idempotency-key"] ?? null, body: request.postData() ?? "" });
    if (await rejectInvalidRequest(route, request)) return;
    const postHold = options.workspacePostHold;
    if (postHold) {
      options.workspacePostHold = undefined;
      postHold.onHold();
      await postHold.release;
    }
    if (options.workspaceReadFails) {
      const error = { code: "SERVICE_NOT_READY", message: "工作区服务暂时不可用" };
      apiResponses.push({ method: "POST", path, status: 503, body: JSON.stringify(error) });
      return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify(error) });
    }
    if (options.noPermission) {
      const error = SIMULATED_ERROR_RESPONSES.find((item) => item.route === path && item.method === "POST" && item.status === 403);
      if (!error) throw new Error("POST /v1/workspaces SCOPE_FORBIDDEN fixture missing");
      apiResponses.push({ method: "POST", path, status: error.status, body: JSON.stringify(error.body) });
      return route.fulfill({ status: error.status, contentType: "application/json", body: JSON.stringify(error.body) });
    }
    if (options.workspaceSequence?.length) {
      const next = options.workspaceSequence.shift()!;
      apiResponses.push({ method: "POST", path, status: 200, body: JSON.stringify(next) });
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(next) });
    }
    workspaceCallCount += 1;
    const response = workspaceCallCount === 1 ? WORKSPACE_CREATED : WORKSPACE_ALREADY_EXISTS;
    let body = uploadConflictConsumed && response === WORKSPACE_ALREADY_EXISTS
      ? { ...response.body, optimistic_version: 14 }
      : response.body;
    const attemptPointer = options.workspaceSubmitAttemptId ?? submitAttemptPointer;
    if (attemptPointer) {
      body = workspacePointerCleared || options.clearWorkspacePointer
        ? { ...body, active_submission_id: workspaceSubmitSucceeded && !options.clearWorkspacePointer ? "submission-1" : null, active_submit_attempt_id: null }
        : { ...body, active_submission_id: null, active_submit_attempt_id: attemptPointer };
    }
    apiResponses.push({ method: "POST", path, status: response.status, body: JSON.stringify(body) });
    return route.fulfill({ status: response.status, contentType: "application/json", body: JSON.stringify(body) });
  });

  await page.route("**/v1/history**", async (route) => {
    const request = route.request();
    if (request.method() !== "GET") return route.fallback();
    const url = new URL(request.url());
    let body: Schemas["HistoryListResponse"] = url.searchParams.has("cursor") ? HISTORY_PAGE_TWO : HISTORY_PAGE_ONE;
    if (!url.searchParams.has("cursor") && options.approvedSubmission) {
      body = { ...body, nodes: body.nodes.map((node) => node.ref_id === "fe2a-history-ref-2" ? { ...node, review_status: "APPROVED" as const, eligibility_note: undefined } : node) };
    }
    if (!url.searchParams.has("cursor") && options.submissionOne) {
      body = { ...body, nodes: [...body.nodes, {
        ref_kind: "submission" as const, ref_id: "submission-1", node_kind: "SUBMISSION" as const, review_status: "PENDING" as const,
        parent: { ref_kind: "baseline_node" as const, ref_id: "fe2a-history-ref-1" }, commit_id: "commit-submission-1",
        identity_exception: false, created_at: "2026-11-03T09:05:00Z",
      }] };
    }
    apiRequests.push({ method: "GET", path: url.pathname + url.search, token: request.headers()["authorization"] ?? null, idempotencyKey: null, body: "" });
    apiResponses.push({ method: "GET", path: url.pathname + url.search, status: 200, body: JSON.stringify(body) });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });

  const reviewReplayKeys = new Set<string>();
  let reviewStatus: Schemas["ReviewFactsResponse"]["status"] = "PENDING";
  // C5: once the ARCHIVE_CLOSED 409 has been served, the re-read review facts
  // carry the manual-close disposition so V12 can assert the §6.4 display.
  let closedServed = false;
  const factsFor = (submissionId: string): Schemas["ReviewFactsResponse"] => ({
    ...TEST_REVIEW_FACTS,
    submission_id: submissionId,
    status: closedServed ? "APPROVED" : reviewStatus,
    review_version: closedServed ? 6 : reviewStatus === "PENDING" ? 5 : 6,
    submission_disposition: closedServed ? {
      submission_id: submissionId,
      disposition: "CLOSED_NOT_ARCHIVED",
      source_kind: "MANUAL_CLOSE",
      result_id: null,
      closure: { closed_by: "reviewer", closed_at: "2026-11-03T10:00:00Z", reason: "不再需要该提交" },
    } : null,
  });
  await page.route("**/v1/submissions/*/review", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const submissionId = path.split("/")[3] ?? "";
    apiRequests.push({ method: "GET", path, token: request.headers()["authorization"] ?? null, idempotencyKey: null, body: "" });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(factsFor(submissionId)) });
  });
  await page.route("**/v1/submissions/*/review-events", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const submissionId = path.split("/")[3] ?? "";
    const key = request.headers()["idempotency-key"] ?? null;
    const body = request.postData() ?? "";
    apiRequests.push({ method: "POST", path, token: request.headers()["authorization"] ?? null, idempotencyKey: key, body });
    if (await rejectInvalidRequest(route, request)) return;
    if (options.reviewTimeoutFirst && key && !reviewReplayKeys.has(key)) {
      reviewReplayKeys.add(key);
      apiResponses.push({ method: "POST", path, status: 503, body: JSON.stringify({ code: "SERVICE_NOT_READY", message: "审核服务暂时不可用" }) });
      return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ code: "SERVICE_NOT_READY", message: "审核服务暂时不可用" }) });
    }
    if (options.reviewConflict) {
      const error = SIMULATED_ERROR_RESPONSES.find((item) => item.route === "/v1/submissions/{submission_id}/review-events" && item.method === "POST" && item.status === 409 && item.body.code === options.reviewConflict);
      if (!error) throw new Error("POST review-events conflict fixture missing");
      if (options.reviewConflict === "ARCHIVE_CLOSED") closedServed = true;
      apiResponses.push({ method: "POST", path, status: 409, body: JSON.stringify(error.body) });
      return route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify(error.body) });
    }
    if (options.reviewForbidden || options.noPermission) {
      const error = SIMULATED_ERROR_RESPONSES.find((item) => item.route === "/v1/submissions/{submission_id}/review-events" && item.method === "POST" && item.status === 403);
      if (!error) throw new Error("POST review-events SCOPE_FORBIDDEN fixture missing");
      apiResponses.push({ method: "POST", path, status: 403, body: JSON.stringify(error.body) });
      return route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify(error.body) });
    }
    const action = (JSON.parse(body) as Schemas["ApplyReviewRequest"]).action;
    reviewStatus = action === "APPROVE" ? "APPROVED" : action === "REJECT" ? "REJECTED" : "WITHDRAWN";
    const response = { ...TEST_REVIEW_APPLIED, submission_id: submissionId, status: reviewStatus, review_version: 6 };
    apiResponses.push({ method: "POST", path, status: 201, body: JSON.stringify(response) });
    return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(response) });
  });

  await page.route("**/v1/history-compares", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const request = route.request();
    const key = request.headers()["idempotency-key"] ?? "missing-key";
    const requestBody = request.postData() ?? "";
    apiRequests.push({ method: "POST", path: "/v1/history-compares", token: request.headers()["authorization"] ?? null, idempotencyKey: key, body: requestBody });
    if (await rejectInvalidRequest(route, request)) return;
    if (options.historyCompareForbidden) {
      const error = SIMULATED_ERROR_RESPONSES.find((item) => item.route === "/v1/history-compares" && item.method === "POST" && item.status === 403);
      if (!error) throw new Error("POST /v1/history-compares SCOPE_FORBIDDEN fixture missing");
      apiResponses.push({ method: "POST", path: "/v1/history-compares", status: error.status, body: JSON.stringify(error.body) });
      return route.fulfill({ status: error.status, contentType: "application/json", body: JSON.stringify(error.body) });
    }
    const previous = idempotentResponses.get(key);
    if (previous) {
      if (previous.requestBody !== requestBody) throw new Error("same Idempotency-Key was reused for another request body");
      await previous.ready;
      apiResponses.push({ method: "POST", path: "/v1/history-compares", status: 200, body: JSON.stringify(previous.response) });
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(previous.response) });
    }
    let finish = () => undefined;
    const ready = new Promise<void>((resolve) => { finish = resolve; });
    const accepted = { ...HISTORY_COMPARE_ACCEPT_BODY } satisfies Schemas["HistoryCompareAcceptResponse"];
    idempotentResponses.set(key, { response: accepted, ready, finish, requestBody });
    if (options.timeoutFirstCompare) await options.timeoutFirstCompare;
    finish();
    apiResponses.push({ method: "POST", path: "/v1/history-compares", status: 202, body: JSON.stringify(accepted) });
    return route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify(accepted) });
  });

  await page.route("**/v1/history-compares/*/bundle", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    apiRequests.push({ method: request.method(), path, token: request.headers()["authorization"] ?? null, idempotencyKey: null, body: "" });
    historyBundleCalls += 1;
    if (historyBundleCalls <= (options.failHistoryBundleAttempts ?? 0)) return route.abort();
    const fixture = await loadFixture("history-three-nodes");
    return fulfillBundle(route, fixture.tar, fixture.manifest, false);
  });

  await page.route(/\/v1\/history-compares\/[^/]+$/, async (route) => {
    const request = route.request();
    if (request.method() !== "GET") return route.fallback();
    const operationId = new URL(request.url()).pathname.split("/").at(-1) ?? "";
    const count = (historyCompareCounts.get(operationId) ?? 0) + 1;
    historyCompareCounts.set(operationId, count);
    apiRequests.push({ method: "GET", path: new URL(request.url()).pathname, token: request.headers()["authorization"] ?? null, idempotencyKey: null, body: "" });
    if (options.historyCompareErrors && count <= options.historyCompareErrors) {
      const error = SIMULATED_ERROR_RESPONSES.find((item) => item.route === "/v1/history-compares/{operation_id}" && item.method === "GET" && item.status === 503);
      if (!error) throw new Error("GET /v1/history-compares/{operation_id} 503 fixture missing");
      apiResponses.push({ method: "GET", path: new URL(request.url()).pathname, status: error.status, body: JSON.stringify(error.body) });
      return route.fulfill({ status: error.status, contentType: "application/json", body: JSON.stringify(error.body) });
    }
    const fixture = await loadFixture("history-three-nodes");
    const result = options.historyCompareStatus?.(operationId, count) ?? { ...testHistoryCompareSucceeded(fixture.manifest.bundle_digest), operation_id: operationId };
    apiResponses.push({ method: "GET", path: new URL(request.url()).pathname, status: 200, body: JSON.stringify(result) });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(result) });
  });

  await page.route(/\/v1\/operations\/[^/]+$/, async (route) => {
    const request = route.request();
    const operationId = new URL(request.url()).pathname.split("/").at(-1) ?? "";
    const count = (operationCounts.get(operationId) ?? 0) + 1;
    operationCounts.set(operationId, count);
    apiRequests.push({ method: "GET", path: new URL(request.url()).pathname, token: request.headers()["authorization"] ?? null, idempotencyKey: null, body: "" });
    if (options.operationStatusForbidden) {
      const error = SIMULATED_ERROR_RESPONSES.find((item) => item.route === "/v1/operations/{operation_id}" && item.method === "GET" && item.status === 403);
      if (!error) throw new Error("GET /v1/operations/{operation_id} SCOPE_FORBIDDEN fixture missing");
      apiResponses.push({ method: "GET", path: new URL(request.url()).pathname, status: error.status, body: JSON.stringify(error.body) });
      return route.fulfill({ status: error.status, contentType: "application/json", body: JSON.stringify(error.body) });
    }
    if (options.operationHold && operationId === options.operationHold.operationId) {
      options.operationHold.onHold?.();
      await options.operationHold.release;
    }
    if (options.operationReadFails) {
      const error = { code: "SERVICE_NOT_READY", message: "操作服务暂时不可用" };
      apiResponses.push({ method: "GET", path: new URL(request.url()).pathname, status: 503, body: JSON.stringify(error) });
      return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify(error) });
    }
    const result = options.operationById?.[operationId]
      ?? options.operationStatus?.(operationId, count)
      ?? (options.uploadHoldPolls && operationId.startsWith("preview-op") && count <= options.uploadHoldPolls
        ? { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId, status: "RUNNING" as const, completed_at: null }
        : { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId });
    if (options.clearWorkspacePointerOnTerminal && operationId === "submit-op-1" && (result.status === "SUCCEEDED" || result.status === "FAILED")) {
      workspacePointerCleared = true;
      workspaceSubmitSucceeded = result.status === "SUCCEEDED";
    }
    apiResponses.push({ method: "GET", path: new URL(request.url()).pathname, status: 200, body: JSON.stringify(result) });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(result) });
  });

  await page.route("**/v1/workspaces/*/upload-revisions", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const uploadBody = request.postDataBuffer()?.toString("utf8") ?? request.postData() ?? "";
    apiRequests.push({ method: "POST", path, token: request.headers()["authorization"] ?? null, idempotencyKey: request.headers()["idempotency-key"] ?? null, body: uploadBody });
    if (await rejectInvalidRequest(route, request)) return;
    if (options.uploadConflictOnce && !uploadConflictConsumed) {
      uploadConflictConsumed = true;
      const error = SIMULATED_ERROR_RESPONSES.find((item) => item.route === "/v1/workspaces/{workspace_id}/upload-revisions" && item.method === "POST" && item.status === 409 && item.body.code === options.uploadConflictOnce);
      if (!error) throw new Error("POST upload-revisions conflict fixture missing");
      apiResponses.push({ method: "POST", path, status: 409, body: JSON.stringify(error.body) });
      return route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify(error.body) });
    }
    if (options.uploadConflict) {
      const error = SIMULATED_ERROR_RESPONSES.find((item) => item.route === "/v1/workspaces/{workspace_id}/upload-revisions" && item.method === "POST" && item.status === 409 && item.body.code === options.uploadConflict);
      if (!error) throw new Error("POST upload-revisions conflict fixture missing");
      apiResponses.push({ method: "POST", path, status: 409, body: JSON.stringify(error.body) });
      return route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify(error.body) });
    }
    if (options.noPermission) {
      const error = SIMULATED_ERROR_RESPONSES.find((item) => item.route === "/v1/workspaces/{workspace_id}/upload-revisions" && item.method === "POST" && item.status === 403);
      if (!error) throw new Error("POST upload-revisions SCOPE_FORBIDDEN fixture missing");
      apiResponses.push({ method: "POST", path, status: 403, body: JSON.stringify(error.body) });
      return route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify(error.body) });
    }
    const response = { ...TEST_UPLOAD_FULL, workspace_id: "workspace-fe2b", generation: 3, optimistic_version: 13 };
    apiResponses.push({ method: "POST", path, status: 201, body: JSON.stringify(response) });
    return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(response) });
  });

  await page.route("**/v1/workspaces/*/preview-operations", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    apiRequests.push({ method: "POST", path, token: request.headers()["authorization"] ?? null, idempotencyKey: request.headers()["idempotency-key"] ?? null, body: request.postData() ?? "" });
    if (await rejectInvalidRequest(route, request)) return;
    if (options.previewForbidden) {
      const error = SIMULATED_ERROR_RESPONSES.find((item) => item.route === "/v1/workspaces/{workspace_id}/preview-operations" && item.method === "POST" && item.status === 403);
      if (!error) throw new Error("POST preview-operations SCOPE_FORBIDDEN fixture missing");
      apiResponses.push({ method: "POST", path, status: 403, body: JSON.stringify(error.body) });
      return route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify(error.body) });
    }
    if (options.previewConflict) {
      const error = SIMULATED_ERROR_RESPONSES.find((item) => item.route === "/v1/workspaces/{workspace_id}/preview-operations" && item.method === "POST" && item.status === 409 && item.body.code === options.previewConflict);
      if (!error) throw new Error("POST preview-operations conflict fixture missing");
      apiResponses.push({ method: "POST", path, status: 409, body: JSON.stringify(error.body) });
      return route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify(error.body) });
    }
    const response = { operation_id: "preview-op-1", workspace_id: "workspace-fe2b", upload_revision_id: "upload-1", generation: 3, status: "QUEUED" as const };
    apiResponses.push({ method: "POST", path, status: 202, body: JSON.stringify(response) });
    return route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify(response) });
  });

  await page.route("**/v1/workspaces/*/preview-results/*", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const previewResultId = path.split("/").at(-1) ?? "";
    apiRequests.push({ method: "GET", path, token: request.headers()["authorization"] ?? null, idempotencyKey: null, body: "" });
    const fixture = await loadFixture("preview-full");
    const identityPairs = options.submitIdentity === "confirm" ? [
      { pair_id: "pair-dataset", applicability: "APPLICABLE" as const, status: "DIFFERENT_PROJECT" as const, mode: "DATASET_REPLACEMENT" as const, assessment_ref: "assessment-1", assessment_digest: "sha256:assessment-1" },
      { pair_id: "pair-unverifiable", applicability: "APPLICABLE" as const, status: "UNVERIFIABLE" as const, mode: "DETAILED" as const, assessment_ref: "assessment-2", assessment_digest: "sha256:assessment-2" },
    ] : [];
    const response = {
      ...testPreviewResult(fixture.manifest.bundle_digest), preview_result_id: previewResultId, workspace_id: "workspace-fe2b",
      upload_revision_id: "upload-1", generation: 3, operation_id: "preview-op-1", business_baseline_node_id: "fe2a-history-ref-1",
      business_baseline_commit_id: "commit-baseline-1", identity_pairs: identityPairs,
    };
    apiResponses.push({ method: "GET", path, status: 200, body: JSON.stringify(response) });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(response) });
  });

  const submitReplayKeys = new Set<string>();
  await page.route("**/v1/workspaces/*/submit-attempts", async (route) => {
    const request = route.request();
    const key = request.headers()["idempotency-key"] ?? null;
    const path = new URL(request.url()).pathname;
    apiRequests.push({ method: "POST", path, token: request.headers()["authorization"] ?? null, idempotencyKey: request.headers()["idempotency-key"] ?? null, body: request.postData() ?? "" });
    if (await rejectInvalidRequest(route, request)) return;
    if (options.submitTimeoutFirst && key && !submitReplayKeys.has(key)) {
      submitReplayKeys.add(key);
      const timeout = { code: "SERVICE_NOT_READY", message: "提交服务暂时不可用" };
      apiResponses.push({ method: "POST", path, status: 503, body: JSON.stringify(timeout) });
      return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify(timeout) });
    }
    if (options.submitConflict) {
      const error = SIMULATED_ERROR_RESPONSES.find((item) => item.route === "/v1/workspaces/{workspace_id}/submit-attempts" && item.method === "POST" && item.status === 409 && item.body.code === options.submitConflict);
      if (!error) throw new Error("POST submit-attempts WORKSPACE_VERSION_CONFLICT fixture missing");
      apiResponses.push({ method: "POST", path, status: 409, body: JSON.stringify(error.body) });
      return route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify(error.body) });
    }
    if (options.submitForbidden) {
      const error = SIMULATED_ERROR_RESPONSES.find((item) => item.route === "/v1/workspaces/{workspace_id}/submit-attempts" && item.method === "POST" && item.status === 403);
      if (!error) throw new Error("POST submit-attempts SCOPE_FORBIDDEN fixture missing");
      apiResponses.push({ method: "POST", path, status: 403, body: JSON.stringify(error.body) });
      return route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify(error.body) });
    }
    const response = { ...TEST_SUBMIT_ACCEPTED, operation_id: "submit-op-1", workspace_id: "workspace-fe2b", preview_result_id: "preview-full", generation: 3 };
    if (options.clearWorkspacePointerOnTerminal && !submitAttemptPointer) submitAttemptPointer = response.submit_attempt_id;
    apiResponses.push({ method: "POST", path, status: 202, body: JSON.stringify(response) });
    return route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify(response) });
  });

  await page.route("**/v1/workspaces/*/submit-attempts/*", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    apiRequests.push({ method: "GET", path, token: request.headers()["authorization"] ?? null, idempotencyKey: null, body: "" });
    if (options.submitAttemptReadFails) {
      const error = { code: "SERVICE_NOT_READY", message: "提交服务暂时不可用" };
      apiResponses.push({ method: "GET", path, status: 503, body: JSON.stringify(error) });
      return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify(error) });
    }
    const attemptState = options.submitAttemptState;
    const response = attemptState === "ABORTED"
      ? { ...TEST_SUBMIT_ATTEMPT_FINALIZED, operation_id: "submit-op-1", state: "ABORTED" as const, submission_id: null, abort_code: "IMPORT_REJECTED" as const }
      : attemptState
        ? { ...TEST_SUBMIT_ATTEMPT_FINALIZED, operation_id: "submit-op-1", workspace_id: "workspace-fe2b", preview_result_id: "preview-full", generation: 3, state: attemptState }
        : options.submitAborted
          ? { ...TEST_SUBMIT_ATTEMPT_FINALIZED, operation_id: "submit-op-1", state: "ABORTED" as const, submission_id: null, abort_code: "IMPORT_REJECTED" as const }
          : { ...TEST_SUBMIT_ATTEMPT_FINALIZED, operation_id: "submit-op-1", workspace_id: "workspace-fe2b", preview_result_id: "preview-full", generation: 3 };
    apiResponses.push({ method: "GET", path, status: 200, body: JSON.stringify(response) });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(response) });
  });

  await page.route("**/v1/workspaces/*/submissions/*", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    apiRequests.push({ method: "GET", path, token: request.headers()["authorization"] ?? null, idempotencyKey: null, body: "" });
    apiResponses.push({ method: "GET", path, status: 200, body: JSON.stringify(TEST_SUBMISSION) });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(TEST_SUBMISSION) });
  });

  let archivePreviewCalls = 0;
  const acceptedAnomalyResolutions = new Map<string, { sequence: number; reason: string }>();
  let anomalyResolutionSequence = 10;
  await page.route("**/v1/archive-candidates", async (route) => {
    // review_version matches the scenario Review GET version (both come from
    // the review projection, §5.3); the review stub below reports 5/6.
    const candidates = { ...TEST_ARCHIVE_CANDIDATES, candidates: [{ submission_id: options.approvedSubmission ? "fe2a-history-ref-2" : "submission-1", expected_candidate_digest: "sha256:candidate", review_version: 5 }] };
    apiRequests.push({ method: "GET", path: "/v1/archive-candidates", token: route.request().headers()["authorization"] ?? null, idempotencyKey: null, body: "" });
    apiResponses.push({ method: "GET", path: "/v1/archive-candidates", status: 200, body: JSON.stringify(candidates) });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(candidates) });
  });
  await page.route("**/v1/archive-plan-preview", async (route) => {
    apiRequests.push({ method: "POST", path: "/v1/archive-plan-preview", token: route.request().headers()["authorization"] ?? null, idempotencyKey: null, body: route.request().postData() ?? "" });
    // Backend rule (ArchiveSelectedRefRequest extra="forbid"): extra selected keys → 422.
    if (await rejectInvalidRequest(route, route.request())) return;
    if (options.archiveForbidden) {
      const error = SIMULATED_ERROR_RESPONSES.find((item) => item.route === "/v1/archive-plan-preview" && item.method === "POST" && item.status === 403);
      if (!error) throw new Error("POST archive-plan-preview SCOPE_FORBIDDEN fixture missing");
      apiResponses.push({ method: "POST", path: "/v1/archive-plan-preview", status: 403, body: JSON.stringify(error.body) });
      return route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify(error.body) });
    }
    archivePreviewCalls += 1;
    // 非阻断分支的异常目标提交跟随 current candidate（approvedSubmission 时为 fe2a-history-ref-2）；
    // 阻断分支沿用 ARCHIVE_PLAN_NEEDS_CONFIRMATION 中的 submission-1，仅用于演示阻断原因。
    const candidateId = options.approvedSubmission ? "fe2a-history-ref-2" : "submission-1";
    if (options.archiveBlocked) {
      const blocked: Schemas["PreviewArchivePlanResponse"] = {
        ...ARCHIVE_PLAN_NEEDS_CONFIRMATION,
        selected: { submission_id: candidateId, expected_candidate_digest: "sha256:candidate" },
        blockers: ["ACTIVE_SUBMIT_ATTEMPT"],
        can_start: false,
      };
      apiResponses.push({ method: "POST", path: "/v1/archive-plan-preview", status: 200, body: JSON.stringify(blocked) });
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(blocked) });
    }
    const withAcceptedAnomalies = (anomalies: Schemas["PreviewArchivePlanResponse"]["anomalies"]) => anomalies.map((anomaly) => {
      const accepted = acceptedAnomalyResolutions.get(anomaly.subject_digest);
      return accepted ? { ...anomaly, resolution_status: "ACCEPTED" as const, latest_sequence: accepted.sequence, accepted_by: "owner", accepted_at: "2026-11-03T09:00:00Z", reason: accepted.reason } : anomaly;
    });
    const identityAnomaly: Schemas["PreviewArchivePlanResponse"]["anomalies"][number] = { subject_kind: "PROJECT_IDENTITY_EXCEPTION", issue_code: "PROJECT_IDENTITY_EXCEPTION", target_submission_id: candidateId, target_candidate_digest: "sha256:candidate", subject_digest: "sha256:anomaly", accepted_at: null, accepted_by: null, affected_submission_ids: [candidateId], details: {}, detected_status: "UNEXPLAINED", latest_sequence: 0, reason: null, relations: [], resolution_status: "UNRESOLVED", side: null };
    const response: Schemas["PreviewArchivePlanResponse"] = archivePreviewCalls >= 3 ? {
      ...ARCHIVE_PLAN_READY,
      selected: { submission_id: candidateId, expected_candidate_digest: "sha256:candidate" },
      anomalies: withAcceptedAnomalies(ARCHIVE_PLAN_READY.anomalies),
      dispositions: [{ submission_id: candidateId, disposition: "ARCHIVED_BASELINE" }],
      workspace_releases: [{ submission_id: candidateId, workspace_id: "workspace-fe2b" }],
    } : {
      // Backend rule (application/archive/queries.py:132): before any confirmation is appended,
      // confirmation_requirements is non-empty and audit is invalid, so can_start must be false.
      ...ARCHIVE_PLAN_NEEDS_CONFIRMATION,
      selected: { submission_id: candidateId, expected_candidate_digest: "sha256:candidate" },
      confirmation_requirements: ["sha256:selection-subject"],
      anomalies: withAcceptedAnomalies([identityAnomaly]),
      dispositions: [{ submission_id: candidateId, disposition: "ARCHIVED_BASELINE" }],
    };
    apiResponses.push({ method: "POST", path: "/v1/archive-plan-preview", status: 200, body: JSON.stringify(response) });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(response) });
  });
  await page.route("**/v1/archive-audit-events**", async (route) => {
    const request = route.request();
    if (await rejectInvalidRequest(route, request)) return;
    apiResponses.push({ method: "GET", path: "/v1/archive-audit-events", status: 200, body: JSON.stringify({ events: [], next_after_sequence: null }) });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ events: [], next_after_sequence: null }) });
  });
  await page.route("**/v1/archive-confirmations", async (route) => {
    const request = route.request();
    apiRequests.push({ method: "POST", path: "/v1/archive-confirmations", token: request.headers()["authorization"] ?? null, idempotencyKey: request.headers()["idempotency-key"] ?? null, body: request.postData() ?? "" });
    // Backend rule (http/routes/archives.py:116): missing Idempotency-Key → 422.
    if (await rejectInvalidRequest(route, request)) return;
    apiResponses.push({ method: "POST", path: "/v1/archive-confirmations", status: 201, body: JSON.stringify(TEST_ARCHIVE_CONFIRM_APPEND) });
    return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(TEST_ARCHIVE_CONFIRM_APPEND) });
  });
  await page.route("**/v1/archive-anomaly-resolutions", async (route) => {
    const request = route.request();
    apiRequests.push({ method: "POST", path: "/v1/archive-anomaly-resolutions", token: request.headers()["authorization"] ?? null, idempotencyKey: request.headers()["idempotency-key"] ?? null, body: request.postData() ?? "" });
    // Backend rule (http/routes/archives.py:159): missing Idempotency-Key → 422.
    if (await rejectInvalidRequest(route, request)) return;
    try {
      const parsed = JSON.parse(request.postData() ?? "{}") as { subject_digest?: string; reason?: string; action?: string };
      if (parsed.action !== "REVOKE" && parsed.subject_digest) {
        anomalyResolutionSequence += 1;
        acceptedAnomalyResolutions.set(parsed.subject_digest, { sequence: anomalyResolutionSequence, reason: parsed.reason ?? "" });
      } else if (parsed.subject_digest) {
        acceptedAnomalyResolutions.delete(parsed.subject_digest);
      }
    } catch {
      // Malformed bodies fall through to the success below; shape checks live in the unit tests.
    }
    apiResponses.push({ method: "POST", path: "/v1/archive-anomaly-resolutions", status: 201, body: JSON.stringify(TEST_ARCHIVE_RESOLUTION_APPEND) });
    return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(TEST_ARCHIVE_RESOLUTION_APPEND) });
  });
  await page.route("**/v1/archives", async (route) => {
    const request = route.request();
    apiRequests.push({ method: "POST", path: "/v1/archives", token: request.headers()["authorization"] ?? null, idempotencyKey: request.headers()["idempotency-key"] ?? null, body: request.postData() ?? "" });
    // Backend rule (http/routes/archives.py:232): missing Idempotency-Key → 422.
    if (await rejectInvalidRequest(route, request)) return;
    if (options.archiveConflict) {
      const error = SIMULATED_ERROR_RESPONSES.find((item) => item.route === "/v1/archives" && item.method === "POST" && item.status === 409 && item.body.code === options.archiveConflict);
      if (!error) throw new Error("POST archives conflict fixture missing");
      apiResponses.push({ method: "POST", path: "/v1/archives", status: 409, body: JSON.stringify(error.body) });
      return route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify(error.body) });
    }
    apiResponses.push({ method: "POST", path: "/v1/archives", status: 201, body: JSON.stringify(TEST_ARCHIVE_STARTED) });
    return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(TEST_ARCHIVE_STARTED) });
  });
  await page.route("**/v1/archives/*", async (route) => {
    const archivedId = options.approvedSubmission ? "fe2a-history-ref-2" : "submission-1";
    const response = { ...TEST_ARCHIVE_RESULT, selected_submission_id: archivedId, dispositions: [{ submission_id: archivedId, disposition: "ARCHIVED_BASELINE" }] };
    apiResponses.push({ method: "GET", path: "/v1/archives/archive-1", status: 200, body: JSON.stringify(response) });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(response) });
  });

  const fulfillBundle = async (route: Route, tar: Buffer, manifest: FixtureManifest, truncate: boolean) => route.fulfill({
    status: 200,
    contentType: "application/x-tar",
    headers: { ETag: manifest.bundle_digest, "Content-Length": String(tar.byteLength) },
    body: truncate ? tar.subarray(0, Math.floor(tar.byteLength / 2)) : tar,
  });
  const routeBundle = async (route: Route, fixtureName: string) => {
    const count = (requests.get(fixtureName) ?? 0) + 1;
    requests.set(fixtureName, count);
    if (fixtureName === "preview-workbench-normal" && options.slowPreview) await options.slowPreview;
    if (options.fail) {
      const error = SIMULATED_ERROR_RESPONSES.find((item) => item.route.endsWith("/bundle") && item.status === 503);
      if (!error) throw new Error("preview bundle SERVICE_NOT_READY fixture missing");
      await route.fulfill({ status: error.status, contentType: "application/json", body: JSON.stringify(error.body) });
      return;
    }
    const fixture = await loadFixture(fixtureName);
    await fulfillBundle(route, fixture.tar, fixture.manifest, options.truncateFirst === true && count === 1);
  };
  await page.route("**/v1/workspaces/*/preview-results/*/bundle", async (route) => {
    const previewResultId = new URL(route.request().url()).pathname.split("/").at(-2) ?? "";
    const fixtureName = previewResultId === "preview-1" ? "preview-full" : previewResultId;
    await routeBundle(route, fixtureName);
  });
  return { requests, apiRequests, apiResponses };
}

function browseUrl(mode: "PREVIEW" | "REVIEW" | "HISTORY", fixtureName: string, extra: Record<string, string> = {}): string {
  const params = new URLSearchParams({ page: "compare", mode, ...extra });
  if (mode === "PREVIEW") {
    params.set("workspaceId", "ws-1");
    params.set("previewResultId", fixtureName === "preview-full" ? "preview-1" : fixtureName);
  } else if (mode === "REVIEW") params.set("submissionId", "fe2a-history-ref-2");
  else {
    params.set("operationId", "history-compare-fe2b-1");
    params.set("operationKind", "history-compare");
  }
  return "/?" + params.toString();
}

async function waitForBrowse(page: Page) {
  await expect(page.getByRole("heading", { name: "差异浏览", level: 1 })).toBeVisible();
  await page.locator(".grid-frame, .compare-error").first().waitFor({ state: "visible", timeout: 15000 });
  const error = page.locator(".compare-error");
  if (await error.isVisible()) {
    const code = await error.locator("p code").innerText();
    const details = await error.locator("details pre").textContent();
    throw new Error(`browse failed at ${page.url()}: ${code}: ${details ?? "no details"}`);
  }
  await expect(page.locator(".grid-frame").first()).toBeVisible();
  const appGrid = page.locator(".grid-frame[data-rendered]").first();
  if (await appGrid.count()) {
    await expect(appGrid).toHaveAttribute("data-rendered", "true");
    await expect(appGrid).toHaveAttribute("data-first-cell-content", /.+/);
    await expect(appGrid.locator("canvas").first()).toBeVisible();
  } else {
    await expect(page.locator(".grid-frame canvas").first()).toBeVisible();
  }
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
}

async function expectNoHorizontalOverflow(page: Page) {
  const metrics = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }));
  expect(metrics.scrollWidth, `页面横向溢出：scrollWidth=${metrics.scrollWidth} innerWidth=${metrics.innerWidth}`).toBeLessThanOrEqual(metrics.innerWidth);
}

async function expectHeaderBreadcrumbVisible(page: Page) {
  const breadcrumb = page.locator(".compare-header .breadcrumb");
  await expect(breadcrumb).toBeVisible();
  const box = await breadcrumb.boundingBox();
  expect(box?.width ?? 0).toBeGreaterThan(0);
}

async function screenshot(page: Page, name: string, width: number) {
  await page.setViewportSize({ width, height: 1080 });
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  const appGrid = page.locator(".grid-frame[data-rendered]").first();
  if (await appGrid.count()) {
    await expect(appGrid).toHaveAttribute("data-rendered", "true");
    await expect(appGrid).toHaveAttribute("data-first-cell-content", /.+/);
    await expect(appGrid.locator("canvas").first()).toBeVisible();
  }
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  // N14: the overflow assertion runs in every mode, not only when screenshots
  // are being saved.
  await expectNoHorizontalOverflow(page);
  if (!outputDirectory) return;
  await mkdir(outputDirectory, { recursive: true });
  await page.screenshot({ path: join(outputDirectory, name + "-" + width + ".png"), fullPage: true, animations: "disabled" });
}

async function waitForGridPaint(page: Page, tabKey: string) {
  const appGrid = page.locator(`.grid-frame[data-tab-key="${tabKey}"]`);
  await expect(appGrid).toHaveCount(1);
  await expect(appGrid).toHaveAttribute("data-rendered", "true");
  await expect(appGrid).toHaveAttribute("data-first-cell-content", /.+/);
  await expect(appGrid.locator("canvas").first()).toBeVisible();
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
}

async function screenshotHeader(page: Page, name: string, width: number) {
  await page.setViewportSize({ width, height: 1080 });
  await expectNoHorizontalOverflow(page);
  if (!outputDirectory) return;
  await mkdir(outputDirectory, { recursive: true });
  await page.locator(".compare-header").screenshot({ path: join(outputDirectory, name + "-" + width + ".png"), animations: "disabled" });
}

async function clickFormulaCell(page: Page) {
  const grid = page.locator(".grid-frame[data-formula-column-offset]").first();
  const bounds = await grid.boundingBox();
  const offset = Number(await grid.getAttribute("data-formula-column-offset"));
  const width = Number(await grid.getAttribute("data-formula-column-width"));
  if (!bounds || !Number.isFinite(offset) || !Number.isFinite(width)) throw new Error("formula column has no grid bounds");
  await page.mouse.click(bounds.x + offset + width / 2, bounds.y + 38 + 19);
}

async function hoverChangedTelemetryValue(page: Page) {
  const grid = page.locator('.grid-frame[data-tab-key="table"]');
  const bounds = await grid.boundingBox();
  if (!bounds) throw new Error("workbench telemetry grid has no bounds");
  const tooltip = page.getByRole("tooltip");
  const rowsVisible = Math.max(1, Math.floor((bounds.height - 38) / 38));
  const valueColumnCandidates = [50, 100, 150, 200, 250, 300];
  for (let row = 0; row < rowsVisible; row += 1) {
    const y = bounds.y + 38 + row * 38 + 19;
    for (const fromRight of valueColumnCandidates) {
      await page.mouse.move(bounds.x + bounds.width - fromRight, y);
      try {
        await expect(tooltip).toContainText("字段变更", { timeout: 100 });
        return;
      } catch {
        // Keep scanning visible telemetry cells until the fixture's changed value is hovered.
      }
    }
  }
  throw new Error("could not hover a changed value in the visible telemetry rows");
}

test("Preview、审核与历史浏览保留 URL 状态，并覆盖 S3/S4 页面", async ({ page }) => {
  const { requests } = await installFixtureRoutes(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(browseUrl("PREVIEW", "preview-full", { pair: "baseline_to_initial", changed: "1" }));
  await waitForBrowse(page);

  await expect(page.locator(".view-tabs small")).toHaveText(["更新", "更新"]);
  const firstPreviewView = page.locator(".view-tabs [role=tab]").first();
  await expect(firstPreviewView).toHaveAttribute("title", /2 张表有比较提示/);
  await expect(firstPreviewView).not.toHaveAttribute("title", /降级比较/);
  await expect(page.locator(".mode-tag")).toHaveText("上传");
  await expect(page.getByRole("navigation", { name: "位置" })).toContainText("原始组态视图");
  await expect(page.locator(".mode-tabs")).toHaveCount(0);
  await expect(page.getByRole("radio", { name: "User" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("tab", { name: /原始组态视图/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: /本次组态视图/ })).toBeVisible();
  await page.getByRole("tab", { name: /本次组态视图/ }).click();
  await expect(page).toHaveURL(/pair=initial_to_modified/);
  expect(new URL(page.url()).searchParams.get("view")).toBeNull();
  await page.reload();
  await waitForBrowse(page);
  expect(new URL(page.url()).searchParams.get("pair")).toBe("initial_to_modified");
  await page.getByRole("tab", { name: /原始组态视图/ }).click();
  await expect(page).toHaveURL(/pair=baseline_to_initial/);
  await expect(page.locator(".distribution-strip")).toBeVisible();
  // F12: a single-table item opens its table directly; the whole-device item
  // is a normal navigation entry instead of the retired diagnostic button.
  await page.locator('.nav-item[data-item-key="device:table"] .nav-item__button').click();
  await waitForGridPaint(page, "table");
  await screenshot(page, "s3-workbench-upload", 1920);
  await screenshotHeader(page, "s3-header-upload", 1920);
  await screenshot(page, "s4-grid-main", 1920);
  const mainGrid = page.locator(".grid-frame").first();
  const gridBounds = await mainGrid.boundingBox();
  if (!gridBounds) throw new Error("comparison grid has no bounding box");
  await page.mouse.move(gridBounds.x + 300, gridBounds.y + 133);
  await expect(page.getByRole("tooltip")).toContainText("字段变更");
  await expect(page.getByRole("tooltip")).toContainText("测控装置（升级）");
  await screenshot(page, "s4-grid-hover", 1920);
  await screenshot(page, "s4-grid-hover", 1280);
  await page.setViewportSize({ width: 1920, height: 1080 });

  await page.goto(browseUrl("PREVIEW", "preview-full", { pair: "baseline_to_initial", changed: "1", debug: "1" }));
  await waitForBrowse(page);
  expect(new URL(page.url()).searchParams.get("pair")).toBe("baseline_to_initial");
  await page.locator('.nav-item[data-item-key="device:table"] .nav-item__button').click();
  await waitForGridPaint(page, "table");
  await expect(page.getByRole("radio", { name: "Debug" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("radio", { name: "User" })).toHaveAttribute("aria-checked", "false");
  await screenshot(page, "s4-grid-debug", 1920);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("button", { name: "收起导航" }).click();
  await screenshot(page, "s4-grid-debug", 1280);
  await page.getByRole("radio", { name: "User" }).click();
  await expect(page.getByRole("radio", { name: "User" })).toHaveAttribute("aria-checked", "true");
  await screenshot(page, "s3-workbench-upload", 1280);
  await screenshotHeader(page, "s3-header-upload", 1280);
  await screenshot(page, "s4-grid-main", 1280);

  await page.getByRole("button", { name: "展开导航" }).click();
  const search = page.getByRole("textbox", { name: "搜索组、节点或页签" });
  await search.fill("复合信号");
  await expect(page.getByRole("button", { name: /复合信号虚装置/ })).toBeVisible();
  await page.locator(".sidebar-toolbar button").click();
  await expect(page).not.toHaveURL(/changed=1/);
  await page.locator(".sidebar-toolbar button").click();
  await expect(page).toHaveURL(/changed=1/);
  await page.getByRole("button", { name: "下一个变更" }).click();
  await expect(page).toHaveURL(/change=1/);
  await page.getByRole("radio", { name: "Debug" }).click();
  await expect.poll(() => new URL(page.url()).searchParams.get("q")).toBe("复合信号");
  const stateBeforeReload = new URL(page.url());
  expect(stateBeforeReload.searchParams.get("view")).toBeNull();
  expect(stateBeforeReload.searchParams.get("pair")).toBe("baseline_to_initial");
  expect(stateBeforeReload.searchParams.get("tab")).toBe("table");
  expect(stateBeforeReload.searchParams.get("changed")).toBe("1");
  expect(stateBeforeReload.searchParams.get("debug")).toBe("1");
  const requestCountBeforeReload = requests.get("preview-full") ?? 0;
  await page.reload();
  await waitForBrowse(page);
  const reloadedSearch = page.getByRole("textbox", { name: "搜索组、节点或页签" });
  if (!(await reloadedSearch.isVisible())) await page.getByRole("button", { name: "展开导航" }).click();
  await expect(reloadedSearch).toHaveValue("复合信号");
  await expect(page.getByRole("radio", { name: "Debug" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("radio", { name: "User" })).toHaveAttribute("aria-checked", "false");
  expect(new URL(page.url()).searchParams.get("node")).toBe(stateBeforeReload.searchParams.get("node"));
  expect(new URL(page.url()).searchParams.get("change")).toBe("1");
  expect(requests.get("preview-full")).toBe(requestCountBeforeReload);

  await page.getByRole("textbox", { name: "搜索组、节点或页签" }).fill("");
  await page.getByRole("button", { name: "显示全部" }).click();
  await page.getByRole("button", { name: /更多/ }).click();
  await expect(page.locator(".overflow-menu")).toBeVisible();
  await screenshot(page, "tab-overflow", 1920);
  await screenshot(page, "tab-overflow", 1280);
  await page.locator(".overflow-menu").getByRole("button", { name: /b1_n1_iec104_syx_list/ }).click();
  await expect(page.locator(".table-heading h2")).toHaveText("b1_n1_iec104_syx_list");
  expect(new URL(page.url()).searchParams.get("tab")).toBe("b1_n1_iec104_syx_list");
  await page.goto(browseUrl("REVIEW", "history-three-nodes", { pair: "left_to_middle" }));
  await waitForBrowse(page);
  expect(new URL(page.url()).searchParams.get("mode")).toBe("REVIEW");
  await expect(page.locator(".mode-tag")).toHaveText("审核");

  await page.goto(browseUrl("HISTORY", "history-three-nodes", { pair: "left_to_middle" }));
  await waitForBrowse(page);
  await expect(page.locator(".mode-tag")).toHaveText("历史比较 · 只读");
  await expect(page.getByRole("tab", { name: "节点 2 → 节点 3" })).toBeVisible();
  await screenshotHeader(page, "s3-header-history", 1920);
  await screenshotHeader(page, "s3-header-history", 1280);
  await page.getByRole("tab", { name: "节点 2 → 节点 3" }).click();
  await expect(page).toHaveURL(/pair=middle_to_right/);

  await page.goto(browseUrl("PREVIEW", "preview-full", { pair: "initial_to_modified" }));
  await waitForBrowse(page);
  await page.getByRole("button", { name: "复合信号虚装置" }).click();
  await expect(page.locator(".table-heading h2")).toHaveText("composite_signal_point");
  await waitForGridPaint(page, "table");
  await clickFormulaCell(page);
  const formula = page.getByRole("dialog", { name: "公式查看" });
  await expect(formula).toBeVisible();
  await expect(formula.getByText("改前公式", { exact: true })).toBeVisible();
  await expect(formula).toContainText("公式已改");
  await expect(formula).toContainText("| 嵌套命名表达式 =");
  await expect(formula).toContainText("+ （* 分组）");
  await expect(formula).toContainText("线路保护装置 A:线路电流");
  await expect(formula).toContainText("Device 999:未映射测点");
  await expect(formula.locator(".formula-line").filter({ hasText: "| - 线路保护装置 A:线路电流" }).last()).toBeInViewport();
  await expect(formula).not.toContainText("kind:");
  await screenshot(page, "formula-preview", 1920);
  await screenshot(page, "formula-preview", 1280);
  await formula.getByRole("button", { name: "关闭公式" }).click();
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(browseUrl("HISTORY", "history-three-nodes", { pair: "left_to_middle", node: "device:composite", tab: "table" }));
  await waitForBrowse(page);
  expect(new URL(page.url()).searchParams.get("pair")).toBe("left_to_middle");
  expect(new URL(page.url()).searchParams.get("tab")).toBe("table");
  await expect(page.locator(".table-heading h2")).toHaveText("composite_signal_point");
  await waitForGridPaint(page, "table");
  await clickFormulaCell(page);
  const historyFormula = page.getByRole("dialog", { name: "公式查看" });
  await expect(historyFormula.getByText("改前公式", { exact: true })).toBeVisible();
  await expect(historyFormula.getByText("改后公式", { exact: true })).toBeVisible();
  await expect(historyFormula.locator(".formula-line").filter({ hasText: "| - 线路保护装置 A:线路电流" }).last()).toBeInViewport();
  await screenshot(page, "formula-history", 1920);
  await screenshot(page, "formula-history", 1280);
});

test("数据集替换显示身份结论与两侧表", async ({ page }) => {
  await installFixtureRoutes(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(browseUrl("PREVIEW", "preview-replacement", { pair: "initial_to_modified" }));
  await waitForBrowse(page);
  // The replacement pair carries no risk report (facts are null per side), so
  // the mode notice takes the place of the per-view risk badge.
  await expect(page.locator(".pair-diagnostic-strip")).toContainText("识别为不同数据集");
  await expect(page.getByText("身份结论：不同项目")).toBeVisible();
  await expect(page.locator(".replacement-side h3")).toHaveCount(2);
  await expect(page.locator(".replacement-side h3").first()).toContainText("device");
  await expect(page.locator(".replacement-summary")).toContainText("替换前：");
  await page.locator(".replacement-side-toggle button").nth(1).click();
  await expect(page.locator(".replacement-side.is-inactive")).toHaveCount(1);
  await screenshot(page, "dataset-replacement-browse", 1920);
  await screenshot(page, "dataset-replacement-browse", 1280);

});

test("覆盖 bundle 下载截断重试、加载骨架、错误页和五级风险语义色", async ({ page }) => {
  const { requests } = await installFixtureRoutes(page, { truncateFirst: true });
  await page.goto(browseUrl("PREVIEW", "preview-full"));
  await waitForBrowse(page);
  expect(requests.get("preview-full")).toBe(2);

  await page.goto("/?design-system=1");
  for (const label of ["高风险", "中高风险", "中低风险", "低风险", "未知风险"]) await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
  await screenshot(page, "s4-semantic-tokens", 1920);
  await screenshot(page, "s4-semantic-tokens", 1280);
});

test("加载中显示骨架，bundle 接口失败显示可重试错误页", async ({ page }) => {
  const holdPreview = deferred();
  await installFixtureRoutes(page, { slowPreview: holdPreview.promise });
  await page.goto(browseUrl("PREVIEW", "preview-workbench-normal"), { waitUntil: "domcontentloaded" });
  await expect(page.getByLabel("下载并校验比较结果")).toBeVisible();
  await screenshot(page, "loading-skeleton", 1920);
  await screenshot(page, "loading-skeleton", 1280);
  holdPreview.resolve();
  await waitForBrowse(page);

  await page.unrouteAll({ behavior: "wait" });
  await installFixtureRoutes(page, { fail: true });
  await page.goto(browseUrl("PREVIEW", "preview-workbench-normal"));
  await expect(page.getByRole("alert")).toContainText("SERVICE_NOT_READY");
  await expect(page.getByRole("alert")).toContainText("比较结果暂时不可用");
  await expect(page.getByText("已连接", { exact: true })).toHaveCount(0);
  await screenshot(page, "bundle-error", 1920);
  await screenshot(page, "bundle-error", 1280);
});

test("正式工作台呈现 History、四列表格、操作说明与 1280/1920 详情面板", async ({ page }) => {
  const { apiRequests, apiResponses } = await installFixtureRoutes(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "组态树", level: 1 })).toBeVisible();
  await expect(page.locator(".workspace-table thead th")).toHaveCount(4);
  await expect(page.locator(".workspace-page")).toHaveClass(/details-open/);
  await expect(page.locator(".workspace-context-bar")).toContainText("工作区 gateway-17");
  await expect(page.locator(".workspace-context-bar").getByRole("button", { name: "原始组态备份" })).toBeEnabled();
  await expect(page.locator(".workspace-context-bar").getByRole("button", { name: "本次归档组态" })).toBeEnabled();
  await expect(page.locator(".workspace-context-bar").getByRole("button", { name: "上传" })).toBeDisabled();
  await expect(page.locator(".workspace-context-bar")).toContainText("需先选择本次归档组态目录");
  await screenshot(page, "s1-workbench", 1920);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.reload();
  await expect(page.locator(".workspace-page")).toHaveClass(/details-collapsed/);
  await screenshot(page, "s1-workbench", 1280);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.reload();
  await expect(page.locator(".workspace-page")).toHaveClass(/details-open/);

  const firstWorkspaceRequest = apiRequests.find((request) => request.method === "POST" && request.path === "/v1/workspaces");
  expect(firstWorkspaceRequest?.token).toBe("Bearer dev-token-submitter");
  expect(firstWorkspaceRequest?.idempotencyKey).toBeNull();
  expect(JSON.parse(firstWorkspaceRequest?.body ?? "{} ")).toEqual({ business_project_id: "project-42", gateway_device_external_key: "gateway-17" });
  expect(apiResponses.find((response) => response.method === "POST" && response.path === "/v1/workspaces")?.status).toBe(201);
  expect(apiRequests.some((request) => request.path === "/v1/history?limit=100")).toBe(true);
  expect(apiRequests.some((request) => request.path === "/v1/history?limit=100&cursor=history-page-2")).toBe(true);

  await page.getByRole("textbox", { name: "搜索工作区与 History 节点" }).fill("提交");
  await expect(page.locator(".workspace-table tbody tr")).toHaveCount(5);
  await page.getByRole("textbox", { name: "搜索工作区与 History 节点" }).fill("");
  await page.getByRole("button", { name: "提交时间", exact: true }).click();
  const widthBefore = await page.locator(".workspace-table col").nth(0).evaluate((element) => Number.parseFloat(getComputedStyle(element).width));
  const resize = page.getByRole("button", { name: "调整节点 / 描述列宽" });
  const resizeBounds = await resize.boundingBox();
  if (!resizeBounds) throw new Error("workspace table column resize handle is missing");
  await page.mouse.move(resizeBounds.x + resizeBounds.width / 2, resizeBounds.y + resizeBounds.height / 2);
  await page.mouse.down();
  await page.mouse.move(resizeBounds.x + resizeBounds.width / 2 + 48, resizeBounds.y + resizeBounds.height / 2);
  await page.mouse.up();
  await expect.poll(() => page.locator(".workspace-table col").nth(0).evaluate((element) => Number.parseFloat(getComputedStyle(element).width))).toBeGreaterThan(widthBefore);

  await page.getByRole("button", { name: "归档基线 1", exact: true }).click();
  await page.locator(".workspace-context-bar").getByRole("button", { name: "加入比较" }).click();
  await page.getByRole("button", { name: "提交 2", exact: true }).click();
  await expect(page.locator(".workspace-context-bar")).toContainText("待审核");
  await expect(page.locator(".workspace-context-bar")).toContainText("提交尚未审核通过");
  await page.locator(".workspace-context-bar").getByRole("button", { name: "加入比较" }).click();
  await expect(page.locator(".compare-tray")).toContainText("2 / 3");
  await expect(page.locator(".workspace-table")).toContainText("比较 1");
  await expect(page.locator(".workspace-table")).toContainText("比较 2");
  await screenshot(page, "s2-compare-tray", 1920);

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.reload();
  await expect(page.locator(".workspace-page")).toHaveClass(/details-collapsed/);
  await expect(page.getByRole("button", { name: "展开详情面板" })).toBeVisible();
  await screenshot(page, "s2-compare-tray", 1280);

  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.reload();
  await expect(page.locator(".workspace-page")).toHaveClass(/details-open/);
  await screenshot(page, "s2-compare-tray", 1920);

  const identity = page.getByRole("combobox", { name: "模拟身份" });
  for (const [role, token] of [["reviewer", "Bearer dev-token-reviewer"], ["archive-confirmer", "Bearer dev-token-archive-confirmer"]]) {
    await identity.selectOption(role);
    await expect.poll(() => apiRequests.filter((request) => request.token === token).length).toBeGreaterThan(0);
  }

  await page.getByRole("button", { name: "工作区 gateway-17", exact: true }).click();
  await page.locator(".workspace-context-bar").getByRole("button", { name: "原始组态备份" }).click();
  expect(new URL(page.url()).searchParams.get("page")).not.toBe("compare");
  await expect(page.getByRole("heading", { name: "组态树", level: 1 })).toBeVisible();
  await page.locator(".workspace-details").getByRole("button", { name: "查看本次组态差异" }).click();
  await waitForBrowse(page);
  expect(new URL(page.url()).searchParams.get("workspaceId")).toBe("workspace-fe2b");
  expect(new URL(page.url()).searchParams.get("previewResultId")).toBe("preview-full");
  expect(new URL(page.url()).searchParams.get("pair")).toBe("initial_to_modified");
  expect(new URL(page.url()).searchParams.get("workbenchNode")).toBe("workspace:workspace-fe2b");
  for (const legacy of ["request", "previewRequest", "reviewRequest", "historyRequest"]) expect(new URL(page.url()).searchParams.has(legacy)).toBe(false);
  await page.getByRole("button", { name: "返回工作台" }).click();
  await expect(page.locator(".workspace-table")).toBeVisible();
  expect(new URL(page.url()).searchParams.get("workbenchNode")).toBe("workspace:workspace-fe2b");
  expect(new URL(page.url()).searchParams.get("workbenchNode")).toBe("workspace:workspace-fe2b");
});

test("待审提交从工作台进入只读审核模式并比较其基线到提交", async ({ page }) => {
  const { apiRequests } = await installFixtureRoutes(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "组态树", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "提交 2", exact: true }).click();
  await page.locator(".workspace-context-bar").getByRole("button", { name: "查看差异" }).click();
  await expect(page).toHaveURL(/mode=REVIEW/);
  await waitForBrowse(page);

  expect(apiRequests.some((request) => request.method === "GET" && request.path === "/v1/submissions/fe2a-history-ref-2/review")).toBe(true);
  const historyCompare = apiRequests.find((request) => request.method === "POST" && request.path === "/v1/history-compares");
  expect(JSON.parse(historyCompare?.body ?? "{}")).toEqual({ nodes: [
    { ref_kind: "baseline_node", ref_id: "fe2a-history-ref-1" },
    { ref_kind: "submission", ref_id: "fe2a-history-ref-2" },
  ] });
  expect(new URL(page.url()).searchParams.get("submissionId")).toBe("fe2a-history-ref-2");
});

test("History 比较超时重试复用同一幂等键，刷新后按 URL 中 operation_id 续查", async ({ page }) => {
  const fixture = await loadFixture("history-three-nodes");
  const holdFirstCompare = deferred();
  const { apiRequests, apiResponses } = await installFixtureRoutes(page, {
    timeoutFirstCompare: holdFirstCompare.promise,
    historyCompareStatus: (operationId, index) => index <= 3
      ? { ...HISTORY_COMPARE_RUNNING, operation_id: operationId }
      : { ...testHistoryCompareSucceeded(fixture.manifest.bundle_digest), operation_id: operationId },
  });
  await page.addInitScript(() => { Object.assign(window, { __gatewayTestConfig: { historyCompareTimeoutMs: 700 } }); });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  await page.getByRole("button", { name: "归档基线 1", exact: true }).click();
  await page.locator(".workspace-context-bar").getByRole("button", { name: "加入比较" }).click();
  await page.getByRole("button", { name: "提交 2", exact: true }).click();
  await page.locator(".workspace-context-bar").getByRole("button", { name: "加入比较" }).click();
  await page.locator(".compare-tray").getByRole("button", { name: "历史比较" }).click();
  await expect(page.getByRole("alert")).toContainText("请求超时");
  holdFirstCompare.resolve();
  await expect.poll(() => apiResponses.filter((response) => response.method === "POST" && response.path === "/v1/history-compares").length).toBe(1);
  await page.locator(".compare-tray").getByRole("button", { name: "重试发起比较" }).click();

  await expect(page).toHaveURL(/operationId=history-compare-fe2b-1/);
  const comparePosts = apiRequests.filter((request) => request.method === "POST" && request.path === "/v1/history-compares");
  await expect.poll(() => apiRequests.filter((request) => request.method === "POST" && request.path === "/v1/history-compares").length).toBe(2);
  expect(comparePosts[0]?.idempotencyKey).toBeTruthy();
  expect(comparePosts[0]?.idempotencyKey).toBe(comparePosts[1]?.idempotencyKey);
  expect(comparePosts[0]?.body).toBe(comparePosts[1]?.body);
  expect(apiResponses.filter((response) => response.method === "POST" && response.path === "/v1/history-compares").map((response) => response.status)).toEqual([202, 200]);
  await expect(page.locator(".history-result-drawer")).toContainText("执行中");
  await expect(page.locator(".compare-tray").getByRole("button", { name: "比较中" })).toBeDisabled();
  await expect(page.locator(".compare-chip").first().getByRole("button")).toBeDisabled();
  await page.reload();
  await expect(page.locator(".history-result-drawer")).toBeVisible();
  await expect(page.locator(".history-result-drawer")).toContainText("已完成");
  await expect(page.locator(".history-result-drawer").getByRole("button", { name: "打开差异工作台" })).toBeVisible();
  await screenshot(page, "history-compare-result-drawer", 1920);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.reload();
  await expect(page.locator(".history-result-drawer")).toContainText("已完成");
  await screenshot(page, "history-compare-result-drawer", 1280);
  expect(new URL(page.url()).searchParams.get("operationId")).toBe("history-compare-fe2b-1");
  expect(apiRequests.some((request) => request.method === "GET"
    && request.path === "/v1/history-compares/history-compare-fe2b-1/bundle")).toBe(true);
  await page.locator(".history-result-drawer").getByRole("button", { name: "打开差异工作台" }).click();
  await expect(page).toHaveURL(/page=compare.*mode=HISTORY/);
  await waitForBrowse(page);
  expect(new URL(page.url()).searchParams.get("operationId")).toBe("history-compare-fe2b-1");
});

test("历史比较抽屉在 bundle 就绪前隐藏打开入口并允许下载重试", async ({ page }) => {
  const { manifest } = await loadFixture("history-three-nodes");
  await installFixtureRoutes(page, {
    failHistoryBundleAttempts: 2,
    historyCompareStatus: (operationId) => ({ ...testHistoryCompareSucceeded(manifest.bundle_digest), operation_id: operationId }),
  });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/?page=workspace&operationId=history-compare-download&operationKind=history-compare&compare=baseline_node%3Afe2a-history-ref-1&compare=submission%3Afe2a-history-ref-2");
  const drawer = page.locator(".history-result-drawer");
  await expect(drawer).toContainText("下载失败，可重试");
  await expect(drawer.getByRole("button", { name: "打开差异工作台" })).toHaveCount(0);
  await expect(drawer).toContainText("节点 1 → 节点 2");
  await expect(drawer).not.toContainText("middle_to_right");
  await drawer.getByRole("button", { name: "重试下载" }).click();
  await expect(drawer).toContainText("已就绪", { timeout: 10_000 });
  await expect(drawer.getByRole("button", { name: "打开差异工作台" })).toBeVisible();
});

test("History 比较仍在运行和连接中断状态清晰显示", async ({ page }) => {
  await installFixtureRoutes(page, { historyCompareStatus: (operationId) => ({ ...HISTORY_COMPARE_RUNNING, operation_id: operationId }) });
  // C4: pin the clock so the running compare shows a fixed waited duration.
  await freezePageClock(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/?page=workspace&operationId=history-compare-running&operationKind=history-compare&compare=baseline_node%3Afe2a-history-ref-1&compare=submission%3Afe2a-history-ref-2");
  await expect(page.locator(".history-result-drawer")).toContainText("执行中");
  await screenshot(page, "history-compare-running", 1920);
  await screenshot(page, "history-compare-running", 1280);

  await page.unrouteAll({ behavior: "wait" });
  await installFixtureRoutes(page, { historyCompareErrors: 5 });
  await page.goto("/?page=workspace&operationId=history-compare-interrupted&operationKind=history-compare&compare=baseline_node%3Afe2a-history-ref-1&compare=submission%3Afe2a-history-ref-2");
  await expect(page.locator(".history-result-drawer")).toContainText("连接中断", { timeout: 25_000 });
  await expect(page.getByRole("button", { name: "重试查询" })).toBeVisible();
  await screenshot(page, "history-compare-connection-interrupted", 1920);
  await screenshot(page, "history-compare-connection-interrupted", 1280);
});

test("MANUAL_RECOVERY_REQUIRED 提供管理员信息并在刷新后跟随 RUNNING 到 SUCCEEDED", async ({ page }) => {
  await installFixtureRoutes(page, { operationStatus: (_operationId, index) => MANUAL_RECOVERY_TO_SUCCESS[Math.min(index - 1, MANUAL_RECOVERY_TO_SUCCESS.length - 1)]! });
  await freezePageClock(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/?operationId=operation-manual-success&operationKind=operation");
  const panel = page.getByRole("region", { name: "操作状态" });
  await expect(panel).toContainText("需要管理员处理");
  await expect(panel).toContainText("operation-manual-success");
  await expect(panel.getByRole("button", { name: "复制 ID" })).toBeVisible();
  await expect(panel.getByRole("button", { name: "重试操作" })).toHaveCount(0);
  expect(new URL(page.url()).searchParams.get("operationId")).toBe("operation-manual-success");
  await screenshot(page, "manual-recovery-required", 1920);
  await screenshot(page, "manual-recovery-required", 1280);
  await panel.getByRole("button", { name: "刷新状态" }).click();
  await expect(panel).toContainText("执行中");
  await expect(panel).toContainText("已完成", { timeout: 5_000 });
});

test("操作状态查询收到权限拒绝时显示错误码而不伪装成连接中断", async ({ page }) => {
  await installFixtureRoutes(page, { operationStatusForbidden: true });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/?operationId=operation-forbidden&operationKind=operation");
  const panel = page.getByRole("region", { name: "操作状态" });
  await expect(panel).toContainText("当前身份没有该操作的权限");
  await expect(panel).toContainText("SCOPE_FORBIDDEN");
  await expect(panel).not.toContainText("连接中断");
  await expect(panel.getByRole("button", { name: "重试查询" })).toHaveCount(0);
});

test("所选模拟身份携带对应 token；无权限错误页不显示已连接", async ({ page }) => {
  const { apiRequests } = await installFixtureRoutes(page, { noPermission: true });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("SCOPE_FORBIDDEN");
  await page.getByRole("combobox", { name: "模拟身份" }).selectOption("no-permission");
  await expect(page.getByRole("heading", { name: "当前身份没有该操作的权限" })).toBeVisible();
  await expect.poll(() => apiRequests.filter((request) => request.method === "POST" && request.path === "/v1/workspaces" && request.token === "Bearer dev-token-no-permission").length).toBeGreaterThan(0);
  await expect(page.getByText("已连接", { exact: true })).toHaveCount(0);
  await screenshot(page, "workspace-error-no-connected", 1920);
  await screenshot(page, "workspace-error-no-connected", 1280);
});

test("无权限身份发起历史比较时托盘显示统一权限提示和错误码", async ({ page }) => {
  const { apiRequests } = await installFixtureRoutes(page, { historyCompareForbidden: true });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  await page.getByRole("combobox", { name: "模拟身份" }).selectOption("no-permission");
  await page.getByRole("button", { name: "归档基线 1", exact: true }).click();
  await page.locator(".workspace-context-bar").getByRole("button", { name: "加入比较" }).click();
  await page.getByRole("button", { name: "提交 2", exact: true }).click();
  await page.locator(".workspace-context-bar").getByRole("button", { name: "加入比较" }).click();
  await page.locator(".compare-tray").getByRole("button", { name: "历史比较" }).click();
  await expect(page.locator(".compare-tray").getByRole("alert")).toContainText("当前身份没有该操作的权限");
  await expect(page.locator(".compare-tray").getByRole("alert")).toContainText("SCOPE_FORBIDDEN");
  await expect(page.getByRole("button", { name: "复制比较错误详情" })).toBeVisible();
  expect(apiRequests.some((request) => request.method === "POST" && request.path === "/v1/history-compares" && request.token === "Bearer dev-token-no-permission")).toBe(true);
});

test("查看差异超时后的重试复用同一幂等意图", async ({ page }) => {
  const holdFirstCompare = deferred();
  const { apiRequests } = await installFixtureRoutes(page, { timeoutFirstCompare: holdFirstCompare.promise });
  await page.addInitScript(() => { Object.assign(window, { __gatewayTestConfig: { historyCompareTimeoutMs: 700 } }); });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  await page.getByRole("button", { name: "提交 1", exact: true }).click();
  await page.locator(".workspace-context-bar").getByRole("button", { name: "查看差异" }).click();
  await expect(page.locator(".compare-tray").getByRole("alert")).toContainText("请求超时");
  holdFirstCompare.resolve();
  await page.locator(".compare-tray").getByRole("button", { name: "重试发起比较" }).click();
  await expect(page).toHaveURL(/operationId=history-compare-fe2b-1/);
  await expect.poll(() => apiRequests.filter((request) => request.method === "POST" && request.path === "/v1/history-compares").length).toBe(2);
  const requests = apiRequests.filter((request) => request.method === "POST" && request.path === "/v1/history-compares");
  expect(requests[0]?.idempotencyKey).toBeTruthy();
  expect(requests[0]?.idempotencyKey).toBe(requests[1]?.idempotencyKey);
  expect(requests[0]?.body).toBe(requests[1]?.body);
  expect(JSON.parse(requests[0]?.body ?? "{}")).toEqual({ nodes: [
    { ref_kind: "baseline_node", ref_id: "fe2a-history-ref-0" },
    { ref_kind: "submission", ref_id: "fe2a-history-ref-old" },
  ] });
});

test("FE2b 正常业务场景以普通页签打开主表且表无诊断（只有 1 条通道提示）", async ({ page }) => {
  await installFixtureRoutes(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(browseUrl("PREVIEW", "preview-workbench-normal", { node: "table:b1_n1_iec104_yc_list", tab: "table" }));
  await expect(page.locator(".task-indicator")).toHaveCount(0);
  await waitForBrowse(page);
  await expect(page.locator(".navigation-sidebar")).toContainText("其他表");
  // BE-b v4 keeps the channel table that no network port claims in 其他表 and
  // reports it as one navigation diagnostic; the tables themselves stay clean.
  await expect(page.locator(".nav-group__diagnostic-count")).toHaveCount(1);
  await expect(page.locator(".nav-group__diagnostic-count")).toHaveText("1 条提示");
  await expect(page.locator(".pair-diagnostic-strip")).toHaveCount(1);
  await expect(page.locator(".pair-diagnostic-strip")).toContainText("项目身份无法验证");
  await expect(page.locator(".table-heading__diagnostics")).toHaveCount(0);
  await expect(page.locator(".table-heading h2")).toHaveText("b1_n1_iec104_yc_list");
  await screenshot(page, "s3-workbench-normal", 1920);
  await waitForGridPaint(page, "table");
  await screenshot(page, "s4-grid-normal-main", 1920);
  await hoverChangedTelemetryValue(page);
  await screenshot(page, "s4-grid-normal-hover", 1920);
  await page.mouse.move(1, 1);
  await expect(page.getByRole("tooltip")).toHaveCount(0);
  await screenshot(page, "s3-workbench-normal", 1280);
  await screenshot(page, "s4-grid-normal-main", 1280);
  await hoverChangedTelemetryValue(page);
  await expect(page.getByRole("tooltip")).toContainText("字段变更");
  await screenshot(page, "s4-grid-normal-hover", 1280);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.getByRole("radio", { name: "Debug" }).click();
  await expect(page.getByRole("radio", { name: "Debug" })).toHaveAttribute("aria-checked", "true");
  await screenshot(page, "s4-grid-normal-debug", 1920);
  await screenshot(page, "s4-grid-normal-debug", 1280);
});

async function freezePageClock(page: Page) {
  await page.clock.setFixedTime(new Date("2026-11-03T09:00:09Z"));
}

async function setDirectoryInput(page: Page, testId: string, root: string, files: Array<{ path: string; content: string }>) {
  await page.evaluate(({ testId, root, files }) => {
    const input = document.querySelector<HTMLInputElement>(`[data-testid="${testId}"]`);
    if (!input) throw new Error(`missing input ${testId}`);
    const transfer = new DataTransfer();
    for (const spec of files) {
      const file = new File([spec.content], spec.path.split("/").at(-1) ?? "file", { type: "text/plain" });
      Object.defineProperty(file, "webkitRelativePath", { value: `${root}/${spec.path}` });
      transfer.items.add(file);
    }
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }, { testId, root, files });
}

const VALID_DIRECTORY = [
  { path: "station.pmc", content: "pmc" },
  { path: "sql/dbcfg.sql", content: "create table device(id int);\n" },
  { path: "comps/logic/logics.xml", content: "<logics/>" },
];

test("FE2c 上传步骤卡校验目录并锁定页面", async ({ page }) => {
  const { apiRequests } = await installFixtureRoutes(page, { uploadHoldPolls: 8 });
  await freezePageClock(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "组态树", level: 1 })).toBeVisible();
  const card = page.getByLabel("上传与预览");
  await expect(card).toBeVisible();
  await screenshot(page, "upload-empty", 1920);
  await screenshot(page, "upload-empty", 1280);
  await page.setViewportSize({ width: 1920, height: 1080 });

  await setDirectoryInput(page, "upload-modified-input", "bad_cfg", [{ path: "readme.txt", content: "x" }]);
  await expect(card.getByText("本次归档组态未通过校验（2 项）")).toBeVisible();
  await expect(card.getByText("根目录下必须恰好存在一个 .pmc 文件")).toBeVisible();
  await expect(card.getByText("目录中必须存在 sql/dbcfg.sql")).toBeVisible();
  await expect(card.getByRole("button", { name: "上传并生成预览" })).toBeDisabled();
  await screenshot(page, "upload-invalid", 1920);
  await screenshot(page, "upload-invalid", 1280);

  await setDirectoryInput(page, "upload-modified-input", "station_cfg_0921", VALID_DIRECTORY);
  await setDirectoryInput(page, "upload-initial-input", "station_cfg_0820", VALID_DIRECTORY);
  await expect(card.getByText("station_cfg_0921", { exact: false }).first()).toBeVisible();
  await expect(card.getByText("3 个文件", { exact: false }).first()).toBeVisible();
  await expect(card.getByText("上传方式：原始备份 + 本次归档")).toBeVisible();
  await expect(card.getByRole("button", { name: "上传并生成预览" })).toBeEnabled();
  await screenshot(page, "upload-selected", 1920);
  await screenshot(page, "upload-selected", 1280);
  await card.getByRole("button", { name: "上传并生成预览" }).click();
  await expect(page.locator(".page-lock-overlay")).toBeVisible();
  await expect(page.getByText("上传与预览执行中，页面其余操作已锁定")).toBeVisible();
  await screenshot(page, "upload-locked", 1920);
  await screenshot(page, "upload-locked", 1280);
  await expect(page).toHaveURL(/mode=PREVIEW/, { timeout: 30000 });
  await waitForBrowse(page);
  expect(apiRequests.some((request) => request.path.endsWith("/upload-revisions"))).toBe(true);
  expect(apiRequests.find((request) => request.path.endsWith("/upload-revisions"))?.idempotencyKey).toBeTruthy();
});

test("FE2c 提交前要求确认项目身份差异并进入审核", async ({ page }) => {
  const { apiRequests } = await installFixtureRoutes(page, { submitIdentity: "confirm", submissionOne: true });
  await page.goto(browseUrl("PREVIEW", "preview-full"));
  await waitForBrowse(page);
  await page.getByRole("button", { name: "提交", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("业务项目不同，需要确认数据集替换")).toBeVisible();
  await expect(dialog.getByText("项目身份无法验证")).toBeVisible();
  // M7 Q11: the workspace row shows the tree display name, not the raw ID.
  await expect(dialog.getByText("工作区").locator("xpath=following-sibling::dd")).toHaveText("gateway-17");
  await screenshot(page, "submit-summary-workspace", 1920);
  await screenshot(page, "submit-summary-workspace", 1280);
  const confirm = dialog.getByRole("button", { name: "确认提交" });
  await expect(confirm).toBeDisabled();

  const checks = dialog.getByRole("checkbox");
  await checks.nth(0).check();
  await dialog.getByLabel(/业务项目不同，需要确认数据集替换的原因/).fill("确认替换到目标项目");
  await checks.nth(1).check();
  await dialog.getByLabel(/项目身份无法验证的原因/).fill("已人工核对差异");
  await expect(confirm).toBeEnabled();
  await screenshot(page, "submit-identity-confirmation", 1920);
  await screenshot(page, "submit-identity-confirmation", 1280);

  await confirm.click();
  await expect(dialog.getByRole("status", { name: "提交结果" })).toBeVisible();
  await dialog.getByRole("button", { name: "查看提交" }).click();
  await expect(page).toHaveURL(/mode=REVIEW.*submissionId=submission-1/, { timeout: 30000 });
  await waitForBrowse(page);
  const submitRequest = apiRequests.find((request) => request.path.endsWith("/submit-attempts"));
  expect(submitRequest?.body).toContain("ACCEPT_DATASET_REPLACEMENT");
  expect(submitRequest?.body).toContain("ACCEPT_UNVERIFIABLE_DETAILED_RESULT");
  expect(submitRequest?.body).toContain("sha256:identity");
  await screenshotHeader(page, "header-review", 1920);
  await screenshotHeader(page, "header-review", 1280);
  await expect(page.getByText("审核：待审核")).toBeVisible();

  await page.getByRole("button", { name: "审核通过", exact: true }).click();
  const approve = page.getByRole("dialog", { name: "确认审核通过" });
  await approve.getByRole("button", { name: "确认通过" }).click();
  await expect(page.getByText("审核：已通过")).toBeVisible();
});

test("FE2c 提交 403 与版本冲突显示内联错误", async ({ page }) => {
  const first = await installFixtureRoutes(page, { submitForbidden: true });
  await page.goto(browseUrl("PREVIEW", "preview-full"));
  await waitForBrowse(page);
  await page.getByRole("button", { name: "提交", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "确认提交" }).click();
  await expect(dialog.getByText("当前身份没有该操作的权限")).toBeVisible();
  await expect(dialog.getByText("SCOPE_FORBIDDEN")).toBeVisible();
  const firstKey = first.apiRequests.find((request) => request.path.endsWith("/submit-attempts"))?.idempotencyKey;

  await page.unrouteAll({ behavior: "wait" });
  const retry = await installFixtureRoutes(page, {});
  await dialog.getByRole("button", { name: "确认提交" }).click();
  await expect(dialog.getByRole("status", { name: "提交结果" })).toBeVisible();
  await dialog.getByRole("button", { name: "查看提交" }).click();
  await expect(page).toHaveURL(/mode=REVIEW.*submissionId=submission-1/, { timeout: 30000 });
  const retriedKey = retry.apiRequests.find((request) => request.path.endsWith("/submit-attempts"))?.idempotencyKey;
  expect(firstKey).toBeTruthy();
  expect(retriedKey).toBeTruthy();
  expect(retriedKey).not.toBe(firstKey);

  await page.unrouteAll({ behavior: "wait" });
  await installFixtureRoutes(page, { submitConflict: "WORKSPACE_VERSION_CONFLICT" });
  await page.goto(browseUrl("PREVIEW", "preview-full"));
  await waitForBrowse(page);
  await page.getByRole("button", { name: "提交", exact: true }).click();
  const conflictDialog = page.getByRole("dialog");
  await conflictDialog.getByRole("button", { name: "确认提交" }).click();
  await expect(conflictDialog.getByText("数据已被更新，请刷新后重试")).toBeVisible();
});

test("FE2c 审核退回必须填写理由并可撤回", async ({ page }) => {
  const { apiRequests } = await installFixtureRoutes(page, { submissionOne: true });
  await page.goto(browseUrl("REVIEW", "preview-full", { submissionId: "submission-1" }));
  await waitForBrowse(page);
  await page.getByRole("combobox", { name: "模拟身份" }).selectOption("reviewer");
  await page.getByRole("button", { name: "退回", exact: true }).click();
  const reject = page.getByRole("dialog", { name: "退回提交" });
  const confirm = reject.getByRole("button", { name: "确认退回" });
  await expect(confirm).toBeDisabled();
  await reject.getByLabel("退回理由").fill("配置与现场不一致，请核对后重新提交");
  await expect(confirm).toBeEnabled();
  await screenshot(page, "review-reject-dialog", 1920);
  await screenshot(page, "review-reject-dialog", 1280);
  await expect.poll(async () => reject.locator(".confirm-impact").evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await confirm.click();
  await expect(page.getByText("审核：已退回")).toBeVisible();
  expect(apiRequests.find((request) => request.path.endsWith("/review-events"))?.token).toBe("Bearer dev-token-reviewer");
});

test("FE2c 审核撤回需要二次确认", async ({ page }) => {
  await installFixtureRoutes(page, { submissionOne: true });
  await page.goto(browseUrl("REVIEW", "preview-full", { submissionId: "submission-1" }));
  await waitForBrowse(page);
  await page.getByRole("button", { name: "撤回", exact: true }).click();
  const withdraw = page.getByRole("dialog", { name: "撤回提交" });
  const withdrawConfirm = withdraw.getByRole("button", { name: "确认撤回" });
  await expect(withdrawConfirm).toBeDisabled();
  await withdraw.getByRole("checkbox").check();
  await expect(withdrawConfirm).toBeEnabled();
  await expect(withdraw.getByText("我已了解撤回后需要重新提交")).toBeVisible();
  await screenshot(page, "review-withdraw-dialog", 1920);
  await screenshot(page, "review-withdraw-dialog", 1280);
  await expect.poll(async () => withdraw.locator(".confirm-impact").evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await withdraw.getByRole("button", { name: "确认撤回" }).click();
  await expect(page.getByText("审核：已撤回")).toBeVisible();
});

test("FE2c 提交执行中刷新后成功后进入提交结果", async ({ page }) => {
  test.setTimeout(90000);
  const manual = [
    { ...MANUAL_RECOVERY_TO_SUCCESS[0]!, operation_id: "submit-op-1", job_kind: "backend-vnext/submit" as const },
    { ...MANUAL_RECOVERY_TO_SUCCESS[1]!, operation_id: "submit-op-1", job_kind: "backend-vnext/submit" as const },
    { ...MANUAL_RECOVERY_TO_SUCCESS[2]!, operation_id: "submit-op-1", job_kind: "backend-vnext/submit" as const },
  ];
  await installFixtureRoutes(page, {
    operationStatus: (_operationId, index) => manual[Math.min(index - 1, manual.length - 1)]!,
    clearWorkspacePointerOnTerminal: true,
    submissionOne: true,
  });
  await page.goto(browseUrl("PREVIEW", "preview-full"));
  await waitForBrowse(page);
  await page.getByRole("button", { name: "提交", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "确认提交" }).click();
  await expect(dialog.getByText("需要管理员处理")).toBeVisible({ timeout: 10000 });
  await page.reload();
  await expect(page.getByRole("region", { name: "操作状态" })).toBeVisible();
  await expect(page).toHaveURL(/mode=REVIEW/, { timeout: 60000 });
  expect(new URL(page.url()).searchParams.get("operationId")).toBeNull();
});

test("FE3c 归档主线确认预检、异常与影响", async ({ page }) => {
  const { apiRequests } = await installFixtureRoutes(page, { approvedSubmission: true });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "组态树", level: 1 })).toBeVisible();
  await page.getByRole("combobox", { name: "模拟身份" }).selectOption("archive-confirmer");
  await page.getByRole("button", { name: "提交 2", exact: true }).click();
  await page.locator(".workspace-context-bar").getByRole("button", { name: "归档主线" }).click();
  const dialog = page.getByRole("dialog", { name: "归档主基线" });
  await expect(dialog.getByText("预检状态")).toBeVisible();
  await expect(dialog.getByRole("heading", { name: "业务核验" })).toBeVisible();
  const confirm = dialog.getByRole("button", { name: "确认归档" });
  await expect(confirm).toBeDisabled();
  await dialog.getByRole("checkbox", { name: /确认把/ }).check();
  await expect(confirm).toBeDisabled();
  await dialog.locator(".archive-anomaly").getByRole("button", { name: "接受" }).click();
  const accept = page.getByRole("dialog", { name: "接受异常" });
  await expect(accept.getByRole("button", { name: "确认接受" })).toBeDisabled();
  await accept.getByLabel("接受理由").fill("已核对项目身份例外");
  await accept.getByRole("button", { name: "确认接受" }).click();
  await expect(confirm).toBeEnabled();
  await screenshot(page, "archive-mainline", 1920);
  await screenshot(page, "archive-mainline", 1280);
  await confirm.click();
  await expect(dialog.getByText("归档完成")).toBeVisible({ timeout: 15000 });
  await expect(dialog.getByText("归档 1 项，关闭 0 项")).toBeVisible();
  await screenshot(page, "archive-mainline-result", 1920);
  await screenshot(page, "archive-mainline-result", 1280);
  const archiveRequests = apiRequests.filter((request) => ["/v1/archives", "/v1/archive-confirmations", "/v1/archive-anomaly-resolutions"].some((suffix) => request.path.endsWith(suffix)));
  expect(archiveRequests.length).toBeGreaterThan(0);
  for (const request of archiveRequests) {
    const parsed = JSON.parse(request.body) as { selected?: Record<string, unknown> };
    expect(Object.keys(parsed.selected ?? {}).sort(), request.path).toEqual(["expected_candidate_digest", "submission_id"]);
  }
  expect(archiveRequests.every((request) => request.token === "Bearer dev-token-archive-confirmer")).toBe(true);
});

test("FE2c 上传失败后重试不重复上传", async ({ page }) => {
  await freezePageClock(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  const { apiRequests } = await installFixtureRoutes(page, { fail: true });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "组态树", level: 1 })).toBeVisible();
  await expect(page.getByLabel("上传与预览")).toBeVisible();
  await setDirectoryInput(page, "upload-initial-input", "original_cfg", VALID_DIRECTORY);
  await setDirectoryInput(page, "upload-modified-input", "station_cfg_0921", VALID_DIRECTORY);
  await page.getByRole("button", { name: "上传", exact: true }).click();
  const card = page.getByLabel("上传与预览");
  await expect(card.getByRole("alert")).toContainText("预览已生成，但下载比较结果失败，请重试", { timeout: 15000 });
  await screenshot(page, "upload-failure-retry", 1920);
  await screenshot(page, "upload-failure-retry", 1280);
  await page.setViewportSize({ width: 1920, height: 1080 });

  await page.unrouteAll({ behavior: "wait" });
  await installFixtureRoutes(page);
  await card.getByRole("button", { name: "重试" }).click();
  await expect(page).toHaveURL(/mode=PREVIEW/, { timeout: 30000 });
  expect(apiRequests.filter((request) => request.path.endsWith("/upload-revisions"))).toHaveLength(1);
});

test("FE2c 上传版本冲突后刷新再上传使用新版本与新 key", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  const { apiRequests } = await installFixtureRoutes(page, { uploadConflictOnce: "WORKSPACE_VERSION_CONFLICT" });
  await page.goto("/");
  const card = page.getByLabel("上传与预览");
  await expect(card).toBeVisible();
  await setDirectoryInput(page, "upload-modified-input", "station_cfg_0921", VALID_DIRECTORY);
  await card.getByRole("button", { name: "上传并生成预览" }).click();
  await expect(card.getByText("WORKSPACE_VERSION_CONFLICT")).toBeVisible();
  await expect(card.getByRole("button", { name: "刷新" })).toBeVisible();
  await card.getByRole("button", { name: "刷新" }).click();
  await expect(card.getByText("WORKSPACE_VERSION_CONFLICT")).toHaveCount(0);
  await card.getByRole("button", { name: "上传并生成预览" }).click();
  await expect(page).toHaveURL(/mode=PREVIEW/, { timeout: 30000 });
  const uploads = apiRequests.filter((request) => request.path.endsWith("/upload-revisions"));
  expect(uploads).toHaveLength(2);
  expect(uploads[0].idempotencyKey).not.toBe(uploads[1].idempotencyKey);
  const version = (body: string | null) => /"expected_workspace_version":(\d+)/.exec(body ?? "")?.[1];
  expect(version(uploads[0].body)).toBe("12");
  expect(version(uploads[1].body)).toBe("14");
});

test("FE2c 上传冲突后刷新失败时进入失败阶段并显示原因", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await installFixtureRoutes(page, { uploadConflictOnce: "WORKSPACE_VERSION_CONFLICT" });
  await page.goto("/");
  const card = page.getByLabel("上传与预览");
  await expect(card).toBeVisible();
  await setDirectoryInput(page, "upload-modified-input", "station_cfg_0921", VALID_DIRECTORY);
  await card.getByRole("button", { name: "上传并生成预览" }).click();
  await expect(card.getByText("WORKSPACE_VERSION_CONFLICT")).toBeVisible();
  await page.unrouteAll({ behavior: "wait" });
  await installFixtureRoutes(page, { noPermission: true });
  await card.getByRole("button", { name: "刷新" }).click();
  await expect(card.getByRole("alert")).toContainText("刷新失败，请检查连接后重试");
  await expect(card.getByText("REFRESH_FAILED")).toBeVisible();
});

test("FE2c 上传与 Preview 的 403、版本冲突就地显示错误码", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await installFixtureRoutes(page, { uploadConflict: "WORKSPACE_VERSION_CONFLICT" });
  await page.goto("/");
  const card = page.getByLabel("上传与预览");
  await expect(card).toBeVisible();
  await setDirectoryInput(page, "upload-modified-input", "station_cfg_0921", VALID_DIRECTORY);
  await card.getByRole("button", { name: "上传并生成预览" }).click();
  await expect(card.getByText("工作区或基线已被更新，请刷新后重新上传")).toBeVisible();
  await expect(card.getByText("WORKSPACE_VERSION_CONFLICT")).toBeVisible();
  await screenshot(page, "upload-version-conflict", 1920);
  await screenshot(page, "upload-version-conflict", 1280);

  await page.unrouteAll({ behavior: "wait" });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await installFixtureRoutes(page, { previewForbidden: true });
  await page.goto("/");
  await expect(page.getByLabel("上传与预览")).toBeVisible();
  await setDirectoryInput(page, "upload-modified-input", "station_cfg_0921", VALID_DIRECTORY);
  await page.getByLabel("上传与预览").getByRole("button", { name: "上传并生成预览" }).click();
  await expect(page.getByLabel("上传与预览").getByText("当前身份没有该操作的权限")).toBeVisible();
  await expect(page.getByLabel("上传与预览").getByText("SCOPE_FORBIDDEN")).toBeVisible();
  await page.setViewportSize({ width: 1920, height: 1080 });
  await screenshot(page, "upload-permission-denied", 1920);
  await screenshot(page, "upload-permission-denied", 1280);
});

test("FE2c 审核 403、版本冲突与超时重试复用同一幂等键", async ({ page }) => {
  const { apiRequests } = await installFixtureRoutes(page, { reviewForbidden: true });
  await page.goto(browseUrl("REVIEW", "preview-full", { submissionId: "submission-1" }));
  await waitForBrowse(page);
  await page.getByRole("combobox", { name: "模拟身份" }).selectOption("reviewer");
  await page.getByRole("button", { name: "审核通过", exact: true }).click();
  const approve = page.getByRole("dialog", { name: "确认审核通过" });
  await approve.getByRole("button", { name: "确认通过" }).click();
  await expect(approve.getByText("当前身份没有该操作的权限")).toBeVisible();
  await expect(approve.getByText("SCOPE_FORBIDDEN")).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 900 });
  await expect.poll(async () => approve.locator(".confirm-impact").evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await screenshot(page, "review-permission-denied", 1920);
  await screenshot(page, "review-permission-denied", 1280);
  expect(apiRequests.find((request) => request.path.endsWith("/review-events"))?.token).toBe("Bearer dev-token-reviewer");

  await page.unrouteAll({ behavior: "wait" });
  const conflict = await installFixtureRoutes(page, { reviewConflict: "REVIEW_VERSION_CONFLICT" });
  await page.reload();
  await waitForBrowse(page);
  await page.getByRole("combobox", { name: "模拟身份" }).selectOption("reviewer");
  await page.getByRole("button", { name: "审核通过", exact: true }).click();
  const conflictDialog = page.getByRole("dialog", { name: "确认审核通过" });
  await conflictDialog.getByRole("button", { name: "确认通过" }).click();
  await expect(conflictDialog.getByText("REVIEW_VERSION_CONFLICT")).toBeVisible();
  const refresh = conflictDialog.getByRole("button", { name: "刷新审核信息" });
  await expect(refresh).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 900 });
  const dialogBox = await conflictDialog.boundingBox();
  const refreshBox = await refresh.boundingBox();
  expect(dialogBox).not.toBeNull();
  expect(refreshBox).not.toBeNull();
  expect(refreshBox!.x + refreshBox!.width).toBeLessThanOrEqual(dialogBox!.x + dialogBox!.width + 0.5);
  expect(refreshBox!.y + refreshBox!.height).toBeLessThanOrEqual(dialogBox!.y + dialogBox!.height + 0.5);
  await screenshot(page, "review-version-conflict", 1920);
  await expect(refresh).toBeInViewport();
  await screenshot(page, "review-version-conflict", 1280);
  await expect(refresh).toBeInViewport();
  await refresh.click();
  await expect(conflictDialog.getByText("REVIEW_VERSION_CONFLICT")).toHaveCount(0);
  await expect(conflictDialog.getByRole("button", { name: "确认通过" })).toBeEnabled();
  expect(conflict.apiRequests.some((request) => request.path.endsWith("/review-events"))).toBe(true);

  await page.unrouteAll({ behavior: "wait" });
  const replay = await installFixtureRoutes(page, { reviewTimeoutFirst: true });
  await page.reload();
  await waitForBrowse(page);
  await page.getByRole("combobox", { name: "模拟身份" }).selectOption("reviewer");
  await page.getByRole("button", { name: "审核通过", exact: true }).click();
  const replayDialog = page.getByRole("dialog", { name: "确认审核通过" });
  await replayDialog.getByRole("button", { name: "确认通过" }).click();
  await expect(replayDialog.getByText("SERVICE_NOT_READY")).toBeVisible();
  await replayDialog.getByRole("button", { name: "确认通过" }).click();
  await expect(page.getByText("审核：已通过")).toBeVisible({ timeout: 15000 });
  const keys = replay.apiRequests.filter((request) => request.path.endsWith("/review-events")).map((request) => request.idempotencyKey);
  expect(keys.length).toBe(2);
  expect(keys[0]).toBeTruthy();
  expect(keys[0]).toBe(keys[1]);
});

test("V11 过期通过后禁用通过并保留退回撤回", async ({ page }) => {
  const { apiRequests } = await installFixtureRoutes(page, { reviewConflict: "BASELINE_VERSION_CONFLICT" });
  await page.goto(browseUrl("REVIEW", "preview-full", { submissionId: "submission-1" }));
  await waitForBrowse(page);
  await page.getByRole("combobox", { name: "模拟身份" }).selectOption("reviewer");
  await page.getByRole("button", { name: "审核通过", exact: true }).click();
  const approve = page.getByRole("dialog", { name: "确认审核通过" });
  const historyGetsBefore = apiRequests.filter((request) =>
    request.method === "GET" && request.path.split("?")[0] === "/v1/history").length;
  await approve.getByRole("button", { name: "确认通过" }).click();
  await expect(page.getByText("该提交所基于的基线已更新，不能通过。可以退回，或由提交人撤回后基于当前基线重新提交。")).toBeVisible();
  const expiredAlert = page.getByRole("alert").filter({ hasText: "该提交所基于的基线已更新" });
  expect(await expiredAlert.evaluate((element) => element.closest(".compare-header__notice") !== null)).toBe(true);
  expect(await expiredAlert.evaluate((element) => element.closest(".review-actions") === null)).toBe(true);
  await expect(page.getByText("BASELINE_VERSION_CONFLICT")).toBeVisible();
  await expect(page.getByRole("button", { name: "审核通过", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "退回", exact: true })).toBeEnabled();
  await expect(page.getByRole("button", { name: "撤回", exact: true })).toBeEnabled();
  // C5: the expired-approve 409 re-reads the review and the History together.
  // listHistory pages with ?limit=100 (and a cursor), so match the path prefix.
  await expect.poll(() => apiRequests.filter((request) =>
    request.method === "GET" && request.path.split("?")[0] === "/v1/history").length,
    { timeout: 15000 }).toBeGreaterThan(historyGetsBefore);
  await screenshot(page, "fe3c-review-expired", 1920);
  await screenshot(page, "fe3c-review-expired", 1280);
  await expectHeaderBreadcrumbVisible(page);
});

test("V12 已处置提交的审核动作提示已归档或关闭", async ({ page }) => {
  const { apiRequests } = await installFixtureRoutes(page, { reviewConflict: "ARCHIVE_CLOSED" });
  await page.goto(browseUrl("REVIEW", "preview-full", { submissionId: "submission-1" }));
  await waitForBrowse(page);
  await page.getByRole("combobox", { name: "模拟身份" }).selectOption("reviewer");
  await page.setViewportSize({ width: 1280, height: 1080 });
  const backWidthBefore = (await page.getByRole("button", { name: "返回工作台" }).boundingBox())?.width;
  await page.getByRole("button", { name: "审核通过", exact: true }).click();
  const approve = page.getByRole("dialog", { name: "确认审核通过" });
  const historyGetsBefore = apiRequests.filter((request) =>
    request.method === "GET" && request.path.split("?")[0] === "/v1/history").length;
  await approve.getByRole("button", { name: "确认通过" }).click();
  await expect(page.getByText("该提交已归档或关闭，已重新读取")).toBeVisible();
  await expect(page.getByText("ARCHIVE_CLOSED")).toBeVisible();
  const closedAlert = page.getByRole("alert").filter({ hasText: "该提交已归档或关闭" });
  await expect(closedAlert).toBeVisible();
  expect(await closedAlert.evaluate((element) => element.closest(".compare-header__notice") !== null)).toBe(true);
  expect(await closedAlert.evaluate((element) => element.closest(".review-actions") === null)).toBe(true);
  // C5: the 409 re-reads the review and the History together; the re-read
  // facts carry the manual-close disposition shown per §6.4.
  const reviewEvents = apiRequests.filter((request) => request.method === "POST" && request.path.endsWith("/review-events"));
  expect(reviewEvents).toHaveLength(1);
  await expect.poll(() => apiRequests.filter((request) =>
    request.method === "GET" && request.path.split("?")[0] === "/v1/history").length,
    { timeout: 15000 }).toBeGreaterThan(historyGetsBefore);
  await expect(page.getByText("由 reviewer 于").first()).toBeVisible();
  await expect(page.getByText("审核：已通过")).toBeVisible();
  await expect(page.locator(".compare-status .status-tag").filter({ hasText: "已关闭（未归档）" })).toBeVisible();
  await page.getByText("查看关闭理由").first().click();
  await expect(page.getByText("不再需要该提交")).toBeVisible();
  const singleReason = page.getByText("该提交已关闭（未归档）", { exact: true });
  await expect(singleReason).toHaveCount(1);
  const reasonId = await singleReason.getAttribute("id");
  expect(reasonId).toBeTruthy();
  for (const name of ["撤回", "退回", "审核通过"]) {
    const button = page.getByRole("button", { name, exact: true });
    await expect(button).toBeDisabled();
    expect(await button.getAttribute("aria-describedby")).toBe(reasonId);
  }
  await expect(page.getByRole("button", { name: "审核通过", exact: true })).toBeDisabled();
  await screenshot(page, "fe3c-review-closed", 1920);
  await screenshot(page, "fe3c-review-closed", 1280);
  await expectHeaderBreadcrumbVisible(page);
  const backWidthAfter = (await page.getByRole("button", { name: "返回工作台" }).boundingBox())?.width ?? 0;
  expect(backWidthAfter).toBeCloseTo(backWidthBefore ?? -1, 0);
});

test("FE2c 提交超时重试复用同一幂等键并回放同一提交", async ({ page }) => {
  const { apiRequests } = await installFixtureRoutes(page, { submitTimeoutFirst: true });
  await page.goto(browseUrl("PREVIEW", "preview-full"));
  await waitForBrowse(page);
  await page.getByRole("button", { name: "提交", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "确认提交" }).click();
  await expect(dialog.getByText("SERVICE_NOT_READY")).toBeVisible();
  await dialog.getByRole("button", { name: "确认提交" }).click();
  await expect(dialog.getByRole("status", { name: "提交结果" })).toBeVisible({ timeout: 30000 });
  await expect(dialog.getByText("submission-1").first()).toBeVisible();
  const keys = apiRequests.filter((request) => request.path.endsWith("/submit-attempts")).map((request) => request.idempotencyKey);
  expect(keys.length).toBe(2);
  expect(keys[0]).toBeTruthy();
  expect(keys[0]).toBe(keys[1]);
});

test("FE2c 提交被中止时显示原始错误代码", async ({ page }) => {
  await installFixtureRoutes(page, { submitAborted: true });
  await page.goto(browseUrl("PREVIEW", "preview-full"));
  await waitForBrowse(page);
  await page.getByRole("button", { name: "提交", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "确认提交" }).click();
  await expect(dialog.getByText("IMPORT_REJECTED")).toBeVisible({ timeout: 15000 });
  await expect(dialog.getByRole("button", { name: "复制错误代码" })).toBeVisible();
  await screenshot(page, "submit-aborted", 1920);
  await expect(dialog.getByText("IMPORT_REJECTED")).toBeInViewport();
  await screenshot(page, "submit-aborted", 1280);
  await expect(dialog.getByText("IMPORT_REJECTED")).toBeInViewport();
});

test("FE3c 归档 403、审计冲突与阻断项", async ({ page }) => {
  await installFixtureRoutes(page, { archiveForbidden: true, approvedSubmission: true });
  await page.goto("/");
  await page.getByRole("button", { name: "提交 2", exact: true }).click();
  await page.getByRole("combobox", { name: "模拟身份" }).selectOption("archive-confirmer");
  await page.locator(".workspace-context-bar").getByRole("button", { name: "归档主线" }).click();
  const forbidden = page.getByRole("dialog", { name: "归档主基线" });
  await expect(forbidden.getByText("SCOPE_FORBIDDEN")).toBeVisible();
  await expect(forbidden.getByText("当前身份没有预检归档方案的权限")).toBeVisible();
  await screenshot(page, "archive-permission-denied", 1920);
  await screenshot(page, "archive-permission-denied", 1280);

  await page.unrouteAll({ behavior: "wait" });
  const conflict = await installFixtureRoutes(page, { archiveConflict: "ARCHIVE_AUDIT_VERSION_CONFLICT", approvedSubmission: true });
  await page.reload();
  await page.getByRole("button", { name: "提交 2", exact: true }).click();
  await page.getByRole("combobox", { name: "模拟身份" }).selectOption("archive-confirmer");
  await page.locator(".workspace-context-bar").getByRole("button", { name: "归档主线" }).click();
  const dialog = page.getByRole("dialog", { name: "归档主基线" });
  await dialog.getByRole("checkbox", { name: /确认把/ }).check();
  await dialog.locator(".archive-anomaly").getByRole("button", { name: "接受" }).click();
  const acceptAnomaly = page.getByRole("dialog", { name: "接受异常" });
  await acceptAnomaly.getByLabel("接受理由").fill("已核对项目身份例外");
  await acceptAnomaly.getByRole("button", { name: "确认接受" }).click();
  await dialog.getByRole("button", { name: "确认归档" }).click();
  await expect(dialog.getByText("ARCHIVE_AUDIT_VERSION_CONFLICT")).toBeVisible({ timeout: 15000 });
  await expect(dialog.getByRole("button", { name: "复制错误代码" })).toBeVisible();
  const refreshPreflight = dialog.locator("footer").getByRole("button", { name: "重新预检" });
  await expect(refreshPreflight).toBeVisible();
  await expect(refreshPreflight).toBeInViewport();
  await expect(dialog.getByText("ARCHIVE_AUDIT_VERSION_CONFLICT")).toBeInViewport();
  await screenshot(page, "archive-audit-conflict", 1920);
  await expect(refreshPreflight).toBeInViewport();
  await expect(dialog.getByText("ARCHIVE_AUDIT_VERSION_CONFLICT")).toBeInViewport();
  await screenshot(page, "archive-audit-conflict", 1280);
  await expect(refreshPreflight).toBeInViewport();
  await expect(dialog.getByText("ARCHIVE_AUDIT_VERSION_CONFLICT")).toBeInViewport();
  expect(conflict.apiRequests.find((request) => request.path === "/v1/archives")?.token).toBe("Bearer dev-token-archive-confirmer");

  await page.unrouteAll({ behavior: "wait" });
  await installFixtureRoutes(page, { archiveBlocked: true, approvedSubmission: true });
  await page.reload();
  await page.getByRole("button", { name: "提交 2", exact: true }).click();
  await page.locator(".workspace-context-bar").getByRole("button", { name: "归档主线" }).click();
  const blocked = page.getByRole("dialog", { name: "归档主基线" });
  await expect(blocked.getByText("ACTIVE_SUBMIT_ATTEMPT", { exact: true })).toBeVisible();
  await expect(blocked.getByRole("button", { name: "确认归档" })).toBeDisabled();
  await screenshot(page, "archive-blocked", 1920);
  await screenshot(page, "archive-blocked", 1280);
});

test("FE2c 执行中刷新后恢复页面锁定并继续到差异浏览", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await installFixtureRoutes(page, { uploadHoldPolls: 8 });
  // C4: pin the clock so the running upload card shows a fixed waited duration.
  await freezePageClock(page);
  await page.goto("/");
  const card = page.getByLabel("上传与预览");
  await expect(card).toBeVisible();
  await setDirectoryInput(page, "upload-modified-input", "station_cfg_0921", VALID_DIRECTORY);
  await card.getByRole("button", { name: "上传并生成预览" }).click();
  await expect(page.locator(".page-lock-overlay")).toBeVisible();
  await expect(card.getByText("解析预览")).toBeVisible();
  await expect(page).toHaveURL(/operationId=preview-op-1/);
  await screenshot(page, "upload-running-modified-only", 1920);
  await screenshot(page, "upload-running-modified-only", 1280);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.reload();
  await expect(page.locator(".page-lock-overlay")).toBeVisible();
  await expect(page.locator(".workspace-topbar")).toHaveJSProperty("inert", true);
  await expect(page.locator(".workspace-layout")).toHaveJSProperty("inert", true);
  await expect(page.getByRole("region", { name: "操作状态" })).toBeVisible();
  await expect(page).toHaveURL(/mode=PREVIEW/, { timeout: 60000 });
  await waitForBrowse(page);
  expect(new URL(page.url()).searchParams.get("operationId")).toBeNull();
});

/** Submit button's own disabled reason in the Preview header (never the alert copy). */
function submitReasonWrap(page: Page) {
  return page.locator(".compare-actions").locator("span.button-wrap", {
    has: page.getByRole("button", { name: "提交", exact: true }),
  });
}

test("n3/W9① 提交续做在操作结束后重读 ABORTED 并恢复可用（B3 可达序列）", async ({ page }) => {
  // Reachable backend sequence: at load the attempt is PREPARED and the
  // operation RUNNING; after the terminal FAILED the attempt is ABORTED with
  // an abort_code and both pointers are cleared. The resume path re-reads the
  // attempt by its known ID, so the message carries IMPORT_REJECTED instead
  // of the stale PREPARED snapshot.
  let releaseOperation!: () => void;
  const released = new Promise<void>((resolve) => { releaseOperation = () => resolve(); });
  let holdOperation!: () => void;
  const held = new Promise<void>((resolve) => { holdOperation = () => resolve(); });
  const fixtureOptions: Parameters<typeof installFixtureRoutes>[1] = {
    workspaceSubmitAttemptId: "attempt-1",
    submitAttemptState: "PREPARED",
    clearWorkspacePointer: false,
    operationHold: { operationId: "submit-op-1", onHold: holdOperation, release: released },
    operationStatus: (operationId) => operationId === "submit-op-1"
      ? { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId, status: "FAILED" as const }
      : { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId },
  };
  const { apiRequests } = await installFixtureRoutes(page, fixtureOptions);
  await page.goto(browseUrl("PREVIEW", "preview-full", { operationId: "submit-op-1", operationKind: "operation" }));
  await waitForBrowse(page);
  const submit = page.getByRole("button", { name: "提交", exact: true });
  await held;
  await expect(page.getByRole("region", { name: "操作状态" })).toBeVisible();
  await expect(submit).toBeDisabled();
  await expect(page.getByText("提交正在执行，完成后才能继续")).toBeVisible();
  fixtureOptions.submitAttemptState = "ABORTED";
  fixtureOptions.clearWorkspacePointer = true;
  releaseOperation();
  await expect(page.getByText("提交未完成，请检查上传与 Preview 后重试")).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("IMPORT_REJECTED")).toBeVisible();
  await expect(submit).toBeEnabled();
  // G1 (r2a): retry keeps the original prompt and code instead of clearing
  // the attempt. Both pointers are empty, so the hook re-reads the attempt
  // by the known ID and stays on the ABORTED copy.
  const attemptReadsBeforeR2a = apiRequests.filter((request) =>
    request.method === "GET" && request.path.includes("/submit-attempts/")).length;
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect.poll(() => apiRequests.filter((request) =>
    request.method === "GET" && request.path.includes("/submit-attempts/")).length,
    { timeout: 15000 }).toBeGreaterThan(attemptReadsBeforeR2a);
  await expect(page.getByRole("alert").getByText("提交未完成，请检查上传与 Preview 后重试")).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("IMPORT_REJECTED")).toBeVisible();
  await expect(submit).toBeEnabled();
});

test("W9② 操作结束后 attempt 读不到时禁用并可重试恢复", async ({ page }) => {
  let releaseOperation!: () => void;
  const released = new Promise<void>((resolve) => { releaseOperation = () => resolve(); });
  let holdOperation!: () => void;
  const held = new Promise<void>((resolve) => { holdOperation = () => resolve(); });
  const fixtureOptions: Parameters<typeof installFixtureRoutes>[1] = {
    workspaceSubmitAttemptId: "attempt-1",
    submitAttemptState: "PREPARED",
    submitAttemptReadFails: false,
    operationHold: { operationId: "submit-op-1", onHold: holdOperation, release: released },
    operationStatus: (operationId) => operationId === "submit-op-1"
      ? { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId, status: "FAILED" as const }
      : { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId },
  };
  await installFixtureRoutes(page, fixtureOptions);
  await page.goto(browseUrl("PREVIEW", "preview-full", { operationId: "submit-op-1", operationKind: "operation" }));
  await waitForBrowse(page);
  const submit = page.getByRole("button", { name: "提交", exact: true });
  await held;
  fixtureOptions.submitAttemptReadFails = true;
  releaseOperation();
  // F1: the prompt and the submit button's own disabled reason come from the
  // same snapshot — assert each in its own place, not via first().
  await expect(page.getByRole("alert").getByText("无法确认提交状态")).toBeVisible({ timeout: 15000 });
  await expect(submit).toBeDisabled();
  await expect(submitReasonWrap(page).getByText("无法确认提交状态")).toBeVisible();
  // The gates and the notice come from the same re-read snapshot, so the
  // executing copy must be gone once the read fails.
  await expect(page.getByText("提交正在执行，完成后才能继续")).toHaveCount(0);
  fixtureOptions.submitAttemptReadFails = false;
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(page.getByRole("alert").getByText("提交结果待确认，需要管理员处理")).toBeVisible({ timeout: 15000 });
  await expect(submitReasonWrap(page).getByText("提交结果待确认，需要管理员处理")).toBeVisible();
  // F1 demo a: retry re-derives the prompt, the old one must be gone.
  await expect(page.getByText("无法确认提交状态")).toHaveCount(0);
  await expect(submit).toBeDisabled();
});

test("W9③ 操作结束后工作区读不到时禁用并可重试恢复", async ({ page }) => {
  let releaseOperation!: () => void;
  const released = new Promise<void>((resolve) => { releaseOperation = () => resolve(); });
  let holdOperation!: () => void;
  const held = new Promise<void>((resolve) => { holdOperation = () => resolve(); });
  const fixtureOptions: Parameters<typeof installFixtureRoutes>[1] = {
    workspaceSubmitAttemptId: "attempt-1",
    submitAttemptState: "PREPARED",
    workspaceReadFails: false,
    operationHold: { operationId: "submit-op-1", onHold: holdOperation, release: released },
    operationStatus: (operationId) => operationId === "submit-op-1"
      ? { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId, status: "FAILED" as const }
      : { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId },
  };
  await installFixtureRoutes(page, fixtureOptions);
  await page.goto(browseUrl("PREVIEW", "preview-full", { operationId: "submit-op-1", operationKind: "operation" }));
  await waitForBrowse(page);
  const submit = page.getByRole("button", { name: "提交", exact: true });
  await held;
  fixtureOptions.workspaceReadFails = true;
  releaseOperation();
  await expect(page.getByRole("alert").getByText("无法确认提交状态")).toBeVisible({ timeout: 15000 });
  await expect(submit).toBeDisabled();
  await expect(submitReasonWrap(page).getByText("无法确认提交状态")).toBeVisible();
  fixtureOptions.workspaceReadFails = false;
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(page.getByRole("alert").getByText("提交结果待确认，需要管理员处理")).toBeVisible({ timeout: 15000 });
  await expect(submitReasonWrap(page).getByText("提交结果待确认，需要管理员处理")).toBeVisible();
  // F1 demo a: retry re-derives the prompt, the old one must be gone.
  await expect(page.getByText("无法确认提交状态")).toHaveCount(0);
  await expect(submit).toBeDisabled();
});

test("W9③b 工作区恢复后指针为空时按已知ID重读attempt", async ({ page }) => {
  // G1 §6.2 step 2d: retry finds the workspace readable with both pointers
  // empty, so it re-reads the attempt by the known ID and renders the prompt
  // from that read. Only calling refresh() would leave no attempt read.
  let releaseOperation!: () => void;
  const released = new Promise<void>((resolve) => { releaseOperation = () => resolve(); });
  let holdOperation!: () => void;
  const held = new Promise<void>((resolve) => { holdOperation = () => resolve(); });
  const fixtureOptions: Parameters<typeof installFixtureRoutes>[1] = {
    workspaceSubmitAttemptId: "attempt-1",
    submitAttemptState: "PREPARED",
    workspaceReadFails: false,
    submitAttemptReadFails: false,
    clearWorkspacePointer: false,
    operationHold: { operationId: "submit-op-1", onHold: holdOperation, release: released },
    operationStatus: (operationId) => operationId === "submit-op-1"
      ? { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId, status: "FAILED" as const }
      : { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId },
  };
  const { apiRequests } = await installFixtureRoutes(page, fixtureOptions);
  await page.goto(browseUrl("PREVIEW", "preview-full", { operationId: "submit-op-1", operationKind: "operation" }));
  await waitForBrowse(page);
  const submit = page.getByRole("button", { name: "提交", exact: true });
  await held;
  fixtureOptions.workspaceReadFails = true;
  releaseOperation();
  await expect(page.getByRole("alert").getByText("无法确认提交状态")).toBeVisible({ timeout: 15000 });
  await expect(submit).toBeDisabled();
  // Workspace recovers with both pointers empty; the attempt is ABORTED and
  // readable by the known ID.
  fixtureOptions.workspaceReadFails = false;
  fixtureOptions.clearWorkspacePointer = true;
  fixtureOptions.submitAttemptState = "ABORTED";
  const attemptReadsBefore = apiRequests.filter((request) =>
    request.method === "GET" && request.path.includes("/submit-attempts/")).length;
  const workspaceReadsBefore = apiRequests.filter((request) =>
    request.method === "POST" && request.path === "/v1/workspaces").length;
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect.poll(() => apiRequests.filter((request) =>
    request.method === "POST" && request.path === "/v1/workspaces").length,
    { timeout: 15000 }).toBeGreaterThan(workspaceReadsBefore);
  await expect(page.getByRole("alert").getByText("提交未完成，请检查上传与 Preview 后重试")).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("IMPORT_REJECTED")).toBeVisible();
  await expect(submit).toBeEnabled();
  const attemptReads = apiRequests.filter((request) =>
    request.method === "GET" && request.path.includes("/submit-attempts/"));
  expect(attemptReads.length).toBeGreaterThan(attemptReadsBefore);
  expect(attemptReads.some((request) => request.path.includes("attempt-1"))).toBe(true);
});

test("W9④ 指针已清空但 attempt 读不到时可用并提示刷新后重试", async ({ page }) => {
  // G1 §6.2 step 2: both pointers are empty yet the attempt cannot be read —
  // the submit stays available with the unreadable-result copy. Retry keeps
  // the original prompt while the attempt stays unreadable, and shows the
  // ABORTED copy with the original code once the attempt becomes readable.
  let releaseOperation!: () => void;
  const released = new Promise<void>((resolve) => { releaseOperation = () => resolve(); });
  let holdOperation!: () => void;
  const held = new Promise<void>((resolve) => { holdOperation = () => resolve(); });
  const fixtureOptions: Parameters<typeof installFixtureRoutes>[1] = {
    workspaceSubmitAttemptId: "attempt-1",
    // Like W9②③ the attempt is open at load (the fixture default FINALIZED
    // would make the load snapshot stale); it is only unreadable at resume.
    submitAttemptState: "PREPARED",
    submitAttemptReadFails: false,
    clearWorkspacePointer: false,
    operationHold: { operationId: "submit-op-1", onHold: holdOperation, release: released },
    operationStatus: (operationId) => operationId === "submit-op-1"
      ? { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId, status: "FAILED" as const }
      : { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId },
  };
  const { apiRequests } = await installFixtureRoutes(page, fixtureOptions);
  await page.goto(browseUrl("PREVIEW", "preview-full", { operationId: "submit-op-1", operationKind: "operation" }));
  await waitForBrowse(page);
  const submit = page.getByRole("button", { name: "提交", exact: true });
  await held;
  // The resume re-read finds the pointers cleared with the attempt unreadable.
  fixtureOptions.submitAttemptReadFails = true;
  fixtureOptions.clearWorkspacePointer = true;
  releaseOperation();
  await expect(page.getByRole("alert").getByText("无法读取提交结果，请刷新后重试")).toBeVisible({ timeout: 15000 });
  await expect(submit).toBeEnabled();
  const attemptReadsBeforeRetry = apiRequests.filter((request) =>
    request.method === "GET" && request.path.includes("/submit-attempts/")).length;
  const workspaceReadsBeforeRetry = apiRequests.filter((request) =>
    request.method === "POST" && request.path === "/v1/workspaces").length;
  // Retry while the attempt is still unreadable keeps the original prompt
  // (the hook re-reads the attempt by the known ID instead of clearing it).
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect.poll(() => apiRequests.filter((request) =>
    request.method === "POST" && request.path === "/v1/workspaces").length,
    { timeout: 15000 }).toBeGreaterThan(workspaceReadsBeforeRetry);
  await expect(page.getByRole("alert").getByText("无法读取提交结果，请刷新后重试")).toBeVisible({ timeout: 15000 });
  await expect(submit).toBeEnabled();
  await expect(page.getByText("IMPORT_REJECTED")).toHaveCount(0);
  expect(apiRequests.filter((request) =>
    request.method === "GET" && request.path.includes("/submit-attempts/")).length)
    .toBeGreaterThan(attemptReadsBeforeRetry);
  // The attempt becomes readable as ABORTED: retry shows the unfinished copy
  // with the original code.
  fixtureOptions.submitAttemptReadFails = false;
  fixtureOptions.submitAttemptState = "ABORTED";
  const workspaceReadsBeforeSecond = apiRequests.filter((request) =>
    request.method === "POST" && request.path === "/v1/workspaces").length;
  const attemptReadsBeforeSecond = apiRequests.filter((request) =>
    request.method === "GET" && request.path.includes("/submit-attempts/")).length;
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect.poll(() => apiRequests.filter((request) =>
    request.method === "POST" && request.path === "/v1/workspaces").length,
    { timeout: 15000 }).toBeGreaterThan(workspaceReadsBeforeSecond);
  await expect(page.getByRole("alert").getByText("提交未完成，请检查上传与 Preview 后重试")).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("IMPORT_REJECTED")).toBeVisible();
  await expect(submit).toBeEnabled();
  await expect(page.getByText("无法读取提交结果，请刷新后重试")).toHaveCount(0);
  // C2: the second retry re-reads the attempt by the known ID, so its content
  // is distinguished from the pre-retry snapshot by a fresh attempt read.
  await expect.poll(() => apiRequests.filter((request) =>
    request.method === "GET" && request.path.includes("/submit-attempts/")).length,
    { timeout: 15000 }).toBeGreaterThan(attemptReadsBeforeSecond);
});

test("C2 重试快速连点两次只读取一次工作区与一次 attempt", async ({ page }) => {
  // C2: a rapid double click while the first retry's workspace read is in
  // flight must join the same read sequence — exactly one workspace read and
  // one attempt read, not two.
  let releaseOperation!: () => void;
  const released = new Promise<void>((resolve) => { releaseOperation = () => resolve(); });
  let holdOperation!: () => void;
  const held = new Promise<void>((resolve) => { holdOperation = () => resolve(); });
  const fixtureOptions: Parameters<typeof installFixtureRoutes>[1] = {
    workspaceSubmitAttemptId: "attempt-1",
    submitAttemptState: "PREPARED",
    submitAttemptReadFails: false,
    clearWorkspacePointer: false,
    operationHold: { operationId: "submit-op-1", onHold: holdOperation, release: released },
    operationStatus: (operationId) => operationId === "submit-op-1"
      ? { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId, status: "FAILED" as const }
      : { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId },
  };
  const { apiRequests } = await installFixtureRoutes(page, fixtureOptions);
  await page.goto(browseUrl("PREVIEW", "preview-full", { operationId: "submit-op-1", operationKind: "operation" }));
  await waitForBrowse(page);
  await held;
  fixtureOptions.submitAttemptReadFails = true;
  fixtureOptions.clearWorkspacePointer = true;
  releaseOperation();
  await expect(page.getByRole("alert").getByText("无法读取提交结果，请刷新后重试")).toBeVisible({ timeout: 15000 });

  let releasePost!: () => void;
  const postReleased = new Promise<void>((resolve) => { releasePost = () => resolve(); });
  let holdPost!: () => void;
  const postHeld = new Promise<void>((resolve) => { holdPost = () => resolve(); });
  fixtureOptions.workspacePostHold = { onHold: holdPost, release: postReleased };

  const workspaceReadsBefore = apiRequests.filter((request) => request.method === "POST" && request.path === "/v1/workspaces").length;
  const attemptReadsBefore = apiRequests.filter((request) => request.method === "GET" && request.path.includes("/submit-attempts/")).length;
  const retry = page.getByRole("button", { name: "重试", exact: true });
  await retry.click();
  await postHeld;
  await retry.click();
  releasePost();

  await expect.poll(() => apiRequests.filter((request) => request.method === "POST" && request.path === "/v1/workspaces").length, { timeout: 15000 }).toBe(workspaceReadsBefore + 1);
  await expect.poll(() => apiRequests.filter((request) => request.method === "GET" && request.path.includes("/submit-attempts/")).length, { timeout: 15000 }).toBe(attemptReadsBefore + 1);
  await expect(page.getByRole("alert").getByText("无法读取提交结果，请刷新后重试")).toBeVisible({ timeout: 15000 });
  expect(apiRequests.filter((request) => request.method === "POST" && request.path === "/v1/workspaces")).toHaveLength(workspaceReadsBefore + 1);
  expect(apiRequests.filter((request) => request.method === "GET" && request.path.includes("/submit-attempts/"))).toHaveLength(attemptReadsBefore + 1);
});

test("C1 续做后开始新的提交时红色提示框清除", async ({ page }) => {
  // C1: after a resume the notice belongs to the resume snapshot. Starting a
  // new submit clears it, so the re-submitted "executing" gate reason is not
  // shown in the red alert box.
  let releaseOperation!: () => void;
  const released = new Promise<void>((resolve) => { releaseOperation = () => resolve(); });
  let holdOperation!: () => void;
  const held = new Promise<void>((resolve) => { holdOperation = () => resolve(); });
  const fixtureOptions: Parameters<typeof installFixtureRoutes>[1] = {
    workspaceSubmitAttemptId: "attempt-1",
    submitAttemptState: "PREPARED",
    submitAttemptReadFails: false,
    clearWorkspacePointer: false,
    operationHold: { operationId: "submit-op-1", onHold: holdOperation, release: released },
    operationStatus: (operationId) => operationId === "submit-op-1"
      ? { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId, status: "FAILED" as const }
      : { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId },
  };
  await installFixtureRoutes(page, fixtureOptions);
  await page.goto(browseUrl("PREVIEW", "preview-full", { operationId: "submit-op-1", operationKind: "operation" }));
  await waitForBrowse(page);
  const submit = page.getByRole("button", { name: "提交", exact: true });
  await held;
  fixtureOptions.workspaceReadFails = true;
  releaseOperation();
  await expect(page.getByRole("alert").getByText("无法确认提交状态")).toBeVisible({ timeout: 15000 });
  fixtureOptions.workspaceReadFails = false;
  fixtureOptions.clearWorkspacePointer = true;
  fixtureOptions.submitAttemptState = "ABORTED";
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(page.getByRole("alert").getByText("提交未完成，请检查上传与 Preview 后重试")).toBeVisible({ timeout: 15000 });
  await expect(submit).toBeEnabled();
  // Starting a new submit opens the dialog and clears the resume notice.
  await submit.click();
  await expect(page.getByRole("dialog", { name: "提交本次组态" })).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole("alert").getByText("提交未完成，请检查上传与 Preview 后重试")).toHaveCount(0);
});

test("工作台续做提示重试时按已知 attempt 重读并保留原提示", async ({ page }) => {
  // Workbench counterpart of n3/W9①: after the terminal FAILED both pointers
  // are cleared while the attempt is ABORTED. The notice retry shares the
  // hook entry with the Preview page, so it re-reads the attempt by the known
  // ID and stays on the unfinished copy with the original code.
  let releaseOperation!: () => void;
  const released = new Promise<void>((resolve) => { releaseOperation = () => resolve(); });
  let holdOperation!: () => void;
  const held = new Promise<void>((resolve) => { holdOperation = () => resolve(); });
  const fixtureOptions: Parameters<typeof installFixtureRoutes>[1] = {
    workspaceSubmitAttemptId: "attempt-1",
    submitAttemptState: "PREPARED",
    clearWorkspacePointer: false,
    operationHold: { operationId: "submit-op-1", onHold: holdOperation, release: released },
    operationStatus: (operationId) => operationId === "submit-op-1"
      ? { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId, status: "FAILED" as const }
      : { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId },
  };
  const { apiRequests } = await installFixtureRoutes(page, fixtureOptions);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/?page=workspace&operationId=submit-op-1&operationKind=operation");
  // The mount read follows the attempt chain into the held operation, so the
  // workbench stays on its loading skeleton until the operation is released.
  await held;
  // The terminal FAILED clears both pointers while the attempt is ABORTED.
  fixtureOptions.submitAttemptState = "ABORTED";
  fixtureOptions.clearWorkspacePointer = true;
  releaseOperation();
  await expect(page.getByRole("heading", { name: "组态树", level: 1 })).toBeVisible({ timeout: 15000 });
  const notice = page.locator(".workspace-notice[role=\"alert\"]");
  await expect(notice.getByText("提交未完成，请检查上传与 Preview 后重试")).toBeVisible({ timeout: 15000 });
  await expect(notice.getByText("IMPORT_REJECTED")).toBeVisible();
  await expect(notice.getByText("原始代码")).toBeVisible();
  // The upload gate is released (only the directory prerequisite remains), so
  // selecting a directory makes both upload entries available.
  await page.getByRole("button", { name: "工作区 gateway-17", exact: true }).click();
  await setDirectoryInput(page, "upload-modified-input", "station_cfg_0921", VALID_DIRECTORY);
  const cardUpload = page.getByLabel("上传与预览").getByRole("button", { name: "上传并生成预览" });
  await expect(cardUpload).toBeEnabled({ timeout: 15000 });
  const toolbarUpload = page.locator(".workspace-actions").getByRole("button", { name: "上传", exact: true });
  await expect(toolbarUpload).toBeEnabled({ timeout: 15000 });
  // The retry affordance lives inside the notice; the workbench has other
  // "重试" buttons (compare tray, history drawer) that must not be clicked.
  const attemptReadsBeforeRetry = apiRequests.filter((request) =>
    request.method === "GET" && request.path.includes("/submit-attempts/")).length;
  await notice.getByRole("button", { name: "重试", exact: true }).click();
  await expect.poll(() => apiRequests.filter((request) =>
    request.method === "GET" && request.path.includes("/submit-attempts/")).length,
    { timeout: 15000 }).toBeGreaterThan(attemptReadsBeforeRetry);
  await expect(notice.getByText("提交未完成，请检查上传与 Preview 后重试")).toBeVisible({ timeout: 15000 });
  await expect(notice.getByText("IMPORT_REJECTED")).toBeVisible();
  await expect(cardUpload).toBeEnabled();
  await expect(toolbarUpload).toBeEnabled();
});

test("工作台续做提示重试时读不到提交结果仍保留刷新提示", async ({ page }) => {
  // Workbench counterpart of W9④: with both pointers cleared and the attempt
  // unreadable, retry keeps the unreadable-result copy instead of clearing it.
  let releaseOperation!: () => void;
  const released = new Promise<void>((resolve) => { releaseOperation = () => resolve(); });
  let holdOperation!: () => void;
  const held = new Promise<void>((resolve) => { holdOperation = () => resolve(); });
  const fixtureOptions: Parameters<typeof installFixtureRoutes>[1] = {
    workspaceSubmitAttemptId: "attempt-1",
    submitAttemptState: "PREPARED",
    submitAttemptReadFails: false,
    clearWorkspacePointer: false,
    operationHold: { operationId: "submit-op-1", onHold: holdOperation, release: released },
    operationStatus: (operationId) => operationId === "submit-op-1"
      ? { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId, status: "FAILED" as const }
      : { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId },
  };
  const { apiRequests } = await installFixtureRoutes(page, fixtureOptions);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/?page=workspace&operationId=submit-op-1&operationKind=operation");
  // The mount read follows the attempt chain into the held operation, so the
  // workbench stays on its loading skeleton until the operation is released.
  await held;
  fixtureOptions.submitAttemptReadFails = true;
  fixtureOptions.clearWorkspacePointer = true;
  releaseOperation();
  await expect(page.getByRole("heading", { name: "组态树", level: 1 })).toBeVisible({ timeout: 15000 });
  const notice = page.locator(".workspace-notice[role=\"alert\"]");
  await expect(notice.getByText("无法读取提交结果，请刷新后重试")).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("IMPORT_REJECTED")).toHaveCount(0);
  await page.getByRole("button", { name: "工作区 gateway-17", exact: true }).click();
  await setDirectoryInput(page, "upload-modified-input", "station_cfg_0921", VALID_DIRECTORY);
  const cardUpload = page.getByLabel("上传与预览").getByRole("button", { name: "上传并生成预览" });
  await expect(cardUpload).toBeEnabled({ timeout: 15000 });
  const toolbarUpload = page.locator(".workspace-actions").getByRole("button", { name: "上传", exact: true });
  await expect(toolbarUpload).toBeEnabled({ timeout: 15000 });
  const attemptReadsBeforeRetry = apiRequests.filter((request) =>
    request.method === "GET" && request.path.includes("/submit-attempts/")).length;
  await notice.getByRole("button", { name: "重试", exact: true }).click();
  await expect.poll(() => apiRequests.filter((request) =>
    request.method === "GET" && request.path.includes("/submit-attempts/")).length,
    { timeout: 15000 }).toBeGreaterThan(attemptReadsBeforeRetry);
  await expect(notice.getByText("无法读取提交结果，请刷新后重试")).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("IMPORT_REJECTED")).toHaveCount(0);
  await expect(cardUpload).toBeEnabled();
  await expect(toolbarUpload).toBeEnabled();
});

test("F2 attempt 已结束但指针未清时按过时重读且不解锁上传", async ({ page }) => {
  // First read: only the attempt pointer is set but the attempt is already
  // FINALIZED — a stale snapshot. The hook re-reads once while keeping the
  // upload disabled; the second read finds the submission pointer (PENDING).
  const stale = {
    ...WORKSPACE_CREATED.body,
    active_submit_attempt_id: "attempt-1",
    active_submission_id: null,
  } satisfies Schemas["WorkspaceResponse"];
  const recovered = {
    ...WORKSPACE_CREATED.body,
    active_submission_id: "submission-1",
    active_submit_attempt_id: null,
  } satisfies Schemas["WorkspaceResponse"];
  const { apiRequests } = await installFixtureRoutes(page, {
    workspaceSequence: [stale, recovered],
    submitAttemptState: "FINALIZED",
    // The submit operation stays polling (RUNNING): a terminal operation would
    // resume-navigate the workbench to the review page, while this case asserts
    // the workbench stays with the upload disabled through the stale window.
    operationById: {
      "submit-op-1": { ...TEST_OPERATION_SUCCEEDED, operation_id: "submit-op-1", job_kind: "backend-vnext/submit", status: "RUNNING" as const, completed_at: null },
    },
  });
  await page.goto("/?page=workspace");
  const upload = page.locator(".workspace-actions").getByRole("button", { name: "上传", exact: true });
  await expect(upload).toBeDisabled({ timeout: 15000 });
  // The stale snapshot must never unlock the upload; the recovered snapshot
  // reports the pending submission.
  await expect(page.locator(".workspace-actions").getByText("已有待审核的提交，撤回后才能重新上传")).toBeVisible({ timeout: 15000 });
  await expect(upload).toBeDisabled();
  await expect(page.locator(".workspace-actions").getByText("无法确认提交状态")).toHaveCount(0);
  // Exactly the mount read plus the single stale re-read: without F2 the
  // stale snapshot unlocks the upload and no re-read happens.
  expect(apiRequests.filter((request) => request.method === "POST" && request.path === "/v1/workspaces")).toHaveLength(2);
});

test("URL 中的提交操作与指针不一致时以指针为准（job_kind）", async ({ page }) => {
  await installFixtureRoutes(page, {
    workspaceSubmitAttemptId: "attempt-1",
    submitAttemptState: "PREPARED",
    operationById: {
      "other-submit-op": { ...TEST_OPERATION_SUCCEEDED, operation_id: "other-submit-op", job_kind: "backend-vnext/submit", status: "RUNNING" as const, completed_at: null },
      "submit-op-1": { ...TEST_OPERATION_SUCCEEDED, operation_id: "submit-op-1", job_kind: "backend-vnext/submit", status: "RUNNING" as const, completed_at: null },
    },
  });
  await page.goto(browseUrl("PREVIEW", "preview-full", { operationId: "other-submit-op", operationKind: "operation" }));
  await waitForBrowse(page);
  await expect.poll(() => new URL(page.url()).searchParams.get("operationId"), { timeout: 15000 }).toBe("submit-op-1");
});

test("URL 中的 Preview 操作不被提交指针覆盖（job_kind）", async ({ page }) => {
  await installFixtureRoutes(page, {
    workspaceSubmitAttemptId: "attempt-1",
    submitAttemptState: "PREPARED",
    operationById: {
      "preview-op-9": { ...TEST_OPERATION_SUCCEEDED, operation_id: "preview-op-9", job_kind: "backend-vnext/preview", status: "SUCCEEDED" as const, completed_at: "2026-11-03T09:00:02Z" },
      "submit-op-1": { ...TEST_OPERATION_SUCCEEDED, operation_id: "submit-op-1", job_kind: "backend-vnext/submit", status: "RUNNING" as const, completed_at: null },
    },
  });
  await page.goto(browseUrl("PREVIEW", "preview-full", { operationId: "preview-op-9", operationKind: "operation" }));
  await waitForBrowse(page);
  await page.waitForTimeout(2000);
  expect(new URL(page.url()).searchParams.get("operationId")).toBe("preview-op-9");
});

test("FE2c 提交对话框显示需要管理员处理并可跟随到成功", async ({ page }) => {
  test.setTimeout(90000);
  const manual = [
    { ...MANUAL_RECOVERY_TO_SUCCESS[0]!, operation_id: "submit-op-1", job_kind: "backend-vnext/submit" as const },
    { ...MANUAL_RECOVERY_TO_SUCCESS[1]!, operation_id: "submit-op-1", job_kind: "backend-vnext/submit" as const },
    { ...MANUAL_RECOVERY_TO_SUCCESS[2]!, operation_id: "submit-op-1", job_kind: "backend-vnext/submit" as const },
  ];
  await installFixtureRoutes(page, { operationStatus: (_operationId, index) => manual[Math.min(index - 1, manual.length - 1)]! });
  await page.goto(browseUrl("PREVIEW", "preview-full"));
  await waitForBrowse(page);
  await page.getByRole("button", { name: "提交", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "确认提交" }).click();
  await expect(dialog.getByText("需要管理员处理")).toBeVisible({ timeout: 10000 });
  await expect(dialog.getByText("submit-op-1")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "复制 ID" })).toBeVisible();
  await screenshot(page, "submit-manual-recovery", 1920);
  await expect(dialog.getByText("需要管理员处理")).toBeInViewport();
  await screenshot(page, "submit-manual-recovery", 1280);
  await expect(dialog.getByText("需要管理员处理")).toBeInViewport();
  await expect(dialog.getByRole("status", { name: "提交结果" })).toBeVisible({ timeout: 60000 });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await screenshot(page, "submit-result", 1920);
  await screenshot(page, "submit-result", 1280);
});
