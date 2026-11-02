import { describe, expect, it } from "vitest";
import { canonicalJson, normalizeSha256, Sha256 } from "./sha256";

describe("incremental bundle SHA-256", () => {
  it("matches standard empty, short and multi-block digests", () => {
    expect(new Sha256().digest()).toBe("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    const encoder = new TextEncoder();
    expect(new Sha256().update(encoder.encode("abc")).digest()).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    const hash = new Sha256();
    hash.update(encoder.encode("a".repeat(31))).update(encoder.encode("b".repeat(100))).update(encoder.encode("c".repeat(101)));
    expect(hash.digest()).toBe("13bcc686c814d5fb63298a036a433eb76e7ce3bce8d2a4a9b637e3135753ed36");
  });

  it("canonicalizes object key order and normalizes quoted ETags", () => {
    expect(canonicalJson({ z: 1, a: { y: 2, b: 3 } })).toBe('{"a":{"b":3,"y":2},"z":1}');
    expect(normalizeSha256('W/"sha256:ABCDEF"')).toBe("abcdef");
  });
});
