import { describe, expect, it } from "vitest";
import { describeRiskReason, RISK_REASON_CODES } from "./risk-copy";

describe("risk reason copy", () => {
  it("has Chinese user copy for every v1 reason and a safe fallback for future codes", () => {
    for (const code of RISK_REASON_CODES) {
      expect(describeRiskReason(code)).not.toBe("风险原因待说明。");
    }
    expect(describeRiskReason("FUTURE_REASON")).toBe("风险原因待说明。");
  });
});
