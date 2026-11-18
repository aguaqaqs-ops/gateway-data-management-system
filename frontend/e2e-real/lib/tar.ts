import { ReadableStream } from "node:stream/web";
import { MemoryBundleStore } from "../../src/features/bundle/local-bundle";
import {
  installBundleTar,
  type BundleManifest as ProductManifest,
  type BundleClosure,
} from "../../src/features/bundle/posix-tar";

export interface TarMember {
  path: string;
  body: Buffer;
}

export interface BundleManifest extends Omit<ProductManifest, "inputs" | "pairs"> {
  bundle_contract_version: string;
  bundle_profile: string;
  status: string;
  inputs: Array<{ input_index: number; role: string; display_name?: string }>;
  pairs: Array<{
    pair_id: string;
    before_input_index: number;
    current_input_index: number;
    status: string;
    summary: Record<string, string>;
  }>;
  failed_pairs: unknown[];
  bundle_digest: string;
  closure_manifest_digest: string;
}

export function digestHex(value: string): string {
  return value.startsWith("sha256:") ? value.slice("sha256:".length) : value;
}

export interface ParsedBundle {
  members: TarMember[];
  manifest: BundleManifest;
  closure: BundleClosure;
  manifestDigest: string;
  bundleDigest: string;
}

export interface BundleDownloadMetadata {
  contentLength: string | null;
  etag: string | null;
  expectedBundleDigest?: string;
}

/** Use the product validator for transport, PAX, complete closure and semantic identity.
 * Member bytes exposed below are installed artifacts, never an unchecked tar Map.
 */
export async function parseBundleTar(
  tar: Buffer,
  metadata: BundleDownloadMetadata,
): Promise<ParsedBundle> {
  const store = new MemoryBundleStore();
  const { manifest, closure } = await installBundleTar({
    body: new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(tar);
        controller.close();
      },
    }) as unknown as globalThis.ReadableStream<Uint8Array>,
    store,
    expectedBundleDigest:
      metadata.expectedBundleDigest ?? metadata.etag?.replace(/^"|"$/g, "") ?? "",
    etag: metadata.etag,
    contentLength: metadata.contentLength,
  });
  console.log(
    "bundle_download=" +
      JSON.stringify({
        content_length: metadata.contentLength,
        received_bytes: tar.length,
        etag: metadata.etag,
        bundle_digest: manifest.bundle_digest,
      }),
  );
  const installed = await store.open(manifest.bundle_digest);
  if (!installed) throw new Error("verified bundle was not installed");
  const members: TarMember[] = [
    { path: "manifest.json", body: Buffer.from(JSON.stringify(manifest)) },
    { path: "artifact-closure.json", body: Buffer.from(JSON.stringify(closure)) },
  ];
  for (const entry of manifest.closure.entries) {
    members.push({
      path: entry.logical_path,
      body: Buffer.from(await (await installed.readArtifact(entry.logical_path)).arrayBuffer()),
    });
  }
  return {
    members,
    manifest: manifest as BundleManifest,
    closure,
    manifestDigest: digestHex(closure.bundle_manifest_digest),
    bundleDigest: digestHex(manifest.bundle_digest),
  };
}

export function countBundlePairs(manifest: BundleManifest): number {
  return manifest.pairs.length;
}
