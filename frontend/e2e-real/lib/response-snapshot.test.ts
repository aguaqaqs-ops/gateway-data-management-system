// @vitest-environment node
import { EventEmitter } from "node:events";
import { createHash } from "node:crypto";
import type { Page, Route } from "@playwright/test";
import { describe, expect, it, vi } from "vitest";
import { captureResponse } from "./response-snapshot";

const actor = { token: "test-snapshot", businessProjectId: "project", gatewayDeviceExternalKey: "device" };
const requestPath = "/v1/history-compares";
function fixture(body: () => Promise<Buffer>, status = 202) {
  const events = new EventEmitter();
  let handler: (route: Route) => Promise<void>;
  const page = { once: events.once.bind(events), off: events.off.bind(events),
    route: vi.fn(async (_match, callback) => { handler = callback; }), unroute: vi.fn(async () => {}) } as unknown as Page;
  const responseHeaders = { "content-type": "application/json", "content-length": "23", etag: '"fixture-etag"' };
  const response = { status: () => status, headers: () => responseHeaders, body };
  const requestHeaders = { authorization: `Bearer ${actor.token}`, "x-gateway-device-key": createHash("sha256").update(actor.gatewayDeviceExternalKey).digest("hex") };
  const route = { request: () => ({ method: () => "POST", url: () => "http://gateway" + requestPath,
    headers: () => requestHeaders, postData: () => '{"nodes":["original"]}' }),
    fetch: vi.fn(async () => response), fulfill: vi.fn(async () => {}), abort: vi.fn(async () => {}), fallback: vi.fn(async () => {}) };
  return { page, events, route, response, requestHeaders, invoke: () => handler(route as unknown as Route) };
}

describe("HTTP response snapshot before browser delivery", () => {
  it("copies complete real bytes before fulfill and retains original request/status/headers", async () => {
    let release: (bytes: Buffer) => void;
    const body = new Promise<Buffer>((resolve) => { release = resolve; });
    const f = fixture(() => body);
    const observed = await captureResponse(f.page, actor, "POST", /\/history-compares$/);
    const running = f.invoke();
    await Promise.resolve();
    expect(f.route.fulfill).not.toHaveBeenCalled();
    release(Buffer.from('{"operation_id":"op-1"}'));
    await running;
    const snapshot = await observed.read();
    expect(f.route.fetch).toHaveBeenCalledExactlyOnceWith({ timeout: 300_000, maxRedirects: 0, maxRetries: 0 });
    expect(f.route.fulfill).toHaveBeenCalledExactlyOnceWith({ response: f.response });
    expect(snapshot.status()).toBe(202);
    expect(snapshot.headers()).toEqual(f.response.headers());
    expect(snapshot.requestUrl).toBe("http://gateway" + requestPath);
    expect(snapshot.requestBody).toBe('{"nodes":["original"]}');
    expect(await snapshot.json()).toEqual({ operation_id: "op-1" });
    const bytes = await snapshot.body(); bytes.fill(0);
    expect(await snapshot.json()).toEqual({ operation_id: "op-1" });
    expect(f.events.listenerCount("close")).toBe(0);
  });

  it.each(["", "{bad-json"])("preserves malformed/missing JSON as a parse error: %j", async (body) => {
    const f = fixture(async () => Buffer.from(body));
    const observed = await captureResponse(f.page, actor, "POST", /\/history-compares$/);
    await f.invoke();
    const snapshot = await observed.read();
    expect(snapshot.status()).toBe(202);
    await expect(snapshot.json()).rejects.toBeInstanceOf(SyntaxError);
    expect(await snapshot.text()).toBe(body);
  });

  it("preserves permission denial and its original error code", async () => {
    const f = fixture(async () => Buffer.from('{"code":"SCOPE_FORBIDDEN"}'), 403);
    const observed = await captureResponse(f.page, actor, "POST", /\/history-compares$/);
    await f.invoke();
    const snapshot = await observed.read();
    expect(snapshot.status()).toBe(403);
    expect(await snapshot.json()).toEqual({ code: "SCOPE_FORBIDDEN" });
  });

  it.each(["upstream", "body", "delivery"])("propagates the original %s exception without retry or fake response", async (where) => {
    const original = new Error("original " + where + " failure");
    const f = fixture(async () => { if (where === "body") throw original; return Buffer.from("{}"); });
    if (where === "upstream") f.route.fetch.mockRejectedValue(original);
    if (where === "delivery") f.route.fulfill.mockRejectedValue(original);
    const observed = await captureResponse(f.page, actor, "POST", /\/history-compares$/);
    await f.invoke();
    await expect(observed.read()).rejects.toBe(original);
    expect(f.route.fetch).toHaveBeenCalledTimes(1);
    expect(f.route.abort).toHaveBeenCalledExactlyOnceWith("failed");
  });

  it("rejects another request identity before contacting the server", async () => {
    const f = fixture(async () => Buffer.from("{}"));
    f.requestHeaders.authorization = "Bearer another-session";
    const observed = await captureResponse(f.page, actor, "POST", /\/history-compares$/);
    await f.invoke();
    await expect(observed.read()).rejects.toThrow("request identity changed");
    expect(f.route.fetch).not.toHaveBeenCalled();
  });

  it("does not reuse a captured response under a changed consumer identity", async () => {
    const identity = { ...actor };
    const f = fixture(async () => Buffer.from("{}"));
    const observed = await captureResponse(f.page, identity, "POST", /\/history-compares$/);
    await f.invoke();
    identity.gatewayDeviceExternalKey = "different-device";
    await expect(observed.read()).rejects.toThrow("consumer identity changed");
  });

  it("cancels a pending capture on page close instead of leaking its timer", async () => {
    const f = fixture(async () => Buffer.from("{}"));
    const observed = await captureResponse(f.page, actor, "POST", /\/history-compares$/);
    f.events.emit("close");
    await expect(observed.read()).rejects.toThrow("page closed before capture");
    await observed.dispose();
  });
});
