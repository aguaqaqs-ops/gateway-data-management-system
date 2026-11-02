import { describe, expect, it } from "vitest";
import { loadComparisonPresentation, readLocalChangeRecords, readLocalRiskAnnotations, readLocalTable } from "../bundle/presentation";
import { installedFixtureBundle, installedGoldenBundle } from "../../test/helpers";
import { normalizeRowIdentity } from "./model";
import { buildBrowseRows, snapshotRowIdentity } from "./table-rows";

describe("table row presentation", () => {
  it("matches keyless duplicate occurrences to their backend add and delete records", async () => {
    const { bundle, manifest } = await installedFixtureBundle("preview-full");
    const pair = manifest.pairs.find((value) => (value as { pair_id: string }).pair_id === "baseline_to_initial") as { pair_id: string };
    const presentation = await loadComparisonPresentation(bundle, pair.pair_id);
    const surface = presentation.surface.tables.find((item) => item.table_name === "keyless_demo");
    if (!surface) throw new Error("backend fixture has no keyless_demo surface");
    const [current, records, annotations] = await Promise.all([
      readLocalTable(bundle, presentation, "keyless_demo", "current") as Promise<Record<string, unknown>[]>,
      readLocalChangeRecords(bundle, presentation, "keyless_demo"),
      readLocalRiskAnnotations(bundle, presentation, "keyless_demo"),
    ]);
    const rows = buildBrowseRows({ table: surface, beforeRows: [], currentRows: current, records, annotations });
    expect(rows.filter((row) => row.kind === "added" || row.kind === "deleted").map((row) => row.kind).sort()).toEqual(["added", "deleted"]);
  });

  it("maps supported row risk levels without changing the fixture target", async () => {
    const { bundle, manifest } = await installedGoldenBundle();
    const pairId = (manifest.pairs[0] as { pair_id: string }).pair_id;
    const presentation = await loadComparisonPresentation(bundle, pairId);
    const surface = presentation.surface.tables.find((item) => item.table_name === "device");
    if (!surface) throw new Error("backend fixture has no device surface");
    const [current, records, annotations] = await Promise.all([
      readLocalTable(bundle, presentation, "device", "current") as Promise<Record<string, unknown>[]>,
      readLocalChangeRecords(bundle, presentation, "device"),
      readLocalRiskAnnotations(bundle, presentation, "device"),
    ]);
    const source = annotations.find((annotation) => annotation.target.target_type === "ROW");
    if (!source) throw new Error("backend fixture has no row annotation");
    const sourceIdentity = [source.target.row_identity, source.target.before_row_identity, source.target.current_row_identity]
      .map((identity) => normalizeRowIdentity(identity ?? undefined))
      .find((identity): identity is string => Boolean(identity));
    if (!sourceIdentity) throw new Error("backend fixture row annotation has no row identity");
    const fixtureRows = buildBrowseRows({ table: surface, beforeRows: [], currentRows: current, records, annotations });
    if (!fixtureRows.some((row) => row.rowIdentity === sourceIdentity)) throw new Error("backend row annotation does not resolve to a fixture row");
    for (const level of ["LOW", "HIGH", "UNKNOWN"] as const) {
      const annotation = { ...source, risk_level: level };
      const result = buildBrowseRows({ table: surface, beforeRows: [], currentRows: current, records,
        annotations: [annotation], onlyInteresting: true });
      expect(result.find((row) => row.rowIdentity === sourceIdentity)?.riskLevel).toBe(level);
    }
  });

  it("keeps a renderer-assigned risk on an unchanged row outside collapsed runs", async () => {
    const { bundle, manifest } = await installedGoldenBundle();
    const pairId = (manifest.pairs[0] as { pair_id: string }).pair_id;
    const presentation = await loadComparisonPresentation(bundle, pairId);
    const surface = presentation.surface.tables.find((item) => item.table_name === "device");
    if (!surface) throw new Error("backend fixture has no device surface");
    const [current, records, annotations] = await Promise.all([
      readLocalTable(bundle, presentation, "device", "current") as Promise<Record<string, unknown>[]>,
      readLocalChangeRecords(bundle, presentation, "device"),
      readLocalRiskAnnotations(bundle, presentation, "device"),
    ]);
    const source = annotations.find((annotation) => annotation.target.target_type === "ROW");
    const currentRow = current.find((row) => {
      const identity = normalizeRowIdentity(snapshotRowIdentity(row, surface) ?? undefined);
      return Boolean(identity && !records.some((record) => normalizeRowIdentity(record.row_identity) === identity
        && ["ROW_ADDED", "ROW_MODIFIED", "ORDERED_ROW_ADDED", "ORDERED_ROW_MODIFIED", "ORDERED_ROW_MOVED"].includes(String(record.record_kind))));
    });
    if (!source || !currentRow) throw new Error("backend fixture lacks source annotation or unchanged device row");
    const identity = normalizeRowIdentity(snapshotRowIdentity(currentRow, surface) ?? undefined);
    if (!identity) throw new Error("fixture unchanged row has no identity");
    const annotation = { ...source, target: { ...source.target, row_identity: identity, before_row_identity: identity, current_row_identity: identity } };
    const result = buildBrowseRows({ table: surface, beforeRows: [], currentRows: current, records,
      annotations: [annotation], onlyInteresting: true });
    const row = result.find((value) => value.rowIdentity === identity);
    expect(row?.kind).toBe("unchanged");
    expect(row?.riskLevel).toBe(source.risk_level);
  });

  it("places ordered records and blank intervals at their backend positions", async () => {
    const { bundle, manifest } = await installedFixtureBundle("preview-full");
    const pair = manifest.pairs.find((value) => (value as { pair_id: string }).pair_id === "baseline_to_initial") as { pair_id: string };
    const presentation = await loadComparisonPresentation(bundle, pair.pair_id);
    const surface = presentation.surface.tables.find((item) => item.table_name === "b1_n1_iec104_syx_list");
    if (!surface) throw new Error("backend fixture has no ordered table surface");
    const [current, records, annotations] = await Promise.all([
      readLocalTable(bundle, presentation, surface.table_name, "current") as Promise<Record<string, unknown>[]>,
      readLocalChangeRecords(bundle, presentation, surface.table_name),
      readLocalRiskAnnotations(bundle, presentation, surface.table_name),
    ]);
    const rows = buildBrowseRows({ table: surface, beforeRows: [], currentRows: current, records, annotations });
    const moved = rows.find((row) => row.recordKind === "ORDERED_ROW_MOVED");
    const blankRecord = records.find((record) => String(record.record_kind).startsWith("BLANK_"));
    const blank = rows.find((row) => row.recordKind === blankRecord?.record_kind);
    const interval = blankRecord?.interval && typeof blankRecord.interval === "object" ? blankRecord.interval as Record<string, unknown> : {};
    const backendPosition = typeof blankRecord?.before_position === "number" ? blankRecord.before_position : interval.before_start;
    expect(moved?.kind).toBe("ordered");
    expect(moved?.semanticKind).toBeTruthy();
    expect(moved?.beforePosition).toEqual(expect.any(Number));
    expect(moved?.currentPosition).toEqual(expect.any(Number));
    expect(blank?.kind).toBe("blank");
    expect(blank?.rowNumber).toBe(backendPosition);
  });

  it("keeps modified rows paired and collapses only ordinary unchanged runs", async () => {
    const { bundle, manifest } = await installedGoldenBundle();
    const pairId = (manifest.pairs[0] as { pair_id: string }).pair_id;
    const presentation = await loadComparisonPresentation(bundle, pairId);
    const surface = presentation.surface.tables.find((item) => item.table_name === "device");
    if (!surface) throw new Error("backend fixture has no device surface");
    const [current, records, annotations] = await Promise.all([
      readLocalTable(bundle, presentation, "device", "current") as Promise<Record<string, unknown>[]>,
      readLocalChangeRecords(bundle, presentation, "device"),
      readLocalRiskAnnotations(bundle, presentation, "device"),
    ]);
    const result = buildBrowseRows({ table: surface, beforeRows: [], currentRows: current, records, annotations, onlyInteresting: true });
    expect(result.filter((row) => row.kind === "modified-before" || row.kind === "modified-after")).toHaveLength(2);
    expect(result.some((row) => row.kind === "collapsed")).toBe(true);
  });
});
