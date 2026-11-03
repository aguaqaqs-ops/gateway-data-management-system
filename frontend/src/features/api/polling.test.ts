import { describe, expect, it, vi } from "vitest";
import type { components } from "./generated/openapi";
import type { GatewayApi } from "./client";
import { ApiError } from "./authenticated-fetch";
import { HISTORY_COMPARE_STATUS_SCENARIOS, MANUAL_RECOVERY_TO_FAILED, MANUAL_RECOVERY_TO_SUCCESS, OPERATION_TERMINAL_RESPONSES, TEST_OPERATION_RUNNING, TEST_OPERATION_SUCCEEDED } from "../dev/mock-data";
import { OperationFailedError, PollingConnectionLostError, pollHistoryCompare, pollOperation } from "./journeys";

type HistoryCompare = components["schemas"]["HistoryCompareResultResponse"];

describe("operation polling", () => {
  it("treats a status-request timeout as still running", async () => {
    const api = {
      getOperation: vi.fn().mockRejectedValueOnce(new DOMException("slow", "TimeoutError")).mockResolvedValueOnce(TEST_OPERATION_RUNNING).mockResolvedValueOnce(TEST_OPERATION_SUCCEEDED),
    } as unknown as GatewayApi;
    const wait = vi.fn(async () => undefined);
    const updates: string[] = [];
    const result = await pollOperation(api, "op-1", { intervalMs: 7, wait, onUpdate: (value) => updates.push(value.status) });
    expect(api.getOperation).toHaveBeenCalledTimes(3);
    expect(updates).toEqual(["RUNNING", "SUCCEEDED"]);
    expect(wait).toHaveBeenCalledTimes(2);
    expect(result.status).toBe("SUCCEEDED");
  });

  it("uses capped backoff for network, 5xx and 429 failures, then reports a lost connection", async () => {
    const api = { getOperation: vi.fn()
      .mockRejectedValueOnce(new TypeError("network unavailable"))
      .mockRejectedValueOnce(new ApiError("busy", 503))
      .mockRejectedValueOnce(new ApiError("limited", 429)) } as unknown as GatewayApi;
    const delays: number[] = [];
    const onConnectionStatus = vi.fn();
    await expect(pollOperation(api, "operation-poll", {
      intervalMs: 25, maxTransientRetries: 2, wait: async (delay) => { delays.push(delay); }, onConnectionStatus,
    })).rejects.toBeInstanceOf(PollingConnectionLostError);
    expect(api.getOperation).toHaveBeenCalledTimes(3);
    expect(delays).toEqual([25, 50]);
    expect(onConnectionStatus).toHaveBeenLastCalledWith("interrupted");
  });

  it("keeps MANUAL_RECOVERY_REQUIRED nonterminal and polls at 30 seconds until success", async () => {
    const api = { getOperation: vi.fn()
      .mockResolvedValueOnce(MANUAL_RECOVERY_TO_SUCCESS[0])
      .mockResolvedValueOnce(MANUAL_RECOVERY_TO_SUCCESS[1])
      .mockResolvedValueOnce(MANUAL_RECOVERY_TO_SUCCESS[2]) } as unknown as GatewayApi;
    const delays: number[] = [];
    const states: string[] = [];
    const result = await pollOperation(api, "operation-manual-success", {
      intervalMs: 5, wait: async (delay) => { delays.push(delay); }, onUpdate: (value) => states.push(value.status),
    });
    expect(states).toEqual(["MANUAL_RECOVERY_REQUIRED", "RUNNING", "SUCCEEDED"]);
    expect(delays).toEqual([30_000, 5]);
    expect(result.status).toBe("SUCCEEDED");
  });

  it("continues polling after MANUAL_RECOVERY_REQUIRED when recovery ends in failure", async () => {
    const api = { getOperation: vi.fn()
      .mockResolvedValueOnce(MANUAL_RECOVERY_TO_FAILED[0])
      .mockResolvedValueOnce(MANUAL_RECOVERY_TO_FAILED[1]) } as unknown as GatewayApi;
    const delays: number[] = [];
    const states: string[] = [];
    await expect(pollOperation(api, "operation-manual-failed", {
      intervalMs: 9, wait: async (delay) => { delays.push(delay); }, onUpdate: (value) => states.push(value.status),
    })).rejects.toBeInstanceOf(OperationFailedError);
    expect(states).toEqual(["MANUAL_RECOVERY_REQUIRED", "FAILED"]);
    expect(delays).toEqual([30_000]);
  });

  it.each(["FAILED", "CANCELLED", "SUPERSEDED"] as const)("recognizes %s as a final operation status", async (status) => {
    const response = OPERATION_TERMINAL_RESPONSES[status];
    const api = { getOperation: vi.fn().mockResolvedValue(response) } as unknown as GatewayApi;
    await expect(pollOperation(api, response.operation_id, { wait: async () => undefined })).rejects.toBeInstanceOf(OperationFailedError);
    expect(api.getOperation).toHaveBeenCalledTimes(1);
  });

  it("polls history-compares through only its five contract statuses", async () => {
    const statuses: HistoryCompare["status"][] = ["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"];
    expect(statuses).toEqual(["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]);
    const api = { getHistoryCompare: vi.fn()
      .mockResolvedValueOnce(HISTORY_COMPARE_STATUS_SCENARIOS.QUEUED)
      .mockResolvedValueOnce(HISTORY_COMPARE_STATUS_SCENARIOS.RUNNING)
      .mockResolvedValueOnce(HISTORY_COMPARE_STATUS_SCENARIOS.SUCCEEDED) } as unknown as GatewayApi;
    const wait = vi.fn(async () => undefined);
    const result = await pollHistoryCompare(api, HISTORY_COMPARE_STATUS_SCENARIOS.QUEUED.operation_id, { intervalMs: 4, wait });
    expect(api.getHistoryCompare).toHaveBeenCalledTimes(3);
    expect(wait).toHaveBeenCalledTimes(2);
    expect(result.status).toBe("SUCCEEDED");
  });

  it.each(["SUCCEEDED", "FAILED", "CANCELLED"] as const)("returns terminal history-compare status %s", async (status) => {
    const response = HISTORY_COMPARE_STATUS_SCENARIOS[status];
    const api = { getHistoryCompare: vi.fn().mockResolvedValue(response) } as unknown as GatewayApi;
    const result = await pollHistoryCompare(api, response.operation_id, { wait: async () => undefined });
    expect(api.getHistoryCompare).toHaveBeenCalledTimes(1);
    expect(result.status).toBe(status);
  });
});
