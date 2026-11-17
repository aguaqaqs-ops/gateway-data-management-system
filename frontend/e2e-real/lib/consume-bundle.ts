import { expect, type Page } from "@playwright/test";
import type { BundleObservation } from "./bundle-observer";
import { digestHex } from "./tar";
import { opfsBundleState, waitForDiffBrowsing } from "./ui";

export async function consumeBundle(
  page: Page,
  observation: BundleObservation,
  options: {
    requestPath: string;
    authorizedDigest: string;
    view?: "grid" | "replacement";
  },
) {
  await observation.assertIdentity();
  if (options.view === "replacement") {
    await expect(page.locator("section.replacement-browser")).toBeVisible({ timeout: 120_000 });
    await expect(page.getByText(/身份结论/)).toBeVisible();
  } else await waitForDiffBrowsing(page);
  const state = await opfsBundleState(page, digestHex(options.authorizedDigest));
  return observation.consume({
    ...options,
    uiReady: true,
    opfsComplete: state.hasDigestDir && state.hasManifest && state.hasCompleteMarker,
  });
}

/** Caller supplies a fresh authorized metadata read, never a URL digest. */
export async function consumePreviewBundle(
  page: Page,
  observation: BundleObservation,
  options: {
    workspaceId: string;
    previewId: string;
    operationId: string;
    uploadRevisionId: string;
    view?: "grid" | "replacement";
    readPreview: () => Promise<{
      status: number;
      body: {
        workspace_id: string;
        preview_result_id: string;
        operation_id: string;
        upload_revision_id: string;
        bundle_digest: string;
      };
    }>;
  },
) {
  await observation.assertIdentity();
  const authorized = await options.readPreview();
  expect(authorized.status, "current Preview authorization").toBe(200);
  expect(authorized.body.workspace_id).toBe(options.workspaceId);
  expect(authorized.body.preview_result_id).toBe(options.previewId);
  expect(authorized.body.operation_id).toBe(options.operationId);
  expect(authorized.body.upload_revision_id).toBe(options.uploadRevisionId);
  return consumeBundle(page, observation, {
    view: options.view,
    authorizedDigest: authorized.body.bundle_digest,
    requestPath: `/v1/workspaces/${encodeURIComponent(options.workspaceId)}/preview-results/${encodeURIComponent(options.previewId)}/bundle`,
  });
}
