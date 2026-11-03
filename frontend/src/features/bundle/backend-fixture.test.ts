import { describe, expect, it } from "vitest";
import { readLocalChangeRecords, readLocalRiskAnnotations, readLocalTable, loadComparisonPresentation } from "./presentation";
import { MemoryBundleStore } from "./local-bundle";
import { installBundleTar, verifyBundleMetadata, type BundleClosure, type BundleManifest } from "./posix-tar";
import { bytesStream, readFixture } from "../../test/helpers";

const FIXTURE_NAMES = ["preview-full", "preview-modified-only", "preview-replacement", "history-three-nodes", "preview-no-navigation", "preview-workbench-normal"];

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
      if (name === "preview-no-navigation") {
        expect(presentation.navigation).toBeUndefined();
        expect(presentation.navigationDiagnostics).toEqual([]);
        expect(presentation.view.groups[0]?.groupKey).toBe("ALL_TABLES");
      } else {
        expect(presentation.navigation).toBeDefined();
        expect(presentation.navigationDiagnostics.length).toBe(name === "preview-replacement" || name === "preview-workbench-normal" ? 0 : 2);
        expect(presentation.navigation).not.toHaveProperty("diagnostics");
      }
    }
  });

  it("generates the normal transfer-channel telemetry browse without diagnostics", async () => {
    const { manifest, bundle } = await installFixture("preview-workbench-normal");
    expect(manifest.pairs).toHaveLength(1);
    const pair = manifest.pairs[0] as { pair_id: string };
    const presentation = await loadComparisonPresentation(bundle, pair.pair_id);
    expect(presentation.navigation?.groups.map((group) => group.label)).toEqual(["转发通道"]);
    expect(presentation.navigationDiagnostics).toEqual([]);
    const table = presentation.surface.tables.find((value) => value.table_name === "b1_n1_iec104_yc_list");
    expect(table?.diagnostics?.diagnostics_summary ?? []).toEqual([]);
    expect(table?.row_change_stats).toMatchObject({ row_count_before: 90, row_count_current: 90 });
    const records = await readLocalChangeRecords(bundle, presentation, "b1_n1_iec104_yc_list");
    expect(records.some((record) => record.record_kind?.includes("ADDED"))).toBe(true);
    expect(records.some((record) => record.record_kind?.includes("DELETED"))).toBe(true);
    expect(records.some((record) => record.record_kind?.includes("MODIFIED"))).toBe(true);
    expect(new Set(records.map((record) => record.record_kind)).size).toBeGreaterThan(1);
  });

  it("browses the Preview FULL row kinds, ordered moves, blank intervals, keyless fallback and formula records", async () => {
    const { manifest, bundle } = await installFixture("preview-full");
    expect((manifest.inputs as Array<{ role: string; display_name: string }>).map(({ role, display_name }) => [role, display_name]))
      .toEqual([["baseline", "Baseline"], ["initial", "Initial"], ["modified", "Modified"]]);
    const pair = manifest.pairs.find((value) => (value as { pair_id: string }).pair_id === "baseline_to_initial") as { pair_id: string };
    const presentation = await loadComparisonPresentation(bundle, pair.pair_id);
    const deviceRecords = await readLocalChangeRecords(bundle, presentation, "device");
    expect(deviceRecords.map((row) => row.record_kind).sort()).toEqual(["ROW_ADDED", "ROW_DELETED", "ROW_MODIFIED"]);
    const ordered = await readLocalChangeRecords(bundle, presentation, "b1_n1_iec104_syx_list");
    expect(ordered.some((row) => row.record_kind === "ORDERED_ROW_MOVED")).toBe(true);
    expect(ordered.some((row) => row.record_kind === "BLANK_DELETE_INTERVAL" || row.record_kind === "BLANK_INSERT_INTERVAL")).toBe(true);
    expect(presentation.surface.tables.some((table) => table.table_name === "keyless_demo" && table.diagnostics?.diagnostics_summary?.includes("DEGRADE_NO_COMPARE_KEY"))).toBe(true);
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
      .toEqual([["fe2a-history-ref-0", "node-0"], ["fe2a-history-ref-1", "node-1"], ["fe2a-history-ref-2", "node-2"]]);
    expect(manifest.pairs.map((pair) => (pair as { pair_id: string }).pair_id)).toEqual(["fe2a-history-fixture-p0", "fe2a-history-fixture-p1"]);
    const paths = bundle.closure.closure_entries.filter((entry) => entry.kind === "SURFACE");
    expect(paths).toHaveLength(2);
  });
});
