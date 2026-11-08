import { expect, test, type Page, type Route } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import type { components } from "../src/features/api/generated/openapi";
import {
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

async function screenshot(page: Page, name: string, width: number) {
  if (!screenshotDirectory) return;
  await mkdir(join(screenshotDirectory, String(width)), { recursive: true });
  await page.setViewportSize({ width, height: width === 1280 ? 800 : 1080 });
  await page.screenshot({ path: join(screenshotDirectory, String(width), `${name}.png`), fullPage: false });
}

function json(route: Route, status: number, body: unknown) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

const baseWorkspace = WORKSPACE_ALREADY_EXISTS.body as Schemas["WorkspaceResponse"];

function workspace(patch: Partial<Schemas["WorkspaceResponse"]>): Schemas["WorkspaceResponse"] {
  return { ...baseWorkspace, active_submission_id: null, active_submit_attempt_id: null, ...patch };
}

function submissionNode(refId: string, createdAt: string, patch: Partial<Schemas["HistoryNodeResponse"]> = {}): Schemas["HistoryNodeResponse"] {
  return {
    ref_kind: "submission" as const,
    ref_id: refId,
    node_kind: "SUBMISSION" as const,
    commit_id: "commit-" + refId,
    created_at: createdAt,
    parent: { ref_kind: "baseline_node" as const, ref_id: "fe2a-history-ref-1" },
    identity_exception: false,
    review_status: "APPROVED" as const,
    ...patch,
  };
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
}

async function installModeRoutes(page: Page, state: ModeState) {
  const bundle = await loadBundle("preview-full");
  await page.route("**/v1/workspaces", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    return json(route, 200, state.workspace);
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
    return json(route, 200, state.review);
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
  await page.route(/\/v1\/operations\/[^/]+$/, (route) => json(route, 200, state.operation ?? { ...TEST_OPERATION_SUCCEEDED, operation_id: route.request().url().split("/").at(-1) }));
}

function previewUrl(extra: Record<string, string> = {}) {
  const params = new URLSearchParams({ page: "compare", mode: "PREVIEW", workspaceId: "workspace-fe2b", previewResultId: "preview-full", ...extra });
  return "/?" + params.toString();
}

async function waitForPreview(page: Page) {
  await expect(page.getByRole("heading", { name: "差异浏览", level: 1 })).toBeVisible();
  await expect(page.locator(".grid-frame").first()).toBeVisible({ timeout: 20000 });
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
  state.workspace = workspace({});
  await page.reload();
  await expect(page.getByText("已有待审核的提交，撤回后才能重新上传")).toHaveCount(0);
  await selectModifiedDirectory(page);
  await expect(upload).toBeEnabled();
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

test("D1-D5 终局处置的组态树与详情显示", async ({ page }) => {
  const archivedBaseline: Schemas["HistoryNodeResponse"] = {
    ref_kind: "baseline_node", ref_id: "baseline-arch", node_kind: "BASELINE_NODE", baseline_kind: "ARCHIVED_SUBMISSION",
    commit_id: "commit-baseline-arch", created_at: "2026-11-07T09:00:00Z", parent: { ref_kind: "baseline_node", ref_id: "fe2a-history-ref-1" },
    identity_exception: false,
  };
  const nodes: Schemas["HistoryNodeResponse"][] = [
    ...HISTORY_PAGE_ONE.nodes,
    submissionNode("d-arch", "2026-11-05T01:00:00Z", {
      submission_disposition: "ARCHIVED_BASELINE", disposition_source_kind: "ARCHIVE" as const, disposition_result_id: "archive-result-1",
      promoted_baseline_node_id: "baseline-arch",
    }),
    submissionNode("d-closed", "2026-11-05T02:00:00Z", {
      submission_disposition: "CLOSED_NOT_ARCHIVED", disposition_source_kind: "ARCHIVE" as const, disposition_result_id: "archive-result-1",
    }),
    submissionNode("d-manual", "2026-11-05T03:00:00Z", {
      submission_disposition: "CLOSED_NOT_ARCHIVED", disposition_source_kind: "MANUAL_CLOSE" as const,
      closure: { closed_by: "owner-9", closed_at: "2026-11-06T08:00:00Z", reason: "第一行\n第二行\n第三行\n第四行" },
    }),
    submissionNode("d4", "2026-11-05T04:00:00Z", {
      submission_disposition: "ARCHIVED_BASELINE", disposition_source_kind: "ARCHIVE" as const, disposition_result_id: "archive-result-1",
      eligibility_note: "NOT_CANDIDATE_BASE_ADVANCED" as const,
    }),
    submissionNode("d5", "2026-11-05T05:00:00Z", { eligibility_note: "NOT_CANDIDATE_BASE_ADVANCED" as const }),
    archivedBaseline,
  ];
  const state: ModeState = {
    workspace: workspace({}),
    review: TEST_REVIEW_FACTS,
    history: { head: HISTORY_PAGE_ONE.head, nodes, next_cursor: null },
  };
  await installModeRoutes(page, state);
  await page.goto("/?page=workspace");
  await expect(page.locator(".workspace-table")).toBeVisible();
  const details = page.locator(".workspace-details");
  const expand = page.getByRole("button", { name: "展开详情面板" });
  if (await expand.count()) await expand.click();
  await expect(details.locator(".workspace-details__content")).toBeVisible();

  await page.locator("tr", { hasText: "已归档" }).first().click();
  await expect(details.getByText("终局处置")).toBeVisible();
  await expect(details.getByText(/已归档，成为归档基线 \d+/)).toBeVisible();
  await expect(page.locator(".workspace-actions").getByText("该提交已归档")).toBeVisible();
  await screenshot(page, "fe3b-d1-archived", 1280);

  await page.locator("tr", { hasText: "已关闭（未归档）" }).first().click();
  await expect(details.getByText("归档时选中了其他提交")).toBeVisible();
  await expect(page.locator(".workspace-actions").getByText("该提交已关闭（未归档）")).toBeVisible();
  await screenshot(page, "fe3b-d2-closed-at-archive", 1280);

  await page.locator("tr", { hasText: "已关闭（未归档）" }).nth(1).click();
  await expect(details.getByText("关闭人")).toBeVisible();
  await expect(details.getByText("关闭理由")).toBeVisible();
  await expect(details.getByText(/owner-9/)).toBeVisible();
  await screenshot(page, "fe3b-d3-manual-close", 1280);

  const d4Row = page.locator("tr", { hasText: "已归档" }).nth(1);
  await d4Row.click();
  await expect(d4Row.locator(".status-tag--warning")).toHaveCount(0);
  await expect(page.locator(".workspace-actions").getByText("该提交已归档")).toBeVisible();
  await screenshot(page, "fe3b-d4-priority", 1280);

  const d5Row = page.locator("tr", { hasText: "基线已更新" }).first();
  await expect(d5Row).toBeVisible();
  await d5Row.click();
  await expect(d5Row.locator(".status-tag--warning")).toHaveText("基线已更新");
  await expect(page.locator(".workspace-actions").getByText("该提交所基于的基线已不是当前基线")).toBeVisible();
  await expect(page.getByText("不能归档")).toHaveCount(0);
  await screenshot(page, "fe3b-d5-flag", 1280);
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
  await page.goto(previewUrl());
  await waitForPreview(page);
  await expect(page.getByRole("button", { name: "撤回", exact: true })).toBeDisabled();
  await expect(page.getByText("提交正在执行，完成后才能撤回")).toBeVisible();
  await expect(page.getByRole("button", { name: "提交", exact: true })).toBeDisabled();
  await screenshot(page, "fe3b-w6-withdraw-busy", 1280);
  await page.goto("/?page=workspace");
  const upload = page.locator(".workspace-actions").getByRole("button", { name: "上传", exact: true });
  await expect(upload).toBeDisabled();
  await expect(page.getByText("提交正在执行，完成后才能继续")).toBeVisible();
  await screenshot(page, "fe3b-w6-attempt-running", 1280);
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
  await screenshot(page, "fe3b-withdraw-unknown", 1280);
});
