import { installedGoldenBundle } from "../../test/helpers";
import { Buffer } from "node:buffer";
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createGatewaySession, currentGatewaySession, deviceRouteKey, validateScopeIdentity } from "./session";
import { createAuthenticatedFetch } from "./authenticated-fetch";
import { createGatewayApi } from "./client";
import { pollOperation, runPreviewJourney, createPreviewJourneyProgress, runHistoryComparison } from "./journeys";
import { scopedStorage } from "./scoped-storage";
import { decodeHandoffFragment, initializeGatewaySession, getGatewaySessionState } from "../session/handoff-session";
import { TEST_HISTORY_CURSOR_FIRST, TEST_OPERATION_ACCEPTED, WORKSPACE_CREATED, TEST_UPLOAD_FULL, testHistoryCompareAcceptance, testHistoryCompareSucceeded } from "../dev/simulated-api";

const vectors = JSON.parse(readFileSync("../vnext/fixtures/processing-groups/v1/identity-vectors.json", "utf8")) as Array<{ gateway_device_external_key: string; route_key: string }>;
const boundaries = JSON.parse(readFileSync("../vnext/fixtures/processing-groups/v1/scope-identity-boundaries.json", "utf8")) as { rejected_noncharacters: string[]; accepted_adjacent_scalars: string[] };
const scalar = (value: string) => String.fromCodePoint(Number.parseInt(value.slice(2), 16));
const input = (device = "device-a", token = "token-a") => ({ businessProjectId: "project", gatewayDeviceExternalKey: device, accessToken: token });
function adopt(device = "device-a", token = "token-a") { window.__gatewaySession = createGatewaySession(input(device, token)); return currentGatewaySession(); }
afterEach(() => { delete window.__gatewaySession; window.sessionStorage.clear(); vi.restoreAllMocks(); });

describe("scope identity Contract", () => {
  it.each(vectors)("uses exact shared device route vector $gateway_device_external_key", (vector) => { expect(deviceRouteKey(vector.gateway_device_external_key)).toBe(vector.route_key); });
  it.each(boundaries.rejected_noncharacters)("rejects shared noncharacter %s before hashing", (point) => {
    for (const field of ["businessProjectId", "gatewayDeviceExternalKey"]) expect(() => createGatewaySession({ ...input(), [field]: scalar(point) })).toThrow();
    const payload = { v: 1, token: "token", business_project_id: "project", gateway_device_external_key: scalar(point), display: { region1: "a", region2: "b", project_name: "c", station_code: "d" }, return_url: "https://directory.test" };
    expect(decodeHandoffFragment(`#gdds-handoff=${Buffer.from(JSON.stringify(payload)).toString("base64url")}`).kind).toBe("invalid");
  });
  it.each(boundaries.accepted_adjacent_scalars)("accepts adjacent scalar %s", (point) => { expect(() => validateScopeIdentity(scalar(point))).not.toThrow(); });
  it("validates scalar length, surrogate and NUL without normalizing", () => {
    for (const value of ["", "a".repeat(256), "\0", "\ud800", "\udfff"]) expect(() => validateScopeIdentity(value)).toThrow();
    for (const value of ["中".repeat(255), "😀".repeat(255), " é "]) expect(() => validateScopeIdentity(value)).not.toThrow();
    expect(deviceRouteKey("é")).not.toBe(deviceRouteKey("é"));
    expect(Object.isFrozen(createGatewaySession(input()))).toBe(true);
    window.__gatewaySession = input("\ud800");
    expect(() => currentGatewaySession()).toThrow();
  });
});

describe("request and flow session binding", () => {
  it("sends token and key from one snapshot for JSON and bundle requests", async () => {
    const snapshot = adopt(); const provider = vi.fn(() => snapshot);
    const fetcher = vi.fn(async () => new Response("{}"));
    const request = createAuthenticatedFetch({ baseUrl: "http://gateway", session: provider, fetcher });
    await request("/v1/history");
    await request("/v1/history-compares/id/bundle");
    expect(provider).toHaveBeenCalledTimes(2);
    for (const [, init] of fetcher.mock.calls as unknown as [URL, RequestInit][]) expect(Object.fromEntries(new Headers(init.headers))).toMatchObject({ authorization: "Bearer token-a", "x-gateway-device-key": snapshot.deviceRouteKey });
  });
  it("does not send a request without a device session and leaves health unscoped", async () => {
    const fetcher = vi.fn(async () => new Response("{}"));
    const request = createAuthenticatedFetch({ baseUrl: "http://gateway", session: currentGatewaySession, fetcher });
    await expect(request("/v1/history")).rejects.toThrow("缺少有效设备会话");
    expect(fetcher).not.toHaveBeenCalled(); await request("/healthz");
    expect(new Headers((fetcher.mock.calls as unknown as [URL, RequestInit][])[0]?.[1].headers).has("X-Gateway-Device-Key")).toBe(false);
  });
  it("stops pagination when the session changes", async () => {
    adopt(); const fetcher = vi.fn(async () => { adopt("device-b", "token-b"); return new Response(JSON.stringify(TEST_HISTORY_CURSOR_FIRST)); });
    const api = createGatewayApi({ baseUrl: "http://gateway", session: currentGatewaySession, fetcher });
    await expect(api.listHistory()).rejects.toThrow("会话已变化"); expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("stops polling and a bound retry before sending under the new identity", async () => {
    adopt(); const fetcher = vi.fn(async () => new Response(JSON.stringify({ ...TEST_OPERATION_ACCEPTED, status: "RUNNING" })));
    const api = createGatewayApi({ baseUrl: "http://gateway", session: currentGatewaySession, fetcher }).bindSession!();
    await expect(pollOperation(api, "op", { wait: async () => { adopt("device-b"); } })).rejects.toThrow("会话已变化");
    await expect(api.getHistoryBundle("op")).rejects.toThrow("会话已变化"); expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("stops upload processing and Preview retry when the flow changes session", async () => {
    adopt();
    const fetcher = vi.fn(async (url: RequestInfo | URL) => {
      if (String(url).endsWith("/v1/workspaces")) return new Response(JSON.stringify(WORKSPACE_CREATED.body));
      return new Response(JSON.stringify(TEST_UPLOAD_FULL));
    });
    const api = createGatewayApi({ baseUrl: "http://gateway", session: currentGatewaySession, fetcher });
    const file = new File(["modified"], "modified.zip");
    Object.defineProperty(file, "stream", { value: () => new ReadableStream<Uint8Array>({ start(controller) { adopt("device-b"); controller.enqueue(new TextEncoder().encode("modified")); controller.close(); } }) });
    const progress = createPreviewJourneyProgress();
    const previewInput = { workspaceRequest: { business_project_id: "project", gateway_device_external_key: "device-a" }, upload: { inputCompleteness: "MODIFIED_ONLY" as const, modified: { partName: "modified", mediaType: "application/zip", file } }, baselineNodeId: "baseline", baselineHeadVersion: 0 };
    const store = {} as Parameters<typeof runPreviewJourney>[1];
    await expect(runPreviewJourney(api, store, previewInput, progress)).rejects.toThrow("会话已变化");
    await expect(runPreviewJourney(api, store, previewInput, progress)).rejects.toThrow("会话已变化");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("does not deliver a bound JSON result after session replacement during decoding", async () => {
    adopt();
    const response = new Response("{}");
    vi.spyOn(response, "json").mockImplementation(async () => { adopt("device-b"); return WORKSPACE_CREATED.body; });
    const api = createGatewayApi({ baseUrl: "http://gateway", session: currentGatewaySession, fetcher: vi.fn(async () => response) }).bindSession!();
    await expect(api.createWorkspace({ business_project_id: "project", gateway_device_external_key: "device-a" })).rejects.toThrow("会话已变化");
  });
  it("does not publish a completed bundle flow after session replacement during local install", async () => {
    adopt();
    const fixture = await installedGoldenBundle();
    const fetcher = vi.fn(async (url: RequestInfo | URL) => new Response(JSON.stringify(String(url).endsWith("/v1/history-compares")
      ? testHistoryCompareAcceptance("compare-op") : testHistoryCompareSucceeded(fixture.manifest.bundle_digest, "compare-op"))));
    const api = createGatewayApi({ baseUrl: "http://gateway", session: currentGatewaySession, fetcher });
    vi.spyOn(fixture.store, "open").mockImplementation(async () => { adopt("device-b"); return fixture.bundle; });
    await expect(runHistoryComparison(api, fixture.store, [{ ref_kind: "baseline_node", ref_id: "a" }, { ref_kind: "baseline_node", ref_id: "b" }], "compare-key")).rejects.toThrow("会话已变化");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
  it("maps only workspace startup 404 to the device entry message without retry", async () => {
    adopt(); const fetcher = vi.fn(async () => new Response(JSON.stringify({ code: "RESOURCE_NOT_FOUND", message: "missing" }), { status: 404, headers: { "X-Gateway-Entry-Rejection": "route-not-loaded" } }));
    const api = createGatewayApi({ baseUrl: "http://gateway", session: currentGatewaySession, fetcher });
    await expect(api.createWorkspace({ business_project_id: "project", gateway_device_external_key: "device-a" })).rejects.toThrow("当前设备未接入网关或暂不可用，请从设备目录重新进入或联系管理员。");
    await expect(api.getOperation("id")).rejects.toThrow("missing"); expect(fetcher).toHaveBeenCalledTimes(2);
  });
  it("does not expire a new handoff when an old request returns 401", async () => {
    const payload = (device: string) => btoa(JSON.stringify({ v: 1, token: device, business_project_id: "project", gateway_device_external_key: device, display: { region1: "a", region2: "b", project_name: "c", station_code: "d" }, return_url: "https://directory.test" })).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
    window.history.replaceState(null, "", `/#gdds-handoff=${payload("device-a")}`); initializeGatewaySession();
    const fetcher = vi.fn(async () => { window.history.replaceState(null, "", `/#gdds-handoff=${payload("device-b")}`); initializeGatewaySession(); return new Response(JSON.stringify({ code: "AUTHENTICATION_REQUIRED" }), { status: 401 }); });
    await expect(createAuthenticatedFetch({ baseUrl: "http://gateway", session: currentGatewaySession, fetcher })("/v1/history")).rejects.toThrow("会话已变化");
    expect(getGatewaySessionState().kind).toBe("handoff"); expect(currentGatewaySession().gatewayDeviceExternalKey).toBe("device-b");
  });
  it("ignores and deletes persisted intent from another scope", () => {
    adopt(); for (const key of ["gateway-preview-operation", "gateway-history-compare-pending-intent", "gateway-review-history-key:id"]) { scopedStorage.setItem(key, "intent"); expect(scopedStorage.getItem(key)).toBe("intent"); }
    adopt("device-b"); for (const key of Object.keys(window.sessionStorage)) { expect(scopedStorage.getItem(key)).toBeNull(); expect(window.sessionStorage.getItem(key)).toBeNull(); }
  });
});
