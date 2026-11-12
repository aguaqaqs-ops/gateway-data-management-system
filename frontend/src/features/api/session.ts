import { Sha256 } from "../bundle/sha256";

export interface GatewaySessionInput {
  readonly businessProjectId: string;
  readonly gatewayDeviceExternalKey: string;
  readonly accessToken: string | null;
}
export interface GatewaySession extends GatewaySessionInput {
  readonly deviceRouteKey: string;
}

declare global {
  interface Window {
    __gatewaySession?: GatewaySessionInput;
    __gatewayTestConfig?: { historyCompareTimeoutMs?: number; disableDevIdentity?: boolean };
  }
}

export function validateScopeIdentity(value: string): void {
  let count = 0;
  for (const scalar of value) {
    const code = scalar.codePointAt(0)!;
    if (code === 0 || (code >= 0xd800 && code <= 0xdfff)
      || (code >= 0xfdd0 && code <= 0xfdef) || (code & 0xffff) >= 0xfffe) {
      throw new Error("设备或项目身份包含非法 Unicode 码点");
    }
    count += 1;
  }
  if (count < 1 || count > 255 || new TextEncoder().encode(value).byteLength > 1020) {
    throw new Error("设备或项目身份长度无效");
  }
}

export function deviceRouteKey(device: string): string {
  validateScopeIdentity(device);
  return new Sha256().update(new TextEncoder().encode(device)).digest();
}

export function createGatewaySession(input: GatewaySessionInput): GatewaySession {
  validateScopeIdentity(input.businessProjectId);
  return Object.freeze({ ...input, deviceRouteKey: deviceRouteKey(input.gatewayDeviceExternalKey) });
}

const sessions = new WeakMap<GatewaySessionInput, GatewaySession>();
const emptySession: GatewaySession = Object.freeze({ businessProjectId: "", gatewayDeviceExternalKey: "", accessToken: null, deviceRouteKey: "" });

export function currentGatewaySession(): GatewaySession {
  const input = window.__gatewaySession;
  if (!input) return emptySession;
  let snapshot = sessions.get(input);
  if (!snapshot) {
    snapshot = createGatewaySession(input);
    sessions.set(input, snapshot);
    sessions.set(snapshot, snapshot);
    window.__gatewaySession = snapshot;
  }
  return snapshot;
}

export class SessionChangedError extends Error {
  constructor() { super("会话已变化"); this.name = "SessionChangedError"; }
}

export function scopeMarker(session = currentGatewaySession()): string {
  return JSON.stringify([session.deviceRouteKey, session.businessProjectId]);
}

const DEFAULT_HISTORY_COMPARE_TIMEOUT_MS = 30_000;

export function historyCompareRequestTimeoutMs(): number {
  if (!import.meta.env.DEV) return DEFAULT_HISTORY_COMPARE_TIMEOUT_MS;
  const configured = window.__gatewayTestConfig?.historyCompareTimeoutMs;
  return typeof configured === "number" && Number.isFinite(configured) && configured > 0
    ? configured
    : DEFAULT_HISTORY_COMPARE_TIMEOUT_MS;
}
