import { describe, expect, it } from "vitest";
import { changeClassByKind, createTableTheme, riskClassByLevel, type CssTokenReader } from "./theme";

describe("shared table and semantic themes", () => {
  it("uses the application font, sizing and neutral change versus risk classes", () => {
    const tokens: Record<string, string> = {
      "--font-family-ui": '"Noto Sans CJK SC", sans-serif',
      "--font-size-xs": "12px",
      "--font-size-sm": "13px",
      "--font-size-md": "14px",
      "--line-height-body": "1.5",
      "--space-1": "4px",
      "--space-2": "8px",
      "--size-icon-header": "18px",
      "--radius-sm": "4px",
      "--color-accent": "#1f5efb",
      "--color-text-on-accent": "#ffffff",
      "--color-accent-soft": "#e8efff",
      "--color-text": "#202833",
      "--color-text-muted": "#596779",
      "--color-text-subtle": "#748195",
      "--color-surface": "#ffffff",
      "--color-surface-muted": "#f6f8fa",
      "--color-surface-hover": "#edf1f6",
      "--color-search-result": "#fff3cd",
      "--color-border": "#d9e0e8",
    };
    const readToken: CssTokenReader = (name) => tokens[name] ?? "";
    const tableTheme = createTableTheme(readToken);
    expect(tableTheme.fontFamily).toContain("Noto Sans CJK SC");
    expect(tableTheme.baseFontStyle).toContain("13px");
    expect(tableTheme.headerFontStyle).toContain("13px");
    expect(tableTheme.accentColor).toBe(tokens["--color-accent"]);
    expect(tableTheme.borderColor).toBe(tokens["--color-border"]);
    expect(tableTheme.cellHorizontalPadding).toBe(8);
    expect(tableTheme.roundingRadius).toBe(4);
    expect(changeClassByKind.ADDED).toBe("diff-added");
    expect(changeClassByKind.DELETED).toBe("diff-deleted");
    expect(riskClassByLevel.HIGH).toBe("risk-high");
    expect(riskClassByLevel.MEDIUM_LOW).not.toBe(changeClassByKind.UPDATED);
  });
});
