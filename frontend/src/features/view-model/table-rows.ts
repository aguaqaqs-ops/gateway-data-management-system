import {
  ComparisonDecodeError,
  normalizeRowIdentity,
  riskAnnotationRowIdentities,
  type ColumnPresentIn,
  type NavigationFacts,
  type NavigationPredicate,
  type NavigationRowFilter,
  type RiskAnnotation,
  type RiskLevel,
  type RowDiffRecord,
  type SurfaceColumn,
  type SurfaceTable,
} from "./model";
import {
  assertPredicateCompatible,
  matchesTypedPredicate,
  type SnapshotColumnEncoding,
} from "./snapshot-encoding";

export type BrowseRowKind = "unchanged" | "added" | "deleted" | "modified-before" | "modified-after" | "ordered" | "blank-interval" | "collapsed";

/**
 * One published blank-interval record. The ranges are the affected region of
 * one skeleton gap (they may span non-skeleton rows or sparse `no`); rowCount
 * is the net occupancy difference, not the range length.
 */
export interface BlankIntervalSummary {
  direction: "INSERT" | "DELETE";
  before: readonly [number, number] | null;
  current: readonly [number, number] | null;
  rowCount: number | null;
}

export interface BrowseRow {
  key: string;
  kind: BrowseRowKind;
  /** Physical side this row comes from; null for blank-interval summaries. */
  side: "before" | "current" | null;
  /** Same-side identity context from the locator when that side has no snapshot; used only to match filters. */
  identityContext?: Record<string, unknown> | null;
  /** Values come from a record or context, not a snapshot row: absent columns are unavailable, not NULL. */
  partialValues?: boolean;
  /** Present exactly on "blank-interval" summary rows. */
  interval?: BlankIntervalSummary;
  /** Grid placement of rows without a snapshot row (blank-interval summaries), on the physical ruler. */
  sortPosition?: number;
  /** 0-based index of the snapshot row this row shows, on the side the grid is ordered by. */
  physicalIndex?: number;
  /**
   * 1-based position on the physical snapshot order, shared by the grid order
   * and the change navigator; rows without a snapshot row sit half a step after
   * the row above them. Business `no` may be sparse and is never used here.
   */
  ruler?: number;
  rowNumber: number | null;
  rowNumberTitle?: string;
  rowIdentity: string | null;
  riskLevel: RiskLevel | null;
  recordKind: string | null;
  semanticKind: string | null;
  beforePosition: number | null;
  currentPosition: number | null;
  changedColumns: string[];
  formulaChanged?: boolean;
  values: Record<string, unknown>;
  pairKey: string | null;
  collapsedCount?: number;
  collapsedRows?: BrowseRow[];
  /** A "collapsed" row with expanded=true is the handle above an opened run. */
  expanded?: boolean;
}

const ADDED_KINDS = new Set(["ROW_ADDED", "ORDERED_ROW_ADDED"]);
const DELETED_KINDS = new Set(["ROW_DELETED", "ORDERED_ROW_DELETED"]);
const MODIFIED_KINDS = new Set(["ROW_MODIFIED", "ORDERED_ROW_MODIFIED", "ORDERED_ROW_MOVED"]);
const STANDARD_ORDINARY_KINDS = new Set(["ROW_ADDED", "ROW_DELETED", "ROW_MODIFIED"]);
const ORDERED_CURRENT_KINDS = new Set(["ORDERED_ROW_ADDED", "ORDERED_ROW_MODIFIED", "ORDERED_ROW_MOVED"]);

/** One decoded five-column locator row, addressed by its published identity. */
export interface RowLocatorRecord {
  beforeRowIndex: number | null;
  currentRowIndex: number | null;
  beforeFilterContext: Record<string, unknown> | null;
  currentFilterContext: Record<string, unknown> | null;
}

function bytesToHex(identity: unknown): string | null {
  const normalized = normalizeRowIdentity(identity as never);
  return normalized;
}

function contextDocument(value: unknown, where: string): Record<string, unknown> | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value !== "string") throw new ComparisonDecodeError(`${where} 的过滤上下文不是 JSON 文本`);
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new ComparisonDecodeError(`${where} 的过滤上下文不是合法 JSON`);
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new ComparisonDecodeError(`${where} 的过滤上下文不是对象`);
  }
  const document = parsed as Record<string, unknown>;
  if (Object.keys(document).length === 0) return null;
  return document;
}

function indexValue(value: unknown, where: string): number | null {
  if (value === null || value === undefined) return null;
  const index = typeof value === "bigint" ? Number(value) : value;
  if (typeof index !== "number" || !Number.isSafeInteger(index) || index < 0) {
    throw new ComparisonDecodeError(`${where} 的行下标无效`);
  }
  return index;
}

/** Decodes the published locator rows; identities are keyed by their canonical `sha256:` spelling. */
export function parseRowLocator(rows: Record<string, unknown>[]): Map<string, RowLocatorRecord> {
  const locator = new Map<string, RowLocatorRecord>();
  for (const row of rows) {
    const identity = bytesToHex(row.row_identity);
    if (!identity) throw new ComparisonDecodeError("locator 缺少行身份");
    if (locator.has(identity)) throw new ComparisonDecodeError(`locator 行身份重复：${identity}`);
    const where = `locator ${identity}`;
    locator.set(identity, {
      beforeRowIndex: indexValue(row.before_row_index, `${where}.before_row_index`),
      currentRowIndex: indexValue(row.current_row_index, `${where}.current_row_index`),
      beforeFilterContext: contextDocument(row.before_filter_context_json, `${where}.before_filter_context_json`),
      currentFilterContext: contextDocument(row.current_filter_context_json, `${where}.current_filter_context_json`),
    });
  }
  return locator;
}

export function locatorIdentity(record: RowDiffRecord): string | null {
  return normalizeRowIdentity(record.row_identity ?? undefined);
}

/**
 * Criteria from Business Navigation / FE-BEB-12: only tables whose local change
 * is complete (basis EXACT) and fully counted may reuse an identity. Risk
 * completeness is a separate fact and never blocks the reuse.
 */
export function canReuseUnrecordedIdentity(
  table: SurfaceTable,
  filterTabs: readonly { facts: NavigationFacts | null }[],
  hasBeforeSnapshot: boolean,
  hasCurrentSnapshot: boolean,
): boolean {
  if (filterTabs.length === 0) return false;
  if (!hasCurrentSnapshot || hasBeforeSnapshot) return false;
  if (table.row_change_stats?.row_count_before == null || table.row_change_stats?.row_count_current == null) return false;
  return filterTabs.every((tab) => tab.facts?.basis === "EXACT");
}

/**
 * Rejects locator payloads that contradict the published surface, records or
 * snapshots. With `exactTable`, the whole table is published as EXACT, so the
 * Business Navigation FE-BEB-12 integrity invariants also apply: both
 * suppressed counts are zero, the published ordinary records match the
 * row_change_stats counts by kind, and the locator identity set matches the
 * published records one-to-one.
 */
export function validateRowLocations(input: {
  table: SurfaceTable;
  locator: Map<string, RowLocatorRecord>;
  records: RowDiffRecord[];
  beforeRowCount: number;
  currentRowCount: number;
  hasBeforeSnapshot: boolean;
  hasCurrentSnapshot: boolean;
  publishesFilterTabs: boolean;
  exactTable: boolean;
}): void {
  const ordinary = input.records.filter((record) => STANDARD_ORDINARY_KINDS.has(String(record.record_kind)));
  if (ordinary.length > 0 && input.locator.size === 0) {
    throw new ComparisonDecodeError(`表 ${input.table.table_name} 有普通行记录但缺少行定位产物`);
  }
  if (input.exactTable) {
    const suppressedAdded = input.table.row_change_stats?.suppressed_added_count ?? 0;
    const suppressedDeleted = input.table.row_change_stats?.suppressed_deleted_count ?? 0;
    if (suppressedAdded !== 0 || suppressedDeleted !== 0) {
      throw new ComparisonDecodeError(`表 ${input.table.table_name} 为 EXACT 但 suppressed 计数非零`);
    }
    const published = { ROW_ADDED: 0, ROW_DELETED: 0, ROW_MODIFIED: 0 };
    for (const record of ordinary) {
      const kind = String(record.record_kind);
      if (kind === "ROW_ADDED" || kind === "ROW_DELETED" || kind === "ROW_MODIFIED") published[kind] += 1;
    }
    const stats = input.table.row_change_stats;
    if (typeof stats?.row_added_count === "number" && published.ROW_ADDED !== stats.row_added_count) {
      throw new ComparisonDecodeError(`表 ${input.table.table_name} 已发布新增行数与 row_change_stats 不符`);
    }
    if (typeof stats?.row_deleted_count === "number" && published.ROW_DELETED !== stats.row_deleted_count) {
      throw new ComparisonDecodeError(`表 ${input.table.table_name} 已发布删除行数与 row_change_stats 不符`);
    }
    if (typeof stats?.row_modified_count === "number" && published.ROW_MODIFIED !== stats.row_modified_count) {
      throw new ComparisonDecodeError(`表 ${input.table.table_name} 已发布修改行数与 row_change_stats 不符`);
    }
  }
  const seen = new Set<string>();
  for (const record of ordinary) {
    const identity = locatorIdentity(record);
    if (!identity) throw new ComparisonDecodeError(`表 ${input.table.table_name} 的普通行记录缺少身份`);
    if (seen.has(identity)) throw new ComparisonDecodeError(`表 ${input.table.table_name} 的普通行记录身份重复：${identity}`);
    seen.add(identity);
    const located = input.locator.get(identity);
    if (!located) throw new ComparisonDecodeError(`表 ${input.table.table_name} 缺少行定位：${identity}`);
    const where = `表 ${input.table.table_name} 的行定位 ${identity}`;
    const beforeExists = !ADDED_KINDS.has(String(record.record_kind));
    const currentExists = !DELETED_KINDS.has(String(record.record_kind));
    if (!beforeExists) {
      if (located.beforeRowIndex !== null) throw new ComparisonDecodeError(`${where} 的改前侧不存在却有快照位置`);
    } else if (input.hasBeforeSnapshot) {
      if (located.beforeRowIndex === null || located.beforeRowIndex >= input.beforeRowCount) throw new ComparisonDecodeError(`${where} 的改前侧位置无效`);
      if (located.beforeFilterContext !== null) throw new ComparisonDecodeError(`${where} 的改前侧有快照时上下文必须为空`);
    } else if (located.beforeRowIndex !== null) {
      throw new ComparisonDecodeError(`${where} 缺少改前快照却给出了改前位置`);
    }
    if (!currentExists) {
      if (located.currentRowIndex !== null) throw new ComparisonDecodeError(`${where} 的改后侧不存在却有快照位置`);
    } else if (input.hasCurrentSnapshot) {
      if (located.currentRowIndex === null || located.currentRowIndex >= input.currentRowCount) throw new ComparisonDecodeError(`${where} 的改后侧位置无效`);
      if (located.currentFilterContext !== null) throw new ComparisonDecodeError(`${where} 的改后侧有快照时上下文必须为空`);
    } else if (located.currentRowIndex !== null) {
      throw new ComparisonDecodeError(`${where} 缺少改后快照却给出了改后位置`);
    }
    if (!input.publishesFilterTabs) {
      if (located.beforeFilterContext !== null || located.currentFilterContext !== null) {
        throw new ComparisonDecodeError(`${where} 的整表入口不应带过滤上下文`);
      }
    }
  }
  if (input.exactTable) {
    for (const identity of input.locator.keys()) {
      if (!seen.has(identity)) {
        throw new ComparisonDecodeError(`表 ${input.table.table_name} 有多余的行定位：${identity}`);
      }
    }
  }
}

function recordValues(value: unknown): Record<string, unknown> {
  if (!Array.isArray(value)) return {};
  const result: Record<string, unknown> = {};
  for (const item of value) {
    if (!item || typeof item !== "object") continue;
    const entry = item as { column_name?: unknown; value?: unknown };
    if (typeof entry.column_name === "string") result[entry.column_name] = entry.value;
  }
  return result;
}

function positionNumber(value: unknown): number | null {
  if (typeof value !== "number" && typeof value !== "bigint" && typeof value !== "string") return null;
  if (typeof value === "string" && value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

function rowRiskMap(annotations: RiskAnnotation[]): Map<string, RiskLevel> {
  const risks = new Map<string, RiskLevel>();
  for (const annotation of annotations) {
    for (const identity of riskAnnotationRowIdentities(annotation)) risks.set(identity, annotation.risk_level);
  }
  return risks;
}

const FLOAT_SQL_TYPE = /^(float|double|real)/i;

/** Shortest decimal that reads back to the same IEEE-754 value, from big-endian bit hex. */
export function formatFloatBits(bits: string): string | null {
  if (!/^([0-9a-f]{8}|[0-9a-f]{16})$/i.test(bits)) return null;
  const view = new DataView(new ArrayBuffer(8));
  if (bits.length === 8) {
    view.setUint32(0, Number.parseInt(bits, 16));
    const value = view.getFloat32(0);
    if (!Number.isFinite(value)) return null;
    for (let digits = 1; digits <= 9; digits += 1) {
      const text = value.toPrecision(digits);
      if (Math.fround(Number(text)) === value) return String(Number(text));
    }
    return String(value);
  }
  view.setUint32(0, Number.parseInt(bits.slice(0, 8), 16)); view.setUint32(4, Number.parseInt(bits.slice(8), 16));
  const value = view.getFloat64(0);
  return Number.isFinite(value) ? String(value) : null;
}

function displayValue(value: unknown, column?: SurfaceColumn): string {
  if (value === null || value === undefined) return "—";
  // Snapshots carry FLOAT/DOUBLE as their exact bit pattern; show the number.
  if (typeof value === "string" && column && FLOAT_SQL_TYPE.test(column.scalar_type ?? "")) return formatFloatBits(value) ?? value;
  if (value && typeof value === "object" && ((value as { kind?: unknown }).kind === "float32" || (value as { kind?: unknown }).kind === "float64")
    && typeof (value as { text?: unknown }).text === "string") {
    const text = (value as { text: string }).text;
    return formatFloatBits(text) ?? text;
  }
  if (typeof value === "bigint") return value.toString();
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (value instanceof ArrayBuffer || ArrayBuffer.isView(value)) return "二进制值";
  if (typeof value === "object") {
    const object = value as Record<string, unknown>;
    if (typeof object.text === "string") return object.text;
    if (object.kind === "null") return "—";
    try { return JSON.stringify(value); } catch { return "[无法显示]"; }
  }
  return String(value);
}

function isBinaryColumn(column: SurfaceColumn): boolean {
  return /^(BIT|BINARY|VARBINARY|TINYBLOB|BLOB|MEDIUMBLOB|LONGBLOB)(\b|\()/i.test(column.scalar_type ?? "");
}

export function displayRowSearchText(row: BrowseRow, columns: SurfaceColumn[]): string {
  if (row.interval) return blankIntervalLabel(row.interval).toLocaleLowerCase();
  return columns.filter((column) => !isBinaryColumn(column) && !(row.values[column.name] instanceof ArrayBuffer)
    && !ArrayBuffer.isView(row.values[column.name]))
    .map((column) => displayValue(row.values[column.name], column)).join(" ").toLocaleLowerCase();
}

export function collapseUnchangedRows(rows: BrowseRow[], expandedKeys: ReadonlySet<string>): BrowseRow[] {
  const output: BrowseRow[] = [];
  for (let index = 0; index < rows.length;) {
    const row = rows[index];
    if (!row || row.kind !== "unchanged" || row.riskLevel) { if (row) output.push(row); index += 1; continue; }
    const run: BrowseRow[] = [];
    while (rows[index]?.kind === "unchanged" && !rows[index]?.riskLevel) {
      const next = rows[index]; if (next) run.push(next); index += 1;
    }
    if (!run.length) continue;
    const key = `unchanged:${run[0]?.rowNumber ?? 0}:${run.length}`;
    const expanded = expandedKeys.has(key);
    output.push({
      key, kind: "collapsed", side: null, rowNumber: run[0]?.rowNumber ?? null, rowIdentity: null, riskLevel: null,
      recordKind: null, semanticKind: null, beforePosition: null, currentPosition: null,
      changedColumns: [], values: {}, pairKey: null, collapsedCount: run.length, collapsedRows: run, expanded,
    });
    if (expanded) output.push(...run);
  }
  return output;
}

const EMPTY_ENCODINGS: ReadonlyMap<string, SnapshotColumnEncoding> = new Map();

/**
 * Renders the missing-side placeholder for a grid cell. A column that is
 * physically absent on the row's side shows 该侧无此列, which is distinct
 * from a NULL value on a present column (shown as — by displayValue).
 */
export function missingSideMarker(side: "before" | "current" | null, presentIn: ColumnPresentIn | undefined): string | null {
  if ((side === "before" && presentIn === "CURRENT") || (side === "current" && presentIn === "BEFORE")) {
    return "该侧无此列";
  }
  return null;
}

const ORDERED_POSITION_COLUMN = "no";

function scalarPosition(value: unknown): number | null {
  const text = value && typeof value === "object" ? (value as { text?: unknown }).text : value;
  return positionNumber(text);
}

function intervalRange(interval: Record<string, unknown>, side: "before" | "current"): readonly [number, number] | null {
  const start = positionNumber(interval[`${side}_start`]);
  const end = positionNumber(interval[`${side}_end`]);
  if (start === null && end === null) return null;
  if (start === null || end === null || end < start) throw new ComparisonDecodeError(`空点区间的 ${side} 范围无效`);
  return [start, end];
}

/**
 * Decodes one published blank-interval record into its summary. It never
 * expands the range into per-position rows: the range is a region, and
 * row_count is the net change in occupancy.
 */
export function blankIntervalSummary(record: RowDiffRecord): BlankIntervalSummary | null {
  const direction = record.record_kind === "BLANK_INSERT_INTERVAL" ? "INSERT" : record.record_kind === "BLANK_DELETE_INTERVAL" ? "DELETE" : null;
  if (direction === null) return null;
  const interval = record.interval && typeof record.interval === "object" ? record.interval as Record<string, unknown> : null;
  if (!interval) throw new ComparisonDecodeError("空点区间记录缺少 interval");
  const before = intervalRange(interval, "before");
  const current = intervalRange(interval, "current");
  if ((direction === "INSERT" ? current : before) === null) throw new ComparisonDecodeError("空点区间缺少变化侧范围");
  const rawCount = interval.row_count;
  const rowCount = rawCount === null || rawCount === undefined ? null : positionNumber(rawCount);
  if (rawCount !== null && rawCount !== undefined && rowCount === null) throw new ComparisonDecodeError("空点区间的 row_count 无效");
  return { direction, before, current, rowCount };
}

/** 1-based physical position of the first snapshot row whose business `no` is at least `no`; past the end if none. */
function physicalPositionOfNo(rows: readonly Record<string, unknown>[], no: number): number {
  for (let index = 0; index < rows.length; index += 1) {
    const value = scalarPosition(rows[index]?.[ORDERED_POSITION_COLUMN]);
    if (value !== null && value >= no) return index + 1;
  }
  return rows.length + 1;
}

const rangeText = (range: readonly [number, number] | null) => range === null ? "—" : range[0] === range[1] ? `${range[0]}` : `${range[0]}–${range[1]}`;

/** One-line description of a blank-interval change: affected region and net count, never a per-position claim. */
export function blankIntervalLabel(interval: BlankIntervalSummary): string {
  const action = interval.direction === "INSERT" ? "插入" : "删除";
  const amount = interval.rowCount === null ? "数量未知" : `${interval.rowCount} 个`;
  return `空点区间${action} ${amount} · 改前 no ${rangeText(interval.before)} → 改后 no ${rangeText(interval.current)}`;
}

function unwrapRecordScalar(value: unknown): { present: boolean; isNull: boolean; text: string | null } {
  if (value === null) return { present: true, isNull: true, text: null };
  if (value && typeof value === "object" && !(value instanceof ArrayBuffer) && !ArrayBuffer.isView(value)) {
    const document = value as Record<string, unknown>;
    if (document.kind === "null") return { present: true, isNull: true, text: null };
    return { present: true, isNull: false, text: typeof document.text === "string" ? document.text : null };
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "bigint") return { present: true, isNull: false, text: String(value) };
  return { present: true, isNull: false, text: null };
}

/**
 * The locator context and the record's own before/current values describe the
 * same row; an overlapping identity value that disagrees is a decode error.
 */
function assertContextAgrees(context: Record<string, unknown> | null, values: Record<string, unknown>, where: string): void {
  if (!context) return;
  for (const [column, expected] of Object.entries(context)) {
    if (!Object.hasOwn(values, column)) continue;
    const actual = unwrapRecordScalar(values[column]);
    const agrees = expected === null ? actual.isNull
      : typeof expected === "number" || typeof expected === "string" ? !actual.isNull && actual.text === String(expected)
        : false;
    if (!agrees) throw new ComparisonDecodeError(`${where} 的过滤上下文 ${column} 与记录值矛盾`);
  }
}

/**
 * Matches a predicate against the typed locator context of a side without a
 * snapshot. Context values are JSON scalars typed by the navigation owner: a
 * safe integer for integer predicates, a string for string predicates. SQL NULL
 * or a missing column never matches.
 */
function matchesContextPredicate(predicate: NavigationPredicate | null, context: Record<string, unknown>, where: string): boolean {
  if (!predicate || !Object.hasOwn(context, predicate.column)) return false;
  const value = context[predicate.column];
  if (value === null) return false;
  const integer = typeof predicate.values[0] === "number";
  if (integer ? !(typeof value === "number" && Number.isSafeInteger(value)) : typeof value !== "string") {
    throw new ComparisonDecodeError(`${where} 的上下文值类型与谓词矛盾：${predicate.column}`);
  }
  return predicate.values.includes(value as string | number);
}

function matchesSide(predicate: NavigationPredicate | null, row: BrowseRow, encodings: ReadonlyMap<string, SnapshotColumnEncoding>, where: string): boolean {
  if (row.identityContext) return matchesContextPredicate(predicate, row.identityContext, where);
  return matchesTypedPredicate(predicate, row.values, encodings, where);
}

/** Rows that exist on both sides and keep their before-side order. */
const SURVIVOR_KINDS: ReadonlySet<BrowseRowKind> = new Set(["unchanged", "modified-after", "ordered"]);

/**
 * Moves deleted rows (sorted last, numbered by before-side row) back to where
 * they stood. A deleted row at before row b goes after the k-th surviving row,
 * where k is the number of non-deleted rows before b. Deleted rows sharing an
 * anchor interleave with the added rows right after it, so replacing rows
 * 14-16 reads -14 +14 -15 +15 -16 +16; the "group" layout keeps the block
 * together instead: -14 -15 -16 +14 +15 +16. Moves make this approximate.
 */
function placeDeletedRowsInline(rows: BrowseRow[], layout: DeletionLayout): void {
  const deleted = rows.filter((row) => row.kind === "deleted" && row.rowNumber !== null)
    .sort((left, right) => (left.rowNumber ?? 0) - (right.rowNumber ?? 0));
  if (!deleted.length) return;
  const base = rows.filter((row) => row.kind !== "deleted");
  const groups = new Map<number, BrowseRow[]>();
  deleted.forEach((row, order) => {
    const anchor = (row.rowNumber ?? 1) - 1 - order;
    groups.set(anchor, [...(groups.get(anchor) ?? []), row]);
  });
  const output: BrowseRow[] = [];
  const flush = (group: BrowseRow[] | undefined, start: number): number => {
    let index = start;
    for (const row of group ?? []) {
      output.push(row);
      if (layout === "interleave" && base[index]?.kind === "added") { output.push(base[index] as BrowseRow); index += 1; }
    }
    return index;
  };
  let survivors = 0;
  let index = flush(groups.get(0), 0);
  groups.delete(0);
  for (; index < base.length; index += 1) {
    const row = base[index] as BrowseRow;
    output.push(row);
    if (!SURVIVOR_KINDS.has(row.kind)) continue;
    survivors += 1;
    const group = groups.get(survivors);
    if (!group) continue;
    groups.delete(survivors);
    index = flush(group, index + 1) - 1;
  }
  for (const group of [...groups.entries()].sort(([left], [right]) => left - right)) output.push(...group[1]);
  output.push(...rows.filter((row) => row.kind === "deleted" && row.rowNumber === null));
  rows.splice(0, rows.length, ...output);
}

/** How deleted rows sit beside the added rows that follow them: one by one, or as one block before them. */
export type DeletionLayout = "interleave" | "group";

export function buildBrowseRows(input: {
  table: SurfaceTable;
  beforeRows: Record<string, unknown>[];
  currentRows: Record<string, unknown>[];
  records: RowDiffRecord[];
  annotations: RiskAnnotation[];
  locator: Map<string, RowLocatorRecord>;
  hasBeforeSnapshot?: boolean;
  hasCurrentSnapshot?: boolean;
  onlyInteresting?: boolean;
  rowFilter?: NavigationRowFilter | null;
  /** Same-side `gateway.sta.enc.v1` column encodings; required when rowFilter is set. */
  beforeEncodings?: ReadonlyMap<string, SnapshotColumnEncoding> | null;
  currentEncodings?: ReadonlyMap<string, SnapshotColumnEncoding> | null;
  /** A degraded table publishes no predicate assertions: its filter is skipped. */
  degraded?: boolean;
  reuseUnrecordedBefore?: boolean;
  /**
   * Whole-table orphan browsing: keep rows whose given side matches none of the
   * table's published predicates for that side. Pairs stay together.
   */
  unassigned?: { side: "before" | "current"; predicates: readonly NavigationPredicate[] } | null;
  search?: string;
  expandedRuns?: ReadonlySet<string>;
  deletionLayout?: DeletionLayout;
}): { rows: BrowseRow[]; scoped: BrowseRow[] } {
  const hasBeforeSnapshot = input.hasBeforeSnapshot ?? input.beforeRows.length > 0;
  const hasCurrentSnapshot = input.hasCurrentSnapshot ?? input.currentRows.length > 0;
  const records = input.records.filter((record) => typeof record.record_kind === "string");
  const risks = rowRiskMap(input.annotations);
  const rows: BrowseRow[] = [];
  let insertion = 0;
  const makeRow = (args: {
    key: string; kind: BrowseRowKind; side: "before" | "current" | null; source: Record<string, unknown>; rowNumber: number | null;
    rowNumberTitle?: string; identity?: string | null; record?: RowDiffRecord; values?: Record<string, unknown>;
    pairKey?: string | null; formulaChanged?: boolean; physical?: number;
  }): BrowseRow => {
    const record = args.record;
    return {
      ...(args.physical !== undefined ? { physicalIndex: args.physical } : {}),
      key: args.key, kind: args.kind, side: args.side, rowNumber: args.rowNumber, ...(args.rowNumberTitle ? { rowNumberTitle: args.rowNumberTitle } : {}),
      rowIdentity: args.identity ?? null, riskLevel: args.identity ? risks.get(args.identity) ?? null : null,
      recordKind: typeof record?.record_kind === "string" ? record.record_kind : null,
      semanticKind: typeof record?.semantic_kind === "string" ? record.semantic_kind : null,
      beforePosition: positionNumber(record?.before_position),
      currentPosition: positionNumber(record?.current_position),
      changedColumns: Array.isArray(record?.changed_columns) ? record.changed_columns : [],
      ...(args.formulaChanged !== undefined ? { formulaChanged: args.formulaChanged } : {}),
      values: { ...(args.values ?? args.source) },
      pairKey: args.pairKey ?? null,
    };
  };

  const located = (record: RowDiffRecord): RowLocatorRecord | null => {
    const identity = locatorIdentity(record);
    return identity ? input.locator.get(identity) ?? null : null;
  };
  const recordByCurrentIndex = new Map<number, RowDiffRecord>();
  const recordByBeforeIndex = new Map<number, RowDiffRecord>();
  for (const record of records) {
    if (!STANDARD_ORDINARY_KINDS.has(String(record.record_kind))) continue;
    const entry = located(record);
    if (!entry) continue;
    if (entry.currentRowIndex !== null) recordByCurrentIndex.set(entry.currentRowIndex, record);
    if (entry.beforeRowIndex !== null) recordByBeforeIndex.set(entry.beforeRowIndex, record);
  }
  // Ordered records carry no row locator; their current position is the row's `no`.
  // A row both modified and moved keeps its modified pair; the move is attached to it.
  const moveByCurrentIndex = new Map<number, RowDiffRecord>();
  if (hasCurrentSnapshot && input.table.ordered_extension) {
    const indexByPosition = new Map<number, number>();
    input.currentRows.forEach((row, index) => {
      const position = scalarPosition(row[ORDERED_POSITION_COLUMN]);
      if (position !== null && !indexByPosition.has(position)) indexByPosition.set(position, index);
    });
    const movesLast = [...records].sort((left, right) =>
      Number(left.record_kind === "ORDERED_ROW_MOVED") - Number(right.record_kind === "ORDERED_ROW_MOVED"));
    for (const record of movesLast) {
      if (!ORDERED_CURRENT_KINDS.has(String(record.record_kind))) continue;
      const position = positionNumber(record.current_position);
      const index = position === null ? undefined : indexByPosition.get(position);
      if (index === undefined) continue;
      if (!recordByCurrentIndex.has(index)) recordByCurrentIndex.set(index, record);
      else if (record.record_kind === "ORDERED_ROW_MOVED") moveByCurrentIndex.set(index, record);
    }
  }

  const tableKind = input.table.change_kind ?? input.table.table_status;
  if (tableKind === "ADDED" || tableKind === "ADDED_TABLE") {
    input.currentRows.forEach((source, index) => rows.push(makeRow({ key: `table-added:${index}`, kind: "added", side: "current", source, rowNumber: index + 1, physical: index })));
  } else if (tableKind === "DELETED" || tableKind === "DELETED_TABLE") {
    input.beforeRows.forEach((source, index) => rows.push(makeRow({ key: `table-deleted:${index}`, kind: "deleted", side: "before", source, rowNumber: index + 1, physical: index })));
  } else {
    const consumed = new Set<RowDiffRecord>();
    input.currentRows.forEach((source, index) => {
      if (!hasCurrentSnapshot) return;
      const candidate = recordByCurrentIndex.get(index);
      if (!candidate) {
        // Real snapshot rows stay as they are, blank points included: a blank
        // interval is summarised once, never painted onto the rows it spans.
        rows.push(makeRow({ key: `current:${index + 1}`, kind: "unchanged", side: "current", source, rowNumber: index + 1, physical: index }));
        return;
      }
      consumed.add(candidate);
      const kind = String(candidate.record_kind);
      const identity = locatorIdentity(candidate);
      if (kind === "ORDERED_ROW_MOVED" && hasCurrentSnapshot) {
        rows.push(makeRow({ key: `record:moved:${index + 1}`, kind: "ordered", side: "current", source,
          rowNumber: positionNumber(candidate.current_position) ?? index + 1, identity, record: candidate, physical: index }));
        return;
      }
      if (MODIFIED_KINDS.has(kind)) {
        const entry = located(candidate);
        const beforeIndex = entry?.beforeRowIndex ?? null;
        const changedColumns = Array.isArray(candidate.changed_columns) ? candidate.changed_columns : [];
        const oldRecordValues = recordValues(candidate.before_values);
        const newRecordValues = recordValues(candidate.current_values);
        const currentFormulaDigest = Object.hasOwn(newRecordValues, "formula_digest")
          ? newRecordValues.formula_digest : source.formula_digest;
        const formulaChanged = Object.hasOwn(oldRecordValues, "formula_digest")
          && currentFormulaDigest !== undefined
          && oldRecordValues.formula_digest !== currentFormulaDigest;
        let beforeValues: Record<string, unknown>;
        let beforeNumber: number | null;
        let title: string | undefined;
        let beforeContext: Record<string, unknown> | null = null;
        if (hasBeforeSnapshot && beforeIndex !== null) {
          beforeValues = input.beforeRows[beforeIndex] ?? oldRecordValues;
          beforeNumber = beforeIndex + 1;
        } else {
          // A modified record lists every compared column that differs, so the
          // other compared columns hold the same value on both sides.
          const ignored = new Set(input.table.compare?.ignored_columns ?? []);
          const effective = input.table.compare?.effective_columns ?? [];
          beforeValues = {};
          for (const [name, value] of Object.entries(source)) {
            if (!ignored.has(name) && (!effective.length || effective.includes(name))) beforeValues[name] = value;
          }
          for (const column of changedColumns) if (column in oldRecordValues) beforeValues[column] = oldRecordValues[column];
          // The before context identifies the row for filters; it never replaces values.
          beforeContext = entry?.beforeFilterContext ?? null;
          assertContextAgrees(beforeContext, oldRecordValues, `表 ${input.table.table_name} 的修改行 ${identity ?? index + 1}`);
          beforeNumber = null;
          title = "改前快照不在本 bundle 中：改前值由改后行与修改记录推出" + (ignored.size ? "，不参与比较的列不可得" : "");
        }
        const move = moveByCurrentIndex.get(index);
        if (move) consumed.add(move);
        const movedFrom = positionNumber(move?.before_position) ?? positionNumber(candidate.before_position);
        const movedTo = positionNumber(move?.current_position) ?? positionNumber(candidate.current_position);
        if (beforeNumber === null && movedFrom !== null) beforeNumber = movedFrom;
        if (title && beforeNumber === null) title += "；改前行号不可得";
        const pairKey = `pair:${identity ?? index + 1}`;
        const beforeRow = makeRow({ key: `${pairKey}:before`, kind: "modified-before", side: "before", source: beforeValues, rowNumber: beforeNumber,
          rowNumberTitle: title, identity, record: candidate, values: beforeValues, pairKey });
        if (beforeContext) beforeRow.identityContext = beforeContext;
        const pair = [
          beforeRow,
          makeRow({ key: `${pairKey}:after`, kind: "modified-after", side: "current", source, rowNumber: index + 1,
            identity, record: candidate, values: source, pairKey, formulaChanged, physical: index }),
        ];
        for (const row of pair) { if (movedFrom !== null) row.beforePosition = movedFrom; if (movedTo !== null) row.currentPosition = movedTo; }
        rows.push(...pair);
      } else if (ADDED_KINDS.has(kind)) {
        rows.push(makeRow({ key: `record:${identity ?? index + 1}`, kind: "added", side: "current",
          source, rowNumber: index + 1, identity, record: candidate, physical: index }));
      } else if (DELETED_KINDS.has(kind)) {
        rows.push(makeRow({ key: `record:${identity ?? index + 1}`, kind: "unchanged", side: "current",
          source, rowNumber: index + 1, identity, record: candidate, physical: index }));
      }
    });

    if (!hasCurrentSnapshot) {
      input.beforeRows.forEach((source, index) => {
        const candidate = recordByBeforeIndex.get(index);
        if (!candidate) {
          rows.push(makeRow({ key: `before-only:${index + 1}`, kind: "unchanged", side: "before", source, rowNumber: index + 1, physical: index }));
          return;
        }
        consumed.add(candidate);
        const kind = String(candidate.record_kind);
        const identity = locatorIdentity(candidate);
        const rowKind = DELETED_KINDS.has(kind) ? "deleted" : "modified-before";
        const pairKey = rowKind === "modified-before" ? `pair:${identity ?? index + 1}` : null;
        rows.push(makeRow({ key: `${rowKind}:${identity ?? index + 1}`, kind: rowKind, side: "before", source, rowNumber: index + 1, identity, record: candidate, pairKey, physical: index }));
      });
    }

    let blankIndex = 0;
    for (const record of records) {
      if (consumed.has(record)) continue;
      const kind = String(record.record_kind);
      if (DELETED_KINDS.has(kind)) {
        const entry = located(record);
        const identity = locatorIdentity(record);
        const beforeIndex = entry?.beforeRowIndex ?? null;
        const where = `表 ${input.table.table_name} 的删除行 ${identity ?? insertion}`;
        const recorded = recordValues(record.before_values);
        // Value source order: the real before snapshot row, else the validated
        // record.before_values. The locator context only identifies the row.
        const fromSnapshot = hasBeforeSnapshot && beforeIndex !== null;
        const context = fromSnapshot ? null : entry?.beforeFilterContext ?? null;
        if (!fromSnapshot) assertContextAgrees(context, recorded, where);
        const hasRecordValues = Object.keys(recorded).length > 0;
        const source = fromSnapshot ? input.beforeRows[beforeIndex] ?? {} : recorded;
        // Preview has no before snapshot; an ordered table's deleted record still carries its before `no`.
        const orderedBefore = !fromSnapshot && input.table.ordered_extension ? scalarPosition(recorded[ORDERED_POSITION_COLUMN]) : null;
        const row = makeRow({ key: `deleted:${identity ?? insertion}`, kind: "deleted", side: "before", source, values: source,
          rowNumber: fromSnapshot ? beforeIndex + 1 : orderedBefore,
          rowNumberTitle: fromSnapshot ? undefined : hasRecordValues ? "改前快照不在本 bundle 中：显示删除记录中的改前值" : "改前值不可得", identity, record });
        if (!fromSnapshot) {
          row.partialValues = true;
          if (context) row.identityContext = context;
        }
        rows.push(row);
        insertion += 1;
        consumed.add(record);
      } else if (kind === "BLANK_INSERT_INTERVAL" || kind === "BLANK_DELETE_INTERVAL") {
        const interval = blankIntervalSummary(record);
        if (!interval) continue;
        const orderRows = hasCurrentSnapshot ? input.currentRows : input.beforeRows;
        const anchor = (hasCurrentSnapshot ? interval.current ?? interval.before : interval.before ?? interval.current) ?? [Number.MAX_SAFE_INTEGER];
        rows.push({
          key: `blank-interval:${blankIndex}`, kind: "blank-interval", side: null, rowNumber: null,
          rowIdentity: null, riskLevel: blankIntervalRiskAnnotation(interval, input.annotations)?.risk_level ?? null,
          recordKind: kind, semanticKind: kind, beforePosition: null, currentPosition: null, changedColumns: [],
          values: {}, pairKey: null, interval,
          // Sit just above the first real row whose business `no` reaches the gap.
          sortPosition: physicalPositionOfNo(orderRows, anchor[0]) - 0.5,
        });
        blankIndex += 1;
        consumed.add(record);
      }
    }

    const physicalOrder = (row: BrowseRow) => row.physicalIndex !== undefined ? row.physicalIndex + 1 : row.currentPosition ?? row.rowNumber ?? Number.MAX_SAFE_INTEGER;
    const afterPositionByPair = new Map<string, number>(rows.filter((row) => row.kind === "modified-after" && row.pairKey)
      .map((row) => [row.pairKey as string, physicalOrder(row)] as const));
    rows.sort((left, right) => {
      const leftDeleted = left.kind === "deleted" ? 1 : 0;
      const rightDeleted = right.kind === "deleted" ? 1 : 0;
      if (leftDeleted !== rightDeleted) return leftDeleted - rightDeleted;
      const position = (row: BrowseRow) => {
        if (row.kind === "blank-interval") return row.sortPosition ?? Number.MAX_SAFE_INTEGER;
        if (row.kind === "deleted") return hasBeforeSnapshot ? row.rowNumber ?? Number.MAX_SAFE_INTEGER : Number.MAX_SAFE_INTEGER;
        if (row.kind === "modified-before" && row.pairKey) return afterPositionByPair.get(row.pairKey) ?? row.beforePosition ?? row.rowNumber ?? Number.MAX_SAFE_INTEGER;
        return physicalOrder(row);
      };
      return position(left) - position(right);
    });
    if (hasCurrentSnapshot) placeDeletedRowsInline(rows, input.deletionLayout ?? "interleave");
  }
  // A modified pair shares the position of its current half.
  const pairPhysical = new Map(rows.flatMap((row) => row.pairKey && row.physicalIndex !== undefined ? [[row.pairKey, row.physicalIndex] as const] : []));
  let last = 0;
  for (const row of rows) {
    const physical = row.physicalIndex ?? (row.pairKey ? pairPhysical.get(row.pairKey) : undefined);
    if (physical !== undefined) last = physical + 1;
    row.ruler = physical !== undefined ? physical + 1 : last + 0.5;
  }

  let scoped = rows;
  const beforeEncodings = input.beforeEncodings ?? EMPTY_ENCODINGS;
  const currentEncodings = input.currentEncodings ?? EMPTY_ENCODINGS;
  const pairs = new Map<string, BrowseRow[]>();
  for (const row of rows) if (row.pairKey) pairs.set(row.pairKey, [...(pairs.get(row.pairKey) ?? []), row]);
  const keepPairs = (matches: (row: BrowseRow) => boolean) =>
    rows.filter((row) => row.pairKey ? (pairs.get(row.pairKey) ?? []).some(matches) : matches(row));
  const filter = input.degraded === true ? null : input.rowFilter ?? null;
  if (filter) {
    assertPredicateCompatible(filter.before, beforeEncodings, "改前筛选");
    assertPredicateCompatible(filter.current, currentEncodings, "改后筛选");
    const reusable = input.reuseUnrecordedBefore === true && !hasBeforeSnapshot && hasCurrentSnapshot;
    scoped = keepPairs((row) => {
      if (row.side === "before") return matchesSide(filter.before, row, beforeEncodings, "改前筛选");
      if (row.side === "current") {
        if (matchesSide(filter.current, row, currentEncodings, "改后筛选")) return true;
        return reusable && row.recordKind === null && matchesTypedPredicate(filter.before, row.values, currentEncodings, "改前筛选");
      }
      // A blank-interval summary belongs to the ordered table, not to a device filter.
      return false;
    });
  } else if (input.unassigned && input.degraded !== true) {
    const { side, predicates } = input.unassigned;
    const encodings = side === "before" ? beforeEncodings : currentEncodings;
    const where = side === "before" ? "改前未归属" : "改后未归属";
    for (const predicate of predicates) assertPredicateCompatible(predicate, encodings, where);
    scoped = keepPairs((row) => row.side === side && !predicates.some((predicate) => matchesSide(predicate, row, encodings, where)));
  }
  const query = input.search?.trim().toLocaleLowerCase();
  let visible = scoped.filter((row) => !query || displayRowSearchText(row, input.table.columns ?? []).includes(query));
  if (input.onlyInteresting) visible = collapseUnchangedRows(visible, input.expandedRuns ?? new Set());
  return { rows: visible, scoped };
}

function annotationSide(annotation: RiskAnnotation): unknown {
  return annotation.reasons.flatMap((reason) => reason.evidence).find(([name]) => name === "side")?.[1];
}

/**
 * The ROW_INTERVAL annotation of one blank-interval record: same changed side
 * and the same affected range. It is never matched to the real rows the range spans.
 */
function blankIntervalRiskAnnotation(interval: BlankIntervalSummary, annotations: RiskAnnotation[]): RiskAnnotation | undefined {
  const side = interval.direction === "INSERT" ? "CURRENT" : "BEFORE";
  const range = interval.direction === "INSERT" ? interval.current : interval.before;
  if (!range) return undefined;
  return annotations.find((annotation) => annotation.target.target_type === "ROW_INTERVAL"
    && annotationSide(annotation) === side
    && annotation.target.position_range?.[0] === range[0] && annotation.target.position_range?.[1] === range[1]);
}

/** The annotation behind a row's risk: by row identity, or the interval risk of a blank-interval summary. */
export function rowRiskAnnotation(row: BrowseRow, annotations: RiskAnnotation[]): RiskAnnotation | undefined {
  const identity = row.rowIdentity;
  if (identity) return annotations.find((annotation) => riskAnnotationRowIdentities(annotation).includes(identity));
  return row.interval ? blankIntervalRiskAnnotation(row.interval, annotations) : undefined;
}

/** One change the navigator can jump to: a row record (one per pair) or a blank-interval summary. */
export interface ChangeLocation {
  index: number;
  /** Grid row key used to scroll to and highlight the change. */
  rowKey: string;
  rowIdentity: string | null;
  recordKind: string;
  riskLevel: RiskLevel | null;
  position: number | null;
}

const LOCATION_KINDS: ReadonlySet<BrowseRowKind> = new Set(["added", "deleted", "modified-before", "modified-after", "ordered", "blank-interval"]);

/** Changes in the current scope (after the device filter, before search), in grid order. */
export function deriveChangeLocations(rows: readonly BrowseRow[]): ChangeLocation[] {
  const seen = new Set<string>();
  const locations: ChangeLocation[] = [];
  for (const row of rows) {
    if (!LOCATION_KINDS.has(row.kind) || row.recordKind === null) continue;
    const key = row.pairKey ?? row.rowIdentity ?? row.key;
    if (seen.has(key)) continue;
    seen.add(key);
    const range = row.interval ? row.interval.current ?? row.interval.before : null;
    locations.push({
      index: locations.length + 1,
      rowKey: row.key,
      rowIdentity: row.rowIdentity,
      recordKind: row.recordKind,
      riskLevel: row.riskLevel,
      position: row.ruler ?? (range ? range[0] : row.currentPosition ?? row.beforePosition ?? row.rowNumber),
    });
  }
  return locations;
}

/** Before → current position when the row changed position, else null. */
export function rowMove(row: BrowseRow): { from: number; to: number } | null {
  return row.beforePosition !== null && row.currentPosition !== null && row.beforePosition !== row.currentPosition
    ? { from: row.beforePosition, to: row.currentPosition } : null;
}

export function normalizeDisplayScalar(value: unknown, column?: SurfaceColumn): string { return displayValue(value, column); }

/** Grid header text: Debug shows the raw field name, User mode the column COMMENT (display_name). */
export function columnHeaderTitle(column: Pick<SurfaceColumn, "name" | "display_name">, debug: boolean): string {
  return debug ? column.name : column.display_name || column.name;
}
