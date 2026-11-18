import {
  DataEditor,
  GridCellKind,
  type DataEditorRef,
  type GridCell,
  type GridColumn,
  type Theme,
} from "@glideapps/glide-data-grid";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ComponentProps,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { RiskBadge } from "../../design-system/components";
import { createTableTheme } from "../../design-system/theme";
import type { RiskAnnotation, SurfaceTable } from "../../features/view-model/model";
import { describeRiskReason } from "../../features/view-model/risk-copy";
import {
  columnHeaderTitle,
  missingSideMarker,
  normalizeDisplayScalar,
  rowMove,
  rowRiskAnnotation,
  type BrowseRow,
  type ChangeLocation,
} from "../../features/view-model/table-rows";
import { rowLabel } from "./view-copy";
import {
  COLUMN_FIT_MAX,
  COLUMN_MIN,
  createTextMeasure,
  fitWidth,
  hasDeletedAppearance,
  HOVER_FIELD_LIMIT,
  riskTokens,
  sampleRows,
  type SizedGridColumn,
} from "./view-helpers";

export function GridTable({
  rows,
  table,
  tabKey,
  annotations,
  debug,
  highlighted,
  storedWidths,
  onWidthChange,
  onVisibleRows,
  onExpand,
  onOpenFormula,
}: {
  rows: BrowseRow[];
  table: SurfaceTable;
  tabKey: string;
  annotations: RiskAnnotation[];
  debug: boolean;
  highlighted: ChangeLocation | null;
  storedWidths: Readonly<Record<string, number>>;
  onWidthChange: (columnId: string, width: number) => void;
  onVisibleRows: (range: { start: number; end: number }) => void;
  onExpand: (row: BrowseRow) => void;
  onOpenFormula: (pointKey: string | null) => void;
}) {
  const gridRef = useRef<DataEditorRef>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  // The hover detail follows the pointer and flips to stay inside the viewport.
  const hoverDetailRef = useRef<HTMLDivElement>(null);
  const pointer = useRef<{ x: number; y: number } | null>(null);
  const placeHoverDetail = useCallback(() => {
    const element = hoverDetailRef.current;
    const at = pointer.current;
    if (!element || !at) return;
    const gap = 14;
    const margin = 8;
    const width = element.offsetWidth;
    const height = element.offsetHeight;
    const left = at.x + gap + width > window.innerWidth - margin ? at.x - gap - width : at.x + gap;
    const top =
      at.y + gap + height > window.innerHeight - margin ? at.y - gap - height : at.y + gap;
    element.style.left =
      Math.max(margin, Math.min(left, window.innerWidth - margin - width)) + "px";
    element.style.top =
      Math.max(margin, Math.min(top, window.innerHeight - margin - height)) + "px";
  }, []);
  const trackPointer = useCallback(
    (event: ReactMouseEvent) => {
      pointer.current = { x: event.clientX, y: event.clientY };
      placeHoverDetail();
    },
    [placeHoverDetail],
  );
  useLayoutEffect(() => {
    placeHoverDetail();
  });
  const [frameSize, setFrameSize] = useState({ width: 0, height: 0 });
  const [paintedToken, setPaintedToken] = useState<object | null>(null);
  const [hoveredCell, setHoveredCell] = useState<readonly [number, number] | null>(null);
  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    // The grid fills the frame, which takes the remaining height of the page.
    const measure = () =>
      setFrameSize((previous) =>
        previous.width === frame.clientWidth && previous.height === frame.clientHeight
          ? previous
          : { width: frame.clientWidth, height: frame.clientHeight },
      );
    const observer = new ResizeObserver(measure);
    observer.observe(frame);
    measure();
    return () => observer.disconnect();
  }, []);
  const orderedColumns = useMemo(
    () =>
      [...(table.columns ?? [])].sort((left, right) => left.display_order - right.display_order),
    [table.columns],
  );
  const pinnedColumnCount = useMemo(() => {
    let count = 0;
    for (const column of orderedColumns) {
      if (!column.pinned) break;
      count += 1;
    }
    return count;
  }, [orderedColumns]);
  const metaColumnCount = debug ? 5 : 2;
  const frozenColumnCount = metaColumnCount + pinnedColumnCount;
  const theme = useMemo(() => createTableTheme(), []);
  const measureCell = useMemo(
    () => createTextMeasure(`${theme.baseFontStyle} ${theme.fontFamily}`),
    [theme.baseFontStyle, theme.fontFamily],
  );
  const measureHeader = useMemo(
    () => createTextMeasure(`${theme.headerFontStyle} ${theme.fontFamily}`),
    [theme.headerFontStyle, theme.fontFamily],
  );
  // Text the grid shows for a sizable column (row labels for 变更, values otherwise).
  const columnText = useCallback(
    (row: BrowseRow, columnId: string): string =>
      columnId === "__diff"
        ? rowLabel(row)
        : row.kind === "collapsed"
          ? ""
          : normalizeDisplayScalar(
              row.values[columnId],
              orderedColumns.find((column) => column.name === columnId),
            ),
    [orderedColumns],
  );
  const fitColumn = useCallback(
    (columnId: string, title: string, sourceRows: readonly BrowseRow[], mode: "auto" | "fit") =>
      fitWidth(
        measureHeader(title),
        sourceRows.map((row) => measureCell(columnText(row, columnId))),
        mode,
      ),
    [columnText, measureCell, measureHeader],
  );
  // Automatic widths are worked out once per table view (when its rows first
  // arrive), so expanding runs or toggling the scope does not shift columns.
  const autoWidthKey = `${table.table_name}|${tabKey}|${debug ? "debug" : "user"}|${rows.length > 0 ? "rows" : "empty"}`;
  const autoWidths = useMemo(() => {
    const sample = sampleRows(rows, 600);
    const widths = new Map<string, number>([
      ["__diff", fitColumn("__diff", "变更", sample, "auto")],
    ]);
    for (const column of orderedColumns)
      widths.set(
        column.name,
        fitColumn(column.name, columnHeaderTitle(column, debug), sample, "auto"),
      );
    return widths;
    // Keyed on the table view, not on rows: later row changes must not move columns.
  }, [autoWidthKey, fitColumn, orderedColumns]);
  const columns = useMemo<SizedGridColumn[]>(() => {
    const width = (id: string, fallback: number) =>
      storedWidths[id] ?? autoWidths.get(id) ?? fallback;
    const meta: SizedGridColumn[] = [
      { id: "__number", title: "#", width: 60 },
      { id: "__diff", title: "变更", width: width("__diff", 150) },
    ];
    if (debug)
      meta.push(
        { id: "__kind", title: "Diff Kind", width: width("__kind", 210) },
        { id: "__role", title: "Row Role", width: width("__role", 84) },
        { id: "__semantic", title: "Ordered Semantic / Position", width: width("__semantic", 260) },
      );
    return [
      ...meta,
      ...orderedColumns.map((column) => ({
        id: column.name,
        title: columnHeaderTitle(column, debug),
        width: width(column.name, 120),
      })),
    ];
  }, [autoWidths, debug, orderedColumns, storedWidths]);
  const resizeColumn = useCallback(
    (column: GridColumn, newSize: number) => {
      if (typeof column.id === "string" && column.id !== "__number")
        onWidthChange(column.id, Math.round(newSize));
    },
    [onWidthChange],
  );
  // Double-clicking a header's right edge fits the column to its longest value.
  // Glide does not report clicks on header edges (its own fit needs a
  // selection reader we do not provide), so the edge under the pointer is
  // tracked from mouse moves and the frame's native double-click fits it.
  const edgeColumn = useRef<number | null>(null);
  const fitEdgeColumn = useCallback(() => {
    const column = edgeColumn.current === null ? undefined : columns[edgeColumn.current];
    if (!column || typeof column.id !== "string" || column.id === "__number") return;
    onWidthChange(
      column.id,
      fitColumn(column.id, String(column.title), sampleRows(rows, 5000), "fit"),
    );
  }, [columns, fitColumn, onWidthChange, rows]);
  const paintToken = useMemo(() => ({}), [columns, rows]);
  const rendered = paintedToken === paintToken;
  const markPainted = useCallback(() => {
    setPaintedToken((previous) => (previous === paintToken ? previous : paintToken));
  }, [paintToken]);
  useEffect(() => {
    if (rows.length !== 0) return;
    let secondFrame = 0;
    const firstFrame = requestAnimationFrame(() => {
      secondFrame = requestAnimationFrame(markPainted);
    });
    return () => {
      cancelAnimationFrame(firstFrame);
      if (secondFrame) cancelAnimationFrame(secondFrame);
    };
  }, [markPainted, rows.length]);
  const formulaColumnIndex = columns.findIndex((column) => column.id === "formula_ast_json");
  const formulaColumnOffset =
    formulaColumnIndex < 0
      ? undefined
      : columns.slice(0, formulaColumnIndex).reduce((width, column) => width + column.width, 0);
  const formulaColumnWidth =
    formulaColumnIndex < 0 ? undefined : columns[formulaColumnIndex]?.width;
  // The row position is a ruler, not data: smaller, lighter, on the header tone.
  const numberTheme = useMemo<Partial<Theme>>(
    () => ({ textDark: "#8B95A1", bgCell: theme.bgHeader, baseFontStyle: "12px" }),
    [theme.bgHeader],
  );
  const pairRows = useMemo(() => {
    const result = new Map<string, number[]>();
    rows.forEach((row, index) => {
      if (row.pairKey) result.set(row.pairKey, [...(result.get(row.pairKey) ?? []), index]);
    });
    return result;
  }, [rows]);
  // A pair shares one identity: both halves highlight; a blank-interval summary is found by its row key.
  const isHighlighted = useCallback(
    (row: BrowseRow) =>
      highlighted !== null &&
      (highlighted.rowIdentity !== null
        ? row.rowIdentity === highlighted.rowIdentity
        : row.key === highlighted.rowKey),
    [highlighted],
  );
  useEffect(() => {
    if (!highlighted) return;
    const row = rows.findIndex(isHighlighted);
    if (row >= 0) gridRef.current?.scrollTo(1, row, "vertical", 0, 0, { vAlign: "center" });
  }, [highlighted, isHighlighted, rows]);
  const getCellContent = useCallback(
    ([columnIndex, rowIndex]: readonly [number, number]): GridCell => {
      const row = rows[rowIndex];
      const column = columns[columnIndex];
      if (!row || !column || typeof column.id !== "string")
        return { kind: GridCellKind.Loading, allowOverlay: false };
      const columnId = column.id;
      const pair = row.pairKey ? pairRows.get(row.pairKey) : undefined;
      const detached = pair && (pair.length !== 2 || Math.abs((pair[0] ?? 0) - (pair[1] ?? 0)) > 1);
      const beforePairRow = pair
        ?.map((index) => rows[index])
        .find((candidate) => candidate?.kind === "modified-before");
      const formulaChanged =
        row.kind === "modified-after" &&
        (beforePairRow
          ? beforePairRow.values.formula_digest !== row.values.formula_digest
          : row.formulaChanged === true);
      const columnShape = orderedColumns.find((item) => item.name === columnId);
      let value: unknown;
      if (columnId === "__number") value = row.rowNumber ?? "";
      else if (columnId === "__diff")
        value = row.kind === "collapsed" ? rowLabel(row) : rowLabel(row) + (detached ? " ↔" : "");
      else if (columnId === "__kind") value = row.recordKind ?? "—";
      else if (columnId === "__role")
        value = row.kind === "modified-before" ? "前" : row.kind === "modified-after" ? "后" : "—";
      else if (columnId === "__semantic")
        value = row.semanticKind
          ? row.semanticKind +
            " · " +
            (row.beforePosition ?? "—") +
            " → " +
            (row.currentPosition ?? "—")
          : "—";
      else if (columnId === "formula_ast_json" && table.table_name === "composite_signal_point") {
        value = "查看公式" + (formulaChanged ? " · 公式已改" : "");
      } else {
        value =
          missingSideMarker(row.side, columnShape?.present_in) ??
          (row.partialValues && !Object.hasOwn(row.values, columnId)
            ? "不可得"
            : row.values[columnId]);
      }
      const risk = row.riskLevel ? riskTokens(row.riskLevel) : null;
      const changed = row.changedColumns.includes(columnId);
      const boldStyle =
        row.kind === "modified-after" && changed ? `600 ${theme.baseFontStyle}` : undefined;
      const cellTheme = risk
        ? {
            bgCell: changed ? risk.cell : risk.bg,
            textDark:
              row.kind === "modified-before" || hasDeletedAppearance(row) ? "#535D69" : risk.text,
            ...(boldStyle ? { baseFontStyle: boldStyle } : {}),
          }
        : changed
          ? {
              bgCell: "#E6E9ED",
              textDark: "#1B2229",
              ...(boldStyle ? { baseFontStyle: boldStyle } : {}),
            }
          : undefined;
      return {
        kind: GridCellKind.Text,
        data: normalizeDisplayScalar(value, columnShape),
        displayData: normalizeDisplayScalar(value, columnShape),
        allowOverlay: false,
        style: row.kind === "modified-before" || hasDeletedAppearance(row) ? "faded" : "normal",
        ...(columnId === "__number" ? { contentAlign: "right" as const } : {}),
        themeOverride: columnId === "__number" ? numberTheme : cellTheme,
      };
    },
    [columns, numberTheme, orderedColumns, pairRows, rows, table.table_name, theme.baseFontStyle],
  );
  const getRowThemeOverride = useCallback(
    (row: number): Partial<Theme> | undefined => {
      const value = rows[row];
      if (!value?.riskLevel) return undefined;
      const risk = riskTokens(value.riskLevel);
      return { bgCell: risk.bg, textDark: risk.text };
    },
    [rows],
  );
  const drawCell = useCallback(
    (
      args: Parameters<NonNullable<ComponentProps<typeof DataEditor>["drawCell"]>>[0],
      drawContent: () => void,
    ) => {
      drawContent();
      if (args.col === 0 && args.row === 0) markPainted();
      const row = rows[args.row];
      if (!row) return;
      if (args.col === 0 && row.riskLevel) {
        args.ctx.fillStyle = riskTokens(row.riskLevel).rail;
        args.ctx.fillRect(args.rect.x, args.rect.y, 4, args.rect.height);
      }
      if (args.col === 1 && row.pairKey) {
        const pair = pairRows.get(row.pairKey) ?? [];
        const at = pair.indexOf(args.row);
        if (pair.length === 2 && Math.abs((pair[0] ?? 0) - (pair[1] ?? 0)) === 1) {
          args.ctx.strokeStyle = "#68798A";
          args.ctx.lineWidth = 1.5;
          args.ctx.beginPath();
          const x = args.rect.x + 14;
          const center = args.rect.y + args.rect.height / 2;
          args.ctx.moveTo(x, at === 0 ? center : args.rect.y);
          args.ctx.lineTo(x, at === 0 ? args.rect.y + args.rect.height : center);
          args.ctx.stroke();
        }
      }
      if (hasDeletedAppearance(row) && args.col >= (debug ? 5 : 2)) {
        args.ctx.strokeStyle = "#535D69";
        args.ctx.lineWidth = 1;
        args.ctx.beginPath();
        const y = args.rect.y + args.rect.height / 2;
        args.ctx.moveTo(args.rect.x + 8, y);
        args.ctx.lineTo(args.rect.x + args.rect.width - 8, y);
        args.ctx.stroke();
      }
      if (isHighlighted(row)) {
        args.ctx.strokeStyle = "#1F5FBF";
        args.ctx.lineWidth = 1;
        args.ctx.beginPath();
        args.ctx.moveTo(args.rect.x, args.rect.y + 0.5);
        args.ctx.lineTo(args.rect.x + args.rect.width, args.rect.y + 0.5);
        args.ctx.moveTo(args.rect.x, args.rect.y + args.rect.height - 0.5);
        args.ctx.lineTo(args.rect.x + args.rect.width, args.rect.y + args.rect.height - 0.5);
        if (args.col === 0) {
          args.ctx.moveTo(args.rect.x + 0.5, args.rect.y);
          args.ctx.lineTo(args.rect.x + 0.5, args.rect.y + args.rect.height);
        }
        if (args.col === columns.length - 1) {
          args.ctx.moveTo(args.rect.x + args.rect.width - 0.5, args.rect.y);
          args.ctx.lineTo(args.rect.x + args.rect.width - 0.5, args.rect.y + args.rect.height);
        }
        args.ctx.stroke();
      }
    },
    [columns.length, debug, isHighlighted, markPainted, pairRows, rows],
  );
  // A single click on an unchanged-run row toggles it; Enter/Space (activation)
  // toggles too, but the activation that follows a double click is ignored.
  const lastToggleClick = useRef(0);
  const click = useCallback(
    ([column, row]: readonly [number, number]) => {
      const target = rows[row];
      if (target?.kind === "collapsed") {
        lastToggleClick.current = Date.now();
        onExpand(target);
        return;
      }
      // Formulas are keyed by source_table:point_gid, the same pair the row carries.
      if (
        table.table_name === "composite_signal_point" &&
        columns[column]?.id === "formula_ast_json"
      ) {
        const values = target?.values ?? {};
        onOpenFormula(
          values.source_table === undefined || values.point_gid === undefined
            ? null
            : `${String(values.source_table ?? "")}:${String(values.point_gid ?? "")}`,
        );
      }
    },
    [columns, onExpand, onOpenFormula, rows, table.table_name],
  );
  const activate = useCallback(
    ([, row]: readonly [number, number]) => {
      const target = rows[row];
      if (target?.kind === "collapsed" && Date.now() - lastToggleClick.current > 600)
        onExpand(target);
    },
    [onExpand, rows],
  );
  const onMouseMove = useCallback(
    (event: Parameters<NonNullable<ComponentProps<typeof DataEditor>["onMouseMove"]>>[0]) => {
      const next = event.kind === "cell" ? event.location : null;
      setHoveredCell((previous) =>
        previous?.[0] === next?.[0] && previous?.[1] === next?.[1] ? previous : next,
      );
      edgeColumn.current = event.kind === "header" && event.isEdge ? event.location[0] : null;
    },
    [],
  );
  const onVisibleRegionChanged = useCallback(
    (range: { y: number; height: number }) => {
      const first = rows[Math.max(0, Math.min(rows.length - 1, range.y))];
      const last = rows[Math.max(0, Math.min(rows.length - 1, range.y + range.height - 1))];
      if (!first || !last) return;
      // The navigator and the grid share the physical ruler; business `no` may be sparse.
      const start = first.ruler ?? 1;
      const end = (last.expanded ? null : last.collapsedRows?.at(-1)?.ruler) ?? last.ruler ?? start;
      markPainted();
      onVisibleRows({ start, end });
    },
    [markPainted, onVisibleRows, rows],
  );
  const hoverRow = hoveredCell ? rows[hoveredCell[1]] : undefined;
  const hoverColumn = hoveredCell ? columns[hoveredCell[0]] : undefined;
  const hoverPair = hoverRow?.pairKey ? pairRows.get(hoverRow.pairKey) : undefined;
  const hoverBefore =
    hoverPair?.length === 2
      ? rows[hoverPair.find((index) => rows[index]?.kind === "modified-before") ?? -1]
      : undefined;
  const hoverAfter =
    hoverPair?.length === 2
      ? rows[hoverPair.find((index) => rows[index]?.kind === "modified-after") ?? -1]
      : undefined;
  const hoverColumnId = typeof hoverColumn?.id === "string" ? hoverColumn.id : null;
  // Every changed field of the hovered modified row, the hovered column first.
  const hoverFields = useMemo(() => {
    if (!hoverRow || !hoverBefore || !hoverAfter || !hoverRow.changedColumns.length) return [];
    const order = new Map(orderedColumns.map((column, index) => [column.name, index]));
    return [...hoverRow.changedColumns]
      .sort(
        (left, right) =>
          Number(right === hoverColumnId) - Number(left === hoverColumnId) ||
          (order.get(left) ?? Number.MAX_SAFE_INTEGER) -
            (order.get(right) ?? Number.MAX_SAFE_INTEGER),
      )
      .map((name) => ({ name, shape: orderedColumns.find((column) => column.name === name) }));
  }, [hoverAfter, hoverBefore, hoverColumnId, hoverRow, orderedColumns]);
  const hoverChanged = hoverFields.length > 0;
  const hoverAnnotation = hoverRow ? rowRiskAnnotation(hoverRow, annotations) : undefined;
  const hoverMove = hoverRow && hoverRow.kind !== "collapsed" ? rowMove(hoverRow) : null;
  const showHoverDetail = Boolean(hoverRow && (hoverChanged || hoverRow.riskLevel || hoverMove));
  const firstColumn = table.columns?.[0];
  const firstCellContent =
    rows[0] && firstColumn ? normalizeDisplayScalar(rows[0].values[firstColumn.name]) : "空表";
  return (
    <div
      ref={frameRef}
      className="grid-frame"
      aria-label="比较表格"
      onDoubleClick={fitEdgeColumn}
      onMouseMove={trackPointer}
      data-tab-key={tabKey}
      data-rendered={rendered ? "true" : "false"}
      data-first-cell-content={firstCellContent}
      data-formula-column-offset={formulaColumnOffset}
      data-formula-column-width={formulaColumnWidth}
    >
      <DataEditor
        ref={gridRef}
        columns={columns}
        rows={rows.length}
        getCellContent={getCellContent}
        getRowThemeOverride={getRowThemeOverride}
        drawCell={drawCell}
        onCellClicked={click}
        onCellActivated={activate}
        onColumnResize={resizeColumn}
        minColumnWidth={COLUMN_MIN}
        maxColumnWidth={COLUMN_FIT_MAX}
        onMouseMove={onMouseMove}
        onVisibleRegionChanged={onVisibleRegionChanged}
        headerHeight={34}
        rowHeight={34}
        theme={theme}
        width="100%"
        height={Math.max(240, frameSize.height)}
        smoothScrollX
        smoothScrollY
        verticalBorder={false}
        freezeColumns={frozenColumnCount}
      />
      {showHoverDetail && hoverRow && (
        <div ref={hoverDetailRef} className="grid-hover-detail" role="tooltip">
          {hoverChanged && hoverBefore && hoverAfter && (
            <section>
              <strong>
                字段变更{hoverFields.length > 1 ? " · " + hoverFields.length + " 列" : ""}
              </strong>
              {hoverFields.slice(0, HOVER_FIELD_LIMIT).map(({ name, shape }) => (
                <div key={name} className={name === hoverColumnId ? "is-hovered" : undefined}>
                  <span>{shape?.display_name || name}</span>
                  <code>{normalizeDisplayScalar(hoverBefore.values[name], shape)}</code>
                  <span aria-hidden="true">→</span>
                  <code className="grid-hover-detail__new">
                    {normalizeDisplayScalar(hoverAfter.values[name], shape)}
                  </code>
                </div>
              ))}
              {hoverFields.length > HOVER_FIELD_LIMIT && (
                <small>另有 {hoverFields.length - HOVER_FIELD_LIMIT} 列</small>
              )}
            </section>
          )}
          {hoverMove && (
            <section>
              <strong>位置</strong>
              <span>
                第 {hoverMove.from} 行 → 第 {hoverMove.to} 行
              </span>
            </section>
          )}
          {hoverRow.riskLevel && (
            <section className="grid-hover-detail__risk">
              <strong>
                风险信息 <RiskBadge level={hoverRow.riskLevel} />
              </strong>
              {hoverAnnotation?.reasons.map((reason) => (
                <span
                  key={reason.reason_code + reason.rule_id}
                  title={
                    debug
                      ? `reason_code=${reason.reason_code} · rule_id=${reason.rule_id}`
                      : undefined
                  }
                >
                  {describeRiskReason(reason.reason_code, reason.evidence)}
                  {debug && (
                    <code>
                      {reason.reason_code} · {reason.rule_id}
                    </code>
                  )}
                </span>
              ))}
              <small>原始规则编码在 Debug 模式中查看</small>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
