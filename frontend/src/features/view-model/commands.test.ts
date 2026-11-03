import { beforeEach, describe, expect, it } from "vitest";
import { installedFixtureBundle } from "../../test/helpers";
import { loadComparisonPresentation } from "../bundle/presentation";
import { BrowseCommandRuntime, decodeBrowseState, encodeBrowseState, executeBrowseCommand, initialBrowseState } from "./commands";

describe("read-only browsing commands and URL state", () => {
  beforeEach(() => window.history.replaceState(null, "", "/"));

  it("round-trips pair, navigation, filters, search and comparison refs through the URL", () => {
    const bundled = { ...executeBrowseCommand(initialBrowseState, { name: "set-bundle", mode: "REVIEW", bundleDigest: "sha256:abc", requestPath: "/v1/history/bundle" }),
      modeRequests: { PREVIEW: "/v1/preview/bundle", REVIEW: "/v1/review/bundle", HISTORY: "/v1/history/bundle" } };
    const pair = executeBrowseCommand(bundled, { name: "select-pair", pairId: "node-a_to_node-b" });
    const state = executeBrowseCommand(pair, { name: "select-node", nodeKey: "device:addr:1" });
    const withTab = executeBrowseCommand(state, { name: "select-tab", tabKey: "measurements" });
    const filtered = executeBrowseCommand(withTab, { name: "set-only-interesting", enabled: true });
    const expanded = executeBrowseCommand(filtered, { name: "toggle-group", groupKey: "SECONDARY_DEVICES" });
    const compared = executeBrowseCommand(expanded, { name: "add-comparison-node", ref: "submission:s1" });
    const encoded = encodeBrowseState(compared);
    expect(decodeBrowseState(encoded)).toEqual(compared);
    expect(new URLSearchParams(encoded).has("view")).toBe(false);
    expect(new URLSearchParams(encoded).get("pair")).toBe("node-a_to_node-b");
    expect(new URLSearchParams(encoded).get("reviewRequest")).toBe("/v1/review/bundle");
  });

  it("falls back to Preview for unknown modes and retains pair identity", () => {
    const decoded = decodeBrowseState("?mode=UNKNOWN&view=opaque-view-id&pair=pair-a");
    expect(decoded.mode).toBe("PREVIEW");
    expect(decoded.pairId).toBe("pair-a");
  });

  it("restores Review and History as separate browsing contexts", () => {
    expect(decodeBrowseState("?mode=REVIEW").mode).toBe("REVIEW");
    expect(decodeBrowseState("?mode=HISTORY").mode).toBe("HISTORY");
  });

  it("switches and restores Preview views by pair_id when both surface view_id values are equal", async () => {
    const { bundle, manifest } = await installedFixtureBundle("preview-full");
    const pairIds = manifest.pairs.map((pair) => (pair as { pair_id: string }).pair_id);
    expect(pairIds).toEqual(["baseline_to_initial", "initial_to_modified"]);
    const presentations = await Promise.all(pairIds.map((pairId) => loadComparisonPresentation(bundle, pairId)));
    expect(presentations.map(({ surface }) => (surface.view as Record<string, unknown>).view_id)).toEqual(["initial_to_modified", "initial_to_modified"]);
    const first = executeBrowseCommand(initialBrowseState, { name: "select-pair", pairId: pairIds[0] as string });
    const second = executeBrowseCommand(first, { name: "select-pair", pairId: pairIds[1] as string });
    expect(decodeBrowseState(encodeBrowseState(second)).pairId).toBe("initial_to_modified");
    expect(new URLSearchParams(encodeBrowseState(second)).has("view")).toBe(false);
  });

  it("caps the comparison tray at three entries and keeps writes outside the command type", () => {
    const state = executeBrowseCommand(initialBrowseState, { name: "add-comparison-node", ref: "baseline:b1" });
    const two = executeBrowseCommand(state, { name: "add-comparison-node", ref: "submission:s1" });
    const three = executeBrowseCommand(two, { name: "add-comparison-node", ref: "submission:s2" });
    expect(executeBrowseCommand(three, { name: "add-comparison-node", ref: "submission:s3" }).comparisonNodeRefs).toHaveLength(3);
    expect(executeBrowseCommand(three, { name: "remove-comparison-node", ref: "submission:s1" }).comparisonNodeRefs).toEqual(["baseline:b1", "submission:s2"]);
  });

  it("allows a human command to interrupt an external browsing operation", () => {
    const runtime = new BrowseCommandRuntime(initialBrowseState, window);
    const signal = runtime.beginExternalOperation();
    expect(runtime.snapshot.externalOperationActive).toBe(true);
    runtime.execute({ name: "select-node", nodeKey: "device" }, "human");
    expect(signal.aborted).toBe(true);
    expect(runtime.snapshot.externalOperationActive).toBe(false);
    expect(new URL(window.location.href).searchParams.get("node")).toBe("device");
  });

  it("marks external state as finished when the caller completes", () => {
    const runtime = new BrowseCommandRuntime(initialBrowseState, window);
    const signal = runtime.beginExternalOperation();
    runtime.execute({ name: "set-search", search: "relay" }, "external");
    runtime.finishExternalOperation(signal);
    expect(runtime.snapshot.externalOperationActive).toBe(false);
    expect(decodeBrowseState(window.location.search).search).toBe("relay");
  });
});
