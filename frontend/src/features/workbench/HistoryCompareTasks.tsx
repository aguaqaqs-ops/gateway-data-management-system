import { useCallback, useEffect, useRef, useState } from "react";
import { ListChecks, RefreshCw } from "lucide-react";
import type { components } from "../api/generated/openapi";
import type { GatewayApi } from "../api/client";
import { ApiError } from "../api/authenticated-fetch";

type Schemas = components["schemas"];
export type HistoryCompareTask = Schemas["HistoryCompareListItemResponse"];

const PAGE_SIZE = 50;
const STATUS_COPY: Record<HistoryCompareTask["status"], string> = {
  QUEUED: "排队中",
  RUNNING: "执行中",
  SUCCEEDED: "已完成",
  FAILED: "失败",
  CANCELLED: "已取消",
};
const STATUS_TONE: Record<HistoryCompareTask["status"], string> = {
  QUEUED: "info",
  RUNNING: "info",
  SUCCEEDED: "success",
  FAILED: "warning",
  CANCELLED: "neutral",
};

function time(iso: string | null): string {
  return iso
    ? new Date(iso).toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      })
    : "—";
}

/**
 * Server-owned list of this device/project's History compares: the way back to
 * a compare started in another tab or terminal. The browser keeps no copy.
 */
export function HistoryCompareTasks({
  api,
  currentOperationId,
  labelFor,
  onOpen,
}: {
  api: GatewayApi;
  currentOperationId: string | null;
  labelFor: (ref: Schemas["HistoryNodeRefResponse"]) => string;
  onOpen: (task: HistoryCompareTask) => void;
}) {
  const [items, setItems] = useState<HistoryCompareTask[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const requestRef = useRef<AbortController | null>(null);

  const load = useCallback(
    async (after: string | null) => {
      requestRef.current?.abort();
      const controller = new AbortController();
      requestRef.current = controller;
      setLoading(true);
      setError(null);
      try {
        const page = await api.listHistoryCompares({ limit: PAGE_SIZE, after }, controller.signal);
        if (controller.signal.aborted) return;
        setItems((current) =>
          after
            ? [
                ...current,
                ...page.items.filter(
                  (item) => !current.some((known) => known.operation_id === item.operation_id),
                ),
              ]
            : page.items,
        );
        setNextCursor(page.next_cursor);
      } catch (cause) {
        if (controller.signal.aborted) return;
        if (after && cause instanceof ApiError && cause.status === 422) {
          // The cursor no longer matches this scope: start again from the first page.
          void load(null);
          return;
        }
        setError(
          cause instanceof ApiError && (cause.status === 403 || cause.code === "SCOPE_FORBIDDEN")
            ? "当前身份没有历史比较权限"
            : cause instanceof Error
              ? cause.message
              : String(cause),
        );
      } finally {
        if (requestRef.current === controller) setLoading(false);
      }
    },
    [api],
  );

  // Re-read when the compare shown on the page changes, so its status is current.
  useEffect(() => {
    void load(null);
    return () => requestRef.current?.abort();
  }, [load, currentOperationId]);

  const activeCount = items.filter(
    (item) => item.status === "QUEUED" || item.status === "RUNNING",
  ).length;
  return (
    <details
      className="compare-tasks"
      ref={detailsRef}
      onToggle={(event) => {
        if (event.currentTarget.open) void load(null);
      }}
    >
      <summary
        className="task-indicator"
        title="本设备的历史比较任务（服务器记录，可接回其他标签页或终端发起的比较）"
      >
        <ListChecks size={13} />
        比较任务
        {activeCount > 0 && <span className="compare-tasks__badge">{activeCount} 进行中</span>}
      </summary>
      <div className="compare-tasks__menu" role="dialog" aria-label="历史比较任务">
        <div className="compare-tasks__heading">
          <strong>历史比较任务</strong>
          <button
            className="icon-button"
            aria-label="刷新比较任务"
            title="刷新"
            disabled={loading}
            onClick={() => void load(null)}
          >
            <RefreshCw size={14} />
          </button>
        </div>
        {error && (
          <p role="alert" className="compare-tasks__error">
            {error}
          </p>
        )}
        {!error && items.length === 0 && !loading && (
          <p className="compare-tasks__empty">没有进行中或保留期内的历史比较</p>
        )}
        {items.length > 0 && (
          <ul className="compare-tasks__list">
            {items.map((item) => (
              <li key={item.operation_id}>
                <button
                  className={item.operation_id === currentOperationId ? "is-current" : ""}
                  onClick={() => {
                    if (detailsRef.current) detailsRef.current.open = false;
                    onOpen(item);
                  }}
                >
                  <span className={`status-tag status-tag--${STATUS_TONE[item.status]}`}>
                    {STATUS_COPY[item.status]}
                  </span>
                  <span className="compare-tasks__nodes">
                    {item.nodes.map(labelFor).join(" → ")}
                  </span>
                  <small>
                    受理 {time(item.accepted_at)}
                    {item.completed_at ? ` · 完成 ${time(item.completed_at)}` : ""}
                    {item.result_expires_at ? ` · 结果保留至 ${time(item.result_expires_at)}` : ""}
                  </small>
                </button>
              </li>
            ))}
          </ul>
        )}
        {nextCursor && (
          <button className="link-button" disabled={loading} onClick={() => void load(nextCursor)}>
            加载更多
          </button>
        )}
        {loading && <small className="compare-tasks__empty">读取中…</small>}
      </div>
    </details>
  );
}
