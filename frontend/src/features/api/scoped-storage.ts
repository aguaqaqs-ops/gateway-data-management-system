import { currentGatewaySession, scopeMarker } from "./session";

const scopedKey = (key: string) => key === "gateway-preview-operation" || key === "gateway-history-compare-pending-intent" || key.startsWith("gateway-review-history-key:");
export function clearScopedState(): void {
  try {
    for (const key of Object.keys(window.sessionStorage)) if (scopedKey(key)) window.sessionStorage.removeItem(key);
  } catch { /* storage is optional */ }
}
export const scopedStorage = {
  getItem(key: string): string | null {
    try {
      const raw = window.sessionStorage.getItem(key);
      if (raw === null) return null;
      const entry = JSON.parse(raw) as { scope?: string; value?: unknown };
      if (entry.scope === scopeMarker(currentGatewaySession()) && typeof entry.value === "string") return entry.value;
    } catch { /* malformed or unavailable */ }
    this.removeItem(key);
    return null;
  },
  setItem(key: string, value: string): void {
    try { window.sessionStorage.setItem(key, JSON.stringify({ scope: scopeMarker(), value })); } catch { /* storage is optional */ }
  },
  removeItem(key: string): void { try { window.sessionStorage.removeItem(key); } catch { /* storage is optional */ } },
};
