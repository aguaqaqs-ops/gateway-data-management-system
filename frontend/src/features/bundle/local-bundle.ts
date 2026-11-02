import { Sha256, normalizeSha256 } from "./sha256";
import { BundleIntegrityError, installBundleTar, type BundleClosure, type BundleManifest, type BundleStore, type BundleWriteTransaction } from "./posix-tar";

const ROOT_NAME = "gateway-comparison-bundles-v1";
const textEncoder = new TextEncoder();
const textDecoder = new TextDecoder();

export interface InstalledBundle {
  manifest: BundleManifest;
  closure: BundleClosure;
  readArtifact(path: string): Promise<Blob>;
}

export interface ReadableBundleStore extends BundleStore {
  open(bundleDigest: string): Promise<InstalledBundle | null>;
}

interface StorageManagerWithOpfs extends StorageManager {
  getDirectory(): Promise<FileSystemDirectoryHandle>;
}

function validateKey(value: string): string {
  const key = normalizeSha256(value);
  if (!/^[a-f0-9]{64}$/.test(key)) throw new Error("bundle digest 必须是 SHA-256");
  return key;
}

function validatePath(path: string): string[] {
  const parts = path.split("/");
  if (!path || path.startsWith("/") || path.includes("\\") || parts.some((part) => !part || part === "." || part === "..")) {
    throw new Error("bundle artifact 路径无效");
  }
  if (parts[0]?.startsWith(".")) throw new Error("bundle artifact 使用了保留路径");
  return parts;
}

async function directory(root: FileSystemDirectoryHandle, path: string, create: boolean): Promise<FileSystemDirectoryHandle> {
  let current = root;
  for (const segment of path.split("/").filter(Boolean)) current = await current.getDirectoryHandle(segment, { create });
  return current;
}

async function removeEntry(root: FileSystemDirectoryHandle, name: string): Promise<void> {
  try { await root.removeEntry(name, { recursive: true }); } catch (error) {
    if (error instanceof DOMException && error.name === "NotFoundError") return;
    throw error;
  }
}

async function readText(dir: FileSystemDirectoryHandle, filename: string): Promise<string> {
  const handle = await dir.getFileHandle(filename);
  return (await handle.getFile()).text();
}

async function hashBlob(blob: Blob): Promise<string> {
  const hash = new Sha256();
  const reader = blob.stream().getReader();
  try {
    for (;;) {
      const next = await reader.read();
      if (next.done) break;
      hash.update(next.value);
    }
  } finally {
    reader.releaseLock();
  }
  return hash.digest();
}

function blobFromBytes(bytes: Uint8Array): Blob {
  const buffer = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(buffer).set(bytes);
  return new Blob([buffer]);
}

function arrayBufferFromBytes(bytes: Uint8Array): ArrayBuffer {
  const buffer = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(buffer).set(bytes);
  return buffer;
}

async function opfsRoot(): Promise<FileSystemDirectoryHandle> {
  if (!navigator.storage || !("getDirectory" in navigator.storage)) throw new Error("当前浏览器不支持 OPFS");
  return (navigator.storage as StorageManagerWithOpfs).getDirectory().then((root) => root.getDirectoryHandle(ROOT_NAME, { create: true }));
}

export class OpfsBundleStore implements ReadableBundleStore {
  constructor(private readonly maxBytes = 4 * 1024 * 1024 * 1024) {}

  async has(bundleDigest: string): Promise<boolean> {
    return (await this.open(bundleDigest)) !== null;
  }

  async open(bundleDigest: string): Promise<InstalledBundle | null> {
    const key = validateKey(bundleDigest);
    const root = await opfsRoot();
    let bundleDir: FileSystemDirectoryHandle;
    try { bundleDir = await root.getDirectoryHandle(key); } catch { return null; }
    try {
      const marker = JSON.parse(await readText(bundleDir, ".complete.json")) as { bundle_digest?: string };
      if (marker.bundle_digest !== key) return null;
      const manifest = JSON.parse(await readText(bundleDir, "manifest.json")) as BundleManifest;
      const closure = JSON.parse(await readText(bundleDir, "artifact-closure.json")) as BundleClosure;
      if (normalizeSha256(manifest.bundle_digest) !== key || normalizeSha256(closure.bundle_digest) !== key) return null;
      for (const entry of manifest.closure) {
        const parts = validatePath(entry.logical_path);
        const parent = await directory(bundleDir, parts.slice(0, -1).join("/"), false);
        await parent.getFileHandle(parts[parts.length - 1] ?? "");
      }
      return {
        manifest,
        closure,
        readArtifact: async (path) => {
          const parts = validatePath(path);
          const parent = await directory(bundleDir, parts.slice(0, -1).join("/"), false);
          const file = await (await parent.getFileHandle(parts[parts.length - 1] ?? "")).getFile();
          const expected = manifest.closure.find((entry) => entry.logical_path === path)?.integrity.raw_sha256;
          if (!expected || normalizeSha256(await hashBlob(file)) !== normalizeSha256(expected)) {
            await removeEntry(root, key);
            throw new Error(`本地 bundle 产物校验失败：${path}`);
          }
          await this.touch(bundleDir);
          return file;
        },
      };
    } catch {
      return null;
    }
  }

  async begin(bundleDigest: string): Promise<BundleWriteTransaction> {
    const key = validateKey(bundleDigest);
    const root = await opfsRoot();
    await removeEntry(root, key);
    const bundleDir = await root.getDirectoryHandle(key, { create: true });
    const writers = new Set<FileSystemWritableFileStream>();
    let complete = false;
    return {
      openArtifact: async (path) => {
        const parts = validatePath(path);
        const parent = await directory(bundleDir, parts.slice(0, -1).join("/"), true);
        const handle = await parent.getFileHandle(parts[parts.length - 1] ?? "", { create: true });
        const writer = await handle.createWritable({ keepExistingData: false });
        writers.add(writer);
        return {
          write: async (chunk) => writer.write(arrayBufferFromBytes(chunk)),
          close: async () => { await writer.close(); writers.delete(writer); },
          abort: async (reason) => { try { await writer.abort(reason); } finally { writers.delete(writer); } },
        };
      },
      commit: async (manifest, closure) => {
        const manifestBytes = textEncoder.encode(JSON.stringify(manifest));
        const closureBytes = textEncoder.encode(JSON.stringify(closure));
        await writeFile(bundleDir, "manifest.json", manifestBytes);
        await writeFile(bundleDir, "artifact-closure.json", closureBytes);
        await writeFile(bundleDir, ".complete.json", textEncoder.encode(JSON.stringify({ bundle_digest: key, committed_at: new Date().toISOString() })));
        await this.evict(root, key, estimateBytes(manifest, closure));
        complete = true;
      },
      abort: async () => {
        for (const writer of writers) try { await writer.abort(); } catch { /* cleanup continues */ }
        writers.clear();
        if (!complete) await removeEntry(root, key);
      },
    };
  }

  private async touch(bundleDir: FileSystemDirectoryHandle): Promise<void> {
    await writeFile(bundleDir, ".last-used", textEncoder.encode(String(Date.now())));
  }

  private async evict(root: FileSystemDirectoryHandle, currentKey: string, currentBytes: number): Promise<void> {
    if (currentBytes > this.maxBytes) throw new Error("bundle 超过本地缓存容量");
    const entries: Array<{ name: string; lastUsed: number; bytes: number }> = [];
    let total = 0;
    for await (const [name, handle] of root.entries()) {
      if (handle.kind !== "directory") continue;
      try {
        const bundle = handle as FileSystemDirectoryHandle;
        const marker = JSON.parse(await readText(bundle, ".complete.json")) as { bundle_digest?: string };
        if (!marker.bundle_digest) continue;
        const lastUsed = Number(await readText(bundle, ".last-used").catch(() => "0")) || 0;
        const bytes = marker.bundle_digest === currentKey ? currentBytes : await estimateDirectoryBytes(bundle);
        total += bytes;
        entries.push({ name, lastUsed, bytes });
      } catch { /* incomplete bundle directories are ignored and cleaned by the next begin */ }
    }
    entries.sort((a, b) => a.lastUsed - b.lastUsed);
    for (const entry of entries) {
      if (total <= this.maxBytes) break;
      if (entry.name === currentKey && entries.length > 1) continue;
      await removeEntry(root, entry.name);
      total -= entry.bytes;
    }
  }
}

async function writeFile(root: FileSystemDirectoryHandle, filename: string, bytes: Uint8Array): Promise<void> {
  const handle = await root.getFileHandle(filename, { create: true });
  const writer = await handle.createWritable({ keepExistingData: false });
  await writer.write(arrayBufferFromBytes(bytes));
  await writer.close();
}

function estimateBytes(manifest: BundleManifest, closure: BundleClosure): number {
  return manifest.closure.reduce((total, entry) => total + entry.integrity.size_bytes, textEncoder.encode(JSON.stringify(manifest)).byteLength + textEncoder.encode(JSON.stringify(closure)).byteLength);
}

async function estimateDirectoryBytes(root: FileSystemDirectoryHandle): Promise<number> {
  let total = 0;
  for await (const [, handle] of root.entries()) {
    if (handle.kind === "file") total += (await (handle as FileSystemFileHandle).getFile()).size;
    else total += await estimateDirectoryBytes(handle as FileSystemDirectoryHandle);
  }
  return total;
}

type EnsureBundleOptions = {
  store: ReadableBundleStore;
  expectedBundleDigest: string;
  fetchBundle: () => Promise<Response>;
  onProgress?: Parameters<typeof installBundleTar>[0]["onProgress"];
};

async function downloadLocalBundle(options: EnsureBundleOptions): Promise<InstalledBundle> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const response = await options.fetchBundle();
    if (!response.ok) throw new Error(`bundle 下载失败（HTTP ${response.status}）`);
    const contentType = response.headers.get("Content-Type")?.split(";", 1)[0]?.trim().toLowerCase();
    if (contentType !== "application/x-tar") throw new Error("bundle 响应类型必须是 application/x-tar");
    const contentEncoding = response.headers.get("Content-Encoding");
    if (contentEncoding && contentEncoding.toLowerCase() !== "identity") throw new Error("bundle tar 不得使用 HTTP 压缩");
    if (!response.body) throw new Error("bundle 响应没有流式 body");
    try {
      await installBundleTar({
        body: response.body,
        store: options.store,
        expectedBundleDigest: options.expectedBundleDigest,
        etag: response.headers.get("ETag"),
        contentLength: response.headers.get("Content-Length"),
        onProgress: options.onProgress,
      });
      const installed = await options.store.open(options.expectedBundleDigest);
      if (!installed) throw new Error("bundle 已验证但无法从本地缓存打开");
      return installed;
    } catch (error) {
      lastError = error;
      if (attempt === 1 || !(error instanceof BundleIntegrityError)) throw error;
    }
  }
  throw lastError;
}

function withLocalReadRetry(bundle: InstalledBundle, options: EnsureBundleOptions, retried: boolean): InstalledBundle {
  return {
    manifest: bundle.manifest,
    closure: bundle.closure,
    async readArtifact(path) {
      try {
        return await bundle.readArtifact(path);
      } catch (error) {
        if (retried) throw error;
        const refreshed = await downloadLocalBundle(options);
        return withLocalReadRetry(refreshed, options, true).readArtifact(path);
      }
    },
  };
}

export async function ensureLocalBundle(options: EnsureBundleOptions): Promise<InstalledBundle> {
  try {
    const cached = await options.store.open(options.expectedBundleDigest);
    if (cached) return withLocalReadRetry(cached, options, false);
  } catch {
    // The local copy may be unavailable or unreadable; fetch a verified copy below.
  }
  return withLocalReadRetry(await downloadLocalBundle(options), options, false);
}

export class MemoryBundleStore implements ReadableBundleStore {
  private readonly bundles = new Map<string, { manifest: BundleManifest; closure: BundleClosure; files: Map<string, Uint8Array> }>();

  async has(bundleDigest: string): Promise<boolean> { return this.bundles.has(validateKey(bundleDigest)); }

  async open(bundleDigest: string): Promise<InstalledBundle | null> {
    const bundle = this.bundles.get(validateKey(bundleDigest));
    if (!bundle) return null;
    return {
      manifest: bundle.manifest,
      closure: bundle.closure,
      readArtifact: async (path) => {
        const bytes = bundle.files.get(path);
        if (!bytes) throw new Error(`本地 bundle 产物不存在：${path}`);
        const expected = bundle.manifest.closure.find((entry) => entry.logical_path === path)?.integrity.raw_sha256;
        const hasher = new Sha256().update(bytes);
        if (!expected || normalizeSha256(hasher.digest()) !== normalizeSha256(expected)) throw new Error(`本地 bundle 产物校验失败：${path}`);
        return blobFromBytes(bytes);
      },
    };
  }

  async begin(bundleDigest: string): Promise<BundleWriteTransaction> {
    const key = validateKey(bundleDigest);
    const files = new Map<string, Uint8Array>();
    let committed = false;
    return {
      openArtifact: async (path) => {
        const parts: Uint8Array[] = [];
        return {
          write: async (chunk) => { parts.push(chunk.slice()); },
          close: async () => {
            const size = parts.reduce((total, chunk) => total + chunk.byteLength, 0);
            const combined = new Uint8Array(size);
            let offset = 0;
            for (const part of parts) { combined.set(part, offset); offset += part.byteLength; }
            files.set(path, combined);
          },
          abort: async () => { parts.length = 0; },
        };
      },
      commit: async (manifest, closure) => {
        this.bundles.set(key, { manifest, closure, files });
        committed = true;
      },
      abort: async () => { if (!committed) files.clear(); this.bundles.delete(key); },
    };
  }
}
