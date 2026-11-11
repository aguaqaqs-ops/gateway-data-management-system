import { describe, expect, it } from "vitest";
import { firstDegradedDiagnostic, formatNavigationDiagnostic, formatSurfaceDiagnostic, NAVIGATION_DIAGNOSTIC_CODES, navigationDiagnosticParamKeys, navigationDiagnosticTemplateParamKeys, pairSurfaceDiagnosticCodes, SURFACE_DIAGNOSTIC_CODES, type NavigationDiagnostic } from "./diagnostics";
import { installedFixtureBundle } from "../../test/helpers";
import { loadComparisonPresentation } from "../bundle/presentation";

describe("navigation and surface diagnostic copy", () => {
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
