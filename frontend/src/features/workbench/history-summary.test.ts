import { describe, expect, it } from "vitest";
import { summarizeSurface } from "./history-summary";
import type { ComparisonSurface } from "../view-model/model";

describe("summarizeSurface", () => {
  it("reports table, changed, degraded, and per-table row counts", () => {
    const surface = {
      tables: [
        { table_id: "t1", table_name: "telemetry", display_name: "遥测", table_status: "READY", change_kind: "UPDATED", row_change_stats: { row_added_count: 2, row_deleted_count: 3, row_modified_count: 4 } },
        { table_id: "t2", table_name: "channel", display_name: "通道", table_status: "READY", change_kind: "UNCHANGED", row_change_stats: { row_added_count: 0, row_deleted_count: 0, row_modified_count: 0 } },
        { table_id: "t3", table_name: "formula", display_name: "公式", table_status: "DEGRADED", change_kind: "DEGRADED" },
      ],
    } as unknown as ComparisonSurface;
    const summary = summarizeSurface(surface, "pair-1");
    expect(summary).toMatchObject({ pairId: "pair-1", tableCount: 3, changedTableCount: 2, degradedTableCount: 1 });
    expect(summary.tables[0]).toMatchObject({ tableName: "telemetry", displayName: "遥测", added: 2, deleted: 3, modified: 4 });
    expect(summary.tables[2]).toMatchObject({ tableName: "formula", added: 0, deleted: 0, modified: 0, changeKind: "DEGRADED" });
  });

  it("treats missing change metadata as unchanged", () => {
    const summary = summarizeSurface({ tables: [{ table_id: "t", table_name: "t", display_name: "T", table_status: "READY" }] } as unknown as ComparisonSurface);
    expect(summary.changedTableCount).toBe(0);
    expect(summary.degradedTableCount).toBe(0);
  });
});
