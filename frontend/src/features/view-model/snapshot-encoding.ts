import { ComparisonDecodeError, type NavigationPredicate } from "./model";

/** Arrow schema metadata key carrying the backend column encoding payload. */
export const SNAPSHOT_ENCODING_METADATA_KEY = "gateway.sta.enc.v1";

const INTEGER_BITS: ReadonlySet<number> = new Set([8, 16, 24, 32, 64]);
const SAFE_MIN = -(2n ** 53n) + 1n;
const SAFE_MAX = 2n ** 53n - 1n;

/** Canonical decimal integer text: `0`, or a non-zero decimal without leading zeros. */
const CANONICAL_INTEGER_TEXT = /^(0|[1-9][0-9]*|-[1-9][0-9]*)$/;

export type SnapshotScalarKind = "integer" | "string" | "unsupported";

export interface SnapshotColumnEncoding {
  columnName: string;
  scalarKind: SnapshotScalarKind;
  declaredBits: number | null;
  signed: boolean;
  sqlType: string;
  logicalType: string;
  physicalType: string;
  declaredKind: string | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Decodes the same-side `gateway.sta.enc.v1` file metadata into per-column
 * scalar kinds. Anything the backend cannot publish predicates for (boolean,
 * decimal, float, dates, binary, bit, enum/set, json, unknown or missing
 * declared types) is `unsupported`, matching Business Navigation FE-BEB-13.
 */
export function decodeSnapshotEncodings(
  keyValueMetadata: ReadonlyArray<{ key: string; value?: string }> | undefined | null,
  where: string,
): Map<string, SnapshotColumnEncoding> {
  const raw = keyValueMetadata?.find((entry) => entry.key === SNAPSHOT_ENCODING_METADATA_KEY)?.value;
  if (raw === undefined || raw === null) {
    throw new ComparisonDecodeError(`${where} 缺少 ${SNAPSHOT_ENCODING_METADATA_KEY} 文件元数据`);
  }
  let payload: unknown;
  try {
    payload = JSON.parse(raw);
  } catch {
    throw new ComparisonDecodeError(`${where} 的 ${SNAPSHOT_ENCODING_METADATA_KEY} 不是合法 JSON`);
  }
  if (!isRecord(payload) || !Array.isArray(payload.columns)) {
    throw new ComparisonDecodeError(`${where} 的 ${SNAPSHOT_ENCODING_METADATA_KEY} 结构无效`);
  }
  const encodings = new Map<string, SnapshotColumnEncoding>();
  for (const item of payload.columns as unknown[]) {
    if (!isRecord(item) || typeof item["canonical_name"] !== "string") {
      throw new ComparisonDecodeError(`${where} 的 ${SNAPSHOT_ENCODING_METADATA_KEY} 列结构无效`);
    }
    const columnName: string = item["canonical_name"];
    const declaredType = isRecord(item["declared_type"]) ? item["declared_type"] : null;
    const declaredKind = typeof declaredType?.["kind"] === "string" ? (declaredType["kind"] as string) : null;
    const logicalType = typeof item["logical_type"] === "string" ? (item["logical_type"] as string) : "";
    const physicalType = typeof item["physical_type"] === "string" ? (item["physical_type"] as string) : "";
    const encoding: SnapshotColumnEncoding = {
      columnName,
      scalarKind: "unsupported",
      declaredBits: null,
      signed: true,
      sqlType: typeof item["sql_type"] === "string" ? (item["sql_type"] as string) : "",
      logicalType,
      physicalType,
      declaredKind: declaredKind,
    };
    if (logicalType === "standard" && (declaredKind === "signed-integer" || declaredKind === "unsigned-integer")) {
      if (physicalType !== "utf8") {
        throw new ComparisonDecodeError(`${where} 列 ${encoding.columnName} 的整数声明与物理类型矛盾`);
      }
      const bits: unknown = declaredType?.["bits"] ?? null;
      if (typeof bits !== "number" || !INTEGER_BITS.has(bits)) {
        throw new ComparisonDecodeError(`${where} 列 ${encoding.columnName} 的整数声明位宽无效`);
      }
      encoding.scalarKind = "integer";
      encoding.declaredBits = bits;
      encoding.signed = declaredKind === "signed-integer";
    } else if (logicalType === "standard" && declaredKind === "string") {
      encoding.scalarKind = "string";
    }
    if (encodings.has(encoding.columnName)) {
      throw new ComparisonDecodeError(`${where} 的 ${SNAPSHOT_ENCODING_METADATA_KEY} 列名重复：${encoding.columnName}`);
    }
    encodings.set(encoding.columnName, encoding);
  }
  return encodings;
}

function declaredRange(encoding: SnapshotColumnEncoding): { min: bigint; max: bigint } {
  const bits = BigInt(encoding.declaredBits ?? 64);
  if (!encoding.signed) return { min: 0n, max: 2n ** bits - 1n };
  return { min: -(2n ** (bits - 1n)), max: 2n ** (bits - 1n) - 1n };
}

function checkIntegerRange(value: bigint, encoding: SnapshotColumnEncoding, where: string): bigint {
  if (value < SAFE_MIN || value > SAFE_MAX) {
    throw new ComparisonDecodeError(`${where} 超出安全整数范围`);
  }
  const { min, max } = declaredRange(encoding);
  if (value < min || value > max) {
    throw new ComparisonDecodeError(`${where} 超出列 ${encoding.columnName} 的声明位宽与符号范围`);
  }
  return value;
}

/**
 * Strictly parses canonical decimal integer text into BigInt and checks the
 * safe range plus the declared width and signedness. Rejects negative zero,
 * whitespace, decimals, exponents and trailing characters.
 */
export function parseStrictIntegerText(text: string, encoding: SnapshotColumnEncoding, where: string): bigint {
  if (!CANONICAL_INTEGER_TEXT.test(text)) {
    throw new ComparisonDecodeError(`${where} 不是规范十进制整数`);
  }
  return checkIntegerRange(BigInt(text), encoding, `${where} 列 ${encoding.columnName}`);
}

function integerPredicateValues(predicate: NavigationPredicate): boolean {
  return predicate.values.every((value) => typeof value === "number");
}

/**
 * Validates a whole predicate against the same-side column encoding once
 * (category match plus declared range of every candidate value). Missing
 * columns are not an error here: a NULL or physically absent column simply
 * never matches.
 */
export function assertPredicateCompatible(
  predicate: NavigationPredicate | null,
  encodings: ReadonlyMap<string, SnapshotColumnEncoding> | null,
  where: string,
): void {
  if (!predicate) return;
  const encoding = encodings?.get(predicate.column);
  if (!encoding) return;
  if (integerPredicateValues(predicate)) {
    if (encoding.scalarKind !== "integer") {
      throw new ComparisonDecodeError(`${where} 的整数谓词与列 ${encoding.columnName} 的类型矛盾`);
    }
    for (const candidate of predicate.values) {
      checkIntegerRange(BigInt(candidate as number), encoding, `${where} 列 ${encoding.columnName}`);
    }
    return;
  }
  if (encoding.scalarKind !== "string") {
    throw new ComparisonDecodeError(`${where} 的字符串谓词与列 ${encoding.columnName} 的类型矛盾`);
  }
}

function unwrapScalar(value: unknown): unknown {
  if (value && typeof value === "object" && !(value instanceof ArrayBuffer) && !ArrayBuffer.isView(value)) {
    const document = value as Record<string, unknown>;
    if (Object.hasOwn(document, "text")) return document.text;
    return undefined;
  }
  return value;
}

/**
 * Typed set membership for one predicate side. Integer columns compare by
 * strictly parsed BigInt value, string columns compare the raw value without
 * trimming, and NULL or a physically absent column never matches. Any
 * predicate/category, physical type or value contradiction is a decode error
 * for the comparison pair.
 */
export function matchesTypedPredicate(
  predicate: NavigationPredicate | null,
  values: Record<string, unknown> | null,
  encodings: ReadonlyMap<string, SnapshotColumnEncoding> | null,
  where: string,
): boolean {
  if (!predicate || !values) return false;
  const raw = unwrapScalar(values[predicate.column]);
  if (raw === null || raw === undefined) return false;
  const encoding = encodings?.get(predicate.column);
  if (!encoding) return false;
  if (integerPredicateValues(predicate)) {
    if (encoding.scalarKind !== "integer") {
      throw new ComparisonDecodeError(`${where} 的整数谓词与列 ${encoding.columnName} 的类型矛盾`);
    }
    const candidates = (predicate.values as number[]).map((candidate) =>
      checkIntegerRange(BigInt(candidate), encoding, `${where} 列 ${encoding.columnName}`));
    let actual: bigint;
    if (typeof raw === "string") {
      actual = parseStrictIntegerText(raw, encoding, `${where} 列 ${encoding.columnName}`);
    } else if (typeof raw === "bigint") {
      actual = checkIntegerRange(raw, encoding, `${where} 列 ${encoding.columnName}`);
    } else if (typeof raw === "number") {
      if (!Number.isSafeInteger(raw)) {
        throw new ComparisonDecodeError(`${where} 列 ${encoding.columnName} 的值不是安全整数`);
      }
      actual = checkIntegerRange(BigInt(raw), encoding, `${where} 列 ${encoding.columnName}`);
    } else {
      throw new ComparisonDecodeError(`${where} 列 ${encoding.columnName} 的值与整数类型矛盾`);
    }
    return candidates.some((candidate) => candidate === actual);
  }
  if (encoding.scalarKind !== "string") {
    throw new ComparisonDecodeError(`${where} 的字符串谓词与列 ${encoding.columnName} 的类型矛盾`);
  }
  if (typeof raw !== "string") {
    throw new ComparisonDecodeError(`${where} 列 ${encoding.columnName} 的值与字符串类型矛盾`);
  }
  return (predicate.values as string[]).some((candidate) => raw === candidate);
}
