import { describe, expect, it } from "vitest";
import { describeRiskReason, RISK_REASON_CODES } from "./risk-copy";

describe("risk reason copy", () => {
  it("has Chinese user copy for every v1 reason and a safe fallback for future codes", () => {
    for (const code of RISK_REASON_CODES) {
      expect(describeRiskReason(code)).not.toBe("风险原因待说明。");
    }
    expect(describeRiskReason("FUTURE_REASON")).toBe("风险原因待说明。");
  });

  it("says whether blank points were inserted or deleted when the evidence names the side", () => {
    expect(describeRiskReason("ORDERED_TAIL_BLANK_INTERVAL", [["count", 2], ["side", "CURRENT"]])).toBe("在有序表末尾插入了 2 个空点。");
    expect(describeRiskReason("ORDERED_MIDDLE_BLANK_INTERVAL", [["count", 1], ["side", "BEFORE"]])).toMatch(/^在有序表中间删除了 1 个空点，/);
    expect(describeRiskReason("ORDERED_MIDDLE_BLANK_INTERVAL")).toMatch(/^在有序表中间插入或删除了空点/);
  });
});
