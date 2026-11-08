import { useEffect, useRef, useState } from "react";
import { Copy, RefreshCw } from "lucide-react";
import type { components } from "../api/generated/openapi";
import { gatewayApi } from "../api/application-api";
import { ApiError } from "../api/authenticated-fetch";
import { OperationFailedError, PollingConnectionLostError, pollOperation } from "../api/journeys";
import { OPERATION_STATUS_COPY } from "../view-model/operation-status-copy";
import { formatWaitDuration } from "./wait-duration";

type Operation = components["schemas"]["OperationResponse"];

export function operationElapsedSeconds(operation: Operation | null, now = Date.now()): number | null {
  if (!operation) return null;
  const startedAt = operation.started_at ?? operation.created_at;
  const started = Date.parse(startedAt);
  return Number.isFinite(started) ? Math.max(0, Math.floor((now - started) / 1_000)) : null;
}

export function OperationStatusPanel({ operationId, onSucceeded, onFailed }: { operationId: string; onSucceeded?: (operationId: string) => void; onFailed?: (operationId: string) => void }) {
  const [operation, setOperation] = useState<Operation | null>(null);
  const [connectionLost, setConnectionLost] = useState(false);
  const [queryError, setQueryError] = useState<{ code: string; message: string } | null>(null);
  const [refreshRevision, setRefreshRevision] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const finished = useRef(false);
  const callbacks = useRef({ onSucceeded, onFailed });
  useEffect(() => { callbacks.current = { onSucceeded, onFailed }; }, [onSucceeded, onFailed]);

  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1_000)), 1_000);
    return () => window.clearInterval(timer);
  }, [operationId]);

  useEffect(() => {
    const controller = new AbortController();
    setConnectionLost(false);
    setQueryError(null);
    void pollOperation(gatewayApi, operationId, {
      signal: controller.signal,
      onUpdate: (value) => {
        setOperation(value);
        setConnectionLost(false);
        if (!finished.current && ["SUCCEEDED", "FAILED", "CANCELLED", "SUPERSEDED", "ABORTED"].includes(value.status)) {
          finished.current = true;
          try {
            const url = new URL(window.location.href);
            url.searchParams.delete("operationId");
            url.searchParams.delete("operationKind");
            window.history.replaceState(null, "", url);
          } catch { /* URL 不可用时忽略 */ }
          if (value.status === "SUCCEEDED") callbacks.current.onSucceeded?.(value.operation_id);
          else callbacks.current.onFailed?.(value.operation_id);
        }
      },
      onConnectionStatus: (status) => setConnectionLost(status === "interrupted"),
    }).catch((cause: unknown) => {
      if (controller.signal.aborted) return;
      if (cause instanceof PollingConnectionLostError) setConnectionLost(true);
      else if (cause instanceof OperationFailedError) setConnectionLost(false);
      else if (cause instanceof ApiError) {
        setConnectionLost(false);
        setQueryError(cause.status === 403 || cause.code === "SCOPE_FORBIDDEN"
          ? { code: "SCOPE_FORBIDDEN", message: "当前身份没有该操作的权限" }
          : { code: cause.code ?? `HTTP_${cause.status}`, message: "无法查询操作状态，请稍后重试" });
      } else {
        setConnectionLost(false);
        setQueryError({ code: cause instanceof Error ? cause.name : "REQUEST_FAILED", message: "无法查询操作状态，请稍后重试" });
      }
    });
    return () => controller.abort(new DOMException("状态查询已停止", "AbortError"));
  }, [operationId, refreshRevision]);

  const status = operation?.status ?? "QUEUED";
  const manualRecovery = status === "MANUAL_RECOVERY_REQUIRED";
  const elapsedSeconds = operationElapsedSeconds(operation) ?? elapsed;
  return <section className={`operation-status-card${manualRecovery ? " operation-status-card--manual" : ""}`} aria-live="polite" aria-label="操作状态">
    <div className="operation-status-card__heading"><strong>{connectionLost ? "连接中断" : queryError ? "无法查询状态" : OPERATION_STATUS_COPY[status as keyof typeof OPERATION_STATUS_COPY] ?? "查询状态"}</strong><span>已等待 {formatWaitDuration(elapsedSeconds)}</span></div>
    <p>{manualRecovery ? "操作需要管理员处理。系统仍在查询状态，操作 ID 可提供给管理员。" : queryError ? `${queryError.message}（${queryError.code}）` : status === "RUNNING" || status === "QUEUED" ? "操作仍在运行，可以继续等待或离开此页面。" : operation?.diagnostic?.message ?? "状态已更新。"}</p>
    {manualRecovery && <div className="operation-status-card__id"><span>操作 ID</span><code>{operationId}</code><button className="button button--ghost" onClick={() => void navigator.clipboard?.writeText(operationId)}><Copy size={14} />复制 ID</button></div>}
    {connectionLost && !manualRecovery && <button className="button button--secondary" onClick={() => setRefreshRevision((value) => value + 1)}><RefreshCw size={14} />重试查询</button>}
    {manualRecovery && <button className="button button--secondary" onClick={() => setRefreshRevision((value) => value + 1)}><RefreshCw size={14} />刷新状态</button>}
  </section>;
}
