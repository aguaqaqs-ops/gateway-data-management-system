import { describe, expect, it } from "vitest";
import { readLocalChangeRecords, readLocalRiskAnnotations, readLocalTable, loadComparisonPresentation } from "./presentation";
import { formatNavigationDiagnostic } from "../view-model/diagnostics";
import { MemoryBundleStore } from "./local-bundle";
import { installBundleTar, verifyBundleMetadata, type BundleClosure, type BundleManifest } from "./posix-tar";
import { bytesStream, readFixture, installedFixtureBundle } from "../../test/helpers";

const FIXTURE_NAMES = ["preview-full", "preview-modified-only", "preview-replacement", "history-three-nodes", "preview-workbench-normal"];

function fixturePhase(name: string): "fe2a" | "fe2b" {
  return name === "preview-workbench-normal" ? "fe2b" : "fe2a";
}

async function installFixture(name: string) {
  const [tar, manifestBytes, closureBytes] = await Promise.all([
    readFixture("src/test/fixtures/generated/" + name + ".tar"),
    readFixture("src/test/fixtures/source/backend/" + fixturePhase(name) + "/" + name + "/manifest.json"),
    readFixture("src/test/fixtures/source/backend/" + fixturePhase(name) + "/" + name + "/artifact-closure.json"),
  ]);
  const manifest = JSON.parse(new TextDecoder().decode(manifestBytes)) as BundleManifest;
  const closure = JSON.parse(new TextDecoder().decode(closureBytes)) as BundleClosure;
  const verified = await verifyBundleMetadata(manifest, closure, manifest.bundle_digest);
  expect(verified.manifest.bundle_digest).toBe(manifest.bundle_digest);
  expect(verified.manifest.closure_manifest_digest).toBe(manifest.closure_manifest_digest);
  expect(verified.closure.bundle_manifest_digest).toBe(closure.bundle_manifest_digest);
  const store = new MemoryBundleStore();
  const installed = await installBundleTar({ body: bytesStream(tar), store, expectedBundleDigest: manifest.bundle_digest,
    etag: manifest.bundle_digest, contentLength: String(tar.byteLength) });
  const bundle = await store.open(installed.manifest.bundle_digest);
  if (!bundle) throw new Error("fixture " + name + " was not installed");
  return { tar, manifest, closure, bundle };
}

describe("backend-generated FE2 bundle fixtures", () => {
  it.each(FIXTURE_NAMES)("matches backend summaries and installs every product for %s", async (name) => {
    const { manifest, bundle } = await installFixture(name);
    expect(bundle.manifest.bundle_digest).toBe(manifest.bundle_digest);
    expect(manifest.pairs.length).toBe(name === "preview-full" || name === "history-three-nodes" ? 2 : 1);
    for (const value of manifest.pairs) {
      const pair = value as { pair_id: string };
      const presentation = await loadComparisonPresentation(bundle, pair.pair_id);
      expect(presentation.surface.surface_digest).toMatch(/^sha256:[0-9a-f]{64}$/);
      expect(presentation.navigationDiagnostics.length).toBe(name === "preview-workbench-normal" ? 2 : 0);
      expect(presentation.navigation.groups.map((group) => group.group_key)).toEqual(name === "preview-replacement" ? [] : ["FORWARD_CHANNELS", "SECONDARY_DEVICES", "COMMUNICATION_PROTOCOLS", "GLOBAL_PARAMETERS", "OTHER_TABLES"]);
    }
  });

  it("matches the backend summary for the normal transfer-channel telemetry browse", async () => {
    const { manifest, bundle } = await installFixture("preview-workbench-normal");
    expect(manifest.pairs).toHaveLength(1);
    const pair = manifest.pairs[0] as { pair_id: string; summary: Record<string, unknown> };
    const presentation = await loadComparisonPresentation(bundle, pair.pair_id);
    expect(presentation.navigation.groups.map((group) => group.label)).toEqual(["转发通道", "二次装置列表", "通讯规约列表", "全局参数", "其他表"]);
    expect(presentation.navigationDiagnostics.map((item) => item.code)).toEqual(["CHANNEL_TABLE_UNCLAIMED", "CHANNEL_TABLE_UNCLAIMED"]);
    const table = presentation.surface.tables.find((value) => value.table_name === "b1_n1_iec104_yc_list");
    expect(table?.diagnostics?.diagnostics_summary ?? []).toEqual([]);
    expect(table?.row_change_stats).toMatchObject({ row_count_before: 90, row_count_current: 90 });
    const tables = presentation.surface.tables;
    const diagnosticsCount = presentation.surfaceDiagnostics.length + presentation.navigationDiagnostics.length
      + tables.reduce((total, value) => total + (value.diagnostics?.diagnostics_summary?.length ?? 0), 0);
    const rowTotal = (key: "row_added_count" | "row_deleted_count" | "row_modified_count") =>
      tables.reduce((total, value) => total + (value.row_change_stats?.[key] ?? 0), 0);
    expect({
      table_count: tables.length,
      changed_table_count: tables.filter((value) => value.change_kind !== "UNCHANGED").length,
      degraded_table_count: tables.filter((value) => value.change_kind === "DEGRADED").length,
      failed_table_count: tables.filter((value) => value.change_kind === "FAILED").length,
      row_added_count: rowTotal("row_added_count"),
      row_deleted_count: rowTotal("row_deleted_count"),
      row_modified_count: rowTotal("row_modified_count"),
    }).toEqual(Object.fromEntries(Object.entries(pair.summary).filter(([key]) => key !== "diagnostics_count").map(([key, value]) => [key, Number(value)])));
    expect(Number(pair.summary.diagnostics_count)).toBeLessThanOrEqual(diagnosticsCount);
    const records = await readLocalChangeRecords(bundle, presentation, "b1_n1_iec104_yc_list");
    expect(records.some((record) => record.record_kind?.includes("ADDED"))).toBe(true);
    expect(records.some((record) => record.record_kind?.includes("DELETED"))).toBe(true);
    expect(records.some((record) => record.record_kind?.includes("MODIFIED"))).toBe(true);
    expect(new Set(records.map((record) => record.record_kind)).size).toBeGreaterThan(1);
  });

  it("browses the Preview FULL row kinds, ordinary channel table, keyless fallback and formula records", async () => {
    const { manifest, bundle } = await installFixture("preview-full");
    expect((manifest.inputs as Array<{ role: string; display_name: string }>).map(({ role, display_name }) => [role, display_name]))
      .toEqual([["baseline", "Baseline"], ["initial", "Initial"], ["modified", "Modified"]]);
    const pair = manifest.pairs.find((value) => (value as { pair_id: string }).pair_id === "baseline_to_initial") as { pair_id: string };
    const presentation = await loadComparisonPresentation(bundle, pair.pair_id);
    const deviceRecords = await readLocalChangeRecords(bundle, presentation, "device");
    expect(deviceRecords.map((row) => row.record_kind).sort()).toEqual(["ROW_ADDED", "ROW_DELETED", "ROW_MODIFIED"]);
    const channelRows = await readLocalChangeRecords(bundle, presentation, "b1_n1_iec104_syx_list");
    expect(channelRows.some((row) => row.record_kind?.startsWith("ROW_"))).toBe(true);
    expect(presentation.surface.tables.some((table) => table.table_name === "keyless_demo" && table.diagnostics?.diagnostics_summary?.includes("KEYLESS_FALLBACK"))).toBe(true);
    const formulas = await readLocalChangeRecords(bundle, presentation, "composite_signal_point");
    expect(formulas.some((row) => row.record_kind === "ROW_MODIFIED")).toBe(true);
    const annotations = await readLocalRiskAnnotations(bundle, presentation, "device");
    expect(new Set(annotations.map((annotation) => annotation.risk_level))).toEqual(new Set(["MEDIUM_LOW", "MEDIUM_HIGH"]));
  });

  it("keeps replacement snapshots side by side and produces only v1's pair-level HIGH risk", async () => {
    const { manifest, bundle } = await installFixture("preview-replacement");
    const pair = manifest.pairs[0] as { pair_id: string };
    const presentation = await loadComparisonPresentation(bundle, pair.pair_id);
    expect(presentation.surface.comparison_mode).toBe("DATASET_REPLACEMENT");
    expect(presentation.surface.tables.some((table) => table.table_name === "device" && table.table_refs?.before_table_ref && table.table_refs?.current_table_ref)).toBe(true);
    const level = presentation.surface.view?.risk_level;
    const levels = new Set(typeof level === "string" ? [level] : []);
    expect(levels).toEqual(new Set(["HIGH"]));
    expect(await readLocalTable(bundle, presentation, "device", "before")).toHaveLength(2);
    expect(await readLocalTable(bundle, presentation, "device", "current")).toHaveLength(2);
  });

  it("contains three History inputs and two adjacent pair surfaces", async () => {
    const { manifest, bundle } = await installFixture("history-three-nodes");
    expect(manifest.inputs).toHaveLength(3);
    expect((manifest.inputs as Array<{ role: string; display_name: string }>).map(({ role, display_name }) => [role, display_name]))
      .toEqual([["fixture-history-ref-0", "node-0"], ["fixture-history-ref-1", "node-1"], ["fixture-history-ref-2", "node-2"]]);
    expect(manifest.pairs.map((pair) => (pair as { pair_id: string }).pair_id)).toEqual(["left_to_middle", "middle_to_right"]);
    const paths = bundle.closure.closure_entries.filter((entry) => entry.kind === "SURFACE");
    expect(paths).toHaveLength(2);
  });
});


it("consumes mixed channel producer output and retains both degraded tables for browsing", async () => {
  const { bundle, manifest } = await installedFixtureBundle("channel-rules");
  const presentation = await loadComparisonPresentation(bundle, (manifest.pairs[0] as { pair_id: string }).pair_id);
  const groups = presentation.navigation.groups;
  const forward = groups.find((group) => group.group_key === "FORWARD_CHANNELS")!;
  expect(forward.items.flatMap((item) => item.tabs.map((tab) => [tab.label, tab.table_id]))).toEqual([
    ["翻转", "b1_n2_flip"], ["串口遥信", "b1_c2_ref"], ["缺列", "b1_c2_short"],
  ]);
  const protocols = groups.find((group) => group.group_key === "COMMUNICATION_PROTOCOLS")!;
  expect(protocols.items.find((item) => item.item_key === "protocol:com_cfg")?.label).toBe("串口配置");
  expect(protocols.items.find((item) => item.item_key === "protocol:b1_n2")?.tabs.map((tab) => tab.table_id)).toEqual(["b1_n2_dll3xx_extra", "b1_n2_dll495_extra"]);
  expect(protocols.items.find((item) => item.item_key === "protocol:b1_c3")?.tabs).toEqual([]);
  for (const [table, code] of [["b1_c2_short", "ORDERED_REQUIRED_COLUMN_MISSING"], ["b1_n2_flip", "ORDERED_INPUT_NOT_CANONICAL"]]) {
    expect(presentation.surface.tables.find((item) => item.table_name === table)?.diagnostics?.diagnostics_summary).toContain(code);
    expect(presentation.view.groups.flatMap((group) => group.items.flatMap((item) => item.tabs)).some((tab) => tab.tableName === table)).toBe(true);
    expect(await readLocalTable(bundle, presentation, table!, "current")).toBeDefined();
  }
  const orphan = presentation.navigationDiagnostics.find((item) => item.code === "CHANNEL_TABLE_UNCLAIMED")!;
  const missing = presentation.navigationDiagnostics.find((item) => item.code === "PROTOCOL_TABLE_NOT_FOUND")!;
  expect(formatNavigationDiagnostic(orphan, presentation.surface.tables)).toContain("串口配置表");
  expect(formatNavigationDiagnostic(missing, presentation.surface.tables)).toContain("预期表名前缀：b1_c3_unknown");
});
