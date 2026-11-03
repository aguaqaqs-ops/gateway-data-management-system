export interface GatewaySession {
  businessProjectId: string;
  gatewayDeviceExternalKey: string;
  accessToken: string | null;
}

declare global {
  interface Window {
    __gatewaySession?: GatewaySession;
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
