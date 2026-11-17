import type { FileMetaData } from "hyparquet";
import type {
  NavigationFacts,
  NavigationPredicate,
  NavigationRowFilter,
  RiskAnnotation,
  RowDiffRecord,
  SurfaceTable,
} from "./model";
import { decodeSnapshotEncodings, type SnapshotColumnEncoding } from "./snapshot-encoding";
import {
  buildBrowseRows,
  canReuseUnrecordedIdentity,
  validateRowLocations,
  type BrowseRow,
  type DeletionLayout,
  type RowLocatorRecord,
} from "./table-rows";

export interface CheckedTableRowLocations {
  publishesFilterTabs: boolean;
  exactTable: boolean;
}

/**
 * First synchronous segment of `loadTable` (B′ order): derive the filter-tab
 * publication facts and validate the row locations BEFORE any parquet
 * metadata read. Throws before any state writes occur.
 */
export function checkTableRowLocations(input: {
  table: SurfaceTable;
  locator: Map<string, RowLocatorRecord>;
  records: RowDiffRecord[];
  beforeRowCount: number;
  currentRowCount: number;
  hasBeforeSnapshot: boolean;
  hasCurrentSnapshot: boolean;
  filterTabs: readonly { facts: NavigationFacts | null; rowFilter: NavigationRowFilter | null }[];
}): CheckedTableRowLocations {
  const publishesFilterTabs = input.filterTabs.length > 0;
  const exactTable =
    publishesFilterTabs && input.filterTabs.every((tab) => tab.facts?.basis === "EXACT");
  validateRowLocations({
    table: input.table,
    locator: input.locator,
    records: input.records,
    beforeRowCount: input.beforeRowCount,
    currentRowCount: input.currentRowCount,
    hasBeforeSnapshot: input.hasBeforeSnapshot,
    hasCurrentSnapshot: input.hasCurrentSnapshot,
    publishesFilterTabs,
    exactTable,
  });
  return { publishesFilterTabs, exactTable };
}

export interface DecodedTableEncodings {
  beforeEncodings: Map<string, SnapshotColumnEncoding>;
  currentEncodings: Map<string, SnapshotColumnEncoding>;
  currentCanonicalBlanks: boolean;
}

/**
 * Second synchronous segment of `loadTable` (B′ order): decode both sides'
 * snapshot encodings and canonical blank provenance AFTER the metadata `await`
 * and BEFORE `setBeforeRows` / `setCurrentRows` / `setAnnotations`.
 */
export function decodeTableEncodings(input: {
  tableName: string;
  beforeMetadata: FileMetaData | null;
  currentMetadata: FileMetaData | null;
  degraded: boolean;
  rowFilter: NavigationRowFilter | null;
  hasUnassigned?: boolean;
}): DecodedTableEncodings {
  const tableLabel = `表 ${input.tableName}`;
  const needsEncodings =
    (input.rowFilter !== null || Boolean(input.hasUnassigned)) && !input.degraded;
  const beforeEncodings: Map<string, SnapshotColumnEncoding> = input.beforeMetadata
    ? decodeSnapshotEncodings(input.beforeMetadata.key_value_metadata, `${tableLabel}.改前`)
    : new Map();
  const currentEncodings: Map<string, SnapshotColumnEncoding> =
    needsEncodings && input.currentMetadata
      ? decodeSnapshotEncodings(input.currentMetadata.key_value_metadata, `${tableLabel}.改后`)
      : new Map();
  const currentCanonicalBlanks =
    input.currentMetadata?.key_value_metadata?.some(
      (entry) =>
        entry.key === "gateway-vnext.batch.blank_provenance" &&
        entry.value === "CANONICAL_PSEUDO_GID",
    ) ?? false;
  return { beforeEncodings, currentEncodings, currentCanonicalBlanks };
}

export interface AssembledTableRows {
  rows: BrowseRow[];
  scoped: BrowseRow[];
}

/**
 * Final segment of `loadTable` (B′ order): build both visible rows and scoped
 * rows AFTER the snapshot/annotation state writes and return them for `setRows`
 * and `setScopedRows`. I/O and state setters stay in the caller hook.
 */
export function assembleTableRows(input: {
  table: SurfaceTable;
  beforeRows: Record<string, unknown>[];
  currentRows: Record<string, unknown>[];
  records: RowDiffRecord[];
  annotations: RiskAnnotation[];
  locator: Map<string, RowLocatorRecord>;
  hasBeforeSnapshot: boolean;
  hasCurrentSnapshot: boolean;
  currentCanonicalBlanks: boolean;
  rowFilter: NavigationRowFilter | null;
  beforeEncodings: ReadonlyMap<string, SnapshotColumnEncoding>;
  currentEncodings: ReadonlyMap<string, SnapshotColumnEncoding>;
  degraded: boolean;
  filterTabs: readonly { facts: NavigationFacts | null; rowFilter: NavigationRowFilter | null }[];
  unassigned: { side: "before" | "current"; predicates: readonly NavigationPredicate[] } | null;
  onlyInteresting: boolean;
  search: string;
  expandedRuns: ReadonlySet<string>;
  deletionLayout: DeletionLayout;
}): AssembledTableRows {
  return buildBrowseRows({
    table: input.table,
    beforeRows: input.beforeRows,
    currentRows: input.currentRows,
    records: input.records,
    annotations: input.annotations,
    locator: input.locator,
    hasBeforeSnapshot: input.hasBeforeSnapshot,
    hasCurrentSnapshot: input.hasCurrentSnapshot,
    currentCanonicalBlanks: input.currentCanonicalBlanks,
    rowFilter: input.rowFilter,
    beforeEncodings: input.beforeEncodings,
    currentEncodings: input.currentEncodings,
    degraded: input.degraded,
    reuseUnrecordedBefore: canReuseUnrecordedIdentity(
      input.table,
      input.filterTabs,
      input.hasBeforeSnapshot,
      input.hasCurrentSnapshot,
    ),
    unassigned: input.unassigned,
    onlyInteresting: input.onlyInteresting,
    search: input.search,
    expandedRuns: input.expandedRuns,
    deletionLayout: input.deletionLayout,
  });
}
