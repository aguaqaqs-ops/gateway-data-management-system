import { test as base, expect } from "@playwright/test";
import { createHash } from "node:crypto";
export { expect } from "@playwright/test";
export type { Page, Request, Route } from "@playwright/test";
export const test = base.extend<{ deviceHeaderGuard: void }>({
  deviceHeaderGuard: [async ({ page }, use) => {
    const checks: Promise<void>[] = [];
    page.on("request", (request) => {
      if (!new URL(request.url()).pathname.startsWith("/v1/")) return;
      checks.push((async () => {
        const headers = await request.headersArray();
        const keys = headers.filter((item) => item.name.toLowerCase() === "x-gateway-device-key");
        expect(keys, "ordinary request needs exactly one device header").toHaveLength(1);
        const session = await page.evaluate(() => window.__gatewaySession);
        expect(session?.gatewayDeviceExternalKey, "request needs an injected device session").toBeTruthy();
        expect(keys[0]?.value).toBe(createHash("sha256").update(session!.gatewayDeviceExternalKey).digest("hex"));
      })());
    });
    await use();
    await Promise.all(checks);
  }, { auto: true }],
});
