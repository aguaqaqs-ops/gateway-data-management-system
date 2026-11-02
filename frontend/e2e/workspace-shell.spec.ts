import { expect, test, type Page, type Route } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import { join } from "node:path";

interface FixtureManifest {
  bundle_digest: string;
  pairs: Array<{ pair_id: string }>;
}

const fixtures = new Map<string, { tar: Buffer; manifest: FixtureManifest }>();
const outputDirectory = process.env.GATEWAY_FE_SCREENSHOT_DIR;
const previewPath = "/v1/fe2a-fixture/preview-full";
const reviewPath = "/v1/fe2a-fixture/history-three-nodes";
const historyPath = "/v1/fe2a-fixture/history-three-nodes";

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

async function installFixtureRoutes(page: Page, options: { truncateFirst?: boolean; fail?: boolean } = {}) {
  const requests = new Map<string, number>();
  await page.route("**/v1/fe2a-fixture/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    const fixtureName = pathname.split("/").at(-1) ?? "";
    requests.set(fixtureName, (requests.get(fixtureName) ?? 0) + 1);
    if (options.fail) {
      await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ code: "FIXTURE_UNAVAILABLE", message: "模拟接口暂时不可用" }) });
      return;
    }
    const fixture = await loadFixture(fixtureName);
    const truncate = options.truncateFirst && requests.get(fixtureName) === 1;
    await route.fulfill({
      status: 200,
      contentType: "application/x-tar",
      headers: {
        ETag: fixture.manifest.bundle_digest,
        "Content-Length": String(fixture.tar.byteLength),
      },
      body: truncate ? fixture.tar.subarray(0, Math.floor(fixture.tar.byteLength / 2)) : fixture.tar,
    });
  });
  return requests;
}

function browseUrl(mode: "PREVIEW" | "REVIEW" | "HISTORY", requestPath: string, extra: Record<string, string> = {}): string {
  const params = new URLSearchParams({
    mode,
    request: requestPath,
    previewRequest: previewPath,
    reviewRequest: reviewPath,
    historyRequest: historyPath,
    ...extra,
  });
  return "/?" + params.toString();
}

async function waitForBrowse(page: Page) {
  await expect(page.getByRole("heading", { name: "差异浏览", level: 1 })).toBeVisible();
  await expect(page.locator(".grid-frame").first()).toBeVisible();
}

async function screenshot(page: Page, name: string, width: number) {
  if (!outputDirectory) return;
  await page.setViewportSize({ width, height: 1080 });
  await mkdir(outputDirectory, { recursive: true });
  await page.screenshot({ path: join(outputDirectory, name + "-" + width + ".png"), fullPage: true, animations: "disabled" });
}

async function screenshotHeader(page: Page, name: string, width: number) {
  if (!outputDirectory) return;
  await page.setViewportSize({ width, height: 1080 });
  await mkdir(outputDirectory, { recursive: true });
  await page.locator(".compare-header").screenshot({ path: join(outputDirectory, name + "-" + width + ".png"), animations: "disabled" });
}

test("Preview、审核与历史浏览保留 URL 状态，并覆盖 S3/S4 页面", async ({ page }) => {
  const requests = await installFixtureRoutes(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(browseUrl("PREVIEW", previewPath, { pair: "baseline_to_initial", changed: "1" }));
  await waitForBrowse(page);

  await expect(page.getByRole("button", { name: "上传预览" })).toHaveClass(/is-active/);
  await expect(page.locator(".distribution-strip")).toBeVisible();
  await page.getByRole("button", { name: "查看整表" }).click();
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

  await page.goto(browseUrl("PREVIEW", previewPath, { pair: "baseline_to_initial", changed: "1", debug: "1" }));
  await waitForBrowse(page);
  await page.getByRole("button", { name: "查看整表" }).click();
  await expect(page.getByRole("button", { name: "Debug" })).toHaveClass(/is-active/);
  await screenshot(page, "s4-grid-debug", 1920);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("button", { name: "收起导航" }).click();
  await screenshot(page, "s4-grid-debug", 1280);

  await page.goto(browseUrl("PREVIEW", previewPath, { pair: "baseline_to_initial", changed: "1" }));
  await waitForBrowse(page);
  await page.getByRole("button", { name: "查看整表" }).click();
  await page.getByRole("button", { name: "收起导航" }).click();
  await screenshot(page, "s3-workbench-upload", 1280);
  await screenshotHeader(page, "s3-header-upload", 1280);
  await screenshot(page, "s4-grid-main", 1280);

  await page.getByRole("button", { name: "展开导航" }).click();
  const search = page.getByRole("textbox", { name: "搜索组、节点或页签" });
  await search.fill("直流屏");
  await expect(page.getByRole("button", { name: /直流屏/ })).toBeVisible();
  await page.locator(".sidebar-toolbar button").click();
  await expect(page).toHaveURL(/changed=1/);
  await page.getByRole("button", { name: "下一个变更" }).click();
  await expect(page).toHaveURL(/change=1/);
  await page.getByRole("button", { name: "Debug" }).click();
  await expect.poll(() => new URL(page.url()).searchParams.get("q")).toBe("直流屏");
  const stateBeforeReload = new URL(page.url());
  expect(stateBeforeReload.searchParams.get("view")).toBe("baseline_to_initial");
  expect(stateBeforeReload.searchParams.get("pair")).toBe("baseline_to_initial");
  expect(stateBeforeReload.searchParams.get("tab")).toBe("__whole__:device");
  expect(stateBeforeReload.searchParams.get("changed")).toBe("1");
  expect(stateBeforeReload.searchParams.get("debug")).toBe("1");
  const requestCountBeforeReload = requests.get("preview-full") ?? 0;
  await page.reload();
  await waitForBrowse(page);
  await page.getByRole("button", { name: "展开导航" }).click();
  await expect(page.getByRole("textbox", { name: "搜索组、节点或页签" })).toHaveValue("直流屏");
  await expect(page.getByRole("button", { name: "Debug" })).toHaveClass(/is-active/);
  expect(new URL(page.url()).searchParams.get("node")).toBe(stateBeforeReload.searchParams.get("node"));
  expect(new URL(page.url()).searchParams.get("change")).toBe("1");
  expect(requests.get("preview-full")).toBe(requestCountBeforeReload);

  await page.getByRole("textbox", { name: "搜索组、节点或页签" }).fill("");
  await page.getByRole("button", { name: "显示全部" }).click();
  await page.getByRole("button", { name: /更多/ }).click();
  await expect(page.locator(".overflow-menu")).toBeVisible();
  await screenshot(page, "tab-overflow", 1920);
  await screenshot(page, "tab-overflow", 1280);
  await page.locator(".overflow-menu").getByRole("button", { name: /keyless_demo/ }).click();
  await expect(page.locator(".table-heading h2")).toHaveText("keyless_demo");
  expect(new URL(page.url()).searchParams.get("tab")).toBe("keyless_demo");

  await page.getByRole("button", { name: "审核", exact: true }).click();
  await waitForBrowse(page);
  await expect(page.getByRole("button", { name: "审核", exact: true })).toHaveClass(/is-active/);
  await screenshotHeader(page, "s3-header-review", 1920);
  await screenshotHeader(page, "s3-header-review", 1280);

  await page.getByRole("button", { name: "历史比较", exact: true }).click();
  await expect(page.getByRole("button", { name: "历史比较", exact: true })).toHaveClass(/is-active/);
  await expect(page.getByRole("tab", { name: "节点 2 → 节点 3" })).toBeVisible();
  await screenshotHeader(page, "s3-header-history", 1920);
  await screenshotHeader(page, "s3-header-history", 1280);
  await page.getByRole("tab", { name: "节点 2 → 节点 3" }).click();
  await expect(page).toHaveURL(/pair=node_2_to_node_3/);

  await page.getByRole("button", { name: "上传预览", exact: true }).click();
  await waitForBrowse(page);
  await page.locator(".table-heading__actions button").click();
  const formula = page.getByRole("dialog", { name: "公式查看" });
  await expect(formula).toBeVisible();
  await expect(formula.getByText("改前公式在 BE-b 实现后提供。", { exact: false })).toBeVisible();
  await screenshot(page, "formula-preview", 1920);
  await screenshot(page, "formula-preview", 1280);
  await formula.getByRole("button", { name: "关闭公式" }).click();
  await page.getByRole("button", { name: "历史比较", exact: true }).click();
  await waitForBrowse(page);
  await page.locator(".table-heading__actions button").click();
  await expect(page.getByRole("dialog", { name: "公式查看" }).getByText("改前公式", { exact: true })).toBeVisible();
  await screenshot(page, "formula-history", 1920);
  await screenshot(page, "formula-history", 1280);
});

test("数据集替换显示身份结论与两侧表，缺失导航使用单组占位回退", async ({ page }) => {
  await installFixtureRoutes(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(browseUrl("PREVIEW", "/v1/fe2a-fixture/preview-replacement", { pair: "replacement_pair" }));
  await waitForBrowse(page);
  await expect(page.getByText("身份结论：不同项目")).toBeVisible();
  await expect(page.getByRole("heading", { name: /替换前/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /替换后/ })).toBeVisible();
  await screenshot(page, "dataset-replacement-browse", 1920);
  await screenshot(page, "dataset-replacement-browse", 1280);

  await page.goto(browseUrl("PREVIEW", "/v1/fe2a-fixture/preview-no-navigation"));
  await waitForBrowse(page);
  await expect(page.getByText("占位导航")).toBeVisible();
  await screenshot(page, "navigation-fallback", 1920);
  await screenshot(page, "navigation-fallback", 1280);
});

test("覆盖 bundle 下载截断重试、加载骨架、错误页和五级风险语义色", async ({ page }) => {
  const requests = await installFixtureRoutes(page, { truncateFirst: true });
  await page.goto(browseUrl("PREVIEW", previewPath));
  await waitForBrowse(page);
  expect(requests.get("preview-full")).toBe(2);

  await page.goto("/?design-system=1");
  for (const label of ["高风险", "中高风险", "中低风险", "低风险", "未知风险"]) await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
  await screenshot(page, "s4-semantic-tokens", 1920);
  await screenshot(page, "s4-semantic-tokens", 1280);
});

test("加载中显示骨架，bundle 接口失败显示可重试错误页", async ({ page }) => {
  await page.route("**/v1/fe2a-fixture/preview-full", async (route: Route) => {
    await new Promise((resolve) => setTimeout(resolve, 1200));
    const fixture = await loadFixture("preview-full");
    await route.fulfill({ status: 200, contentType: "application/x-tar", headers: { ETag: fixture.manifest.bundle_digest, "Content-Length": String(fixture.tar.byteLength) }, body: fixture.tar });
  });
  await page.goto(browseUrl("PREVIEW", previewPath), { waitUntil: "domcontentloaded" });
  await expect(page.getByLabel("下载并校验比较结果")).toBeVisible();
  await screenshot(page, "loading-skeleton", 1920);
  await screenshot(page, "loading-skeleton", 1280);
  await waitForBrowse(page);

  await page.unrouteAll();
  await installFixtureRoutes(page, { fail: true });
  await page.goto(browseUrl("PREVIEW", previewPath));
  await expect(page.getByRole("alert")).toContainText("BUNDLE_LOAD_FAILED");
  await screenshot(page, "bundle-error", 1920);
  await screenshot(page, "bundle-error", 1280);
});
