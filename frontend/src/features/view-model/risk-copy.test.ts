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
    for (const evidence of [[], [["coverage", "ROW_COUNTS"]], [["count", 3]]] as Array<
      Array<[string, unknown]>
    >) {
      const text = describeRiskReason("ROW_MODIFIED", evidence);
      expect(text).toBe("修改了数据行（未确认只涉及名称或描述，按普通修改评估）。");
      expect(text).not.toMatch(/以外|低风险/);
    }
    expect(describeRiskReason("ORDERED_RISK_UNKNOWN")).toMatch(/无法可靠判定/);
  });

  it("describes blank-point changes concisely without implying individual positions", () => {
    expect(
      describeRiskReason("ORDERED_TAIL_BLANK_INTERVAL", [
        ["count", 2],
        ["side", "CURRENT"],
      ]),
    ).toBe("新增了空点。");
    const middleCases: Array<[Array<[string, unknown]>, string]> = [
      [
        [
          ["count", 2],
          ["side", "CURRENT"],
        ],
        "新增了空点，需要复核。",
      ],
      [
        [
          ["count", 1],
          ["side", "BEFORE"],
        ],
        "删除了空点，需要复核。",
      ],
      [
        [
          ["count", 2],
          ["side", "UNKNOWN"],
        ],
        "空点发生变化，需要复核。",
      ],
      [[], "空点发生变化，需要复核。"],
    ];
    for (const [evidence, expected] of middleCases) {
      expect(describeRiskReason("ORDERED_MIDDLE_BLANK_INTERVAL", evidence)).toBe(expected);
    }
  });
});
