import { describe, expect, it } from "vitest";
import { ApiError } from "../api/authenticated-fetch";
import { describeHistoryReadError, describeHistoryStartError } from "./history-compare-errors";

const START_CASES: Array<[string, ApiError, { code: string; retry: "same" | "new" | null; operationIds: string[] }]> = [
  ["fingerprint conflict needs a new key", new ApiError("conflict", 409, "IDEMPOTENCY_CONFLICT", { idempotency_key: "k" }), { code: "IDEMPOTENCY_CONFLICT", retry: "new", operationIds: [] }],
  ["expired original key needs a new key", new ApiError("expired", 409, "HISTORY_COMPARE_REQUEST_EXPIRED"), { code: "HISTORY_COMPARE_REQUEST_EXPIRED", retry: "new", operationIds: [] }],
  ["scope limit offers at most two active jobs", new ApiError("limit", 409, "HISTORY_COMPARE_SCOPE_LIMIT", { operation_ids: ["op-a", "op-b", "op-c", 7] }), { code: "HISTORY_COMPARE_SCOPE_LIMIT", retry: "same", operationIds: ["op-a", "op-b"] }],
  ["alias limit points at the original job", new ApiError("alias", 429, "HISTORY_COMPARE_ALIAS_LIMIT", { operation_id: "op-a" }), { code: "HISTORY_COMPARE_ALIAS_LIMIT", retry: null, operationIds: ["op-a"] }],
  ["global queue full keeps the key", new ApiError("full", 429, "OPERATION_QUEUE_FULL"), { code: "OPERATION_QUEUE_FULL", retry: "same", operationIds: [] }],
  ["service not ready keeps the key", new ApiError("not ready", 503, "SERVICE_NOT_READY"), { code: "SERVICE_NOT_READY", retry: "same", operationIds: [] }],
  ["unreadable replay needs a new key", new ApiError("gone", 404, "ARTIFACT_UNAVAILABLE"), { code: "ARTIFACT_UNAVAILABLE", retry: "new", operationIds: [] }],
  ["binding integrity failure needs a new key", new ApiError("bad", 503, "HISTORY_INTEGRITY_FAILURE"), { code: "HISTORY_INTEGRITY_FAILURE", retry: "new", operationIds: [] }],
  ["bundle integrity failure needs a new key", new ApiError("bad", 503, "BUNDLE_INTEGRITY_FAILURE"), { code: "BUNDLE_INTEGRITY_FAILURE", retry: "new", operationIds: [] }],
  ["forbidden is not retried", new ApiError("no", 403, "SCOPE_FORBIDDEN"), { code: "SCOPE_FORBIDDEN", retry: null, operationIds: [] }],
];

describe("History compare failures", () => {
  it.each(START_CASES)("start: %s", (_name, cause, expected) => {
    expect(describeHistoryStartError(cause)).toMatchObject(expected);
  });

  it("start: a timeout may already be accepted, so the same key is retried", () => {
    expect(describeHistoryStartError(new DOMException("slow", "TimeoutError"))).toMatchObject({ code: "TimeoutError", retry: "same" });
  });

  it("read: an expired result asks for an explicit new compare", () => {
    expect(describeHistoryReadError(new ApiError("expired", 410, "HISTORY_COMPARE_RESULT_EXPIRED"))).toMatchObject({ code: "HISTORY_COMPARE_RESULT_EXPIRED", retry: "new" });
    expect(describeHistoryReadError(new ApiError("bad", 503, "BUNDLE_INTEGRITY_FAILURE"))).toMatchObject({ retry: "new" });
    expect(describeHistoryReadError(new ApiError("no", 403, "SCOPE_FORBIDDEN"))).toMatchObject({ retry: null });
  });
});
