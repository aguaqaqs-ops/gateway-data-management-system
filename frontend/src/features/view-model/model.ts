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

export const NAVIGATION_CONTRACT_VERSION = "backend-vnext/business-navigation/v4";

export type NavigationBasis = "EXACT" | "TABLE_FALLBACK";
/** Local change kinds of a filtered tab (Business Navigation v4). */
export type NavigationLocalChangeKind = "UNCHANGED" | "ADDED" | "DELETED" | "UPDATED";

export interface NavigationTableScope {
  change: boolean;
  risk_level: RiskLevel | null;
}

export interface NavigationRowChanges {
  added: number;
  deleted: number;
  /** Includes migrated rows; moved_in/moved_out are subsets, never added on top. */
  modified: number;
  moved_in: number;
  moved_out: number;
}

/**
 * Local facts of one filtered tab. `basis` states only whether the local change
 * is complete; risk and registry membership completeness are separate fields.
 */
export interface NavigationFacts {
  basis: NavigationBasis;
  change_kind: NavigationLocalChangeKind | null;
  risk_level: RiskLevel | null;
  risk_complete: boolean;
  before_row_count: number | null;
  current_row_count: number | null;
  /** Table-level change/risk marker; public to the table, never a device's own result. */
  table_scope: NavigationTableScope | null;
  membership_changed: boolean;
  membership_complete: boolean;
  row_changes: NavigationRowChanges | null;
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

export interface NavigationSummary {
  change_kinds: ChangeKind[];
  risk_level: RiskLevel | null;
  nonempty_tab_count: number;
  change_complete: boolean;
  risk_complete: boolean;
}

export interface NavigationTab {
  tab_key: string;
  empty: boolean;
  label: string;
  table_id: string;
  row_filter: NavigationRowFilter | null;
  facts: NavigationFacts | null;
}

export interface NavigationItem {
  item_key: string;
  item_kind: string;
  label: string;
  attributes: Record<string, string | number>;
  tabs: NavigationTab[];
  summary: NavigationSummary;
}

export interface NavigationGroup {
  group_key: string;
  label: string;
  items: NavigationItem[];
  nonempty_item_count: number;
}

export interface UnlocatedRowRisk {
  risk_level: RiskLevel | null;
  count: number | null;
  reason_codes: string[];
}

/** Public facts of one shared table that belong to no single device. */
export interface NavigationTableNotice {
  table_id: string;
  table_scope: NavigationTableScope | null;
  unlocated_row_risk: UnlocatedRowRisk | null;
  risk_complete: boolean;
}

export interface DeviceDefinitionChange {
  record_identity: string;
  change_kind: "ADDED" | "DELETED" | "UPDATED";
  before_item_key: string | null;
  current_item_key: string | null;
  before_dev_addr: number | null;
  current_dev_addr: number | null;
  risk_level: RiskLevel | null;
  risk_complete: boolean;
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
  table_notices: NavigationTableNotice[];
  device_definition_changes: DeviceDefinitionChange[];
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
}

export interface DerivedNavigationTab {
  tabKey: string;
  empty: boolean;
  label: string;
  tableName: string;
  rowFilter: NavigationTab["row_filter"];
  facts: NavigationFacts | null;
  table: DerivedTable | null;
  /** Public notice of this tab's table; shown beside, never as, the tab's own result. */
  notice: NavigationTableNotice | null;
}

export interface DerivedNavigationGroup {
  nonemptyItemCount: number;
  groupKey: string;
  label: string;
  items: Array<{
    itemKey: string;
    itemKind: string;
    label: string;
    attributes: NavigationItem["attributes"];
    tabs: DerivedNavigationTab[];
    nonemptyTabCount: number;
    showTabs: boolean;
    changeKinds: ChangeKind[];
    riskLevels: RiskLevel[];
    changeComplete: boolean;
    riskComplete: boolean;
  }>;
}

/**
 * What one navigation tab may claim as its own. Every badge, header, filter and
 * count reads this instead of mixing local facts with whole-table results.
 */
export interface TabScope {
  /** WHOLE_TABLE: whole-table entry (or replacement side); LOCAL_*: a filtered device tab. */
  kind: "WHOLE_TABLE" | "LOCAL_EXACT" | "LOCAL_FALLBACK";
  /** null means the local change is unknown (TABLE_FALLBACK). */
  changeKind: ChangeKind | null;
  /** Confirmed risk located in this scope; null does not prove "no risk" unless riskComplete. */
  riskLevel: RiskLevel | null;
  riskComplete: boolean;
  membershipChanged: boolean;
  membershipComplete: boolean;
  rowChanges: NavigationRowChanges | null;
  beforeCount: number | null;
  currentCount: number | null;
  notice: NavigationTableNotice | null;
}

export function tabScope(tab: Pick<DerivedNavigationTab, "rowFilter" | "facts" | "table" | "notice">): TabScope {
  const facts = tab.facts;
  if (facts === null) {
    const whole = tab.rowFilter === null;
    return {
      kind: "WHOLE_TABLE",
      changeKind: tab.table?.changeKind ?? "UNCHANGED",
      riskLevel: tab.table?.riskLevel ?? null,
      riskComplete: true,
      membershipChanged: false,
      membershipComplete: true,
      rowChanges: null,
      beforeCount: whole ? tab.table?.rowCounts.before ?? null : null,
      currentCount: whole ? tab.table?.rowCounts.current ?? null : null,
      notice: tab.notice,
    };
  }
  return {
    kind: facts.basis === "EXACT" ? "LOCAL_EXACT" : "LOCAL_FALLBACK",
    changeKind: facts.basis === "EXACT" ? facts.change_kind : null,
    riskLevel: facts.risk_level,
    riskComplete: facts.risk_complete,
    membershipChanged: facts.membership_changed,
    membershipComplete: facts.membership_complete,
    rowChanges: facts.row_changes,
    beforeCount: facts.before_row_count,
    currentCount: facts.current_row_count,
    notice: tab.notice,
  };
}

/** Local content/membership change, unknown comparison, or located risk; public notices are listed separately. */
export function navigationTabHasDifferences(tab: Pick<DerivedNavigationTab, "rowFilter" | "facts" | "table" | "notice">): boolean {
  const scope = tabScope(tab);
  return scope.changeKind === null || scope.changeKind !== "UNCHANGED" || scope.riskLevel !== null || scope.membershipChanged;
}

export interface DerivedBundleView {
  groups: DerivedNavigationGroup[];
  tables: DerivedTable[];
  /** Non-null exactly for DATASET_REPLACEMENT; each side owns its own groups. */
  replacementSides: DerivedReplacementSide | null;
  tableNotices: NavigationTableNotice[];
  deviceDefinitionChanges: DeviceDefinitionChange[];
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

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));
}

function requireObject(value: unknown, keys: readonly string[], where: string): Record<string, unknown> {
  if (!isRecord(value) || !hasExactKeys(value, keys)) reject(`${where} 字段无效`);
  return value;
}

function nonEmptyString(value: unknown, where: string): string {
  if (typeof value !== "string" || value.length === 0) reject(`${where} 必须是非空字符串`);
  return value;
}

const UTF8 = new TextEncoder();

/** Byte-wise UTF-8 order, the canonical string order of the backend documents. */
export function compareUtf8(left: string, right: string): number {
  const a = UTF8.encode(left);
  const b = UTF8.encode(right);
  for (let index = 0; index < Math.min(a.length, b.length); index += 1) {
    const diff = (a[index] as number) - (b[index] as number);
    if (diff !== 0) return diff;
  }
  return a.length - b.length;
}

function strictlyAscendingUtf8(values: readonly string[]): boolean {
  return values.every((value, index) => index === 0 || compareUtf8(values[index - 1] as string, value) < 0);
}

const RISK_LEVELS: ReadonlySet<string> = new Set(["HIGH", "MEDIUM_HIGH", "UNKNOWN", "MEDIUM_LOW", "LOW"]);
/** Severity order shared with the backend RiskLevel (UNKNOWN between MEDIUM_HIGH and MEDIUM_LOW). */
export const RISK_SEVERITY: readonly RiskLevel[] = ["HIGH", "MEDIUM_HIGH", "UNKNOWN", "MEDIUM_LOW", "LOW"];

export function maximumRisk(levels: ReadonlyArray<RiskLevel | null>): RiskLevel | null {
  let best: RiskLevel | null = null;
  for (const level of levels) {
    if (level !== null && (best === null || RISK_SEVERITY.indexOf(level) < RISK_SEVERITY.indexOf(best))) best = level;
  }
  return best;
}

function riskLevel(value: unknown, where: string): RiskLevel | null {
  if (value === null) return null;
  if (typeof value !== "string" || !RISK_LEVELS.has(value)) reject(`${where} 的风险等级无效`);
  return value as RiskLevel;
}

function strictBoolean(value: unknown, where: string): boolean {
  if (typeof value !== "boolean") reject(`${where} 必须是布尔值`);
  return value;
}

function count(value: unknown, where: string): number | null {
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) reject(`${where} 必须是非负整数或 null`);
  return value;
}

function decodePredicate(value: unknown, where: string): NavigationPredicate {
  const raw = requireObject(value, ["column", "values"], where);
  const column = nonEmptyString(raw.column, `${where}.column`);
  const rawValues = raw.values;
  if (!Array.isArray(rawValues) || rawValues.length === 0) reject(`${where} 的 values 为空`);
  const allNumbers = rawValues.every((item) => typeof item === "number");
  const allStrings = rawValues.every((item) => typeof item === "string");
  if (!allNumbers && !allStrings) reject(`${where} 的 values 类型不一致`);
  if (allNumbers) {
    if (!rawValues.every((item) => Number.isSafeInteger(item))) reject(`${where} 的整数值超出安全范围`);
    if (!rawValues.every((item, index) => index === 0 || (rawValues[index - 1] as number) < (item as number))) reject(`${where} 的 values 未按规范排序或重复`);
  } else {
    if (rawValues.some((item) => item === "")) reject(`${where} 的字符串值为空`);
    if (!strictlyAscendingUtf8(rawValues as string[])) reject(`${where} 的 values 未按规范排序或重复`);
  }
  return { column, values: [...rawValues] as Array<string | number> };
}

function decodeRowFilter(value: unknown, where: string): NavigationRowFilter | null {
  if (value === null) return null;
  const raw = requireObject(value, ["before", "current"], `${where}.row_filter`);
  const before = raw.before === null ? null : decodePredicate(raw.before, `${where}.before`);
  const current = raw.current === null ? null : decodePredicate(raw.current, `${where}.current`);
  if (before === null && current === null) reject(`${where} 的 row_filter 两侧都为空`);
  return { before, current };
}

function decodeTableScope(value: unknown, where: string): NavigationTableScope | null {
  if (value === null) return null;
  const raw = requireObject(value, ["change", "risk_level"], `${where}.table_scope`);
  const scope = { change: strictBoolean(raw.change, `${where}.table_scope.change`), risk_level: riskLevel(raw.risk_level, `${where}.table_scope`) };
  if (!scope.change && scope.risk_level === null) reject(`${where} 的空 table_scope 必须为 null`);
  return scope;
}

const LOCAL_CHANGE_KINDS: ReadonlySet<string> = new Set(["UNCHANGED", "ADDED", "DELETED", "UPDATED"]);
const FACT_KEYS = ["basis", "change_kind", "risk_level", "risk_complete", "before_row_count", "current_row_count",
  "table_scope", "membership_changed", "membership_complete", "row_changes"] as const;

function decodeRowChanges(value: unknown, where: string): NavigationRowChanges | null {
  if (value === null) return null;
  const raw = requireObject(value, ["added", "deleted", "modified", "moved_in", "moved_out"], `${where}.row_changes`);
  const changes = {
    added: count(raw.added, `${where}.row_changes.added`),
    deleted: count(raw.deleted, `${where}.row_changes.deleted`),
    modified: count(raw.modified, `${where}.row_changes.modified`),
    moved_in: count(raw.moved_in, `${where}.row_changes.moved_in`),
    moved_out: count(raw.moved_out, `${where}.row_changes.moved_out`),
  };
  if (Object.values(changes).some((item) => item === null)) reject(`${where}.row_changes 不能含 null`);
  const exact = changes as NavigationRowChanges;
  if (exact.moved_in > exact.modified || exact.moved_out > exact.modified) reject(`${where}.row_changes 的迁移数超过修改数`);
  return exact;
}

function decodeFacts(value: unknown, where: string): NavigationFacts {
  const raw = requireObject(value, FACT_KEYS, `${where}.facts`);
  if (raw.basis !== "EXACT" && raw.basis !== "TABLE_FALLBACK") reject(`${where} 的 facts.basis 无效`);
  const basis = raw.basis;
  const rowChanges = decodeRowChanges(raw.row_changes, where);
  const changeKind = raw.change_kind;
  if (basis === "EXACT") {
    if (typeof changeKind !== "string" || !LOCAL_CHANGE_KINDS.has(changeKind) || rowChanges === null) reject(`${where} 的 EXACT facts 缺少局部变化`);
  } else if (changeKind !== null || rowChanges !== null) {
    reject(`${where} 的 TABLE_FALLBACK facts 不能声明局部变化`);
  }
  return {
    basis,
    change_kind: changeKind as NavigationLocalChangeKind | null,
    risk_level: riskLevel(raw.risk_level, `${where}.facts`),
    risk_complete: strictBoolean(raw.risk_complete, `${where}.facts.risk_complete`),
    before_row_count: count(raw.before_row_count, `${where}.facts.before_row_count`),
    current_row_count: count(raw.current_row_count, `${where}.facts.current_row_count`),
    table_scope: decodeTableScope(raw.table_scope, where),
    membership_changed: strictBoolean(raw.membership_changed, `${where}.facts.membership_changed`),
    membership_complete: strictBoolean(raw.membership_complete, `${where}.facts.membership_complete`),
    row_changes: rowChanges,
  };
}

const SUMMARY_KINDS = new Set(["UNCHANGED", "BUSINESS_EQUIVALENT", "ADDED", "DELETED", "UPDATED", "SCHEMA_CHANGED", "DEGRADED", "FAILED", "REPLACED"]);

function decodeSummary(value: unknown, tabs: NavigationTab[], where: string): NavigationSummary {
  const raw = requireObject(value, ["change_kinds", "risk_level", "nonempty_tab_count", "change_complete", "risk_complete"], `${where}.summary`);
  const kinds = raw.change_kinds;
  if (!Array.isArray(kinds) || kinds.some((kind) => typeof kind !== "string" || !SUMMARY_KINDS.has(kind))
      || !strictlyAscendingUtf8(kinds as string[])) reject(`${where} 的 summary.change_kinds 无效`);
  const risk = riskLevel(raw.risk_level, `${where}.summary`);
  const nonempty = tabs.filter((tab) => !tab.empty);
  if (raw.nonempty_tab_count !== nonempty.length) reject(`${where} 的 summary.nonempty_tab_count 无效`);
  if (nonempty.length === 0 && (kinds.length !== 0 || risk !== null)) reject(`${where} 的全空项 summary 必须中性`);
  const localFacts = nonempty.flatMap((tab) => tab.facts === null ? [] : [tab.facts]);
  const changeComplete = strictBoolean(raw.change_complete, `${where}.summary.change_complete`);
  const riskComplete = strictBoolean(raw.risk_complete, `${where}.summary.risk_complete`);
  if (changeComplete !== localFacts.every((facts) => facts.basis === "EXACT" && facts.membership_complete)) reject(`${where} 的 summary.change_complete 与页签不符`);
  if (riskComplete !== localFacts.every((facts) => facts.risk_complete)) reject(`${where} 的 summary.risk_complete 与页签不符`);
  // When every nonempty tab is a filtered tab, the summary is exactly their local facts.
  if (localFacts.length === nonempty.length) {
    const localKinds = [...new Set(localFacts.flatMap((facts) => facts.change_kind === null ? [] : [facts.change_kind]))].sort(compareUtf8);
    if (JSON.stringify(localKinds) !== JSON.stringify(kinds)) reject(`${where} 的 summary.change_kinds 与页签局部变化不符`);
    if (maximumRisk(localFacts.map((facts) => facts.risk_level)) !== risk) reject(`${where} 的 summary.risk_level 与页签局部风险不符`);
  }
  return { change_kinds: kinds as ChangeKind[], risk_level: risk, nonempty_tab_count: nonempty.length, change_complete: changeComplete, risk_complete: riskComplete };
}

const ORDINARY_GROUP_KEYS = ["FORWARD_CHANNELS", "SECONDARY_DEVICES", "COMMUNICATION_PROTOCOLS", "GLOBAL_PARAMETERS", "OTHER_TABLES"] as const;
const ITEM_KINDS: ReadonlySet<string> = new Set(["FORWARD_CHANNEL", "DEVICE", "COMPOSITE_SIGNAL_DEVICE", "PROTOCOL_CHANNEL", "TABLE"]);

function decodeAttributes(value: unknown, where: string): Record<string, string | number> {
  if (!isRecord(value)) reject(`${where}.attributes 不是对象`);
  for (const attribute of Object.values(value)) {
    if (typeof attribute !== "string" && !(typeof attribute === "number" && Number.isSafeInteger(attribute))) reject(`${where}.attributes 含无效标量`);
  }
  return { ...value } as Record<string, string | number>;
}

/** `side` is null for ordinary navigation, else the replacement side whose groups these are. */
function decodeGroups(value: unknown, tables: Map<string, SurfaceTable>, where: string, side: "BEFORE" | "CURRENT" | null): NavigationGroup[] {
  if (!Array.isArray(value)) reject(`${where} 不是数组`);
  if (side !== null && value.length === 0) return [];
  if (value.length !== ORDINARY_GROUP_KEYS.length) reject(`${where} 必须按顺序包含五个分组`);
  const itemKeys = new Set<string>();
  const perTable = new Map<string, Array<{ groupKey: string; tab: NavigationTab }>>();
  const groups: NavigationGroup[] = [];
  for (const [groupIndex, rawGroup] of value.entries()) {
    const group = requireObject(rawGroup, ["group_key", "label", "items", "nonempty_item_count"], `${where}[${groupIndex}]`);
    if (group.group_key !== ORDINARY_GROUP_KEYS[groupIndex]) reject(`${where}[${groupIndex}] 的分组顺序无效：${String(group.group_key)}`);
    const groupKey: string = ORDINARY_GROUP_KEYS[groupIndex] as string;
    const groupLabel = nonEmptyString(group.label, `${where}.${groupKey}.label`);
    if (!Array.isArray(group.items)) reject(`${where}.${groupKey}.items 不是数组`);
    const items: NavigationItem[] = [];
    for (const [itemIndex, rawItem] of group.items.entries()) {
      const itemWhere = `${where}.${groupKey}[${itemIndex}]`;
      const item = requireObject(rawItem, ["item_key", "item_kind", "label", "attributes", "tabs", "summary"], itemWhere);
      const itemKey = nonEmptyString(item.item_key, `${itemWhere}.item_key`);
      if (itemKeys.has(itemKey)) reject(`${where} 的 item_key 重复：${itemKey}`);
      itemKeys.add(itemKey);
      if (typeof item.item_kind !== "string" || !ITEM_KINDS.has(item.item_kind)) reject(`${itemWhere} 的 item_kind 无效`);
      if (!Array.isArray(item.tabs)) reject(`${where}.${groupKey}.${itemKey}.tabs 不是数组`);
      const tabKeys = new Set<string>();
      const tabs: NavigationTab[] = [];
      for (const [tabIndex, rawTab] of item.tabs.entries()) {
        const tabWhere = `${where}.${groupKey}.${itemKey}[${tabIndex}]`;
        const raw = requireObject(rawTab, ["tab_key", "label", "table_id", "row_filter", "facts", "empty"], tabWhere);
        const tabKey = nonEmptyString(raw.tab_key, `${tabWhere}.tab_key`);
        if (tabKeys.has(tabKey)) reject(`${where}.${groupKey}.${itemKey} 的 tab_key 重复：${tabKey}`);
        tabKeys.add(tabKey);
        const tableId = raw.table_id;
        if (typeof tableId !== "string" || !tables.has(tableId)) reject(`导航引用了未发布的表：${String(tableId)}`);
        if (typeof raw.empty !== "boolean" || (side !== null && raw.empty)) reject(`${where}.${groupKey}.${itemKey}.${tabKey} 的 empty 无效`);
        const rowFilter = decodeRowFilter(raw.row_filter, `${where}.${groupKey}.${itemKey}.${tabKey}`);
        if (side !== null && rowFilter !== null && (side === "BEFORE" ? rowFilter.current : rowFilter.before) !== null) {
          reject(`${where}.${groupKey}.${itemKey}.${tabKey} 的替换筛选跨侧`);
        }
        let facts: NavigationFacts | null = null;
        if (side !== null || rowFilter === null) {
          if (raw.facts !== null) reject(`${where}.${groupKey}.${itemKey}.${tabKey} 的整表或替换页签不能带局部 facts`);
        } else {
          facts = decodeFacts(raw.facts, `${where}.${groupKey}.${itemKey}.${tabKey}`);
        }
        const tab: NavigationTab = { empty: raw.empty, tab_key: tabKey, label: nonEmptyString(raw.label, `${tabWhere}.label`), table_id: tableId, row_filter: rowFilter, facts };
        const entries = perTable.get(tableId) ?? [];
        entries.push({ groupKey, tab });
        perTable.set(tableId, entries);
        tabs.push(tab);
      }
      items.push({
        item_key: itemKey,
        item_kind: item.item_kind,
        label: nonEmptyString(item.label, `${itemWhere}.label`),
        attributes: decodeAttributes(item.attributes, itemWhere),
        tabs,
        summary: decodeSummary(item.summary, tabs, `${where}.${groupKey}.${itemKey}`),
      });
    }
    if (group.nonempty_item_count !== items.filter((item) => item.summary.nonempty_tab_count > 0).length) reject(`${where}.${groupKey} 的 nonempty_item_count 无效`);
    groups.push({ nonempty_item_count: group.nonempty_item_count as number, group_key: groupKey, label: groupLabel, items });
  }
  for (const [tableId, entries] of perTable) {
    const wholeTable = entries.filter((entry) => entry.tab.row_filter === null);
    if (wholeTable.length > 1) reject(`表 ${tableId} 有多个整表页签`);
    if (wholeTable.length === 1 && entries.length > 1) reject(`表 ${tableId} 的整表页签与筛选页签同时存在`);
    if (new Set(entries.map((entry) => entry.groupKey)).size > 1) reject(`表 ${tableId} 的筛选页签不在同一分组`);
    const facts = entries.flatMap((entry) => entry.tab.facts === null ? [] : [entry.tab.facts]);
    if (new Set(facts.map((item) => item.basis)).size > 1) reject(`表 ${tableId} 的筛选页签 facts.basis 不一致`);
    if (new Set(facts.map((item) => JSON.stringify(item.table_scope))).size > 1) reject(`表 ${tableId} 的筛选页签 table_scope 不一致`);
  }
  return groups;
}

function decodeTableNotices(value: unknown, groups: NavigationGroup[]): NavigationTableNotice[] {
  if (!Array.isArray(value)) reject("table_notices 不是数组");
  const tabsByTable = new Map<string, NavigationTab[]>();
  for (const tab of groups.flatMap((group) => group.items.flatMap((item) => item.tabs))) {
    tabsByTable.set(tab.table_id, [...(tabsByTable.get(tab.table_id) ?? []), tab]);
  }
  const notices = value.map((rawNotice, index): NavigationTableNotice => {
    const where = `table_notices[${index}]`;
    const raw = requireObject(rawNotice, ["table_id", "table_scope", "unlocated_row_risk", "risk_complete"], where);
    const tableId = nonEmptyString(raw.table_id, `${where}.table_id`);
    const tabs = tabsByTable.get(tableId);
    if (!tabs) reject(`${where} 引用了导航中不存在的表：${tableId}`);
    const tableScope = decodeTableScope(raw.table_scope, where);
    let unlocated: UnlocatedRowRisk | null = null;
    if (raw.unlocated_row_risk !== null) {
      const risk = requireObject(raw.unlocated_row_risk, ["risk_level", "count", "reason_codes"], `${where}.unlocated_row_risk`);
      const reasons = risk.reason_codes;
      if (!Array.isArray(reasons) || reasons.some((code) => typeof code !== "string" || code.length === 0) || !strictlyAscendingUtf8(reasons as string[])) {
        reject(`${where}.unlocated_row_risk.reason_codes 必须去重排序`);
      }
      unlocated = { risk_level: riskLevel(risk.risk_level, `${where}.unlocated_row_risk`), count: count(risk.count, `${where}.unlocated_row_risk.count`), reason_codes: [...reasons] as string[] };
    }
    const riskComplete = strictBoolean(raw.risk_complete, `${where}.risk_complete`);
    if (tableScope === null && unlocated === null && riskComplete) reject(`${where} 是空提示`);
    const facts = tabs.flatMap((tab) => tab.facts === null ? [] : [tab.facts]);
    if (facts.length > 0 && JSON.stringify(facts[0]?.table_scope ?? null) !== JSON.stringify(tableScope)) reject(`${where} 的 table_scope 与页签不一致`);
    if (facts.some((item) => item.risk_complete !== riskComplete)) reject(`${where} 的 risk_complete 与页签不一致`);
    return { table_id: tableId, table_scope: tableScope, unlocated_row_risk: unlocated, risk_complete: riskComplete };
  });
  if (!strictlyAscendingUtf8(notices.map((notice) => notice.table_id))) reject("table_notices 必须按 table_id 唯一排序");
  // A table whose risk is incomplete or that carries a table scope must be discoverable publicly.
  const noticed = new Set(notices.map((notice) => notice.table_id));
  for (const [tableId, tabs] of tabsByTable) {
    const facts = tabs.flatMap((tab) => tab.facts === null ? [] : [tab.facts]);
    if (!noticed.has(tableId) && facts.some((item) => !item.risk_complete || item.table_scope !== null)) reject(`表 ${tableId} 缺少公共提示`);
  }
  return notices;
}

function decodeDeviceDefinitionChanges(value: unknown, groups: NavigationGroup[]): DeviceDefinitionChange[] {
  if (!Array.isArray(value)) reject("device_definition_changes 不是数组");
  const itemKeys = new Set(groups.flatMap((group) => group.items.map((item) => item.item_key)));
  const changes = value.map((rawChange, index): DeviceDefinitionChange => {
    const where = `device_definition_changes[${index}]`;
    const raw = requireObject(rawChange, ["record_identity", "change_kind", "before_item_key", "current_item_key", "before_dev_addr", "current_dev_addr", "risk_level", "risk_complete"], where);
    if (raw.change_kind !== "ADDED" && raw.change_kind !== "DELETED" && raw.change_kind !== "UPDATED") reject(`${where}.change_kind 无效`);
    const side = (name: "before" | "current") => {
      const key = raw[`${name}_item_key`];
      const address = raw[`${name}_dev_addr`];
      if (address !== null && !(typeof address === "number" && Number.isSafeInteger(address))) reject(`${where}.${name}_dev_addr 无效`);
      if (key !== null && (typeof key !== "string" || !itemKeys.has(key) || address === null)) reject(`${where}.${name}_item_key 引用了不存在的项`);
      return { key: key as string | null, address: address as number | null };
    };
    const before = side("before");
    const current = side("current");
    if (raw.change_kind === "ADDED" && (before.key !== null || before.address !== null)) reject(`${where} 的新增定义不能有改前侧`);
    if (raw.change_kind === "DELETED" && (current.key !== null || current.address !== null)) reject(`${where} 的删除定义不能有改后侧`);
    return {
      record_identity: nonEmptyString(raw.record_identity, `${where}.record_identity`),
      change_kind: raw.change_kind,
      before_item_key: before.key,
      current_item_key: current.key,
      before_dev_addr: before.address,
      current_dev_addr: current.address,
      risk_level: riskLevel(raw.risk_level, where),
      risk_complete: strictBoolean(raw.risk_complete, `${where}.risk_complete`),
    };
  });
  if (!strictlyAscendingUtf8(changes.map((change) => change.record_identity))) reject("device_definition_changes 必须按 record_identity 唯一排序");
  return changes;
}

/** Strict decode of the single business navigation artifact belonging to a pair. */
export function decodeBusinessNavigation(input: unknown, surface: ComparisonSurface): BusinessNavigation {
  const raw = requireObject(input, ["contract_version", "groups", "replacement_sides", "table_notices", "device_definition_changes"], "business navigation");
  if (raw.contract_version !== NAVIGATION_CONTRACT_VERSION) {
    reject(`不支持的 business navigation contract version：${String(raw.contract_version)}`);
  }
  const tables = new Map(surface.tables.map((table) => [table.table_name, table]));
  if (raw.replacement_sides !== null) {
    const sides = requireObject(raw.replacement_sides, ["before", "current"], "replacement_sides");
    if (surface.comparison_mode !== "DATASET_REPLACEMENT") reject("非替换模式下出现 replacement_sides");
    if (!Array.isArray(raw.groups) || raw.groups.length > 0) reject("替换模式的 groups 必须为空");
    if (!Array.isArray(raw.table_notices) || raw.table_notices.length > 0) reject("替换模式的 table_notices 必须为空");
    if (!Array.isArray(raw.device_definition_changes) || raw.device_definition_changes.length > 0) reject("替换模式的 device_definition_changes 必须为空");
    return {
      contract_version: NAVIGATION_CONTRACT_VERSION,
      groups: [],
      replacement_sides: {
        before: decodeGroups(sides.before, tables, "replacement_sides.before", "BEFORE"),
        current: decodeGroups(sides.current, tables, "replacement_sides.current", "CURRENT"),
      },
      table_notices: [],
      device_definition_changes: [],
    };
  }
  if (surface.comparison_mode === "DATASET_REPLACEMENT") reject("替换模式缺少 replacement_sides");
  const groups = decodeGroups(raw.groups, tables, "groups", null);
  return {
    contract_version: NAVIGATION_CONTRACT_VERSION,
    groups,
    replacement_sides: null,
    table_notices: decodeTableNotices(raw.table_notices, groups),
    device_definition_changes: decodeDeviceDefinitionChanges(raw.device_definition_changes, groups),
  };
}

function deriveGroups(groups: NavigationGroup[], tables: Map<string, DerivedTable>, notices: ReadonlyMap<string, NavigationTableNotice>): DerivedNavigationGroup[] {
  return groups.map((group) => ({
    nonemptyItemCount: group.nonempty_item_count,
    groupKey: group.group_key,
    label: group.label || group.group_key,
    items: group.items.map((item) => {
      const tabs = item.tabs.map((tab): DerivedNavigationTab => ({
        empty: tab.empty,
        tabKey: tab.tab_key,
        label: tab.label,
        tableName: tab.table_id,
        rowFilter: tab.row_filter,
        facts: tab.facts,
        table: tables.get(tab.table_id) ?? null,
        notice: notices.get(tab.table_id) ?? null,
      }));
      return {
        itemKey: item.item_key,
        itemKind: item.item_kind,
        label: item.label,
        attributes: item.attributes,
        tabs,
        nonemptyTabCount: item.summary.nonempty_tab_count,
        showTabs: tabs.length > 1,
        changeKinds: item.summary.change_kinds,
        riskLevels: item.summary.risk_level === null ? [] : [item.summary.risk_level],
        changeComplete: item.summary.change_complete,
        riskComplete: item.summary.risk_complete,
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
        existing.nonemptyTabCount = existing.tabs.filter((tab) => !tab.empty).length;
        existing.changeKinds = [...new Set([...existing.changeKinds, ...item.changeKinds])].sort();
        existing.riskLevels = [...new Set([...existing.riskLevels, ...item.riskLevels])]
          .sort((a, b) => RISK_SEVERITY.indexOf(a) - RISK_SEVERITY.indexOf(b));
      }
    }
  }
  return [...groups.values()].map((group) => ({ ...group, nonemptyItemCount: group.items.filter((item) => item.nonemptyTabCount > 0).length }));
}

export function deriveBundleView(input: {
  surface: ComparisonSurface;
  navigation: BusinessNavigation;
  riskReport?: RiskReport;
}): DerivedBundleView {
  const tableMap = tableProjection(input.surface, input.riskReport);
  const notices = new Map(input.navigation.table_notices.map((notice) => [notice.table_id, notice]));
  const sides = input.navigation.replacement_sides;
  const replacementSides = sides === null ? null : {
    before: deriveGroups(sides.before, tableMap, notices),
    current: deriveGroups(sides.current, tableMap, notices),
  };
  // Replacement navigation keeps `groups` empty; the sidebar still needs one
  // selectable tree, so both sides are merged by group/item and their tabs are
  // unioned by table. The side toggle decides which rows the table shows.
  const groups = replacementSides === null
    ? deriveGroups(input.navigation.groups, tableMap, notices)
    : mergeReplacementGroups(replacementSides);
  return {
    groups,
    tables: [...tableMap.values()],
    replacementSides,
    tableNotices: input.navigation.table_notices,
    deviceDefinitionChanges: input.navigation.device_definition_changes,
    diagnostics: [],
  };
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
