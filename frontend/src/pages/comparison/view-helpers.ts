import type { GridColumn } from "@glideapps/glide-data-grid";
import { ApiError } from "../../features/api/authenticated-fetch";
import { bundleLoadErrorCode } from "../../features/bundle/local-bundle";
import type { LocalComparisonPresentation } from "../../features/bundle/presentation";
import type { BrowseState } from "../../features/view-model/commands";
import { pairSurfaceDiagnosticCodes } from "../../features/view-model/diagnostics";
import type {
  DerivedNavigationGroup,
  RiskLevel,
  SurfaceTable,
} from "../../features/view-model/model";
import type { BrowseRow } from "../../features/view-model/table-rows";

export type PairSummary = { pair_id: string; summary?: Record<string, string> };
export type PairPresentation = { pair: PairSummary; presentation: LocalComparisonPresentation };
export type SizedGridColumn = GridColumn & { width: number };
export type NavItem = DerivedNavigationGroup["items"][number];
export type NavTab = NavItem["tabs"][number];
export type TextMeasure = (text: string) => number;

export function bundleErrorState(
  cause: unknown,
  details: string,
): { code: string; details: string } {
  // B5: the server's ApiError code is carried into the error state verbatim so
  // it stays visible and copyable; only non-HTTP failures use the generic
  // bundle-load codes. Never construct an empty bundle from an error response.
  if (cause instanceof ApiError)
    return { code: cause.code ?? `HTTP_${cause.status}`, details: cause.message || details };
  return { code: bundleLoadErrorCode(cause), details };
}

export function serverResultReleaseCode(cause: unknown): string | undefined {
  return cause instanceof ApiError &&
    cause.status === 503 &&
    (cause.code === "SUBMISSION_RESULT_UNAVAILABLE" ||
      cause.code === "SUBMISSION_RESULT_INTEGRITY_FAILURE")
    ? cause.code
    : undefined;
}

export function bundlePathForState(state: BrowseState): string | null {
  if (state.mode === "PREVIEW" && state.workspaceId && state.previewResultId) {
    return `/v1/workspaces/${encodeURIComponent(state.workspaceId)}/preview-results/${encodeURIComponent(state.previewResultId)}/bundle`;
  }
  if (state.mode === "REVIEW" && state.submissionId)
    return `/v1/submissions/${encodeURIComponent(state.submissionId)}/result/bundle`;
  if (state.mode === "HISTORY" && state.operationId) {
    return `/v1/history-compares/${encodeURIComponent(state.operationId)}/bundle`;
  }
  return null;
}

export function viewRiskLevel(pair: PairPresentation): RiskLevel | null {
  const risk = pair.presentation.surface.view?.risk_level;
  return risk === "HIGH" ||
    risk === "MEDIUM_HIGH" ||
    risk === "MEDIUM_LOW" ||
    risk === "LOW" ||
    risk === "UNKNOWN"
    ? risk
    : null;
}

export function pairDiagnosticDetails(pair: PairPresentation): {
  codes: string[];
  tableCount: number;
} {
  const surface = pair.presentation.surface;
  const tableCount = surface.tables.filter(
    (table) => (table.diagnostics?.diagnostics_summary?.length ?? 0) > 0,
  ).length;
  return { codes: pairSurfaceDiagnosticCodes(surface), tableCount };
}

export function riskTokens(level: RiskLevel): {
  bg: string;
  rail: string;
  text: string;
  cell: string;
} {
  const style = getComputedStyle(document.documentElement);
  const name = "risk-" + level.toLowerCase().replace("_", "-");
  return {
    bg: style.getPropertyValue("--" + name + "-bg").trim(),
    rail: style.getPropertyValue("--" + name + "-rail").trim(),
    text: style.getPropertyValue("--" + name + "-text").trim(),
    cell: style.getPropertyValue("--" + name + "-cell").trim(),
  };
}

/** Changed fields listed in the hover detail before the rest are summarised. */
export const HOVER_FIELD_LIMIT = 8;

/** Rows an ordered table moved; row_change_stats does not count moves. */
export function orderedMovedCount(table: SurfaceTable): number {
  const summary = table.ordered_extension?.ordered_summary;
  const moved =
    summary && typeof summary === "object"
      ? (summary as Record<string, unknown>).row_moved_count
      : null;
  return typeof moved === "number" && moved > 0 ? moved : 0;
}

export function hasDeletedAppearance(row: BrowseRow): boolean {
  return (
    row.kind === "deleted" ||
    (row.kind === "blank-interval" && row.interval?.direction === "DELETE")
  );
}

export function recordValues(value: unknown): Record<string, unknown> {
  if (!Array.isArray(value)) return {};
  return Object.fromEntries(
    value.flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const entry = item as { column_name?: unknown; value?: unknown };
      return typeof entry.column_name === "string" ? [[entry.column_name, entry.value]] : [];
    }),
  );
}

/** Measures text in the grid's own canvas font; falls back to a rough estimate. */
export function createTextMeasure(font: string): TextMeasure {
  const context =
    typeof document === "undefined" ? null : document.createElement("canvas").getContext("2d");
  if (!context) return (text) => Array.from(text).length * 9;
  context.font = font;
  const cache = new Map<string, number>();
  return (text) => {
    let width = cache.get(text);
    if (width === undefined) {
      width = context.measureText(text).width;
      if (cache.size < 20_000) cache.set(text, width);
    }
    return width;
  };
}

/** Up to `limit` rows spread evenly over the table, so long tables size from more than their head. */
export function sampleRows<T>(rows: readonly T[], limit: number): T[] {
  if (rows.length <= limit) return [...rows];
  const step = rows.length / limit;
  return Array.from({ length: limit }, (_, index) => rows[Math.floor(index * step)] as T);
}

export const COLUMN_PADDING = 26;
export const COLUMN_MIN = 56;
export const COLUMN_AUTO_MAX = 420;
export const COLUMN_FIT_MAX = 900;

/**
 * Width that fits the header and most values. Auto sizing uses the 95th
 * percentile so a few very long values do not widen the column; a double-click
 * fit uses the longest value.
 */
export function fitWidth(headerWidth: number, valueWidths: number[], mode: "auto" | "fit"): number {
  const sorted = valueWidths.filter((width) => width > 0).sort((left, right) => left - right);
  const value =
    sorted.length === 0
      ? 0
      : mode === "fit"
        ? (sorted[sorted.length - 1] ?? 0)
        : (sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))] ?? 0);
  return Math.round(
    Math.min(
      mode === "fit" ? COLUMN_FIT_MAX : COLUMN_AUTO_MAX,
      Math.max(COLUMN_MIN, headerWidth, value) + COLUMN_PADDING,
    ),
  );
}

export function matchesGroup(group: DerivedNavigationGroup, query: string): boolean {
  const value = query.trim().toLocaleLowerCase();
  if (!value) return true;
  return [
    group.label,
    ...group.items.flatMap((item) => [item.label, ...item.tabs.map((tab) => tab.label)]),
  ].some((item) => item.toLocaleLowerCase().includes(value));
}

export function matchesItem(item: DerivedNavigationGroup["items"][number], query: string): boolean {
  const value = query.trim().toLocaleLowerCase();
  return (
    !value ||
    [item.label, ...item.tabs.map((tab) => tab.label)].some((label) =>
      label.toLocaleLowerCase().includes(value),
    )
  );
}
