import { expect, test } from "@playwright/test";

test("打开应用显示工作台骨架页", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "网关数据工作台", level: 1 })).toBeVisible();
});
