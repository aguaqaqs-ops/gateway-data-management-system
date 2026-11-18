import { useCallback, useState } from "react";
import type { InstalledBundle } from "../../features/bundle/local-bundle";
import { parseRowLocator } from "../../features/view-model/table-rows";
import { readParquetTable } from "../../features/bundle/parquet-reader";
import {
  readLocalChangeRecords,
  readLocalTable,
  type LocalComparisonPresentation,
} from "../../features/bundle/presentation";
import type { BrowseState } from "../../features/view-model/commands";
import {
  deriveFormulaDisplays,
  normalizeRowIdentity,
  type FormulaDisplay,
} from "../../features/view-model/model";
import { recordValues } from "./view-helpers";

export function useFormulaPanel(options: {
  bundle: InstalledBundle | null;
  presentation: LocalComparisonPresentation | null;
  browseMode: BrowseState["mode"];
}) {
  const { bundle, presentation, browseMode } = options;
  const [formulaOpen, setFormulaOpen] = useState(false);
  const [formulas, setFormulas] = useState<FormulaDisplay[]>([]);
  const [formulaFocus, setFormulaFocus] = useState<string | null>(null);

  const openFormula = useCallback(
    async (pointKey: string | null) => {
      if (!bundle || !presentation) return;
      const composite = presentation.surface.tables.find(
        (item) => item.table_name === "composite_signal_point",
      );
      if (!composite) return;
      const compositeLocatorPath =
        presentation.tableArtifacts.get(composite.table_name)?.rowLocator ?? null;
      const locatorRows = compositeLocatorPath
        ? await readParquetTable(bundle, compositeLocatorPath, {
            columns: [
              "row_identity",
              "before_row_index",
              "current_row_index",
              "before_filter_context_json",
              "current_filter_context_json",
            ],
          })
        : [];
      const compositeLocator = parseRowLocator(locatorRows as Record<string, unknown>[]);
      const [before, current, beforeDevices, currentDevices] = await Promise.all([
        presentation.tableArtifacts.get(composite.table_name)?.before
          ? readLocalTable(bundle, presentation, composite.table_name, "before")
          : Promise.resolve([]),
        presentation.tableArtifacts.get(composite.table_name)?.current
          ? readLocalTable(bundle, presentation, composite.table_name, "current")
          : Promise.resolve([]),
        presentation.tableArtifacts.get("device")?.before
          ? readLocalTable(bundle, presentation, "device", "before")
          : Promise.resolve([]),
        presentation.tableArtifacts.get("device")?.current
          ? readLocalTable(bundle, presentation, "device", "current")
          : Promise.resolve([]),
      ]);
      const beforeRows = [...(before as Record<string, unknown>[])];
      const currentRows = current as Record<string, unknown>[];
      const records = await readLocalChangeRecords(bundle, presentation, composite.table_name);
      const hasBeforeSnapshot = Boolean(
        presentation.tableArtifacts.get(composite.table_name)?.before,
      );
      const deletedPointKeys = new Set<string>();
      for (const record of records) {
        const recordKind = String(record.record_kind ?? "");
        const values = recordValues(record.before_values);
        if (recordKind === "ROW_DELETED") {
          if (typeof values.source_table !== "string" || values.point_gid === undefined) continue;
          beforeRows.push(values);
          deletedPointKeys.add(`${values.source_table}:${String(values.point_gid)}`);
          continue;
        }
        if (
          browseMode === "HISTORY" ||
          hasBeforeSnapshot ||
          !["ROW_MODIFIED", "ORDERED_ROW_MODIFIED"].includes(recordKind) ||
          !("formula_digest" in values)
        )
          continue;
        const recordIdentity = normalizeRowIdentity(
          (record.current_row_identity ?? record.row_identity) as never,
        );
        const locatedIndex = recordIdentity
          ? (compositeLocator.get(recordIdentity)?.currentRowIndex ?? null)
          : null;
        const currentRow = locatedIndex === null ? undefined : currentRows[locatedIndex];
        if (!currentRow) continue;
        beforeRows.push({ ...currentRow, ...values, formula_ast_json: null });
      }
      setFormulas(
        deriveFormulaDisplays({
          mode: browseMode === "HISTORY" ? "HISTORY" : "PREVIEW",
          before: beforeRows,
          current: currentRows,
          beforeDevices: beforeDevices as Record<string, unknown>[],
          currentDevices: currentDevices as Record<string, unknown>[],
          deletedPointKeys,
        }),
      );
      setFormulaFocus(pointKey);
      setFormulaOpen(true);
    },
    [browseMode, bundle, presentation],
  );

  return {
    formulaOpen,
    setFormulaOpen,
    formulas,
    formulaFocus,
    setFormulaFocus,
    openFormula,
  };
}
