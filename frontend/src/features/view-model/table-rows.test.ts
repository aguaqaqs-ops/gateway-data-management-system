import { describe, expect, it } from "vitest";
import { installedFixtureBundle } from "../../test/helpers";
import { loadComparisonPresentation, readLocalChangeRecords, readLocalRiskAnnotations, readLocalTable } from "../bundle/presentation";
import { normalizeRowIdentity, type RiskAnnotation, type RowDiffRecord, type SurfaceTable } from "./model";
import { buildBrowseRows, displayRowSearchText, normalizeDisplayScalar, snapshotRowIdentity, type BrowseRow } from "./table-rows";

const FIXTURES = ["preview-full", "preview-modified-only", "preview-replacement", "preview-no-navigation", "history-three-nodes"];
const ADDED = new Set(["ROW_ADDED", "ORDERED_ROW_ADDED"]);
const DELETED = new Set(["ROW_DELETED", "ORDERED_ROW_DELETED"]);
const MODIFIED = new Set(["ROW_MODIFIED", "ORDERED_ROW_MODIFIED", "ORDERED_ROW_MOVED"]);

function recordIdentity(record: RowDiffRecord, side: "before" | "current"): string | null {
  const values = record as Record<string, unknown>;
  return normalizeRowIdentity((values[side === "before" ? "before_row_identity" : "current_row_identity"] ?? record.row_identity) as never);
}

function matchingIndexes(rows: Record<string, unknown>[], table: SurfaceTable, record: RowDiffRecord, side: "before" | "current"): number[] {
  const kind = String(record.record_kind ?? "");
  if (kind.startsWith("ORDERED_")) {
    const rawPosition = record[side === "before" ? "before_position" : "current_position"];
    const position = typeof rawPosition === "number" || typeof rawPosition === "bigint" || typeof rawPosition === "string" ? Number(rawPosition) : NaN;
    return Number.isSafeInteger(position) && position > 0 && position <= rows.length ? [position - 1] : [];
  }
  const identity = recordIdentity(record, side);
  if (!identity) return [];
  return rows.flatMap((row, index) => snapshotRowIdentity(row, table) === identity ? [index] : []);
}

async function loadTable(bundle: Awaited<ReturnType<typeof installedFixtureBundle>>["bundle"], presentation: Awaited<ReturnType<typeof loadComparisonPresentation>>, tableName: string) {
  const surface = presentation.surface.tables.find((table) => table.table_name === tableName);
  if (!surface) throw new Error(`fixture table not found: ${tableName}`);
  const paths = presentation.tableArtifacts.get(tableName);
  const [before, current, records, annotations] = await Promise.all([
    paths?.before ? readLocalTable(bundle, presentation, tableName, "before") as Promise<Record<string, unknown>[]> : Promise.resolve([]),
    paths?.current ? readLocalTable(bundle, presentation, tableName, "current") as Promise<Record<string, unknown>[]> : Promise.resolve([]),
    readLocalChangeRecords(bundle, presentation, tableName), readLocalRiskAnnotations(bundle, presentation, tableName),
  ]);
  return { surface, paths, before, current, records, annotations };
}

describe("table row presentation", () => {
  it("validates every fixture row record against each snapshot side and builds preview old-value rows", async () => {
    for (const fixtureName of FIXTURES) {
      const { bundle, manifest } = await installedFixtureBundle(fixtureName);
      for (const pairSummary of manifest.pairs) {
        const presentation = await loadComparisonPresentation(bundle, (pairSummary as { pair_id: string }).pair_id);
        for (const surface of presentation.surface.tables) {
          const source = await loadTable(bundle, presentation, surface.table_name);
          const rowRecords = source.records.filter((record) => ADDED.has(String(record.record_kind)) || DELETED.has(String(record.record_kind)) || MODIFIED.has(String(record.record_kind)));
          for (const [hasSnapshot, rows] of [[Boolean(source.paths?.before), source.before], [Boolean(source.paths?.current), source.current]] as const) {
            if (!hasSnapshot) continue;
            const identities = rows.map((row) => snapshotRowIdentity(row, source.surface)).filter((identity): identity is string => identity !== null);
            expect(new Set(identities).size, `${fixtureName}/${presentation.pairId}/${surface.table_name} duplicate identity`).toBe(identities.length);
          }
          for (const record of rowRecords) {
            const kind = String(record.record_kind);
            if (source.paths?.before && (DELETED.has(kind) || MODIFIED.has(kind))) {
              expect(matchingIndexes(source.before, source.surface, record, "before"), `${fixtureName}/${presentation.pairId}/${surface.table_name}/${kind} before`).toHaveLength(1);
            }
            if (source.paths?.current && (ADDED.has(kind) || MODIFIED.has(kind))) {
              expect(matchingIndexes(source.current, source.surface, record, "current"), `${fixtureName}/${presentation.pairId}/${surface.table_name}/${kind} current`).toHaveLength(1);
            }
          }
          const built = buildBrowseRows({ table: source.surface, beforeRows: source.before, currentRows: source.current,
            records: source.records, annotations: source.annotations, hasBeforeSnapshot: Boolean(source.paths?.before), hasCurrentSnapshot: Boolean(source.paths?.current) });
          expect(built.locationValid, `${fixtureName}/${presentation.pairId}/${surface.table_name}`).toBe(true);
          const deletedRows = built.rows.filter((row) => row.kind === "deleted");
          if (deletedRows.length > 0) {
            expect(built.rows.slice(-deletedRows.length)).toEqual(deletedRows);
            if (source.paths?.before) {
              expect(deletedRows.map((row) => row.rowNumber)).toEqual([...deletedRows.map((row) => row.rowNumber)].sort((left, right) => (left ?? 0) - (right ?? 0)));
            } else {
              expect(deletedRows.map((row) => row.rowIdentity)).toEqual(rowRecords.filter((record) => DELETED.has(String(record.record_kind))).map((record) => recordIdentity(record, "before")));
            }
          }
          for (const side of ["before", "current"] as const) {
            const hasSnapshot = side === "before" ? Boolean(source.paths?.before) : Boolean(source.paths?.current);
            if (!hasSnapshot) continue;
            const owners = new Map<number, number>();
            for (const record of rowRecords) {
              const kind = String(record.record_kind);
              const relevant = side === "before" ? DELETED.has(kind) || MODIFIED.has(kind) : ADDED.has(kind) || MODIFIED.has(kind);
              if (!relevant) continue;
              for (const rowIndex of matchingIndexes(side === "before" ? source.before : source.current, source.surface, record, side)) owners.set(rowIndex, (owners.get(rowIndex) ?? 0) + 1);
            }
            expect([...owners.values()].every((count) => count === 1)).toBe(true);
          }
          if (fixtureName.startsWith("preview") && !source.paths?.before) {
            const deletedRecords = rowRecords.filter((record) => DELETED.has(String(record.record_kind)));
            const modifiedRecords = rowRecords.filter((record) => MODIFIED.has(String(record.record_kind)));
            for (const record of deletedRecords) {
              const identity = recordIdentity(record, "before");
              const row = built.rows.find((candidate) => candidate.kind === "deleted" && candidate.rowIdentity === identity);
              expect(row?.rowNumber).toBeNull();
              expect(row?.rowNumberTitle).toBe("改前行号不在本 bundle 中");
              expect(row?.values).toEqual(expect.objectContaining(valuesAsObject(record.before_values)));
            }
            for (const record of modifiedRecords) {
              const identity = recordIdentity(record, "current");
              const orderedPosition = kind.startsWith("ORDERED_") ? Number(record.current_position) : null;
              const after = built.rows.find((candidate) => candidate.kind === "modified-after"
                && (orderedPosition !== null ? candidate.rowNumber === orderedPosition : candidate.rowIdentity === identity));
              const before = built.rows.find((candidate) => candidate.kind === "modified-before" && candidate.pairKey === after?.pairKey);
              expect(before?.rowNumber).toBeNull();
              expect(before?.rowNumberTitle).toBe("改前值不在本 bundle 中");
              for (const key of source.surface.compare?.compare_key_columns ?? []) expect(before?.values[key]).toEqual(after?.values[key]);
              for (const key of record.changed_columns ?? []) expect(before?.values[key]).toEqual(valuesAsObject(record.before_values)[key]);
              const populated = new Set([...(source.surface.compare?.compare_key_columns ?? []), ...(record.changed_columns ?? [])]);
              for (const column of source.surface.columns ?? []) if (!populated.has(column.name)) expect(before?.values).not.toHaveProperty(column.name);
            }
          }
        }
      }
    }
  });

  it("falls back to table-level location when one row record identity changes", async () => {
    const { bundle, manifest } = await installedFixtureBundle("history-three-nodes");
    const presentation = await loadComparisonPresentation(bundle, (manifest.pairs[0] as { pair_id: string }).pair_id);
    const source = await loadTable(bundle, presentation, "device");
    const index = source.records.findIndex((record) => MODIFIED.has(String(record.record_kind)));
    expect(index).toBeGreaterThanOrEqual(0);
    const changed = [...source.records];
    const original = changed[index];
    if (!original) throw new Error("missing device row record");
    changed[index] = { ...original, row_identity: `sha256:${"f".repeat(64)}`, before_row_identity: `sha256:${"f".repeat(64)}`, current_row_identity: `sha256:${"f".repeat(64)}` };
    const result = buildBrowseRows({ table: source.surface, beforeRows: source.before, currentRows: source.current,
      records: changed, annotations: source.annotations, hasBeforeSnapshot: true, hasCurrentSnapshot: true });
    expect(result.locationValid).toBe(false);
    expect(result.rows.every((row) => row.riskLevel === null && row.kind === "unchanged")).toBe(true);
  });

  it("maps an unrecorded ROW annotation to one unchanged row and falls back when that id is absent", async () => {
    const { bundle, manifest } = await installedFixtureBundle("history-three-nodes");
    const presentation = await loadComparisonPresentation(bundle, (manifest.pairs[0] as { pair_id: string }).pair_id);
    const source = await loadTable(bundle, presentation, "device");
    const recorded = new Set(source.records.map((record) => recordIdentity(record, "current")));
    const unchanged = source.current.find((row) => {
      const id = snapshotRowIdentity(row, source.surface);
      return Boolean(id && !recorded.has(id));
    });
    const sourceAnnotation = source.annotations.find((annotation) => annotation.target.target_type === "ROW");
    expect(unchanged).toBeTruthy();
    expect(sourceAnnotation).toBeTruthy();
    const identity = snapshotRowIdentity(unchanged ?? {}, source.surface);
    if (!identity || !sourceAnnotation) throw new Error("fixture has no unchanged row or ROW annotation");
    const annotation: RiskAnnotation = { ...sourceAnnotation, target: { ...sourceAnnotation.target, row_identity: identity, before_row_identity: identity, current_row_identity: identity } };
    const matched = buildBrowseRows({ table: source.surface, beforeRows: source.before, currentRows: source.current,
      records: source.records, annotations: [annotation], hasBeforeSnapshot: true, hasCurrentSnapshot: true });
    expect(matched.locationValid).toBe(true);
    expect(matched.rows.find((row) => row.rowIdentity === identity)?.riskLevel).toBe(annotation.risk_level);
    const modifiedRecord = source.records.find((record) => MODIFIED.has(String(record.record_kind)));
    if (!modifiedRecord) throw new Error("fixture has no modified row record");
    const beforeModifiedIdentity = recordIdentity(modifiedRecord, "before");
    const currentModifiedIdentity = recordIdentity(modifiedRecord, "current");
    if (!beforeModifiedIdentity || !currentModifiedIdentity) throw new Error("fixture modified row record has no side identities");
    const pairAnnotation: RiskAnnotation = { ...annotation, target: { ...annotation.target, target_type: "ROW_PAIR", row_identity: null,
      before_row_identity: beforeModifiedIdentity, current_row_identity: currentModifiedIdentity } };
    const paired = buildBrowseRows({ table: source.surface, beforeRows: source.before, currentRows: source.current,
      records: source.records, annotations: [pairAnnotation], hasBeforeSnapshot: true, hasCurrentSnapshot: true });
    const beforeModified = paired.rows.find((row) => row.kind === "modified-before" && row.rowIdentity === beforeModifiedIdentity);
    const afterModified = paired.rows.find((row) => row.kind === "modified-after" && row.rowIdentity === currentModifiedIdentity);
    expect(paired.locationValid).toBe(true);
    expect(beforeModified?.riskLevel).toBe(pairAnnotation.risk_level);
    expect(afterModified?.riskLevel).toBe(pairAnnotation.risk_level);
    const missing = { ...annotation, target: { ...annotation.target, row_identity: `sha256:${"e".repeat(64)}`, before_row_identity: `sha256:${"e".repeat(64)}`, current_row_identity: `sha256:${"e".repeat(64)}` } };
    const unmatched = buildBrowseRows({ table: source.surface, beforeRows: source.before, currentRows: source.current,
      records: source.records, annotations: [missing], hasBeforeSnapshot: true, hasCurrentSnapshot: true });
    expect(unmatched.locationValid).toBe(false);

    const beforeRecorded = new Set(source.records.map((record) => recordIdentity(record, "before")));
    const beforeUnchanged = source.before.find((row) => {
      const id = snapshotRowIdentity(row, source.surface);
      return Boolean(id && !beforeRecorded.has(id));
    });
    const beforeIdentity = snapshotRowIdentity(beforeUnchanged ?? {}, source.surface);
    if (!beforeIdentity) throw new Error("fixture has no unchanged before row");
    const beforeOnlyAnnotation: RiskAnnotation = { ...annotation, target: { ...annotation.target, row_identity: beforeIdentity, before_row_identity: beforeIdentity, current_row_identity: beforeIdentity } };
    const beforeOnly = buildBrowseRows({ table: source.surface, beforeRows: source.before, currentRows: [], records: [], annotations: [beforeOnlyAnnotation], hasBeforeSnapshot: true, hasCurrentSnapshot: false });
    expect(beforeOnly.locationValid).toBe(true);
    expect(beforeOnly.rows.find((row) => row.rowIdentity === beforeIdentity)?.riskLevel).toBe(beforeOnlyAnnotation.risk_level);
  });

  it("validates the whole table before applying a navigation row filter", async () => {
    const { bundle, manifest } = await installedFixtureBundle("preview-full");
    const presentation = await loadComparisonPresentation(bundle, (manifest.pairs[0] as { pair_id: string }).pair_id);
    const source = await loadTable(bundle, presentation, "device");
    const result = buildBrowseRows({ table: source.surface, beforeRows: source.before, currentRows: source.current,
      records: source.records, annotations: source.annotations, hasBeforeSnapshot: Boolean(source.paths?.before), hasCurrentSnapshot: Boolean(source.paths?.current),
      rowFilter: { column: "dev_addr", value: 1 } });
    expect(result.locationValid).toBe(true);
    expect(result.rows.every((row) => normalizeDisplayScalar(row.values.dev_addr) === "1")).toBe(true);
  });

  it("uses the added_table fixture as the sole owner of whole-table added rows", async () => {
    const { bundle, manifest } = await installedFixtureBundle("preview-full");
    const presentation = await loadComparisonPresentation(bundle, (manifest.pairs[1] as { pair_id: string }).pair_id);
    const source = await loadTable(bundle, presentation, "added_table");
    const result = buildBrowseRows({ table: source.surface, beforeRows: source.before, currentRows: source.current,
      records: source.records, annotations: source.annotations, hasBeforeSnapshot: Boolean(source.paths?.before), hasCurrentSnapshot: Boolean(source.paths?.current) });
    expect(result.rows).toHaveLength(source.current.length);
    expect(result.rows.every((row) => row.kind === "added")).toBe(true);
  });

  it("searches displayed cell values while excluding byte identities and binary values", () => {
    const table: SurfaceTable = {
      table_id: "binary_demo", table_name: "binary_demo", display_name: "二进制测试", table_status: "UNCHANGED",
      columns: [{ name: "identity", display_name: "标识", scalar_type: "VARBINARY(8)", nullable: false }, { name: "payload", display_name: "内容", scalar_type: "BLOB", nullable: true }],
      compare: { compare_key_columns: ["identity"] },
    };
    const source = { identity: Uint8Array.from([0x0c]), payload: Uint8Array.from([0x2e]) } as unknown as Record<string, unknown>;
    const result = buildBrowseRows({ table, beforeRows: [], currentRows: [source], records: [], annotations: [], hasCurrentSnapshot: true });
    expect(displayRowSearchText(result.rows[0] as BrowseRow, table.columns ?? [])).toBe("");
    expect(buildBrowseRows({ table, beforeRows: [], currentRows: [source], records: [], annotations: [], hasCurrentSnapshot: true, search: "12" }).rows).toEqual([]);
    expect(buildBrowseRows({ table, beforeRows: [], currentRows: [source], records: [], annotations: [], hasCurrentSnapshot: true, search: "二进制" }).rows).toEqual([]);
  });
});

function valuesAsObject(value: unknown): Record<string, unknown> {
  if (!Array.isArray(value)) return {};
  return Object.fromEntries(value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const rowValue = item as { column_name?: unknown; value?: unknown };
    return typeof rowValue.column_name === "string" ? [[rowValue.column_name, rowValue.value]] : [];
  }));
}
