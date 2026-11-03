import { describe, expect, it } from "vitest";
import { bundleLoadErrorCode } from "./local-bundle";
import { BundleIntegrityError } from "./posix-tar";

describe("bundle loading error classification", () => {
  it("uses the integrity error type rather than matching message text", () => {
    expect(bundleLoadErrorCode(new BundleIntegrityError("transport failed"))).toBe("BUNDLE_INTEGRITY_MISMATCH");
    expect(bundleLoadErrorCode(new Error("bundle 校验完整性失败"))).toBe("BUNDLE_LOAD_FAILED");
  });
});
