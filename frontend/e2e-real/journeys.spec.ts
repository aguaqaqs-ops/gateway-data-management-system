import { test, expect, type Browser, type BrowserContext, type Page, type Response as PlaywrightResponse } from "@playwright/test";
import {
  appendCaseLog,
  collectPageDiagnostics,
  compareAction,
  contextForIdentity,
  expandWorkspaceDetails,
  expectDisabledWithReason,
  expectEnabled,
  gotoWorkbench,
  opfsBundleState,
  recordBundleResponses,
  reviewAction,
  reviewStatus,
  saveEvidence,
  selectTreeRow,
  selectUploadDirs,
  startUpload,
  stepUploadAction,
  treeRow,
  waitForBundleResponse,
  waitForDiffBrowsing,
  waitForInstalledBundle,
  waitForPreviewOutcome,
  workshopAction,
} from "./lib/ui";
import {
  appendArchiveAnomalyResolution,
  applyReview,
  currentWorkspace,
  getPreviewResult,
  getReviewFacts,
  listArchiveCandidates,
  listHistory,
  previewArchivePlan,
  tryApi,
  waitForOperation,
  waitForPendingSubmission,
  type ArchivePlanBody,
  type ReviewFactsBody,
  type WorkspaceBody,
} from "./lib/api";
import { countBundlePairs, digestHex, parseBundleTar, type ParsedBundle } from "./lib/tar";
import { identityFor, inputDir, scopeBySlug, type JourneyIdentity, type JourneyScope } from "./lib/env";

/**
 * FE3b real-backend journeys (kickoff §4.7, §6.1–§6.4).
 *
 * Every test is an independent serial scope: it owns one repository + empty
 * INITIAL baseline (seeded by scripts/run-real-backend-e2e.sh), reads its
 * identities from GATEWAY_FE_IDENTITIES and its upload inputs from
 * GATEWAY_FE_JOURNEY_SCOPES. Workers=1/retries=0 come from
 * playwright.real.config.ts, so scopes never interleave.
 */

const BUNDLE_CONTENT_TYPE = "application/x-tar";
const REVIEW_EVENTS = "/review-events";
const SUBMIT_ATTEMPTS = "/submit-attempts";

test.beforeEach(() => {
  // FULL upload + preview + history compare + submit can exceed the default 300s.
  test.setTimeout(900_000);
});

function requireJourneyEnv(): void {
  const missing = ["GATEWAY_FE_IDENTITIES", "GATEWAY_FE_JOURNEY_SCOPES"].filter((name) => !process.env[name]);
  test.skip(
    missing.length > 0,
    `journeys suite requires ${missing.join(", ")}; run scripts/run-real-backend-e2e.sh --suite journeys`,
  );
}

interface Session {
  context: BrowserContext;
  page: Page;
  diagnostics: ReturnType<typeof collectPageDiagnostics>;
}

async function openSession(browser: Browser, identity: JourneyIdentity): Promise<Session> {
  const context = await contextForIdentity(browser, identity);
  const page = await context.newPage();
  // 1920 keeps the details panel (and the upload card) expanded by default.
  await page.setViewportSize({ width: 1920, height: 1080 });
  return { context, page, diagnostics: collectPageDiagnostics(page) };
}

async function closeSession(session: Session): Promise<void> {
  await session.context.close().catch(() => undefined);
}

// Browsers log every non-2xx fetch as a console error; 403/404/409 are the
// expected outcomes of the permission/conflict journeys. Any other console
// error, and every uncaught page error, fails the scope.
const EXPECTED_CONSOLE = [
  /Failed to load resource/i,
  /net::ERR_/i,
  /the server responded with a status of (401|403|404|409)/i,
];

function assertClean(diagnostics: Session["diagnostics"], phase: string): void {
  expect(diagnostics.pageErrors, `${phase}: uncaught page errors`).toEqual([]);
  const unexpected = diagnostics.consoleErrors.filter((line) => !EXPECTED_CONSOLE.some((pattern) => pattern.test(line)));
  expect(unexpected, `${phase}: unexpected console errors`).toEqual([]);
}

function isPost(response: PlaywrightResponse, suffix: string): boolean {
  return response.request().method() === "POST" && new URL(response.url()).pathname.endsWith(suffix);
}

function countPosts(page: Page, suffix: string): { count: () => number; keys: () => string[] } {
  const keys: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname.endsWith(suffix)) {
      keys.push(request.headers()["idempotency-key"] ?? "");
    }
  });
  return { count: () => keys.length, keys: () => keys };
}

interface UploadRun {
  previewId: string;
  workspaceId: string;
  operationId: string;
  bundle: ParsedBundle;
  status: number;
  previewStatus: number;
  etag: string;
}

/**
 * Browser-driven upload + preview. The upload card packages the directory,
 * POSTs the multipart revision, starts the preview operation, polls it, and
 * installs the tar bundle into OPFS before entering diff browsing.
 */
async function uploadAndPreview(
  page: Page,
  identity: JourneyIdentity,
  scope: JourneyScope,
  input: "modified_only" | "full",
): Promise<UploadRun> {
  const bundleWait = waitForBundleResponse(page, 300_000);
  const uploadWait = page.waitForResponse((response) => isPost(response, "/upload-revisions"), { timeout: 300_000 });
  const previewWait = page.waitForResponse((response) => isPost(response, "/preview-operations"), { timeout: 300_000 });

  if (input === "full") {
    await selectUploadDirs(page, {
      modified: inputDir(scope, "full_modified"),
      initial: inputDir(scope, "full_initial"),
    });
  } else {
    await selectUploadDirs(page, { modified: inputDir(scope, "modified_only") });
  }
  await startUpload(page);

  const upload = await uploadWait;
  expect(upload.status(), "upload-revisions status").toBe(201);
  const preview = await previewWait;
  expect(preview.status(), "preview-operations status").toBe(202);
  const accepted = (await preview.json()) as { operation_id: string };

  const operation = await waitForOperation(identity, accepted.operation_id, 240_000);
  expect(operation.status, `preview operation ${accepted.operation_id}`).toBe("SUCCEEDED");

  const bundleResponse = await bundleWait;
  expect(bundleResponse.status(), "bundle status").toBe(200);
  const body = Buffer.from(await bundleResponse.body());
  const bundle = parseBundleTar(body);

  const contentLength = bundleResponse.headers()["content-length"];
  expect(contentLength, "bundle Content-Length").toBe(String(body.byteLength));
  expect(bundleResponse.headers()["content-type"] ?? "").toContain(BUNDLE_CONTENT_TYPE);
  const etag = (bundleResponse.headers()["etag"] ?? "").replace(/^W\//, "");
  expect(etag, "bundle ETag").toBe(`"${bundle.manifest.bundle_digest}"`);
  expect(digestHex(etag.replace(/^"|"$/g, "")), "ETag digest").toBe(bundle.bundleDigest);

  const outcome = await waitForPreviewOutcome(page);
  expect(outcome, "preview outcome").toBe("compare");
  await waitForDiffBrowsing(page);

  const url = new URL(page.url());
  const previewId = url.searchParams.get("previewResultId");
  const workspaceId = url.searchParams.get("workspaceId");
  expect(previewId, "previewResultId in compare URL").toBeTruthy();
  expect(workspaceId, "workspaceId in compare URL").toBeTruthy();

  return {
    previewId: previewId as string,
    workspaceId: workspaceId as string,
    operationId: accepted.operation_id,
    bundle,
    status: upload.status(),
    previewStatus: preview.status(),
    etag,
  };
}

interface SubmitRun {
  submissionId: string;
  status: number;
  idempotencyKey: string | null;
}

async function submitViaUi(page: Page, identity: JourneyIdentity, workspaceId: string): Promise<SubmitRun> {
  const keys = countPosts(page, SUBMIT_ATTEMPTS);
  const accepted = page.waitForResponse((response) => isPost(response, SUBMIT_ATTEMPTS), { timeout: 300_000 });

  await compareAction(page, "提交").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("heading", { name: "提交本次组态", exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "确认提交", exact: true }).click();

  const response = await accepted;
  expect(response.status(), "submit-attempts status").toBe(202);
  const result = page.locator('section[aria-label="提交结果"]');
  await expect(result).toBeVisible({ timeout: 240_000 });
  await expect(result).toContainText("提交成功，已生成待审核提交。");

  const { submission } = await waitForPendingSubmission(identity, workspaceId, 240_000);
  return {
    submissionId: submission.submission_id,
    status: response.status(),
    idempotencyKey: keys.keys().at(-1) ?? null,
  };
}

async function openReviewPage(page: Page, submissionId: string): Promise<void> {
  await page.goto(`/?page=compare&mode=REVIEW&submissionId=${submissionId}`);
  await expect(page.locator("main.comparison-page")).toBeVisible({ timeout: 60_000 });
  await waitForDiffBrowsing(page);
  await expect(page.locator(".review-actions")).toBeVisible();
}

async function waitForReviewStatus(
  identity: JourneyIdentity,
  submissionId: string,
  status: ReviewFactsBody["status"],
  timeout = 120_000,
): Promise<ReviewFactsBody> {
  let facts: ReviewFactsBody | null = null;
  await expect
    .poll(async () => {
      facts = (await getReviewFacts(identity, submissionId)).body;
      return facts.status;
    }, { timeout, intervals: [250, 500, 1_000] })
    .toBe(status);
  return facts as unknown as ReviewFactsBody;
}

async function rejectInReview(page: Page, reason: string): Promise<PlaywrightResponse> {
  const response = page.waitForResponse((value) => isPost(value, REVIEW_EVENTS), { timeout: 120_000 });
  await reviewAction(page, "退回").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("退回理由").fill(reason);
  await dialog.getByRole("button", { name: "确认退回", exact: true }).click();
  const result = await response;
  expect(result.status(), "review reject status").toBe(201);
  await expect(dialog).toBeHidden({ timeout: 120_000 });
  return result;
}

async function approveInReview(page: Page): Promise<PlaywrightResponse> {
  const response = page.waitForResponse((value) => isPost(value, REVIEW_EVENTS), { timeout: 120_000 });
  await reviewAction(page, "审核通过").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "确认通过", exact: true }).click();
  const result = await response;
  expect(result.status(), "review approve status").toBe(201);
  await expect(dialog).toBeHidden({ timeout: 120_000 });
  return result;
}

/** Withdraw through the PREVIEW header action or the REVIEW header action. */
async function withdrawInUi(page: Page, location: "preview" | "review"): Promise<PlaywrightResponse> {
  const response = page.waitForResponse((value) => isPost(value, REVIEW_EVENTS), { timeout: 120_000 });
  const trigger = location === "preview" ? compareAction(page, "撤回") : reviewAction(page, "撤回");
  await trigger.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("heading", { name: "撤回提交", exact: true })).toBeVisible();
  await dialog.getByLabel("我已了解撤回后需要重新提交，并确认继续").check();
  await dialog.getByRole("button", { name: "确认撤回", exact: true }).click();
  return response;
}

async function expectPointersCleared(identity: JourneyIdentity): Promise<WorkspaceBody> {
  const workspace = await currentWorkspace(identity);
  expect(workspace.active_submission_id, "active_submission_id").toBeNull();
  expect(workspace.active_submit_attempt_id, "active_submit_attempt_id").toBeNull();
  expect(workspace.current_upload_revision_id, "current_upload_revision_id").toBeNull();
  expect(workspace.current_preview_result_id, "current_preview_result_id").toBeNull();
  return workspace;
}

async function gotoWorkbenchFresh(page: Page): Promise<void> {
  await page.goto("/?page=workspace");
  await expect(page.getByRole("heading", { level: 1, name: /组态树/ })).toBeVisible({ timeout: 60_000 });
  await expect(page.locator(".workspace-context-bar")).toBeVisible();
}

/** Upload + preview + submit on a fresh workbench; returns preview and submission ids. */
async function createSubmission(
  page: Page,
  identity: JourneyIdentity,
  scope: JourneyScope,
  input: "modified_only" | "full",
): Promise<{ preview: UploadRun; submission: SubmitRun }> {
  await gotoWorkbenchFresh(page);
  const preview = await uploadAndPreview(page, identity, scope, input);
  const submission = await submitViaUi(page, identity, preview.workspaceId);
  return { preview, submission };
}

// ---------------------------------------------------------------------------
// R1 — CreateOrGet idempotence and tree node states.
// ---------------------------------------------------------------------------
test("r1-states", async ({ browser }, testInfo) => {
  requireJourneyEnv();
  const scope = scopeBySlug("r1-states");
  const submitter = identityFor(scope, "submitter");
  const reviewer = identityFor(scope, "reviewer");
  const session = await openSession(browser, submitter);

  try {
    const statuses: number[] = [];
    session.page.on("response", (response) => {
      if (response.request().method() === "POST" && new URL(response.url()).pathname === "/v1/workspaces") {
        statuses.push(response.status());
      }
    });

    await gotoWorkbench(session.page);
    await expect.poll(() => statuses.length, { timeout: 60_000 }).toBeGreaterThanOrEqual(1);
    expect(statuses[0], "first CreateOrGet").toBe(201);

    await session.page.reload();
    await expect(session.page.locator(".workspace-context-bar")).toBeVisible({ timeout: 60_000 });
    await expect.poll(() => statuses.length, { timeout: 60_000 }).toBeGreaterThanOrEqual(2);
    expect(statuses.slice(1), "refreshed CreateOrGet").toContain(200);

    const baselineRow = treeRow(session.page, "初始基线");
    await expect(baselineRow).toBeVisible();
    await expect(baselineRow).toContainText("初始基线");

    const history = await listHistory(submitter);
    expect(history.body.head.version, "empty INITIAL baseline head version").toBe(0);
    expect(history.body.nodes).toHaveLength(1);
    expect(history.body.nodes[0].baseline_kind).toBe("INITIAL");
    expect(history.body.nodes[0].parent).toBeNull();

    const { submission } = await createSubmission(session.page, submitter, scope, "modified_only");
    await gotoWorkbenchFresh(session.page);
    await expect(treeRow(session.page, "提交 1")).toContainText("待审核");
    expect((await currentWorkspace(submitter)).active_submission_id).toBe(submission.submissionId);

    // Reject with the reviewer identity, then verify the tree state.
    const rejected = await applyReview(reviewer, submission.submissionId, {
      expected_review_version: 0,
      action: "REJECT",
      reason: "r1-states: 退回后验证组态树状态",
    }, `r1-reject-${submission.submissionId}`);
    expect(rejected.status).toBe(201);
    await waitForReviewStatus(reviewer, submission.submissionId, "REJECTED");
    await gotoWorkbenchFresh(session.page);
    await expect(treeRow(session.page, "提交 1")).toContainText("已退回");
    await selectUploadDirs(session.page, { modified: inputDir(scope, "modified_only") });
    await expectEnabled(workshopAction(session.page, "上传"));

    // A second submission is withdrawn, exercising the other terminal state.
    const second = await createSubmission(session.page, submitter, scope, "modified_only");
    expect(second.submission.submissionId).not.toBe(submission.submissionId);
    await gotoWorkbenchFresh(session.page);
    await expect(treeRow(session.page, "提交 2")).toContainText("待审核");
    const withdrawn = await applyReview(submitter, second.submission.submissionId, {
      expected_review_version: 0,
      action: "WITHDRAW",
    }, `r1-withdraw-${second.submission.submissionId}`);
    expect(withdrawn.status).toBe(201);
    await waitForReviewStatus(submitter, second.submission.submissionId, "WITHDRAWN");
    await gotoWorkbenchFresh(session.page);
    await expect(treeRow(session.page, "提交 2")).toContainText("已撤回");
    await expect(treeRow(session.page, "提交 1")).toContainText("已退回");

    assertClean(session.diagnostics, "r1-states");
    appendCaseLog(`r1-states ok create_or_get=${statuses.join(",")} reject=${submission.submissionId} withdraw=${second.submission.submissionId}`);
  } finally {
    await saveEvidence(session.page, testInfo, "r1-states-workbench").catch(() => undefined);
    await closeSession(session);
  }
});

// ---------------------------------------------------------------------------
// R2 preview (MODIFIED_ONLY): one pair, OPFS install, no re-download on reopen.
// ---------------------------------------------------------------------------
test("r2-preview", async ({ browser }, testInfo) => {
  requireJourneyEnv();
  const scope = scopeBySlug("r2-preview");
  const submitter = identityFor(scope, "submitter");
  const session = await openSession(browser, submitter);
  let bundleHits = 0;
  session.page.on("request", (request) => {
    if (new URL(request.url()).pathname.endsWith("/bundle")) bundleHits += 1;
  });

  try {
    await gotoWorkbenchFresh(session.page);
    const run = await uploadAndPreview(session.page, submitter, scope, "modified_only");

    expect(countBundlePairs(run.bundle.manifest), "MODIFIED_ONLY pair count").toBe(1);
    expect(run.bundle.manifest.pairs[0].before_input_index).toBe(0);
    expect(run.bundle.manifest.pairs[0].current_input_index).toBe(1);
    expect(run.bundle.members.length).toBeGreaterThan(2);
    expect(run.bundle.manifest.status).toBe("READY");
    expect(run.bundle.closure.entries.length).toBeGreaterThan(0);

    const preview = await getPreviewResult(submitter, run.workspaceId, run.previewId);
    expect(preview.status).toBe(200);
    expect(preview.body.preview_result_id).toBe(run.previewId);
    expect(preview.body.bundle_digest).toBe(run.bundle.manifest.bundle_digest);

    const opfs = await opfsBundleState(session.page, run.bundle.bundleDigest);
    expect(opfs.hasDigestDir, "OPFS bundle directory").toBe(true);
    expect(opfs.hasManifest, "OPFS manifest.json").toBe(true);
    expect(opfs.hasCompleteMarker, "OPFS complete marker").toBe(true);

    const footer = session.page.locator(".sidebar-footer");
    await expect(footer).toContainText("本地 bundle · 浏览期间不请求后端");
    await expect(footer).toContainText(run.bundle.manifest.bundle_digest.slice(0, 19));

    const tabs = session.page.getByRole("tablist", { name: "比较视图" });
    await expect(tabs.getByRole("tab")).toHaveCount(1);
    await expect(tabs.getByRole("tab").first()).toContainText("当前基线 → 本次归档组态");
    await expect(session.page.locator("section.comparison-content")).toContainText(/表|变更/);

    // Re-opening the same preview in the same context must reuse OPFS.
    const hitsBeforeReopen = bundleHits;
    expect(hitsBeforeReopen, "bundle downloads before reopen").toBeGreaterThanOrEqual(1);
    await session.page.reload();
    await expect(session.page.locator("main.comparison-page")).toBeVisible();
    await waitForDiffBrowsing(session.page);
    expect(bundleHits, "bundle downloads after reopening the same preview").toBe(hitsBeforeReopen);

    await saveEvidence(session.page, testInfo, "r2-preview-diff");
    assertClean(session.diagnostics, "r2-preview");
    appendCaseLog(`r2-preview ok preview=${run.previewId} bundle=${run.bundle.bundleDigest}`);
  } finally {
    await closeSession(session);
  }
});

// ---------------------------------------------------------------------------
// R2 full (FULL A then B): exactly two pairs 0→1 and 1→2.
// ---------------------------------------------------------------------------
test("r2-full", async ({ browser }, testInfo) => {
  requireJourneyEnv();
  const scope = scopeBySlug("r2-full");
  const submitter = identityFor(scope, "submitter");
  const session = await openSession(browser, submitter);

  try {
    await gotoWorkbenchFresh(session.page);
    const run = await uploadAndPreview(session.page, submitter, scope, "full");

    expect(countBundlePairs(run.bundle.manifest), "FULL pair count").toBe(2);
    expect(run.bundle.manifest.pairs.map((pair) => pair.before_input_index)).toEqual([0, 1]);
    expect(run.bundle.manifest.pairs.map((pair) => pair.current_input_index)).toEqual([1, 2]);
    expect(run.bundle.manifest.inputs.map((input) => input.input_index)).toEqual([0, 1, 2]);
    expect(run.bundle.manifest.failed_pairs).toEqual([]);
    expect(run.bundle.manifest.status).toBe("READY");

    const preview = await getPreviewResult(submitter, run.workspaceId, run.previewId);
    expect(preview.body.identity_pairs).toHaveLength(2);

    const tabs = session.page.getByRole("tablist", { name: "比较视图" });
    await expect(tabs.getByRole("tab")).toHaveCount(2);
    await expect(tabs.getByRole("tab", { name: "原始组态视图" })).toBeVisible();
    await expect(tabs.getByRole("tab", { name: "本次组态视图" })).toBeVisible();
    await expect(session.page.locator(".sidebar-footer")).toContainText("本地 bundle");
    await expect(session.page.locator(".grid-frame")).toBeVisible();

    await saveEvidence(session.page, testInfo, "r2-full-diff");
    assertClean(session.diagnostics, "r2-full");
    appendCaseLog(`r2-full ok preview=${run.previewId} pairs=${countBundlePairs(run.bundle.manifest)}`);
  } finally {
    await closeSession(session);
  }
});

// ---------------------------------------------------------------------------
// R3 — a truncated real bundle aborts the install and is recoverable.
// ---------------------------------------------------------------------------
test("r3-truncated", async ({ browser }, testInfo) => {
  requireJourneyEnv();
  const scope = scopeBySlug("r3-truncated");
  const submitter = identityFor(scope, "submitter");
  const session = await openSession(browser, submitter);
  let truncated = 0;
  let realEtag: string | null = null;
  let realLength = 0;
  const bundleRoute = async (route: import("@playwright/test").Route): Promise<void> => {
    const upstream = await route.fetch();
    const body = Buffer.from(await upstream.body());
    realEtag = upstream.headers()["etag"] ?? realEtag;
    realLength = body.byteLength;
    truncated += 1;
    const cut = Math.max(1, Math.min(4_096, Math.floor(body.byteLength / 3)));
    const headers = { ...upstream.headers() };
    delete headers["content-length"];
    delete headers["content-encoding"];
    await route.fulfill({ status: upstream.status(), headers, body: body.subarray(0, body.byteLength - cut) });
  };
  await session.page.route(/\/bundle$/, bundleRoute);

  try {
    await gotoWorkbenchFresh(session.page);
    await selectUploadDirs(session.page, { modified: inputDir(scope, "modified_only") });
    const uploadWait = session.page.waitForResponse((response) => isPost(response, "/upload-revisions"), { timeout: 300_000 });
    await startUpload(session.page);
    expect((await uploadWait).status()).toBe(201);

    const outcome = await waitForPreviewOutcome(session.page);
    expect(outcome, "truncated bundle outcome").toBe("error");
    const error = session.page.locator(".upload-error");
    await expect(error).toBeVisible({ timeout: 120_000 });
    await expect(error).toContainText("预览已生成，但下载比较结果失败，请重试");
    await expect(session.page.getByText("无差异")).toHaveCount(0);
    await expect(session.page.locator("section.comparison-content")).toHaveCount(0);
    await expect(session.page.locator(".grid-frame")).toHaveCount(0);
    expect(truncated, "truncated bundle attempts").toBeGreaterThanOrEqual(2);
    expect(realEtag, "real bundle ETag").toBeTruthy();
    expect(realLength, "real bundle length").toBeGreaterThan(0);

    const etagDigest = digestHex(String(realEtag).replace(/^"|"$/g, ""));
    const half = await opfsBundleState(session.page, etagDigest);
    expect(half.hasCompleteMarker, "no completed bundle after truncation").toBe(false);

    // Re-download from the real backend succeeds and enters diff browsing.
    await session.page.unroute(/\/bundle$/, bundleRoute);
    const recovered = waitForBundleResponse(session.page, 300_000);
    await error.getByRole("button", { name: "重试", exact: true }).click();
    const recoveredResponse = await recovered;
    expect(recoveredResponse.status()).toBe(200);
    const parsed = parseBundleTar(Buffer.from(await recoveredResponse.body()));
    expect(parsed.manifest.status).toBe("READY");
    expect(countBundlePairs(parsed.manifest)).toBe(1);
    await waitForDiffBrowsing(session.page);
    const complete = await opfsBundleState(session.page, parsed.bundleDigest);
    expect(complete.hasCompleteMarker, "bundle completed after re-download").toBe(true);

    await saveEvidence(session.page, testInfo, "r3-recovered-diff");
    assertClean(session.diagnostics, "r3-truncated");
    appendCaseLog(`r3-truncated ok truncations=${truncated} recovered=${parsed.bundleDigest}`);
  } finally {
    await session.page.unroute(/\/bundle$/, bundleRoute).catch(() => undefined);
    await closeSession(session);
  }
});

// ---------------------------------------------------------------------------
// R4 — submit creates a PENDING submission (no approval).
// ---------------------------------------------------------------------------
test("r4-submit", async ({ browser }) => {
  requireJourneyEnv();
  const scope = scopeBySlug("r4-submit");
  const submitter = identityFor(scope, "submitter");
  const session = await openSession(browser, submitter);

  try {
    await gotoWorkbenchFresh(session.page);
    const run = await uploadAndPreview(session.page, submitter, scope, "modified_only");
    const submission = await submitViaUi(session.page, submitter, run.workspaceId);

    const workspace = await currentWorkspace(submitter);
    expect(workspace.active_submission_id).toBe(submission.submissionId);
    expect(workspace.active_submit_attempt_id).toBeNull();
    expect(workspace.current_upload_revision_id).not.toBeNull();
    expect(workspace.current_preview_result_id).not.toBeNull();

    const facts = await waitForReviewStatus(submitter, submission.submissionId, "PENDING");
    expect(facts.review_version).toBe(0);

    await expect(session.page.getByRole("heading", { name: "提交本次组态", exact: true })).toHaveCount(0);
    await session.page.getByRole("button", { name: "关闭", exact: true }).click().catch(() => undefined);
    await gotoWorkbenchFresh(session.page);
    await expect(treeRow(session.page, "提交 1")).toContainText("待审核");
    await expectDisabledWithReason(workshopAction(session.page, "上传"), "已有待审核的提交，撤回后才能重新上传");
    // B1: the UploadStepCard start button is disabled with the same occupancy reason.
    await selectTreeRow(session.page, /工作区/);
    await expandWorkspaceDetails(session.page);
    await selectUploadDirs(session.page, { modified: inputDir(scope, "modified_only") });
    await expectDisabledWithReason(stepUploadAction(session.page), "已有待审核的提交，撤回后才能重新上传");

    assertClean(session.diagnostics, "r4-submit");
    appendCaseLog(`r4-submit ok submission=${submission.submissionId}`);
  } finally {
    await closeSession(session);
  }
});

// ---------------------------------------------------------------------------
// R5 — idempotent submit retry after the browser response is lost.
// ---------------------------------------------------------------------------
test("r5-idempotency", async ({ browser }) => {
  requireJourneyEnv();
  const scope = scopeBySlug("r5-idempotency");
  const submitter = identityFor(scope, "submitter");
  const reviewer = identityFor(scope, "reviewer");
  const session = await openSession(browser, submitter);
  const submitKeys: string[] = [];
  const upstreamStatuses: number[] = [];
  let attempts = 0;

  const submitRoute = async (route: import("@playwright/test").Route): Promise<void> => {
    attempts += 1;
    submitKeys.push(route.request().headers()["idempotency-key"] ?? "");
    if (attempts === 1) {
      // Perform the real submit, then hide the response from the browser.
      const upstream = await route.fetch();
      upstreamStatuses.push(upstream.status());
      await route.abort("failed");
      return;
    }
    await route.continue();
  };
  await session.page.route(/\/submit-attempts$/, submitRoute);

  try {
    await gotoWorkbenchFresh(session.page);
    const run = await uploadAndPreview(session.page, submitter, scope, "modified_only");

    await compareAction(session.page, "提交").click();
    const dialog = session.page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    const firstAttempt = session.page.waitForEvent("requestfailed", { predicate: (request) => request.method() === "POST" && new URL(request.url()).pathname.endsWith(SUBMIT_ATTEMPTS), timeout: 300_000 });
    await dialog.getByRole("button", { name: "确认提交", exact: true }).click();
    await firstAttempt;
    await expect(dialog.locator(".form-error")).toBeVisible({ timeout: 120_000 });
    expect(attempts, "first intercepted submit").toBe(1);
    expect(upstreamStatuses[0], "backend accepted the intercepted submit").toBe(202);

    const replay = session.page.waitForResponse((response) => isPost(response, SUBMIT_ATTEMPTS), { timeout: 300_000 });
    await dialog.getByRole("button", { name: "确认提交", exact: true }).click();
    const replayResponse = await replay;
    expect(replayResponse.status(), "submit replay status").toBe(202);
    expect(attempts, "submit attempts").toBe(2);
    expect(submitKeys[1], "retry reuses the Idempotency-Key").toBe(submitKeys[0]);

    const result = session.page.locator('section[aria-label="提交结果"]');
    await expect(result).toBeVisible({ timeout: 240_000 });
    const { submission } = await waitForPendingSubmission(submitter, run.workspaceId, 240_000);
    expect((await currentWorkspace(submitter)).active_submission_id).toBe(submission.submission_id);

    // Review replay: same key and body returns 200 instead of 201.
    const facts = await waitForReviewStatus(reviewer, submission.submission_id, "PENDING");
    const reviewKey = `r5-review-${submission.submission_id}`;
    const reviewBody = { expected_review_version: facts.review_version, action: "APPROVE" as const };
    const first = await applyReview(reviewer, submission.submission_id, reviewBody, reviewKey);
    expect(first.status, "first review status").toBe(201);
    const second = await applyReview(reviewer, submission.submission_id, reviewBody, reviewKey);
    expect(second.status, "review replay status").toBe(200);
    expect(second.body.review_version).toBe(first.body.review_version);
    expect(second.body.status).toBe("APPROVED");

    await session.page.unroute(/\/submit-attempts$/, submitRoute);
    assertClean(session.diagnostics, "r5-idempotency");
    appendCaseLog(`r5-idempotency ok submission=${submission.submission_id} keys_equal=${submitKeys[0] === submitKeys[1]} review_replay=200`);
  } finally {
    await session.page.unroute(/\/submit-attempts$/, submitRoute).catch(() => undefined);
    await closeSession(session);
  }
});

// ---------------------------------------------------------------------------
// R6 — reviewer rejects with a reason, submitter re-uploads and is approved.
// ---------------------------------------------------------------------------
test("r6-reject-approve", async ({ browser }, testInfo) => {
  requireJourneyEnv();
  const scope = scopeBySlug("r6-reject-approve");
  const submitter = identityFor(scope, "submitter");
  const reviewer = identityFor(scope, "reviewer");
  const submitterSession = await openSession(browser, submitter);
  const reviewerSession = await openSession(browser, reviewer);

  try {
    await gotoWorkbenchFresh(submitterSession.page);
    const first = await uploadAndPreview(submitterSession.page, submitter, scope, "modified_only");
    const firstSubmission = await submitViaUi(submitterSession.page, submitter, first.workspaceId);

    await openReviewPage(reviewerSession.page, firstSubmission.submissionId);
    await expect(reviewStatus(reviewerSession.page)).toHaveText("审核：待审核");
    const reason = "r6: 组态缺少订单表索引说明，请补充后重新提交";
    await rejectInReview(reviewerSession.page, reason);
    await expect(reviewStatus(reviewerSession.page)).toHaveText("审核：已退回");
    const facts = await waitForReviewStatus(reviewer, firstSubmission.submissionId, "REJECTED");
    expect(facts.review_version).toBe(1);
    await saveEvidence(reviewerSession.page, testInfo, "r6-rejected-review");

    // Submitter sees cleared pointers and can re-upload the same input.
    await gotoWorkbenchFresh(submitterSession.page);
    await expect(treeRow(submitterSession.page, "提交 1")).toContainText("已退回");
    await selectUploadDirs(submitterSession.page, { modified: inputDir(scope, "modified_only") });
    await expectEnabled(workshopAction(submitterSession.page, "上传"));
    await expectPointersCleared(submitter);

    const second = await uploadAndPreview(submitterSession.page, submitter, scope, "modified_only");
    const secondSubmission = await submitViaUi(submitterSession.page, submitter, second.workspaceId);
    expect(secondSubmission.submissionId).not.toBe(firstSubmission.submissionId);

    await openReviewPage(reviewerSession.page, secondSubmission.submissionId);
    await expect(reviewStatus(reviewerSession.page)).toHaveText("审核：待审核");
    await approveInReview(reviewerSession.page);
    await expect(reviewStatus(reviewerSession.page)).toHaveText("审核：已通过");
    const approved = await waitForReviewStatus(reviewer, secondSubmission.submissionId, "APPROVED");
    expect(approved.review_version).toBe(1);
    await saveEvidence(reviewerSession.page, testInfo, "r6-approved-review");

    assertClean(submitterSession.diagnostics, "r6-submitter");
    assertClean(reviewerSession.diagnostics, "r6-reviewer");
    appendCaseLog(`r6-reject-approve ok rejected=${firstSubmission.submissionId} approved=${secondSubmission.submissionId}`);
  } finally {
    await closeSession(reviewerSession);
    await closeSession(submitterSession);
  }
});

// ---------------------------------------------------------------------------
// R7 W1/W2/W8 — withdraw a PENDING submission, then re-upload and submit.
// ---------------------------------------------------------------------------
test("r7-withdraw", async ({ browser }, testInfo) => {
  requireJourneyEnv();
  const scope = scopeBySlug("r7-withdraw");
  const submitter = identityFor(scope, "submitter");
  const session = await openSession(browser, submitter);

  try {
    await gotoWorkbenchFresh(session.page);
    const first = await uploadAndPreview(session.page, submitter, scope, "modified_only");
    const firstSubmission = await submitViaUi(session.page, submitter, first.workspaceId);

    // W8: a PENDING submission blocks re-upload, including the step card (B1).
    await gotoWorkbenchFresh(session.page);
    await expectDisabledWithReason(workshopAction(session.page, "上传"), "已有待审核的提交，撤回后才能重新上传");
    await selectTreeRow(session.page, /工作区/);
    await expandWorkspaceDetails(session.page);
    await selectUploadDirs(session.page, { modified: inputDir(scope, "modified_only") });
    await expectDisabledWithReason(stepUploadAction(session.page), "已有待审核的提交，撤回后才能重新上传");

    // W1: withdraw from the PREVIEW header (bundle already installed).
    await session.page.goto(`/?page=compare&mode=PREVIEW&workspaceId=${first.workspaceId}&previewResultId=${first.previewId}`);
    await waitForDiffBrowsing(session.page);
    const response = await withdrawInUi(session.page, "preview");
    expect(response.request().headers()["idempotency-key"]).toBeTruthy();
    await expect(session.page).toHaveURL(/page=workspace/, { timeout: 120_000 });
    await expect(session.page.locator(".workspace-notice")).toContainText("已撤回，可以重新上传");

    // W2: all workspace pointers are empty and upload is enabled again.
    await expectPointersCleared(submitter);
    await selectUploadDirs(session.page, { modified: inputDir(scope, "modified_only") });
    await expectEnabled(workshopAction(session.page, "上传"));
    await expectEnabled(stepUploadAction(session.page));
    await expect(treeRow(session.page, "提交 1")).toContainText("已撤回");
    await saveEvidence(session.page, testInfo, "r7-withdraw-notice");

    const second = await uploadAndPreview(session.page, submitter, scope, "modified_only");
    const secondSubmission = await submitViaUi(session.page, submitter, second.workspaceId);
    expect(secondSubmission.submissionId).not.toBe(firstSubmission.submissionId);
    const workspace = await currentWorkspace(submitter);
    expect(workspace.active_submission_id).toBe(secondSubmission.submissionId);
    expect(await waitForReviewStatus(submitter, secondSubmission.submissionId, "PENDING")).toBeTruthy();

    assertClean(session.diagnostics, "r7-withdraw");
    appendCaseLog(`r7-withdraw ok withdrawn=${firstSubmission.submissionId} resubmitted=${secondSubmission.submissionId}`);
  } finally {
    await closeSession(session);
  }
});

// ---------------------------------------------------------------------------
// R7 W3 — upload-only cannot withdraw; review facts return 403.
// ---------------------------------------------------------------------------
test("r7-upload-only", async ({ browser }) => {
  requireJourneyEnv();
  const scope = scopeBySlug("r7-upload-only");
  const uploadOnly = identityFor(scope, "submitter-upload-only");
  const session = await openSession(browser, uploadOnly);

  try {
    await gotoWorkbenchFresh(session.page);
    const uploadWait = session.page.waitForResponse((response) => isPost(response, "/upload-revisions"), { timeout: 300_000 });
    const previewWait = session.page.waitForResponse((response) => isPost(response, "/preview-operations"), { timeout: 300_000 });
    await selectUploadDirs(session.page, { modified: inputDir(scope, "modified_only") });
    await startUpload(session.page);
    expect((await uploadWait).status()).toBe(201);
    const previewResponse = await previewWait;
    expect(previewResponse.status()).toBe(202);
    const accepted = (await previewResponse.json()) as { operation_id: string };
    expect((await waitForOperation(uploadOnly, accepted.operation_id, 240_000)).status).toBe("SUCCEEDED");
    await waitForPreviewOutcome(session.page);
    await waitForDiffBrowsing(session.page);
    const url = new URL(session.page.url());
    const workspaceId = url.searchParams.get("workspaceId") as string;
    const previewId = url.searchParams.get("previewResultId") as string;
    const submission = await submitViaUi(session.page, uploadOnly, workspaceId);

    // W3: server refuses review facts; the withdraw gate shows the 403 reason.
    await session.page.goto(`/?page=compare&mode=PREVIEW&workspaceId=${workspaceId}&previewResultId=${previewId}`);
    await waitForDiffBrowsing(session.page);
    const facts403 = await tryApi<unknown>(uploadOnly, "GET", `/v1/submissions/${submission.submissionId}/review`);
    expect(facts403.status).toBe(403);
    expect(facts403).toMatchObject({ ok: false, code: "SCOPE_FORBIDDEN" });
    await expectDisabledWithReason(compareAction(session.page, "撤回"), "当前身份没有撤回权限");

    // Opening review mode is refused as well (history bundle/review query).
    const review403 = session.page.waitForResponse((response) => new URL(response.url()).pathname.endsWith(`/v1/submissions/${submission.submissionId}/review`), { timeout: 120_000 });
    await session.page.goto(`/?page=compare&mode=REVIEW&submissionId=${submission.submissionId}`);
    const refused = await review403;
    expect(refused.status()).toBe(403);
    // The compare error carries the server code with the matching copy.
    const errorSection = session.page.locator("section.compare-error");
    await expect(errorSection).toBeVisible({ timeout: 120_000 });
    await expect(errorSection).toContainText("当前身份没有该操作的权限");
    await expect(errorSection).toContainText("SCOPE_FORBIDDEN");
    await expect(session.page.locator(".grid-frame")).toHaveCount(0);

    assertClean(session.diagnostics, "r7-upload-only");
    appendCaseLog(`r7-upload-only ok submission=${submission.submissionId} review=403`);
  } finally {
    await closeSession(session);
  }
});

// ---------------------------------------------------------------------------
// R7 W4 — an approved submission keeps its pointer and blocks upload/withdraw.
// ---------------------------------------------------------------------------
test("r7-approved", async ({ browser }, testInfo) => {
  requireJourneyEnv();
  const scope = scopeBySlug("r7-approved");
  const submitter = identityFor(scope, "submitter");
  const reviewer = identityFor(scope, "reviewer");
  const session = await openSession(browser, submitter);

  try {
    await gotoWorkbenchFresh(session.page);
    const run = await uploadAndPreview(session.page, submitter, scope, "modified_only");
    const submission = await submitViaUi(session.page, submitter, run.workspaceId);
    const facts = await waitForReviewStatus(reviewer, submission.submissionId, "PENDING");
    expect((await applyReview(reviewer, submission.submissionId, {
      expected_review_version: facts.review_version,
      action: "APPROVE",
    }, `r7-approved-${submission.submissionId}`)).status).toBe(201);
    await waitForReviewStatus(reviewer, submission.submissionId, "APPROVED");

    await gotoWorkbenchFresh(session.page);
    const workspace = await currentWorkspace(submitter);
    expect(workspace.active_submission_id, "approved submission pointer is kept").toBe(submission.submissionId);
    await expect(treeRow(session.page, "提交 1")).toContainText("已通过");
    await expectDisabledWithReason(workshopAction(session.page, "上传"), "该提交已通过审核，归档或关闭后才能重新上传");
    // B1: the UploadStepCard start button is disabled with the same occupancy reason.
    await selectTreeRow(session.page, /工作区/);
    await expandWorkspaceDetails(session.page);
    await selectUploadDirs(session.page, { modified: inputDir(scope, "modified_only") });
    await expectDisabledWithReason(stepUploadAction(session.page), "该提交已通过审核，归档或关闭后才能重新上传");

    await session.page.goto(`/?page=compare&mode=PREVIEW&workspaceId=${run.workspaceId}&previewResultId=${run.previewId}`);
    await waitForDiffBrowsing(session.page);
    await expectDisabledWithReason(compareAction(session.page, "撤回"), "该提交已通过审核，不能撤回");
    await expectDisabledWithReason(compareAction(session.page, "提交"), "该提交已通过审核，归档或关闭后才能重新上传");
    await saveEvidence(session.page, testInfo, "r7-approved-gates");

    assertClean(session.diagnostics, "r7-approved");
    appendCaseLog(`r7-approved ok submission=${submission.submissionId}`);
  } finally {
    await closeSession(session);
  }
});

// ---------------------------------------------------------------------------
// R7 W5 — a withdrawn dialog races the reviewer; one request, no auto-resend.
// ---------------------------------------------------------------------------
test("r7-stale", async ({ browser }) => {
  requireJourneyEnv();
  const scope = scopeBySlug("r7-stale");
  const submitter = identityFor(scope, "submitter");
  const reviewer = identityFor(scope, "reviewer");
  const submitterSession = await openSession(browser, submitter);
  const reviewerSession = await openSession(browser, reviewer);

  try {
    await gotoWorkbenchFresh(submitterSession.page);
    const run = await uploadAndPreview(submitterSession.page, submitter, scope, "modified_only");
    const submission = await submitViaUi(submitterSession.page, submitter, run.workspaceId);

    // Open the withdraw dialog first, then let the reviewer decide.
    await submitterSession.page.goto(`/?page=compare&mode=PREVIEW&workspaceId=${run.workspaceId}&previewResultId=${run.previewId}`);
    await waitForDiffBrowsing(submitterSession.page);
    const withdrawRequests = countPosts(submitterSession.page, REVIEW_EVENTS);
    await compareAction(submitterSession.page, "撤回").click();
    const dialog = submitterSession.page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByLabel("我已了解撤回后需要重新提交，并确认继续").check();

    await openReviewPage(reviewerSession.page, submission.submissionId);
    await rejectInReview(reviewerSession.page, "r7-stale: reviewer 先退回，提交人撤回应冲突");
    await waitForReviewStatus(reviewer, submission.submissionId, "REJECTED");

    const conflict = submitterSession.page.waitForResponse((response) => isPost(response, REVIEW_EVENTS), { timeout: 120_000 });
    await dialog.getByRole("button", { name: "确认撤回", exact: true }).click();
    const conflictResponse = await conflict;
    expect(conflictResponse.status(), "stale withdraw status").toBe(409);
    const conflictBody = (await conflictResponse.json()) as { code?: string };
    expect(conflictBody.code, "stale withdraw code").toBe("REVIEW_VERSION_CONFLICT");

    const alert = dialog.locator('[role="alert"].form-error');
    await expect(alert).toContainText("审核状态已变化，已重新读取");
    await expect(alert).toContainText("REVIEW_VERSION_CONFLICT");
    // The server-state was re-read; the dialog stays open with the conflict message.
    expect(withdrawRequests.count(), "withdraw requests sent").toBe(1);
    await submitterSession.page.waitForTimeout(2_500);
    expect(withdrawRequests.count(), "withdraw requests after settling").toBe(1);

    await dialog.getByRole("button", { name: "取消", exact: true }).click();
    await gotoWorkbenchFresh(submitterSession.page);
    await expect(treeRow(submitterSession.page, "提交 1")).toContainText("已退回");

    assertClean(submitterSession.diagnostics, "r7-stale-submitter");
    assertClean(reviewerSession.diagnostics, "r7-stale-reviewer");
    appendCaseLog(`r7-stale ok submission=${submission.submissionId} withdraw_requests=1`);
  } finally {
    await closeSession(reviewerSession);
    await closeSession(submitterSession);
  }
});

// ---------------------------------------------------------------------------
// R7 W7 — reviewer header withdraw regression.
// ---------------------------------------------------------------------------
test("r7-reviewer-withdraw", async ({ browser }, testInfo) => {
  requireJourneyEnv();
  const scope = scopeBySlug("r7-reviewer-withdraw");
  const submitter = identityFor(scope, "submitter");
  const reviewer = identityFor(scope, "reviewer");
  const submitterSession = await openSession(browser, submitter);
  const reviewerSession = await openSession(browser, reviewer);

  try {
    await gotoWorkbenchFresh(submitterSession.page);
    const run = await uploadAndPreview(submitterSession.page, submitter, scope, "modified_only");
    const submission = await submitViaUi(submitterSession.page, submitter, run.workspaceId);

    await openReviewPage(reviewerSession.page, submission.submissionId);
    await expect(reviewStatus(reviewerSession.page)).toHaveText("审核：待审核");
    const response = await withdrawInUi(reviewerSession.page, "review");
    expect(response.request().headers()["idempotency-key"]).toBeTruthy();
    await expect(reviewStatus(reviewerSession.page)).toHaveText("审核：已撤回", { timeout: 120_000 });
    await expectDisabledWithReason(reviewAction(reviewerSession.page, "撤回"), "该提交已撤回");
    await expectDisabledWithReason(reviewAction(reviewerSession.page, "审核通过"), "该提交已撤回");
    await saveEvidence(reviewerSession.page, testInfo, "r7-reviewer-withdraw");

    await expectPointersCleared(submitter);
    await gotoWorkbenchFresh(submitterSession.page);
    await expect(treeRow(submitterSession.page, "提交 1")).toContainText("已撤回");
    await selectUploadDirs(submitterSession.page, { modified: inputDir(scope, "modified_only") });
    await expectEnabled(workshopAction(submitterSession.page, "上传"));

    assertClean(submitterSession.diagnostics, "r7-reviewer-withdraw-submitter");
    assertClean(reviewerSession.diagnostics, "r7-reviewer-withdraw-reviewer");
    appendCaseLog(`r7-reviewer-withdraw ok submission=${submission.submissionId}`);
  } finally {
    await closeSession(reviewerSession);
    await closeSession(submitterSession);
  }
});

// ---------------------------------------------------------------------------
// R9 — History with INITIAL + one submission: drawer counts and diff browsing.
// ---------------------------------------------------------------------------
test("r9-history", async ({ browser }, testInfo) => {
  requireJourneyEnv();
  const scope = scopeBySlug("r9-history");
  const submitter = identityFor(scope, "submitter");
  const session = await openSession(browser, submitter);

  try {
    await gotoWorkbenchFresh(session.page);
    const run = await uploadAndPreview(session.page, submitter, scope, "modified_only");
    await submitViaUi(session.page, submitter, run.workspaceId);

    const history = await listHistory(submitter);
    expect(history.body.nodes).toHaveLength(2);
    expect(history.body.nodes.filter((node) => node.ref_kind === "baseline_node")).toHaveLength(1);
    expect(history.body.nodes.filter((node) => node.ref_kind === "submission")).toHaveLength(1);

    await gotoWorkbenchFresh(session.page);
    await selectTreeRow(session.page, "初始基线");
    await workshopAction(session.page, "加入比较").click();
    await selectTreeRow(session.page, "提交 1");
    await workshopAction(session.page, "加入比较").click();

    const compareResponse = session.page.waitForResponse((response) => response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/history-compares"), { timeout: 120_000 });
    await session.page.locator(".compare-tray").getByRole("button", { name: "历史比较", exact: true }).click();
    expect((await compareResponse).status()).toBeLessThan(300);

    const drawer = session.page.locator('section[aria-label="历史比较结果抽屉"]');
    await expect(drawer).toBeVisible({ timeout: 60_000 });
    await expect(drawer.locator(".status-tag")).toHaveText("已完成", { timeout: 300_000 });
    await expect(drawer.locator(".history-pair-summary")).toHaveCount(1);
    const summary = drawer.locator(".history-pair-summary").first();
    await expect(summary).toContainText("比较对 1");
    await expect(summary).toContainText(/节点 \d+ → 节点 \d+/);
    await expect(summary).toContainText(/\d+ 条差异记录/);
    await expect(summary).toContainText(/表 \d+/);
    await expect(summary).toContainText(/变更 \d+/);
    await expect(drawer).toContainText("已就绪：bundle 已下载并校验。", { timeout: 300_000 });
    await saveEvidence(session.page, testInfo, "r9-history-drawer");

    await drawer.getByRole("button", { name: "打开差异工作台", exact: true }).click();
    await waitForDiffBrowsing(session.page);
    await expect(session.page.locator(".mode-tag")).toHaveText("历史比较 · 只读");
    const tabs = session.page.getByRole("tablist", { name: "比较视图" });
    await expect(tabs.getByRole("tab")).toHaveCount(1);
    await expect(tabs.getByRole("tab").first()).toHaveText(/节点 \d+ → 节点 \d+/);
    await saveEvidence(session.page, testInfo, "r9-history-diff");

    assertClean(session.diagnostics, "r9-history");
    appendCaseLog(`r9-history ok nodes=${history.body.nodes.length}`);
  } finally {
    await closeSession(session);
  }
});

// ---------------------------------------------------------------------------
// R10 #1/#2 — upload without permission and review mode without permission.
// ---------------------------------------------------------------------------
test("r10-noperm", async ({ browser }) => {
  requireJourneyEnv();
  const scope = scopeBySlug("r10-noperm");
  const submitter = identityFor(scope, "submitter");
  const nobody = identityFor(scope, "none");
  const submitterSession = await openSession(browser, submitter);
  const noPermSession = await openSession(browser, nobody);

  try {
    await gotoWorkbenchFresh(submitterSession.page);
    const run = await uploadAndPreview(submitterSession.page, submitter, scope, "modified_only");
    const submission = await submitViaUi(submitterSession.page, submitter, run.workspaceId);

    // #1 no-permission upload.
    await gotoWorkbenchFresh(noPermSession.page);
    await selectUploadDirs(noPermSession.page, { modified: inputDir(scope, "modified_only") });
    const uploadDenied = noPermSession.page.waitForResponse((response) => isPost(response, "/upload-revisions"), { timeout: 120_000 });
    await startUpload(noPermSession.page);
    const uploadResponse = await uploadDenied;
    expect(uploadResponse.status()).toBe(403);
    expect((await uploadResponse.json()) as { code?: string }).toMatchObject({ code: "SCOPE_FORBIDDEN" });
    const uploadError = noPermSession.page.locator(".upload-error");
    await expect(uploadError).toBeVisible({ timeout: 120_000 });
    await expect(uploadError).toContainText("当前身份没有该操作的权限");
    await expect(uploadError).toContainText("SCOPE_FORBIDDEN");
    await expect(uploadError).toContainText("切换身份后重试，或联系管理员授予权限。");

    // #2 no-permission opening review mode.
    const reviewDenied = noPermSession.page.waitForResponse((response) => new URL(response.url()).pathname.endsWith(`/v1/submissions/${submission.submissionId}/review`), { timeout: 120_000 });
    await noPermSession.page.goto(`/?page=compare&mode=REVIEW&submissionId=${submission.submissionId}`);
    expect((await reviewDenied).status()).toBe(403);
    const errorSection = noPermSession.page.locator("section.compare-error");
    await expect(errorSection).toBeVisible({ timeout: 120_000 });
    await expect(errorSection).toContainText("当前身份没有该操作的权限");
    await expect(errorSection).toContainText("SCOPE_FORBIDDEN");
    await expect(noPermSession.page.locator(".grid-frame")).toHaveCount(0);

    assertClean(submitterSession.diagnostics, "r10-noperm-submitter");
    assertClean(noPermSession.diagnostics, "r10-noperm-none");
    appendCaseLog(`r10-noperm ok submission=${submission.submissionId} upload=403 review=403`);
  } finally {
    await closeSession(noPermSession);
    await closeSession(submitterSession);
  }
});

// ---------------------------------------------------------------------------
// R10 #2' — identity with upload but without preview: starting preview is 403.
// ---------------------------------------------------------------------------
test("r10-no-preview", async ({ browser }) => {
  requireJourneyEnv();
  const scope = scopeBySlug("r10-no-preview");
  const noPreview = identityFor(scope, "submitter-no-preview");
  const session = await openSession(browser, noPreview);

  try {
    await gotoWorkbenchFresh(session.page);
    await selectUploadDirs(session.page, { modified: inputDir(scope, "modified_only") });
    const uploadWait = session.page.waitForResponse((response) => isPost(response, "/upload-revisions"), { timeout: 300_000 });
    const previewWait = session.page.waitForResponse((response) => isPost(response, "/preview-operations"), { timeout: 300_000 });
    await startUpload(session.page);
    expect((await uploadWait).status(), "upload without preview permission").toBe(201);
    const preview = await previewWait;
    expect(preview.status(), "preview without preview permission").toBe(403);
    expect((await preview.json()) as { code?: string }).toMatchObject({ code: "SCOPE_FORBIDDEN" });

    const error = session.page.locator(".upload-error");
    await expect(error).toBeVisible({ timeout: 120_000 });
    await expect(error).toContainText("当前身份没有该操作的权限");
    await expect(error).toContainText("SCOPE_FORBIDDEN");
    await expect(session.page.locator("section.comparison-content")).toHaveCount(0);

    assertClean(session.diagnostics, "r10-no-preview");
    appendCaseLog("r10-no-preview ok preview=403");
  } finally {
    await closeSession(session);
  }
});

// ---------------------------------------------------------------------------
// R10 #3 — no-permission archive-mainline candidate query (approved submission).
// ---------------------------------------------------------------------------
test("r10-archive", async ({ browser }) => {
  requireJourneyEnv();
  const scope = scopeBySlug("r10-archive");
  const submitter = identityFor(scope, "submitter");
  const reviewer = identityFor(scope, "reviewer");
  const nobody = identityFor(scope, "none");
  const submitterSession = await openSession(browser, submitter);
  const noPermSession = await openSession(browser, nobody);

  try {
    await gotoWorkbenchFresh(submitterSession.page);
    const run = await uploadAndPreview(submitterSession.page, submitter, scope, "modified_only");
    const submission = await submitViaUi(submitterSession.page, submitter, run.workspaceId);
    const facts = await waitForReviewStatus(reviewer, submission.submissionId, "PENDING");
    expect((await applyReview(reviewer, submission.submissionId, {
      expected_review_version: facts.review_version,
      action: "APPROVE",
    }, `r10-archive-${submission.submissionId}`)).status).toBe(201);
    await waitForReviewStatus(reviewer, submission.submissionId, "APPROVED");

    await gotoWorkbenchFresh(noPermSession.page);
    await selectTreeRow(noPermSession.page, "提交 1");
    await expectEnabled(workshopAction(noPermSession.page, "归档主线"));
    const candidates = noPermSession.page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/v1/archive-candidates"), { timeout: 120_000 });
    await workshopAction(noPermSession.page, "归档主线").click();
    const denied = await candidates;
    expect(denied.status(), "archive-candidates status").toBe(403);
    expect((await denied.json()) as { code?: string }).toMatchObject({ code: "SCOPE_FORBIDDEN" });

    const dialog = noPermSession.page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 60_000 });
    const alert = dialog.locator('[role="alert"].form-error');
    await expect(alert).toBeVisible({ timeout: 120_000 });
    await expect(alert).toContainText("SCOPE_FORBIDDEN");
    await expect(alert).toContainText("当前身份没有该操作的权限");

    assertClean(submitterSession.diagnostics, "r10-archive-submitter");
    // The expected 403 is logged by the browser; nothing else may be.
    assertClean(noPermSession.diagnostics, "r10-archive-none");
    appendCaseLog(`r10-archive ok submission=${submission.submissionId} candidates=403`);
  } finally {
    await closeSession(noPermSession);
    await closeSession(submitterSession);
  }
});

// ---------------------------------------------------------------------------
// R11 — review-version conflict: refresh, no automatic resend.
// ---------------------------------------------------------------------------
test("r11-review-conflict", async ({ browser }, testInfo) => {
  requireJourneyEnv();
  const scope = scopeBySlug("r11-review-conflict");
  const submitter = identityFor(scope, "submitter");
  const reviewer = identityFor(scope, "reviewer");
  const submitterSession = await openSession(browser, submitter);
  const reviewerSession = await openSession(browser, reviewer);

  try {
    await gotoWorkbenchFresh(submitterSession.page);
    const run = await uploadAndPreview(submitterSession.page, submitter, scope, "modified_only");
    const submission = await submitViaUi(submitterSession.page, submitter, run.workspaceId);

    await openReviewPage(reviewerSession.page, submission.submissionId);
    await expect(reviewStatus(reviewerSession.page)).toHaveText("审核：待审核");
    const reviewRequests = countPosts(reviewerSession.page, REVIEW_EVENTS);

    // Another client changes the submission behind the reviewer's back.
    const pending = await waitForReviewStatus(submitter, submission.submissionId, "PENDING");
    expect((await applyReview(submitter, submission.submissionId, {
      expected_review_version: pending.review_version,
      action: "WITHDRAW",
    }, `r11-review-conflict-${submission.submissionId}`)).status).toBe(201);
    await waitForReviewStatus(submitter, submission.submissionId, "WITHDRAWN");

    const stale = reviewerSession.page.waitForResponse((response) => isPost(response, REVIEW_EVENTS), { timeout: 120_000 });
    await reviewAction(reviewerSession.page, "审核通过").click();
    const dialog = reviewerSession.page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "确认通过", exact: true }).click();
    const staleResponse = await stale;
    expect(staleResponse.status(), "stale review status").toBe(409);
    expect((await staleResponse.json()) as { code?: string }).toMatchObject({ code: "REVIEW_VERSION_CONFLICT" });

    const alert = dialog.locator('[role="alert"].form-error');
    await expect(alert).toContainText("数据已被更新，请刷新审核信息后重试");
    await expect(alert).toContainText("REVIEW_VERSION_CONFLICT");
    expect(reviewRequests.count(), "review requests before refresh").toBe(1);
    await reviewerSession.page.waitForTimeout(2_500);
    expect(reviewRequests.count(), "no automatic resend").toBe(1);

    await alert.getByRole("button", { name: "刷新审核信息", exact: true }).click();
    await expect(dialog.locator('[role="alert"].form-error')).toHaveCount(0);
    await expect(reviewStatus(reviewerSession.page)).toHaveText("审核：已撤回", { timeout: 120_000 });
    expect(reviewRequests.count(), "refresh does not resend the actions").toBe(1);
    await dialog.getByRole("button", { name: "取消", exact: true }).click();
    await expectDisabledWithReason(reviewAction(reviewerSession.page, "审核通过"), "该提交已撤回");
    await saveEvidence(reviewerSession.page, testInfo, "r11-review-conflict");

    assertClean(submitterSession.diagnostics, "r11-review-conflict-submitter");
    assertClean(reviewerSession.diagnostics, "r11-review-conflict-reviewer");
    appendCaseLog(`r11-review-conflict ok submission=${submission.submissionId} requests=1`);
  } finally {
    await closeSession(reviewerSession);
    await closeSession(submitterSession);
  }
});

// ---------------------------------------------------------------------------
// R11 — workspace-version conflict: another preview invalidates the dialog.
// ---------------------------------------------------------------------------
test("r11-workspace-conflict", async ({ browser }) => {
  requireJourneyEnv();
  const scope = scopeBySlug("r11-workspace-conflict");
  const submitter = identityFor(scope, "submitter");
  const firstSession = await openSession(browser, submitter);
  const secondSession = await openSession(browser, submitter);

  try {
    await gotoWorkbenchFresh(firstSession.page);
    const first = await uploadAndPreview(firstSession.page, submitter, scope, "modified_only");
    await compareAction(firstSession.page, "提交").click();
    const dialog = firstSession.page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "提交本次组态", exact: true })).toBeVisible();
    const submitRequests = countPosts(firstSession.page, SUBMIT_ATTEMPTS);

    // A second upload/preview in the same identity bumps optimistic_version.
    await gotoWorkbenchFresh(secondSession.page);
    const second = await uploadAndPreview(secondSession.page, submitter, scope, "modified_only");
    expect(second.previewId).not.toBe(first.previewId);

    const conflict = firstSession.page.waitForResponse((response) => isPost(response, SUBMIT_ATTEMPTS), { timeout: 120_000 });
    await dialog.getByRole("button", { name: "确认提交", exact: true }).click();
    const conflictResponse = await conflict;
    expect(conflictResponse.status(), "stale workspace submit status").toBe(409);
    expect((await conflictResponse.json()) as { code?: string }).toMatchObject({ code: "WORKSPACE_VERSION_CONFLICT" });

    const alert = dialog.locator('[role="alert"].form-error');
    await expect(alert).toContainText("数据已被更新，请刷新后重试");
    await expect(alert).toContainText("WORKSPACE_VERSION_CONFLICT");
    const refresh = alert.getByRole("button", { name: "刷新后重试", exact: true });
    await expect(refresh).toBeVisible();
    expect(submitRequests.count(), "submit requests").toBe(1);
    await firstSession.page.waitForTimeout(2_500);
    expect(submitRequests.count(), "no automatic submit resend").toBe(1);

    const workspace = await currentWorkspace(submitter);
    expect(workspace.active_submission_id, "conflict must not create a submission").toBeNull();
    expect(workspace.active_submit_attempt_id).toBeNull();

    await refresh.click();
    await firstSession.page.waitForLoadState("domcontentloaded");
    await expect(firstSession.page.locator("main.comparison-page")).toBeVisible({ timeout: 60_000 });
    expect(submitRequests.count(), "reload does not resend the submit").toBe(1);
    expect((await currentWorkspace(submitter)).active_submission_id).toBeNull();

    assertClean(firstSession.diagnostics, "r11-workspace-conflict-first");
    assertClean(secondSession.diagnostics, "r11-workspace-conflict-second");
    appendCaseLog(`r11-workspace-conflict ok first=${first.previewId} second=${second.previewId}`);
  } finally {
    await closeSession(secondSession);
    await closeSession(firstSession);
  }
});

// ---------------------------------------------------------------------------
// FE3c J1/J2 — archive mainline and manual close (kickoff §4.6, R8/R12).
// Anomaly-set calibration (kickoff §4.6 “实测校正”): every preview below is
// read through the API and compared with the kickoff table before the UI
// drives the same state. Any mismatch fails the journey for design review.
// ---------------------------------------------------------------------------

function anomalySet(plan: ArchivePlanBody): string[] {
  return plan.anomalies
    .map((anomaly) => [anomaly.subject_kind, anomaly.issue_code, anomaly.side ?? "-", [...anomaly.affected_submission_ids].sort().join(",")].join("|"))
    .sort();
}

function businessIssueSet(plan: ArchivePlanBody): string[] {
  return plan.business_validation.issues
    .filter((issue) => issue.subject_kind !== "APPROVED_SIBLING_EXCLUDED" && issue.subject_kind !== "PROJECT_IDENTITY_EXCEPTION")
    .map((issue) => [issue.subject_kind, issue.issue_code, issue.side ?? "-"].join("|"))
    .sort();
}

function expectAnomalySets(plan: ArchivePlanBody, expected: string[], phase: string): void {
  const actual = anomalySet(plan);
  appendCaseLog(`${phase} anomalies=${JSON.stringify(actual)}`);
  expect(actual, `${phase}: anomaly set differs from the kickoff table (stop for design review)`).toEqual([...expected].sort());
}

async function uploadDirsAndPreview(
  page: Page,
  identity: JourneyIdentity,
  scope: JourneyScope,
  dirs: { modified: string; initial?: string },
): Promise<UploadRun> {
  const bundleRecording = recordBundleResponses(page);
  try {
    const uploadWait = page.waitForResponse((response) => isPost(response, "/upload-revisions"), { timeout: 300_000 });
    const previewWait = page.waitForResponse((response) => isPost(response, "/preview-operations"), { timeout: 300_000 });
    await selectUploadDirs(page, dirs);
    await startUpload(page);
    const upload = await uploadWait;
    expect(upload.status(), "upload-revisions status").toBe(201);
    const preview = await previewWait;
    expect(preview.status(), "preview-operations status").toBe(202);
    const accepted = (await preview.json()) as { operation_id: string };
    const operation = await waitForOperation(identity, accepted.operation_id, 240_000);
    expect(operation.status, `preview operation ${accepted.operation_id}`).toBe("SUCCEEDED");
    // Outcome first: a failed preview surfaces here instead of masking as a
    // missing bundle download.
    const outcome = await waitForPreviewOutcome(page);
    expect(outcome, "preview outcome").toBe("compare");
    const url = new URL(page.url());
    const previewId = url.searchParams.get("previewResultId");
    const workspaceId = url.searchParams.get("workspaceId");
    expect(previewId, "previewResultId in compare URL").toBeTruthy();
    expect(workspaceId, "workspaceId in compare URL").toBeTruthy();
    const previewResult = (await getPreviewResult(identity, workspaceId as string, previewId as string)).body;
    await waitForInstalledBundle(page, digestHex(previewResult.bundle_digest));
    // Prefer the newest recorded download; fall back to earlier ones.
    let bundle: ParsedBundle | null = null;
    let bundleResponse: PlaywrightResponse | null = null;
    for (const recorded of [...bundleRecording.responses].reverse()) {
      try {
        expect(recorded.status(), "bundle status").toBe(200);
        bundle = parseBundleTar(Buffer.from(await recorded.body()));
        bundleResponse = recorded;
        break;
      } catch {
        continue;
      }
    }
    expect(bundle, "bundle downloaded and installed").toBeTruthy();
    expect(bundleResponse, "bundle response recorded").toBeTruthy();
    await waitForDiffBrowsing(page);
    return { previewId: previewId as string, workspaceId: workspaceId as string, operationId: accepted.operation_id, bundle: bundle as ParsedBundle, status: upload.status(), previewStatus: preview.status(), etag: (bundleResponse as PlaywrightResponse).headers()["etag"] ?? "" };
  } finally {
    bundleRecording.dispose();
  }
}

async function approveByReviewer(reviewer: JourneyIdentity, submissionId: string): Promise<number> {
  const facts = (await getReviewFacts(reviewer, submissionId)).body;
  expect(facts.status, "review status before approve").toBe("PENDING");
  const applied = await applyReview(reviewer, submissionId, { expected_review_version: facts.review_version, action: "APPROVE" });
  expect(applied.status, "review approve status").toBe(201);
  return applied.body.review_version;
}

async function acceptAnomalies(archiver: JourneyIdentity, submissionId: string, candidateDigest: string, reason: string, only?: (side: string | null, issueCode: string) => boolean): Promise<ArchivePlanBody> {
  const listed = (await listArchiveCandidates(archiver)).body;
  const candidate = listed.candidates.find((item) => item.submission_id === submissionId);
  expect(candidate, "candidate present").toBeTruthy();
  const plan = (await previewArchivePlan(archiver, { submission_id: submissionId, expected_candidate_digest: candidateDigest })).body;
  for (const anomaly of plan.anomalies) {
    if (anomaly.resolution_status === "ACCEPTED") continue;
    if (only && !only(anomaly.side, anomaly.issue_code)) continue;
    const action = anomaly.subject_kind === "APPROVED_SIBLING_EXCLUDED" ? "ACKNOWLEDGE_EXCLUSION"
      : anomaly.subject_kind === "PROJECT_IDENTITY_EXCEPTION" ? "ACKNOWLEDGE_IDENTITY_EXCEPTION"
      : anomaly.subject_kind === "CONFIGURATION_SOURCE" ? "ACKNOWLEDGE_SOURCE_EXCEPTION"
      : anomaly.subject_kind === "CONFIGURATION_TIME_QUALITY" ? "ACKNOWLEDGE_TIME_QUALITY"
      : "ACKNOWLEDGE_TIME_ORDER";
    await appendArchiveAnomalyResolution(archiver, {
      expected_baseline_node_id: plan.head.business_baseline_node_id,
      expected_baseline_head_version: plan.head.baseline_head_version,
      candidate_set_digest: plan.candidate_set_digest,
      selected: { submission_id: submissionId, expected_candidate_digest: candidateDigest },
      subject_digest: anomaly.subject_digest,
      subject_kind: anomaly.subject_kind,
      issue_code: anomaly.issue_code,
      target_submission_id: anomaly.target_submission_id,
      target_candidate_digest: anomaly.target_candidate_digest,
      expected_sequence: anomaly.latest_sequence,
      action,
      reason,
    });
  }
  return (await previewArchivePlan(archiver, { submission_id: submissionId, expected_candidate_digest: candidateDigest })).body;
}

async function acceptAllAnomalies(archiver: JourneyIdentity, submissionId: string, candidateDigest: string, reason: string): Promise<ArchivePlanBody> {
  return acceptAnomalies(archiver, submissionId, candidateDigest, reason);
}

async function openArchiveDialogUi(page: Page, submissionLabel: string) {
  await gotoWorkbenchFresh(page);
  await page.getByRole("button", { name: submissionLabel, exact: true }).click();
  await page.locator(".workspace-context-bar").getByRole("button", { name: "归档主线" }).click();
  const dialog = page.getByRole("dialog", { name: "归档主基线" });
  await expect(dialog.getByText("预检状态")).toBeVisible({ timeout: 60_000 });
  return dialog;
}

async function historyHeadVersion(identity: JourneyIdentity): Promise<number> {
  return (await listHistory(identity)).body.head.version;
}

// ---------------------------------------------------------------------------
// J1 — archive mainline, pending-review blocking, two-sided items, identity
// confirmation (R1/R4/R8/R9-three-node).
// ---------------------------------------------------------------------------
test("j1-archive-mainline", async ({ browser }, testInfo) => {
  test.setTimeout(1_800_000);
  requireJourneyEnv();
  const scope = scopeBySlug("j1-archive-mainline");
  const s1 = identityFor(scope, "submitter");
  const s2 = identityFor(scope, "submitter2");
  const reviewer = identityFor(scope, "reviewer");
  const archiver = identityFor(scope, "archiver");
  const s1Session = await openSession(browser, s1);
  const archiverSession = await openSession(browser, archiver);
  const archiverSecondSession = await openSession(browser, archiver);

  try {
    // Steps 1–3: A archived with accept → revoke → re-accept in the UI.
    await gotoWorkbenchFresh(s1Session.page);
    const runA = await uploadDirsAndPreview(s1Session.page, s1, scope, { modified: inputDir(scope, "modified_only") });
    const submitA = await submitViaUi(s1Session.page, s1, runA.workspaceId);
    await approveByReviewer(reviewer, submitA.submissionId);

    const listedA = (await listArchiveCandidates(archiver)).body;
    expect(listedA.candidates.map((candidate) => candidate.submission_id)).toEqual([submitA.submissionId]);
    const digestA = listedA.candidates[0]!.expected_candidate_digest;
    const planA = (await previewArchivePlan(archiver, { submission_id: submitA.submissionId, expected_candidate_digest: digestA })).body;
    expectAnomalySets(planA, [`CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|${submitA.submissionId}`], "j1-step2");
    expect(businessIssueSet(planA), "j1-step2 business issues").toEqual(["CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED"]);
    // Empty INITIAL baseline: one NOT_APPLICABLE source row, no baseline-time item.
    const diagnosticsA = planA.business_validation.source_diagnostics as Array<{ detected_status: string; initial_origin: string; submission_id: string }>;
    expect(diagnosticsA.map((diagnostic) => [diagnostic.submission_id, diagnostic.detected_status, diagnostic.initial_origin].join("|")), "j1-step2 source diagnostics").toEqual([
      `${submitA.submissionId}|NOT_APPLICABLE|INITIAL_EMPTY`,
    ]);

    const dialogA = await openArchiveDialogUi(archiverSession.page, "提交 1");
    const startA = dialogA.getByRole("button", { name: "确认归档" });
    await expect(startA).toBeDisabled();
    await expect(dialogA.getByText("还有 1 项未处理")).toBeVisible();
    await dialogA.getByRole("checkbox", { name: /确认把/ }).check();
    await expect(startA).toBeDisabled();
    await expect(dialogA.getByText("还有 1 项未处理")).toBeVisible();
    const cardA = dialogA.locator(".archive-anomaly");
    await cardA.getByRole("button", { name: "接受" }).click();
    const acceptA = archiverSession.page.getByRole("dialog", { name: "接受异常" });
    await acceptA.getByLabel("接受理由").fill("j1 现场版本没有写入生成时间");
    await acceptA.getByRole("button", { name: "确认接受" }).click();
    await expect(cardA.getByText("已接受")).toBeVisible();
    await cardA.getByRole("button", { name: "撤销接受" }).click();
    const revokeA = archiverSession.page.getByRole("dialog", { name: "撤销接受" });
    await revokeA.getByLabel("撤销理由").fill("j1 重新核对");
    await revokeA.getByRole("button", { name: "确认撤销" }).click();
    await expect(dialogA.getByText("还有 1 项未处理")).toBeVisible();
    await cardA.getByRole("button", { name: "接受" }).click();
    const acceptA2 = archiverSession.page.getByRole("dialog", { name: "接受异常" });
    await acceptA2.getByLabel("接受理由").fill("j1 现场版本没有写入生成时间");
    await acceptA2.getByRole("button", { name: "确认接受" }).click();
    await expect(startA).toBeEnabled();
    await saveEvidence(archiverSession.page, testInfo, "j1-archive-dialog");
    await startA.click();
    await expect(dialogA.getByText("归档完成")).toBeVisible({ timeout: 120_000 });
    expect(await historyHeadVersion(s1)).toBe(1);
    await saveEvidence(archiverSession.page, testInfo, "j1-archive-result");
    assertClean(archiverSession.diagnostics, "j1-archive");
    appendCaseLog(`j1-archive-a ok submission=${submitA.submissionId} head=1`);
    // D1 real coverage: tree shows 已归档, details show 成为归档基线 1.
    await dialogA.getByRole("button", { name: "完成" }).click();
    await gotoWorkbenchFresh(archiverSession.page);
    await archiverSession.page.getByRole("button", { name: "提交 1", exact: true }).click();
    await expect(archiverSession.page.locator(".workspace-details").getByText("已归档，成为归档基线 1")).toBeVisible();
    await saveEvidence(archiverSession.page, testInfo, "j1-disposition-archived");

    // Step 4: FULL B over A — baseline_to_initial empty, initial_to_modified ≥ 1.
    await gotoWorkbenchFresh(s1Session.page);
    const runB = await uploadDirsAndPreview(s1Session.page, s1, scope, { modified: inputDir(scope, "full_modified"), initial: inputDir(scope, "full_initial") });
    const summaries = new Map(runB.bundle.manifest.pairs.map((pair) => [pair.pair_id, pair.summary]));
    expect(summaries.size, "FULL pair count").toBe(2);
    const baselineToInitial = summaries.get("baseline_to_initial");
    const initialToModified = summaries.get("initial_to_modified");
    expect(baselineToInitial, "baseline_to_initial present").toBeTruthy();
    expect(initialToModified, "initial_to_modified present").toBeTruthy();
    expect(Number(baselineToInitial!.changed_table_count), "baseline_to_initial changed").toBe(0);
    expect(Number(initialToModified!.changed_table_count), "initial_to_modified changed").toBeGreaterThanOrEqual(1);
    appendCaseLog(`j1-step4 ok baseline_to_initial.changed=0 initial_to_modified.changed=${initialToModified!.changed_table_count}`);

    // Step 5: B submitted, C submitted by s2, reviewer approves B.
    const submitB = await submitViaUi(s1Session.page, s1, runB.workspaceId);
    const s2Session = await openSession(browser, s2);
    let runC = await uploadDirsAndPreview(s2Session.page, s2, scope, { modified: inputDir(scope, "modified_only") });
    const submitC = await submitViaUi(s2Session.page, s2, runC.workspaceId);
    await approveByReviewer(reviewer, submitB.submissionId);

    // Step 6: pending-review blocker names C and disables the start.
    const planBlocked = (await previewArchivePlan(archiver, { submission_id: submitB.submissionId, expected_candidate_digest: (await listArchiveCandidates(archiver)).body.candidates.find((candidate) => candidate.submission_id === submitB.submissionId)!.expected_candidate_digest })).body;
    expect(planBlocked.blockers, "j1-step6 blockers").toContain("ARCHIVE_PENDING_REVIEW");
    expect(planBlocked.pending_submission_ids, "j1-step6 pending list").toContain(submitC.submissionId);
    const dialogB = await openArchiveDialogUi(archiverSession.page, "提交 2");
    await expect(dialogB.getByText(/有 1 个待审核的提交/)).toBeVisible();
    await expect(dialogB.getByRole("button", { name: "提交 3" })).toBeVisible();
    await expect(dialogB.getByText("只有上传或预览、尚未提交的工作区不影响归档。")).toBeVisible();
    await expect(dialogB.getByRole("button", { name: "确认归档" })).toBeDisabled();
    await expect(dialogB.getByText("当前预检存在阻断项")).toBeVisible();
    await saveEvidence(archiverSession.page, testInfo, "j1-pending-blocked");
    await dialogB.getByRole("button", { name: "关闭对话框" }).click();

    // Step 7: reject C, re-upload C as a draft; the three expected anomalies.
    const factsC = (await getReviewFacts(reviewer, submitC.submissionId)).body;
    expect(factsC.status, "j1-step7 C still pending").toBe("PENDING");
    await applyReview(reviewer, submitC.submissionId, { expected_review_version: factsC.review_version, action: "REJECT", reason: "j1 退回重传" });
    await gotoWorkbenchFresh(s2Session.page);
    runC = await uploadDirsAndPreview(s2Session.page, s2, scope, { modified: inputDir(scope, "modified_only") });
    const digestB = (await listArchiveCandidates(archiver)).body.candidates.find((candidate) => candidate.submission_id === submitB.submissionId)!.expected_candidate_digest;
    const planB = (await previewArchivePlan(archiver, { submission_id: submitB.submissionId, expected_candidate_digest: digestB })).body;
    expectAnomalySets(planB, [
      `CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|INITIAL|${submitB.submissionId}`,
      `CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|${submitB.submissionId}`,
      `CONFIGURATION_TIME_QUALITY|BASELINE_TIME_UNAVAILABLE|BASELINE|${submitB.submissionId}`,
    ], "j1-step7");
    appendCaseLog(`j1-step7 ok submission=${submitB.submissionId}`);

    // Step 8: accept only the INITIAL side; MODIFIED stays unprocessed.
    await acceptAnomalies(archiver, submitB.submissionId, digestB, "j1 只接受①", (side) => side === "INITIAL");
    const dialogB2 = await openArchiveDialogUi(archiverSession.page, "提交 2");
    await expect(dialogB2.locator(".archive-anomaly", { hasText: "②本次归档组态" }).getByText("未处理")).toBeVisible();
    await dialogB2.getByRole("checkbox", { name: /确认把/ }).check();
    await expect(dialogB2.getByRole("button", { name: "确认归档" })).toBeDisabled();
    await dialogB2.getByRole("button", { name: "关闭对话框" }).click();

    // Step 9: revoke MODIFIED in a second context; the first context's start
    // is rejected and the re-preview shows the revoked item.
    const planB2 = (await previewArchivePlan(archiver, { submission_id: submitB.submissionId, expected_candidate_digest: digestB })).body;
    const modifiedItem = planB2.anomalies.find((anomaly) => anomaly.side === "MODIFIED");
    expect(modifiedItem, "j1-step9 modified item accepted").toBeTruthy();
    await appendArchiveAnomalyResolution(archiver, {
      expected_baseline_node_id: planB2.head.business_baseline_node_id,
      expected_baseline_head_version: planB2.head.baseline_head_version,
      candidate_set_digest: planB2.candidate_set_digest,
      selected: { submission_id: submitB.submissionId, expected_candidate_digest: digestB },
      subject_digest: modifiedItem!.subject_digest,
      subject_kind: modifiedItem!.subject_kind,
      issue_code: modifiedItem!.issue_code,
      target_submission_id: modifiedItem!.target_submission_id,
      target_candidate_digest: modifiedItem!.target_candidate_digest,
      expected_sequence: modifiedItem!.latest_sequence,
      action: "REVOKE",
      reason: "j1 第二个身份复核后撤销",
    });
    const dialogB3 = await openArchiveDialogUi(archiverSession.page, "提交 2");
    await dialogB3.getByRole("checkbox", { name: /确认把/ }).check();
    await dialogB3.getByRole("button", { name: "确认归档" }).click();
    await expect(dialogB3.getByText("归档候选或核验结果已变化，请重新预检")).toBeVisible({ timeout: 120_000 });
    await dialogB3.getByRole("button", { name: "重新预检" }).click();
    await expect(dialogB3.locator(".archive-anomaly", { hasText: "②本次归档组态" }).getByText("已撤销接受，需要重新处理")).toBeVisible();
    assertClean(archiverSession.diagnostics, "j1-revoke-conflict");

    // Step 10: re-accept and archive B as baseline 2.
    await acceptAllAnomalies(archiver, submitB.submissionId, digestB, "j1 重新接受②");
    const dialogB4 = await openArchiveDialogUi(archiverSession.page, "提交 2");
    await dialogB4.getByRole("checkbox", { name: /确认把/ }).check();
    await dialogB4.getByRole("button", { name: "确认归档" }).click();
    await expect(dialogB4.getByText("归档完成")).toBeVisible({ timeout: 120_000 });
    expect(await historyHeadVersion(s1)).toBe(2);
    appendCaseLog(`j1-step10 ok submission=${submitB.submissionId} head=2`);
    assertClean(archiverSession.diagnostics, "j1-archive-b");

    // Step 11: re-upload C on baseline 2, approve, archive as baseline 3.
    // (The archive-result dialog from step 10 is still open; start fresh.)
    await gotoWorkbenchFresh(s2Session.page);
    runC = await uploadDirsAndPreview(s2Session.page, s2, scope, { modified: inputDir(scope, "modified_only") });
    const submitC2 = await submitViaUi(s2Session.page, s2, runC.workspaceId);
    await approveByReviewer(reviewer, submitC2.submissionId);
    const digestC2 = (await listArchiveCandidates(archiver)).body.candidates.find((candidate) => candidate.submission_id === submitC2.submissionId)!.expected_candidate_digest;
    const planC2 = (await previewArchivePlan(archiver, { submission_id: submitC2.submissionId, expected_candidate_digest: digestC2 })).body;
    expectAnomalySets(planC2, [
      `CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|${submitC2.submissionId}`,
      `CONFIGURATION_TIME_QUALITY|BASELINE_TIME_UNAVAILABLE|BASELINE|${submitC2.submissionId}`,
    ], "j1-step11");
    await acceptAllAnomalies(archiver, submitC2.submissionId, digestC2, "j1 接受 C");
    const dialogC = await openArchiveDialogUi(archiverSecondSession.page, "提交 4");
    await dialogC.getByRole("checkbox", { name: /确认把/ }).check();
    await dialogC.getByRole("button", { name: "确认归档" }).click();
    await expect(dialogC.getByText("归档完成")).toBeVisible({ timeout: 120_000 });
    expect(await historyHeadVersion(s1)).toBe(3);
    appendCaseLog(`j1-step11 ok submission=${submitC2.submissionId} head=3`);

    // Steps 12–13: D (DIFFERENT_PROJECT) requires identity confirmation.
    await gotoWorkbenchFresh(s1Session.page);
    await selectUploadDirs(s1Session.page, { modified: inputDir(scope, "replacement") });
    await startUpload(s1Session.page);
    expect(await waitForPreviewOutcome(s1Session.page)).toBe("compare");
    await waitForDiffBrowsing(s1Session.page);
    const submitResponse = s1Session.page.waitForResponse((response) => isPost(response, "/submit-attempts"), { timeout: 300_000 });
    await compareAction(s1Session.page, "提交").click();
    const submitDialog = s1Session.page.getByRole("dialog");
    await expect(submitDialog).toBeVisible();
    await expect(submitDialog.getByText(/项目身份/)).toBeVisible({ timeout: 60_000 });
    for (const requirement of await submitDialog.locator(".confirm-requirement").all()) {
      await requirement.getByRole("checkbox").check();
      await requirement.getByRole("textbox").fill("j1 已核对项目身份差异");
    }
    await submitDialog.getByRole("button", { name: "确认提交", exact: true }).click();
    const submitted = await submitResponse;
    expect(submitted.status(), "D submit status").toBe(202);
    const { submission: submissionD } = await waitForPendingSubmission(s1, runA.workspaceId, 240_000);
    await approveByReviewer(reviewer, submissionD.submission_id);
    const digestD = (await listArchiveCandidates(archiver)).body.candidates.find((candidate) => candidate.submission_id === submissionD.submission_id)!.expected_candidate_digest;
    const planD = (await previewArchivePlan(archiver, { submission_id: submissionD.submission_id, expected_candidate_digest: digestD })).body;
    expectAnomalySets(planD, [
      `CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|${submissionD.submission_id}`,
      `CONFIGURATION_TIME_QUALITY|BASELINE_TIME_UNAVAILABLE|BASELINE|${submissionD.submission_id}`,
      `PROJECT_IDENTITY_EXCEPTION|PROJECT_IDENTITY_EXCEPTION|-|${submissionD.submission_id}`,
    ], "j1-step13");
    await acceptAllAnomalies(archiver, submissionD.submission_id, digestD, "j1 接受 D 含身份例外");
    const dialogD = await openArchiveDialogUi(archiverSession.page, "提交 5");
    await dialogD.getByRole("checkbox", { name: /确认把/ }).check();
    await dialogD.getByRole("button", { name: "确认归档" }).click();
    await expect(dialogD.getByText("归档完成")).toBeVisible({ timeout: 120_000 });
    expect(await historyHeadVersion(s1)).toBe(4);
    appendCaseLog(`j1-step13 ok submission=${submissionD.submission_id} head=4`);
    assertClean(s1Session.diagnostics, "j1-submit-d");
    assertClean(archiverSecondSession.diagnostics, "j1-archive-d");

    // Step 14: three-node history compare (INITIAL, baselines 1 and 2).
    await gotoWorkbenchFresh(s1Session.page);
    await selectTreeRow(s1Session.page, "初始基线");
    await workshopAction(s1Session.page, "加入比较").click();
    await selectTreeRow(s1Session.page, "归档基线 1");
    await workshopAction(s1Session.page, "加入比较").click();
    await selectTreeRow(s1Session.page, "归档基线 2");
    await workshopAction(s1Session.page, "加入比较").click();
    const compareResponse = s1Session.page.waitForResponse((response) => response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/history-compares"), { timeout: 120_000 });
    await s1Session.page.locator(".compare-tray").getByRole("button", { name: "历史比较", exact: true }).click();
    expect((await compareResponse).status()).toBeLessThan(300);
    const drawer = s1Session.page.locator('section[aria-label="历史比较结果抽屉"]');
    await expect(drawer).toBeVisible({ timeout: 60_000 });
    await expect(drawer.locator(".status-tag")).toHaveText("已完成", { timeout: 300_000 });
    await expect(drawer.locator(".history-pair-summary")).toHaveCount(2);
    await saveEvidence(s1Session.page, testInfo, "j1-history-three-nodes");
    await drawer.getByRole("button", { name: "打开差异工作台", exact: true }).click();
    await waitForDiffBrowsing(s1Session.page);
    assertClean(s1Session.diagnostics, "j1-history");
    appendCaseLog("j1 ok three-node history compare browsed");
  } finally {
    await closeSession(archiverSecondSession);
    await closeSession(archiverSession);
    await closeSession(s1Session);
  }
});

// ---------------------------------------------------------------------------
// J2 — manual close, re-verification, terminal dispositions (R12, D2/D3).
// ---------------------------------------------------------------------------
test("j2-manual-close", async ({ browser }, testInfo) => {
  test.setTimeout(1_800_000);
  requireJourneyEnv();
  const scope = scopeBySlug("j2-manual-close");
  const s1 = identityFor(scope, "submitter");
  const s2 = identityFor(scope, "submitter2");
  const s3 = identityFor(scope, "submitter-upload-only");
  const reviewer = identityFor(scope, "reviewer");
  const archiver = identityFor(scope, "archiver");
  const s1Session = await openSession(browser, s1);
  const s2Session = await openSession(browser, s2);
  const s3Session = await openSession(browser, s3);
  const archiverSession = await openSession(browser, archiver);

  try {
    // Step 1: A submitted, approved, archived.
    await gotoWorkbenchFresh(s1Session.page);
    const runA = await uploadDirsAndPreview(s1Session.page, s1, scope, { modified: inputDir(scope, "modified_only") });
    const submitA = await submitViaUi(s1Session.page, s1, runA.workspaceId);
    await approveByReviewer(reviewer, submitA.submissionId);
    const digestA = (await listArchiveCandidates(archiver)).body.candidates[0]!.expected_candidate_digest;
    const planA = (await previewArchivePlan(archiver, { submission_id: submitA.submissionId, expected_candidate_digest: digestA })).body;
    expectAnomalySets(planA, [`CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|${submitA.submissionId}`], "j2-step1");
    await acceptAllAnomalies(archiver, submitA.submissionId, digestA, "j2 t1 证据运行");
    const dialogA = await openArchiveDialogUi(archiverSession.page, "提交 1");
    await dialogA.getByRole("checkbox", { name: /确认把/ }).check();
    await dialogA.getByRole("button", { name: "确认归档" }).click();
    await expect(dialogA.getByText("归档完成")).toBeVisible({ timeout: 120_000 });
    expect(await historyHeadVersion(s1)).toBe(1);
    appendCaseLog(`j2-step1 ok submission=${submitA.submissionId} head=1`);

    // Step 2: B, C and E submitted and approved.
    // (The archive-result dialog from step 1 is still open; start fresh.)
    await gotoWorkbenchFresh(s1Session.page);
    const runB = await uploadDirsAndPreview(s1Session.page, s1, scope, { modified: inputDir(scope, "full_modified"), initial: inputDir(scope, "full_initial") });
    const submitB = await submitViaUi(s1Session.page, s1, runB.workspaceId);
    const runC = await uploadDirsAndPreview(s2Session.page, s2, scope, { modified: inputDir(scope, "modified_only") });
    const submitC = await submitViaUi(s2Session.page, s2, runC.workspaceId);
    const runE = await uploadDirsAndPreview(s3Session.page, s3, scope, { modified: inputDir(scope, "e_modified"), initial: inputDir(scope, "e_initial") });
    const submitE = await submitViaUi(s3Session.page, s3, runE.workspaceId);
    await approveByReviewer(reviewer, submitB.submissionId);
    await approveByReviewer(reviewer, submitC.submissionId);
    await approveByReviewer(reviewer, submitE.submissionId);

    // Step 3: eight anomalies; every source explained.
    const listed = (await listArchiveCandidates(archiver)).body;
    expect(listed.candidates.map((candidate) => candidate.submission_id).sort()).toEqual([submitB.submissionId, submitC.submissionId, submitE.submissionId].sort());
    const digestB = listed.candidates.find((candidate) => candidate.submission_id === submitB.submissionId)!.expected_candidate_digest;
    const plan3 = (await previewArchivePlan(archiver, { submission_id: submitB.submissionId, expected_candidate_digest: digestB })).body;
    expectAnomalySets(plan3, [
      `CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|INITIAL|${submitB.submissionId}`,
      `CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|${submitB.submissionId}`,
      `CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|${submitC.submissionId}`,
      `CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|INITIAL|${submitE.submissionId}`,
      `CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|${submitE.submissionId}`,
      `CONFIGURATION_TIME_QUALITY|BASELINE_TIME_UNAVAILABLE|BASELINE|${submitB.submissionId},${submitC.submissionId},${submitE.submissionId}`,
      `APPROVED_SIBLING_EXCLUDED|APPROVED_SIBLING_EXCLUDED|-|${submitC.submissionId}`,
      `APPROVED_SIBLING_EXCLUDED|APPROVED_SIBLING_EXCLUDED|-|${submitE.submissionId}`,
    ], "j2-step3");
    const diagnostics3 = plan3.business_validation.source_diagnostics as Array<{ submission_id: string; detected_status: string }>;
    expect(diagnostics3.length, "j2-step3 source diagnostics").toBe(3);
    for (const diagnostic of diagnostics3) expect(diagnostic.detected_status, `j2-step3 source ${diagnostic.submission_id}`).toBe("EXPLAINED");

    // Step 4: close C with a reason; interrupt once, retry with the same key.
    const digestC = listed.candidates.find((candidate) => candidate.submission_id === submitC.submissionId)!;
    const closureBodies: string[] = [];
    let closureAborted = false;
    await archiverSession.page.route("**/v1/submissions/*/closure", async (route) => {
      if (!closureAborted) {
        closureAborted = true;
        await route.abort("failed");
        return;
      }
      await route.fallback();
    });
    archiverSession.page.on("request", (request) => {
      if (request.method() === "POST" && new URL(request.url()).pathname.endsWith("/closure")) closureBodies.push(request.postData() ?? "");
    });
    const dialogClose = await openArchiveDialogUi(archiverSession.page, "提交 2");
    await dialogClose.locator("section[aria-label='候选提交']").getByRole("button", { name: "关闭（不归档）" }).nth(1).click();
    const closeDialog = archiverSession.page.getByRole("dialog", { name: "关闭提交（不归档）" });
    await closeDialog.getByLabel("关闭理由").fill("C 的业务口径已变化，先关闭");
    await closeDialog.getByRole("checkbox", { name: /我已了解关闭不可撤销/ }).check();
    await closeDialog.getByRole("button", { name: "确认关闭" }).click();
    await expect(closeDialog.getByText("关闭请求未能送达，可以重试")).toBeVisible({ timeout: 120_000 });
    await closeDialog.getByRole("button", { name: "重试" }).click();
    await expect(closeDialog.getByText("已关闭")).toBeVisible({ timeout: 120_000 });
    await saveEvidence(archiverSession.page, testInfo, "j2-close-result");
    expect(closureBodies.length, "closure sends (abort + retry)").toBe(2);
    const firstClose = JSON.parse(closureBodies[0]!) as { expected_review_version: number; reason: string };
    const retryClose = JSON.parse(closureBodies[1]!) as { expected_review_version: number; reason: string };
    expect(firstClose.expected_review_version, "close takes the candidate review_version").toBe(digestC.review_version);
    expect(retryClose, "retry reuses the same key and body").toEqual(firstClose);
    expect(retryClose.reason).toBe("C 的业务口径已变化，先关闭");
    appendCaseLog(`j2-step4 ok closed=${submitC.submissionId} review_version=${firstClose.expected_review_version}`);
    await archiverSession.page.unroute("**/v1/submissions/*/closure");
    await closeDialog.getByRole("button", { name: "取消" }).click();
    await expect(dialogClose.getByText("候选集合已变化，之前的接受不再适用，请重新核对")).toBeVisible();

    // Step 5: the set is re-derived; everything is unprocessed again.
    const plan5 = (await previewArchivePlan(archiver, { submission_id: submitB.submissionId, expected_candidate_digest: digestB })).body;
    expectAnomalySets(plan5, [
      `CONFIGURATION_SOURCE|INITIAL_SOURCE_UNEXPLAINED|INITIAL|${submitE.submissionId}`,
      `CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|INITIAL|${submitB.submissionId}`,
      `CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|${submitB.submissionId}`,
      `CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|INITIAL|${submitE.submissionId}`,
      `CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|${submitE.submissionId}`,
      `CONFIGURATION_TIME_QUALITY|BASELINE_TIME_UNAVAILABLE|BASELINE|${submitB.submissionId},${submitE.submissionId}`,
      `APPROVED_SIBLING_EXCLUDED|APPROVED_SIBLING_EXCLUDED|-|${submitE.submissionId}`,
    ], "j2-step5");
    expect(plan5.anomalies.every((anomaly) => anomaly.resolution_status === "UNRESOLVED"), "j2-step5 all unprocessed").toBe(true);
    expect(plan5.candidate_set_digest, "j2-step5 set re-derived").not.toBe(plan3.candidate_set_digest);

    // Step 6: s2's workspace is released; C reads closed; review shows both.
    const workspaceC = await currentWorkspace(s2);
    expect(workspaceC.active_submission_id, "s2 pointer cleared").toBeNull();
    expect(workspaceC.active_submit_attempt_id, "s2 attempt cleared").toBeNull();
    await gotoWorkbenchFresh(s2Session.page);
    await s2Session.page.getByRole("button", { name: "提交 3", exact: true }).click();
    const detailsC = s2Session.page.locator(".workspace-details");
    await expect(detailsC.getByText("已关闭（未归档）").first()).toBeVisible();
    await expect(detailsC.getByText(archiver.actorId)).toBeVisible();
    await saveEvidence(s2Session.page, testInfo, "j2-disposition-closed");
    const factsC = (await getReviewFacts(s2, submitC.submissionId)).body;
    expect(factsC.status, "j2-step6 review keeps APPROVED").toBe("APPROVED");
    expect(factsC.submission_disposition, "j2-step6 disposition").toBe("CLOSED_NOT_ARCHIVED");
    assertClean(s2Session.diagnostics, "j2-closed-read");

    // Step 7: accept all seven; B archived, E closed at archive (D2 real).
    await acceptAllAnomalies(archiver, submitB.submissionId, digestB, "j2 接受余下全部");
    const dialogStart = await openArchiveDialogUi(archiverSession.page, "提交 2");
    await dialogStart.getByRole("checkbox", { name: /确认把/ }).check();
    await dialogStart.getByRole("button", { name: "确认归档" }).click();
    await expect(dialogStart.getByText("归档完成")).toBeVisible({ timeout: 120_000 });
    await expect(dialogStart.getByText("归档 1 项，关闭 1 项")).toBeVisible();
    expect(await historyHeadVersion(s1)).toBe(2);
    const workspaceE = await currentWorkspace(s3);
    expect(workspaceE.active_submission_id, "s3 workspace released").toBeNull();
    await saveEvidence(archiverSession.page, testInfo, "j2-archive-result");
    appendCaseLog(`j2-step7 ok archived=${submitB.submissionId} closed=${submitE.submissionId} head=2`);
    await dialogStart.getByRole("button", { name: "完成" }).click();
    await gotoWorkbenchFresh(archiverSession.page);
    await archiverSession.page.getByRole("button", { name: "提交 4", exact: true }).click();
    const detailsE = archiverSession.page.locator(".workspace-details");
    await expect(detailsE.getByText("已关闭（未归档）").first()).toBeVisible();
    await expect(detailsE.getByText("归档时选中了其他提交")).toBeVisible();
    await saveEvidence(archiverSession.page, testInfo, "j2-disposition-closed-at-archive");

    // Step 8: C re-uploaded on baseline 2, approved, archived as baseline 3.
    await gotoWorkbenchFresh(s2Session.page);
    const runC2 = await uploadDirsAndPreview(s2Session.page, s2, scope, { modified: inputDir(scope, "modified_only") });
    const submitC2 = await submitViaUi(s2Session.page, s2, runC2.workspaceId);
    await approveByReviewer(reviewer, submitC2.submissionId);
    const digestC2 = (await listArchiveCandidates(archiver)).body.candidates.find((candidate) => candidate.submission_id === submitC2.submissionId)!.expected_candidate_digest;
    const planC2 = (await previewArchivePlan(archiver, { submission_id: submitC2.submissionId, expected_candidate_digest: digestC2 })).body;
    expectAnomalySets(planC2, [
      `CONFIGURATION_TIME_QUALITY|GENERATION_TIME_MISSING|MODIFIED|${submitC2.submissionId}`,
      `CONFIGURATION_TIME_QUALITY|BASELINE_TIME_UNAVAILABLE|BASELINE|${submitC2.submissionId}`,
    ], "j2-step8");
    await acceptAllAnomalies(archiver, submitC2.submissionId, digestC2, "j2 重新接受 C");
    const dialogC2 = await openArchiveDialogUi(archiverSession.page, "提交 5");
    await dialogC2.getByRole("checkbox", { name: /确认把/ }).check();
    await dialogC2.getByRole("button", { name: "确认归档" }).click();
    await expect(dialogC2.getByText("归档完成")).toBeVisible({ timeout: 120_000 });
    expect(await historyHeadVersion(s1)).toBe(3);
    appendCaseLog(`j2-step8 ok submission=${submitC2.submissionId} head=3`);
    assertClean(s2Session.diagnostics, "j2-reupload");
    assertClean(s3Session.diagnostics, "j2-e");
    assertClean(archiverSession.diagnostics, "j2-archive");
  } finally {
    await closeSession(archiverSession);
    await closeSession(s3Session);
    await closeSession(s2Session);
    await closeSession(s1Session);
  }
});

