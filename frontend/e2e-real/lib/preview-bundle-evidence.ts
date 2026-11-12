import { digestHex, parseBundleTar, type ParsedBundle } from "./tar";

export interface EvidenceIdentity {
  token: string;
  businessProjectId: string;
  gatewayDeviceExternalKey: string;
}

export interface BundleDownload {
  body: Buffer;
  contentLength: string | null;
  contentType: string | null;
  etag: string | null;
}

/** Test-only evidence from actual downloads; neither an OPFS marker nor a URL
 * can register a verified bundle. Context and current credentials bound reuse.
 */
export class PreviewBundleEvidence {
  private readonly contexts = new WeakMap<object, Map<string, ParsedBundle>>();

  async resolve(options: {
    context: object;
    identity: EvidenceIdentity;
    authorizedDigest: string;
    uiReady: boolean;
    opfsComplete: boolean;
    download?: BundleDownload;
  }): Promise<{ bundle: ParsedBundle; source: "download" | "cache" }> {
    const digest = digestHex(options.authorizedDigest);
    if (!/^[a-f0-9]{64}$/.test(digest)) throw new Error("current authorized Preview digest is invalid");
    if (!options.uiReady || !options.opfsComplete) throw new Error("Preview UI and complete OPFS installation are required");
    const { token, businessProjectId, gatewayDeviceExternalKey } = options.identity;
    // JSON tuple avoids ambiguous separators; never log this credential key.
    const key = JSON.stringify([token, businessProjectId, gatewayDeviceExternalKey, digest]);
    if (options.download) {
      if (options.download.contentType?.split(";", 1)[0]?.trim() !== "application/x-tar") throw new Error("bundle Content-Type is not application/x-tar");
      if (options.download.contentLength !== String(options.download.body.byteLength)) throw new Error("bundle Content-Length differs from received bytes");
      if (options.download.etag !== `"${options.authorizedDigest}"`) throw new Error("bundle ETag differs from the quoted authorized digest");
      const bundle = await parseBundleTar(options.download.body, {
        contentLength: options.download.contentLength, etag: options.download.etag,
        expectedBundleDigest: options.authorizedDigest,
      });
      let records = this.contexts.get(options.context);
      if (!records) { records = new Map(); this.contexts.set(options.context, records); }
      records.set(key, bundle);
      return { bundle, source: "download" };
    }
    const bundle = this.contexts.get(options.context)?.get(key);
    if (!bundle) throw new Error("OPFS cache has no strictly verified download in this context and session scope");
    return { bundle, source: "cache" };
  }
}
