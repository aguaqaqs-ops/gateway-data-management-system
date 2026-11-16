import { describe, expect, it } from "vitest";
import { decodeNavigationDiagnostics, firstDegradedDiagnostic, formatNavigationDiagnostic, formatSurfaceDiagnostic, groupNavigationDiagnostics, NAVIGATION_DIAGNOSTIC_CODES, navigationDiagnosticParamKeys, navigationDiagnosticTemplateParamKeys, pairSurfaceDiagnosticCodes, SURFACE_DIAGNOSTIC_CODES, type NavigationDiagnostic } from "./diagnostics";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { installedFixtureBundle } from "../../test/helpers";
import { loadComparisonPresentation } from "../bundle/presentation";
import { ComparisonDecodeError } from "./model";

const BACKEND_CODES = join(process.cwd(), "..", "vnext/fixtures/presentation-inputs/diagnostic-codes.json");

describe("navigation and surface diagnostic copy", () => {
  it("matches the backend-owned diagnostic code table exactly", () => {
    const table = JSON.parse(readFileSync(BACKEND_CODES, "utf8")) as {
      navigation: Record<string, string[]>;
      surface_summary_codes: string[];
    };
    expect([...NAVIGATION_DIAGNOSTIC_CODES].sort()).toEqual(Object.keys(table.navigation).sort());
    for (const [code, params] of Object.entries(table.navigation)) {
      expect([...(navigationDiagnosticParamKeys(code) ?? [])].sort(), code).toEqual([...params].sort());
    }
    expect([...SURFACE_DIAGNOSTIC_CODES].sort()).toEqual([...table.surface_summary_codes].sort());
  });

  it("has a localized template for every v1 navigation code and consumes exactly its params", () => {
    for (const code of NAVIGATION_DIAGNOSTIC_CODES) {
      const required = navigationDiagnosticParamKeys(code);
      expect(required).not.toBeNull();
      const params = Object.fromEntries((required ?? []).map((key) => [key, "值"]));
      const templateKeys = [...(navigationDiagnosticTemplateParamKeys(code) ?? [])];
      expect(templateKeys.every((key) => (required ?? []).includes(key))).toBe(true);
      const value: NavigationDiagnostic = { code, target: { group_key: null, item_key: null, tab_key: null, table_id: "device" }, side: "CURRENT", params };
      const text = formatNavigationDiagnostic(value, [{ table_id: "device", table_name: "device", display_name: "装置表", table_status: "MODIFIED" }]);
      expect(text).not.toContain("{");
      expect(text).not.toContain("}");
      expect(text.length).toBeGreaterThan(0);
      expect(text).not.toBe("导航提示（" + code + "）");
    }
  });

  it("matches only full stable codes and keeps unknown values generic", () => {
    expect(formatNavigationDiagnostic({ code: "FUTURE_CODE", target: { group_key: null, item_key: null, tab_key: null, table_id: null }, side: null, params: {} }, [])).toBe("导航提示（FUTURE_CODE）");
    for (const code of SURFACE_DIAGNOSTIC_CODES) {
      expect(formatSurfaceDiagnostic(code).message).not.toBe("比较过程有提示");
    }
    expect(formatSurfaceDiagnostic("DUPLICATE_EFFECTIVE_KEY:device").message).toBe("比较过程有提示");
    expect(formatSurfaceDiagnostic("RuntimeError").message).toBe("比较过程有提示");
    expect(formatSurfaceDiagnostic("FUTURE_SURFACE_CODE").message).toBe("比较过程有提示");
    expect(firstDegradedDiagnostic(["ORDERED_DIFF_UNSUPPORTED", "DEGRADE_NO_COMPARE_KEY"])).toBe("本表没有可用的比较键");
    expect(firstDegradedDiagnostic(["FUTURE_SURFACE_CODE"])).toBe("降级原因未提供");
    expect(formatSurfaceDiagnostic("ORDERED_PROVENANCE_MISSING").message).toBe("有序表缺少空行来源信息，或该信息无效");
    expect(formatSurfaceDiagnostic("ORDERED_PROVENANCE_INVALID").message).toBe("有序表缺少空行来源信息，或该信息无效");
    expect(formatSurfaceDiagnostic("METADATA_ROUTE_REQUIRES_NATIVE_ROWS").message).toBe("比较时发生内部错误");
    expect(formatSurfaceDiagnostic("METADATA_ROLE_REQUIRES_NATIVE_ROWS").message).toBe("比较时发生内部错误");
    expect(formatSurfaceDiagnostic("BLANK_PROVENANCE_INVALID").message).toBe("有序表的 gid 或空行标记无效");
    for (const removed of ["ROW_IDENTITY_UNSUPPORTED", "ORDER_KEY_UNSUPPORTED", "COMPARISON_MODE_NOT_DETAILED", "ORDERED_POLICY_MISSING", "risk table budget exceeded"]) {
      expect(SURFACE_DIAGNOSTIC_CODES).not.toContain(removed);
      expect(formatSurfaceDiagnostic(removed).message).toBe("比较过程有提示");
    }
  });

  it("subtracts table diagnostics from the view summary by exact stable code", () => {
    const surface = {
      view: { diagnostics_summary: ["DUPLICATE_EFFECTIVE_KEY", "PROJECT_IDENTITY_UNVERIFIABLE"] },
      tables: [{ diagnostics: { diagnostics_summary: ["DUPLICATE_EFFECTIVE_KEY"] } }],
    } as unknown as Parameters<typeof pairSurfaceDiagnosticCodes>[0];
    expect(pairSurfaceDiagnosticCodes(surface)).toEqual(["PROJECT_IDENTITY_UNVERIFIABLE"]);
  });

  it("formats all diagnostics in the five backend fixtures and keeps table codes out of pair notices", async () => {
    for (const name of ["preview-full", "preview-modified-only", "preview-replacement", "history-three-nodes"]) {
      const { bundle, manifest } = await installedFixtureBundle(name);
      for (const summary of manifest.pairs) {
        const presentation = await loadComparisonPresentation(bundle, (summary as { pair_id: string }).pair_id);
        const surface = presentation.surface;
        const view = surface.view as Record<string, unknown> | undefined;
        const tableCodes = new Set(surface.tables.flatMap((table) => table.diagnostics?.diagnostics_summary ?? []));
        for (const code of [...(Array.isArray(view?.diagnostics_summary) ? view.diagnostics_summary as string[] : []), ...tableCodes]) {
          expect(formatSurfaceDiagnostic(code).message).not.toBe("比较过程有提示");
        }
        const pairCodes = pairSurfaceDiagnosticCodes(surface);
        expect(pairCodes.some((code) => tableCodes.has(code))).toBe(false);
        const device = surface.tables.find((table) => table.table_name === "device");
        expect(device?.diagnostics?.diagnostics_summary ?? []).toEqual([]);
      }
    }
  });

  it("does not show navigation diagnostics when diagnostics_ref is absent", async () => {
    const { bundle, manifest } = await installedFixtureBundle("preview-replacement");
    const pair = manifest.pairs[0] as { pair_id: string };
    const presentation = await loadComparisonPresentation(bundle, pair.pair_id);
    expect(presentation.surface.projections?.find((projection) => projection.projection_kind === "BUSINESS_NAVIGATION")?.diagnostics_ref).toBeNull();
    expect(presentation.navigationDiagnostics).toEqual([]);
  });
});


describe("navigation diagnostic decoding", () => {
  const target = { group_key: "COMMUNICATION_PROTOCOLS", item_key: "channel:c2", tab_key: null, table_id: null };
  const document = (code: string, params: Record<string, unknown>) => ({ contract_version: "backend-vnext/business-navigation/v5", diagnostics: [{ code, target, side: "CURRENT", params }] });
  const serial = { channel_prefix: "b12_c2", registry_table: "com_cfg" };
  const tableWide = (code: string, reason: string) => ({ contract_version: "backend-vnext/business-navigation/v5", diagnostics: [{ code, target: { group_key: "SECONDARY_DEVICES", item_key: null, tab_key: null, table_id: "device_st" }, side: null, params: { identity_column: "dev_addr", reason } }] });
  it("accepts the table-wide risk and membership completeness diagnostics and words them as incomplete, not as risk", () => {
    const risk = decodeNavigationDiagnostics(tableWide("DEVICE_TAB_RISK_UNAVAILABLE", "RISK_ATTRIBUTION_UNAVAILABLE")).diagnostics[0]!;
    const membership = decodeNavigationDiagnostics(tableWide("DEVICE_MEMBERSHIP_UNAVAILABLE", "MEMBERSHIP_UNAVAILABLE")).diagnostics[0]!;
    const tables = [{ table_id: "device_st", table_name: "device_st", display_name: "状态类", table_status: "MODIFIED" }];
    expect(formatNavigationDiagnostic(risk, tables)).toBe("状态类的风险信息不完整（部分风险无法归属到具体装置），装置页签只列出已确认的风险");
    expect(formatNavigationDiagnostic(membership, tables)).toBe("状态类的测点归属变化无法完整判断（无法完整判断测点归属是否变化），装置页签只列出已确认的归属变化");
    for (const text of [formatNavigationDiagnostic(risk, tables), formatNavigationDiagnostic(membership, tables)]) expect(text).not.toMatch(/sha256|\/home|RISK_|MEMBERSHIP_/);
  });
  it("accepts and formats serial and network diagnostics with prefixes", () => {
    const orphan = decodeNavigationDiagnostics(document("CHANNEL_TABLE_UNCLAIMED", serial)).diagnostics[0]!;
    const orphanText = formatNavigationDiagnostic(orphan, []);
    expect(orphanText).toContain("串口配置表");
    for (const forbidden of ["网口", "IEC104", "tab_num", "_n"]) expect(orphanText).not.toContain(forbidden);
    const other = { ...orphan, target: { ...orphan.target, group_key: "OTHER_TABLES" } };
    const forward = { ...orphan, target: { ...orphan.target, group_key: "FORWARD_CHANNELS" } };
    expect(formatNavigationDiagnostic(other, [])).toContain("已放入“其他表”");
    expect(formatNavigationDiagnostic(forward, [])).not.toContain("其他表");
    const missing = decodeNavigationDiagnostics(document("PROTOCOL_TABLE_NOT_FOUND", { ...serial, protocol: "规约", expected_prefixes: ["b12_c2_a", "b12_c2_b"] })).diagnostics[0]!;
    const missingText = formatNavigationDiagnostic(missing, []);
    expect(missingText).toContain("预期表名前缀：b12_c2_a、b12_c2_b");
    for (const forbidden of ["网口", "IEC104", "tab_num", "_n"]) expect(missingText).not.toContain(forbidden);
    expect(formatNavigationDiagnostic(decodeNavigationDiagnostics(document("CHANNEL_TABLE_UNCLAIMED", { channel_prefix: "b1_n3", registry_table: "net_cfg" })).diagnostics[0]!, [])).toContain("网口配置表");
  });
  it.each([
    ["old version", { ...document("CHANNEL_TABLE_UNCLAIMED", serial), contract_version: "backend-vnext/business-navigation/v3" }],
    ["unknown code", document("PROTOCOL_EXE_MISSING", serial)],
    ["extra key", document("CHANNEL_TABLE_UNCLAIMED", { ...serial, link_no: 2 })],
    ["missing key", document("CHANNEL_TABLE_UNCLAIMED", { channel_prefix: "b12_c2" })],
    ["bad prefix", document("CHANNEL_TABLE_UNCLAIMED", { ...serial, channel_prefix: "b01_c2" })],
    ["unsafe prefix", document("CHANNEL_TABLE_UNCLAIMED", { ...serial, channel_prefix: "b9007199254740992_c2" })],
    ["wrong registry", document("CHANNEL_TABLE_UNCLAIMED", { ...serial, registry_table: "net_cfg" })],
    ["network with serial registry", document("CHANNEL_TABLE_UNCLAIMED", { channel_prefix: "b1_n2", registry_table: "com_cfg" })],
    ["missing actual side", { ...document("CHANNEL_TABLE_UNCLAIMED", serial), diagnostics: [{ ...document("CHANNEL_TABLE_UNCLAIMED", serial).diagnostics[0], side: null }] }],
    ["local facts with actual side", document("DEVICE_TAB_FACTS_UNAVAILABLE", { identity_column: "gid", reason: "TABLE_DEGRADED" })],
    ["risk incomplete with actual side", document("DEVICE_TAB_RISK_UNAVAILABLE", { identity_column: "gid", reason: "RISK_ATTRIBUTION_UNAVAILABLE" })],
    ["risk incomplete as a fallback reason", tableWide("DEVICE_TAB_FACTS_UNAVAILABLE", "RISK_ATTRIBUTION_UNAVAILABLE")],
    ["membership incomplete with a risk reason", tableWide("DEVICE_MEMBERSHIP_UNAVAILABLE", "RISK_ATTRIBUTION_UNAVAILABLE")],
    ["table-wide diagnostic on an item", { ...tableWide("DEVICE_TAB_RISK_UNAVAILABLE", "RISK_ATTRIBUTION_UNAVAILABLE"), diagnostics: [{ ...tableWide("DEVICE_TAB_RISK_UNAVAILABLE", "RISK_ATTRIBUTION_UNAVAILABLE").diagnostics[0], target: { group_key: "SECONDARY_DEVICES", item_key: "device:addr:1", tab_key: null, table_id: "device_st" } }] }],
    ["empty diagnostics", { contract_version: "backend-vnext/business-navigation/v5", diagnostics: [] }],
    ["unknown reason", document("DEVICE_FILTER_VALUE_UNSUPPORTED", { identity_column: "gid", reason: "UNKNOWN" })],
    ["empty prefixes", document("PROTOCOL_TABLE_NOT_FOUND", { ...serial, protocol: "x", expected_prefixes: [] })],
    ["too many prefixes", document("PROTOCOL_TABLE_NOT_FOUND", { ...serial, protocol: "x", expected_prefixes: ["b12_c2_a", "b12_c2_b", "b12_c2_c"] })],
    ["wrong prefix", document("PROTOCOL_TABLE_NOT_FOUND", { ...serial, protocol: "x", expected_prefixes: ["b12_n2_a"] })],
  ])("rejects %s", (_name, value) => {
    expect(() => decodeNavigationDiagnostics(value)).toThrowError(ComparisonDecodeError);
  });
});


it("keeps a zero-tab channel diagnostic in its group while avoiding duplicate visible-item notes", () => {
  const hidden = decodeNavigationDiagnostics({ contract_version: "backend-vnext/business-navigation/v5", diagnostics: [{ code: "PROTOCOL_TABLE_NOT_FOUND", target: { group_key: "COMMUNICATION_PROTOCOLS", item_key: "channel:c2", tab_key: null, table_id: null }, side: "CURRENT", params: { channel_prefix: "b1_c2", registry_table: "com_cfg", protocol: "规约", expected_prefixes: ["b1_c2_x"] } }] }).diagnostics;
  expect(groupNavigationDiagnostics(hidden, "COMMUNICATION_PROTOCOLS", [])).toEqual(hidden);
  expect(groupNavigationDiagnostics(hidden, "COMMUNICATION_PROTOCOLS", ["channel:c2"])).toEqual([]);
  expect(groupNavigationDiagnostics(hidden, "OTHER_TABLES", [])).toEqual([]);
});
