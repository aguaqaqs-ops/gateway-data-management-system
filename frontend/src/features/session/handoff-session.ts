import { useSyncExternalStore } from "react";
import type { GatewaySession } from "../api/session";

export const HANDOFF_SESSION_STORAGE_KEY = "gdds-gateway-session";
export const HANDOFF_FRAGMENT_KEY = "gdds-handoff";

export interface HandoffDisplay {
  region1: string;
  region2: string;
  project_name: string;
  station_code: string;
}

export interface HandoffSession {
  businessProjectId: string;
  gatewayDeviceExternalKey: string;
  accessToken: string;
  display: HandoffDisplay;
  returnUrl: string;
}

export type GatewaySessionState =
  | { kind: "none" }
  | { kind: "preset"; session: GatewaySession }
  | { kind: "handoff"; session: HandoffSession }
  | { kind: "invalid" }
  | { kind: "expired"; returnUrl: string | null; display: HandoffDisplay | null };

type FragmentResult =
  | { kind: "absent" }
  | { kind: "invalid" }
  | { kind: "ok"; session: HandoffSession };

const listeners = new Set<() => void>();
let currentState: GatewaySessionState = { kind: "none" };
let initialized = false;

function emit(): void {
  for (const listener of listeners) listener();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requiredString(value: Record<string, unknown>, key: string): string | null {
  const candidate = value[key];
  return typeof candidate === "string" && candidate.length > 0 ? candidate : null;
}

function parseDisplay(value: unknown): HandoffDisplay | null {
  if (!isRecord(value)) return null;
  const region1 = requiredString(value, "region1");
  const region2 = requiredString(value, "region2");
  const projectName = requiredString(value, "project_name");
  const stationCode = requiredString(value, "station_code");
  if (!region1 || !region2 || !projectName || !stationCode) return null;
  return { region1, region2, project_name: projectName, station_code: stationCode };
}

function parseReturnUrl(value: unknown): string | null {
  if (typeof value !== "string" || value.length === 0) return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? value : null;
  } catch {
    return null;
  }
}

function parseHandoffPayload(value: unknown): HandoffSession | null {
  if (!isRecord(value) || value.v !== 1) return null;
  const token = requiredString(value, "token");
  const gatewayDeviceExternalKey = requiredString(value, "gateway_device_external_key");
  const businessProjectId = requiredString(value, "business_project_id");
  const display = parseDisplay(value.display);
  const returnUrl = parseReturnUrl(value.return_url);
  if (!token || !gatewayDeviceExternalKey || !businessProjectId || !display || !returnUrl) return null;
  return { businessProjectId, gatewayDeviceExternalKey, accessToken: token, display, returnUrl };
}

function storedPayload(session: HandoffSession): Record<string, unknown> {
  return {
    v: 1,
    token: session.accessToken,
    gateway_device_external_key: session.gatewayDeviceExternalKey,
    business_project_id: session.businessProjectId,
    display: session.display,
    return_url: session.returnUrl,
  };
}

function toGatewaySession(session: HandoffSession): GatewaySession {
  return {
    businessProjectId: session.businessProjectId,
    gatewayDeviceExternalKey: session.gatewayDeviceExternalKey,
    accessToken: session.accessToken,
  };
}

export function decodeHandoffFragment(hash: string): FragmentResult {
  const rawHash = hash.startsWith("#") ? hash.slice(1) : hash;
  if (rawHash.length === 0) return { kind: "absent" };
  const encoded = new URLSearchParams(rawHash).get(HANDOFF_FRAGMENT_KEY);
  if (encoded === null) return { kind: "absent" };
  // base64url without padding only; a length of 4n+1 cannot be valid.
  if (!/^[A-Za-z0-9_-]+$/.test(encoded) || encoded.length % 4 === 1) return { kind: "invalid" };
  try {
    const base64 = encoded.replaceAll("-", "+").replaceAll("_", "/")
      + "=".repeat((4 - encoded.length % 4) % 4);
    const binary = atob(base64);
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    const decoded = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    const session = parseHandoffPayload(JSON.parse(decoded) as unknown);
    return session ? { kind: "ok", session } : { kind: "invalid" };
  } catch {
    return { kind: "invalid" };
  }
}

function clearHandoffFragment(): void {
  const url = new URL(window.location.href);
  if (url.hash.length === 0) return;
  // replaceState keeps the current entry and never sends the fragment to a server.
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}`);
}

function removeStoredSession(): void {
  try {
    window.sessionStorage.removeItem(HANDOFF_SESSION_STORAGE_KEY);
  } catch {
    // Session storage may be unavailable (privacy mode); the in-memory state
    // remains authoritative for this load.
  }
}

function persistSession(session: HandoffSession): void {
  try {
    window.sessionStorage.setItem(HANDOFF_SESSION_STORAGE_KEY, JSON.stringify(storedPayload(session)));
  } catch {
    // Same as above: keep the session in memory for this load only.
  }
}

function readStoredSession(): HandoffSession | null {
  try {
    const raw = window.sessionStorage.getItem(HANDOFF_SESSION_STORAGE_KEY);
    if (raw === null) return null;
    let value: unknown;
    try {
      value = JSON.parse(raw);
    } catch {
      window.sessionStorage.removeItem(HANDOFF_SESSION_STORAGE_KEY);
      return null;
    }
    const parsed = parseHandoffPayload(value);
    if (parsed) return parsed;
    window.sessionStorage.removeItem(HANDOFF_SESSION_STORAGE_KEY);
    return null;
  } catch {
    return null;
  }
}

function computeState(): GatewaySessionState {
  const fragment = decodeHandoffFragment(window.location.hash);
  if (fragment.kind === "ok") {
    clearHandoffFragment();
    window.__gatewaySession = toGatewaySession(fragment.session);
    persistSession(fragment.session);
    return { kind: "handoff", session: fragment.session };
  }
  if (fragment.kind === "invalid") {
    // A fragment was present but unusable: never fall back to an older session.
    clearHandoffFragment();
    delete window.__gatewaySession;
    removeStoredSession();
    return { kind: "invalid" };
  }

  const preset = window.__gatewaySession;
  if (preset && (preset.businessProjectId || preset.gatewayDeviceExternalKey || preset.accessToken)) {
    // Test injection: keep it exactly as supplied and never touch sessionStorage.
    return { kind: "preset", session: preset };
  }

  const stored = readStoredSession();
  if (stored) {
    window.__gatewaySession = toGatewaySession(stored);
    return { kind: "handoff", session: stored };
  }
  return { kind: "none" };
}

export function initializeGatewaySession(): void {
  initialized = true;
  currentState = computeState();
  emit();
}

function ensureInitialized(): void {
  if (initialized) return;
  initialized = true;
  currentState = computeState();
}

export function getGatewaySessionState(): GatewaySessionState {
  ensureInitialized();
  return currentState;
}

export function subscribeGatewaySession(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function setState(next: GatewaySessionState): void {
  currentState = next;
  emit();
}

export function useGatewaySessionState(): GatewaySessionState {
  ensureInitialized();
  return useSyncExternalStore(subscribeGatewaySession, getGatewaySessionState, getGatewaySessionState);
}

export function hasGatewayIdentity(state: GatewaySessionState = getGatewaySessionState()): boolean {
  return state.kind === "handoff" || state.kind === "preset";
}

export function isGatewaySessionBlocked(state: GatewaySessionState = getGatewaySessionState()): boolean {
  return state.kind === "none" || state.kind === "invalid" || state.kind === "expired";
}

export function formatHandoffDisplay(display: HandoffDisplay): string {
  return `${display.region1} / ${display.region2} / ${display.project_name}（${display.station_code}）`;
}

export function handoffSessionOwnsIdentity(): boolean {
  const kind = getGatewaySessionState().kind;
  return kind === "handoff" || kind === "invalid" || kind === "expired";
}

export function shouldPublishDevIdentity(): boolean {
  return getGatewaySessionState().kind === "none"
    && window.__gatewayTestConfig?.disableDevIdentity !== true;
}

export function adoptInjectedSession(session: GatewaySession): void {
  const kind = getGatewaySessionState().kind;
  if (kind === "handoff" || kind === "invalid" || kind === "expired") return;
  setState({ kind: "preset", session });
}

export function expireHandoffSessionOnUnauthorized(): boolean {
  const state = getGatewaySessionState();
  if (state.kind !== "handoff") return false;
  const returnUrl = state.session.returnUrl;
  const display = state.session.display;
  delete window.__gatewaySession;
  removeStoredSession();
  setState({ kind: "expired", returnUrl, display });
  return true;
}
