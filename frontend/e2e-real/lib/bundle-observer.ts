import type { Page, Response } from "@playwright/test";
import { PreviewBundleEvidence, type BundleDownload, type EvidenceIdentity } from "./preview-bundle-evidence";

const verified = new PreviewBundleEvidence();

/** Capture bytes at the response event, before any full-page navigation.
 * Failed reads are retained as errors, never dropped in favour of a cache hit.
 */
export function captureBundleDownloads(page: Page, session: EvidenceIdentity) {
  const identity = Object.freeze({ token: session.token, businessProjectId: session.businessProjectId,
    gatewayDeviceExternalKey: session.gatewayDeviceExternalKey });
  const responses: Array<{ path: string; status: number; result: Promise<{ download: BundleDownload } | { error: unknown }> }> = [];
  const listener = (response: Response): void => {
    if (response.request().method() !== "GET" || !new URL(response.url()).pathname.endsWith("/bundle")) return;
    responses.push({ path: new URL(response.url()).pathname, status: response.status(),
      result: response.body().then((body) => ({ download: { body: Buffer.from(body),
        contentType: response.headers()["content-type"] ?? null, contentLength: response.headers()["content-length"] ?? null,
        etag: response.headers()["etag"] ?? null } }), (error: unknown) => ({ error })) });
  };
  page.on("response", listener);
  const assertIdentity = async (): Promise<void> => {
    const matches = await page.evaluate((expected) => {
      const current = window.__gatewaySession;
      return current?.accessToken === expected.token && current.businessProjectId === expected.businessProjectId
        && current.gatewayDeviceExternalKey === expected.gatewayDeviceExternalKey;
    }, identity);
    if (!matches) throw new Error("browser session changed; refusing bundle evidence reuse");
  };
  return {
    assertIdentity,
    async consume(options: { requestPath: string; authorizedDigest: string; uiReady: boolean; opfsComplete: boolean }) {
      await assertIdentity();
      const matching = responses.filter((response) => response.path === options.requestPath);
      let evidence: Awaited<ReturnType<PreviewBundleEvidence["resolve"]>> | undefined;
      let etag: string | null = null;
      for (const response of matching) {
        if (response.status !== 200) throw new Error(`bundle HTTP ${response.status}`);
        const result = await response.result;
        if ("error" in result) throw result.error;
        evidence = await verified.resolve({ context: page.context(), identity, ...options, download: result.download });
        etag = result.download.etag;
      }
      evidence ??= await verified.resolve({ context: page.context(), identity, ...options });
      await assertIdentity();
      return { ...evidence, etag, downloadCount: matching.length };
    },
    dispose: () => { page.off("response", listener); },
  };
}

export type BundleObservation = ReturnType<typeof captureBundleDownloads>;
