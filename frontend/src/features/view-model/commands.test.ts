import { beforeEach, describe, expect, it } from "vitest";
import { BrowseCommandRuntime, decodeBrowseState, encodeBrowseState, executeBrowseCommand, initialBrowseState } from "./commands";

describe("read-only browsing commands and URL state", () => {
  beforeEach(() => window.history.replaceState(null, "", "/"));

  it("round-trips view, navigation, filters, search and comparison refs through the URL", () => {
    const state = executeBrowseCommand(initialBrowseState, { name: "select-node", nodeKey: "device:addr:1" });
    const withTab = executeBrowseCommand(state, { name: "select-tab", tabKey: "measurements" });
    const filtered = executeBrowseCommand(withTab, { name: "set-only-interesting", enabled: true });
    const expanded = executeBrowseCommand(filtered, { name: "toggle-group", groupKey: "SECONDARY_DEVICES" });
    const compared = executeBrowseCommand(expanded, { name: "add-comparison-node", ref: "submission:s1" });
    const encoded = encodeBrowseState(compared);
    expect(decodeBrowseState(encoded)).toEqual(compared);
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
