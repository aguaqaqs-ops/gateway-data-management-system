import type { Theme } from "@glideapps/glide-data-grid";

export type CssTokenReader = (name: string) => string;

function readComputedToken(name: string): string {
  if (typeof document === "undefined") throw new Error("表格主题需要浏览器中的设计 token");
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function requiredToken(readToken: CssTokenReader, name: string): string {
  const value = readToken(name).trim();
  if (!value) throw new Error(`缺少设计 token：${name}`);
  return value;
}

function numericToken(readToken: CssTokenReader, name: string): number {
  const value = Number.parseFloat(requiredToken(readToken, name));
  if (!Number.isFinite(value)) throw new Error(`设计 token 不是有效数值：${name}`);
  return value;
}

/** Read the same CSS tokens used by page components when a grid is created. */
export function createTableTheme(readToken: CssTokenReader = readComputedToken): Theme {
  const fontFamily = requiredToken(readToken, "--font-family-ui");
  const fontSizeSm = requiredToken(readToken, "--font-size-sm");
  const fontSizeMd = requiredToken(readToken, "--font-size-md");
  const fontSizeXs = requiredToken(readToken, "--font-size-xs");
  const surfaceMuted = requiredToken(readToken, "--color-surface-muted");
  const border = requiredToken(readToken, "--color-border");

  return {
    accentColor: requiredToken(readToken, "--color-accent"),
    accentFg: requiredToken(readToken, "--color-text-on-accent"),
    accentLight: requiredToken(readToken, "--color-accent-soft"),
    textDark: requiredToken(readToken, "--color-text"),
    textMedium: requiredToken(readToken, "--color-text-muted"),
    textLight: requiredToken(readToken, "--color-text-subtle"),
    textBubble: requiredToken(readToken, "--color-text"),
    bgIconHeader: requiredToken(readToken, "--color-text-muted"),
    fgIconHeader: requiredToken(readToken, "--color-text-on-accent"),
    textHeader: requiredToken(readToken, "--color-text-muted"),
    textGroupHeader: requiredToken(readToken, "--color-text"),
    textHeaderSelected: requiredToken(readToken, "--color-text"),
    bgCell: requiredToken(readToken, "--color-surface"),
    bgCellMedium: surfaceMuted,
    bgHeader: surfaceMuted,
    bgHeaderHasFocus: requiredToken(readToken, "--color-accent-soft"),
    bgHeaderHovered: requiredToken(readToken, "--color-surface-hover"),
    bgBubble: surfaceMuted,
    bgBubbleSelected: requiredToken(readToken, "--color-accent-soft"),
    bgSearchResult: requiredToken(readToken, "--color-search-result"),
    borderColor: border,
    drilldownBorder: border,
    linkColor: requiredToken(readToken, "--color-accent"),
    cellHorizontalPadding: numericToken(readToken, "--space-2"),
    cellVerticalPadding: numericToken(readToken, "--space-1"),
    headerFontStyle: `600 ${fontSizeSm} ${fontFamily}`,
    headerIconSize: numericToken(readToken, "--size-icon-header"),
    baseFontStyle: `${fontSizeSm} ${fontFamily}`,
    markerFontStyle: `${fontSizeXs} ${fontFamily}`,
    fontFamily,
    editorFontSize: fontSizeMd,
    lineHeight: numericToken(readToken, "--line-height-body"),
    roundingRadius: numericToken(readToken, "--radius-sm"),
  };
}

export const riskClassByLevel = {
  HIGH: "risk-high",
  MEDIUM_HIGH: "risk-medium-high",
  MEDIUM_LOW: "risk-medium-low",
  LOW: "risk-low",
  UNKNOWN: "risk-unknown",
} as const;

export const changeClassByKind = {
  ADDED: "diff-added",
  DELETED: "diff-deleted",
  UPDATED: "diff-updated",
  UNCHANGED: "diff-unchanged",
} as const;
