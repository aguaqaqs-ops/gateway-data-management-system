import { expect, test, type Page, type Request as PlaywrightRequest, type Route } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import type { components } from "../src/features/api/generated/openapi";
import {
  SIMULATED_ERROR_RESPONSES,
  TEST_ARCHIVE_RESULT,
  TEST_ARCHIVE_STARTED,
  TEST_CLOSE_SUBMISSION,
  V_CANDIDATES,
  validateSimulatedRequest,
  vHistoryPage,
  vPreviewAfterClose,
  vPreviewAllKinds,
  vPreviewAllKindsMissingAccepted,
  vPreviewBlocked,
  vReviewFacts,
} from "../src/features/dev/simulated-api";
import {
  vCandidates200,
  vManyHistoryPage,
  vPreview399Accepted,
  vPreviewAcceptedSource,
  vPreviewAcceptedSourceRevoked,
  vPreviewPending,
  vPreviewTwoSided,
  vPreviewTwoSidedAccepted,
  vPreviewTwoSidedInitialAccepted,
  vPreviewTwoSidedBothAccepted,
  vPreviewTwoSidedBothRevoked,
  vPreviewTwoSidedInitialRevoked,
  vPreviewPendingStartable,
  vPreviewUnknownCode,
  vPreviewRechanged,
  V_CANDIDATES_AFTER_CLOSE,
  V_CANDIDATES_RECHANGED,
  V_PENDING_CANDIDATES,
} from "../src/features/dev/archive-validation-data";

type Schemas = components["schemas"];
type Preview = Schemas["PreviewArchivePlanResponse"];

const screenshotDirectory = process.env.GATEWAY_FE_SCREENSHOT_DIR;

async function screenshot(page: Page, name: string, width: number) {
  if (!screenshotDirectory) return;
  for (const current of [width, width === 1280 ? 1920 : 1280]) {
    await mkdir(join(screenshotDirectory, String(current)), { recursive: true });
    await page.setViewportSize({ width: current, height: current === 1280 ? 800 : 1080 });
    await page.screenshot({ path: join(screenshotDirectory, String(current), `${name}.png`), fullPage: false, animations: "disabled" });
  }
  await page.setViewportSize({ width, height: width === 1280 ? 800 : 1080 });
}

async function cardScreenshot(page: Page, name: string, width: number, locator: ReturnType<Page["locator"]>) {
  if (!screenshotDirectory) return;
  for (const current of [width, width === 1280 ? 1920 : 1280]) {
    await mkdir(join(screenshotDirectory, String(current)), { recursive: true });
    await page.setViewportSize({ width: current, height: current === 1280 ? 800 : 1080 });
    await locator.scrollIntoViewIfNeeded();
    await page.waitForTimeout(50);
    await page.screenshot({ path: join(screenshotDirectory, String(current), `${name}.png`), fullPage: false, animations: "disabled" });
  }
  await page.setViewportSize({ width, height: width === 1280 ? 800 : 1080 });
}

interface ArchiveScenario {
  candidates?: Schemas["ArchiveCandidatesResponse"];
  /** Consumed in order per list call (last repeats): models the set change. */
  candidatesList?: Schemas["ArchiveCandidatesResponse"][];
  previews?: Preview[];
  history?: Schemas["HistoryListResponse"];
  candidatesForbidden?: boolean;
  previewForbidden?: boolean;
  confirmConflict?: string;
  resolutionConflict?: string;
  startConflict?: string;
  closure?: { status: number; code?: string }[] | "created-then-replay";
  closeForbidden?: boolean;
  /** The first closure attempt is lost in the browser; the retry replays the same key. */
  closureAbortOnce?: boolean;
  /** When true, the preview handler waits for the test to release the gate. */
  holdPreview?: boolean;
}

function errorBody(route: string, status: number, code: string, method = "POST"): { code: string; message: string } {
  const found = SIMULATED_ERROR_RESPONSES.find((item) => item.route === route && item.method === method && item.status === status && item.body.code === code);
  if (!found) throw new Error(`simulated error missing: ${method} ${route} ${status} ${code}`);
  return found.body;
}

async function installArchiveScenario(page: Page, scenario: ArchiveScenario = {}) {
  let releasePreview: () => void = () => {};
  let previewGate: Promise<void> | null = null;
  if (scenario.holdPreview) {
    let release!: () => void;
    previewGate = new Promise<void>((resolve) => {
      release = resolve;
    });
    releasePreview = release;
  }
  const apiRequests: Array<{ method: string; path: string; token: string | null; idempotencyKey: string | null; body: string }> = [];
  const apiResponses: Array<{ method: string; path: string; status: number; body: string }> = [];
  const record = (method: string, path: string, token: string | null, idempotencyKey: string | null, body: string, status: number, responseBody: string) => {
    apiRequests.push({ method, path, token, idempotencyKey, body });
    apiResponses.push({ method, path, status, body: responseBody });
  };
  const rejectInvalid = async (route: Route, request: PlaywrightRequest): Promise<boolean> => {
    const invalid = validateSimulatedRequest({ method: request.method(), url: new URL(request.url()), headers: request.headers(), body: request.postData() ?? "" });
    if (!invalid) return false;
    record(request.method(), new URL(request.url()).pathname, request.headers()["authorization"] ?? null, request.headers()["idempotency-key"] ?? null, request.postData() ?? "", 422, JSON.stringify(invalid));
    await route.fulfill({ status: 422, contentType: "application/json", body: JSON.stringify(invalid) });
    return true;
  };
  const json = (route: Route, request: PlaywrightRequest, status: number, body: unknown) => {
    record(request.method(), new URL(request.url()).pathname, request.headers()["authorization"] ?? null, request.headers()["idempotency-key"] ?? null, request.postData() ?? "", status, JSON.stringify(body));
    return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  };

  await page.route("**/v1/workspaces", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const request = route.request();
    if (await rejectInvalid(route, request)) return;
    const response = { ...SIMULATED_WORKSPACE };
    return json(route, request, 200, response);
  });
  await page.route("**/v1/history**", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    return json(route, route.request(), 200, scenario.history ?? vHistoryPage());
  });
  await page.route("**/v1/submissions/*/review", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const submissionId = path.split("/")[3] ?? "";
    return json(route, route.request(), 200, vReviewFacts(submissionId));
  });
  const candidatesScript = [...(scenario.candidatesList ?? (scenario.candidates ? [scenario.candidates] : [V_CANDIDATES]))];
  let candidatesCalls = 0;
  await page.route("**/v1/archive-candidates", async (route) => {
    const request = route.request();
    if (scenario.candidatesForbidden) {
      const error = errorBody("/v1/archive-candidates", 403, "SCOPE_FORBIDDEN", "GET");
      return json(route, request, 403, error);
    }
    candidatesCalls += 1;
    return json(route, request, 200, candidatesScript[Math.min(candidatesCalls - 1, candidatesScript.length - 1)]!);
  });
  const previews = [...(scenario.previews ?? [vPreviewAllKinds()])];
  let previewCalls = 0;
  await page.route("**/v1/archive-plan-preview", async (route) => {
    const request = route.request();
    if (await rejectInvalid(route, request)) return;
    if (scenario.previewForbidden) {
      const error = errorBody("/v1/archive-plan-preview", 403, "SCOPE_FORBIDDEN");
      return json(route, request, 403, error);
    }
    if (previewGate) await previewGate;
    previewCalls += 1;
    return json(route, request, 200, previews[Math.min(previewCalls - 1, previews.length - 1)]!);
  });
  await page.route("**/v1/archive-audit-events**", async (route) => {
    const request = route.request();
    if (await rejectInvalid(route, request)) return;
    return json(route, request, 200, { events: [], next_after_sequence: null });
  });
  let appendSequence = 10;
  await page.route("**/v1/archive-confirmations", async (route) => {
    const request = route.request();
    if (await rejectInvalid(route, request)) return;
    if (scenario.confirmConflict) {
      const error = errorBody("/v1/archive-confirmations", 409, scenario.confirmConflict);
      return json(route, request, 409, error);
    }
    appendSequence += 1;
    return json(route, request, 201, { event_id: `event-${appendSequence}`, sequence: appendSequence });
  });
  await page.route("**/v1/archive-anomaly-resolutions", async (route) => {
    const request = route.request();
    if (await rejectInvalid(route, request)) return;
    if (scenario.resolutionConflict) {
      const error = errorBody("/v1/archive-anomaly-resolutions", 409, scenario.resolutionConflict);
      return json(route, request, 409, error);
    }
    appendSequence += 1;
    return json(route, request, 201, { event_id: `event-${appendSequence}`, sequence: appendSequence });
  });
  await page.route("**/v1/archives", async (route) => {
    const request = route.request();
    if (await rejectInvalid(route, request)) return;
    if (scenario.startConflict) {
      const error = errorBody("/v1/archives", 409, scenario.startConflict);
      return json(route, request, 409, error);
    }
    const selected = (JSON.parse(request.postData() ?? "{}") as { selected?: { submission_id?: string } }).selected;
    return json(route, request, 201, { ...TEST_ARCHIVE_STARTED, selected_submission_id: selected?.submission_id ?? "v-s1" });
  });
  await page.route("**/v1/archives/*", async (route) => {
    const selected = previews[previews.length - 1]?.selected?.submission_id ?? "v-s1";
    const refs = (JSON.parse("{}") as { refs?: unknown }).refs;
    void refs;
    return json(route, route.request(), 200, { ...TEST_ARCHIVE_RESULT, selected_submission_id: selected, dispositions: [{ submission_id: selected, disposition: "ARCHIVED_BASELINE" }] });
  });
  let closureCalls = 0;
  let closureAborted = false;
  const closureScript = scenario.closure ?? "created-then-replay";
  await page.route("**/v1/submissions/*/closure", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (scenario.closureAbortOnce && !closureAborted) {
      closureAborted = true;
      apiRequests.push({ method: request.method(), path, token: request.headers()["authorization"] ?? null, idempotencyKey: request.headers()["idempotency-key"] ?? null, body: request.postData() ?? "" });
      return route.abort("failed");
    }
    if (await rejectInvalid(route, request)) return;
    if (scenario.closeForbidden) {
      const error = errorBody("/v1/submissions/{submission_id}/closure", 403, "SCOPE_FORBIDDEN");
      return json(route, request, 403, error);
    }
    if (closureScript === "created-then-replay") {
      closureCalls += 1;
      const submissionId = path.split("/")[3] ?? "";
      const response = { ...TEST_CLOSE_SUBMISSION, submission_id: submissionId };
      return json(route, request, closureCalls === 1 ? 201 : 200, response);
    }
    const step = closureScript[Math.min(closureCalls, closureScript.length - 1)]!;
    closureCalls += 1;
    if (step.status === 201 || step.status === 200) {
      const submissionId = path.split("/")[3] ?? "";
      return json(route, request, step.status, { ...TEST_CLOSE_SUBMISSION, submission_id: submissionId });
    }
    const error = errorBody("/v1/submissions/{submission_id}/closure", step.status, step.code ?? "");
    return json(route, request, step.status, error);
  });
  return { apiRequests, apiResponses, releasePreview };
}

const SIMULATED_WORKSPACE: Schemas["WorkspaceResponse"] = {
  workspace_id: "workspace-v",
  gateway_device_external_key: "gateway-v",
  business_project_id: "project-v",
  state: "OPEN",
  generation: 1,
  optimistic_version: 3,
  created_at: "2026-11-07T08:00:00Z",
  updated_at: "2026-11-07T09:00:00Z",
  current_upload_revision_id: null,
  current_preview_result_id: null,
  active_submission_id: null,
  active_submit_attempt_id: null,
};

async function openArchiveDialog(page: Page, submission: string) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "组态树", level: 1 })).toBeVisible();
  await page.getByRole("combobox", { name: "模拟身份" }).selectOption("archive-confirmer");
  await page.getByRole("button", { name: submission, exact: true }).click();
  await page.locator(".workspace-context-bar").getByRole("button", { name: "归档主线" }).click();
  const dialog = page.getByRole("dialog", { name: "归档主基线" });
  await expect(dialog.getByText("预检状态")).toBeVisible();
  return dialog;
}

test("V1 业务核验九类卡片与详情", async ({ page }) => {
  await installArchiveScenario(page);
  const dialog = await openArchiveDialog(page, "提交 1");
  await expect(dialog.locator("dt", { hasText: "当前基线" })).toBeVisible();
  await expect(dialog.getByText(/归档基线 1/)).toBeVisible();
  await expect(dialog.getByText("待处理项")).toBeVisible();
  await expect(dialog.locator(".archive-overview").getByText("未解释", { exact: true })).toBeVisible();
  await expect(dialog.getByText("缺少组态生成时间")).toBeVisible();
  await expect(dialog.getByText("生成时间中有无法识别的值")).toBeVisible();
  await expect(dialog.getByText("最后一个生成时间不是最大值")).toBeVisible();
  await expect(dialog.getByText("本次归档组态的生成时间早于对照")).toBeVisible();
  await expect(dialog.getByText("原始组态备份的生成时间早于当前基线")).toBeVisible();
  await expect(dialog.getByText("当前基线没有可用的生成时间，本轮无法比较时间先后")).toBeVisible();
  await expect(dialog.getByText("基线没有生成时间记录；比较结果：无法比较")).toBeVisible();
  await expect(dialog.getByText("2 个值无法识别")).toBeVisible();
  await expect(dialog.getByText("归档后该已通过的提交将被关闭（不归档）")).toBeVisible();
  await expect(dialog.getByText("选中的提交有项目身份例外")).toBeVisible();
  const lastNotMax = dialog.locator(".archive-anomaly", { hasText: "最后一个生成时间不是最大值" }).first();
  await cardScreenshot(page, "fe3c-last-not-max-card", 1280, lastNotMax);
  const regressed = dialog.locator(".archive-anomaly", { hasText: "本次归档组态的生成时间早于对照" }).first();
  await cardScreenshot(page, "fe3c-time-regression-card", 1280, regressed);
  // C6: the source detail tooltip carries the full raw digests, and the card
  // title carries the raw codes.
  const unexplained = dialog.locator(".archive-anomaly", { hasText: "原始组态备份的来源无法解释" }).first();
  const unexplainedDetail = unexplained.locator("p", { hasText: "与当前基线及本轮已通过的提交都对不上" });
  await expect(unexplainedDetail).toHaveAttribute("title", /sha256:v-content-s1-initial/);
  await expect(unexplainedDetail).toHaveAttribute("title", /sha256:v-content-s1-modified/);
  await expect(unexplainedDetail).toHaveAttribute("title", /issue_code=INITIAL_SOURCE_UNEXPLAINED/);
  await expect(unexplainedDetail).toHaveAttribute("title", /subject_digest=sha256:v-source/);
  await expect(unexplained.locator("strong").first()).toHaveAttribute("title", /subject_digest=sha256:v-source/);
  await dialog.locator(".dialog__body").evaluate((node) => { node.scrollTop = 0; });
  await screenshot(page, "fe3c-validation-overview", 1920);
});

test("C6 长理由折叠为三行并可展开", async ({ page }) => {
  const longReason = `${"长理由内容".repeat(30)}尾`;
  expect(longReason.length).toBeGreaterThan(120);
  await installArchiveScenario(page, { previews: [vPreviewAllKinds(), vPreviewAllKindsMissingAccepted(longReason)] });
  const dialog = await openArchiveDialog(page, "提交 1");
  await expandArchiveGroup(dialog, "生成时间");
  const card = () => dialog.locator(".archive-anomaly", { hasText: "缺少组态生成时间" }).first();
  await card().getByRole("button", { name: "接受" }).click();
  const accept = page.getByRole("dialog", { name: "接受异常" });
  await accept.getByLabel("接受理由").fill(longReason);
  await accept.getByRole("button", { name: "确认接受" }).click();
  await expandArchiveGroup(dialog, "生成时间");
  const accepted = card();
  await expect(accepted.getByText("已接受")).toBeVisible();
  // Long reasons are clamped to 3 lines with an expand toggle.
  const toggle = accepted.getByRole("button", { name: "展开" });
  await expect(toggle).toBeVisible();
  await expect(accepted.locator(".reason-text__body--clamped")).toHaveCount(1);
  await screenshot(page, "fe4a-c6-reason-collapsed", 1280);
  await toggle.click();
  await expect(accepted.getByRole("button", { name: "收起" })).toBeVisible();
  await expect(accepted.locator(".reason-text__body--clamped")).toHaveCount(0);
  await expect(accepted.getByText(longReason)).toBeVisible();
  await screenshot(page, "fe4a-c6-reason-expanded", 1280);
});

test("C6 多行长理由折叠为三行并可展开收起", async ({ page }) => {
  const longReason = "第一行\n第二行\n第三行\n第四行";
  await installArchiveScenario(page, { previews: [vPreviewAllKinds(), vPreviewAllKindsMissingAccepted(longReason)] });
  const dialog = await openArchiveDialog(page, "提交 1");
  await expandArchiveGroup(dialog, "生成时间");
  const card = () => dialog.locator(".archive-anomaly", { hasText: "缺少组态生成时间" }).first();
  await card().getByRole("button", { name: "接受" }).click();
  const accept = page.getByRole("dialog", { name: "接受异常" });
  await accept.getByLabel("接受理由").fill(longReason);
  await accept.getByRole("button", { name: "确认接受" }).click();
  await expandArchiveGroup(dialog, "生成时间");
  const accepted = card();
  await expect(accepted.getByText("已接受")).toBeVisible();
  await expect(accepted.locator(".reason-text__body--clamped")).toHaveCount(1);
  await accepted.getByRole("button", { name: "展开" }).click();
  await expect(accepted.locator(".reason-text__body--clamped")).toHaveCount(0);
  await expect(accepted.getByRole("button", { name: "收起" })).toBeVisible();
  await expect(accepted).toContainText("第四行");
  await accepted.getByRole("button", { name: "收起" }).click();
  await expect(accepted.locator(".reason-text__body--clamped")).toHaveCount(1);
  await expect(accepted.getByRole("button", { name: "展开" })).toBeVisible();
});

test("C6 三行以内理由不显示展开", async ({ page }) => {
  const shortReason = "第一行\n第二行\n第三行";
  await installArchiveScenario(page, { previews: [vPreviewAllKinds(), vPreviewAllKindsMissingAccepted(shortReason)] });
  const dialog = await openArchiveDialog(page, "提交 1");
  await expandArchiveGroup(dialog, "生成时间");
  const card = () => dialog.locator(".archive-anomaly", { hasText: "缺少组态生成时间" }).first();
  await card().getByRole("button", { name: "接受" }).click();
  const accept = page.getByRole("dialog", { name: "接受异常" });
  await accept.getByLabel("接受理由").fill(shortReason);
  await accept.getByRole("button", { name: "确认接受" }).click();
  await expandArchiveGroup(dialog, "生成时间");
  const accepted = card();
  await expect(accepted.getByText("已接受")).toBeVisible();
  await expect(accepted.getByRole("button", { name: "展开" })).toHaveCount(0);
  await expect(accepted).toContainText("第三行");
});

test("V1 未知编码没有接受入口且禁用确认归档", async ({ page }) => {
  await installArchiveScenario(page, { previews: [vPreviewUnknownCode()] });
  const dialog = await openArchiveDialog(page, "提交 1");
  await expect(dialog.getByText("FUTURE_CODE", { exact: true })).toBeVisible();
  await expect(dialog.getByText("当前版本不能处理该项，请刷新或联系管理员")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "接受", exact: true })).toBeHidden();
  const confirm = dialog.getByRole("button", { name: "确认归档" });
  await expect(confirm).toBeDisabled();
  await expect(dialog.getByText("存在当前版本不能处理的项")).toBeVisible();
  await screenshot(page, "fe3c-disabled-unknown-code", 1280);
});

test("V2 两侧独立项分别接受与撤销", async ({ page }) => {
  const { apiRequests } = await installArchiveScenario(page, {
    previews: [
      vPreviewTwoSided(),
      vPreviewTwoSidedInitialAccepted(),
      vPreviewTwoSidedBothAccepted(),
      vPreviewTwoSidedInitialRevoked(),
      vPreviewTwoSidedBothRevoked(),
    ],
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await expect(dialog.getByText("待处理项")).toBeVisible();
  await expandArchiveGroup(dialog, "生成时间");
  const initialCard = () => dialog.locator(".archive-anomaly", { hasText: "①原始组态备份" });
  const modifiedCard = () => dialog.locator(".archive-anomaly", { hasText: "②本次归档组态" });

  await initialCard().getByRole("button", { name: "接受" }).click();
  const acceptInitial = page.getByRole("dialog", { name: "接受异常" });
  await expect(acceptInitial.getByRole("button", { name: "确认接受" })).toBeDisabled();
  await screenshot(page, "fe3c-accept-dialog", 1920);
  await acceptInitial.getByLabel("接受理由").fill("① 已核对");
  await acceptInitial.getByRole("button", { name: "确认接受" }).click();
  await expandArchiveGroup(dialog, "生成时间");
  await expect(initialCard().getByText("已接受")).toBeVisible();
  await expect(modifiedCard().getByText("未处理")).toBeVisible();

  await modifiedCard().getByRole("button", { name: "接受" }).click();
  const acceptModified = page.getByRole("dialog", { name: "接受异常" });
  await acceptModified.getByLabel("接受理由").fill("② 已核对");
  await acceptModified.getByRole("button", { name: "确认接受" }).click();
  await expandArchiveGroup(dialog, "生成时间");
  await expect(initialCard().getByText("已接受")).toBeVisible();
  await expect(modifiedCard().getByText("已接受")).toBeVisible();
  const confirm = dialog.getByRole("button", { name: "确认归档" });
  await dialog.getByRole("checkbox", { name: /确认把/ }).check();
  await expect(confirm).toBeEnabled();
  await screenshot(page, "fe3c-twoside-accepted", 1280);

  await initialCard().getByRole("button", { name: "撤销接受" }).click();
  const revokeInitial = page.getByRole("dialog", { name: "撤销接受" });
  await revokeInitial.getByLabel("撤销理由").fill("① 撤销理由");
  await revokeInitial.getByRole("button", { name: "确认撤销" }).click();
  await expandArchiveGroup(dialog, "生成时间");
  await expect(initialCard().getByText("已撤销接受，需要重新处理")).toBeVisible();
  await expect(initialCard().getByText("已撤销，原因：① 撤销理由")).toBeVisible();
  await expect(confirm).toBeDisabled();
  await expect(dialog.getByText("还有 1 项异常未处理")).toBeVisible();
  await screenshot(page, "fe3c-disabled-unprocessed", 1280);

  await modifiedCard().getByRole("button", { name: "撤销接受" }).click();
  const revokeModified = page.getByRole("dialog", { name: "撤销接受" });
  await revokeModified.getByLabel("撤销理由").fill("② 撤销理由");
  await revokeModified.getByRole("button", { name: "确认撤销" }).click();
  await expandArchiveGroup(dialog, "生成时间");
  await expect(modifiedCard().getByText("已撤销接受，需要重新处理")).toBeVisible();
  await expect(dialog.getByText("还有 2 项异常未处理")).toBeVisible();

  const bodies = apiRequests
    .filter((request) => request.path === "/v1/archive-anomaly-resolutions")
    .map((request) => JSON.parse(request.body) as { subject_digest: string; expected_sequence: number; action: string; reason: string });
  expect(bodies.map((body) => [body.action, body.subject_digest, body.expected_sequence, body.reason])).toEqual([
    ["ACKNOWLEDGE_TIME_QUALITY", "sha256:v-twoside-initial", 0, "① 已核对"],
    ["ACKNOWLEDGE_TIME_QUALITY", "sha256:v-twoside-modified", 0, "② 已核对"],
    ["REVOKE", "sha256:v-twoside-initial", 4, "① 撤销理由"],
    ["REVOKE", "sha256:v-twoside-modified", 5, "② 撤销理由"],
  ]);
});

async function expandArchiveGroup(dialog: ReturnType<Page["getByRole"]>, title: string) {
  // C6: match the group by its full title plus the trailing count paren, so
  // "生成时间" never matches the "生成时间先后" group.
  const summary = dialog.locator("summary", { hasText: new RegExp(`^${title}（`) });
  const open = await summary.evaluate((node) => (node.parentElement as HTMLDetailsElement | null)?.open ?? false);
  if (!open) await summary.click();
}

test("V3 接受后原始诊断不变且无成功色", async ({ page }) => {
  await installArchiveScenario(page, { previews: [vPreviewAcceptedSource()] });
  const dialog = await openArchiveDialog(page, "提交 1");
  await expandArchiveGroup(dialog, "原始组态来源");
  const card = dialog.locator(".archive-anomaly", { hasText: "原始组态备份的来源无法解释" });
  await expect(card.getByText("来源未解释")).toBeVisible();
  await expect(card.getByText("已接受")).toBeVisible();
  const acceptedTag = card.locator(".status-tag").nth(1);
  await expect(acceptedTag).toHaveClass(/status-tag--neutral/);
  await expect(acceptedTag).not.toHaveClass(/success/);
  await expect(card.getByText("通过", { exact: true })).toBeHidden();
  await expect(card.getByText("已解决")).toBeHidden();
  await screenshot(page, "fe3c-source-accepted", 1920);
});

test("V4 撤销后回到未处理且禁用确认归档", async ({ page }) => {
  const { apiRequests } = await installArchiveScenario(page, {
    previews: [vPreviewAcceptedSource(), vPreviewAcceptedSourceRevoked()],
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await expandArchiveGroup(dialog, "原始组态来源");
  const card = dialog.locator(".archive-anomaly", { hasText: "原始组态备份的来源无法解释" });
  await card.getByRole("button", { name: "撤销接受" }).click();
  const revoke = page.getByRole("dialog", { name: "撤销接受" });
  await expect(revoke.getByRole("button", { name: "确认撤销" })).toBeDisabled();
  await revoke.getByLabel("撤销理由").fill("需要重新核对来源");
  await screenshot(page, "fe3c-revoke-dialog", 1920);
  await revoke.getByRole("button", { name: "确认撤销" }).click();
  await expandArchiveGroup(dialog, "原始组态来源");
  await expect(card.getByText("已撤销接受，需要重新处理")).toBeVisible();
  await expect(card.getByText("已撤销，原因：需要重新核对来源")).toBeVisible();
  const confirm = dialog.getByRole("button", { name: "确认归档" });
  await dialog.getByRole("checkbox", { name: /确认把/ }).check();
  await expect(confirm).toBeDisabled();
  await expect(dialog.getByText("还有 2 项异常未处理")).toBeVisible();
  const bodies = apiRequests
    .filter((request) => request.path === "/v1/archive-anomaly-resolutions")
    .map((request) => JSON.parse(request.body) as { subject_digest: string; expected_sequence: number; action: string });
  expect(bodies).toHaveLength(1);
  expect(bodies[0]).toMatchObject({
    subject_digest: "sha256:v-source",
    expected_sequence: 3,
    action: "REVOKE",
    reason: "需要重新核对来源",
  });
});

test("V5 审计冲突后提示并重新预检不重发", async ({ page }) => {
  const { apiRequests } = await installArchiveScenario(page, {
    previews: [vPreviewTwoSided(), vPreviewTwoSided()],
    resolutionConflict: "ARCHIVE_AUDIT_VERSION_CONFLICT",
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await dialog.locator(".archive-anomaly", { hasText: "①原始组态备份" }).getByRole("button", { name: "接受" }).click();
  const accept = page.getByRole("dialog", { name: "接受异常" });
  await accept.getByLabel("接受理由").fill("① 已核对");
  await accept.getByRole("button", { name: "确认接受" }).click();
  await expect(dialog.getByText("归档候选或核验结果已变化，已重新预检")).toBeVisible();
  const resolutionRequests = apiRequests.filter((request) => request.path === "/v1/archive-anomaly-resolutions");
  expect(resolutionRequests).toHaveLength(1);
});

test("V5 候选集合变化显示提示", async ({ page }) => {
  await installArchiveScenario(page, {
    candidatesList: [V_CANDIDATES, V_CANDIDATES_AFTER_CLOSE],
    previews: [vPreviewTwoSided(), vPreviewAfterClose()],
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await dialog.locator(".archive-anomaly", { hasText: "①原始组态备份" }).getByRole("button", { name: "接受" }).click();
  const accept = page.getByRole("dialog", { name: "接受异常" });
  await accept.getByLabel("接受理由").fill("① 已核对");
  await accept.getByRole("button", { name: "确认接受" }).click();
  await expect(dialog.getByText("候选集合已变化，之前的接受不再适用，请重新核对")).toBeVisible();
  await expect(dialog.getByText("原始组态备份的来源无法解释")).toBeVisible();
});

test("C8 关闭 409 后集合变化时两条提示都出现", async ({ page }) => {
  // C8: the 409 conflict notice and the candidate-set change notice render in
  // two places after a close 409 whose refresh sees a changed set.
  await installArchiveScenario(page, {
    candidatesList: [V_CANDIDATES, V_CANDIDATES_AFTER_CLOSE],
    previews: [vPreviewTwoSided(), vPreviewAfterClose()],
    closure: [{ status: 409, code: "BASELINE_VERSION_CONFLICT" }],
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await dialog.locator("section[aria-label='候选提交']").getByRole("button", { name: "关闭（不归档）" }).nth(1).click();
  const close = page.getByRole("dialog", { name: "关闭提交（不归档）" });
  await close.getByLabel("关闭理由").fill("集合变化场景");
  await close.getByRole("checkbox", { name: /我已了解关闭不可撤销/ }).check();
  await close.getByRole("button", { name: "确认关闭" }).click();
  // C8: the 409 conflict text and the generic set-change text render in two
  // separate banners.
  await expect(dialog.locator(".form-warning", { hasText: "提交或基线已变化，已重新预检" })).toBeVisible();
  await expect(dialog.locator(".form-error", { hasText: "候选集合已变化，之前的接受不再适用，请重新核对" })).toBeVisible();
  await screenshot(page, "fe4a-c8-both-notices", 1280);
});

test("C8 集合未变的成功接受后清除集合变化提示", async ({ page }) => {
  await installArchiveScenario(page, {
    candidatesList: [V_CANDIDATES, V_CANDIDATES_AFTER_CLOSE],
    previews: [vPreviewTwoSided(), vPreviewAfterClose(), vPreviewAfterClose()],
    closure: [{ status: 409, code: "BASELINE_VERSION_CONFLICT" }],
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await dialog.locator("section[aria-label='候选提交']").getByRole("button", { name: "关闭（不归档）" }).nth(1).click();
  const close = page.getByRole("dialog", { name: "关闭提交（不归档）" });
  await close.getByLabel("关闭理由").fill("集合变化场景");
  await close.getByRole("checkbox", { name: /我已了解关闭不可撤销/ }).check();
  await close.getByRole("button", { name: "确认关闭" }).click();
  await expect(dialog.locator(".form-error", { hasText: "候选集合已变化，之前的接受不再适用，请重新核对" })).toBeVisible();
  await dialog.locator(".archive-anomaly", { hasText: "①原始组态备份" }).first().getByRole("button", { name: "接受" }).click();
  const accept = page.getByRole("dialog", { name: "接受异常" });
  await accept.getByLabel("接受理由").fill("集合未变后重新核对");
  await accept.getByRole("button", { name: "确认接受" }).click();
  await expect(dialog.locator(".form-error", { hasText: "候选集合已变化，之前的接受不再适用，请重新核对" })).toHaveCount(0);
  await expect(dialog.locator(".form-warning", { hasText: "提交或基线已变化，已重新预检" })).toHaveCount(0);
});

test("C8 集合未变时后续加载不显示旧的冲突提示", async ({ page }) => {
  // C8: after a close 409 with an unchanged set only the conflict notice
  // shows; an ordinary reload afterwards clears the stale conflict notice.
  await installArchiveScenario(page, {
    previews: [vPreviewTwoSided(), vPreviewTwoSided(), vPreviewTwoSided()],
    closure: [{ status: 409, code: "BASELINE_VERSION_CONFLICT" }],
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await dialog.locator("section[aria-label='候选提交']").getByRole("button", { name: "关闭（不归档）" }).first().click();
  const close = page.getByRole("dialog", { name: "关闭提交（不归档）" });
  await close.getByLabel("关闭理由").fill("集合未变场景");
  await close.getByRole("checkbox", { name: /我已了解关闭不可撤销/ }).check();
  await close.getByRole("button", { name: "确认关闭" }).click();
  await expect(dialog.locator(".form-warning", { hasText: "提交或基线已变化，已重新预检" })).toBeVisible();
  await expect(dialog.locator(".form-error", { hasText: "提交或基线已变化，已重新预检" })).toHaveCount(0);
  await dialog.locator("footer").getByRole("button", { name: "重新预检" }).click();
  await expect(dialog.getByText("待处理项")).toBeVisible();
  await expect(dialog.locator(".form-warning", { hasText: "提交或基线已变化，已重新预检" })).toHaveCount(0);
});

test("C8 加载失败后不保留待处理的冲突提示", async ({ page }) => {
  const scenario: Parameters<typeof installArchiveScenario>[1] = {
    previews: [vPreviewTwoSided(), vPreviewTwoSided()],
    closure: [{ status: 409, code: "BASELINE_VERSION_CONFLICT" }],
  };
  await installArchiveScenario(page, scenario);
  const dialog = await openArchiveDialog(page, "提交 1");
  await dialog.locator("section[aria-label='候选提交']").getByRole("button", { name: "关闭（不归档）" }).first().click();
  const close = page.getByRole("dialog", { name: "关闭提交（不归档）" });
  await close.getByLabel("关闭理由").fill("加载失败场景");
  await close.getByRole("checkbox", { name: /我已了解关闭不可撤销/ }).check();
  await close.getByRole("button", { name: "确认关闭" }).click();
  await expect(dialog.locator(".form-warning", { hasText: "提交或基线已变化，已重新预检" })).toBeVisible();
  scenario.previewForbidden = true;
  await dialog.locator("footer").getByRole("button", { name: "重新预检" }).click();
  await expect(dialog.getByText("当前身份没有预检归档方案的权限")).toBeVisible();
  scenario.previewForbidden = false;
  await dialog.locator("footer").getByRole("button", { name: "重新预检" }).click();
  await expect(dialog.getByText("待处理项")).toBeVisible();
  await expect(dialog.locator(".form-warning", { hasText: "提交或基线已变化，已重新预检" })).toHaveCount(0);
});

test("V6 全部引用进入开始归档请求", async ({ page }) => {
  const { apiRequests } = await installArchiveScenario(page, {
    candidates: vCandidates200(),
    history: vManyHistoryPage(),
    previews: [vPreview399Accepted()],
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await expect(dialog.getByText("待处理项")).toBeVisible();
  await dialog.getByRole("checkbox", { name: /确认把/ }).check();
  await dialog.getByRole("button", { name: "确认归档" }).click();
  await expect(dialog.getByText("归档完成")).toBeVisible({ timeout: 30000 });
  const starts = apiRequests.filter((request) => request.path === "/v1/archives" && request.method === "POST");
  expect(starts).toHaveLength(1);
  const body = JSON.parse(starts[0]!.body) as { anomaly_resolution_refs: unknown[]; confirmation_refs: unknown[] };
  expect(body.anomaly_resolution_refs).toHaveLength(399);
  expect(body.confirmation_refs).toHaveLength(1);
  for (const request of apiRequests) {
    if (!request.path.startsWith("/v1/archive") || request.method !== "POST") continue;
    const parsed = JSON.parse(request.body) as { selected?: Record<string, unknown> };
    expect(Object.keys(parsed.selected ?? {}).sort(), request.path).toEqual(["expected_candidate_digest", "submission_id"]);
  }
  await screenshot(page, "fe3c-many-first", 1920);
});

test("V7 阻断项只有文字与重新预检", async ({ page }) => {
  await installArchiveScenario(page, { previews: [vPreviewBlocked("ARCHIVE_INTEGRITY_FAILURE")] });
  const dialog = await openArchiveDialog(page, "提交 1");
  await expect(dialog.getByText("归档被阻止")).toBeVisible();
  await expect(dialog.getByText("归档数据完整性校验未通过，不能继续，请联系管理员")).toBeVisible();
  await expect(dialog.locator(".archive-blockers code").getByText("ARCHIVE_INTEGRITY_FAILURE", { exact: true })).toBeVisible();
  await expect(dialog.getByText("当前预检存在阻断项")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "接受", exact: true })).toBeHidden();
  await expect(dialog.getByRole("button", { name: "确认归档" })).toBeDisabled();
  await screenshot(page, "fe3c-blocker-no-entry", 1920);
  await page.unrouteAll({ behavior: "wait" });
  await installArchiveScenario(page, { previews: [vPreviewBlocked("ACTIVE_SUBMIT_ATTEMPT")] });
  await page.goto("/");
  const reloaded = await openArchiveDialog(page, "提交 1");
  await expect(reloaded.getByText("已有提交正在处理，完成后才能归档")).toBeVisible();
  await expect(reloaded.locator(".archive-blockers code").getByText("ACTIVE_SUBMIT_ATTEMPT", { exact: true })).toBeVisible();
  await expect(reloaded.getByRole("button", { name: "确认归档" })).toBeDisabled();
});

test("V8 待审核阻塞列出全部并可定位", async ({ page }) => {
  const { apiResponses } = await installArchiveScenario(page, {
    candidates: V_PENDING_CANDIDATES,
    previews: [vPreviewPending(), vPreviewPendingStartable()],
    startConflict: "ARCHIVE_PENDING_REVIEW",
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await expect(dialog.getByText(/有 2 个待审核的提交/)).toBeVisible();
  await expect(dialog.getByText("只有上传或预览、尚未提交的工作区不影响归档。")).toBeVisible();
  await screenshot(page, "fe3c-pending-blocked", 1920);
  const pendingLink = dialog.getByRole("button", { name: "提交 2" });
  await expect(pendingLink).toBeVisible();
  await pendingLink.click();
  await expect(dialog).toBeHidden();
  const selectedRow = page.locator('table[aria-label="History 组态树"] tr.is-selected');
  await expect(selectedRow).toContainText("提交 2");

  const reopened = await openArchiveDialog(page, "提交 1");
  await reopened.getByRole("checkbox", { name: /确认把/ }).check();
  await reopened.getByRole("button", { name: "确认归档" }).click();
  await expect(reopened.getByText("出现了新的待审核提交，请重新预检")).toBeVisible();
  await expect(reopened.getByText("ARCHIVE_PENDING_REVIEW", { exact: true })).toBeVisible();
  const startResponses = apiResponses.filter((response) => response.path === "/v1/archives");
  expect(startResponses).toHaveLength(1);
  expect(startResponses[0]?.status).toBe(409);
});

test("V9 关闭中断后同 key 重试并显示首次关闭人", async ({ page }) => {
  const { apiRequests, apiResponses } = await installArchiveScenario(page, {
    previews: [vPreviewAllKinds()],
    closureAbortOnce: true,
    closure: [{ status: 200 }],
  });
  let reviewGets = 0;
  page.on("request", (request) => {
    if (request.method() === "GET" && /\/v1\/submissions\/[^/]+\/review$/.test(new URL(request.url()).pathname)) reviewGets += 1;
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await dialog.locator("section[aria-label='候选提交']").getByRole("button", { name: "关闭（不归档）" }).nth(1).click();
  const close = page.getByRole("dialog", { name: "关闭提交（不归档）" });
  // C9: the body uses the display name directly without duplicating it.
  await expect(close.getByText(/关闭提交 \d+（不归档）。/)).toBeVisible();
  await expect(close.getByText("关闭提交提交")).toHaveCount(0);
  await expect(close.getByRole("button", { name: "确认关闭" })).toBeDisabled();
  await close.getByLabel("关闭理由").fill("该提交的业务口径已变化");
  await expect(close.getByRole("button", { name: "确认关闭" })).toBeDisabled();
  await screenshot(page, "fe3c-close-dialog", 1920);
  await close.getByRole("checkbox", { name: /我已了解关闭不可撤销/ }).check();
  await close.getByRole("button", { name: "确认关闭" }).click();
  await expect(close.getByText("关闭请求未能送达，可以重试")).toBeVisible();
  await close.getByRole("button", { name: "重试" }).click();
  const result = close.locator('[aria-label="关闭结果"]');
  await expect(result).toBeVisible();
  await expect(result).toContainText("已关闭");
  await expect(result).toContainText("关闭人：reviewer");
  await expect(result).toContainText("关闭时间：2026-11-03 10:00:00 UTC");
  await expect(result).toContainText("理由：不再需要该提交");
  // C9: after success only the single close button remains; no cancel, no
  // disabled danger button, and no duplicated disabled reason.
  await expect(close.getByRole("button", { name: "关闭", exact: true })).toBeEnabled();
  await expect(close.getByRole("button", { name: "取消" })).toHaveCount(0);
  await expect(close.getByRole("button", { name: "已关闭" })).toHaveCount(0);
  await expect(close.getByRole("button", { name: "确认关闭" })).toHaveCount(0);
  await expect(close.getByText("已关闭", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("combobox", { name: "模拟身份" })).toHaveValue("archive-confirmer");
  const closureRequests = apiRequests.filter((request) => request.path.endsWith("/closure"));
  expect(closureRequests).toHaveLength(2);
  expect(closureRequests[0]?.idempotencyKey).toBeTruthy();
  expect(closureRequests[1]?.idempotencyKey).toBe(closureRequests[0]?.idempotencyKey);
  expect(closureRequests[1]?.body).toBe(closureRequests[0]?.body);
  const closureResponses = apiResponses.filter((response) => response.path.endsWith("/closure"));
  expect(closureResponses.map((response) => response.status)).toEqual([200]);
  expect(reviewGets).toBe(0);
});

test("V9 版本冲突后重新打开取新加载的审核版本", async ({ page }) => {
  const refreshed = {
    ...V_CANDIDATES_AFTER_CLOSE,
    candidates: V_CANDIDATES_AFTER_CLOSE.candidates.map((candidate) => candidate.submission_id === "v-s2" ? { ...candidate, review_version: 22 } : candidate),
  };
  const { apiRequests } = await installArchiveScenario(page, {
    candidatesList: [V_CANDIDATES, refreshed],
    previews: [vPreviewAllKinds(), vPreviewAfterClose()],
    closure: [{ status: 409, code: "REVIEW_VERSION_CONFLICT" }, { status: 200 }],
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await dialog.locator("section[aria-label='候选提交']").getByRole("button", { name: "关闭（不归档）" }).nth(1).click();
  const close = page.getByRole("dialog", { name: "关闭提交（不归档）" });
  await close.getByLabel("关闭理由").fill("版本冲突场景");
  await close.getByRole("checkbox", { name: /我已了解关闭不可撤销/ }).check();
  await close.getByRole("button", { name: "确认关闭" }).click();
  await expect(dialog.getByText("提交或基线已变化，已重新预检")).toBeVisible();
  await dialog.locator("section[aria-label='候选提交']").getByRole("button", { name: "关闭（不归档）" }).nth(1).click();
  const reopened = page.getByRole("dialog", { name: "关闭提交（不归档）" });
  await reopened.getByLabel("关闭理由").fill("版本冲突后重开");
  await reopened.getByRole("checkbox", { name: /我已了解关闭不可撤销/ }).check();
  await reopened.getByRole("button", { name: "确认关闭" }).click();
  const requests = apiRequests.filter((request) => request.path.endsWith("/closure"));
  expect(requests).toHaveLength(2);
  expect((JSON.parse(requests[0]!.body) as { expected_review_version: number }).expected_review_version).toBe(12);
  expect((JSON.parse(requests[1]!.body) as { expected_review_version: number }).expected_review_version).toBe(22);
});

test("V9 关闭 404 与 422 显示 kickoff 文案", async ({ page }) => {
  await installArchiveScenario(page, {
    previews: [vPreviewAllKinds()],
    closure: [
      { status: 404, code: "RESOURCE_NOT_FOUND" },
      { status: 422, code: "REQUEST_VALIDATION_FAILED" },
    ],
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await dialog.locator("section[aria-label='候选提交']").getByRole("button", { name: "关闭（不归档）" }).first().click();
  const close = page.getByRole("dialog", { name: "关闭提交（不归档）" });
  await close.getByLabel("关闭理由").fill("404 场景");
  await close.getByRole("checkbox", { name: /我已了解关闭不可撤销/ }).check();
  await close.getByRole("button", { name: "确认关闭" }).click();
  await expect(close.getByText("未找到该提交，请重新预检")).toBeVisible();
  await expect(close.getByText("RESOURCE_NOT_FOUND", { exact: true })).toBeVisible();
  await close.getByRole("button", { name: "确认关闭" }).click();
  await expect(close.getByText("理由或请求不符合要求")).toBeVisible();
  await expect(close.getByText("REQUEST_VALIDATION_FAILED", { exact: true })).toBeVisible();
});

test("V9 关闭 403 与 413 显示关闭未完成", async ({ page }) => {
  await installArchiveScenario(page, {
    previews: [vPreviewAllKinds()],
    closure: [{ status: 403, code: "SCOPE_FORBIDDEN" }, { status: 413, code: "REQUEST_TOO_LARGE" }],
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await dialog.locator("section[aria-label='候选提交']").getByRole("button", { name: "关闭（不归档）" }).first().click();
  const close = page.getByRole("dialog", { name: "关闭提交（不归档）" });
  await close.getByLabel("关闭理由").fill("权限场景");
  await close.getByRole("checkbox", { name: /我已了解关闭不可撤销/ }).check();
  await close.getByRole("button", { name: "确认关闭" }).click();
  await expect(close.getByText("当前身份没有该操作的权限")).toBeVisible();
  await close.getByRole("button", { name: "确认关闭" }).click();
  await expect(close.getByText("关闭未完成")).toBeVisible();
  await expect(close.getByText("REQUEST_TOO_LARGE", { exact: true })).toBeVisible();
});

test("V9 关闭理由 4096 可用且 4097 禁用", async ({ page }) => {
  await installArchiveScenario(page, { previews: [vPreviewAllKinds()] });
  const dialog = await openArchiveDialog(page, "提交 1");
  await dialog.locator("section[aria-label='候选提交']").getByRole("button", { name: "关闭（不归档）" }).first().click();
  const close = page.getByRole("dialog", { name: "关闭提交（不归档）" });
  const boundary = "多".repeat(1365) + "x";
  await close.getByLabel("关闭理由").fill(boundary);
  await close.getByRole("checkbox", { name: /我已了解关闭不可撤销/ }).check();
  await expect(close.getByText("已输入 4096 字节")).toBeVisible();
  await expect(close.getByRole("button", { name: "确认关闭" })).toBeEnabled();
  await close.getByLabel("关闭理由").fill(`${boundary}x`);
  await expect(close.getByRole("button", { name: "确认关闭" })).toBeDisabled();
  await expect(close.getByText("理由不能超过 4096 字节").first()).toBeVisible();
});

test("V10 关闭后自动重新预检且全部回到未处理", async ({ page }) => {
  await installArchiveScenario(page, {
    candidatesList: [V_CANDIDATES, V_CANDIDATES_AFTER_CLOSE],
    previews: [vPreviewTwoSided(), vPreviewAfterClose()],
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await dialog.locator("section[aria-label='候选提交']").getByRole("button", { name: "关闭（不归档）" }).nth(1).click();
  const close = page.getByRole("dialog", { name: "关闭提交（不归档）" });
  await close.getByLabel("关闭理由").fill("v-s2 的口径已变化，先关闭");
  await close.getByRole("checkbox", { name: /我已了解关闭不可撤销/ }).check();
  await close.getByRole("button", { name: "确认关闭" }).click();
  const result = close.locator('[aria-label="关闭结果"]');
  await expect(result).toBeVisible();
  await expect(result).toContainText("已关闭");
  await screenshot(page, "fe3c-close-result", 1920);
  await close.getByRole("button", { name: "取消" }).click();
  await expect(dialog.getByText("原始组态备份的来源无法解释")).toBeVisible();
  await expect(dialog.getByText("候选集合已变化，之前的接受不再适用，请重新核对")).toBeVisible();
  const cards = dialog.locator(".archive-anomaly");
  expect(await cards.count()).toBe(3);
  for (let index = 0; index < 3; index += 1) {
    const text = await cards.nth(index).textContent();
    expect(text).toContain("未处理");
    expect(text).not.toContain("已接受");
  }
});

test("V13 开始归档被拒后提示并可重新预检", async ({ page }) => {
  await installArchiveScenario(page, {
    previews: [vPreviewTwoSidedAccepted()],
    startConflict: "ARCHIVE_ANOMALY_UNRESOLVED",
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await dialog.getByRole("checkbox", { name: /确认把/ }).check();
  await dialog.getByRole("button", { name: "确认归档" }).click();
  await expect(dialog.getByText("归档候选或核验结果已变化，请重新预检")).toBeVisible();
  await expect(dialog.getByText("ARCHIVE_ANOMALY_UNRESOLVED", { exact: true })).toBeVisible();
  await screenshot(page, "fe3c-start-rejected", 1920);
  await dialog.locator("footer").getByRole("button", { name: "重新预检" }).click();
  await expect(dialog.getByText("预检状态")).toBeVisible();
});

test("V13 归档范围超限提示", async ({ page }) => {
  await installArchiveScenario(page, {
    previews: [vPreviewTwoSidedAccepted()],
    startConflict: "ARCHIVE_SCOPE_LIMIT_EXCEEDED",
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await dialog.getByRole("checkbox", { name: /确认把/ }).check();
  await dialog.getByRole("button", { name: "确认归档" }).click();
  await expect(dialog.getByText("候选提交超过归档上限，需要管理员处理")).toBeVisible();
  await expect(dialog.getByText("ARCHIVE_SCOPE_LIMIT_EXCEEDED", { exact: true })).toBeVisible();
});

test("B4 候选读取与预检不一致时重读候选与预检一次", async ({ page }) => {
  const { apiRequests } = await installArchiveScenario(page, {
    candidatesList: [V_CANDIDATES, V_CANDIDATES_RECHANGED],
    previews: [vPreviewAfterClose(), vPreviewRechanged()],
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await expect(dialog.getByText("待处理项")).toBeVisible();
  await expect(dialog.getByText("归档候选集合已变化，请重新预检")).toBeHidden();
  expect(apiRequests.filter((request) => request.path === "/v1/archive-candidates")).toHaveLength(2);
  const previews = apiRequests.filter((request) => request.path === "/v1/archive-plan-preview");
  expect(previews).toHaveLength(2);
  const second = JSON.parse(previews[1]!.body) as { selected: { expected_candidate_digest: string } };
  expect(second.selected.expected_candidate_digest).toBe("sha256:v-candidate-v-s1-refreshed");
});

test("V14 全部归档请求的选择引用恰好两个键", async ({ page }) => {
  const { apiRequests } = await installArchiveScenario(page, {
    previews: [vPreviewAcceptedSource(), vPreviewAcceptedSource(), vPreviewAcceptedSource()],
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await dialog.locator(".archive-anomaly", { hasText: "缺少组态生成时间" }).getByRole("button", { name: "接受" }).click();
  const accept = page.getByRole("dialog", { name: "接受异常" });
  await accept.getByLabel("接受理由").fill("② 已核对");
  await accept.getByRole("button", { name: "确认接受" }).click();
  await expandArchiveGroup(dialog, "原始组态来源");
  await dialog.locator(".archive-anomaly", { hasText: "原始组态备份的来源无法解释" }).getByRole("button", { name: "撤销接受" }).click();
  const revoke = page.getByRole("dialog", { name: "撤销接受" });
  await revoke.getByLabel("撤销理由").fill("重新核对");
  await revoke.getByRole("button", { name: "确认撤销" }).click();
  await dialog.getByRole("checkbox", { name: /确认把/ }).check();
  const checkedCount = await dialog.locator(".archive-anomaly", { hasText: "缺少组态生成时间" }).count();
  expect(checkedCount).toBeGreaterThan(0);
  for (const request of apiRequests) {
    if (!request.path.startsWith("/v1/archive") || request.method !== "POST") continue;
    if (request.path === "/v1/archive-audit-events") continue;
    const parsed = JSON.parse(request.body) as { selected?: Record<string, unknown> };
    expect(Object.keys(parsed.selected ?? {}).sort(), request.path).toEqual(["expected_candidate_digest", "submission_id"]);
    expect(parsed.selected?.submission_id, request.path).toBe("v-s1");
  }
  expect(apiRequests.some((request) => request.path === "/v1/archive-plan-preview")).toBe(true);
  expect(apiRequests.some((request) => request.path === "/v1/archive-anomaly-resolutions")).toBe(true);
});

test("B7 确认归档禁用原因截图", async ({ page }) => {
  const { releasePreview } = await installArchiveScenario(page, { previews: [vPreviewTwoSidedAccepted()], holdPreview: true });
  await page.goto("/");
  await page.getByRole("combobox", { name: "模拟身份" }).selectOption("archive-confirmer");
  await page.getByRole("button", { name: "提交 1", exact: true }).click();
  await page.locator(".workspace-context-bar").getByRole("button", { name: "归档主线" }).click();
  const loading = page.getByRole("dialog", { name: "归档主基线" });
  await expect(loading.getByText("正在预检").first()).toBeVisible();
  await screenshot(page, "fe3c-confirm-disabled-loading", 1280);

  releasePreview();
  await expect(loading.getByText("预检状态")).toBeVisible();
  await page.unrouteAll({ behavior: "wait" });
  await installArchiveScenario(page, { previews: [vPreviewBlocked("ARCHIVE_INTEGRITY_FAILURE")] });
  const blocked = await openArchiveDialog(page, "提交 1");
  await expect(blocked.getByText("当前预检存在阻断项")).toBeVisible();
  await screenshot(page, "fe3c-confirm-disabled-blocked", 1280);

  await page.unrouteAll({ behavior: "wait" });
  await installArchiveScenario(page, { previews: [vPreviewTwoSided()] });
  const unprocessed = await openArchiveDialog(page, "提交 1");
  await unprocessed.getByRole("checkbox", { name: /确认把/ }).check();
  await expect(unprocessed.getByText("还有 2 项异常未处理")).toBeVisible();
  await screenshot(page, "fe3c-confirm-disabled-unprocessed", 1280);

  await page.unrouteAll({ behavior: "wait" });
  await installArchiveScenario(page, { previews: [vPreviewUnknownCode()] });
  const unknown = await openArchiveDialog(page, "提交 1");
  await expect(unknown.getByText("存在当前版本不能处理的项")).toBeVisible();
  await screenshot(page, "fe3c-confirm-disabled-unknown", 1280);

  await page.unrouteAll({ behavior: "wait" });
  await installArchiveScenario(page, { previews: [vPreviewTwoSidedAccepted()] });
  const unchecked = await openArchiveDialog(page, "提交 1");
  await expect(unchecked.getByText("请确认归档选择")).toBeVisible();
  await screenshot(page, "fe3c-confirm-disabled-unchecked", 1280);
});
