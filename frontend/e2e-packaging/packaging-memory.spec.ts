import { expect, test, type Browser } from "@playwright/test";
import { execFile } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import { promisify } from "node:util";
import { chromium } from "@playwright/test";
import type { GatewaySession } from "../src/features/api/session";

const execFileAsync = promisify(execFile);

/**
 * FE3a M1 packaging peak-memory measurement (frontend kickoff §8.4).
 *
 * Environment:
 *   GATEWAY_M1_INPUT_ROOT  selected root directory (read-only mount)
 *   GATEWAY_M1_MODE        modified|full
 *   GATEWAY_M1_REPORT      absolute JSON report path
 *   GATEWAY_M1_RUNS        repeat count (default 3)
 *
 * Each run launches a FRESH browser (kickoff §8.4). After page load the
 * per-process VmHWM peaks are zeroed via /proc/<pid>/clear_refs (=5) and
 * baselines recorded; the upload request fires only after packaging
 * (read + tar + gzip + sha256) finishes, so wall time and the VmHWM
 * increment cover packaging. The upload request is route-intercepted
 * (503): no backend is needed. Process types come from the browser-level
 * CDP SystemInfo.getProcessInfo; the renderer increment is the main metric.
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
        bytes += Number((await stat(full)).size);
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

interface ProcInfo {
  pid: number;
  kind: string;
}

async function browserProcs(browser: Browser): Promise<ProcInfo[]> {
  try {
    const session = await browser.newBrowserCDPSession();
    const info = (await session.send("SystemInfo.getProcessInfo")) as {
      processInfo: Array<{ id: number; type: string }>;
    };
    return info.processInfo.map((p) => ({ pid: p.id, kind: p.type }));
  } catch {
    const found: ProcInfo[] = [];
    for (const pattern of ["chrome", "headless", "playwright"]) {
      const { stdout } = await execFileAsync("pgrep", ["-f", pattern]).catch(() => ({ stdout: "" }));
      const pids = stdout.split("\n").map((s) => Number(s.trim())).filter(Boolean);
      if (pids.length > 0) return pids.map((pid) => ({ pid, kind: "unknown" }));
    }
    return found;
  }
}

test("M1 packaging peak memory", async () => {
  const inputRoot = process.env.GATEWAY_M1_INPUT_ROOT;
  const mode = process.env.GATEWAY_M1_MODE ?? "modified";
  const reportPath = process.env.GATEWAY_M1_REPORT;
  if (!inputRoot || !reportPath || (mode !== "modified" && mode !== "full")) {
    throw new Error("GATEWAY_M1_INPUT_ROOT / GATEWAY_M1_MODE=modified|full / GATEWAY_M1_REPORT are required");
  }
  const runs = Number(process.env.GATEWAY_M1_RUNS ?? "3");
  const { files: fileCount, bytes: dirBytes } = await dirStats(inputRoot);

  const stubWorkspace = {
    workspace_id: "m1-probe",
    gateway_device_external_key: "m1-device",
    business_project_id: "m1-project",
    state: "OPEN",
    generation: 1,
    optimistic_version: 1,
    created_at: "2026-11-05T00:00:00Z",
    updated_at: "2026-11-05T00:00:00Z",
    current_upload_revision_id: null,
    current_preview_result_id: null,
  };
  const stubHistory = {
    head: { node_id: "m1-baseline", commit_id: "m1-commit", version: 1 },
    nodes: [
      {
        ref_kind: "baseline_node",
        ref_id: "m1-baseline",
        node_kind: "BASELINE_NODE",
        baseline_kind: "INITIAL",
        commit_id: "m1-commit",
        created_at: "2026-11-05T00:00:00Z",
        parent: null,
        identity_exception: false,
      },
    ],
    next_cursor: null,
  };

  const scenarios: Array<{
    run: number;
    wallMs: number;
    manifestMultipartBytes: number | null;
    processes: Array<{
      pid: number;
      kind: string;
      peakBytes: number | null;
      baseBytes: number | null;
      incrementBytes: number | null;
    }>;
  }> = [];

  for (let run = 0; run < runs; run += 1) {
    const browser = await chromium.launch({ args: ["--enable-precise-memory-info"] });
    try {
      const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
      await context.route("**/v1/workspaces", async (route) => {
        if (route.request().method() !== "POST") return route.fallback();
        return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(stubWorkspace) });
      });
      await context.route("**/v1/history*", async (route) => {
        if (route.request().method() !== "GET") return route.fallback();
        return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(stubHistory) });
      });
      await context.addInitScript(() => {
        (window as unknown as { __gatewaySession: GatewaySession }).__gatewaySession = {
          accessToken: "Bearer m1-probe",
          businessProjectId: "m1-project",
          gatewayDeviceExternalKey: "m1-device",
        };
      });
      const page = await context.newPage();
      await page.goto("/");
      await expect(page.getByRole("heading", { name: "组态树", level: 1 })).toBeVisible({ timeout: 30000 });
      await expect(page.getByLabel("上传与预览")).toBeVisible({ timeout: 30000 });

      // Zero peaks after page load, record baselines with process kinds.
      const targets = await browserProcs(browser);
      expect(targets.length).toBeGreaterThan(0);
      const baselines = new Map<number, { base: number | null; kind: string }>();
      for (const { pid, kind } of targets) {
        await writeFile(`/proc/${pid}/clear_refs`, "5").catch(() => null);
        baselines.set(pid, { base: await readVmHWM(pid), kind });
      }

      // Select directory: FULL uses the same dir as both ① and ②.
      if (mode === "full") {
        const initial = page.locator('[data-testid="upload-initial-input"]');
        await initial.evaluate((el) => el.classList.remove("sr-only"));
        await initial.setInputFiles(inputRoot);
      }
      const modified = page.locator('[data-testid="upload-modified-input"]');
      await modified.evaluate((el) => el.classList.remove("sr-only"));
      await modified.setInputFiles(inputRoot);

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

      const start = Date.now();
      await page.getByRole("button", { name: "上传并生成预览" }).click();
      await page.waitForResponse("**/v1/workspaces/*/upload-revisions", { timeout: 300000 });
      const wallMs = Date.now() - start;

      const processes = [];
      for (const [pid, { base, kind }] of baselines) {
        const peak = await readVmHWM(pid);
        processes.push({
          pid,
          kind,
          peakBytes: peak,
          baseBytes: base,
          incrementBytes: peak != null && base != null ? peak - base : null,
        });
      }
      scenarios.push({ run: run + 1, wallMs, manifestMultipartBytes, processes });
      await context.close();
    } finally {
      await browser.close();
    }
  }

  const rendererMax = (s: (typeof scenarios)[number]): number =>
    s.processes
      .filter((p) => /renderer/i.test(p.kind))
      .reduce((max, p) => Math.max(max, p.incrementBytes ?? 0), 0);
  const rendererIncrements = scenarios.map(rendererMax);
  const sorted = [...rendererIncrements].sort((a, b) => a - b);
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
        rendererMaxIncrementBytes: Math.max(...rendererIncrements),
        rendererMedianIncrementBytes: sorted[Math.floor(sorted.length / 2)],
        maxWallMs: Math.max(...scenarios.map((s) => s.wallMs)),
      },
      null,
      2,
    ) + "\n",
  );
});
