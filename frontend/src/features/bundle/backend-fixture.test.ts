import { describe, expect, it } from "vitest";
import { readLocalChangeRecords, readLocalTable, loadComparisonPresentation } from "./presentation";
import { MemoryBundleStore } from "./local-bundle";
import { installBundleTar, verifyBundleMetadata, type BundleClosure, type BundleManifest } from "./posix-tar";
import { bytesStream, readFixture } from "../../test/helpers";

describe("backend generated comparison bundle fixture", () => {
  it("matches backend digests, installs every product and browses both table sides locally", async () => {
    const [tar, manifestBytes, closureBytes] = await Promise.all([
      readFixture("src/test/fixtures/generated/golden-bundle.tar"),
      readFixture("src/test/fixtures/source/backend/manifest.json"),
      readFixture("src/test/fixtures/source/backend/artifact-closure.json"),
    ]);
    const backendManifest = JSON.parse(new TextDecoder().decode(manifestBytes)) as BundleManifest;
    const backendClosure = JSON.parse(new TextDecoder().decode(closureBytes)) as BundleClosure;

    const verified = await verifyBundleMetadata(backendManifest, backendClosure, backendManifest.bundle_digest);
    expect(verified.manifest.bundle_digest).toBe(backendManifest.bundle_digest);
    expect(verified.manifest.closure_manifest_digest).toBe(backendManifest.closure_manifest_digest);
    expect(verified.closure.bundle_manifest_digest).toBe(backendClosure.bundle_manifest_digest);

    const store = new MemoryBundleStore();
    const installed = await installBundleTar({
      body: bytesStream(tar),
      store,
      expectedBundleDigest: backendManifest.bundle_digest,
      etag: backendManifest.bundle_digest,
      contentLength: String(tar.byteLength),
    });
    expect(installed.manifest.bundle_digest).toBe(backendManifest.bundle_digest);
    const bundle = await store.open(installed.manifest.bundle_digest);
    expect(bundle).not.toBeNull();
    if (!bundle) throw new Error("backend fixture was not installed");

    const pair = backendManifest.pairs[0] as { pair_id: string } | undefined;
    if (!pair) throw new Error("backend fixture manifest has no comparison pair");
    const presentation = await loadComparisonPresentation(bundle, pair.pair_id);
    expect(presentation.view.groups[0]?.groupKey).toBe("SECONDARY_DEVICES");
    expect(presentation.view.groups[0]?.items[0]?.riskLevels).toContain("MEDIUM_LOW");
    expect(presentation.view.tables[0]?.riskLevel).toBe("MEDIUM_HIGH");

    const beforeRows = await readLocalTable(bundle, presentation, "device", "before", { columns: ["dev_addr"] });
    const currentRows = await readLocalTable(bundle, presentation, "device", "current", { columns: ["dev_addr"] });
    const records = await readLocalChangeRecords(bundle, presentation, "device", { columns: ["record_kind"] });
    expect(beforeRows).toHaveLength(3);
    expect(currentRows).toHaveLength(3);
    expect(records.map((row) => row.record_kind).sort()).toEqual(["ROW_ADDED", "ROW_DELETED", "ROW_MODIFIED"]);
  });
});
