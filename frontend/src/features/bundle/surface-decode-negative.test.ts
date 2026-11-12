import { describe, expect, it } from "vitest";
import { MemoryBundleStore, type InstalledBundle } from "../bundle/local-bundle";
import { loadComparisonPresentation } from "../bundle/presentation";
import type { BundleClosure, BundleManifest } from "../bundle/posix-tar";
import { installedFixtureBundle, sha256Hex } from "../../test/helpers";

const FIXTURE = "preview-full";
const PAIR = "initial_to_modified";

interface ClonedBundle {
  bundle: InstalledBundle;
  manifest: BundleManifest;
  closure: BundleClosure;
}

function flipHexTail(value: string): string {
  const tail = value.slice(-1);
  return `${value.slice(0, -1)}${tail === "0" ? "1" : "0"}`;
}

/** Installs the generated fixture, mutates one surface field, and re-commits the clone. */
async function installMutatedSurface(mutate: (surface: Record<string, unknown>) => void): Promise<ClonedBundle> {
  const installed = await installedFixtureBundle(FIXTURE);
  const sourceEntries = installed.manifest.closure.entries as unknown as Array<Record<string, unknown>>;
  const surfaceEntry = sourceEntries.find((entry) => entry["kind"] === "SURFACE" && entry["pair_id"] === PAIR);
  if (!surfaceEntry || typeof surfaceEntry["logical_path"] !== "string") throw new Error("fixture has no surface entry");
  const surfacePath = surfaceEntry["logical_path"] as string;
  const surfaceBytes = new Uint8Array(await (await installed.bundle.readArtifact(surfacePath)).arrayBuffer());
  const surface = JSON.parse(new TextDecoder().decode(surfaceBytes)) as Record<string, unknown>;
  mutate(surface);
  const mutatedBytes = new TextEncoder().encode(JSON.stringify(surface));
  const mutatedDigest = `sha256:${sha256Hex(mutatedBytes)}`;
  const store = new MemoryBundleStore();
  const transaction = await store.begin(`sha256:${"0".repeat(64)}`);
  const nextEntries: Array<Record<string, unknown>> = [];
  for (const entry of sourceEntries) {
    const logicalPath = entry["logical_path"] as string;
    const bytes = logicalPath === surfacePath
      ? mutatedBytes
      : new Uint8Array(await (await installed.bundle.readArtifact(logicalPath)).arrayBuffer());
    const sink = await transaction.openArtifact(logicalPath);
    if (!("write" in sink)) throw new Error("memory store must return an artifact sink");
    await sink.write(bytes);
    await sink.close();
    if (logicalPath === surfacePath) {
      const integrity = { ...((entry["integrity"] ?? {}) as Record<string, unknown>), raw_sha256: mutatedDigest, size_bytes: bytes.byteLength };
      nextEntries.push({ ...entry, integrity });
    } else {
      nextEntries.push(entry);
    }
  }
  const nextManifest = {
    ...installed.manifest,
    closure: { ...(installed.manifest.closure as unknown as Record<string, unknown>), entries: nextEntries },
    closure_entries: (installed.manifest.closure_entries as unknown as Array<Record<string, unknown>>).map((entry) =>
      entry["logical_path"] === surfacePath
        ? { ...entry, raw_sha256: mutatedDigest, size_bytes: mutatedBytes.byteLength }
        : entry),
  } as unknown as BundleManifest;
  const nextClosure = {
    ...installed.closure,
    closure_entries: (installed.closure.closure_entries as unknown as Array<Record<string, unknown>>).map((entry) =>
      entry["logical_path"] === surfacePath
        ? { ...entry, raw_sha256: mutatedDigest, size_bytes: mutatedBytes.byteLength }
        : entry),
  } as unknown as BundleClosure;
  await transaction.commit(nextManifest, nextClosure);
  const bundle = await store.open(`sha256:${"0".repeat(64)}`);
  if (!bundle) throw new Error("mutated bundle was not committed");
  return { bundle, manifest: nextManifest, closure: nextClosure };
}

function businessNavigationOf(surface: Record<string, unknown>): Record<string, unknown> {
  const projections = surface["projections"] as Array<Record<string, unknown>>;
  const navigation = projections.find((projection) => projection["projection_kind"] === "BUSINESS_NAVIGATION");
  if (!navigation) throw new Error("mutated surface lost its navigation projection");
  return navigation;
}

function deviceTableOf(surface: Record<string, unknown>): Record<string, unknown> {
  const tables = surface["tables"] as Array<Record<string, unknown>>;
  const device = tables.find((table) => table["table_name"] === "device");
  if (!device) throw new Error("mutated surface lost the device table");
  return device;
}

describe("surface and navigation strict decoding from generated fixtures", () => {
  it("loads the unmutated generated fixture", async () => {
    const { bundle } = await installMutatedSurface(() => {});
    const presentation = await loadComparisonPresentation(bundle, PAIR);
    expect(presentation.surface.tables.length).toBeGreaterThan(0);
  });

  const mutations: Array<[string, (surface: Record<string, unknown>) => void, RegExp]> = [
    ["缺导航", (surface) => { surface["projections"] = []; }, /必须且只能包含一个/],
    ["两份导航", (surface) => {
      const projections = surface["projections"] as Array<Record<string, unknown>>;
      projections.push(structuredClone(businessNavigationOf(surface)));
    }, /必须且只能包含一个/],
    ["surface 版本前缀而非精确匹配", (surface) => { surface["surface_contract_version"] = "backend-vnext/comparison-surface/v5"; }, /comparison surface contract version/],
    ["display_order 不连续", (surface) => {
      const columns = deviceTableOf(surface)["columns"] as Array<Record<string, unknown>>;
      columns[1]!["display_order"] = 5;
    }, /display_order/],
    ["binding 与表引用空值不一致", (surface) => {
      const bindings = deviceTableOf(surface)["table_content_bindings"] as Record<string, unknown>;
      bindings["before"] = null;
    }, /空值不一致/],
    ["surface 记录引用与 closure 大小不同", (surface) => {
      const ref = (deviceTableOf(surface)["records_refs"] as Record<string, unknown>)["records_ref"] as Record<string, unknown>;
      ref["size_bytes"] = (ref["size_bytes"] as number) + 1;
    }, /摘要与 closure 不一致/],
    ["ROW_LOCATOR 条目 SHA 改一位", (surface) => {
      const ref = deviceTableOf(surface)["row_locator_ref"] as Record<string, unknown>;
      ref["raw_sha256"] = flipHexTail(ref["raw_sha256"] as string);
    }, /摘要与 closure 不一致/],
  ];
  it.each(mutations)("rejects %s as a decode error for the pair", async (_, mutate, pattern) => {
    const { bundle } = await installMutatedSurface(mutate);
    await expect(loadComparisonPresentation(bundle, PAIR)).rejects.toThrow(pattern);
  });
});
