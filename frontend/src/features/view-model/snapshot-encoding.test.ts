import { describe, expect, it } from "vitest";
import {
  decodeSnapshotEncodings,
  matchesTypedPredicate,
  parseStrictIntegerText,
  SNAPSHOT_ENCODING_METADATA_KEY,
  type SnapshotColumnEncoding,
} from "./snapshot-encoding";

function integerColumn(overrides: Partial<SnapshotColumnEncoding> = {}): SnapshotColumnEncoding {
  return {
    columnName: "gid",
    scalarKind: "integer",
    declaredBits: 64,
    signed: true,
    sqlType: "BIGINT",
    logicalType: "standard",
    physicalType: "utf8",
    declaredKind: "signed-integer",
    ...overrides,
  };
}

function stringColumn(name = "payload"): SnapshotColumnEncoding {
  return {
    columnName: name,
    scalarKind: "string",
    declaredBits: null,
    signed: true,
    sqlType: "TEXT",
    logicalType: "standard",
    physicalType: "utf8",
    declaredKind: "string",
  };
}

function unsupportedColumn(name = "flag"): SnapshotColumnEncoding {
  return {
    columnName: name,
    scalarKind: "unsupported",
    declaredBits: null,
    signed: true,
    sqlType: "BOOLEAN",
    logicalType: "standard",
    physicalType: "bool",
    declaredKind: "boolean",
  };
}

function metadata(columns: Array<Record<string, unknown>>) {
  return [{ key: SNAPSHOT_ENCODING_METADATA_KEY, value: JSON.stringify({ columns }) }];
}

function integerPayload(column: Record<string, unknown> = {}) {
  return {
    canonical_name: "gid",
    display_name: "gid",
    ordinal: 0,
    sql_type: "BIGINT",
    logical_type: "standard",
    nullable: true,
    physical_type: "utf8",
    declared_type: { kind: "signed-integer", bits: 64 },
    enum_or_set_labels: null,
    ...column,
  };
}

describe("snapshot encoding metadata decoding", () => {
  it("resolves integer and string columns from the same-side file metadata", () => {
    const encodings = decodeSnapshotEncodings(metadata([integerPayload(), { ...integerPayload(), canonical_name: "payload", sql_type: "TEXT", declared_type: { kind: "string" } }]), "表 device_cfg.改后");
    expect(encodings.get("gid")?.scalarKind).toBe("integer");
    expect(encodings.get("payload")?.scalarKind).toBe("string");
  });

  it("marks non-predicate scalar kinds as unsupported", () => {
    const encodings = decodeSnapshotEncodings(metadata([
      { ...integerPayload(), canonical_name: "flag", physical_type: "bool", declared_type: { kind: "boolean" } },
      { ...integerPayload(), canonical_name: "amount", declared_type: { kind: "decimal", precision: 10, scale: 2 } },
      { ...integerPayload(), canonical_name: "when", declared_type: { kind: "datetime" } },
      { ...integerPayload(), canonical_name: "blob", physical_type: "binary", declared_type: { kind: "binary" } },
      { ...integerPayload(), canonical_name: "mystery", declared_type: null, sql_type: "UNKNOWN_TYPE" },
    ]), "表 demo.改后");
    for (const name of ["flag", "amount", "when", "blob", "mystery"]) {
      expect(encodings.get(name)?.scalarKind).toBe("unsupported");
    }
  });

  it.each([
    ["missing key", undefined],
    ["malformed JSON", "{not json"],
    ["missing columns", JSON.stringify({})],
    ["nameless column", JSON.stringify({ columns: [{ sql_type: "BIGINT" }] })],
  ])("rejects %s file metadata", (_, value) => {
    const entries = value === undefined ? [] : [{ key: SNAPSHOT_ENCODING_METADATA_KEY, value: value as string }];
    expect(() => decodeSnapshotEncodings(entries, "表 demo.改后")).toThrow(/元数据|结构无效/);
  });

  it("rejects an integer declaration that contradicts the physical type or width", () => {
    expect(() => decodeSnapshotEncodings(metadata([{ ...integerPayload(), physical_type: "binary" }]), "表 demo.改后")).toThrow(/矛盾/);
    expect(() => decodeSnapshotEncodings(metadata([{ ...integerPayload(), declared_type: { kind: "signed-integer", bits: 128 } }]), "表 demo.改后")).toThrow(/位宽/);
  });
});

describe("strict canonical decimal integers", () => {
  const encoding = integerColumn();
  const acceptCases: Array<[string, bigint]> = [
    ["0", 0n],
    ["7", 7n],
    ["-7", -7n],
    ["9007199254740991", 9007199254740991n],
    ["-9007199254740991", -9007199254740991n],
  ];
  it.each(acceptCases)("accepts %s", (text, expected) => {
    expect(parseStrictIntegerText(text, encoding, "改后筛选")).toBe(expected);
  });

  const rejectTexts: Array<[string, string]> = [
    ["负零", "-0"],
    ["前导零", "007"],
    ["正号前导零", "+7"],
    ["前导空白", " 7"],
    ["尾随空白", "7 "],
    ["小数", "7.0"],
    ["小数位", "7.5"],
    ["指数", "1e3"],
    ["十六进制", "0x7"],
    ["尾随字符", "7a"],
    ["空串", ""],
  ];
  it.each(rejectTexts)("rejects %s", (_, text) => {
    expect(() => parseStrictIntegerText(text, encoding, "改后筛选")).toThrow(/规范十进制/);
  });

  const rangeCases: Array<[string, string, SnapshotColumnEncoding]> = [
    ["超出安全整数", "9007199254740992", integerColumn()],
    ["低于安全整数", "-9007199254740992", integerColumn()],
    ["超出 TINYINT 上界", "128", integerColumn({ declaredBits: 8 })],
    ["低于 TINYINT 下界", "-129", integerColumn({ declaredBits: 8 })],
    ["无符号列出现负值", "-1", integerColumn({ signed: false, declaredKind: "unsigned-integer" })],
    ["超出无符号 8 位", "256", integerColumn({ declaredBits: 8, signed: false, declaredKind: "unsigned-integer" })],
  ];
  it.each(rangeCases)("rejects out-of-range %s", (_, text, column) => {
    expect(() => parseStrictIntegerText(text, column, "改后筛选")).toThrow(/范围/);
  });

  it("accepts TINYINT edges and unsigned zero", () => {
    expect(parseStrictIntegerText("127", integerColumn({ declaredBits: 8 }), "改后筛选")).toBe(127n);
    expect(parseStrictIntegerText("-128", integerColumn({ declaredBits: 8 }), "改后筛选")).toBe(-128n);
    expect(parseStrictIntegerText("0", integerColumn({ declaredBits: 8, signed: false, declaredKind: "unsigned-integer" }), "改后筛选")).toBe(0n);
  });
});

describe("typed predicate matching", () => {
  const gid = () => new Map([["gid", integerColumn()]]);
  const payload = () => new Map([["payload", stringColumn()]]);

  it("compares integer predicates by BigInt value", () => {
    expect(matchesTypedPredicate({ column: "gid", values: [8] }, { gid: "8" }, gid(), "改后筛选")).toBe(true);
    expect(matchesTypedPredicate({ column: "gid", values: [8] }, { gid: "9" }, gid(), "改后筛选")).toBe(false);
    expect(matchesTypedPredicate({ column: "gid", values: [8] }, { gid: 8 }, gid(), "改后筛选")).toBe(true);
    expect(matchesTypedPredicate({ column: "gid", values: [8] }, { gid: 8n }, gid(), "改后筛选")).toBe(true);
  });

  it("compares string predicates by raw value without trimming", () => {
    expect(matchesTypedPredicate({ column: "payload", values: [" 7"] }, { payload: " 7" }, payload(), "改后筛选")).toBe(true);
    expect(matchesTypedPredicate({ column: "payload", values: [" 7"] }, { payload: "7" }, payload(), "改后筛选")).toBe(false);
    expect(matchesTypedPredicate({ column: "payload", values: ["7"] }, { payload: " 7" }, payload(), "改后筛选")).toBe(false);
  });

  it("never matches NULL or a physically absent column", () => {
    expect(matchesTypedPredicate({ column: "gid", values: [0] }, { gid: null }, gid(), "改后筛选")).toBe(false);
    expect(matchesTypedPredicate({ column: "gid", values: [0] }, {}, gid(), "改后筛选")).toBe(false);
    expect(matchesTypedPredicate({ column: "missing", values: [0] }, { missing: "0" }, gid(), "改后筛选")).toBe(false);
    expect(matchesTypedPredicate(null, { gid: "8" }, gid(), "改后筛选")).toBe(false);
    expect(matchesTypedPredicate({ column: "gid", values: [8] }, null, gid(), "改后筛选")).toBe(false);
  });

  const categoryCases: Array<[string, import("./model").NavigationPredicate, Record<string, unknown>, ReadonlyMap<string, SnapshotColumnEncoding>]> = [
    ["字符串列配整数谓词", { column: "payload", values: [7] }, { payload: "7" }, payload()],
    ["整数列配字符串谓词", { column: "gid", values: ["7"] }, { gid: "7" }, gid()],
    ["不支持列配整数谓词", { column: "flag", values: [1] }, { flag: "1" }, new Map([["flag", unsupportedColumn()]])],
    ["不支持列配字符串谓词", { column: "flag", values: ["1"] }, { flag: "1" }, new Map([["flag", unsupportedColumn()]])],
    ["超范围谓词值", { column: "gid", values: [128] }, { gid: "128" }, new Map([["gid", integerColumn({ declaredBits: 8 })]])],
  ];
  it.each(categoryCases)("rejects %s as a decode error", (_, predicate, values, encodings) => {
    expect(() => matchesTypedPredicate(predicate, values, encodings, "改后筛选")).toThrow(/矛盾|范围/);
  });

  const valueCases: Array<[string, Record<string, unknown>]> = [
    ["空白整数文本", { gid: " 7" }],
    ["前导零整数文本", { gid: "007" }],
    ["负零整数文本", { gid: "-0" }],
    ["小整数文本", { gid: "7.5" }],
    ["指数整数文本", { gid: "1e2" }],
    ["超范围整数文本", { gid: "99999999999999999999" }],
    ["整数列出现对象值", { gid: { text: "x" } }],
  ];
  it.each(valueCases)("rejects contradictory integer value %s", (_, values) => {
    expect(() => matchesTypedPredicate({ column: "gid", values: [7] }, values, gid(), "改后筛选")).toThrow(/矛盾|规范|范围/);
  });

  it("rejects a non-string value in a string column", () => {
    expect(() => matchesTypedPredicate({ column: "payload", values: ["7"] }, { payload: 7 }, payload(), "改后筛选")).toThrow(/矛盾/);
  });
});
