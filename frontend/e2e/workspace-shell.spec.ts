import { expect, test } from "@playwright/test";

test("打开应用显示 FE1 工作台基础与组件预览", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "网关数据工作台", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "比较工作台基础组件", level: 2 })).toBeVisible();
  await expect(page.getByRole("button", { name: "主要操作" })).toBeVisible();
  await expect(page.getByRole("button", { name: "次要操作" })).toBeVisible();
  await expect(page.getByRole("button", { name: "幽灵操作" })).toBeVisible();
  await expect(page.getByRole("button", { name: "危险操作" })).toBeVisible();
  await expect(page.getByText("请先完成上传校验")).toBeVisible();
  await expect(page.getByText("站点A_2026-11-02")).toBeVisible();
  await expect(page.getByLabel("正在加载比较结果")).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("BUNDLE_INTEGRITY_MISMATCH");
});

test("确认对话框捕获焦点并要求填写理由", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "预览退回确认" }).click();
  const dialog = page.getByRole("dialog", { name: "退回这次提交？" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "确认退回" })).toBeDisabled();
  await expect(dialog.getByText("填写理由后才能确认")).toBeVisible();
  await page.locator("#review-reason").fill("请补齐变更说明");
  await expect(dialog.getByRole("button", { name: "确认退回" })).toBeEnabled();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: "预览退回确认" })).toBeFocused();
});
