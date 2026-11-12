import {
  ComparisonDecodeError,
  normalizeRowIdentity,
  riskAnnotationRowIdentities,
  type ColumnPresentIn,
  type NavigationFacts,
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

export type BrowseRowKind = "unchanged" | "added" | "deleted" | "modified-before" | "modified-after" | "ordered" | "blank" | "collapsed";

export interface BrowseRow {
  key: string;
  kind: BrowseRowKind;
  /** Physical side this row comes from; null for blank intervals. */
  side: "before" | "current" | null;
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
}

const ADDED_KINDS = new Set(["ROW_ADDED", "ORDERED_ROW_ADDED"]);
const DELETED_KINDS = new Set(["ROW_DELETED", "ORDERED_ROW_DELETED"]);
const MODIFIED_KINDS = new Set(["ROW_MODIFIED", "ORDERED_ROW_MODIFIED", "ORDERED_ROW_MOVED"]);
const STANDARD_ORDINARY_KINDS = new Set(["ROW_ADDED", "ROW_DELETED", "ROW_MODIFIED"]);

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

/** Criteria from Business Navigation / FE-BEB-12: only EXACT, fully counted tables may reuse an identity. */
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

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
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
  return columns.filter((column) => !isBinaryColumn(column) && !(row.values[column.name] instanceof ArrayBuffer)
    && !ArrayBuffer.isView(row.values[column.name]))
    .map((column) => displayValue(row.values[column.name])).join(" ").toLocaleLowerCase();
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
    if (expandedKeys.has(key)) output.push(...run);
    else output.push({
      key, kind: "collapsed", side: null, rowNumber: run[0]?.rowNumber ?? null, rowIdentity: null, riskLevel: null,
      recordKind: null, semanticKind: null, beforePosition: null, currentPosition: null,
      changedColumns: [], values: {}, pairKey: null, collapsedCount: run.length, collapsedRows: run,
    });
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
  search?: string;
  expandedRuns?: ReadonlySet<string>;
}): { rows: BrowseRow[] } {
  const hasBeforeSnapshot = input.hasBeforeSnapshot ?? input.beforeRows.length > 0;
  const hasCurrentSnapshot = input.hasCurrentSnapshot ?? input.currentRows.length > 0;
  const records = input.records.filter((record) => typeof record.record_kind === "string");
  const risks = rowRiskMap(input.annotations);
  const rows: BrowseRow[] = [];
  let insertion = 0;
  const makeRow = (args: {
    key: string; kind: BrowseRowKind; side: "before" | "current" | null; source: Record<string, unknown>; rowNumber: number | null;
    rowNumberTitle?: string; identity?: string | null; record?: RowDiffRecord; values?: Record<string, unknown>;
    pairKey?: string | null; formulaChanged?: boolean;
  }): BrowseRow => {
    const record = args.record;
    const interval = record?.interval && typeof record.interval === "object" ? record.interval as Record<string, unknown> : {};
    return {
      key: args.key, kind: args.kind, side: args.side, rowNumber: args.rowNumber, ...(args.rowNumberTitle ? { rowNumberTitle: args.rowNumberTitle } : {}),
      rowIdentity: args.identity ?? null, riskLevel: args.identity ? risks.get(args.identity) ?? null : null,
      recordKind: typeof record?.record_kind === "string" ? record.record_kind : null,
      semanticKind: typeof record?.semantic_kind === "string" ? record.semantic_kind : null,
      beforePosition: positionNumber(record?.before_position) ?? positionNumber(interval.before_start),
      currentPosition: positionNumber(record?.current_position) ?? positionNumber(interval.current_start),
      changedColumns: Array.isArray(record?.changed_columns) ? record.changed_columns : [],
      ...(args.formulaChanged !== undefined ? { formulaChanged: args.formulaChanged } : {}),
      values: { ...(args.values ?? args.source), ...(record?.interval ? { interval: record.interval } : {}) },
      pairKey: args.pairKey ?? null,
      ...(record && (String(record.record_kind).startsWith("BLANK_") && !record.semantic_kind) ? { semanticKind: String(record.record_kind) } : {}),
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

  const tableKind = input.table.change_kind ?? input.table.table_status;
  if (tableKind === "ADDED" || tableKind === "ADDED_TABLE") {
    input.currentRows.forEach((source, index) => rows.push(makeRow({ key: `table-added:${index}`, kind: "added", side: "current", source, rowNumber: index + 1 })));
  } else if (tableKind === "DELETED" || tableKind === "DELETED_TABLE") {
    input.beforeRows.forEach((source, index) => rows.push(makeRow({ key: `table-deleted:${index}`, kind: "deleted", side: "before", source, rowNumber: index + 1 })));
  } else {
    const consumed = new Set<RowDiffRecord>();
    input.currentRows.forEach((source, index) => {
      if (!hasCurrentSnapshot) return;
      const candidate = recordByCurrentIndex.get(index);
      if (!candidate) {
        rows.push(makeRow({ key: `current:${index + 1}`, kind: "unchanged", side: "current", source, rowNumber: index + 1 }));
        return;
      }
      consumed.add(candidate);
      const kind = String(candidate.record_kind);
      const identity = locatorIdentity(candidate);
      if (kind === "ORDERED_ROW_MOVED" && hasBeforeSnapshot && hasCurrentSnapshot) {
        rows.push(makeRow({ key: `record:moved:${index + 1}`, kind: "ordered", side: "current", source,
          rowNumber: positionNumber(candidate.current_position) ?? index + 1, identity, record: candidate }));
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
        if (hasBeforeSnapshot && beforeIndex !== null) {
          beforeValues = input.beforeRows[beforeIndex] ?? oldRecordValues;
          beforeNumber = beforeIndex + 1;
        } else if (entry?.beforeFilterContext) {
          beforeValues = { ...entry.beforeFilterContext };
          beforeNumber = null;
          title = "改前值不在本 bundle 中";
        } else {
          const keys = new Set(input.table.compare?.compare_key_columns ?? []);
          beforeValues = {};
          for (const key of keys) if (key in source) beforeValues[key] = source[key];
          for (const column of changedColumns) if (column in oldRecordValues) beforeValues[column] = oldRecordValues[column];
          beforeNumber = null;
          title = "改前值不可得";
        }
        const pairKey = `pair:${identity ?? index + 1}`;
        rows.push(makeRow({ key: `${pairKey}:before`, kind: "modified-before", side: "before", source: beforeValues, rowNumber: beforeNumber,
          rowNumberTitle: title, identity, record: candidate, values: beforeValues, pairKey }));
        rows.push(makeRow({ key: `${pairKey}:after`, kind: "modified-after", side: "current", source, rowNumber: index + 1,
          identity, record: candidate, values: source, pairKey, formulaChanged }));
      } else if (ADDED_KINDS.has(kind)) {
        rows.push(makeRow({ key: `record:${identity ?? index + 1}`, kind: "added", side: "current",
          source, rowNumber: index + 1, identity, record: candidate }));
      } else if (DELETED_KINDS.has(kind)) {
        rows.push(makeRow({ key: `record:${identity ?? index + 1}`, kind: "unchanged", side: "current",
          source, rowNumber: index + 1, identity, record: candidate }));
      }
    });

    if (!hasCurrentSnapshot) {
      input.beforeRows.forEach((source, index) => {
        const candidate = recordByBeforeIndex.get(index);
        if (!candidate) {
          rows.push(makeRow({ key: `before-only:${index + 1}`, kind: "unchanged", side: "before", source, rowNumber: index + 1 }));
          return;
        }
        consumed.add(candidate);
        const kind = String(candidate.record_kind);
        const identity = locatorIdentity(candidate);
        const rowKind = DELETED_KINDS.has(kind) ? "deleted" : "modified-before";
        const pairKey = rowKind === "modified-before" ? `pair:${identity ?? index + 1}` : null;
        rows.push(makeRow({ key: `${rowKind}:${identity ?? index + 1}`, kind: rowKind, side: "before", source, rowNumber: index + 1, identity, record: candidate, pairKey }));
      });
    }

    for (const record of records) {
      if (consumed.has(record)) continue;
      const kind = String(record.record_kind);
      if (DELETED_KINDS.has(kind)) {
        const entry = located(record);
        const identity = locatorIdentity(record);
        const beforeIndex = entry?.beforeRowIndex ?? null;
        const hasContext = entry?.beforeFilterContext != null;
        const source = hasBeforeSnapshot && beforeIndex !== null ? input.beforeRows[beforeIndex] : hasContext ? { ...entry?.beforeFilterContext } : recordValues(record.before_values);
        rows.push(makeRow({ key: `deleted:${identity ?? insertion}`, kind: "deleted", side: "before", source, values: source,
          rowNumber: hasBeforeSnapshot && beforeIndex !== null ? beforeIndex + 1 : null,
          rowNumberTitle: hasBeforeSnapshot ? undefined : hasContext ? "改前值不在本 bundle 中" : "改前值不可得", identity, record }));
        insertion += 1;
        consumed.add(record);
      } else if (kind.startsWith("BLANK_")) {
        const interval = record.interval && typeof record.interval === "object" ? record.interval as Record<string, unknown> : {};
        const position = positionNumber(record.before_position) ?? positionNumber(interval.before_start)
          ?? positionNumber(record.current_position) ?? positionNumber(interval.current_start) ?? input.currentRows.length + insertion + 1;
        rows.push(makeRow({ key: `blank:${insertion}`, kind: "blank", side: null, source: {}, rowNumber: position, record, values: {} }));
        insertion += 1;
        consumed.add(record);
      }
    }

    const afterPositionByPair = new Map<string, number>(rows.filter((row) => row.kind === "modified-after" && row.pairKey)
      .map((row) => [row.pairKey as string, row.currentPosition ?? row.rowNumber ?? Number.MAX_SAFE_INTEGER] as const));
    rows.sort((left, right) => {
      const leftDeleted = left.kind === "deleted" ? 1 : 0;
      const rightDeleted = right.kind === "deleted" ? 1 : 0;
      if (leftDeleted !== rightDeleted) return leftDeleted - rightDeleted;
      const position = (row: BrowseRow) => {
        if (row.kind === "deleted") return hasBeforeSnapshot ? row.rowNumber ?? Number.MAX_SAFE_INTEGER : Number.MAX_SAFE_INTEGER;
        if (row.kind === "modified-before" && row.pairKey) return afterPositionByPair.get(row.pairKey) ?? row.beforePosition ?? row.rowNumber ?? Number.MAX_SAFE_INTEGER;
        return row.currentPosition ?? row.rowNumber ?? Number.MAX_SAFE_INTEGER;
      };
      return position(left) - position(right);
    });
  }

  let visible = rows;
  const filter = input.degraded === true ? null : input.rowFilter ?? null;
  if (filter) {
    const beforeEncodings = input.beforeEncodings ?? EMPTY_ENCODINGS;
    const currentEncodings = input.currentEncodings ?? EMPTY_ENCODINGS;
    assertPredicateCompatible(filter.before, beforeEncodings, "改前筛选");
    assertPredicateCompatible(filter.current, currentEncodings, "改后筛选");
    const reusable = input.reuseUnrecordedBefore === true && !hasBeforeSnapshot && hasCurrentSnapshot;
    const matches = (row: BrowseRow) => {
      if (row.side === "before") return matchesTypedPredicate(filter.before, row.values, beforeEncodings, "改前筛选");
      if (row.side === "current") {
        if (matchesTypedPredicate(filter.current, row.values, currentEncodings, "改后筛选")) return true;
        return reusable && row.recordKind === null && matchesTypedPredicate(filter.before, row.values, currentEncodings, "改前筛选");
      }
      return false;
    };
    const pairs = new Map<string, BrowseRow[]>();
    for (const row of rows) if (row.pairKey) pairs.set(row.pairKey, [...(pairs.get(row.pairKey) ?? []), row]);
    visible = rows.filter((row) => row.pairKey ? (pairs.get(row.pairKey) ?? []).some(matches) : matches(row));
  }
  const query = input.search?.trim().toLocaleLowerCase();
  visible = visible.filter((row) => !query || displayRowSearchText(row, input.table.columns ?? []).includes(query));
  if (input.onlyInteresting) visible = collapseUnchangedRows(visible, input.expandedRuns ?? new Set());
  return { rows: visible };
}

export function normalizeDisplayScalar(value: unknown): string { return displayValue(value); }
