import { renderToStaticMarkup } from "react-dom/server";
import { loadComparisonPresentation } from "../bundle/presentation";
import { installedFixtureBundle } from "../../test/helpers";
import { TableFailureNotice, tableStatusText } from "./table-state";

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
});
