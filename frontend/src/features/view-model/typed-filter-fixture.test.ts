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
    const address51 = table.presentation.view.groups
      .flatMap((group) => group.items)
      .flatMap((item) => item.tabs.map((tab) => ({ item, tab })))
      .find((entry) => entry.item.itemKey === "device:addr:51" && entry.tab.tabKey === "device_cfg");
    const rowFilter = address51?.tab.rowFilter;
    expect(rowFilter).toEqual({ before: { column: "gid", values: [9] }, current: { column: "gid", values: [9] } });
    const shown = buildBrowseRows({
      table: table.surfaceTable, beforeRows: table.beforeRows, currentRows: table.currentRows,
      records: table.tableRecords, annotations: [], locator: table.locator,
      hasBeforeSnapshot: table.hasBeforeSnapshot, hasCurrentSnapshot: table.hasCurrentSnapshot,
      rowFilter: rowFilter ?? null, beforeEncodings: table.beforeEncodings, currentEncodings: table.currentEncodings,
    });
    expect(shown.rows.length).toBeGreaterThan(0);
    for (const row of shown.rows) expect(String(row.values.gid)).toBe("9");
  });

  it("excluded-identity rejects non-canonical integer text against the same encodings", async () => {
    const table = await loadTableCase("excluded-identity", "device_cfg");
    expect(table.currentEncodings.get("gid")?.scalarKind).toBe("integer");
    for (const spoiled of ["07", " 7", "7 ", "-0"]) {
      const attempt = () => buildBrowseRows({
        table: table.surfaceTable, beforeRows: [], currentRows: [{ gid: spoiled }],
        records: [], annotations: [], locator: new Map(),
        hasBeforeSnapshot: false, hasCurrentSnapshot: true,
        rowFilter: { before: null, current: { column: "gid", values: [7] } },
        beforeEncodings: table.beforeEncodings, currentEncodings: table.currentEncodings,
      });
      expect(attempt, `gid text ${JSON.stringify(spoiled)}`).toThrow(/规范十进制/);
    }
  });

  it("integer-boundary matches integer predicates by value with real encodings", async () => {
    const table = await loadTableCase("integer-boundary", "device");
    expect(table.currentEncodings.get("dev_addr")?.scalarKind).toBe("integer");
    const safeRows = table.currentRows.filter((row) => {
      const value = row.dev_addr;
      return typeof value === "string" && /^(0|[1-9][0-9]*)$/.test(value) && BigInt(value) <= 9007199254740991n;
    });
    expect(safeRows.length).toBeGreaterThan(0);
    const target = Number(safeRows[0]?.dev_addr);
    const shown = buildBrowseRows({
      table: table.surfaceTable, beforeRows: [], currentRows: safeRows,
      records: [], annotations: [], locator: new Map(),
      hasBeforeSnapshot: false, hasCurrentSnapshot: true,
      rowFilter: { before: null, current: { column: "dev_addr", values: [target] } },
      beforeEncodings: table.beforeEncodings, currentEncodings: table.currentEncodings,
    });
    expect(shown.rows.length).toBeGreaterThan(0);
    for (const row of shown.rows) expect(row.values.dev_addr).toBe(safeRows[0]?.dev_addr);
    const spoiled = () => buildBrowseRows({
      table: table.surfaceTable, beforeRows: [], currentRows: [...safeRows, { dev_addr: `0${String(safeRows[0]?.dev_addr)}` }],
      records: [], annotations: [], locator: new Map(),
      hasBeforeSnapshot: false, hasCurrentSnapshot: true,
      rowFilter: { before: null, current: { column: "dev_addr", values: [target] } },
      beforeEncodings: table.beforeEncodings, currentEncodings: table.currentEncodings,
    });
    expect(spoiled).toThrow(/规范十进制/);
  });

  it("integer-boundary refuses to evaluate predicates over out-of-range values", async () => {
    const table = await loadTableCase("integer-boundary", "device");
    const wild = table.currentRows.filter((row) => typeof row.dev_addr === "string" && BigInt(row.dev_addr as string) > 9007199254740991n);
    expect(wild.length).toBeGreaterThan(0);
    const attempt = () => buildBrowseRows({
      table: table.surfaceTable, beforeRows: [], currentRows: table.currentRows,
      records: [], annotations: [], locator: new Map(),
      hasBeforeSnapshot: false, hasCurrentSnapshot: true,
      rowFilter: { before: null, current: { column: "dev_addr", values: [65532] } },
      beforeEncodings: table.beforeEncodings, currentEncodings: table.currentEncodings,
    });
    expect(attempt).toThrow(/范围/);
  });

  it("text-identities compares string columns by raw value and rejects integer predicates", async () => {
    const table = await loadTableCase("text-identities", "device_cfg");
    expect(table.currentEncodings.get("gid")?.scalarKind).toBe("string");
    const candidates = table.currentRows.filter((row) => typeof row.gid === "string");
    expect(candidates.length).toBeGreaterThan(0);
    const predicate = String(candidates[0]?.gid);
    const shown = buildBrowseRows({
      table: table.surfaceTable, beforeRows: table.beforeRows, currentRows: table.currentRows,
      records: table.tableRecords, annotations: [], locator: table.locator,
      hasBeforeSnapshot: table.hasBeforeSnapshot, hasCurrentSnapshot: table.hasCurrentSnapshot,
      rowFilter: { before: null, current: { column: "gid", values: [predicate] } },
      beforeEncodings: table.beforeEncodings, currentEncodings: table.currentEncodings,
    });
    expect(shown.rows.length).toBeGreaterThan(0);
    expect(shown.rows.some((row) => row.values.gid === predicate)).toBe(true);
    for (const row of shown.rows) {
      if (row.values.gid !== undefined) expect(row.values.gid).toBe(predicate);
    }
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
