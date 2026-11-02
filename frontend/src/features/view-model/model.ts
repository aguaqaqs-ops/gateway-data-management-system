export type ComparisonMode = "PREVIEW" | "HISTORY" | "DATASET_REPLACEMENT";
export type ChangeKind = "UNCHANGED" | "ADDED" | "DELETED" | "UPDATED" | "SCHEMA_CHANGED" | string;
export type RiskLevel = "HIGH" | "MEDIUM_HIGH" | "MEDIUM_LOW" | "LOW" | "UNKNOWN";

export interface SurfaceColumn {
  name: string;
  display_name?: string | null;
  data_type?: string | null;
  nullable?: boolean;
  pinned?: boolean;
  display_order?: number;
}

export interface SurfaceTable {
  table_id?: string;
  table_name: string;
  display_name?: string;
  table_status?: string;
  change_kind?: ChangeKind;
  columns?: SurfaceColumn[];
  row_change_stats?: Record<string, number | null>;
  records_refs?: { records_format?: string; records_ref?: unknown };
  table_refs?: { before_table_ref?: unknown; current_table_ref?: unknown; browse_table_ref?: unknown };
  risk_refs?: { risk_level?: RiskLevel | null; annotation_count?: number };
  display?: { strategy?: string; layout?: string };
  compare?: { keys?: string[] };
}

export interface ComparisonSurface {
  surface_contract_version?: string;
  direction?: string;
  comparison_mode?: string;
  view?: { view_key?: string; label?: string };
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
  diagnostics?: unknown[];
}

export interface RiskTableReport {
  table_name: string;
  risk_level?: RiskLevel | null;
  reason_codes?: string[];
  annotation_count?: number;
  annotations?: Array<{ row_identity?: string | null; risk_level?: RiskLevel; reason_codes?: string[] }>;
}

export interface RiskReport {
  risk_report_contract_version?: string;
  overall?: { risk_level?: RiskLevel | null; annotation_count?: number };
  tables: RiskTableReport[];
}

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

function rowCount(table: SurfaceTable, key: string): number | null {
  const candidates = key === "before" ? ["row_count_before", "before_row_count"] : ["row_count_current", "current_row_count"];
  for (const candidate of candidates) {
    const value = table.row_change_stats?.[candidate];
    if (typeof value === "number") return value;
  }
  return null;
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
      columns: [...(table.columns ?? [])].sort((left, right) => (left.display_order ?? Number.MAX_SAFE_INTEGER) - (right.display_order ?? Number.MAX_SAFE_INTEGER)),
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
  const diagnostics = Array.isArray(navigation.diagnostics) ? navigation.diagnostics.map(diagnosticText) : [];
  return { value: { ...navigation, groups }, diagnostics };
}

function diagnosticText(value: unknown): string {
  if (typeof value === "string") return value;
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const item = value as Record<string, unknown>;
    const code = typeof item.code === "string" ? item.code : null;
    const message = typeof item.message === "string" ? item.message : null;
    if (code && message) return `${code}: ${message}`;
    if (message) return message;
  }
  try { return JSON.stringify(value) ?? String(value); } catch { return String(value); }
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

export interface RowDiffRecord {
  table_name: string;
  record_kind: string;
  row_identity?: Uint8Array | string | null;
  changed_columns?: string[];
  before_values?: unknown[];
  current_values?: unknown[];
  field_changes?: unknown[];
  diagnostics?: string[];
}

export interface RiskAnnotation {
  row_identity?: Uint8Array | string | null;
  risk_level?: RiskLevel;
  reason_codes?: string[];
}

export interface ChangeLocation {
  index: number;
  rowIdentity: string | null;
  recordKind: string;
  riskLevel: RiskLevel | null;
}

function identityKey(identity: Uint8Array | string | null | undefined): string | null {
  if (identity == null) return null;
  if (typeof identity === "string") return identity;
  return Array.from(identity, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function deriveChangeLocations(records: RowDiffRecord[], annotations: RiskAnnotation[] = []): ChangeLocation[] {
  const risks = new Map(annotations.map((annotation) => [identityKey(annotation.row_identity), annotation.risk_level ?? null]));
  return records.filter((record) => record.record_kind !== "UNCHANGED" && record.record_kind !== "UNCHANGED_RANGE").map((record, index) => {
    const rowIdentity = identityKey(record.row_identity);
    return { index: index + 1, rowIdentity, recordKind: record.record_kind, riskLevel: risks.get(rowIdentity) ?? null };
  });
}

export function filterChangedRows<T extends Record<string, unknown>>(rows: T[], criteria: {
  onlyInteresting?: boolean;
  search?: string;
  changeKinds?: Set<string>;
  rowRisk?: ReadonlyMap<string, RiskLevel>;
  rowIdentityColumn?: string;
}): T[] {
  const query = criteria.search?.trim().toLocaleLowerCase();
  return rows.filter((row) => {
    const changed = Boolean(row.record_kind && row.record_kind !== "UNCHANGED" && row.record_kind !== "UNCHANGED_RANGE");
    const identity = criteria.rowIdentityColumn ? identityKey(row[criteria.rowIdentityColumn] as Uint8Array | string | null | undefined) : null;
    const risky = identity !== null && criteria.rowRisk?.has(identity);
    if (criteria.onlyInteresting && !changed && !risky) return false;
    if (criteria.changeKinds?.size && !criteria.changeKinds.has(String(row.record_kind ?? ""))) return false;
    return !query || Object.values(row).some((value) => String(value ?? "").toLocaleLowerCase().includes(query));
  });
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
  beforeDeviceName: string | null;
  currentDeviceName: string | null;
  beforeFormula: unknown | null;
  currentFormula: unknown | null;
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
  changedPointKeys?: Set<string>;
  deletedPointKeys?: Set<string>;
}): FormulaDisplay[] {
  const keyOf = (row: FormulaSourceRow) => `${String(row.source_table ?? "")}:${String(row.point_gid ?? "")}`;
  const before = new Map(input.before.map((row) => [keyOf(row), row]));
  const current = new Map(input.current.map((row) => [keyOf(row), row]));
  const keys = new Set([...before.keys(), ...current.keys()]);
  return [...keys].sort().map((key) => {
    const oldRow = before.get(key);
    const newRow = current.get(key);
    const deleted = input.deletedPointKeys?.has(key) ?? (!newRow && Boolean(oldRow));
    const changed = input.changedPointKeys?.has(key) ?? Boolean(oldRow && newRow && oldRow.formula_digest !== newRow.formula_digest);
    const isPreviewChanged = input.mode === "PREVIEW" && changed && !deleted;
    return {
      pointKey: key,
      beforeDeviceName: oldRow ? deviceName(oldRow.dev_addr, input.beforeDevices ?? []) : null,
      currentDeviceName: newRow ? deviceName(newRow.dev_addr, input.currentDevices ?? []) : null,
      beforeFormula: input.mode === "HISTORY" || deleted ? oldRow?.formula_ast_json ?? null : null,
      currentFormula: newRow?.formula_ast_json ?? null,
      formulaChanged: isPreviewChanged,
      label: isPreviewChanged ? "公式已改" : null,
    };
  });
}

export function applyNavigationRowFilter<T extends Record<string, unknown>>(rows: T[], rowFilter: NavigationTab["row_filter"]): T[] {
  if (!rowFilter) return rows;
  return rows.filter((row) => String(row[rowFilter.column] ?? "") === String(rowFilter.value));
}
