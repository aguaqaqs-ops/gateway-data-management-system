import { describe, expect, it } from "vitest";
import { formatNavigationDiagnostic, formatSurfaceDiagnostic, NAVIGATION_DIAGNOSTIC_CODES, navigationDiagnosticParamKeys, navigationDiagnosticTemplateParamKeys, SURFACE_DIAGNOSTIC_CODES, type NavigationDiagnostic } from "./diagnostics";
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

  it("uses the defined unknown-code fallback and the complete v1 surface copy map", () => {
    expect(formatNavigationDiagnostic({ code: "FUTURE_CODE", target: { group_key: null, item_key: null, tab_key: null, table_id: null }, side: null, params: {} }, [])).toBe("导航提示（FUTURE_CODE）");
    for (const code of SURFACE_DIAGNOSTIC_CODES) {
      expect(formatSurfaceDiagnostic(code).message).not.toBe("比较过程有提示");
    }
    expect(formatSurfaceDiagnostic("FUTURE_SURFACE_CODE").message).toBe("比较过程有提示");
  });

  it("does not show navigation diagnostics when diagnostics_ref is absent", async () => {
    const { bundle, manifest } = await installedFixtureBundle("preview-replacement");
    const pair = manifest.pairs[0] as { pair_id: string };
    const presentation = await loadComparisonPresentation(bundle, pair.pair_id);
    expect(presentation.surface.projections?.find((projection) => projection.projection_kind === "BUSINESS_NAVIGATION")?.diagnostics_ref).toBeNull();
    expect(presentation.navigationDiagnostics).toEqual([]);
  });
});
