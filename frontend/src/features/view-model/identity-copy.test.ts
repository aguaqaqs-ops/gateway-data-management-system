import { describe, expect, it } from "vitest";
import { identityStatusText } from "./identity-copy";

describe("project identity copy", () => {
  it("keeps missing assessment distinct from a different-project conclusion", () => {
    expect(identityStatusText(undefined)).toBe("项目身份评估不可用");
    expect(identityStatusText("DIFFERENT_PROJECT")).toBe("不同项目");
  });
});
