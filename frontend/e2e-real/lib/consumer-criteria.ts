import { parquetReadObjects, type AsyncBuffer, type ParquetRow } from "hyparquet";
import { compressors } from "hyparquet-compressors";

/**
 * FE-BEB-03 consumer criteria (FE4 kickoff §5.3) for a downloaded comparison
 * bundle. This is an independent oracle: it reads the same tar members the
 * browser installs and re-checks the four published criteria without calling
 * the product view-model's filtering, locating or summary helpers.
 *
 * 1. navigation shape: exactly one BUSINESS_NAVIGATION projection per pair,
 *    the five fixed groups in order for ordinary pairs, and the B1
 *    uniqueness/routing invariants;
 * 2. unreferenced tables: no side rows, UNCHANGED/BUSINESS_EQUIVALENT and no
 *    risk;
 * 3. per-side coverage: for shared tables with published filter tabs, the
 *    union of the published predicates plus the same-side
 *    DEVICE_ROWS_UNASSIGNED count equals the snapshot row count;
 * 4. row locations: every published STANDARD ordinary record has exactly one
 *    locator row, side existence matches the record kind, snapshot-side
 *    indexes are legal and context-free, missing-snapshot sides carry a
 *    filter context when filter tabs are published, and no table-level
 *    fallback is accepted.
 *
 * The consumer does not recompute production row identities (row-location
 * contract): identities are compared as the published `sha256:` spellings of
 * the 32 raw identity bytes.
 */

export interface BundleMemberLike {
  path: string;
  body: Buffer;
}

export interface ArtifactRefLike {
  artifact_id?: unknown;
  raw_sha256?: unknown;
  size_bytes?: unknown;
}

export interface ClosureEntryLike {
  logical_path?: unknown;
  artifact_ref?: ArtifactRefLike;
}

/** Structural subset of `ParsedBundle` (e2e-real/lib/tar.ts) the checks need. */
export interface BundleCriteriaSource {
  members: BundleMemberLike[];
  closure: { closure_entries?: ClosureEntryLike[] };
}

interface Predicate {
  column: string;
  values: Array<string | number>;
}

interface RowFilter {
  before: Predicate | null;
  current: Predicate | null;
}

interface NavigationTab {
  tab_key: string;
  table_id: string;
  row_filter: RowFilter | null;
  facts: { basis?: unknown } | null;
  side?: "before" | "current";
}

interface NavigationItem {
  item_key: string;
  tabs: NavigationTab[];
}

interface NavigationGroup {
  group_key: string;
  items: NavigationItem[];
}

interface NavigationDocument {
  contract_version?: unknown;
  groups?: NavigationGroup[];
  replacement_sides?: { before: NavigationGroup[]; current: NavigationGroup[] } | null;
}

interface BindingSide {
  row_count?: unknown;
}

interface SurfaceTable {
  table_id: string;
  table_name?: string;
  change_kind?: unknown;
  records_refs?: { records_ref?: ArtifactRefLike | null } | null;
  table_content_bindings?: Record<string, BindingSide | null> | null;
  risk_refs?: { risk_level?: unknown; annotation_count?: unknown } | null;
  row_locator_ref?: ArtifactRefLike | null;
  table_refs?: Record<string, ArtifactRefLike | null> | null;
}

interface ComparisonSurface {
  surface_contract_version?: unknown;
  comparison_mode?: unknown;
  tables?: SurfaceTable[];
  projections?: Array<{
    projection_kind?: unknown;
    projection_ref?: ArtifactRefLike | null;
    diagnostics_ref?: ArtifactRefLike | null;
  }>;
}

interface NavigationDiagnostic {
  code?: unknown;
  side?: unknown;
  params?: Record<string, unknown> | null;
  target?: { table_id?: unknown } | null;
}

export interface PairCriteriaSummary {
  pair_id: string;
  mode: string;
  table_count: number;
  navigation_tab_count: number;
  fallback_tab_count: number;
  fallback_table_count: number;
  located_table_count: number;
  located_row_count: number;
  covered_filter_sides: number;
  unreferenced_table_count: number;
}

export interface BundleCriteriaSummary {
  pair_ids: string[];
  pairs: PairCriteriaSummary[];
}

const SURFACE_CONTRACT_VERSION = "backend-vnext/comparison-surface/v4";
const NAVIGATION_CONTRACT_VERSION = "backend-vnext/business-navigation/v1";
const FIXED_GROUPS = [
  "FORWARD_CHANNELS",
  "SECONDARY_DEVICES",
  "COMMUNICATION_PROTOCOLS",
  "GLOBAL_PARAMETERS",
  "OTHER_TABLES",
] as const;
const STANDARD_ORDINARY_KINDS = new Set(["ROW_ADDED", "ROW_DELETED", "ROW_MODIFIED"]);

function fail(where: string, message: string): never {
  throw new Error(`${where}: ${message}`);
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function identityHex(value: unknown): string {
  let bytes: Uint8Array | null = null;
  if (value instanceof Uint8Array) bytes = value;
  else if (value instanceof ArrayBuffer) bytes = new Uint8Array(value);
  else if (ArrayBuffer.isView(value)) bytes = new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
  if (!bytes || bytes.byteLength !== 32) fail("locator", `行身份不是 32 字节（${String(value)}）`);
  return `sha256:${Buffer.from(bytes).toString("hex")}`;
}

function contextDocument(value: unknown, where: string): Record<string, unknown> | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value !== "string") fail(where, "过滤上下文不是 JSON 文本");
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    fail(where, "过滤上下文不是合法 JSON");
  }
  const document = asRecord(parsed);
  if (!document) fail(where, "过滤上下文不是对象");
  if (Object.keys(document).length === 0) return null;
  return document;
}

function indexValue(value: unknown, where: string): number | null {
  if (value === null || value === undefined) return null;
  const index = typeof value === "bigint" ? Number(value) : value;
  if (typeof index !== "number" || !Number.isSafeInteger(index) || index < 0) fail(where, `行下标无效（${String(value)}）`);
  return index;
}

function compareValues(row: ParquetRow, column: string, predicate: Predicate): boolean {
  const raw = row[column];
  if (raw === null || raw === undefined) return false;
  if (typeof raw === "bigint") {
    if (predicate.values.some((value) => typeof value !== "number")) return false;
    const text = raw.toString();
    return predicate.values.some((value) => (value as number).toString() === text);
  }
  if (raw instanceof Uint8Array || raw instanceof ArrayBuffer || ArrayBuffer.isView(raw)) return false;
  const text = String(raw);
  return predicate.values.some((value) => {
    if (typeof value === "number") return /^-?\d+$/.test(text) && text === String(value);
    return text === value;
  });
}

function decodePredicate(value: unknown, where: string): Predicate {
  const record = asRecord(value);
  if (!record) fail(where, "谓词不是对象");
  if (typeof record.column !== "string" || record.column === "") fail(where, "谓词缺少 column");
  if (!Array.isArray(record.values) || record.values.length === 0) fail(where, "谓词 values 为空");
  const values = record.values as unknown[];
  const allNumbers = values.every((item) => typeof item === "number" && Number.isSafeInteger(item));
  const allStrings = values.every((item) => typeof item === "string");
  if (!allNumbers && !allStrings) fail(where, "谓词 values 不是同类型的安全整数或字符串");
  if (new Set(values.map(String)).size !== values.length) fail(where, "谓词 values 有重复");
  const ordered = [...values].sort((left, right) =>
    allNumbers ? (left as number) - (right as number) : Buffer.compare(Buffer.from(left as string, "utf8"), Buffer.from(right as string, "utf8")),
  );
  if (ordered.some((item, index) => item !== values[index])) fail(where, "谓词 values 未按规范顺序排列");
  return { column: record.column, values: values as Array<string | number> };
}

function decodeRowFilter(value: unknown, where: string): RowFilter | null {
  if (value === null || value === undefined) return null;
  const record = asRecord(value);
  if (!record) fail(where, "row_filter 不是对象");
  const before = record.before === null || record.before === undefined ? null : decodePredicate(record.before, `${where}.before`);
  const current = record.current === null || record.current === undefined ? null : decodePredicate(record.current, `${where}.current`);
  if (before === null && current === null) fail(where, "row_filter 两侧都不存在");
  return { before, current };
}

export class BundleCriteriaReader {
  private readonly members = new Map<string, Buffer>();
  private readonly artifactPaths = new Map<string, string>();
  private readonly source: BundleCriteriaSource;

  constructor(source: BundleCriteriaSource) {
    this.source = source;
    for (const member of source.members) this.members.set(member.path, member.body);
    for (const entry of source.closure.closure_entries ?? []) {
      const record = asRecord(entry);
      const ref = asRecord(record?.artifact_ref);
      if (!record || !ref) continue;
      const artifactId = ref.artifact_id;
      const logicalPath = record.logical_path;
      if (typeof artifactId === "string" && typeof logicalPath === "string" && !this.artifactPaths.has(artifactId)) {
        this.artifactPaths.set(artifactId, logicalPath);
      }
    }
  }

  hasMember(path: string): boolean {
    return this.members.has(path);
  }

  json<T>(path: string): T {
    const body = this.members.get(path);
    if (!body) fail(path, "tar 中缺少该成员");
    try {
      return JSON.parse(body.toString("utf8")) as T;
    } catch {
      fail(path, "不是 JSON 成员");
    }
  }

  pathOf(ref: unknown, where: string): string {
    const record = asRecord(ref);
    if (!record) fail(where, "引用不是 ArtifactRef");
    const artifactId = record.artifact_id;
    if (typeof artifactId !== "string") fail(where, "引用缺少 artifact_id");
    const path = this.artifactPaths.get(artifactId);
    if (!path) fail(where, `closure 未声明 artifact ${artifactId}`);
    const entry = (this.source.closure.closure_entries ?? []).find((candidate) => {
      const candidateRef = asRecord(asRecord(candidate)?.artifact_ref);
      return candidateRef?.artifact_id === artifactId;
    });
    const entryRef = asRecord(asRecord(entry)?.artifact_ref);
    if (entryRef && record.raw_sha256 !== undefined && record.raw_sha256 !== entryRef.raw_sha256) fail(where, "引用摘要与 closure 不一致");
    if (entryRef && record.size_bytes !== undefined && record.size_bytes !== entryRef.size_bytes) fail(where, "引用大小与 closure 不一致");
    if (!this.members.has(path)) fail(where, `tar 中缺少 artifact 成员 ${path}`);
    return path;
  }

  async parquet(path: string): Promise<ParquetRow[]> {
    const body = this.members.get(path);
    if (!body) fail(path, "tar 中缺少该成员");
    const file: AsyncBuffer = {
      byteLength: body.length,
      slice: async (start: number, end: number) => {
        const view = body.subarray(start, end);
        return view.buffer.slice(view.byteOffset, view.byteOffset + view.byteLength) as ArrayBuffer;
      },
    };
    return parquetReadObjects({ file, compressors });
  }
}

type NavigationSide = "before" | "current";

interface NavigationSideGroups {
  side: NavigationSide | null;
  groups: NavigationGroup[];
  where: string;
}

function collectSideGroups(navigation: NavigationDocument, mode: string, where: string): NavigationSideGroups[] {
  if (mode === "DATASET_REPLACEMENT") {
    if ((navigation.groups ?? []).length !== 0) fail(where, "替换模式导航不应含普通 groups");
    const sides = asRecord(navigation.replacement_sides);
    if (!sides) fail(where, "替换模式导航缺少 replacement_sides");
    return (["before", "current"] as const).map((side) => {
      const groups = sides[side];
      if (!Array.isArray(groups)) fail(where, `替换模式导航缺少 ${side} 侧分组`);
      return { side, groups: groups as NavigationGroup[], where: `${where} ${side} 侧` };
    });
  }
  const groups = navigation.groups ?? [];
  if (groups.length !== FIXED_GROUPS.length || groups.some((group, index) => group.group_key !== FIXED_GROUPS[index])) {
    fail(where, `普通模式导航组不是固定的五组顺序（实际 ${groups.map((group) => group.group_key).join(",")}）`);
  }
  return [{ side: null, groups, where }];
}

function checkNavigationShape(navigation: NavigationDocument, surface: ComparisonSurface, where: string): NavigationTab[] {
  if (navigation.contract_version !== NAVIGATION_CONTRACT_VERSION) {
    fail(where, `导航 contract version 不是 ${NAVIGATION_CONTRACT_VERSION}`);
  }
  const tableIds = new Set((surface.tables ?? []).map((table) => table.table_id));
  const tabs: NavigationTab[] = [];
  for (const { side, groups, where: sideWhere } of collectSideGroups(navigation, String(surface.comparison_mode ?? ""), where)) {
    const groupKeys = new Set<string>();
    const itemKeys = new Set<string>();
    const wholeByTable = new Map<string, string>();
    const filterGroupByTable = new Map<string, string>();
    for (const group of groups) {
      if (typeof group.group_key !== "string") fail(sideWhere, "导航组缺少 group_key");
      if (groupKeys.has(group.group_key)) fail(sideWhere, `导航组重复：${group.group_key}`);
      groupKeys.add(group.group_key);
      for (const item of group.items ?? []) {
        if (typeof item.item_key !== "string") fail(sideWhere, "导航项缺少 item_key");
        if (itemKeys.has(item.item_key)) fail(sideWhere, `导航项重复：${item.item_key}`);
        itemKeys.add(item.item_key);
        const tabKeys = new Set<string>();
        for (const tab of item.tabs ?? []) {
          if (typeof tab.tab_key !== "string") fail(sideWhere, "页签缺少 tab_key");
          if (tabKeys.has(tab.tab_key)) fail(sideWhere, `导航项 ${item.item_key} 的页签重复：${tab.tab_key}`);
          tabKeys.add(tab.tab_key);
          if (typeof tab.table_id !== "string" || !tableIds.has(tab.table_id)) fail(sideWhere, `页签 ${tab.tab_key} 引用了 surface 中不存在的表 ${String(tab.table_id)}`);
          const rowFilter = decodeRowFilter(tab.row_filter, `${sideWhere} 页签 ${tab.tab_key}`);
          if (rowFilter === null) {
            if (wholeByTable.has(tab.table_id)) fail(sideWhere, `表 ${tab.table_id} 有多个整表页签`);
            if (filterGroupByTable.has(tab.table_id)) fail(sideWhere, `表 ${tab.table_id} 的整表页签与筛选页签并存`);
            wholeByTable.set(tab.table_id, tab.tab_key);
          } else {
            if (wholeByTable.has(tab.table_id)) fail(sideWhere, `表 ${tab.table_id} 的整表页签与筛选页签并存`);
            const previous = filterGroupByTable.get(tab.table_id);
            if (previous !== undefined && previous !== group.group_key) fail(sideWhere, `表 ${tab.table_id} 的筛选页签跨组`);
            filterGroupByTable.set(tab.table_id, group.group_key);
          }
          tabs.push(side ? { ...tab, side } : tab);
        }
      }
    }
  }
  return tabs;
}

function tabsOnSide(tab: NavigationTab, side: NavigationSide): boolean {
  return tab.side === undefined || tab.side === side;
}

function referencedTableIds(tabs: NavigationTab[]): Set<string> {
  const referenced = new Set<string>();
  for (const tab of tabs) if (typeof tab.table_id === "string") referenced.add(tab.table_id);
  return referenced;
}

function rowCountOf(table: SurfaceTable, side: "before" | "current"): number | null {
  const binding = table.table_content_bindings?.[side];
  if (!binding) return null;
  const count = binding.row_count;
  if (count === null || count === undefined) return null;
  return typeof count === "number" && Number.isSafeInteger(count) && count >= 0 ? count : fail(`表 ${table.table_id}`, `${side} 行数无效`);
}

function diagnosticsFor(
  diagnostics: NavigationDiagnostic[],
  code: string,
  tableId: string,
  side: "before" | "current",
): number {
  let total = 0;
  for (const diagnostic of diagnostics) {
    if (diagnostic.code !== code) continue;
    if (diagnostic.target?.table_id !== tableId) continue;
    if (String(diagnostic.side ?? "").toUpperCase() !== side.toUpperCase()) continue;
    const count = diagnostic.params?.row_count;
    if (typeof count !== "number" || !Number.isSafeInteger(count) || count < 0) fail(`表 ${tableId}`, `${code} 诊断的 row_count 无效`);
    total += count;
  }
  return total;
}

async function checkCoverage(
  reader: BundleCriteriaReader,
  pairId: string,
  table: SurfaceTable,
  filterTabsBySide: Record<NavigationSide, NavigationTab[]>,
  diagnostics: NavigationDiagnostic[],
  where: string,
): Promise<number> {
  let checked = 0;
  for (const side of ["before", "current"] as const) {
    const filterTabs = filterTabsBySide[side];
    if (filterTabs.length === 0) continue;
    const binding = table.table_content_bindings?.[side];
    if (!binding) continue;
    const rowCount = rowCountOf(table, side);
    if (rowCount === null) continue;
    if (!filterTabs.every((tab) => tab.facts?.basis === "EXACT")) continue;
    const tableRef = table.table_refs?.[`${side}_table_ref`] ?? null;
    if (!tableRef) fail(where, `${side} 有行数绑定但缺少快照引用`);
    const path = reader.pathOf(tableRef, `${where}.${side}_table_ref`);
    const rows = await reader.parquet(path);
    if (rows.length !== rowCount) fail(where, `${side} 快照行数 ${rows.length} 与绑定 ${rowCount} 不一致`);
    const covered = new Set<number>();
    for (const tab of filterTabs) {
      const predicate = decodeRowFilter(tab.row_filter, `${where} 页签 ${tab.tab_key}`)?.[side] ?? null;
      if (!predicate) continue;
      rows.forEach((row, index) => {
        if (compareValues(row, predicate.column, predicate)) covered.add(index);
      });
    }
    const orphans = diagnosticsFor(diagnostics, "DEVICE_ROWS_UNASSIGNED", table.table_id, side);
    if (covered.size + orphans !== rowCount) {
      fail(
        where,
        `${side} 覆盖 ${covered.size} + 孤儿 ${orphans} 不等于行数 ${rowCount}（pair ${pairId}，表 ${table.table_id}）`,
      );
    }
    checked += 1;
  }
  return checked;
}

async function checkLocations(
  reader: BundleCriteriaReader,
  table: SurfaceTable,
  beforeHasFilterTab: boolean,
  currentHasFilterTab: boolean,
  where: string,
): Promise<{ tableLocated: boolean; rows: number }> {
  const recordsRef = table.records_refs?.records_ref ?? null;
  const ordinary: Array<{ identity: string; kind: string }> = [];
  if (recordsRef) {
    const path = reader.pathOf(recordsRef, `${where}.records_ref`);
    for (const row of await reader.parquet(path)) {
      const kind = String(row.record_kind ?? "");
      if (!STANDARD_ORDINARY_KINDS.has(kind)) continue;
      ordinary.push({ identity: identityHex(row.row_identity), kind });
    }
  }
  const locatorRef = table.row_locator_ref ?? null;
  if (ordinary.length > 0 && !locatorRef) fail(where, "有已发布的 STANDARD 普通行记录但缺少 row_locator_ref（不允许表级回退）");
  if (!locatorRef) return { tableLocated: false, rows: 0 };
  const path = reader.pathOf(locatorRef, `${where}.row_locator_ref`);
  const rows = await reader.parquet(path);
  const located = new Map<string, { before: number | null; current: number | null; beforeContext: Record<string, unknown> | null; currentContext: Record<string, unknown> | null }>();
  let previousIdentity: Buffer | null = null;
  rows.forEach((row, rowIndex) => {
    const identity = identityHex(row.row_identity);
    const raw = row.row_identity instanceof Uint8Array ? Buffer.from(row.row_identity) : Buffer.from(new Uint8Array(row.row_identity as ArrayBuffer));
    if (previousIdentity && Buffer.compare(previousIdentity, raw) >= 0) fail(where, `locator 行身份未严格升序（第 ${rowIndex} 行）`);
    previousIdentity = raw;
    if (located.has(identity)) fail(where, `locator 行身份重复：${identity}`);
    located.set(identity, {
      before: indexValue(row.before_row_index, `${where} ${identity}.before_row_index`),
      current: indexValue(row.current_row_index, `${where} ${identity}.current_row_index`),
      beforeContext: contextDocument(row.before_filter_context_json, `${where} ${identity}.before_filter_context_json`),
      currentContext: contextDocument(row.current_filter_context_json, `${where} ${identity}.current_filter_context_json`),
    });
  });
  if (located.size !== ordinary.length) fail(where, `locator 行数 ${located.size} 与普通行记录数 ${ordinary.length} 不一致`);
  const anyFilterTab = beforeHasFilterTab || currentHasFilterTab;
  const beforeCount = rowCountOf(table, "before");
  const currentCount = rowCountOf(table, "current");
  const beforeIndexes = new Set<number>();
  const currentIndexes = new Set<number>();
  for (const record of ordinary) {
    const entry = located.get(record.identity);
    if (!entry) fail(where, `缺少行定位：${record.identity}`);
    const beforeExists = record.kind !== "ROW_ADDED";
    const currentExists = record.kind !== "ROW_DELETED";
    const checkSide = (
      side: "before" | "current",
      exists: boolean,
      index: number | null,
      context: Record<string, unknown> | null,
      count: number | null,
      seen: Set<number>,
    ): void => {
      const label = `${where} ${record.identity}.${side}`;
      if (!exists) {
        if (index !== null) fail(label, "逻辑不存在的侧却有行下标");
        if (context !== null) fail(label, "逻辑不存在的侧却有过滤上下文");
        return;
      }
      if (count !== null) {
        if (index === null) fail(label, "有快照的一侧缺少行下标");
        if (index >= count) fail(label, `行下标 ${index} 超出该侧行数 ${count}`);
        if (context !== null) fail(label, "有快照的一侧不应带过滤上下文");
        if (seen.has(index)) fail(label, `行下标 ${index} 被多条定位命中`);
        seen.add(index);
      } else {
        if (index !== null) fail(label, "缺少快照的一侧却给出了行下标");
        const hasFilterTab = side === "before" ? beforeHasFilterTab : currentHasFilterTab;
        if (hasFilterTab && context === null) fail(label, "缺少快照且有筛选页签时过滤上下文不能为空");
        if (!hasFilterTab && context !== null) fail(label, "整表入口不应带过滤上下文");
      }
    };
    checkSide("before", beforeExists, entry.before, entry.beforeContext, beforeCount, beforeIndexes);
    checkSide("current", currentExists, entry.current, entry.currentContext, currentCount, currentIndexes);
    if (!anyFilterTab && (entry.beforeContext !== null || entry.currentContext !== null)) fail(where, "整表入口不应带过滤上下文");
  }
  return { tableLocated: true, rows: located.size };
}

/** Runs criteria 1–4 for every pair in a verified bundle and returns per-pair totals. */
export async function assertBundleConsumerCriteria(
  source: BundleCriteriaSource,
  context: string,
): Promise<BundleCriteriaSummary> {
  const reader = new BundleCriteriaReader(source);
  const manifestPath = "manifest.json";
  if (!reader.hasMember(manifestPath)) fail(context, "bundle 缺少 manifest.json");
  const manifest = reader.json<{ pairs?: Array<{ pair_id?: unknown }> }>(manifestPath);
  const pairIds = (manifest.pairs ?? [])
    .map((pair) => pair.pair_id)
    .filter((pairId): pairId is string => typeof pairId === "string");
  if (pairIds.length === 0) fail(context, "bundle manifest 没有比较对");
  const summaries: PairCriteriaSummary[] = [];
  for (const pairId of pairIds) {
    const where = `${context} 比较对 ${pairId}`;
    const surfacePath = `pairs/${pairId}/comparison-surface.json`;
    if (!reader.hasMember(surfacePath)) fail(where, "缺少 comparison-surface.json");
    const surface = reader.json<ComparisonSurface>(surfacePath);
    if (surface.surface_contract_version !== SURFACE_CONTRACT_VERSION) fail(where, "surface contract version 不是 v4");
    const tables = surface.tables ?? [];
    const ids = new Set<string>();
    for (const table of tables) {
      if (typeof table.table_id !== "string") fail(where, "surface 表缺少 table_id");
      if (ids.has(table.table_id)) fail(where, `surface 表重复：${table.table_id}`);
      ids.add(table.table_id);
    }
    const navigationProjections = (surface.projections ?? []).filter((projection) => projection.projection_kind === "BUSINESS_NAVIGATION");
    if (navigationProjections.length !== 1) fail(where, `必须恰有一个 BUSINESS_NAVIGATION projection（实际 ${navigationProjections.length}）`);
    const navigationPath = reader.pathOf(navigationProjections[0].projection_ref, `${where}.navigation`);
    const navigation = reader.json<NavigationDocument>(navigationPath);
    let diagnostics: NavigationDiagnostic[] = [];
    if (navigationProjections[0].diagnostics_ref) {
      const diagnosticsPath = reader.pathOf(navigationProjections[0].diagnostics_ref, `${where}.navigation_diagnostics`);
      diagnostics = reader.json<{ diagnostics?: NavigationDiagnostic[] }>(diagnosticsPath).diagnostics ?? [];
    }
    const tabs = checkNavigationShape(navigation, surface, where);
    const referenced = referencedTableIds(tabs);
    const fallbackTabs = tabs.filter((tab) => tab.facts?.basis === "TABLE_FALLBACK");
    const fallbackTables = new Set(fallbackTabs.map((tab) => tab.table_id));
    let unreferenced = 0;
    for (const table of tables) {
      if (referenced.has(table.table_id)) continue;
      unreferenced += 1;
      // A null binding means the bundle carries no snapshot for that side;
      // kickoff §5.3 only requires zero rows for sides with a binding.
      if ((rowCountOf(table, "before") ?? 0) !== 0 || (rowCountOf(table, "current") ?? 0) !== 0) fail(where, `未引用表 ${table.table_id} 的行数不为 0`);
      if (table.change_kind !== "UNCHANGED" && table.change_kind !== "BUSINESS_EQUIVALENT") fail(where, `未引用表 ${table.table_id} 的变化类型为 ${String(table.change_kind)}`);
      if (table.risk_refs?.risk_level !== null && table.risk_refs?.risk_level !== undefined) fail(where, `未引用表 ${table.table_id} 带有风险`);
      if (table.risk_refs?.annotation_count !== 0 && table.risk_refs?.annotation_count !== undefined) fail(where, `未引用表 ${table.table_id} 带有风险注释`);
    }
    let coveredFilterSides = 0;
    let locatedTables = 0;
    let locatedRows = 0;
    for (const table of tables) {
      const tableTabs = tabs.filter((tab) => tab.table_id === table.table_id && tab.row_filter !== null);
      const filterTabsBySide = {
        before: tableTabs.filter((tab) => tabsOnSide(tab, "before")),
        current: tableTabs.filter((tab) => tabsOnSide(tab, "current")),
      };
      if (filterTabsBySide.before.length > 0 || filterTabsBySide.current.length > 0) {
        coveredFilterSides += await checkCoverage(reader, pairId, table, filterTabsBySide, diagnostics, `${where} 表 ${table.table_id}`);
      }
      const located = await checkLocations(reader, table, filterTabsBySide.before.length > 0, filterTabsBySide.current.length > 0, `${where} 表 ${table.table_id}`);
      if (located.tableLocated) locatedTables += 1;
      locatedRows += located.rows;
    }
    summaries.push({
      pair_id: pairId,
      mode: String(surface.comparison_mode ?? ""),
      table_count: tables.length,
      navigation_tab_count: tabs.length,
      fallback_tab_count: fallbackTabs.length,
      fallback_table_count: fallbackTables.size,
      located_table_count: locatedTables,
      located_row_count: locatedRows,
      covered_filter_sides: coveredFilterSides,
      unreferenced_table_count: unreferenced,
    });
  }
  return { pair_ids: pairIds, pairs: summaries };
}

export function formatCriteriaSummary(summary: BundleCriteriaSummary): string {
  return summary.pairs
    .map(
      (pair) =>
        `${pair.pair_id}[tabs=${pair.navigation_tab_count},fallbackTabs=${pair.fallback_tab_count},fallbackTables=${pair.fallback_table_count},locatedTables=${pair.located_table_count},locatedRows=${pair.located_row_count},filterSides=${pair.covered_filter_sides}]`,
    )
    .join(" ");
}
