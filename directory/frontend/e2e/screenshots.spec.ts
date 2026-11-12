import { expect, test } from "@playwright/test";
import { mockCatalog } from "./fixtures";

const output = process.env.GDDS_DIRECTORY_SCREENSHOT_DIR;
const states = ["browse", "search", "unprovisioned", "handoff-error", "empty"] as const;

for (const state of states) {
  for (const width of [1280, 1920]) {
    test(`@screenshots ${state} ${width}`, async ({ page }) => {
      if (!output || !output.startsWith("/")) throw new Error("GDDS_DIRECTORY_SCREENSHOT_DIR must be an absolute directory");
      await page.setViewportSize({ width, height: 800 });
      await mockCatalog(page, state === "empty");
      if (state === "handoff-error") {
        await page.route("**/api/handoffs", (route) => route.fulfill({ status: 409, json: { code: "SESSION_EXPIRED", message: "expired" } }));
      }
      await page.goto(state === "empty" ? "/" : "/?r1=%E6%B1%9F%E8%8B%8F&r2=%E8%8B%8F%E5%B7%9E");
      if (state === "empty") await expect(page.getByText("目录尚未导入")).toBeVisible();
      else await expect(page.getByText("共 14 个项目")).toBeVisible();
      if (state === "search") {
        await page.getByLabel("搜索项目").fill("cn");
        await expect(page.getByText("共 3 个项目")).toBeVisible();
      }
      if (state === "unprovisioned") {
        const button = page.getByRole("button", { name: /未开通/ });
        await expect(button).toBeDisabled();
        await button.hover({ force: true });
      }
      if (state === "handoff-error") {
        await page.getByRole("button", { name: "进入提交树" }).first().click();
        await expect(page.getByRole("alert")).toContainText("会话已过期");
      }
      await page.screenshot({ path: `${output}/${state}-${width}.png`, animations: "disabled" });
    });
  }
}
