// @vitest-environment node
import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";
import { PreviewBundleEvidence, type BundleDownload } from "./preview-bundle-evidence";

const identity = { token: "test-only-session", businessProjectId: "project-a", gatewayDeviceExternalKey: "device-a" };
const ready = { uiReady: true, opfsComplete: true };
async function fixture(name = "preview-full"): Promise<{ digest: string; download: BundleDownload }> {
  const body = await readFile(`src/test/fixtures/generated/${name}.tar`);
  const size = Number.parseInt(body.subarray(124, 136).toString().replace(/\0.*$/, "").trim(), 8);
  const manifest = JSON.parse(body.subarray(512, 512 + size).toString()) as { bundle_digest: string };
  return { digest: manifest.bundle_digest, download: { body, contentLength: String(body.byteLength), contentType: "application/x-tar", etag: `"${manifest.bundle_digest}"` } };
}

describe("Preview journey evidence preserves transport checks and permits proven cache reuse", () => {
  it("validates the first download and reuses its result for an authorized identical digest", async () => {
    const { digest, download } = await fixture();
    const evidence = new PreviewBundleEvidence();
    const options = { context: {}, identity, authorizedDigest: digest, ...ready };
    const first = await evidence.resolve({ ...options, download });
    expect(first.source).toBe("download");
    const second = await evidence.resolve(options);
    expect(second.source).toBe("cache");
    expect(second.bundle).toBe(first.bundle);
  });

  it("requires and validates a new download when the authorized digest changes", async () => {
    const a = await fixture(), b = await fixture("preview-modified-only");
    const evidence = new PreviewBundleEvidence();
    const options = { context: {}, identity, ...ready };
    await evidence.resolve({ ...options, authorizedDigest: a.digest, download: a.download });
    expect(a.digest).not.toBe(b.digest);
    await expect(evidence.resolve({ ...options, authorizedDigest: b.digest })).rejects.toThrow("no strictly verified download");
    const next = await evidence.resolve({ ...options, authorizedDigest: b.digest, download: b.download });
    expect(next.source).toBe("download");
    expect(next.bundle.manifest.bundle_digest).toBe(b.digest);
  });

  it("never promotes an unverified OPFS marker/UI into a verified download", async () => {
    const { digest } = await fixture();
    await expect(new PreviewBundleEvidence().resolve({ context: {}, identity, authorizedDigest: digest, ...ready })).rejects.toThrow("no strictly verified download");
  });

  it("cannot register a truncated archive even when its HTTP length matches", async () => {
    const { digest, download } = await fixture();
    const evidence = new PreviewBundleEvidence();
    const options = { context: {}, identity, authorizedDigest: digest, ...ready };
    const body = download.body.subarray(0, download.body.length - 1024);
    await expect(evidence.resolve({ ...options, download: { ...download, body, contentLength: String(body.length) } })).rejects.toThrow();
    await expect(evidence.resolve(options)).rejects.toThrow("no strictly verified download");
  });

  it.each(["context", "token", "businessProjectId", "gatewayDeviceExternalKey"] as const)("keeps verified evidence isolated by %s", async (field) => {
    const { digest, download } = await fixture();
    const evidence = new PreviewBundleEvidence();
    const options = { context: {}, identity, authorizedDigest: digest, ...ready };
    await evidence.resolve({ ...options, download });
    const changed = field === "context" ? { ...options, context: {} } : { ...options, identity: { ...identity, [field]: "different-scope-or-session" } };
    await expect(evidence.resolve(changed)).rejects.toThrow("no strictly verified download");
  });

  it.each(["uiReady", "opfsComplete"] as const)("requires %s even for a previously verified digest", async (field) => {
    const { digest, download } = await fixture();
    const evidence = new PreviewBundleEvidence();
    const options = { context: {}, identity, authorizedDigest: digest, ...ready };
    await evidence.resolve({ ...options, download });
    await expect(evidence.resolve({ ...options, [field]: false })).rejects.toThrow("complete OPFS");
  });

  it.each([
    ["length", { contentLength: "1024" }, "Content-Length"],
    ["etag", { etag: '"sha256:' + "0".repeat(64) + '"' }, "ETag"],
    ["media type", { contentType: "application/json" }, "Content-Type"],
  ] as const)("does not bypass invalid download %s with an existing cache record", async (_name, metadata, message) => {
    const { digest, download } = await fixture();
    const evidence = new PreviewBundleEvidence();
    const options = { context: {}, identity, authorizedDigest: digest, ...ready };
    await evidence.resolve({ ...options, download });
    await expect(evidence.resolve({ ...options, download: { ...download, ...metadata } })).rejects.toThrow(message);
  });
});
