import { assertCurrentSession, SessionChangedError, currentGatewaySession, type GatewaySession } from "./session";
import { reportConnectionStatus } from "./connection-status";
import { expireHandoffSessionOnUnauthorized } from "../session/handoff-session";

export type SessionProvider = () => GatewaySession;
export type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly details: unknown;

  constructor(message: string, status: number, code: string | null = null, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export interface AuthenticatedFetchOptions {
  baseUrl: string;
  session: SessionProvider;
  boundSession?: GatewaySession;
  fetcher?: FetchLike;
  trackConnection?: boolean;
}

/**
 * Adds the current bearer token to every API call. The directory-handoff trial
 * is the one exception to "no credentials in browser storage": it keeps the
 * per-tab session in sessionStorage (see features/session/handoff-session.ts).
 */
export function createAuthenticatedFetch({ baseUrl, session, boundSession, fetcher = fetch, trackConnection = true }: AuthenticatedFetchOptions) {
  const root = baseUrl.replace(/\/$/, "");
  return async function authenticatedFetch(path: string, init: RequestInit = {}): Promise<Response> {
    const snapshot = boundSession ?? session();
    if (boundSession && session() !== boundSession) throw new SessionChangedError();
    const isApi = new URL(path, `${root}/`).pathname.startsWith("/v1/");
    if (isApi && (!snapshot.accessToken || !snapshot.deviceRouteKey)) throw new Error("缺少有效设备会话");
    const accessToken = snapshot.accessToken;
    const headers = new Headers(init.headers);
    headers.set("Accept", headers.get("Accept") ?? "application/json");
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
    else headers.delete("Authorization");
    if (isApi) headers.set("X-Gateway-Device-Key", snapshot.deviceRouteKey);
    else headers.delete("X-Gateway-Device-Key");
    const response = await fetcher(new URL(path, `${root}/`), { ...init, headers });
    if (response.ok) {
      if (trackConnection) reportConnectionStatus("connected");
      return response;
    }

    let body: unknown;
    try {
      body = await response.clone().json();
    } catch {
      body = undefined;
    }
    const errorBody = body && typeof body === "object" ? body as Record<string, unknown> : {};
    const code = typeof errorBody.code === "string" ? errorBody.code : null;
    const message = typeof errorBody.message === "string"
      ? errorBody.message
      : `请求失败（HTTP ${response.status}）`;
    if (response.status === 401 && code === "AUTHENTICATION_REQUIRED") {
      // The handoff session is the only state that can expire here; injected
      // dev/test identities are left alone so their own error surfaces remain.
      expireHandoffSessionOnUnauthorized(snapshot);
    }
    if (currentGatewaySession() !== snapshot && session === currentGatewaySession) assertCurrentSession(snapshot);
    const displayMessage = response.status === 404 && init.method === "POST" && path === "/v1/workspaces"
      ? "当前设备未接入网关或暂不可用，请从设备目录重新进入或联系管理员。" : message;
    throw new ApiError(displayMessage, response.status, code, errorBody.details);
  };
}

export type AuthenticatedFetch = ReturnType<typeof createAuthenticatedFetch>;
