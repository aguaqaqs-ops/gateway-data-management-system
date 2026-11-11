import { describe, expect, it } from "vitest";
import { readLocalChangeRecords, readLocalRiskAnnotations, loadComparisonPresentation } from "../bundle/presentation";
import { installedGoldenBundle } from "../../test/helpers";
import {
  decodeBusinessNavigation,
  deriveBundleView,
  deriveChangeLocations,
  deriveFormulaDisplays,
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

const exactFacts = { basis: "EXACT" as const, change_kind: "MODIFIED" as const, risk_level: "MEDIUM_LOW" as const, before_row_count: 3, current_row_count: 3, table_scope: null };

function navigation(overrides: Partial<BusinessNavigation> = {}): BusinessNavigation {
  return {
    contract_version: "backend-vnext/business-navigation/v1",
    groups: [{ group_key: "FUTURE_GROUP", label: "扩展业务组", items: [{
      item_key: "future:one", item_kind: "FUTURE_ITEM", label: "扩展节点", tabs: [
        { tab_key: "first", label: "一", table_id: "device", row_filter: { before: { column: "dev_addr", values: [1] }, current: null }, facts: exactFacts },
        { tab_key: "second", label: "二", table_id: "device", row_filter: { before: null, current: { column: "dev_addr", values: [2] } }, facts: exactFacts },
      ],
    }] }],
    replacement_sides: null,
    ...overrides,
  };
}

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
  it("rejects an unsupported contract version and a missing navigation", () => {
    expect(() => decodeBusinessNavigation(null, surface())).toThrow(/不是对象|缺少/);
    expect(() => decodeBusinessNavigation({ ...navigation(), contract_version: "backend-vnext/business-navigation/v0" }, surface())).toThrow(/不支持的 business navigation contract version/);
  });

  it("rejects duplicate keys, unpublished tables and whole-table/filter mixtures", () => {
    const duplicateTabs = navigation();
    duplicateTabs.groups[0]!.items[0]!.tabs.push({ ...duplicateTabs.groups[0]!.items[0]!.tabs[0]! });
    expect(() => decodeBusinessNavigation(duplicateTabs, surface())).toThrow(/tab_key 重复/);
    const unpublished = navigation();
    unpublished.groups[0]!.items[0]!.tabs[0]!.table_id = "missing";
    expect(() => decodeBusinessNavigation(unpublished, surface())).toThrow(/未发布的表/);
    const noWholeTable = navigation();
    noWholeTable.groups[0]!.items[0]!.tabs.push({ tab_key: "third", label: "三", table_id: "device_ext", row_filter: null, facts: exactFacts });
    expect(decodeBusinessNavigation(noWholeTable, surface()).groups[0]!.items[0]!.tabs).toHaveLength(3);
    const mixed = navigation();
    mixed.groups[0]!.items[0]!.tabs.push({ tab_key: "whole", label: "整表", table_id: "device", row_filter: null, facts: exactFacts });
    expect(() => decodeBusinessNavigation(mixed, surface())).toThrow(/整表页签/);
  });

  it("keeps filter tabs of one table in a single group and with one basis", () => {
    const crossGroup = navigation();
    crossGroup.groups.push({ group_key: "OTHER_TABLES", label: "其他表", items: [{ item_key: "other", item_kind: "TABLE", label: "其他", tabs: [
      { tab_key: "third", label: "三", table_id: "device", row_filter: { before: null, current: { column: "dev_addr", values: [3] } }, facts: exactFacts },
    ] }] });
    expect(() => decodeBusinessNavigation(crossGroup, surface())).toThrow(/不在同一分组/);
    const mixedBasis = navigation();
    mixedBasis.groups[0]!.items[0]!.tabs[1]!.facts = { ...exactFacts, basis: "TABLE_FALLBACK" };
    expect(() => decodeBusinessNavigation(mixedBasis, surface())).toThrow(/facts.basis 不一致/);
  });

  it("requires sorted, deduplicated, single-type predicate values", () => {
    const unsorted = navigation();
    unsorted.groups[0]!.items[0]!.tabs[0]!.row_filter = { before: { column: "dev_addr", values: [3, 1] }, current: null };
    expect(() => decodeBusinessNavigation(unsorted, surface())).toThrow(/未按规范排序/);
    const mixedTypes = navigation();
    mixedTypes.groups[0]!.items[0]!.tabs[0]!.row_filter = { before: { column: "dev_addr", values: [1, "2"] }, current: null };
    expect(() => decodeBusinessNavigation(mixedTypes, surface())).toThrow(/类型不一致/);
  });

  it("decodes replacement sides and requires them exactly for DATASET_REPLACEMENT", () => {
    const replacementSurface = surface([surfaceTable("device")]);
    (replacementSurface as unknown as { comparison_mode: string }).comparison_mode = "DATASET_REPLACEMENT";
    expect(() => decodeBusinessNavigation(navigation(), replacementSurface)).toThrow(/replacement_sides/);
    const replacement = decodeBusinessNavigation({
      contract_version: "backend-vnext/business-navigation/v1",
      groups: [],
      replacement_sides: {
        before: [{ group_key: "FUTURE_GROUP", label: "改前", items: [{ item_key: "before:device", item_kind: "TABLE", label: "改前装置表", tabs: [{ tab_key: "before", label: "改前", table_id: "device", row_filter: null, facts: null }] }] }],
        current: [{ group_key: "FUTURE_GROUP", label: "改后", items: [{ item_key: "current:device", item_kind: "TABLE", label: "改后装置表", tabs: [{ tab_key: "current", label: "改后", table_id: "device", row_filter: null, facts: null }] }] }],
      },
    }, replacementSurface);
    const view = deriveBundleView({ surface: replacementSurface, navigation: replacement });
    expect(view.replacementSides?.before[0]?.label).toBe("改前");
    expect(view.replacementSides?.current[0]?.items[0]?.label).toBe("改后装置表");
    // Replacement navigation keeps `groups` empty in the artifact, but the sidebar
    // merges both sides into one selectable tree keyed by group and item.
    expect(view.groups).toHaveLength(1);
    expect(view.groups[0]?.groupKey).toBe("FUTURE_GROUP");
    expect(view.groups[0]?.items.map((item) => item.itemKey)).toEqual(["before:device", "current:device"]);
  });
});

describe("bundle view derivation", () => {
  it("renders backend groups without fixed slots and keeps unknown group keys", () => {
    const decoded = decodeBusinessNavigation(navigation(), surface());
    const result = deriveBundleView({ surface: surface(), navigation: decoded, riskReport: riskReport([tableRisk("device", "MEDIUM_LOW", 2)]) });
    expect(result.groups[0]?.groupKey).toBe("FUTURE_GROUP");
    expect(result.groups[0]?.items[0]?.showTabs).toBe(true);
    expect(result.groups[0]?.items[0]?.tabs[0]?.rowFilter).toEqual({ before: { column: "dev_addr", values: [1] }, current: null });
    expect(result.tables.find((table) => table.tableName === "device")?.riskLevel).toBe("MEDIUM_LOW");
    expect(result.tables.find((table) => table.tableName === "device_ext")?.riskLevel).toBeNull();
    expect(result.diagnostics).toEqual([]);
  });

  it("orders columns by display_order and exposes the locator flag and table scope", () => {
    const scoped = surfaceTable("device", { row_locator_ref: { artifact_id: "a1:x:y", media_type: "application/vnd.apache.parquet", raw_sha256: `sha256:${"1".repeat(64)}`, size_bytes: 10 } });
    const decoded = decodeBusinessNavigation(navigation(), surface([scoped]));
    const result = deriveBundleView({ surface: surface([scoped]), navigation: decoded });
    const table = result.tables[0]!;
    expect(table.columns.map((value) => value.display_order)).toEqual([0, 1]);
    expect(table.hasRowLocator).toBe(true);
    const wholeTable = navigation();
    wholeTable.groups[0]!.items[0]!.tabs = [{ tab_key: "whole", label: "整表", table_id: "device", row_filter: null, facts: { ...exactFacts, table_scope: { change: true, risk_level: "HIGH" } } }];
    const withScope = deriveBundleView({ surface: surface([scoped]), navigation: decodeBusinessNavigation(wholeTable, surface([scoped])) });
    expect(withScope.tables[0]?.tableScope).toEqual({ change: true, risk_level: "HIGH" });
  });

  it("summarizes filtered tabs from facts and ignores unknown risk tables", () => {
    const decoded = decodeBusinessNavigation(navigation(), surface());
    const result = deriveBundleView({ surface: surface(), navigation: decoded, riskReport: riskReport([]) });
    expect(result.groups[0]?.items[0]?.changeKinds).toEqual(["MODIFIED"]);
    expect(result.groups[0]?.items[0]?.riskLevels).toEqual(["MEDIUM_LOW"]);
    expect(result.tables.map((table) => table.riskLevel)).toEqual([null, null]);
    expect(result.tables[0]?.annotationCount).toBe(0);
  });
});

describe("record and formula derivation", () => {
  it("maps backend row records to their local annotations", async () => {
    const { bundle, manifest } = await installedGoldenBundle();
    const pair = manifest.pairs[0] as { pair_id: string };
    const presentation = await loadComparisonPresentation(bundle, pair.pair_id);
    const records = await readLocalChangeRecords(bundle, presentation, "device");
    const annotations = await readLocalRiskAnnotations(bundle, presentation, "device");
    const firstAnnotation = annotations[0];
    if (!firstAnnotation) throw new Error("backend fixture has no row risk annotation");
    const tableAnnotation = { ...firstAnnotation, annotation_id: "device:table-scope", risk_level: "HIGH" as const, target: { ...firstAnnotation.target, target_type: "TABLE" } };
    const locations = deriveChangeLocations([
      ...records,
      { table_name: "device", record_kind: "SCHEMA_CHANGE", row_identity: null },
    ], [...annotations, tableAnnotation]);
    expect(locations.map(({ recordKind, riskLevel }) => [recordKind, riskLevel])).toEqual([
      ["ROW_ADDED", "MEDIUM_LOW"],
      ["ROW_DELETED", "MEDIUM_LOW"],
      ["ROW_MODIFIED", "MEDIUM_HIGH"],
    ]);
    expect(locations.map(({ index }) => index)).toEqual([1, 2, 3]);
  });

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
