import { useEffect, useState } from "react";
import { Copy, RefreshCw } from "lucide-react";
import type { components } from "../api/generated/openapi";
import { gatewayApi } from "../api/application-api";
import { OperationFailedError, PollingConnectionLostError, pollOperation } from "../api/journeys";
import { OPERATION_STATUS_COPY } from "../view-model/operation-status-copy";

type Operation = components["schemas"]["OperationResponse"];

export function OperationStatusPanel({ operationId }: { operationId: string }) {
  const [operation, setOperation] = useState<Operation | null>(null);
  const [connectionLost, setConnectionLost] = useState(false);
  const [refreshRevision, setRefreshRevision] = useState(0);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1_000)), 1_000);
    return () => window.clearInterval(timer);
  }, [operationId]);

  useEffect(() => {
    const controller = new AbortController();
    setConnectionLost(false);
    void pollOperation(gatewayApi, operationId, {
      signal: controller.signal,
      onUpdate: (value) => { setOperation(value); setConnectionLost(false); },
      onConnectionStatus: (status) => setConnectionLost(status === "interrupted"),
    }).catch((cause: unknown) => {
      if (controller.signal.aborted) return;
      if (cause instanceof PollingConnectionLostError) setConnectionLost(true);
      else if (cause instanceof OperationFailedError) setConnectionLost(false);
      else setConnectionLost(true);
    });
    return () => controller.abort(new DOMException("状态查询已停止", "AbortError"));
  }, [operationId, refreshRevision]);

  const status = operation?.status ?? "QUEUED";
  const manualRecovery = status === "MANUAL_RECOVERY_REQUIRED";
  return <section className={`operation-status-card${manualRecovery ? " operation-status-card--manual" : ""}`} aria-live="polite" aria-label="操作状态">
    <div className="operation-status-card__heading"><strong>{connectionLost ? "连接中断" : OPERATION_STATUS_COPY[status as keyof typeof OPERATION_STATUS_COPY] ?? "查询状态"}</strong><span>已等待 {elapsed} 秒</span></div>
    <p>{manualRecovery ? "操作需要管理员处理。系统仍在查询状态，操作 ID 可提供给管理员。" : status === "RUNNING" || status === "QUEUED" ? "操作仍在运行，可以继续等待或离开此页面。" : operation?.diagnostic?.message ?? "状态已更新。"}</p>
    {manualRecovery && <div className="operation-status-card__id"><span>操作 ID</span><code>{operationId}</code><button className="button button--ghost" onClick={() => void navigator.clipboard?.writeText(operationId)}><Copy size={14} />复制 ID</button></div>}
    {connectionLost && !manualRecovery && <button className="button button--secondary" onClick={() => setRefreshRevision((value) => value + 1)}><RefreshCw size={14} />重试查询</button>}
    {manualRecovery && <button className="button button--secondary" onClick={() => setRefreshRevision((value) => value + 1)}><RefreshCw size={14} />刷新状态</button>}
  </section>;
}
