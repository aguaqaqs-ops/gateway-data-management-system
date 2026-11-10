import { describe, expect, it } from "vitest";
import { bundleLoadErrorCode, removeEntry } from "./local-bundle";
import { BundleIntegrityError } from "./posix-tar";

describe("bundle loading error classification", () => {
  it("uses the integrity error type rather than matching message text", () => {
    expect(bundleLoadErrorCode(new BundleIntegrityError("transport failed"))).toBe("BUNDLE_INTEGRITY_MISMATCH");
    expect(bundleLoadErrorCode(new Error("bundle 校验完整性失败"))).toBe("BUNDLE_LOAD_FAILED");
  });
});

function handleWith(remove: () => Promise<void>): FileSystemDirectoryHandle {
  return { removeEntry: remove } as unknown as FileSystemDirectoryHandle;
}

describe("OPFS removeEntry retry", () => {
  it("succeeds after two transient NoModificationAllowedError failures", async () => {
    let calls = 0;
    const handle = handleWith(async () => {
      calls += 1;
      if (calls < 3) throw new DOMException("locked", "NoModificationAllowedError");
    });
    await removeEntry(handle, "artifact");
    expect(calls).toBe(3);
  });

  it("throws a persistent NoModificationAllowedError after the last attempt", async () => {
    let calls = 0;
    const handle = handleWith(async () => {
      calls += 1;
      throw new DOMException("locked", "NoModificationAllowedError");
    });
    await expect(removeEntry(handle, "artifact")).rejects.toMatchObject({ name: "NoModificationAllowedError" });
    expect(calls).toBe(5);
  });

  it("throws other DOMExceptions immediately", async () => {
    let calls = 0;
    const handle = handleWith(async () => {
      calls += 1;
      throw new DOMException("denied", "NotAllowedError");
    });
    await expect(removeEntry(handle, "artifact")).rejects.toMatchObject({ name: "NotAllowedError" });
    expect(calls).toBe(1);
  });

  it("returns on NotFoundError without retrying", async () => {
    let calls = 0;
    const handle = handleWith(async () => {
      calls += 1;
      throw new DOMException("missing", "NotFoundError");
    });
    await removeEntry(handle, "artifact");
    expect(calls).toBe(1);
  });
});
