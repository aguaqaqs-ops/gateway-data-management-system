import { describe, expect, it } from "vitest";
import { applyNavigationRowFilter, deriveBundleView, deriveChangeLocations, deriveFormulaDisplays, filterChangedRows, type BusinessNavigation, type ComparisonSurface } from "./model";

const surface: ComparisonSurface = {
  tables: [
    { table_name: "device", display_name: "装置表", change_kind: "UPDATED", columns: [{ name: "dev_addr", display_order: 1 }, { name: "description", display_order: 2 }], row_change_stats: { row_count_before: 3, row_count_current: 3 }, records_refs: { records_format: "PARQUET" } },
    { table_name: "device_ext", change_kind: "UNCHANGED", columns: [{ name: "id" }] },
  ],
};

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
    const result = deriveBundleView({ surface, navigation, riskReport: { tables: [{ table_name: "device", risk_level: "MEDIUM_LOW", annotation_count: 2 }] } });
    expect(result.groups[0]?.groupKey).toBe("FUTURE_GROUP");
    expect(result.groups[0]?.label).toBe("扩展业务组");
    expect(result.groups[0]?.items[0]?.showTabs).toBe(true);
    expect(result.groups[0]?.items[0]?.tabs[0]?.rowFilter).toEqual({ column: "dev_addr", value: 1 });
    expect(result.groups.some((group) => group.groupKey === "OTHER_TABLES")).toBe(true);
    expect(result.tables.find((table) => table.tableName === "device")?.riskLevel).toBe("MEDIUM_LOW");
    expect(result.tables.find((table) => table.tableName === "device_ext")?.riskLevel).toBeNull();
  });

  it("does not synthesize unknown risk when the RiskReport has no table entry", () => {
    const result = deriveBundleView({ surface, riskReport: { tables: [] } });
    expect(result.tables.map((table) => table.riskLevel)).toEqual([null, null]);
    expect(result.tables[0]?.annotationCount).toBe(0);
  });

  it("locates changed records and filters locally by change, risk and search", () => {
    const records = [
      { table_name: "device", record_kind: "UNCHANGED", row_identity: new Uint8Array([1]), label: "keep" },
      { table_name: "device", record_kind: "UPDATED", row_identity: new Uint8Array([2]), label: "changed row" },
      { table_name: "device", record_kind: "UNCHANGED", row_identity: new Uint8Array([3]), label: "risk only" },
    ];
    const locations = deriveChangeLocations(records, [{ row_identity: new Uint8Array([2]), risk_level: "HIGH" }]);
    expect(locations).toEqual([{ index: 1, rowIdentity: "02", recordKind: "UPDATED", riskLevel: "HIGH" }]);
    expect(filterChangedRows(records, { onlyInteresting: true, rowIdentityColumn: "row_identity", rowRisk: new Map([["03", "LOW"]]) })).toHaveLength(2);
    expect(filterChangedRows(records, { search: "changed row" })).toHaveLength(1);
    expect(applyNavigationRowFilter(records, { column: "record_kind", value: "UPDATED" })).toHaveLength(1);
  });

  it("shows only the uploaded formula during a changed Preview and both sides in History", () => {
    const before = [{ source_table: "composite_signal_point", point_gid: 8, dev_addr: 65532, formula_digest: "old", formula_ast_json: { op: "add", args: [1, 2] } }];
    const current = [{ source_table: "composite_signal_point", point_gid: 8, dev_addr: 65532, formula_digest: "new", formula_ast_json: { op: "add", args: [1, 3] } }];
    const devices = [{ dev_addr: 65532, description: "复合信号装置" }];
    const preview = deriveFormulaDisplays({ mode: "PREVIEW", before, current, beforeDevices: devices, currentDevices: devices });
    expect(preview[0]).toMatchObject({ beforeFormula: null, currentFormula: current[0]?.formula_ast_json, formulaChanged: true, label: "公式已改", currentDeviceName: "复合信号装置" });
    const history = deriveFormulaDisplays({ mode: "HISTORY", before, current, beforeDevices: [{ dev_addr: 65532, description: "改前名称" }], currentDevices: devices });
    expect(history[0]).toMatchObject({ beforeFormula: before[0]?.formula_ast_json, currentFormula: current[0]?.formula_ast_json, formulaChanged: false, label: null, beforeDeviceName: "改前名称", currentDeviceName: "复合信号装置" });
    const deletedPreview = deriveFormulaDisplays({ mode: "PREVIEW", before, current: [], beforeDevices: devices, deletedPointKeys: new Set(["composite_signal_point:8"]) });
    expect(deletedPreview[0]?.beforeFormula).toEqual(before[0]?.formula_ast_json);
  });
});
