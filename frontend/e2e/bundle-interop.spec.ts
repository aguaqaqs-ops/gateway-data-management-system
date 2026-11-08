import { expect, test, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";

const FIXTURE_DIR = "src/test/fixtures/backend-interop/be-d-0ba45e5ef8";
const OPFS_ROOT = "gateway-comparison-bundles-v1";
const WORKSPACE_ID = "ws-1";
const PREVIEW_RESULT_ID = "preview-interop-1";

interface InteropIndex {
  bundle_digest: string;
  content_length: number;
  files: Array<{ path: string; length: number; sha256: string }>;
  ordinary_artifacts: Array<{ logical_path: string; size_bytes: number; raw_sha256: string }>;
}

interface InstalledFile {
  size: number;
  sha256: string;
}

type BundleMode = "full" | "truncated" | "corrupted";

const WORKSPACE_RESPONSE = {
  workspace_id: WORKSPACE_ID,
  business_project_id: "bp-1",
  gateway_device_external_key: "device-1",
  active_submission_id: null,
  active_submit_attempt_id: null,
  current_preview_result_id: PREVIEW_RESULT_ID,
  current_upload_revision_id: null,
  generation: 1,
  optimistic_version: 1,
  state: "ACTIVE",
  created_at: "2026-11-08T09:00:00Z",
  updated_at: "2026-11-08T09:00:00Z",
};

async function readFixture(name: string): Promise<Buffer> {
  return readFile(`${FIXTURE_DIR}/${name}`);
}

function corruptParquetByte(tar: Buffer): Buffer {
  const corrupted = Buffer.from(tar);
  // rows.parquet member header starts at 16896; its 741-byte payload starts at 17408.
  corrupted[17408 + 100] = corrupted[17408 + 100]! ^ 0xff;
  return corrupted;
}

function hexDigest(digest: string): string {
  return digest.replace(/^sha256:/, "");
}

function expectedInstalledFiles(index: InteropIndex): Map<string, InstalledFile> {
  const expected = new Map<string, InstalledFile>();
  for (const file of index.files) {
    if (file.path === "manifest.json" || file.path === "artifact-closure.json") {
      expected.set(file.path, { size: file.length, sha256: file.sha256 });
    }
  }
  for (const artifact of index.ordinary_artifacts) {
    expected.set(artifact.logical_path, {
      size: artifact.size_bytes,
      sha256: artifact.raw_sha256.replace(/^sha256:/, ""),
    });
  }
  return expected;
}

/**
 * Installs the minimal API surface this page needs for a direct PREVIEW URL, then
 * returns a collector for any unexpected /v1 request so a missing mock fails loudly.
 */
async function installRoutes(page: Page, mode: BundleMode, tar: Buffer, index: InteropIndex): Promise<{ unexpected: string[]; bundleRequests: () => number }> {
  const unexpected: string[] = [];
  let bundleRequests = 0;

  await page.route("**/v1/**", async (route) => {
    const request = route.request();
    unexpected.push(`${request.method()} ${new URL(request.url()).pathname}`);
    await route.fulfill({
      status: 404,
      contentType: "application/problem+json",
      body: JSON.stringify({ type: "about:blank", title: "NOT_FOUND", status: 404, code: "NOT_FOUND", detail: "unexpected request" }),
    });
  });

  await page.route("**/v1/workspaces", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(WORKSPACE_RESPONSE) });
  });

  await page.route("**/v1/workspaces/*/preview-results/*/bundle", async (route) => {
    bundleRequests += 1;
    const body = mode === "full" ? tar : mode === "truncated" ? tar.subarray(0, tar.byteLength - 512) : corruptParquetByte(tar);
    await route.fulfill({
      status: 200,
      contentType: "application/x-tar",
      headers: { ETag: index.bundle_digest, "Content-Length": String(tar.byteLength) },
      body,
    });
  });

  return { unexpected, bundleRequests: () => bundleRequests };
}

function browseUrl(index: InteropIndex): string {
  const params = new URLSearchParams({
    page: "compare",
    mode: "PREVIEW",
    workspaceId: WORKSPACE_ID,
    previewResultId: PREVIEW_RESULT_ID,
    bundleDigest: index.bundle_digest,
  });
  return "/?" + params.toString();
}

async function waitForInstalledBundle(page: Page): Promise<void> {
  await expect(page.getByRole("heading", { name: "差异浏览", level: 1 })).toBeVisible();
  await page.locator(".grid-frame, .compare-error").first().waitFor({ state: "visible", timeout: 20_000 });
  const error = page.locator(".compare-error");
  if (await error.isVisible()) {
    throw new Error(`bundle browse failed: ${await error.innerText()}`);
  }
  await expect(page.locator(".grid-frame").first()).toBeVisible();
}

async function readInstalledFiles(page: Page, key: string, paths: string[]): Promise<{ files: Record<string, InstalledFile>; names: string[]; marker: { bundle_digest?: string } }> {
  return page.evaluate(async ({ rootName, key, paths }) => {
    const root = await navigator.storage.getDirectory();
    const bundles = await root.getDirectoryHandle(rootName, { create: false });
    const dir = await bundles.getDirectoryHandle(key, { create: false });
    const files: Record<string, { size: number; sha256: string }> = {};
    for (const path of paths) {
      const segments = path.split("/");
      let handle = dir;
      for (const segment of segments.slice(0, -1)) handle = await handle.getDirectoryHandle(segment, { create: false });
      const file = await (await handle.getFileHandle(segments.at(-1) ?? "", { create: false })).getFile();
      const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
      files[path] = {
        size: file.size,
        sha256: Array.from(new Uint8Array(digest)).map((byte) => byte.toString(16).padStart(2, "0")).join(""),
      };
    }
    const names: string[] = [];
    for await (const name of dir.keys()) names.push(name);
    const markerFile = await dir.getFileHandle(".complete.json", { create: false });
    const marker = JSON.parse(await (await markerFile.getFile()).text()) as { bundle_digest?: string };
    return { files, names, marker };
  }, { rootName: OPFS_ROOT, key, paths });
}

async function bundleDirectoryExists(page: Page, key: string): Promise<boolean> {
  return page.evaluate(async ({ rootName, key }) => {
    try {
      const root = await navigator.storage.getDirectory();
      const bundles = await root.getDirectoryHandle(rootName, { create: false });
      await bundles.getDirectoryHandle(key, { create: false });
      return true;
    } catch {
      return false;
    }
  }, { rootName: OPFS_ROOT, key });
}

async function expectDownloadFailure(page: Page): Promise<void> {
  await expect(page.locator(".compare-error")).toBeVisible();
  await expect(page.getByRole("alert")).toContainText(/BUNDLE_(INTEGRITY_MISMATCH|LOAD_FAILED)/);
}

test("installs the backend interop bundle into OPFS with matching sizes and digests", async ({ page }) => {
  const index = JSON.parse((await readFixture("index.json")).toString("utf8")) as InteropIndex;
  const tar = await readFixture("bundle.tar");
  expect(tar.byteLength).toBe(24_576);
  expect(tar.byteLength).toBe(index.content_length);
  const routes = await installRoutes(page, "full", tar, index);
  const key = hexDigest(index.bundle_digest);

  await page.goto(browseUrl(index));
  await waitForInstalledBundle(page);

  const expected = expectedInstalledFiles(index);
  expect(expected.size).toBe(6);
  const installed = await readInstalledFiles(page, key, Array.from(expected.keys()));
  const topLevelDirs = [...new Set([...expected.keys()].filter((path) => path.includes("/")).map((path) => path.split("/")[0] ?? ""))];
  expect(installed.names.sort()).toEqual([".complete.json", "artifact-closure.json", "manifest.json", ...topLevelDirs].sort());
  expect(installed.marker.bundle_digest).toBe(key);
  for (const [path, file] of expected) {
    expect(installed.files[path]?.size).toBe(file.size);
    expect(installed.files[path]?.sha256).toBe(file.sha256);
  }
  expect(routes.bundleRequests()).toBe(1);
  expect(routes.unexpected).toEqual([]);

  // The frontend installs tar/OPFS artifacts only; the backend reports the same
  // bundle as verified_logical_record_count === 0 because it has no RECORDS entry.
  const closure = JSON.parse((await readFixture("artifact-closure.json")).toString("utf8")) as { entries: Array<{ kind: string }> };
  expect(closure.entries.some((entry) => entry.kind === "RECORDS")).toBe(false);
  expect([...installed.names].some((name) => name.toLowerCase().includes("records"))).toBe(false);
});

test("aborts the opfs install when the bundle body is truncated", async ({ page }) => {
  const index = JSON.parse((await readFixture("index.json")).toString("utf8")) as InteropIndex;
  const tar = await readFixture("bundle.tar");
  const routes = await installRoutes(page, "truncated", tar, index);

  await page.goto(browseUrl(index));
  await expectDownloadFailure(page);
  expect(await bundleDirectoryExists(page, hexDigest(index.bundle_digest))).toBe(false);
  // ensureLocalBundle retries a BundleIntegrityError once and surfaces the second failure.
  expect(routes.bundleRequests()).toBe(2);
});

test("aborts the opfs install when a parquet member byte is corrupted", async ({ page }) => {
  const index = JSON.parse((await readFixture("index.json")).toString("utf8")) as InteropIndex;
  const tar = await readFixture("bundle.tar");
  const routes = await installRoutes(page, "corrupted", tar, index);

  await page.goto(browseUrl(index));
  await expectDownloadFailure(page);
  await expect(page.locator(".compare-error")).toContainText("BUNDLE_INTEGRITY_MISMATCH");
  expect(await bundleDirectoryExists(page, hexDigest(index.bundle_digest))).toBe(false);
  expect(routes.bundleRequests()).toBe(2);
});
