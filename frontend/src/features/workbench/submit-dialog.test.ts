import { describe, expect, it } from "vitest";
import { ApiError } from "../api/authenticated-fetch";
import { describeSubmitError } from "./SubmitDialog";

const NO_CANONICAL_CHANGE_COPY =
  "本次组态与基线一致，没有可提交的变更。注释等展示信息的变化不单独保存，将随下一次业务变化一起保存。";

describe("submit NO_CANONICAL_CHANGE copy (F13)", () => {
  it("shows the exact agreed copy for NO_CANONICAL_CHANGE", () => {
    const failure = describeSubmitError(new ApiError("preview canonical business digest equals current business base", 409, "NO_CANONICAL_CHANGE"));
    expect(failure.title).toBe(NO_CANONICAL_CHANGE_COPY);
    expect(failure.code).toBe("NO_CANONICAL_CHANGE");
    expect(failure.retryable).toBe(true);
  });
});
