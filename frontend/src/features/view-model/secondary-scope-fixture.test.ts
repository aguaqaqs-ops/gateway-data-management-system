import { describe, expect, it } from "vitest";
import { loadTableCase, type FixtureTableCase } from "../../test/helpers";
import { tabScope, type NavigationPredicate } from "./model";
import { itemChangeMark, scopeChangeMark } from "./scope-copy";
import { buildBrowseRows, canReuseUnrecordedIdentity, deriveChangeLocations, validateRowLocations } from "./table-rows";

/**
 * P3 consumer states against the real producer fixtures (archive
 * producer-fixtures-794dce0e, see src/test/fixtures/source/backend-provenance.json).
 */

function tab(table: FixtureTableCase, itemKey: string, tabKey: string) {
  const found = table.presentation.view.groups.flatMap((group) => group.items)
    .find((item) => item.itemKey === itemKey)?.tabs.find((entry) => entry.tabKey === tabKey);
  if (!found) throw new Error(`no tab ${itemKey}/${tabKey}`);
  return found;
}

function exactTable(table: FixtureTableCase): boolean {
  return table.filterTabs.length > 0 && table.filterTabs.every((entry) => entry.facts?.basis === "EXACT");
}

function browse(table: FixtureTableCase, extra: Partial<Parameters<typeof buildBrowseRows>[0]> = {}) {
  validateRowLocations({
    table: table.surfaceTable, locator: table.locator, records: table.tableRecords,
    beforeRowCount: table.beforeRows.length, currentRowCount: table.currentRows.length,
    hasBeforeSnapshot: table.hasBeforeSnapshot, hasCurrentSnapshot: table.hasCurrentSnapshot,
    publishesFilterTabs: table.filterTabs.length > 0, exactTable: exactTable(table),
  });
  return buildBrowseRows({
    table: table.surfaceTable, beforeRows: table.beforeRows, currentRows: table.currentRows,
    records: table.tableRecords, annotations: table.annotations, locator: table.locator,
    hasBeforeSnapshot: table.hasBeforeSnapshot, hasCurrentSnapshot: table.hasCurrentSnapshot,
    beforeEncodings: table.beforeEncodings, currentEncodings: table.currentEncodings,
    reuseUnrecordedBefore: canReuseUnrecordedIdentity(table.surfaceTable, table.filterTabs, table.hasBeforeSnapshot, table.hasCurrentSnapshot),
    ...extra,
  });
}

function predicates(table: FixtureTableCase, side: "before" | "current"): NavigationPredicate[] {
  return table.filterTabs.flatMap((entry) => {
    const predicate = entry.rowFilter?.[side];
    return predicate ? [predicate] : [];
  });
}

describe("pure row additions and deletions", () => {
  it("are EXACT with no risk, and show the deleted record's full before values including SQL NULL", async () => {
    const table = await loadTableCase("pure-row-changes", "device_st");
    const device = tab(table, "device:addr:49", "device_st");
    expect(tabScope(device)).toMatchObject({ kind: "LOCAL_EXACT", changeKind: "UPDATED", riskLevel: null, riskComplete: true,
      rowChanges: { added: 1, deleted: 1, modified: 0, moved_in: 0, moved_out: 0 } });
    expect(device.notice).toBeNull();
    expect(table.annotations).toEqual([]);
    expect(table.hasBeforeSnapshot).toBe(false);
    const { rows } = browse(table, { rowFilter: device.rowFilter });
    expect(rows.filter((row) => row.kind !== "unchanged").map((row) => row.kind).sort()).toEqual(["added", "deleted"]);
    const deleted = rows.find((row) => row.kind === "deleted")!;
    expect(deleted.partialValues).toBe(true);
    expect(deleted.identityContext).toEqual({ dev_addr: 49 });
    // Values come from record.before_values, so SQL NULL stays NULL instead of "unavailable".
    expect(Object.values(deleted.values).some((value) => (value as { kind?: unknown } | null)?.kind === "null")).toBe(true);
    expect(Object.keys(deleted.values).length).toBeGreaterThan(1);
    expect(rows.every((row) => row.riskLevel === null)).toBe(true);
  });
});

describe("ownership migration and registry definition changes", () => {
  it("assigns a migrated row to the old device by its before context and to the new one by its current value", async () => {
    const table = await loadTableCase("ownership", "device_st");
    const oldDevice = tab(table, "device:addr:49", "device_st");
    const newDevice = tab(table, "device:addr:50", "device_st");
    expect(tabScope(oldDevice)).toMatchObject({ changeKind: "DELETED", rowChanges: { modified: 1, moved_out: 1 } });
    expect(tabScope(newDevice)).toMatchObject({ changeKind: "ADDED", rowChanges: { added: 1, modified: 1, moved_in: 1 } });
    const old = browse(table, { rowFilter: oldDevice.rowFilter }).rows;
    expect(old.map((row) => row.kind)).toEqual(["modified-before", "modified-after"]);
    expect(old[0]?.identityContext).toEqual({ dev_addr: 49 });
    const moved = browse(table, { rowFilter: newDevice.rowFilter }).rows;
    expect(moved.filter((row) => row.kind === "modified-after")).toHaveLength(1);
    expect(moved.filter((row) => row.kind === "added")).toHaveLength(1);
    expect(old[0]?.rowIdentity).toBe(moved.find((row) => row.kind === "modified-before")?.rowIdentity);
  });

  it("shows migration and registry-only membership as neutral marks, never as created or deleted rows", async () => {
    const table = await loadTableCase("ownership", "device_st");
    const mark = (itemKey: string, tabKey: string) => scopeChangeMark(tabScope(tab(table, itemKey, tabKey)));
    // device_cfg of 49: membership_changed with all row counts zero, although change_kind is DELETED.
    expect(tab(table, "device:addr:49", "device_cfg").facts).toMatchObject({ change_kind: "DELETED", membership_changed: true,
      row_changes: { added: 0, deleted: 0, modified: 0, moved_in: 0, moved_out: 0 } });
    expect(mark("device:addr:49", "device_cfg")).toMatchObject({ kind: "marker", text: "归属变化" });
    expect(mark("device:addr:49", "device_st")).toMatchObject({ kind: "marker", text: "移出" });
    // Real content changes keep their badges.
    expect(mark("device:addr:50", "device_st")).toEqual({ kind: "badge", changeKind: "ADDED" });
    expect(mark("device:addr:51", "device_st")).toEqual({ kind: "badge", changeKind: "DELETED" });
    expect(mark("device:addr:51", "device_cfg")).toEqual({ kind: "badge", changeKind: "UPDATED" });
    const items = table.presentation.view.groups.flatMap((group) => group.items);
    const itemMark = (key: string) => { const item = items.find((entry) => entry.itemKey === key)!; return itemChangeMark(item, item.tabs.filter((entry) => !entry.empty).map(tabScope)); };
    expect(itemMark("device:addr:49")).toMatchObject({ kind: "marker", text: "迁移" });
    expect(itemMark("device:addr:50")).toBeNull();
    const pure = await loadTableCase("pure-row-changes", "device_st");
    expect(scopeChangeMark(tabScope(tab(pure, "device:addr:49", "device_st")))).toEqual({ kind: "badge", changeKind: "UPDATED" });
  });

  it("lists definition changes and the public name-update risk apart from every device", async () => {
    const table = await loadTableCase("ownership", "device_st");
    const view = table.presentation.view;
    expect(view.deviceDefinitionChanges.map((change) => [change.change_kind, change.before_item_key, change.current_item_key]))
      .toEqual([["DELETED", "device:addr:49", null], ["ADDED", null, "device:addr:50"]]);
    expect(view.tableNotices).toEqual([{ table_id: "device_st", table_scope: null, risk_complete: true,
      unlocated_row_risk: { risk_level: "LOW", count: null, reason_codes: ["STANDARD_NAME_UPDATE"] } }]);
    // The public LOW risk is attached to every device_st tab as a notice, never as the tab's own risk.
    const unaffected = tab(table, "device:addr:51", "device_st");
    expect(tabScope(unaffected).riskLevel).toBeNull();
    expect(unaffected.notice?.unlocated_row_risk?.risk_level).toBe("LOW");
  });

  it("browses unassigned rows per side without mixing the other side's orphans", async () => {
    const table = await loadTableCase("ownership", "device_st");
    const diagnostics = table.presentation.navigationDiagnostics.filter((item) => item.code === "DEVICE_ROWS_UNASSIGNED" && item.target.table_id === "device_st");
    const current = browse(table, { unassigned: { side: "current", predicates: predicates(table, "current") } }).scoped;
    const currentOrphans = new Set(current.filter((row) => row.side === "current").map((row) => row.key));
    expect(currentOrphans.size).toBe(diagnostics.find((item) => item.side === "CURRENT")?.params.row_count);
    const before = browse(table, { unassigned: { side: "before", predicates: predicates(table, "before") } }).scoped;
    const beforeOrphans = before.filter((row) => row.side === "before");
    // Without a before snapshot only rows with a before record/context can be browsed.
    expect(beforeOrphans.length).toBeGreaterThan(0);
    expect(beforeOrphans.length).toBeLessThanOrEqual(Number(diagnostics.find((item) => item.side === "BEFORE")?.params.row_count));
    const claimed = new Set(predicates(table, "before").flatMap((predicate) => predicate.values));
    for (const row of beforeOrphans) expect(claimed.has(row.identityContext?.dev_addr as number)).toBe(false);
  });
});

describe("exact local change beside incomplete risk", () => {
  it("keeps EXACT changes and known risk while the table's risk is published as incomplete", async () => {
    const incomplete = await loadTableCase("ownership-risk-incomplete", "device_st");
    const complete = await loadTableCase("ownership", "device_st");
    const device = tab(incomplete, "device:addr:49", "device_st");
    // The moved point changes dev_addr and name; v9 ignores the address and rates the name change LOW.
    expect(tabScope(device)).toMatchObject({ kind: "LOCAL_EXACT", changeKind: "DELETED", riskLevel: "LOW", riskComplete: false });
    expect(device.notice).toMatchObject({ table_id: "device_st", risk_complete: false });
    expect(incomplete.presentation.view.tableNotices.map((notice) => notice.table_id)).toEqual(["device_cfg", "device_st"]);
    expect(incomplete.presentation.navigationDiagnostics.filter((item) => item.code === "DEVICE_TAB_RISK_UNAVAILABLE").map((item) => item.target.table_id))
      .toEqual(["device_st", "device_cfg"]);
    // Incomplete risk does not block identity reuse or change the local rows.
    expect(canReuseUnrecordedIdentity(incomplete.surfaceTable, incomplete.filterTabs, incomplete.hasBeforeSnapshot, incomplete.hasCurrentSnapshot))
      .toBe(canReuseUnrecordedIdentity(complete.surfaceTable, complete.filterTabs, complete.hasBeforeSnapshot, complete.hasCurrentSnapshot));
    expect(browse(incomplete, { rowFilter: device.rowFilter }).rows.map((row) => row.kind))
      .toEqual(browse(complete, { rowFilter: tab(complete, "device:addr:49", "device_st").rowFilter }).rows.map((row) => row.kind));
  });
});

describe("actual blank delete interval", () => {
  it("shows one summary for the published interval with its own risk and invents no blank rows", async () => {
    const table = await loadTableCase("preview-full", "b1_n1_iec104_syx_list", "baseline_to_initial");
    const blanks = table.tableRecords.filter((record) => String(record.record_kind).startsWith("BLANK_"));
    expect(blanks).toHaveLength(1);
    const result = browse(table);
    const summaries = result.rows.filter((row) => row.kind === "blank-interval");
    expect(summaries.map((row) => row.interval)).toEqual([{ direction: "DELETE", before: [2, 4], current: [3, 3], rowCount: 1 }]);
    expect(summaries[0]?.riskLevel).toBe("MEDIUM_HIGH");
    const recordedAddsAndDeletes = table.tableRecords.filter((record) => /_(ADDED|DELETED)$/.test(String(record.record_kind))).length;
    expect(result.rows.filter((row) => row.kind === "added" || row.kind === "deleted")).toHaveLength(recordedAddsAndDeletes);
    expect(deriveChangeLocations(result.scoped).some((location) => location.recordKind === "BLANK_DELETE_INTERVAL")).toBe(true);
  });
});
