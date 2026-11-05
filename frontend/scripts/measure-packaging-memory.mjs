#!/usr/bin/env node
/**
 * FE3a M1: packaging peak-memory measurement (frontend kickoff §8.4).
 *
 * Measures, for one directory and one packaging mode:
 *   - directory bytes + file count, compressed package bytes
 *   - packaging wall time (from the upload step card's phase timer)
 *   - Chromium process VmHWM peak increments (renderer + browser + GPU +
 *     utility/network), via browser CDP SystemInfo.getProcessInfo with a
 *     /proc fallback
 *
 * Each scenario runs 3 times in a fresh browser; the report prints the
 * median and max per process. The upload request is route-intercepted
 * (returns 503) so no backend is needed; packaging already finished when
 * the request is issued.
 *
 * Usage:
 *   node scripts/measure-packaging-memory.mjs --input-root <dir>
 *     --mode modified|full --runs 3 --output <report-json>
 *
 * `--input-root` holds one selected root directory per scenario run:
 * for MODIFIED_ONLY a single directory; for FULL the same directory is
 * used as both ① and ② (kickoff §8.4).
 */
import { readdir, stat } from "node:fs/promises";
import { join } from "node:path";
import { exit, argv, env } from "node:process";
import { chromium } from "@playwright/test";

const args = new Map();
for (let i = 2; i < argv.length; i += 2) args.set(argv[i], argv[i + 1]);
const inputRoot = args.get("--input-root");
const mode = args.get("--mode") ?? "modified";
const runs = Number(args.get("--runs") ?? "3");
const output = args.get("--output");
if (!inputRoot || !output || (mode !== "modified" && mode !== "full")) {
  console.error(
    "usage: measure-packaging-memory.mjs --input-root <dir> --mode modified|full --runs <n> --output <report-json>",
  );
  exit(2);
}

async function dirStats(root) {
  let files = 0;
  let bytes = 0;
  async function walk(dir) {
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

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
}

const { files: fileCount, bytes: dirBytes } = await dirStats(inputRoot);
console.log(`input: ${inputRoot} files=${fileCount} bytes=${dirBytes} mode=${mode} runs=${runs}`);

const scenarios = [];
for (let run = 0; run < runs; run += 1) {
  const browser = await chromium.launch({ args: ["--enable-precise-memory-info"] });
  try {
    const context = await browser.newContext();
    const page = await context.newPage();

    // Resolve renderer PIDs via browser-level CDP; fall back to /proc scan.
    let pids = [];
    try {
      const session = await browser.newBrowserCDPSession();
      const info = await session.send("SystemInfo.getProcessInfo");
      pids = info.processInfo
        .filter((p) => /renderer|browser|gpu|utility|network/i.test(p.type + " " + (p.cpuTime ?? "")))
        .map((p) => p.id);
      if (pids.length === 0) pids = info.processInfo.map((p) => p.id);
    } catch {
      pids = [];
    }

    const { readFile } = await import("node:fs/promises");
    async function readVmHWM(pid) {
      try {
        const status = await readFile(`/proc/${pid}/status`, "utf8");
        const m = status.match(/VmHWM:\s+(\d+)\s+kB/);
        return m ? Number(m[1]) * 1024 : null;
      } catch {
        return null;
      }
    }

    await page.goto("/");
    await page.getByRole("heading", { name: "组态树", level: 1 }).waitFor();

    // Zero the peaks after page load, record baselines.
    const { execFile } = await import("node:child_process");
    const { promisify } = await import("node:util");
    const execFileAsync = promisify(execFile);
    let targets = pids;
    if (targets.length === 0) {
      const { stdout } = await execFileAsync("pgrep", ["-f", "chrome.*type="]).catch(() => ({ stdout: "" }));
      targets = stdout.split("\n").map((s) => Number(s.trim())).filter(Boolean);
      if (targets.length === 0) {
        const { stdout: all } = await execFileAsync("pgrep", ["-f", "chrome"]).catch(() => ({ stdout: "" }));
        targets = all.split("\n").map((s) => Number(s.trim())).filter(Boolean);
      }
    }
    const baselines = new Map();
    for (const pid of targets) {
      try {
        await readFile(`/proc/${pid}/clear_refs`).catch(() => null);
        const { writeFile } = await import("node:fs/promises");
        await writeFile(`/proc/${pid}/clear_refs`, "5").catch(() => null);
        baselines.set(pid, await readVmHWM(pid));
      } catch {
        /* process may have exited */
      }
    }

    // Select directory(s): MODIFIED_ONLY selects only ②; FULL selects
    // the same dir as both ① and ② (kickoff §8.4: ① and ② both large-1).
    if (mode === "full") {
      await page.locator('[data-testid="upload-initial-input"]').setInputFiles(inputRoot);
    }
    await page.locator('[data-testid="upload-modified-input"]').setInputFiles(inputRoot);

    // Intercept the upload: packaging is done when the request fires.
    let manifestSize = null;
    await page.route("**/v1/workspaces/*/upload-revisions", async (route) => {
      const buf = route.request().postDataBuffer();
      manifestSize = buf ? buf.byteLength : null;
      return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ code: "SERVICE_NOT_READY", message: "M1 probe" }) });
    });

    const start = Date.now();
    await page.getByRole("button", { name: "上传并生成预览" }).click();
    await page.waitForResponse("**/v1/workspaces/*/upload-revisions", { timeout: 300000 });
    const wallMs = Date.now() - start;

    // Read peaks.
    const peaks = [];
    for (const pid of baselines.keys()) {
      const peak = await readVmHWM(pid);
      const base = baselines.get(pid);
      if (peak != null) peaks.push({ pid, peakBytes: peak, baseBytes: base ?? null, incrementBytes: base != null ? peak - base : null });
    }

    // Packaging time from the step card phase timer (seconds) is rendered
    // only after advance(); wall time above covers file read + gzip + sha256.
    scenarios.push({ run: run + 1, wallMs, manifestMultipartBytes: manifestSize, processes: peaks });
    console.log(`run ${run + 1}: wallMs=${wallMs} processes=${peaks.length} manifestBytes=${manifestSize}`);
    await context.close();
  } finally {
    await browser.close();
  }
}

const increments = scenarios.map((s) =>
  s.processes.reduce((max, p) => Math.max(max, p.incrementBytes ?? 0), 0),
);
const { writeFile } = await import("node:fs/promises");
await writeFile(
  output,
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
      medianIncrementBytes: median(increments),
      maxWallMs: Math.max(...scenarios.map((s) => s.wallMs)),
      medianWallMs: median(scenarios.map((s) => s.wallMs)),
    },
    null,
    2,
  ) + "\n",
);
console.log(`report: ${output}`);
console.log(`maxIncrementBytes=${Math.max(...increments)} medianIncrementBytes=${median(increments)}`);
void env;
