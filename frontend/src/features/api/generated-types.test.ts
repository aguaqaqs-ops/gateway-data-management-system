import { execFile } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * FE3a §5.4: the committed generated API types must match a fresh
 * `npm run generate:api-types` output byte for byte, so hand-edited
 * generated files cannot drift from `frontend/openapi.json`.
 */
describe("generated API types match the OpenAPI snapshot (§5.4)", () => {
  it("regenerates openapi.d.ts byte for byte", async () => {
    const workdir = await mkdtemp(join(tmpdir(), "fe3a-api-types-"));
    try {
      // N3: derive the CLI invocation from the npm script instead of
      // duplicating its arguments here; only the output path is redirected.
      const packageJson = JSON.parse(await readFile("package.json", "utf8")) as {
        scripts: Record<string, string>;
      };
      const [command, ...args] = packageJson.scripts["generate:api-types"].trim().split(/\s+/);
      if (!command || (!args.includes("--output") && !args.includes("-o"))) {
        throw new Error("generate:api-types script must name openapi-typescript and an output flag");
      }
      const outputFlag = args.includes("--output") ? "--output" : "-o";
      args[args.indexOf(outputFlag) + 1] = join(workdir, "openapi.d.ts");
      await new Promise<void>((resolve, reject) => {
        execFile(
          command,
          args,
          { cwd: process.cwd() },
          (error, stdout, stderr) => {
            if (error) {
              reject(
                new Error(
                  `openapi-typescript failed: ${error.message}\n${stdout}\n${stderr}`,
                ),
              );
              return;
            }
            resolve();
          },
        );
      });
      const [fresh, committed] = await Promise.all([
        readFile(join(workdir, "openapi.d.ts"), "utf8"),
        readFile("src/features/api/generated/openapi.d.ts", "utf8"),
      ]);
      expect(fresh).toBe(committed);
    } finally {
      await rm(workdir, { recursive: true, force: true });
    }
  }, 120000);
});
