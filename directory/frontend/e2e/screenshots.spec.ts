import { createHash } from "node:crypto";
import { expect, test } from "@playwright/test";
import type { Locator, Page } from "@playwright/test";
import { mockCatalog, projects } from "./fixtures";

const output = process.env.GDDS_DIRECTORY_SCREENSHOT_DIR;
const states = ["browse", "search", "unprovisioned", "handoff-error", "empty"] as const;

async function capture(page: Page, path: string): Promise<void> {
  const png = await page.screenshot({ path, animations: "disabled" });
  console.log(`screenshot_path=${path} sha256=${createHash("sha256").update(png).digest("hex")}`);
}

async function expectReason(reason: Locator, visible: boolean): Promise<void> {
  await expect.poll(() => reason.evaluate((node) => {
    const style = getComputedStyle(node, "::after");
    return { content: style.content, visibility: style.visibility, opacity: style.opacity };
  })).toEqual({
    content: '"该设备尚未在网关系统开通"',
    visibility: visible ? "visible" : "hidden",
    opacity: visible ? "1" : "0"
  });
}

for (const state of states) {
  for (const width of [1280, 1920]) {
    test(`@screenshots ${state} ${width}`, async ({ page }) => {
      if (!output || !output.startsWith("/")) throw new Error("GDDS_DIRECTORY_SCREENSHOT_DIR must be an absolute directory");
      await page.setViewportSize({ width, height: 800 });
      await mockCatalog(page, state === "empty");
      if (state !== "empty") {
        await page.addInitScript((keys) => localStorage.setItem("gdds-directory-recent", JSON.stringify(keys)),
          [projects[3], projects[8], projects[17], projects[14]].map((project) => project.device_key));
      }
      if (state === "handoff-error") {
        await page.route("**/api/handoffs", (route) => route.fulfill({ status: 409, json: { code: "SESSION_EXPIRED", message: "expired" } }));
      }
      await page.goto(state === "empty" ? "/" : "/?r1=%E6%B1%9F%E8%8B%8F&r2=%E8%8B%8F%E5%B7%9E");
      if (state === "empty") await expect(page.getByText("目录尚未导入")).toBeVisible();
      else {
        await expect(page.getByText("共 14 个项目")).toBeVisible();
        await expect(page.getByLabel("筛选地区", { exact: true })).toBeVisible();
        await expect(page.getByLabel("地区内筛选项目", { exact: true })).toBeVisible();
        await expect(page.locator(".recent .chip")).toHaveCount(4);
        await expect(page.locator(".recent .chip").first()).toContainText("城南");
        expect(await page.locator(".recent").evaluate((node) => {
          const first = node.querySelector(".chip")?.getBoundingClientRect();
          const label = node.querySelector(".muted")?.getBoundingClientRect();
          const bounds = node.getBoundingClientRect();
          return !!first && !!label && label.left >= bounds.left && first.left >= label.right
            && first.right <= bounds.right && first.top >= bounds.top && first.bottom <= bounds.bottom;
        })).toBe(true);
      }
      if (state === "search") {
        await page.getByLabel("搜索项目").fill("cn");
        await expect(page.getByText("共 3 个项目")).toBeVisible();
        await expect(page.getByRole("columnheader", { name: "地区", exact: true })).toBeVisible();
        await expect(page.getByRole("cell", { name: "浙江 / 宁波", exact: true })).toBeVisible();
      }
      if (state === "unprovisioned") {
        const button = page.getByRole("button", { name: /未开通/ });
        const reason = button.locator("..");
        await expect(button).toBeDisabled();
        await expect(reason).toHaveAttribute("title", "该设备尚未在网关系统开通");
        await expectReason(reason, false);
        await reason.hover();
        await expectReason(reason, true);
        // Keep the gate's ten-file set: hover at 1280, keyboard focus at 1920.
        // Both triggers are independently checked at both widths.
        if (width === 1280) {
          console.log(`unprovisioned_trigger=hover width=${width}`);
          await capture(page, `${output}/${state}-${width}.png`);
        }

        // Clear hover, then use the product's arrow-key selection, not DOM focus injection.
        await page.locator("body").click({ position: { x: 2, y: 2 } });
        await expectReason(reason, false);
        const index = await page.locator("tbody tr").evaluateAll((rows) => rows.findIndex((row) => row.querySelector(".unavailable")));
        expect(index).toBeGreaterThanOrEqual(0);
        for (let step = 0; step <= index; step += 1) await page.keyboard.press("ArrowDown");
        const row = button.locator("ancestor::tr");
        await expect(row).toBeFocused();
        await expect(row).toHaveAttribute("aria-selected", "true");
        expect(await row.evaluate((node) => node.matches(":focus-visible"))).toBe(true);
        expect(await reason.evaluate((node) => node.matches(":hover"))).toBe(false);
        await expect(button).toBeDisabled();
        await expectReason(reason, true);
        if (width === 1920) {
          console.log(`unprovisioned_trigger=keyboard-focus width=${width}`);
          await capture(page, `${output}/${state}-${width}.png`);
        }
        return;
      }
      if (state === "handoff-error") {
        await page.getByRole("button", { name: "进入提交树" }).first().click();
        await expect(page.getByRole("alert")).toContainText("会话已过期");
        const scrollport = page.locator(".table-wrap");
        await expect.poll(() => scrollport.evaluate((node) => node.scrollTop)).toBe(0);
        await scrollport.hover();
        await page.mouse.wheel(0, 800);
        // A partly visible row at the initial scroll boundary must be fully reachable.
        // Visibility alone would also pass for a clipped row, so check the geometry.
        await expect.poll(() => scrollport.evaluate((node) => {
          const last = node.querySelector("tbody tr:last-child");
          const footer = node.parentElement?.querySelector(".card-foot");
          const header = node.querySelector("thead");
          if (!last || !footer || !header) return false;
          const viewport = node.getBoundingClientRect();
          const row = last.getBoundingClientRect();
          return node.scrollTop > 0 && node.scrollHeight - node.clientHeight - node.scrollTop <= 1
            && row.top >= viewport.top + header.getBoundingClientRect().height
            && row.bottom <= viewport.bottom && viewport.bottom <= footer.getBoundingClientRect().top;
        })).toBe(true);
        await expect(page.getByRole("alert")).toContainText("会话已过期");
        await expect(page.locator(".card-foot")).toBeInViewport({ ratio: 1 });
      }
      await capture(page, `${output}/${state}-${width}.png`);
    });
  }
}
