/**
 * Browser-side packaging for the Source Package Contract.
 *
 * The upload Contract accepts a gzip-compressed tar archive whose paths are
 * relative to the selected root directory and which contains `/sql/dbcfg.sql`
 * (required) and `/comps/logic/logics.xml` (optional). The whole selected
 * directory is archived, matching the "original/current configuration backup"
 * meaning of the two artifact roles; the backend ignores members outside the
 * two Contract paths.
 */

export const MAX_DIRECTORY_FILES = 5_000;
export const MAX_DIRECTORY_BYTES = 1024 * 1024 * 1024;
export const REQUIRED_SQL_PATH = "sql/dbcfg.sql";
export const OPTIONAL_XML_PATH = "comps/logic/logics.xml";
export const MAX_ARCHIVE_BYTES = 256 * 1024 * 1024;
export const MAX_ARCHIVE_ENTRIES = 8_192;

export interface LocalDirectoryFile {
  path: string;
  file: File;
}

export interface LocalDirectory {
  rootName: string;
  files: LocalDirectoryFile[];
  totalBytes: number;
  mainFile: string;
}

export interface LocalDirectoryValidation {
  directory: LocalDirectory | null;
  errors: string[];
}

interface RelativeFile {
  path: string;
  file: File;
}

type FileWithRelativePath = File & { webkitRelativePath?: string };

function relativePath(file: File): string {
  return ((file as FileWithRelativePath).webkitRelativePath ?? "").replaceAll("\\", "/");
}

/** Collects a directory input into a normalized list relative to its single root. */
export function collectLocalDirectory(input: FileList | File[]): LocalDirectoryValidation {
  const files = Array.from(input);
  if (files.length === 0) return { directory: null, errors: ["未选择目录"] };
  const roots = new Set<string>();
  const relative: RelativeFile[] = [];
  for (const file of files) {
    const raw = relativePath(file);
    const parts = raw.split("/").filter(Boolean);
    if (parts.length < 2) return { directory: null, errors: ["只能选择一个根目录"] };
    const [root, ...rest] = parts;
    roots.add(root);
    relative.push({ path: rest.join("/"), file });
  }
  if (roots.size !== 1) return { directory: null, errors: ["只能选择一个根目录"] };
  const rootName = [...roots][0] ?? "";
  const byPath = new Map(relative.map((item) => [item.path, item]));
  const rootFiles = relative.filter((item) => !item.path.includes("/"));
  const mainFiles = rootFiles.filter((item) => item.path.toLocaleLowerCase().endsWith(".pmc"));
  const totalBytes = relative.reduce((sum, item) => sum + item.file.size, 0);
  const errors: string[] = [];
  if (mainFiles.length !== 1) errors.push("根目录下必须恰好存在一个 .pmc 文件");
  if (!byPath.has(REQUIRED_SQL_PATH)) errors.push("目录中必须存在 sql/dbcfg.sql");
  if (relative.length > MAX_DIRECTORY_FILES) errors.push(`文件数量不能超过 ${MAX_DIRECTORY_FILES} 个`);
  if (totalBytes > MAX_DIRECTORY_BYTES) errors.push("目录总大小不能超过 1 GB");
  if (errors.length > 0) return { directory: null, errors };
  const directory: LocalDirectory = {
    rootName,
    files: relative.sort((left, right) => left.path.localeCompare(right.path)),
    totalBytes,
    mainFile: mainFiles[0]?.path ?? "",
  };
  return { directory, errors: [] };
}

const BLOCK_SIZE = 512;

function encode(value: string): Uint8Array {
  return new TextEncoder().encode(value);
}

function writeString(header: Uint8Array, offset: number, length: number, value: string): void {
  const bytes = encode(value);
  header.set(bytes.subarray(0, Math.max(0, length - 1)), offset);
}

function writeOctal(header: Uint8Array, offset: number, length: number, value: number): void {
  writeString(header, offset, length, `${value.toString(8).padStart(length - 1, "0")}\0`);
}

function fits(text: string, limit: number): boolean {
  return encode(text).length <= limit;
}

/** ustar header with deterministic metadata (mtime 0, uid/gid 0, mode 0644). */
function tarHeader(path: string, size: number): Uint8Array {
  const header = new Uint8Array(BLOCK_SIZE);
  let name = path;
  let prefix = "";
  if (!fits(name, 100)) {
    const parts = path.split("/");
    for (let index = 1; index < parts.length; index += 1) {
      const candidateName = parts.slice(index).join("/");
      const candidatePrefix = parts.slice(0, index).join("/");
      if (fits(candidateName, 100) && fits(candidatePrefix, 155)) {
        name = candidateName;
        prefix = candidatePrefix;
        break;
      }
    }
    if (!prefix) throw new Error(`目录中的文件路径过长，无法打包：${path}`);
  }
  writeString(header, 0, 100, name);
  writeString(header, 100, 8, "0000644\0");
  writeString(header, 108, 8, "0000000\0");
  writeString(header, 116, 8, "0000000\0");
  writeOctal(header, 124, 12, size);
  writeOctal(header, 136, 12, 0);
  header.fill(0x20, 148, 156);
  writeString(header, 156, 1, "0");
  writeString(header, 257, 6, "ustar\0");
  writeString(header, 263, 2, "00");
  writeString(header, 345, 155, prefix);
  let checksum = 0;
  for (const byte of header) checksum += byte;
  writeString(header, 148, 8, `${checksum.toString(8).padStart(6, "0")}\0 `);
  return header;
}

function pad(length: number): Uint8Array {
  const remainder = length % BLOCK_SIZE;
  return new Uint8Array(remainder === 0 ? 0 : BLOCK_SIZE - remainder);
}

/** Deterministic ustar archive; exported for unit tests. */
export async function buildTar(directory: LocalDirectory): Promise<Uint8Array> {
  const blocks: Uint8Array[] = [];
  for (const entry of directory.files) {
    if (entry.path.startsWith("/") || entry.path.split("/").some((part) => part === "..")) {
      throw new Error(`目录中的文件路径不安全：${entry.path}`);
    }
    const content = new Uint8Array(await entry.file.arrayBuffer());
    blocks.push(tarHeader(entry.path, content.byteLength), content, pad(content.byteLength));
  }
  blocks.push(new Uint8Array(BLOCK_SIZE * 2));
  const total = blocks.reduce((sum, block) => sum + block.byteLength, 0);
  const archive = new Uint8Array(total);
  let offset = 0;
  for (const block of blocks) {
    archive.set(block, offset);
    offset += block.byteLength;
  }
  return archive;
}

/** Packages one selected directory as a deterministic gzip-compressed tar artifact. */
export async function buildSourcePackage(directory: LocalDirectory): Promise<File> {
  if (directory.files.length > MAX_ARCHIVE_ENTRIES) throw new Error("条目超过 8192，后端将返回 413");
  const tar = await buildTar(directory);
  const source = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(tar);
      controller.close();
    },
  });
  const compressed = source.pipeThrough(new CompressionStream("gzip") as unknown as TransformStream<Uint8Array, Uint8Array>);
  const bytes = await new Response(compressed).arrayBuffer();
  if (bytes.byteLength > MAX_ARCHIVE_BYTES) throw new Error("压缩后超过 256 MiB，后端将返回 413");
  return new File([bytes], `${directory.rootName}.tar.gz`, { type: "application/gzip" });
}
