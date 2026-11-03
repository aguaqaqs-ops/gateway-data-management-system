import { useSyncExternalStore } from "react";
import type { GatewaySession } from "../api/session";

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

function identityById(id: string): typeof IDENTITIES[number] {
  return IDENTITIES.find((identity) => identity.id === id) ?? IDENTITIES[0];
}

function publish(): void {
  const identity = identityById(selected);
  const session: GatewaySession = {
    businessProjectId: "project-42",
    gatewayDeviceExternalKey: "gateway-17",
    accessToken: identity.token,
  };
  window.__gatewaySession = session;
  window.dispatchEvent(new Event("gateway-session-change"));
  try { window.sessionStorage.setItem(SESSION_KEY, selected); } catch { /* the in-memory session remains available */ }
  for (const listener of listeners) listener();
}

try {
  const stored = window.sessionStorage.getItem(SESSION_KEY);
  if (stored && IDENTITIES.some((identity) => identity.id === stored)) selected = stored as IdentityId;
} catch { /* use the default simulated identity */ }
publish();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): IdentityId {
  return selected;
}

export function DevIdentityControl() {
  const identity = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  return <label className="dev-identity-control">模拟身份
    <select aria-label="模拟身份" value={identity} onChange={(event) => { selected = event.currentTarget.value as IdentityId; publish(); }}>
      {IDENTITIES.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}
    </select>
  </label>;
}
