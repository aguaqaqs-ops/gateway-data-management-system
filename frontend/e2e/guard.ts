import { test as base } from "@playwright/test";
import { createHash } from "node:crypto";
export { expect } from "@playwright/test";
export type { Locator, Page, Request, Route } from "@playwright/test";

export const test = base.extend<{ deviceHeaderGuard: void }>({
  deviceHeaderGuard: [
    async ({ page }, use) => {
      const failures: string[] = [];
      await page.exposeBinding(
        "__checkGatewayMockHeaders",
        (_source, value: { header: string | null; device?: string }) => {
          const expected = value.device
            ? createHash("sha256").update(value.device).digest("hex")
            : null;
          if (!expected || value.header !== expected)
            failures.push(
              "ordinary mock request has missing, multiple or mismatched device header",
            );
        },
      );
      await page.addInitScript(() => {
        const original = window.fetch.bind(window);
        window.fetch = async (input, init) => {
          const path = new URL(
            input instanceof Request ? input.url : String(input),
            window.location.origin,
          ).pathname;
          if (path.startsWith("/v1/")) {
            const headers = new Headers(
              init?.headers ?? (input instanceof Request ? input.headers : undefined),
            );
            const scope = window.__gatewaySession;
            await (
              window as unknown as { __checkGatewayMockHeaders: (value: unknown) => Promise<void> }
            ).__checkGatewayMockHeaders({
              header: headers.get("X-Gateway-Device-Key"),
              device: scope?.gatewayDeviceExternalKey,
            });
          }
          return original(input, init);
        };
      });
      await use();
      if (failures.length) throw new Error(failures.join("\n"));
    },
    { auto: true },
  ],
});
