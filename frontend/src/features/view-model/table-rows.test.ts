import { describe, expect, it } from "vitest";
import type { NavigationFacts, RiskAnnotation, RowDiffRecord, SurfaceTable } from "./model";
import {
  type BrowseRow,
  buildBrowseRows,
  blankIntervalLabel,
  canReuseUnrecordedIdentity,
  collapseUnchangedRows,
  columnHeaderTitle,
  deriveChangeLocations,
  formatFloatBits,
  missingSideMarker,
  normalizeDisplayScalar,
  parseRowLocator,
  rowMove,
  rowRiskAnnotation,
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

describe("device point address changes", () => {
  const pointTables = ["device_st", "device_mx", "device_co", "device_sg", "device_sp", "device_cnt", "device_sn", "device_tap", "device_other", "device_disturb"];
  function browse(tableName: string, columns: string[] | undefined, onlyInteresting = false) {
    const modified = record("ROW_MODIFIED", 0x11, columns === undefined ? {} : { changed_columns: columns });
    return buildBrowseRows({
      table: table({ table_name: tableName }), beforeRows: [{ dev_addr: 1, description: "旧" }],
      currentRows: [{ dev_addr: 2, description: "新" }], records: [modified], locator: parseRowLocator([locatorRow(0x11, 0, 0)]),
      annotations: [{ annotation_id: "risk", risk_level: "MEDIUM_HIGH", diagnostics: [], reasons: [],
        target: { target_type: "ROW", table_name: tableName, row_identity: `sha256:${"11".repeat(32)}`,
          before_row_identity: null, current_row_identity: null, changed_columns: [], coverage: null, position: null, position_range: null } }],
      onlyInteresting,
    });
  }

  it.each(pointTables)("keeps the current %s point but excludes address-only changes from navigation and differences", (name) => {
    const result = browse(name, ["dev_addr"]);
    expect(result.rows).toHaveLength(1);
    expect(result.rows[0]).toMatchObject({ kind: "unchanged", values: { dev_addr: 2 }, changedColumns: [], riskLevel: null });
    expect(deriveChangeLocations(result.scoped)).toEqual([]);
    expect(browse(name, ["dev_addr"], true).rows.map((row) => row.kind)).toEqual(["collapsed"]);
  });

  it.each([true, false])("matches the real before side when a snapshot is available: %s", (hasBefore) => {
    const base = {
      table: table({ table_name: "device_st" }), beforeRows: hasBefore ? [{ dev_addr: 1, description: "旧" }] : [],
      currentRows: [{ dev_addr: 2, description: "当前" }], hasBeforeSnapshot: hasBefore,
      records: [record("ROW_MODIFIED", 0x11, { changed_columns: ["dev_addr"], before_values: [{ column_name: "dev_addr", value: { kind: "int", text: "1" } }] })],
      locator: parseRowLocator([locatorRow(0x11, hasBefore ? 0 : null, 0, hasBefore ? {} : { before: { dev_addr: 1 } })]),
      annotations: [], beforeEncodings: browseEncodings(), currentEncodings: browseEncodings(),
    };
    const oldSide = buildBrowseRows({ ...base, rowFilter: { before: { column: "dev_addr", values: [1] }, current: null } });
    expect(oldSide.rows).toHaveLength(1);
    expect(oldSide.rows[0]).toMatchObject({ kind: "unchanged", side: "current", values: { dev_addr: 2, description: "当前" } });
    expect(deriveChangeLocations(oldSide.scoped)).toEqual([]);
    expect(buildBrowseRows({ ...base, rowFilter: { before: { column: "dev_addr", values: [2] }, current: null } }).rows).toEqual([]);
    expect(buildBrowseRows({ ...base, unassigned: { side: "before", predicates: [{ column: "dev_addr", values: [2] }] } }).rows).toHaveLength(1);
    expect(buildBrowseRows({ ...base, unassigned: { side: "before", predicates: [{ column: "dev_addr", values: [1] }] } }).rows).toEqual([]);
    const only = buildBrowseRows({ ...base, rowFilter: { before: { column: "dev_addr", values: [1] }, current: null }, onlyInteresting: true });
    expect(only.rows.map((row) => row.kind)).toEqual(["collapsed"]);
  });

  it("shows other changed fields and retains conservative handling for missing evidence and other tables", () => {
    const mixed = browse("device_st", ["dev_addr", "description"]);
    expect(mixed.rows.map((row) => row.kind)).toEqual(["modified-before", "modified-after"]);
    expect(mixed.rows.map((row) => row.changedColumns)).toEqual([["description"], ["description"]]);
    expect(deriveChangeLocations(mixed.scoped)).toHaveLength(1);
    for (const columns of [undefined, []]) expect(browse("device_st", columns).rows[0]?.kind).toBe("modified-before");
    for (const name of ["device", "device_cfg", "composite_signal_point"]) {
      expect(browse(name, ["dev_addr"]).rows.map((row) => row.kind)).toEqual(["modified-before", "modified-after"]);
    }
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
  const exactFacts: NavigationFacts = { basis: "EXACT", change_kind: "UPDATED", risk_level: null, risk_complete: true, before_row_count: 1, current_row_count: 1,
    table_scope: null, membership_changed: false, membership_complete: true, membership_initial_baseline: false, row_changes: { added: 0, deleted: 0, modified: 1, moved_in: 0, moved_out: 0 } };
  const exact = { facts: exactFacts };
  const fallback = { facts: { ...exactFacts, basis: "TABLE_FALLBACK" as const, change_kind: null, row_changes: null } };
  const riskIncomplete = { facts: { ...exactFacts, risk_complete: false, risk_level: "MEDIUM_HIGH" as const } };

  it("allows reuse only for EXACT, fully counted tables without a before snapshot", () => {
    expect(canReuseUnrecordedIdentity(table(), [exact], false, true)).toBe(true);
    expect(canReuseUnrecordedIdentity(table(), [exact], true, true)).toBe(false);
    expect(canReuseUnrecordedIdentity(table(), [exact], false, false)).toBe(false);
    expect(canReuseUnrecordedIdentity(table(), [], false, true)).toBe(false);
    expect(canReuseUnrecordedIdentity(table(), [fallback], false, true)).toBe(false);
    expect(canReuseUnrecordedIdentity(table(), [exact, fallback], false, true)).toBe(false);
    // Incomplete risk is not incomplete change: the identity reuse still holds.
    expect(canReuseUnrecordedIdentity(table(), [riskIncomplete, exact], false, true)).toBe(true);
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

  it("rebuilds a modified row's before side from the record and keeps the context for identity only", () => {
    const locator = parseRowLocator([locatorRow(0x11, null, 0, { before: { gid: 8 } })]);
    const result = buildBrowseRows({
      table: table({ row_change_stats: { row_count_before: 3, row_count_current: 3 } }),
      beforeRows: [], currentRows: [rowsCurrent[0]!],
      records: [record("ROW_MODIFIED", 0x11, { changed_columns: ["gid"], before_values: [{ column_name: "gid", value: { kind: "int", text: "8" } }] })],
      annotations: [], locator, hasBeforeSnapshot: false,
    });
    const before = result.rows.find((row) => row.kind === "modified-before");
    expect(before?.rowNumberTitle).toMatch(/^改前快照不在本 bundle 中/);
    expect(before?.values.gid).toEqual({ kind: "int", text: "8" });
    expect(before?.identityContext).toEqual({ gid: 8 });
    // Columns the record does not list as changed are equal on both sides.
    expect(before?.values.description).toBe("一改");
  });

  // Deleted rows without a before snapshot show record.before_values; the context only identifies them.
  const DELETED_VALUE_CASES: Array<[string, Record<string, unknown> | undefined, Record<string, unknown>[] | undefined, RegExp | Record<string, unknown>]> = [
    ["full before values with SQL NULL", { dev_addr: 49 }, [{ column_name: "dev_addr", value: { kind: "int", text: "49" } }, { column_name: "description", value: { kind: "null" } }],
      { dev_addr: { kind: "int", text: "49" }, description: { kind: "null" } }],
    ["a context that contradicts the record", { dev_addr: 50 }, [{ column_name: "dev_addr", value: { kind: "int", text: "49" } }], /与记录值矛盾/],
    ["a NULL context against a value", { dev_addr: null }, [{ column_name: "dev_addr", value: { kind: "int", text: "49" } }], /与记录值矛盾/],
    ["context only, no record values", { dev_addr: 49 }, undefined, {}],
  ];
  it.each(DELETED_VALUE_CASES)("deleted row without a before snapshot: %s", (_name, context, beforeValues, expected) => {
    const locator = parseRowLocator([locatorRow(0x33, null, null, { before: context })]);
    const build = () => buildBrowseRows({
      table: table({ row_change_stats: { row_count_before: 1, row_count_current: 0, row_deleted_count: 1 } }),
      beforeRows: [], currentRows: [], records: [record("ROW_DELETED", 0x33, beforeValues ? { before_values: beforeValues } : {})],
      annotations: [], locator, hasBeforeSnapshot: false, hasCurrentSnapshot: false,
    });
    if (expected instanceof RegExp) { expect(build).toThrow(expected); return; }
    const deleted = build().rows.find((row) => row.kind === "deleted");
    expect(deleted?.values).toEqual(expected);
    expect(deleted?.partialValues).toBe(true);
    expect(deleted?.identityContext).toEqual(context);
    expect(deleted?.rowNumberTitle).toBe(beforeValues ? "改前快照不在本 bundle 中：显示删除记录中的改前值" : "改前值不可得");
  });

  it("matches a deleted row to a device filter by its typed context, not by guessed snapshot types", () => {
    const locator = parseRowLocator([locatorRow(0x33, null, null, { before: { dev_addr: 49 } })]);
    const browse = (values: Array<number>) => buildBrowseRows({
      table: table({ row_change_stats: { row_count_before: 1, row_count_current: 0, row_deleted_count: 1 } }),
      beforeRows: [], currentRows: [], records: [record("ROW_DELETED", 0x33, { before_values: [{ column_name: "dev_addr", value: { kind: "int", text: "49" } }] })],
      annotations: [], locator, hasBeforeSnapshot: false, hasCurrentSnapshot: false,
      rowFilter: { before: { column: "dev_addr", values }, current: null }, beforeEncodings: new Map(), currentEncodings: browseEncodings(),
    }).rows.length;
    expect(browse([49])).toBe(1);
    expect(browse([50])).toBe(0);
    const stringContext = parseRowLocator([locatorRow(0x33, null, null, { before: { dev_addr: "49" } })]);
    expect(() => buildBrowseRows({
      table: table(), beforeRows: [], currentRows: [], records: [record("ROW_DELETED", 0x33)], annotations: [], locator: stringContext,
      hasBeforeSnapshot: false, hasCurrentSnapshot: false, rowFilter: { before: { column: "dev_addr", values: [49] }, current: null },
    })).toThrow(/上下文值类型与谓词矛盾/);
  });

  it("marks swapped ordered rows by their position when no row locator is published", () => {
    const current = [1, 4, 3, 2].map((n, index) => ({ dev_addr: n, description: `点${n}`, no: String(index + 1) }));
    const moved = (byte: number, from: number, to: number) => record("ORDERED_ROW_MOVED", byte, { semantic_kind: "MOVE", before_position: from, current_position: to, changed_columns: [] });
    const result = buildBrowseRows({
      table: table({ ordered_extension: {}, row_change_stats: { row_count_before: 4, row_count_current: 4 } }),
      beforeRows: [], currentRows: current, hasBeforeSnapshot: false,
      records: [moved(0x02, 2, 4), moved(0x04, 4, 2)], annotations: [], locator: new Map(),
    });
    expect(result.rows.map((row) => `${row.kind}:${row.beforePosition ?? ""}>${row.currentPosition ?? ""}`))
      .toEqual(["unchanged:>", "ordered:4>2", "unchanged:>", "ordered:2>4"]);
  });

  it("keeps a modified and moved row as one pair carrying the move", () => {
    const current = [1, 4, 3, 2].map((n, index) => ({ dev_addr: n, description: n === 2 ? "改名" : `点${n}`, no: String(index + 1) }));
    const ordered = (kind: string, byte: number, from: number, to: number, extras: Record<string, unknown> = {}) =>
      record(kind, byte, { before_position: from, current_position: to, changed_columns: [], ...extras });
    const records = [ordered("ORDERED_ROW_MOVED", 0x02, 2, 4), ordered("ORDERED_ROW_MODIFIED", 0x02, 2, 4,
      { changed_columns: ["description"], before_values: [{ column_name: "description", value: { kind: "string", text: "点2" } }] }),
      ordered("ORDERED_ROW_MOVED", 0x04, 4, 2)];
    const result = buildBrowseRows({
      table: table({ ordered_extension: {}, row_change_stats: { row_count_before: 4, row_count_current: 4 } }),
      beforeRows: [], currentRows: current, hasBeforeSnapshot: false, locator: new Map(), annotations: [], records,
    });
    expect(result.rows.map((row) => `${row.kind}:${row.rowNumber}:${rowMove(row)?.from ?? ""}>${rowMove(row)?.to ?? ""}`))
      .toEqual(["unchanged:1:>", "ordered:2:4>2", "unchanged:3:>", "modified-before:2:2>4", "modified-after:4:2>4"]);
    // The jump list counts that row once, in grid order.
    expect(deriveChangeLocations(result.scoped).map((location) => location.position)).toEqual([2, 4]);
  });

  const blankRecord = (kind: string, interval: Record<string, number | null>) => ({ table_name: "device", record_kind: kind, interval }) as RowDiffRecord;
  const intervalRisk = (side: "CURRENT" | "BEFORE", start: number, end: number, count: number, level: RiskAnnotation["risk_level"]): RiskAnnotation => ({
    annotation_id: side + start, risk_level: level, diagnostics: [],
    reasons: [{ reason_code: "ORDERED_MIDDLE_BLANK_INTERVAL", message: "", rule_id: "ORDERED_MIDDLE_BLANK_INTERVAL", evidence: [["count", count], ["side", side]] }],
    target: { target_type: "ROW_INTERVAL", table_name: "device", row_identity: null, before_row_identity: null, current_row_identity: null,
      changed_columns: [], coverage: null, position: null, position_range: [start, end] },
  });

  it("summarises each blank interval once and never invents per-position blank rows", () => {
    // Before: 1 2 _ _ 5 _ _ 8. Insert two blanks after 1 and shrink the 6-7 run to one blank.
    const current = ["1", "", "", "2", "", "", "5", "", "8"].map((label, index) => ({ dev_addr: label, description: label || "空点", no: String(index + 1) }));
    const result = buildBrowseRows({
      table: table({ ordered_extension: {}, row_change_stats: { row_count_before: null, row_count_current: 9 } }),
      beforeRows: [], currentRows: current, hasBeforeSnapshot: false, locator: new Map(), annotations: [],
      records: [blankRecord("BLANK_INSERT_INTERVAL", { before_start: null, before_end: null, current_start: 2, current_end: 3, row_count: 2 }),
        blankRecord("BLANK_DELETE_INTERVAL", { before_start: 6, before_end: 7, current_start: 8, current_end: 8, row_count: 1 })],
    });
    expect(result.rows.map((row) => row.kind === "blank-interval" ? `[${row.interval?.direction}]` : `${row.kind}:${row.rowNumber}`))
      .toEqual(["unchanged:1", "[INSERT]", "unchanged:2", "unchanged:3", "unchanged:4", "unchanged:5", "unchanged:6", "unchanged:7", "[DELETE]", "unchanged:8", "unchanged:9"]);
    const summaries = result.rows.filter((row) => row.kind === "blank-interval");
    expect(summaries.map((row) => row.rowNumber)).toEqual([null, null]);
    expect(summaries.map((row) => blankIntervalLabel(row.interval!))).toEqual([
      "+ 新增",
      "− 删除",
    ]);
    // Summaries are changes to jump to, but no business row is counted as added or deleted.
    expect(deriveChangeLocations(result.scoped).map((location) => [location.recordKind, location.position]))
      .toEqual([["BLANK_INSERT_INTERVAL", 1.5], ["BLANK_DELETE_INTERVAL", 7.5]]);
    expect(result.rows.some((row) => row.kind === "added" || row.kind === "deleted")).toBe(false);
  });

  it("keeps a range wider than the occupancy change as one region and its interval risk on the summary only", () => {
    // Current 1..6: a sparse gap whose blank region 2..5 also spans a real new point at 4; net change is 1.
    const current = [1, 2, 3, 4, 5, 6].map((no) => ({ dev_addr: no === 4 ? 40 : no, description: no === 4 ? "新点" : no === 2 || no === 5 ? "" : `点${no}`, no: String(no) }));
    const added = record("ORDERED_ROW_ADDED", 0x40, { current_position: 4 });
    const pointRisk: RiskAnnotation = { ...intervalRisk("CURRENT", 0, 0, 0, "LOW"), annotation_id: "point", reasons: [{ reason_code: "ORDERED_MIDDLE_INSERT_DELETE", message: "", rule_id: "ORDERED_MIDDLE_INSERT_DELETE", evidence: [] }],
      target: { ...intervalRisk("CURRENT", 0, 0, 0, "LOW").target, target_type: "ROW", row_identity: `sha256:${"40".repeat(32)}`, position_range: null, position: 4 } };
    const annotations = [intervalRisk("CURRENT", 2, 5, 1, "MEDIUM_HIGH"), pointRisk];
    const result = buildBrowseRows({
      table: table({ ordered_extension: {}, row_change_stats: { row_count_before: null, row_count_current: 6 } }),
      beforeRows: [], currentRows: current, hasBeforeSnapshot: false, locator: new Map(), annotations,
      records: [blankRecord("BLANK_INSERT_INTERVAL", { before_start: 2, before_end: 3, current_start: 2, current_end: 5, row_count: 1 }), added],
    });
    const summary = result.rows.find((row) => row.kind === "blank-interval")!;
    expect(summary.interval).toEqual({ direction: "INSERT", before: [2, 3], current: [2, 5], rowCount: 1 });
    expect(summary.riskLevel).toBe("MEDIUM_HIGH");
    expect(rowRiskAnnotation(summary, annotations)?.annotation_id).toBe("CURRENT2");
    // The real new point keeps its own ROW risk; nothing else in the region is painted.
    expect(result.rows.find((row) => row.kind === "added")?.riskLevel).toBe("LOW");
    expect(result.rows.filter((row) => row.kind === "unchanged" && row.riskLevel !== null)).toEqual([]);
    expect(result.rows.filter((row) => row.kind === "added")).toHaveLength(1);
    // A device filter never claims the ordered summary, while search finds it by its description.
    const searched = buildBrowseRows({
      table: table({ ordered_extension: {}, row_change_stats: { row_count_before: null, row_count_current: 6 } }),
      beforeRows: [], currentRows: current, hasBeforeSnapshot: false, locator: new Map(), annotations,
      records: [blankRecord("BLANK_INSERT_INTERVAL", { before_start: 2, before_end: 3, current_start: 2, current_end: 5, row_count: 1 })], search: "新增",
    });
    expect(searched.rows.map((row) => row.kind)).toEqual(["blank-interval"]);
  });

  it("places a blank summary at the nearest real row by business no, on the same ruler as the navigator", () => {
    // Sparse business no: 10, 15 (a real blank), 20, 30. Physical positions are 1..4.
    const current = [10, 15, 20, 30].map((no) => ({ dev_addr: no, description: no === 15 ? "" : `点${no}`, no: String(no) }));
    const records = [blankRecord("BLANK_INSERT_INTERVAL", { before_start: null, before_end: null, current_start: 15, current_end: 15, row_count: 1 }),
      record("ORDERED_ROW_ADDED", 0x30, { current_position: 30 })];
    const result = buildBrowseRows({
      table: table({ ordered_extension: {}, row_change_stats: { row_count_before: null, row_count_current: 4 } }),
      beforeRows: [], currentRows: current, hasBeforeSnapshot: false, locator: new Map(), annotations: [], records,
    });
    expect(result.rows.map((row) => row.kind === "blank-interval" ? "[blank]" : String(row.values.no))).toEqual(["10", "[blank]", "15", "20", "30"]);
    expect(result.rows.map((row) => row.ruler)).toEqual([1, 1.5, 2, 3, 4]);
    // The navigator uses the ruler, not business no (30 would fall off a 4-row table).
    expect(deriveChangeLocations(result.scoped).map((location) => [location.recordKind, location.position]))
      .toEqual([["BLANK_INSERT_INTERVAL", 1.5], ["ORDERED_ROW_ADDED", 4]]);
    // A gap beyond the last real row goes after it.
    const tail = buildBrowseRows({
      table: table({ ordered_extension: {}, row_change_stats: { row_count_before: null, row_count_current: 4 } }),
      beforeRows: [], currentRows: current, hasBeforeSnapshot: false, locator: new Map(), annotations: [],
      records: [blankRecord("BLANK_DELETE_INTERVAL", { before_start: 40, before_end: 41, current_start: null, current_end: null, row_count: 2 })],
    });
    expect(tail.rows.at(-1)?.kind).toBe("blank-interval");
    expect(tail.rows.at(-1)?.ruler).toBe(4.5);
  });

  it("rejects a blank interval without the changed side's range", () => {
    expect(() => buildBrowseRows({
      table: table({ ordered_extension: {} }), beforeRows: [], currentRows: [{ no: "1" }], hasBeforeSnapshot: false, locator: new Map(), annotations: [],
      records: [blankRecord("BLANK_DELETE_INTERVAL", { before_start: null, before_end: null, current_start: 1, current_end: 1, row_count: 1 })],
    })).toThrow(/变化侧范围/);
  });

  it("shows a FLOAT column's bit pattern as its number", () => {
    expect(formatFloatBits("3f800000")).toBe("1");
    expect(formatFloatBits("3ba3d70a")).toBe("0.005");
    expect(formatFloatBits("00000000")).toBe("0");
    expect(formatFloatBits("3ff0000000000000")).toBe("1");
    expect(formatFloatBits("7f800000")).toBeNull();
    const column = { name: "k", display_name: "系数", scalar_type: "FLOAT", nullable: true, present_in: "BOTH", display_order: 0, pinned: false } as const;
    expect(normalizeDisplayScalar("3f800000", column)).toBe("1");
    expect(normalizeDisplayScalar("3f800000")).toBe("3f800000");
    expect(normalizeDisplayScalar({ kind: "float32", text: "3f800000" })).toBe("1");
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

  it("keeps a deleted block ahead of its added block in the grouped layout", () => {
    const before = [1, 2, 3, 4].map((n) => ({ dev_addr: n, description: `旧${n}` }));
    const current = [1, 21, 31, 4].map((n) => ({ dev_addr: n, description: `新${n}` }));
    const locator = parseRowLocator([locatorRow(0x12, 1, null), locatorRow(0x13, 2, null), locatorRow(0x21, null, 1), locatorRow(0x31, null, 2)]);
    const result = buildBrowseRows({
      table: table(), beforeRows: before, currentRows: current, deletionLayout: "group",
      records: [record("ROW_DELETED", 0x12), record("ROW_DELETED", 0x13), record("ROW_ADDED", 0x21), record("ROW_ADDED", 0x31)],
      annotations: [], locator,
    });
    expect(result.rows.map((row) => `${row.kind === "deleted" ? "-" : row.kind === "added" ? "+" : " "}${row.rowNumber}`))
      .toEqual([" 1", "-2", "-3", "+2", "+3", " 4"]);
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

  const INSERTED_ROW_SHAPES: Array<[string, RowDiffRecord[], Array<Record<string, unknown>>]> = [
    ["an ordinary row", [record("ROW_ADDED", 0x0b)], [locatorRow(0x0b, null, 1)]],
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

  const no = (value: number) => [{ column_name: "no", value: { kind: "unsigned-integer", text: String(value) } }];
  const DELETED_ROW_SHAPES: Array<[string, RowDiffRecord[], Array<Record<string, unknown>>]> = [
    ["an ordinary row", [record("ROW_DELETED", 0x02, { before_values: no(2) })], [locatorRow(0x02, null, null)]],
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

describe("grid column headers", () => {
  it("show the raw field name in Debug and the COMMENT otherwise", () => {
    const column = { name: "dev_addr", display_name: "装置地址" };
    expect(columnHeaderTitle(column, true)).toBe("dev_addr");
    expect(columnHeaderTitle(column, false)).toBe("装置地址");
    expect(columnHeaderTitle({ name: "no_comment", display_name: "" }, false)).toBe("no_comment");
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
