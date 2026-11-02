import { describe, expect, it } from "vitest";
import { readLocalChangeRecords, readLocalRiskAnnotations, loadComparisonPresentation } from "../bundle/presentation";
import { installedGoldenBundle } from "../../test/helpers";
import { applyNavigationRowFilter, deriveBundleView, deriveChangeLocations, deriveFormulaDisplays, filterChangedRows, type BusinessNavigation, type ComparisonSurface, type RiskReport, type RiskTableReport } from "./model";

const surface: ComparisonSurface = {
  tables: [
    { table_id: "device", table_name: "device", display_name: "装置表", table_status: "MODIFIED", change_kind: "UPDATED", columns: [{ name: "dev_addr", display_name: "装置地址", scalar_type: "INT", nullable: false }, { name: "description", display_name: "描述", scalar_type: "VARCHAR(128)", nullable: true }], row_change_stats: { row_count_before: 3, row_count_current: 3 }, records_refs: { records_format: "PARQUET" } },
    { table_id: "device_ext", table_name: "device_ext", display_name: "装置扩展表", table_status: "UNCHANGED", change_kind: "UNCHANGED", columns: [{ name: "id", display_name: "编号", scalar_type: "INT", nullable: false }] },
  ],
};

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

describe("bundle view model", () => {
  it("uses the single-group placeholder when business navigation is absent", () => {
    const result = deriveBundleView({ surface });
    expect(result.groups).toHaveLength(1);
    expect(result.groups[0]?.label).toBe("全部表");
    expect(result.groups[0]?.items).toHaveLength(2);
    expect(result.groups[0]?.items.every((item) => !item.showTabs)).toBe(true);
    expect(result.diagnostics).toContain("未提供业务导航产物，使用单组全部表占位");
  });

  it("renders backend groups and unknown group keys without fixed slots", () => {
    const navigation: BusinessNavigation = {
      groups: [{ group_key: "FUTURE_GROUP", label: "扩展业务组", items: [{
        item_key: "future:one", item_kind: "FUTURE_ITEM", label: "扩展节点", tabs: [
          { tab_key: "first", label: "一", table_id: "device", row_filter: { column: "dev_addr", value: 1 } },
          { tab_key: "second", label: "二", table_id: "device", row_filter: { column: "dev_addr", value: 2 } },
        ],
      }] }],
    };
    const result = deriveBundleView({ surface, navigation, riskReport: riskReport([tableRisk("device", "MEDIUM_LOW", 2)]) });
    expect(result.groups[0]?.groupKey).toBe("FUTURE_GROUP");
    expect(result.groups[0]?.label).toBe("扩展业务组");
    expect(result.groups[0]?.items[0]?.showTabs).toBe(true);
    expect(result.groups[0]?.items[0]?.tabs[0]?.rowFilter).toEqual({ column: "dev_addr", value: 1 });
    expect(result.groups.some((group) => group.groupKey === "OTHER_TABLES")).toBe(true);
    expect(result.tables.find((table) => table.tableName === "device")?.riskLevel).toBe("MEDIUM_LOW");
    expect(result.tables.find((table) => table.tableName === "device_ext")?.riskLevel).toBeNull();
  });

  it("summarizes filtered tabs from scoped facts without reading inline diagnostics", () => {
    const navigation: BusinessNavigation = {
      groups: [{ group_key: "SECONDARY_DEVICES", label: "二次装置列表", items: [{
        item_key: "device:addr:1", item_kind: "DEVICE", label: "装置一", tabs: [
          { tab_key: "filtered", label: "装置一的表", table_id: "device", row_filter: { column: "dev_addr", value: 1 }, facts: { change_kind: "ADDED", risk_level: "HIGH" } },
          { tab_key: "whole", label: "装置整表", table_id: "device_ext", row_filter: null },
        ],
      }] }],
    };
    const result = deriveBundleView({
      surface,
      navigation,
      riskReport: riskReport([tableRisk("device", "MEDIUM_LOW", 0)]),
    });

    expect(result.groups[0]?.items[0]?.changeKinds).toEqual(["ADDED", "UNCHANGED"]);
    expect(result.groups[0]?.items[0]?.riskLevels).toEqual(["HIGH"]);
    expect(result.diagnostics).toEqual([]);
  });

  it("does not synthesize unknown risk when the RiskReport has no table entry", () => {
    const result = deriveBundleView({ surface, riskReport: riskReport([]) });
    expect(result.tables.map((table) => table.riskLevel)).toEqual([null, null]);
    expect(result.tables[0]?.annotationCount).toBe(0);
  });

  it("maps backend row records to their local annotations and filters row changes", async () => {
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

    const rowRisk = new Map(locations.flatMap(({ rowIdentity, riskLevel }) => rowIdentity && riskLevel ? [[rowIdentity, riskLevel] as const] : []));
    expect(filterChangedRows(records, { onlyInteresting: true, rowIdentityColumn: "row_identity", rowRisk })).toHaveLength(3);
    expect(filterChangedRows(records, { changeKinds: new Set(["ROW_MODIFIED"]), search: "测控装置（升级）" })).toHaveLength(1);
    expect(applyNavigationRowFilter(records, { column: "record_kind", value: "ROW_DELETED" })).toHaveLength(1);
  });

  it("does not search binary row identities or structural kind fields", () => {
    const rows = [
      { row_identity: Uint8Array.from([0x12, 0x34]), kind: "string", record_kind: "ROW_ADDED", value: "继电器" },
    ];
    expect(filterChangedRows(rows, { search: "12" })).toEqual([]);
    expect(filterChangedRows(rows, { search: "string" })).toEqual([]);
    expect(filterChangedRows(rows, { search: "继电器" })).toHaveLength(1);
  });

  it("shows only the uploaded formula during a changed Preview and both sides in History", () => {
    const before = [{ source_table: "composite_signal_point", point_gid: 8, dev_addr: 65532, formula_digest: "old", formula_ast_json: { op: "add", args: [1, 2] } }];
    const current = [{ source_table: "composite_signal_point", point_gid: 8, dev_addr: 65532, formula_digest: "new", formula_ast_json: { op: "add", args: [1, 3] } }];
    const devices = [{ dev_addr: 65532, description: "复合信号装置" }];
    const preview = deriveFormulaDisplays({ mode: "PREVIEW", before, current, beforeDevices: devices, currentDevices: devices });
    expect(preview[0]).toMatchObject({ beforeFormula: null, currentFormula: current[0]?.formula_ast_json, formulaChanged: true, label: "公式已改", currentDeviceName: "复合信号装置" });
    const history = deriveFormulaDisplays({ mode: "HISTORY", before, current, beforeDevices: [{ dev_addr: 65532, description: "改前名称" }], currentDevices: devices });
    expect(history[0]).toMatchObject({ beforeFormula: before[0]?.formula_ast_json, currentFormula: current[0]?.formula_ast_json, changed: true, formulaChanged: false, label: null, beforeDeviceName: "改前名称", currentDeviceName: "复合信号装置" });
    const deletedPreview = deriveFormulaDisplays({ mode: "PREVIEW", before, current: [], beforeDevices: devices, deletedPointKeys: new Set(["composite_signal_point:8"]) });
    expect(deletedPreview[0]?.beforeFormula).toEqual(before[0]?.formula_ast_json);
  });
});
