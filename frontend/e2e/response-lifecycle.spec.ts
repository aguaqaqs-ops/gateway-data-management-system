import { expect, test, type Page } from "./guard";
import { createServer, type Server } from "node:http";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { captureResponse } from "../e2e-real/lib/response-snapshot";
import { parseBundleTar } from "../e2e-real/lib/tar";
import { assertBundleConsumerCriteria } from "../e2e-real/lib/consumer-criteria";
import { HISTORY_PAGE_ONE, HISTORY_PAGE_TWO, WORKSPACE_ALREADY_EXISTS } from "../src/features/dev/simulated-api";

// A local HTTP fixture, not real-backend evidence. Requests go through Vite's
// ordinary proxy to this server; the capture helper fetches the original URL.
const identity = { token: "test-http-lifecycle", businessProjectId: "snapshot-project", gatewayDeviceExternalKey: "snapshot-device" };
const deviceKey = createHash("sha256").update(identity.gatewayDeviceExternalKey).digest("hex");
const calls: Array<{ path: string; body: string; key?: string; authorization?: string; device?: string }> = [];
let server: Server;
let sequence = 0;
let tar: Buffer;
let tarDigest: string;
const unexpected: string[] = [];

test.describe.configure({ mode: "serial" });
test.beforeAll(async () => {
  tar = await readFile("src/test/fixtures/generated/preview-full.tar");
  const manifestSize = Number.parseInt(tar.subarray(124, 136).toString().replace(/\0.*$/, "").trim(), 8);
  const manifestDigest = (JSON.parse(tar.subarray(512, 512 + manifestSize).toString()) as { bundle_digest: string }).bundle_digest;
  tarDigest = (await parseBundleTar(tar, { contentLength: String(tar.length), etag: `"${manifestDigest}"` })).bundleDigest;
  server = createServer(async (request, response) => {
    const path = new URL(request.url!, "http://fixture").pathname;
    let body = "";
    for await (const chunk of request) body += String(chunk);
    const reply = (status: number, value: unknown) => {
      const bytes = Buffer.isBuffer(value) ? value : Buffer.from(JSON.stringify(value));
      response.writeHead(status, { "Content-Type": Buffer.isBuffer(value) ? "application/x-tar" : "application/json", "Content-Length": String(bytes.length), ETag: Buffer.isBuffer(value) ? `"${tarDigest}"` : '"http-lifecycle"' });
      response.end(bytes);
    };
    if (request.headers.authorization !== `Bearer ${identity.token}` || request.headers["x-gateway-device-key"] !== deviceKey) return reply(403, { code: "SCOPE_FORBIDDEN" });
    if (request.method === "POST" && path === "/v1/workspaces") return reply(200, {
      ...WORKSPACE_ALREADY_EXISTS.body, business_project_id: identity.businessProjectId,
      gateway_device_external_key: identity.gatewayDeviceExternalKey, active_submission_id: null,
      active_preview_operation_id: null, active_submit_attempt_id: null, current_preview_result_id: null, current_upload_revision_id: null,
    });
    if (path === "/v1/history") return reply(200, { ...HISTORY_PAGE_ONE, nodes: [...HISTORY_PAGE_ONE.nodes, ...HISTORY_PAGE_TWO.nodes], next_cursor: null });
    if (request.method === "POST" && path === "/v1/history-compares") {
      sequence += 1;
      calls.push({ path, body, key: request.headers["idempotency-key"] as string,
        authorization: request.headers.authorization, device: request.headers["x-gateway-device-key"] as string });
      return reply(202, { operation_id: `history-http-${sequence}`, status: "QUEUED", replayed: false });
    }
    if (request.method === "GET" && /^\/v1\/history-compares\/history-http-\d+$/.test(path)) return reply(200, { operation_id: path.split("/").at(-1), status: "QUEUED", diagnostic: null });
    if (request.method === "POST" && /\/(upload-revisions|preview-operations)$/.test(path)) {
      calls.push({ path, body });
      return reply(path.endsWith("upload-revisions") ? 201 : 202, { operation_id: "preview-http", workspace_id: "ws-http", upload_revision_id: "upload-http" });
    }
    if (path.endsWith("/bundle")) { calls.push({ path, body }); return reply(200, tar); }
    unexpected.push(path);
    return reply(404, { code: "UNEXPECTED_FIXTURE_REQUEST" });
  });
  await new Promise<void>((resolve, reject) => { server.once("error", reject); server.listen(8000, "127.0.0.1", resolve); });
});
test.afterAll(async () => { await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve())); });
async function session(page: Page) {
  await page.addInitScript((actor) => {
    window.__gatewaySession = { accessToken: actor.token, businessProjectId: actor.businessProjectId, gatewayDeviceExternalKey: actor.gatewayDeviceExternalKey };
  }, identity);
}

test("History POST 202 snapshot survives immediate product navigation repeatedly", async ({ page }) => {
  test.setTimeout(120_000);
  await session(page);
  const navigations: number[] = [];
  page.on("framenavigated", (frame) => {
    if (frame === page.mainFrame() && /operationId=history-http-/.test(frame.url())) navigations.push(Date.now());
  });
  const start = calls.length;
  for (let attempt = 0; attempt < 20; attempt += 1) {
    await page.goto("/?page=workspace");
    await expect(page.getByRole("heading", { name: /组态树/ })).toBeVisible();
    for (const label of ["初始基线", "归档基线 1"]) {
      await page.getByRole("checkbox", { name: `加入比较：${label}` }).check();
    }
    const capture = await captureResponse(page, identity, "POST", /\/history-compares$/, 15_000);
    try {
      await page.locator(".compare-tray").getByRole("button", { name: "历史比较", exact: true }).click();
      await expect(page).toHaveURL(new RegExp(`operationId=history-http-${attempt + 1}(?:&|$)`));
      await expect(page.locator('section[aria-label="历史比较结果抽屉"]')).toBeVisible();
      // Deliberately consume only after actual product document navigation.
      const snapshot = await capture.read();
      expect(snapshot.status()).toBe(202);
      expect(snapshot.headers()["content-type"]).toBe("application/json");
      expect(snapshot.headers().etag).toBe('"http-lifecycle"');
      expect(snapshot.headers()["content-length"]).toBe(String((await snapshot.body()).length));
      expect(await snapshot.json()).toEqual({ operation_id: `history-http-${attempt + 1}`, status: "QUEUED", replayed: false });
      expect(snapshot.capturedAt).toBeLessThanOrEqual(navigations.at(-1)!);
      const sent = calls.at(-1)!;
      expect(snapshot.requestBody).toBe(sent.body);
      expect(JSON.parse(sent.body)).toEqual({ nodes: [
        { ref_kind: "baseline_node", ref_id: "fe2a-history-ref-0" },
        { ref_kind: "baseline_node", ref_id: "fe2a-history-ref-1" },
      ] });
      expect(sent.key).toBeTruthy();
      expect(sent.authorization).toBe(`Bearer ${identity.token}`);
      expect(sent.device).toBe(deviceKey);
    } finally { await capture.dispose(); }
  }
  expect(navigations).toHaveLength(20);
  expect(calls.length - start).toBe(20); // No replay/new POST to repair lost evidence.
  expect(unexpected).toEqual([]);
});

test("upload/preview acceptance and a required fresh recovery bundle remain readable after navigation", async ({ page }) => {
  await session(page);
  await page.goto("/?page=workspace");
  const cases = [
    { path: "/v1/workspaces/ws-http/upload-revisions", method: "POST" as const, status: 201 },
    { path: "/v1/workspaces/ws-http/preview-operations", method: "POST" as const, status: 202 },
    { path: "/v1/workspaces/ws-http/preview-results/pr-http/bundle", method: "GET" as const, status: 200 },
  ];
  for (const [index, item] of cases.entries()) {
    const before = calls.length;
    const captured = await captureResponse(page, identity, item.method, new RegExp(item.path + "$"));
    try {
      await page.evaluate(async ({ item, deviceKey, token, index }) => {
        const response = await fetch(item.path, { method: item.method, headers: { Authorization: `Bearer ${token}`, "X-Gateway-Device-Key": deviceKey, "Content-Type": "application/json" }, body: item.method === "POST" ? '{"original":"body"}' : undefined });
        await response.arrayBuffer();
        window.location.assign(`/?page=workspace&snapshotMarker=${index}`);
      }, { item, deviceKey, token: identity.token, index });
      await expect(page).toHaveURL(new RegExp(`snapshotMarker=${index}$`));
      const snapshot = await captured.read();
      expect(snapshot.status()).toBe(item.status);
      expect(calls.length - before).toBe(1);
      if (item.method === "GET") {
        const bundle = await parseBundleTar(await snapshot.body(), { contentLength: snapshot.headers()["content-length"], etag: snapshot.headers().etag });
        await assertBundleConsumerCriteria(bundle, "fresh R3 HTTP recovery after navigation");
        expect(await snapshot.body()).toEqual(tar);
      } else expect(await snapshot.json()).toMatchObject({ operation_id: "preview-http", upload_revision_id: "upload-http" });
    } finally { await captured.dispose(); }
  }
  expect(unexpected).toEqual([]);
});
