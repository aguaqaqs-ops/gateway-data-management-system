import { expect, test, type Page, type Route } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import type { components } from "../src/features/api/generated/openapi";
import {
  HISTORY_PAGE_ONE, HISTORY_PAGE_TWO, HISTORY_COMPARE_RUNNING, MANUAL_RECOVERY_TO_SUCCESS,
  SIMULATED_ERROR_RESPONSES, TEST_REVIEW_FACTS, WORKSPACE_ALREADY_EXISTS, WORKSPACE_CREATED, HISTORY_COMPARE_ACCEPT_BODY,
  TEST_OPERATION_SUCCEEDED, testHistoryCompareSucceeded,
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

async function installFixtureRoutes(page: Page, options: {
  truncateFirst?: boolean;
  fail?: boolean;
  slowPreview?: boolean;
  noPermission?: boolean;
  timeoutFirstCompare?: boolean;
  historyCompareErrors?: number;
  historyCompareStatus?: (operationId: string, index: number) => Schemas["HistoryCompareResultResponse"];
  operationStatus?: (operationId: string, index: number) => Schemas["OperationResponse"];
} = {}) {
  const requests = new Map<string, number>();
  const apiRequests: Array<{ method: string; path: string; token: string | null; idempotencyKey: string | null; body: string }> = [];
  const apiResponses: Array<{ method: string; path: string; status: number; body: string }> = [];
  const historyCompareCounts = new Map<string, number>();
  const operationCounts = new Map<string, number>();
  const idempotentResponses = new Map<string, { response: Schemas["HistoryCompareAcceptResponse"]; ready: Promise<void>; finish: () => void; requestBody: string }>();
  let workspaceCallCount = 0;

  await page.route("**/v1/workspaces", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const request = route.request();
    const path = new URL(request.url()).pathname;
    apiRequests.push({ method: request.method(), path, token: request.headers()["authorization"] ?? null, idempotencyKey: request.headers()["idempotency-key"] ?? null, body: request.postData() ?? "" });
    if (options.noPermission) {
      const error = SIMULATED_ERROR_RESPONSES.find((item) => item.route === path && item.method === "POST" && item.status === 403);
      if (!error) throw new Error("POST /v1/workspaces SCOPE_FORBIDDEN fixture missing");
      apiResponses.push({ method: "POST", path, status: error.status, body: JSON.stringify(error.body) });
      return route.fulfill({ status: error.status, contentType: "application/json", body: JSON.stringify(error.body) });
    }
    workspaceCallCount += 1;
    const response = workspaceCallCount === 1 ? WORKSPACE_CREATED : WORKSPACE_ALREADY_EXISTS;
    apiResponses.push({ method: "POST", path, status: response.status, body: JSON.stringify(response.body) });
    return route.fulfill({ status: response.status, contentType: "application/json", body: JSON.stringify(response.body) });
  });

  await page.route("**/v1/history**", async (route) => {
    const request = route.request();
    if (request.method() !== "GET") return route.fallback();
    const url = new URL(request.url());
    const body = url.searchParams.has("cursor") ? HISTORY_PAGE_TWO : HISTORY_PAGE_ONE;
    apiRequests.push({ method: "GET", path: url.pathname + url.search, token: request.headers()["authorization"] ?? null, idempotencyKey: null, body: "" });
    apiResponses.push({ method: "GET", path: url.pathname + url.search, status: 200, body: JSON.stringify(body) });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });

  await page.route("**/v1/submissions/*/review", async (route) => {
    const request = route.request();
    apiRequests.push({ method: "GET", path: new URL(request.url()).pathname, token: request.headers()["authorization"] ?? null, idempotencyKey: null, body: "" });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(TEST_REVIEW_FACTS) });
  });

  await page.route("**/v1/history-compares", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const request = route.request();
    const key = request.headers()["idempotency-key"] ?? "missing-key";
    const requestBody = request.postData() ?? "";
    apiRequests.push({ method: "POST", path: "/v1/history-compares", token: request.headers()["authorization"] ?? null, idempotencyKey: key, body: requestBody });
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
    if (options.timeoutFirstCompare) await new Promise((resolve) => setTimeout(resolve, 900));
    finish();
    apiResponses.push({ method: "POST", path: "/v1/history-compares", status: 202, body: JSON.stringify(accepted) });
    return route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify(accepted) });
  });

  await page.route("**/v1/history-compares/*/bundle", async (route) => {
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
    const result = options.operationStatus?.(operationId, count) ?? { ...TEST_OPERATION_SUCCEEDED, operation_id: operationId };
    apiResponses.push({ method: "GET", path: new URL(request.url()).pathname, status: 200, body: JSON.stringify(result) });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(result) });
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
    if (fixtureName === "preview-workbench-normal" && options.slowPreview) await new Promise((resolve) => setTimeout(resolve, 1_200));
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

async function screenshot(page: Page, name: string, width: number) {
  if (!outputDirectory) return;
  await page.setViewportSize({ width, height: 1080 });
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  const appGrid = page.locator(".grid-frame[data-rendered]").first();
  if (await appGrid.count()) {
    await expect(appGrid).toHaveAttribute("data-rendered", "true");
    await expect(appGrid).toHaveAttribute("data-first-cell-content", /.+/);
    await expect(appGrid.locator("canvas").first()).toBeVisible();
  }
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
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
  if (!outputDirectory) return;
  await page.setViewportSize({ width, height: 1080 });
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
  const grid = page.locator('.grid-frame[data-tab-key="telemetry"]');
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
  await expect(firstPreviewView).toHaveAttribute("title", /2 张表降级比较/);
  await expect(firstPreviewView).toHaveAttribute("title", /3 张表有比较提示/);
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
  await page.getByRole("button", { name: "查看整表" }).click();
  await waitForGridPaint(page, "__whole__:device");
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
  await page.getByRole("button", { name: "查看整表" }).click();
  await waitForGridPaint(page, "__whole__:device");
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
  await search.fill("直流屏");
  await expect(page.getByRole("button", { name: /直流屏/ })).toBeVisible();
  await page.locator(".sidebar-toolbar button").click();
  await expect(page).not.toHaveURL(/changed=1/);
  await page.locator(".sidebar-toolbar button").click();
  await expect(page).toHaveURL(/changed=1/);
  await page.getByRole("button", { name: "下一个变更" }).click();
  await expect(page).toHaveURL(/change=1/);
  await page.getByRole("radio", { name: "Debug" }).click();
  await expect.poll(() => new URL(page.url()).searchParams.get("q")).toBe("直流屏");
  const stateBeforeReload = new URL(page.url());
  expect(stateBeforeReload.searchParams.get("view")).toBeNull();
  expect(stateBeforeReload.searchParams.get("pair")).toBe("baseline_to_initial");
  expect(stateBeforeReload.searchParams.get("tab")).toBe("__whole__:device");
  expect(stateBeforeReload.searchParams.get("changed")).toBe("1");
  expect(stateBeforeReload.searchParams.get("debug")).toBe("1");
  const requestCountBeforeReload = requests.get("preview-full") ?? 0;
  await page.reload();
  await waitForBrowse(page);
  const reloadedSearch = page.getByRole("textbox", { name: "搜索组、节点或页签" });
  if (!(await reloadedSearch.isVisible())) await page.getByRole("button", { name: "展开导航" }).click();
  await expect(reloadedSearch).toHaveValue("直流屏");
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
  await page.goto(browseUrl("REVIEW", "history-three-nodes", { pair: "fe2a-history-fixture-p0" }));
  await waitForBrowse(page);
  expect(new URL(page.url()).searchParams.get("mode")).toBe("REVIEW");
  await expect(page.locator(".mode-tag")).toHaveText("审核");

  await page.goto(browseUrl("HISTORY", "history-three-nodes", { pair: "fe2a-history-fixture-p0" }));
  await waitForBrowse(page);
  await expect(page.locator(".mode-tag")).toHaveText("历史比较 · 只读");
  await expect(page.getByRole("tab", { name: "节点 2 → 节点 3" })).toBeVisible();
  await screenshotHeader(page, "s3-header-history", 1920);
  await screenshotHeader(page, "s3-header-history", 1280);
  await page.getByRole("tab", { name: "节点 2 → 节点 3" }).click();
  await expect(page).toHaveURL(/pair=fe2a-history-fixture-p1/);

  await page.goto(browseUrl("PREVIEW", "preview-full", { pair: "initial_to_modified" }));
  await waitForBrowse(page);
  await page.getByRole("button", { name: "复合信号虚装置" }).click();
  await expect(page.locator(".table-heading h2")).toHaveText("复合信号测点");
  await waitForGridPaint(page, "composite_signal_point");
  await clickFormulaCell(page);
  const formula = page.getByRole("dialog", { name: "公式查看" });
  await expect(formula).toBeVisible();
  await expect(formula.getByText("改前公式在 BE-b 实现后提供", { exact: true })).toBeVisible();
  await expect(formula).toContainText("公式已改");
  await expect(formula).toContainText("| 嵌套命名表达式 =");
  await expect(formula).toContainText("+ （* 分组）");
  await expect(formula).toContainText("线路保护装置 A:线路电流");
  await expect(formula).toContainText("Device 999:未映射测点");
  await expect(formula).not.toContainText("kind:");
  await screenshot(page, "formula-preview", 1920);
  await screenshot(page, "formula-preview", 1280);
  await formula.getByRole("button", { name: "关闭公式" }).click();
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(browseUrl("HISTORY", "history-three-nodes", { pair: "fe2a-history-fixture-p0", node: "device:composite", tab: "composite_signal_point" }));
  await waitForBrowse(page);
  expect(new URL(page.url()).searchParams.get("pair")).toBe("fe2a-history-fixture-p0");
  expect(new URL(page.url()).searchParams.get("tab")).toBe("composite_signal_point");
  await expect(page.locator(".table-heading h2")).toHaveText("复合信号测点");
  await waitForGridPaint(page, "composite_signal_point");
  await clickFormulaCell(page);
  await expect(page.getByRole("dialog", { name: "公式查看" }).getByText("改前公式", { exact: true })).toBeVisible();
  await expect(page.getByRole("dialog", { name: "公式查看" }).getByText("改后公式", { exact: true })).toBeVisible();
  await screenshot(page, "formula-history", 1920);
  await screenshot(page, "formula-history", 1280);
});

test("数据集替换显示身份结论与两侧表，缺失导航使用单组占位回退", async ({ page }) => {
  await installFixtureRoutes(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(browseUrl("PREVIEW", "preview-replacement", { pair: "initial_to_modified" }));
  await waitForBrowse(page);
  await expect(page.locator(".view-tabs")).toContainText("高风险");
  await expect(page.getByText("身份结论：不同项目")).toBeVisible();
  await expect(page.getByRole("heading", { name: /替换前/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /替换后/ })).toBeVisible();
  await screenshot(page, "dataset-replacement-browse", 1920);
  await screenshot(page, "dataset-replacement-browse", 1280);

  await page.goto(browseUrl("PREVIEW", "preview-no-navigation"));
  await waitForBrowse(page);
  await expect(page.getByText("占位导航")).toBeVisible();
  await screenshot(page, "navigation-fallback", 1920);
  await screenshot(page, "navigation-fallback", 1280);
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
  await installFixtureRoutes(page, { slowPreview: true });
  await page.goto(browseUrl("PREVIEW", "preview-workbench-normal"), { waitUntil: "domcontentloaded" });
  await expect(page.getByLabel("下载并校验比较结果")).toBeVisible();
  await screenshot(page, "loading-skeleton", 1920);
  await screenshot(page, "loading-skeleton", 1280);
  await waitForBrowse(page);

  await page.unrouteAll();
  await installFixtureRoutes(page, { fail: true });
  await page.goto(browseUrl("PREVIEW", "preview-workbench-normal"));
  await expect(page.getByRole("alert")).toContainText("BUNDLE_LOAD_FAILED");
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
  await expect(page.locator(".workspace-table tbody tr")).toHaveCount(3);
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

  await page.getByRole("button", { name: "归档基线", exact: true }).click();
  await page.locator(".workspace-context-bar").getByRole("button", { name: "加入比较" }).click();
  await page.getByRole("button", { name: "提交 2", exact: true }).click();
  await expect(page.locator(".workspace-context-bar")).toContainText("待审核");
  await expect(page.locator(".workspace-context-bar")).toContainText("提交尚未审核通过");
  await page.locator(".workspace-context-bar").getByRole("button", { name: "加入比较" }).click();
  await expect(page.locator(".compare-tray")).toContainText("2 / 3");
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
  await waitForBrowse(page);
  expect(new URL(page.url()).searchParams.get("workspaceId")).toBe("workspace-fe2b");
  expect(new URL(page.url()).searchParams.get("previewResultId")).toBe("preview-full");
  expect(new URL(page.url()).searchParams.get("pair")).toBe("baseline_to_initial");
  for (const legacy of ["request", "previewRequest", "reviewRequest", "historyRequest"]) expect(new URL(page.url()).searchParams.has(legacy)).toBe(false);
  await page.goBack();
  await expect(page.locator(".workspace-table")).toBeVisible();
  await page.getByRole("button", { name: "工作区 gateway-17", exact: true }).click();
  await page.locator(".workspace-context-bar").getByRole("button", { name: "本次归档组态" }).click();
  await waitForBrowse(page);
  expect(new URL(page.url()).searchParams.get("pair")).toBe("initial_to_modified");
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
  const { apiRequests, apiResponses } = await installFixtureRoutes(page, {
    timeoutFirstCompare: true,
    historyCompareStatus: (operationId, index) => index <= 3
      ? { ...HISTORY_COMPARE_RUNNING, operation_id: operationId }
      : { ...testHistoryCompareSucceeded(fixture.manifest.bundle_digest), operation_id: operationId },
  });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  await page.getByRole("button", { name: "归档基线", exact: true }).click();
  await page.locator(".workspace-context-bar").getByRole("button", { name: "加入比较" }).click();
  await page.getByRole("button", { name: "提交 2", exact: true }).click();
  await page.locator(".workspace-context-bar").getByRole("button", { name: "加入比较" }).click();
  await page.locator(".compare-tray").getByRole("button", { name: "历史比较" }).click();
  await expect(page.getByRole("alert")).toContainText("请求超时");
  await page.locator(".compare-tray").getByRole("button", { name: "重试发起比较" }).click();

  await expect(page).toHaveURL(/operationId=history-compare-fe2b-1/);
  const comparePosts = apiRequests.filter((request) => request.method === "POST" && request.path === "/v1/history-compares");
  await expect.poll(() => apiRequests.filter((request) => request.method === "POST" && request.path === "/v1/history-compares").length).toBe(2);
  expect(comparePosts[0]?.idempotencyKey).toBeTruthy();
  expect(comparePosts[0]?.idempotencyKey).toBe(comparePosts[1]?.idempotencyKey);
  expect(comparePosts[0]?.body).toBe(comparePosts[1]?.body);
  expect(apiResponses.filter((response) => response.method === "POST" && response.path === "/v1/history-compares").map((response) => response.status)).toEqual([202, 200]);
  await expect(page.locator(".history-result-drawer")).toContainText("仍在运行");
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
});

test("History 比较仍在运行和连接中断状态清晰显示", async ({ page }) => {
  await installFixtureRoutes(page, { historyCompareStatus: (operationId) => ({ ...HISTORY_COMPARE_RUNNING, operation_id: operationId }) });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/?page=workspace&operationId=history-compare-running&operationKind=history-compare&compare=baseline_node%3Afe2a-history-ref-1&compare=submission%3Afe2a-history-ref-2");
  await expect(page.locator(".history-result-drawer")).toContainText("仍在运行");
  await screenshot(page, "history-compare-running", 1920);
  await screenshot(page, "history-compare-running", 1280);

  await page.unrouteAll();
  await installFixtureRoutes(page, { historyCompareErrors: 5 });
  await page.goto("/?page=workspace&operationId=history-compare-interrupted&operationKind=history-compare&compare=baseline_node%3Afe2a-history-ref-1&compare=submission%3Afe2a-history-ref-2");
  await expect(page.locator(".history-result-drawer")).toContainText("连接中断", { timeout: 25_000 });
  await expect(page.getByRole("button", { name: "重试查询" })).toBeVisible();
  await screenshot(page, "history-compare-connection-interrupted", 1920);
  await screenshot(page, "history-compare-connection-interrupted", 1280);
});

test("MANUAL_RECOVERY_REQUIRED 提供管理员信息并在刷新后跟随 RUNNING 到 SUCCEEDED", async ({ page }) => {
  await installFixtureRoutes(page, { operationStatus: (_operationId, index) => MANUAL_RECOVERY_TO_SUCCESS[Math.min(index - 1, MANUAL_RECOVERY_TO_SUCCESS.length - 1)]! });
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

test("所选模拟身份携带对应 token；无权限错误页不显示已连接", async ({ page }) => {
  const { apiRequests } = await installFixtureRoutes(page, { noPermission: true });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("SCOPE_FORBIDDEN");
  await page.getByRole("combobox", { name: "模拟身份" }).selectOption("no-permission");
  await expect.poll(() => apiRequests.filter((request) => request.method === "POST" && request.path === "/v1/workspaces" && request.token === "Bearer dev-token-no-permission").length).toBeGreaterThan(0);
  await expect(page.getByText("已连接", { exact: true })).toHaveCount(0);
  await screenshot(page, "workspace-error-no-connected", 1920);
  await screenshot(page, "workspace-error-no-connected", 1280);
});

test("FE2b 正常业务场景以普通页签打开主表且无导航或表诊断", async ({ page }) => {
  await installFixtureRoutes(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(browseUrl("PREVIEW", "preview-workbench-normal", { node: "forward-channel:b1_n1", tab: "telemetry" }));
  await waitForBrowse(page);
  await expect(page.locator(".navigation-sidebar")).toContainText("转发通道");
  await expect(page.locator(".nav-group__diagnostic-count")).toHaveCount(0);
  await expect(page.locator(".diagnostic-note")).toHaveCount(0);
  await expect(page.locator(".pair-diagnostic-strip")).toHaveCount(0);
  await expect(page.locator(".table-heading__diagnostics")).toHaveCount(0);
  await expect(page.locator(".table-heading h2")).toHaveText("遥测量");
  await screenshot(page, "s3-workbench-normal", 1920);
  await waitForGridPaint(page, "telemetry");
  await screenshot(page, "s4-grid-normal-main", 1920);
  await hoverChangedTelemetryValue(page);
  await screenshot(page, "s4-grid-normal-hover", 1920);
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
