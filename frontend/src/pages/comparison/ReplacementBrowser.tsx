import {
  DataEditor,
  GridCellKind,
  type GridCell,
  type GridColumn,
} from "@glideapps/glide-data-grid";
import { useCallback, useMemo } from "react";
import { createTableTheme } from "../../design-system/theme";
import { identityStatusText } from "../../features/view-model/identity-copy";
import type { SurfaceTable } from "../../features/view-model/model";
import { columnHeaderTitle, normalizeDisplayScalar } from "../../features/view-model/table-rows";
import { createTextMeasure, fitWidth, sampleRows } from "./view-helpers";

export function ReplacementBrowser({
  before,
  current,
  table,
  assessment,
  side,
  debug,
  onSelectSide,
}: {
  before: Record<string, unknown>[];
  current: Record<string, unknown>[];
  table: SurfaceTable;
  assessment?: Record<string, unknown>;
  side: "before" | "current" | null;
  debug: boolean;
  onSelectSide: (side: "before" | "current") => void;
}) {
  const summary =
    table.replacement_summary && typeof table.replacement_summary === "object"
      ? table.replacement_summary
      : {};
  const identityStatus = assessment?.status;
  const beforeSide =
    summary.before && typeof summary.before === "object"
      ? (summary.before as Record<string, unknown>)
      : {};
  const currentSide =
    summary.current && typeof summary.current === "object"
      ? (summary.current as Record<string, unknown>)
      : {};
  const beforeColumns = Array.isArray(beforeSide.columns)
    ? (beforeSide.columns as NonNullable<SurfaceTable["columns"]>)
    : (table.columns ?? []);
  const currentColumns = Array.isArray(currentSide.columns)
    ? (currentSide.columns as NonNullable<SurfaceTable["columns"]>)
    : (table.columns ?? []);
  const beforeTitle =
    typeof beforeSide.display_name === "string" && beforeSide.display_name
      ? beforeSide.display_name
      : "替换前";
  const currentTitle =
    typeof currentSide.display_name === "string" && currentSide.display_name
      ? currentSide.display_name
      : "替换后";
  return (
    <section className="replacement-browser">
      <div className="replacement-summary">
        <strong>数据集替换 · 双侧浏览</strong>
        <span className="replacement-status">身份结论：{identityStatusText(identityStatus)}</span>
        <div className="identity-pair-summary">
          <span>匹配条目：{String(assessment?.matched_entry_count ?? "—")}</span>
          <span>替换前：{String(assessment?.before_distinct_entry_count ?? "—")} 个身份条目</span>
          <span>替换后：{String(assessment?.current_distinct_entry_count ?? "—")} 个身份条目</span>
        </div>
        <div className="replacement-side-toggle" role="tablist" aria-label="替换侧">
          <button
            role="tab"
            aria-selected={side === "before"}
            className={side === "before" ? "is-active" : ""}
            onClick={() => onSelectSide("before")}
          >
            {beforeTitle}
          </button>
          <button
            role="tab"
            aria-selected={side === "current"}
            className={side === "current" ? "is-active" : ""}
            onClick={() => onSelectSide("current")}
          >
            {currentTitle}
          </button>
        </div>
        <small>
          {beforeTitle}：{before.length} 行 · {beforeColumns.length} 列
        </small>
        <small>
          {currentTitle}：{current.length} 行 · {currentColumns.length} 列
        </small>
      </div>
      <div className="replacement-sides">
        <ReplacementSide
          title={beforeTitle}
          rows={before}
          columns={beforeColumns}
          debug={debug}
          active={side === null || side === "before"}
        />
        <ReplacementSide
          title={currentTitle}
          rows={current}
          columns={currentColumns}
          debug={debug}
          active={side === null || side === "current"}
        />
      </div>
    </section>
  );
}

function ReplacementSide({
  title,
  rows,
  columns,
  debug,
  active,
}: {
  title: string;
  rows: Record<string, unknown>[];
  columns: NonNullable<SurfaceTable["columns"]>;
  debug: boolean;
  active: boolean;
}) {
  const theme = useMemo(() => createTableTheme(), []);
  const gridColumns = useMemo<GridColumn[]>(() => {
    const measureCell = createTextMeasure(`${theme.baseFontStyle} ${theme.fontFamily}`);
    const measureHeader = createTextMeasure(`${theme.headerFontStyle} ${theme.fontFamily}`);
    const sample = sampleRows(rows, 600);
    return columns.map((column) => {
      const title = columnHeaderTitle(column, debug);
      return {
        id: column.name,
        title,
        width: fitWidth(
          measureHeader(title),
          sample.map((row) => measureCell(normalizeDisplayScalar(row[column.name], column))),
          "auto",
        ),
      };
    });
  }, [columns, debug, rows, theme]);
  const getCellContent = useCallback(
    ([column, row]: readonly [number, number]): GridCell => {
      const key = gridColumns[column]?.id;
      const item = rows[row];
      if (!key || !item) return { kind: GridCellKind.Loading, allowOverlay: false };
      const value = normalizeDisplayScalar(item[key], columns[column]);
      return { kind: GridCellKind.Text, data: value, displayData: value, allowOverlay: false };
    },
    [columns, gridColumns, rows],
  );
  return (
    <section className={active ? "replacement-side" : "replacement-side is-inactive"}>
      <h3>
        {title} <small>{rows.length} 行</small>
      </h3>
      <div className="grid-frame">
        <DataEditor
          columns={gridColumns}
          rows={rows.length}
          getCellContent={getCellContent}
          rowMarkers={{ kind: "number", width: 44 }}
          headerHeight={34}
          rowHeight={34}
          theme={theme}
          width="100%"
          height={420}
          verticalBorder={false}
        />
      </div>
    </section>
  );
}
