import { ArrowDown, ArrowUp, Rows2, Rows4 } from "lucide-react";
import type {
  BrowseRow,
  ChangeLocation,
  DeletionLayout,
} from "../../features/view-model/table-rows";

export function ChangeNavigator({
  locations,
  riskRows,
  rowCount,
  visibleRows,
  currentIndex,
  onJump,
  deletionLayout,
  onDeletionLayout,
}: {
  locations: ChangeLocation[];
  riskRows: BrowseRow[];
  rowCount: number;
  visibleRows: { start: number; end: number };
  currentIndex: number;
  onJump: (index: number) => void;
  deletionLayout: DeletionLayout;
  onDeletionLayout: (layout: DeletionLayout) => void;
}) {
  if (!locations.length && !riskRows.length)
    return (
      <div className="change-navigator">
        <span title="没有行级变化">—</span>
      </div>
    );
  const grouped = deletionLayout === "group";
  const layoutTitle = grouped
    ? "删除与新增：合并显示（点击改为逐行交替）"
    : "删除与新增：逐行交替（点击改为合并显示）";
  const index = Math.min(currentIndex, Math.max(0, locations.length - 1));
  const range = Math.max(rowCount, 1);
  const toPercent = (position: number) =>
    Math.max(0, Math.min(100, ((position - 0.5) / range) * 100));
  const selectedPosition = locations[index]?.position ?? index + 1;
  const visibleStart = Math.max(1, visibleRows.start);
  const visibleEnd = Math.max(visibleStart, visibleRows.end);
  const visibleTop = toPercent(visibleStart);
  const visibleBottom = Math.min(100, (visibleEnd / range) * 100);
  return (
    <div className="change-navigator">
      <div className="change-navigator__controls">
        {locations.length ? (
          <>
            <span
              className="change-navigator__count"
              title={"第 " + (index + 1) + " 个变更，共 " + locations.length + " 个"}
            >
              <strong>{index + 1}</strong>
              <span>/{locations.length}</span>
            </span>
            <button
              aria-label="上一个变更"
              onClick={() => onJump(Math.max(0, index - 1))}
              disabled={index === 0}
            >
              <ArrowUp size={15} />
            </button>
            <button
              aria-label="下一个变更"
              onClick={() => onJump(Math.min(locations.length - 1, index + 1))}
              disabled={index === locations.length - 1}
            >
              <ArrowDown size={15} />
            </button>
          </>
        ) : (
          <span title="没有行级变化">—</span>
        )}
        <button
          className="change-navigator__layout"
          aria-label={layoutTitle}
          title={layoutTitle}
          aria-pressed={grouped}
          onClick={() => onDeletionLayout(grouped ? "interleave" : "group")}
        >
          {grouped ? <Rows2 size={15} /> : <Rows4 size={15} />}
        </button>
      </div>
      <div
        className="distribution-strip"
        role="group"
        aria-label={locations.length + " 个变更的位置分布"}
      >
        <span
          className="distribution-visible-range"
          aria-hidden="true"
          style={{ top: visibleTop + "%", height: Math.max(1, visibleBottom - visibleTop) + "%" }}
        />
        {riskRows.map((row) => (
          <span
            key={"risk:" + row.key}
            aria-label={"第 " + (row.rowNumber ?? "未知") + " 行风险"}
            className={
              "distribution-mark distribution-mark--risk-only distribution-mark--" +
              (row.riskLevel ?? "UNKNOWN").toLowerCase().replace("_", "-")
            }
            style={{ top: toPercent(row.ruler ?? 1) + "%" }}
          />
        ))}
        {locations.map((location, itemIndex) => {
          const position = location.position ?? itemIndex + 1;
          return (
            <button
              key={String(location.rowIdentity) + itemIndex}
              aria-label={"定位第 " + (itemIndex + 1) + " 个变更"}
              className={
                "distribution-mark" +
                (location.riskLevel
                  ? " distribution-mark--" + location.riskLevel.toLowerCase().replace("_", "-")
                  : "") +
                (itemIndex === index ? " is-current" : "")
              }
              style={{ top: toPercent(position) + "%" }}
              onClick={() => onJump(itemIndex)}
            />
          );
        })}
        {locations.length > 0 && (
          <span
            className="distribution-current-position"
            aria-hidden="true"
            style={{ top: toPercent(selectedPosition) + "%" }}
          />
        )}
      </div>
    </div>
  );
}
