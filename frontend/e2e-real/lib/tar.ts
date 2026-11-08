import { createHash } from "node:crypto";
import { canonicalJson } from "../../src/features/bundle/sha256";

/**
 * Minimal reader for the deterministic POSIX tar files the backend returns at
 * the bundle paths (vnext backend `artifacts/tar_stream.py`):
 *
 * - 512-byte headers, `ustar\0` magic, octal size field, mtime 0;
 * - `0` (ordinary) members and `x` (PAX) headers for non-ASCII/long paths or
 *   sizes >= 8**11;
 * - two zero blocks terminate the archive (readers stop at the first all-zero
 *   header, so a truncated archive is detected by the members it is missing).
 *
 * We read the members in the test process instead of re-downloading through a
 * JSON endpoint: the real backend streams `application/x-tar` (FE3b §4.7/§3.3).
 */
export interface TarMember {
  path: string;
  size: number;
  headerSize: number;
  body: Buffer;
}

export interface TarFacts {
  members: Map<string, Buffer>;
  /** Member digests verified against `artifact-closure.json` (hex, no prefix). */
  digests: Map<string, string>;
}

export interface BundleManifest {
  bundle_contract_version: number;
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
  closure: unknown;
  closure_entries: unknown;
  bundle_digest: string;
  closure_manifest_digest: string;
}

export interface BundleClosureEntry {
  logical_path: string;
  size_bytes: number;
  raw_sha256: string;
}

export interface BundleClosure {
  bundle_contract_version: number;
  bundle_digest: string;
  bundle_manifest_digest: string;
  entries: BundleClosureEntry[];
  closure_entries: unknown;
}

const BLOCK = 512;

function padToBlock(size: number): number {
  return Math.ceil(size / BLOCK) * BLOCK;
}

function readField(header: Buffer, start: number, length: number): string {
  const raw = header.subarray(start, start + length);
  const nul = raw.indexOf(0);
  return raw.subarray(0, nul === -1 ? raw.length : nul).toString("utf8");
}

function readOctal(header: Buffer, start: number, length: number): number {
  const text = readField(header, start, length).trim();
  if (!text) return 0;
  const parsed = Number.parseInt(text, 8);
  return Number.isFinite(parsed) ? parsed : 0;
}

function readPaxRecords(data: Buffer): Map<string, string> {
  const records = new Map<string, string>();
  let offset = 0;
  while (offset < data.length) {
    const space = data.indexOf(0x20, offset);
    if (space === -1) break;
    const length = Number.parseInt(data.subarray(offset, space).toString("utf8"), 10);
    if (!Number.isFinite(length) || length <= 0) break;
    const record = data.subarray(space + 1, offset + length - 1).toString("utf8");
    const equals = record.indexOf("=");
    if (equals > 0) records.set(record.slice(0, equals), record.slice(equals + 1));
    offset += length;
  }
  return records;
}

export function readTarMembers(tar: Buffer): TarMember[] {
  const members: TarMember[] = [];
  let offset = 0;
  let pax: Map<string, string> | null = null;
  while (offset + BLOCK <= tar.length) {
    const header = tar.subarray(offset, offset + BLOCK);
    if (header.every((byte) => byte === 0)) break;
    const name = readField(header, 0, 100);
    const headerSize = readOctal(header, 124, 12);
    const typeflag = header.subarray(156, 157).toString("utf8");
    const dataStart = offset + BLOCK;
    if (typeflag === "x") {
      pax = readPaxRecords(tar.subarray(dataStart, dataStart + headerSize));
      offset = dataStart + padToBlock(headerSize);
      continue;
    }
    const path = pax?.get("path") ?? name;
    const size = pax?.has("size") ? Number.parseInt(pax.get("size") ?? "", 10) : headerSize;
    if (!Number.isFinite(size) || dataStart + size > tar.length) {
      throw new Error(`tar 成员 ${path} 被截断：声明 ${size} 字节`);
    }
    members.push({ path, size, headerSize, body: Buffer.from(tar.subarray(dataStart, dataStart + size)) });
    pax = null;
    offset = dataStart + padToBlock(size);
  }
  return members;
}

export function sha256Hex(body: Buffer): string {
  return createHash("sha256").update(body).digest("hex");
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

/**
 * Parse a bundle tar and verify the manifest/closure identity plus every member
 * digest (`ETag`, `manifest.bundle_digest`, `artifact-closure.json` entries).
 */
export function parseBundleTar(tar: Buffer): ParsedBundle {
  const members = readTarMembers(tar);
  const byPath = new Map(members.map((member) => [member.path, member]));
  const manifestMember = byPath.get("manifest.json");
  const closureMember = byPath.get("artifact-closure.json");
  if (!manifestMember) throw new Error("bundle tar 缺少 manifest.json");
  if (!closureMember) throw new Error("bundle tar 缺少 artifact-closure.json");
  const manifest = JSON.parse(manifestMember.body.toString("utf8")) as BundleManifest;
  const closure = JSON.parse(closureMember.body.toString("utf8")) as BundleClosure;
  // The backend digest is over the manifest semantic payload (JCS canonical
  // JSON without bundle_digest/closure_manifest_digest/closure_entries), not
  // over the manifest document bytes; mirrors posix-tar verifyBundleMetadata.
  const semantic = { ...(manifest as unknown as Record<string, unknown>) };
  delete semantic.bundle_digest;
  delete semantic.closure_manifest_digest;
  delete semantic.closure_entries;
  const manifestDigest = sha256Hex(Buffer.from(canonicalJson(semantic), "utf8"));
  if (digestHex(closure.bundle_manifest_digest) !== manifestDigest) {
    throw new Error("closure.bundle_manifest_digest 与 manifest 语义摘要不一致");
  }
  if (digestHex(manifest.bundle_digest) !== manifestDigest) {
    throw new Error("manifest.bundle_digest 与 manifest 语义摘要不一致");
  }
  if (digestHex(closure.bundle_digest) !== digestHex(manifest.bundle_digest)) {
    throw new Error("closure.bundle_digest 与 manifest.bundle_digest 不一致");
  }
  const entries = new Map(closure.entries.map((entry) => [entry.logical_path, entry]));
  for (const member of members) {
    if (member.path === "manifest.json" || member.path === "artifact-closure.json") continue;
    const entry = entries.get(member.path);
    if (!entry) throw new Error(`closure 未声明 tar 成员 ${member.path}`);
    if (entry.size_bytes !== member.body.length) throw new Error(`成员 ${member.path} 大小与 closure 不一致（tar=${member.body.length}, closure=${entry.size_bytes}, header=${member.headerSize}）`);
    if (digestHex(entry.raw_sha256) !== sha256Hex(member.body)) throw new Error(`成员 ${member.path} 摘要与 closure 不一致`);
  }
  return {
    members,
    manifest,
    closure,
    manifestDigest,
    bundleDigest: digestHex(manifest.bundle_digest),
  };
}

export function countBundlePairs(manifest: BundleManifest): number {
  return manifest.pairs.length;
}
