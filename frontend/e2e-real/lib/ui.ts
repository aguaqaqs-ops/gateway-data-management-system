import { expect, type Browser, type BrowserContext, type Locator, type Page, type Response, type TestInfo } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import { resultsDir, type JourneyIdentity } from "./env";

/** One browser context per identity: OPFS and storage stay identity-scoped. */
export async function contextForIdentity(browser: Browser, identity: JourneyIdentity): Promise<BrowserContext> {
  const context = await browser.newContext({
    baseURL: process.env.GATEWAY_FE_PREVIEW_URL ?? "http://127.0.0.1:4173",
    viewport: { width: 1280, height: 900 },
  });
  await context.addInitScript((session) => {
    (window as unknown as { __gatewaySession: unknown }).__gatewaySession = session;
  }, {
    businessProjectId: identity.businessProjectId,
    gatewayDeviceExternalKey: identity.gatewayDeviceExternalKey,
    accessToken: identity.token,
  });
  return context;
}

export async function gotoWorkbench(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /组态树/ })).toBeVisible();
  await expect(page.locator(".workspace-context-bar")).toBeVisible();
}

export interface UploadDirs {
  modified: string;
  initial?: string;
}

export async function selectUploadDirs(page: Page, dirs: UploadDirs): Promise<void> {
  if (dirs.initial) {
    await page.getByTestId("upload-initial-input").setInputFiles(dirs.initial);
    await page.getByTestId("upload-modified-input").setInputFiles(dirs.modified);
    await expect(page.locator(".upload-card").getByText(/原始备份 \+ 本次归档/).first()).toBeVisible();
  } else {
    await page.getByTestId("upload-modified-input").setInputFiles(dirs.modified);
    await expect(page.locator(".upload-card").getByText(/仅本次归档/).first()).toBeVisible();
  }
}

export async function startUpload(page: Page): Promise<void> {
  await page.getByRole("button", { name: "上传并生成预览" }).click();
}

export type PreviewOutcome = "compare" | "error";

export async function waitForPreviewOutcome(page: Page, timeout = 300_000): Promise<PreviewOutcome> {
  const compare = page.locator("section.comparison-content");
  const error = page.locator(".upload-error, section.compare-error");
  await expect(compare.or(error).first()).toBeVisible({ timeout });
  return (await page.locator(".upload-error, section.compare-error").first().isVisible()) ? "error" : "compare";
}

/** Wait until the diff workspace renders a grid (FE3b §4.7: no early assertions). */
export async function waitForDiffBrowsing(page: Page): Promise<void> {
  await expect(page.locator("section.comparison-content")).toBeVisible({ timeout: 120_000 });
  await expect(page.locator('div.grid-frame[aria-label="比较表格"]')).toHaveAttribute("data-rendered", "true", {
    timeout: 120_000,
  });
}

export function waitForBundleResponse(page: Page, timeout = 300_000): Promise<Response> {
  return page.waitForResponse(
    (response) => response.request().method() === "GET" && response.url().split("?")[0].endsWith("/bundle"),
    { timeout },
  );
}

export function treeRow(page: Page, text: string | RegExp): Locator {
  return page.locator('table[aria-label="History 组态树"] tr').filter({ hasText: text }).first();
}

export async function selectTreeRow(page: Page, text: string | RegExp): Promise<void> {
  const row = treeRow(page, text);
  await expect(row).toBeVisible();
  await row.getByRole("button").first().click();
  await expect(row).toHaveClass(/is-selected/);
}

export function workshopAction(page: Page, label: string): Locator {
  return page.locator(".workspace-actions .workspace-action").filter({ hasText: label }).getByRole("button").first();
}

export function compareAction(page: Page, name: "撤回" | "提交"): Locator {
  return page.locator(".compare-actions").getByRole("button", { name, exact: true });
}

export function reviewAction(page: Page, name: "撤回" | "退回" | "审核通过"): Locator {
  return page.locator(".review-actions").getByRole("button", { name, exact: true });
}

export function reviewStatus(page: Page): Locator {
  return page.locator("span.review-facts-status");
}

export async function expectDisabledWithReason(button: Locator, reason: string): Promise<void> {
  await expect(button).toBeDisabled();
  await expect(button.locator('xpath=following-sibling::span[contains(@class, "disabled-reason")]')).toHaveText(reason);
}

export async function expectEnabled(button: Locator): Promise<void> {
  await expect(button).toBeEnabled();
}

export interface OpfsBundleState {
  bundleDirs: string[];
  hasDigestDir: boolean;
  hasCompleteMarker: boolean;
  hasManifest: boolean;
}

/**
 * Inspect the OPFS comparison-bundle store (`gateway-comparison-bundles-v1`).
 * A bundle is visible only when its digest directory carries `.complete.json`;
 * an aborted install must not leave a partial directory behind.
 */
export async function opfsBundleState(page: Page, digestHex: string): Promise<OpfsBundleState> {
  return page.evaluate(async (digest) => {
    const storage = navigator.storage as unknown as { getDirectory(): Promise<FileSystemDirectoryHandle> };
    const root = await storage.getDirectory();
    const empty: OpfsBundleState = { bundleDirs: [], hasDigestDir: false, hasCompleteMarker: false, hasManifest: false };
    let bundles: FileSystemDirectoryHandle;
    try {
      bundles = await root.getDirectoryHandle("gateway-comparison-bundles-v1");
    } catch {
      return empty;
    }
    const iterate = bundles as unknown as { keys(): AsyncIterableIterator<string> };
    const bundleDirs: string[] = [];
    for await (const name of iterate.keys()) bundleDirs.push(name);
    if (!bundleDirs.includes(digest)) return { ...empty, bundleDirs };
    const dir = await bundles.getDirectoryHandle(digest);
    const names: string[] = [];
    for await (const name of (dir as unknown as { keys(): AsyncIterableIterator<string> }).keys()) names.push(name);
    return {
      bundleDirs,
      hasDigestDir: true,
      hasCompleteMarker: names.includes(".complete.json"),
      hasManifest: names.includes("manifest.json"),
    };
  }, digestHex);
}

export interface PageDiagnostics {
  pageErrors: string[];
  consoleErrors: string[];
}

export function collectPageDiagnostics(page: Page): PageDiagnostics {
  const diagnostics: PageDiagnostics = { pageErrors: [], consoleErrors: [] };
  page.on("pageerror", (error) => diagnostics.pageErrors.push(error.stack ?? error.message));
  page.on("console", (message) => {
    if (message.type() === "error") diagnostics.consoleErrors.push(message.text());
  });
  return diagnostics;
}

export async function expectNoPageErrors(diagnostics: PageDiagnostics, phase: string): Promise<void> {
  expect(diagnostics.pageErrors, `未捕获的页面错误（${phase}）`).toEqual([]);
}

export function evidenceDir(): string {
  return process.env.GATEWAY_FE_EVIDENCE_DIR ?? path.join(resultsDir(), "evidence");
}

function evidenceName(value: string): string {
  return value.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80);
}

/** Reference screenshot per key page (FE3b §4.7; not acceptance evidence). */
export async function saveEvidence(page: Page, testInfo: TestInfo, label: string): Promise<void> {
  const directory = evidenceDir();
  await mkdir(directory, { recursive: true });
  const file = path.join(directory, `${evidenceName(testInfo.title)}-${evidenceName(label)}.png`);
  await page.screenshot({ path: file, fullPage: true });
  await testInfo.attach(label, { path: file, contentType: "image/png" });
}

export async function appendCaseLog(line: string): Promise<void> {
  const directory = evidenceDir();
  await mkdir(directory, { recursive: true });
  await writeFile(path.join(directory, "journey-cases.log"), `${new Date().toISOString()} ${line}\n`, { flag: "a" });
}
