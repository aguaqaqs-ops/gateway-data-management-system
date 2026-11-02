import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptPath = fileURLToPath(import.meta.url);
const frontendRoot = dirname(dirname(scriptPath));
const sourceRoot = join(frontendRoot, "src/test/fixtures/source");

function canonical(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
}

const digest = (bytes) => `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
const jsonBytes = (value) => Buffer.from(canonical(value), "utf8");
const ref = (bytes, mediaType, name) => ({
  artifact_id: `fixture-${digest(bytes).slice(0, 32)}-${name}`,
  media_type: mediaType,
  size_bytes: bytes.byteLength,
  raw_sha256: digest(bytes),
});

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

function physicalEntry(item) {
  const value = {
    artifact_ref: item.ref,
    kind: item.kind,
    logical_path: item.path,
    raw_sha256: item.ref.raw_sha256,
    shared: item.shared ?? false,
    size_bytes: item.ref.size_bytes,
  };
  if (item.kind === "SNAPSHOT_TABLE") value.table_bindings = item.tableBindings;
  else {
    value.pair_id = item.pairId;
    value.table_name = item.tableName;
  }
  return value;
}

function semanticEntry(item) {
  const value = {
    integrity: { media_type: item.ref.media_type, raw_sha256: item.ref.raw_sha256, size_bytes: item.ref.size_bytes },
    kind: item.kind,
    logical_path: item.path,
    shared: item.shared ?? false,
  };
  if (item.kind === "SNAPSHOT_TABLE") value.table_bindings = item.tableBindings;
  else {
    value.pair_id = item.pairId;
    value.table_name = item.tableName;
  }
  return value;
}

async function readJson(path) {
  return JSON.parse(await readFile(join(sourceRoot, path), "utf8"));
}

export async function buildGoldenBundleTar() {
  const [surface, riskReport, navigation, bindingsGolden, surfaceGolden, riskGolden] = await Promise.all([
    readJson("comparison-surface.json"),
    readJson("risk-report.json"),
    readJson("business-navigation.json"),
    readJson("golden/bundle/snapshot-table-bindings.json"),
    readJson("golden/surface/table-presentation.json"),
    readJson("golden/risk/structural-risk.json"),
  ]);
  if (bindingsGolden.cases.identical_snapshot_rows_across_pairs.binding_count !== 1) throw new Error("snapshot binding golden changed");
  if (surfaceGolden.cases.added_column_excluded_values_swapped.change_kind !== "UPDATED") throw new Error("surface golden changed");
  if (riskGolden.cases.incompatible_enum_set_label_change.risk_level !== "MEDIUM_HIGH") throw new Error("risk golden changed");

  const pairId = "initial_to_modified";
  const media = {
    json: "application/json",
    parquet: "application/vnd.apache.parquet",
  };
  const bytes = {
    before: await readFile(join(sourceRoot, "parquet/device.before.parquet")),
    current: await readFile(join(sourceRoot, "parquet/device.current.parquet")),
    records: await readFile(join(sourceRoot, "parquet/device.records.parquet")),
    navigation: jsonBytes(navigation),
    risk: jsonBytes(riskReport),
  };

  const recordManifestValue = {
    contract_version: "backend-vnext/comparison-records-manifest/v1",
    content_digest: digest(bytes.records),
    family: "STANDARD",
    record_count: 3,
    row_diff_detail_policy: "FULL_BEFORE_AFTER_VALUES",
    schema_version: "backend-vnext/comparison-records-standard/v1",
    table_name: "device",
  };
  bytes.recordManifest = jsonBytes(recordManifestValue);
  const artifacts = [
    { path: `pairs/${pairId}/comparison/records/device.records.manifest.json`, kind: "RECORDS_MANIFEST", bytes: bytes.recordManifest, mediaType: media.json, pairId, tableName: "device" },
    { path: `pairs/${pairId}/comparison/records/device.records.parquet`, kind: "RECORDS", bytes: bytes.records, mediaType: media.parquet, pairId, tableName: "device" },
    { path: `pairs/${pairId}/projections/business-navigation/fixture-generated-from-the-approved-be-b-draft/business-navigation.json`, kind: "PROJECTION", bytes: bytes.navigation, mediaType: media.json, pairId, tableName: "device" },
    { path: `pairs/${pairId}/risk/risk-report.json`, kind: "RISK_REPORT", bytes: bytes.risk, mediaType: media.json, pairId, tableName: "device" },
    { path: `pairs/${pairId}/tables/before/device.parquet`, kind: "SNAPSHOT_TABLE", bytes: bytes.before, mediaType: media.parquet, pairId, tableName: "device", tableBindings: [{ pair_id: pairId, side: "before", table_name: "device" }] },
    { path: `pairs/${pairId}/tables/current/device.parquet`, kind: "SNAPSHOT_TABLE", bytes: bytes.current, mediaType: media.parquet, pairId, tableName: "device", tableBindings: [{ pair_id: pairId, side: "current", table_name: "device" }] },
  ].map((item) => ({ ...item, ref: ref(item.bytes, item.mediaType, item.kind.toLowerCase()) }));

  const recordRef = artifacts.find((item) => item.kind === "RECORDS").ref;
  const recordManifestRef = artifacts.find((item) => item.kind === "RECORDS_MANIFEST").ref;
  const currentTableRef = artifacts.find((item) => item.kind === "SNAPSHOT_TABLE" && item.tableBindings[0].side === "current").ref;
  const beforeTableRef = artifacts.find((item) => item.kind === "SNAPSHOT_TABLE" && item.tableBindings[0].side === "before").ref;
  const navigationRef = artifacts.find((item) => item.kind === "PROJECTION").ref;
  const riskRef = artifacts.find((item) => item.kind === "RISK_REPORT").ref;
  const surfaceDigest = digest(Buffer.from("fixture-surface-semantic-digest", "utf8"));
  const comparisonDigest = digest(Buffer.from("fixture-comparison-semantic-digest", "utf8"));
  const riskDigest = digest(Buffer.from("fixture-risk-evaluation-digest", "utf8"));
  surface.surface_digest = surfaceDigest;
  surface.comparison_digest = comparisonDigest;
  surface.surface_id = "fixture-surface-device";
  surface.project_identity_status = "SAME_PROJECT";
  surface.project_identity_assessment_digest = null;
  surface.requires_submit_confirmation = false;
  surface.risk_evaluation_digest = riskDigest;
  surface.tables[0].table_refs = { before_table_ref: beforeTableRef, current_table_ref: currentTableRef, browse_table_ref: null };
  surface.tables[0].records_refs = { records_format: "PARQUET", records_ref: recordRef, records_manifest_ref: recordManifestRef };
  surface.tables[0].risk_refs = { annotation_count: 1, annotation_manifest_ref: null, annotation_ref: null, reason_codes: ["SCHEMA_CHANGED"], report_ref: riskRef, risk_level: "MEDIUM_HIGH" };
  surface.projections = [{ projection_id: "business-navigation", projection_kind: "BUSINESS_NAVIGATION", projection_ref: navigationRef, projection_digest: digest(bytes.navigation), projection_summary: [{ key: "group_count", value: String(navigation.groups.length) }], risk_summary_ref: null, diagnostics_ref: null }];
  const surfaceBytes = jsonBytes(surface);
  artifacts.push({ path: `pairs/${pairId}/comparison-surface.json`, kind: "SURFACE", bytes: surfaceBytes, mediaType: media.json, pairId, tableName: "device", ref: ref(surfaceBytes, media.json, "surface") });
  artifacts.sort((left, right) => left.path.localeCompare(right.path) || left.kind.localeCompare(right.kind));

  const semanticEntries = artifacts.map(semanticEntry);
  const physicalEntries = artifacts.map(physicalEntry);
  const closure = { entries: semanticEntries };
  const closureDigest = digest(jsonBytes(closure));
  const manifestSemantic = {
    bundle_contract_version: "backend-vnext/comparison-bundle/v3",
    bundle_profile: "SINGLE_PAIR",
    closure: semanticEntries,
    diagnostics: [],
    failed_pairs: [],
    inputs: [
      { display_metadata: {}, display_name: "基线组态", input_index: 0, role: "BEFORE", snapshot_digest: null },
      { display_metadata: {}, display_name: "上传组态", input_index: 1, role: "CURRENT", snapshot_digest: null },
    ],
    pairs: [{
      before_input_index: 0,
      comparison_digest: comparisonDigest,
      current_input_index: 1,
      pair_id: pairId,
      risk_evaluation_digest: riskDigest,
      status: "PUBLISHED",
      summary: { changed_table_count: "1", risk_level: "MEDIUM_HIGH" },
      surface_digest: surfaceDigest,
    }],
    status: "READY",
  };
  const bundleDigest = digest(jsonBytes(manifestSemantic));
  const manifest = {
    ...manifestSemantic,
    bundle_digest: bundleDigest,
    closure_manifest_digest: closureDigest,
    closure_entries: physicalEntries,
  };
  const manifestSemanticDigest = digest(jsonBytes(manifestSemantic));
  const closureDocument = {
    bundle_contract_version: "backend-vnext/comparison-bundle/v3",
    bundle_digest: bundleDigest,
    bundle_manifest_digest: manifestSemanticDigest,
    ...closure,
    closure_entries: physicalEntries,
  };
  const members = [
    ["manifest.json", jsonBytes(manifest)],
    ["artifact-closure.json", jsonBytes(closureDocument)],
    ...artifacts.map((artifact) => [artifact.path, artifact.bytes]),
  ];
  return { bytes: createTar(members), bundleDigest, manifest, closure: closureDocument, source: { bindingsGolden, surfaceGolden, riskGolden } };
}

if (process.argv[1] && resolve(process.argv[1]) === scriptPath) {
  const result = await buildGoldenBundleTar();
  const output = join(frontendRoot, "src/test/fixtures/generated/golden-bundle.tar");
  await mkdir(dirname(output), { recursive: true });
  await writeFile(output, result.bytes);
  process.stdout.write(`fixture_bundle_digest=${result.bundleDigest}\nfixture_tar_bytes=${result.bytes.byteLength}\nfixture_tar_sha256=${digest(result.bytes)}\n`);
}
