import { AlertTriangle, ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type {
  DeviceDefinitionChange,
  NavigationTableNotice,
  SurfaceTable,
  TabScope,
} from "../../features/view-model/model";
import { scopeChangeMark, type ScopeChangeMark } from "../../features/view-model/scope-copy";
import { SurfaceChangeBadge } from "../../features/view-model/table-state";
import { definitionChangeText, noticeLines, noticeReasonText, riskLevelText } from "./view-copy";

/** Change badge or neutral marker of a scope; migration and registry-only changes never show add/delete. */
export function ChangeMark({ mark }: { mark: ScopeChangeMark }) {
  if (mark.kind === "unknown")
    return (
      <span className="scope-marker scope-marker--unknown" title="本页签的逐行变化无法确定">
        变化未知
      </span>
    );
  if (mark.kind === "marker")
    return (
      <span className="scope-marker" title={mark.title}>
        {mark.text}
      </span>
    );
  return <SurfaceChangeBadge kind={mark.changeKind} />;
}

export function ScopeChangeBadge({ scope }: { scope: TabScope }) {
  return <ChangeMark mark={scopeChangeMark(scope)} />;
}

/** A sideways strip without a scrollbar: the wheel scrolls it and arrows appear at hidden edges. */
export function ScrollStrip({ children }: { children: ReactNode }) {
  const stripRef = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ left: false, right: false });
  useEffect(() => {
    const strip = stripRef.current;
    if (!strip) return;
    const update = () =>
      setEdges((previous) => {
        const left = strip.scrollLeft > 1;
        const right = strip.scrollLeft + strip.clientWidth < strip.scrollWidth - 1;
        return previous.left === left && previous.right === right ? previous : { left, right };
      });
    const wheel = (event: WheelEvent) => {
      if (
        strip.scrollWidth <= strip.clientWidth ||
        Math.abs(event.deltaY) <= Math.abs(event.deltaX)
      )
        return;
      strip.scrollLeft += event.deltaY;
      event.preventDefault();
    };
    update();
    strip.addEventListener("scroll", update);
    strip.addEventListener("wheel", wheel, { passive: false });
    const resize = new ResizeObserver(update);
    resize.observe(strip);
    const content = new MutationObserver(update);
    content.observe(strip, { childList: true, subtree: true });
    return () => {
      strip.removeEventListener("scroll", update);
      strip.removeEventListener("wheel", wheel);
      resize.disconnect();
      content.disconnect();
    };
  }, []);
  const scroll = (direction: -1 | 1) =>
    stripRef.current?.scrollBy({ left: direction * 280, behavior: "smooth" });
  return (
    <>
      {edges.left && (
        <button
          type="button"
          className="overflow-tabs__arrow"
          aria-label="向左查看页签"
          onClick={() => scroll(-1)}
        >
          <ChevronLeft size={15} />
        </button>
      )}
      <div ref={stripRef} className="overflow-tabs__visible">
        {children}
      </div>
      {edges.right && (
        <button
          type="button"
          className="overflow-tabs__arrow"
          aria-label="向右查看页签"
          onClick={() => scroll(1)}
        >
          <ChevronRight size={15} />
        </button>
      )}
    </>
  );
}

/** A small button in the table info line that opens its details over the grid. */
export function InfoPopover({
  label,
  tone,
  children,
}: {
  label: string;
  tone: "risk" | "warn";
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  return (
    <div ref={rootRef} className={`info-popover info-popover--${tone}`}>
      <button type="button" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <AlertTriangle size={13} aria-hidden="true" />
        {label}
        <ChevronDown size={13} aria-hidden="true" />
      </button>
      {open && (
        <div className="info-popover__panel" role="dialog" aria-label={label}>
          {children}
        </div>
      )}
    </div>
  );
}

/**
 * Public table facts and device-definition changes, listed independently of
 * device items so they stay reachable when empty tabs are hidden or only
 * differences are shown. Nothing here paints a device with personal risk.
 */
export function PublicNoticesPanel({
  notices,
  changes,
  tables,
  items,
  debug,
  onOpenWholeTable,
  onOpenItem,
}: {
  notices: readonly NavigationTableNotice[];
  changes: readonly DeviceDefinitionChange[];
  tables: readonly SurfaceTable[];
  items: ReadonlyMap<string, string>;
  debug: boolean;
  onOpenWholeTable: (tableName: string, itemKey?: string | null) => void;
  onOpenItem: (itemKey: string) => void;
}) {
  if (notices.length === 0 && changes.length === 0) return null;
  const tableLabel = (tableId: string) =>
    tables.find((table) => table.table_name === tableId)?.display_name || tableId;
  return (
    <section className="public-notices" aria-label="表公共提示与装置定义变化">
      {notices.length > 0 && (
        <details className="public-notices__section" open>
          <summary>
            表公共提示 <small>{notices.length}</small>
          </summary>
          {notices.map((notice) => (
            <div className="public-notice" key={notice.table_id} data-table-id={notice.table_id}>
              <button
                className="public-notice__title"
                onClick={() => onOpenWholeTable(notice.table_id)}
                title="打开整表"
              >
                {tableLabel(notice.table_id)}
              </button>
              {noticeLines(notice).map((line) => (
                <span key={line}>{line}</span>
              ))}
              {notice.unlocated_row_risk && notice.unlocated_row_risk.reason_codes.length > 0 && (
                <span className="public-notice__reasons">
                  {notice.unlocated_row_risk.reason_codes.map((code) => (
                    <span key={code}>
                      {noticeReasonText(code)}
                      {debug && <code>{code}</code>}
                    </span>
                  ))}
                </span>
              )}
            </div>
          ))}
        </details>
      )}
      {changes.length > 0 && (
        <details className="public-notices__section" open>
          <summary>
            装置定义变化 <small>{changes.length}</small>
          </summary>
          {changes.map((change) => (
            <div
              className="public-notice"
              key={change.record_identity}
              data-record-identity={change.record_identity}
            >
              <button
                className="public-notice__title"
                onClick={() => onOpenWholeTable("device")}
                title="在装置总表中查看"
              >
                {definitionChangeText(change)}
              </button>
              <span>
                {change.risk_level
                  ? "风险：" + riskLevelText(change.risk_level)
                  : change.risk_complete
                    ? "未生成风险标注"
                    : "风险信息不完整"}
                {change.risk_level && !change.risk_complete ? "（风险信息不完整）" : ""}
              </span>
              <span className="public-notice__links">
                {[change.before_item_key, change.current_item_key]
                  .filter(
                    (key, index, keys): key is string =>
                      key !== null && keys.indexOf(key) === index,
                  )
                  .map((key) => (
                    <button key={key} className="link-button" onClick={() => onOpenItem(key)}>
                      {items.get(key) ?? key}
                    </button>
                  ))}
              </span>
              {debug && <code>{change.record_identity}</code>}
            </div>
          ))}
        </details>
      )}
    </section>
  );
}
