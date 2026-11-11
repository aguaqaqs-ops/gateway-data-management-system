import { useSyncExternalStore } from "react";
import type { GatewaySession } from "../api/session";
import {
  adoptInjectedSession,
  getGatewaySessionState,
  handoffSessionOwnsIdentity,
  shouldPublishDevIdentity,
  useGatewaySessionState,
} from "../session/handoff-session";

const IDENTITIES = [
  { id: "submitter", label: "提交人", token: "dev-token-submitter" },
  { id: "reviewer", label: "审核人", token: "dev-token-reviewer" },
  { id: "archive-confirmer", label: "归档确认人", token: "dev-token-archive-confirmer" },
  { id: "no-permission", label: "无权限身份", token: "dev-token-no-permission" },
] as const;

type IdentityId = typeof IDENTITIES[number]["id"];
const SESSION_KEY = "gateway-dev-identity";
const listeners = new Set<() => void>();
let selected: IdentityId = "submitter";
let publishedByDevIdentity = false;

function identityById(id: string): typeof IDENTITIES[number] {
  return IDENTITIES.find((identity) => identity.id === id) ?? IDENTITIES[0];
}

function publish(): void {
  if (handoffSessionOwnsIdentity()) return;
  const state = getGatewaySessionState();
  if (state.kind === "preset" && !publishedByDevIdentity) return;
  const identity = identityById(selected);
  const session: GatewaySession = {
    businessProjectId: "project-42",
    gatewayDeviceExternalKey: "gateway-17",
    accessToken: identity.token,
  };
  publishedByDevIdentity = true;
  window.__gatewaySession = session;
  adoptInjectedSession(session);
  window.dispatchEvent(new Event("gateway-session-change"));
  try { window.sessionStorage.setItem(SESSION_KEY, selected); } catch { /* the in-memory session remains available */ }
  for (const listener of listeners) listener();
}

try {
  const stored = window.sessionStorage.getItem(SESSION_KEY);
  if (stored && IDENTITIES.some((identity) => identity.id === stored)) selected = stored as IdentityId;
} catch { /* use the default simulated identity */ }
// A directory handoff, an injected test session, or an invalid/expired
// handoff always wins; only an otherwise empty session gets the dev identity.
if (shouldPublishDevIdentity()) publish();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): IdentityId {
  return selected;
}

export function DevIdentityControl() {
  const identity = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const sessionState = useGatewaySessionState();
  const disabled = window.__gatewayTestConfig?.disableDevIdentity === true;
  const visible = !disabled
    && (sessionState.kind === "none" || (sessionState.kind === "preset" && publishedByDevIdentity));
  if (!visible) return null;
  return <label className="dev-identity-control">模拟身份
    <select aria-label="模拟身份" value={identity} onChange={(event) => { selected = event.currentTarget.value as IdentityId; publish(); }}>
      {IDENTITIES.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}
    </select>
  </label>;
}
