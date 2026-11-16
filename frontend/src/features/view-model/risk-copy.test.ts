import { describe, expect, it } from "vitest";
import { describeRiskReason, RISK_REASON_CODES } from "./risk-copy";

describe("risk reason copy", () => {
  it("has Chinese user copy for every v1 reason and a safe fallback for future codes", () => {
    for (const code of RISK_REASON_CODES) {
      expect(describeRiskReason(code)).not.toBe("风险原因待说明。");
    }
    expect(describeRiskReason("FUTURE_REASON")).toBe("风险原因待说明。");
  });

  it("describes name/description-only changes as LOW without claiming other rules are low", () => {
    expect(describeRiskReason("STANDARD_NAME_UPDATE")).toMatch(/名称或描述.*低风险/);
    expect(describeRiskReason("ORDERED_NAME_UPDATE")).toMatch(/名称或描述.*低风险/);
    // ROW_MODIFIED also covers rows whose changed columns are unknown (missing evidence, COUNTS_ONLY aggregate).
    for (const evidence of [[], [["coverage", "ROW_COUNTS"]], [["count", 3]]] as Array<Array<[string, unknown]>>) {
      const text = describeRiskReason("ROW_MODIFIED", evidence);
      expect(text).toBe("修改了数据行（未确认只涉及名称或描述，按普通修改评估）。");
      expect(text).not.toMatch(/以外|低风险/);
    }
    expect(describeRiskReason("ORDERED_RISK_UNKNOWN")).toMatch(/无法可靠判定/);
  });

  it("states the net blank-point count of an interval region, never a per-position change", () => {
    expect(describeRiskReason("ORDERED_TAIL_BLANK_INTERVAL", [["count", 2], ["side", "CURRENT"]])).toBe("有序表末尾的空点区间净增 2 个空点，其后没有保留的有效测点。");
    expect(describeRiskReason("ORDERED_MIDDLE_BLANK_INTERVAL", [["count", 1], ["side", "BEFORE"]])).toMatch(/^有序表中间的空点区间净减 1 个空点，/);
    expect(describeRiskReason("ORDERED_MIDDLE_BLANK_INTERVAL")).toMatch(/^在有序表中间插入或删除了空点/);
  });
});
