import { expect, test, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";

const FIXTURE_DIR = "src/test/fixtures/backend-interop/be-d-0ba45e5ef8";
const OPFS_ROOT = "gateway-comparison-bundles-v1";
const WORKSPACE_ID = "ws-1";
const PREVIEW_RESULT_ID = "preview-interop-1";

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

interface TarMember {
  path: string;
  offset: number;
  size: number;
  sha256: string;
}

interface TarBundle {
  tar: Buffer;
  bundleDigest: string;
  contractVersion: string;
  members: Map<string, TarMember>;
}

function hexDigest(digest: string): string {
  return digest.replace(/^sha256:/, "");
}

function sha256(bytes: Buffer): string {
  return createHash("sha256").update(bytes).digest("hex");
}

/**
 * Reads a generated bundle tar without the product parser: the e2e assertion
 * must know the expected members (sizes and digests) independently of the code
 * under test. Long paths are emitted as PAX extended headers by the fixture
 * builder, so `x` entries are folded into the next member.
 */
async function readGeneratedBundle(name: string): Promise<TarBundle> {
  const tar = await readFile(`src/test/fixtures/generated/${name}.tar`);
  const members = new Map<string, TarMember>();
  let offset = 0;
  let pendingPath: string | null = null;
  while (offset + 512 <= tar.byteLength) {
    const header = tar.subarray(offset, offset + 512);
    if (header.every((byte) => byte === 0)) break;
    const size = Number.parseInt(header.subarray(124, 136).toString("ascii").replace(/\0.*$/, "").trim(), 8);
    const type = String.fromCharCode(header[156] ?? 48);
    const nameField = header.subarray(0, 100).toString("utf8").replace(/\0.*$/, "");
    const prefix = header.subarray(345, 500).toString("utf8").replace(/\0.*$/, "");
    const payload = tar.subarray(offset + 512, offset + 512 + size);
    offset += 512 + Math.ceil(size / 512) * 512;
    if (type === "x") {
      const record = payload.toString("utf8");
      const match = /(?:^|\n)\d+ path=([^\n]+)\n/.exec(record);
      if (!match?.[1]) throw new Error("PAX header without a path record");
      pendingPath = match[1];
      continue;
    }
    const path = pendingPath ?? (prefix ? `${prefix}/${nameField}` : nameField);
    pendingPath = null;
    members.set(path, { path, offset: offset - Math.ceil(size / 512) * 512 - 512 + 512, size, sha256: sha256(payload) });
  }
  const manifestBytes = tar.subarray(512, 512 + (members.get("manifest.json")?.size ?? 0));
  const manifest = JSON.parse(manifestBytes.toString("utf8")) as { bundle_digest: string; bundle_contract_version: string };
  return { tar, bundleDigest: manifest.bundle_digest, contractVersion: manifest.bundle_contract_version, members };
}

function expectedInstalledFiles(bundle: TarBundle): Map<string, InstalledFile> {
  const expected = new Map<string, InstalledFile>();
  for (const member of bundle.members.values()) expected.set(member.path, { size: member.size, sha256: member.sha256 });
  return expected;
}

function corruptArtifactByte(bundle: TarBundle): Buffer {
  const corrupted = Buffer.from(bundle.tar);
  const artifact = [...bundle.members.values()].find((member) => member.path.endsWith(".parquet"));
  if (!artifact) throw new Error("generated bundle has no parquet artifact to corrupt");
  corrupted[artifact.offset + 64] = corrupted[artifact.offset + 64]! ^ 0xff;
  return corrupted;
}

/**
 * Installs the minimal API surface this page needs for a direct PREVIEW URL, then
 * returns a collector for any unexpected /v1 request so a missing mock fails loudly.
 */
async function installRoutes(page: Page, mode: BundleMode, bundle: TarBundle): Promise<{ unexpected: string[]; bundleRequests: () => number }> {
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
    const body = mode === "full" ? bundle.tar : mode === "truncated" ? bundle.tar.subarray(0, bundle.tar.byteLength - 512) : corruptArtifactByte(bundle);
    await route.fulfill({
      status: 200,
      contentType: "application/x-tar",
      headers: { ETag: bundle.bundleDigest, "Content-Length": String(bundle.tar.byteLength) },
      body,
    });
  });

  return { unexpected, bundleRequests: () => bundleRequests };
}

function browseUrl(bundle: { bundleDigest: string }): string {
  const params = new URLSearchParams({
    page: "compare",
    mode: "PREVIEW",
    workspaceId: WORKSPACE_ID,
    previewResultId: PREVIEW_RESULT_ID,
    bundleDigest: bundle.bundleDigest,
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

test("installs a v4 backend bundle into OPFS with matching sizes and digests", async ({ page }) => {
  const bundle = await readGeneratedBundle("preview-replacement");
  expect(bundle.contractVersion).toBe("backend-vnext/comparison-bundle/v4");
  const routes = await installRoutes(page, "full", bundle);
  const key = hexDigest(bundle.bundleDigest);

  await page.goto(browseUrl(bundle));
  await waitForInstalledBundle(page);

  const expected = expectedInstalledFiles(bundle);
  expect(expected.size).toBeGreaterThan(4);
  const installed = await readInstalledFiles(page, key, Array.from(expected.keys()));
  const topLevelDirs = [...new Set([...expected.keys()].filter((path) => path.includes("/")).map((path) => path.split("/")[0] ?? ""))];
  expect(installed.names.sort()).toEqual([".complete.json", ".last-used", ...topLevelDirs].sort());
  expect(installed.marker.bundle_digest).toBe(key);
  for (const [path, file] of expected) {
    expect(installed.files[path]?.size).toBe(file.size);
    expect(installed.files[path]?.sha256).toBe(file.sha256);
  }
  expect(routes.bundleRequests()).toBe(1);
  expect(routes.unexpected).toEqual([]);
});

test("aborts the opfs install when the bundle body is truncated", async ({ page }) => {
  const bundle = await readGeneratedBundle("preview-replacement");
  const routes = await installRoutes(page, "truncated", bundle);

  await page.goto(browseUrl(bundle));
  await expectDownloadFailure(page);
  expect(await bundleDirectoryExists(page, hexDigest(bundle.bundleDigest))).toBe(false);
  // ensureLocalBundle retries a BundleIntegrityError once and surfaces the second failure.
  expect(routes.bundleRequests()).toBe(2);
});

test("aborts the opfs install when a parquet member byte is corrupted", async ({ page }) => {
  const bundle = await readGeneratedBundle("preview-replacement");
  const routes = await installRoutes(page, "corrupted", bundle);

  await page.goto(browseUrl(bundle));
  await expectDownloadFailure(page);
  await expect(page.locator(".compare-error")).toContainText("BUNDLE_INTEGRITY_MISMATCH");
  expect(await bundleDirectoryExists(page, hexDigest(bundle.bundleDigest))).toBe(false);
  expect(routes.bundleRequests()).toBe(2);
});

test("rejects the v3 interop tar before anything reaches OPFS", async ({ page }) => {
  const index = JSON.parse((await readFixture("index.json")).toString("utf8")) as { bundle_digest: string; content_length: number };
  const tar = await readFixture("bundle.tar");
  const bundle: TarBundle = {
    tar,
    bundleDigest: index.bundle_digest,
    contractVersion: "backend-vnext/comparison-bundle/v3",
    members: new Map(),
  };
  expect(tar.byteLength).toBe(24_576);
  expect(tar.byteLength).toBe(index.content_length);
  const routes = await installRoutes(page, "full", bundle);

  await page.goto(browseUrl(bundle));
  await expectDownloadFailure(page);
  expect(await bundleDirectoryExists(page, hexDigest(index.bundle_digest))).toBe(false);
  expect(routes.unexpected).toEqual([]);
});
