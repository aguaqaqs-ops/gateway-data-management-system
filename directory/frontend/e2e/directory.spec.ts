import { expect, test } from "@playwright/test";
import { mockCatalog, projects } from "./fixtures";

test("地区树过滤只缩小地区选项，地区内过滤复用搜索与地址状态", async ({ page }) => {
  await mockCatalog(page);
  await page.goto("/?r1=%E6%B1%9F%E8%8B%8F&r2=%E8%8B%8F%E5%B7%9E&page=2");
  const original = page.url();
  const tree = page.getByRole("navigation", { name: "地区", exact: true });
  await page.getByLabel("筛选地区", { exact: true }).fill("宁波");
  await expect(tree.getByRole("button", { name: /浙江/ })).toHaveAttribute("aria-expanded", "true");
  await expect(tree.getByRole("button", { name: /宁波/ })).toBeVisible();
  await expect(tree.getByRole("button", { name: /江苏/ })).toHaveCount(0);
  await expect(page.getByText("共 14 个项目")).toBeVisible();
  expect(page.url()).toBe(original);
  await page.getByLabel("筛选地区", { exact: true }).fill("不存在");
  await expect(tree.getByText("没有匹配的地区")).toBeVisible();
  await expect(page.getByText("共 14 个项目")).toBeVisible();
  await page.getByLabel("筛选地区", { exact: true }).fill("");
  await expect(tree.getByRole("button", { name: /苏州/ })).toHaveAttribute("aria-current", "true");
  await page.getByLabel("地区内筛选项目", { exact: true }).fill("Cn");
  await expect(page.getByLabel("搜索项目", { exact: true })).toHaveValue("Cn");
  await expect(page.getByRole("radio", { name: "仅 江苏 / 苏州" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByText("共 2 个项目")).toBeVisible();
  expect(Object.fromEntries(new URL(page.url()).searchParams)).toEqual({ r1: "江苏", r2: "苏州", q: "Cn", scope: "region" });
  await page.getByLabel("搜索项目", { exact: true }).fill("NB");
  await expect(page.getByLabel("地区内筛选项目", { exact: true })).toHaveValue("NB");
  await expect(page.getByText("共 0 个项目")).toBeVisible();
  await page.getByRole("radio", { name: "全部地区", exact: true }).click();
  await expect(page.getByText("共 1 个项目")).toBeVisible();
  await expect(page.getByLabel("地区内筛选项目", { exact: true })).toHaveCount(0);
  await page.goBack();
  await expect(page.getByLabel("地区内筛选项目", { exact: true })).toHaveValue("NB");
  await expect(page.getByText("共 0 个项目")).toBeVisible();
  await page.goForward();
  await expect(page.getByText("共 1 个项目")).toBeVisible();
});

for (const [query, hit, column, count] of [["城南", "城南", 0, 2], ["sZ-0004", "SZ-0004", 2, 1]] as const) {
  test(`搜索结果显示地区路径与直接命中高亮 ${query}`, async ({ page }) => {
    await mockCatalog(page);
    await page.goto(`/?q=${encodeURIComponent(query)}`);
    await expect(page.getByRole("columnheader", { name: "地区", exact: true })).toBeVisible();
    await expect(page.locator("tbody tr")).toHaveCount(count);
    for (const row of await page.locator("tbody tr").all()) {
      await expect(row.getByRole("cell").nth(1)).toHaveText("江苏 / 苏州");
      await expect(row.getByRole("cell").nth(column).locator("mark")).toHaveText(hit);
    }
    await page.getByLabel("搜索项目", { exact: true }).press("Escape");
    await expect(page.getByRole("columnheader", { name: "地区", exact: true })).toHaveCount(0);
    await expect(page.locator("tbody mark")).toHaveCount(0);
  });
}

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
