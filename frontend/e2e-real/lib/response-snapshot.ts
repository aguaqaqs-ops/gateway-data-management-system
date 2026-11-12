import type { Page, Route } from "@playwright/test";
import { createHash } from "node:crypto";

interface Identity { token: string; businessProjectId: string; gatewayDeviceExternalKey: string }
export interface ResponseSnapshot {
  readonly requestUrl: string;
  readonly requestBody: string | null;
  readonly capturedAt: number;
  status(): number;
  headers(): Record<string, string>;
  body(): Promise<Buffer>;
  text(): Promise<string>;
  json(): Promise<unknown>;
}

/** Copy one real HTTP response before delivering it to the browser. A response
 * event alone cannot prevent the product's immediate full-document navigation
 * from racing a CDP getResponseBody call. No alternate request, URL, identity,
 * redirect or retry is used; this only buffers the selected response delivery.
 */
export async function captureResponse(
  page: Page, identity: Identity, method: "GET" | "POST", pathname: RegExp, timeout = 300_000,
) {
  const actor = { ...identity };
  const deviceKey = createHash("sha256").update(actor.gatewayDeviceExternalKey).digest("hex");
  let claimed = false;
  let settled = false;
  let complete: (result: { snapshot: ResponseSnapshot } | { error: unknown }) => void;
  const result = new Promise<{ snapshot: ResponseSnapshot } | { error: unknown }>((resolve) => { complete = resolve; });
  const match = (url: URL) => pathname.test(url.pathname);
  const closed = () => finish({ error: new Error("response snapshot page closed before capture") });
  const finish = (value: { snapshot: ResponseSnapshot } | { error: unknown }) => {
    if (settled) return;
    settled = true;
    clearTimeout(timer);
    page.off("close", closed);
    complete(value);
  };
  const handler = async (route: Route) => {
    if (claimed || route.request().method() !== method) return route.fallback();
    claimed = true;
    try {
      const request = route.request();
      const headers = request.headers();
      if (headers.authorization !== `Bearer ${actor.token}` || headers["x-gateway-device-key"] !== deviceKey) {
        throw new Error("response snapshot request identity changed");
      }
      const response = await route.fetch({ timeout, maxRedirects: 0, maxRetries: 0 });
      const bytes = Buffer.from(await response.body());
      if (settled) return route.abort("failed");
      const status = response.status();
      const responseHeaders = response.headers();
      const snapshot: ResponseSnapshot = {
        requestUrl: request.url(), requestBody: request.postData(), capturedAt: Date.now(),
        status: () => status, headers: () => ({ ...responseHeaders }),
        body: async () => Buffer.from(bytes), text: async () => bytes.toString("utf8"),
        json: async () => JSON.parse(bytes.toString("utf8")) as unknown,
      };
      // APIResponse caches its body; fulfill preserves the actual status/headers
      // and cached bytes. The browser cannot parse it or navigate before this.
      await route.fulfill({ response });
      finish({ snapshot });
    } catch (error) {
      finish({ error });
      // Keep the original upstream/capture error, including abort failure details
      // in Playwright's trace. Never replace it with an empty/mocked response.
      await route.abort("failed");
    } finally {
      await page.unroute(match, handler);
    }
  };
  const timer = setTimeout(() => {
    finish({ error: new Error(`response snapshot timed out: ${method} ${pathname.source}`) });
    void page.unroute(match, handler);
  }, timeout);
  page.once("close", closed);
  await page.route(match, handler);
  return {
    async read(): Promise<ResponseSnapshot> {
      const value = await result;
      if ("error" in value) throw value.error;
      if (identity.token !== actor.token || identity.businessProjectId !== actor.businessProjectId
        || identity.gatewayDeviceExternalKey !== actor.gatewayDeviceExternalKey) throw new Error("response snapshot consumer identity changed");
      return value.snapshot;
    },
    async dispose() {
      finish({ error: new Error("response snapshot disposed before capture") });
      await page.unroute(match, handler);
    },
  };
}
