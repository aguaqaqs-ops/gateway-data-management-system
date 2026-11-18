import { ApiError } from "../../features/api/authenticated-fetch";
import type { components } from "../../features/api/generated/openapi";
import { bundleErrorTitle } from "../../features/bundle/local-bundle";
import type { WorkspaceTreeRow } from "../../features/view-model/workspace";

export type Schemas = components["schemas"];
export type SortColumn = "label" | "time";

export function shortTime(iso: string | null): string {
  return iso
    ? new Date(iso).toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      })
    : "—";
}

export function timeTitle(row: WorkspaceTreeRow): string {
  return row.kind === "workspace"
    ? "工作区最近更新时间"
    : row.kind === "submission"
      ? "提交时间"
      : "创建时间";
}

export function refKey(ref: Schemas["HistoryCompareNodeRequest"]): string {
  return `${ref.ref_kind}:${ref.ref_id}`;
}

export function historyRef(row: WorkspaceTreeRow): Schemas["HistoryCompareNodeRequest"] | null {
  return row.refId && row.refKind ? { ref_kind: row.refKind, ref_id: row.refId } : null;
}

export function pageUrl(
  page: "workspace" | "compare",
  extra: Record<string, string | null | undefined> = {},
  compareNodes: Schemas["HistoryCompareNodeRequest"][] = [],
): string {
  const params = new URLSearchParams({ page });
  for (const [key, value] of Object.entries(extra)) if (value) params.set(key, value);
  for (const node of compareNodes) params.append("compare", refKey(node));
  return `/?${params.toString()}`;
}

export function isTemporaryError(cause: unknown): boolean {
  return (
    cause instanceof TypeError ||
    (cause instanceof DOMException && cause.name === "TimeoutError") ||
    (cause instanceof ApiError && (cause.status === 429 || cause.status >= 500))
  );
}

export function messageFrom(cause: unknown): { code: string; message: string } {
  if (cause instanceof ApiError)
    return { code: cause.code ?? `HTTP_${cause.status}`, message: cause.message };
  return {
    code: cause instanceof Error ? cause.name : "REQUEST_FAILED",
    message: cause instanceof Error ? cause.message : String(cause),
  };
}

export function statusClass(tone: WorkspaceTreeRow["statusTone"]): string {
  return `tree-status tree-status--${tone}`;
}

export function showOperationForCompare(
  operationId: string | null,
  state: Schemas["HistoryCompareResultResponse"] | null,
): boolean {
  return Boolean(
    operationId && (!state || state.status === "QUEUED" || state.status === "RUNNING"),
  );
}

export function historyBundleErrorMessage(cause: unknown): string {
  if (cause instanceof ApiError) {
    const title = cause.code ? bundleErrorTitle(cause.code) : undefined;
    const head = cause.code ? `${cause.code}：` : "";
    return `${title ? `${title}。` : ""}${head}${cause.message}`;
  }
  return cause instanceof Error ? cause.message : String(cause);
}

export function fullTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString("zh-CN", { hour12: false }) : "—";
}
