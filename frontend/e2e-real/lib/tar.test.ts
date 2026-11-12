// @vitest-environment node
import { describe, expect, it } from "vitest";
import { installedGoldenBundle } from "../../src/test/helpers";
import { parseBundleTar } from "./tar";

// Only a fixture mutator: production installBundleTar is the validation oracle.
function memberSegments(tar: Buffer): Buffer[] {
  const segments: Buffer[] = [];
  let offset = 0;
  let start = 0;
  while (offset < tar.length) {
    const header = tar.subarray(offset, offset + 512);
    if (header.every((byte) => byte === 0)) break;
    const size = Number.parseInt(header.subarray(124, 136).toString().replace(/\0.*$/, "").trim(), 8);
    offset += 512 + Math.ceil(size / 512) * 512;
    if (header[156] !== "x".charCodeAt(0)) {
      segments.push(tar.subarray(start, offset));
      start = offset;
    }
  }
  return segments;
}

const archiveFaults: Array<[string, (members: Buffer[], end: Buffer) => Buffer, RegExp]> = [
  ["only valid metadata without declared artifacts or end", (m) => Buffer.concat(m.slice(0, 2)), /结束标记|全部 closure/],
  ["missing declared artifact", (m, end) => Buffer.concat([...m.slice(0, 2), ...m.slice(3), end]), /成员顺序或路径|全部 closure/],
  ["duplicate artifact path", (m, end) => Buffer.concat([...m.slice(0, 3), m[2], ...m.slice(3), end]), /成员顺序或路径|未声明成员/],
  ["extra undeclared member", (m, end) => Buffer.concat([...m, m[2], end]), /未声明成员/],
  ["missing both end blocks", (m) => Buffer.concat(m), /结束标记/],
  ["missing second end block", (m) => Buffer.concat([...m, Buffer.alloc(512)]), /截断|结束块/],
  ["invalid second end block", (m) => Buffer.concat([...m, Buffer.alloc(512), Buffer.alloc(512, 1)]), /结束块/],
  ["nonzero data after end blocks", (m, end) => Buffer.concat([...m, end, Buffer.from([1])]), /额外数据/],
  ["truncated artifact", (m) => Buffer.concat(m).subarray(0, Buffer.concat(m).length - 600), /截断|Content-Length/],
];

const metadataFaults = [
  ["missing Content-Length", { contentLength: null }, /Content-Length/],
  ["wrong Content-Length", { contentLength: "1024" }, /Content-Length/],
  ["missing ETag", { etag: null }, /ETag/],
  ["wrong ETag", { etag: `"sha256:${"0".repeat(64)}"` }, /ETag|digest/],
  ["wrong expected identity", { expectedBundleDigest: `sha256:${"0".repeat(64)}` }, /摘要|digest/],
] as const;

describe("real e2e bundle transport uses the complete product validator", () => {
  it("accepts the backend golden format including legal long PAX paths and semantic ETag", async () => {
    const { tar, manifest } = await installedGoldenBundle();
    const parsed = await parseBundleTar(Buffer.from(tar), { contentLength: String(tar.length), etag: `"${manifest.bundle_digest}"`, expectedBundleDigest: manifest.bundle_digest });
    expect(parsed.members.length).toBe(manifest.closure.entries.length + 2);
    expect(parsed.members.some((member) => member.path.length > 100)).toBe(true);
    expect(parsed.bundleDigest).toBe(manifest.bundle_digest.replace(/^sha256:/, ""));
  });

  it.each(archiveFaults)("rejects %s even with matching actual HTTP length", async (_name, mutate, message) => {
    const { tar, manifest } = await installedGoldenBundle();
    const malformed = mutate(memberSegments(Buffer.from(tar)), Buffer.alloc(1024));
    await expect(parseBundleTar(malformed, { contentLength: String(malformed.length), etag: `"${manifest.bundle_digest}"`, expectedBundleDigest: manifest.bundle_digest })).rejects.toThrow(message);
  });

  it.each(metadataFaults)("rejects %s on a valid complete archive", async (_name, metadata, message) => {
    const { tar, manifest } = await installedGoldenBundle();
    await expect(parseBundleTar(Buffer.from(tar), { contentLength: String(tar.length), etag: `"${manifest.bundle_digest}"`, expectedBundleDigest: manifest.bundle_digest, ...metadata })).rejects.toThrow(message);
  });
});
