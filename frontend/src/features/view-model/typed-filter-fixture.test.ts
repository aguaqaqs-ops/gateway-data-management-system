import { describe, expect, it } from "vitest";
import { loadTableCase } from "../../test/helpers";
import { buildBrowseRows } from "./table-rows";

/**
 * Strict scalar filtering against the three kickoff F4 scenarios, driven by
 * the generated fixtures: real snapshot rows plus the real same-side
 * `gateway.sta.enc.v1` column encodings.
 */
describe("strict scalar filtering on F4 scenarios", () => {
  it("excluded-identity matches the published EXACT integer predicate exactly", async () => {
    const table = await loadTableCase("excluded-identity", "device_cfg");
    expect(table.hasBeforeSnapshot).toBe(true);
    expect(table.hasCurrentSnapshot).toBe(true);
    const address49 = table.presentation.view.groups
      .flatMap((group) => group.items)
      .flatMap((item) => item.tabs.map((tab) => ({ item, tab })))
      .find((entry) => entry.item.itemKey === "device:addr:49" && entry.tab.tabKey === "device_cfg");
    const rowFilter = address49?.tab.rowFilter;
    expect(rowFilter).toEqual({ before: { column: "gid", values: [7] }, current: null });
    const shown = buildBrowseRows({
      table: table.surfaceTable, beforeRows: table.beforeRows, currentRows: table.currentRows,
      records: table.tableRecords, annotations: [], locator: table.locator,
      hasBeforeSnapshot: table.hasBeforeSnapshot, hasCurrentSnapshot: table.hasCurrentSnapshot,
      rowFilter: rowFilter ?? null, beforeEncodings: table.beforeEncodings, currentEncodings: table.currentEncodings,
    });
    expect(shown.rows.length).toBeGreaterThan(0);
    for (const row of shown.rows) expect(String(row.values.gid)).toBe("7");
  });

  it("excluded-identity rejects non-canonical integer text against the same encodings", async () => {
    const table = await loadTableCase("excluded-identity", "device_cfg");
    for (const spoiled of ["07", " 7", "7 ", "-0"]) {
      const attempt = () => buildBrowseRows({
        table: table.surfaceTable, beforeRows: [{ gid: spoiled }], currentRows: [],
        records: [], annotations: [], locator: new Map(),
        hasBeforeSnapshot: true, hasCurrentSnapshot: false,
        rowFilter: { before: { column: "gid", values: [7] }, current: null },
        beforeEncodings: table.beforeEncodings, currentEncodings: table.currentEncodings,
      });
      expect(attempt, `gid text ${JSON.stringify(spoiled)}`).toThrow(/规范十进制/);
    }
  });

  it("integer-boundary matches integer predicates by value with real encodings", async () => {
    const table = await loadTableCase("integer-boundary", "device");
    const first = table.currentRows[0]?.dev_addr;
    expect(typeof first).toBe("string");
    const target = Number(first);
    expect(Number.isSafeInteger(target)).toBe(true);
    const shown = buildBrowseRows({
      table: table.surfaceTable, beforeRows: table.beforeRows, currentRows: table.currentRows,
      records: table.tableRecords, annotations: [], locator: table.locator,
      hasBeforeSnapshot: table.hasBeforeSnapshot, hasCurrentSnapshot: table.hasCurrentSnapshot,
      rowFilter: { before: null, current: { column: "dev_addr", values: [target] } },
      beforeEncodings: table.beforeEncodings, currentEncodings: table.currentEncodings,
    });
    expect(shown.rows.length).toBeGreaterThan(0);
    for (const row of shown.rows) expect(row.values.dev_addr).toBe(first);
    const spoiled = () => buildBrowseRows({
      table: table.surfaceTable, beforeRows: [], currentRows: [{ dev_addr: `0${first}` }],
      records: [], annotations: [], locator: new Map(),
      hasBeforeSnapshot: false, hasCurrentSnapshot: true,
      rowFilter: { before: null, current: { column: "dev_addr", values: [target] } },
      beforeEncodings: table.beforeEncodings, currentEncodings: table.currentEncodings,
    });
    expect(spoiled).toThrow(/规范十进制/);
  });

  it("text-identities compares string columns by raw value and rejects integer predicates", async () => {
    const table = await loadTableCase("text-identities", "device_cfg");
    expect(table.currentEncodings.get("gid")?.scalarKind).toBe("string");
    const first = table.currentRows[0]?.gid;
    expect(typeof first).toBe("string");
    const predicate = String(first);
    const shown = buildBrowseRows({
      table: table.surfaceTable, beforeRows: table.beforeRows, currentRows: table.currentRows,
      records: table.tableRecords, annotations: [], locator: table.locator,
      hasBeforeSnapshot: table.hasBeforeSnapshot, hasCurrentSnapshot: table.hasCurrentSnapshot,
      rowFilter: { before: null, current: { column: "gid", values: [predicate] } },
      beforeEncodings: table.beforeEncodings, currentEncodings: table.currentEncodings,
    });
    expect(shown.rows.length).toBeGreaterThan(0);
    for (const row of shown.rows) expect(row.values.gid).toBe(predicate);
    const numeric = Number(predicate);
    if (Number.isSafeInteger(numeric)) {
      const integerAttempt = () => buildBrowseRows({
        table: table.surfaceTable, beforeRows: table.beforeRows, currentRows: table.currentRows,
        records: table.tableRecords, annotations: [], locator: table.locator,
        hasBeforeSnapshot: table.hasBeforeSnapshot, hasCurrentSnapshot: table.hasCurrentSnapshot,
        rowFilter: { before: null, current: { column: "gid", values: [numeric] } },
        beforeEncodings: table.beforeEncodings, currentEncodings: table.currentEncodings,
      });
      expect(integerAttempt).toThrow(/矛盾/);
    }
  });
});
