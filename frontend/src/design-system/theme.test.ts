import { describe, expect, it } from "vitest";
import { changeClassByKind, createTableTheme, riskClassByLevel, type CssTokenReader } from "./theme";

describe("shared table and semantic themes", () => {
  it("uses the application font, sizing and neutral change versus risk classes", () => {
    const tokens: Record<string, string> = {
      "--font-family-ui": "'IBM Plex Sans', 'PingFang SC', 'Noto Sans SC', 'Noto Sans CJK SC', 'Microsoft YaHei', sans-serif",
      "--font-size-xs": "12px",
      "--font-size-sm": "13px",
      "--font-size-md": "14px",
      "--line-height-body": "1.5",
      "--space-1": "4px",
      "--space-2": "8px",
      "--size-icon-header": "18px",
      "--radius-sm": "4px",
      "--color-accent": "#1F5FBF",
      "--color-accent-hover": "#174A96",
      "--color-focus-ring": "#1F5FBF",
      "--color-text-on-accent": "#ffffff",
      "--color-accent-soft": "#E9F0FB",
      "--color-page": "#F3F5F7",
      "--color-text": "#1B2229",
      "--color-text-muted": "#5F6B78",
      "--color-text-subtle": "#4A5563",
      "--color-surface": "#ffffff",
      "--color-surface-muted": "#F7F9FB",
      "--color-surface-hover": "#F7F9FB",
      "--color-search-result": "#fff3cd",
      "--color-border": "#DDE2E7",
      "--color-border-strong": "#C9D0D8",
      "--color-row-separator": "#EEF1F4",
    };
    const readToken: CssTokenReader = (name) => tokens[name] ?? "";
    const tableTheme = createTableTheme(readToken);
    expect(tableTheme.fontFamily).toContain("IBM Plex Sans");
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
