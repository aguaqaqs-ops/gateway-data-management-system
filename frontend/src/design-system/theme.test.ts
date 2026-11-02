import { describe, expect, it } from "vitest";
import { changeClassByKind, riskClassByLevel, tableTheme } from "./theme";

describe("shared table and semantic themes", () => {
  it("uses the application font, sizing and neutral change versus risk classes", () => {
    expect(tableTheme.fontFamily).toContain("Noto Sans CJK SC");
    expect(tableTheme.baseFontStyle).toContain("13px");
    expect(tableTheme.headerFontStyle).toContain("13px");
    expect(changeClassByKind.ADDED).toBe("diff-added");
    expect(changeClassByKind.DELETED).toBe("diff-deleted");
    expect(riskClassByLevel.HIGH).toBe("risk-high");
    expect(riskClassByLevel.MEDIUM_LOW).not.toBe(changeClassByKind.UPDATED);
  });
});
