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

const UPLOAD_SOURCE_MANIFEST = join(process.cwd(), "..", "vnext/fixtures/presentation-inputs/manifest.json");
const UPLOAD_SOURCE_NAMES = [
  "sql-baseline.sql", "sql-initial.sql", "sql-modified.sql", "sql-replacement-before.sql",
  "sql-replacement-current.sql", "logics-1.xml", "logics-2.xml", "logics-3.xml",
] as const;

function backendUploadDigests(): Record<string, string> {
  const manifest = JSON.parse(readFileSync(UPLOAD_SOURCE_MANIFEST, "utf8")) as { files: Array<{ path: string; sha256: string }> };
  return Object.fromEntries(manifest.files.filter((file) => (UPLOAD_SOURCE_NAMES as readonly string[]).includes(file.path)).map((file) => [file.path, file.sha256]));
}

function sha256(text: string): string {
  return createHash("sha256").update(text, "utf8").digest("hex");
}

describe("real-e2e upload inputs are derived from the shared source fixtures", () => {
  it("keeps the eight upload originals identical to the backend-owned input manifest", () => {
    const digests = backendUploadDigests();
    expect(Object.keys(digests).sort()).toEqual([...UPLOAD_SOURCE_NAMES].sort());
    for (const [name, digest] of Object.entries(digests)) {
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
