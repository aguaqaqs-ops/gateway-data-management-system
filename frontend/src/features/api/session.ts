export interface GatewaySession {
  businessProjectId: string;
  gatewayDeviceExternalKey: string;
  accessToken: string | null;
}

declare global {
  interface Window {
    __gatewaySession?: GatewaySession;
    __gatewayTestConfig?: { historyCompareTimeoutMs?: number };
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

export function historyCompareRequestTimeoutMs(): number {
  const configured = window.__gatewayTestConfig?.historyCompareTimeoutMs;
  return typeof configured === "number" && Number.isFinite(configured) && configured > 0 ? configured : 30_000;
}
