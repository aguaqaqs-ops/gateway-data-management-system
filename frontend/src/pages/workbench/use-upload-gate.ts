import { useCallback, useRef, useState } from "react";
import type { GatewayApi } from "../../features/api/client";
import { scopedStorage } from "../../features/api/scoped-storage";
import { currentGatewaySession, SessionChangedError } from "../../features/api/session";
import { ensureLocalBundle, OpfsBundleStore } from "../../features/bundle/local-bundle";
import type { UploadModeSnapshot } from "../../features/workbench/use-upload-mode";
import { pageUrl, type Schemas } from "./workbench-helpers";

export function useUploadGate(
  gatewayApi: GatewayApi,
  uploadMode: UploadModeSnapshot,
  options: {
    operationId: string | null;
    compareRefs: Schemas["HistoryCompareNodeRequest"][];
    selectedKey: string;
  },
) {
  const { operationId, compareRefs, selectedKey } = options;
  const [resumePreviewOperation] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get("operationId");
    return Boolean(
      id &&
      params.get("operationKind") !== "history-compare" &&
      scopedStorage.getItem("gateway-preview-operation") === id,
    );
  });
  const resumePending = useRef(resumePreviewOperation);
  const [uploadLocked, setUploadLocked] = useState(resumePreviewOperation);

  const resumePreviewFromOperation = useCallback(
    async (finishedOperationId: string) => {
      if (scopedStorage.getItem("gateway-preview-operation") !== finishedOperationId) return;
      const session = currentGatewaySession();
      try {
        const workspace = await gatewayApi.createWorkspace({
          business_project_id: session.businessProjectId,
          gateway_device_external_key: session.gatewayDeviceExternalKey,
        });
        const previewResultId = workspace.current_preview_result_id;
        if (!previewResultId) {
          setUploadLocked(false);
          return;
        }
        const preview = await gatewayApi.getPreviewResult(workspace.workspace_id, previewResultId);
        await ensureLocalBundle({
          store: new OpfsBundleStore(),
          expectedBundleDigest: preview.bundle_digest,
          fetchBundle: () => gatewayApi.getPreviewBundle(workspace.workspace_id, previewResultId),
        });
        gatewayApi.assertSession?.();
        resumePending.current = false;
        scopedStorage.removeItem("gateway-preview-operation");
        window.location.assign(
          pageUrl(
            "compare",
            {
              mode: "PREVIEW",
              workspaceId: workspace.workspace_id,
              previewResultId,
              workbenchNode: selectedKey,
            },
            compareRefs,
          ),
        );
      } catch (cause) {
        if (cause instanceof SessionChangedError) return;
        try {
          gatewayApi.assertSession?.();
        } catch {
          return;
        }
        resumePending.current = false;
        scopedStorage.removeItem("gateway-preview-operation");
        setUploadLocked(false);
      }
    },
    [compareRefs, selectedKey],
  );

  // The server names the newest active Preview of the current upload revision
  // (possibly started in another tab or terminal); it is a reattach hint, not
  // proof that it is the only one.
  const activePreviewOperationId =
    !operationId && !uploadLocked
      ? (uploadMode.workspace?.active_preview_operation_id ?? null)
      : null;
  const resumeActivePreview = (id: string) => {
    try {
      scopedStorage.setItem("gateway-preview-operation", id);
    } catch {
      /* the status panel still shows without auto-open */
    }
    window.location.assign(
      pageUrl(
        "workspace",
        { operationId: id, operationKind: "operation", workbenchNode: selectedKey },
        compareRefs,
      ),
    );
  };

  const handleUploadStateChange = (active: boolean) => {
    if (active) {
      resumePending.current = false;
      uploadMode.clearResumeNotice();
    }
    if (active || !resumePending.current) setUploadLocked(active);
  };

  const handlePreviewResumeFailed = () => {
    resumePending.current = false;
    scopedStorage.removeItem("gateway-preview-operation");
    setUploadLocked(false);
  };

  return {
    resumePreviewOperation,
    uploadLocked,
    resumePreviewFromOperation,
    activePreviewOperationId,
    resumeActivePreview,
    handleUploadStateChange,
    handlePreviewResumeFailed,
  };
}
