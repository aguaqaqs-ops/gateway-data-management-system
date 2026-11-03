import { describe, expect, it } from "vitest";
import { TEST_OPERATION_SUCCEEDED } from "../dev/mock-data";
import { operationElapsedSeconds } from "./OperationStatusPanel";

describe("operation status elapsed time", () => {
  it("uses server operation timestamps so elapsed time survives a page refresh", () => {
    const operation = { ...TEST_OPERATION_SUCCEEDED, created_at: "2026-11-03T09:00:00Z", started_at: "2026-11-03T09:00:12Z" };
    expect(operationElapsedSeconds(operation, Date.parse("2026-11-03T09:00:42Z"))).toBe(30);
  });

  it("falls back to created_at when the operation has not started", () => {
    const operation = { ...TEST_OPERATION_SUCCEEDED, created_at: "2026-11-03T09:00:00Z", started_at: null };
    expect(operationElapsedSeconds(operation, Date.parse("2026-11-03T09:00:07Z"))).toBe(7);
  });
});
