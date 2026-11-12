import { describe, expect, it } from "vitest";
import { loadComparisonPresentation } from "../bundle/presentation";
import { loadTableCase, type FixtureTableCase } from "../../test/helpers";
import {
  buildBrowseRows,
  canReuseUnrecordedIdentity,
  validateRowLocations,
  type RowLocatorRecord,
} from "./table-rows";
import type { RowDiffRecord, SurfaceTable } from "./model";

function findTabFilter(presentation: Awaited<ReturnType<typeof loadComparisonPresentation>>, itemKey: string, tabKey: string) {
  for (const group of presentation.view.groups) {
    for (const item of group.items) {
      if (item.itemKey !== itemKey) continue;
      const tab = item.tabs.find((entry) => entry.tabKey === tabKey);
      if (tab?.rowFilter) return tab.rowFilter;
    }
  }
  throw new Error(`no filter tab ${itemKey}/${tabKey}`);
}

function exactTableOf(filterTabs: FixtureTableCase["filterTabs"]): boolean {
  return filterTabs.length > 0 && filterTabs.every((tab) => tab.facts?.basis === "EXACT");
}

describe("unrecorded identity reuse against generated fixtures", () => {
  it("shows the unrecorded current row through the before predicate only with reuse", async () => {
    const table = await loadTableCase("duplicates-orphans", "device_cfg");
    const rowFilter = findTabFilter(table.presentation, "device:addr:50", "device_cfg");
    expect(rowFilter).toEqual({ before: { column: "gid", values: [8] }, current: null });
    expect(table.hasBeforeSnapshot).toBe(false);
    expect(table.hasCurrentSnapshot).toBe(true);
    expect(exactTableOf(table.filterTabs)).toBe(true);
    const reuse = canReuseUnrecordedIdentity(table.surfaceTable, table.filterTabs, table.hasBeforeSnapshot, table.hasCurrentSnapshot);
    expect(reuse).toBe(true);
    const shown = buildBrowseRows({
      table: table.surfaceTable, beforeRows: table.beforeRows, currentRows: table.currentRows,
      records: table.tableRecords, annotations: [], locator: table.locator,
      hasBeforeSnapshot: table.hasBeforeSnapshot, hasCurrentSnapshot: table.hasCurrentSnapshot,
      rowFilter, beforeEncodings: table.beforeEncodings, currentEncodings: table.currentEncodings,
      reuseUnrecordedBefore: true,
    });
    expect(shown.rows.map((row) => String(row.values.id))).toContain("2");
    const hidden = buildBrowseRows({
      table: table.surfaceTable, beforeRows: table.beforeRows, currentRows: table.currentRows,
      records: table.tableRecords, annotations: [], locator: table.locator,
      hasBeforeSnapshot: table.hasBeforeSnapshot, hasCurrentSnapshot: table.hasCurrentSnapshot,
      rowFilter, beforeEncodings: table.beforeEncodings, currentEncodings: table.currentEncodings,
      reuseUnrecordedBefore: false,
    });
    expect(hidden.rows).toHaveLength(0);
  });

  it("never reuses an unrecorded identity under TABLE_FALLBACK", async () => {
    const table = await loadTableCase("identity-changes", "device_cfg");
    expect(exactTableOf(table.filterTabs)).toBe(false);
    const reuse = canReuseUnrecordedIdentity(table.surfaceTable, table.filterTabs, table.hasBeforeSnapshot, table.hasCurrentSnapshot);
    expect(reuse).toBe(false);
    const beforeOnly = findTabFilter(table.presentation, "device:addr:49", "device_cfg");
    expect(beforeOnly).toEqual({ before: { column: "gid", values: [7] }, current: null });
    const shown = buildBrowseRows({
      table: table.surfaceTable, beforeRows: table.beforeRows, currentRows: table.currentRows,
      records: table.tableRecords, annotations: [], locator: table.locator,
      hasBeforeSnapshot: table.hasBeforeSnapshot, hasCurrentSnapshot: table.hasCurrentSnapshot,
      rowFilter: beforeOnly, beforeEncodings: table.beforeEncodings, currentEncodings: table.currentEncodings,
      reuseUnrecordedBefore: false,
    });
    expect(shown.rows).toHaveLength(0);
  });
});

describe("EXACT integrity invariants from generated fixtures", () => {
  async function invariantInput(): Promise<{ table: SurfaceTable; records: RowDiffRecord[]; locator: Map<string, RowLocatorRecord> }> {
    const table = await loadTableCase("duplicates-orphans", "device_cfg");
    expect(exactTableOf(table.filterTabs)).toBe(true);
    return { table: table.surfaceTable, records: table.tableRecords, locator: table.locator };
  }

  function validate(table: SurfaceTable, records: RowDiffRecord[], locator: Map<string, RowLocatorRecord>, exactTable: boolean) {
    return () => validateRowLocations({
      table, records, locator, beforeRowCount: 0, currentRowCount: 3,
      hasBeforeSnapshot: false, hasCurrentSnapshot: true, publishesFilterTabs: true, exactTable,
    });
  }

  it("accepts the published EXACT table unchanged", async () => {
    const { table, records, locator } = await invariantInput();
    expect(validate(table, records, locator, true)).not.toThrow();
  });

  const mutations: Array<[string, ((table: SurfaceTable) => SurfaceTable) | null, ((records: RowDiffRecord[]) => RowDiffRecord[]) | null, RegExp]> = [
    ["非零 suppressed_added_count", (table: SurfaceTable) => ({ ...table, row_change_stats: { ...table.row_change_stats, suppressed_added_count: 1 } }), null, /suppressed/],
    ["非零 suppressed_deleted_count", (table: SurfaceTable) => ({ ...table, row_change_stats: { ...table.row_change_stats, suppressed_deleted_count: 2 } }), null, /suppressed/],
    ["已发布行记录数与 row_change_stats 不符", null, (records: RowDiffRecord[]) => records.filter((record) => record.record_kind !== "ROW_MODIFIED"), /不符/],
    ["locator 身份集合多余", null, null, /多余/],
  ];
  it.each(mutations)("rejects %s", async (_, patchTable, patchRecords, pattern) => {
    const { table, records, locator } = await invariantInput();
    const nextTable = patchTable ? patchTable(table) : table;
    const nextRecords = patchRecords ? patchRecords(records) : records;
    const nextLocator = new Map(locator);
    if (!patchTable && !patchRecords) nextLocator.set(`sha256:${"ff".repeat(32)}`, { beforeRowIndex: null, currentRowIndex: 2, beforeFilterContext: null, currentFilterContext: null });
    expect(validate(nextTable, nextRecords, nextLocator, true)).toThrow(pattern);
  });

  it("does not apply the EXACT invariants to a TABLE_FALLBACK table", async () => {
    const { table, records, locator } = await invariantInput();
    const degraded = { ...table, row_change_stats: { ...table.row_change_stats, suppressed_added_count: 5, row_modified_count: 99 } };
    const extra = new Map(locator);
    extra.set(`sha256:${"ff".repeat(32)}`, { beforeRowIndex: null, currentRowIndex: 2, beforeFilterContext: null, currentFilterContext: null });
    expect(validate(degraded, records, extra, false)).not.toThrow();
  });
});
