export type ComparisonMode = "PREVIEW" | "REVIEW" | "HISTORY" | "DATASET_REPLACEMENT";
/** Surface change kinds summarize a table, not an individual records row. */
export type ChangeKind = "UNCHANGED" | "ADDED" | "DELETED" | "UPDATED" | "SCHEMA_CHANGED" | string;
export type RiskLevel = "HIGH" | "MEDIUM_HIGH" | "MEDIUM_LOW" | "LOW" | "UNKNOWN";

export type RowRecordKind =
  | "ROW_ADDED"
  | "ROW_DELETED"
  | "ROW_MODIFIED"
  | "ORDERED_ROW_ADDED"
  | "ORDERED_ROW_DELETED"
  | "ORDERED_ROW_MODIFIED"
  | "ORDERED_ROW_MOVED";
export type TableRecordKind = "SCHEMA_CHANGE" | "TABLE_DEGRADED" | "ORDERED_TABLE_DEGRADED";
export type BlankRecordKind = "BLANK_DELETE_INTERVAL" | "BLANK_INSERT_INTERVAL";
export type RecordKind = RowRecordKind | TableRecordKind | BlankRecordKind;

const ROW_RECORD_KINDS: ReadonlySet<string> = new Set([
  "ROW_ADDED",
  "ROW_DELETED",
  "ROW_MODIFIED",
  "ORDERED_ROW_ADDED",
  "ORDERED_ROW_DELETED",
  "ORDERED_ROW_MODIFIED",
  "ORDERED_ROW_MOVED",
]);
const TABLE_RECORD_KINDS: ReadonlySet<string> = new Set([
  "SCHEMA_CHANGE",
  "TABLE_DEGRADED",
  "ORDERED_TABLE_DEGRADED",
]);
function isRowRecordKind(value: unknown): value is RowRecordKind {
  return typeof value === "string" && ROW_RECORD_KINDS.has(value) && !TABLE_RECORD_KINDS.has(value);
}

export interface SurfaceColumn {
  name: string;
  display_name: string;
  scalar_type: string | null;
  nullable: boolean;
}

export interface ArtifactReference {
  artifact_id: string;
  media_type: string;
  raw_sha256: string;
  size_bytes: number;
}

export interface SurfaceTable {
  table_id: string;
  table_name: string;
  display_name: string;
  table_status: string;
  change_kind?: ChangeKind;
  columns?: SurfaceColumn[];
  row_change_stats?: {
    row_added_count?: number;
    row_count_before?: number | null;
    row_count_current?: number | null;
    row_deleted_count?: number;
    row_modified_count?: number;
    suppressed_added_count?: number;
    suppressed_deleted_count?: number;
  };
  records_refs?: {
    records_format?: string;
    records_manifest_ref?: ArtifactReference | null;
    records_ref?: ArtifactReference | null;
  };
  table_refs?: {
    before_table_ref?: ArtifactReference | null;
    current_table_ref?: ArtifactReference | null;
    browse_table_ref?: ArtifactReference | null;
  };
  risk_refs?: {
    risk_level?: RiskLevel | null;
    reason_codes?: string[];
    annotation_count?: number;
    report_ref?: ArtifactReference | null;
    annotation_ref?: ArtifactReference | null;
    annotation_manifest_ref?: ArtifactReference | null;
  };
  display?: { replay_guarantee?: string; strategy?: string; table_processing_mode?: string };
  compare?: {
    artifact_scope?: string | null;
    compare_key_columns?: string[];
    effective_columns?: string[];
    ignored_columns?: string[];
    projection_logical_digest?: string | null;
    projection_schema_digest?: string | null;
    provider?: string | null;
  };
  diagnostics?: { diagnostics_ref?: ArtifactReference | null; diagnostics_summary?: string[] };
  schema_summary?: Record<string, unknown> | null;
  content_changed?: boolean;
  replacement_summary?: Record<string, unknown> | null;
  ordered_extension?: Record<string, unknown> | null;
}

export interface ComparisonSurface {
  comparison_digest?: string;
  comparison_mode?: string;
  surface_contract_version?: string;
  direction?: string;
  project_identity_assessment_digest?: string | null;
  project_identity_status?: string;
  projections?: Array<{
    projection_id: string;
    projection_kind: string;
    projection_ref: ArtifactReference;
    projection_digest: string;
    projection_summary?: Array<{ key: string; value: string }>;
    risk_summary_ref?: ArtifactReference | null;
    diagnostics_ref?: ArtifactReference | null;
  }>;
  refs?: {
    diagnostics_ref?: ArtifactReference | null;
    project_identity_assessment_ref?: ArtifactReference | null;
    records_closure_ref?: ArtifactReference | null;
    risk_annotation_closure_ref?: ArtifactReference | null;
    risk_report_ref?: ArtifactReference | null;
  };
  diagnostics?: { diagnostics_ref?: ArtifactReference | null; diagnostics_summary?: string[] };
  requires_submit_confirmation?: boolean;
  reserved_extensions?: Array<{ key: string; value: string }>;
  risk_evaluation_digest?: string | null;
  surface_digest?: string;
  surface_id?: string;
  summary?: Record<string, unknown>;
  view?: Record<string, unknown>;
  tables: SurfaceTable[];
}

export interface NavigationFacts {
  change_kind?: ChangeKind | null;
  risk_level?: RiskLevel | null;
  before_row_count?: number | null;
  current_row_count?: number | null;
}

export interface NavigationTab {
  tab_key: string;
  label: string;
  table_id: string;
  row_filter: { column: string; value: string | number } | null;
  facts?: NavigationFacts | null;
}

export interface NavigationItem {
  item_key: string;
  item_kind: string;
  label: string;
  attributes?: Record<string, string | number | boolean | null>;
  tabs: NavigationTab[];
}

export interface NavigationGroup {
  group_key: string;
  label: string;
  items: NavigationItem[];
}

export interface BusinessNavigation {
  contract_version?: string;
  groups: NavigationGroup[];
}

export interface RiskReason {
  reason_code: string;
  message: string;
  rule_id: string;
  evidence: Array<[string, unknown]>;
}

export interface RiskAnnotationTarget {
  target_type: string;
  row_identity: string | null;
  table_name: string | null;
  before_row_identity: string | null;
  current_row_identity: string | null;
  changed_columns: string[];
  coverage: string | null;
  position: number | null;
  position_range: [number, number] | null;
}

export interface RiskAnnotation {
  annotation_id: string;
  risk_level: RiskLevel;
  reasons: RiskReason[];
  diagnostics: string[];
  target: RiskAnnotationTarget;
}

export interface RiskAnnotationDocument {
  contract_version: string;
  table_name: string;
  annotations: RiskAnnotation[];
}

export interface RiskTableReport {
  table_name: string;
  risk_level: RiskLevel;
  reason_codes: string[];
  annotation_count: number;
  source_table_status: string;
  annotation_ref: ArtifactReference | null;
  diagnostics: string[];
}

export interface RiskSummary {
  risk_level: RiskLevel | null;
  reason_codes: string[];
  table_count: number;
  annotation_count: number;
}

export interface RiskReport {
  risk_report_contract_version: string;
  risk_evaluation_digest: string;
  overall: RiskSummary;
  tables: RiskTableReport[];
  annotation_refs: ArtifactReference[];
  diagnostics: string[];
}

export type RowIdentity = string | ArrayBuffer | ArrayBufferView | null;

export interface DerivedTable {
  tableName: string;
  label: string;
  changeKind: ChangeKind;
  riskLevel: RiskLevel | null;
  annotationCount: number;
  columns: SurfaceColumn[];
  rowCounts: { before: number | null; current: number | null };
  hasRecords: boolean;
}

export interface DerivedNavigationGroup {
  groupKey: string;
  label: string;
  items: Array<{
    itemKey: string;
    itemKind: string;
    label: string;
    attributes: NavigationItem["attributes"];
    tabs: Array<{
      tabKey: string;
      label: string;
      tableName: string;
      rowFilter: NavigationTab["row_filter"];
      facts: NavigationFacts | null;
      table: DerivedTable | null;
    }>;
    showTabs: boolean;
    changeKinds: ChangeKind[];
    riskLevels: RiskLevel[];
  }>;
}

export interface DerivedBundleView {
  groups: DerivedNavigationGroup[];
  tables: DerivedTable[];
  diagnostics: string[];
}

function rowCount(table: SurfaceTable, side: "before" | "current"): number | null {
  const value = side === "before"
    ? table.row_change_stats?.row_count_before
    : table.row_change_stats?.row_count_current;
  return typeof value === "number" ? value : null;
}

function tableProjection(surface: ComparisonSurface, risk?: RiskReport): Map<string, DerivedTable> {
  const result = new Map<string, DerivedTable>();
  for (const table of surface.tables) {
    const name = table.table_name;
    const riskReport = risk?.tables.find((item) => item.table_name === name);
    result.set(name, {
      tableName: name,
      label: table.display_name || name,
      changeKind: table.change_kind ?? table.table_status ?? "UNCHANGED",
      riskLevel: riskReport?.risk_level ?? table.risk_refs?.risk_level ?? null,
      annotationCount: riskReport?.annotation_count ?? table.risk_refs?.annotation_count ?? 0,
      columns: [...(table.columns ?? [])],
      rowCounts: { before: rowCount(table, "before"), current: rowCount(table, "current") },
      hasRecords: table.records_refs?.records_format === "PARQUET" || table.records_refs?.records_ref != null,
    });
  }
  return result;
}

function fallbackNavigation(tables: DerivedTable[]): BusinessNavigation {
  return {
    contract_version: "frontend-placeholder/business-navigation/v1",
    groups: [{
      group_key: "ALL_TABLES",
      label: "全部表",
      items: tables.map((table) => ({
        item_key: `table:${table.tableName}`,
        item_kind: "TABLE",
        label: table.label,
        tabs: [{ tab_key: table.tableName, label: table.label, table_id: table.tableName, row_filter: null }],
      })),
    }],
  };
}

function normalizeNavigation(navigation: BusinessNavigation | undefined, tables: DerivedTable[]): { value: BusinessNavigation; diagnostics: string[] } {
  if (!navigation || !Array.isArray(navigation.groups)) return { value: fallbackNavigation(tables), diagnostics: ["未提供业务导航产物，使用单组全部表占位"] };
  const known = new Set(tables.map((table) => table.tableName));
  const claimed = new Set<string>();
  const groups = navigation.groups.map((group) => ({
    ...group,
    label: group.label || group.group_key,
    items: (group.items ?? []).map((item) => ({
      ...item,
      tabs: (item.tabs ?? []).filter((tab) => {
        if (!known.has(tab.table_id)) return false;
        claimed.add(tab.table_id);
        return true;
      }),
    })),
  }));
  const unclaimed = tables.filter((table) => !claimed.has(table.tableName));
  if (unclaimed.length) {
    let other = groups.find((group) => group.group_key === "OTHER_TABLES");
    if (!other) {
      other = { group_key: "OTHER_TABLES", label: "其他表", items: [] };
      groups.push(other);
    }
    other.items.push(...unclaimed.map((table) => ({
      item_key: `table:${table.tableName}`,
      item_kind: "TABLE",
      label: table.label,
      tabs: [{ tab_key: table.tableName, label: table.label, table_id: table.tableName, row_filter: null }],
    })));
  }
  return { value: { ...navigation, groups }, diagnostics: [] };
}

export function deriveBundleView(input: {
  surface: ComparisonSurface;
  navigation?: BusinessNavigation;
  riskReport?: RiskReport;
}): DerivedBundleView {
  const tableMap = tableProjection(input.surface, input.riskReport);
  const tables = [...tableMap.values()];
  const navigation = normalizeNavigation(input.navigation, tables);
  const groups = navigation.value.groups.map((group) => ({
    groupKey: group.group_key,
    label: group.label || group.group_key,
    items: group.items.map((item) => {
      const tabs = item.tabs.map((tab) => ({
        tabKey: tab.tab_key,
        label: tab.label,
        tableName: tab.table_id,
        rowFilter: tab.row_filter,
        facts: tab.facts ?? null,
        table: tableMap.get(tab.table_id) ?? null,
      }));
      return {
        itemKey: item.item_key,
        itemKind: item.item_kind,
        label: item.label,
        attributes: item.attributes,
        tabs,
        showTabs: tabs.length > 1,
        changeKinds: [...new Set(tabs.map((tab) => tab.rowFilter === null ? tab.table?.changeKind : tab.facts?.change_kind).filter((value): value is ChangeKind => Boolean(value)))],
        riskLevels: [...new Set(tabs.map((tab) => tab.rowFilter === null ? tab.table?.riskLevel : tab.facts?.risk_level).filter((value): value is RiskLevel => Boolean(value)))],
      };
    }),
  }));
  return { groups, tables, diagnostics: navigation.diagnostics };
}

export interface RowDiffRecord extends Record<string, unknown> {
  table_name?: string;
  record_kind?: RecordKind;
  row_identity?: RowIdentity;
  changed_columns?: string[];
  before_values?: RowValue[];
  current_values?: RowValue[];
  field_changes?: FieldChange[];
  diagnostics?: string[];
  semantic_kind?: string;
  entity_key_kind?: string;
  before_position?: number | null;
  current_position?: number | null;
  interval?: Record<string, number | null> | null;
}

export interface RowValue {
  column_name: string;
  value: Record<string, unknown>;
}

export interface FieldChange {
  column_name: string;
  before_value: Record<string, unknown> | null;
  current_value: Record<string, unknown> | null;
}

export interface ChangeLocation {
  index: number;
  rowIdentity: string | null;
  recordKind: RowRecordKind;
  riskLevel: RiskLevel | null;
  position: number | null;
}

function identityKey(identity: RowIdentity | undefined): string | null {
  if (identity == null) return null;
  if (typeof identity === "string") {
    const normalized = identity.toLowerCase();
    if (/^sha256:[0-9a-f]{64}$/.test(normalized)) return normalized;
    if (/^[0-9a-f]{64}$/.test(normalized)) return `sha256:${normalized}`;
    return identity;
  }
  const bytes = identity instanceof ArrayBuffer
    ? new Uint8Array(identity)
    : new Uint8Array(identity.buffer, identity.byteOffset, identity.byteLength);
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `sha256:${hex}`;
}

export function deriveChangeLocations(records: RowDiffRecord[], annotations: RiskAnnotation[] = []): ChangeLocation[] {
  const risks = new Map<string, RiskLevel>();
  for (const annotation of annotations) {
    for (const identity of riskAnnotationRowIdentities(annotation)) risks.set(identity, annotation.risk_level);
  }
  const rowRecords = records.filter((record): record is RowDiffRecord & { record_kind: RowRecordKind } => isRowRecordKind(record.record_kind));
  return rowRecords.map((record, index) => {
    const rowIdentity = identityKey(record.row_identity);
    return {
      index: index + 1,
      rowIdentity,
      recordKind: record.record_kind,
      riskLevel: rowIdentity ? risks.get(rowIdentity) ?? null : null,
      position: typeof record.current_position === "number" ? record.current_position
        : typeof record.before_position === "number" ? record.before_position : null,
    };
  });
}

export function normalizeRowIdentity(identity: RowIdentity | undefined): string | null {
  return identityKey(identity);
}

export function riskAnnotationRowIdentities(annotation: RiskAnnotation): string[] {
  const identities = annotation.target.target_type === "ROW"
    ? [annotation.target.row_identity]
    : annotation.target.target_type === "ROW_PAIR"
      ? [annotation.target.before_row_identity, annotation.target.current_row_identity]
      : [];
  return identities.map((identity) => normalizeRowIdentity(identity ?? undefined))
    .filter((identity): identity is string => identity !== null);
}

export interface FormulaSourceRow {
  source_table?: string;
  point_gid?: string | number;
  dev_addr?: number | string;
  formula_ast_json?: unknown;
  formula_digest?: string;
  description?: string | null;
}

export interface FormulaDisplay {
  pointKey: string;
  pointLabel: string;
  beforeDeviceName: string | null;
  currentDeviceName: string | null;
  beforeDevices: FormulaSourceRow[];
  currentDevices: FormulaSourceRow[];
  beforeFormula: unknown | null;
  currentFormula: unknown | null;
  changed: boolean;
  deleted: boolean;
  formulaChanged: boolean;
  label: string | null;
}

function deviceName(devAddr: number | string | undefined, devices: FormulaSourceRow[]): string {
  const key = String(devAddr ?? "");
  if (key) {
    const matches = devices.filter((device) => String(device.dev_addr ?? "") === key && typeof device.description === "string" && device.description.trim());
    if (matches.length === 1) return matches[0]?.description as string;
  }
  return `Device ${key || "?"}:测点`;
}

export function deriveFormulaDisplays(input: {
  mode: ComparisonMode;
  before: FormulaSourceRow[];
  current: FormulaSourceRow[];
  beforeDevices?: FormulaSourceRow[];
  currentDevices?: FormulaSourceRow[];
  deletedPointKeys?: Set<string>;
}): FormulaDisplay[] {
  const keyOf = (row: FormulaSourceRow) => `${String(row.source_table ?? "")}:${String(row.point_gid ?? "")}`;
  const before = new Map(input.before.map((row) => [keyOf(row), row]));
  const current = new Map(input.current.map((row) => [keyOf(row), row]));
  const keys = new Set([...before.keys(), ...current.keys()]);
  return [...keys].sort().map((key) => {
    const oldRow = before.get(key);
    const newRow = current.get(key);
    const pointId = newRow?.point_gid ?? oldRow?.point_gid ?? "?";
    const deleted = input.deletedPointKeys?.has(key) ?? (!newRow && Boolean(oldRow));
    const changed = Boolean(oldRow && newRow && oldRow.formula_digest !== newRow.formula_digest);
    const isPreviewChanged = input.mode === "PREVIEW" && changed && !deleted;
    return {
      pointKey: key,
      pointLabel: `测点 ${String(pointId)}`,
      beforeDeviceName: oldRow ? deviceName(oldRow.dev_addr, input.beforeDevices ?? []) : null,
      currentDeviceName: newRow ? deviceName(newRow.dev_addr, input.currentDevices ?? []) : null,
      beforeDevices: input.beforeDevices ?? [],
      currentDevices: input.currentDevices ?? [],
      beforeFormula: input.mode === "HISTORY" ? oldRow?.formula_ast_json ?? null : null,
      currentFormula: newRow?.formula_ast_json ?? (input.mode === "PREVIEW" && deleted ? oldRow?.formula_ast_json ?? null : null),
      changed: changed && !deleted,
      deleted,
      formulaChanged: isPreviewChanged,
      label: isPreviewChanged ? "公式已改" : null,
    };
  });
}
