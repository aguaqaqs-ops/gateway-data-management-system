import { Sha256 } from "../bundle/sha256";
import { normalizeRowIdentity, riskAnnotationRowIdentities, type RiskAnnotation, type RiskLevel, type RowDiffRecord, type SurfaceColumn, type SurfaceTable } from "./model";

export type BrowseRowKind = "unchanged" | "added" | "deleted" | "modified-before" | "modified-after" | "ordered" | "blank" | "collapsed";

export interface BrowseRow {
  key: string;
  kind: BrowseRowKind;
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

const ROW_KINDS = new Set([
  "ROW_ADDED", "ROW_DELETED", "ROW_MODIFIED",
  "ORDERED_ROW_ADDED", "ORDERED_ROW_DELETED", "ORDERED_ROW_MODIFIED", "ORDERED_ROW_MOVED",
]);
const ADDED_KINDS = new Set(["ROW_ADDED", "ORDERED_ROW_ADDED"]);
const DELETED_KINDS = new Set(["ROW_DELETED", "ORDERED_ROW_DELETED"]);
const MODIFIED_KINDS = new Set(["ROW_MODIFIED", "ORDERED_ROW_MODIFIED", "ORDERED_ROW_MOVED"]);

function bytes(...parts: Uint8Array[]): Uint8Array {
  const output = new Uint8Array(parts.reduce((size, part) => size + part.byteLength, 0));
  let offset = 0;
  for (const part of parts) { output.set(part, offset); offset += part.byteLength; }
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

function validCivilDate(year: number, month: number, day: number): boolean {
  if (year < 1 || year > 9999 || month < 1 || month > 12) return false;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day >= 1 && day <= (days[month - 1] ?? 0);
}

function canonicalTemporal(value: unknown, type: "DATE" | "DATETIME" | "TIMESTAMP" | "TIME"): value is string {
  if (typeof value !== "string") return false;
  if (type === "DATE") {
    const match = /^([0-9]{4})-([0-9]{2})-([0-9]{2})$/.exec(value);
    return Boolean(match && validCivilDate(Number(match[1]), Number(match[2]), Number(match[3])));
  }
  if (type === "DATETIME" || type === "TIMESTAMP") {
    const match = type === "TIMESTAMP"
      ? /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,6}))?Z$/.exec(value)
      : /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,6}))?$/.exec(value);
    const fraction = match?.[7];
    return Boolean(match && validCivilDate(Number(match[1]), Number(match[2]), Number(match[3]))
      && Number(match[4]) <= 23 && Number(match[5]) <= 59 && Number(match[6]) <= 59
      && (!fraction || fraction.at(-1) !== "0"));
  }
  const match = /^(-)?([0-9]{2,3}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,6}))?$/.exec(value);
  if (!match) return false;
  const hours = Number(match[2]);
  const minutes = Number(match[3]);
  const seconds = Number(match[4]);
  const fraction = match[5];
  const hoursText = match[2] ?? "";
  const isNegativeZero = match[1] === "-" && hours === 0 && minutes === 0 && seconds === 0 && (!fraction || /^0+$/.test(fraction));
  return hours <= 838 && minutes <= 59 && seconds <= 59 && hoursText.length === (hours <= 99 ? 2 : 3)
    && !isNegativeZero && (!fraction || fraction.at(-1) !== "0");
}

function scalarFrame(value: unknown, spelling: string): Uint8Array | null {
  const type = spelling.toUpperCase().trim();
  if (value === null) return frame(0x00, new Uint8Array());
  if (value === undefined) return null;
  if (/^(BOOL|BOOLEAN)(\b|\()/.test(type)) return typeof value === "boolean" ? frame(0x01, Uint8Array.of(value ? 1 : 0)) : null;
  const integer = /^(TINYINT|SMALLINT|MEDIUMINT|INT|INTEGER|BIGINT)(\b|\()/.exec(type);
  if (integer) {
    try {
      const bits = ({ TINYINT: 8, SMALLINT: 16, MEDIUMINT: 24, INT: 32, INTEGER: 32, BIGINT: 64 } as const)[integer[1] as "TINYINT" | "SMALLINT" | "MEDIUMINT" | "INT" | "INTEGER" | "BIGINT"];
      const unsigned = /\bUNSIGNED\b/.test(type);
      if (typeof value === "number" && (!Number.isSafeInteger(value) || !Number.isInteger(value))) return null;
      const number = typeof value === "bigint" ? value : BigInt(String(value));
      const lower = unsigned ? 0n : -(1n << BigInt(bits - 1));
      const upper = unsigned ? (1n << BigInt(bits)) - 1n : (1n << BigInt(bits - 1)) - 1n;
      if (number < lower || number > upper) return null;
      const payload = new Uint8Array(8);
      const view = new DataView(payload.buffer);
      if (unsigned) view.setBigUint64(0, number, false); else view.setBigInt64(0, number, false);
      return frame(unsigned ? 0x11 : 0x10, payload);
    } catch { return null; }
  }
  if (/^(CHAR|VARCHAR|TINYTEXT|TEXT|MEDIUMTEXT|LONGTEXT|JSON|ENUM)(\b|\()/.test(type)) {
    return typeof value === "string" ? frame(0x20, new TextEncoder().encode(value)) : null;
  }
  if (/^(BINARY|VARBINARY|TINYBLOB|BLOB|MEDIUMBLOB|LONGBLOB)(\b|\()/.test(type)) {
    if (value instanceof ArrayBuffer) return frame(0x21, new Uint8Array(value));
    if (ArrayBuffer.isView(value)) return frame(0x21, new Uint8Array(value.buffer, value.byteOffset, value.byteLength));
    return null;
  }
  if (/^DATE\b/.test(type)) return canonicalTemporal(value, "DATE") ? frame(0x30, new TextEncoder().encode(value)) : null;
  if (/^DATETIME\b/.test(type)) return canonicalTemporal(value, "DATETIME") ? frame(0x31, new TextEncoder().encode(value)) : null;
  if (/^TIMESTAMP\b/.test(type)) return canonicalTemporal(value, "TIMESTAMP") ? frame(0x32, new TextEncoder().encode(value)) : null;
  if (/^TIME\b/.test(type)) return canonicalTemporal(value, "TIME") ? frame(0x33, new TextEncoder().encode(value)) : null;
  if (/^FLOAT\b/.test(type)) {
    const number = Number(value);
    if (!Number.isFinite(number)) return null;
    const payload = new Uint8Array(4);
    const view = new DataView(payload.buffer);
    view.setFloat32(0, Object.is(number, -0) ? 0 : number, false);
    if (!Number.isFinite(view.getFloat32(0, false))) return null;
    return frame(0x13, payload);
  }
  if (/^(DOUBLE|REAL)\b/.test(type)) {
    const number = Number(value);
    if (!Number.isFinite(number)) return null;
    const payload = new Uint8Array(8);
    new DataView(payload.buffer).setFloat64(0, Object.is(number, -0) ? 0 : number, false);
    return frame(0x14, payload);
  }
  // SET, BIT, DECIMAL and unknown scalar types intentionally have no approximate identity encoding.
  return null;
}

function compareBytes(left: Uint8Array, right: Uint8Array): number {
  for (let index = 0; index < Math.min(left.length, right.length); index += 1) {
    const difference = (left[index] ?? 0) - (right[index] ?? 0);
    if (difference) return difference;
  }
  return left.length - right.length;
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
  const hash = new Sha256().update(encoder.encode("gateway-vnext:row:v1\0")).update(bytes(...parts)).digest();
  return `sha256:${hash}`;
}

/** Computes the row identity only when the comparison key has an exact supported encoding. */
export function snapshotRowIdentity(row: Record<string, unknown>, table: SurfaceTable): string | null {
  const keyColumns = table.compare?.compare_key_columns ?? [];
  return keyColumns.length ? rowDigest(row, table, keyColumns) : null;
}

function snapshotRowIdentities(rows: Record<string, unknown>[], table: SurfaceTable): Array<string | null> {
  return rows.map((row) => snapshotRowIdentity(row, table));
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

function sideIdentity(record: RowDiffRecord, side: "before" | "current"): string | null {
  const values = record as Record<string, unknown>;
  const specific = normalizeRowIdentity(values[side === "before" ? "before_row_identity" : "current_row_identity"] as never);
  return specific ?? normalizeRowIdentity(record.row_identity ?? undefined);
}

function rowRiskMap(annotations: RiskAnnotation[]): Map<string, RiskLevel> {
  const risks = new Map<string, RiskLevel>();
  for (const annotation of annotations) {
    for (const identity of riskAnnotationRowIdentities(annotation)) risks.set(identity, annotation.risk_level);
  }
  return risks;
}

function validateLocations(input: {
  records: RowDiffRecord[];
  annotations: RiskAnnotation[];
  beforeIdentities: Array<string | null>;
  currentIdentities: Array<string | null>;
  hasBeforeSnapshot: boolean;
  hasCurrentSnapshot: boolean;
}): boolean {
  const uniqueOnSide = (identities: Array<string | null>) => {
    const present = identities.filter((identity): identity is string => identity !== null);
    return new Set(present).size === present.length;
  };
  if (input.hasBeforeSnapshot && !uniqueOnSide(input.beforeIdentities)) return false;
  if (input.hasCurrentSnapshot && !uniqueOnSide(input.currentIdentities)) return false;

  const matchesIdentity = (identities: Array<string | null>, identity: string | null) =>
    identity === null ? [] : identities.flatMap((value, index) => value === identity ? [index] : []);
  const matchesPosition = (length: number, value: unknown) => {
    const position = positionNumber(value);
    return position !== null && position <= length ? [position - 1] : [];
  };
  const beforeOwners = new Map<number, number>();
  const currentOwners = new Map<number, number>();
  for (const record of input.records) {
    const kind = String(record.record_kind ?? "");
    if (!ROW_KINDS.has(kind)) continue;
    const ordered = kind.startsWith("ORDERED_");
    const beforeMatches = ordered
      ? matchesPosition(input.beforeIdentities.length, record.before_position)
      : matchesIdentity(input.beforeIdentities, sideIdentity(record, "before"));
    const currentMatches = ordered
      ? matchesPosition(input.currentIdentities.length, record.current_position)
      : matchesIdentity(input.currentIdentities, sideIdentity(record, "current"));
    if (DELETED_KINDS.has(kind)) {
      if (input.hasBeforeSnapshot && beforeMatches.length !== 1) return false;
    } else if (ADDED_KINDS.has(kind)) {
      if (input.hasCurrentSnapshot && currentMatches.length !== 1) return false;
    } else if (MODIFIED_KINDS.has(kind)) {
      if (input.hasBeforeSnapshot && beforeMatches.length !== 1) return false;
      if (input.hasCurrentSnapshot && currentMatches.length !== 1) return false;
    }
    const claimsBefore = input.hasBeforeSnapshot && (DELETED_KINDS.has(kind) || MODIFIED_KINDS.has(kind));
    const claimsCurrent = input.hasCurrentSnapshot && (ADDED_KINDS.has(kind) || MODIFIED_KINDS.has(kind));
    if (claimsBefore) {
      const index = beforeMatches[0];
      if (index === undefined || (beforeOwners.get(index) ?? 0) > 0) return false;
      beforeOwners.set(index, 1);
    }
    if (claimsCurrent) {
      const index = currentMatches[0];
      if (index === undefined || (currentOwners.get(index) ?? 0) > 0) return false;
      currentOwners.set(index, 1);
    }
  }

  for (const annotation of input.annotations) {
    if (annotation.target.target_type !== "ROW" && annotation.target.target_type !== "ROW_PAIR") continue;
    const linkedRecords = input.records.filter((record) => {
      if (!ROW_KINDS.has(String(record.record_kind))) return false;
      const beforeIdentity = sideIdentity(record, "before");
      const currentIdentity = sideIdentity(record, "current");
      if (annotation.target.target_type === "ROW") {
        const identity = normalizeRowIdentity(annotation.target.row_identity ?? undefined);
        return identity !== null && (identity === beforeIdentity || identity === currentIdentity);
      }
      const annotationBefore = normalizeRowIdentity(annotation.target.before_row_identity ?? undefined);
      const annotationCurrent = normalizeRowIdentity(annotation.target.current_row_identity ?? undefined);
      return (annotationBefore !== null || annotationCurrent !== null)
        && (annotationBefore === null || annotationBefore === beforeIdentity)
        && (annotationCurrent === null || annotationCurrent === currentIdentity);
    });
    if (linkedRecords.length > 1) return false;
    if (linkedRecords.length === 1) continue;

    const unrecordedIdentity = annotation.target.target_type === "ROW_PAIR"
      ? normalizeRowIdentity(annotation.target.current_row_identity ?? undefined) ?? normalizeRowIdentity(annotation.target.before_row_identity ?? undefined)
      : normalizeRowIdentity(annotation.target.row_identity ?? undefined);
    const validationSide = input.hasCurrentSnapshot ? input.currentIdentities : input.hasBeforeSnapshot ? input.beforeIdentities : [];
    if (matchesIdentity(validationSide, unrecordedIdentity).length !== 1) return false;
  }
  return true;
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
      key, kind: "collapsed", rowNumber: run[0]?.rowNumber ?? null, rowIdentity: null, riskLevel: null,
      recordKind: null, semanticKind: null, beforePosition: null, currentPosition: null,
      changedColumns: [], values: {}, pairKey: null, collapsedCount: run.length, collapsedRows: run,
    });
  }
  return output;
}

export interface BrowseRowsResult { rows: BrowseRow[]; locationValid: boolean }

export function buildBrowseRows(input: {
  table: SurfaceTable;
  beforeRows: Record<string, unknown>[];
  currentRows: Record<string, unknown>[];
  records: RowDiffRecord[];
  annotations: RiskAnnotation[];
  hasBeforeSnapshot?: boolean;
  hasCurrentSnapshot?: boolean;
  onlyInteresting?: boolean;
  rowFilter?: { column: string; value: unknown } | null;
  search?: string;
  expandedRuns?: ReadonlySet<string>;
}): BrowseRowsResult {
  const hasBeforeSnapshot = input.hasBeforeSnapshot ?? input.beforeRows.length > 0;
  const hasCurrentSnapshot = input.hasCurrentSnapshot ?? input.currentRows.length > 0;
  const records = input.records.filter((record) => typeof record.record_kind === "string");
  const beforeIdentities = snapshotRowIdentities(input.beforeRows, input.table);
  const currentIdentities = snapshotRowIdentities(input.currentRows, input.table);
  const locationValid = validateLocations({ records, annotations: input.annotations, beforeIdentities, currentIdentities, hasBeforeSnapshot, hasCurrentSnapshot });
  const risks = locationValid ? rowRiskMap(input.annotations) : new Map<string, RiskLevel>();
  const rows: BrowseRow[] = [];
  let insertion = 0;
  const makeRow = (args: {
    key: string; kind: BrowseRowKind; source: Record<string, unknown>; rowNumber: number | null;
    rowNumberTitle?: string; identity?: string | null; record?: RowDiffRecord; values?: Record<string, unknown>;
    pairKey?: string | null; formulaChanged?: boolean;
  }): BrowseRow => {
    const record = args.record;
    const interval = record?.interval && typeof record.interval === "object" ? record.interval as Record<string, unknown> : {};
    return {
      key: args.key, kind: args.kind, rowNumber: args.rowNumber, ...(args.rowNumberTitle ? { rowNumberTitle: args.rowNumberTitle } : {}),
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

  const tableKind = input.table.change_kind ?? input.table.table_status;
  if (tableKind === "ADDED" || tableKind === "ADDED_TABLE") {
    input.currentRows.forEach((source, index) => rows.push(makeRow({ key: `table-added:${index}`, kind: "added", source, rowNumber: index + 1, identity: currentIdentities[index] })));
  } else if (tableKind === "DELETED" || tableKind === "DELETED_TABLE") {
    input.beforeRows.forEach((source, index) => rows.push(makeRow({ key: `table-deleted:${index}`, kind: "deleted", source, rowNumber: index + 1, identity: beforeIdentities[index] })));
  } else if (locationValid) {
    const consumed = new Set<RowDiffRecord>();
    const orderedRecordAt = (side: "before" | "current", position: number) => records.find((record) => {
      const kind = String(record.record_kind);
      const targetPosition = positionNumber(record[side === "before" ? "before_position" : "current_position"]);
      return kind.startsWith("ORDERED_") && targetPosition === position;
    });
    input.currentRows.forEach((source, index) => {
      const identity = currentIdentities[index] ?? null;
      const candidates = records.filter((record) => {
        const kind = String(record.record_kind);
        return !consumed.has(record) && !DELETED_KINDS.has(kind) && !kind.startsWith("BLANK_")
          && ((identity !== null && sideIdentity(record, "current") === identity)
            || (kind.startsWith("ORDERED_") && positionNumber(record.current_position) === index + 1));
      });
      const candidate = candidates[0] ?? (!input.records.some((record) => ROW_KINDS.has(String(record.record_kind)))
        ? orderedRecordAt("current", index + 1) : undefined);
      if (!candidate) {
        rows.push(makeRow({ key: `current:${index + 1}`, kind: "unchanged", source, rowNumber: index + 1, identity }));
        return;
      }
      consumed.add(candidate);
      const kind = String(candidate.record_kind);
      if (kind === "ORDERED_ROW_MOVED") {
        rows.push(makeRow({ key: `record:moved:${index + 1}`, kind: "ordered", source,
          rowNumber: positionNumber(candidate.current_position) ?? index + 1, identity, record: candidate }));
        return;
      }
      if (MODIFIED_KINDS.has(kind)) {
        const beforeIdentity = sideIdentity(candidate, "before");
        const beforeIndex = kind.startsWith("ORDERED_")
          ? (positionNumber(candidate.before_position) ?? 0) - 1
          : beforeIdentity ? beforeIdentities.findIndex((value) => value === beforeIdentity) : -1;
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
        if (hasBeforeSnapshot && beforeIndex >= 0) {
          beforeValues = input.beforeRows[beforeIndex] ?? recordValues(candidate.before_values);
          beforeNumber = positionNumber(candidate.before_position) ?? beforeIndex + 1;
        } else {
          const old = recordValues(candidate.before_values);
          const keys = new Set(input.table.compare?.compare_key_columns ?? []);
          beforeValues = {};
          for (const key of keys) if (key in source) beforeValues[key] = source[key];
          for (const column of changedColumns) if (column in old) beforeValues[column] = old[column];
          beforeNumber = null;
          title = "改前值不在本 bundle 中";
        }
        const pairKey = `pair:${beforeIdentity ?? identity ?? index + 1}`;
        rows.push(makeRow({ key: `${pairKey}:before`, kind: "modified-before", source: beforeValues, rowNumber: beforeNumber,
          rowNumberTitle: title, identity: beforeIdentity ?? identity, record: candidate, values: beforeValues, pairKey }));
        rows.push(makeRow({ key: `${pairKey}:after`, kind: "modified-after", source, rowNumber: positionNumber(candidate.current_position) ?? index + 1,
          identity, record: candidate, values: source, pairKey, formulaChanged }));
      } else {
        rows.push(makeRow({ key: `record:${identity ?? index + 1}`, kind: "added",
          source, rowNumber: positionNumber(candidate.current_position) ?? index + 1, identity, record: candidate }));
      }
    });

    if (!hasCurrentSnapshot && hasBeforeSnapshot) {
      input.beforeRows.forEach((source, index) => {
        const identity = beforeIdentities[index] ?? null;
        const record = records.find((candidate) => {
          const kind = String(candidate.record_kind);
          if (!DELETED_KINDS.has(kind) && !MODIFIED_KINDS.has(kind)) return false;
          return kind.startsWith("ORDERED_")
            ? positionNumber(candidate.before_position) === index + 1
            : identity !== null && sideIdentity(candidate, "before") === identity;
        });
        if (!record) {
          rows.push(makeRow({ key: `before-only:${index + 1}`, kind: "unchanged", source, rowNumber: index + 1, identity }));
          return;
        }
        consumed.add(record);
        const kind = String(record.record_kind);
        const rowKind = DELETED_KINDS.has(kind) ? "deleted" : "modified-before";
        const pairKey = rowKind === "modified-before" ? `pair:${identity ?? index + 1}` : null;
        rows.push(makeRow({ key: `${rowKind}:${identity ?? index + 1}`, kind: rowKind, source, rowNumber: positionNumber(record.before_position) ?? index + 1, identity, record, pairKey }));
      });
    }

    for (const record of records) {
      if (consumed.has(record)) continue;
      const kind = String(record.record_kind);
      if (DELETED_KINDS.has(kind)) {
        const identity = sideIdentity(record, "before");
        const beforeIndex = kind.startsWith("ORDERED_")
          ? (positionNumber(record.before_position) ?? 0) - 1
          : identity ? beforeIdentities.findIndex((value) => value === identity) : -1;
        const source = hasBeforeSnapshot && beforeIndex >= 0 ? input.beforeRows[beforeIndex] : recordValues(record.before_values);
        rows.push(makeRow({ key: `deleted:${identity ?? insertion}`, kind: "deleted", source, values: source,
          rowNumber: hasBeforeSnapshot ? positionNumber(record.before_position) ?? beforeIndex + 1 : null,
          rowNumberTitle: hasBeforeSnapshot ? undefined : "改前行号不在本 bundle 中", identity, record }));
        insertion += 1;
        consumed.add(record);
      } else if (kind.startsWith("BLANK_")) {
        const interval = record.interval && typeof record.interval === "object" ? record.interval as Record<string, unknown> : {};
        const position = positionNumber(record.before_position) ?? positionNumber(interval.before_start)
          ?? positionNumber(record.current_position) ?? positionNumber(interval.current_start) ?? input.currentRows.length + insertion + 1;
        rows.push(makeRow({ key: `blank:${insertion}`, kind: "blank", source: {}, rowNumber: position, record, values: {} }));
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
        if (row.kind === "modified-before" && row.pairKey) return afterPositionByPair.get(row.pairKey) ?? (!hasCurrentSnapshot ? row.beforePosition ?? row.rowNumber : row.currentPosition ?? row.rowNumber) ?? Number.MAX_SAFE_INTEGER;
        return row.currentPosition ?? row.rowNumber ?? Number.MAX_SAFE_INTEGER;
      };
      return position(left) - position(right);
    });
  } else {
    const fallbackRows = hasCurrentSnapshot ? input.currentRows : input.beforeRows;
    fallbackRows.forEach((source, index) => rows.push(makeRow({ key: `fallback:${index + 1}`, kind: "unchanged", source, rowNumber: index + 1, identity: null })));
  }

  let visible = rows;
  if (input.rowFilter) {
    const expected = String(input.rowFilter.value);
    const matches = (row: BrowseRow) => normalizeDisplayScalar(row.values[input.rowFilter!.column]) === expected;
    const pairs = new Map<string, BrowseRow[]>();
    for (const row of rows) if (row.pairKey) pairs.set(row.pairKey, [...(pairs.get(row.pairKey) ?? []), row]);
    visible = rows.filter((row) => row.pairKey ? (pairs.get(row.pairKey) ?? []).some(matches) : matches(row));
  }
  const query = input.search?.trim().toLocaleLowerCase();
  visible = visible.filter((row) => !query || displayRowSearchText(row, input.table.columns ?? []).includes(query));
  if (input.onlyInteresting) visible = collapseUnchangedRows(visible, input.expandedRuns ?? new Set());
  return { rows: visible, locationValid };
}

export function normalizeDisplayScalar(value: unknown): string { return displayValue(value); }
