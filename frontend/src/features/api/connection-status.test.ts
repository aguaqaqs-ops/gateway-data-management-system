import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { connectionStatusLabel, getConnectionStatus, reportConnectionStatus } from "./connection-status";
import { ConnectionStatusIndicator } from "../../design-system/ConnectionStatusIndicator";

describe("API connection status copy", () => {
  it("shows connected, interrupted, or no indicator before the first request", () => {
    expect(connectionStatusLabel("connected")).toBe("已连接");
    expect(connectionStatusLabel("interrupted")).toBe("连接中断");
    expect(connectionStatusLabel(null)).toBeNull();
  });

  it("renders no request, connected, and interrupted states and hides connected on an error page", async () => {
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    const container = document.createElement("div");
    document.body.append(container);
    const root = createRoot(container);
    try {
      await act(async () => root.render(createElement(ConnectionStatusIndicator)));
      expect(container.querySelector('[role="status"]')).toBeNull();
      await act(async () => reportConnectionStatus("connected"));
      expect(container.textContent).toBe("已连接");
      await act(async () => root.render(createElement(ConnectionStatusIndicator, { hideConnected: true })));
      expect(container.querySelector('[role="status"]')).toBeNull();
      await act(async () => reportConnectionStatus("interrupted"));
      expect(container.textContent).toBe("连接中断");
    } finally {
      await act(async () => root.unmount());
      container.remove();
    }
  });

  it("retains the last request status for indicators mounted after the request", () => {
    reportConnectionStatus("connected");
    expect(getConnectionStatus()).toBe("connected");
    reportConnectionStatus("interrupted");
    expect(getConnectionStatus()).toBe("interrupted");
  });
});
