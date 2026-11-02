import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { MemoryBundleStore } from "../features/bundle/local-bundle";
import { installBundleTar } from "../features/bundle/posix-tar";

export function bytesBlob(bytes: Uint8Array): Blob {
  const buffer = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(buffer).set(bytes);
  return new Blob([buffer]);
}

export async function readFixture(relativePath: string): Promise<Uint8Array> {
  return new Uint8Array(await readFile(resolve(process.cwd(), relativePath)));
}

export async function readGoldenBundle(): Promise<Uint8Array> {
  return readFixture("src/test/fixtures/generated/golden-bundle.tar");
}

export async function installedGoldenBundle() {
  const tar = await readGoldenBundle();
  const manifestSize = Number.parseInt(new TextDecoder().decode(tar.slice(124, 136)).replace(/\0.*$/, "").trim(), 8);
  const manifest = JSON.parse(new TextDecoder().decode(tar.slice(512, 512 + manifestSize))) as { bundle_digest?: string };
  const store = new MemoryBundleStore();
  const result = await installBundleTar({
    body: bytesBlob(tar).stream(),
    store,
    expectedBundleDigest: manifest.bundle_digest ?? "",
    etag: manifest.bundle_digest ?? null,
    contentLength: String(tar.byteLength),
  });
  const bundle = await store.open(result.manifest.bundle_digest);
  if (!bundle) throw new Error("fixture bundle was not installed");
  return { tar, store, bundle, manifest: result.manifest, closure: result.closure };
}

export function responseForTar(tar: Uint8Array, etag: string, contentLength = tar.byteLength): Response {
  return new Response(bytesBlob(tar), {
    status: 200,
    headers: { "Content-Type": "application/x-tar", ETag: etag, "Content-Length": String(contentLength) },
  });
}
