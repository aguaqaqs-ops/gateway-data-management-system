import { describe, expect, it, vi } from "vitest";
import type { components } from "./generated/openapi";
import { readHistoryCompareIntent, requestWithTimeout, resolveHistoryCompareIntent } from "./idempotency";

type Request = components["schemas"]["HistoryCompareAcceptRequest"];

describe("History comparison intent keys", () => {
  it("reuses the stored key after a timeout and creates a key when the selected nodes change", async () => {
    const createKey = vi.fn().mockReturnValueOnce("intent-key-1").mockReturnValueOnce("intent-key-2");
    const viewDiffRequest = { nodes: [
      { ref_kind: "baseline_node", ref_id: "baseline-parent" },
      { ref_kind: "submission", ref_id: "submission-current" },
    ] } satisfies Request;
    const otherRequest = { nodes: [
      { ref_kind: "baseline_node", ref_id: "baseline-other" },
      { ref_kind: "submission", ref_id: "submission-other" },
    ] } satisfies Request;
    const first = resolveHistoryCompareIntent(null, viewDiffRequest, createKey);
    const start = vi.fn()
      .mockImplementationOnce(() => new Promise((resolve) => globalThis.setTimeout(() => resolve({ operation_id: "op-1" }), 30)))
      .mockResolvedValueOnce({ operation_id: "op-1" });
    const firstRequest = start(first.request, first.key);

    const timeoutPromise = requestWithTimeout(firstRequest, 2);
    await expect(timeoutPromise).rejects.toMatchObject({ name: "TimeoutError" });
    await firstRequest.catch(() => undefined);
    const restored = readHistoryCompareIntent(JSON.stringify(first));
    const retry = resolveHistoryCompareIntent(restored, viewDiffRequest, createKey);
    await expect(requestWithTimeout(start(retry.request, retry.key), 100)).resolves.toEqual({ operation_id: "op-1" });

    expect(retry.key).toBe(first.key);
    expect(start.mock.calls.map((call) => call[1])).toEqual([first.key, first.key]);
    const changed = resolveHistoryCompareIntent(retry, otherRequest, createKey);
    expect(changed.key).not.toBe(first.key);
    expect(changed.request).toEqual(otherRequest);
    expect(createKey).toHaveBeenCalledTimes(2);
  });

  it("rejects malformed saved intents instead of retrying an unrelated request", () => {
    expect(readHistoryCompareIntent("not json")).toBeNull();
    expect(readHistoryCompareIntent(JSON.stringify({ key: "x", request: { nodes: [] } }))).toBeNull();
  });
});
