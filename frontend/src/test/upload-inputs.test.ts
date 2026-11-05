import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * FE3a Q10: the real-e2e upload inputs are derived from the shared source
 * fixtures by exactly two substitutions in `b1_n1_iec104_yc_list`. The shared
 * files stay untouched; the derived files are committed under
 * `e2e-real/fixtures/upload-inputs/`.
 */
const SOURCE_DIR = join(process.cwd(), "src/test/fixtures/source/upload-inputs");
const DERIVED_DIR = join(process.cwd(), "e2e-real/fixtures/upload-inputs");

const OLD_CREATE = "CREATE TABLE b1_n1_iec104_yc_list (no INT NOT NULL, value VARCHAR(32) NULL);";
const NEW_CREATE = "CREATE TABLE b1_n1_iec104_yc_list (gid INT NULL, no INT NOT NULL, value VARCHAR(32) NULL);";
const OLD_INSERT = "INSERT INTO b1_n1_iec104_yc_list VALUES (1, '无稳定 gid');";
const NEW_INSERT = "INSERT INTO b1_n1_iec104_yc_list VALUES (1, 1, '无稳定 gid');";

const SOURCE_SHA256 = {
  "sql-baseline.sql": "f6205557b237abeeac5d2832a5365273d326014bebdc87bd7d2c2ad95d1b7730",
  "sql-initial.sql": "83b2fa42fc9fb3bf196425eec4c8ccfd58e9720f85a045941204af2b0367c001",
  "sql-modified.sql": "57450fdce2e9ab27e695e48a7cb0c80475caa016c7c9beaeef41b30bea717773",
  "sql-replacement-before.sql": "7b696562f88ffc56146935fbd7023194a3e53f279e62fcf6b36d3857bdd1b48f",
  "sql-replacement-current.sql": "b71a5b8c19541c349fe34946dd66b26ec1783c7f0fcdd716fc6915c3ca133dd4",
  "logics-1.xml": "033a4c33fe7ef18caf5d3780862aaf2a82eba7e78cd8f147e0db0861ab60a53b",
  "logics-2.xml": "9eb1789efacd87bf6aed01320c34ba538b2a294df80956df60808c2201932de2",
  "logics-3.xml": "3387cc9165ab81cc7c8e2f95ecc0dc4562569730d7670b5607e10fe9e8fccbca",
} as const;

function sha256(text: string): string {
  return createHash("sha256").update(text, "utf8").digest("hex");
}

describe("real-e2e upload inputs are derived from the shared source fixtures", () => {
  it("leaves every shared source fixture byte-identical", () => {
    for (const [name, digest] of Object.entries(SOURCE_SHA256)) {
      expect(sha256(readFileSync(join(SOURCE_DIR, name), "utf8")), name).toBe(digest);
    }
  });

  it("contains exactly one replacement site per derived SQL file", () => {
    for (const name of ["sql-baseline.sql", "sql-initial.sql", "sql-modified.sql"]) {
      const text = readFileSync(join(SOURCE_DIR, name), "utf8");
      expect(text.split(OLD_CREATE)).toHaveLength(2);
      expect(text.split(OLD_INSERT)).toHaveLength(2);
    }
  });

  it("derives each committed SQL file by the two documented substitutions", () => {
    for (const name of ["sql-baseline.sql", "sql-initial.sql", "sql-modified.sql"]) {
      const source = readFileSync(join(SOURCE_DIR, name), "utf8");
      const derived = readFileSync(join(DERIVED_DIR, name), "utf8");
      expect(derived, name).toBe(source.replace(OLD_CREATE, NEW_CREATE).replace(OLD_INSERT, NEW_INSERT));
    }
  });

  it("keeps the replacement SQL and logics files in the shared directory only", () => {
    expect(readdirSync(DERIVED_DIR).sort()).toEqual([
      "sql-baseline.sql",
      "sql-initial.sql",
      "sql-modified.sql",
    ]);
  });
});
