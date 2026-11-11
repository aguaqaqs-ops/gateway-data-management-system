import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptPath = fileURLToPath(import.meta.url);
const frontendRoot = dirname(dirname(scriptPath));
const sourceRoot = join(frontendRoot, "src/test/fixtures/source/backend");
// Every bundle the mock e2e suite can open by name. `fe2a`/`fe2b` hold the
// Preview/History journeys, `scenarios` the BE-b acceptance scenarios that back
// the FE4b business-navigation and row-location screenshots.
const fixtureDirectories = {
  "preview-full": "fe2a/preview-full",
  "preview-modified-only": "fe2a/preview-modified-only",
  "preview-replacement": "fe2a/preview-replacement",
  "history-three-nodes": "fe2a/history-three-nodes",
  "preview-workbench-normal": "fe2b/preview-workbench-normal",
  "identity-changes": "scenarios/identity-changes",
  "duplicates-orphans": "scenarios/duplicates-orphans",
  "text-identities": "scenarios/text-identities",
  "integer-boundary": "scenarios/integer-boundary",
  "schema-keyless": "scenarios/schema-keyless",
  "table-addition": "scenarios/table-addition",
  "comment-only": "scenarios/comment-only",
  "formula-unchanged-device": "scenarios/formula-unchanged-device",
  "identity-unrecorded-exact": "scenarios/identity-unrecorded-exact",
  "excluded-identity": "scenarios/excluded-identity",
  "missing-identity-column": "scenarios/missing-identity-column",
};
const fixtureNames = Object.keys(fixtureDirectories);

const sha256 = (bytes) => `sha256:${createHash("sha256").update(bytes).digest("hex")}`;

function octal(value, width) {
  return `${value.toString(8).padStart(width - 1, "0")}\0`;
}

function tarHeader(path, bytes, type = "0") {
  const header = Buffer.alloc(512);
  const name = Buffer.from(path, "utf8");
  if (name.byteLength > 100) throw new Error("tar fallback path must fit the ustar name field");
  name.copy(header, 0);
  Buffer.from(octal(0o644, 8)).copy(header, 100);
  Buffer.from(octal(0, 8)).copy(header, 108);
  Buffer.from(octal(0, 8)).copy(header, 116);
  Buffer.from(octal(bytes.byteLength, 12)).copy(header, 124);
  Buffer.from(octal(0, 12)).copy(header, 136);
  header.fill(0x20, 148, 156);
  header[156] = type.charCodeAt(0);
  Buffer.from("ustar\0", "ascii").copy(header, 257);
  Buffer.from("00", "ascii").copy(header, 263);
  const checksum = header.reduce((sum, byte) => sum + byte, 0);
  Buffer.from(`${checksum.toString(8).padStart(6, "0")}\0 `, "ascii").copy(header, 148);
  return header;
}

function paxRecord(key, value) {
  const body = `${key}=${value}\n`;
  let length = Buffer.byteLength(body) + 2;
  for (;;) {
    const next = Buffer.byteLength(body) + String(length).length + 1;
    if (next === length) return Buffer.from(`${length} ${body}`, "utf8");
    length = next;
  }
}

function pushEntry(chunks, path, bytes, index) {
  const utf8Path = Buffer.from(path, "utf8");
  if (utf8Path.byteLength > 100) {
    const pax = paxRecord("path", path);
    chunks.push(tarHeader(`PaxHeaders/${index}`, pax, "x"), pax);
    chunks.push(Buffer.alloc((512 - pax.byteLength % 512) % 512));
    chunks.push(tarHeader(`PaxFile/${index}`, bytes), bytes);
  } else {
    chunks.push(tarHeader(path, bytes), bytes);
  }
  chunks.push(Buffer.alloc((512 - bytes.byteLength % 512) % 512));
}

function createTar(members) {
  const chunks = [];
  members.forEach(([path, bytes], index) => pushEntry(chunks, path, bytes, index));
  chunks.push(Buffer.alloc(1024));
  return Buffer.concat(chunks);
}

async function readBackendBundle(fixtureName) {
  const fixtureDirectory = fixtureDirectories[fixtureName];
  if (!fixtureDirectory) throw new Error("unknown golden fixture: " + fixtureName);
  const fixtureRoot = join(sourceRoot, ...fixtureDirectory.split("/"));
  const manifestBytes = await readFile(join(fixtureRoot, "manifest.json"));
  const closureBytes = await readFile(join(fixtureRoot, "artifact-closure.json"));
  const manifest = JSON.parse(manifestBytes.toString("utf8"));
  const closure = JSON.parse(closureBytes.toString("utf8"));
  const entries = manifest?.closure?.entries;
  const physicalEntries = manifest?.closure_entries;
  if (!Array.isArray(entries) || !Array.isArray(physicalEntries) || entries.length !== physicalEntries.length) {
    throw new Error("backend manifest must provide matching closure.entries and closure_entries arrays");
  }
  if (closure.bundle_digest !== manifest.bundle_digest || closure.bundle_manifest_digest !== manifest.bundle_digest) {
    throw new Error("backend closure digests do not match the manifest bundle digest");
  }

  const members = [["manifest.json", manifestBytes], ["artifact-closure.json", closureBytes]];
  for (let index = 0; index < entries.length; index += 1) {
    const entry = entries[index];
    const physical = physicalEntries[index];
    if (!entry || !physical || entry.logical_path !== physical.logical_path) {
      throw new Error(`backend closure order differs at index ${index}`);
    }
    const logicalPath = entry.logical_path;
    if (typeof logicalPath !== "string" || logicalPath.startsWith("/") || logicalPath.includes("\\") || logicalPath.split("/").some((part) => !part || part === "." || part === "..")) {
      throw new Error(`backend emitted an invalid logical path: ${logicalPath}`);
    }
    const artifactBytes = await readFile(join(fixtureRoot, ...logicalPath.split("/")));
    if (artifactBytes.byteLength !== entry.integrity.size_bytes || sha256(artifactBytes) !== entry.integrity.raw_sha256) {
      throw new Error(`backend artifact bytes do not match closure integrity: ${logicalPath}`);
    }
    members.push([logicalPath, artifactBytes]);
  }
  return { members, manifest, closure };
}

export async function buildGoldenBundleTar() {
  const bundle = await readBackendBundle("preview-full");
  return { ...bundle, bytes: createTar(bundle.members) };
}

if (process.argv[1] && resolve(process.argv[1]) === scriptPath) {
  const outputRoot = join(frontendRoot, "src/test/fixtures/generated");
  await mkdir(outputRoot, { recursive: true });
  for (const fixtureName of fixtureNames) {
    const bundle = await readBackendBundle(fixtureName);
    const bytes = createTar(bundle.members);
    await writeFile(join(outputRoot, fixtureName + ".tar"), bytes);
    process.stdout.write("fixture=" + fixtureName + "\n");
    process.stdout.write("fixture_bundle_digest=" + bundle.manifest.bundle_digest + "\n");
    process.stdout.write("fixture_closure_manifest_digest=" + bundle.manifest.closure_manifest_digest + "\n");
    process.stdout.write("fixture_bundle_manifest_digest=" + bundle.closure.bundle_manifest_digest + "\n");
    process.stdout.write("fixture_tar_bytes=" + bytes.byteLength + "\n");
    process.stdout.write("fixture_tar_sha256=" + sha256(bytes) + "\n");
    if (fixtureName === "preview-full") await writeFile(join(outputRoot, "golden-bundle.tar"), bytes);
  }
}
