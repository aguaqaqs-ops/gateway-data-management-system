import { Buffer } from "node:buffer";
import { describe, expect, it, vi } from "vitest";
import { ensureLocalBundle, MemoryBundleStore } from "./local-bundle";
import { BundleIntegrityError, installBundleTar } from "./posix-tar";
import { bytesStream, installedGoldenBundle, responseForTar } from "../../test/helpers";

async function installedFixtureWithRecords() {
  const installed = await installedGoldenBundle();
  const entry = installed.manifest.closure.entries.find((candidate) => candidate.kind === "RECORDS");
  if (!entry) throw new Error("backend fixture has no records artifact");
  const bytes = new Uint8Array(await (await installed.bundle.readArtifact(entry.logical_path)).arrayBuffer());
  return { ...installed, recordsBytes: bytes };
}

describe("POSIX tar bundle installation", () => {
  it("installs a golden bundle in closure order and supports long pax paths", async () => {
    const { manifest, closure, bundle } = await installedGoldenBundle();
    expect(manifest.bundle_contract_version).toBe("backend-vnext/comparison-bundle/v4");
    expect(manifest.closure.entries.map((entry) => entry.logical_path)).toEqual(closure.entries.map((entry) => entry.logical_path));
    expect(manifest.closure.entries.some((entry) => entry.logical_path.length > 100)).toBe(true);
    expect(await bundle.readArtifact(manifest.closure.entries[0]?.logical_path ?? "")).toBeInstanceOf(Blob);
  });

  it("rejects a wrong ETag, declared length, truncated stream, or artifact digest", async () => {
    const { tar, manifest, recordsBytes } = await installedFixtureWithRecords();
    const makeStore = () => new MemoryBundleStore();
    const key = manifest.bundle_digest;

    const wrongEtagStore = makeStore();
    await expect(installBundleTar({ body: bytesStream(tar), store: wrongEtagStore, expectedBundleDigest: key, etag: `"${"0".repeat(64)}"`, contentLength: String(tar.byteLength) })).rejects.toBeInstanceOf(BundleIntegrityError);
    expect(await wrongEtagStore.has(key)).toBe(false);

    const wrongLengthStore = makeStore();
    await expect(installBundleTar({ body: bytesStream(tar), store: wrongLengthStore, expectedBundleDigest: key, etag: key, contentLength: String(tar.byteLength + 1) })).rejects.toThrow("Content-Length");
    expect(await wrongLengthStore.has(key)).toBe(false);

    const truncatedStore = makeStore();
    await expect(installBundleTar({ body: bytesStream(tar.slice(0, tar.byteLength - 700)), store: truncatedStore, expectedBundleDigest: key, etag: key, contentLength: String(tar.byteLength) })).rejects.toBeInstanceOf(BundleIntegrityError);
    expect(await truncatedStore.has(key)).toBe(false);

    const corrupt = tar.slice();
    const offset = Buffer.from(corrupt).indexOf(Buffer.from(recordsBytes));
    expect(offset).toBeGreaterThan(0);
    corrupt[offset + 140] = (corrupt[offset + 140] ?? 0) ^ 0xff;
    const corruptStore = makeStore();
    await expect(installBundleTar({ body: bytesStream(corrupt), store: corruptStore, expectedBundleDigest: key, etag: key, contentLength: String(corrupt.byteLength) })).rejects.toThrow("产物摘要不匹配");
    expect(await corruptStore.has(key)).toBe(false);
  });

  it("drops a bad local copy and requests the bundle again once", async () => {
    const { tar, manifest, recordsBytes } = await installedFixtureWithRecords();
    const corrupt = tar.slice();
    const offset = Buffer.from(corrupt).indexOf(Buffer.from(recordsBytes));
    corrupt[offset + 96] = (corrupt[offset + 96] ?? 0) ^ 0x01;
    const fetchBundle = vi.fn()
      .mockResolvedValueOnce(responseForTar(corrupt, manifest.bundle_digest))
      .mockResolvedValueOnce(responseForTar(tar, manifest.bundle_digest));
    const result = await ensureLocalBundle({ store: new MemoryBundleStore(), expectedBundleDigest: manifest.bundle_digest, fetchBundle });
    expect(fetchBundle).toHaveBeenCalledTimes(2);
    expect(result.manifest.bundle_digest).toBe(manifest.bundle_digest);
  });

  it("returns an already installed bundle without contacting the source", async () => {
    const { manifest, store } = await installedGoldenBundle();
    const fetchBundle = vi.fn();
    const cached = await ensureLocalBundle({ store, expectedBundleDigest: manifest.bundle_digest, fetchBundle });
    expect(cached.manifest.bundle_digest).toBe(manifest.bundle_digest);
    expect(fetchBundle).not.toHaveBeenCalled();
  });
});
