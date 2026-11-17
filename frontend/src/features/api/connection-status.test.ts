import { describe, expect, it } from "vitest";
import {
  connectionStatusLabel,
  getConnectionStatus,
  reportConnectionStatus,
} from "./connection-status";

describe("API connection status copy", () => {
  it("shows connected, interrupted, or no indicator before the first request", () => {
    expect(connectionStatusLabel("connected")).toBe("已连接");
    expect(connectionStatusLabel("interrupted")).toBe("连接中断");
    expect(connectionStatusLabel(null)).toBeNull();
  });

  it("retains the last request status for indicators mounted after the request", () => {
    reportConnectionStatus("connected");
    expect(getConnectionStatus()).toBe("connected");
    reportConnectionStatus("interrupted");
    expect(getConnectionStatus()).toBe("interrupted");
  });
});
