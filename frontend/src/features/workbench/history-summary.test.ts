import { describe, expect, it } from "vitest";
import { installedFixtureBundle } from "../../test/helpers";
import { loadComparisonPresentation } from "../bundle/presentation";
import { summarizeHistoryPair, summarizeSurface } from "./history-summary";
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
  it("matches the History three-node fixture surfaces (D1 fixture-based regression)", async () => {
    // Backend facts: history-three-nodes.tar manifest pairs carry
    // p0 table_count 9 / changed 6 / degraded 2, p1 table_count 10 / changed 7 / degraded 2.
    const { bundle, manifest } = await installedFixtureBundle("history-three-nodes");
    const pairs = (manifest.pairs ?? []) as Array<{ pair_id: string }>;
    expect(pairs.map((pair) => pair.pair_id).sort()).toEqual(["fe2a-history-fixture-p0", "fe2a-history-fixture-p1"]);
    const expectations: Record<string, { tableCount: number; changedTableCount: number; degradedTableCount: number }> = {
      "fe2a-history-fixture-p0": { tableCount: 9, changedTableCount: 6, degradedTableCount: 2 },
      "fe2a-history-fixture-p1": { tableCount: 10, changedTableCount: 7, degradedTableCount: 2 },
    };
    for (const pair of pairs) {
      const presentation = await loadComparisonPresentation(bundle, pair.pair_id);
      const summary = summarizeHistoryPair
        ? await summarizeHistoryPair(bundle, pair.pair_id)
        : summarizeSurface(presentation.surface, pair.pair_id);
      const expected = expectations[pair.pair_id];
      expect(summary).toMatchObject({ pairId: pair.pair_id, ...expected });
      expect(summary.tables).toHaveLength(expected.tableCount);
    }
  });
});
