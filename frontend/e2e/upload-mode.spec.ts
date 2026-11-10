import { expect, test, type Page, type Route } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import type { components } from "../src/features/api/generated/openapi";
import {
  DISPOSITION_D5_NODE, DISPOSITION_HEAD, DISPOSITION_REVIEW_FACTS, DISPOSITION_SCENARIO_BASELINES, DISPOSITION_SCENARIO_NODES,
  HISTORY_PAGE_ONE, HISTORY_PAGE_TWO, SIMULATED_ERROR_RESPONSES, TEST_OPERATION_SUCCEEDED,
  TEST_REVIEW_APPLIED, TEST_REVIEW_FACTS, TEST_SUBMIT_ATTEMPT_FINALIZED, WORKSPACE_ALREADY_EXISTS,
} from "../src/features/dev/simulated-api";

type Schemas = components["schemas"];
const screenshotDirectory = process.env.GATEWAY_FE_SCREENSHOT_DIR;

interface FixtureBundle {
  tar: Buffer;
  manifest: { bundle_digest: string };
}

const bundles = new Map<string, FixtureBundle>();

async function loadBundle(name: string): Promise<FixtureBundle> {
  const cached = bundles.get(name);
  if (cached) return cached;
  const tar = await readFile("src/test/fixtures/generated/" + name + ".tar");
  const manifestSize = Number.parseInt(tar.subarray(124, 136).toString("ascii").replace(/\0.*$/, "").trim(), 8);
  const manifest = JSON.parse(tar.subarray(512, 512 + manifestSize).toString("utf8")) as { bundle_digest: string };
  const result = { tar, manifest };
  bundles.set(name, result);
  return result;
}

async function settleAfterResize(page: Page) {
  await page.evaluate(async () => {
    const frames = () => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
    await frames();
    const frame = document.querySelector<HTMLElement>(".grid-frame");
    const canvas = frame?.querySelector("canvas");
    if (!frame || !canvas) return;
    // 视口变化后 canvas 的后备尺寸由 ResizeObserver 异步更新；在两者匹配前截图会拍到空网格。
    for (let attempt = 0; attempt < 120; attempt += 1) {
      const dpr = window.devicePixelRatio || 1;
      const expected = Math.floor(frame.clientWidth * dpr);
      if (canvas.width === expected && frame.getAttribute("data-rendered") === "true") return;
      await new Promise((resolve) => setTimeout(resolve, 16));
    }
  });
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
}

async function screenshot(page: Page, name: string, width: number) {
  if (!screenshotDirectory) return;
  for (const current of [width, width === 1280 ? 1920 : 1280]) {
    await mkdir(join(screenshotDirectory, String(current)), { recursive: true });
    await page.setViewportSize({ width: current, height: current === 1280 ? 800 : 1080 });
    await settleAfterResize(page);
    await page.screenshot({ path: join(screenshotDirectory, String(current), `${name}.png`), fullPage: false, animations: "disabled" });
  }
  await page.setViewportSize({ width, height: width === 1280 ? 800 : 1080 });
  await settleAfterResize(page);
}

// C4: pin the page clock for waited-duration screenshots. setFixedTime fixes
// Date (new Date()/Date.now()) while timers keep running, so polling still
// works; the instant sits 8 seconds after the mock operation start.
async function freezePageClock(page: Page) {
  await page.clock.setFixedTime(new Date("2026-11-03T09:00:09Z"));
}

function json(route: Route, status: number, body: unknown) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

const baseWorkspace = WORKSPACE_ALREADY_EXISTS.body as Schemas["WorkspaceResponse"];

function workspace(patch: Partial<Schemas["WorkspaceResponse"]>): Schemas["WorkspaceResponse"] {
  return { ...baseWorkspace, active_submission_id: null, active_submit_attempt_id: null, ...patch };
}

interface ModeState {
  workspace: Schemas["WorkspaceResponse"];
  review: Schemas["ReviewFactsResponse"];
  reviewStatus?: number;
  history?: Schemas["HistoryListResponse"];
  attempt?: Schemas["SubmitAttemptResponse"];
  attemptStatus?: number;
  reviewEventsConflictOnce?: boolean;
  operation?: Schemas["OperationResponse"];
  operationById?: Record<string, Schemas["OperationResponse"]>;
  /** B2: queued workspace responses; the first read returns stale data, later reads recover. */
  workspaceSequence?: Schemas["WorkspaceResponse"][];
  /** REVIEW-mode facts keyed by submission id; falls back to state.review. */
  reviewBySubmission?: Record<string, Schemas["ReviewFactsResponse"]>;
}

async function installModeRoutes(page: Page, state: ModeState) {
  const bundle = await loadBundle("preview-full");
  let workspaceReads = 0;
  const workspaceReadsOf = () => workspaceReads;
  await page.route("**/v1/workspaces", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    workspaceReads += 1;
    const next = state.workspaceSequence?.length ? state.workspaceSequence.shift()! : state.workspace;
    return json(route, 200, next);
  });
  await page.route("**/v1/history-compares", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    return json(route, 202, { operation_id: "history-compare-d", status: "QUEUED", replayed: false });
  });
  await page.route(/\/v1\/history-compares\/[^/]+\/bundle$/, (route) => route.fulfill({
    status: 200,
    headers: { "Content-Type": "application/x-tar", "Content-Length": String(bundle.tar.length), ETag: bundle.manifest.bundle_digest },
    body: bundle.tar,
  }));
  await page.route(/\/v1\/history-compares\/[^/]+$/, async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    return json(route, 200, {
      operation_id: "history-compare-d",
      status: "SUCCEEDED",
      diagnostic: null,
      result: {
        bundle_digest: bundle.manifest.bundle_digest,
        completed_at: "2026-11-03T09:15:00Z",
        input: { nodes: [] },
        pairs: [],
      },
    });
  });
  await page.route(/\/v1\/history(\?|$)/, async (route) => {
    const history = state.history ?? {
      head: HISTORY_PAGE_ONE.head,
      nodes: [...HISTORY_PAGE_ONE.nodes, ...HISTORY_PAGE_TWO.nodes],
      next_cursor: null,
    };
    return json(route, 200, history);
  });
  await page.route(/\/v1\/workspaces\/[^/]+\/preview-results\/[^/]+\/bundle$/, (route) => route.fulfill({
    status: 200,
    headers: { "Content-Type": "application/x-tar", "Content-Length": String(bundle.tar.length), ETag: bundle.manifest.bundle_digest },
    body: bundle.tar,
  }));
  await page.route(/\/v1\/submissions\/[^/]+\/review$/, async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    if (state.reviewStatus && state.reviewStatus !== 200) {
      const error = SIMULATED_ERROR_RESPONSES.find((item) => item.route === "/v1/submissions/{submission_id}/review" && item.status === state.reviewStatus);
      return json(route, state.reviewStatus, error?.body ?? { code: "SCOPE_FORBIDDEN", message: "forbidden" });
    }
    const submissionId = new URL(route.request().url()).pathname.split("/")[3] ?? "";
    return json(route, 200, state.reviewBySubmission?.[submissionId] ?? state.review);
  });
  await page.route(/\/v1\/submissions\/[^/]+\/review-events$/, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    if (state.reviewEventsConflictOnce) {
      state.reviewEventsConflictOnce = false;
      const error = SIMULATED_ERROR_RESPONSES.find((item) => item.route === "/v1/submissions/{submission_id}/review-events" && item.status === 409);
      return json(route, 409, error?.body ?? { code: "REVIEW_VERSION_CONFLICT", message: "conflict" });
    }
    state.workspace = workspace({ current_upload_revision_id: null, current_preview_result_id: null });
    return json(route, 200, TEST_REVIEW_APPLIED);
  });
  await page.route(/\/v1\/workspaces\/[^/]+\/submit-attempts\/[^/]+$/, async (route) => {
    if (state.attemptStatus && state.attemptStatus !== 200) {
      return json(route, state.attemptStatus, { code: "SERVICE_NOT_READY", message: "unavailable" });
    }
    return json(route, 200, state.attempt ?? { ...TEST_SUBMIT_ATTEMPT_FINALIZED, workspace_id: "workspace-fe2b", preview_result_id: "preview-full" });
  });
  await page.route(/\/v1\/operations\/[^/]+$/, (route) => {
    const operationId = route.request().url().split("/").at(-1) ?? "";
    return json(route, 200, state.operationById?.[operationId] ?? state.operation ?? { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId });
  });
  return { workspaceReadsOf };
}

function previewUrl(extra: Record<string, string> = {}) {
  const params = new URLSearchParams({ page: "compare", mode: "PREVIEW", workspaceId: "workspace-fe2b", previewResultId: "preview-full", ...extra });
  return "/?" + params.toString();
}

async function waitForPreview(page: Page) {
  await expect(page.getByRole("heading", { name: "差异浏览", level: 1 })).toBeVisible();
  await expect(page.locator(".grid-frame[data-rendered]").first()).toBeVisible({ timeout: 20000 });
}


const VALID_UPLOAD_DIRECTORY = [
  { path: "station.pmc", content: "pmc" },
  { path: "sql/dbcfg.sql", content: "create table device(id int);\n" },
  { path: "comps/logic/logics.xml", content: "<logics/>" },
];

async function selectModifiedDirectory(page: Page) {
  if ((await page.getByTestId("upload-modified-input").count()) === 0) {
    await page.getByRole("button", { name: "展开详情面板" }).click();
  }
  await expect(page.getByTestId("upload-modified-input")).toBeAttached({ timeout: 10000 });
  await page.evaluate((files) => {
    const input = document.querySelector<HTMLInputElement>('[data-testid="upload-modified-input"]');
    if (!input) throw new Error("missing upload-modified-input");
    const transfer = new DataTransfer();
    for (const spec of files) {
      const file = new File([spec.content], spec.path.split("/").at(-1) ?? "file", { type: "text/plain" });
      Object.defineProperty(file, "webkitRelativePath", { value: `station_cfg_0921/${spec.path}` });
      transfer.items.add(file);
    }
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }, VALID_UPLOAD_DIRECTORY);
}

async function chooseUploadDirectory(page: Page) {
  const expand = page.getByRole("button", { name: "展开详情面板" });
  if (await expand.count()) await expand.click();
  await page.evaluate((files) => {
    const input = document.querySelector<HTMLInputElement>('[data-testid="upload-modified-input"]');
    if (!input) throw new Error("missing upload-modified-input");
    const transfer = new DataTransfer();
    for (const spec of files) {
      const file = new File([spec.content], spec.path.split("/").at(-1) ?? "file", { type: "text/plain" });
      Object.defineProperty(file, "webkitRelativePath", { value: `station_cfg_0921/${spec.path}` });
      transfer.items.add(file);
    }
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }, VALID_UPLOAD_DIRECTORY);
}

test("W1/W2 撤回成功后回到上传步骤并恢复上传", async ({ page }) => {
  const state: ModeState = {
    workspace: workspace({ active_submission_id: "submission-1" }),
    review: TEST_REVIEW_FACTS,
  };
  await installModeRoutes(page, state);
  await page.goto(previewUrl());
  await waitForPreview(page);
  const withdraw = page.getByRole("button", { name: "撤回", exact: true });
  await expect(withdraw).toBeEnabled();
  await screenshot(page, "fe3b-withdraw-enabled", 1920);
  await expect(withdraw).toBeInViewport();
  await screenshot(page, "fe3b-withdraw-enabled", 1280);
  await withdraw.click();
  const dialog = page.getByRole("dialog", { name: "撤回提交" });
  await expect(dialog).toBeVisible();
  await screenshot(page, "fe3b-withdraw-dialog", 1920);
  await dialog.getByRole("checkbox").check();
  await dialog.getByRole("button", { name: "确认撤回" }).click();
  await expect(page).toHaveURL(/page=workspace/);
  await expect(page.getByText("已撤回，可以重新上传")).toBeVisible();
  await chooseUploadDirectory(page);
  await expect(page.locator(".workspace-actions").getByRole("button", { name: "上传", exact: true })).toBeEnabled();
  await screenshot(page, "fe3b-upload-restored", 1280);
});

test("W3 没有审核权限的身份不能撤回", async ({ page }) => {
  const state: ModeState = {
    workspace: workspace({ active_submission_id: "submission-1" }),
    review: TEST_REVIEW_FACTS,
    reviewStatus: 403,
  };
  await installModeRoutes(page, state);
  await page.goto(previewUrl());
  await waitForPreview(page);
  await expect(page.getByRole("button", { name: "撤回", exact: true })).toBeDisabled();
  await expect(page.getByText("当前身份没有撤回权限")).toBeVisible();
  await screenshot(page, "fe3b-withdraw-forbidden", 1280);
});

test("W4 已通过提交不能撤回也不能上传", async ({ page }) => {
  const state: ModeState = {
    workspace: workspace({ active_submission_id: "submission-1" }),
    review: { ...TEST_REVIEW_FACTS, status: "APPROVED" as const },
  };
  await installModeRoutes(page, state);
  await page.goto("/?page=workspace");
  const upload = page.locator(".workspace-actions").getByRole("button", { name: "上传", exact: true });
  await expect(upload).toBeDisabled();
  await expect(page.getByText("该提交已通过审核，归档或关闭后才能重新上传")).toBeVisible();
  await screenshot(page, "fe3b-w4-approved-upload", 1280);
  await page.goto(previewUrl());
  await waitForPreview(page);
  await expect(page.getByRole("button", { name: "撤回", exact: true })).toBeDisabled();
  await expect(page.getByText("该提交已通过审核，不能撤回")).toBeVisible();
  await screenshot(page, "fe3b-w4-approved-withdraw", 1280);
});

test("W8 待审核提交禁用上传，撤回后恢复", async ({ page }) => {
  const state: ModeState = {
    workspace: workspace({ active_submission_id: "submission-1" }),
    review: TEST_REVIEW_FACTS,
  };
  await installModeRoutes(page, state);
  await page.goto("/?page=workspace");
  const upload = page.locator(".workspace-actions").getByRole("button", { name: "上传", exact: true });
  await expect(upload).toBeDisabled();
  await expect(page.getByText("已有待审核的提交，撤回后才能重新上传")).toBeVisible();
  await screenshot(page, "fe3b-w8-upload-disabled", 1280);
  // B1: the UploadStepCard start button shares the toolbar occupancy reason,
  // while the directory picker stays enabled.
  await selectModifiedDirectory(page);
  const stepCard = page.locator(".upload-card");
  const stepUpload = stepCard.getByRole("button", { name: "上传并生成预览" });
  await expect(stepUpload).toBeDisabled();
  await expect(stepCard.getByText("已有待审核的提交，撤回后才能重新上传")).toBeVisible();
  await expect(stepCard.getByRole("button", { name: "选择目录" }).first()).toBeEnabled();
  state.workspace = workspace({});
  await page.reload();
  await expect(page.getByText("已有待审核的提交，撤回后才能重新上传")).toHaveCount(0);
  await selectModifiedDirectory(page);
  await expect(upload).toBeEnabled();
  await expect(page.locator(".upload-card").getByRole("button", { name: "上传并生成预览" })).toBeEnabled();
});

test("W10 陈旧指针遇到已处置提交时显示终局原因", async ({ page }) => {
  const state: ModeState = {
    workspace: workspace({ active_submission_id: "submission-1" }),
    review: {
      ...TEST_REVIEW_FACTS,
      status: "APPROVED" as const,
      submission_disposition: { submission_id: "submission-1", disposition: "ARCHIVED_BASELINE", source_kind: "ARCHIVE", result_id: "archive-result-1", closure: null },
    },
  };
  await installModeRoutes(page, state);
  await page.goto("/?page=workspace");
  await expect(page.getByText("该提交已归档").first()).toBeVisible();
  await screenshot(page, "fe3b-w10-stale-workspace", 1280);
  await page.goto(previewUrl());
  await waitForPreview(page);
  await expect(page.getByRole("button", { name: "撤回", exact: true })).toBeDisabled();
  await expect(page.getByText("该提交已归档").first()).toBeVisible();
  await screenshot(page, "fe3b-w10-stale-preview", 1280);
});

test("W10 陈旧指针重读后恢复可用（一次性重读，B2）", async ({ page }) => {
  // The first workspace read is stale; the one-time re-read (reread) recovers.
  // Removing the re-read logic leaves the terminal reason on screen, so this
  // case fails without B2. The hook dedupes the mount read, so the recovery
  // is exactly the second workspace request even under StrictMode.
  const staleWorkspace = workspace({ active_submission_id: "submission-1" });
  const state: ModeState = {
    workspace: workspace({}),
    workspaceSequence: [staleWorkspace, workspace({})],
    review: {
      ...TEST_REVIEW_FACTS,
      status: "APPROVED" as const,
      submission_disposition: { submission_id: "submission-1", disposition: "ARCHIVED_BASELINE", source_kind: "ARCHIVE", result_id: "archive-result-1", closure: null },
    },
  };
  const { workspaceReadsOf } = await installModeRoutes(page, state);
  await page.goto("/?page=workspace");
  const upload = page.locator(".workspace-actions").getByRole("button", { name: "上传", exact: true });
  await selectModifiedDirectory(page);
  await expect(upload).toBeEnabled({ timeout: 15000 });
  expect(workspaceReadsOf()).toBe(2);
  await page.goto(previewUrl());
  await waitForPreview(page);
  await expect(page.getByRole("button", { name: "撤回", exact: true })).toBeDisabled();
  await expect(page.getByText("当前没有待审核的提交")).toBeVisible({ timeout: 15000 });
});

test("D1-D5 终局处置的组态树与详情显示", async ({ page }) => {
  // B7: disposition scenarios live in mock-data.ts and are asserted reachable by unit tests.
  // d5 joins only this D5 case dataset (DC89-unreachable, defensive); the head
  // is the tip of the reachable baseline chain (F4). Rows are selected by
  // submission label (creation order: ref-2=1, d-arch=2, d-closed=3,
  // d-manual=4, d4=5, d5=6), not by DOM position, since parents changed.
  const nodes: Schemas["HistoryNodeResponse"][] = [
    ...HISTORY_PAGE_ONE.nodes,
    ...DISPOSITION_SCENARIO_NODES,
    ...DISPOSITION_SCENARIO_BASELINES,
    DISPOSITION_D5_NODE,
  ];
  const state: ModeState = {
    workspace: workspace({}),
    review: TEST_REVIEW_FACTS,
    history: { head: DISPOSITION_HEAD, nodes, next_cursor: null },
  };
  await installModeRoutes(page, state);
  await page.goto("/?page=workspace");
  await expect(page.locator(".workspace-table")).toBeVisible();
  const details = page.locator(".workspace-details");
  const expand = page.getByRole("button", { name: "展开详情面板" });
  if (await expand.count()) await expand.click();
  await expect(details.locator(".workspace-details__content")).toBeVisible();

  await page.locator("tr", { hasText: "提交 2" }).click();
  await expect(details.getByText("终局处置")).toBeVisible();
  await expect(details.getByText(/已归档，成为归档基线 \d+/)).toBeVisible();
  await expect(details.getByText("终局状态", { exact: true })).toHaveCount(0);
  await expect(details.getByText("审核状态")).toBeVisible();
  await expect(page.locator(".workspace-actions").getByText("该提交已归档")).toBeVisible();
  await screenshot(page, "fe3b-d1-archived", 1280);

  await page.locator("tr", { hasText: "提交 3" }).click();
  await expect(details.getByText("归档时选中了其他提交")).toBeVisible();
  await expect(page.locator(".workspace-actions").getByText("该提交已关闭（未归档）")).toBeVisible();
  await screenshot(page, "fe3b-d2-closed-at-archive", 1280);

  const d3Row = page.locator("tr", { hasText: "提交 4" });
  await expect(d3Row.locator(".tree-status")).toHaveAttribute("title", "有理由关闭，详情见右侧面板");
  await d3Row.click();
  await expect(details.getByText("关闭人")).toBeVisible();
  await expect(details.getByText("关闭理由")).toBeVisible();
  await expect(details.getByText(/owner-9/)).toBeVisible();
  await expect(details.getByTitle("2026-11-06T08:00:00Z")).toContainText("11/06");
  await expect(details.getByText("展开理由")).toBeVisible();
  await details.getByText("展开理由").click();
  await expect(details.getByText("第一行")).toBeVisible();
  await expect(page.locator(".workspace-actions").getByRole("button", { name: "归档主线" })).toBeDisabled();
  await expect(page.locator(".workspace-actions").getByText("该提交已关闭（未归档）")).toBeVisible();
  await screenshot(page, "fe3b-d3-manual-close", 1280);

  const d4Row = page.locator("tr", { hasText: "提交 5" });
  await d4Row.click();
  await expect(d4Row.locator(".status-tag--warning")).toHaveCount(0);
  await expect(page.locator(".workspace-actions").getByText("该提交已归档")).toBeVisible();
  await screenshot(page, "fe3b-d4-priority", 1280);

  const d5Row = page.locator("tr", { hasText: "提交 6" });
  await expect(d5Row).toBeVisible();
  await d5Row.click();
  await expect(d5Row.locator(".status-tag--warning")).toHaveText("基线已更新");
  await expect(page.locator(".workspace-actions").getByText("该提交所基于的基线已不是当前基线")).toBeVisible();
  await expect(page.getByText("不能归档")).toHaveCount(0);
  await screenshot(page, "fe3b-d5-flag", 1280);
});

test("D1 审核模式顶栏显示已归档标签与禁用原因", async ({ page }) => {
  const archived = DISPOSITION_REVIEW_FACTS.find((facts) => facts.submission_id === "d-arch");
  if (!archived) throw new Error("d-arch review facts missing");
  const nodes: Schemas["HistoryNodeResponse"][] = [
    ...HISTORY_PAGE_ONE.nodes,
    ...DISPOSITION_SCENARIO_NODES,
    ...DISPOSITION_SCENARIO_BASELINES,
  ];
  const state: ModeState = {
    workspace: workspace({}),
    review: TEST_REVIEW_FACTS,
    reviewBySubmission: { "d-arch": archived },
    history: { head: DISPOSITION_HEAD, nodes, next_cursor: null },
  };
  await installModeRoutes(page, state);
  await page.goto("/?page=compare&mode=REVIEW&submissionId=d-arch");
  await expect(page.getByText("审核：已通过")).toBeVisible({ timeout: 30000 });
  await expect(page.getByText("已归档", { exact: true }).first()).toBeVisible();
  for (const name of ["撤回", "退回", "审核通过"] as const) {
    const button = page.locator(".review-actions").getByRole("button", { name, exact: true });
    await expect(button).toBeDisabled();
  }
  await expect(page.locator(".review-actions").getByText("该提交已归档").first()).toBeVisible();
  await expect(page.locator(".review-disposition-line")).toHaveCount(0);
  // N1: wait for the bundle so the top bar is not shot over the skeleton.
  await expect(page.locator(".grid-frame[data-rendered]").first()).toBeVisible({ timeout: 20000 });
  await screenshot(page, "fe3b-d1-review-topbar", 1280);
});

test("D2 审核模式顶栏显示归档时关闭的一行说明", async ({ page }) => {
  const closed = DISPOSITION_REVIEW_FACTS.find((facts) => facts.submission_id === "d-closed");
  if (!closed) throw new Error("d-closed review facts missing");
  const nodes: Schemas["HistoryNodeResponse"][] = [
    ...HISTORY_PAGE_ONE.nodes,
    ...DISPOSITION_SCENARIO_NODES,
    ...DISPOSITION_SCENARIO_BASELINES,
  ];
  const state: ModeState = {
    workspace: workspace({}),
    review: TEST_REVIEW_FACTS,
    reviewBySubmission: { "d-closed": closed },
    history: { head: DISPOSITION_HEAD, nodes, next_cursor: null },
  };
  await installModeRoutes(page, state);
  await page.goto("/?page=compare&mode=REVIEW&submissionId=d-closed");
  await expect(page.getByText("审核：已通过")).toBeVisible({ timeout: 30000 });
  await expect(page.getByText("已关闭（未归档）", { exact: true }).first()).toBeVisible();
  await expect(page.locator(".review-disposition-line")).toContainText("归档时选中了其他提交");
  for (const name of ["撤回", "退回", "审核通过"] as const) {
    const button = page.locator(".review-actions").getByRole("button", { name, exact: true });
    await expect(button).toBeDisabled();
  }
  await expect(page.locator(".review-actions").getByText("该提交已关闭（未归档）").first()).toBeVisible();
  // N1: wait for the bundle so the top bar is not shot over the skeleton.
  await expect(page.locator(".grid-frame[data-rendered]").first()).toBeVisible({ timeout: 20000 });
  await screenshot(page, "fe3b-d2-review-topbar", 1280);
});

test("D3 审核模式顶栏显示关闭人与理由展开", async ({ page }) => {
  const manual = DISPOSITION_REVIEW_FACTS.find((facts) => facts.submission_id === "d-manual");
  if (!manual) throw new Error("d-manual review facts missing");
  const nodes: Schemas["HistoryNodeResponse"][] = [
    ...HISTORY_PAGE_ONE.nodes,
    ...DISPOSITION_SCENARIO_NODES,
    ...DISPOSITION_SCENARIO_BASELINES,
  ];
  const state: ModeState = {
    workspace: workspace({}),
    review: TEST_REVIEW_FACTS,
    reviewBySubmission: { "d-manual": manual },
    history: { head: DISPOSITION_HEAD, nodes, next_cursor: null },
  };
  await installModeRoutes(page, state);
  await page.goto("/?page=compare&mode=REVIEW&submissionId=d-manual");
  await expect(page.getByText("审核：已通过")).toBeVisible({ timeout: 30000 });
  await expect(page.getByText("已关闭（未归档）", { exact: true }).first()).toBeVisible();
  const line = page.locator(".review-disposition-line");
  await expect(line.getByText(/由 owner-9 于/)).toBeVisible();
  await expect(line.locator("span[title='2026-11-06T08:00:00Z']")).toContainText("11/06");
  await line.getByText("查看关闭理由").click();
  await expect(line.getByText("第一行")).toBeVisible();
  for (const name of ["撤回", "退回", "审核通过"] as const) {
    const button = page.locator(".review-actions").getByRole("button", { name, exact: true });
    await expect(button).toBeDisabled();
  }
  await expect(page.locator(".review-actions").getByText("该提交已关闭（未归档）").first()).toBeVisible();
  // N1: wait for the bundle so the top bar is not shot over the skeleton.
  await expect(page.locator(".grid-frame[data-rendered]").first()).toBeVisible({ timeout: 20000 });
  await screenshot(page, "fe3b-d3-review-topbar", 1280);
});

test("F3 review 查询 404 时只读一次工作区，刷新后重读", async ({ page }) => {
  // G2 (§6.1): the 404 row labels its entry "刷新" while the other retry rows
  // keep "重试读取". Clicking it re-runs the read sequence.
  const state: ModeState = {
    workspace: workspace({ active_submission_id: "submission-1" }),
    review: TEST_REVIEW_FACTS,
    reviewStatus: 404,
  };
  const { workspaceReadsOf } = await installModeRoutes(page, state);
  await page.goto(previewUrl());
  await waitForPreview(page);
  await expect(page.getByRole("button", { name: "撤回", exact: true })).toBeDisabled();
  await expect(page.getByText("未找到该提交，请刷新后重试")).toBeVisible();
  await expect(page.getByRole("button", { name: "刷新", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "重试读取", exact: true })).toHaveCount(0);
  expect(workspaceReadsOf()).toBe(1);
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  await expect.poll(() => workspaceReadsOf(), { timeout: 15000 }).toBe(2);
  await expect(page.getByText("未找到该提交，请刷新后重试")).toBeVisible();
});

test("W5 撤回遇到审核版本冲突时重新读取且不自动重发", async ({ page }) => {
  let reviewEventCalls = 0;
  const state: ModeState = {
    workspace: workspace({ active_submission_id: "submission-1" }),
    review: TEST_REVIEW_FACTS,
    reviewEventsConflictOnce: true,
  };
  await installModeRoutes(page, state);
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/review-events")) reviewEventCalls += 1;
  });
  await page.goto(previewUrl());
  await waitForPreview(page);
  await page.getByRole("button", { name: "撤回", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "撤回提交" });
  await dialog.getByRole("checkbox").check();
  await dialog.getByRole("button", { name: "确认撤回" }).click();
  await expect(dialog.getByText("审核状态已变化，已重新读取")).toBeVisible();
  await expect(page).toHaveURL(/page=compare/);
  expect(reviewEventCalls).toBe(1);
  await screenshot(page, "fe3b-w5-conflict", 1280);
});

test("W6 提交尝试未结束时撤回、提交与上传均禁用", async ({ page }) => {
  const state: ModeState = {
    workspace: workspace({ active_submit_attempt_id: "attempt-1" }),
    review: TEST_REVIEW_FACTS,
    attempt: { ...TEST_SUBMIT_ATTEMPT_FINALIZED, state: "PREPARED" as const, workspace_id: "workspace-fe2b", preview_result_id: "preview-full" },
    operation: { ...TEST_OPERATION_SUCCEEDED, status: "RUNNING" as const, completed_at: null },
  };
  await installModeRoutes(page, state);
  // C4: pin the clock so any waited duration in later screenshots is fixed.
  await freezePageClock(page);
  await page.goto(previewUrl());
  await waitForPreview(page);
  await expect(page.getByRole("button", { name: "撤回", exact: true })).toBeDisabled();
  await expect(page.getByText("提交正在执行，完成后才能撤回")).toBeVisible();
  await expect(page.getByRole("button", { name: "提交", exact: true })).toBeDisabled();
  // C3: the two disabled reasons render in separate button-wrapped spans with
  // an explicit divider between them, each described by its own button.
  const actions = page.locator(".compare-actions");
  await expect(actions.locator(".compare-actions__divider")).toBeVisible();
  const withdraw = page.getByRole("button", { name: "撤回", exact: true });
  const submit = page.getByRole("button", { name: "提交", exact: true });
  const withdrawDescribedBy = await withdraw.getAttribute("aria-describedby");
  const submitDescribedBy = await submit.getAttribute("aria-describedby");
  expect(withdrawDescribedBy).toBeTruthy();
  expect(submitDescribedBy).toBeTruthy();
  expect(withdrawDescribedBy).not.toBe(submitDescribedBy);
  // Each reason renders in its own span: exactly two reason spans, one per
  // button, so the texts cannot merge into a single sentence.
  await expect(actions.locator(".disabled-reason")).toHaveCount(2);
  await expect(actions.locator(".disabled-reason", { hasText: "提交正在执行，完成后才能撤回" })).toBeVisible();
  await expect(actions.locator(".disabled-reason", { hasText: "提交正在执行，完成后才能继续" })).toBeVisible();
  await screenshot(page, "fe3b-w6-withdraw-busy", 1280);
  await page.goto("/?page=workspace");
  const upload = page.locator(".workspace-actions").getByRole("button", { name: "上传", exact: true });
  await expect(upload).toBeDisabled();
  await expect(page.getByText("提交正在执行，完成后才能继续")).toBeVisible();
  await screenshot(page, "fe3b-w6-attempt-running", 1280);
});

test("W6 刷新后找回操作卡片，终态未结束显示需要管理员处理", async ({ page }) => {
  // F5: the URL carries no operation; the page takes the operation_id from the
  // workspace attempt pointer, writes it back to the URL and resumes the card.
  const state: ModeState = {
    workspace: workspace({ active_submit_attempt_id: "attempt-1" }),
    review: TEST_REVIEW_FACTS,
    attempt: { ...TEST_SUBMIT_ATTEMPT_FINALIZED, state: "PREPARED" as const, workspace_id: "workspace-fe2b", preview_result_id: "preview-full", operation_id: "submit-op-1" },
    operationById: {
      "submit-op-1": { ...TEST_OPERATION_SUCCEEDED, operation_id: "submit-op-1", job_kind: "backend-vnext/submit", status: "RUNNING" as const, completed_at: null },
    },
  };
  await installModeRoutes(page, state);
  // C4: pin the clock so the operation card shows a fixed waited duration.
  await freezePageClock(page);
  await page.goto("/?page=workspace");
  await expect(page.getByRole("region", { name: "操作状态" })).toBeVisible({ timeout: 15000 });
  // The frozen instant sits 8 seconds after the mock operation start.
  await expect(page.getByRole("region", { name: "操作状态" })).toContainText("已等待 8 秒");
  await expect.poll(() => new URL(page.url()).searchParams.get("operationId"), { timeout: 15000 }).toBe("submit-op-1");
  await selectModifiedDirectory(page);
  const upload = page.locator(".workspace-actions").getByRole("button", { name: "上传", exact: true });
  await expect(upload).toBeDisabled();
  await expect(page.locator(".workspace-actions").getByText("提交正在执行，完成后才能继续")).toBeVisible();
  await screenshot(page, "fe3b-w6-resumed-card", 1280);
});

test("W6 Preview 页刷新后找回操作卡片", async ({ page }) => {
  // F5 Preview half of the pointer path: no operationId in the URL, the hook
  // writes the pointer attempt's operation_id back and mounts the resume card.
  const state: ModeState = {
    workspace: workspace({ active_submit_attempt_id: "attempt-1" }),
    review: TEST_REVIEW_FACTS,
    attempt: { ...TEST_SUBMIT_ATTEMPT_FINALIZED, state: "PREPARED" as const, workspace_id: "workspace-fe2b", preview_result_id: "preview-full", operation_id: "submit-op-1" },
    operationById: {
      "submit-op-1": { ...TEST_OPERATION_SUCCEEDED, operation_id: "submit-op-1", job_kind: "backend-vnext/submit", status: "RUNNING" as const, completed_at: null },
    },
  };
  await installModeRoutes(page, state);
  // C4: pin the clock so the operation card shows a fixed waited duration.
  await freezePageClock(page);
  await page.goto(previewUrl());
  await expect(page.getByRole("region", { name: "操作状态" })).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole("region", { name: "操作状态" })).toContainText("已等待 8 秒");
  await expect.poll(() => new URL(page.url()).searchParams.get("operationId"), { timeout: 15000 }).toBe("submit-op-1");
  await waitForPreview(page);
  await expect(page.getByRole("button", { name: "提交", exact: true })).toBeDisabled();
  await expect(page.getByText("提交正在执行，完成后才能继续").first()).toBeVisible();
  await screenshot(page, "fe3b-w6-preview-resumed-card", 1280);
});

test("W6 操作终态而 attempt 未结束时显示需要管理员处理", async ({ page }) => {
  const state: ModeState = {
    workspace: workspace({ active_submit_attempt_id: "attempt-1" }),
    review: TEST_REVIEW_FACTS,
    attempt: { ...TEST_SUBMIT_ATTEMPT_FINALIZED, state: "PREPARED" as const, workspace_id: "workspace-fe2b", preview_result_id: "preview-full", operation_id: "submit-op-1" },
    operationById: {
      "submit-op-1": { ...TEST_OPERATION_SUCCEEDED, operation_id: "submit-op-1", job_kind: "backend-vnext/submit", status: "SUCCEEDED" as const, completed_at: "2026-11-03T09:00:02Z" },
    },
  };
  await installModeRoutes(page, state);
  // C4: pin the clock so the operation card shows a fixed waited duration.
  await freezePageClock(page);
  await page.goto("/?page=workspace&operationId=submit-op-1&operationKind=operation");
  await selectModifiedDirectory(page);
  const upload = page.locator(".workspace-actions").getByRole("button", { name: "上传", exact: true });
  await expect(upload).toBeDisabled({ timeout: 15000 });
  await expect(page.locator(".workspace-actions").getByText("提交结果待确认，需要管理员处理")).toBeVisible();
  await expect(page.getByText("提交结果待确认，需要管理员处理").first()).toBeVisible();
  await screenshot(page, "fe3b-w6-recovery", 1280);
});

test("§6.1 没有待审核提交与状态无法确认时的撤回禁用原因", async ({ page }) => {
  const state: ModeState = { workspace: workspace({}), review: { ...TEST_REVIEW_FACTS, status: "PENDING" as const } };
  await installModeRoutes(page, state);
  await page.goto(previewUrl());
  await waitForPreview(page);
  await expect(page.getByRole("button", { name: "撤回", exact: true })).toBeDisabled();
  await expect(page.getByText("当前没有待审核的提交")).toBeVisible();
  await screenshot(page, "fe3b-withdraw-none", 1280);
});

test("§6.1 工作区读取失败时撤回显示无法确认提交状态", async ({ page }) => {
  const state: ModeState = { workspace: workspace({ active_submission_id: "submission-1" }), review: TEST_REVIEW_FACTS };
  await installModeRoutes(page, state);
  await page.route("**/v1/workspaces", (route) => route.request().method() === "POST"
    ? route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ code: "SERVICE_UNAVAILABLE", message: "unavailable" }), headers: { "Access-Control-Allow-Origin": "*" } })
    : route.fallback());
  await page.goto(previewUrl());
  await expect(page.getByRole("button", { name: "撤回", exact: true })).toBeDisabled();
  await expect(page.getByText("无法确认提交状态").first()).toBeVisible();
  // N3: wait for the bundle so the top bar is not shot over a skeleton.
  await waitForPreview(page);
  await screenshot(page, "fe3b-withdraw-unknown", 1280);
});
