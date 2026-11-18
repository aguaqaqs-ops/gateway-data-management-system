import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import type { InstalledBundle } from "../../features/bundle/local-bundle";
import { readParquetMetadata, readParquetTable } from "../../features/bundle/parquet-reader";
import {
  readLocalChangeRecords,
  readLocalRiskAnnotations,
  readLocalTable,
  type LocalComparisonPresentation,
} from "../../features/bundle/presentation";
import type { BrowseState } from "../../features/view-model/commands";
import {
  tabScope,
  type DerivedNavigationTab,
  type NavigationPredicate,
  type RiskLevel,
  type RowDiffRecord,
  type SurfaceTable,
} from "../../features/view-model/model";
import { describeRiskReason } from "../../features/view-model/risk-copy";
import {
  assembleTableRows,
  checkTableRowLocations,
  decodeTableEncodings,
} from "../../features/view-model/table-assembly";
import {
  deriveChangeLocations,
  parseRowLocator,
  rowRiskAnnotation,
  type BrowseRow,
  type DeletionLayout,
} from "../../features/view-model/table-rows";
import type { ColumnWidths } from "./sidebar-settings";

export function useTableData(options: {
  bundle: InstalledBundle | null;
  presentation: LocalComparisonPresentation | null;
  selectedTab: DerivedNavigationTab | null;
  surfaceTable: SurfaceTable | null;
  replacement: boolean;
  browse: BrowseState;
  expandedRuns: Set<string>;
  filterTabsForTable: (tableName: string) => DerivedNavigationTab[];
  activeUnassigned: NavigationPredicate[] | null;
  wholeTableName: string | null;
  deletionLayout: DeletionLayout;
  columnWidths: ColumnWidths;
  setColumnWidths: Dispatch<SetStateAction<ColumnWidths>>;
  setError: (error: { code: string; details: string } | null) => void;
}) {
  const {
    bundle,
    presentation,
    selectedTab,
    surfaceTable,
    replacement,
    browse,
    expandedRuns,
    filterTabsForTable,
    activeUnassigned,
    wholeTableName,
    deletionLayout,
    columnWidths,
    setColumnWidths,
    setError,
  } = options;
  const [rows, setRows] = useState<BrowseRow[]>([]);
  const [beforeRows, setBeforeRows] = useState<Record<string, unknown>[]>([]);
  const [currentRows, setCurrentRows] = useState<Record<string, unknown>[]>([]);
  const [scopedRows, setScopedRows] = useState<BrowseRow[]>([]);
  const [annotations, setAnnotations] = useState<
    Awaited<ReturnType<typeof readLocalRiskAnnotations>>
  >([]);
  const [tableLoading, setTableLoading] = useState(false);
  const [visibleRows, setVisibleRows] = useState({ start: 1, end: 1 });

  const loadTable = useCallback(async () => {
    if (!bundle || !presentation || !selectedTab || !surfaceTable) {
      setRows([]);
      setScopedRows([]);
      return;
    }
    setTableLoading(true);
    try {
      const paths = presentation.tableArtifacts.get(selectedTab.tableName);
      const beforePromise = paths?.before
        ? readLocalTable(bundle, presentation, selectedTab.tableName, "before")
        : Promise.resolve([]);
      const currentPromise = paths?.current
        ? readLocalTable(bundle, presentation, selectedTab.tableName, "current")
        : Promise.resolve([]);
      const locatorPromise = paths?.rowLocator
        ? readParquetTable(bundle, paths.rowLocator, {
            columns: [
              "row_identity",
              "before_row_index",
              "current_row_index",
              "before_filter_context_json",
              "current_filter_context_json",
            ],
          })
        : Promise.resolve([] as Record<string, unknown>[]);
      if (replacement) {
        const [before, current] = await Promise.all([beforePromise, currentPromise]);
        setBeforeRows(before as Record<string, unknown>[]);
        setCurrentRows(current as Record<string, unknown>[]);
        setRows([]);
        setScopedRows([]);
        setAnnotations([]);
        return;
      }
      const [before, current, rowRecords, risks, locatorRows] = await Promise.all([
        beforePromise,
        currentPromise,
        readLocalChangeRecords(bundle, presentation, selectedTab.tableName),
        readLocalRiskAnnotations(bundle, presentation, selectedTab.tableName),
        locatorPromise,
      ]);
      const beforeSnapshotRows = before as Record<string, unknown>[];
      const currentSnapshotRows = current as Record<string, unknown>[];
      const tableRecords = rowRecords as RowDiffRecord[];
      const locator = parseRowLocator(locatorRows as Record<string, unknown>[]);
      const filterTabs = filterTabsForTable(surfaceTable.table_name);
      checkTableRowLocations({
        table: surfaceTable,
        locator,
        records: tableRecords,
        beforeRowCount: beforeSnapshotRows.length,
        currentRowCount: currentSnapshotRows.length,
        hasBeforeSnapshot: Boolean(paths?.before),
        hasCurrentSnapshot: Boolean(paths?.current),
        filterTabs,
      });
      const degraded = tableRecords.some(
        (record) =>
          record.record_kind === "TABLE_DEGRADED" ||
          record.record_kind === "ORDERED_TABLE_DEGRADED",
      );
      const unassigned =
        activeUnassigned && browse.unassignedSide
          ? {
              side: browse.unassignedSide === "BEFORE" ? ("before" as const) : ("current" as const),
              predicates: activeUnassigned,
            }
          : null;
      const needsEncodings = (selectedTab.rowFilter !== null || unassigned !== null) && !degraded;
      const needsBlankProvenance = tableRecords.some(
        (record) => record.record_kind === "BLANK_INSERT_INTERVAL",
      );
      const [beforeMeta, currentMeta] = await Promise.all([
        needsEncodings && paths?.before
          ? readParquetMetadata(bundle, paths.before)
          : Promise.resolve(null),
        (needsEncodings || needsBlankProvenance) && paths?.current
          ? readParquetMetadata(bundle, paths.current)
          : Promise.resolve(null),
      ]);
      const { beforeEncodings, currentEncodings, currentCanonicalBlanks } = decodeTableEncodings({
        tableName: surfaceTable.table_name,
        beforeMetadata: beforeMeta,
        currentMetadata: currentMeta,
        degraded,
        rowFilter: selectedTab.rowFilter,
        hasUnassigned: unassigned !== null,
      });
      setBeforeRows(beforeSnapshotRows);
      setCurrentRows(currentSnapshotRows);
      setAnnotations(risks);
      const built = assembleTableRows({
        table: surfaceTable,
        beforeRows: beforeSnapshotRows,
        currentRows: currentSnapshotRows,
        records: tableRecords,
        annotations: risks,
        locator,
        hasBeforeSnapshot: Boolean(paths?.before),
        hasCurrentSnapshot: Boolean(paths?.current),
        currentCanonicalBlanks,
        rowFilter: selectedTab.rowFilter,
        beforeEncodings,
        currentEncodings,
        degraded,
        filterTabs,
        unassigned,
        onlyInteresting: browse.onlyInteresting,
        search: browse.search,
        expandedRuns,
        deletionLayout,
      });
      setRows(built.rows);
      setScopedRows(built.scoped);
    } catch (cause) {
      setError({
        code: "TABLE_READ_FAILED",
        details: cause instanceof Error ? cause.message : String(cause),
      });
    } finally {
      setTableLoading(false);
    }
  }, [
    activeUnassigned,
    browse.onlyInteresting,
    browse.search,
    browse.unassignedSide,
    bundle,
    expandedRuns,
    filterTabsForTable,
    presentation,
    replacement,
    selectedTab,
    deletionLayout,
    surfaceTable,
  ]);

  useEffect(() => {
    void loadTable();
  }, [loadTable]);

  // Locations, risk counts and reasons all follow the current scope: the device
  // filter or orphan view, never the whole table's records behind it.
  const locations = useMemo(() => deriveChangeLocations(scopedRows), [scopedRows]);
  const rowRiskCounts = useMemo(() => {
    const risks = new Map<string, RiskLevel>();
    for (const row of scopedRows)
      if (row.riskLevel) risks.set(row.pairKey ?? row.rowIdentity ?? row.key, row.riskLevel);
    return [...risks.values()].reduce(
      (levels, level) => {
        const match = levels.find((item) => item.level === level);
        if (match) match.count += 1;
        else levels.push({ level, count: 1 });
        return levels;
      },
      [] as Array<{ level: RiskLevel; count: number }>,
    );
  }, [scopedRows]);
  const currentIndex = Math.min(browse.changeIndex, Math.max(0, locations.length - 1));
  const selectedScopeKind = selectedTab ? tabScope(selectedTab).kind : "WHOLE_TABLE";
  const riskReasonDetails = useMemo(() => {
    const result = new Map<string, { reasonCode: string; ruleId: string | null; copy: string }>();
    for (const row of scopedRows) {
      if (!row.riskLevel) continue;
      const annotation = rowRiskAnnotation(row, annotations);
      for (const reason of annotation?.reasons ?? []) {
        result.set(reason.reason_code + "|" + reason.rule_id, {
          reasonCode: reason.reason_code,
          ruleId: reason.rule_id,
          copy: describeRiskReason(reason.reason_code, reason.evidence),
        });
      }
    }
    // Table-level reasons belong to the whole-table view; a device tab lists them under the public notice.
    if (selectedScopeKind === "WHOLE_TABLE" && !browse.unassignedSide) {
      for (const code of surfaceTable?.risk_refs?.reason_codes ?? []) {
        if (![...result.values()].some((detail) => detail.reasonCode === code))
          result.set(code, { reasonCode: code, ruleId: null, copy: describeRiskReason(code) });
      }
    }
    return [...result.values()];
  }, [annotations, browse.unassignedSide, scopedRows, selectedScopeKind, surfaceTable]);
  const unassignedView = useMemo(() => {
    if (!activeUnassigned || !browse.unassignedSide || !wholeTableName || !presentation)
      return null;
    const diagnostic = presentation.navigationDiagnostics.find(
      (item) =>
        item.code === "DEVICE_ROWS_UNASSIGNED" &&
        item.target.table_id === wholeTableName &&
        item.side === browse.unassignedSide,
    );
    const side = browse.unassignedSide === "BEFORE" ? "before" : "current";
    return {
      side: browse.unassignedSide,
      rowCount:
        typeof diagnostic?.params.row_count === "number" ? diagnostic.params.row_count : null,
      changedRowCount:
        typeof diagnostic?.params.changed_row_count === "number"
          ? diagnostic.params.changed_row_count
          : null,
      browsableCount: new Set(scopedRows.filter((row) => row.side === side).map((row) => row.key))
        .size,
      partial:
        browse.unassignedSide === "BEFORE" &&
        !presentation.tableArtifacts.get(wholeTableName)?.before,
    };
  }, [activeUnassigned, browse.unassignedSide, presentation, scopedRows, wholeTableName]);

  const widthTable = surfaceTable?.table_name ?? null;
  const storedWidths = useMemo(
    () => (widthTable ? columnWidths[widthTable] : undefined) ?? {},
    [columnWidths, widthTable],
  );
  const changeColumnWidth = useCallback(
    (columnId: string, width: number) => {
      if (!widthTable) return;
      setColumnWidths((old) => ({
        ...old,
        [widthTable]: { ...old[widthTable], [columnId]: width },
      }));
    },
    [widthTable],
  );
  const resetColumnWidths = () => {
    if (widthTable)
      setColumnWidths((old) => {
        const next = { ...old };
        delete next[widthTable];
        return next;
      });
  };

  return {
    rows,
    beforeRows,
    currentRows,
    annotations,
    tableLoading,
    visibleRows,
    setVisibleRows,
    locations,
    rowRiskCounts,
    currentIndex,
    riskReasonDetails,
    unassignedView,
    widthTable,
    storedWidths,
    changeColumnWidth,
    resetColumnWidths,
  };
}
