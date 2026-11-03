import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { loadComparisonPresentation } from "../bundle/presentation";
import { installedFixtureBundle } from "../../test/helpers";
import { SURFACE_CHANGE_PRESENTATION, SurfaceChangeBadge, TableFailureNotice, tableStatusText } from "./table-state";

describe("table status rendering", () => {
  it("renders a failed table notice from a cloned backend table projection", async () => {
    const { bundle, manifest } = await installedFixtureBundle("preview-full");
    const pairId = (manifest.pairs[0] as { pair_id: string }).pair_id;
    const presentation = await loadComparisonPresentation(bundle, pairId);
    const source = presentation.view.tables.find((table) => table.tableName === "device");
    if (!source) throw new Error("backend fixture has no device table projection");
    const failed = { ...source, changeKind: "FAILED" as const };

    const html = renderToStaticMarkup(<><span>{tableStatusText(failed)}</span><TableFailureNotice table={failed} /></>);
    expect(html).toContain("比较失败");
    expect(html).toContain('role="alert"');
    expect(html).toContain("该表没有可显示的比较结果。");
  });

  it("uses one presentation mapping for all nine SurfaceChangeKind values", () => {
    const kinds = ["UNCHANGED", "BUSINESS_EQUIVALENT", "ADDED", "DELETED", "UPDATED", "SCHEMA_CHANGED", "DEGRADED", "FAILED", "REPLACED"] as const;
    expect(Object.keys(SURFACE_CHANGE_PRESENTATION).sort()).toEqual([...kinds].sort());
    for (const kind of kinds) {
      const presentation = SURFACE_CHANGE_PRESENTATION[kind];
      expect(tableStatusText({ changeKind: kind })).toBe(presentation.text);
      const html = renderToStaticMarkup(<SurfaceChangeBadge kind={kind} />);
      if (presentation.badgeText) expect(html).toContain(presentation.badgeText);
      else expect(html).toBe("");
      if (kind === "BUSINESS_EQUIVALENT") expect(presentation.tooltip).toBe("内容写法不同，业务含义相同");
      if (kind === "DELETED") expect(presentation.deleted).toBe(true);
    }
  });
});
