import { describe, expect, it } from "vitest";
import { alignFormulaLines, renderFormulaLines } from "./formula-view";

describe("composite signal formula rendering", () => {
  it("renders production EXPRESS, POINT and DIGITAL ASTs as mapped formula lines", () => {
    const ast = {
      kind: "EXPRESS", operator: "|", name: "Device 65532:复合测点", children: [
        { kind: "EXPRESS", operator: "+", name: "嵌套命名表达式", children: [
          { kind: "EXPRESS", operator: "+", children: [
            { kind: "POINT", name: "Device 1:线路电流" }, { kind: "DIGITAL", value: "2" },
            { kind: "EXPRESS", operator: "+", children: [{ kind: "DIGITAL", value: "3" }, { kind: "POINT", name: "Device 2:测量电压" }] },
          ] },
          { kind: "EXPRESS", operator: "*", children: [{ kind: "DIGITAL", value: "4" }, { kind: "EXPRESS", operator: "*", children: [{ kind: "POINT", name: "Device 999:未映射测点" }, { kind: "DIGITAL", value: "5" }] }] },
        ] },
        { kind: "EXPRESS", operator: "", children: [{ kind: "DIGITAL", value: "6" }] },
        { kind: "EXPRESS", operator: "-", children: [{ kind: "POINT", name: "Device 1:线路电流" }] },
      ],
    };
    const lines = renderFormulaLines(JSON.stringify(ast), [{ dev_addr: 1, description: "线路保护装置 A" }, { dev_addr: 2, description: "测控装置" }]);
    expect(lines.map((line) => [line.kind, line.text])).toEqual([
      ["group", "| 嵌套命名表达式 ="],
      ["expression", "线路保护装置 A:线路电流"],
      ["expression", "+ 2"],
      ["expression", "+ 3"],
      ["expression", "+ 测控装置:测量电压"],
      ["group", "+ （* 分组）"],
      ["expression", "* 4"],
      ["expression", "* Device 999:未映射测点"],
      ["expression", "* 5"],
      ["expression", "| 6"],
      ["expression", "| - 线路保护装置 A:线路电流"],
    ]);
    expect(lines.at(-1)).toMatchObject({ kind: "expression", text: "| - 线路保护装置 A:线路电流", depth: 0 });
    expect(lines.some((line) => line.text.includes("- 分组"))).toBe(false);
    const productGroup = lines.find((line) => line.text === "+ （* 分组）");
    expect(productGroup).toMatchObject({ kind: "group", depth: 1 });
    expect(lines.filter((line) => line.text.startsWith("* ")).map((line) => line.depth)).toEqual([2, 2, 2]);
  });

  it("renders unary minus as the first child without an outer operator prefix", () => {
    const lines = renderFormulaLines({
      kind: "EXPRESS", operator: "", children: [
        { kind: "EXPRESS", operator: "-", children: [{ kind: "POINT", name: "Device 1:X" }] },
      ],
    });
    expect(lines.map((line) => line.text)).toEqual(["- X"]);
  });

  it("keeps the fixture's mixed-operator group and its History rows aligned", () => {
    const ast = (firstValue: string) => ({
      kind: "EXPRESS", operator: "|", children: [
        { kind: "EXPRESS", operator: "+", name: "嵌套命名表达式", children: [
          { kind: "EXPRESS", operator: "+", children: [
            { kind: "EXPRESS", operator: "+", children: [
              { kind: "POINT", name: "Device 1:线路电流" },
              { kind: "DIGITAL", value: "1" },
              { kind: "EXPRESS", operator: "+", children: [
                { kind: "DIGITAL", value: "2" },
                { kind: "POINT", name: "Device 2:测量电压" },
              ] },
            ] },
            { kind: "EXPRESS", operator: "*", children: [
              { kind: "DIGITAL", value: firstValue },
              { kind: "EXPRESS", operator: "*", children: [
                { kind: "POINT", name: "Device 2:测量电压" },
                { kind: "DIGITAL", value: "4" },
              ] },
            ] },
          ] },
        ] },
        { kind: "EXPRESS", operator: "|", children: [
          { kind: "POINT", name: "Device 999:未映射测点" },
          { kind: "DIGITAL", value: "5" },
        ] },
        { kind: "EXPRESS", operator: "", children: [{ kind: "DIGITAL", value: "6" }] },
        { kind: "EXPRESS", operator: "-", children: [{ kind: "POINT", name: "Device 1:线路电流" }] },
      ],
    });
    const devices = [{ dev_addr: 1, description: "线路保护装置 A" }, { dev_addr: 2, description: "测控装置" }];
    const before = renderFormulaLines(ast("3"), devices);
    const current = renderFormulaLines(ast("5"), devices);
    const aligned = alignFormulaLines(before, current);
    expect(aligned.find((line) => line.before?.text === "+ （* 分组）")).toMatchObject({
      state: "same", before: { kind: "group", depth: 1 }, current: { kind: "group", depth: 1 },
    });
    expect(aligned.find((line) => line.before?.text === "* 3")).toMatchObject({
      state: "changed", before: { text: "* 3", depth: 2 }, current: { text: "* 5", depth: 2 },
    });
    expect(aligned.find((line) => line.before?.text.includes("| - 线路保护装置 A:线路电流"))).toMatchObject({
      state: "same", before: { kind: "expression", depth: 0 }, current: { kind: "expression", depth: 0 },
    });
  });

  it("aligns changed, added and removed formula rows", () => {
    const before = renderFormulaLines({ kind: "EXPRESS", operator: "+", children: [{ kind: "DIGITAL", value: "1" }, { kind: "DIGITAL", value: "2" }] });
    const current = renderFormulaLines({ kind: "EXPRESS", operator: "+", children: [{ kind: "DIGITAL", value: "1" }, { kind: "DIGITAL", value: "3" }, { kind: "DIGITAL", value: "4" }] });
    expect(alignFormulaLines(before, current).map((line) => [line.before?.text ?? null, line.current?.text ?? null, line.state])).toEqual([
      ["1", "1", "same"], ["+ 2", "+ 3", "changed"], [null, "+ 4", "current-only"],
    ]);
    expect(alignFormulaLines(current, before).at(-1)?.state).toBe("before-only");
  });

  it("aligns by original POINT values so a device rename does not mark a formula change", () => {
    const expression = { kind: "EXPRESS", operator: "+", children: [{ kind: "POINT", name: "Device 1:温度" }, { kind: "DIGITAL", value: "2" }] };
    const before = renderFormulaLines(expression, [{ dev_addr: 1, description: "旧装置名" }]);
    const current = renderFormulaLines(expression, [{ dev_addr: 1, description: "新装置名" }]);
    const aligned = alignFormulaLines(before, current);
    expect(aligned.every((line) => line.state === "same")).toBe(true);
    expect(aligned[0]?.before?.text).toBe("旧装置名:温度");
    expect(aligned[0]?.current?.text).toBe("新装置名:温度");
  });
});
