import { Buffer } from "node:buffer";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { ReadableStream as NodeReadableStream } from "node:stream/web";
import { MemoryBundleStore } from "../features/bundle/local-bundle";
import { installBundleTar } from "../features/bundle/posix-tar";
import { loadComparisonPresentation, readLocalChangeRecords, readLocalTable, type LocalComparisonPresentation } from "../features/bundle/presentation";
import { readParquetMetadata, readParquetTable } from "../features/bundle/parquet-reader";
import { decodeSnapshotEncodings, type SnapshotColumnEncoding } from "../features/view-model/snapshot-encoding";
import { parseRowLocator, type RowLocatorRecord } from "../features/view-model/table-rows";
import type { NavigationFacts, NavigationRowFilter, RowDiffRecord, SurfaceTable } from "../features/view-model/model";

export function bytesStream(bytes: Uint8Array): ReadableStream<Uint8Array> {
  return new NodeReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(bytes);
      controller.close();
    },
  }) as unknown as ReadableStream<Uint8Array>;
}

export async function readFixture(relativePath: string): Promise<Uint8Array> {
  return new Uint8Array(await readFile(resolve(process.cwd(), relativePath)));
}

export async function readGoldenBundle(): Promise<Uint8Array> {
  return readFixture("src/test/fixtures/generated/golden-bundle.tar");
}

export async function installedGoldenBundle() {
  return installedFixtureBundle("golden-bundle");
}

export async function installedFixtureBundle(fixtureName: string) {
  const tar = await readFixture(`src/test/fixtures/generated/${fixtureName}.tar`);
  const manifestSize = Number.parseInt(new TextDecoder().decode(tar.slice(124, 136)).replace(/\0.*$/, "").trim(), 8);
  const manifest = JSON.parse(new TextDecoder().decode(tar.slice(512, 512 + manifestSize))) as { bundle_digest?: string };
  const store = new MemoryBundleStore();
  const result = await installBundleTar({
    body: bytesStream(tar),
    store,
    expectedBundleDigest: manifest.bundle_digest ?? "",
    etag: manifest.bundle_digest ?? null,
    contentLength: String(tar.byteLength),
  });
  const bundle = await store.open(result.manifest.bundle_digest);
  if (!bundle) throw new Error("fixture bundle was not installed");
  return { tar, store, bundle, manifest: result.manifest, closure: result.closure };
}

export interface FixtureTableCase {
  presentation: LocalComparisonPresentation;
  surfaceTable: SurfaceTable;
  beforeRows: Record<string, unknown>[];
  currentRows: Record<string, unknown>[];
  tableRecords: RowDiffRecord[];
  locator: Map<string, RowLocatorRecord>;
  hasBeforeSnapshot: boolean;
  hasCurrentSnapshot: boolean;
  filterTabs: Array<{ facts: NavigationFacts | null; rowFilter: NavigationRowFilter | null }>;
  beforeEncodings: Map<string, SnapshotColumnEncoding>;
  currentEncodings: Map<string, SnapshotColumnEncoding>;
}

/** Loads one table of a generated fixture through the same call chain ComparisonPage uses. */
export async function loadTableCase(fixtureName: string, tableName: string): Promise<FixtureTableCase> {
  const { bundle, manifest } = await installedFixtureBundle(fixtureName);
  const pairId = (manifest.pairs as Array<{ pair_id: string }>)[0]?.pair_id;
  if (!pairId) throw new Error(`fixture ${fixtureName} has no pair`);
  const presentation = await loadComparisonPresentation(bundle, pairId);
  const surfaceTable = presentation.surface.tables.find((table) => table.table_name === tableName);
  if (!surfaceTable) throw new Error(`fixture ${fixtureName} has no table ${tableName}`);
  const paths = presentation.tableArtifacts.get(tableName);
  const hasBeforeSnapshot = Boolean(paths?.before);
  const hasCurrentSnapshot = Boolean(paths?.current);
  const beforeRows = hasBeforeSnapshot ? (await readLocalTable(bundle, presentation, tableName, "before") as Record<string, unknown>[]) : [];
  const currentRows = hasCurrentSnapshot ? (await readLocalTable(bundle, presentation, tableName, "current") as Record<string, unknown>[]) : [];
  const tableRecords = (await readLocalChangeRecords(bundle, presentation, tableName)) as RowDiffRecord[];
  const locatorRows = paths?.rowLocator
    ? (await readParquetTable(bundle, paths.rowLocator, { columns: ["row_identity", "before_row_index", "current_row_index", "before_filter_context_json", "current_filter_context_json"] }) as Record<string, unknown>[])
    : [];
  const locator = parseRowLocator(locatorRows);
  const filterTabs = presentation.view.groups
    .flatMap((group) => group.items)
    .flatMap((item) => item.tabs)
    .filter((tab) => tab.tableName === tableName && tab.rowFilter !== null)
    .map((tab) => ({ facts: tab.facts, rowFilter: tab.rowFilter }));
  const beforeMeta = paths?.before ? await readParquetMetadata(bundle, paths.before) : null;
  const currentMeta = paths?.current ? await readParquetMetadata(bundle, paths.current) : null;
  return {
    presentation,
    surfaceTable,
    beforeRows,
    currentRows,
    tableRecords,
    locator,
    hasBeforeSnapshot,
    hasCurrentSnapshot,
    filterTabs,
    beforeEncodings: beforeMeta ? decodeSnapshotEncodings(beforeMeta.key_value_metadata, `${tableName}.before`) : new Map(),
    currentEncodings: currentMeta ? decodeSnapshotEncodings(currentMeta.key_value_metadata, `${tableName}.current`) : new Map(),
  };
}

export function sha256Hex(bytes: Uint8Array): string {
  return createHash("sha256").update(bytes).digest("hex");
}

export function responseForTar(tar: Uint8Array, etag: string, contentLength = tar.byteLength): Response {
  return new Response(Buffer.from(tar), {
    status: 200,
    headers: { "Content-Type": "application/x-tar", ETag: etag, "Content-Length": String(contentLength) },
  });
}
