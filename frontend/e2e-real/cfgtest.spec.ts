import { captureResponse } from "./lib/response-snapshot";
import { test, expect, type Page, type TestInfo } from "@playwright/test";
import { readdir, stat } from "node:fs/promises";
import { join } from "node:path";
import {
  appendCaseLog,
  collectPageDiagnostics,
  compareAction,
  contextForIdentity,
  expectNoPageErrors,
  saveEvidence,
  waitForDiffBrowsing,
  waitForPreviewOutcome,
} from "./lib/ui";
import {
  appendArchiveAnomalyResolution,
  appendArchiveConfirmation,
  applyReview,
  getArchiveResult,
  getPreviewResult,
  getReviewFacts,
  listArchiveCandidates,
  listHistory,
  previewArchivePlan,
  startArchive,
  tryApi,
  waitForOperation,
  waitForPendingSubmission,
} from "./lib/api";
import type { ParsedBundle } from "./lib/tar";
import { captureBundleDownloads, type BundleObservation } from "./lib/bundle-observer";
import { consumeBundle, consumePreviewBundle } from "./lib/consume-bundle";
import { assertBundleConsumerCriteria, BundleCriteriaReader, formatCriteriaSummary } from "./lib/consumer-criteria";
import { identityFor, scopeBySlug } from "./lib/env";

/**
 * Secondary-device risk scope, Owner-confirmed minimal real range: the read-only
 * copies of legacy/data/com_cfg_test/1 and /2 (identity verified by the entry
 * script). com_cfg_test/1 is archived as the baseline, com_cfg_test/2 is
 * previewed against it (the 1→2 pair), submitted, and the same 1→2 pair is
 * compared in History. Both bundles must carry the same device_mx facts.
 *
 * Expected values come from the raw SQL (design §1.1, Owner-confirmed §9):
 * device_mx +0 / −2 / modified 5; gid 1753–1757 dev_addr 34 → 9234 (only that
 * column); gid 5009/5012 dev_addr 65532 deleted with complete before values and
 * no ordinary deletion risk; dev_addr 35 is an unaffected device whose
 * device_mx rows do not change; device gid 1721 moves 34 → 9234.
 */

test.setTimeout(2_400_000);

const TABLE = "device_mx";
const MOVED_GIDS = ["1753", "1754", "1755", "1756", "1757"];
const DELETED = new Map([["5009", "#1主变档位"], ["5012", "#2主变档位"]]);
const UNAFFECTED_ITEM = "device:addr:35";

type Row = Record<string, unknown>;

function requireEnv() {
  const missing = ["GATEWAY_FE_IDENTITIES", "GATEWAY_FE_JOURNEY_SCOPES", "GATEWAY_FE_CFGTEST_INPUT_ROOT"].filter((name) => !process.env[name]);
  test.skip(missing.length > 0, `cfgtest suite requires ${missing.join(", ")}; run scripts/run-real-backend-e2e.sh --suite cfgtest`);
  const scope = scopeBySlug("cfgtest");
  return {
    submitter: identityFor(scope, "submitter"),
    reviewer: identityFor(scope, "reviewer"),
    archiver: identityFor(scope, "archiver"),
    inputRoot: process.env.GATEWAY_FE_CFGTEST_INPUT_ROOT as string,
  };
}

function hex(value: unknown): string {
  if (typeof value === "string") return value.startsWith("sha256:") ? value : `sha256:${value}`;
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value as ArrayBuffer);
  return "sha256:" + Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function scalarText(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "object" && !(value instanceof Uint8Array)) {
    const document = value as Record<string, unknown>;
    if (document.kind === "null") return null;
    return typeof document.text === "string" ? document.text : JSON.stringify(document);
  }
  return String(value);
}

function recordValues(value: unknown): Map<string, unknown> {
  const result = new Map<string, unknown>();
  for (const entry of Array.isArray(value) ? value : []) {
    const item = entry as { column_name?: unknown; value?: unknown };
    if (typeof item.column_name === "string") result.set(item.column_name, item.value);
  }
  return result;
}

interface SurfaceTableShape {
  table_name: string;
  row_change_stats: Record<string, number>;
  records_refs?: { records_ref?: unknown };
  row_locator_ref?: unknown;
  table_refs?: { current_table_ref?: unknown; before_table_ref?: unknown };
  columns: Array<{ name: string; present_in: string }>;
  risk_refs?: { annotation_ref?: unknown };
}

interface AnnotationShape {
  risk_level: string;
  target?: { row_identity?: string | null; before_row_identity?: string | null; current_row_identity?: string | null };
}

interface NavigationShape {
  groups: Array<{ items: Array<{ item_key: string; tabs: Array<{ tab_key: string; table_id: string; facts: Record<string, unknown> | null; empty: boolean }> }> }>;
  device_definition_changes: Array<Record<string, unknown>>;
  table_notices: Array<Record<string, unknown>>;
}

interface ScopeFacts {
  deletedIdentities: string[];
  modifiedIdentities: string[];
  tabs: Record<string, unknown>;
  definitionChange: unknown;
}

/** Row- and tab-level checks of one 1→2 pair; returns the facts compared across Preview and History. */
async function assertPairScope(bundle: ParsedBundle, pairId: string, label: string): Promise<ScopeFacts> {
  const reader = new BundleCriteriaReader(bundle);
  const where = `${label} ${pairId}`;
  const surface = reader.json<{ tables: SurfaceTableShape[]; projections?: Array<{ projection_kind?: string; projection_ref?: unknown }> }>(`pairs/${pairId}/comparison-surface.json`);
  const table = surface.tables.find((candidate) => candidate.table_name === TABLE);
  expect(table, `${where} has ${TABLE}`).toBeTruthy();
  const stats = table!.row_change_stats;
  expect({ added: stats.row_added_count, deleted: stats.row_deleted_count, modified: stats.row_modified_count }, `${where} ${TABLE} counts`)
    .toEqual({ added: 0, deleted: 2, modified: 5 });
  expect(stats.suppressed_added_count ?? 0, `${where} suppressed added`).toBe(0);
  expect(stats.suppressed_deleted_count ?? 0, `${where} suppressed deleted`).toBe(0);

  const records = await reader.parquet(reader.pathOf(table!.records_refs?.records_ref, `${where}.records`)) as Row[];
  const byKind = (kind: string) => records.filter((record) => record.record_kind === kind);
  expect(byKind("ROW_ADDED"), `${where} no added records`).toHaveLength(0);
  const locator = new Map((await reader.parquet(reader.pathOf(table!.row_locator_ref, `${where}.locator`)) as Row[]).map((row) => [hex(row.row_identity), row]));
  const currentRef = table!.table_refs?.current_table_ref;
  const beforeRef = table!.table_refs?.before_table_ref;
  const currentRows = currentRef ? await reader.parquet(reader.pathOf(currentRef, `${where}.current`)) as Row[] : [];
  const beforeRows = beforeRef ? await reader.parquet(reader.pathOf(beforeRef, `${where}.before`)) as Row[] : [];
  const beforeColumns = table!.columns.filter((column) => column.present_in !== "CURRENT").map((column) => column.name);
  const sideValue = (row: Row | undefined, column: string) => row ? scalarText(row[column]) : null;
  const beforeDevAddr = (located: Row | undefined) => {
    if (!located) return null;
    if (located.before_row_index !== null && located.before_row_index !== undefined) return sideValue(beforeRows[Number(located.before_row_index)], "dev_addr");
    const context = typeof located.before_filter_context_json === "string" ? JSON.parse(located.before_filter_context_json) as Record<string, unknown> : {};
    return context.dev_addr === undefined || context.dev_addr === null ? null : String(context.dev_addr);
  };

  // Two complete deletions on the composite device, values from the snapshot or the record.
  const deleted = byKind("ROW_DELETED");
  expect(deleted, `${where} deleted records`).toHaveLength(2);
  const seenDeleted = new Map<string, string | null>();
  for (const record of deleted) {
    const located = locator.get(hex(record.row_identity));
    const values = recordValues(record.before_values);
    const snapshot = located?.before_row_index !== null && located?.before_row_index !== undefined ? beforeRows[Number(located.before_row_index)] : undefined;
    const value = (column: string) => snapshot ? sideValue(snapshot, column) : scalarText(values.get(column));
    if (!snapshot) for (const column of beforeColumns) expect(values.has(column), `${where} deleted record carries before value of ${column}`).toBe(true);
    expect(value("dev_addr"), `${where} deleted dev_addr`).toBe("65532");
    seenDeleted.set(String(value("gid")), value("name"));
  }
  expect(Object.fromEntries(seenDeleted), `${where} deleted gid/name`).toEqual(Object.fromEntries(DELETED));

  // Five address migrations 34 → 9234, changing only dev_addr.
  const modified = byKind("ROW_MODIFIED");
  expect(modified, `${where} modified records`).toHaveLength(5);
  const moved: string[] = [];
  for (const record of modified) {
    expect(record.changed_columns, `${where} modified columns`).toEqual(["dev_addr"]);
    const located = locator.get(hex(record.row_identity));
    expect(located, `${where} modified record located`).toBeTruthy();
    const current = currentRows[Number(located!.current_row_index)];
    expect(sideValue(current, "dev_addr"), `${where} current dev_addr`).toBe("9234");
    expect(beforeDevAddr(located), `${where} before dev_addr`).toBe("34");
    moved.push(String(sideValue(current, "gid")));
  }
  expect(moved.sort(), `${where} moved gids`).toEqual(MOVED_GIDS);

  // Risk: the migrations keep their address-change risk; deletions carry none.
  const annotationRef = table!.risk_refs?.annotation_ref;
  const annotations = annotationRef ? reader.json<{ annotations: AnnotationShape[] }>(reader.pathOf(annotationRef, `${where}.annotations`)).annotations : [];
  const riskOf = (identity: string) => annotations.filter((annotation) => [annotation.target?.row_identity, annotation.target?.before_row_identity, annotation.target?.current_row_identity].includes(identity));
  for (const record of deleted) expect(riskOf(hex(record.row_identity)), `${where} no ordinary deletion risk`).toHaveLength(0);
  for (const record of modified) expect(riskOf(hex(record.row_identity)).map((annotation) => annotation.risk_level), `${where} migration risk`).toEqual(["MEDIUM_HIGH"]);

  // Navigation: local facts per device; the unaffected device inherits nothing.
  const projection = (surface.projections ?? []).find((candidate) => candidate.projection_kind === "BUSINESS_NAVIGATION");
  const navigation = reader.json<NavigationShape>(reader.pathOf(projection!.projection_ref, `${where}.navigation`));
  const facts = (itemKey: string) => {
    const tab = navigation.groups.flatMap((group) => group.items).find((item) => item.item_key === itemKey)?.tabs.find((candidate) => candidate.table_id === TABLE);
    expect(tab, `${where} ${itemKey} has a ${TABLE} tab`).toBeTruthy();
    return tab!.facts!;
  };
  const pick = (value: Record<string, unknown>) => ({ basis: value.basis, change_kind: value.change_kind, risk_level: value.risk_level, risk_complete: value.risk_complete, row_changes: value.row_changes, membership_changed: value.membership_changed });
  const tabs = {
    "device:addr:34": pick(facts("device:addr:34")),
    "device:addr:9234": pick(facts("device:addr:9234")),
    "device:composite": pick(facts("device:composite")),
    [UNAFFECTED_ITEM]: pick(facts(UNAFFECTED_ITEM)),
  };
  expect(tabs["device:addr:34"], `${where} old device`).toMatchObject({ basis: "EXACT", risk_level: "MEDIUM_HIGH", risk_complete: true, row_changes: { added: 0, deleted: 0, modified: 5, moved_in: 0, moved_out: 5 } });
  expect(tabs["device:addr:9234"], `${where} new device`).toMatchObject({ basis: "EXACT", risk_level: "MEDIUM_HIGH", risk_complete: true, row_changes: { added: 0, deleted: 0, modified: 5, moved_in: 5, moved_out: 0 } });
  expect(tabs["device:composite"], `${where} composite device`).toMatchObject({ basis: "EXACT", risk_level: null, risk_complete: true, row_changes: { added: 0, deleted: 2, modified: 0 } });
  expect(tabs[UNAFFECTED_ITEM], `${where} unaffected device`).toMatchObject({ basis: "EXACT", change_kind: "UNCHANGED", risk_level: null, risk_complete: true, membership_changed: false });
  const definitionChange = navigation.device_definition_changes.find((change) => change.before_dev_addr === 34);
  expect(definitionChange, `${where} device definition 34 → 9234`).toMatchObject({ change_kind: "UPDATED", before_item_key: "device:addr:34", current_item_key: "device:addr:9234", current_dev_addr: 9234 });
  await appendCaseLog(`cfgtest ${where} ok notices=${JSON.stringify(navigation.table_notices.filter((notice) => notice.table_id === TABLE))}`);
  return {
    deletedIdentities: deleted.map((record) => hex(record.row_identity)).sort(),
    modifiedIdentities: modified.map((record) => hex(record.row_identity)).sort(),
    tabs,
    definitionChange,
  };
}

async function evidenceBothWidths(page: Page, testInfo: TestInfo, label: string): Promise<void> {
  for (const width of [1920, 1280]) {
    await page.setViewportSize({ width, height: 1080 });
    await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    await saveEvidence(page, testInfo, `${label}-${width}`);
  }
  await page.setViewportSize({ width: 1920, height: 1080 });
}

/** Opens one device tab by URL state and checks the page shows that device's own scope. */
async function openDeviceTab(page: Page, itemKey: string, expected: RegExp, testInfo: TestInfo, label: string): Promise<void> {
  const url = new URL(page.url());
  url.searchParams.set("node", itemKey);
  url.searchParams.set("tab", TABLE);
  url.searchParams.delete("unassigned");
  await page.goto(url.toString());
  await waitForDiffBrowsing(page);
  await expect(page.locator(".table-info")).toContainText(expected, { timeout: 60_000 });
  await evidenceBothWidths(page, testInfo, label);
}

async function checkBrowser(page: Page, testInfo: TestInfo, prefix: string): Promise<void> {
  await openDeviceTab(page, "device:addr:34", /移出本装置 5 行/, testInfo, `${prefix}-device-34`);
  // The tab's own located risk (the header also has per-level count chips).
  await expect(page.locator('.table-info > span[title^="本页已确认风险"] .risk-badge')).toHaveText("中高风险");
  await openDeviceTab(page, "device:addr:9234", /移入本装置 5 行/, testInfo, `${prefix}-device-9234`);
  await openDeviceTab(page, "device:composite", /删除 2 行/, testInfo, `${prefix}-device-65532`);
  await expect(page.locator(".table-info .risk-badge")).toHaveCount(0);
  await openDeviceTab(page, UNAFFECTED_ITEM, /未变化/, testInfo, `${prefix}-device-35`);
  await expect(page.locator(".table-info .risk-badge")).toHaveCount(0);
  await expect(page.locator(".public-notices .public-notice", { hasText: "修改装置定义 · 地址 34 → 9234" })).toBeVisible();
}

/** Workbench as it is rendered on this base: the History tree and the selected workspace's upload card. */
async function openWorkbench(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /组态树/ })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("table", { name: "History 组态树" })).toBeVisible({ timeout: 60_000 });
}

async function uploadModifiedOnly(page: Page, dir: string): Promise<void> {
  await page.getByTestId("upload-modified-input").setInputFiles(dir);
  await page.getByRole("button", { name: "上传并生成预览" }).click({ timeout: 120_000 });
}

/**
 * Archives com_cfg_test/1 through the same API sequence the archive dialog
 * runs (runArchiveJourney): acknowledge time anomalies, confirm required
 * subjects, then start. The browser is exercised on the comparison pages.
 */
async function archiveViaApi(archiver: ReturnType<typeof requireEnv>["archiver"], submissionId: string): Promise<string> {
  const listed = (await listArchiveCandidates(archiver)).body;
  const digest = listed.candidates.find((candidate) => candidate.submission_id === submissionId)!.expected_candidate_digest;
  const selected = { submission_id: submissionId, expected_candidate_digest: digest };
  let plan = (await previewArchivePlan(archiver, selected)).body;
  await appendCaseLog(`cfgtest archive anomalies=${JSON.stringify(plan.anomalies.map((anomaly) => anomaly.issue_code))} confirmations=${plan.confirmation_requirements.length} blockers=${JSON.stringify(plan.blockers)}`);
  for (const anomaly of plan.anomalies) {
    expect(["GENERATION_TIME_MISSING", "GENERATION_TIME_INVALID_VALUES", "GENERATION_TIME_LAST_NOT_MAX", "TIME_ABNORMAL_MODIFIED", "TIME_ABNORMAL_INITIAL"].includes(anomaly.issue_code),
      `cfgtest unexpected archive anomaly ${anomaly.issue_code}`).toBe(true);
    await appendArchiveAnomalyResolution(archiver, {
      expected_baseline_node_id: plan.head.business_baseline_node_id,
      expected_baseline_head_version: plan.head.baseline_head_version,
      candidate_set_digest: plan.candidate_set_digest,
      selected,
      subject_digest: anomaly.subject_digest,
      subject_kind: anomaly.subject_kind,
      issue_code: anomaly.issue_code,
      target_submission_id: anomaly.target_submission_id,
      target_candidate_digest: anomaly.target_candidate_digest,
      expected_sequence: anomaly.latest_sequence,
      action: anomaly.issue_code.startsWith("TIME_ABNORMAL") ? "ACKNOWLEDGE_TIME_ORDER" : "ACKNOWLEDGE_TIME_QUALITY",
      reason: `cfgtest 证据运行：${anomaly.issue_code}`,
    });
  }
  const confirmationRefs: Array<{ subject_digest: string; sequence: number }> = [];
  for (const subjectDigest of plan.confirmation_requirements) {
    const appended = (await appendArchiveConfirmation(archiver, {
      expected_baseline_node_id: plan.head.business_baseline_node_id,
      expected_baseline_head_version: plan.head.baseline_head_version,
      selected,
      candidate_set_digest: plan.candidate_set_digest,
      subject_digest: subjectDigest,
      expected_sequence: 0,
      action: "CONFIRM",
      reason: "cfgtest 证据运行：确认归档选择",
    })).body;
    confirmationRefs.push({ subject_digest: subjectDigest, sequence: appended.sequence });
  }
  plan = (await previewArchivePlan(archiver, selected)).body;
  expect(plan.blockers, "cfgtest archive blockers").toEqual([]);
  const started = (await startArchive(archiver, {
    expected_baseline_node_id: plan.head.business_baseline_node_id,
    expected_baseline_head_version: plan.head.baseline_head_version,
    candidate_set_digest: plan.candidate_set_digest,
    selected,
    confirmation_refs: confirmationRefs,
    anomaly_resolution_refs: plan.anomalies.filter((anomaly) => anomaly.resolution_status === "ACCEPTED")
      .map((anomaly) => ({ subject_digest: anomaly.subject_digest, sequence: anomaly.latest_sequence })),
  })).body;
  const result = (await getArchiveResult(archiver, started.archive_result_id)).body;
  await appendCaseLog(`cfgtest archived submission=${submissionId} baseline_node=${result.baseline_node_id} head=${result.baseline_head_version}`);
  return result.baseline_node_id;
}

interface PairIdentity { baselineNodeId: string; submissionId: string }

/**
 * Selects the 1→2 pair by identity, not by label or position: every History
 * tree row is opened and its "节点 ID" read from the details panel; only the
 * archived baseline produced by this run and the second submission are ticked.
 * The API must show that submission's parent is that baseline, and the
 * history-compare request must carry exactly these two refs.
 */
async function addPairToCompare(page: Page, submitter: ReturnType<typeof requireEnv>["submitter"], pair: PairIdentity): Promise<void> {
  const history = (await listHistory(submitter)).body;
  const baseline = history.nodes.find((node) => node.ref_kind === "baseline_node" && node.ref_id === pair.baselineNodeId);
  const submission = history.nodes.find((node) => node.ref_kind === "submission" && node.ref_id === pair.submissionId);
  expect(baseline?.baseline_kind, "the archived com_cfg_test/1 baseline is in History").toBe("ARCHIVED_SUBMISSION");
  expect(submission?.parent, "the com_cfg_test/2 submission is based on that baseline (the 1→2 pair)").toEqual({ ref_kind: "baseline_node", ref_id: pair.baselineNodeId });
  const expand = page.getByRole("button", { name: "展开详情面板" });
  if (await expand.count()) await expand.click();
  const table = page.getByRole("table", { name: "History 组态树" });
  const rows = table.locator("tbody tr");
  const wanted = new Map([[pair.baselineNodeId, "归档基线"], [pair.submissionId, "提交"]]);
  const mapping: string[] = [];
  const picked = new Map<string, number>();
  for (let index = 0; index < await rows.count(); index += 1) {
    const row = rows.nth(index);
    const label = (await row.locator("button.workspace-node-label").innerText()).trim();
    if (label.startsWith("工作区")) continue;
    await row.locator("button.workspace-node-label").click();
    await expect(page.locator(".workspace-details__header h2")).toHaveText(label);
    const details = page.locator("dl.details-list");
    const nodeId = (await details.locator("div").filter({ has: page.locator("dt", { hasText: /^节点 ID$/ }) }).locator("dd").innerText()).trim();
    const nodeType = (await details.locator("div").filter({ has: page.locator("dt", { hasText: /^节点类型$/ }) }).locator("dd").innerText()).trim();
    mapping.push(`${label}=${nodeType}:${nodeId}`);
    if (wanted.has(nodeId)) {
      expect(nodeType, `node ${nodeId} type`).toBe(wanted.get(nodeId));
      expect(picked.has(nodeId), `node ${nodeId} appears once`).toBe(false);
      picked.set(nodeId, index);
    }
  }
  await appendCaseLog(`cfgtest history rows ${JSON.stringify(mapping)} expected baseline=${pair.baselineNodeId} submission=${pair.submissionId}`);
  expect([...picked.keys()].sort(), "both pair nodes found in the History tree").toEqual([...wanted.keys()].sort());
  for (const index of picked.values()) await rows.nth(index).getByRole("checkbox", { name: /^加入比较：/ }).check({ timeout: 60_000 });
}

/** The accepted request must name exactly the archived baseline and the second submission. */
function assertCompareRequest(body: unknown, pair: PairIdentity): void {
  const nodes = ((body as { nodes?: Array<{ ref_kind: string; ref_id: string }> }).nodes ?? [])
    .map((node) => `${node.ref_kind}:${node.ref_id}`).sort();
  expect(nodes, "history compare request names the 1→2 pair").toEqual([`baseline_node:${pair.baselineNodeId}`, `submission:${pair.submissionId}`].sort());
}

test("cfgtest com_cfg_test 1→2 secondary-device scope across Preview, History and browser", async ({ browser }, testInfo) => {
  const { submitter, reviewer, archiver, inputRoot } = requireEnv();
  const v1Dir = join(inputRoot, "cfgtest-v1");
  const v2Dir = join(inputRoot, "cfgtest-v2");
  for (const dir of [v1Dir, v2Dir]) {
    const entries = await readdir(dir);
    expect(entries.filter((name) => name.endsWith(".pmc")), `${dir} has one .pmc`).toHaveLength(1);
    await stat(join(dir, "sql", "dbcfg.sql"));
    await appendCaseLog(`cfgtest-input dir=${dir} entries=${entries.length}`);
  }
  const context = await contextForIdentity(browser, submitter);
  const page = await context.newPage();
  await page.setViewportSize({ width: 1920, height: 1080 });
  const diagnostics = collectPageDiagnostics(page);
  const observations: BundleObservation[] = [];
  try {
    // Step 1: com_cfg_test/1 on the empty INITIAL baseline; submit, approve, archive.
    await openWorkbench(page);
    const recording1 = captureBundleDownloads(page, submitter);
    observations.push(recording1);
    const preview1Wait = await captureResponse(page, submitter, "POST", /\/preview-operations$/);
    await uploadModifiedOnly(page, v1Dir);
    const preview1 = await preview1Wait.read();
    expect(preview1.status(), "v1 preview accepted").toBe(202);
    const accepted1 = (await preview1.json()) as { operation_id: string };
    expect((await waitForOperation(submitter, accepted1.operation_id, 900_000)).status, "v1 preview operation").toBe("SUCCEEDED");
    expect(await waitForPreviewOutcome(page, 900_000)).toBe("compare");
    const workspaceId = new URL(page.url()).searchParams.get("workspaceId") as string;
    await waitForDiffBrowsing(page);
    const submit1 = page.waitForResponse((response) => response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/submit-attempts"), { timeout: 300_000 });
    await compareAction(page, "提交").click({ timeout: 120_000 });
    await page.getByRole("dialog").getByRole("button", { name: "确认提交", exact: true }).click({ timeout: 120_000 });
    expect((await submit1).status(), "v1 submit").toBe(202);
    const { submission: submissionV1 } = await waitForPendingSubmission(submitter, workspaceId, 900_000);
    const facts1 = (await getReviewFacts(reviewer, submissionV1.submission_id)).body;
    await applyReview(reviewer, submissionV1.submission_id, { expected_review_version: facts1.review_version, action: "APPROVE" });
    const archivedBaselineId = await archiveViaApi(archiver, submissionV1.submission_id);
    expect((await listHistory(submitter)).body.head.version, "baseline head after archiving com_cfg_test/1").toBe(1);
    recording1.dispose();

    // Step 2: Preview com_cfg_test/2 against the archived 1 — the 1→2 pair.
    await openWorkbench(page);
    const recording2 = captureBundleDownloads(page, submitter);
    observations.push(recording2);
    const preview2Wait = await captureResponse(page, submitter, "POST", /\/preview-operations$/);
    await uploadModifiedOnly(page, v2Dir);
    const preview2 = await preview2Wait.read();
    expect(preview2.status(), "v2 preview accepted").toBe(202);
    const accepted2 = (await preview2.json()) as { operation_id: string; upload_revision_id: string };
    expect((await waitForOperation(submitter, accepted2.operation_id, 900_000)).status, "v2 preview operation").toBe("SUCCEEDED");
    expect(await waitForPreviewOutcome(page, 900_000)).toBe("compare");
    const compareUrl = new URL(page.url());
    const previewId = compareUrl.searchParams.get("previewResultId") as string;
    const workspace2 = compareUrl.searchParams.get("workspaceId") as string;
    const previewEvidence = await consumePreviewBundle(page, recording2, { workspaceId: workspace2, previewId,
      operationId: accepted2.operation_id, uploadRevisionId: accepted2.upload_revision_id,
      readPreview: () => getPreviewResult(submitter, workspace2, previewId) });
    recording2.dispose();
    const previewCriteria = await assertBundleConsumerCriteria(previewEvidence.bundle, "cfgtest preview bundle");
    await recording2.assertIdentity();
    await appendCaseLog(`cfgtest preview criteria source=${previewEvidence.source} ${formatCriteriaSummary(previewCriteria)}`);
    expect(previewEvidence.bundle.manifest.pairs.map((pair) => pair.pair_id), "preview pairs").toEqual(["initial_to_modified"]);
    const previewFacts = await assertPairScope(previewEvidence.bundle, "initial_to_modified", "preview");
    await checkBrowser(page, testInfo, "cfgtest-preview");

    const submit2 = page.waitForResponse((response) => response.request().method() === "POST" && new URL(response.url()).pathname.endsWith("/submit-attempts"), { timeout: 300_000 });
    await compareAction(page, "提交").click({ timeout: 120_000 });
    await page.getByRole("dialog").getByRole("button", { name: "确认提交", exact: true }).click({ timeout: 120_000 });
    expect((await submit2).status(), "v2 submit").toBe(202);
    const { submission: submissionV2 } = await waitForPendingSubmission(submitter, workspace2, 900_000);
    const facts2 = (await getReviewFacts(reviewer, submissionV2.submission_id)).body;
    await applyReview(reviewer, submissionV2.submission_id, { expected_review_version: facts2.review_version, action: "APPROVE" });

    // Step 3: History compare of the same 1→2 pair (archived 1, submission 2).
    const pair = { baselineNodeId: archivedBaselineId, submissionId: submissionV2.submission_id };
    await openWorkbench(page);
    await addPairToCompare(page, submitter, pair);
    const historyBodies = captureBundleDownloads(page, submitter);
    observations.push(historyBodies);
    const compareRequest = page.waitForRequest((request) => request.method() === "POST" && new URL(request.url()).pathname.endsWith("/history-compares"), { timeout: 300_000 });
    const compareResponse = await captureResponse(page, submitter, "POST", /\/history-compares$/, 300_000);
    await page.locator(".compare-tray").getByRole("button", { name: "历史比较", exact: true }).click({ timeout: 120_000 });
    assertCompareRequest((await compareRequest).postDataJSON(), pair);
    const compareAccepted = await compareResponse.read();
    expect(compareAccepted.status(), "history compare accepted").toBeLessThan(300);
    const historyOperationId = ((await compareAccepted.json()) as { operation_id: string }).operation_id;
    const drawer = page.locator('section[aria-label="历史比较结果抽屉"]');
    await expect(drawer.locator(".status-tag")).toHaveText("已完成", { timeout: 900_000 });
    await expect(drawer.locator(".history-pair-summary")).toHaveCount(1);
    await drawer.getByRole("button", { name: "打开差异工作台", exact: true }).click({ timeout: 120_000 });
    await waitForDiffBrowsing(page);
    const authorized = await tryApi<{ operation_id: string; status: string; result: { bundle_digest: string } | null }>(
      submitter, "GET", `/v1/history-compares/${encodeURIComponent(historyOperationId)}`);
    if (!("body" in authorized) || !authorized.body.result) throw new Error("History bundle authorization failed");
    const historyEvidence = await consumeBundle(page, historyBodies, { authorizedDigest: authorized.body.result.bundle_digest,
      requestPath: `/v1/history-compares/${encodeURIComponent(historyOperationId)}/bundle` });
    const historyCriteria = await assertBundleConsumerCriteria(historyEvidence.bundle, "cfgtest history bundle");
    await historyBodies.assertIdentity();
    await appendCaseLog(`cfgtest history criteria source=${historyEvidence.source} ${formatCriteriaSummary(historyCriteria)}`);
    const historyPairs = historyEvidence.bundle.manifest.pairs.map((pair) => pair.pair_id);
    expect(historyPairs, "history has one pair").toHaveLength(1);
    const historyFacts = await assertPairScope(historyEvidence.bundle, historyPairs[0] as string, "history");
    // Preview and History publish the same row identities and the same device facts.
    expect(historyFacts, "History facts equal Preview facts for the same 1→2 pair").toEqual(previewFacts);
    await checkBrowser(page, testInfo, "cfgtest-history");

    expectNoPageErrors(diagnostics, "cfgtest");
    await appendCaseLog(`cfgtest ok preview=${previewId} history=${historyOperationId}`);
  } finally {
    for (const observation of observations) observation.dispose();
    await context.close().catch(() => undefined);
  }
});
