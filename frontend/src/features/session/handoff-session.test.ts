import { Buffer } from "node:buffer";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createAuthenticatedFetch } from "../api/authenticated-fetch";
import {
  HANDOFF_FRAGMENT_KEY,
  HANDOFF_SESSION_STORAGE_KEY,
  decodeHandoffFragment,
  expireHandoffSessionOnUnauthorized,
  formatHandoffDisplay,
  getGatewaySessionState,
  hasGatewayIdentity,
  initializeGatewaySession,
  isGatewaySessionBlocked,
  shouldPublishDevIdentity,
  type HandoffSession,
} from "./handoff-session";

const VALID: HandoffSession = {
  businessProjectId: "prj-42",
  gatewayDeviceExternalKey: "dev-17",
  accessToken: "dir-token-secret",
  display: { region1: "华东", region2: "上海", project_name: "示例项目", station_code: "站-01" },
  returnUrl: "http://directory.example:8100/?r1=%E5%8D%8E%E4%B8%9C&page=1",
};

function encodeBase64Url(value: unknown): string {
  return Buffer.from(JSON.stringify(value), "utf8").toString("base64url");
}

function payload(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    v: 1,
    token: VALID.accessToken,
    gateway_device_external_key: VALID.gatewayDeviceExternalKey,
    business_project_id: VALID.businessProjectId,
    display: VALID.display,
    return_url: VALID.returnUrl,
    ...overrides,
  };
}

function storedPayload(overrides: Record<string, unknown> = {}): string {
  return JSON.stringify(payload(overrides));
}

function openWithFragment(encoded: string): void {
  window.history.replaceState(null, "", `/#${HANDOFF_FRAGMENT_KEY}=${encoded}`);
  initializeGatewaySession();
}

beforeEach(() => {
  window.history.replaceState(null, "", "/");
  window.sessionStorage.clear();
  delete window.__gatewaySession;
  delete window.__gatewayTestConfig;
  initializeGatewaySession();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("decodeHandoffFragment", () => {
  it("decodes a valid base64url payload and preserves UTF-8 display text", () => {
    const result = decodeHandoffFragment(`#${HANDOFF_FRAGMENT_KEY}=${encodeBase64Url(payload())}`);
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.session).toEqual(VALID);
    expect(formatHandoffDisplay(result.session.display)).toBe("华东 / 上海 / 示例项目（站-01）");
  });

  it.each([
    ["wrong version", payload({ v: 2 })],
    ["missing version", payload({ v: undefined })],
    ["empty token", payload({ token: "" })],
    ["missing device key", payload({ gateway_device_external_key: undefined })],
    ["missing project id", payload({ business_project_id: undefined })],
    ["missing display", payload({ display: undefined })],
    ["empty display region", payload({ display: { ...VALID.display, region2: "" } })],
    ["non-string display", payload({ display: { ...VALID.display, station_code: 17 } })],
    ["ftp return url", payload({ return_url: "ftp://directory.example/" })],
    ["javascript return url", payload({ return_url: "javascript:alert(1)" })],
    ["relative return url", payload({ return_url: "/workbench" })],
  ])("rejects %s", (_name, value) => {
    expect(decodeHandoffFragment(`#${HANDOFF_FRAGMENT_KEY}=${encodeBase64Url(value)}`).kind).toBe("invalid");
  });

  it("rejects malformed base64url and non-JSON payloads", () => {
    const invalidUtf8 = Buffer.from([0xff, 0xfe, 0xfd]).toString("base64url");
    expect(decodeHandoffFragment(`#${HANDOFF_FRAGMENT_KEY}=${invalidUtf8}`).kind).toBe("invalid");
    expect(decodeHandoffFragment(`#${HANDOFF_FRAGMENT_KEY}=${Buffer.from("not json").toString("base64url")}`).kind).toBe("invalid");
    expect(decodeHandoffFragment(`#${HANDOFF_FRAGMENT_KEY}=abc=`).kind).toBe("invalid");
    expect(decodeHandoffFragment(`#${HANDOFF_FRAGMENT_KEY}=a`).kind).toBe("invalid");
    expect(decodeHandoffFragment(`#${HANDOFF_FRAGMENT_KEY}=ab$c`).kind).toBe("invalid");
    expect(decodeHandoffFragment(`#${HANDOFF_FRAGMENT_KEY}=`).kind).toBe("invalid");
    expect(decodeHandoffFragment("#other=value").kind).toBe("absent");
    expect(decodeHandoffFragment("").kind).toBe("absent");
  });
});

describe("handoff initialization priority", () => {
  it("prefers a valid fragment, stores the session, and clears the fragment", () => {
    window.__gatewaySession = { businessProjectId: "preset", gatewayDeviceExternalKey: "preset-device", accessToken: "preset-token" };
    window.sessionStorage.setItem(HANDOFF_SESSION_STORAGE_KEY, storedPayload({ token: "older-token" }));
    const encoded = encodeBase64Url(payload());
    openWithFragment(encoded);

    const state = getGatewaySessionState();
    expect(state.kind).toBe("handoff");
    if (state.kind === "handoff") expect(state.session).toEqual(VALID);
    expect(window.__gatewaySession).toEqual({
      businessProjectId: VALID.businessProjectId,
      gatewayDeviceExternalKey: VALID.gatewayDeviceExternalKey,
      accessToken: VALID.accessToken,
    });
    expect(window.sessionStorage.getItem(HANDOFF_SESSION_STORAGE_KEY)).toBe(storedPayload());
    expect(window.location.hash).toBe("");
    expect(window.location.pathname).toBe("/");
  });

  it("clears the fragment with replaceState and never calls pushState", () => {
    // Credential boundary: the token-bearing fragment must not stay in the
    // browsing history. A pushState-based clear would keep it there.
    const pushState = vi.spyOn(window.history, "pushState");
    openWithFragment(encodeBase64Url(payload()));

    expect(window.location.hash).toBe("");
    expect(pushState).not.toHaveBeenCalled();
  });

  it("does not fall back to an older session when the fragment is invalid", () => {
    window.sessionStorage.setItem(HANDOFF_SESSION_STORAGE_KEY, storedPayload());
    openWithFragment(encodeBase64Url(payload({ v: 9 })));

    expect(getGatewaySessionState().kind).toBe("invalid");
    expect(window.sessionStorage.getItem(HANDOFF_SESSION_STORAGE_KEY)).toBeNull();
    expect(window.__gatewaySession).toBeUndefined();
    expect(window.location.hash).toBe("");
  });

  it("keeps an injected window.__gatewaySession untouched and never reads storage", () => {
    const preset = { businessProjectId: "project-42", gatewayDeviceExternalKey: "gateway-17", accessToken: "dev-token-submitter" };
    window.__gatewaySession = preset;
    window.sessionStorage.setItem(HANDOFF_SESSION_STORAGE_KEY, storedPayload());
    const getItem = vi.spyOn(Storage.prototype, "getItem");
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    initializeGatewaySession();

    expect(getGatewaySessionState()).toEqual({ kind: "preset", session: preset });
    expect(getItem).not.toHaveBeenCalled();
    expect(setItem).not.toHaveBeenCalled();
    expect(window.sessionStorage.getItem(HANDOFF_SESSION_STORAGE_KEY)).toBe(storedPayload());
  });

  it("restores a valid stored session when there is no fragment or preset", () => {
    window.sessionStorage.setItem(HANDOFF_SESSION_STORAGE_KEY, storedPayload());
    initializeGatewaySession();

    const state = getGatewaySessionState();
    expect(state.kind).toBe("handoff");
    if (state.kind === "handoff") expect(state.session).toEqual(VALID);
    expect(window.__gatewaySession?.accessToken).toBe(VALID.accessToken);
  });

  it("deletes a corrupt stored session and continues without one", () => {
    window.sessionStorage.setItem(HANDOFF_SESSION_STORAGE_KEY, "{not-json");
    initializeGatewaySession();
    expect(getGatewaySessionState().kind).toBe("none");
    expect(window.sessionStorage.getItem(HANDOFF_SESSION_STORAGE_KEY)).toBeNull();
    expect(window.__gatewaySession).toBeUndefined();
  });

  it("keeps the handoff session in memory when sessionStorage throws", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("privacy mode"); });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("privacy mode"); });
    openWithFragment(encodeBase64Url(payload()));

    const state = getGatewaySessionState();
    expect(state.kind).toBe("handoff");
    if (state.kind === "handoff") expect(state.session.accessToken).toBe(VALID.accessToken);
    expect(hasGatewayIdentity(state)).toBe(true);
    expect(isGatewaySessionBlocked(state)).toBe(false);
  });
});

describe("expiry and dev identity", () => {
  it("expires a handoff session on 401 AUTHENTICATION_REQUIRED and keeps the return address", async () => {
    openWithFragment(encodeBase64Url(payload()));
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ code: "AUTHENTICATION_REQUIRED", message: "expired" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    }));
    const request = createAuthenticatedFetch({ baseUrl: "http://gateway.example", token: () => "dir-token-secret", fetcher });

    await expect(request("/v1/workspaces")).rejects.toMatchObject({ status: 401, code: "AUTHENTICATION_REQUIRED" });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(getGatewaySessionState()).toEqual({ kind: "expired", returnUrl: VALID.returnUrl, display: VALID.display });
    expect(window.sessionStorage.getItem(HANDOFF_SESSION_STORAGE_KEY)).toBeNull();
    expect(window.__gatewaySession).toBeUndefined();
    expect(isGatewaySessionBlocked(getGatewaySessionState())).toBe(true);
  });

  it("does not expire an injected preset on 401", async () => {
    window.__gatewaySession = { businessProjectId: "project-42", gatewayDeviceExternalKey: "gateway-17", accessToken: "dev-token" };
    initializeGatewaySession();
    const request = createAuthenticatedFetch({ baseUrl: "http://gateway.example", token: () => "dev-token",
      fetcher: async () => new Response(JSON.stringify({ code: "AUTHENTICATION_REQUIRED", message: "no" }), { status: 401 }) });

    await expect(request("/v1/workspaces")).rejects.toMatchObject({ status: 401 });
    expect(getGatewaySessionState().kind).toBe("preset");
    expect(expireHandoffSessionOnUnauthorized()).toBe(false);
  });

  it("lets the dev identity publish only when nothing else owns the session", () => {
    expect(shouldPublishDevIdentity()).toBe(true);
    window.__gatewayTestConfig = { disableDevIdentity: true };
    expect(shouldPublishDevIdentity()).toBe(false);
    delete window.__gatewayTestConfig;
    openWithFragment(encodeBase64Url(payload()));
    expect(shouldPublishDevIdentity()).toBe(false);
  });
});
