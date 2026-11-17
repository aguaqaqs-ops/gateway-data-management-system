import { describe, expect, it } from "vitest";
import { loadTableCase } from "../../test/helpers";
import { assembleTableRows, checkTableRowLocations, decodeTableEncodings } from "./table-assembly";

/**
 * Contract tests for the pure row assembly used by the comparison page. The
 * three segments mirror the B′ statement order of `loadTable`: check (validate
 * before the metadata read), decode (after the read, before the state
 * writes), assemble (after the state writes). The fixture bundle supplies
 * real snapshot rows plus the same-side `gateway.sta.enc.v1` encodings, so a
 * regression in either the encoding wiring (R10d) or the EXACT-table locator
 * validation (R11f) fails here.
 */
describe("assembleTableRows", () => {
  it("reports the filter-tab publication facts before any metadata read", async () => {
    const table = await loadTableCase("excluded-identity", "device_cfg");
    const checked = checkTableRowLocations({
      table: table.surfaceTable,
      locator: table.locator,
      records: table.tableRecords,
      beforeRowCount: table.beforeRows.length,
      currentRowCount: table.currentRows.length,
      hasBeforeSnapshot: table.hasBeforeSnapshot,
      hasCurrentSnapshot: table.hasCurrentSnapshot,
      filterTabs: table.filterTabs,
    });
    expect(checked.publishesFilterTabs).toBe(true);
    expect(checked.exactTable).toBe(true);
  });

  it("decodes both sides snapshot encodings from the real metadata", async () => {
    const table = await loadTableCase("excluded-identity", "device_cfg");
    const rowFilter = {
      before: { column: "gid", values: [9] },
      current: { column: "gid", values: [9] },
    };
    const { beforeEncodings, currentEncodings, currentCanonicalBlanks } = decodeTableEncodings({
      tableName: table.surfaceTable.table_name,
      beforeMetadata: table.beforeMetadata,
      currentMetadata: table.currentMetadata,
      degraded: false,
      rowFilter,
    });
    expect(beforeEncodings.size).toBeGreaterThan(0);
    expect(currentEncodings.size).toBeGreaterThan(0);
    expect(typeof currentCanonicalBlanks).toBe("boolean");
  });

  it("assembles filtered rows and scoped rows from the real fixture metadata", async () => {
    const table = await loadTableCase("excluded-identity", "device_cfg");
    const rowFilter = {
      before: { column: "gid", values: [9] },
      current: { column: "gid", values: [9] },
    };
    checkTableRowLocations({
      table: table.surfaceTable,
      locator: table.locator,
      records: table.tableRecords,
      beforeRowCount: table.beforeRows.length,
      currentRowCount: table.currentRows.length,
      hasBeforeSnapshot: table.hasBeforeSnapshot,
      hasCurrentSnapshot: table.hasCurrentSnapshot,
      filterTabs: table.filterTabs,
    });
    const { beforeEncodings, currentEncodings, currentCanonicalBlanks } = decodeTableEncodings({
      tableName: table.surfaceTable.table_name,
      beforeMetadata: table.beforeMetadata,
      currentMetadata: table.currentMetadata,
      degraded: false,
      rowFilter,
    });
    const built = assembleTableRows({
      table: table.surfaceTable,
      beforeRows: table.beforeRows,
      currentRows: table.currentRows,
      records: table.tableRecords,
      annotations: [],
      locator: table.locator,
      hasBeforeSnapshot: table.hasBeforeSnapshot,
      hasCurrentSnapshot: table.hasCurrentSnapshot,
      currentCanonicalBlanks,
      rowFilter,
      beforeEncodings,
      currentEncodings,
      filterTabs: table.filterTabs,
      degraded: false,
      unassigned: null,
      onlyInteresting: false,
      search: "",
      expandedRuns: new Set(),
      deletionLayout: "interleave",
    });
    expect(built.rows.length).toBeGreaterThan(0);
    expect(built.scoped.length).toBe(built.rows.length);
    for (const row of built.rows) expect(String(row.values.gid)).toBe("9");
  });

  it("enforces EXACT-table change counts against row_change_stats", async () => {
    const table = await loadTableCase("excluded-identity", "device_cfg");
    const stats = table.surfaceTable.row_change_stats;
    expect(stats).toBeDefined();
    const mutated = {
      ...table.surfaceTable,
      row_change_stats: {
        ...stats,
        row_added_count: (stats?.row_added_count ?? 0) + 1,
      },
    };
    expect(() =>
      checkTableRowLocations({
        table: mutated,
        locator: table.locator,
        records: table.tableRecords,
        beforeRowCount: table.beforeRows.length,
        currentRowCount: table.currentRows.length,
        hasBeforeSnapshot: table.hasBeforeSnapshot,
        hasCurrentSnapshot: table.hasCurrentSnapshot,
        filterTabs: table.filterTabs,
      }),
    ).toThrow(/已发布新增行数与 row_change_stats 不符/);
  });
});
