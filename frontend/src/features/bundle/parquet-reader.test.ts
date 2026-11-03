import { describe, expect, it, vi } from "vitest";
import { readParquetTable } from "./parquet-reader";
import { loadComparisonPresentation, readLocalChangeRecords, readLocalTable } from "./presentation";
import { installedGoldenBundle, responseForTar } from "../../test/helpers";
import { Sha256 } from "./sha256";
import { ensureLocalBundle, MemoryBundleStore, type InstalledBundle } from "./local-bundle";
import { BundleIntegrityError } from "./posix-tar";

describe("local Parquet browsing", () => {
  it("browses table slices and added, deleted and modified records locally", async () => {
    const { bundle, manifest } = await installedGoldenBundle();
    const pairId = (manifest.pairs[0] as { pair_id: string }).pair_id;
    const presentation = await loadComparisonPresentation(bundle, pairId);
    const rows = await readLocalTable(bundle, presentation, "device", "current", { columns: ["dev_addr", "description"], rowStart: 0, rowEnd: 2 });
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ dev_addr: "1", description: "线路保护装置 A" });
    expect(rows[1]).toMatchObject({ dev_addr: "2", description: "测控装置（升级）" });

    const diffs = await readLocalChangeRecords(bundle, presentation, "device", { columns: ["record_kind", "before_values", "current_values"] });
    expect(diffs.map((row) => row.record_kind).sort()).toEqual(["ROW_ADDED", "ROW_DELETED", "ROW_MODIFIED"]);
    const modified = diffs.find((row) => row.record_kind === "ROW_MODIFIED");
    expect(modified?.before_values).toMatchObject([{ column_name: "description", value: { kind: "string", text: "测控装置" } }]);
    expect(modified?.current_values).toMatchObject([{ column_name: "description", value: { kind: "string", text: "测控装置（升级）" } }]);
  });

  it("loads surface, business navigation and risk from the bundle, then browses table and records locally", async () => {
    const { bundle, manifest } = await installedGoldenBundle();
    const pairId = (manifest.pairs[0] as { pair_id: string }).pair_id;
    const presentation = await loadComparisonPresentation(bundle, pairId);
    expect(presentation.view.groups[0]?.groupKey).toBe("SECONDARY_DEVICES");
    expect(presentation.view.tables.find((table) => table.tableName === "device")?.riskLevel).toBe("MEDIUM_HIGH");
    expect(presentation.tableArtifacts.get("device")?.before).toBeNull();
    expect(presentation.tableArtifacts.get("device")?.current).toContain("tables/current/device.parquet");
    const rows = await readLocalTable(bundle, presentation, "device", "current", { columns: ["dev_addr"] });
    const diffs = await readLocalChangeRecords(bundle, presentation, "device");
    expect(rows).toHaveLength(4);
    expect(diffs.map((row) => row.record_kind).sort()).toEqual(["ROW_ADDED", "ROW_DELETED", "ROW_MODIFIED"]);
  });

  it("hashes an artifact once per opened browsing session", async () => {
    const { bundle, manifest } = await installedGoldenBundle();
    const path = manifest.closure.entries.find((entry) => entry.kind === "RECORDS")?.logical_path;
    if (!path) throw new Error("fixture has no records artifact");
    const digest = vi.spyOn(Sha256.prototype, "digest");
    try {
      await bundle.readArtifact(path);
      await bundle.readArtifact(path);
      expect(digest).toHaveBeenCalledTimes(1);
    } finally { digest.mockRestore(); }
  });

  it("re-downloads once when local Parquet parsing fails", async () => {
    const { manifest, closure, tar } = await installedGoldenBundle();
    const pairId = (manifest.pairs[0] as { pair_id: string }).pair_id;
    const path = manifest.closure_entries.find((entry) => entry.kind === "RECORDS" && entry.table_name === "device" && entry.pair_id === pairId)?.logical_path;
    if (!path) throw new Error("fixture has no records artifact");
    const memory = new MemoryBundleStore();
    let stale = true;
    const store = {
      has: (digest: string) => memory.has(digest),
      begin: (digest: string) => memory.begin(digest),
      open: async (digest: string): Promise<InstalledBundle | null> => {
        if (stale) {
          stale = false;
          return { manifest, closure, readArtifact: async () => new Blob(["not parquet"]) };
        }
        return memory.open(digest);
      },
    };
    let downloads = 0;
    const local = await ensureLocalBundle({ store, expectedBundleDigest: manifest.bundle_digest,
      fetchBundle: async () => { downloads += 1; return responseForTar(tar, manifest.bundle_digest); } });
    const rows = await readParquetTable(local, path);
    expect(rows).toHaveLength(3);
    expect(downloads).toBe(1);
  });

  it("re-downloads once when the first local artifact digest check fails", async () => {
    const { manifest, closure, tar } = await installedGoldenBundle();
    const pairId = (manifest.pairs[0] as { pair_id: string }).pair_id;
    const path = manifest.closure_entries.find((entry) => entry.kind === "RECORDS" && entry.table_name === "device" && entry.pair_id === pairId)?.logical_path;
    if (!path) throw new Error("fixture has no records artifact");
    const memory = new MemoryBundleStore();
    let stale = true;
    const store = {
      has: (digest: string) => memory.has(digest),
      begin: (digest: string) => memory.begin(digest),
      open: async (digest: string): Promise<InstalledBundle | null> => {
        if (stale) {
          stale = false;
          return { manifest, closure, readArtifact: async () => { throw new BundleIntegrityError("本地 bundle 产物校验失败"); } };
        }
        return memory.open(digest);
      },
    };
    let downloads = 0;
    const local = await ensureLocalBundle({ store, expectedBundleDigest: manifest.bundle_digest,
      fetchBundle: async () => { downloads += 1; return responseForTar(tar, manifest.bundle_digest); } });
    const rows = await readParquetTable(local, path);
    expect(rows).toHaveLength(3);
    expect(downloads).toBe(1);
  });
});
