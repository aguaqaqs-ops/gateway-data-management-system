import { describe, expect, it, vi } from "vitest";
import type { components } from "./generated/openapi";
import { createIdempotentIntent } from "./idempotency";
import { testHistoryCompareAcceptance } from "../dev/mock-data";

describe("idempotency keys follow user intent", () => {
  it("reuses a key for retrying one intent and creates a new key for another", async () => {
    const createKey = vi.fn().mockReturnValueOnce("intent-key-1").mockReturnValueOnce("intent-key-2");
    const firstRequest = { nodes: [
      { ref_kind: "baseline_node", ref_id: "baseline-a" },
      { ref_kind: "submission", ref_id: "submission-a" },
    ] } satisfies components["schemas"]["HistoryCompareAcceptRequest"];
    const secondRequest = { nodes: [
      { ref_kind: "baseline_node", ref_id: "baseline-b" },
      { ref_kind: "submission", ref_id: "submission-b" },
    ] } satisfies components["schemas"]["HistoryCompareAcceptRequest"];
    const firstIntent = createIdempotentIntent(firstRequest, createKey);
    const start = vi.fn().mockRejectedValueOnce(new TypeError("request timed out")).mockResolvedValueOnce(testHistoryCompareAcceptance("operation-a"));
    await expect(start(firstIntent.request, firstIntent.key)).rejects.toThrow("request timed out");
    await expect(start(firstIntent.request, firstIntent.key)).resolves.toEqual(testHistoryCompareAcceptance("operation-a"));
    const secondIntent = createIdempotentIntent(secondRequest, createKey);
    await start(secondIntent.request, secondIntent.key);
    expect(start.mock.calls.map((call) => call[1])).toEqual(["intent-key-1", "intent-key-1", "intent-key-2"]);
    expect(createKey).toHaveBeenCalledTimes(2);
  });
});
