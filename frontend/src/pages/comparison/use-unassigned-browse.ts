import { useCallback, useEffect, useMemo } from "react";
import type { LocalComparisonPresentation } from "../../features/bundle/presentation";
import type { BrowseCommandRuntime, BrowseState } from "../../features/view-model/commands";
import type { NavigationDiagnostic } from "../../features/view-model/diagnostics";
import type { NavigationPredicate } from "../../features/view-model/model";

export function useUnassignedBrowse(options: {
  presentation: LocalComparisonPresentation | null;
  wholeTableName: string | null;
  browse: BrowseState;
  runtime: BrowseCommandRuntime;
  openWholeTable: (tableName: string, itemKey?: string | null) => void;
}) {
  const { presentation, wholeTableName, browse, runtime, openWholeTable } = options;

  const filterTabsForTable = useCallback(
    (tableName: string) => {
      if (!presentation) return [];
      const sides = presentation.view.replacementSides
        ? [
            ...presentation.view.groups,
            ...presentation.view.replacementSides.before,
            ...presentation.view.replacementSides.current,
          ]
        : presentation.view.groups;
      return sides
        .flatMap((group) => group.items.flatMap((item) => item.tabs))
        .filter((tab) => tab.tableName === tableName && tab.rowFilter !== null);
    },
    [presentation],
  );
  /**
   * Predicates of every device filter on one side of a table, for orphan
   * browsing. Null when the side cannot be judged: replacement, no published
   * predicate, unsupported identity, or a missing current snapshot.
   */
  const unassignedPredicates = useCallback(
    (tableName: string, side: "BEFORE" | "CURRENT"): NavigationPredicate[] | null => {
      if (!presentation || presentation.view.replacementSides) return null;
      const diagnostics = presentation.navigationDiagnostics.filter(
        (diagnostic) => diagnostic.target.table_id === tableName && diagnostic.side === side,
      );
      if (!diagnostics.some((diagnostic) => diagnostic.code === "DEVICE_ROWS_UNASSIGNED"))
        return null;
      if (diagnostics.some((diagnostic) => diagnostic.code === "DEVICE_FILTER_VALUE_UNSUPPORTED"))
        return null;
      if (side === "CURRENT" && !presentation.tableArtifacts.get(tableName)?.current) return null;
      const predicates = filterTabsForTable(tableName).flatMap((tab) => {
        const predicate = side === "BEFORE" ? tab.rowFilter?.before : tab.rowFilter?.current;
        return predicate ? [predicate] : [];
      });
      return predicates.length > 0 ? predicates : null;
    },
    [filterTabsForTable, presentation],
  );
  const canBrowseUnassigned = useCallback(
    (diagnostic: NavigationDiagnostic) =>
      diagnostic.code === "DEVICE_ROWS_UNASSIGNED" &&
      typeof diagnostic.target.table_id === "string" &&
      diagnostic.side !== null &&
      unassignedPredicates(diagnostic.target.table_id, diagnostic.side) !== null,
    [unassignedPredicates],
  );
  const browseUnassigned = (tableName: string, side: "BEFORE" | "CURRENT") => {
    openWholeTable(tableName);
    runtime.execute({ name: "set-unassigned", side });
  };
  const activeUnassigned = useMemo(
    () =>
      wholeTableName && browse.unassignedSide
        ? unassignedPredicates(wholeTableName, browse.unassignedSide)
        : null,
    [browse.unassignedSide, unassignedPredicates, wholeTableName],
  );
  // An orphan state restored from the URL that this table cannot honour falls back to the plain whole table.
  useEffect(() => {
    if (presentation && browse.unassignedSide && !activeUnassigned)
      runtime.execute({ name: "set-unassigned", side: null }, "external");
  }, [activeUnassigned, browse.unassignedSide, presentation, runtime]);

  return {
    filterTabsForTable,
    canBrowseUnassigned,
    browseUnassigned,
    activeUnassigned,
  };
}
