import type { InstalledBundle } from "./local-bundle";
import { readJsonArtifact, readParquetTable, type ParquetReadRequest } from "./parquet-reader";
import type { BundleArtifactEntry } from "./posix-tar";
import { ComparisonDecodeError, decodeBusinessNavigation, deriveBundleView, type BusinessNavigation, type ComparisonSurface, type DerivedBundleView, type RiskAnnotation, type RiskAnnotationDocument, type RiskReport, type RowDiffRecord, type SurfaceTable } from "../view-model/model";
import type { NavigationDiagnostic, NavigationDiagnosticsDocument } from "../view-model/diagnostics";

export type SnapshotSide = "before" | "current" | "browse";

export interface TableArtifactPaths {
  before: string | null;
  current: string | null;
  browse: string | null;
  records: string | null;
  orderedRecords: string | null;
  blankRecords: string[];
  /** Typed 5-column row locator; null when the table publishes no ordinary rows. */
  rowLocator: string | null;
  annotations: string | null;
}

export interface LocalComparisonPresentation {
  pairId: string;
  surface: ComparisonSurface;
  navigation: BusinessNavigation;
  navigationDiagnostics: NavigationDiagnostic[];
  surfaceDiagnostics: string[];
  riskReport?: RiskReport;
  projectIdentityAssessment?: Record<string, unknown>;
  view: DerivedBundleView;
  tableArtifacts: Map<string, TableArtifactPaths>;
}

function physicalEntries(bundle: InstalledBundle): BundleArtifactEntry[] {
  return bundle.closure.closure_entries;
}

function entryPathByArtifactId(bundle: InstalledBundle, artifact: unknown): string | null {
  if (!artifact || typeof artifact !== "object") return null;
  const artifactId = (artifact as Record<string, unknown>).artifact_id;
  if (typeof artifactId !== "string") return null;
  return physicalEntries(bundle).find((entry) => entry.artifact_ref.artifact_id === artifactId)?.logical_path ?? null;
}

function pairArtifact(bundle: InstalledBundle, kind: string, pairId: string): BundleArtifactEntry | undefined {
  return physicalEntries(bundle).find((entry) => entry.kind === kind && entry.pair_id === pairId);
}

const SURFACE_CONTRACT_VERSION = "backend-vnext/comparison-surface/v4";
const PRESENT_IN_VALUES: ReadonlySet<string> = new Set(["BEFORE", "CURRENT", "BOTH"]);

function tableRef(bundle: InstalledBundle, artifact: unknown, where: string): BundleArtifactEntry | null {
  if (artifact == null) return null;
  if (typeof artifact !== "object") throw new ComparisonDecodeError(`${where} 不是 ArtifactRef`);
  const artifactId = (artifact as Record<string, unknown>).artifact_id;
  if (typeof artifactId !== "string") throw new ComparisonDecodeError(`${where} 缺少 artifact_id`);
  const entry = physicalEntries(bundle).find((item) => item.artifact_ref.artifact_id === artifactId);
  if (!entry) throw new ComparisonDecodeError(`${where} 引用了 closure 中不存在的 artifact：${artifactId}`);
  const reference = artifact as Record<string, unknown>;
  if (reference.raw_sha256 !== entry.raw_sha256 || reference.size_bytes !== entry.size_bytes) {
    throw new ComparisonDecodeError(`${where} 的摘要与 closure 不一致`);
  }
  return entry;
}

/** Validates the v4 surface shape and its per-side content bindings. */
function validateSurface(bundle: InstalledBundle, surface: ComparisonSurface): void {
  if (surface.surface_contract_version !== SURFACE_CONTRACT_VERSION) {
    throw new ComparisonDecodeError(`不支持的 comparison surface contract version：${String(surface.surface_contract_version)}`);
  }
  if (!Array.isArray(surface.tables)) throw new ComparisonDecodeError("surface.tables 不是数组");
  for (const table of surface.tables) {
    const where = `表 ${table.table_name}`;
    const columns = table.columns ?? [];
    const orders = columns.map((column) => column.display_order).sort((left, right) => left - right);
    if (orders.some((value, index) => value !== index)) throw new ComparisonDecodeError(`${where} 的 display_order 不是从 0 开始的连续序列`);
    for (const column of columns) {
      if (!PRESENT_IN_VALUES.has(column.present_in)) throw new ComparisonDecodeError(`${where}.${column.name} 的 present_in 无效`);
      if (typeof column.pinned !== "boolean") throw new ComparisonDecodeError(`${where}.${column.name} 的 pinned 无效`);
    }
    const bindings = table.table_content_bindings;
    if (bindings === undefined || bindings === null) throw new ComparisonDecodeError(`${where} 缺少 table_content_bindings`);
    const refs = table.table_refs as Record<string, unknown> | undefined;
    for (const side of ["before", "current", "browse"] as const) {
      const reference = refs?.[side === "browse" ? "browse_table_ref" : `${side}_table_ref`] ?? null;
      if ((bindings[side] == null) !== (reference == null)) throw new ComparisonDecodeError(`${where} 的 ${side} 绑定与表引用空值不一致`);
      tableRef(bundle, reference, `${where}.${side}_table_ref`);
    }
    tableRef(bundle, table.records_refs?.records_ref, `${where}.records_ref`);
    tableRef(bundle, table.ordered_extension?.ordered_records_ref, `${where}.ordered_records_ref`);
    tableRef(bundle, table.risk_refs?.annotation_ref, `${where}.annotation_ref`);
    tableRef(bundle, table.row_locator_ref, `${where}.row_locator_ref`);
  }
  tableRef(bundle, surface.refs?.risk_report_ref, "surface.risk_report_ref");
  tableRef(bundle, surface.refs?.project_identity_assessment_ref, "surface.project_identity_assessment_ref");
  for (const projection of surface.projections ?? []) {
    tableRef(bundle, projection.projection_ref, `projection.${projection.projection_kind}.projection_ref`);
    tableRef(bundle, projection.diagnostics_ref, `projection.${projection.projection_kind}.diagnostics_ref`);
  }
}

function resolveTableArtifactPaths(bundle: InstalledBundle, pairId: string, table: SurfaceTable): TableArtifactPaths {
  const bindings = physicalEntries(bundle).filter((entry) => entry.kind === "SNAPSHOT_TABLE");
  const bySide = (side: SnapshotSide) => {
    const ref = side === "before" ? table.table_refs?.before_table_ref : side === "current" ? table.table_refs?.current_table_ref : table.table_refs?.browse_table_ref;
    const referencedPath = entryPathByArtifactId(bundle, ref);
    if (referencedPath) return referencedPath;
    return bindings.find((entry) => entry.table_bindings?.some((binding) => binding.pair_id === pairId && binding.table_name === table.table_name && binding.side === side))?.logical_path ?? null;
  };
  return {
    before: bySide("before"),
    current: bySide("current"),
    browse: bySide("browse"),
    records: entryPathByArtifactId(bundle, table.records_refs?.records_ref),
    orderedRecords: entryPathByArtifactId(bundle, table.ordered_extension?.ordered_records_ref),
    blankRecords: physicalEntries(bundle)
      .filter((entry) => entry.kind === "RECORDS" && entry.pair_id === pairId && entry.table_name === table.table_name && entry.logical_path.includes("/blank/"))
      .map((entry) => entry.logical_path),
    rowLocator: entryPathByArtifactId(bundle, table.row_locator_ref),
    annotations: entryPathByArtifactId(bundle, table.risk_refs?.annotation_ref),
  };
}

/** Loads all view metadata from the verified local bundle before any table rows are requested. */
export async function loadComparisonPresentation(bundle: InstalledBundle, pairId: string): Promise<LocalComparisonPresentation> {
  const surfaceEntry = pairArtifact(bundle, "SURFACE", pairId);
  if (!surfaceEntry) throw new ComparisonDecodeError(`bundle 缺少比较 surface：${pairId}`);
  const surface = await readJsonArtifact<ComparisonSurface>(bundle, surfaceEntry.logical_path);
  validateSurface(bundle, surface);
  const reportPath = entryPathByArtifactId(bundle, surface.refs?.risk_report_ref)
    ?? pairArtifact(bundle, "RISK_REPORT", pairId)?.logical_path;
  const riskReport = reportPath ? await readJsonArtifact<RiskReport>(bundle, reportPath) : undefined;
  const identityPath = entryPathByArtifactId(bundle, surface.refs?.project_identity_assessment_ref);
  const projectIdentityAssessment = identityPath ? await readJsonArtifact<Record<string, unknown>>(bundle, identityPath) : undefined;
  const navigationProjections = (surface.projections ?? []).filter((projection) => projection.projection_kind === "BUSINESS_NAVIGATION");
  if (navigationProjections.length !== 1) {
    throw new ComparisonDecodeError(`比较 surface 必须且只能包含一个业务导航产物：${pairId}（实际 ${navigationProjections.length}）`);
  }
  const navigationProjection = navigationProjections[0];
  const navigationPath = entryPathByArtifactId(bundle, navigationProjection.projection_ref);
  if (!navigationPath) throw new ComparisonDecodeError(`bundle 缺少业务导航产物：${pairId}`);
  const navigation = decodeBusinessNavigation(await readJsonArtifact<unknown>(bundle, navigationPath), surface);
  const diagnosticsPath = entryPathByArtifactId(bundle, navigationProjection?.diagnostics_ref);
  const navigationDiagnosticsDocument = diagnosticsPath
    ? await readJsonArtifact<NavigationDiagnosticsDocument>(bundle, diagnosticsPath)
    : undefined;
  const viewDiagnostics = surface.view && typeof surface.view === "object"
    ? (surface.view as Record<string, unknown>).diagnostics_summary
    : undefined;
  const surfaceDiagnostics = Array.isArray(surface.diagnostics?.diagnostics_summary)
    ? surface.diagnostics.diagnostics_summary
    : Array.isArray(viewDiagnostics) ? viewDiagnostics.filter((value): value is string => typeof value === "string") : [];
  const tableArtifacts = new Map(surface.tables.map((table) => [table.table_name, resolveTableArtifactPaths(bundle, pairId, table)]));
  return {
    pairId,
    surface,
    navigation,
    navigationDiagnostics: navigationDiagnosticsDocument?.diagnostics ?? [],
    surfaceDiagnostics,
    riskReport,
    projectIdentityAssessment,
    view: deriveBundleView({ surface, navigation, riskReport }),
    tableArtifacts,
  };
}

/** Opens a selected table from OPFS; no backend request is possible through this path. */
export async function readLocalTable(
  bundle: InstalledBundle,
  presentation: LocalComparisonPresentation,
  tableName: string,
  side: SnapshotSide,
  request: ParquetReadRequest = {},
) {
  const paths = presentation.tableArtifacts.get(tableName);
  if (!paths) throw new Error(`surface 中没有表 ${tableName}`);
  const path = paths[side] ?? (side === "browse" ? paths.current ?? paths.before : null);
  if (!path) throw new Error(`${tableName} 没有可浏览的 ${side} 侧表产物`);
  return readParquetTable(bundle, path, request);
}

export async function readLocalChangeRecords(
  bundle: InstalledBundle,
  presentation: LocalComparisonPresentation,
  tableName: string,
  request: ParquetReadRequest = {},
): Promise<RowDiffRecord[]> {
  const paths = presentation.tableArtifacts.get(tableName);
  if (!paths) return [];
  const [standardRows, orderedRows, ...blankRows] = await Promise.all([
    paths.records ? readParquetTable(bundle, paths.records, request) : Promise.resolve([]),
    paths.orderedRecords ? readParquetTable(bundle, paths.orderedRecords, request) : Promise.resolve([]),
    ...paths.blankRecords.map((path) => readParquetTable(bundle, path, request)),
  ]);
  const surfaceTable = presentation.surface.tables.find((table) => table.table_name === tableName);
  const hasComparisonKeys = (surfaceTable?.compare?.compare_key_columns?.length ?? 0) > 0;
  const selectedRows = [...selectChangeRecordRows(standardRows, orderedRows, hasComparisonKeys), ...blankRows.flat()];
  return selectedRows.map((row) => row as unknown as RowDiffRecord);
}

export function selectChangeRecordRows(
  standardRows: RowDiffRecord[],
  orderedRows: RowDiffRecord[],
  hasComparisonKeys: boolean,
): RowDiffRecord[] {
  const hasStandardRowRecords = standardRows.some((row) =>
    typeof row.record_kind === "string" && /^(ROW_ADDED|ROW_DELETED|ROW_MODIFIED)$/.test(row.record_kind));
  const orderedRecords = orderedRows.filter((row) => typeof row.record_kind === "string" && row.record_kind.startsWith("ORDERED_ROW_"));
  const useOrderedRows = orderedRecords.length > 0 && (!hasStandardRowRecords || !hasComparisonKeys);
  if (useOrderedRows) return orderedRows;
  // Standard identities avoid duplicate rows; keep ordered movement records because they
  // carry a distinct positional change that standard row records cannot represent.
  const movements = hasStandardRowRecords && hasComparisonKeys
    ? orderedRecords.filter((row) => row.record_kind === "ORDERED_ROW_MOVED")
    : [];
  return [...standardRows, ...movements];
}

/** Reads the table-scoped annotation document from the installed local bundle only. */
export async function readLocalRiskAnnotations(
  bundle: InstalledBundle,
  presentation: LocalComparisonPresentation,
  tableName: string,
): Promise<RiskAnnotation[]> {
  const paths = presentation.tableArtifacts.get(tableName);
  if (!paths) throw new Error(`surface 中没有表 ${tableName}`);
  if (!paths.annotations) return [];
  const document = await readJsonArtifact<RiskAnnotationDocument>(bundle, paths.annotations);
  if (document.table_name !== tableName || !Array.isArray(document.annotations)) {
    throw new Error(`单表风险标注产物与表 ${tableName} 不匹配`);
  }
  return document.annotations;
}
