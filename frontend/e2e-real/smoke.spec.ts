import { expect, test, type Browser, type Page } from "@playwright/test";

/**
 * FE3a smoke suite on the real backend (frontend kickoff §3.3).
 *
 * Identities come from GATEWAY_FE_IDENTITIES (JSON array, written by
 * run-real-backend-e2e.sh). Each identity gets its own browser context
 * (owner Q5); no identity switching inside one context.
 *
 * Every identity carries workspace_read + read_project_history (kickoff
 * §4.6); upload/preview/review/archive permissions differ per identity.
 */

interface Identity {
  name: string;
  token: string;
  actorId: string;
  businessProjectId: string;
  gatewayDeviceExternalKey: string;
}

interface WorkspaceBody {
  workspace_id: string;
  current_preview_result_id: string | null;
  optimistic_version: number;
}

interface PreviewResultBody {
  preview_result_id: string;
  workspace_id: string;
  operation_id: string;
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
      window.__gatewaySession = { accessToken: token, businessProjectId, gatewayDeviceExternalKey };
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

/** Collect uncaught page errors; assert empty at the end of every test (§4.7). */
function collectPageErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

/** CreateOrGet the workspace through the same same-origin API the page uses. */
async function workspaceFromPage(page: Page, identity: Identity): Promise<WorkspaceBody> {
  return page.evaluate(
    async ({ token, businessProjectId, gatewayDeviceExternalKey }) => {
      const response = await fetch("/v1/workspaces", {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
        body: JSON.stringify({ business_project_id: businessProjectId, gateway_device_external_key: gatewayDeviceExternalKey }),
      });
      if (!response.ok) throw new Error(`POST /v1/workspaces returned ${response.status}`);
      return (await response.json()) as WorkspaceBody;
    },
    identity,
  );
}

async function selectModifiedAndUpload(page: Page): Promise<void> {
  const inputRoot = process.env.GATEWAY_FE_SMOKE_INPUT_ROOT ?? "/input";
  await page.locator('[data-testid="upload-modified-input"]').setInputFiles(inputRoot);
  await page.getByRole("button", { name: "上传并生成预览" }).click();
}

test("smoke: workspace CreateOrGet returns 201 or 200 and history shows INITIAL", async ({ browser }) => {
  const identity = byName("submitter");
  const context = await contextWithIdentity(browser, identity);
  const page = await context.newPage();
  await page.setViewportSize({ width: 1920, height: 1080 });
  const pageErrors = collectPageErrors(page);

  const created = page.waitForResponse(
    (r) => r.url().endsWith("/v1/workspaces") && r.request().method() === "POST",
    { timeout: 120000 },
  );
  await gotoWorkbench(page);
  const workspaceResponse = await created;
  expect([200, 201]).toContain(workspaceResponse.status());

  // History has only the INITIAL baseline: the tree shows the initial node.
  await expect(page.getByText("初始基线").first()).toBeVisible({ timeout: 60000 });
  expect(await workspaceFromPage(page, identity)).toMatchObject({ workspace_id: expect.any(String) });
  expect(pageErrors).toEqual([]);
  await context.close();
});

test("smoke: upload accepted, preview SUCCEEDED, pointer matches, no uncaught error", async ({ browser }) => {
  const identity = byName("submitter");
  const context = await contextWithIdentity(browser, identity);
  const page = await context.newPage();
  await page.setViewportSize({ width: 1920, height: 1080 });
  const pageErrors = collectPageErrors(page);

  const uploadResponses: number[] = [];
  const previewResults: PreviewResultBody[] = [];
  const operationStates: string[] = [];
  page.on("response", (response) => {
    const request = response.request();
    const path = new URL(response.url()).pathname;
    if (request.method() === "POST" && /\/v1\/workspaces\/[^/]+\/upload-revisions$/.test(path)) {
      uploadResponses.push(response.status());
    }
    if (request.method() === "GET" && path.includes("/preview-results/") && response.status() === 200) {
      void response.json().then((body) => previewResults.push(body as PreviewResultBody)).catch(() => undefined);
    }
    if (request.method() === "GET" && /\/v1\/operations\/[^/]+$/.test(path) && response.status() === 200) {
      void response.json().then((body) => operationStates.push((body as { status: string }).status)).catch(() => undefined);
    }
  });

  await gotoWorkbench(page);
  await selectModifiedAndUpload(page);

  // The upload is accepted by the real backend (upload_revision created).
  await expect.poll(() => uploadResponses, { timeout: 300000 }).toContain(201);
  // The preview operation reaches SUCCEEDED.
  await expect.poll(() => operationStates, { timeout: 600000 }).toContain("SUCCEEDED");
  // GET preview-results/{id} returns 200.
  await expect.poll(() => previewResults.length, { timeout: 120000 }).toBeGreaterThan(0);
  const previewBody = previewResults[0]!;

  // The workspace pointer is the same preview result (kickoff §3.3).
  const workspace = await workspaceFromPage(page, identity);
  expect(previewBody.preview_result_id).toBe(workspace.current_preview_result_id);
  expect(previewBody.workspace_id).toBe(workspace.workspace_id);

  // Bundle download still fails on the current backend (BE-d pending); the
  // page must not raise an uncaught error, and that failure is not asserted.
  expect(pageErrors).toEqual([]);
  await context.close();
});

test("smoke: no-permission upload returns 403 copy", async ({ browser }) => {
  const identity = byName("noperm");
  const context = await contextWithIdentity(browser, identity);
  const page = await context.newPage();
  await page.setViewportSize({ width: 1920, height: 1080 });
  const pageErrors = collectPageErrors(page);

  const uploadStatuses: number[] = [];
  page.on("response", (response) => {
    const path = new URL(response.url()).pathname;
    if (response.request().method() === "POST" && /\/v1\/workspaces\/[^/]+\/upload-revisions$/.test(path)) {
      uploadStatuses.push(response.status());
    }
  });

  await gotoWorkbench(page);
  await selectModifiedAndUpload(page);
  await expect.poll(() => uploadStatuses, { timeout: 120000 }).toContain(403);
  await expect(page.getByText("当前身份没有该操作的权限").first()).toBeVisible({ timeout: 60000 });
  await expect(page.getByText("SCOPE_FORBIDDEN").first()).toBeVisible();
  expect(pageErrors).toEqual([]);
  await context.close();
});

test("smoke: upload-only identity gets 403 on preview start", async ({ browser }) => {
  const identity = byName("no-preview");
  const context = await contextWithIdentity(browser, identity);
  const page = await context.newPage();
  await page.setViewportSize({ width: 1920, height: 1080 });
  const pageErrors = collectPageErrors(page);

  const uploadStatuses: number[] = [];
  const previewStatuses: number[] = [];
  page.on("response", (response) => {
    const request = response.request();
    const path = new URL(response.url()).pathname;
    if (request.method() === "POST" && /\/v1\/workspaces\/[^/]+\/upload-revisions$/.test(path)) {
      uploadStatuses.push(response.status());
    }
    if (request.method() === "POST" && /\/v1\/workspaces\/[^/]+\/preview-operations$/.test(path)) {
      previewStatuses.push(response.status());
    }
  });

  await gotoWorkbench(page);
  await selectModifiedAndUpload(page);
  // Upload succeeds (201); preview-operations is denied with 403.
  await expect.poll(() => uploadStatuses, { timeout: 300000 }).toContain(201);
  await expect.poll(() => previewStatuses, { timeout: 120000 }).toContain(403);
  await expect(page.getByText("当前身份没有该操作的权限").first()).toBeVisible({ timeout: 60000 });
  await expect(page.getByText("SCOPE_FORBIDDEN").first()).toBeVisible();
  expect(pageErrors).toEqual([]);
  await context.close();
});
