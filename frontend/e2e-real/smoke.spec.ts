import { expect, test, type Browser, type Page } from "@playwright/test";

/**
 * FE3a smoke suite on the real backend (frontend kickoff §3.3).
 *
 * Identities come from GATEWAY_FE_IDENTITIES (JSON array, written by
 * run-real-backend-e2e.sh). Each identity gets its own browser context
 * (owner Q5); no identity switching inside one context.
 */

interface Identity {
  name: string;
  token: string;
  actorId: string;
  businessProjectId: string;
  gatewayDeviceExternalKey: string;
}

function identities(): Identity[] {
  const raw = process.env.GATEWAY_FE_IDENTITIES;
  if (!raw) throw new Error("GATEWAY_FE_IDENTITIES is required (JSON array)");
  return JSON.parse(raw) as Identity[];
}

function byName(name: string): Identity {
  const found = identities().find((i) => i.name === name);
  if (!found) throw new Error(`identity ${name} missing`);
  return found;
}

async function contextWithIdentity(browser: Browser, identity: Identity) {
  const context = await browser.newContext();
  await context.addInitScript(
    ({ token, businessProjectId, gatewayDeviceExternalKey }) => {
      window.__gatewaySession = { accessToken: `Bearer ${token}`, businessProjectId, gatewayDeviceExternalKey };
    },
    {
      token: identity.token,
      businessProjectId: identity.businessProjectId,
      gatewayDeviceExternalKey: identity.gatewayDeviceExternalKey,
    },
  );
  return context;
}

async function gotoWorkbench(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "组态树", level: 1 })).toBeVisible({ timeout: 60000 });
}

/** Fail the test on any uncaught page error (kickoff §4.7). */
function failOnPageError(page: Page): void {
  page.on("pageerror", (error) => {
    throw new Error(`uncaught page error: ${error.message}`);
  });
}

test("smoke: workspace CreateOrGet returns 201 or 200 and history shows INITIAL", async ({ browser }) => {
  const context = await contextWithIdentity(browser, byName("submitter"));
  const page = await context.newPage();
  failOnPageError(page);

  const created = page.waitForResponse(
    (r) => r.url().endsWith("/v1/workspaces") && r.request().method() === "POST",
  );
  await gotoWorkbench(page);
  const workspaceResponse = await created;
  expect([200, 201]).toContain(workspaceResponse.status());

  // History has only INITIAL: the tree shows the initial baseline node.
  await expect(page.getByText("初始基线")).toBeVisible();
  await context.close();
});

test("smoke: upload accepted, preview SUCCEEDED, pointer matches, no uncaught error", async ({ browser }) => {
  const context = await contextWithIdentity(browser, byName("submitter"));
  const page = await context.newPage();
  failOnPageError(page);
  await gotoWorkbench(page);

  // Select the MODIFIED_ONLY input directory (mounted read-only in the
  // toolchain container at /input by run-real-backend-e2e.sh smoke setup).
  const inputRoot = process.env.GATEWAY_FE_SMOKE_INPUT_ROOT ?? "/input";
  await page.locator('[data-testid="upload-modified-input"]').setInputFiles(inputRoot);
  await page.getByRole("button", { name: "上传并生成预览" }).click();

  // Preview result pointer round-trip (kickoff §3.3): GET preview-results
  // returns 200 with the workspace's current_preview_result_id.
  const previewResultResponse = await page.waitForResponse(
    (r) => r.url().includes("/preview-results/") && r.request().method() === "GET",
    { timeout: 300000 },
  );
  expect(previewResultResponse.status()).toBe(200);
  const previewBody = (await previewResultResponse.json()) as {
    preview_result_id: string;
    operation_id: string;
  };

  // Workspace reflects the new preview result.
  const workspaceResponse = await page.waitForResponse(
    (r) => r.url().endsWith("/v1/workspaces") && r.request().method() === "POST",
    { timeout: 60000 },
  );
  const workspaceBody = (await workspaceResponse.json()) as {
    current_preview_result_id: string | null;
  };
  expect(previewBody.preview_result_id).toBe(workspaceBody.current_preview_result_id);

  // Bundle download fails on the current backend (BE-d pending): assert the
  // page shows the retry UI and raises no uncaught error instead.
  await expect(page.getByText("预览已生成，但下载比较结果失败，请重试")).toBeVisible({ timeout: 120000 });
  await context.close();
});

test("smoke: no-permission upload returns 403 copy", async ({ browser }) => {
  const context = await contextWithIdentity(browser, byName("noperm"));
  const page = await context.newPage();
  failOnPageError(page);
  await gotoWorkbench(page);

  const inputRoot = process.env.GATEWAY_FE_SMOKE_INPUT_ROOT ?? "/input";
  await page.locator('[data-testid="upload-modified-input"]').setInputFiles(inputRoot);
  await page.getByRole("button", { name: "上传并生成预览" }).click();
  await expect(page.getByText("当前身份没有该操作的权限")).toBeVisible({ timeout: 60000 });
  await expect(page.getByText("SCOPE_FORBIDDEN")).toBeVisible();
  await context.close();
});

test("smoke: upload-only identity gets 403 on preview start", async ({ browser }) => {
  const context = await contextWithIdentity(browser, byName("no-preview"));
  const page = await context.newPage();
  failOnPageError(page);
  await gotoWorkbench(page);

  const inputRoot = process.env.GATEWAY_FE_SMOKE_INPUT_ROOT ?? "/input";
  await page.locator('[data-testid="upload-modified-input"]').setInputFiles(inputRoot);
  // Upload succeeds (200/201); preview-operations returns 403.
  await page.getByRole("button", { name: "上传并生成预览" }).click();
  const previewOp = await page.waitForResponse(
    (r) => r.url().includes("/preview-operations") && r.request().method() === "POST",
    { timeout: 120000 },
  );
  expect(previewOp.status()).toBe(403);
  await context.close();
});
