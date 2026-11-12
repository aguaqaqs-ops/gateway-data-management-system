import { expect, test } from "@playwright/test";
import { mockCatalog, projects } from "./fixtures";

test("长编码返回位置可进入并恢复地区、搜索、范围与页码", async ({ page }) => {
  const state = { r1: "江".repeat(50), r2: "苏".repeat(50), q: "站".repeat(20), scope: "region", page: "2" };
  const catalog = Array.from({ length: 51 }, (_, index) => ({ ...projects[0],
    device_key: `dev-${index.toString(16).padStart(16, "0")}`, station_code: `ST-${index}`,
    region1: state.r1, region2: state.r2, name: state.q }));
  await page.route("**/api/catalog", (route) => route.fulfill({ json: { projects: catalog } }));
  let returnUrl = "";
  await page.route("**/api/handoffs", async (route) => {
    const body = route.request().postDataJSON() as { return_query: string };
    expect(Array.from(body.return_query).length).toBeLessThanOrEqual(1000);
    returnUrl = new URL(body.return_query, "http://127.0.0.1:5173/").href;
    await route.fulfill({ json: { gateway_url: "http://127.0.0.1:5173/#gdds-handoff=fixture" } });
  });
  const query = new URLSearchParams(state).toString();
  expect(query.length).toBeGreaterThan(1000);
  await page.goto(`/?${query}`);
  await page.getByRole("button", { name: "进入提交树" }).click();
  await expect.poll(() => page.evaluate(() => location.hash)).toBe("#gdds-handoff=fixture");
  await page.goto(returnUrl);
  await expect(page.getByLabel("搜索项目")).toHaveValue(state.q);
  await expect(page.getByRole("radio", { name: `仅 ${state.r1} / ${state.r2}` })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByText("2 / 2", { exact: true })).toBeVisible();
  expect(Object.fromEntries(new URL(page.url()).searchParams)).toEqual(state);
});

test("返回位置仍超限时提示缩短搜索且不丢失状态或发送 handoff", async ({ page }) => {
  await mockCatalog(page);
  await page.addInitScript((key) => localStorage.setItem("gdds-directory-recent", JSON.stringify([key])), projects[0].device_key);
  let requests = 0;
  await page.route("**/api/handoffs", (route) => {
    requests++;
    return route.fulfill({ json: { gateway_url: "http://127.0.0.1:5173/#gdds-handoff=fixture" } });
  });
  const query = new URLSearchParams({ r1: "江苏", r2: "苏州", q: "x".repeat(1000), scope: "region", page: "2" });
  await page.goto(`/?${query}`);
  const original = page.url();
  await page.locator(".recent .chip").click();
  await expect(page.getByRole("alert")).toContainText("请缩短搜索内容后再进入");
  expect(page.url()).toBe(original);
  expect(requests).toBe(0);
  await page.getByLabel("搜索项目").fill("城南");
  await page.locator(".recent .chip").click();
  await expect.poll(() => page.evaluate(() => location.hash)).toBe("#gdds-handoff=fixture");
  expect(requests).toBe(1);
});

test("浏览、搜索、历史和键盘", async ({ page }) => {
  await mockCatalog(page);
  await page.goto("/");
  await expect(page.getByText("18 个项目", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /江苏/ }).click();
  await page.getByRole("button", { name: /苏州/ }).click();
  await expect(page.getByText("共 14 个项目")).toBeVisible();
  await page.keyboard.press("/");
  await expect(page.getByLabel("搜索项目")).toBeFocused();
  await page.getByLabel("搜索项目").fill("cn");
  await page.getByRole("radio", { name: /仅 江苏/ }).click();
  await expect(page.getByText("共 2 个项目")).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("radio", { name: "全部地区" })).toHaveAttribute("aria-checked", "true");
  await page.keyboard.press("Escape");
  await expect(page.getByLabel("搜索项目")).toHaveValue("");
  await page.getByRole("button", { name: "全部地区" }).focus();
  await page.locator("body").click({ position: { x: 2, y: 2 } });
  await page.keyboard.press("ArrowDown");
  await expect(page.locator("tr[aria-selected=true]")).toHaveCount(1);
});

test("存储不可用时键盘仍可进入", async ({ page }) => {
  await mockCatalog(page);
  await page.addInitScript(() => Object.defineProperty(window, "localStorage", { get() { throw new Error("storage unavailable"); } }));
  await page.route("**/api/handoffs", (route) => route.fulfill({ status: 409, json: { code: "SESSION_UPDATING" } }));
  await page.goto("/");
  await expect(page.getByText("18 个项目", { exact: true })).toBeVisible();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("alert")).toContainText("会话正在更新");
});

test("最近访问与成功跳转", async ({ page }) => {
  await mockCatalog(page);
  await page.addInitScript((key) => localStorage.setItem("gdds-directory-recent", JSON.stringify([key, "deleted"])), projects[0].device_key);
  await page.route("**/api/handoffs", (route) => route.fulfill({ json: { gateway_url: "http://127.0.0.1:5173/#gdds-handoff=fixture" } }));
  await page.goto("/");
  await expect(page.locator(".recent .chip")).toHaveCount(1);
  await page.locator(".recent .chip").click();
  await expect.poll(() => page.evaluate(() => location.hash.startsWith("#gdds-handoff="))).toBe(true);
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem("gdds-directory-recent") || "[]") as string[]);
  expect(saved).toEqual([projects[0].device_key]);
});

for (const [code, message] of [["DEVICE_NOT_FOUND", "该设备已不在目录中"], ["DEVICE_NOT_PROVISIONED", "尚未在网关系统开通"], ["SESSION_EXPIRED", "会话已过期"], ["SESSION_UPDATING", "会话正在更新"]]) {
  test(`跳转错误 ${code}`, async ({ page }) => {
    await mockCatalog(page);
    await page.route("**/api/handoffs", (route) => route.fulfill({ status: 409, json: { code, message: "error" } }));
    await page.goto("/");
    await page.getByRole("button", { name: "进入提交树" }).first().click();
    await expect(page.getByRole("alert")).toContainText(message);
    expect(await page.evaluate(() => location.hash)).toBe("");
  });
}

test("未开通设备不可进入，加载错误可重试", async ({ page }) => {
  let first = true;
  await page.route("**/api/catalog", (route) => {
    if (first) { first = false; return route.fulfill({ status: 500, json: { code: "ERROR" } }); }
    return route.fulfill({ json: { catalog_version: "test", imported_at: "", projects } });
  });
  await page.goto("/");
  await expect(page.getByText("目录加载失败")).toBeVisible();
  await page.getByRole("button", { name: "重试" }).click();
  await expect(page.getByRole("button", { name: /未开通/ })).toBeDisabled();
});
