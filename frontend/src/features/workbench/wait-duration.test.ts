import { describe, expect, it } from "vitest";
import { formatWaitDuration } from "./wait-duration";

describe("formatWaitDuration", () => {
  it("shows seconds below one minute", () => {
    expect(formatWaitDuration(0)).toBe("0 秒");
    expect(formatWaitDuration(59)).toBe("59 秒");
  });

  it("shows minutes and seconds from one minute", () => {
    expect(formatWaitDuration(60)).toBe("1 分 0 秒");
    expect(formatWaitDuration(61)).toBe("1 分 1 秒");
    expect(formatWaitDuration(3599)).toBe("59 分 59 秒");
  });

  it("shows hours, minutes, and seconds from one hour", () => {
    expect(formatWaitDuration(3600)).toBe("1 小时 0 分 0 秒");
    expect(formatWaitDuration(3661)).toBe("1 小时 1 分 1 秒");
  });

  it("clamps invalid negative or fractional input", () => {
    expect(formatWaitDuration(-4)).toBe("0 秒");
    expect(formatWaitDuration(12.9)).toBe("12 秒");
  });
});
