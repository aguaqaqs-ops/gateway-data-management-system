import { canonicalJson, normalizeSha256, Sha256 } from "./sha256";

const BLOCK = 512;
const METADATA_LIMIT = 16 * 1024 * 1024;

/** Budget for one local PAX payload, counted from the header-declared size. */
export const MAX_PAX_PAYLOAD_BYTES = 16 * 1024 * 1024;
/** Budget for one member path, applied to PAX `path` records and ustar name/prefix. */
export const MAX_PATH_UTF8_BYTES = 8 * 1024 * 1024;

const textDecoder = new TextDecoder("utf-8", { fatal: true });
const textEncoder = new TextEncoder();

export interface BundleIntegrity {
  media_type: string;
  raw_sha256: string;
  size_bytes: number;
}

export interface BundleSemanticEntry {
  integrity: BundleIntegrity;
  kind: string;
  logical_path: string;
  shared: boolean;
  table_bindings?: Array<{ pair_id: string; side: string; table_name: string }>;
  pair_id?: string;
  table_name?: string;
}

export interface BundleSemanticClosure {
  entries: BundleSemanticEntry[];
}

export interface BundleArtifactEntry {
  artifact_ref: { artifact_id: string; media_type: string; raw_sha256: string; size_bytes: number };
  kind: string;
  logical_path: string;
  raw_sha256: string;
  shared: boolean;
  size_bytes: number;
  table_bindings?: Array<{ pair_id: string; side: string; table_name: string }>;
  pair_id?: string;
  table_name?: string;
}

export interface BundleManifest {
  bundle_contract_version: string;
  bundle_profile: string;
  status: string;
  inputs: unknown[];
  pairs: unknown[];
  failed_pairs: unknown[];
  diagnostics: string[];
  closure: BundleSemanticClosure;
  closure_entries: BundleArtifactEntry[];
  bundle_digest: string;
  closure_manifest_digest: string;
}

export interface BundleClosure {
  bundle_contract_version: string;
  bundle_digest: string;
  bundle_manifest_digest: string;
  entries: BundleSemanticEntry[];
  closure_entries: BundleArtifactEntry[];
}

export interface BundleWriteTransaction {
  openArtifact(path: string): Promise<WritableStream<Uint8Array> | ArtifactSink>;
  commit(manifest: BundleManifest, closure: BundleClosure): Promise<void>;
  abort(): Promise<void>;
}

export interface ArtifactSink {
  write(chunk: Uint8Array): Promise<void>;
  close(): Promise<void>;
  abort(reason?: unknown): Promise<void>;
}

export interface BundleStore {
  has(bundleDigest: string): Promise<boolean>;
  begin(bundleDigest: string): Promise<BundleWriteTransaction>;
}

export interface BundleDownloadProgress {
  receivedBytes: number;
  contentLength: number;
}

export interface PaxRecord {
  key: string;
  value: string;
}

export interface MemberPaxHeader {
  path: string | null;
  size: number | null;
}

export class BundleIntegrityError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BundleIntegrityError";
  }
}

class StreamReader {
  private readonly reader: ReadableStreamDefaultReader<Uint8Array>;
  private current: Uint8Array | null = null;
  private offset = 0;
  consumedBytes = 0;
  private ended = false;

  constructor(stream: ReadableStream<Uint8Array>) {
    this.reader = stream.getReader();
  }

  async readExactly(length: number, allowEnd = false): Promise<Uint8Array | null> {
    if (length < 0) throw new BundleIntegrityError("tar 长度字段无效");
    const output = new Uint8Array(length);
    let written = 0;
    while (written < length) {
      if (!this.current || this.offset >= this.current.byteLength) {
        if (this.ended) break;
        let next: ReadableStreamReadResult<Uint8Array>;
        try { next = await this.reader.read(); } catch { throw new BundleIntegrityError("bundle 下载流中断"); }
        if (next.done) {
          this.ended = true;
          break;
        }
        this.current = next.value;
        this.offset = 0;
        if (this.current.byteLength === 0) continue;
      }
      const chunk = this.current;
      const available = chunk.byteLength - this.offset;
      const copyLength = Math.min(available, length - written);
      output.set(chunk.subarray(this.offset, this.offset + copyLength), written);
      this.offset += copyLength;
      written += copyLength;
      this.consumedBytes += copyLength;
    }
    if (written === 0 && allowEnd) return null;
    if (written !== length) throw new BundleIntegrityError("bundle tar 被截断");
    return output;
  }

  async readToEnd(onChunk: (chunk: Uint8Array) => void): Promise<void> {
    if (this.current && this.offset < this.current.byteLength) {
      const rest = this.current.subarray(this.offset);
      this.offset = this.current.byteLength;
      this.consumedBytes += rest.byteLength;
      onChunk(rest);
    }
    while (!this.ended) {
      let next: ReadableStreamReadResult<Uint8Array>;
      try { next = await this.reader.read(); } catch { throw new BundleIntegrityError("bundle 下载流中断"); }
      if (next.done) {
        this.ended = true;
        break;
      }
      this.consumedBytes += next.value.byteLength;
      onChunk(next.value);
    }
  }

  release(): void {
    this.reader.releaseLock();
  }
}

function fieldString(header: Uint8Array, start: number, end: number): string {
  let limit = end;
  for (let i = start; i < end; i += 1) {
    if (header[i] === 0) {
      limit = i;
      break;
    }
  }
  try { return textDecoder.decode(header.subarray(start, limit)); } catch { throw new BundleIntegrityError("tar header 文本不是有效 UTF-8"); }
}

function octal(header: Uint8Array, start: number, end: number, label: string): number {
  const raw = fieldString(header, start, end).trim().replace(/^\0+/, "");
  if (!raw) return 0;
  if (!/^[0-7]+$/.test(raw)) throw new BundleIntegrityError(`tar ${label} 不是有效八进制数`);
  const value = Number.parseInt(raw, 8);
  if (!Number.isSafeInteger(value) || value < 0) throw new BundleIntegrityError(`tar ${label} 超出支持范围`);
  return value;
}

function validatePath(path: string): string {
  if (!path || path.startsWith("/") || path.includes("\\") || path.includes("\0") || path.endsWith("/")) {
    throw new BundleIntegrityError("bundle 成员路径无效");
  }
  const parts = path.split("/");
  if (parts.some((part) => !part || part === "." || part === "..")) throw new BundleIntegrityError("bundle 成员路径越界");
  return path;
}

function checkPathBudget(path: string): string {
  if (textEncoder.encode(path).byteLength > MAX_PATH_UTF8_BYTES) throw new BundleIntegrityError("bundle 成员路径超过允许大小");
  return path;
}

/** Parses a 512-byte ustar header; PAX overrides are applied by the installer. */
export function parseTarHeader(header: Uint8Array): { path: string; size: number; type: string } {
  const stored = octal(header, 148, 156, "校验和");
  let checksum = 0;
  for (let i = 0; i < header.byteLength; i += 1) checksum += i >= 148 && i < 156 ? 32 : (header[i] ?? 0);
  if (checksum !== stored) throw new BundleIntegrityError("tar header 校验和不匹配");
  const name = fieldString(header, 0, 100);
  const prefix = fieldString(header, 345, 500);
  const path = checkPathBudget(validatePath(prefix ? `${prefix}/${name}` : name));
  const typeByte = header[156] ?? 0;
  const type = typeByte === 0 ? "0" : String.fromCharCode(typeByte);
  const size = octal(header, 124, 136, "成员大小");
  return { path, size, type };
}

interface RawPaxRecord {
  key: string;
  valueBytes: Uint8Array;
}

function decodeUtf8(bytes: Uint8Array, label: string): string {
  try { return textDecoder.decode(bytes); } catch { throw new BundleIntegrityError(`${label} 不是有效 UTF-8`); }
}

/**
 * Splits a local PAX payload at byte boundaries. Each record starts with an
 * ASCII decimal length and one space; the length counts the prefix, the space,
 * `key=value`, and the trailing newline. Values stay as bytes so a per-key
 * budget can be applied before the string is allocated.
 */
function splitPaxRecords(payload: Uint8Array): RawPaxRecord[] {
  const records: RawPaxRecord[] = [];
  let offset = 0;
  while (offset < payload.byteLength) {
    let digitsEnd = offset;
    while (digitsEnd < payload.byteLength && payload[digitsEnd] >= 0x30 && payload[digitsEnd] <= 0x39) digitsEnd += 1;
    if (digitsEnd === offset || payload[digitsEnd] !== 0x20) throw new BundleIntegrityError("pax 记录长度格式无效");
    let digits = "";
    for (let index = offset; index < digitsEnd; index += 1) digits += String.fromCharCode(payload[index]);
    const length = Number(digits);
    if (!Number.isSafeInteger(length) || length <= digitsEnd - offset + 1) throw new BundleIntegrityError("pax 记录长度无效");
    const recordEnd = offset + length;
    if (recordEnd > payload.byteLength) throw new BundleIntegrityError("pax 记录越过 payload");
    if (payload[recordEnd - 1] !== 0x0a) throw new BundleIntegrityError("pax 记录缺少结尾换行");
    const bodyStart = digitsEnd + 1;
    let separator = bodyStart;
    while (separator < recordEnd - 1 && payload[separator] !== 0x3d) separator += 1;
    if (separator === bodyStart || separator >= recordEnd - 1) throw new BundleIntegrityError("pax 记录缺少 key 或分隔符");
    records.push({
      key: decodeUtf8(payload.subarray(bodyStart, separator), "pax key"),
      valueBytes: payload.subarray(separator + 1, recordEnd - 1),
    });
    offset = recordEnd;
  }
  return records;
}

/** Record-splitter layer: decodes every `(key, value)` pair with strict UTF-8. */
export function parsePaxRecords(payload: Uint8Array): PaxRecord[] {
  return splitPaxRecords(payload).map((record) => ({ key: record.key, value: decodeUtf8(record.valueBytes, `pax ${record.key}`) }));
}

function parsePaxSize(value: string): number {
  if (!/^[0-9]+$/.test(value)) throw new BundleIntegrityError("pax size 不是十进制非负整数");
  const size = Number(value);
  if (!Number.isSafeInteger(size)) throw new BundleIntegrityError("pax size 超出安全整数范围");
  return size;
}

/**
 * Member layer: a member's local PAX header may carry only `path` and `size`.
 * Duplicate keys, any other key, and empty values abort the install.
 */
export function parseMemberPaxHeader(payload: Uint8Array): MemberPaxHeader {
  let path: string | null = null;
  let size: number | null = null;
  for (const record of splitPaxRecords(payload)) {
    if (record.key === "path") {
      if (path !== null) throw new BundleIntegrityError("pax 头包含重复的 path");
      if (record.valueBytes.byteLength === 0) throw new BundleIntegrityError("pax 头 path 为空");
      if (record.valueBytes.byteLength > MAX_PATH_UTF8_BYTES) throw new BundleIntegrityError("pax 头 path 超过允许大小");
      path = decodeUtf8(record.valueBytes, "pax path");
      continue;
    }
    if (record.key === "size") {
      if (size !== null) throw new BundleIntegrityError("pax 头包含重复的 size");
      if (record.valueBytes.byteLength === 0) throw new BundleIntegrityError("pax 头 size 为空");
      size = parsePaxSize(decodeUtf8(record.valueBytes, "pax size"));
      continue;
    }
    throw new BundleIntegrityError(`pax 头包含不支持的 key：${record.key}`);
  }
  return { path, size };
}

function parseJson<T>(bytes: Uint8Array, label: string): T {
  try {
    return JSON.parse(textDecoder.decode(bytes)) as T;
  } catch {
    throw new BundleIntegrityError(`${label} 不是有效 JSON`);
  }
}

function object(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new BundleIntegrityError(`${label} 结构无效`);
  return value as Record<string, unknown>;
}

function sameCanonical(left: unknown, right: unknown): boolean {
  return canonicalJson(left) === canonicalJson(right);
}

function manifestSemanticPayload(manifest: BundleManifest): Record<string, unknown> {
  const payload = { ...manifest } as unknown as Record<string, unknown>;
  delete payload.bundle_digest;
  delete payload.closure_manifest_digest;
  delete payload.closure_entries;
  return payload;
}

function hashJson(value: unknown): string {
  const bytes = new TextEncoder().encode(canonicalJson(value));
  return `sha256:${new Sha256().update(bytes).digest()}`;
}

async function readMemberBytes(reader: StreamReader, size: number, label: string): Promise<Uint8Array> {
  if (size > METADATA_LIMIT) throw new BundleIntegrityError(`${label} 超过最大索引大小`);
  const bytes = await reader.readExactly(size);
  if (!bytes) throw new BundleIntegrityError(`${label} 缺失`);
  return bytes;
}

async function discardPadding(reader: StreamReader, size: number): Promise<void> {
  const padding = (BLOCK - size % BLOCK) % BLOCK;
  if (padding) await reader.readExactly(padding);
}

async function readArtifact(
  reader: StreamReader,
  entry: BundleSemanticEntry,
  transaction: BundleWriteTransaction,
  progress: (bytes: number) => void,
  contentLength: number,
): Promise<void> {
  const size = entry.integrity.size_bytes;
  if (!Number.isSafeInteger(size) || size < 0) throw new BundleIntegrityError("产物大小超出允许范围");
  const sinkValue = await transaction.openArtifact(entry.logical_path);
  const sink: ArtifactSink = typeof (sinkValue as WritableStream<Uint8Array>).getWriter === "function"
    ? writerSink((sinkValue as WritableStream<Uint8Array>).getWriter())
    : sinkValue as ArtifactSink;
  const hasher = new Sha256();
  let remaining = size;
  try {
    while (remaining > 0) {
      const block = await reader.readExactly(Math.min(1024 * 1024, remaining));
      if (!block) throw new BundleIntegrityError(`产物 ${entry.logical_path} 被截断`);
      hasher.update(block);
      await sink.write(block);
      remaining -= block.byteLength;
      progress(reader.consumedBytes);
      if (reader.consumedBytes > contentLength) throw new BundleIntegrityError("bundle 实际长度超过 Content-Length");
    }
    if (normalizeSha256(hasher.digest()) !== normalizeSha256(entry.integrity.raw_sha256)) {
      throw new BundleIntegrityError(`产物摘要不匹配：${entry.logical_path}`);
    }
    await sink.close();
  } catch (error) {
    await sink.abort(error);
    throw error;
  }
  await discardPadding(reader, size);
}

function writerSink(writer: WritableStreamDefaultWriter<Uint8Array>): ArtifactSink {
  return {
    write: async (chunk) => writer.write(chunk),
    close: async () => writer.close(),
    abort: async (reason) => {
      try { await writer.abort(reason); } catch { /* preserve the primary failure */ }
    },
  };
}

function verifyEntry(entry: BundleSemanticEntry, physical: BundleArtifactEntry): void {
  if (entry.logical_path !== physical.logical_path || entry.kind !== physical.kind || entry.shared !== physical.shared) {
    throw new BundleIntegrityError("manifest closure entry 与引用索引不匹配");
  }
  if (entry.integrity.raw_sha256 !== physical.raw_sha256 || entry.integrity.size_bytes !== physical.size_bytes || entry.integrity.raw_sha256 !== physical.artifact_ref.raw_sha256 || entry.integrity.size_bytes !== physical.artifact_ref.size_bytes || entry.integrity.media_type !== physical.artifact_ref.media_type) {
    throw new BundleIntegrityError(`产物引用完整性字段不匹配：${entry.logical_path}`);
  }
  if (entry.pair_id !== physical.pair_id || entry.table_name !== physical.table_name || !sameCanonical(entry.table_bindings ?? null, physical.table_bindings ?? null)) {
    throw new BundleIntegrityError(`产物作用域不匹配：${entry.logical_path}`);
  }
}

function validateManifests(manifestValue: unknown, closureValue: unknown, etag: string, expectedDigest: string): { manifest: BundleManifest; closure: BundleClosure } {
  const manifest = object(manifestValue, "bundle manifest") as unknown as BundleManifest;
  const closure = object(closureValue, "bundle closure") as unknown as BundleClosure;
  const semanticClosure = object(manifest.closure, "bundle manifest closure") as unknown as BundleSemanticClosure;
  if (!Array.isArray(semanticClosure.entries) || !Array.isArray(manifest.closure_entries) || !Array.isArray(closure.entries) || !Array.isArray(closure.closure_entries)) {
    throw new BundleIntegrityError("bundle closure 列表缺失");
  }
  if (normalizeSha256(manifest.bundle_digest) !== normalizeSha256(closure.bundle_digest) || normalizeSha256(manifest.bundle_digest) !== normalizeSha256(expectedDigest)) throw new BundleIntegrityError("bundle 摘要不一致");
  if (manifest.bundle_contract_version !== closure.bundle_contract_version) throw new BundleIntegrityError("bundle contract version 不一致");
  if (normalizeSha256(etag) !== normalizeSha256(expectedDigest)) throw new BundleIntegrityError("ETag 与预期 bundle 摘要不一致");
  if (!sameCanonical(semanticClosure.entries, closure.entries) || !sameCanonical(manifest.closure_entries, closure.closure_entries)) {
    throw new BundleIntegrityError("manifest 与 closure 内容不一致");
  }
  if (semanticClosure.entries.length !== manifest.closure_entries.length) throw new BundleIntegrityError("closure 引用数量不一致");
  const paths = new Set<string>();
  for (let index = 0; index < semanticClosure.entries.length; index += 1) {
    const entry = semanticClosure.entries[index];
    const physical = manifest.closure_entries[index];
    if (!entry || !physical) throw new BundleIntegrityError("closure entry 缺失");
    verifyEntry(entry, physical);
    validatePath(entry.logical_path);
    if (entry.logical_path === "manifest.json" || entry.logical_path === "artifact-closure.json" || paths.has(entry.logical_path)) {
      throw new BundleIntegrityError(`closure 路径重复或保留：${entry.logical_path}`);
    }
    paths.add(entry.logical_path);
  }
  return { manifest, closure };
}

export async function verifyBundleMetadata(manifestValue: unknown, closureValue: unknown, expectedDigest: string, etag = expectedDigest): Promise<{ manifest: BundleManifest; closure: BundleClosure }> {
  const verified = validateManifests(manifestValue, closureValue, etag, expectedDigest);
  const { manifest, closure } = verified;
  if (manifest.closure_manifest_digest !== await hashJson(manifest.closure)) throw new BundleIntegrityError("closure manifest 摘要不匹配");
  const semanticDigest = await hashJson(manifestSemanticPayload(manifest));
  if (closure.bundle_manifest_digest !== semanticDigest) throw new BundleIntegrityError("manifest 语义摘要不匹配");
  if (normalizeSha256(manifest.bundle_digest) !== normalizeSha256(semanticDigest)) throw new BundleIntegrityError("bundle 语义摘要不匹配");
  return verified;
}

/** Reads the agreed uncompressed tar format and installs only a fully verified bundle. */
export async function installBundleTar(options: {
  body: ReadableStream<Uint8Array>;
  store: BundleStore;
  expectedBundleDigest: string;
  etag: string | null;
  contentLength: string | null;
  onProgress?: (progress: BundleDownloadProgress) => void;
}): Promise<{ manifest: BundleManifest; closure: BundleClosure }> {
  const contentLength = Number(options.contentLength);
  if (!Number.isSafeInteger(contentLength) || contentLength < 1024) throw new BundleIntegrityError("响应缺少有效 Content-Length");
  if (!options.etag) throw new BundleIntegrityError("响应缺少 ETag");
  const transaction = await options.store.begin(normalizeSha256(options.expectedBundleDigest));
  const reader = new StreamReader(options.body);
  let pendingPax: MemberPaxHeader | null = null;
  try {
    let manifest: BundleManifest | null = null;
    let closure: BundleClosure | null = null;
    let entryIndex = 0;
    for (;;) {
      const header = await reader.readExactly(BLOCK, true);
      if (!header) throw new BundleIntegrityError("tar 缺少结束标记");
      options.onProgress?.({ receivedBytes: reader.consumedBytes, contentLength });
      if (header.every((byte) => byte === 0)) {
        if (pendingPax) throw new BundleIntegrityError("pax 扩展头没有后继成员");
        const second = await reader.readExactly(BLOCK);
        if (!second || !second.every((byte) => byte === 0)) throw new BundleIntegrityError("tar 结束块无效");
        break;
      }
      const parsed = parseTarHeader(header);
      if (parsed.type === "x") {
        if (pendingPax) throw new BundleIntegrityError("pax 扩展头不能连续出现");
        if (parsed.size > MAX_PAX_PAYLOAD_BYTES || parsed.size > contentLength - reader.consumedBytes) {
          throw new BundleIntegrityError("pax 头超过允许大小");
        }
        const pax = await readMemberBytes(reader, parsed.size, "pax header");
        pendingPax = parseMemberPaxHeader(pax);
        await discardPadding(reader, parsed.size);
        continue;
      }
      if (parsed.type !== "0") throw new BundleIntegrityError(`不支持 tar 成员类型：${parsed.type}`);
      const inheritedPax = pendingPax;
      pendingPax = null;
      const path = checkPathBudget(validatePath(inheritedPax?.path ?? parsed.path));
      const size = inheritedPax?.size ?? parsed.size;
      if (size > contentLength - reader.consumedBytes) throw new BundleIntegrityError(`tar 成员超出 Content-Length：${path}`);
      if (!manifest) {
        if (path !== "manifest.json") throw new BundleIntegrityError("tar 第一个成员必须是 manifest.json");
        const bytes = await readMemberBytes(reader, size, "bundle manifest");
        manifest = parseJson<BundleManifest>(bytes, "bundle manifest");
        await discardPadding(reader, size);
        options.onProgress?.({ receivedBytes: reader.consumedBytes, contentLength });
        continue;
      }
      if (!closure) {
        if (path !== "artifact-closure.json") throw new BundleIntegrityError("tar 第二个成员必须是 artifact-closure.json");
        const bytes = await readMemberBytes(reader, size, "bundle closure");
        closure = parseJson<BundleClosure>(bytes, "bundle closure");
        await verifyBundleMetadata(manifest, closure, options.expectedBundleDigest, options.etag);
        await discardPadding(reader, size);
        options.onProgress?.({ receivedBytes: reader.consumedBytes, contentLength });
        continue;
      }
      const entry = manifest.closure.entries[entryIndex];
      if (!entry) throw new BundleIntegrityError(`tar 中存在未声明成员：${path}`);
      if (path !== entry.logical_path) throw new BundleIntegrityError(`tar 成员顺序或路径不匹配：预期 ${entry.logical_path}，收到 ${path}`);
      if (size !== entry.integrity.size_bytes) throw new BundleIntegrityError(`tar 成员大小与 closure 不符：${path}`);
      await readArtifact(reader, entry, transaction, (receivedBytes) => options.onProgress?.({ receivedBytes, contentLength }), contentLength);
      entryIndex += 1;
    }
    if (pendingPax) throw new BundleIntegrityError("pax 扩展头没有后继成员");
    if (!manifest || !closure) throw new BundleIntegrityError("tar 缺少 bundle manifest 或 closure");
    if (entryIndex !== manifest.closure.entries.length) throw new BundleIntegrityError("tar 未包含全部 closure 产物");
    let hasNonZeroTrailer = false;
    await reader.readToEnd((chunk) => { if (chunk.some((byte) => byte !== 0)) hasNonZeroTrailer = true; });
    if (hasNonZeroTrailer) throw new BundleIntegrityError("tar 结束块之后存在额外数据");
    const received = reader.consumedBytes;
    if (received !== contentLength) throw new BundleIntegrityError(`Content-Length 不匹配：声明 ${contentLength}，收到 ${received}`);
    options.onProgress?.({ receivedBytes: received, contentLength });
    await transaction.commit(manifest, closure);
    return { manifest, closure };
  } catch (error) {
    await transaction.abort();
    throw error;
  } finally {
    reader.release();
  }
}

export function jsonBytes(value: unknown): Uint8Array {
  return new TextEncoder().encode(canonicalJson(value));
}
