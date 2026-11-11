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

export type ColumnPresentIn = "BEFORE" | "CURRENT" | "BOTH";

export interface SurfaceColumn {
  name: string;
  display_name: string;
  scalar_type: string | null;
  nullable: boolean;
  /** Which side physically has this column; a missing side renders 该侧无此列. */
  present_in: ColumnPresentIn;
  /** Contiguous 0-based union order; the frontend never re-derives it from names. */
  display_order: number;
  pinned: boolean;
}

/** Columns in their business order; guards against a non-contiguous decode. */
export function orderedColumns(table: SurfaceTable): SurfaceColumn[] {
  return [...(table.columns ?? [])].sort((left, right) => left.display_order - right.display_order);
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
  /** Per-side physical content identity; each side is null exactly when its table ref is null. */
  table_content_bindings?: {
    before?: Record<string, unknown> | null;
    current?: Record<string, unknown> | null;
    browse?: Record<string, unknown> | null;
  };
  /** Typed 5-column row locator; null when the table publishes no ordinary row records. */
  row_locator_ref?: ArtifactReference | null;
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

export const NAVIGATION_CONTRACT_VERSION = "backend-vnext/business-navigation/v1";

export type NavigationBasis = "EXACT" | "TABLE_FALLBACK";

export interface NavigationTableScope {
  change: boolean;
  risk_level: RiskLevel | null;
}

export interface NavigationFacts {
  basis?: NavigationBasis | null;
  change_kind?: ChangeKind | null;
  risk_level?: RiskLevel | null;
  before_row_count?: number | null;
  current_row_count?: number | null;
  /** Table-level change/risk marker; it summarizes the table and is never painted on rows. */
  table_scope?: NavigationTableScope | null;
}

/** One side of a typed set predicate; null means the side contributes no matching identity. */
export interface NavigationPredicate {
  column: string;
  values: Array<string | number>;
}

export interface NavigationRowFilter {
  before: NavigationPredicate | null;
  current: NavigationPredicate | null;
}

export interface NavigationTab {
  tab_key: string;
  label: string;
  table_id: string;
  row_filter: NavigationRowFilter | null;
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

export interface DerivedReplacementSide {
  before: DerivedNavigationGroup[];
  current: DerivedNavigationGroup[];
}

export interface ReplacementNavigationSide {
  before: NavigationGroup[];
  current: NavigationGroup[];
}

export interface BusinessNavigation {
  contract_version: string;
  groups: NavigationGroup[];
  /** Non-null exactly for DATASET_REPLACEMENT; each side owns its own key space. */
  replacement_sides: ReplacementNavigationSide | null;
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
  /** True when the table publishes a typed 5-column row locator. */
  hasRowLocator: boolean;
  /** Table-level change/risk marker from the whole-table tab, if any. */
  tableScope: NavigationTableScope | null;
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
  /** Non-null exactly for DATASET_REPLACEMENT; each side owns its own groups. */
  replacementSides: DerivedReplacementSide | null;
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
      columns: orderedColumns(table),
      rowCounts: { before: rowCount(table, "before"), current: rowCount(table, "current") },
      hasRecords: table.records_refs?.records_format === "PARQUET" || table.records_refs?.records_ref != null,
      hasRowLocator: table.row_locator_ref != null,
      tableScope: null,
    });
  }
  return result;
}

/** Raised when a bundle payload violates the presentation Contract. */
export class ComparisonDecodeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ComparisonDecodeError";
  }
}

function reject(message: string): never {
  throw new ComparisonDecodeError(message);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const NAVIGATION_BASES: ReadonlySet<string> = new Set(["EXACT", "TABLE_FALLBACK"]);

function decodePredicate(value: unknown, where: string): NavigationPredicate {
  if (!isRecord(value)) reject(`${where} 不是对象`);
  const column = value.column;
  if (typeof column !== "string" || column.length === 0) reject(`${where} 缺少列`);
  const rawValues = value.values;
  if (!Array.isArray(rawValues) || rawValues.length === 0) reject(`${where} 的 values 为空`);
  const allNumbers = rawValues.every((item) => typeof item === "number");
  const allStrings = rawValues.every((item) => typeof item === "string");
  if (!allNumbers && !allStrings) reject(`${where} 的 values 类型不一致`);
  const seen = new Set<string | number>();
  const values: Array<string | number> = [];
  let previous: string | number | null = null;
  for (const item of rawValues) {
    if (typeof item === "number") {
      if (!Number.isSafeInteger(item)) reject(`${where} 的整数值超出安全范围`);
    } else if (typeof item === "string") {
      if (item.length === 0) reject(`${where} 的字符串值为空`);
    } else {
      reject(`${where} 的 values 类型不一致`);
    }
    if (seen.has(item)) reject(`${where} 的 values 重复`);
    seen.add(item);
    if (previous !== null) {
      const ordered = typeof previous === typeof item && item > previous;
      if (!ordered) reject(`${where} 的 values 未按规范排序`);
    }
    previous = item;
    values.push(item);
  }
  return { column, values };
}

function decodeRowFilter(value: unknown, where: string): NavigationRowFilter | null {
  if (value === null || value === undefined) return null;
  if (!isRecord(value)) reject(`${where} 的 row_filter 不是对象`);
  const before = value.before === null || value.before === undefined ? null : decodePredicate(value.before, `${where}.before`);
  const current = value.current === null || value.current === undefined ? null : decodePredicate(value.current, `${where}.current`);
  if (before === null && current === null) reject(`${where} 的 row_filter 两侧都为空`);
  return { before, current };
}

function decodeTableScope(value: unknown, where: string): NavigationTableScope | null {
  if (value === null || value === undefined) return null;
  if (!isRecord(value) || typeof value.change !== "boolean") reject(`${where} 的 table_scope 无效`);
  const risk = value.risk_level ?? null;
  if (risk !== null && typeof risk !== "string") reject(`${where} 的 table_scope.risk_level 无效`);
  return { change: value.change, risk_level: risk as RiskLevel | null };
}

function decodeFacts(value: unknown, where: string): NavigationFacts | null {
  if (value === null || value === undefined) return null;
  if (!isRecord(value)) reject(`${where} 的 facts 不是对象`);
  const basis = value.basis ?? null;
  if (basis !== null && (typeof basis !== "string" || !NAVIGATION_BASES.has(basis))) reject(`${where} 的 facts.basis 无效`);
  return {
    basis: basis as NavigationBasis | null,
    change_kind: (value.change_kind ?? null) as ChangeKind | null,
    risk_level: (value.risk_level ?? null) as RiskLevel | null,
    before_row_count: typeof value.before_row_count === "number" ? value.before_row_count : null,
    current_row_count: typeof value.current_row_count === "number" ? value.current_row_count : null,
    table_scope: decodeTableScope(value.table_scope, where),
  };
}

function decodeGroups(value: unknown, tables: Map<string, SurfaceTable>, where: string): NavigationGroup[] {
  if (!Array.isArray(value)) reject(`${where} 不是数组`);
  const groupKeys = new Set<string>();
  const perTable = new Map<string, Array<{ groupKey: string; tab: NavigationTab }>>();
  const groups: NavigationGroup[] = [];
  for (const [groupIndex, rawGroup] of value.entries()) {
    if (!isRecord(rawGroup)) reject(`${where}[${groupIndex}] 不是对象`);
    const groupKey = rawGroup.group_key;
    if (typeof groupKey !== "string" || groupKey.length === 0) reject(`${where}[${groupIndex}] 缺少 group_key`);
    if (groupKeys.has(groupKey)) reject(`${where} 的 group_key 重复：${groupKey}`);
    groupKeys.add(groupKey);
    if (!Array.isArray(rawGroup.items)) reject(`${where}.${groupKey}.items 不是数组`);
    const itemKeys = new Set<string>();
    const items: NavigationItem[] = [];
    for (const [itemIndex, rawItem] of rawGroup.items.entries()) {
      if (!isRecord(rawItem)) reject(`${where}.${groupKey}[${itemIndex}] 不是对象`);
      const itemKey = rawItem.item_key;
      if (typeof itemKey !== "string" || itemKey.length === 0) reject(`${where}.${groupKey}[${itemIndex}] 缺少 item_key`);
      if (itemKeys.has(itemKey)) reject(`${where}.${groupKey} 的 item_key 重复：${itemKey}`);
      itemKeys.add(itemKey);
      if (!Array.isArray(rawItem.tabs)) reject(`${where}.${groupKey}.${itemKey}.tabs 不是数组`);
      const tabKeys = new Set<string>();
      const tabs: NavigationTab[] = [];
      for (const [tabIndex, rawTab] of rawItem.tabs.entries()) {
        if (!isRecord(rawTab)) reject(`${where}.${groupKey}.${itemKey}[${tabIndex}] 不是对象`);
        const tabKey = rawTab.tab_key;
        if (typeof tabKey !== "string" || tabKey.length === 0) reject(`${where}.${groupKey}.${itemKey}[${tabIndex}] 缺少 tab_key`);
        if (tabKeys.has(tabKey)) reject(`${where}.${groupKey}.${itemKey} 的 tab_key 重复：${tabKey}`);
        tabKeys.add(tabKey);
        const tableId = rawTab.table_id;
        if (typeof tableId !== "string" || !tables.has(tableId)) reject(`导航引用了未发布的表：${String(tableId)}`);
        const tab: NavigationTab = {
          tab_key: tabKey,
          label: typeof rawTab.label === "string" && rawTab.label.length > 0 ? rawTab.label : tabKey,
          table_id: tableId,
          row_filter: decodeRowFilter(rawTab.row_filter, `${where}.${groupKey}.${itemKey}.${tabKey}`),
          facts: decodeFacts(rawTab.facts, `${where}.${groupKey}.${itemKey}.${tabKey}`),
        };
        const entries = perTable.get(tableId) ?? [];
        entries.push({ groupKey, tab });
        perTable.set(tableId, entries);
        tabs.push(tab);
      }
      items.push({
        item_key: itemKey,
        item_kind: typeof rawItem.item_kind === "string" ? rawItem.item_kind : "TABLE",
        label: typeof rawItem.label === "string" && rawItem.label.length > 0 ? rawItem.label : itemKey,
        attributes: isRecord(rawItem.attributes) ? (rawItem.attributes as NavigationItem["attributes"]) : undefined,
        tabs,
      });
    }
    groups.push({ group_key: groupKey, label: typeof rawGroup.label === "string" ? rawGroup.label : groupKey, items });
  }
  for (const [tableId, entries] of perTable) {
    const wholeTable = entries.filter((entry) => entry.tab.row_filter === null);
    if (wholeTable.length > 1) reject(`表 ${tableId} 有多个整表页签`);
    if (wholeTable.length === 1 && entries.length > 1) reject(`表 ${tableId} 的整表页签与筛选页签同时存在`);
    const filterTabs = entries.filter((entry) => entry.tab.row_filter !== null);
    if (filterTabs.length > 1) {
      if (new Set(entries.map((entry) => entry.groupKey)).size > 1) reject(`表 ${tableId} 的筛选页签不在同一分组`);
      if (new Set(filterTabs.map((entry) => entry.tab.facts?.basis ?? null)).size > 1) reject(`表 ${tableId} 的筛选页签 facts.basis 不一致`);
    }
  }
  return groups;
}

/** Strict decode of the single business navigation artifact belonging to a pair. */
export function decodeBusinessNavigation(input: unknown, surface: ComparisonSurface): BusinessNavigation {
  if (!isRecord(input)) reject("business navigation 不是对象");
  if (input.contract_version !== NAVIGATION_CONTRACT_VERSION) {
    reject(`不支持的 business navigation contract version：${String(input.contract_version)}`);
  }
  const tables = new Map(surface.tables.map((table) => [table.table_name, table]));
  const groups = decodeGroups(input.groups, tables, "groups");
  const replacementRaw = input.replacement_sides ?? null;
  let replacementSides: ReplacementNavigationSide | null = null;
  if (replacementRaw !== null) {
    if (!isRecord(replacementRaw)) reject("replacement_sides 不是对象");
    if (surface.comparison_mode !== "DATASET_REPLACEMENT") reject("非替换模式下出现 replacement_sides");
    if (groups.length > 0) reject("替换模式的 groups 必须为空");
    replacementSides = {
      before: decodeGroups(replacementRaw.before, tables, "replacement_sides.before"),
      current: decodeGroups(replacementRaw.current, tables, "replacement_sides.current"),
    };
  } else if (surface.comparison_mode === "DATASET_REPLACEMENT") {
    reject("替换模式缺少 replacement_sides");
  }
  return { contract_version: NAVIGATION_CONTRACT_VERSION, groups, replacement_sides: replacementSides };
}

function deriveGroups(groups: NavigationGroup[], tables: Map<string, DerivedTable>): DerivedNavigationGroup[] {
  return groups.map((group) => ({
    groupKey: group.group_key,
    label: group.label || group.group_key,
    items: group.items.map((item) => {
      const tabs = item.tabs.map((tab) => ({
        tabKey: tab.tab_key,
        label: tab.label,
        tableName: tab.table_id,
        rowFilter: tab.row_filter,
        facts: tab.facts ?? null,
        table: tables.get(tab.table_id) ?? null,
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
}

function mergeReplacementGroups(sides: { before: DerivedNavigationGroup[]; current: DerivedNavigationGroup[] }): DerivedNavigationGroup[] {
  const groups = new Map<string, DerivedNavigationGroup>();
  for (const side of [sides.before, sides.current]) {
    for (const group of side) {
      const target = groups.get(group.groupKey) ?? { ...group, items: [] as DerivedNavigationGroup["items"] };
      groups.set(group.groupKey, target);
      for (const item of group.items) {
        const existing = target.items.find((candidate) => candidate.itemKey === item.itemKey);
        if (existing === undefined) {
          target.items.push({ ...item, tabs: [...item.tabs] });
          continue;
        }
        for (const tab of item.tabs) {
          const sameTable = existing.tabs.find((candidate) => candidate.tableName === tab.tableName && candidate.tableName !== "");
          if (sameTable === undefined) existing.tabs.push(tab);
          else sameTable.rowFilter ??= tab.rowFilter;
        }
        existing.showTabs = existing.tabs.length > 1;
      }
    }
  }
  return [...groups.values()];
}

export function deriveBundleView(input: {
  surface: ComparisonSurface;
  navigation: BusinessNavigation;
  riskReport?: RiskReport;
}): DerivedBundleView {
  const tableMap = tableProjection(input.surface, input.riskReport);
  const sides = input.navigation.replacement_sides;
  const replacementSides = sides === null ? null : {
    before: deriveGroups(sides.before, tableMap),
    current: deriveGroups(sides.current, tableMap),
  };
  // Replacement navigation keeps `groups` empty; the sidebar still needs one
  // selectable tree, so both sides are merged by group/item and their tabs are
  // unioned by table. The side toggle decides which rows the table shows.
  const groups = replacementSides === null
    ? deriveGroups(input.navigation.groups, tableMap)
    : mergeReplacementGroups(replacementSides);
  const scopes = replacementSides === null ? groups : [...replacementSides.before, ...replacementSides.current];
  for (const group of scopes) {
    for (const item of group.items) {
      for (const tab of item.tabs) {
        if (tab.rowFilter !== null || tab.table === null || tab.facts?.table_scope == null) continue;
        tab.table.tableScope = tab.facts.table_scope;
      }
    }
  }
  return { groups, tables: [...tableMap.values()], replacementSides, diagnostics: [] };
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
      beforeFormula: oldRow?.formula_ast_json ?? null,
      currentFormula: newRow?.formula_ast_json ?? (input.mode === "PREVIEW" && deleted ? oldRow?.formula_ast_json ?? null : null),
      changed: changed && !deleted,
      deleted,
      formulaChanged: isPreviewChanged,
      label: isPreviewChanged ? "公式已改" : null,
    };
  });
}
