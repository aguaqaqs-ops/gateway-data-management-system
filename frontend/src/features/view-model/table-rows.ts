import { Sha256 } from "../bundle/sha256";
import { normalizeRowIdentity, type RiskAnnotation, type RiskLevel, type RowDiffRecord, type SurfaceColumn, type SurfaceTable } from "./model";

export type BrowseRowKind = "unchanged" | "added" | "deleted" | "modified-before" | "modified-after" | "ordered" | "blank" | "collapsed";

export interface BrowseRow {
  key: string;
  kind: BrowseRowKind;
  rowNumber: number;
  rowIdentity: string | null;
  riskLevel: RiskLevel | null;
  recordKind: string | null;
  semanticKind: string | null;
  beforePosition: number | null;
  currentPosition: number | null;
  changedColumns: string[];
  values: Record<string, unknown>;
  pairKey: string | null;
  collapsedCount?: number;
  collapsedRows?: BrowseRow[];
}

function bytes(...parts: Uint8Array[]): Uint8Array {
  const output = new Uint8Array(parts.reduce((size, part) => size + part.byteLength, 0));
  let offset = 0;
  for (const part of parts) {
    output.set(part, offset);
    offset += part.byteLength;
  }
  return output;
}

function uleb(value: number): Uint8Array {
  const output: number[] = [];
  let remaining = value;
  do {
    let byte = remaining & 0x7f;
    remaining = Math.floor(remaining / 128);
    if (remaining > 0) byte |= 0x80;
    output.push(byte);
  } while (remaining > 0);
  return Uint8Array.from(output);
}

function frame(tag: number, payload: Uint8Array): Uint8Array {
  return bytes(Uint8Array.of(tag), uleb(payload.byteLength), payload);
}

function scalarFrame(value: unknown, spelling: string): Uint8Array | null {
  const type = spelling.toUpperCase().trim();
  if (value === null || value === undefined) return frame(0x00, new Uint8Array());
  if (/^(BOOL|BOOLEAN)(\b|\()/.test(type)) return frame(0x01, Uint8Array.of(value === true || value === 1 || value === "1" ? 1 : 0));
  const integer = /^(TINYINT|SMALLINT|MEDIUMINT|INT|INTEGER|BIGINT)(\b|\()/.exec(type);
  if (integer) {
    const unsigned = /\bUNSIGNED\b/.test(type);
    const number = typeof value === "bigint" ? value : BigInt(String(value));
    const payload = new Uint8Array(8);
    const view = new DataView(payload.buffer);
    if (unsigned) view.setBigUint64(0, number, false);
    else view.setBigInt64(0, number, false);
    return frame(unsigned ? 0x11 : 0x10, payload);
  }
  if (/^(CHAR|VARCHAR|TINYTEXT|TEXT|MEDIUMTEXT|LONGTEXT|JSON|ENUM|SET)(\b|\()/.test(type)) {
    return frame(0x20, new TextEncoder().encode(String(value)));
  }
  if (/^(BINARY|VARBINARY|TINYBLOB|BLOB|MEDIUMBLOB|LONGBLOB)(\b|\()/.test(type)) {
    if (value instanceof ArrayBuffer) return frame(0x21, new Uint8Array(value));
    if (ArrayBuffer.isView(value)) return frame(0x21, new Uint8Array(value.buffer, value.byteOffset, value.byteLength));
    return null;
  }
  if (/^DATE\b/.test(type)) return frame(0x30, new TextEncoder().encode(String(value)));
  if (/^DATETIME\b/.test(type)) return frame(0x31, new TextEncoder().encode(String(value)));
  if (/^TIMESTAMP\b/.test(type)) return frame(0x32, new TextEncoder().encode(String(value)));
  if (/^TIME\b/.test(type)) return frame(0x33, new TextEncoder().encode(String(value)));
  if (/^(DECIMAL|NUMERIC)(\b|\()/.test(type)) return frame(0x12, new TextEncoder().encode(String(value)));
  if (/^FLOAT\b/.test(type)) {
    const payload = new Uint8Array(4);
    new DataView(payload.buffer).setFloat32(0, Number(value), false);
    return frame(0x13, payload);
  }
  if (/^(DOUBLE|REAL)\b/.test(type)) {
    const payload = new Uint8Array(8);
    new DataView(payload.buffer).setFloat64(0, Number(value), false);
    return frame(0x14, payload);
  }
  return null;
}

function rowDigest(row: Record<string, unknown>, table: SurfaceTable, columnNames: string[]): string | null {
  if (!columnNames.length) return null;
  const columnMap = new Map((table.columns ?? []).map((column) => [column.name, column]));
  const encoder = new TextEncoder();
  const orderedKeys = [...columnNames].sort((left, right) => compareBytes(encoder.encode(left), encoder.encode(right)));
  const parts: Uint8Array[] = [uleb(orderedKeys.length)];
  for (const name of orderedKeys) {
    const column = columnMap.get(name);
    if (!column) return null;
    const nameBytes = encoder.encode(name);
    const valueFrame = scalarFrame(row[name], column.scalar_type ?? "");
    if (!valueFrame) return null;
    parts.push(uleb(nameBytes.byteLength), nameBytes, valueFrame);
  }
  const hash = new Sha256()
    .update(encoder.encode("gateway-vnext:row:v1\0"))
    .update(bytes(...parts))
    .digest();
  return `sha256:${hash}`;
}

/** Computes the backend semantic identity for common SQL scalar columns. */
export function snapshotRowIdentity(row: Record<string, unknown>, table: SurfaceTable): string | null {
  const keyColumns = table.compare?.compare_key_columns ?? [];
  return rowDigest(row, table, keyColumns.length ? keyColumns : table.compare?.effective_columns ?? []);
}

function rowOccurrenceIdentity(identity: string, occurrence: number): string {
  if (occurrence === 0) return identity;
  const encoder = new TextEncoder();
  const payload = bytes(encoder.encode("keyless-row-occurrence:v1\0"), encoder.encode(identity), uleb(occurrence));
  const hash = new Sha256().update(encoder.encode("gateway-vnext:row:v1\0")).update(payload).digest();
  return `sha256:${hash}`;
}

function snapshotRowIdentities(rows: Record<string, unknown>[], table: SurfaceTable): Array<string | null> {
  const keyColumns = table.compare?.compare_key_columns ?? [];
  if (keyColumns.length) return rows.map((row) => rowDigest(row, table, keyColumns));
  const contentColumns = table.compare?.effective_columns ?? [];
  const occurrences = new Map<string, number>();
  return rows.map((row) => {
    const identity = rowDigest(row, table, contentColumns);
    if (!identity) return null;
    const occurrence = occurrences.get(identity) ?? 0;
    occurrences.set(identity, occurrence + 1);
    return rowOccurrenceIdentity(identity, occurrence);
  });
}

function compareBytes(left: Uint8Array, right: Uint8Array): number {
  for (let index = 0; index < Math.min(left.length, right.length); index += 1) {
    const difference = (left[index] ?? 0) - (right[index] ?? 0);
    if (difference) return difference;
  }
  return left.length - right.length;
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
  return Number.isSafeInteger(parsed) ? parsed : null;
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

function rowRiskMap(annotations: RiskAnnotation[]): Map<string, RiskLevel> {
  const risks = new Map<string, RiskLevel>();
  for (const annotation of annotations) {
    if (annotation.target.target_type !== "ROW") continue;
    for (const identity of [annotation.target.row_identity, annotation.target.before_row_identity, annotation.target.current_row_identity]) {
      const key = normalizeRowIdentity(identity);
      if (key) risks.set(key, annotation.risk_level);
    }
  }
  return risks;
}

export function displayRowSearchText(row: BrowseRow, columns: SurfaceColumn[]): string {
  return columns.map((column) => displayValue(row.values[column.name])).join(" ").toLocaleLowerCase();
}

export function collapseUnchangedRows(rows: BrowseRow[], expandedKeys: ReadonlySet<string>): BrowseRow[] {
  const output: BrowseRow[] = [];
  for (let index = 0; index < rows.length;) {
    const row = rows[index];
    if (!row || row.kind !== "unchanged" || row.riskLevel) {
      if (row) output.push(row);
      index += 1;
      continue;
    }
    const run: BrowseRow[] = [];
    while (rows[index]?.kind === "unchanged" && !rows[index]?.riskLevel) {
      const next = rows[index];
      if (next) run.push(next);
      index += 1;
    }
    if (run.length < 1) continue;
    const key = `unchanged:${run[0]?.rowNumber ?? 0}:${run.length}`;
    if (expandedKeys.has(key)) output.push(...run);
    else output.push({
      key,
      kind: "collapsed",
      rowNumber: run[0]?.rowNumber ?? 0,
      rowIdentity: null,
      riskLevel: null,
      recordKind: null,
      semanticKind: null,
      beforePosition: null,
      currentPosition: null,
      changedColumns: [],
      values: {},
      pairKey: null,
      collapsedCount: run.length,
      collapsedRows: run,
    });
  }
  return output;
}

export function buildBrowseRows(input: {
  table: SurfaceTable;
  beforeRows: Record<string, unknown>[];
  currentRows: Record<string, unknown>[];
  records: RowDiffRecord[];
  annotations: RiskAnnotation[];
  onlyInteresting?: boolean;
  search?: string;
  expandedRuns?: ReadonlySet<string>;
}): BrowseRow[] {
  const risks = rowRiskMap(input.annotations);
  const records = input.records.filter((record) => typeof record.record_kind === "string");
  const beforeIdentities = snapshotRowIdentities(input.beforeRows, input.table);
  const currentIdentities = snapshotRowIdentities(input.currentRows, input.table);
  const byIdentity = new Map<string, RowDiffRecord[]>();
  for (const record of records) {
    const identity = normalizeRowIdentity(record.row_identity);
    if (!identity) continue;
    const entries = byIdentity.get(identity) ?? [];
    entries.push(record);
    byIdentity.set(identity, entries);
  }

  const rows: BrowseRow[] = [];
  const consumed = new Set<RowDiffRecord>();
  const makeRow = (args: {
    key: string;
    kind: BrowseRowKind;
    source: Record<string, unknown>;
    rowNumber: number;
    identity?: string | null;
    record?: RowDiffRecord;
    pairKey?: string | null;
    values?: Record<string, unknown>;
  }): BrowseRow => {
    const identity = args.identity ?? snapshotRowIdentity(args.source, input.table);
    const record = args.record;
    const interval = record?.interval && typeof record.interval === "object" ? record.interval as Record<string, unknown> : {};
    return {
      key: args.key,
      kind: args.kind,
      rowNumber: args.rowNumber,
      rowIdentity: identity,
      riskLevel: identity ? risks.get(identity) ?? null : null,
      recordKind: typeof record?.record_kind === "string" ? record.record_kind : null,
      semanticKind: typeof record?.semantic_kind === "string" ? record.semantic_kind : null,
      beforePosition: positionNumber(record?.before_position) ?? positionNumber(interval.before_start),
      currentPosition: positionNumber(record?.current_position) ?? positionNumber(interval.current_start),
      changedColumns: Array.isArray(record?.changed_columns) ? record.changed_columns : [],
      values: { ...(args.values ?? args.source), ...(record?.interval ? { interval: record.interval } : {}) },
      pairKey: args.pairKey ?? null,
      ...(record && (record.record_kind === "BLANK_DELETE_INTERVAL" || record.record_kind === "BLANK_INSERT_INTERVAL") && !record.semantic_kind
        ? { semanticKind: String(record.record_kind) }
        : {}),
    };
  };

  const tableKind = input.table.change_kind ?? input.table.table_status;
  if (!records.length && (tableKind === "ADDED" || tableKind === "ADDED_TABLE")) {
    input.currentRows.forEach((source, index) => rows.push(makeRow({
      key: "table-added:" + index,
      kind: "added",
      source,
      rowNumber: index + 1,
      identity: currentIdentities[index] ?? null,
    })));
  }
  if (!records.length && (tableKind === "DELETED" || tableKind === "DELETED_TABLE")) {
    input.beforeRows.forEach((source, index) => rows.push(makeRow({
      key: "table-deleted:" + index,
      kind: "deleted",
      source,
      rowNumber: index + 1,
      identity: beforeIdentities[index] ?? null,
    })));
  }

  input.currentRows.forEach((source, index) => {
    const identity = currentIdentities[index] ?? null;
    const rowRecords = ["ROW_ADDED", "ROW_MODIFIED", "ORDERED_ROW_ADDED", "ORDERED_ROW_MODIFIED", "ORDERED_ROW_MOVED"];
    const candidate = (identity ? byIdentity.get(identity)?.find((record) => !consumed.has(record) && rowRecords.includes(String(record.record_kind))) : undefined)
      ?? input.records.find((record) => !consumed.has(record)
        && ["ORDERED_ROW_ADDED", "ORDERED_ROW_MODIFIED", "ORDERED_ROW_MOVED"].includes(String(record.record_kind))
        && positionNumber(record.current_position) === index + 1);
    if (!candidate) {
      rows.push(makeRow({ key: `current:${index + 1}`, kind: "unchanged", source, rowNumber: index + 1, identity }));
      return;
    }
    consumed.add(candidate);
    const recordKind = String(candidate.record_kind);
    if (recordKind === "ROW_MODIFIED" || recordKind === "ORDERED_ROW_MODIFIED") {
      const beforeValues = recordValues(candidate.before_values);
      const beforeIndex = beforeIdentities.findIndex((value) => value === identity);
      const before = beforeIndex >= 0 ? input.beforeRows[beforeIndex] ?? { ...source, ...beforeValues } : { ...source, ...beforeValues };
      const after = source;
      const pairKey = `pair:${identity}`;
      const beforeNumber = beforeIndex >= 0 ? beforeIndex + 1 : positionNumber(candidate.before_position) ?? index + 1;
      const currentNumber = positionNumber(candidate.current_position) ?? index + 1;
      rows.push(makeRow({ key: `${pairKey}:before`, kind: "modified-before", source: before, rowNumber: beforeNumber, identity, record: candidate, pairKey, values: before }));
      rows.push(makeRow({ key: `${pairKey}:after`, kind: "modified-after", source: after, rowNumber: currentNumber, identity, record: candidate, pairKey, values: after }));
    } else {
      rows.push(makeRow({ key: `record:${identity ?? index + 1}`, kind: recordKind === "ORDERED_ROW_MOVED" ? "ordered" : "added",
        source, rowNumber: positionNumber(candidate.current_position) ?? index + 1, identity, record: candidate }));
    }
  });

  for (const record of records) {
    if (consumed.has(record)) continue;
    const kind = String(record.record_kind);
    if (kind === "ROW_DELETED" || kind === "ORDERED_ROW_DELETED") {
      const identity = normalizeRowIdentity(record.row_identity);
      const beforeIndex = identity ? beforeIdentities.findIndex((value) => value === identity) : -1;
      const source = beforeIndex >= 0 ? input.beforeRows[beforeIndex] : undefined;
      rows.push(makeRow({ key: `deleted:${identity ?? rows.length}`, kind: "deleted", source: source ?? recordValues(record.before_values), rowNumber: positionNumber(record.before_position) ?? (beforeIndex >= 0 ? beforeIndex + 1 : input.beforeRows.length + rows.length + 1), identity, record, values: source ?? recordValues(record.before_values) }));
      consumed.add(record);
    } else if (kind.startsWith("BLANK_")) {
      const interval = record.interval && typeof record.interval === "object" ? record.interval as Record<string, unknown> : {};
      const position = positionNumber(record.before_position)
        ?? positionNumber(interval.before_start)
        ?? positionNumber(record.current_position)
        ?? positionNumber(interval.current_start)
        ?? input.currentRows.length + rows.length + 1;
      rows.push(makeRow({ key: `blank:${rows.length}`, kind: "blank", source: {}, rowNumber: position, record, values: {} }));
      consumed.add(record);
    }
  }

  rows.sort((left, right) => left.rowNumber - right.rowNumber);
  const query = input.search?.trim().toLocaleLowerCase();
  let visible = rows.filter((row) => {
    if (query && !displayRowSearchText(row, input.table.columns ?? []).includes(query)) return false;
    return true;
  });
  if (input.onlyInteresting) visible = collapseUnchangedRows(visible, input.expandedRuns ?? new Set());
  return visible;
}

export function normalizeDisplayScalar(value: unknown): string {
  return displayValue(value);
}
