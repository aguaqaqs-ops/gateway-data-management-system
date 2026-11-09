import { test, expect, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { readdir, readFile, stat, writeFile } from "node:fs/promises";
import { join } from "node:path";
import {
  appendCaseLog,
  collectPageDiagnostics,
  compareAction,
  contextForIdentity,
  expectNoPageErrors,
  gotoWorkbench,
  recordBundleResponses,
  saveEvidence,
  selectTreeRow,
  selectUploadDirs,
  startUpload,
  waitForDiffBrowsing,
  waitForInstalledBundle,
  waitForPreviewOutcome,
  workshopAction,
} from "./lib/ui";
import {
  appendArchiveAnomalyResolution,
  applyReview,
  getPreviewResult,
  getReviewFacts,
  listArchiveCandidates,
  listHistory,
  previewArchivePlan,
  waitForOperation,
  waitForPendingSubmission,
} from "./lib/api";
import { digestHex, parseBundleTar, type ParsedBundle } from "./lib/tar";
import { identityFor, scopeBySlug, type JourneyIdentity, type JourneyScope } from "./lib/env";

/**
 * FE3c t1 real-data journey (kickoff §8): one independent scope over the
 * read-only t1 source dirs. Step 4 is FULL; M1 is re-measured in-journey at
 * steps 1 (MODIFIED_ONLY) and 4 (FULL) and reported against the FE3a t1
 * numbers without extrapolation (Q20).
 */

test.setTimeout(1_800_000);

interface T1Expected {
  S2B_DATASET_BASELINE: Record<string, { preview_table_count: number }>;
  S1B_V2_PREVIEW_CHANGED_COUNTS: Record<string, number>;
}

function requireT1Env(): { scope: JourneyScope; submitter: JourneyIdentity; reviewer: JourneyIdentity; archiver: JourneyIdentity; inputRoot: string; expected: T1Expected } {
  const missing = ["GATEWAY_FE_IDENTITIES", "GATEWAY_FE_JOURNEY_SCOPES", "GATEWAY_FE_T1_INPUT_ROOT", "GATEWAY_FE_T1_EXPECTED_JSON"]
    .filter((name) => !process.env[name]);
  test.skip(missing.length > 0, `t1 suite requires ${missing.join(", ")}; run scripts/run-real-backend-e2e.sh --suite t1`);
  return {
    scope: scopeBySlug("t1"),
    submitter: identityFor(scopeBySlug("t1"), "submitter"),
    reviewer: identityFor(scopeBySlug("t1"), "reviewer"),
    archiver: identityFor(scopeBySlug("t1"), "archiver"),
    inputRoot: process.env.GATEWAY_FE_T1_INPUT_ROOT as string,
    expected: JSON.parse(process.env.GATEWAY_FE_T1_EXPECTED_JSON as string) as T1Expected,
  };
}

async function readProcStatus(pid: number): Promise<{ hwmBytes: number; rssBytes: number; rssAnon: number | null; rssFile: number | null; rssShmem: number | null } | null> {
  try {
    const status = await readFile(`/proc/${pid}/status`, "utf8");
    const num = (key: string): number | null => {
      const match = status.match(new RegExp(`${key}:\\s+(\\d+)\\s+kB`));
      return match ? Number(match[1]) * 1024 : null;
    };
    const hwmBytes = num("VmHWM");
    const rssBytes = num("VmRSS");
    if (hwmBytes === null || rssBytes === null) return null;
    return { hwmBytes, rssBytes, rssAnon: num("RssAnon"), rssFile: num("RssFile"), rssShmem: num("RssShmem") };
  } catch {
    return null;
  }
}

async function browserProcs(browser: Browser): Promise<Array<{ pid: number; kind: string }>> {
  const session = await browser.newBrowserCDPSession();
  try {
    const info = (await session.send("SystemInfo.getProcessInfo")) as { processInfo: Array<{ id: number; type: string }> };
    return info.processInfo.map((p) => ({ pid: p.id, kind: p.type }));
  } finally {
    await session.detach().catch(() => undefined);
  }
}

interface M1Sample {
  atMs: number;
  rssAnonMax: number | null;
  rssFileMax: number | null;
  rssShmemMax: number | null;
}

/** Baseline every Chromium process, then sample RssAnon/RssFile/RssShmem every ~100ms until stop. */
async function measurePackaging(browser: Browser, during: () => Promise<void>): Promise<{ rendererIncrementBytes: number | null; samples: M1Sample[]; maxRssAnon: number | null; maxRssFile: number | null; maxRssShmem: number | null }> {
  const procs = await browserProcs(browser);
  expect(procs.length, "chromium processes visible").toBeGreaterThan(0);
  const baselines = new Map<number, { kind: string; hwm: number; rss: number }>();
  for (const { pid, kind } of procs) {
    try {
      await writeFile(`/proc/${pid}/clear_refs`, "5");
    } catch {
      // A process that exits mid-baseline is skipped below.
    }
    const status = await readProcStatus(pid);
    if (status) baselines.set(pid, { kind, hwm: status.hwmBytes, rss: status.rssBytes });
  }
  const startedAt = Date.now();
  const samples: M1Sample[] = [];
  let stopped = false;
  const sampler = (async () => {
    while (!stopped) {
      const current = await browserProcs(browser).catch(() => []);
      let anon: number | null = null;
      let file: number | null = null;
      let shmem: number | null = null;
      for (const { pid } of current) {
        const status = await readProcStatus(pid);
        if (!status) continue;
        if (status.rssAnon !== null) anon = Math.max(anon ?? 0, status.rssAnon);
        if (status.rssFile !== null) file = Math.max(file ?? 0, status.rssFile);
        if (status.rssShmem !== null) shmem = Math.max(shmem ?? 0, status.rssShmem);
      }
      samples.push({ atMs: Date.now() - startedAt, rssAnonMax: anon, rssFileMax: file, rssShmemMax: shmem });
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  })();
  await during();
  stopped = true;
  await sampler;
  const finals = await browserProcs(browser).catch(() => []);
  let rendererIncrement: number | null = null;
  for (const { pid, kind } of finals) {
    if (kind !== "renderer") continue;
    const status = await readProcStatus(pid);
    const base = baselines.get(pid);
    if (status && base) rendererIncrement = (rendererIncrement ?? 0) + (status.hwmBytes - base.hwm);
  }
  const maxOf = (pick: (sample: M1Sample) => number | null): number | null => {
    let max: number | null = null;
    for (const sample of samples) {
      const value = pick(sample);
      if (value !== null) max = Math.max(max ?? 0, value);
    }
    return max;
  };
  return {
    rendererIncrementBytes: rendererIncrement,
    samples,
    maxRssAnon: maxOf((sample) => sample.rssAnonMax),
    maxRssFile: maxOf((sample) => sample.rssFileMax),
    maxRssShmem: maxOf((sample) => sample.rssShmemMax),
  };
}

function pairSummary(bundle: ParsedBundle, pairId: string): Record<string, string> {
  const pair = bundle.manifest.pairs.find((item) => item.pair_id === pairId);
  expect(pair, `pair ${pairId} present`).toBeTruthy();
  return pair!.summary;
}

function compositeChanged(bundle: ParsedBundle, pairId: string): number | null {
  const member = bundle.members.find((item) => item.path === `pairs/${pairId}/comparison-surface.json`);
  if (!member) return null;
  const surface = JSON.parse(member.body.toString("utf8")) as { tables?: Array<{ table_name?: string; display_name?: string; table_status?: string }> };
  const table = (surface.tables ?? []).find((item) => item.table_name === "composite_signal_point" || item.display_name === "composite_signal_point");
  if (!table?.table_status) return null;
  return table.table_status === "UNCHANGED" || table.table_status === "BUSINESS_EQUIVALENT" ? 0 : 1;
}

test("t1 real-data journey with M1 re-measurement", async ({ browser }, testInfo) => {
  const { submitter, reviewer, archiver, inputRoot, expected } = requireT1Env();
  const v1Dir = join(inputRoot, "t1-v1");
  const v2Dir = join(inputRoot, "t1-v2");
  for (const dir of [v1Dir, v2Dir]) {
    const entries = await readdir(dir);
    expect(entries.filter((name) => name.endsWith(".pmc")), `${dir} has one .pmc`).toHaveLength(1);
    await stat(join(dir, "sql", "dbcfg.sql"));
    await stat(join(dir, "comps", "logic", "logics.xml"));
    appendCaseLog(`t1-input dir=${dir} entries=${entries.length}`);
  }
  const t1a = "rd-t1-a-v1";
  const t1b = "rd-t1-a-v2";
  const v1PreviewCount = expected.S2B_DATASET_BASELINE[t1a]?.preview_table_count;
  const v2PreviewCount = expected.S2B_DATASET_BASELINE[t1b]?.preview_table_count;
  const v2Changed = expected.S1B_V2_PREVIEW_CHANGED_COUNTS[t1b];
  expect(v1PreviewCount, "t1 v1 preview_table_count readable").toBe(124);
  expect(v2PreviewCount, "t1 v2 preview_table_count readable").toBe(124);
  expect(v2Changed, "t1 v2 changed count readable").toBe(4);

  const context: BrowserContext = await contextForIdentity(browser, submitter);
  const page: Page = await context.newPage();
  await page.setViewportSize({ width: 1920, height: 1080 });
  const diagnostics = collectPageDiagnostics(page);
  const m1: Array<{ step: string; rendererIncrementBytes: number | null; maxRssAnon: number | null; maxRssFile: number | null; maxRssShmem: number | null }> = [];

  try {
    // Step 1: t1 v1 MODIFIED_ONLY on the empty INITIAL baseline.
    // Baselines go in after directory selection, immediately before packaging.
    await gotoWorkbench(page);
    await selectUploadDirs(page, { modified: v1Dir });
    const recording1 = recordBundleResponses(page);
    const uploadWait1 = page.waitForResponse((response) => response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/upload-revisions"), { timeout: 300_000 });
    const previewWait1 = page.waitForResponse((response) => response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/preview-operations"), { timeout: 300_000 });
    const measured1 = await measurePackaging(browser, async () => {
      await startUpload(page);
      await uploadWait1;
    });
    const upload1 = await uploadWait1;
    expect(upload1.status(), "step1 upload status").toBe(201);
    const preview1 = await previewWait1;
    expect(preview1.status(), "step1 preview status").toBe(202);
    const operation1 = await waitForOperation(submitter, ((await preview1.json()) as { operation_id: string }).operation_id, 600_000);
    expect(operation1.status, "step1 preview operation").toBe("SUCCEEDED");
    m1.push({ step: "t1-v1-modified", rendererIncrementBytes: measured1.rendererIncrementBytes, maxRssAnon: measured1.maxRssAnon, maxRssFile: measured1.maxRssFile, maxRssShmem: measured1.maxRssShmem });
    expect(await waitForPreviewOutcome(page)).toBe("compare");
    const compareUrl1 = new URL(page.url());
    const workspaceId = compareUrl1.searchParams.get("workspaceId");
    const previewId1 = compareUrl1.searchParams.get("previewResultId");
    expect(workspaceId, "step1 workspaceId").toBeTruthy();
    expect(previewId1, "step1 previewId").toBeTruthy();
    const previewResult1 = (await getPreviewResult(submitter, workspaceId as string, previewId1 as string)).body;
    await waitForInstalledBundle(page, digestHex(previewResult1.bundle_digest));
    let bundle1: ParsedBundle | null = null;
    for (const recorded of [...recording1.responses].reverse()) {
      try {
        expect(recorded.status(), "step1 bundle status").toBe(200);
        bundle1 = parseBundleTar(Buffer.from(await recorded.body()));
        break;
      } catch {
        continue;
      }
    }
    expect(bundle1, "step1 bundle downloaded and installed").toBeTruthy();
    recording1.dispose();
    const summary1 = pairSummary(bundle1 as ParsedBundle, "initial_to_modified");
    expect(Number(summary1.table_count), "step1 table_count").toBe(v1PreviewCount + 1);
    expect(Number(summary1.changed_table_count), "step1 changed").toBe(v1PreviewCount + 1);
    expect(Number(summary1.degraded_table_count), "step1 degraded").toBe(0);
    expect(Number(summary1.failed_table_count), "step1 failed").toBe(0);
    await waitForDiffBrowsing(page);
    await saveEvidence(page, testInfo, "t1-v1-diff");

    // Submit v1.
    const submitWait = page.waitForResponse((response) => response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/submit-attempts"), { timeout: 300_000 });
    await compareAction(page, "提交").click();
    await page.getByRole("dialog").getByRole("button", { name: "确认提交", exact: true }).click();
    expect((await submitWait).status(), "step1 submit status").toBe(202);
    const { submission } = await waitForPendingSubmission(submitter, workspaceId as string, 600_000);
    const submissionV1 = submission.submission_id;

    // Step 2: approve as the reviewer.
    const factsV1 = (await getReviewFacts(reviewer, submissionV1)).body;
    expect(factsV1.status).toBe("PENDING");
    await applyReview(reviewer, submissionV1, { expected_review_version: factsV1.review_version, action: "APPROVE" });

    // Step 3: archive v1; t1 carries generation time, so no anomalies are expected.
    const listed3 = (await listArchiveCandidates(archiver)).body;
    const digestV1 = listed3.candidates.find((candidate) => candidate.submission_id === submissionV1)!.expected_candidate_digest;
    const plan3 = (await previewArchivePlan(archiver, { submission_id: submissionV1, expected_candidate_digest: digestV1 })).body;
    const codes3 = plan3.anomalies.map((anomaly) => anomaly.issue_code);
    appendCaseLog(`t1-step3 anomalies=${JSON.stringify(codes3)}`);
    for (const anomaly of plan3.anomalies) {
      expect(
        ["GENERATION_TIME_MISSING", "GENERATION_TIME_INVALID_VALUES", "GENERATION_TIME_LAST_NOT_MAX", "TIME_ABNORMAL_MODIFIED", "TIME_ABNORMAL_INITIAL"].includes(anomaly.issue_code),
        `t1-step3 unexpected code ${anomaly.issue_code} (stop for design review)`,
      ).toBe(true);
      const action = anomaly.issue_code.startsWith("TIME_ABNORMAL") ? "ACKNOWLEDGE_TIME_ORDER" : "ACKNOWLEDGE_TIME_QUALITY";
      await appendArchiveAnomalyResolution(archiver, {
        expected_baseline_node_id: plan3.head.business_baseline_node_id,
        expected_baseline_head_version: plan3.head.baseline_head_version,
        candidate_set_digest: plan3.candidate_set_digest,
        selected: { submission_id: submissionV1, expected_candidate_digest: digestV1 },
        subject_digest: anomaly.subject_digest,
        subject_kind: anomaly.subject_kind,
        issue_code: anomaly.issue_code,
        target_submission_id: anomaly.target_submission_id,
        target_candidate_digest: anomaly.target_candidate_digest,
        expected_sequence: anomaly.latest_sequence,
        action,
        reason: `t1 证据运行：${anomaly.issue_code}`,
      });
    }
    await gotoWorkbench(page);
    await page.getByRole("button", { name: "提交 1", exact: true }).click();
    await page.locator(".workspace-context-bar").getByRole("button", { name: "归档主线" }).click();
    const archiveDialog = page.getByRole("dialog", { name: "归档主基线" });
    await expect(archiveDialog.getByText("预检状态")).toBeVisible({ timeout: 60_000 });
    await archiveDialog.getByRole("checkbox", { name: /确认把/ }).check();
    await archiveDialog.getByRole("button", { name: "确认归档" }).click();
    await expect(archiveDialog.getByText("归档完成")).toBeVisible({ timeout: 300_000 });
    const headAfterArchive = (await listHistory(submitter)).body.head.version;
    appendCaseLog(`t1-step3 archived submission=${submissionV1} head=${headAfterArchive}`);
    expect(headAfterArchive, "t1-step3 head moved").toBe(1);
    await saveEvidence(page, testInfo, "t1-archive-v1");

    // Steps 4–5: FULL ①=t1-v1 ②=t1-v2, then approve.
    await gotoWorkbench(page);
    await selectUploadDirs(page, { modified: v2Dir, initial: v1Dir });
    const recording2 = recordBundleResponses(page);
    const previewWait2 = page.waitForResponse((response) => response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/preview-operations"), { timeout: 300_000 });
    const uploadWait2 = page.waitForResponse((response) => response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/upload-revisions"), { timeout: 300_000 });
    const measured2 = await measurePackaging(browser, async () => {
      await startUpload(page);
      await uploadWait2;
    });
    m1.push({ step: "t1-full", rendererIncrementBytes: measured2.rendererIncrementBytes, maxRssAnon: measured2.maxRssAnon, maxRssFile: measured2.maxRssFile, maxRssShmem: measured2.maxRssShmem });
    const preview2 = await previewWait2;
    expect(preview2.status(), "step4 preview status").toBe(202);
    const operation2 = await waitForOperation(submitter, ((await preview2.json()) as { operation_id: string }).operation_id, 900_000);
    expect(operation2.status, "step4 preview operation").toBe("SUCCEEDED");
    expect(await waitForPreviewOutcome(page)).toBe("compare");
    const compareUrl2 = new URL(page.url());
    const previewId2 = compareUrl2.searchParams.get("previewResultId");
    const workspaceId2 = compareUrl2.searchParams.get("workspaceId");
    expect(previewId2, "step4 previewId").toBeTruthy();
    expect(workspaceId2, "step4 workspaceId").toBeTruthy();
    const previewResult2 = (await getPreviewResult(submitter, workspaceId2 as string, previewId2 as string)).body;
    await waitForInstalledBundle(page, digestHex(previewResult2.bundle_digest));
    let bundle2: ParsedBundle | null = null;
    for (const recorded of [...recording2.responses].reverse()) {
      try {
        expect(recorded.status(), "step4 bundle status").toBe(200);
        bundle2 = parseBundleTar(Buffer.from(await recorded.body()));
        break;
      } catch {
        continue;
      }
    }
    expect(bundle2, "step4 bundle downloaded and installed").toBeTruthy();
    recording2.dispose();
    expect((bundle2 as ParsedBundle).manifest.pairs.map((pair) => pair.pair_id).sort()).toEqual(["baseline_to_initial", "initial_to_modified"]);
    const bti = pairSummary(bundle2 as ParsedBundle, "baseline_to_initial");
    expect(Number(bti.changed_table_count), "baseline_to_initial changed").toBe(0);
    expect(Number(bti.degraded_table_count), "baseline_to_initial degraded").toBe(0);
    expect(Number(bti.failed_table_count), "baseline_to_initial failed").toBe(0);
    const itm = pairSummary(bundle2 as ParsedBundle, "initial_to_modified");
    expect(Number(itm.table_count), "initial_to_modified table_count").toBe(v2PreviewCount + 1);
    expect(Number(itm.degraded_table_count), "initial_to_modified degraded").toBe(0);
    expect(Number(itm.failed_table_count), "initial_to_modified failed").toBe(0);
    const composite = compositeChanged(bundle2 as ParsedBundle, "initial_to_modified");
    appendCaseLog(`t1-step4 composite_changed=${composite}`);
    const changedExpected = v2Changed + (composite ?? 0);
    expect(Number(itm.changed_table_count), "initial_to_modified changed").toBe(changedExpected);
    await waitForDiffBrowsing(page);
    const submitWait2 = page.waitForResponse((response) => response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/submit-attempts"), { timeout: 300_000 });
    await compareAction(page, "提交").click();
    await page.getByRole("dialog").getByRole("button", { name: "确认提交", exact: true }).click();
    expect((await submitWait2).status(), "step4 submit status").toBe(202);
    const { submission: submissionV2 } = await waitForPendingSubmission(submitter, workspaceId2 as string, 600_000);
    const factsV2 = (await getReviewFacts(reviewer, submissionV2.submission_id)).body;
    expect(factsV2.status).toBe("PENDING");
    await applyReview(reviewer, submissionV2.submission_id, { expected_review_version: factsV2.review_version, action: "APPROVE" });
    await saveEvidence(page, testInfo, "t1-v2-diff");

    // Step 6: three-node history compare (INITIAL, archived v1, v2 submission).
    await gotoWorkbench(page);
    await selectTreeRow(page, "初始基线");
    await workshopAction(page, "加入比较").click();
    await selectTreeRow(page, "归档基线 1");
    await workshopAction(page, "加入比较").click();
    await selectTreeRow(page, "提交 2");
    await workshopAction(page, "加入比较").click();
    const compareResponse = page.waitForResponse((response) => response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/history-compares"), { timeout: 300_000 });
    await page.locator(".compare-tray").getByRole("button", { name: "历史比较", exact: true }).click();
    expect((await compareResponse).status()).toBeLessThan(300);
    const drawer = page.locator('section[aria-label="历史比较结果抽屉"]');
    await expect(drawer).toBeVisible({ timeout: 120_000 });
    await expect(drawer.locator(".status-tag")).toHaveText("已完成", { timeout: 600_000 });
    await expect(drawer.locator(".history-pair-summary")).toHaveCount(2);
    await saveEvidence(page, testInfo, "t1-history-three-nodes");
    await drawer.getByRole("button", { name: "打开差异工作台", exact: true }).click();
    await waitForDiffBrowsing(page);

    // M1 report (single in-journey samples; FE3a t1 v1 MODIFIED renderer 24.86 MiB).
    for (const entry of m1) {
      appendCaseLog(
        `t1-m1 step=${entry.step} renderer_increment_bytes=${entry.rendererIncrementBytes} max_rss_anon=${entry.maxRssAnon} max_rss_file=${entry.maxRssFile} max_rss_shmem=${entry.maxRssShmem}`,
      );
    }
    expectNoPageErrors(diagnostics, "t1");
    appendCaseLog("t1 ok");
  } finally {
    await context.close().catch(() => undefined);
  }
});
