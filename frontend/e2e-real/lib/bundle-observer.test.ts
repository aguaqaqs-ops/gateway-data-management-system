// @vitest-environment node
import { EventEmitter } from "node:events";
import { readFile } from "node:fs/promises";
import type { Page, Response } from "@playwright/test";
import { describe, expect, it } from "vitest";
import { captureBundleDownloads } from "./bundle-observer";

const identity = { token: "test-only", businessProjectId: "project", gatewayDeviceExternalKey: "device" };
const requestPath = "/v1/workspaces/ws/preview-results/pr/bundle";
async function fixture() {
  const body = await readFile("src/test/fixtures/generated/preview-full.tar");
  const size = Number.parseInt(body.subarray(124, 136).toString().replace(/\0.*$/, "").trim(), 8);
  return { body, digest: (JSON.parse(body.subarray(512, 512 + size).toString()) as { bundle_digest: string }).bundle_digest };
}
function fakePage() {
  const events = new EventEmitter();
  const context = {};
  const page = { on: events.on.bind(events), off: events.off.bind(events), context: () => context,
    evaluate: async () => true } as unknown as Page;
  return { events, page };
}
function response(body: () => Promise<Buffer>, digest: string, size: number): Response {
  return { request: () => ({ method: () => "GET" }), url: () => "http://gateway" + requestPath, status: () => 200,
    headers: () => ({ "content-type": "application/x-tar", "content-length": String(size), etag: `"${digest}"` }), body } as unknown as Response;
}

describe("bundle observer preserves response lifetime and failures", () => {
  it("starts reading at the response event and consumes saved bytes after navigation", async () => {
    const { body, digest } = await fixture();
    const { events, page } = fakePage();
    const observed = captureBundleDownloads(page, identity);
    let navigated = false, reads = 0;
    events.emit("response", response(async () => { reads += 1; if (navigated) throw new Error("resource navigated away"); return body; }, digest, body.length));
    expect(reads).toBe(1);
    navigated = true;
    const result = await observed.consume({ requestPath, authorizedDigest: digest, uiReady: true, opfsComplete: true });
    expect(result.source).toBe("download");
    expect(result.downloadCount).toBe(1);
    expect(reads).toBe(1);
    observed.dispose();
    expect(events.listenerCount("response")).toBe(0);
  });

  it("propagates the original body failure even if this context already has verified cache", async () => {
    const { body, digest } = await fixture();
    const { events, page } = fakePage();
    const options = { requestPath, authorizedDigest: digest, uiReady: true, opfsComplete: true };
    const first = captureBundleDownloads(page, identity);
    events.emit("response", response(async () => body, digest, body.length));
    await first.consume(options);
    first.dispose();
    const next = captureBundleDownloads(page, identity);
    const original = new Error("original response body failure");
    events.emit("response", response(async () => { throw original; }, digest, body.length));
    await expect(next.consume(options)).rejects.toBe(original);
    next.dispose();
    expect(events.listenerCount("response")).toBe(0);
  });
});
