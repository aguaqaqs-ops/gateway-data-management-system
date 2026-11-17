import { createHash } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SOURCE = resolve(process.cwd(), "src/test/fixtures/source");

async function listFiles(root: string): Promise<string[]> {
  const entries = await readdir(root, { withFileTypes: true });
  const nested = await Promise.all(
    entries.map(async (entry) => {
      const path = join(root, entry.name);
      return entry.isDirectory() ? listFiles(path) : [path];
    }),
  );
  return nested.flat();
}

describe("backend producer fixture import", () => {
  it("matches the producer archive member list byte for byte", async () => {
    const provenance = JSON.parse(
      await readFile(join(SOURCE, "backend-provenance.json"), "utf8"),
    ) as { file_digests: string; generator_commit: string };
    expect(provenance.generator_commit).toMatch(/^[0-9a-f]{40}$/);
    const expected = new Map(
      (await readFile(join(SOURCE, provenance.file_digests), "utf8"))
        .trim()
        .split("\n")
        .map((line) => {
          const match = /^([0-9a-f]{64}) {2}(.+)$/.exec(line);
          if (!match) throw new Error(`bad digest line: ${line}`);
          return [match[2] as string, match[1] as string] as const;
        }),
    );
    const root = join(SOURCE, "backend");
    const actual = new Map<string, string>();
    for (const path of await listFiles(root)) {
      actual.set(
        relative(root, path).split("\\").join("/"),
        createHash("sha256")
          .update(await readFile(path))
          .digest("hex"),
      );
    }
    expect([...actual.keys()].sort()).toEqual([...expected.keys()].sort());
    for (const [path, digest] of expected) expect(actual.get(path), path).toBe(digest);
  });
});
