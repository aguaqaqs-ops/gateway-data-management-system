import type { InstalledBundle } from "./local-bundle";
import { readJsonArtifact, readParquetTable, type ParquetReadRequest } from "./parquet-reader";
import type { BundleArtifactEntry } from "./posix-tar";
import { deriveBundleView, type BusinessNavigation, type ComparisonSurface, type DerivedBundleView, type RiskAnnotation, type RiskAnnotationDocument, type RiskReport, type RowDiffRecord, type SurfaceTable } from "../view-model/model";
import type { NavigationDiagnostic, NavigationDiagnosticsDocument } from "../view-model/diagnostics";

export type SnapshotSide = "before" | "current" | "browse";

export interface TableArtifactPaths {
  before: string | null;
  current: string | null;
  browse: string | null;
  records: string | null;
  orderedRecords: string | null;
  blankRecords: string[];
  annotations: string | null;
}

export interface LocalComparisonPresentation {
  pairId: string;
  surface: ComparisonSurface;
  navigation?: BusinessNavigation;
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
    annotations: entryPathByArtifactId(bundle, table.risk_refs?.annotation_ref),
  };
}

/** Loads all view metadata from the verified local bundle before any table rows are requested. */
export async function loadComparisonPresentation(bundle: InstalledBundle, pairId: string): Promise<LocalComparisonPresentation> {
  const surfaceEntry = pairArtifact(bundle, "SURFACE", pairId);
  if (!surfaceEntry) throw new Error(`bundle 缺少比较 surface：${pairId}`);
  const surface = await readJsonArtifact<ComparisonSurface>(bundle, surfaceEntry.logical_path);
  const reportPath = entryPathByArtifactId(bundle, surface.refs?.risk_report_ref)
    ?? pairArtifact(bundle, "RISK_REPORT", pairId)?.logical_path;
  const riskReport = reportPath ? await readJsonArtifact<RiskReport>(bundle, reportPath) : undefined;
  const identityPath = entryPathByArtifactId(bundle, surface.refs?.project_identity_assessment_ref);
  const projectIdentityAssessment = identityPath ? await readJsonArtifact<Record<string, unknown>>(bundle, identityPath) : undefined;
  const projectionRefs = surface.projections ?? [];
  const navigationProjection = projectionRefs.find((projection) => projection.projection_kind === "BUSINESS_NAVIGATION");
  const navigationPath = entryPathByArtifactId(bundle, navigationProjection?.projection_ref);
  const navigation = navigationPath ? await readJsonArtifact<BusinessNavigation>(bundle, navigationPath) : undefined;
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
  const records = await Promise.all([paths.records, paths.orderedRecords, ...paths.blankRecords]
    .filter((path): path is string => Boolean(path))
    .map((path) => readParquetTable(bundle, path, request)));
  return records.flat().map((row) => row as unknown as RowDiffRecord);
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
