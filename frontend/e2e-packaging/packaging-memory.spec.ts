import { expect, test, type Browser } from "@playwright/test";
import { chromium } from "@playwright/test";
import { readFile, readdir, stat, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { GatewaySession } from "../src/features/api/session";

/**
 * FE3a M1 packaging peak-memory measurement (frontend kickoff §8.4).
 *
 * Environment:
 *   GATEWAY_M1_INPUT_ROOT  selected root directory (read-only mount)
 *   GATEWAY_M1_MODE        modified|full
 *   GATEWAY_M1_REPORT      absolute JSON report path
 *   GATEWAY_M1_RUNS        repeat count (default 3)
 *
 * Each run launches a FRESH browser (kickoff §8.4). After both directories
 * are selected and before the click, every Chromium process gets
 * /proc/<pid>/clear_refs = 5 (zero VmHWM) and its VmHWM/VmRSS baseline;
 * the upload request is route-intercepted (503), so the peak increment and
 * the measured packaging interval only cover packaging (read + tar + gzip +
 * sha256) up to the upload request. Process types come from the browser-level
 * CDP SystemInfo.getProcessInfo; renderer is the main metric.
 */

test.setTimeout(15 * 60_000);

interface ProcessSnapshot {
  pid: number;
  kind: string;
  baseHwmBytes: number | null;
  baseRssBytes: number | null;
  peakBytes: number | null;
  incrementBytes: number | null;
}

interface Scenario {
  run: number;
  packagingMs: number | null;
  wallMs: number;
  uploadRequestMs: number;
  manifestBytes: number | null;
  manifest: unknown;
  inputCompleteness: string | null;
  initialSizeBytes: number | null;
  modifiedSizeBytes: number | null;
  jsHeapUsedBytes: number | null;
  processes: ProcessSnapshot[];
}

interface ProcAddress {
  pid: number;
  kind: string;
}

async function dirStats(root: string): Promise<{ files: number; bytes: number }> {
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

async function readProcStatus(pid: number): Promise<{ hwmBytes: number; rssBytes: number } | null> {
  try {
    const status = await readFile(`/proc/${pid}/status`, "utf8");
    const hwm = status.match(/VmHWM:\s+(\d+)\s+kB/);
    const rss = status.match(/VmRSS:\s+(\d+)\s+kB/);
    if (!hwm || !rss) return null;
    return { hwmBytes: Number(hwm[1]) * 1024, rssBytes: Number(rss[1]) * 1024 };
  } catch {
    return null;
  }
}

async function browserProcs(browser: Browser): Promise<ProcAddress[]> {
  const session = await browser.newBrowserCDPSession();
  try {
    const info = (await session.send("SystemInfo.getProcessInfo")) as {
      processInfo: Array<{ id: number; type: string }>;
    };
    return info.processInfo.map((p) => ({ pid: p.id, kind: p.type }));
  } finally {
    await session.detach().catch(() => undefined);
  }
}

/** Zero VmHWM on every process, then record HWM/RSS baselines. */
async function baselineProcesses(browser: Browser): Promise<Map<number, ProcessSnapshot>> {
  const procs = await browserProcs(browser);
  expect(procs.length).toBeGreaterThan(0);
  const baselines = new Map<number, ProcessSnapshot>();
  for (const { pid, kind } of procs) {
    await writeFile(`/proc/${pid}/clear_refs`, "5");
    const status = await readProcStatus(pid);
    baselines.set(pid, {
      pid,
      kind,
      baseHwmBytes: status?.hwmBytes ?? null,
      baseRssBytes: status?.rssBytes ?? null,
      peakBytes: null,
      incrementBytes: null,
    });
  }
  return baselines;
}

async function snapshotProcesses(browser: Browser, baselines: Map<number, ProcessSnapshot>): Promise<ProcessSnapshot[]> {
  const procs = await browserProcs(browser);
  const seen = new Set<number>();
  const snapshots: ProcessSnapshot[] = [];
  for (const { pid, kind } of procs) {
    seen.add(pid);
    const base = baselines.get(pid);
    const status = await readProcStatus(pid);
    snapshots.push({
      pid,
      kind,
      baseHwmBytes: base?.baseHwmBytes ?? null,
      baseRssBytes: base?.baseRssBytes ?? null,
      peakBytes: status?.hwmBytes ?? null,
      incrementBytes: status && base?.baseHwmBytes != null ? status.hwmBytes - base.baseHwmBytes : null,
    });
  }
  for (const [pid, base] of baselines) {
    if (seen.has(pid)) continue;
    snapshots.push({ ...base, peakBytes: null, incrementBytes: null });
  }
  return snapshots;
}

function parseManifest(body: Buffer | null, contentType: string | null): {
  manifest: unknown;
  inputCompleteness: string | null;
  initialSizeBytes: number | null;
  modifiedSizeBytes: number | null;
} {
  if (!body) return { manifest: null, inputCompleteness: null, initialSizeBytes: null, modifiedSizeBytes: null };
  const boundaryMatch = /boundary=(?:"([^"]+)"|([^;]+))/.exec(contentType ?? "");
  const boundary = (boundaryMatch?.[1] ?? boundaryMatch?.[2] ?? "").trim();
  if (!boundary) return { manifest: null, inputCompleteness: null, initialSizeBytes: null, modifiedSizeBytes: null };
  const parts = body.toString("latin1").split(`--${boundary}`);
  const part = parts.find((candidate) => /name="manifest"/.test(candidate));
  if (!part) return { manifest: null, inputCompleteness: null, initialSizeBytes: null, modifiedSizeBytes: null };
  const headerEnd = part.indexOf("\r\n\r\n");
  if (headerEnd < 0) return { manifest: null, inputCompleteness: null, initialSizeBytes: null, modifiedSizeBytes: null };
  const jsonText = part.slice(headerEnd + 4).replace(/\r\n$/, "").trim();
  try {
    const parsed = JSON.parse(jsonText) as {
      input_completeness?: string;
      artifacts?: {
        INITIAL?: { size_bytes?: number };
        MODIFIED?: { size_bytes?: number };
      };
    };
    return {
      manifest: parsed,
      inputCompleteness: parsed.input_completeness ?? null,
      initialSizeBytes: parsed.artifacts?.INITIAL?.size_bytes ?? null,
      modifiedSizeBytes: parsed.artifacts?.MODIFIED?.size_bytes ?? null,
    };
  } catch {
    return { manifest: null, inputCompleteness: null, initialSizeBytes: null, modifiedSizeBytes: null };
  }
}

async function observePhases(page: import("@playwright/test").Page): Promise<void> {
  await page.evaluate(() => {
    const recorded: Array<{ phase: string; at: number }> = [];
    (window as unknown as { __m1Phases: typeof recorded }).__m1Phases = recorded;
    const record = (): void => {
      const section = document.querySelector("section.upload-card");
      const phase = section?.getAttribute("data-phase");
      if (!phase) return;
      if (recorded.length === 0 || recorded[recorded.length - 1]!.phase !== phase) {
        recorded.push({ phase, at: performance.now() });
      }
    };
    record();
    new MutationObserver(record).observe(document.body, { subtree: true, attributes: true, attributeFilter: ["data-phase"] });
  });
}

async function readPhases(page: import("@playwright/test").Page): Promise<Array<{ phase: string; at: number }>> {
  return page.evaluate(() => (window as unknown as { __m1Phases?: Array<{ phase: string; at: number }> }).__m1Phases ?? []);
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
    active_submission_id: null,
    active_submit_attempt_id: null,
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

  const scenarios: Scenario[] = [];

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

      // FULL uses the same directory for ① (initial) and ② (modified).
      if (mode === "full") {
        const initial = page.locator('[data-testid="upload-initial-input"]');
        await initial.evaluate((el) => el.classList.remove("sr-only"));
        await initial.setInputFiles(inputRoot);
        await expect(page.getByText("原始备份 + 本次归档", { exact: false })).toBeVisible({ timeout: 30000 });
      }
      const modified = page.locator('[data-testid="upload-modified-input"]');
      await modified.evaluate((el) => el.classList.remove("sr-only"));
      await modified.setInputFiles(inputRoot);

      // Baselines after directory selection, immediately before packaging.
      const baselines = await baselineProcesses(browser);

      let manifestBody: Buffer | null = null;
      let manifestContentType: string | null = null;
      await page.route("**/v1/workspaces/*/upload-revisions", async (route) => {
        manifestBody = route.request().postDataBuffer();
        manifestContentType = route.request().headers()["content-type"] ?? null;
        return route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ code: "SERVICE_NOT_READY", message: "M1 probe" }),
        });
      });

      await observePhases(page);
      const uploadResponse = page.waitForResponse("**/v1/workspaces/*/upload-revisions", { timeout: 600000 });
      const clickAt = Date.now();
      await page.getByRole("button", { name: "上传并生成预览" }).click();
      await uploadResponse;
      const wallMs = Date.now() - clickAt;

      const phases = await readPhases(page);
      const packagingAt = phases.find((entry) => entry.phase === "packaging")?.at ?? null;
      const uploadingAt = phases.find((entry) => entry.phase === "uploading")?.at ?? null;
      const packagingMs = packagingAt != null && uploadingAt != null && uploadingAt >= packagingAt
        ? Math.round(uploadingAt - packagingAt)
        : null;
      const parsed = parseManifest(manifestBody, manifestContentType);
      const jsHeapUsedBytes = await page.evaluate(() => {
        const memory = (performance as Performance & { memory?: { usedJSHeapSize?: number } }).memory;
        return memory?.usedJSHeapSize ?? null;
      });
      const processes = await snapshotProcesses(browser, baselines);

      scenarios.push({
        run: run + 1,
        packagingMs,
        wallMs,
        uploadRequestMs: wallMs,
        manifestBytes: manifestBody?.byteLength ?? null,
        manifest: parsed.manifest,
        inputCompleteness: parsed.inputCompleteness,
        initialSizeBytes: parsed.initialSizeBytes,
        modifiedSizeBytes: parsed.modifiedSizeBytes,
        jsHeapUsedBytes,
        processes,
      });
      await context.close();
    } finally {
      await browser.close();
    }
  }

  const rendererIncrement = (scenario: Scenario): number =>
    scenario.processes
      .filter((process) => /renderer/i.test(process.kind))
      .reduce((max, process) => Math.max(max, process.incrementBytes ?? 0), 0);
  const rendererIncrements = scenarios.map(rendererIncrement);
  const sortedRenderers = [...rendererIncrements].sort((a, b) => a - b);
  const packagingTimes = scenarios.map((scenario) => scenario.packagingMs).filter((value): value is number => value != null);
  const sortedPackaging = [...packagingTimes].sort((a, b) => a - b);

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
        rendererMedianIncrementBytes: sortedRenderers[Math.floor(sortedRenderers.length / 2)] ?? 0,
        packagingMaxMs: packagingTimes.length ? Math.max(...packagingTimes) : null,
        packagingMedianMs: sortedPackaging.length ? sortedPackaging[Math.floor(sortedPackaging.length / 2)] : null,
        modifiedSizeMaxBytes: Math.max(...scenarios.map((scenario) => scenario.modifiedSizeBytes ?? 0)),
        initialSizeMaxBytes: Math.max(...scenarios.map((scenario) => scenario.initialSizeBytes ?? 0)),
      },
      null,
      2,
    ) + "\n",
  );
});
