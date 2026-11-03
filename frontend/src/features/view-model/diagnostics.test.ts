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
      expect([...(navigationDiagnosticTemplateParamKeys(code) ?? [])].sort()).toEqual([...(required ?? [])].sort());
      const value: NavigationDiagnostic = { code, target: { group_key: null, item_key: null, tab_key: null, table_id: "device" }, side: "CURRENT", params };
      const text = formatNavigationDiagnostic(value, [{ table_id: "device", table_name: "device", display_name: "装置表", table_status: "MODIFIED" }]);
      expect(text).not.toContain("{");
      expect(text).not.toContain("}");
      expect(text.length).toBeGreaterThan(0);
      expect(text).not.toBe("导航提示（" + code + "）");
    }
  });

  it("has specific v1 copy and the specified exact, prefix, exception, generic matching order", () => {
    expect(formatNavigationDiagnostic({ code: "FUTURE_CODE", target: { group_key: null, item_key: null, tab_key: null, table_id: null }, side: null, params: {} }, [])).toBe("导航提示（FUTURE_CODE）");
    for (const code of SURFACE_DIAGNOSTIC_CODES) {
      expect(formatSurfaceDiagnostic(code).message).not.toBe("比较过程有提示");
    }
    expect(formatSurfaceDiagnostic("DUPLICATE_EFFECTIVE_KEY:device").message).toBe("比较键有重复值");
    expect(formatSurfaceDiagnostic("RuntimeError").message).toBe("比较时发生内部错误");
    expect(formatSurfaceDiagnostic("FUTURE_SURFACE_CODE").message).toBe("比较过程有提示");
    expect(firstDegradedDiagnostic(["ORDERED_DIFF_UNSUPPORTED", "DEGRADE_NO_COMPARE_KEY"])).toBe("本表没有可用的比较键");
    expect(firstDegradedDiagnostic(["FUTURE_SURFACE_CODE"])).toBe("降级原因未提供");
  });

  it("subtracts table diagnostics after removing table-name suffixes from the view summary", () => {
    const surface = {
      view: { diagnostics_summary: ["DUPLICATE_EFFECTIVE_KEY", "PROJECT_IDENTITY_UNVERIFIABLE"] },
      tables: [{ diagnostics: { diagnostics_summary: ["DUPLICATE_EFFECTIVE_KEY:device"] } }],
    } as unknown as Parameters<typeof pairSurfaceDiagnosticCodes>[0];
    expect(pairSurfaceDiagnosticCodes(surface)).toEqual(["PROJECT_IDENTITY_UNVERIFIABLE"]);
  });

  it("formats all diagnostics in the five backend fixtures and keeps table codes out of pair notices", async () => {
    for (const name of ["preview-full", "preview-modified-only", "preview-replacement", "preview-no-navigation", "history-three-nodes"]) {
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
