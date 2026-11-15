import { describe, expect, it } from "vitest";
import type { RowDiffRecord, SurfaceTable } from "./model";
import {
  type BrowseRow,
  buildBrowseRows,
  canReuseUnrecordedIdentity,
  collapseUnchangedRows,
  missingSideMarker,
  normalizeDisplayScalar,
  parseRowLocator,
  validateRowLocations,
} from "./table-rows";
import { loadTableCase } from "../../test/helpers";
import type { SnapshotColumnEncoding } from "./snapshot-encoding";

function encodings(entries: Array<[string, Partial<SnapshotColumnEncoding> & { scalarKind: SnapshotColumnEncoding["scalarKind"] }]>): Map<string, SnapshotColumnEncoding> {
  return new Map(entries.map(([name, entry]) => [name, {
    columnName: name, declaredBits: null, signed: true, sqlType: "", logicalType: "standard", physicalType: "utf8",
    declaredKind: entry.scalarKind === "integer" ? "signed-integer" : entry.scalarKind === "string" ? "string" : null,
    ...entry,
  }]));
}

const browseEncodings = () => encodings([
  ["dev_addr", { scalarKind: "integer", declaredBits: 64, signed: true }],
  ["description", { scalarKind: "string" }],
]);

function hex(byte: number): Uint8Array {
  return new Uint8Array(32).fill(byte);
}

function table(overrides: Partial<SurfaceTable> = {}): SurfaceTable {
  return {
    table_id: "device",
    table_name: "device",
    display_name: "装置表",
    table_status: "MODIFIED",
    columns: [
      { name: "dev_addr", display_name: "装置地址", scalar_type: "INT", nullable: false, present_in: "BOTH", display_order: 0, pinned: true },
      { name: "description", display_name: "描述", scalar_type: "VARCHAR(128)", nullable: true, present_in: "BOTH", display_order: 1, pinned: false },
    ],
    row_change_stats: { row_count_before: 3, row_count_current: 3, row_added_count: 1, row_deleted_count: 1, row_modified_count: 1 },
    ...overrides,
  } as SurfaceTable;
}

function record(kind: string, byte: number, extras: Record<string, unknown> = {}): RowDiffRecord {
  return { table_name: "device", record_kind: kind, row_identity: hex(byte), ...extras } as RowDiffRecord;
}

function locatorRow(byte: number, before: number | null, current: number | null, context: { before?: unknown; current?: unknown } = {}): Record<string, unknown> {
  return {
    row_identity: hex(byte),
    before_row_index: before === null ? null : BigInt(before),
    current_row_index: current === null ? null : BigInt(current),
    before_filter_context_json: context.before === undefined ? null : JSON.stringify(context.before),
    current_filter_context_json: context.current === undefined ? null : JSON.stringify(context.current),
  };
}

describe("row locator decoding", () => {
  it("keys locator rows by their canonical identity and converts BigInt indices", () => {
    const locator = parseRowLocator([locatorRow(0x11, 2, 0), locatorRow(0x22, null, 1, { current: { gid: 8 } })]);
    expect([...locator.keys()]).toHaveLength(2);
    expect(locator.get(`sha256:${"11".repeat(32)}`)).toEqual({ beforeRowIndex: 2, currentRowIndex: 0, beforeFilterContext: null, currentFilterContext: null });
    expect(locator.get(`sha256:${"22".repeat(32)}`)?.currentFilterContext).toEqual({ gid: 8 });
  });

  it("rejects duplicate identities and non-object filter contexts", () => {
    expect(() => parseRowLocator([locatorRow(0x11, 0, 0), locatorRow(0x11, 1, 1)])).toThrow(/行身份重复/);
    expect(() => parseRowLocator([{ ...locatorRow(0x11, 0, 0), before_filter_context_json: "[1]" }])).toThrow(/不是对象/);
    expect(() => parseRowLocator([{ ...locatorRow(0x11, 0, 0), current_filter_context_json: "not-json" }])).toThrow(/不是合法 JSON/);
  });
});

describe("locator validation", () => {
  const base = { table: table(), publications: true };
  function validate(records: RowDiffRecord[], locatorRows: Record<string, unknown>[], overrides: Partial<Parameters<typeof validateRowLocations>[0]> = {}) {
    return () => validateRowLocations({
      table: base.table,
      records,
      locator: parseRowLocator(locatorRows),
      beforeRowCount: 3,
      currentRowCount: 3,
      hasBeforeSnapshot: true,
      hasCurrentSnapshot: true,
      publishesFilterTabs: base.publications,
      exactTable: false,
      ...overrides,
    });
  }

  it("accepts one locator row per published ordinary record", () => {
    expect(validate([record("ROW_ADDED", 0x11), record("ROW_MODIFIED", 0x22), record("ROW_DELETED", 0x33)], [locatorRow(0x11, null, 1), locatorRow(0x22, 1, 0), locatorRow(0x33, 2, null)])).not.toThrow();
    expect(validate([record("ROW_ADDED", 0x11), record("ROW_MODIFIED", 0x22), record("ROW_DELETED", 0x33)], [locatorRow(0x11, null, 1), locatorRow(0x22, 1, 0), locatorRow(0x33, 2, null)], { exactTable: true })).not.toThrow();
  });

  it.each([
    ["普通行记录缺少身份", [record("ROW_ADDED", 0x11)], []],
    ["缺少行定位", [record("ROW_ADDED", 0x11)], [locatorRow(0x22, null, 2)]],
    ["身份重复", [record("ROW_ADDED", 0x11), record("ROW_MODIFIED", 0x11)], [locatorRow(0x11, null, 2)]],
    ["改后侧不存在却有快照位置", [record("ROW_DELETED", 0x11)], [locatorRow(0x11, 2, 1)]],
    ["改前侧有快照时上下文必须为空", [record("ROW_MODIFIED", 0x11)], [locatorRow(0x11, 1, 0, { before: { gid: 1 } })]],
    ["整表入口不应带过滤上下文", [record("ROW_MODIFIED", 0x11)], [locatorRow(0x11, 1, 0, { current: { gid: 1 } })]],
  ])("rejects %s", (_, records, locatorRows) => {
    expect(validate(records, locatorRows)).toThrow(/Row.*|表 device/);
  });

  it("rejects indices without the matching snapshot and out-of-range indices", () => {
    expect(validate([record("ROW_MODIFIED", 0x11)], [locatorRow(0x11, 1, 0)], { hasBeforeSnapshot: false })).toThrow(/缺少改前快照/);
    expect(validate([record("ROW_MODIFIED", 0x11)], [locatorRow(0x11, 1, 0)], { hasBeforeSnapshot: true, hasCurrentSnapshot: false })).toThrow(/缺少改后快照/);
    expect(validate([record("ROW_MODIFIED", 0x11)], [locatorRow(0x11, 5, 0)])).toThrow(/改前侧位置无效/);
    expect(validate([record("ROW_MODIFIED", 0x11)], [locatorRow(0x11, 1, 5)])).toThrow(/改后侧位置无效/);
  });

  it("requires a locator whenever ordinary records exist", () => {
    expect(validate([record("ROW_MODIFIED", 0x11)], [])).toThrow(/缺少行定位产物/);
  });
});

describe("unrecorded identity reuse criteria", () => {
  const exact = { facts: { basis: "EXACT" as const, change_kind: "MODIFIED", risk_level: null, before_row_count: 1, current_row_count: 1, table_scope: null } };
  const fallback = { facts: { ...exact.facts, basis: "TABLE_FALLBACK" as const } };

  it("allows reuse only for EXACT, fully counted tables without a before snapshot", () => {
    expect(canReuseUnrecordedIdentity(table(), [exact], false, true)).toBe(true);
    expect(canReuseUnrecordedIdentity(table(), [exact], true, true)).toBe(false);
    expect(canReuseUnrecordedIdentity(table(), [exact], false, false)).toBe(false);
    expect(canReuseUnrecordedIdentity(table(), [], false, true)).toBe(false);
    expect(canReuseUnrecordedIdentity(table(), [fallback], false, true)).toBe(false);
    expect(canReuseUnrecordedIdentity(table(), [exact, fallback], false, true)).toBe(false);
    expect(canReuseUnrecordedIdentity(table({ row_change_stats: { row_count_before: null, row_count_current: 1 } }), [exact], false, true)).toBe(false);
  });
});

describe("browse rows from published locators", () => {
  const rowsBefore = [
    { dev_addr: 7, description: "一" },
    { dev_addr: 8, description: "二" },
    { dev_addr: 9, description: "三" },
  ];
  const rowsCurrent = [
    { dev_addr: 7, description: "一改" },
    { dev_addr: 8, description: "二" },
    { dev_addr: 10, description: "新" },
  ];

  it("places snapshot values by locator index instead of matching rows in the browser", () => {
    const locator = parseRowLocator([locatorRow(0x11, 0, 0), locatorRow(0x22, 1, 1), locatorRow(0x33, 2, null), locatorRow(0x44, null, 2)]);
    const result = buildBrowseRows({
      table: table(), beforeRows: rowsBefore, currentRows: rowsCurrent,
      records: [record("ROW_MODIFIED", 0x11, { changed_columns: ["description"] }), record("ROW_DELETED", 0x33), record("ROW_ADDED", 0x44)],
      annotations: [], locator,
    });
    const kinds = result.rows.map((row) => row.kind);
    expect(kinds).toContain("modified-before");
    expect(kinds).toContain("modified-after");
    expect(kinds).toContain("deleted");
    expect(kinds).toContain("added");
    const modifiedAfter = result.rows.find((row) => row.kind === "modified-after");
    expect(modifiedAfter?.values.description).toBe("一改");
    const unchanged = result.rows.find((row) => row.kind === "unchanged");
    expect(unchanged?.values.description).toBe("二");
  });

  it("uses the recorded before context when the before snapshot is missing", () => {
    const locator = parseRowLocator([locatorRow(0x11, null, 0, { before: { gid: 8 } })]);
    const result = buildBrowseRows({
      table: table({ row_change_stats: { row_count_before: 3, row_count_current: 3 } }),
      beforeRows: [], currentRows: [rowsCurrent[0]!],
      records: [record("ROW_MODIFIED", 0x11, { changed_columns: ["gid"], before_values: [{ column_name: "gid", value: { kind: "int", text: "8" } }] })],
      annotations: [], locator, hasBeforeSnapshot: false,
    });
    const before = result.rows.find((row) => row.kind === "modified-before");
    expect(before?.rowNumberTitle).toBe("改前值不在本 bundle 中");
    expect(before?.values.gid).toBe(8);
  });

  it("marks a keyless deleted row whose before value is unavailable", () => {
    const locator = parseRowLocator([locatorRow(0x55, null, null)]);
    const result = buildBrowseRows({
      table: table({ row_change_stats: { row_count_before: null, row_count_current: 3 } }),
      beforeRows: [], currentRows: rowsCurrent, records: [record("ROW_DELETED", 0x55)], annotations: [],
      locator, hasBeforeSnapshot: false,
    });
    const deleted = result.rows.find((row) => row.kind === "deleted");
    expect(deleted?.rowNumberTitle).toBe("改前值不可得");
  });

  it("interleaves replaced rows where they stood instead of listing deletions last", () => {
    const before = [1, 2, 3, 4, 5].map((n) => ({ dev_addr: n, description: `旧${n}` }));
    const current = [1, 21, 31, 4, 51, 6].map((n) => ({ dev_addr: n, description: `新${n}` }));
    const locator = parseRowLocator([
      locatorRow(0x12, 1, null), locatorRow(0x13, 2, null), locatorRow(0x21, null, 1), locatorRow(0x31, null, 2),
      locatorRow(0x05, 4, null), locatorRow(0x51, null, 4), locatorRow(0x06, null, 5),
    ]);
    const result = buildBrowseRows({
      table: table(), beforeRows: before, currentRows: current,
      records: [record("ROW_DELETED", 0x12), record("ROW_DELETED", 0x13), record("ROW_ADDED", 0x21), record("ROW_ADDED", 0x31),
        record("ROW_DELETED", 0x05), record("ROW_ADDED", 0x51), record("ROW_ADDED", 0x06)],
      annotations: [], locator,
    });
    expect(result.rows.map((row) => `${row.kind === "deleted" ? "-" : row.kind === "added" ? "+" : " "}${row.rowNumber}`))
      .toEqual([" 1", "-2", "+2", "-3", "+3", " 4", "-5", "+5", "+6"]);
  });

  it("places Preview deletions of an ordered table by their recorded before position", () => {
    const current = [1, 21, 31, 4].map((n) => ({ dev_addr: n, description: `新${n}` }));
    const locator = parseRowLocator([locatorRow(0x12, null, null), locatorRow(0x13, null, null), locatorRow(0x21, null, 1), locatorRow(0x31, null, 2)]);
    const result = buildBrowseRows({
      table: table({ ordered_extension: {}, row_change_stats: { row_count_before: null, row_count_current: 4 } }),
      beforeRows: [], currentRows: current, hasBeforeSnapshot: false,
      records: [record("ROW_DELETED", 0x13, { before_values: no(3) }), record("ROW_DELETED", 0x12, { before_values: no(2) }),
        record("ROW_ADDED", 0x21), record("ROW_ADDED", 0x31)],
      annotations: [], locator,
    });
    expect(result.rows.map((row) => `${row.kind === "deleted" ? "-" : row.kind === "added" ? "+" : " "}${row.rowNumber}`))
      .toEqual([" 1", "-2", "+2", "-3", "+3", " 4"]);
  });

  // A blank row (published only as a blank interval) displays and shifts later rows exactly like an ordinary insert.
  const INSERTED_ROW_SHAPES: Array<[string, RowDiffRecord[], Array<Record<string, unknown>>]> = [
    ["an ordinary row", [record("ROW_ADDED", 0x0b)], [locatorRow(0x0b, null, 1)]],
    ["a blank row", [{ table_name: "device", record_kind: "BLANK_INSERT_INTERVAL",
      interval: { before_start: null, before_end: null, current_start: 2, current_end: 2, row_count: 1 } } as RowDiffRecord], []],
  ];
  it.each(INSERTED_ROW_SHAPES)("pairs shifted replacements after inserting %s above them", (_, insertRecords, insertLocator) => {
    const current = [1, 0, 2, 31, 41, 5].map((n) => ({ dev_addr: n, description: `新${n}` }));
    const locator = parseRowLocator([...insertLocator, locatorRow(0x13, null, null), locatorRow(0x14, null, null),
      locatorRow(0x31, null, 3), locatorRow(0x41, null, 4)]);
    const result = buildBrowseRows({
      table: table({ ordered_extension: {}, row_change_stats: { row_count_before: null, row_count_current: 6 } }),
      beforeRows: [], currentRows: current, hasBeforeSnapshot: false,
      records: [...insertRecords, record("ROW_DELETED", 0x13, { before_values: no(3) }), record("ROW_DELETED", 0x14, { before_values: no(4) }),
        record("ROW_ADDED", 0x31), record("ROW_ADDED", 0x41)],
      annotations: [], locator,
    });
    expect(result.rows.map((row) => `${row.kind === "deleted" ? "-" : row.kind === "added" ? "+" : " "}${row.rowNumber}`))
      .toEqual([" 1", "+2", " 3", "-3", "+4", "-4", "+5", " 6"]);
  });

  // Deleting a blank row displays and shifts later rows exactly like an ordinary delete.
  const no = (value: number) => [{ column_name: "no", value: { kind: "unsigned-integer", text: String(value) } }];
  const DELETED_ROW_SHAPES: Array<[string, RowDiffRecord[], Array<Record<string, unknown>>]> = [
    ["an ordinary row", [record("ROW_DELETED", 0x02, { before_values: no(2) })], [locatorRow(0x02, null, null)]],
    ["a blank row", [{ table_name: "device", record_kind: "BLANK_DELETE_INTERVAL",
      interval: { before_start: 2, before_end: 2, current_start: null, current_end: null, row_count: 1 } } as RowDiffRecord], []],
  ];
  it.each(DELETED_ROW_SHAPES)("pairs shifted replacements after deleting %s above them", (_, deleteRecords, deleteLocator) => {
    const current = [1, 3, 41, 51, 6].map((n) => ({ dev_addr: n, description: `新${n}` }));
    const locator = parseRowLocator([...deleteLocator, locatorRow(0x14, null, null), locatorRow(0x15, null, null),
      locatorRow(0x41, null, 2), locatorRow(0x51, null, 3)]);
    const result = buildBrowseRows({
      table: table({ ordered_extension: {}, row_change_stats: { row_count_before: null, row_count_current: 5 } }),
      beforeRows: [], currentRows: current, hasBeforeSnapshot: false,
      records: [...deleteRecords, record("ROW_DELETED", 0x14, { before_values: no(4) }), record("ROW_DELETED", 0x15, { before_values: no(5) }),
        record("ROW_ADDED", 0x41), record("ROW_ADDED", 0x51)],
      annotations: [], locator,
    });
    expect(result.rows.map((row) => `${row.kind === "deleted" ? "-" : row.kind === "added" ? "+" : " "}${row.rowNumber}`)).toEqual([" 1", "-2", " 2", "-4", "+3", "-5", "+4", " 5"]);
  });

  it("matches either half of the per-side filter", () => {
    const locator = parseRowLocator([locatorRow(0x11, 0, 0)]);
    const result = buildBrowseRows({
      table: table(), beforeRows: rowsBefore, currentRows: rowsCurrent,
      records: [record("ROW_MODIFIED", 0x11, { changed_columns: ["description"] })],
      annotations: [], locator, rowFilter: { before: { column: "dev_addr", values: [7] }, current: null },
      beforeEncodings: browseEncodings(), currentEncodings: browseEncodings(),
    });
    expect(result.rows.map((row) => row.values.dev_addr)).toEqual([7, 7]);
    const currentOnly = buildBrowseRows({
      table: table(), beforeRows: rowsBefore, currentRows: rowsCurrent,
      records: [record("ROW_MODIFIED", 0x11, { changed_columns: ["description"] })],
      annotations: [], locator, rowFilter: { before: null, current: { column: "dev_addr", values: [7] } },
      beforeEncodings: browseEncodings(), currentEncodings: browseEncodings(),
    });
    expect(currentOnly.rows.map((row) => row.kind)).toEqual(["modified-before", "modified-after"]);
  });

  it("applies the unrecorded-identity reuse only when the criteria say so", () => {
    const filterResult = (reuse: boolean) => buildBrowseRows({
      table: table(), beforeRows: [], currentRows: rowsCurrent, records: [],
      annotations: [], locator: new Map(), hasBeforeSnapshot: false, rowFilter: { before: { column: "dev_addr", values: [8] }, current: null },
      beforeEncodings: browseEncodings(), currentEncodings: browseEncodings(),
      reuseUnrecordedBefore: reuse,
    }).rows.map((row) => row.values.dev_addr);
    expect(filterResult(false)).toEqual([]);
    expect(filterResult(true)).toEqual([8]);
  });

  it("never matches NULL and compares integer predicates by value", () => {
    const locator = parseRowLocator([locatorRow(0x66, null, null)]);
    const nullRow = buildBrowseRows({
      table: table(), beforeRows: [], currentRows: [{ dev_addr: null }], records: [], annotations: [], locator,
      rowFilter: { before: null, current: { column: "dev_addr", values: [0] } },
      beforeEncodings: browseEncodings(), currentEncodings: browseEncodings(),
    });
    expect(nullRow.rows).toHaveLength(0);
    const integerRow = buildBrowseRows({
      table: table(), beforeRows: [], currentRows: [{ dev_addr: 7n }], records: [], annotations: [], locator,
      rowFilter: { before: null, current: { column: "dev_addr", values: [7] } },
      beforeEncodings: browseEncodings(), currentEncodings: browseEncodings(),
    });
    expect(integerRow.rows).toHaveLength(1);
  });

  it("skips predicate assertions for a degraded table", () => {
    const locator = parseRowLocator([locatorRow(0x11, 0, 0)]);
    const result = buildBrowseRows({
      table: table(), beforeRows: rowsBefore, currentRows: rowsCurrent,
      records: [record("ROW_MODIFIED", 0x11, { changed_columns: ["description"] })],
      annotations: [], locator, rowFilter: { before: { column: "dev_addr", values: [999] }, current: null },
      degraded: true,
    });
    expect(result.rows.length).toBeGreaterThan(0);
  });
});

describe("missing-side cell marker", () => {
  it("marks physically absent columns and keeps NULL distinct", async () => {
    const { surfaceTable } = await loadTableCase("schema-keyless", "device_st");
    const presentIn = new Map(surfaceTable.columns?.map((column) => [column.name, column.present_in]));
    expect(presentIn.get("before_only")).toBe("BEFORE");
    expect(presentIn.get("dev_addr")).toBe("BOTH");
    expect(missingSideMarker("current", presentIn.get("before_only"))).toBe("该侧无此列");
    expect(missingSideMarker("before", presentIn.get("before_only"))).toBeNull();
    expect(missingSideMarker("current", presentIn.get("dev_addr"))).toBeNull();
    expect(missingSideMarker("before", presentIn.get("dev_addr"))).toBeNull();
    expect(missingSideMarker(null, presentIn.get("before_only"))).toBeNull();
    expect(missingSideMarker("current", presentIn.get("before_only")) ?? normalizeDisplayScalar(null)).toBe("该侧无此列");
    expect(missingSideMarker("current", presentIn.get("dev_addr")) ?? normalizeDisplayScalar(null)).toBe("—");
  });
});

describe("unchanged run folding", () => {
  const row = (rowNumber: number, kind: BrowseRow["kind"] = "unchanged"): BrowseRow => ({
    key: `r${rowNumber}`, kind, side: "current", rowNumber, rowIdentity: `id${rowNumber}`, riskLevel: null,
    recordKind: null, semanticKind: null, beforePosition: null, currentPosition: rowNumber,
    changedColumns: [], values: {}, pairKey: null,
  });
  const rows = [row(1), row(2), row(3, "added"), row(4), row(5), row(6)];

  it("folds each unchanged run into one row", () => {
    const folded = collapseUnchangedRows(rows, new Set());
    expect(folded.map((item) => [item.kind, item.collapsedCount ?? null, item.expanded ?? null]))
      .toEqual([["collapsed", 2, false], ["added", null, null], ["collapsed", 3, false]]);
  });

  it("keeps a handle above an opened run so it can fold again", () => {
    const key = collapseUnchangedRows(rows, new Set())[2]?.key ?? "";
    const opened = collapseUnchangedRows(rows, new Set([key]));
    expect(opened.map((item) => item.kind === "collapsed" ? `handle:${String(item.expanded)}` : item.key))
      .toEqual(["handle:false", "r3", "handle:true", "r4", "r5", "r6"]);
    expect(opened[2]?.key).toBe(key);
    expect(collapseUnchangedRows(rows, new Set())).toHaveLength(3);
  });
});
