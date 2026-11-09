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
  vPreviewBlocked,
  vReviewFacts,
} from "../src/features/dev/simulated-api";
import {
  vCandidates200,
  vManyHistoryPage,
  vPreview399Accepted,
  vPreviewAcceptedSource,
  vPreviewPending,
  vPreviewTwoSided,
  vPreviewTwoSidedAccepted,
  vPreviewTwoSidedInitialAccepted,
  vPreviewUnknownCode,
  V_CANDIDATES_AFTER_CLOSE,
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
    await page.screenshot({ path: join(screenshotDirectory, String(current), `${name}.png`), fullPage: false });
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
}

function errorBody(route: string, status: number, code: string, method = "POST"): { code: string; message: string } {
  const found = SIMULATED_ERROR_RESPONSES.find((item) => item.route === route && item.method === method && item.status === status && item.body.code === code);
  if (!found) throw new Error(`simulated error missing: ${method} ${route} ${status} ${code}`);
  return found.body;
}

async function installArchiveScenario(page: Page, scenario: ArchiveScenario = {}) {
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
  const closureScript = scenario.closure ?? "created-then-replay";
  await page.route("**/v1/submissions/*/closure", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
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
  return { apiRequests, apiResponses };
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
  await expect(dialog.getByText("当前基线没有可用的生成时间")).toBeVisible();
  await expect(dialog.getByText("归档后该已通过的提交将被关闭（不归档）")).toBeVisible();
  await expect(dialog.getByText("选中的提交有项目身份例外")).toBeVisible();
  await screenshot(page, "fe3c-validation-overview", 1920);
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
});

test("V2 两侧独立项分别接受与撤销", async ({ page }) => {
  const { apiRequests } = await installArchiveScenario(page, {
    previews: [vPreviewTwoSided(), vPreviewTwoSidedInitialAccepted()],
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await expect(dialog.getByText("待处理项")).toBeVisible();
  const initialCard = dialog.locator(".archive-anomaly", { hasText: "①原始组态备份" });
  const modifiedCard = dialog.locator(".archive-anomaly", { hasText: "②本次归档组态" });
  await initialCard.getByRole("button", { name: "接受" }).click();
  const accept = page.getByRole("dialog", { name: "接受异常" });
  await expect(accept.getByRole("button", { name: "确认接受" })).toBeDisabled();
  await screenshot(page, "fe3c-accept-dialog", 1920);
  await accept.getByLabel("接受理由").fill("① 已核对");
  await accept.getByRole("button", { name: "确认接受" }).click();
  await expect(dialog.getByText("已接受")).toBeVisible();
  await expect(modifiedCard.getByText("未处理")).toBeVisible();
  const confirm = dialog.getByRole("button", { name: "确认归档" });
  await expect(confirm).toBeDisabled();
  await screenshot(page, "fe3c-twoside", 1920);
  const resolutionBodies = apiRequests.filter((request) => request.path === "/v1/archive-anomaly-resolutions").map((request) => JSON.parse(request.body) as { subject_digest: string; expected_sequence: number });
  expect(resolutionBodies).toHaveLength(1);
  expect(resolutionBodies[0]?.subject_digest).toBe("sha256:v-twoside-initial");
  expect(resolutionBodies[0]?.expected_sequence).toBe(0);
});

async function expandArchiveGroup(dialog: ReturnType<Page["getByRole"]>, title: string) {
  const summary = dialog.locator("summary", { hasText: title });
  if (await summary.getAttribute("aria-expanded").catch(() => null) === null) {
    await summary.click();
  } else {
    const open = await summary.evaluate((node) => (node.parentElement as HTMLDetailsElement | null)?.open ?? true);
    if (!open) await summary.click();
  }
}

test("V3 接受后原始诊断不变且无成功色", async ({ page }) => {
  await installArchiveScenario(page, { previews: [vPreviewAcceptedSource()] });
  const dialog = await openArchiveDialog(page, "提交 1");
  await expandArchiveGroup(dialog, "原始组态来源");
  const card = dialog.locator(".archive-anomaly", { hasText: "原始组态备份的来源无法解释" });
  await expect(card.getByText("来源未解释")).toBeVisible();
  await expect(card.getByText("已接受")).toBeVisible();
  await expect(card.getByText("通过", { exact: true })).toBeHidden();
  await expect(card.getByText("已解决")).toBeHidden();
  await screenshot(page, "fe3c-source-accepted", 1920);
});

test("V4 撤销后回到未处理且禁用确认归档", async ({ page }) => {
  await installArchiveScenario(page, { previews: [vPreviewAcceptedSource(), vPreviewAcceptedSource()] });
  const dialog = await openArchiveDialog(page, "提交 1");
  await expandArchiveGroup(dialog, "原始组态来源");
  const card = dialog.locator(".archive-anomaly", { hasText: "原始组态备份的来源无法解释" });
  await card.getByRole("button", { name: "撤销接受" }).click();
  const revoke = page.getByRole("dialog", { name: "撤销接受" });
  await expect(revoke.getByRole("button", { name: "确认撤销" })).toBeDisabled();
  await revoke.getByLabel("撤销理由").fill("需要重新核对来源");
  await screenshot(page, "fe3c-revoke-dialog", 1920);
  await revoke.getByRole("button", { name: "确认撤销" }).click();
  await expect(dialog.getByRole("button", { name: "确认归档" })).toBeDisabled();
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
  await expect(dialog.getByText("ARCHIVE_INTEGRITY_FAILURE", { exact: true })).toBeVisible();
  await expect(dialog.getByText("当前预检存在阻断项")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "接受", exact: true })).toBeHidden();
  await expect(dialog.getByRole("button", { name: "确认归档" })).toBeDisabled();
  await screenshot(page, "fe3c-blocker-no-entry", 1920);
  await page.unrouteAll();
  await installArchiveScenario(page, { previews: [vPreviewBlocked("ACTIVE_SUBMIT_ATTEMPT")] });
  await page.goto("/");
  const reloaded = await openArchiveDialog(page, "提交 1");
  await expect(reloaded.getByText("ACTIVE_SUBMIT_ATTEMPT", { exact: true }).first()).toBeVisible();
  await expect(reloaded.getByRole("button", { name: "确认归档" })).toBeDisabled();
});

test("V8 待审核阻塞列出全部并可定位", async ({ page }) => {
  const { apiRequests } = await installArchiveScenario(page, {
    candidates: V_PENDING_CANDIDATES,
    previews: [vPreviewPending()],
    startConflict: "ARCHIVE_PENDING_REVIEW",
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await expect(dialog.getByText(/有 2 个待审核的提交/)).toBeVisible();
  await expect(dialog.getByText("只有上传或预览、尚未提交的工作区不影响归档。")).toBeVisible();
  await screenshot(page, "fe3c-pending-blocked", 1920);
  const pendingLink = dialog.getByRole("button", { name: "提交 2" });
  await expect(pendingLink).toBeVisible();
  await dialog.locator("section[aria-label='候选提交']").getByRole("button", { name: "关闭（不归档）" }).first().click();
  const close = page.getByRole("dialog", { name: "关闭提交（不归档）" });
  await close.getByLabel("关闭理由").fill("V8 不关闭，只验证入口存在");
  await close.getByRole("button", { name: "取消" }).click();
  await pendingLink.click();
  await expect(dialog).toBeHidden();
  expect(apiRequests.some((request) => request.path === "/v1/archives")).toBe(false);
});

test("V9 关闭携带同次候选的审核版本且回放显示首次关闭人", async ({ page }) => {
  const { apiRequests } = await installArchiveScenario(page);
  const dialog = await openArchiveDialog(page, "提交 1");
  await dialog.locator("section[aria-label='候选提交']").getByRole("button", { name: "关闭（不归档）" }).nth(1).click();
  const close = page.getByRole("dialog", { name: "关闭提交（不归档）" });
  await expect(close.getByRole("button", { name: "确认关闭" })).toBeDisabled();
  await close.getByLabel("关闭理由").fill("该提交的业务口径已变化");
  await expect(close.getByRole("button", { name: "确认关闭" })).toBeDisabled();
  await screenshot(page, "fe3c-close-dialog", 1920);
  await close.getByRole("checkbox", { name: /我已了解关闭不可撤销/ }).check();
  await close.getByRole("button", { name: "确认关闭" }).click();
  await expect(close.getByText("已关闭")).toBeVisible();
  await expect(close.getByText(/关闭人：reviewer/)).toBeVisible();
  await expect(close.getByText(/理由：不再需要该提交/)).toBeVisible();
  const closureRequests = apiRequests.filter((request) => request.path.endsWith("/closure"));
  expect(closureRequests).toHaveLength(1);
  const closureBody = JSON.parse(closureRequests[0]!.body) as { expected_review_version: number; reason: string };
  expect(closureBody.expected_review_version).toBe(12);
  expect(closureBody.reason).toBe("该提交的业务口径已变化");
  expect(closureRequests[0]?.idempotencyKey).toBeTruthy();
});

test("V9 关闭理由字节边界与409提示", async ({ page }) => {
  await installArchiveScenario(page, {
    closure: [
      { status: 409, code: "REVIEW_VERSION_CONFLICT" },
      { status: 403, code: "SCOPE_FORBIDDEN" },
      { status: 404, code: "RESOURCE_NOT_FOUND" },
      { status: 422, code: "REQUEST_VALIDATION_FAILED" },
    ],
  });
  const dialog = await openArchiveDialog(page, "提交 1");
  await dialog.locator("section[aria-label='候选提交']").getByRole("button", { name: "关闭（不归档）" }).first().click();
  const close = page.getByRole("dialog", { name: "关闭提交（不归档）" });
  await close.getByLabel("关闭理由").fill("x".repeat(4097));
  await close.getByRole("checkbox", { name: /我已了解关闭不可撤销/ }).check();
  await expect(close.getByRole("button", { name: "确认关闭" })).toBeDisabled();
  await expect(close.getByRole("alert").getByText("理由不能超过 4096 字节")).toBeVisible();
  await close.getByLabel("关闭理由").fill("多字节".repeat(400));
  await expect(close.getByText("已输入 3600 字节")).toBeVisible();
  await close.getByRole("button", { name: "确认关闭" }).click();
  await expect(close).toBeHidden();
  await expect(dialog.getByText("提交或基线已变化，已重新预检")).toBeVisible();
  await page.unrouteAll();
  await installArchiveScenario(page, { closure: [{ status: 403, code: "SCOPE_FORBIDDEN" }] });
  const reopened = await openArchiveDialog(page, "提交 1");
  await reopened.locator("section[aria-label='候选提交']").getByRole("button", { name: "关闭（不归档）" }).first().click();
  const close2 = page.getByRole("dialog", { name: "关闭提交（不归档）" });
  await close2.getByLabel("关闭理由").fill("重试关闭");
  await close2.getByRole("checkbox", { name: /我已了解关闭不可撤销/ }).check();
  await close2.getByRole("button", { name: "确认关闭" }).click();
  await expect(close2.getByText("当前身份没有该操作的权限")).toBeVisible();
  await expect(close2.getByText("SCOPE_FORBIDDEN")).toBeVisible();
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
  await expect(close.getByText("已关闭")).toBeVisible();
  await screenshot(page, "fe3c-close-result", 1920);
  await close.getByRole("button", { name: "取消" }).click();
  await expect(dialog.getByText("原始组态备份的来源无法解释")).toBeVisible();
  await expect(dialog.getByText("候选集合已变化，之前的接受不再适用，请重新核对")).toBeVisible();
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
