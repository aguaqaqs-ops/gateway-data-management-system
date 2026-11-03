export type ConnectionStatus = "connected" | "interrupted" | null;
let currentStatus: ConnectionStatus = null;

export interface ConnectionStatusEvent extends Event {
  detail: Exclude<ConnectionStatus, null>;
}

export function connectionStatusLabel(status: ConnectionStatus): string | null {
  if (status === "connected") return "已连接";
  if (status === "interrupted") return "连接中断";
  return null;
}

export function getConnectionStatus(): ConnectionStatus {
  return currentStatus;
}

export function reportConnectionStatus(status: Exclude<ConnectionStatus, null>): void {
  currentStatus = status;
  window.dispatchEvent(new CustomEvent<Exclude<ConnectionStatus, null>>("gateway-connection-status", { detail: status }));
}
