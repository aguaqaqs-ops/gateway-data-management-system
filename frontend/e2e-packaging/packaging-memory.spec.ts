import { execFile } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import { promisify } from "node:util";
import { expect, test } from "@playwright/test";

const execFileAsync = promisify(execFile);

/**
 * FE3a M1 packaging peak-memory measurement (frontend kickoff §8.4).
 *
 * Environment:
 *   GATEWAY_M1_INPUT_ROOT  selected root directory (read-only mount)
 *   GATEWAY_M1_MODE        modified|full
 *   GATEWAY_M1_REPORT      absolute JSON report path
 *
 * Each scenario runs in the same browser context sequence with a fresh page;
 * the report records per-process VmHWM peak increments (renderer + browser +
 * GPU + utility/network), directory stats, and wall time. The upload request
 * is route-intercepted (503) so no backend is needed; packaging finishes
 * before the request is issued.
 */

async function dirStats(root: string): Promise<{ files: number; bytes: number }> {
  const { readdir, stat } = await import("node:fs/promises");
  const { join } = await import("node:path");
  let files = 0;
  let bytes = 0;
  async function walk(dir: string): Promise<void> {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) await walk(full);
      else if (entry.isFile()) {
        files += 1;
        bytes += (await stat(full)).st_size;
      }
    }
  }
  await walk(root);
  return { files, bytes };
}

async function readVmHWM(pid: number): Promise<number | null> {
  try {
    const status = await readFile(`/proc/${pid}/status`, "utf8");
    const m = status.match(/VmHWM:\s+(\d+)\s+kB/);
    return m ? Number(m[1]) * 1024 : null;
  } catch {
    return null;
  }
}

async function chromePids(): Promise<number[]> {
  for (const pattern of ["chrome", "headless", "playwright"]) {
    const { stdout } = await execFileAsync("pgrep", ["-f", pattern]).catch(() => ({ stdout: "" }));
    const pids = stdout.split("\n").map((s) => Number(s.trim())).filter(Boolean);
    if (pids.length > 0) return pids;
  }
  return [];
}

test("M1 packaging peak memory", async ({ page }) => {
  const inputRoot = process.env.GATEWAY_M1_INPUT_ROOT;
  const mode = process.env.GATEWAY_M1_MODE ?? "modified";
  const reportPath = process.env.GATEWAY_M1_REPORT;
  if (!inputRoot || !reportPath || (mode !== "modified" && mode !== "full")) {
    throw new Error("GATEWAY_M1_INPUT_ROOT / GATEWAY_M1_MODE=modified|full / GATEWAY_M1_REPORT are required");
  }
  const runs = Number(process.env.GATEWAY_M1_RUNS ?? "3");
  const { files: fileCount, bytes: dirBytes } = await dirStats(inputRoot);

  await page.route("**/v1/workspaces", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        workspace_id: "m1-probe", gateway_device_external_key: "m1-device",
        business_project_id: "m1-project", state: "OPEN", generation: 1,
        optimistic_version: 1, created_at: "2026-11-05T00:00:00Z",
        updated_at: "2026-11-05T00:00:00Z",
        current_upload_revision_id: null, current_preview_result_id: null,
      }),
    });
  });
  await page.route("**/v1/history*", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        head: { node_id: "m1-baseline", commit_id: "m1-commit", version: 1 },
        nodes: [{
          ref_kind: "baseline_node", ref_id: "m1-baseline", node_kind: "BASELINE_NODE",
          baseline_kind: "INITIAL", commit_id: "m1-commit", created_at: "2026-11-05T00:00:00Z",
          parent: null, identity_exception: false,
        }],
        next_cursor: null,
      }),
    });
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "组态树", level: 1 })).toBeVisible({ timeout: 30000 });
  // Zero peaks after page load, record baselines.
  const targets = await chromePids();
  const baselines = new Map<number, number | null>();
  const { writeFile: writeProc } = await import("node:fs/promises");
  for (const pid of targets) {
    await writeProc(`/proc/${pid}/clear_refs`, "5").catch(() => null);
    baselines.set(pid, await readVmHWM(pid));
  }
  expect(baselines.size).toBeGreaterThan(0);

  // Select directory: FULL uses the same dir as both ① and ②.
  if (mode === "full") {
    await page.locator('[data-testid="upload-initial-input"]').setInputFiles(inputRoot);
  }
  await page.locator('[data-testid="upload-modified-input"]').setInputFiles(inputRoot);

  // Intercept the upload: packaging is done when the request fires.
  let manifestMultipartBytes: number | null = null;
  await page.route("**/v1/workspaces/*/upload-revisions", async (route) => {
    const buf = route.request().postDataBuffer();
    manifestMultipartBytes = buf ? buf.byteLength : null;
    return route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ code: "SERVICE_NOT_READY", message: "M1 probe" }),
    });
  });

  const scenarios: Array<{
    run: number;
    wallMs: number;
    manifestMultipartBytes: number | null;
    processes: Array<{ pid: number; peakBytes: number | null; baseBytes: number | null; incrementBytes: number | null }>;
  }> = [];
  for (let run = 0; run < runs; run += 1) {
    const start = Date.now();
    await page.getByRole("button", { name: "上传并生成预览" }).click();
    await page.waitForResponse("**/v1/workspaces/*/upload-revisions", { timeout: 300000 });
    const wallMs = Date.now() - start;
    const processes = [];
    for (const [pid, base] of baselines) {
      const peak = await readVmHWM(pid);
      processes.push({
        pid,
        peakBytes: peak,
        baseBytes: base,
        incrementBytes: peak != null && base != null ? peak - base : null,
      });
    }
    scenarios.push({ run: run + 1, wallMs, manifestMultipartBytes, processes });
    // Reload for the next run so each packaging starts from a clean page.
    if (run + 1 < runs) {
      await page.reload();
      await expect(page.getByRole("heading", { name: "组态树", level: 1 })).toBeVisible();
      if (mode === "full") {
        await page.locator('[data-testid="upload-initial-input"]').setInputFiles(inputRoot);
      }
      await page.locator('[data-testid="upload-modified-input"]').setInputFiles(inputRoot);
      for (const pid of baselines.keys()) {
        await writeProc(`/proc/${pid}/clear_refs`, "5").catch(() => null);
        baselines.set(pid, await readVmHWM(pid));
      }
    }
  }

  const increments = scenarios.map((s) =>
    s.processes.reduce((max, p) => Math.max(max, p.incrementBytes ?? 0), 0),
  );
  const sorted = [...increments].sort((a, b) => a - b);
  await writeFile(
    reportPath,
    JSON.stringify(
      {
        inputRoot,
        mode,
        runs,
        fileCount,
        dirBytes,
        measuredAt: new Date().toISOString(),
        scenarios,
        maxIncrementBytes: Math.max(...increments),
        medianIncrementBytes: sorted[Math.floor(sorted.length / 2)],
        maxWallMs: Math.max(...scenarios.map((s) => s.wallMs)),
      },
      null,
      2,
    ) + "\n",
  );
});
