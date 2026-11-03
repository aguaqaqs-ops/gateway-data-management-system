import { loadComparisonPresentation } from "../bundle/presentation";
import type { InstalledBundle } from "../bundle/local-bundle";
import type { ChangeKind, ComparisonSurface } from "../view-model/model";

export interface HistoryPairTableSummary {
  tableName: string;
  displayName: string;
  changeKind: ChangeKind;
  added: number;
  deleted: number;
  modified: number;
}

export interface HistoryPairSummary {
  pairId: string;
  tableCount: number;
  changedTableCount: number;
  degradedTableCount: number;
  tables: HistoryPairTableSummary[];
}

const CHANGE_KINDS = new Set<ChangeKind>(["UNCHANGED", "BUSINESS_EQUIVALENT", "ADDED", "DELETED", "UPDATED", "SCHEMA_CHANGED", "DEGRADED", "FAILED", "REPLACED"]);

function changeKindOf(table: ComparisonSurface["tables"][number]): ChangeKind {
  if (table.change_kind) return table.change_kind;
  if (table.table_status === "DEGRADED") return "DEGRADED";
  if (CHANGE_KINDS.has(table.table_status as ChangeKind)) return table.table_status as ChangeKind;
  const stats = table.row_change_stats;
  const changed = (stats?.row_added_count ?? 0) + (stats?.row_deleted_count ?? 0) + (stats?.row_modified_count ?? 0) > 0;
  return changed ? "UPDATED" : "UNCHANGED";
}

/**
 * Computes the drawer summary from local bundle facts only: the surface tables
 * carry the per-table change counts, so no backend field or extra request exists.
 */
export function summarizeSurface(surface: ComparisonSurface, pairId = "unknown"): HistoryPairSummary {
  const tables = surface.tables.map((table) => {
    const stats = table.row_change_stats;
    return {
      tableName: table.table_name,
      displayName: table.display_name || table.table_name,
      changeKind: changeKindOf(table),
      added: stats?.row_added_count ?? 0,
      deleted: stats?.row_deleted_count ?? 0,
      modified: stats?.row_modified_count ?? 0,
    };
  });
  return {
    pairId,
    tableCount: tables.length,
    changedTableCount: tables.filter((table) => table.changeKind !== "UNCHANGED").length,
    degradedTableCount: tables.filter((table) => table.changeKind === "DEGRADED").length,
    tables,
  };
}

export async function summarizeHistoryPair(bundle: InstalledBundle, pairId: string): Promise<HistoryPairSummary> {
  const presentation = await loadComparisonPresentation(bundle, pairId);
  return summarizeSurface(presentation.surface, pairId);
}
