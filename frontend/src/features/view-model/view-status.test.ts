import { describe, expect, it } from "vitest";
import { presentViewStatus } from "./view-status";

describe("view-level status copy", () => {
  it("shows unchanged or updated and puts degraded, failed, and diagnostic counts in the tooltip", () => {
    expect(presentViewStatus({ changed_table_count: 0 }, 0).text).toBe("一致");
    expect(presentViewStatus({ changed_table_count: 2 }, 0).text).toBe("更新");
    const degraded = presentViewStatus({ degraded_table_count: 2 }, 0);
    expect(degraded.text).toBe("一致");
    expect(degraded.tooltipItems).toContain("2 张表降级比较");
    const failed = presentViewStatus({ failed_table_count: 1 }, 0);
    expect(failed.text).toBe("一致");
    expect(failed.tooltipItems).toContain("1 张表比较失败");
    expect(presentViewStatus({ degraded_table_count: 2, failed_table_count: 1 }, 3).tooltipItems).toEqual([
      "2 张表降级比较", "1 张表比较失败", "3 张表有比较提示",
    ]);
  });
});
