import { test, expect } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { identities, resultsDir, type JourneyIdentity } from "./lib/env";
import { contextForIdentity, gotoWorkbench } from "./lib/ui";
import { apiRequest, currentWorkspace, tryApi } from "./lib/api";

test("public entry opens two groups and a hot added synthetic device without cross-scope reads", async ({ browser }) => {
  test.setTimeout(180_000);
  const control = join(resultsDir(), "groups-control");
  const topology = JSON.parse(await readFile(join(control, "groups-ready.json"), "utf8")) as {
    synthetic: JourneyIdentity; hot: JourneyIdentity;
  };
  const first = identities()[0]!;
  const second = topology.synthetic;
  for (const identity of [first, second]) {
    const context = await contextForIdentity(browser, identity);
    try {
      const page = await context.newPage();
      const history = page.waitForResponse((response) => response.url().includes("/v1/history") && response.status() === 200);
      await gotoWorkbench(page);
      await history;
      await expect(page.getByText("初始基线").first()).toBeVisible({ timeout: 60_000 });
    } finally { await context.close(); }
  }
  const workspace = await currentWorkspace(first);
  const crossScope = await tryApi(second, "GET", `/v1/workspaces/${workspace.workspace_id}`);
  expect(crossScope).toMatchObject({ ok: false, status: 404 });
  await writeFile(join(control, "hot-add-request"), "add-device");
  await expect.poll(async () => {
    try { return JSON.parse(await readFile(join(control, "hot-add-result.json"), "utf8")); } catch { return null; }
  }, { timeout: 120_000 }).toMatchObject({ state: "available", containers_unchanged: true });
  const hotContext = await contextForIdentity(browser, topology.hot);
  try {
    const page = await hotContext.newPage();
    await gotoWorkbench(page);
    await expect(page.getByText("初始基线").first()).toBeVisible({ timeout: 60_000 });
    const response = await apiRequest<{ group_id: string; gateway_device_external_key: string }>(topology.hot, "GET", "/v1/device-context");
    expect(response.body).toMatchObject({ group_id: "group-b", gateway_device_external_key: topology.hot.gatewayDeviceExternalKey });
  } finally { await hotContext.close(); }
});
