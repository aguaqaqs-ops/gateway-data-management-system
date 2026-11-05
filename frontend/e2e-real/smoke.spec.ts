import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type Browser, type Page } from "@playwright/test";

/**
 * FE3a smoke suite on the real backend (frontend kickoff §3.3, §4.6).
 *
 * Identities come from GATEWAY_FE_IDENTITIES (JSON array, written by
 * run-real-backend-e2e.sh). Each identity gets its own browser context
 * (owner Q5); no identity switching inside one context.
 *
 * Every identity carries workspace_read + read_project_history (kickoff
 * §4.6); upload/preview/review/archive permissions differ per identity.
 *
 * The five `input-*` scopes are independent repositories seeded on an empty
 * INITIAL baseline. They upload the A/B/C/D inputs (Q10) through the real
 * UI and then read the bundle manifest through the preview proxy, because the
 * current backend still returns JSON at the bundle path (§3.3).
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
  bundle_digest: string;
  identity_pairs: Array<{ pair_id: string; status: string }>;
}

interface OperationBody {
  operation_id: string;
  status: string;
  diagnostic?: { code: string; message: string } | null;
}

interface BundleBody {
  bundle_id?: string;
  manifest_ref?: { artifact_id?: string };
  failed_pairs: unknown[];
  inputs: Array<{ input_index: number; role: string; display_name: string }>;
  pairs: Array<{
    pair_id: string;
    before_input_index: number;
    current_input_index: number;
    status: string;
    summary: Record<string, string>;
  }>;
}

interface ScopeRecord {
  identity: string;
  scope: string;
  upload_status: number;
  operation_id: string;
  preview_result_id: string;
  bundle_id: string;
  failed_pairs: number;
  pairs: Array<{
    before_input_index: number;
    current_input_index: number;
    status: string;
    table_count: number;
    changed_table_count: number;
    degraded_table_count: number;
    failed_table_count: number;
  }>;
  identity_pairs: Array<{ pair_id: string; status: string }>;
}

const inputResults: ScopeRecord[] = [];

function identities(): Identity[] {
  const raw = process.env.GATEWAY_FE_IDENTITIES;
  if (!raw) throw new Error("GATEWAY_FE_IDENTITIES is required (JSON array)");
  return JSON.parse(raw) as Identity[];
}

function byName(name: string): Identity {
  const found = identities().find((item) => item.name === name);
  if (!found) throw new Error(`identity ${name} missing`);
  return found;
}

function inputRoot(): string {
  return process.env.GATEWAY_FE_SMOKE_INPUT_ROOT ?? "/input";
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

async function selectAndUpload(page: Page, modifiedDir: string, initialDir?: string): Promise<void> {
  if (initialDir) {
    await page.locator('[data-testid="upload-initial-input"]').setInputFiles(initialDir);
  }
  await page.locator('[data-testid="upload-modified-input"]').setInputFiles(modifiedDir);
  await page.getByRole("button", { name: "上传并生成预览" }).click();
}

async function waitForOperation(page: Page, token: string, operationId: string): Promise<OperationBody> {
  const deadline = Date.now() + 300_000;
  while (Date.now() < deadline) {
    const operation = await page.evaluate(
      async ({ token, operationId }) => {
        const response = await fetch(`/v1/operations/${encodeURIComponent(operationId)}`, {
          headers: { authorization: `Bearer ${token}` },
        });
        if (!response.ok) throw new Error(`GET /v1/operations returned ${response.status}`);
        return (await response.json()) as OperationBody;
      },
      { token, operationId },
    );
    if (["SUCCEEDED", "FAILED", "CANCELLED"].includes(operation.status)) return operation;
    await page.waitForTimeout(500);
  }
  throw new Error(`operation ${operationId} did not finish within 300s`);
}

async function previewAndBundle(page: Page, identity: Identity): Promise<{ preview: PreviewResultBody; bundle: BundleBody }> {
  const workspace = await workspaceFromPage(page, identity);
  if (!workspace.current_preview_result_id) throw new Error("workspace has no current preview result");
  const preview = await page.evaluate(
    async ({ token, workspaceId, previewResultId }) => {
      const response = await fetch(
        `/v1/workspaces/${encodeURIComponent(workspaceId)}/preview-results/${encodeURIComponent(previewResultId)}`,
        { headers: { authorization: `Bearer ${token}` } },
      );
      if (!response.ok) throw new Error(`GET preview-results returned ${response.status}`);
      return (await response.json()) as PreviewResultBody;
    },
    { token: identity.token, workspaceId: workspace.workspace_id, previewResultId: workspace.current_preview_result_id },
  );
  const bundle = await page.evaluate(
    async ({ token, workspaceId, previewResultId }) => {
      const response = await fetch(
        `/v1/workspaces/${encodeURIComponent(workspaceId)}/preview-results/${encodeURIComponent(previewResultId)}/bundle`,
        { headers: { authorization: `Bearer ${token}` } },
      );
      if (!response.ok) throw new Error(`GET preview bundle returned ${response.status}`);
      return (await response.json()) as BundleBody;
    },
    { token: identity.token, workspaceId: workspace.workspace_id, previewResultId: workspace.current_preview_result_id },
  );
  return { preview, bundle };
}

/**
 * Run one independent input scope through the real UI and verify the bundle
 * manifest criteria from Q10. The ② input is always the highest input index
 * (the current archive); its comparison pair must show a canonical change.
 */
async function runInputScope(
  browser: Browser,
  identityName: string,
  modifiedDir: string,
  initialDir?: string,
): Promise<ScopeRecord> {
  const identity = byName(identityName);
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
  const acceptedResponse = page.waitForResponse(
    (response) => response.request().method() === "POST"
      && /\/v1\/workspaces\/[^/]+\/preview-operations$/.test(new URL(response.url()).pathname),
    { timeout: 300_000 },
  );

  await gotoWorkbench(page);
  await selectAndUpload(page, modifiedDir, initialDir);
  await expect.poll(() => uploadStatuses, { timeout: 300_000 }).toContain(201);
  const accepted = await acceptedResponse;
  expect(accepted.status()).toBe(202);
  const acceptedBody = (await accepted.json()) as { operation_id: string };
  const operation = await waitForOperation(page, identity.token, acceptedBody.operation_id);
  expect(operation.status).toBe("SUCCEEDED");

  const { preview, bundle } = await previewAndBundle(page, identity);
  expect(bundle.failed_pairs).toEqual([]);
  expect(bundle.pairs.length).toBeGreaterThan(0);
  const lastInputIndex = Math.max(...bundle.inputs.map((input) => input.input_index));
  const pairs = bundle.pairs.map((pair) => ({
    before_input_index: pair.before_input_index,
    current_input_index: pair.current_input_index,
    status: pair.status,
    table_count: Number(pair.summary.table_count),
    changed_table_count: Number(pair.summary.changed_table_count),
    degraded_table_count: Number(pair.summary.degraded_table_count),
    failed_table_count: Number(pair.summary.failed_table_count),
  }));
  for (const pair of pairs) expect(pair.failed_table_count, `${pair.pair_id}.failed_table_count`).toBe(0);
  const currentPair = pairs.find((pair) => pair.current_input_index === lastInputIndex);
  expect(currentPair, "comparison pair containing the ② input").toBeTruthy();
  expect(currentPair!.changed_table_count).toBeGreaterThanOrEqual(1);

  const record: ScopeRecord = {
    identity: identity.name,
    scope: identity.scope,
    upload_status: 201,
    operation_id: acceptedBody.operation_id,
    preview_result_id: preview.preview_result_id,
    bundle_id: bundle.bundle_id ?? bundle.manifest_ref?.artifact_id ?? "",
    failed_pairs: bundle.failed_pairs.length,
    pairs,
    identity_pairs: preview.identity_pairs,
  };
  inputResults.push(record);
  expect(pageErrors).toEqual([]);
  await context.close();
  return record;
}

test("smoke: workspace CreateOrGet returns 201 or 200 and history shows INITIAL", async ({ browser }) => {
  const identity = byName("submitter");
  const context = await contextWithIdentity(browser, identity);
  const page = await context.newPage();
  await page.setViewportSize({ width: 1920, height: 1080 });
  const pageErrors = collectPageErrors(page);

  const created = page.waitForResponse(
    (response) => response.url().endsWith("/v1/workspaces") && response.request().method() === "POST",
    { timeout: 120000 },
  );
  await gotoWorkbench(page);
  const workspaceResponse = await created;
  expect([200, 201]).toContain(workspaceResponse.status());

  // History has only the INITIAL baseline: the tree shows the initial node.
  await expect(page.getByText("初始基线").first()).toBeVisible({ timeout: 60000 });
  expect(await workspaceFromPage(page, identity)).toMatchObject({ workspace_id: expect.any(String) });
  const history = await page.evaluate(async (token: string) => {
    const response = await fetch("/v1/history?limit=100", {
      headers: { authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new Error(`GET /v1/history returned ${response.status}`);
    return (await response.json()) as {
      head: { node_id: string };
      nodes: Array<{ ref_id: string; ref_kind: string; baseline_kind?: string | null }>;
    };
  }, identity.token);
  // The history contains exactly one node, the INITIAL baseline (B5).
  expect(history.nodes).toHaveLength(1);
  expect(history.nodes[0]?.baseline_kind).toBe("INITIAL");
  expect(history.nodes[0]?.ref_kind).toBe("baseline_node");
  expect(history.head.node_id).toBe(history.nodes[0]?.ref_id);
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
    if (request.method() === "GET" && /\/preview-results\/[^/]+$/.test(path) && response.status() === 200) {
      void response.json().then((body) => previewResults.push(body as PreviewResultBody)).catch(() => undefined);
    }
    if (request.method() === "GET" && /\/v1\/operations\/[^/]+$/.test(path) && response.status() === 200) {
      void response.json().then((body) => operationStates.push((body as { status: string }).status)).catch(() => undefined);
    }
  });

  const bundleResponse = page.waitForResponse(
    (response) => response.request().method() === "GET"
      && /\/preview-results\/[^/]+\/bundle$/.test(new URL(response.url()).pathname),
    { timeout: 120000 },
  );

  await gotoWorkbench(page);
  await selectAndUpload(page, join(inputRoot(), "c"));

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

  // Preview success downloads the bundle before entering compare; the current
  // backend returns JSON, so wait for the stable download-failure prompt
  // before asserting no uncaught page error (B5).
  await bundleResponse;
  await expect(page.getByText("预览已生成，但下载比较结果失败，请重试")).toBeVisible({ timeout: 120000 });
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
  await selectAndUpload(page, join(inputRoot(), "c"));
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
  await selectAndUpload(page, join(inputRoot(), "c"));
  // Upload succeeds (201); preview-operations is denied with 403.
  await expect.poll(() => uploadStatuses, { timeout: 300000 }).toContain(201);
  await expect.poll(() => previewStatuses, { timeout: 120000 }).toContain(403);
  await expect(page.getByText("当前身份没有该操作的权限").first()).toBeVisible({ timeout: 60000 });
  await expect(page.getByText("SCOPE_FORBIDDEN").first()).toBeVisible();
  expect(pageErrors).toEqual([]);
  await context.close();
});

test("smoke inputs A: baseline MODIFIED_ONLY reaches SUCCEEDED with a canonical change", async ({ browser }) => {
  await runInputScope(browser, "input-a", join(inputRoot(), "a"));
});

test("smoke inputs B②: initial MODIFIED_ONLY reaches SUCCEEDED with a canonical change", async ({ browser }) => {
  await runInputScope(browser, "input-b-mod", join(inputRoot(), "b"));
});

test("smoke inputs C: modified MODIFIED_ONLY reaches SUCCEEDED with a canonical change", async ({ browser }) => {
  await runInputScope(browser, "input-c", join(inputRoot(), "c"));
});

test("smoke inputs D: replacement-current MODIFIED_ONLY reaches SUCCEEDED and records identity pairs", async ({ browser }) => {
  await runInputScope(browser, "input-d", join(inputRoot(), "d"));
});

test("smoke inputs B FULL: ① = A and ② = B reaches SUCCEEDED with a canonical change", async ({ browser }) => {
  await runInputScope(browser, "input-b-full", join(inputRoot(), "b"), join(inputRoot(), "a"));
});

test.afterAll(() => {
  const directory = process.env.GATEWAY_FE_RESULTS_DIR ?? "/results";
  mkdirSync(directory, { recursive: true });
  writeFileSync(join(directory, "input-scope-results.json"), `${JSON.stringify(inputResults, null, 2)}\n`);
});
