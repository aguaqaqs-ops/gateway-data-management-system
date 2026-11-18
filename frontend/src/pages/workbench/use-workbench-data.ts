import { useCallback, useEffect, useState } from "react";
import type { GatewayApi } from "../../features/api/client";
import { reportConnectionStatus } from "../../features/api/connection-status";
import { currentGatewaySession } from "../../features/api/session";
import {
  getUrlOperationJobKind,
  type UploadModeSnapshot,
} from "../../features/workbench/use-upload-mode";
import { isTemporaryError, messageFrom, type Schemas } from "./workbench-helpers";

export function useWorkbenchData(
  gatewayApi: GatewayApi,
  uploadMode: UploadModeSnapshot,
  setResumeSubmitOperationId: (id: string | null) => void,
) {
  const [history, setHistory] = useState<Schemas["HistoryListResponse"] | null>(null);
  const [loadError, setLoadError] = useState<{ code: string; message: string } | null>(null);
  const [loading, setLoading] = useState(true);

  const reloadHistory = useCallback(async (): Promise<Schemas["HistoryListResponse"] | null> => {
    try {
      const loaded = await gatewayApi.listHistory();
      setHistory(loaded);
      return loaded;
    } catch {
      return null;
    }
  }, []);

  const load = useCallback(async () => {
    const session = currentGatewaySession();
    if (!session.businessProjectId || !session.gatewayDeviceExternalKey) {
      setLoadError({ code: "SESSION_REQUIRED", message: "当前会话没有业务项目与网关设备身份" });
      setHistory(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setLoadError(null);
    try {
      const snapshot = await uploadMode.refresh();
      if (!snapshot.workspace || snapshot.workspaceError) {
        // The shared refresh keeps stale state on failure; the page-level
        // load still reports it as a load error (as before B4).
        setLoadError(
          snapshot.workspaceError ?? { code: "WORKSPACE_LOAD_FAILED", message: "工作区加载失败" },
        );
        setHistory(null);
        return;
      }
      const loadedHistory = await gatewayApi.listHistory();
      setHistory(loadedHistory);
      const loadedAttempt = snapshot.attempt;
      if (snapshot.workspace.active_submit_attempt_id && loadedAttempt?.operation_id) {
        const url = new URL(window.location.href);
        const urlOperationId = url.searchParams.get("operationId");
        if (urlOperationId !== loadedAttempt.operation_id) {
          // §6.2: only a submit operation in the URL loses to the pointer;
          // a preview operation belongs to the preview flow (job_kind).
          const jobKind = urlOperationId
            ? await getUrlOperationJobKind(gatewayApi, urlOperationId)
            : null;
          if (!urlOperationId || jobKind === "backend-vnext/submit") {
            url.searchParams.set("operationId", loadedAttempt.operation_id);
            url.searchParams.set("operationKind", "operation");
            window.history.replaceState(null, "", url);
          }
        }
      } else {
        setResumeSubmitOperationId(null);
      }
      setLoadError(null);
    } catch (cause) {
      const message = messageFrom(cause);
      if (isTemporaryError(cause)) reportConnectionStatus("interrupted");
      setLoadError(message);
      setHistory(null);
    } finally {
      setLoading(false);
    }
  }, [uploadMode.refresh]);

  const reloadHead = useCallback(async (): Promise<
    Schemas["HistoryListResponse"]["head"] | null
  > => {
    const session = currentGatewaySession();
    if (!session.businessProjectId || !session.gatewayDeviceExternalKey) return null;
    try {
      const snapshot = await uploadMode.refresh();
      if (!snapshot.workspace || snapshot.workspaceError) return null;
      const loadedHistory = await gatewayApi.listHistory();
      setHistory(loadedHistory);
      return loadedHistory.head;
    } catch {
      return null;
    }
  }, [uploadMode.refresh]);

  useEffect(() => {
    void load();
    const onSessionChange = () => {
      void load();
    };
    window.addEventListener("gateway-session-change", onSessionChange);
    return () => window.removeEventListener("gateway-session-change", onSessionChange);
  }, [load]);

  return { history, loadError, loading, load, reloadHistory, reloadHead };
}
