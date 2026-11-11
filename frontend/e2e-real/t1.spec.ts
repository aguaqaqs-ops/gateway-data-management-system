import { test, expect, type Browser, type BrowserContext, type Page, type TestInfo } from "@playwright/test";
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
import { assertBundleConsumerCriteria, BundleCriteriaReader, formatCriteriaSummary } from "./lib/consumer-criteria";
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

/**
 * FE4a §3.3 reference screenshots (not acceptance evidence): capture the page
 * at 1280 and 1920 widths. All call sites sit outside the M1 measurement
 * windows and add no journey steps.
 */
async function saveEvidenceBothWidths(page: Page, testInfo: TestInfo, label: string): Promise<void> {
  await page.setViewportSize({ width: 1280, height: 800 });
  await saveEvidence(page, testInfo, `${label}-1280`);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await saveEvidence(page, testInfo, `${label}-1920`);
}

interface NavigationTabLike {
  tab_key: string;
  label: string;
  table_id: string;
  row_filter: unknown;
  facts: { basis?: string; before_row_count?: number; current_row_count?: number; change_kind?: string } | null;
}

interface NavigationItemLike {
  item_key: string;
  label: string;
  tabs: NavigationTabLike[];
}

interface NavigationGroupLike {
  group_key: string;
  label: string;
  items: NavigationItemLike[];
}

interface SurfaceColumnLike {
  name: string;
  display_name?: string | null;
  pinned?: boolean;
}

interface SurfaceTableLike {
  table_id: string;
  table_name: string;
  row_locator_ref: unknown;
  columns: SurfaceColumnLike[];
  table_content_bindings?: Record<string, { row_count?: number } | null | undefined>;
}

interface SurfaceLike {
  tables: SurfaceTableLike[];
}

interface NavigationDiagnosticLike {
  code: string;
  side: string;
  params: Record<string, unknown>;
  target: { group_key: string; item_key: string; tab_key: string; table_id: string };
}

interface PairArtifacts {
  surface: SurfaceLike;
  groups: NavigationGroupLike[];
  diagnostics: NavigationDiagnosticLike[];
}

/** Read the published surface and business navigation of one bundle pair. */
function pairArtifacts(bundle: ParsedBundle, pairId: string): PairArtifacts {
  const reader = new BundleCriteriaReader(bundle);
  const surface = reader.json<SurfaceLike & { projections?: Array<{ projection_kind?: string; projection_ref?: unknown; diagnostics_ref?: unknown }> }>(
    `pairs/${pairId}/comparison-surface.json`,
  );
  const projection = (surface.projections ?? []).find((candidate) => candidate.projection_kind === "BUSINESS_NAVIGATION");
  if (!projection?.projection_ref) throw new Error(`bundle 缺少 ${pairId} 的业务导航投影`);
  const navigation = reader.json<{ groups?: NavigationGroupLike[] }>(reader.pathOf(projection.projection_ref, `${pairId}.navigation`));
  const diagnostics = projection.diagnostics_ref
    ? (reader.json<{ diagnostics?: NavigationDiagnosticLike[] }>(reader.pathOf(projection.diagnostics_ref, `${pairId}.diagnostics`)).diagnostics ?? [])
    : [];
  return { surface, groups: navigation.groups ?? [], diagnostics };
}

function firstPairWithNavigation(bundle: ParsedBundle): string {
  for (const pair of bundle.manifest.pairs) {
    try {
      if (pairArtifacts(bundle, pair.pair_id).groups.length > 0) return pair.pair_id;
    } catch {
      continue;
    }
  }
  throw new Error("bundle 没有含业务导航的比较对");
}

function tableOf(surface: SurfaceLike, tableId: string): SurfaceTableLike {
  const table = surface.tables.find((candidate) => candidate.table_id === tableId);
  if (!table) throw new Error(`surface 缺少表 ${tableId}`);
  return table;
}

function tabHasRows(surface: SurfaceLike, tab: NavigationTabLike): boolean {
  const facts = tab.facts ?? {};
  const counts = [facts.before_row_count, facts.current_row_count].filter((value): value is number => typeof value === "number");
  if (counts.length > 0) return counts.some((count) => count > 0);
  const bindings = tableOf(surface, tab.table_id).table_content_bindings ?? {};
  return ["before", "current"].some((side) => (bindings[side]?.row_count ?? 0) > 0);
}

function maxTabsItem(items: readonly NavigationItemLike[]): NavigationItemLike | null {
  let picked: NavigationItemLike | null = null;
  for (const item of items) {
    if (item.tabs.length === 0) continue;
    if (!picked || item.tabs.length > picked.tabs.length) picked = item;
  }
  return picked;
}

function firstTabWithRows(surface: SurfaceLike, item: NavigationItemLike): NavigationTabLike {
  return item.tabs.find((tab) => tabHasRows(surface, tab)) ?? item.tabs[0];
}

function settleFrames(page: Page): Promise<void> {
  return page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
}

async function expandNavigation(page: Page): Promise<void> {
  const expand = page.getByRole("button", { name: "展开导航" });
  if (await expand.isVisible().catch(() => false)) {
    await expand.click();
    await page.waitForTimeout(150);
  }
}

async function expandAllGroups(page: Page): Promise<void> {
  for (let guard = 0; guard < 10; guard += 1) {
    const collapsed = page.locator('.nav-group__heading[aria-expanded="false"]');
    if ((await collapsed.count()) === 0) return;
    await collapsed.first().click();
    await settleFrames(page);
  }
}

async function openSidebarTab(page: Page, itemKey: string, tabKey: string): Promise<void> {
  await expandNavigation(page);
  await expandAllGroups(page);
  await page.locator(`.nav-item[data-item-key="${itemKey}"] .nav-tab button[data-tab-key="${tabKey}"]`).click({ timeout: 120_000 });
  await waitForDiffBrowsing(page);
  await settleFrames(page);
}

/** Overflow control is only rendered when the tab bar cannot show every tab. */
async function assertTabsReachable(page: Page): Promise<boolean> {
  const overflow = page.locator(".overflow-tabs__menu > button");
  if (!(await overflow.isVisible().catch(() => false))) return false;
  await overflow.click();
  const entries = page.locator(".overflow-menu button");
  const count = await entries.count();
  expect(count, "页签溢出菜单至少一项").toBeGreaterThan(0);
  await entries.nth(count - 1).click({ timeout: 120_000 });
  await waitForDiffBrowsing(page);
  return true;
}

/** Capture a multi-tab item at both widths and record the overflow state per width. */
async function captureTabItemBothWidths(
  page: Page,
  testInfo: TestInfo,
  label: string,
  surface: SurfaceLike,
  item: NavigationItemLike,
  tab: NavigationTabLike,
): Promise<void> {
  const overflow: string[] = [];
  for (const width of [1280, 1920]) {
    await page.setViewportSize({ width, height: width === 1280 ? 800 : 1080 });
    await settleFrames(page);
    await openSidebarTab(page, item.item_key, tab.tab_key);
    await saveEvidence(page, testInfo, `${label}-${width}`);
    overflow.push((await assertTabsReachable(page)) ? `${width}=溢出` : `${width}=未溢出`);
    await openSidebarTab(page, item.item_key, tab.tab_key);
  }
  appendCaseLog(`${label} item=${item.item_key} tabs=${item.tabs.length} tab=${tab.tab_key} ${overflow.join(" ")}`);
}

function pickColumnsTab(surface: SurfaceLike, groups: readonly NavigationGroupLike[]): { item: NavigationItemLike; tab: NavigationTabLike; table: SurfaceTableLike } | null {
  const seen = new Set<string>();
  for (const group of groups) {
    for (const item of group.items) {
      for (const tab of item.tabs) {
        if (seen.has(tab.table_id)) continue;
        seen.add(tab.table_id);
        const table = tableOf(surface, tab.table_id);
        const hasPinned = table.columns.some((column) => column.pinned === true);
        const hasDisplayName = table.columns.some((column) => typeof column.display_name === "string" && column.display_name.length > 0 && column.display_name !== column.name);
        if (hasPinned && hasDisplayName) return { item, tab, table };
      }
    }
  }
  return null;
}

function pickLocatedTab(surface: SurfaceLike, groups: readonly NavigationGroupLike[]): { item: NavigationItemLike; tab: NavigationTabLike; table: SurfaceTableLike } | null {
  const seen = new Set<string>();
  for (const group of groups) {
    for (const item of group.items) {
      for (const tab of item.tabs) {
        if (seen.has(tab.table_id)) continue;
        seen.add(tab.table_id);
        const table = tableOf(surface, tab.table_id);
        if (table.row_locator_ref) return { item, tab, table };
      }
    }
  }
  return null;
}

async function jumpToFirstLocatedRow(page: Page): Promise<void> {
  const next = page.getByRole("button", { name: "下一个变更" });
  if (await next.isEnabled().catch(() => false)) {
    await next.click();
    const previous = page.getByRole("button", { name: "上一个变更" });
    if (await previous.isEnabled().catch(() => false)) await previous.click();
  }
  await settleFrames(page);
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
  let navDiagnosticsCaptured = false;

  try {
    // Step 1: t1 v1 MODIFIED_ONLY on the empty INITIAL baseline.
    // Baselines go in after directory selection, immediately before packaging.
    await gotoWorkbench(page);
    await saveEvidenceBothWidths(page, testInfo, "fe4-t1-workbench");
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
    const criteria1 = await assertBundleConsumerCriteria(bundle1 as ParsedBundle, "t1 step1 preview bundle");
    appendCaseLog(`t1-step1 criteria ${formatCriteriaSummary(criteria1)}`);
    const summary1 = pairSummary(bundle1 as ParsedBundle, "initial_to_modified");
    expect(Number(summary1.table_count), "step1 table_count").toBe(v1PreviewCount + 1);
    expect(Number(summary1.changed_table_count), "step1 changed").toBe(v1PreviewCount + 1);
    expect(Number(summary1.degraded_table_count), "step1 degraded").toBe(0);
    expect(Number(summary1.failed_table_count), "step1 failed").toBe(0);
    await waitForDiffBrowsing(page);
    await saveEvidence(page, testInfo, "t1-v1-diff");
    await saveEvidenceBothWidths(page, testInfo, "fe4-t1-preview-v1");

    // FE4b §7.3: dependent-on-BE-b pages, still outside the M1 window.
    const v1PairId = firstPairWithNavigation(bundle1 as ParsedBundle);
    const v1 = pairArtifacts(bundle1 as ParsedBundle, v1PairId);
    const secondaryItem = maxTabsItem(v1.groups.find((group) => group.group_key === "SECONDARY_DEVICES")?.items ?? []);
    if (secondaryItem) {
      await captureTabItemBothWidths(page, testInfo, "fe4-t1-device-tabs", v1.surface, secondaryItem, firstTabWithRows(v1.surface, secondaryItem));
    }
    const forwardItem = maxTabsItem(v1.groups.find((group) => group.group_key === "FORWARD_CHANNELS")?.items ?? []);
    if (forwardItem) {
      await captureTabItemBothWidths(page, testInfo, "fe4-t1-forward-channel", v1.surface, forwardItem, firstTabWithRows(v1.surface, forwardItem));
    } else {
      appendCaseLog("fe4-t1-forward-channel skipped: FORWARD_CHANNELS 无项");
    }
    if (v1.diagnostics.length > 0) {
      const firstDiagnostic = v1.diagnostics[0];
      await openSidebarTab(page, firstDiagnostic.target.item_key, firstDiagnostic.target.tab_key);
      await expect(page.locator(".diagnostic-note--navigation").first()).toBeVisible();
      await saveEvidenceBothWidths(page, testInfo, "fe4-t1-nav-diagnostics");
      appendCaseLog(`fe4-t1-nav-diagnostics pair=${v1PairId} code=${firstDiagnostic.code} item=${firstDiagnostic.target.item_key} tab=${firstDiagnostic.target.tab_key}`);
      navDiagnosticsCaptured = true;
    }

    // Submit v1.
    const submitWait = page.waitForResponse((response) => response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/submit-attempts"), { timeout: 300_000 });
    await compareAction(page, "提交").click({ timeout: 120_000 });
    await page.getByRole("dialog").getByRole("button", { name: "确认提交", exact: true }).click({ timeout: 120_000 });
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
    // The archive dialog needs the archiver identity (only archive_submission
    // may list candidates); the submitter's page would get a 403 here.
    const archiverContext = await contextForIdentity(browser, archiver);
    const archiverPage = await archiverContext.newPage();
    await archiverPage.setViewportSize({ width: 1920, height: 1080 });
    const archiverDiagnostics = collectPageDiagnostics(archiverPage);
    try {
      await gotoWorkbench(archiverPage);
      await archiverPage.getByRole("button", { name: "提交 1", exact: true }).click({ timeout: 120_000 });
      await archiverPage.locator(".workspace-context-bar").getByRole("button", { name: "归档主线" }).click({ timeout: 120_000 });
      const archiveDialog = archiverPage.getByRole("dialog", { name: "归档主基线" });
      await expect(archiveDialog.getByText("预检状态")).toBeVisible({ timeout: 60_000 });
      await saveEvidenceBothWidths(archiverPage, testInfo, "fe4-t1-archive");
      await archiveDialog.getByRole("checkbox", { name: /确认把/ }).check({ timeout: 120_000 });
      await archiveDialog.getByRole("button", { name: "确认归档" }).click({ timeout: 120_000 });
      await expect(archiveDialog.getByText("归档完成")).toBeVisible({ timeout: 300_000 });
      await saveEvidence(archiverPage, testInfo, "t1-archive-v1");
      expectNoPageErrors(archiverDiagnostics, "t1-archive");
    } finally {
      await archiverContext.close().catch(() => undefined);
    }
    const headAfterArchive = (await listHistory(submitter)).body.head.version;
    appendCaseLog(`t1-step3 archived submission=${submissionV1} head=${headAfterArchive}`);
    expect(headAfterArchive, "t1-step3 head moved").toBe(1);

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
    const criteria2 = await assertBundleConsumerCriteria(bundle2 as ParsedBundle, "t1 step4 full bundle");
    appendCaseLog(`t1-step4 criteria ${formatCriteriaSummary(criteria2)}`);
    expect((bundle2 as ParsedBundle).manifest.pairs.map((pair) => pair.pair_id).sort()).toEqual(["baseline_to_initial", "initial_to_modified"]);
    const bti = pairSummary(bundle2 as ParsedBundle, "baseline_to_initial");
    expect(Number(bti.changed_table_count), "baseline_to_initial changed").toBe(0);
    expect(Number(bti.degraded_table_count), "baseline_to_initial degraded").toBe(0);
    expect(Number(bti.failed_table_count), "baseline_to_initial failed").toBe(0);
    appendCaseLog(`t1-step4 baseline_to_initial.table_count=${bti.table_count}`);
    const itm = pairSummary(bundle2 as ParsedBundle, "initial_to_modified");
    expect(Number(itm.table_count), "initial_to_modified table_count").toBe(v2PreviewCount + 1);
    expect(Number(itm.degraded_table_count), "initial_to_modified degraded").toBe(0);
    expect(Number(itm.failed_table_count), "initial_to_modified failed").toBe(0);
    const composite = compositeChanged(bundle2 as ParsedBundle, "initial_to_modified");
    appendCaseLog(`t1-step4 composite_changed=${composite}`);
    expect(composite, "initial_to_modified comparison surface exposes composite_signal_point").not.toBeNull();
    const changedExpected = v2Changed + (composite as number);
    expect(Number(itm.changed_table_count), "initial_to_modified changed").toBe(changedExpected);
    await waitForDiffBrowsing(page);
    await page.getByRole("tab", { name: "原始组态视图" }).click({ timeout: 120_000 });
    await waitForDiffBrowsing(page);
    await saveEvidenceBothWidths(page, testInfo, "fe4-t1-preview-v2-baseline_to_initial");
    await page.getByRole("tab", { name: "本次组态视图" }).click({ timeout: 120_000 });
    await waitForDiffBrowsing(page);
    await saveEvidenceBothWidths(page, testInfo, "fe4-t1-preview-v2-initial_to_modified");

    // FE4b §7.3: dependent-on-BE-b pages on the v2 FULL initial_to_modified pair.
    const v2PairId = "initial_to_modified";
    const v2 = pairArtifacts(bundle2 as ParsedBundle, v2PairId);
    await expandNavigation(page);
    await expandAllGroups(page);
    await saveEvidenceBothWidths(page, testInfo, "fe4-t1-nav-groups");
    const columnsPick = pickColumnsTab(v2.surface, v2.groups);
    expect(columnsPick, "t1 v2 initial_to_modified 有中文列名与固定列的表").toBeTruthy();
    await openSidebarTab(page, columnsPick!.item.item_key, columnsPick!.tab.tab_key);
    await saveEvidenceBothWidths(page, testInfo, "fe4-t1-columns");
    appendCaseLog(`fe4-t1-columns table=${columnsPick!.table.table_id} item=${columnsPick!.item.item_key} tab=${columnsPick!.tab.tab_key}`);
    const locatedPick = pickLocatedTab(v2.surface, v2.groups);
    expect(locatedPick, "t1 v2 initial_to_modified 有 row_locator_ref 的表").toBeTruthy();
    await openSidebarTab(page, locatedPick!.item.item_key, locatedPick!.tab.tab_key);
    await jumpToFirstLocatedRow(page);
    await saveEvidenceBothWidths(page, testInfo, "fe4-t1-located-rows");
    appendCaseLog(`fe4-t1-located-rows table=${locatedPick!.table.table_id} item=${locatedPick!.item.item_key} tab=${locatedPick!.tab.tab_key}`);
    if (!navDiagnosticsCaptured) {
      for (const pair of ["baseline_to_initial", "initial_to_modified"] as const) {
        const artifacts = pair === v2PairId ? v2 : pairArtifacts(bundle2 as ParsedBundle, pair);
        if (artifacts.diagnostics.length === 0) {
          appendCaseLog(`t1-nav-diagnostics ${pair} count=0`);
          continue;
        }
        if (pair === "baseline_to_initial") {
          await page.getByRole("tab", { name: "原始组态视图" }).click({ timeout: 120_000 });
          await waitForDiffBrowsing(page);
        }
        const firstDiagnostic = artifacts.diagnostics[0];
        await openSidebarTab(page, firstDiagnostic.target.item_key, firstDiagnostic.target.tab_key);
        await expect(page.locator(".diagnostic-note--navigation").first()).toBeVisible();
        await saveEvidenceBothWidths(page, testInfo, "fe4-t1-nav-diagnostics");
        appendCaseLog(`fe4-t1-nav-diagnostics pair=${pair} code=${firstDiagnostic.code} item=${firstDiagnostic.target.item_key} tab=${firstDiagnostic.target.tab_key}`);
        navDiagnosticsCaptured = true;
        if (pair === "baseline_to_initial") {
          await page.getByRole("tab", { name: "本次组态视图" }).click({ timeout: 120_000 });
          await waitForDiffBrowsing(page);
        }
        break;
      }
      if (!navDiagnosticsCaptured) appendCaseLog("fe4-t1-nav-diagnostics skipped: 所有比较对诊断数为 0");
    }
    const submitWait2 = page.waitForResponse((response) => response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/submit-attempts"), { timeout: 300_000 });
    await compareAction(page, "提交").click({ timeout: 120_000 });
    await page.getByRole("dialog").getByRole("button", { name: "确认提交", exact: true }).click({ timeout: 120_000 });
    expect((await submitWait2).status(), "step4 submit status").toBe(202);
    const { submission: submissionV2 } = await waitForPendingSubmission(submitter, workspaceId2 as string, 600_000);
    const factsV2 = (await getReviewFacts(reviewer, submissionV2.submission_id)).body;
    expect(factsV2.status).toBe("PENDING");
    await applyReview(reviewer, submissionV2.submission_id, { expected_review_version: factsV2.review_version, action: "APPROVE" });
    await saveEvidence(page, testInfo, "t1-v2-diff");
    // FE4a §3.3: read-only review-mode visit for the reference screenshot.
    const reviewerContext = await contextForIdentity(browser, reviewer);
    const reviewerPage = await reviewerContext.newPage();
    await reviewerPage.setViewportSize({ width: 1920, height: 1080 });
    try {
      await reviewerPage.goto(`/?page=compare&mode=REVIEW&submissionId=${submissionV2.submission_id}`);
      await expect(reviewerPage.locator("main.comparison-page")).toBeVisible({ timeout: 60_000 });
      await waitForDiffBrowsing(reviewerPage);
      await expect(reviewerPage.locator(".review-actions")).toBeVisible({ timeout: 60_000 });
      await saveEvidenceBothWidths(reviewerPage, testInfo, "fe4-t1-review");
    } finally {
      await reviewerContext.close().catch(() => undefined);
    }

    // Step 6: three-node history compare (INITIAL, archived v1, v2 submission).
    await gotoWorkbench(page);
    await selectTreeRow(page, "初始基线");
    await workshopAction(page, "加入比较").click({ timeout: 120_000 });
    await selectTreeRow(page, "归档基线 1");
    await workshopAction(page, "加入比较").click({ timeout: 120_000 });
    await selectTreeRow(page, "提交 2");
    await workshopAction(page, "加入比较").click({ timeout: 120_000 });
    const compareResponse = page.waitForResponse((response) => response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/history-compares"), { timeout: 300_000 });
    await page.locator(".compare-tray").getByRole("button", { name: "历史比较", exact: true }).click({ timeout: 120_000 });
    expect((await compareResponse).status()).toBeLessThan(300);
    const drawer = page.locator('section[aria-label="历史比较结果抽屉"]');
    await expect(drawer).toBeVisible({ timeout: 120_000 });
    await expect(drawer.locator(".status-tag")).toHaveText("已完成", { timeout: 600_000 });
    await expect(drawer.locator(".history-pair-summary")).toHaveCount(2);
    await saveEvidence(page, testInfo, "t1-history-three-nodes");
    await saveEvidenceBothWidths(page, testInfo, "fe4-t1-history-3node");
    await drawer.getByRole("button", { name: "打开差异工作台", exact: true }).click({ timeout: 120_000 });
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
