export interface GatewaySession {
  businessProjectId: string;
  gatewayDeviceExternalKey: string;
  accessToken: string | null;
}

declare global {
  interface Window {
    __gatewaySession?: GatewaySession;
    __gatewayTestConfig?: { historyCompareTimeoutMs?: number; disableDevIdentity?: boolean };
  }
}

const emptySession: GatewaySession = {
  businessProjectId: "",
  gatewayDeviceExternalKey: "",
  accessToken: null,
};

export function currentGatewaySession(): GatewaySession {
  return window.__gatewaySession ?? emptySession;
}

export function currentAccessToken(): string | null {
  return currentGatewaySession().accessToken;
}

const DEFAULT_HISTORY_COMPARE_TIMEOUT_MS = 30_000;

export function historyCompareRequestTimeoutMs(): number {
  if (!import.meta.env.DEV) return DEFAULT_HISTORY_COMPARE_TIMEOUT_MS;
  const configured = window.__gatewayTestConfig?.historyCompareTimeoutMs;
  return typeof configured === "number" && Number.isFinite(configured) && configured > 0
    ? configured
    : DEFAULT_HISTORY_COMPARE_TIMEOUT_MS;
}
