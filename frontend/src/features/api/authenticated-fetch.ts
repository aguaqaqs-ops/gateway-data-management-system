import { reportConnectionStatus } from "./connection-status";

export type AccessTokenProvider = () => string | null | Promise<string | null>;
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
  token: AccessTokenProvider;
  fetcher?: FetchLike;
  trackConnection?: boolean;
}

/** Adds the current bearer token to every API call without persisting credentials in browser storage. */
export function createAuthenticatedFetch({ baseUrl, token, fetcher = fetch, trackConnection = true }: AuthenticatedFetchOptions) {
  const root = baseUrl.replace(/\/$/, "");
  return async function authenticatedFetch(path: string, init: RequestInit = {}): Promise<Response> {
    const accessToken = await token();
    const headers = new Headers(init.headers);
    headers.set("Accept", headers.get("Accept") ?? "application/json");
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
    else headers.delete("Authorization");
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
    throw new ApiError(message, response.status, code, errorBody.details);
  };
}

export type AuthenticatedFetch = ReturnType<typeof createAuthenticatedFetch>;
