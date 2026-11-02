import type { Theme } from "@glideapps/glide-data-grid";

export const tableTheme: Theme = {
  accentColor: "#1f5efb",
  accentFg: "#ffffff",
  accentLight: "#e8efff",
  textDark: "#202833",
  textMedium: "#596779",
  textLight: "#748195",
  textBubble: "#202833",
  bgIconHeader: "#596779",
  fgIconHeader: "#ffffff",
  textHeader: "#596779",
  textGroupHeader: "#202833",
  textHeaderSelected: "#202833",
  bgCell: "#ffffff",
  bgCellMedium: "#f6f8fa",
  bgHeader: "#f6f8fa",
  bgHeaderHasFocus: "#e8efff",
  bgHeaderHovered: "#edf1f6",
  bgBubble: "#f6f8fa",
  bgBubbleSelected: "#e8efff",
  bgSearchResult: "#fff3cd",
  borderColor: "#d9e0e8",
  drilldownBorder: "#d9e0e8",
  linkColor: "#1f5efb",
  cellHorizontalPadding: 8,
  cellVerticalPadding: 4,
  headerFontStyle: "600 13px \"Noto Sans CJK SC\", sans-serif",
  headerIconSize: 18,
  baseFontStyle: "13px \"Noto Sans CJK SC\", sans-serif",
  markerFontStyle: "12px \"Noto Sans CJK SC\", sans-serif",
  fontFamily: "\"Noto Sans CJK SC\", sans-serif",
  editorFontSize: "14px",
  lineHeight: 1.45,
  roundingRadius: 4,
};

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
