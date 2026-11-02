import { describe, expect, it } from "vitest";
import { readParquetTable } from "./parquet-reader";
import { loadComparisonPresentation, readLocalChangeRecords, readLocalTable } from "./presentation";
import { installedGoldenBundle } from "../../test/helpers";

describe("local Parquet browsing", () => {
  it("browses table slices and added, deleted and modified records locally", async () => {
    const { bundle, manifest } = await installedGoldenBundle();
    const current = manifest.closure.entries.find((entry) => entry.kind === "SNAPSHOT_TABLE" && entry.table_bindings?.some((binding) => binding.side === "current"));
    const records = manifest.closure.entries.find((entry) => entry.kind === "RECORDS");
    expect(current).toBeDefined();
    expect(records).toBeDefined();

    const rows = await readParquetTable(bundle, current?.logical_path ?? "", { columns: ["dev_addr", "description"], rowStart: 0, rowEnd: 2 });
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ dev_addr: "1", description: "线路保护装置 A" });
    expect(rows[1]).toMatchObject({ dev_addr: "2", description: "测控装置（升级）" });

    const diffs = await readParquetTable(bundle, records?.logical_path ?? "", { columns: ["record_kind", "before_values", "current_values"] });
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
    expect(presentation.view.tables[0]?.riskLevel).toBe("MEDIUM_HIGH");
    expect(presentation.tableArtifacts.get("device")?.before).toContain("tables/before/device/rows/");
    expect(presentation.tableArtifacts.get("device")?.current).toContain("tables/current/device.parquet");
    const beforeRows = await readLocalTable(bundle, presentation, "device", "before", { columns: ["dev_addr"] });
    const rows = await readLocalTable(bundle, presentation, "device", "current", { columns: ["dev_addr"] });
    const diffs = await readLocalChangeRecords(bundle, presentation, "device", { columns: ["record_kind"] });
    expect(beforeRows).toHaveLength(3);
    expect(rows).toHaveLength(3);
    expect(diffs.map((row) => row.record_kind).sort()).toEqual(["ROW_ADDED", "ROW_DELETED", "ROW_MODIFIED"]);
  });
});
