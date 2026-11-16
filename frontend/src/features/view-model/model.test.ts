import { describe, expect, it } from "vitest";
import {
  decodeBusinessNavigation,
  deriveBundleView,
  deriveFormulaDisplays,
  navigationTabHasDifferences,
  tabScope,
  type NavigationFacts,
  type NavigationGroup,
  type RiskLevel,
  type BusinessNavigation,
  type ComparisonSurface,
  type RiskReport,
  type RiskTableReport,
  type SurfaceColumn,
  type SurfaceTable,
} from "./model";

function column(name: string, order: number, present: SurfaceColumn["present_in"] = "BOTH"): SurfaceColumn {
  return { name, display_name: name.toUpperCase(), scalar_type: "VARCHAR(64)", nullable: true, pinned: order === 0, present_in: present, display_order: order };
}

function surfaceTable(name: string, overrides: Partial<SurfaceTable> = {}): SurfaceTable {
  return {
    table_id: name,
    table_name: name,
    display_name: name + "表",
    table_status: "MODIFIED",
    change_kind: "UPDATED",
    columns: [column("dev_addr", 0), column("description", 1)],
    row_change_stats: { row_count_before: 3, row_count_current: 3, row_added_count: 0, row_deleted_count: 0, row_modified_count: 1 },
    records_refs: { records_format: "PARQUET" },
    table_refs: { before_table_ref: null, current_table_ref: null },
    table_content_bindings: { before: null, current: null, browse: null },
    ...overrides,
  } as SurfaceTable;
}

function surface(tables: SurfaceTable[] = [surfaceTable("device"), surfaceTable("device_ext")]): ComparisonSurface {
  return { surface_contract_version: "backend-vnext/comparison-surface/v4", comparison_mode: "VERSION_COMPARE", view: {}, tables } as unknown as ComparisonSurface;
}

const exactFacts: NavigationFacts = {
  basis: "EXACT", change_kind: "UPDATED", risk_level: "MEDIUM_LOW", risk_complete: true, before_row_count: 3, current_row_count: 3,
  table_scope: null, membership_changed: false, membership_complete: true, row_changes: { added: 0, deleted: 0, modified: 1, moved_in: 0, moved_out: 0 },
};

const GROUP_KEYS = ["FORWARD_CHANNELS", "SECONDARY_DEVICES", "COMMUNICATION_PROTOCOLS", "GLOBAL_PARAMETERS", "OTHER_TABLES"] as const;

/** An ordinary v4 navigation: five fixed groups; the device item lives in SECONDARY_DEVICES. */
function navigation(overrides: Partial<BusinessNavigation> = {}): BusinessNavigation {
  const groups: NavigationGroup[] = GROUP_KEYS.map((group_key) => ({ group_key, label: group_key, items: [], nonempty_item_count: 0 }));
  groups[1] = { nonempty_item_count: 1, group_key: "SECONDARY_DEVICES", label: "二次装置列表", items: [{
    summary: { change_kinds: ["UPDATED"], risk_level: "MEDIUM_LOW", nonempty_tab_count: 2, change_complete: true, risk_complete: true },
    item_key: "device:addr:1", item_kind: "DEVICE", label: "装置一", attributes: { dev_addr: 1 }, tabs: [
      { empty: false, tab_key: "first", label: "一", table_id: "device", row_filter: { before: { column: "dev_addr", values: [1] }, current: null }, facts: { ...exactFacts } },
      { empty: false, tab_key: "second", label: "二", table_id: "device", row_filter: { before: null, current: { column: "dev_addr", values: [2] } }, facts: { ...exactFacts } },
    ],
  }] };
  return { contract_version: "backend-vnext/business-navigation/v4", groups, replacement_sides: null, table_notices: [], device_definition_changes: [], ...overrides };
}

const deviceItem = (doc: BusinessNavigation) => doc.groups[1]!.items[0]!;

function riskReport(tables: RiskTableReport[]): RiskReport {
  const riskLevel = tables[0]?.risk_level ?? null;
  return {
    risk_report_contract_version: "backend-vnext/risk-report/v1",
    risk_evaluation_digest: `sha256:${"0".repeat(64)}`,
    overall: { risk_level: riskLevel, reason_codes: riskLevel ? ["ROW_ADDED"] : [], table_count: tables.length, annotation_count: tables.reduce((total, table) => total + table.annotation_count, 0) },
    tables,
    annotation_refs: [],
    diagnostics: [],
  };
}

function tableRisk(tableName: string, riskLevel: RiskTableReport["risk_level"], annotationCount: number): RiskTableReport {
  return { table_name: tableName, risk_level: riskLevel, reason_codes: ["ROW_ADDED"], annotation_count: annotationCount, source_table_status: "MODIFIED", annotation_ref: null, diagnostics: [] };
}

describe("business navigation decoding", () => {
  it("rejects an unsupported contract version, a v3 payload and a missing navigation", () => {
    expect(() => decodeBusinessNavigation(null, surface())).toThrow(/字段无效/);
    expect(() => decodeBusinessNavigation({ ...navigation(), contract_version: "backend-vnext/business-navigation/v3" }, surface())).toThrow(/不支持的 business navigation contract version/);
    const v3Shape = { ...navigation(), contract_version: "backend-vnext/business-navigation/v3" } as Record<string, unknown>;
    delete v3Shape.table_notices;
    delete v3Shape.device_definition_changes;
    expect(() => decodeBusinessNavigation(v3Shape, surface())).toThrow(/字段无效/);
  });

  it("accepts a complete v4 document", () => {
    expect(decodeBusinessNavigation(navigation(), surface()).groups).toHaveLength(5);
  });

  it("rejects duplicate keys, unpublished tables and whole-table/filter mixtures", () => {
    const duplicateTabs = navigation();
    deviceItem(duplicateTabs).tabs.push({ ...deviceItem(duplicateTabs).tabs[0]! });
    deviceItem(duplicateTabs).summary.nonempty_tab_count = 3;
    expect(() => decodeBusinessNavigation(duplicateTabs, surface())).toThrow(/tab_key 重复/);
    const unpublished = navigation();
    deviceItem(unpublished).tabs[0]!.table_id = "missing";
    expect(() => decodeBusinessNavigation(unpublished, surface())).toThrow(/未发布的表/);
    const mixed = navigation();
    deviceItem(mixed).tabs.push({ empty: false, tab_key: "whole", label: "整表", table_id: "device", row_filter: null, facts: null });
    deviceItem(mixed).summary.nonempty_tab_count = 3;
    expect(() => decodeBusinessNavigation(mixed, surface())).toThrow(/整表页签/);
    const wholeWithFacts = navigation();
    deviceItem(wholeWithFacts).tabs = [{ empty: false, tab_key: "whole", label: "整表", table_id: "device_ext", row_filter: null, facts: { ...exactFacts } }];
    deviceItem(wholeWithFacts).summary.nonempty_tab_count = 1;
    expect(() => decodeBusinessNavigation(wholeWithFacts, surface())).toThrow(/不能带局部 facts/);
  });

  it("requires the five ordinary groups in order", () => {
    const missing = navigation();
    missing.groups.pop();
    expect(() => decodeBusinessNavigation(missing, surface())).toThrow(/五个分组/);
    const swapped = navigation();
    [swapped.groups[0], swapped.groups[1]] = [swapped.groups[1]!, swapped.groups[0]!];
    expect(() => decodeBusinessNavigation(swapped, surface())).toThrow(/分组顺序/);
  });

  it("keeps filter tabs of one table in a single group with one basis and one table scope", () => {
    const crossGroup = navigation();
    crossGroup.groups[4] = { nonempty_item_count: 1, group_key: "OTHER_TABLES", label: "其他表", items: [{ summary: { change_kinds: ["UPDATED"], risk_level: "MEDIUM_LOW", nonempty_tab_count: 1, change_complete: true, risk_complete: true }, item_key: "other", item_kind: "TABLE", label: "其他", attributes: {}, tabs: [
      { empty: false, tab_key: "third", label: "三", table_id: "device", row_filter: { before: null, current: { column: "dev_addr", values: [3] } }, facts: { ...exactFacts } },
    ] }] };
    expect(() => decodeBusinessNavigation(crossGroup, surface())).toThrow(/不在同一分组/);
    const mixedBasis = navigation();
    deviceItem(mixedBasis).tabs[1]!.facts = { ...exactFacts, basis: "TABLE_FALLBACK", change_kind: null, row_changes: null };
    deviceItem(mixedBasis).summary.change_complete = false;
    expect(() => decodeBusinessNavigation(mixedBasis, surface())).toThrow(/facts.basis 不一致/);
  });

  it("requires sorted, deduplicated, single-type predicate values", () => {
    const unsorted = navigation();
    deviceItem(unsorted).tabs[0]!.row_filter = { before: { column: "dev_addr", values: [3, 1] }, current: null };
    expect(() => decodeBusinessNavigation(unsorted, surface())).toThrow(/未按规范排序/);
    const mixedTypes = navigation();
    deviceItem(mixedTypes).tabs[0]!.row_filter = { before: { column: "dev_addr", values: [1, "2"] }, current: null };
    expect(() => decodeBusinessNavigation(mixedTypes, surface())).toThrow(/类型不一致/);
  });

  it("decodes replacement sides and requires them exactly for DATASET_REPLACEMENT", () => {
    const replacementSurface = surface([surfaceTable("device")]);
    (replacementSurface as unknown as { comparison_mode: string }).comparison_mode = "DATASET_REPLACEMENT";
    expect(() => decodeBusinessNavigation(navigation(), replacementSurface)).toThrow(/replacement_sides/);
    const replacement = decodeBusinessNavigation(sameKeyReplacement(["device"]), replacementSurface);
    const view = deriveBundleView({ surface: replacementSurface, navigation: replacement });
    expect(view.replacementSides?.before[1]?.items[0]?.label).toBe("同一装置");
    // Replacement navigation keeps `groups` empty in the artifact, but the sidebar
    // merges both sides into one selectable tree keyed by group and item.
    expect(view.groups.map((group) => group.groupKey)).toEqual([...GROUP_KEYS]);
    expect(view.tableNotices).toEqual([]);
    expect(view.deviceDefinitionChanges).toEqual([]);
    const withNotices = { ...sameKeyReplacement(["device"]), table_notices: [{ table_id: "device", table_scope: { change: true, risk_level: null }, unlocated_row_risk: null, risk_complete: true }] };
    expect(() => decodeBusinessNavigation(withNotices, replacementSurface)).toThrow(/table_notices 必须为空/);
  });
});

/** Same-shape v4 faults whose only difference is the payload and the expected rejection. */
const INVALID_NAVIGATION_SHAPES: Array<[string, (doc: BusinessNavigation) => void, RegExp]> = [
  ["missing empty", (doc) => { Reflect.deleteProperty(deviceItem(doc).tabs[0]!, "empty"); }, /字段无效/],
  ["string empty", (doc) => { Object.assign(deviceItem(doc).tabs[0]!, { empty: "false" }); }, /empty 无效/],
  ["unknown root field", (doc) => { Object.assign(doc, { future: [] }); }, /字段无效/],
  ["unknown facts field", (doc) => { Object.assign(deviceItem(doc).tabs[0]!.facts!, { extra: true }); }, /facts 字段无效/],
  ["missing risk_complete", (doc) => { Reflect.deleteProperty(deviceItem(doc).tabs[0]!.facts!, "risk_complete"); }, /facts 字段无效/],
  ["missing membership flag", (doc) => { Reflect.deleteProperty(deviceItem(doc).tabs[0]!.facts!, "membership_changed"); }, /facts 字段无效/],
  ["summary extra", (doc) => { Object.assign(deviceItem(doc).summary, { extra: true }); }, /summary 字段无效/],
  ["summary missing change_complete", (doc) => { Reflect.deleteProperty(deviceItem(doc).summary, "change_complete"); }, /summary 字段无效/],
  ["unknown risk", (doc) => { Object.assign(deviceItem(doc).summary, { risk_level: "FUTURE" }); }, /风险等级无效/],
  ["wrong tab count", (doc) => { deviceItem(doc).summary.nonempty_tab_count = 0; }, /nonempty_tab_count/],
  ["string group count", (doc) => { Object.assign(doc.groups[1]!, { nonempty_item_count: "1" }); }, /nonempty_item_count/],
  ["fallback with a change kind", (doc) => { deviceItem(doc).tabs.forEach((tab) => { tab.facts = { ...exactFacts, basis: "TABLE_FALLBACK", row_changes: null }; }); }, /TABLE_FALLBACK/],
  ["exact without row changes", (doc) => { deviceItem(doc).tabs[0]!.facts!.row_changes = null; }, /EXACT/],
  ["moved_in beyond modified", (doc) => { deviceItem(doc).tabs[0]!.facts!.row_changes = { added: 0, deleted: 0, modified: 1, moved_in: 2, moved_out: 0 }; }, /迁移数超过/],
  ["empty table scope", (doc) => { deviceItem(doc).tabs.forEach((tab) => { tab.facts!.table_scope = { change: false, risk_level: null }; }); }, /table_scope 必须为 null/],
  ["summary risk differs from tabs", (doc) => { deviceItem(doc).summary.risk_level = "HIGH"; }, /summary.risk_level 与页签/],
  ["summary kinds differ from tabs", (doc) => { deviceItem(doc).summary.change_kinds = ["ADDED"]; }, /summary.change_kinds 与页签/],
  ["summary risk_complete differs from tabs", (doc) => { deviceItem(doc).summary.risk_complete = false; }, /summary.risk_complete/],
  ["summary change_complete ignores membership", (doc) => { deviceItem(doc).tabs[0]!.facts!.membership_complete = false; }, /summary.change_complete/],
  ["risk incomplete without public notice", (doc) => { deviceItem(doc).tabs.forEach((tab) => { tab.facts!.risk_complete = false; }); deviceItem(doc).summary.risk_complete = false; }, /缺少公共提示/],
  ["notice for a table outside navigation", (doc) => { doc.table_notices = [{ table_id: "device_ext", table_scope: null, unlocated_row_risk: null, risk_complete: false }]; }, /不存在的表/],
  ["empty notice", (doc) => { doc.table_notices = [{ table_id: "device", table_scope: null, unlocated_row_risk: null, risk_complete: true }]; }, /空提示/],
  ["notice scope differs from facts", (doc) => { doc.table_notices = [{ table_id: "device", table_scope: { change: true, risk_level: null }, unlocated_row_risk: null, risk_complete: true }]; }, /table_scope 与页签/],
  ["notice risk_complete differs from facts", (doc) => { doc.table_notices = [{ table_id: "device", table_scope: null, unlocated_row_risk: { risk_level: null, count: null, reason_codes: [] }, risk_complete: false }]; }, /risk_complete 与页签/],
  ["unsorted notice reasons", (doc) => { doc.table_notices = [{ table_id: "device", table_scope: null, unlocated_row_risk: { risk_level: "LOW", count: null, reason_codes: ["ROW_MODIFIED", "ROW_ADDED"] }, risk_complete: true }]; }, /去重排序/],
  ["definition change on a missing item", (doc) => { doc.device_definition_changes = [{ record_identity: "sha256:aa", change_kind: "UPDATED", before_item_key: "device:addr:9", current_item_key: null, before_dev_addr: 9, current_dev_addr: null, risk_level: null, risk_complete: true }]; }, /不存在的项/],
  ["added definition with a before side", (doc) => { doc.device_definition_changes = [{ record_identity: "sha256:aa", change_kind: "ADDED", before_item_key: null, current_item_key: "device:addr:1", before_dev_addr: 1, current_dev_addr: 1, risk_level: null, risk_complete: true }]; }, /新增定义/],
  ["unsorted definition changes", (doc) => { const change = { change_kind: "UPDATED" as const, before_item_key: null, current_item_key: null, before_dev_addr: null, current_dev_addr: null, risk_level: null, risk_complete: true }; doc.device_definition_changes = [{ ...change, record_identity: "sha256:bb" }, { ...change, record_identity: "sha256:aa" }]; }, /record_identity 唯一排序/],
];

it.each(INVALID_NAVIGATION_SHAPES)("rejects v4 navigation: %s", (_name, mutate, pattern) => {
  const doc = navigation();
  mutate(doc);
  expect(() => decodeBusinessNavigation(doc, surface())).toThrow(pattern);
});

it("accepts EXACT local changes beside incomplete risk and a public notice", () => {
  const doc = navigation();
  deviceItem(doc).tabs.forEach((tab) => { tab.facts!.risk_complete = false; });
  deviceItem(doc).summary.risk_complete = false;
  doc.table_notices = [{ table_id: "device", table_scope: null, unlocated_row_risk: { risk_level: null, count: null, reason_codes: ["RISK_ANNOTATION_ARTIFACT_BUDGET_EXCEEDED"] }, risk_complete: false }];
  const view = deriveBundleView({ surface: surface(), navigation: decodeBusinessNavigation(doc, surface()) });
  const tab = view.groups[1]!.items[0]!.tabs[0]!;
  expect(tabScope(tab)).toMatchObject({ kind: "LOCAL_EXACT", changeKind: "UPDATED", riskLevel: "MEDIUM_LOW", riskComplete: false });
  expect(tab.notice?.risk_complete).toBe(false);
  expect(view.groups[1]!.items[0]!.riskComplete).toBe(false);
});

it("preserves backend empty markers and neutral all-empty summaries without deriving them from Surface", () => {
  const doc = navigation();
  const item = deviceItem(doc);
  item.tabs.forEach((tab) => { tab.empty = true; });
  item.summary = { change_kinds: [], risk_level: null, nonempty_tab_count: 0, change_complete: true, risk_complete: true };
  doc.groups[1]!.nonempty_item_count = 0;
  const view = deriveBundleView({ surface: surface(), navigation: decodeBusinessNavigation(doc, surface()) });
  expect(view.groups[1]!.nonemptyItemCount).toBe(0);
  expect(view.groups[1]!.items[0]!.tabs.every((tab) => tab.empty)).toBe(true);
  expect(view.groups[1]!.items[0]!.changeKinds).toEqual([]);
  expect(view.groups[1]!.items[0]!.riskLevels).toEqual([]);
  item.summary.risk_level = "HIGH";
  expect(() => decodeBusinessNavigation(doc, surface())).toThrow(/全空项/);
});

describe("bundle view derivation", () => {
  it("keeps whole-table results on the table and local facts on the tab", () => {
    const decoded = decodeBusinessNavigation(navigation(), surface());
    const result = deriveBundleView({ surface: surface(), navigation: decoded, riskReport: riskReport([tableRisk("device", "HIGH", 2)]) });
    expect(result.groups[1]?.items[0]?.showTabs).toBe(true);
    expect(result.groups[1]?.items[0]?.tabs[0]?.rowFilter).toEqual({ before: { column: "dev_addr", values: [1] }, current: null });
    expect(result.tables.find((table) => table.tableName === "device")?.riskLevel).toBe("HIGH");
    // The whole table's HIGH risk is not the device tab's own risk.
    expect(tabScope(result.groups[1]!.items[0]!.tabs[0]!).riskLevel).toBe("MEDIUM_LOW");
    expect(result.tables.find((table) => table.tableName === "device_ext")?.riskLevel).toBeNull();
  });

  it("orders columns by display_order and exposes the locator flag", () => {
    const scoped = surfaceTable("device", { row_locator_ref: { artifact_id: "a1:x:y", media_type: "application/vnd.apache.parquet", raw_sha256: `sha256:${"1".repeat(64)}`, size_bytes: 10 } });
    const result = deriveBundleView({ surface: surface([scoped]), navigation: decodeBusinessNavigation(navigation(), surface([scoped])) });
    expect(result.tables[0]!.columns.map((value) => value.display_order)).toEqual([0, 1]);
    expect(result.tables[0]!.hasRowLocator).toBe(true);
  });
});

const SCOPE_VISIBILITY_CASES: Array<[string, Partial<NavigationFacts>, boolean]> = [
  ["local changes", { change_kind: "UPDATED", risk_level: null }, true],
  ["local row risk", { change_kind: "UNCHANGED", risk_level: "LOW", row_changes: { added: 0, deleted: 0, modified: 0, moved_in: 0, moved_out: 0 } }, true],
  ["registry-only membership change", { change_kind: "UPDATED", risk_level: null, membership_changed: true, row_changes: { added: 0, deleted: 0, modified: 0, moved_in: 0, moved_out: 0 } }, true],
  ["unknown local change", { basis: "TABLE_FALLBACK", change_kind: null, risk_level: null, row_changes: null }, true],
  ["only a public table scope", { change_kind: "UNCHANGED", risk_level: null, table_scope: { change: true, risk_level: "HIGH" }, row_changes: { added: 0, deleted: 0, modified: 0, moved_in: 0, moved_out: 0 } }, false],
  ["unchanged rows", { change_kind: "UNCHANGED", risk_level: null, row_changes: { added: 0, deleted: 0, modified: 0, moved_in: 0, moved_out: 0 } }, false],
];

it.each(SCOPE_VISIBILITY_CASES)("difference filtering for %s", (_name, facts, expected) => {
  const tab = { rowFilter: { before: { column: "dev_addr", values: [1] }, current: null }, facts: { ...exactFacts, ...facts }, table: null, notice: null };
  expect(navigationTabHasDifferences(tab)).toBe(expected);
});

it("reads whole-table tabs from the table and never invents a local scope for them", () => {
  const table = { tableName: "device", label: "装置表", changeKind: "UPDATED", riskLevel: "HIGH" as RiskLevel, annotationCount: 1, columns: [], rowCounts: { before: 2, current: 3 }, hasRecords: true, hasRowLocator: false };
  expect(tabScope({ rowFilter: null, facts: null, table, notice: null })).toMatchObject({ kind: "WHOLE_TABLE", changeKind: "UPDATED", riskLevel: "HIGH", beforeCount: 2, currentCount: 3 });
});

function sameKeyReplacement(tables: string[] = ["device", "device_ext"]): BusinessNavigation {
  const groups = (items: NavigationGroup["items"]): NavigationGroup[] => GROUP_KEYS.map((group_key) => group_key === "SECONDARY_DEVICES"
    ? { group_key, label: "装置", nonempty_item_count: 1, items }
    : { group_key, label: group_key, nonempty_item_count: 0, items: [] });
  const tab = (table: string) => ({ empty: false, tab_key: table, label: table, table_id: table, row_filter: null, facts: null });
  return { contract_version: "backend-vnext/business-navigation/v4", groups: [], table_notices: [], device_definition_changes: [], replacement_sides: {
    before: groups([{ item_key: "same-device", item_kind: "DEVICE", label: "同一装置", attributes: {}, summary: { change_kinds: ["ADDED"], risk_level: "LOW", nonempty_tab_count: 1, change_complete: true, risk_complete: true }, tabs: [tab(tables[0]!)] }]),
    current: groups([{ item_key: "same-device", item_kind: "DEVICE", label: "同一装置", attributes: {}, summary: { change_kinds: ["DELETED"], risk_level: "HIGH", nonempty_tab_count: tables.length, change_complete: true, risk_complete: true }, tabs: tables.map(tab) }]),
  } };
}

it("merges published replacement summaries for the same item and deduplicates shared tables", () => {
  const replacementSurface = { ...surface(), comparison_mode: "DATASET_REPLACEMENT" } as ComparisonSurface;
  const view = deriveBundleView({ surface: replacementSurface, navigation: decodeBusinessNavigation(sameKeyReplacement(), replacementSurface) });
  const group = view.groups[1]!;
  expect(group.items).toHaveLength(1);
  expect(group.nonemptyItemCount).toBe(1);
  expect(group.items[0]!.tabs.map((tab) => tab.tableName)).toEqual(["device", "device_ext"]);
  expect(group.items[0]!.nonemptyTabCount).toBe(2);
  expect(group.items[0]!.changeKinds).toEqual(["ADDED", "DELETED"]);
  expect(group.items[0]!.riskLevels).toEqual(["HIGH", "LOW"]);
});

it.each(["before", "current"] as const)("rejects empty replacement tab on %s side", (side) => {
  const doc = sameKeyReplacement();
  doc.replacement_sides![side][1]!.items[0]!.tabs[0]!.empty = true;
  const replacementSurface = { ...surface(), comparison_mode: "DATASET_REPLACEMENT" } as ComparisonSurface;
  expect(() => decodeBusinessNavigation(doc, replacementSurface)).toThrow(/empty/);
});

describe("record and formula derivation", () => {
  it("shows the before and current formula during a changed Preview and both sides in History", () => {
    const beforeAst = { kind: "EXPRESS", operator: "+", children: [{ kind: "DIGITAL", value: "1" }, { kind: "POINT", name: "Device 1:温度" }] };
    const currentAst = { kind: "EXPRESS", operator: "+", children: [{ kind: "DIGITAL", value: "1" }, { kind: "POINT", name: "Device 1:温度" }, { kind: "DIGITAL", value: "3" }] };
    const before = [{ source_table: "composite_signal_point", point_gid: 8, dev_addr: 65532, formula_digest: "old", formula_ast_json: beforeAst }];
    const current = [{ source_table: "composite_signal_point", point_gid: 8, dev_addr: 65532, formula_digest: "new", formula_ast_json: currentAst }];
    const devices = [{ dev_addr: 65532, description: "复合信号装置" }];
    const preview = deriveFormulaDisplays({ mode: "PREVIEW", before, current, beforeDevices: devices, currentDevices: devices });
    expect(preview[0]).toMatchObject({ beforeFormula: beforeAst, currentFormula: currentAst, formulaChanged: true, label: "公式已改", beforeDeviceName: "复合信号装置", currentDeviceName: "复合信号装置" });
    const history = deriveFormulaDisplays({ mode: "HISTORY", before, current, beforeDevices: [{ dev_addr: 65532, description: "改前名称" }], currentDevices: devices });
    expect(history[0]).toMatchObject({ beforeFormula: beforeAst, currentFormula: currentAst, changed: true, formulaChanged: false, label: null, beforeDeviceName: "改前名称", currentDeviceName: "复合信号装置" });
    const deletedPreview = deriveFormulaDisplays({ mode: "PREVIEW", before, current: [], beforeDevices: devices, deletedPointKeys: new Set(["composite_signal_point:8"]) });
    expect(deletedPreview[0]).toMatchObject({ beforeFormula: beforeAst, currentFormula: beforeAst, deleted: true });
  });
});
