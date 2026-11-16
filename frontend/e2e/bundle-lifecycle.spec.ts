import { expect, test, type Page } from "./guard";
import { readFile } from "node:fs/promises";
import { captureBundleDownloads } from "../e2e-real/lib/bundle-observer";
import { consumePreviewBundle } from "../e2e-real/lib/consume-bundle";
import { assertBundleConsumerCriteria } from "../e2e-real/lib/consumer-criteria";
import { INITIAL_ONLY_HISTORY, WORKSPACE_ALREADY_EXISTS, testPreviewResult } from "../src/features/dev/simulated-api";
import type { GatewaySession } from "../src/features/api/session";

const identity = { token: "test-lifecycle", businessProjectId: "project-lifecycle", gatewayDeviceExternalKey: "device-lifecycle" };
const workspaceId = "ws-lifecycle";
async function install(page: Page, fixtures: Record<string, string>) {
  const bundles = new Map<string, { body: Buffer; digest: string }>();
  for (const [id, name] of Object.entries(fixtures)) {
    const body = await readFile(`src/test/fixtures/generated/${name}.tar`);
    const size = Number.parseInt(body.subarray(124, 136).toString().replace(/\0.*$/, "").trim(), 8);
    bundles.set(id, { body, digest: (JSON.parse(body.subarray(512, 512 + size).toString()) as { bundle_digest: string }).bundle_digest });
  }
  const unexpected: string[] = [];
  let downloads = 0;
  await page.route("**/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/v1/workspaces" && route.request().method() === "POST") return route.fulfill({ json: {
      ...WORKSPACE_ALREADY_EXISTS.body, workspace_id: workspaceId, business_project_id: identity.businessProjectId,
      gateway_device_external_key: identity.gatewayDeviceExternalKey, active_submission_id: null, active_preview_operation_id: null, active_submit_attempt_id: null,
      current_preview_result_id: null, current_upload_revision_id: null,
    } });
    if (path === "/v1/history") return route.fulfill({ json: INITIAL_ONLY_HISTORY });
    const match = /^\/v1\/workspaces\/ws-lifecycle\/preview-results\/([^/]+)(\/bundle)?$/.exec(path);
    const bundle = match ? bundles.get(match[1]) : undefined;
    if (match && bundle) {
      if (match[2]) {
        downloads += 1;
        return route.fulfill({ body: bundle.body, headers: { "Content-Type": "application/x-tar", "Content-Length": String(bundle.body.length), ETag: `"${bundle.digest}"` } });
      }
      return route.fulfill({ json: { ...testPreviewResult(bundle.digest), workspace_id: workspaceId,
        preview_result_id: match[1], operation_id: "op-" + match[1], upload_revision_id: "upload-" + match[1] } });
    }
    unexpected.push(path);
    return route.fulfill({ status: 404, json: { code: "UNEXPECTED_REQUEST", message: "missing lifecycle fixture" } });
  });
  return { downloads: () => downloads, unexpected };
}
function previewPath(id: string) { return `/v1/workspaces/${workspaceId}/preview-results/${id}`; }
async function visit(page: Page, id: string) {
  const hash = Buffer.from(JSON.stringify({ v: 1, token: identity.token, business_project_id: identity.businessProjectId,
    gateway_device_external_key: identity.gatewayDeviceExternalKey, display: { region1: "a", region2: "b", project_name: "c", station_code: "d" }, return_url: "https://directory.test" })).toString("base64url");
  await page.goto(`/?page=compare&mode=PREVIEW&workspaceId=${workspaceId}&previewResultId=${id}#gdds-handoff=${hash}`);
  await expect(page.locator("section.comparison-content")).toBeVisible();
}
function consume(page: Page, observation: ReturnType<typeof captureBundleDownloads>, id: string, view: "grid" | "replacement" = "grid") {
  return consumePreviewBundle(page, observation, { workspaceId, previewId: id, operationId: "op-" + id,
    uploadRevisionId: "upload-" + id, view, readPreview: () => page.evaluate(async (path) => {
      const session = window.__gatewaySession as GatewaySession;
      const response = await fetch(path, { headers: { Authorization: `Bearer ${session.accessToken}`, "X-Gateway-Device-Key": session.deviceRouteKey } });
      return { status: response.status, body: await response.json() };
    }, previewPath(id)) });
}

// These are actual Chromium responses and full document navigations. They use
// the exact consumer shared by J1/J2, generic upload and t1, without a backend.
test("J1/J2 consumer keeps a first download across navigation and reuses authorized C retransmission", async ({ page }) => {
  const routes = await install(page, { a: "preview-full", c: "preview-full" });
  const first = captureBundleDownloads(page, identity);
  try {
    await visit(page, "a");
    await expect(page.locator(".grid-frame").first()).toBeVisible();
    await page.goto("about:blank");
    await visit(page, "a");
    const downloaded = await consume(page, first, "a");
    expect(downloaded.source).toBe("download");
    expect(downloaded.downloadCount).toBe(1);
    await assertBundleConsumerCriteria(downloaded.bundle, "lifecycle J1/J2 first download");
    expect(routes.downloads()).toBe(1);
    first.dispose();
    const retransmission = captureBundleDownloads(page, identity);
    try {
      await visit(page, "c");
      const cached = await consume(page, retransmission, "c");
      expect(cached.source).toBe("cache");
      expect(cached.bundle).toBe(downloaded.bundle);
      expect(cached.etag).toBeNull();
      expect(cached.downloadCount).toBe(0);
      await assertBundleConsumerCriteria(cached.bundle, "lifecycle J1 C retransmission");
      expect(routes.downloads()).toBe(1);
    } finally { retransmission.dispose(); }
    expect(routes.unexpected).toEqual([]);
  } finally { first.dispose(); }
});

test("J1 replacement consumer uses replacement readiness across navigation", async ({ page }) => {
  const routes = await install(page, { replacement: "preview-replacement" });
  const observation = captureBundleDownloads(page, identity);
  try {
    await visit(page, "replacement");
    await expect(page.locator("section.replacement-browser")).toBeVisible();
    await page.goto("about:blank");
    await visit(page, "replacement");
    const evidence = await consume(page, observation, "replacement", "replacement");
    expect(evidence.source).toBe("download");
    expect(evidence.downloadCount).toBe(1);
    await assertBundleConsumerCriteria(evidence.bundle, "lifecycle J1 replacement");
    expect(routes.downloads()).toBe(1);
    expect(routes.unexpected).toEqual([]);
  } finally { observation.dispose(); }
});

test("t1 step1 and step4 consumers validate new digests after document navigation", async ({ page }) => {
  const routes = await install(page, { step1: "preview-modified-only", step4: "preview-full" });
  const digests: string[] = [];
  for (const id of ["step1", "step4"]) {
    const observation = captureBundleDownloads(page, identity);
    try {
      await visit(page, id);
      await expect(page.locator(".grid-frame").first()).toBeVisible();
      await page.goto("about:blank");
      await visit(page, id);
      const evidence = await consume(page, observation, id);
      expect(evidence.source).toBe("download");
      expect(evidence.downloadCount).toBe(1);
      await assertBundleConsumerCriteria(evidence.bundle, `lifecycle t1 ${id}`);
      digests.push(evidence.bundle.bundleDigest);
    } finally { observation.dispose(); }
  }
  expect(digests[0]).not.toBe(digests[1]);
  expect(routes.downloads()).toBe(2);
  expect(routes.unexpected).toEqual([]);
});
