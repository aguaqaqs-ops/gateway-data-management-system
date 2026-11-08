import { Buffer } from "node:buffer";
import { ReadableStream as NodeReadableStream } from "node:stream/web";
import { describe, expect, it } from "vitest";
import { bytesStream, readFixture } from "../../test/helpers";
import { normalizeSha256, Sha256 } from "./sha256";
import {
  BundleIntegrityError,
  installBundleTar,
  MAX_PATH_UTF8_BYTES,
  MAX_PAX_PAYLOAD_BYTES,
  parseMemberPaxHeader,
  parsePaxRecords,
  parseTarHeader,
  jsonBytes,
} from "./posix-tar";
import type { ArtifactSink, BundleClosure, BundleManifest, BundleStore, BundleWriteTransaction } from "./posix-tar";

const FIXTURE_DIR = "src/test/fixtures/backend-interop/be-d-0ba45e5ef8";

interface InteropIndex {
  bundle_digest: string;
  content_length: number;
  files: Array<{ path: string; length: number; sha256: string }>;
  ordinary_artifacts: Array<{ logical_path: string; size_bytes: number; raw_sha256: string }>;
}

interface SizeVector {
  size_bytes: number;
  header_only_file: string;
  header_length: number;
  complete_tar: boolean;
  framed_size: number;
}

type PaxVectors = Record<string, string>;

function fixture(path: string): Promise<Uint8Array> {
  return readFixture(`${FIXTURE_DIR}/${path}`);
}

async function jsonFixture<T>(path: string): Promise<T> {
  return JSON.parse(new TextDecoder().decode(await fixture(path))) as T;
}

function sha256(bytes: Uint8Array): string {
  return new Sha256().update(bytes).digest();
}

function concat(chunks: Uint8Array[]): Uint8Array {
  const total = chunks.reduce((sum, chunk) => sum + chunk.byteLength, 0);
  const merged = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return merged;
}

class RecordingStore implements BundleStore {
  readonly opened: string[] = [];
  readonly files = new Map<string, Uint8Array>();
  aborted = false;

  async has(): Promise<boolean> {
    return false;
  }

  async begin(): Promise<BundleWriteTransaction> {
    return new RecordingTransaction(this);
  }
}

class RecordingTransaction implements BundleWriteTransaction {
  constructor(private readonly store: RecordingStore) {}

  async openArtifact(path: string): Promise<ArtifactSink> {
    this.store.opened.push(path);
    const chunks: Uint8Array[] = [];
    return {
      write: async (chunk) => {
        chunks.push(chunk.slice());
      },
      close: async () => {
        this.store.files.set(path, concat(chunks));
      },
      abort: async () => {
        chunks.length = 0;
      },
    };
  }

  async commit(manifest: BundleManifest, closure: BundleClosure): Promise<void> {
    this.store.files.set("manifest.json", jsonBytes(manifest));
    this.store.files.set("artifact-closure.json", jsonBytes(closure));
  }

  async abort(): Promise<void> {
    this.store.aborted = true;
    this.store.files.clear();
  }
}

/** Builds one standards-compliant pax record with an ASCII byte-length prefix. */
function paxRecord(key: string, value: string): Uint8Array {
  const body = new TextEncoder().encode(`${key}=${value}\n`);
  let digits = 1;
  let total = digits + 1 + body.byteLength;
  while (String(total).length !== digits) {
    digits = String(total).length;
    total = digits + 1 + body.byteLength;
  }
  const prefix = new TextEncoder().encode(`${total} `);
  expect(prefix.byteLength).toBe(digits + 1);
  return concat([prefix, body]);
}

function paxPayload(records: Array<[string, string]>): Uint8Array {
  return concat(records.map(([key, value]) => paxRecord(key, value)));
}

/** Builds a 512-byte ustar header with a valid checksum for in-memory vectors. */
function tarHeader(options: { name: string; size: number; type: string }): Uint8Array {
  const header = new Uint8Array(512);
  header.set(new TextEncoder().encode(options.name).subarray(0, 100), 0);
  header.set(new TextEncoder().encode(options.size.toString(8).padStart(11, "0")), 124);
  header[156] = options.type.charCodeAt(0);
  header.set(new TextEncoder().encode("ustar\0" + "00"), 257);
  header.fill(0x20, 148, 156);
  const checksum = header.reduce((sum, byte) => sum + byte, 0);
  header.set(new TextEncoder().encode(checksum.toString(8).padStart(6, "0")), 148);
  header[154] = 0;
  header[155] = 0x20;
  return header;
}

describe("backend interop bundle fixtures", () => {
  it("installs the backend interop bundle with byte-identical metadata and six members", async () => {
    const index = await jsonFixture<InteropIndex>("index.json");
    const tar = await fixture("bundle.tar");
    expect(tar.byteLength).toBe(24_576);
    expect(sha256(tar)).toBe("b08a310c82162ecf559b9f82eca30548cc97a75cc0d8775e20b2bd24611332a2");
    for (const file of index.files) {
      const bytes = await fixture(file.path);
      expect(bytes.byteLength).toBe(file.length);
      expect(sha256(bytes)).toBe(file.sha256);
    }

    const store = new RecordingStore();
    const result = await installBundleTar({
      body: bytesStream(tar),
      store,
      expectedBundleDigest: index.bundle_digest,
      etag: index.bundle_digest,
      contentLength: String(index.content_length),
    });

    expect(store.aborted).toBe(false);
    expect(store.files.size).toBe(6);
    expect(store.opened).toEqual(index.ordinary_artifacts.map((artifact) => artifact.logical_path));
    expect(normalizeSha256(result.manifest.bundle_digest)).toBe(normalizeSha256(index.bundle_digest));
    expect(Buffer.from(store.files.get("manifest.json") ?? new Uint8Array()).equals(Buffer.from(await fixture("manifest.json")))).toBe(true);
    expect(Buffer.from(store.files.get("artifact-closure.json") ?? new Uint8Array()).equals(Buffer.from(await fixture("artifact-closure.json")))).toBe(true);
    for (const artifact of index.ordinary_artifacts) {
      const bytes = store.files.get(artifact.logical_path);
      expect(bytes?.byteLength).toBe(artifact.size_bytes);
      expect(`sha256:${sha256(bytes ?? new Uint8Array())}`).toBe(artifact.raw_sha256);
    }
    // The frontend installs tar/OPFS content only: there is no RECORDS artifact,
    // which is what the backend reports as verified_logical_record_count === 0.
    expect(result.manifest.closure.entries.some((entry) => entry.kind === "RECORDS")).toBe(false);
  });

  it("decodes literal and long-path pax records at both layers", async () => {
    const vectors = await jsonFixture<PaxVectors>("pax-records.json");
    const cases: Array<[string, string]> = [
      ["literal_utf8", "中"],
      ["prefix_99", "a".repeat(90)],
      ["prefix_101", "a".repeat(91)],
    ];
    for (const [name, expected] of cases) {
      const bytes = new Uint8Array(Buffer.from(vectors[name] ?? "", "hex"));
      expect(parsePaxRecords(bytes)).toEqual([{ key: "path", value: expected }]);
      expect(parseMemberPaxHeader(bytes)).toEqual({ path: expected, size: null });
    }
  });

  it("rejects adjacent or unsupported pax records at the member layer", async () => {
    const vectors = await jsonFixture<PaxVectors>("pax-records.json");
    const adjacent = new Uint8Array(Buffer.from(vectors.adjacent_records ?? "", "hex"));
    expect(parsePaxRecords(adjacent)).toEqual([
      { key: "path", value: "中" },
      { key: "comment", value: "😀" },
    ]);
    expect(() => parseMemberPaxHeader(adjacent)).toThrow("不支持的 key");
    expect(() => parseMemberPaxHeader(paxPayload([["path", "a"], ["path", "b"]]))).toThrow("重复的 path");
    expect(() => parseMemberPaxHeader(paxPayload([["size", "1"], ["size", "2"]]))).toThrow("重复的 size");
    expect(() => parseMemberPaxHeader(paxPayload([["path", ""]]))).toThrow("path 为空");
    expect(() => parseMemberPaxHeader(paxPayload([["size", ""]]))).toThrow("size 为空");
  });

  it("rejects malformed pax records at the split layer", async () => {
    const vectors = await jsonFixture<PaxVectors>("pax-records.json");
    for (const name of ["invalid_wrong_byte_length", "invalid_no_newline", "invalid_truncated_utf8"]) {
      const bytes = new Uint8Array(Buffer.from(vectors[name] ?? "", "hex"));
      expect(() => parsePaxRecords(bytes)).toThrow(BundleIntegrityError);
    }
  });

  it("reads header-only size vectors and rejects installation without committing", async () => {
    const index = await jsonFixture<InteropIndex>("index.json");
    const vectors = await jsonFixture<SizeVector[]>("size-vectors.json");
    for (const vector of vectors) {
      const bytes = await fixture(vector.header_only_file);
      expect(bytes.byteLength).toBe(vector.header_length);
      expect(vector.complete_tar).toBe(false);
      const header = parseTarHeader(bytes.subarray(0, 512));
      let size = header.size;
      if (header.type === "x") {
        const pax = parseMemberPaxHeader(bytes.subarray(512, 512 + header.size));
        expect(pax.size).not.toBeNull();
        size = pax.size ?? -1;
        expect(parseTarHeader(bytes.subarray(1024, 1536)).type).toBe("0");
      }
      expect(size).toBe(vector.size_bytes);

      // The largest vector's true framed size (9007199254742528) exceeds
      // Number.MAX_SAFE_INTEGER, so its Content-Length header would itself be
      // rejected. Use the body length so the member size is checked against the
      // remaining Content-Length, which is the incomplete-data failure under test.
      const contentLength = Math.max(vector.header_length, 1024);
      expect(vector.framed_size).toBeGreaterThanOrEqual(contentLength);
      const store = new RecordingStore();
      await expect(installBundleTar({
        body: bytesStream(bytes),
        store,
        expectedBundleDigest: index.bundle_digest,
        etag: index.bundle_digest,
        contentLength: String(contentLength),
      })).rejects.toThrow("tar 成员超出 Content-Length");
      expect(store.files.size).toBe(0);
      expect(store.aborted).toBe(true);
    }
  });

  it("enforces pax path and payload budgets before allocating", async () => {
    const acceptedPath = "a".repeat(1_572_864);
    expect(parseMemberPaxHeader(paxPayload([["path", acceptedPath]])).path).toBe(acceptedPath);

    const rejectedPath = "a".repeat(MAX_PATH_UTF8_BYTES + 1);
    expect(() => parseMemberPaxHeader(paxPayload([["path", rejectedPath]]))).toThrow("pax 头 path 超过允许大小");

    expect(parseMemberPaxHeader(paxPayload([["size", "9007199254740991"]]))).toEqual({ path: null, size: 9_007_199_254_740_991 });
    expect(() => parseMemberPaxHeader(paxPayload([["size", "9007199254740992"]]))).toThrow("pax size 超出安全整数范围");

    const oversizedPaxHeader = tarHeader({ name: "PaxHeaders/path", size: MAX_PAX_PAYLOAD_BYTES + 1, type: "x" });
    // Only the 512-byte header is available: reading the declared PAX payload
    // would hit end-of-stream, so the budget error proves the check ran first.
    const body = new NodeReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(oversizedPaxHeader);
        controller.close();
      },
    }) as unknown as ReadableStream<Uint8Array>;
    const store = new RecordingStore();
    await expect(installBundleTar({
      body,
      store,
      expectedBundleDigest: "sha256:" + "0".repeat(64),
      etag: "sha256:" + "0".repeat(64),
      contentLength: String(MAX_PAX_PAYLOAD_BYTES + 1024),
    })).rejects.toThrow("pax 头超过允许大小");
    expect(store.files.size).toBe(0);
    expect(store.aborted).toBe(true);
  });
});
